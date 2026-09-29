"""Trade concentration: drop top-N trend winners from each construction."""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
W = C.World()
t0, t1 = H.ts_of("2013-01-01"), H.ts_of("2026-07-31") + 86399
def uret(t):
    if t.exit_ts is None: return 0.0
    sg = 1 if t.side=="L" else -1
    return sg*(t.exit_price/t.entry_price-1)
B = {"baseline": C.baseline, "H5a": C.CANDIDATES["H5a H1+H2a"], "H5b": C.CANDIDATES["H5b H1+H2b"]}
# per-leg unit trade stats
for nm, fn in (("pull", None), ("trend_prod", None), ("trend_rest", H.process_donchian_resting_stop)):
    strat = "pullback" if nm=="pull" else "donchian"
    tr = W.trades("btcusd", strat, t0, t1, donchian_fn=fn)
    u = np.array([uret(t) for t in tr])
    s = np.sort(u)[::-1]
    print(nm, "n", len(u), "sum logret %.2f" % np.log1p(u).sum(), "top5 sum log %.2f" % np.log1p(s[:5]).sum(), "top10 %.2f"% np.log1p(s[:10]).sum())
    yrs = pd.Series(np.log1p(u), index=[pd.Timestamp(t.entry_ts,unit='s').year for t in tr]).groupby(level=0).sum()
    print("   by-year sum log unit ret:", " ".join(f"{y}:{v:+.2f}" for y,v in yrs.items()))
for N in (0, 3, 5, 10):
    line = f"drop top{N:2d} trend winners:"
    res = {}
    for n, bld in B.items():
        legs, cl = bld(W, t0, t1)
        new = []
        for lg in legs:
            if lg.trades and lg.trades[0].leg == "donchian" and N:
                keep = sorted(lg.trades, key=uret, reverse=True)[N:]
                keep = sorted(keep, key=lambda t: t.entry_ts)
                lg = H.LegSpec(keep, lg.weight, lg.asset, lg.weight_fn)
            new.append(lg)
        r = H.simulate(new, cl, 1.0, t0, t1); s = H.stats(r)
        res[n] = s
        line += f" {n} Sh {s['sharpe']:.3f} CAGR {s['cagr']*100:5.1f}% |"
    print(line)
