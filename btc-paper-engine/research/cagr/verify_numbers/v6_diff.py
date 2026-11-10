"""Paired stationary block bootstrap of Sharpe DIFFERENCE vs baseline, and
pure-trend / pure-pullback reference points (diagnostic)."""
import os, sys, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
W = C.World()
def R(build, a, b):
    t0, t1 = H.ts_of(a), H.ts_of(b) + 86399
    legs, cl = build(W, t0, t1)
    r = H.simulate(legs, cl, 1.0, t0, t1)
    p = np.concatenate([[r.start_equity], r.equity]); return np.diff(p)/p[:-1]
def static(s):
    def b(W, t0, t1):
        return ([H.LegSpec(W.trades("btcusd","pullback",t0,t1), 1.5*(1-s)),
                 H.LegSpec(W.trades("btcusd","donchian",t0,t1, donchian_fn=H.process_donchian_resting_stop), 1.5*s)],
                {"btcusd": W.closes["btcusd"]})
    return b
sh = lambda x: x.mean()/x.std()*math.sqrt(H.BARS_PER_YEAR)
for a, b in (("2013-01-01","2026-07-31"), ("2020-01-01","2026-07-31"), ("2022-01-01","2026-07-31")):
    base = R(C.baseline, a, b)
    print(f"window {a}..{b}: baseline Sh {sh(base):.3f}; pure pullback {sh(R(static(0.0),a,b)):.3f}; pure trend {sh(R(static(1.0),a,b)):.3f}")
    for n in ("H5a H1+H2a", "H5b H1+H2b"):
        x = R(C.CANDIDATES[n], a, b)
        rng = np.random.default_rng(11); n_ = len(x); d = []
        for _ in range(1000):
            idx = H._stationary_bootstrap_idx(n_, n_, 180.0, rng)
            d.append(sh(x[idx]) - sh(base[idx]))
        d = np.array(d)
        print(f"   {n}: dSharpe {sh(x)-sh(base):+.3f}  boot 5-95% [{np.percentile(d,5):+.3f},{np.percentile(d,95):+.3f}]  P(d<=0) {np.mean(d<=0):.3f}")
