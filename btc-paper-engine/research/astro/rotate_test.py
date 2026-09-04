"""THE definitive null for calendar effects: circularly rotate the calendar
mask against the return series. This preserves (a) the mask's exact clustering
and duty cycle and (b) the return series' exact volatility clustering, while
destroying only the alignment between them. Strictly better than the block
bootstrap, which under-states variance when the 'on' days are few and
heteroskedastic (it gave lunar_eclipse p=0.003 at |t|=1.44 - impossible).

Also tests the SECOND outcome: |return| (volatility), which is the one with a
plausible use for us - stop width and sizing, not direction.
"""
import csv, json
import numpy as np
from scipy import stats

rng = np.random.default_rng(7)
res_prev = {r["test"]: r for r in json.load(open("battery_results.json"))}
feat = json.load(open("features.json"))
rows = list(csv.DictReader(open("../btc_daily_full.csv")))
close = np.array([float(r["close"]) for r in rows])
ret = np.diff(np.log(close))
n = len(ret)

# rebuild masks exactly as battery.py did
import importlib.util, sys, types
src = open("battery.py").read().split("# --- statistics")[0]
src = src.replace('json.dump(res', '#').replace('print(', '#print(')
ns = {"__name__": "m"}
exec(compile(src, "masks", "exec"), ns)
tests = ns["tests"]
valid = ns["valid"]

NROT = 5000
offsets = rng.integers(1, n-1, NROT)
absret = np.abs(ret)

def rot_p(mask, y):
    m = mask[valid][:n] if len(mask) != n else mask
    m = np.asarray(m, bool)
    obs = y[m].mean() - y[~m].mean()
    non = m.sum(); noff = n - non
    idx = (np.arange(n)[None, :] + offsets[:, None]) % n
    M = m[idx]                                    # NROT x n rotated masks
    d = (M @ y) / non - ((~M) @ y) / noff
    return obs, (np.sum(np.abs(d) >= abs(obs)) + 1) / (NROT + 1)

out = []
for name, (fam, mask) in tests.items():
    m = mask[valid][:n] if mask.shape[0] != n else mask
    m = np.asarray(m, bool)[:n]
    if m.sum() < 20 or m.sum() > n-20: continue
    o_r, p_r = rot_p(m, ret)
    o_v, p_v = rot_p(m, absret)
    t_r = stats.ttest_ind(ret[m], ret[~m], equal_var=False)
    t_v = stats.ttest_ind(absret[m], absret[~m], equal_var=False)
    out.append({"test": name, "family": fam, "n_on": int(m.sum()),
                "ret_edge_bps": float(o_r*1e4), "ret_t": float(t_r.statistic),
                "ret_p_rot": float(p_r), "ret_p_welch": float(t_r.pvalue),
                "vol_edge_bps": float(o_v*1e4), "vol_t": float(t_v.statistic),
                "vol_p_rot": float(p_v), "vol_p_welch": float(t_v.pvalue)})
json.dump(out, open("rotate_results.json","w"), indent=1)

A=[r for r in out if r["family"][0] in "ABCDEF"]
G=[r for r in out if r["family"]=="G_control"]
H=[r for r in out if r["family"]=="H_null"]
print(f"{len(out)} tests | rotation null, {NROT} rotations\n")
for lbl, key in (("DIRECTION (next-day return)","ret_p_rot"),
                 ("VOLATILITY (|next-day return|)","vol_p_rot")):
    print(f"--- {lbl} ---")
    for nm, rs in (("astrology A-F",A),("controls G",G),("nulls H",H)):
        a=sum(r[key]<0.05 for r in rs)
        print(f"   {nm:<16} p<0.05: {a}/{len(rs)} ({100*a/len(rs):5.1f}%)  [chance 5.0%]")
    def bh(rs,q=0.10):
        p=np.array([r[key] for r in rs]); o=np.argsort(p); m=len(p)
        ok=p[o]<=q*np.arange(1,m+1)/m
        return (p[o][np.max(np.where(ok)[0])] if ok.any() else 0.0), int(ok.sum() and np.max(np.where(ok)[0])+1)
    c,k=bh(A); print(f"   BH-FDR q=0.10 -> {k} survivor(s) (crit p={c:.5f})")
    print(f"   top 6:")
    for r in sorted(A,key=lambda x:x[key])[:6]:
        e = r["ret_edge_bps"] if key.startswith("ret") else r["vol_edge_bps"]
        t = r["ret_t"] if key.startswith("ret") else r["vol_t"]
        print(f"     {r['test']:<32}{r['n_on']:>6}{e:>9.1f}bps  t={t:>6.2f}  p={r[key]:.4f}")
    print()
