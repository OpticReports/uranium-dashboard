"""Independent re-implementation of the stress study's PORTFOLIO + GUARD layer
(PREREG.md "Portfolio emulation" + btc-executor/app/mirror.py halt code),
written WITHOUT reading stress.py's portfolio code.

Inputs per run: the saved run JSON (anchor/scale/t0, engine trade lists =
harness.leg_trades output), the raw Bitstamp 4h CSVs (to rebuild the spliced
O/H/L/C bars - the run JSON only saved closes), BitMEX funding CSVs, and
carry_sleeve.simulate_carry called from its public interface.

Usage: python3 verify.py [COVID|2008|1999] [K]   (default: all 3 x {0.75,0.30})
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
CAGR = os.path.abspath(os.path.join(STRESS, "..", "cagr"))
BACKEND = os.path.abspath(os.path.join(STRESS, "..", "..", "backend"))
for p in (STRESS, CAGR, BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.volsize import size_mult            # noqa: E402  production vol target
import carry_sleeve                           # noqa: E402  study's sleeve (public API)

BAR = 14_400
DAY = 86_400

# ---- the deployed book (PREREG table / config.py / mirror.py) ----
BASE = 100_000.0           # SIZING_BASE_USD (fixed)
LEV = 1.5                  # LIVE_LEV
W_TREND = 0.30             # LIVE_W_TREND
MAX_NOTIONAL = 130_000.0
MAX_ACCOUNT_LEV = 2.0
DD_HALT_PCT = 0.30
DAILY_LOSS_PCT = 0.06
DAILY_LOSS_REF_K = 0.30
FEE = 4.32 / 1e4           # per side, every fill
START_EQUITY = 100_000.0
CARRY_NOTIONAL = 30_000.0
USDC_BACKING = 70_000.0
HW_SEED = 100_000.0
PAPER_SEED = {"pullback": dict(equity=104_840.0, peak=107_860.0, dd_halt=0.30),
              "trend": dict(equity=109_343.0, peak=115_992.0, dd_halt=0.50)}
PAPER_FEE_RT = 12.0 / 1e4  # engine paper book: 2 x TradeCfg.taker_fee_bps (6.0)
CARRY_START = {"on": True, "qty": 11.096, "entry_px": 2703.9}
RESUME_DAYS_B = 7


def utc(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def leg_w(leg: str) -> float:
    return W_TREND if leg == "trend" else 1.0 - W_TREND


# --------------------------------------------------------------------------
# data: rebuild the spliced O/H/L/C bars from the raw CSV + the run's anchor
# --------------------------------------------------------------------------
def read_bars(path: str, now: float) -> list[tuple]:
    out = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            t = int(r["ts_open_unix"])
            if t + BAR > now:
                continue
            out.append((t, float(r["open"]), float(r["high"]), float(r["low"]),
                        float(r["close"]), float(r["volume"])))
    return out


def splice(bars: list[tuple], anchor_ts: int, t0: int, n_path: int, last_real_ts: int):
    """history (real, ts <= last_real_ts) + path (analogue from anchor, scaled
    so the anchor bar's close == today's close, placed on today's grid)."""
    hist = [b for b in bars if b[0] <= last_real_ts]
    today_close = hist[-1][4]
    idx = {b[0]: i for i, b in enumerate(bars)}
    a = idx[anchor_ts]
    scale = today_close / bars[a][4]
    path = []
    for k in range(n_path):
        t, o, h, l, c, v = bars[a + k]
        assert t == anchor_ts + k * BAR, "analogue window has a gap"
        path.append((t0 + k * BAR, o * scale, h * scale, l * scale, c * scale, v))
    return hist, path, scale, today_close


# --------------------------------------------------------------------------
# 1) engine paper-book halt emulation (core.py _size / _close_position)
# --------------------------------------------------------------------------
def paper_book(trades: list[dict], seed: dict) -> dict:
    eq, peak, ddh = seed["equity"], seed["peak"], seed["dd_halt"]
    halted, halt_ts, eq_halt = False, None, None
    published, path = [], []
    for t in trades:
        if halted:
            break                         # one-way: nothing published after the halt
        published.append(t)
        if t["exit_ts"] is None:
            break
        notional = min(eq * 1.0, 1.0 * eq)          # fixed lev 1.0, cap 1.0
        qty = round(notional / t["entry_price"], 6)
        notional = qty * t["entry_price"]
        sgn = 1.0 if t["side"] == "L" else -1.0
        pnl = qty * (t["exit_price"] - t["entry_price"]) * sgn - notional * PAPER_FEE_RT
        eq += pnl
        peak = max(peak, eq)
        dd = eq / peak - 1.0
        path.append((t["exit_ts"], round(eq, 2), round(dd, 4)))
        if dd <= -ddh:
            halted, halt_ts, eq_halt = True, t["exit_ts"], eq
    return dict(halted=halted, halt_ts=halt_ts, halt_date=utc(halt_ts) if halt_ts else None,
                equity_at_halt=eq_halt, published=published, dropped=len(trades) - len(published),
                equity_end=eq, peak_end=peak, path=path)


# --------------------------------------------------------------------------
# 2-4) executor replay with the halt layer, carry inside the same account
# --------------------------------------------------------------------------
def replay(path, closes_all: dict, pub: dict, K: float, carry_value: list,
           variant: str = "A", intrabar: bool = True, today_close: float = 1.0,
           hw_intrabar: bool = False, worst_mode: str = "linear") -> dict:
    f = FEE
    dpct = DAILY_LOSS_PCT * max(1.0, K / DAILY_LOSS_REF_K)
    cap_notional = min(MAX_NOTIONAL, MAX_ACCOUNT_LEV * BASE)

    # engine trades keyed by entry / exit bar
    entries: dict[int, list] = {}
    for leg, lst in pub.items():
        for t in lst:
            entries.setdefault(t["entry_ts"], []).append((leg, t))

    def engine_open_at(ts: int) -> list:
        """engine positions HELD when bar `ts` opens (entered strictly before)."""
        out = []
        for leg, lst in pub.items():
            for t in lst:
                if t["entry_ts"] < ts and (t["exit_ts"] is None or t["exit_ts"] >= ts):
                    out.append((leg, t))
        return out

    def mult_for(entry_ts: int) -> float:
        sig = entry_ts - BAR
        return float(size_mult(closes_all, sig)["m"])

    def leg_qty(leg: str, px: float, mult: float, pos: dict) -> float:
        want = K * LEV * leg_w(leg) * BASE * mult / px
        other = sum(abs(p["qty"]) for n, p in pos.items() if n != leg)
        room = max(0.0, cap_notional / px - other)
        if want > room:
            want = room
        return round(want, 8)

    cash = START_EQUITY - CARRY_NOTIONAL       # the BTC book's cash (USDC)
    pos: dict[str, dict] = {}                  # leg -> position
    hw = HW_SEED
    halted: str | None = None
    halt_until: int | None = None              # variant B resume bar
    day_key = None
    day_start = START_EQUITY
    fees = 0.0
    n_entries = 0
    trades_out, events, halts = [], [], []
    eq_tot, eq_btc, worst_tot, bench = [], [], [], []
    clamps = []

    def btc_equity_at(px: float, cash_: float, pos_: dict) -> float:
        return cash_ + sum(p["qty"] * (px - p["entry_px"]) * p["sgn"] for p in pos_.values())

    def open_position(leg, t, px, ts, kind, mult):
        nonlocal cash, fees, n_entries
        q = leg_qty(leg, px, mult, pos)
        if q <= 0:
            return
        fee = f * q * px
        cash -= fee
        fees += fee
        n_entries += 1
        pos[leg] = dict(leg=leg, side=t["side"], sgn=1.0 if t["side"] == "L" else -1.0,
                        qty=q, entry_px=px, entry_ts=ts, efee=fee, trade=t, kind=kind,
                        mult=mult, notional=q * px)

    def close_position(leg, px, ts, reason):
        nonlocal cash, fees
        p = pos.pop(leg)
        gross = p["qty"] * (px - p["entry_px"]) * p["sgn"]
        fee = f * p["qty"] * px
        cash += gross - fee
        fees += fee
        trades_out.append(dict(leg=leg, side=p["side"], entry_ts=p["entry_ts"], entry_px=p["entry_px"],
                               exit_ts=ts, exit_px=px, qty=p["qty"], notional=p["notional"],
                               size_mult=p["mult"], gross=gross, fees=fee + p["efee"],
                               pnl=gross - fee - p["efee"], reason=reason, kind=p["kind"],
                               engine_entry_ts=p["trade"]["entry_ts"], engine_exit_ts=p["trade"]["exit_ts"]))

    def remirror(ts, o, label):
        for leg, t in engine_open_at(ts):
            if t["exit_ts"] == ts and t["reason"] in ("SIGNAL", "TIME"):
                continue   # the engine is exiting at this very open: flat target
            mult = mult_for(t["entry_ts"])
            open_position(leg, t, o, ts, "remirror", mult)
            if leg in pos:
                events.append((ts, "REMIRROR", f"{leg} {t['side']} {pos[leg]['qty']:.5f} BTC at open {o:.0f} ({label}) mult {mult}",
                               round(btc_equity_at(o, cash, pos) + carry_value[len(eq_tot)], 2)))

    prev_close_eq = START_EQUITY
    margins = {"dd": (math.inf, None, None, None), "dl": (math.inf, None, None, None)}
    for i, (ts, o, h, l, c, v) in enumerate(path):
        cv = carry_value[i]
        # ---- UTC day rollover (mirror._roll_day) at a 00:00 bar open ----
        dk = ts // DAY
        if dk != day_key:
            if day_key is not None and halted == "DAILY_LOSS":
                if prev_close_eq < hw - DD_HALT_PCT * BASE:
                    halted = "DRAWDOWN"
                    halt_until = (ts + RESUME_DAYS_B * DAY) if variant == "B" else None
                    halts.append(dict(kind="DRAWDOWN", ts=ts, date=utc(ts), equity=prev_close_eq,
                                      note="relabel at rollover (daily halt not re-armed)"))
                else:
                    halted = None
                    events.append((ts, "REARM", "DAILY_LOSS cleared at UTC rollover", prev_close_eq))
                    remirror(ts, o, "re-arm")
            day_key = dk
            day_start = prev_close_eq
        if halted == "DRAWDOWN" and variant == "B" and halt_until is not None and ts >= halt_until:
            halted, halt_until = None, None
            events.append((ts, "RESUME", "manual resume after 7d (variant B)", prev_close_eq))
            remirror(ts, o, "resume")
        hw = max(hw, prev_close_eq)
        if i == 0:
            remirror(ts, o, "t0")
        # ---- exits first ----
        for leg in list(pos):
            t = pos[leg]["trade"]
            if t["exit_ts"] == ts:
                px = t["exit_price"]
                if pos[leg]["kind"] == "remirror" and t["reason"] == "STOP" and pos[leg]["entry_ts"] == ts:
                    # mirrored at the open; the resting stop fills at the level, or at the open if through it
                    px = t["exit_price"]
                close_position(leg, px, ts, t["reason"])
        # ---- entries (not while halted) ----
        if halted is None:
            for leg, t in entries.get(ts, []):
                if leg in pos:
                    continue
                mult = mult_for(ts)
                want = K * LEV * leg_w(leg) * BASE * mult / t["entry_price"]
                open_position(leg, t, t["entry_price"], ts, "engine", mult)
                if leg in pos and pos[leg]["qty"] < want - 1e-6:
                    clamps.append((ts, leg, want, pos[leg]["qty"]))
        # ---- intrabar worst + guard ----
        eq_open = btc_equity_at(o, cash, pos) + cv
        if worst_mode == "linear":
            w_btc = min(btc_equity_at(l, cash, pos), btc_equity_at(h, cash, pos))
        else:   # per-position adverse extreme (longs at the low, shorts at the high)
            w_btc = cash + sum(p["qty"] * ((l if p["sgn"] > 0 else h) - p["entry_px"]) * p["sgn"] for p in pos.values())
        worst = w_btc + cv
        close_eq = btc_equity_at(c, cash, pos) + cv
        if halted is None and pos:
            dd_line = hw - DD_HALT_PCT * BASE
            dl_line = day_start - dpct * BASE
            test_eq = worst if intrabar else close_eq
            if test_eq < dd_line or test_eq < dl_line:
                # first cross: the higher line is hit first on the way down
                if dd_line >= dl_line:
                    kind, level = "DRAWDOWN", dd_line
                else:
                    kind, level = "DAILY_LOSS", dl_line
                if not intrabar:
                    level = close_eq
                # fill at the line (gap through it: at the open)
                net = sum(p["qty"] * p["sgn"] for p in pos.values())
                if eq_open < level or abs(net) < 1e-12:
                    px_fill = o if intrabar else c
                else:
                    px_fill = (level - cv - cash + sum(p["qty"] * p["entry_px"] * p["sgn"] for p in pos.values())) / net
                    px_fill = min(max(px_fill, l), h)
                for leg in list(pos):
                    close_position(leg, px_fill, ts, "HALT_" + kind)
                after = cash + cv
                halted = kind
                if kind == "DAILY_LOSS" and after < dd_line:
                    halted = "DRAWDOWN"
                    halts.append(dict(kind="DAILY_LOSS->DRAWDOWN", ts=ts, date=utc(ts), equity=after,
                                      px=px_fill, line=level))
                else:
                    halts.append(dict(kind=kind, ts=ts, date=utc(ts), equity=after, px=px_fill, line=level))
                if halted == "DRAWDOWN":
                    halt_until = (ts + RESUME_DAYS_B * DAY) if variant == "B" else None
                worst = min(worst, after)
                close_eq = after
        wtest = min(worst, close_eq)    # every bar: a stopped-out bar ends flat but its close is still polled
        m_dd = wtest - (hw - DD_HALT_PCT * BASE)
        m_dl = wtest - (day_start - dpct * BASE)
        if m_dd < margins["dd"][0]:
            margins["dd"] = (m_dd, ts, wtest, hw)
        if m_dl < margins["dl"][0]:
            margins["dl"] = (m_dl, ts, wtest, day_start)
        eq_tot.append(close_eq)
        eq_btc.append(close_eq - cv)
        worst_tot.append(min(worst, close_eq))
        bench.append(START_EQUITY * c / today_close)
        prev_close_eq = close_eq
        if hw_intrabar:
            hw = max(hw, btc_equity_at(h if sum(p["sgn"] for p in pos.values()) >= 0 else l, cash, pos) + cv)
    # still-open positions: leave marked (same as the builder's n_open)
    return dict(ts=[b[0] for b in path], equity_total=eq_tot, equity_btc=eq_btc,
                worst=worst_tot, bench=bench, trades=trades_out, events=events, halts=halts,
                fees=fees, n_entries=n_entries, n_open=len(pos), hw_end=max(hw, prev_close_eq), clamps=clamps,
                margins=margins)


def max_dd(curve: list, start: float, lows: list | None = None) -> float:
    """max drawdown of `curve` (closes) from its running peak (start included);
    with `lows`, the intrabar worst of each bar against the running peak of
    the CLOSES up to and including that bar."""
    peak, worst = start, 0.0
    for i, e in enumerate(curve):
        peak = max(peak, e)
        x = lows[i] if lows is not None else e
        worst = min(worst, x / peak - 1.0)
    return worst


def worst_utc_day(ts: list, eq: list, worst: list, start: float) -> dict:
    """min over days of (equity_worst_in_day - day_start) in $, day start = the
    equity at the first 00:00 poll = the previous bar's close."""
    best = None
    prev = start
    day_start, dk, dmin = start, None, None
    for t, e, w in zip(ts, eq, worst):
        k = t // DAY
        if k != dk:
            if dk is not None and (best is None or dmin - day_start < best["usd"]):
                best = dict(day=datetime.fromtimestamp(dk * DAY, tz=timezone.utc).strftime("%Y-%m-%d"),
                            usd=dmin - day_start, from_equity=day_start, to_worst=dmin)
            dk, day_start, dmin = k, prev, w
        dmin = min(dmin, w)
        prev = e
    return best


def run(scenario: str, K: float, variant="A", intrabar=True, engine_halts=True,
        hw_intrabar=False, worst_mode="linear", funding_src=None, verbose=True) -> dict:
    tag = f"{scenario}_K{K:g}_off_0_{variant}_{'intra' if intrabar else 'close'}_{'eh' if engine_halts else 'noeh'}_first_cross_carry.json"
    fn = os.path.join(STRESS, "runs", tag)
    if not os.path.exists(fn):
        fn = os.path.join(STRESS, "runs", f"{scenario}_noeh_K{K:g}_off_0_A_intra_noeh_first_cross_carry.json")
    R = json.load(open(fn))
    now = R["now_used"]
    anchor_ts, t0, n_path, last_real = R["anchor_ts"], R["t0"], R["n_path_bars"], R["last_real_ts"]

    btc = read_bars(os.path.join(CAGR, "data", "bars_4h_btcusd.csv"), now)
    hist, path, scale, today_close = splice(btc, anchor_ts, t0, n_path, last_real)
    # check the rebuilt closes against the run's saved closes
    sc = R["spliced_closes"]
    assert len(sc) == len(path), (len(sc), len(path))
    dmax = max(abs(a[1] - b[4]) / b[4] for a, b in zip(sc, path))
    assert all(a[0] == b[0] for a, b in zip(sc, path))
    closes_all = {b[0]: b[4] for b in hist}
    closes_all.update({b[0]: b[4] for b in path})

    # ETH path + funding for the carry sleeve (same splice rule, own scale)
    eth = read_bars(os.path.join(CAGR, "data", "bars_4h_ethusd.csv"), now)
    ehist, epath, escale, eth_today = splice(eth, anchor_ts, t0, n_path, last_real)
    eth_closes = {b[0]: b[4] for b in epath}
    src = funding_src or R.get("carry_funding_source", "ETHUSD")
    fund_raw = carry_sleeve.load_funding(os.path.join(STRESS, "data", f"funding_bitmex_{src}.csv"),
                                         lo_ms=(anchor_ts - 31 * DAY) * 1000,
                                         hi_ms=(anchor_ts + n_path * BAR) * 1000)
    shift_ms = (t0 - anchor_ts) * 1000
    funding = {k + shift_ms: v for k, v in fund_raw.items()}
    cr = carry_sleeve.simulate_carry(eth_closes, funding, CARRY_START, notional=CARRY_NOTIONAL,
                                     usdc_backing=USDC_BACKING)
    carry_value = cr.value
    assert len(carry_value) == n_path

    # engine trade lists (raw leg_trades output) -> paper-book halt emulation
    eng = R["engine_trades"]
    books = {}
    pub = {}
    for leg in ("pullback", "trend"):
        if engine_halts:
            books[leg] = paper_book(eng[leg], PAPER_SEED[leg])
            pub[leg] = books[leg]["published"]
        else:
            books[leg] = None
            pub[leg] = eng[leg]

    res = replay(path, closes_all, pub, K, carry_value, variant=variant, intrabar=intrabar,
                 today_close=today_close, hw_intrabar=hw_intrabar, worst_mode=worst_mode)
    ts = res["ts"]
    idx = {t: i for i, t in enumerate(ts)}
    bal = {}
    for d in (91, 182, 273, 365):
        i = idx.get(t0 + d * DAY)
        if i is None and t0 + d * DAY > ts[-1]:
            i = len(ts) - 1          # path ends 4h short of day 365: last bar
        bal[d] = res["equity_total"][i] if i is not None else None
    out = dict(
        scenario=scenario, K=K, variant=variant, intrabar=intrabar, engine_halts=engine_halts,
        funding_src=src, scale=scale, eth_scale=escale, close_rebuild_maxrel=dmax,
        balances=bal, final_equity=res["equity_total"][-1],
        max_dd=max_dd(res["equity_total"], START_EQUITY),
        max_dd_intrabar=max_dd(res["equity_total"], START_EQUITY, lows=res["worst"]),
        max_dd_intrabar_ownpeak=max_dd(res["worst"], START_EQUITY),
        max_dd_btc=max_dd(res["equity_btc"], START_EQUITY - CARRY_NOTIONAL),
        max_dd_bench=max_dd(res["bench"], START_EQUITY),
        halts=res["halts"], events=res["events"], fees=res["fees"], n_entries=res["n_entries"],
        n_trades=len(res["trades"]), n_open=res["n_open"], hw_end=res["hw_end"],
        worst_day=worst_utc_day(ts, res["equity_total"], res["worst"], START_EQUITY),
        engine_halts_info={leg: (None if b is None else {k: v for k, v in b.items() if k != "published"})
                           for leg, b in books.items()},
        carry=dict(final=carry_value[-1], funding=cr.funding_cum[-1], fees=cr.fees_cum[-1],
                   flips=[(utc(e[2]["close_ts"]), e[1], round(e[2]["value"], 2)) for e in cr.flips()],
                   on_frac=round(sum(cr.on) / len(cr.on), 3),
                   max_close_over_liq=max((eth_closes[t] / lp for t, lp in zip(cr.ts, cr.liq_px) if lp == lp and lp > 0), default=None)),
        clamps=res["clamps"], margins=res["margins"], curves=dict(ts=ts, total=res["equity_total"], btc=res["equity_btc"],
                                           worst=res["worst"], carry=carry_value, bench=res["bench"]),
        trades=res["trades"], run_file=fn)
    return out, R


def compare(mine: dict, R: dict) -> list[str]:
    lines = []
    def row(name, a, b, tol=None, fmt="{:,.2f}"):
        ok = ""
        if a is not None and b is not None and tol is not None:
            ok = "OK" if abs(a - b) <= tol else "MISMATCH"
        fa = fmt.format(a) if isinstance(a, (int, float)) else str(a)
        fb = fmt.format(b) if isinstance(b, (int, float)) else str(b)
        lines.append(f"  {name:<22} mine {fa:>14}  theirs {fb:>14}  {ok}")
    for d in (91, 182, 273, 365):
        a, b = mine["balances"][d], R["balances"][str(d)]["equity"]
        row(f"balance {d}d", a, b, tol=max(200.0, 0.003 * abs(b)))
    row("final_equity", mine["final_equity"], R["final_equity"], tol=max(200.0, 0.003 * abs(R["final_equity"])))
    row("max_dd", mine["max_dd"], R["max_dd"], tol=0.003, fmt="{:.4f}")
    row("max_dd_intrabar", mine["max_dd_intrabar"], R["max_dd_intrabar"], tol=0.003, fmt="{:.4f}")
    row("max_dd_btc_book", mine["max_dd_btc"], R.get("max_dd_btc_book"), tol=0.003, fmt="{:.4f}")
    row("max_dd_bench", mine["max_dd_bench"], R.get("max_dd_bench"), tol=0.003, fmt="{:.4f}")
    row("fees", mine["fees"], R["fees"], tol=max(5.0, 0.01 * R["fees"]))
    row("n_entries", mine["n_entries"], R["n_entries"], tol=0, fmt="{}")
    row("n_trades(closed)", mine["n_trades"], R["n_trades"], tol=0, fmt="{}")
    row("hw_end", mine["hw_end"], R["hw_end"], tol=max(200.0, 0.003 * R["hw_end"]))
    row("halts", [(h["kind"], h["date"], round(h["equity"])) for h in mine["halts"]],
        [(h if not isinstance(h, dict) else {k: h[k] for k in h if k in ("kind", "date", "equity")}) for h in R["halts"]])
    for leg in ("pullback", "trend"):
        m, t = mine["engine_halts_info"][leg], R["engine_halts_info"][leg]
        if m is None:
            continue
        row(f"eng halt {leg}", f"{m['halted']} {m['halt_date']} eq {m['equity_at_halt'] and round(m['equity_at_halt'], 2)} drop {m['dropped']}",
            f"{t['halted']} {t['halt_date']} eq {t['equity_at_halt'] and round(t['equity_at_halt'], 2)} drop {t['dropped']}")
        row(f"eng eq_end {leg}", m["equity_end"], t["equity_end"], tol=1.0)
    # curves
    ct, tt = mine["curves"]["total"], R["equity_total"]
    cc, tc = mine["curves"]["carry"], R["carry_value"]
    cb, tb = mine["curves"]["btc"], R["equity_btc"]
    cw, tw = mine["curves"]["worst"], R["worst_intrabar_equity"]
    n = min(len(ct), len(tt))
    def mx(a, b):
        return max(abs(x - y) for x, y in zip(a, b))
    row("curve total maxabs", mx(ct[:n], tt[:n]), 0.0, tol=200.0)
    row("curve btc maxabs", mx(cb[:n], tb[:n]), 0.0, tol=200.0)
    row("curve carry maxabs", mx(cc[:n], tc[:n]), 0.0, tol=50.0)
    row("curve worst maxabs", mx(cw[:n], tw[:n]), 0.0, tol=200.0)
    row("worst day (mine: worst-vs-daystart)", f"{mine['worst_day']['day']} {mine['worst_day']['usd']:,.0f}",
        f"{R['worst_day']['date']} {R['worst_day']['usd']:,.0f}")
    row("carry final/funding/fees", f"{mine['carry']['final']:,.0f}/{mine['carry']['funding']:,.0f}/{mine['carry']['fees']:,.0f}",
        f"{R['carry_value'][-1]:,.0f}")
    row("carry flips / on-frac", f"{len(mine['carry']['flips'])} / {mine['carry']['on_frac']}", "")
    row("carry max close/liq", mine["carry"]["max_close_over_liq"], None, fmt="{:.3f}")
    row("cap clamps", len(mine["clamps"]), None)
    md, ml = mine["margins"]["dd"], mine["margins"]["dl"]
    row("min margin to DD line", f"{md[0]:,.0f} at {utc(md[1])} (worst {md[2]:,.0f}, HW {md[3]:,.0f})", "")
    row("min margin to DAILY line", f"{ml[0]:,.0f} at {utc(ml[1])} (worst {ml[2]:,.0f}, day start {ml[3]:,.0f})", "")
    row("max_dd_intrabar(own peak)", mine["max_dd_intrabar_ownpeak"], None, fmt="{:.4f}")
    return lines


if __name__ == "__main__":
    scen = sys.argv[1:2] or ["COVID", "2008", "1999"]
    Ks = [float(sys.argv[2])] if len(sys.argv) > 2 else [0.75, 0.30]
    summary = {}
    for s in (scen if len(scen) > 1 else [scen[0]]):
        for K in Ks:
            mine, R = run(s, K)
            key = f"{s}_K{K:g}"
            print(f"=== {key}  (run file {os.path.basename(mine['run_file'])}; close rebuild max rel err {mine['close_rebuild_maxrel']:.2e}; BTC scale {mine['scale']:.6f} ETH scale {mine['eth_scale']:.6f} funding {mine['funding_src']})")
            print("\n".join(compare(mine, R)))
            for e in mine["events"]:
                print("   event:", utc(e[0]), e[1], e[2], round(e[3], 2))
            for h in mine["halts"]:
                print("   HALT:", h)
            if mine["clamps"]:
                for cl in mine["clamps"][:10]:
                    print("   clamp:", utc(cl[0]), cl[1], f"want {cl[2]:.5f} got {cl[3]:.5f}")
            summary[key] = {k: v for k, v in mine.items() if k not in ("curves", "trades", "events")}
            with open(os.path.join(HERE, f"mine_{key}.json"), "w") as fh:
                json.dump({k: v for k, v in mine.items() if k != "trades"} | {"trades": mine["trades"]}, fh, default=str)
    with open(os.path.join(HERE, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
