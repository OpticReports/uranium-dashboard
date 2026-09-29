"""Diagnostic sweep of static trend share s (gross 1.5), with H1 resting stop. 11 trials."""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness as H, candidates as C
W = C.World()
def build(s):
    def b(W, t0, t1):
        return ([H.LegSpec(W.trades("btcusd","pullback",t0,t1), 1.5*(1-s)),
                 H.LegSpec(W.trades("btcusd","donchian",t0,t1, donchian_fn=H.process_donchian_resting_stop), 1.5*s)],
                {"btcusd": W.closes["btcusd"]})
    return b
eras = {k[:2]: v for k, v in H.ERAS.items() if k[:2] in ("E1","E2","E3","E4","E5")}
eras["x13"] = ("2014-01-01","2026-07-31")
base = {}
out = {}
shares = [0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75]
for s in shares:
    row = {}
    for en,(a,b) in {"FULL": ("2013-01-01","2026-07-31"), **eras}.items():
        t0,t1 = H.ts_of(a), H.ts_of(b)+86399
        legs, cl = build(s)(W,t0,t1)
        r = H.simulate(legs, cl, 1.0, t0, t1); st = H.stats(r)
        row[en] = st["sharpe"]
        if en == "FULL":
            path = np.concatenate([[r.start_equity], r.equity])
            ks,_ = H.k_safe(np.diff(path)/path[:-1])
            kd = H.k_at_dd(legs, cl, 0.30, start_ts=t0, end_ts=t1)
            row["cagr_ks"] = H.stats(H.simulate(legs, cl, ks, t0, t1))["cagr"]
            row["cagr_ku"] = H.stats(H.simulate(legs, cl, min(ks,kd), t0, t1))["cagr"]
            row["ks"], row["kd"] = ks, kd
    out[s] = row
    print(f"s={s:.2f} FULL Sh {row['FULL']:.3f} x13 {row['x13']:.3f} | E1 {row['E1']:.2f} E2 {row['E2']:.2f} E3 {row['E3']:.2f} E4 {row['E4']:.2f} E5 {row['E5']:.2f} | k_safe {row['ks']:.3f} CAGR {row['cagr_ks']*100:.1f}% | k_use {min(row['ks'],row['kd']):.3f} CAGR {row['cagr_ku']*100:.1f}%", flush=True)
json.dump(out, open(os.path.join(HERE,"v3_sweep.json"),"w"), indent=1)
