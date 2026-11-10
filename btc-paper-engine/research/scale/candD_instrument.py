"""CANDIDATE D: does the edge survive on the instrument it actually trades?

candD_fixaxis.py returned recommended_m = 0.00 on PERP bars where SPOT bars
give 0.43, over the SAME window.  Before that can be reported it has to be
separated from a confound: eval_signal has vol_filter=True and tests
bar.volume > vol_sma20, and the VOLUME SERIES is venue-specific even though
the test itself is scale-invariant.  So four arms:

    spot bars / vol filter ON   = the shipped configuration
    perp bars / vol filter ON
    spot bars / vol filter OFF  = price-only
    perp bars / vol filter OFF  = price-only

If the perp failure survives with the volume filter OFF, it is a PRICE result
and the edge is specific to the Bitstamp series.  If it disappears, the failure
was the volume series and the price edge transfers.

Run: python3 research/scale/candD_instrument.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar, SignalCfg                        # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze, SEED                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOTB = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
PERPB = os.path.join(HERE, "candD_bars_4h_btcperp.csv")
BASIS = os.path.join(HERE, "candD_perp_4h.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
OUT = os.path.join(HERE, "candD_instrument.json")
EQUITY, REF_LEV, W_TREND, TAKER = 100_055.0, 1.5, 0.25, 4.32
SEEDS = [SEED, 11, 101, 1009, 777, 4242]


def bars_from(p):
    with open(p) as f:
        return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                    high=float(r["high"]), low=float(r["low"]),
                    close=float(r["close"]), volume=float(r["volume"]))
                for r in csv.DictReader(f)]


def main() -> None:
    spot, perp = bars_from(SPOTB), bars_from(PERPB)
    bc = {}
    with open(BASIS) as f:
        for r in csv.DictReader(f):
            bc[int(r["ts"])] = float(r["basis_close_bps"]) / 1e4
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

    start_ts = perp[210].ts
    end_ts = min(max(b.ts for b in spot), max(b.ts for b in perp))
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=TAKER)

    # price-series comparability, for the record
    sp = {b.ts: b for b in spot}
    pp = {b.ts: b for b in perp}
    common = sorted(set(sp) & set(pp))
    rs = [(sp[common[i]].close / sp[common[i-1]].close - 1) for i in range(1, len(common))]
    rp = [(pp[common[i]].close / pp[common[i-1]].close - 1) for i in range(1, len(common))]
    ms, mp = statistics.fmean(rs), statistics.fmean(rp)
    cov = sum((a-ms)*(b-mp) for a, b in zip(rs, rp)) / (len(rs)-1)
    corr = cov / (statistics.stdev(rs) * statistics.stdev(rp))
    vs = [sp[t].volume for t in common]; vp = [pp[t].volume for t in common]
    mvs, mvp = statistics.fmean(vs), statistics.fmean(vp)
    vcov = sum((a-mvs)*(b-mvp) for a, b in zip(vs, vp)) / (len(vs)-1)
    vcorr = vcov / (statistics.stdev(vs) * statistics.stdev(vp))
    res = {"start_ts": start_ts, "end_ts": end_ts,
           "price_return_corr_4h": corr, "volume_corr_4h": vcorr,
           "n_common_bars": len(common), "arms": {}}
    print(f"4h close-return correlation spot vs perp: {corr:.6f}")
    print(f"4h VOLUME correlation      spot vs perp: {vcorr:.4f}")

    def steps(bars, scfg, apply_basis):
        ev = []
        for bn, w in (("S3", 1 - W_TREND), ("S4", W_TREND)):
            bk = [b for b in RESEARCH_BOOKS if b.name == bn]
            trs = run_replay(bars, bk, scfg, tc, start_ts=start_ts,
                             end_ts=end_ts, cash_apy=0.0).books[bn].trades
            for t in trs:
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
                fund = -sgn * fsum(t.entry_ts, t.exit_ts)
                ev.append((t.exit_ts, REF_LEV * w * (g - fee + fund)
                           * t.notional / t.equity_before))
        ev.sort()
        return [x for _, x in ev]

    arms = [
        ("spot bars, vol filter ON  (shipped)", spot, True, True),
        ("perp bars, vol filter ON", perp, False, True),
        ("spot bars, vol filter OFF (price only)", spot, True, False),
        ("perp bars, vol filter OFF (price only)", perp, False, False),
    ]
    print(f"\n{'arm':<42}{'n':>5}{'mean%':>9}{'sd%':>8}{'kelly_m':>9}"
          f"{'p10':>7}{'dd30':>7}{'rec_m':>7}{'gross $':>11}")
    print("-" * 105)
    for label, bars, ab, vf in arms:
        scfg = dataclasses.replace(RESEARCH_SIGNAL, vol_filter=vf)
        s = steps(bars, scfg, ab)
        A = analyze(s, label)
        recs = [analyze(s, label, seed=sd)["recommended_m"] for sd in SEEDS]
        row = {"n": A["n"], "mean_pct": A["mean_pct"], "sd_pct": A["sd_pct"],
               "kelly_m": A["kelly_m"], "p10": A["bootstrap"]["p10"],
               "prob_negative_edge": A["bootstrap"]["prob_negative_edge"],
               "dd30_m": A["dd_constrained"]["p_maxdd30_le_10pct"],
               "half_kelly_m": A["half_kelly_m"],
               "conservative_m": A["conservative_m"],
               "shrinkage_c_star": A["shrinkage_c_star"],
               "recommended_m": A["recommended_m"],
               "authorised_gross_usd": A["recommended_m"] * REF_LEV * EQUITY,
               "rec_m_across_seeds": recs,
               "rec_m_seed_min": min(recs), "rec_m_seed_max": max(recs),
               "verdict": A["verdict"], "basis_applied": ab, "vol_filter": vf}
        res["arms"][label] = row
        print(f"{label:<42}{A['n']:>5}{A['mean_pct']:>9}{A['sd_pct']:>8}"
              f"{A['kelly_m']:>9}{A['bootstrap']['p10']:>7}"
              f"{A['dd_constrained']['p_maxdd30_le_10pct']:>7}"
              f"{A['recommended_m']:>7.2f}"
              f"{A['recommended_m']*REF_LEV*EQUITY:>11,.0f}")
        print(f"{'':<42}seeds {recs}  prob_neg_edge "
              f"{A['bootstrap']['prob_negative_edge']}")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
