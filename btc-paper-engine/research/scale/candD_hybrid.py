"""CANDIDATE D: the missing cell -- PERP prices with SPOT volume.

candD_instrument.py showed rec_m 0.47 on spot bars and 0.00 on perp bars.
candD_signal_agree.py showed the pullback signal agrees only 69% across the two
series WITH the volume filter but 94% WITHOUT it -- the same 94% as the pure
price donchian control.  So the disagreement is the VOLUME SOURCE, not the
prices.  That leaves one cell unmeasured, and it decides the reading:

    perp PRICES + spot VOLUME

If the edge comes back, the strategy is not fragile to the price series and the
'edge dies on the traded instrument' result is purely about whose volume you
read -- which the engine is free to choose, since it is a keyless decision brain.
If it does NOT come back, the price series itself is load-bearing and the edge is
knife-edge.

Run: python3 research/scale/candD_hybrid.py
"""
from __future__ import annotations
import bisect, csv, dataclasses, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "..", "backend")
sys.path.insert(0, BACKEND)
from app.engine.core import Bar                                   # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.engine.kelly import analyze, SEED                        # noqa: E402
from app.config import (RESEARCH_BOOKS, RESEARCH_SIGNAL,          # noqa: E402
                        RESEARCH_TRADE)

SPOTB = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
PERPB = os.path.join(HERE, "candD_bars_4h_btcperp.csv")
FUND = os.path.join(HERE, "funding_hl_btc.csv")
BASIS = os.path.join(HERE, "candD_perp_4h.csv")
OUT = os.path.join(HERE, "candD_hybrid.json")
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
    sv = {b.ts: b.volume for b in spot}
    pv = {b.ts: b.volume for b in perp}
    # HYBRID: perp OHLC, spot volume (only bars where both exist)
    hybrid = [Bar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
                  volume=sv[b.ts]) for b in perp if b.ts in sv]
    # CONTROL: spot OHLC, perp volume
    control = [Bar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close,
                   volume=pv[b.ts]) for b in spot if b.ts in pv]
    print(f"hybrid bars (perp OHLC + spot volume): {len(hybrid)}")
    print(f"control bars (spot OHLC + perp volume): {len(control)}")

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

    start_ts = perp[210].ts
    end_ts = min(max(b.ts for b in spot), max(b.ts for b in perp))
    tc = dataclasses.replace(RESEARCH_TRADE, taker_fee_bps=TAKER)

    def run(bars, apply_basis):
        ev = []
        for bn, w in (("S3", 1 - W_TREND), ("S4", W_TREND)):
            bk = [b for b in RESEARCH_BOOKS if b.name == bn]
            trs = run_replay(bars, bk, RESEARCH_SIGNAL, tc, start_ts=start_ts,
                             end_ts=end_ts, cash_apy=0.0).books[bn].trades
            for t in trs:
                sgn = 1.0 if t.side == "L" else -1.0
                fee = t.fees_usd / t.notional
                if apply_basis:
                    b0, b1 = bc.get(t.signal_ts), bc.get(t.exit_ts)
                    if b0 is None or b1 is None:
                        continue
                    ratio = (t.exit_price*(1+b1)) / (t.entry_price*(1+b0))
                else:
                    ratio = t.exit_price / t.entry_price
                g = (ratio-1) if t.side == "L" else (1-ratio)
                fund = -sgn * fsum(t.entry_ts, t.exit_ts)
                ev.append((t.exit_ts, REF_LEV*w*(g-fee+fund)
                           * t.notional/t.equity_before))
        ev.sort()
        return [x for _, x in ev]

    arms = [
        ("spot OHLC + spot volume  (LIVE config)", spot, True),
        ("perp OHLC + perp volume", perp, False),
        ("perp OHLC + SPOT volume  (the missing cell)", hybrid, False),
        ("spot OHLC + PERP volume  (control)", control, True),
    ]
    res = {"arms": {}}
    print(f"\n{'arm':<46}{'n':>5}{'mean%':>9}{'kelly_m':>9}{'p10':>7}"
          f"{'pneg':>7}{'rec_m':>7}{'gross $':>11}")
    print("-" * 101)
    for label, bars, ab in arms:
        s = run(bars, ab)
        A = analyze(s, label)
        recs = [analyze(s, label, seed=sd)["recommended_m"] for sd in SEEDS]
        res["arms"][label] = {
            "n": A["n"], "mean_pct": A["mean_pct"], "sd_pct": A["sd_pct"],
            "kelly_m": A["kelly_m"], "p10": A["bootstrap"]["p10"],
            "prob_negative_edge": A["bootstrap"]["prob_negative_edge"],
            "dd30_m": A["dd_constrained"]["p_maxdd30_le_10pct"],
            "recommended_m": A["recommended_m"],
            "authorised_gross_usd": A["recommended_m"]*REF_LEV*EQUITY,
            "rec_m_across_seeds": recs, "verdict": A["verdict"]}
        print(f"{label:<46}{A['n']:>5}{A['mean_pct']:>9}{A['kelly_m']:>9}"
              f"{A['bootstrap']['p10']:>7}"
              f"{A['bootstrap']['prob_negative_edge']:>7}"
              f"{A['recommended_m']:>7.2f}"
              f"{A['recommended_m']*REF_LEV*EQUITY:>11,.0f}")
        print(f"{'':<46}seeds {recs}")
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
