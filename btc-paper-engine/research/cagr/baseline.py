"""Baseline: the engine exactly as deployed, on the shared harness.

S5 = S3 pullback 75% + S4 donchian-20/trail-5 25%, blend lev 1.5, so leg
weights at k = 1 are 1.125 and 0.375 of equity. Live runs KELLY_M 0.20 of
this (k = 0.20). Fees 4.32 bps/side (live HL). Engine re-run per window
(start_ts gate, indicators on full history) so no position leaks across a
window boundary - the bench_blend.py convention.

Writes baseline.json.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H                                                 # noqa: E402

W_PULL, W_TREND, LEV = 0.75, 0.25, 1.5


def legs_for(bars, t0, t1, donchian_fn=None, inds=None):
    pull = H.leg_trades(bars, "pullback", start_ts=t0, end_ts=t1, inds=inds,
                        leg="pullback")
    trend = H.leg_trades(bars, "donchian", start_ts=t0, end_ts=t1, inds=inds,
                         donchian_fn=donchian_fn, leg="trend")
    return [H.LegSpec(pull, W_PULL * LEV), H.LegSpec(trend, W_TREND * LEV)]


def evaluate(bars, closes, t0, t1, donchian_fn=None, inds=None,
             do_ksafe=True):
    legs = legs_for(bars, t0, t1, donchian_fn, inds)
    out = {}
    for k in (1.0, 0.20):
        r = H.simulate(legs, closes, k=k, start_ts=t0, end_ts=t1)
        out[f"k={k}"] = H.stats(r)
    kdd = H.k_at_dd(legs, closes, 0.30, start_ts=t0, end_ts=t1)
    r = H.simulate(legs, closes, k=kdd, start_ts=t0, end_ts=t1)
    out["k_at_dd30_realised"] = dict(k=kdd, **H.stats(r))
    if do_ksafe:
        r1 = H.simulate(legs, closes, k=1.0, start_ts=t0, end_ts=t1)
        unit = np.diff(r1.equity) / r1.equity[:-1]
        ks, meta = H.k_safe(unit)
        r = H.simulate(legs, closes, k=ks, start_ts=t0, end_ts=t1)
        out["k_safe_boot"] = dict(k=ks, **meta, **H.stats(r))
    return out


def main():
    bars = H.load_bars("btcusd")
    closes = {"btcusd": H.closes_of(bars)}
    inds = H.compute_indicators(bars, 20)
    res = {}
    windows = {"FULL 2013-2026": H.FULL, **H.ERAS}
    for name, (a, b) in windows.items():
        t0, t1 = H.ts_of(a), H.ts_of(b) + 86399
        res[name] = evaluate(bars, closes, t0, t1, inds=inds,
                             do_ksafe=name.startswith("FULL"))
        s = res[name]["k=1.0"]
        print(f"{name:24s} k=1: CAGR {s['cagr']*100:7.1f}%  MTMdd "
              f"{s['maxdd']*100:6.1f}%  MAR {s['mar'] or 0:5.2f}  "
              f"Sharpe {s['sharpe'] or 0:5.2f}  n={s['n']}", flush=True)
    with open(os.path.join(HERE, "baseline.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    f = res["FULL 2013-2026"]
    for key in ("k=1.0", "k=0.2", "k_at_dd30_realised", "k_safe_boot"):
        s = f[key]
        print(f"FULL {key:22s} k={s.get('k', key)!s:>8.6}  CAGR "
              f"{s['cagr']*100:6.1f}%  MTMdd {s['maxdd']*100:6.1f}%  "
              f"maxGrossLev {s.get('max_gross_lev', 0):.2f}")


if __name__ == "__main__":
    main()
