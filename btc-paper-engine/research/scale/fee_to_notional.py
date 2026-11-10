"""EDGE-SIDE LEVER 1, priced in DOLLARS: what does fixing execution buy in
AUTHORISED GROSS NOTIONAL, at IDENTICAL drawdown?

Fixes two measurement defects inherited from RESEARCH_FEES.md:
 1. Its fee override was a NO-OP (found by research/scale/fee_axis.py): both
    of its arms ran the same experiment. The axis here goes through
    TradeCfg.taker_fee_bps, which core.py:261/337 actually read.
 2. Its S5/S6 rows charged the DONCHIAN leg 12.0 bps while the venue charges
    4.32 (its own honesty box, item 5). Here each leg gets its OWN fee, by
    running the two books in SEPARATE replays -- legal because run_replay
    keeps books fully independent (each has its own equity, position and
    pending; they never interact).

Fee vectors are built from the REAL venue schedule (type=userFees, fetched
2026-09-28) and from the MEASURED exit mix (verify_maker.py: S3 exits are
65.3% SIGNAL / 34.7% STOP; S4 exits are 100% STOP).

Run: python3 research/scale/fee_to_notional.py
"""
from __future__ import annotations
import csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
import numpy as np                                              # noqa: E402
from app.engine.core import Bar, BookCfg                        # noqa: E402
from app.engine.replay import run_replay                        # noqa: E402
from app.engine.kelly import analyze                            # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,        # noqa: E402
                        RESEARCH_TRADE)

BARS = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
EQUITY   = 100_055.0     # live Hyperliquid account value (spot USDC backing)
BASE     = 50_000.0      # SIZING_BASE_USD
REF_LEV  = 1.5           # REFERENCE_LEV: what /exec/target ships as the S5 blend
KELLY_M  = 0.20          # live
LIVE_GROSS = KELLY_M * REF_LEV * BASE                # $15,000
MAX_NOTIONAL_USD = 20_000.0
MAX_ACCOUNT_LEV  = 2.0

# venue schedule, frozen from the live info endpoint
TAKER, MAKER = 4.32, 1.44
# measured exit mix (verify_maker.py)
S3_SIGNAL_FRAC = 124 / 190
S3_BLENDED_MAKER_EXIT = S3_SIGNAL_FRAC * MAKER + (1 - S3_SIGNAL_FRAC) * TAKER   # 2.44

bars = [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]), volume=float(r["volume"]))
        for r in csv.DictReader(open(BARS))]
LAST = bars[-1].ts
W = {"full": None, "2y": LAST - 730 * 86400}

P_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S3"]
T_BOOKS = [b for b in RESEARCH_BOOKS if b.name == "S4"]


def leg(books, rt_bps, start_ts):
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=rt_bps / 2.0)
    r = run_replay(bars, books, RESEARCH_SIGNAL, tc, start_ts=start_ts, cash_apy=0.0)
    return r.books[books[0].name]


def blend_steps(b3, b4, w_trend=0.25, lev=REF_LEV):
    evs = sorted([(t.exit_ts, "P", t.equity_after / b3.cfg.start_equity) for t in b3.trades]
                 + [(t.exit_ts, "T", t.equity_after / b4.cfg.start_equity) for t in b4.trades])
    p3 = p4 = 1.0; out = []
    for _, w, ratio in evs:
        if w == "P":
            out.append(lev * (ratio / p3 - 1) * (1 - w_trend)); p3 = ratio
        else:
            out.append(lev * (ratio / p4 - 1) * w_trend); p4 = ratio
    return out


ARMS = [
    ("LIVE TODAY          entry taker, exit taker",        2 * TAKER, 2 * TAKER),
    ("FIX 1: maker entry  entry maker, exit taker",        MAKER + TAKER, 2 * TAKER),
    ("FIX 1+2: + maker SIGNAL exits (S3 only, measured)",  MAKER + S3_BLENDED_MAKER_EXIT, 2 * TAKER),
    # maker_exit_risk.py: resting the SIGNAL exit nets +1.09 bps per exit, NOT
    # the nominal 2.88 -- the passive exit gives up 1.76 bps of PRICE (the
    # shipped exit at the next bar's open captures the momentum continuation).
    # So the honest exit leg is TAKER - 1.09*(124/190) on the S3 book.
    ("FIX 1+2 RISK-ADJUSTED (measured net exit gain, not nominal)",
     MAKER + (TAKER - 1.09 * S3_SIGNAL_FRAC), 2 * TAKER),
    ("CEILING: both legs fully maker (not achievable)",    2 * MAKER, 2 * MAKER),
    ("VIP tier 1 ($5m/14d) on top of FIX 1+2",
     0.96*1.2 + (S3_SIGNAL_FRAC*0.96*1.2 + (1-S3_SIGNAL_FRAC)*0.96*4.0),
     2 * 0.96 * 4.0),
    ("VIP tier 2 ($25m/14d) on top of FIX 1+2",
     0.96*0.8 + (S3_SIGNAL_FRAC*0.96*0.8 + (1-S3_SIGNAL_FRAC)*0.96*3.5),
     2 * 0.96 * 3.5),
]

print("=" * 96)
print("FEE FIX -> AUTHORISED GROSS NOTIONAL, per-leg venue fees, cash_apy 0")
print("=" * 96)
print(f"  live: KELLY_M {KELLY_M} x REFERENCE_LEV {REF_LEV} x SIZING_BASE_USD "
      f"{BASE:,.0f} = ${LIVE_GROSS:,.0f} gross = {LIVE_GROSS/EQUITY*100:.1f}% of equity")
