#!/usr/bin/env python3
"""Re-verifier 1: independent replay of the FIXED headline (offset 0, K 0.75,
variant A, intrabar, XBTUSD-funded carry, BTC perp funding on the book).

Written from PREREG.md + mirror.py semantics + the task spec, NOT from
stress.Executor. Reused via public interfaces only: stress.build_spliced
(splice; spot-checked below), harness.leg_trades (the production engine
path), app.volsize.size_mult (production), carry_sleeve.simulate_carry
(the sleeve; its funding total is re-summed from the raw stamps here).

Prints my numbers next to results.json / the saved run file for each
scenario, plus the three fix checks:
  F1 (BLOCKING)  headline carry series is XBTUSD in every cell / run file
  F2 (SERIOUS)   BTC perp funding is booked; re-summed from the saved trades
  F3 (SERIOUS)   seam variants exist; pending_live reproduced from core.Book
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
CAGR = os.path.abspath(os.path.join(STRESS, "..", "cagr"))
BACKEND = os.path.abspath(os.path.join(STRESS, "..", "..", "backend"))
for p in (STRESS, CAGR, BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

import harness                                                  # noqa: E402
from harness import leg_trades, compute_indicators              # noqa: E402
from app import volsize                                         # noqa: E402
from app.engine import core                                     # noqa: E402
from app.engine.core import (Book, BookCfg, Pending, SignalCfg,  # noqa: E402
                             TradeCfg, eval_signal, process_closed_bar,
                             resolve_open_exit)
import carry_sleeve                                             # noqa: E402
import stress                                                   # noqa: E402  build_spliced only

BAR, DAY = 14_400, 86_400
NOW = 1_791_383_077                      # the seed's as-of instant (results.json meta.now_used)
BASE, LEV, W_TREND = 100_000.0, 1.5, 0.30
W = {"pullback": 1.0 - W_TREND, "trend": W_TREND}
K = 0.75
MAX_NOTIONAL, MAX_ACCOUNT_LEV = 130_000.0, 2.0
DD_PCT, DAILY_PCT = 0.30, 0.06 * max(1.0, K / 0.30)
FEE = 4.32 / 1e4
START, CARRY0, HW0 = 100_000.0, 30_000.0, 100_000.0
PAPER_SEED = {"pullback": (104_840.0, 107_860.0, 0.30), "trend": (109_343.0, 115_992.0, 0.50)}
PAPER_RT = 2 * 6.0 / 1e4
DATA = os.path.join(STRESS, "data")
RUNS = os.path.join(STRESS, "runs")
SCEN = (("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17"))


def utc(t):
    return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- funding (my loader)
def load_funding_csv(sym: str) -> list[tuple[int, float]]:
    out = []
    with open(os.path.join(DATA, f"funding_bitmex_{sym}.csv")) as fh:
        for r in csv.DictReader(fh):
            out.append((int(r["ts_ms"]) // 1000, float(r["rate_8h"])))
    out.sort()
    return out


def funding_window(sym: str, anchor_ts: int, n: int, t0: int, pre_days: int = 30):
    """stamps in [anchor-30d, anchor+n*4h] shifted by (t0-anchor): {ts_ms: rate}."""
    lo, hi = anchor_ts - pre_days * DAY, anchor_ts + n * BAR
    shift = t0 - anchor_ts
    return {(s + shift) * 1000: r for s, r in load_funding_csv(sym) if lo <= s <= hi}


# ---------------------------------------------------------------- paper book (mine)
def paper(trades, t0, seed):
    eq, peak, ddh = seed
    halt_ts = None
    out = []
    margin_min, margin_at_halt = None, None
    for t in trades:
        if t.exit_ts is not None and t.exit_ts < t0:
            continue
        if halt_ts is not None and t.entry_ts > halt_ts:
            continue
        out.append(t)
        if t.exit_ts is None:
            continue
        q = round(eq / t.entry_price, 6)
        sgn = 1 if t.side == "L" else -1
        eq += q * (t.exit_price - t.entry_price) * sgn - q * t.entry_price * PAPER_RT
        peak = max(peak, eq)
        m = eq - peak * (1 - ddh)
        if halt_ts is None and (margin_min is None or m < margin_min):
            margin_min = m
        if halt_ts is None and eq / peak - 1 <= -ddh:
            halt_ts, margin_at_halt = t.exit_ts, m
    return out, dict(halt=halt_ts, eq=eq, margin_min=margin_min, margin_at_halt=margin_at_halt)


# ---------------------------------------------------------------- executor (mine)
def replay(bars, pub, carry_val, fund_ms, k=K):
    seam = bars.seam
    path = bars[seam:]
    closes_all = {b.ts: b.close for b in bars}
    stamps = {}                                   # close ts -> [rates]
    for ms, r in fund_ms.items():
        s = ms // 1000
        c = -(-s // BAR) * BAR
        stamps.setdefault(c, []).append(r)
    by_entry = {leg: {t.entry_ts: t for t in pub[leg]} for leg in pub}
    cash = START - CARRY0
    pos = {}                                      # leg -> dict
    hw, day_start = HW0, START
    halted = None
    fees = funding = 0.0
    fund_leg = {"pullback": 0.0, "trend": 0.0}
    n_stamps = 0
    eq_tot, eq_btc, worst_l, ts_l, dstart_l = [], [], [], [], []
    trades = []
    need_remirror = True

    def unreal(px):
        return sum(p["q"] * (px - p["px"]) * p["s"] for p in pos.values())

    def equity(px, cv):
        return cash + unreal(px) + cv

    def open_pos(leg, t, px, ts, kind):
        nonlocal cash, fees
        m = volsize.size_mult(closes_all, t.entry_ts - BAR)["m"]
        want = min(k, 0.75) * LEV * W[leg] * BASE * m / px
        other = sum(abs(p["q"]) for l, p in pos.items() if l != leg)
        room = max(0.0, min(MAX_NOTIONAL, MAX_ACCOUNT_LEV * BASE) / px - other)
        q = min(want, room)
        assert q >= want - 1e-9, f"cap bound {leg} {utc(ts)}"
        if q <= 0:
            return
        f = FEE * q * px
        cash -= f
        fees += f
        pos[leg] = dict(q=q, px=px, s=1 if t.side == "L" else -1, side=t.side, t=t, ts=ts,
                        efee=f, fund=0.0, kind=kind)

    def close_pos(leg, px, ts, why):
        nonlocal cash, fees
        p = pos.pop(leg)
        g = p["q"] * (px - p["px"]) * p["s"]
        f = FEE * p["q"] * px
        cash += g - f
        fees += f
        trades.append(dict(leg=leg, side=p["side"], entry_ts=p["ts"], exit_ts=ts, qty=p["q"],
                           entry_px=p["px"], exit_px=px, gross=g, fees=f + p["efee"],
                           funding=p["fund"], pnl=g - f - p["efee"] + p["fund"], why=why))

    for j, b in enumerate(path):
        cv = float(carry_val[j])
        eo = equity(b.open, cv)
        if j > 0 and b.ts % DAY == 0:
            if halted == "DAILY_LOSS":
                if eo < hw - DD_PCT * BASE:
                    halted = "DRAWDOWN"
                else:
                    halted = None
                    need_remirror = True
            day_start = eo
        hw = max(hw, eo)
        # exits
        for leg in list(pos):
            t = pos[leg]["t"]
            if t.exit_ts is not None and t.exit_ts <= b.ts:
                if t.reason == "STOP":
                    fill = min(t.exit_price, b.open) if pos[leg]["s"] > 0 else max(t.exit_price, b.open)
                else:
                    fill = t.exit_price
                close_pos(leg, fill, b.ts, t.reason)
        # entries
        if halted is None:
            if need_remirror:
                need_remirror = False
                for leg in ("pullback", "trend"):
                    if leg in pos:
                        continue
                    for t in pub[leg]:
                        if t.entry_ts < b.ts and (t.exit_ts is None or t.exit_ts >= b.ts):
                            if t.exit_ts == b.ts and t.reason != "STOP":
                                break
                            open_pos(leg, t, b.open, b.ts, "remirror")
                            if t.exit_ts == b.ts and leg in pos:
                                fill = min(t.exit_price, b.open) if t.side == "L" else max(t.exit_price, b.open)
                                close_pos(leg, fill, b.ts, "STOP")
                            break
            for leg in ("pullback", "trend"):
                if leg in pos:
                    continue
                t = by_entry[leg].get(b.ts)
                if t is not None:
                    open_pos(leg, t, t.entry_price, b.ts, "engine")
        # intrabar halt test at the adverse extreme (net position linear in px)
        worst = None
        net = sum(p["q"] * p["s"] for p in pos.values())
        if abs(net) > 1e-12:
            adverse, favour = (b.low, b.high) if net > 0 else (b.high, b.low)
            worst = equity(adverse, cv)
            hw = max(hw, equity(favour, cv))
            l_dd, l_day = hw - DD_PCT * BASE, day_start - DAILY_PCT * BASE
            line = max(l_dd, l_day)
            if halted is None and (equity(b.open, cv) < line or worst < line):
                # the executor polls every 20 s: the higher line is met first
                if equity(b.open, cv) < line:
                    kind = "DRAWDOWN" if equity(b.open, cv) < l_dd else "DAILY_LOSS"
                    line = l_dd if kind == "DRAWDOWN" else l_day
                else:
                    kind = "DRAWDOWN" if l_dd >= l_day else "DAILY_LOSS"
                p_star = (line - cash - cv + sum(p["q"] * p["px"] * p["s"] for p in pos.values())) / net
                px = min(p_star, b.open) if net > 0 else max(p_star, b.open)
                for leg in list(pos):
                    close_pos(leg, px, b.ts, "HALT_" + kind)
                halted = kind
                print(f"    !! executor halt {kind} at {utc(b.ts)} fill {px:,.0f}")
                if kind == "DAILY_LOSS" and equity(px, cv) < hw - DD_PCT * BASE:
                    halted = "DRAWDOWN"
        # funding at the close on what is still held
        for r in stamps.get(b.ts + BAR, []):
            for leg, p in pos.items():
                pay = -p["s"] * p["q"] * b.close * r
                cash += pay
                p["fund"] += pay
                funding += pay
                fund_leg[leg] += pay
                n_stamps += 1
        ec = equity(b.close, cv)
        if halted is None:
            l_dd, l_day = hw - DD_PCT * BASE, day_start - DAILY_PCT * BASE
            if ec < l_dd or ec < l_day:
                kind = "DRAWDOWN" if ec < l_dd else "DAILY_LOSS"
                for leg in list(pos):
                    close_pos(leg, b.close, b.ts, "HALT_" + kind)
                halted = kind
                ec = equity(b.close, cv)
                print(f"    !! executor halt {kind} at close {utc(b.ts)}")
        hw = max(hw, ec)
        ts_l.append(b.ts)
        eq_tot.append(ec)
        eq_btc.append(ec - cv)
        worst_l.append(ec if worst is None else min(worst, ec))
        dstart_l.append(day_start)
    # open positions at the end
    for leg, p in pos.items():
        g = p["q"] * (path[-1].close - p["px"]) * p["s"]
        trades.append(dict(leg=leg, side=p["side"], entry_ts=p["ts"], exit_ts=None, qty=p["q"],
                           entry_px=p["px"], exit_px=None, gross=g, fees=p["efee"], funding=p["fund"],
                           pnl=g - p["efee"] + p["fund"], why="OPEN"))
    return dict(ts=ts_l, tot=eq_tot, btc=eq_btc, worst=worst_l, day_start=dstart_l, trades=trades,
                fees=fees, funding=funding, fund_leg=fund_leg, n_stamps=n_stamps, hw=hw, halted=halted)


def max_dd(start, eq):
    p = np.concatenate([[start], np.asarray(eq)])
    return float((p / np.maximum.accumulate(p) - 1).min())


def bal(ts, eq, t0, d):
    ts = np.asarray(ts)
    i = np.searchsorted(ts, t0 + d * DAY, side="right") - 1
    return float(eq[i]), bool(ts[i] == t0 + d * DAY)


def worst_day_c2c(ts, eq, start):
    days = {}
    for t, e in zip(ts, eq):
        days[utc(t)[:10]] = e
    prev, w = start, (None, 0.0)
    for d, e in days.items():
        if e - prev < w[1]:
            w = (d, e - prev)
        prev = e
    return w


# ---------------------------------------------------------------- pending_live (mine, from core.Book)
def pullback_pending_live(bars):
    """Continue the production Book from the live 08:00Z snapshot: flat, long
    limit at the last closed bar's close, signal_ts that bar."""
    tc, scfg = TradeCfg(taker_fee_bps=4.32), SignalCfg()
    inds = compute_indicators(bars, 20)
    book = Book(cfg=BookCfg(name="pullback", sizing="fixed", strategy="pullback", trail_atr=5.0,
                            leverage=1.0, cap=1.0, start_equity=1.0, dd_halt=1e9))
    for i in range(210, len(bars)):
        if i == bars.seam:
            last, il = bars[i - 1], inds[i - 1]
            book.position = None
            book.pending = Pending(side="L", limit=last.close, signal_ts=last.ts, atr_signal=il.atr14 or 0.0)
        resolve_open_exit(book, bars[i], tc)
        process_closed_bar(book, bars[i], inds[i], scfg, tc, eval_signal(bars[i], inds[i], scfg))
    out = [harness.Trade("pullback", t.side, t.entry_ts, t.entry_price, t.exit_ts, t.exit_price, t.exit_reason)
           for t in book.trades]
    if book.position is not None:
        p = book.position
        out.append(harness.Trade("pullback", p.side, p.entry_ts, p.entry_price, None, None, "OPEN"))
    return out


