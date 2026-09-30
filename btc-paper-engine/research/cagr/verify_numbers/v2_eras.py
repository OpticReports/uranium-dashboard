import os, sys, json, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
W = C.World()
B = {"baseline": C.baseline, "H5a": C.CANDIDATES["H5a H1+H2a"], "H5b": C.CANDIDATES["H5b H1+H2b"]}
def run(build, a, b, k=1.0):
    t0, t1 = H.ts_of(a), H.ts_of(b) + 86399
    legs, cl = build(W, t0, t1)
    return H.simulate(legs, cl, k=k, start_ts=t0, end_ts=t1), legs, cl, t0, t1
out = {}
wins = {"FULL": H.FULL, "FULL-to-2026-07": ("2013-01-01","2026-07-31"),
        "ex2013 2014-2026-07": ("2014-01-01", "2026-07-31"),
        "ex2013-2014 2015-2026-07": ("2015-01-01", "2026-07-31"),
        **{k[:2]: v for k, v in H.ERAS.items()},
        "E1ex2013 2014-16": ("2014-01-01","2016-12-31")}
for y in range(2013, 2027):
    wins[str(y)] = (f"{y}-01-01", f"{y}-12-31")
for n, bld in B.items():
    out[n] = {}
    for wn, (a, b) in wins.items():
        r, legs, cl, t0, t1 = run(bld, a, b)
        s = H.stats(r)
        row = dict(sharpe=s["sharpe"], cagr=s["cagr"], dd=s["maxdd"], n=s["n"])
        if wn in ("FULL", "FULL-to-2026-07", "ex2013 2014-2026-07", "ex2013-2014 2015-2026-07"):
            path = np.concatenate([[r.start_equity], r.equity])
            ks, _ = H.k_safe(np.diff(path) / path[:-1])
            kd = H.k_at_dd(legs, cl, 0.30, start_ts=t0, end_ts=t1)
            rs = H.stats(H.simulate(legs, cl, k=ks, start_ts=t0, end_ts=t1))
            ku = min(ks, kd)
            ru = H.stats(H.simulate(legs, cl, k=ku, start_ts=t0, end_ts=t1))
            row.update(k_safe=ks, cagr_ks=rs["cagr"], dd_ks=rs["maxdd"], k_dd=kd, k_use=ku, cagr_ku=ru["cagr"], dd_ku=ru["maxdd"])
        out[n][wn] = row
    print(n, "done", flush=True)
json.dump(out, open(os.path.join(HERE, "v2_eras.json"), "w"), indent=1, default=float)
for wn in wins:
    line = f"{wn:26s}"
    for n in B:
        r = out[n][wn]
        line += f" | {n}: Sh {r['sharpe'] or 0:5.2f} ret {r['cagr']*100:7.1f}%"
    print(line)
for wn in ("FULL", "FULL-to-2026-07", "ex2013 2014-2026-07", "ex2013-2014 2015-2026-07"):
    for n in B:
        r = out[n][wn]
        print(f"{wn:26s} {n:8s} k_safe {r['k_safe']:.3f} CAGR {r['cagr_ks']*100:5.1f}% DD {r['dd_ks']*100:5.1f}% | k_dd30 {r['k_dd']:.3f} | k_use {r['k_use']:.3f} CAGR {r['cagr_ku']*100:5.1f}% DD {r['dd_ku']*100:5.1f}%")
