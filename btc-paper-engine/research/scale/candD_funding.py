"""CANDIDATE D, component 2: FUNDING AT SIZE.

The brief: "At $1m notional, funding is a first-order cost that is invisible at
$15k.  If funding materially eats the edge at size, that is a finding that
constrains Casey's $1m target and it must be stated plainly."

Phase 1 measured the PULLBACK leg only (+0.0202%/yr, a credit) and explicitly
refused to guess the trend leg.  The trend leg is the one that matters: it
holds 271h per trade against the pullback's 40h.  This measures BOTH, weights
them into the shipped 75/25 blend, and stress-scales to the worst funding
regime in HL's BTC history.

Run: python3 research/scale/candD_funding.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOT = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
OUT = os.path.join(HERE, "candD_funding.json")
W_TREND, TAKER = 0.25, 4.32


def main() -> None:
    bars = []
    with open(SPOT) as f:
        for r in csv.DictReader(f):
            bars.append(Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                            high=float(r["high"]), low=float(r["low"]),
                            close=float(r["close"]), volume=float(r["volume"])))
    fts, rate = [], []
    with open(FUND) as f:
        for r in csv.DictReader(f):
            fts.append(int(r["ts_ms"]) // 1000)
            rate.append(float(r["funding_rate_1h"]))
    o = sorted(range(len(fts)), key=lambda i: fts[i])
    fts = [fts[i] for i in o]; rate = [rate[i] for i in o]
    pre = [0.0]
    for x in rate:
        pre.append(pre[-1] + x)

    def fsum(t0, t1):
        return (pre[bisect.bisect_right(fts, t1)]
                - pre[bisect.bisect_right(fts, t0)])

    # the funding series is the window: measure the book over exactly the span
    # where funding is known, so held hours and calendar hours agree.
    lo, hi = min(fts), max(fts)
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=TAKER)
    res = {"funding_window_unix": [lo, hi],
           "funding_stamps": len(fts),
           "years": (hi - lo) / (365.25 * 86400)}
    YRS = res["years"]

    legs = {}
    for name, bn, w in (("pullback_S3", "S3", 1 - W_TREND),
                        ("trend_S4", "S4", W_TREND)):
        bk = [b for b in RESEARCH_BOOKS if b.name == bn]
        trs = [t for t in run_replay(bars, bk, RESEARCH_SIGNAL, tc,
                                     start_ts=lo, cash_apy=0.0
                                     ).books[bn].trades if t.exit_ts <= hi]
        signed, hrs, longs = [], [], 0
        hot_short, cold_short, hot_bps, cold_bps = 0, 0, [], []
        for t in trs:
            sgn = 1.0 if t.side == "L" else -1.0
            fr = fsum(t.entry_ts, t.exit_ts)
            bps = -sgn * fr * 1e4
            h = (t.exit_ts - t.entry_ts) / 3600.0
            signed.append(bps); hrs.append(h); longs += t.side == "L"
            ann = (fr / h * 8760 * 100) if h > 0 else 0.0   # %/yr during hold
            if ann > 10.0:
                hot_bps.append(bps); hot_short += t.side == "S"
            else:
                cold_bps.append(bps); cold_short += t.side == "S"
        tot_frac = sum(signed) / 1e4
        # time in market over the funding window
        tim = sum(hrs) / ((hi - lo) / 3600.0)
        legs[name] = {
            "n": len(trs), "n_long": longs, "n_short": len(trs) - longs,
            "short_frac": (len(trs) - longs) / len(trs),
            "mean_hold_hours": statistics.fmean(hrs),
            "total_held_hours": sum(hrs), "time_in_market_frac": tim,
            "signed_bps_per_trade": {
                "mean": statistics.fmean(signed), "median": statistics.median(signed),
                "sd": statistics.stdev(signed), "min": min(signed), "max": max(signed),
                "total": sum(signed)},
            "pct_of_own_notional_per_year": tot_frac / YRS * 100,
            "weight_in_gross": w,
            "pct_of_GROSS_notional_per_year": tot_frac / YRS * 100 * w,
            "hot_regime": {"n": len(hot_bps), "short_frac":
                           hot_short / max(1, len(hot_bps)),
                           "mean_bps": statistics.fmean(hot_bps) if hot_bps else None},
            "cold_regime": {"n": len(cold_bps), "short_frac":
                            cold_short / max(1, len(cold_bps)),
                            "mean_bps": statistics.fmean(cold_bps) if cold_bps else None},
            # ALL-LONG bound: the same hours, but never receiving
            "all_long_bound_pct_of_own_notional_per_year":
                -sum(abs(fsum(t.entry_ts, t.exit_ts)) if fsum(t.entry_ts, t.exit_ts) > 0
                     else fsum(t.entry_ts, t.exit_ts) for t in trs) / YRS * 100,
        }
        # exact all-long: pay whatever funding was, signed as a long always
        al = -sum(fsum(t.entry_ts, t.exit_ts) for t in trs)
        legs[name]["all_long_exact_pct_of_own_notional_per_year"] = al / YRS * 100
        print(f"{name}: n={len(trs)} short={legs[name]['short_frac']:.1%} "
              f"mean_hold={statistics.fmean(hrs):.0f}h "
              f"TiM={tim:.1%}")
        print(f"   signed funding mean {statistics.fmean(signed):+7.2f} bps/trade "
              f"sd {statistics.stdev(signed):6.2f}  "
              f"total {tot_frac/YRS*100:+.4f}%/yr of its notional")
        print(f"   all-long bound      {al/YRS*100:+.4f}%/yr of its notional")

    res["legs"] = legs
    blend_pct = sum(v["pct_of_GROSS_notional_per_year"] for v in legs.values())
    blend_all_long = sum(v["all_long_exact_pct_of_own_notional_per_year"]
                         * v["weight_in_gross"] for v in legs.values())
    res["blend_funding_pct_of_gross_per_year"] = blend_pct
    res["blend_all_long_bound_pct_of_gross_per_year"] = blend_all_long

    # worst-regime stress: scale by worst-90d / window-mean funding
    W = 90 * 24
    roll = []
    for i in range(W, len(rate)):
        roll.append(sum(rate[i - W:i]) / W * 8760 * 100)
    mean_rate_ann = statistics.fmean(rate) * 8760 * 100
    worst90 = max(roll)
    res["funding_regime"] = {"window_mean_pct_per_year": mean_rate_ann,
                             "worst_90d_pct_per_year": worst90,
                             "best_90d_pct_per_year": min(roll),
                             "stress_multiple": worst90 / mean_rate_ann}
    res["blend_all_long_WORST_REGIME_pct_of_gross_per_year"] = (
        blend_all_long * worst90 / mean_rate_ann)

    # dollars at each target notional, against the fee load
    RT_PER_YEAR_P = legs["pullback_S3"]["n"] / YRS
    RT_PER_YEAR_T = legs["trend_S4"]["n"] / YRS
    fee_pct_gross = ((2 * TAKER / 1e4) * RT_PER_YEAR_P * (1 - W_TREND)
                     + (2 * TAKER / 1e4) * RT_PER_YEAR_T * W_TREND) * 100
    res["fee_pct_of_gross_per_year"] = fee_pct_gross
    res["at_notional"] = {}
    for N in (15_000, 100_000, 1_000_000):
        res["at_notional"][str(N)] = {
            "funding_usd_per_year": blend_pct / 100 * N,
            "funding_all_long_usd_per_year": blend_all_long / 100 * N,
            "funding_all_long_worst_regime_usd_per_year":
                res["blend_all_long_WORST_REGIME_pct_of_gross_per_year"] / 100 * N,
            "fees_usd_per_year": -fee_pct_gross / 100 * N,
            "funding_as_frac_of_fees": abs(blend_pct) / fee_pct_gross}
    print(f"\nBLEND funding {blend_pct:+.4f}%/yr of GROSS notional")
    print(f"  all-long bound      {blend_all_long:+.4f}%/yr of gross")
    print(f"  all-long WORST 90d  "
          f"{res['blend_all_long_WORST_REGIME_pct_of_gross_per_year']:+.4f}%/yr")
    print(f"  fees for comparison {-fee_pct_gross:+.4f}%/yr of gross")
    print(f"  funding / fees = {abs(blend_pct)/fee_pct_gross:.1%}")
    for N, v in res["at_notional"].items():
        print(f"  at ${int(N):>9,} gross: funding {v['funding_usd_per_year']:+9,.0f}/yr"
              f"  fees {v['fees_usd_per_year']:+10,.0f}/yr"
              f"  all-long worst "
              f"{v['funding_all_long_worst_regime_usd_per_year']:+10,.0f}/yr")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
