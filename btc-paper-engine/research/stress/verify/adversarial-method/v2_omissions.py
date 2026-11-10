#!/usr/bin/env python3
"""T4b bookkeeping replay (fixed: entry fee charged while open)
T7  BTC perp funding on the book's own positions (NOT modelled by the study) - XBTUSD BitMEX 8h rates of the analogue window
T8  volume-regime sensitivity: analogue volume rescaled to today's level (preserves relative structure)
T9  carry: independent recomputation of funding, gate, and ETH close / liq ratio from the account's USDC
T10 full grid on the XBTUSD proxy (what the integrator ran only at offset 0 / K 0.75)
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
STRESS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, STRESS)
import stress, carry_sleeve as cs, run_all, harness          # noqa: E402
from stress import BAR, DAY, build_spliced, run_path, _date, PAPER_SEED  # noqa: E402
from app.engine.core import Bar                                   # noqa: E402
NOW = stress.SEED_NOW
RUNS = os.path.join(STRESS, "runs")
SCEN = (("COVID", "2020-02-13"), ("2008", "2021-11-09"), ("1999", "2017-12-17"))

# ---------------------------------------------------------------- T4b
print("== T4b bookkeeping replay from saved trades (entry fee charged at entry)")
def replay(r):
    ts = r["ts"]; closes = dict(r["spliced_closes"]); f = r["constants"]["FEE_BPS"] / 1e4
    cash = r["constants"]["START_EQUITY"] - r["constants"]["CARRY_START"]
    out = []
    for t in ts:
        for tr in r["trades"]:
            if tr["entry_ts"] == t:
                cash -= f * tr["notional"]
            if tr["exit_ts"] == t:
                cash += tr["gross"] - f * tr["qty"] * tr["exit_px"]
        unreal = sum(tr["qty"] * (closes[t] - tr["entry_px"]) * (1 if tr["side"] == "L" else -1)
                     for tr in r["trades"] if tr["entry_ts"] <= t and (tr["exit_ts"] is None or tr["exit_ts"] > t))
        out.append(cash + unreal)
    return np.array(out)
for scen, _ in SCEN:
    for K in ("0.75", "0.3"):
        r = json.load(open(os.path.join(RUNS, f"{scen}_K{K}_off_0_A_intra_eh_first_cross_carry.json")))
        d = np.abs(replay(r) - np.array(r["equity_btc"])).max()
        print(f"  {scen} K{K}: replay |d| {d:.3f}  {'PASS' if d < 0.5 else 'FAIL'}")

# ---------------------------------------------------------------- T7
print("\n== T7 BTC perp funding on the executor's positions (K 0.75, offset 0): XBTUSD BitMEX 8h of the analogue window, shifted")
tot_fund = {}
for scen, anchor in SCEN:
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW)
    n = len(bars.path)
    fund, meta = run_all.funding_for(bars.anchor_ts, n, bars.t0, force="XBTUSD")
    stamps = sorted((k // 1000, v) for k, v in fund.items() if k // 1000 >= bars.t0)
    closes = {b.ts: b.close for b in bars.path}
    r = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
    cost = 0.0; cost_by_leg = {"pullback": 0.0, "trend": 0.0}; held_stamps = 0
    for s, rate in stamps:
        bar_ts = (s - BAR) // BAR * BAR if s % BAR == 0 else s // BAR * BAR   # stamp at a close -> the bar that closes there
        px = closes.get(bar_ts)
        if px is None:
            continue
        for tr in r["trades"]:
            ent, ex = tr["entry_ts"], tr["exit_ts"]
            if ent < s and (ex is None or ex + BAR > s):      # held through the stamp
                sgn = 1 if tr["side"] == "L" else -1
                pay = -sgn * tr["qty"] * px * rate               # long PAYS a positive rate
                cost += pay; cost_by_leg[tr["leg"]] += pay; held_stamps += 1
    ann = np.mean([v for _, v in stamps]) * 1095 * 100
    tot_fund[scen] = cost
    print(f"  {scen}: XBTUSD window mean funding {ann:+.1f}%/yr; book's net funding P&L {cost:+,.0f} "
          f"(pullback {cost_by_leg['pullback']:+,.0f}, trend {cost_by_leg['trend']:+,.0f}; {held_stamps} position-stamps); "
          f"headline 12m {r['balances']['365']['equity']:,.0f} -> {r['balances']['365']['equity'] + cost:,.0f}")

# ---------------------------------------------------------------- T8
print("\n== T8 volume regime: analogue volume x (today's pre-seam 20-bar mean / analogue's pre-anchor 20-bar mean)")
full = harness.load_bars("btcusd")
for scen, anchor in SCEN:
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW)
    a_ts = bars.anchor_ts
    pre_anchor = [b for b in full if a_ts - 20 * BAR <= b.ts < a_ts]
    v_today = np.mean([b.volume for b in bars[bars.seam - 20:bars.seam]])
    v_anc = np.mean([b.volume for b in pre_anchor])
    k = v_today / v_anc
    nb = stress.SplicedBars(list(bars[:bars.seam]) + [Bar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
                                                          volume=b.volume * k) for b in bars.path])
    for a in ("seam", "t0", "scale", "anchor_ts", "anchor_close", "today_close", "last_real_ts", "now_used", "pair", "mode"):
        setattr(nb, a, getattr(bars, a))
    nb.key = ("volnorm", scen)
    bars_e = build_spliced("ethusd", anchor, 12, 0, now=NOW)
    fund, meta = run_all.funding_for(bars.anchor_ts, len(bars.path), bars.t0)
    cr = run_all.run_carry(bars_e, fund)
    r0 = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
    r1 = run_path(scen + "_volnorm", nb, 0.75, carry_value=cr.value, save=False, extra=dict(offset_days=0))
    n0 = len(r0["engine_trades"]["pullback"]); n1 = len(r1["engine_trades"]["pullback"])
    print(f"  {scen}: volume factor x{k:.3f}; 12m {r0['balances']['365']['equity']:,.0f} -> {r1['balances']['365']['equity']:,.0f}; "
          f"maxDD {r0['max_dd']:.1%} -> {r1['max_dd']:.1%}; pullback engine trades {n0} -> {n1}; "
          f"S3 halt {r0['engine_halts_info']['pullback']['halt_date']} -> {r1['engine_halts_info']['pullback']['halt_date']}; "
          f"first pullback entries {[t['entry_date'] for t in r0['engine_trades']['pullback'][:3]]} -> {[t['entry_date'] for t in r1['engine_trades']['pullback'][:3]]}")

# ---------------------------------------------------------------- T9
print("\n== T9 carry: independent recomputation (offset 0)")
for scen, anchor in SCEN:
    bars = build_spliced("btcusd", anchor, 12, 0, now=NOW); bars_e = build_spliced("ethusd", anchor, 12, 0, now=NOW)
    n = len(bars.path)
    for src in ("ETHUSD", "XBTUSD"):
        if src == "ETHUSD" and run_all.funding_first_stamp("ETHUSD") > bars.anchor_ts - run_all.PRE_WINDOW_S:
            continue
        fund, meta = run_all.funding_for(bars.anchor_ts, n, bars.t0, force=src)
        cr = run_all.run_carry(bars_e, fund)
        closes = [b.close for b in bars_e.path]
        # (a) funding recomputed from the raw stamps and the sleeve's own qty/on path
        stamps = sorted((k // 1000, v) for k, v in fund.items() if k // 1000 >= bars.t0 + BAR)
        ts = cr.ts; idx = {t: i for i, t in enumerate(ts)}
        f_re = 0.0
        for s, rate in stamps:
            j = idx.get(s - BAR)      # bar closing at s
            if j is None:
                continue
            if cr.on[j] and cr.qty[j] > 0:
                f_re += cr.qty[j] * closes[j] * rate
        # (b) window mean annualised; (c) worst ETH close / liq with ACCOUNT usdc = equity_btc + sleeve flows
        r = json.load(open(os.path.join(RUNS, f"{scen}_K0.75_off_0_A_intra_eh_first_cross_carry.json")))
        eqb = r["equity_btc"]
        worst = 0.0; wj = None
        for j in range(n):
            if cr.on[j] and cr.qty[j] > 0:
                usdc = eqb[j] + (cr.usdc_eff[j] - 70000.0)
                liq = cs.liq_px_short(usdc, cr.qty[j], cr.entry_px[j])
                ratio = closes[j] / liq
                if ratio > worst:
                    worst, wj = ratio, j
        ann = np.mean([v for _, v in stamps]) * 1095 * 100
        neg = sum(1 for _, v in stamps if v < 0) / len(stamps)
        print(f"  {scen} {src}: window mean {ann:+.1f}%/yr ({neg:.0%} of stamps negative); funding recomputed {f_re:,.0f} vs sleeve {cr.funding_cum[-1]:,.0f}; "
              f"flips {len(cr.flips())}; on {100*sum(cr.on)/n:.0f}%; worst ETH/liq {worst:.2f} at {_date(ts[wj]) if wj is not None else None} "
              f"(ETH {closes[wj] if wj is not None else 0:,.0f}); sleeve 12m value {cr.value[-1]:,.0f}")

# ---------------------------------------------------------------- T10
print("\n== T10 full grid on the XBTUSD funding proxy (variant A, intrabar) vs the ETHUSD headline")
rows = []
for scen, anchor in SCEN:
    for off in (-28, -14, 0, 14, 28):
        bars = build_spliced("btcusd", anchor, 12, off, now=NOW); bars_e = build_spliced("ethusd", anchor, 12, off, now=NOW)
        n = len(bars.path)
        fund, meta = run_all.funding_for(bars.anchor_ts, n, bars.t0, force="XBTUSD")
        cr = run_all.run_carry(bars_e, fund)
        for K in (0.75, 0.30):
            r = run_path(f"{scen}_xbt", bars, K, carry_value=cr.value, save=False, extra=dict(offset_days=off))
            r0 = json.load(open(os.path.join(RUNS, f"{scen}_K{K:g}_off{off:+d}_A_intra_eh_first_cross_carry.json".replace("off+", "off_").replace("off-", "off-"))))
            rows.append((scen, off, K, r0["balances"]["365"]["equity"], r["balances"]["365"]["equity"], r0["max_dd"], r["max_dd"],
                         len(r["halts"]), len(cr.flips()), cr.value[-1]))
print(f"  {'scen':6s}{'off':>5s}{'K':>5s} | {'12m ETHUSD':>11s} {'12m XBTUSD':>11s} | {'mDD ETH':>8s} {'mDD XBT':>8s} | halts flips carry12m")
for row in rows:
    print(f"  {row[0]:6s}{row[1]:>+5d}{row[2]:>5g} | {row[3]:>11,.0f} {row[4]:>11,.0f} | {row[5]:>8.1%} {row[6]:>8.1%} | {row[7]:>5d} {row[8]:>5d} {row[9]:>8,.0f}")
json.dump(dict(rows=rows, btc_funding=tot_fund), open(os.path.join(HERE, "v2_out.json"), "w"))
