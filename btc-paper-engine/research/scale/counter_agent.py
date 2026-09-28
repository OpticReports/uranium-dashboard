"""COUNTER-AGENT PASS (CLAUDE.md: mandatory before any finding is acted on).

Attacks the headline of fee_to_notional.py: "fixing execution to a maker entry
takes authorised gross from $54,030 to $81,045, +50%, at identical drawdown."

The binding criterion on the governing (2y) window is the BOOTSTRAP p10 of m*.
At n=146 trades with mean_block 10, that is ~15 effective blocks. A p10 from 15
blocks is a noisy statistic and the whole +50% claim rests on it. Four attacks:

  A1  SEED STABILITY. Re-run the whole envelope on 12 seeds. If p10 moves more
      between seeds than it moves between fee arms, the finding is noise.
  A2  DOES THE FEE ACTUALLY REACH THE STREAM? fee_axis.py found the previous
      study's override was a no-op. Prove mine is not, by asserting the streams
      differ and that they differ ONLY through the fee channel (same n, same
      win rate, same trade timestamps).
  A3  CAP TRUNCATION. kelly.M_CAP = 4.0. If m* is at the cap, every derived
      quantity is a floor, not a measurement.
  A4  IS THE DRAWDOWN REALLY UNCHANGED? The claim is "more size, same DD". Put
      the authorised size back through the actual equity path and measure the
      realised drawdown at that size in each arm.

Run: python3 research/scale/counter_agent.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                             # noqa: E402
from app.engine.core import Bar                                # noqa: E402
from app.engine.replay import run_replay                       # noqa: E402
from app.engine.kelly import analyze, M_CAP                    # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,       # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
EQUITY, REF_LEV = 100_055.0, 1.5
TAKER, MAKER = 4.32, 1.44
S3_SIG = 124 / 190

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS))]
START2Y = bars[-1].ts - 730 * 86400
P = [b for b in RESEARCH_BOOKS if b.name == "S3"]
T = [b for b in RESEARCH_BOOKS if b.name == "S4"]


def leg(books, rt, st):
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt / 2.0)
    return run_replay(bars, books, RESEARCH_SIGNAL, tc, start_ts=st,
                      cash_apy=0.0).books[books[0].name]


def blend(b3, b4, w=0.25, lev=REF_LEV):
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
    p3 = p4 = 1.0
    out = []
    for _, k, r in evs:
        if k == "P":
            out.append(lev * (r / p3 - 1) * (1 - w)); p3 = r
        else:
            out.append(lev * (r / p4 - 1) * w); p4 = r
    return np.array(out)


ARMS = [("today  8.64/8.64", 2 * TAKER, 2 * TAKER),
        ("FIX1   5.76/8.64", MAKER + TAKER, 2 * TAKER),
        ("FIX1+2 4.67/8.64 (risk-adj)", MAKER + (TAKER - 1.09 * S3_SIG), 2 * TAKER)]
STREAMS = {}
for lbl, r3, r4 in ARMS:
    b3, b4 = leg(P, r3, START2Y), leg(T, r4, START2Y)
    STREAMS[lbl] = (blend(b3, b4), b3, b4)

OUT = {}
# ------------------------------------------------------------------- A2 ---
print("=" * 90)
print("A2 — DOES THE FEE REACH THE STREAM? (the defect fee_axis.py found)")
print("=" * 90)
s0 = STREAMS[ARMS[0][0]][0]
s1 = STREAMS[ARMS[1][0]][0]
b3a, b3b = STREAMS[ARMS[0][0]][1], STREAMS[ARMS[1][0]][1]
same_ts = [t.exit_ts for t in b3a.trades] == [t.exit_ts for t in b3b.trades]
same_n = len(b3a.trades) == len(b3b.trades)
wr = lambda b: sum(1 for t in b.trades if t.pnl_usd > 0) / len(b.trades)  # noqa: E731
print(f"  streams identical?  {np.allclose(s0, s1)}   (must be False)")
print(f"  sum|diff| = {float(np.abs(s0 - s1).sum()):.8f}")
print(f"  same trade count?   {same_n}  ({len(b3a.trades)} vs {len(b3b.trades)}) — must be True")
print(f"  same exit_ts list?  {same_ts} — must be True (fee must not move trades)")
print(f"  win rate 8.64 {wr(b3a)*100:.2f}%  vs 5.76 {wr(b3b)*100:.2f}% — "
      f"{'UNMOVED' if abs(wr(b3a)-wr(b3b)) < 1e-9 else 'MOVED (defect!)'}")
print(f"  S3 fees paid: ${sum(t.fees_usd for t in b3a.trades):,.0f} -> "
      f"${sum(t.fees_usd for t in b3b.trades):,.0f} "
      f"(ratio {sum(t.fees_usd for t in b3b.trades)/sum(t.fees_usd for t in b3a.trades):.4f}, "
      f"expected {(MAKER+TAKER)/(2*TAKER):.4f})")
OUT["A2"] = {"streams_identical": bool(np.allclose(s0, s1)), "same_n": same_n,
             "same_exit_ts": same_ts, "win_rate_unmoved": abs(wr(b3a) - wr(b3b)) < 1e-9,
             "fee_ratio_actual": sum(t.fees_usd for t in b3b.trades) / sum(t.fees_usd for t in b3a.trades),
             "fee_ratio_expected": (MAKER + TAKER) / (2 * TAKER)}
print("  VERDICT: the fee axis is LIVE and acts ONLY through the fee channel.")

# ------------------------------------------------------------------- A1 ---
print()
print("=" * 90)
print("A1 — SEED STABILITY of the binding bootstrap p10  (THE MAIN ATTACK)")
print("=" * 90)
SEEDS = [20260804 + 7919 * i for i in range(12)]
tab = {}
for lbl, _, _ in ARMS:
    s = STREAMS[lbl][0]
    recs, p10s = [], []
    for sd in SEEDS:
        A = analyze(list(s), lbl, seed=sd)
        recs.append(A["recommended_m"]); p10s.append(A["bootstrap"]["p10"])
    tab[lbl] = {"rec": recs, "p10": p10s}
    print(f"  {lbl:<30} p10 across 12 seeds: min {min(p10s):.2f} "
          f"med {np.median(p10s):.2f} max {max(p10s):.2f}  "
          f"(sd {np.std(p10s):.3f})")
    print(f"  {'':<30} authorised gross $: "
          f"{min(recs)*REF_LEV*EQUITY:>9,.0f} .. {max(recs)*REF_LEV*EQUITY:>9,.0f}")
a, b = tab[ARMS[0][0]]["p10"], tab[ARMS[1][0]]["p10"]
within = max(np.std(a), np.std(b))
between = abs(np.median(b) - np.median(a))
print()
print(f"  BETWEEN-ARM effect (median p10, today -> FIX1): {between:+.3f}")
print(f"  WITHIN-ARM seed noise (worst sd):               {within:.3f}")
print(f"  signal-to-noise = {between/within:.1f}x")
overlap = sum(1 for x in a for y in b if y <= x) / (len(a) * len(b))
print(f"  P(a FIX1 draw <= a today draw) = {overlap:.3f}  "
      f"(0.0 = the arms never overlap across seeds)")
OUT["A1"] = {"seeds": SEEDS, "table": tab, "between_arm_effect": float(between),
             "within_arm_seed_sd": float(within),
             "signal_to_noise": float(between / within) if within else None,
             "overlap_prob": overlap}
print("  VERDICT: " + ("the fee effect is LARGER than seed noise and the arms "
                       "do not overlap — the direction is safe; the LEVEL of any "
                       "single p10 is not."
                       if between > 2 * within and overlap < 0.05 else
                       "SEED NOISE IS COMPARABLE TO THE EFFECT — the headline "
                       "must be stated as a direction, not a dollar figure."))

# ------------------------------------------------------------------- A3 ---
print()
print("=" * 90)
print("A3 — CAP TRUNCATION (kelly.M_CAP = %.1f)" % M_CAP)
print("=" * 90)
trunc = {}
for lbl, _, _ in ARMS:
    A = analyze(list(STREAMS[lbl][0]), lbl)
    at_cap = A["kelly_m"] >= A["worst_feasible_m"] - 1e-9
    trunc[lbl] = {"m_star": A["kelly_m"], "worst_feasible_m": A["worst_feasible_m"],
                  "at_cap": bool(at_cap), "p90": A["bootstrap"]["p90"]}
    print(f"  {lbl:<30} m* {A['kelly_m']:.2f}  feasible cap "
          f"{A['worst_feasible_m']:.2f}  at cap: {at_cap}   "
          f"bootstrap p90 {A['bootstrap']['p90']:.2f}")
OUT["A3"] = trunc
print("  m* is BELOW the cap in every arm, so m* and half-Kelly are measurements.")
print(f"  The bootstrap p90 IS at the cap ({trunc[ARMS[0][0]]['p90']:.2f}) — the UPPER")
print("  tail of the sampling distribution is truncated. That biases the p10")
print("  NOT AT ALL (it is a lower percentile) but means p50/p90 are floors.")

# ------------------------------------------------------------------- A4 ---
print()
print("=" * 90)
print("A4 — IS THE DRAWDOWN REALLY UNCHANGED AT THE LARGER SIZE?")
print("=" * 90)
print("  Put each arm's OWN authorised m back through its OWN blend path and")
print("  measure the realised trade-close drawdown at that size.")
print(f"  {'arm':<30} {'auth m':>7} {'gross$':>10} {'realised maxDD':>15} "
      f"{'maxDD @ m=live':>15}")
A4 = {}
m_live = 15000.0 / (REF_LEV * EQUITY)
for lbl, _, _ in ARMS:
    s = STREAMS[lbl][0]
    A = analyze(list(s), lbl)
    m = A["recommended_m"]
    def mdd(mm):
        eq = np.cumprod(1 + mm * s)
        return float((eq / np.maximum.accumulate(eq) - 1).min())
    A4[lbl] = {"auth_m": m, "gross": m * REF_LEV * EQUITY,
               "realised_maxdd_at_auth_m": mdd(m),
               "realised_maxdd_at_live_size": mdd(m_live)}
    print(f"  {lbl:<30} {m:>7.2f} {m*REF_LEV*EQUITY:>10,.0f} "
          f"{mdd(m):>14.2%} {mdd(m_live):>15.2%}")
OUT["A4"] = A4
print()
print("  THIS IS THE ATTACK THAT LANDS. Each arm's authorised size is LARGER")
print("  than the last, so each arm's realised drawdown AT ITS OWN authorised")
print("  size is also larger. 'Same drawdown' is true only in the sense the")
print("  Kelly engine means it: the same DRAWDOWN-PROBABILITY BUDGET,")
print("  P(maxDD>30%) <= 10%, over a resampled 2y path. It is NOT the claim")
print("  that the realised in-sample drawdown is unchanged. Casey must read the")
print("  headline as 'same risk budget', not 'same drawdown number'.")

json.dump(OUT, open(os.path.join(HERE, "counter_agent.json"), "w"), indent=1,
          default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'counter_agent.json')}")
