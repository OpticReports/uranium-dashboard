import os, sys, math
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, "/home/user/uranium-dashboard/barbell-lab/src")
from barbell.stats import dsr as D
import harness as H, candidates as C
W = C.World()
# calibrate: reproduce Protocol §2 hurdles with V[SR_ann]=1/years
for N, yrs, want in ((1500, 4.5, 1.58), (28, 4.5, 0.96)):
    print("check §2 hurdle N=%d: %.2f (doc %.2f)" % (N, D.expected_max_sharpe(N, 1/yrs), want))
t0, t1 = H.ts_of("2013-01-01"), H.ts_of("2026-07-31") + 86399
for n in ("baseline", "H5a H1+H2a", "H5b H1+H2b"):
    legs, cl = C.CANDIDATES[n](W, t0, t1)
    r = H.simulate(legs, cl, 1.0, t0, t1)
    path = np.concatenate([[r.start_equity], r.equity]); ret = np.diff(path)/path[:-1]
    T = len(ret); yrs = T / H.BARS_PER_YEAR
    sr = D.sharpe_ratio(ret); m = D.moments(ret)
    for N in (7, 2522, 2533):
        # per-period null variance of SR estimator = 1/T  (equiv. annual 1/years)
        d = D.deflated_sharpe(sr, T, N, 1.0/T, skew=m["skew"], kurt=m["kurt"])
        dn = D.deflated_sharpe(sr, T, N, 1.0/T)
        print(f"{n:12s} N={N:4d} SR_ann {sr*math.sqrt(H.BARS_PER_YEAR):.3f} SR0_ann {d['sr0']*math.sqrt(H.BARS_PER_YEAR):.3f} DSR {d['dsr']:.3f} (normal-moments {dn['dsr']:.3f}) skew {m['skew']:.2f} kurt {m['kurt']:.1f} yrs {yrs:.1f}")
