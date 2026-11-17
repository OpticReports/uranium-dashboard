"""Exploratory follow-up: daily band check (20%), full rebalance executed k trading days after the breach."""
import sys, json
import numpy as np, pandas as pd
D = sys.argv[1]
src = open(D + "/cadence.py").read().split("if __name__")[0]
g = {"__name__": "x"}; sys.argv = ["x", D]; exec(src, g)

def sim_delay(R, w, c, band, k):
    Pn, T, N = R.shape
    H = np.tile(w * (1 - c), (Pn, 1)); cd = np.full(Pn, -1); n = np.zeros(Pn, int)
    for t in range(T):
        H = H * (1 + R[:, t])
        cd[cd > 0] -= 1
        go = cd == 0
        if go.any():
            W = H[go].sum(1, keepdims=True); tr = np.abs(w * W - H[go]); fee = (tr * c).sum(1, keepdims=True)
            H[go] = w * (W - fee); cd[go] = -1; n[go] += 1
        W = H.sum(1, keepdims=True); trig = (np.abs(H / W / w - 1) > band).any(1) & (cd < 0)
        cd[trig] = k
    return g["cagr"](H.sum(1)[:, None], n=T), n

out = {}
tick = list(g["TARGETS"]); w = np.array([g["TARGETS"][t] for t in tick]); c = np.array([g["COST_BPS"][t] * 1e-4 for t in tick])
t6 = tick[:-1]; w6 = w[:-1] / w[:-1].sum(); c6 = c[:-1]
rng = np.random.default_rng(11)
for lab, tk, ww, cc, prox in [("A", tick, w, c, False), ("B", tick, w, c, True), ("C", t6, w6, c6, True)]:
    R = g["build"](tk, prox)[1]; idx = R.index; Rv = R.values
    row = {}
    # bootstrap paths: monthly blocks
    per = idx.to_period("M"); blocks = [np.where(per == p)[0] for p in per.unique()]
    Rb = np.empty((500, len(idx), len(tk)))
    for p in range(500):
        rows = []
        while len(rows) < len(idx): rows.extend(blocks[rng.integers(len(blocks))])
        Rb[p] = Rv[np.array(rows[:len(idx)])]
    base_b = sim_delay(Rb, ww, cc, .2, 1)[0]
    for k in [1, 2, 3, 5, 10, 21]:
        cg, n = sim_delay(Rv[None], ww, cc, .2, k)
        bb = sim_delay(Rb, ww, cc, .2, k)[0] - base_b
        row[k] = dict(cagr=float(cg[0]), n_reb=int(n[0]), boot_vs_k1_bps=float(bb.mean() * 1e4),
                      ci95=[float(np.percentile(bb, 2.5) * 1e4), float(np.percentile(bb, 97.5) * 1e4)])
    out[lab] = row
    print(lab, {k: (round(v["cagr"] * 100, 2), v["n_reb"], round(v["boot_vs_k1_bps"], 1), [round(x) for x in v["ci95"]]) for k, v in row.items()})
json.dump(out, open(D + "/delay_probe.json", "w"), indent=1)