# ---------------------------------------------------------------- main
def main():
    res = json.load(open(os.path.join(STRESS, "results.json")))
    full_btc = harness.load_bars("btcusd")
    out = {}
    print("== F1 (BLOCKING): carry funding source in EVERY headline cell of results.json")
    bad = []
    for scen, _ in SCEN:
        S = res["scenarios"][scen]
        for Kk, byoff in S["runs"].items():
            for tag, s in byoff.items():
                if s["carry"]["funding_source"] != "XBTUSD" or s["carry"]["funding_quanto"]:
                    bad.append((scen, Kk, tag, s["carry"]["funding_source"]))
                if s["btc_funding"]["source"] != "XBTUSD" or not s["btc_funding"]["modelled"]:
                    bad.append((scen, Kk, tag, "btc_funding " + str(s["btc_funding"])))
                if s["file"] and "carryXBTUSD_bfund" not in s["file"]:
                    bad.append((scen, Kk, tag, s["file"]))
        for Kk, byoff in S["runs_quanto"].items():
            for tag, s in byoff.items():
                if s["carry"]["funding_source"] != "ETHUSD" or not s["carry"]["funding_quanto"]:
                    bad.append((scen, Kk, tag, "quanto col " + s["carry"]["funding_source"]))
    print("   headline cells:", sum(len(v) for S in res["scenarios"].values() for v in S["runs"].values()),
          " non-XBTUSD / unflagged:", bad or "none")
    print("   meta.headline_funding =", res["meta"]["headline_funding"], "; quanto_label =", res["meta"]["quanto_label"])
    tbl = "\n".join(res["table"])
    print("   table header names XBTUSD:", "carry funded by BitMEX XBTUSD" in tbl,
          "; quanto column labelled 'not the live venue':", "not the live venue's instrument" in tbl)

    for scen, anchor in SCEN:
        print(f"\n==== {scen}  anchor {anchor}  offset 0  K {K}")
        bars = stress.build_spliced("btcusd", anchor, 12, 0, now=NOW)
        bars_e = stress.build_spliced("ethusd", anchor, 12, 0, now=NOW)
        n = len(bars.path)
        # splice spot-checks (my own): first path close == last real close; returns == analogue's
        a_ts = bars.anchor_ts
        win = [b for b in full_btc if a_ts <= b.ts < a_ts + n * BAR]
        assert len(win) == n and abs(bars.path[0].close - bars[bars.seam - 1].close) < 1e-6
        rr = max(abs((bars.path[j].close / bars.path[j - 1].close) - (win[j].close / win[j - 1].close))
                 for j in range(1, n))
        assert rr < 1e-9, rr
        assert all(bars.path[j].ts == bars.t0 + j * BAR for j in range(n))
        print(f"   splice ok: {n} path bars from {utc(bars.t0)}, returns == analogue (max |d| {rr:.1e})")
        # funding (my loader) and carry (sleeve, public API)
        fx = funding_window("XBTUSD", a_ts, n, bars.t0)
        cr = carry_sleeve.simulate_carry({b.ts: b.close for b in bars_e.path}, fx,
                                         dict(on=True, qty=11.096, entry_px=2703.9),
                                         notional=30_000.0, usdc_backing=70_000.0, liq_buffer=0.15)
        # re-sum the sleeve's funding from the raw stamps and its own on/qty path
        idx = {t: i for i, t in enumerate(cr.ts)}
        eth_c = [b.close for b in bars_e.path]
        f_re = 0.0
        for ms, r in fx.items():
            s = ms // 1000
            j = idx.get(s - BAR)
            if j is not None and cr.on[j] and cr.qty[j] > 0:
                f_re += cr.qty[j] * eth_c[j] * r
        print(f"   carry (XBTUSD proxy): 12m value {cr.value[-1]:,.2f}; funding re-summed {f_re:,.2f} "
              f"vs sleeve {cr.funding_cum[-1]:,.2f}; flips {len(cr.flips())}; on {100 * sum(cr.on) / n:.1f}%")
        # engine (production path) + my paper book
        tc = TradeCfg(taker_fee_bps=4.32)
        raw = {"pullback": leg_trades(bars, "pullback", scfg=SignalCfg(), tcfg=tc, leg="pullback"),
               "trend": leg_trades(bars, "donchian", trail_atr=5.0, tcfg=tc, leg="trend")}
        pub, info = {}, {}
        for leg in raw:
            pub[leg], info[leg] = paper(raw[leg], bars.t0, PAPER_SEED[leg])
        r = replay(bars, pub, cr.value, fx)
        theirs = res["scenarios"][scen]["runs"]["K0.75"]["off+0"]
        run = json.load(open(os.path.join(STRESS, theirs["file"])))
        # compare
        mine_bal = {d: bal(r["ts"], r["tot"], bars.t0, d) for d in (91, 182, 273, 365)}
        mdd = max_dd(START, r["tot"])
        wd = worst_day_c2c(r["ts"], r["tot"], START)
        print(f"   {'':14s} {'mine':>12s} {'results.json':>13s} {'diff':>9s}")
        for d in (91, 182, 273, 365):
            print(f"   {str(d) + 'd' + ('' if mine_bal[d][1] else '*'):14s} {mine_bal[d][0]:>12,.2f} "
                  f"{theirs['balances'][str(d)]:>13,.2f} {mine_bal[d][0] - theirs['balances'][str(d)]:>+9.2f}")
        print(f"   {'maxDD':14s} {mdd:>12.4%} {theirs['max_dd']:>13.4%} {mdd - theirs['max_dd']:>+9.4%}")
        print(f"   {'final':14s} {r['tot'][-1]:>12,.2f} {theirs['final_equity']:>13,.2f}")
        print(f"   {'BTC funding':14s} {r['funding']:>12,.2f} {theirs['btc_funding']['total']:>13,.2f}  "
              f"by leg mine {r['fund_leg']}  stamps {r['n_stamps']} / {theirs['btc_funding']['stamps']}")
        print(f"   {'fees':14s} {r['fees']:>12,.2f} {theirs['fees']:>13,.2f}   trades {len([t for t in r['trades'] if t['why'] != 'OPEN'])} / {theirs['n_trades']}")
        print(f"   {'worst day c2c':14s} {wd[1]:>12,.2f} {theirs['worst_day']['usd']:>13,.2f}  ({wd[0]} / {theirs['worst_day']['date']})")
        print(f"   {'hw_end':14s} {r['hw']:>12,.2f} {theirs['hw_end']:>13,.2f}   exec halted: {r['halted']} / {theirs['halts']}")
        d_tot = np.abs(np.asarray(r["tot"]) - np.asarray(run["equity_total"])).max()
        d_btc = np.abs(np.asarray(r["btc"]) - np.asarray(run["equity_btc"])).max()
        d_w = np.abs(np.asarray(r["worst"]) - np.asarray(run["worst_intrabar_equity"])).max()
        d_c = np.abs(np.asarray(cr.value) - np.asarray(run["carry_value"])).max()
        print(f"   curves vs run file: max|d| total {d_tot:.3f}  btc {d_btc:.3f}  worst-intrabar {d_w:.3f}  carry {d_c:.3f}")
        for leg in ("pullback", "trend"):
            e = theirs["engine_halts_info"][leg]
            print(f"   paper {leg}: halt mine {utc(info[leg]['halt']) if info[leg]['halt'] else None} / theirs {e['date']}; "
                  f"margin_at_halt mine {info[leg]['margin_at_halt']} / theirs {e['margin_at_halt']}; "
                  f"min margin mine {info[leg]['margin_min']:+,.2f} / theirs {e['min_margin']:+,.2f}")
        # F2: funding re-summed from the SAVED trades with the T7 rule (held through the stamp)
        closes = dict(run["spliced_closes"])
        f7 = 0.0
        f7_leg = {"pullback": 0.0, "trend": 0.0}
        for ms, rate in fx.items():
            s = ms // 1000
            if s < bars.t0 + BAR:
                continue
            px = closes.get(s - BAR)
            if px is None:
                continue
            for tr in run["trades"]:
                if tr["entry_ts"] < s and (tr["exit_ts"] is None or tr["exit_ts"] + BAR > s):
                    pay = -(1 if tr["side"] == "L" else -1) * tr["qty"] * px * rate
                    f7 += pay
                    f7_leg[tr["leg"]] += pay
        ff = sum(tr["funding"] for tr in run["trades"])
        print(f"   F2: T7-rule funding from saved trades {f7:,.2f} (by leg {f7_leg}) vs run total {run['btc_funding_total']:,.2f}; "
              f"sum of per-trade 'funding' {ff:,.2f}; cum[-1] {run['btc_funding_cum'][-1]:,.2f}; "
              f"sum(pnl) - (btc_end - 70k) = {sum(t['pnl'] for t in run['trades']) - (run['equity_btc'][-1] - 70_000):+.2f}")
        # funding up to the 365-day bar vs the 'without' sensitivity
        nf = res["scenarios"][scen]["sensitivity"]["no_btc_funding"]["K0.75"]["balances"]["365"]
        i365 = np.searchsorted(np.asarray(run["ts"]), bars.t0 + 365 * DAY, side="right") - 1
        print(f"   F2: 12m with {theirs['balances']['365']:,.2f} / without {nf:,.2f} = {theirs['balances']['365'] - nf:+,.2f}; "
              f"funding cum at that bar {run['btc_funding_cum'][i365]:+,.2f}")
        # F3: seam variants
        pl_mine = pullback_pending_live(bars)
        pl_theirs = stress.engine_trades(bars, "pending_live")["pullback"]
        same = [(t.side, t.entry_ts, round(t.entry_price, 4), t.exit_ts, t.exit_price and round(t.exit_price, 4), t.reason) for t in pl_mine] == \
               [(t.side, t.entry_ts, round(t.entry_price, 4), t.exit_ts, t.exit_price and round(t.exit_price, 4), t.reason) for t in pl_theirs]
        live_first = [t for t in pl_mine if t.exit_ts is None or t.exit_ts >= bars.t0][0]
        pub_pl = dict(pub)
        pub_pl["pullback"], info_pl = paper(pl_mine, bars.t0, PAPER_SEED["pullback"])
        r_pl = replay(bars, pub_pl, cr.value, fx)
        sr = res["scenarios"][scen]["seam_range"]["K0.75"]
        print(f"   F3: pending_live trade list identical to stress.engine_trades: {same}; first live trade "
              f"{live_first.side} {utc(live_first.entry_ts)} @ {live_first.entry_price:,.2f} ({live_first.reason})")
        print(f"   F3: pending_live 12m mine {bal(r_pl['ts'], r_pl['tot'], bars.t0, 365)[0]:,.2f} / theirs {sr['by_variant']['pending_live']:,.2f}; "
              f"S3 halt mine {utc(info_pl['halt']) if info_pl['halt'] else None} margin {info_pl['margin_at_halt']}; "
              f"csv-variant S3 margin {info['pullback']['margin_at_halt']} ({(info['pullback']['margin_at_halt'] or 0) / 107_860:+.2%} of peak)")
        seam_tr = [t for t in raw["pullback"] if t.entry_ts < bars.t0 and (t.exit_ts is None or t.exit_ts >= bars.t0)]
        ds = [t for t in raw["pullback"] if t not in seam_tr]
        pub_ds = dict(pub)
        pub_ds["pullback"], info_ds = paper(ds, bars.t0, PAPER_SEED["pullback"])
        r_ds = replay(bars, pub_ds, cr.value, fx)
        print(f"   F3: drop_seam 12m mine {bal(r_ds['ts'], r_ds['tot'], bars.t0, 365)[0]:,.2f} / theirs {sr['by_variant']['drop_seam']:,.2f}; "
              f"S3 halt {utc(info_ds['halt']) if info_ds['halt'] else None}; seam trade(s) {[(t.side, utc(t.entry_ts), t.entry_price) for t in seam_tr]}")
        out[scen] = dict(balances={d: mine_bal[d][0] for d in mine_bal}, max_dd=mdd, final=r["tot"][-1],
                         funding=r["funding"], fees=r["fees"], carry_12m=cr.value[-1],
                         pending_live_12m=bal(r_pl["ts"], r_pl["tot"], bars.t0, 365)[0],
                         drop_seam_12m=bal(r_ds["ts"], r_ds["tot"], bars.t0, 365)[0],
                         d_curve_total=float(d_tot), f7=f7)
    json.dump(out, open(os.path.join(HERE, "replay_out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
