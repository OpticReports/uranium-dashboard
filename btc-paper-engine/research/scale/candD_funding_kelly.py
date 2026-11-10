"""CANDIDATE D: funding's REGIME dependence, and what it costs in authorised size.

Two of my own runs disagreed by 14x on the same quantity:
  basis window   2024-06 -> 2026-07 : blend funding -0.13%/yr of gross
  funding window 2023-05 -> 2026-09 : blend funding -1.86%/yr of gross
Both are correct; they are different regimes.  Phase 1's +0.0202%/yr credit is
a third window again.  A number that moves 14x with the window is not a
constant to quote -- so this decomposes it by year and prices the Kelly cost of
funding on the LONGER window, where the basis series cannot reach but funding
can.

Run: python3 research/scale/candD_funding_kelly.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, os, statistics, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze, SEED                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOT = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
BASIS = os.path.join(HERE, "candD_perp_4h.csv")
OUT = os.path.join(HERE, "candD_funding_kelly.json")
EQUITY, REF_LEV, W_TREND, TAKER = 100_055.0, 1.5, 0.25, 4.32
SEEDS = [SEED, 11, 101, 1009, 777, 4242, 31337, 5]


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
            fts.append(int(r["ts_ms"]) // 1000); rate.append(float(r["funding_rate_1h"]))
    o = sorted(range(len(fts)), key=lambda i: fts[i])
    fts = [fts[i] for i in o]; rate = [rate[i] for i in o]
    pre = [0.0]
    for x in rate:
        pre.append(pre[-1] + x)

    def fsum(a, b):
        return pre[bisect.bisect_right(fts, b)] - pre[bisect.bisect_right(fts, a)]

    bc = {}
    with open(BASIS) as f:
        for r in csv.DictReader(f):
            bc[int(r["ts"])] = float(r["basis_close_bps"]) / 1e4

    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=TAKER)
    res = {"windows": {}}

    def legs(start_ts, end_ts):
        out = {}
        for bn in ("S3", "S4"):
            bk = [b for b in RESEARCH_BOOKS if b.name == bn]
            trs = run_replay(bars, bk, RESEARCH_SIGNAL, tc, start_ts=start_ts,
                             cash_apy=0.0).books[bn].trades
            out[bn] = [t for t in trs if t.exit_ts <= end_ts]
        return out

    # ---------- funding by YEAR, per leg, weighted into the blend ----------
    all_legs = legs(min(fts), max(fts))
    by_year: dict[str, dict] = {}
    for bn, w in (("S3", 1 - W_TREND), ("S4", W_TREND)):
        for t in all_legs[bn]:
            y = time.strftime("%Y", time.gmtime(t.entry_ts))
            sgn = 1.0 if t.side == "L" else -1.0
            frac = -sgn * fsum(t.entry_ts, t.exit_ts)
            d = by_year.setdefault(y, {"S3": 0.0, "S4": 0.0, "S3_n": 0,
                                       "S4_n": 0, "S3_long": 0, "S4_long": 0,
                                       "hours": 0.0})
            d[bn] += frac; d[f"{bn}_n"] += 1
            d[f"{bn}_long"] += t.side == "L"
            d["hours"] += (t.exit_ts - t.entry_ts) / 3600.0
    # year fraction actually covered by the funding series
    for y, d in by_year.items():
        y0 = int(time.mktime(time.strptime(f"{y}-01-01", "%Y-%m-%d")))
        y1 = int(time.mktime(time.strptime(f"{int(y)+1}-01-01", "%Y-%m-%d")))
        cov = (min(y1, max(fts)) - max(y0, min(fts))) / (y1 - y0)
        d["coverage_frac_of_year"] = cov
        d["blend_pct_of_gross_per_year"] = (
            (d["S3"] * (1 - W_TREND) + d["S4"] * W_TREND) / max(cov, 1e-9) * 100)
        d["mean_funding_rate_pct_per_year"] = None
    res["funding_by_year"] = by_year
    print("FUNDING BY YEAR (blended, % of GROSS notional per year):")
    for y in sorted(by_year):
        d = by_year[y]
        print(f"  {y}: {d['blend_pct_of_gross_per_year']:+8.4f}%/yr  "
              f"(S3 n={d['S3_n']} long={d['S3_long']}, "
              f"S4 n={d['S4_n']} long={d['S4_long']}, cov={d['coverage_frac_of_year']:.2f})")

    # ---------- Kelly: funding's cost in authorised size, two windows ----------
    def steps(trs_by_book, apply_basis, apply_funding):
        ev = []
        for bn, w in (("S3", 1 - W_TREND), ("S4", W_TREND)):
            for t in trs_by_book[bn]:
                sgn = 1.0 if t.side == "L" else -1.0
                fee = t.fees_usd / t.notional
                if apply_basis:
                    b0, b1 = bc.get(t.signal_ts), bc.get(t.exit_ts)
                    if b0 is None or b1 is None:
                        continue
                    ratio = (t.exit_price * (1 + b1)) / (t.entry_price * (1 + b0))
                else:
                    ratio = t.exit_price / t.entry_price
                g = (ratio - 1) if t.side == "L" else (1 - ratio)
                fund = (-sgn * fsum(t.entry_ts, t.exit_ts)) if apply_funding else 0.0
                ev.append((t.exit_ts, REF_LEV * w
                           * (g - fee + fund) * t.notional / t.equity_before))
        ev.sort()
        return [x for _, x in ev]

    windows = {
        "funding_window_2023-05_to_2026-09": (min(fts), max(fts), False),
        "basis_window_2024-06_to_2026-07": (min(bc), max(bc), True),
    }
    for wname, (lo, hi, has_basis) in windows.items():
        L = legs(lo, hi)
        row = {}
        variants = [("no_funding", has_basis, False), ("with_funding", has_basis, True)]
        for vname, ab, af in variants:
            s = steps(L, ab, af)
            A = analyze(s, f"{wname}|{vname}")
            row[vname] = {
                "n": A["n"], "mean_pct": A["mean_pct"], "sd_pct": A["sd_pct"],
                "kelly_m": A["kelly_m"], "p10": A["bootstrap"]["p10"],
                "dd30_m": A["dd_constrained"]["p_maxdd30_le_10pct"],
                "recommended_m": A["recommended_m"],
                "authorised_gross_usd": A["recommended_m"] * REF_LEV * EQUITY,
                "prob_negative_edge": A["bootstrap"]["prob_negative_edge"]}
        # paired seeds on the funding haircut
        s0 = steps(L, has_basis, False); s1 = steps(L, has_basis, True)
        rr = []
        for sd in SEEDS:
            a = analyze(s0, "a", seed=sd); b = analyze(s1, "b", seed=sd)
            if a["recommended_m"] > 0:
                rr.append(b["recommended_m"] / a["recommended_m"])
        row["paired_funding_ratio"] = {
            "mean": statistics.fmean(rr), "sd": statistics.stdev(rr),
            "min": min(rr), "max": max(rr),
            "n_below_1": sum(1 for x in rr if x < 1.0), "n_seeds": len(rr)}
        row["basis_applied"] = has_basis
        res["windows"][wname] = row
        n = row["no_funding"]; wf = row["with_funding"]
        print(f"\n{wname}  (basis applied: {has_basis})")
        print(f"  no funding  : n={n['n']} mean={n['mean_pct']}% rec_m="
              f"{n['recommended_m']} -> ${n['authorised_gross_usd']:,.0f}")
        print(f"  with funding: n={wf['n']} mean={wf['mean_pct']}% rec_m="
              f"{wf['recommended_m']} -> ${wf['authorised_gross_usd']:,.0f}")
        print(f"  paired-seed funding ratio {row['paired_funding_ratio']['mean']:.3f} "
              f"(sd {row['paired_funding_ratio']['sd']:.3f}, "
              f"{row['paired_funding_ratio']['n_below_1']}/{len(rr)} below 1.0)")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