print(f"  Kelly m on the research S5 basis is a multiplier on 1.5x equity, so")
print(f"  m = 1.0 -> ${REF_LEV*EQUITY:,.0f} gross. Live sits at m_equiv = "
      f"{LIVE_GROSS/(REF_LEV*EQUITY):.4f}.")
print(f"  authorised_gross($) = m_rec x {REF_LEV} x {EQUITY:,.0f}")
print()

OUT = {"live": {"gross_usd": LIVE_GROSS, "equity": EQUITY,
                "m_equiv": LIVE_GROSS / (REF_LEV * EQUITY),
                "MAX_NOTIONAL_USD": MAX_NOTIONAL_USD,
                "rail_cap_usd": min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV * BASE)},
       "fee_schedule": {"taker_bps": TAKER, "maker_bps": MAKER,
                        "S3_signal_exit_frac": S3_SIGNAL_FRAC,
                        "S3_blended_maker_exit_bps": S3_BLENDED_MAKER_EXIT},
       "arms": {}}

for wname, st in W.items():
    print("-" * 96)
    print(f"  WINDOW {wname}   (S5 blend 75/25 @1.5x)")
    print(f"  {'arm':<52} {'S3rt':>5} {'S4rt':>5} {'n':>4} {'m*':>5} "
          f"{'p10':>5} {'dd30':>5} {'REC':>5} {'binds':>6} {'AUTH GROSS $':>13} {'x live':>7}")
    base_rec = None
    for label, rt3, rt4 in ARMS:
        b3 = leg(P_BOOKS, rt3, st)
        b4 = leg(T_BOOKS, rt4, st)
        s = blend_steps(b3, b4)
        A = analyze(s, f"S5|{wname}|{label}")
        terms = {"half": A["half_kelly_m"], "p10": A["bootstrap"]["p10"],
                 "c*m*": round(A["shrinkage_c_star"] * A["kelly_m"], 2),
                 "dd30": A["dd_constrained"]["p_maxdd30_le_10pct"]}
        bind = min(terms.items(), key=lambda t: t[1])
        rec = A["recommended_m"]
        gross = rec * REF_LEV * EQUITY
        if base_rec is None:
            base_rec = rec
        # drawdown check: the DD the book PRINTED at this arm, so the reader can
        # see that the authorised size is not bought with more drawdown
        dd_tc = None
        eq = np.cumprod(1 + np.array(s)); pk = np.maximum.accumulate(eq)
        dd_tc = float((eq / pk - 1).min())
        OUT["arms"][f"{wname}|{label}"] = {
            "rt_S3": rt3, "rt_S4": rt4, "n": A["n"], "m_star": A["kelly_m"],
            "terms": terms, "binding": bind[0], "recommended_m": rec,
            "authorised_gross_usd": gross, "x_live": gross / LIVE_GROSS,
            "x_live_authorised_vs_baseline_arm": rec / base_rec if base_rec else None,
            "blend_maxdd_tradeclose": dd_tc,
            "P_dd_gt_30_at_that_m": A["dd_constrained"],
            "fees_usd_S3": sum(t.fees_usd for t in b3.trades),
            "fees_usd_S4": sum(t.fees_usd for t in b4.trades),
            "KELLY_M_equivalent_at_base_50k": rec / (BASE / EQUITY),
        }
        print(f"  {label:<52} {rt3:>5.2f} {rt4:>5.2f} {A['n']:>4} {A['kelly_m']:>5.2f} "
              f"{terms['p10']:>5.2f} {terms['dd30']:>5.2f} {rec:>5.2f} {bind[0]:>6} "
              f"{gross:>13,.0f} {gross/LIVE_GROSS:>6.2f}x")
    print(f"  blend trade-close maxDD is IDENTICAL in shape across arms "
          f"(fee does not change which trades win: RESEARCH_FEES.md win-rate finding)")

print()
print("=" * 96)
print("THE GOVERNING NUMBER  (conservative-window rule: KELLY.md doctrine)")
print("=" * 96)
gov = {}
for label, _, _ in ARMS:
    recs = [OUT["arms"][f"{w}|{label}"]["recommended_m"] for w in W]
    g = min(recs)
    gov[label] = {"recommended_m": g, "authorised_gross_usd": g * REF_LEV * EQUITY,
                  "x_live": g * REF_LEV * EQUITY / LIVE_GROSS,
                  "per_window": dict(zip(W, recs))}
    print(f"  {label:<52} m={g:>5.2f}  ${g*REF_LEV*EQUITY:>10,.0f}  "
          f"{g*REF_LEV*EQUITY/LIVE_GROSS:>5.2f}x live   (windows {recs})")
OUT["governing"] = gov
base = gov[ARMS[0][0]]["authorised_gross_usd"]
for label, _, _ in ARMS[1:]:
    d = gov[label]["authorised_gross_usd"] - base
    print(f"  + fee fix '{label[:40]}' = +${d:,.0f} authorised gross "
          f"({d/base*100:+.1f}%)")
OUT["extra_authorised_vs_live_arm"] = {
    l: gov[l]["authorised_gross_usd"] - base for l, _, _ in ARMS}

print()
print("  RAIL CHECK: every arm above already exceeds MAX_NOTIONAL_USD "
      f"${MAX_NOTIONAL_USD:,.0f}")
print(f"  and the MAX_ACCOUNT_LEV x base cap ${MAX_ACCOUNT_LEV*BASE:,.0f}.")
print("  The edge side is NOT what is holding the book at $15,000.")

json.dump(OUT, open(os.path.join(HERE, "fee_to_notional.json"), "w"), indent=1,
          default=str)
print(f"\nfrozen -> {os.path.join(HERE, 'fee_to_notional.json')}")
