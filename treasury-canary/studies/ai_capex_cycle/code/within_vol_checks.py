import json, sys, os, csv, math, numpy as np
from collections import defaultdict
eps = json.load(open(sys.argv[1])); RAW = sys.argv[2]
frows = list(csv.reader(open(os.path.join(RAW, "F-F_Research_Data_Factors.csv"))))
fi = next(i for i, r in enumerate(frows) if r and r[0].strip() == "" and "Mkt-RF" in r[1])
mkt = {}
for r in frows[fi + 1:]:
    if not r or len(r[0].strip()) != 6 or not r[0].strip().isdigit(): break
    mkt[r[0].strip()] = (float(r[1]) + float(r[4])) / 100
months = sorted(mkt); PM = np.cumprod([1 + mkt[m] for m in months]); idx = {m: i for i, m in enumerate(months)}
for e in eps: e["crash"] = int(e["fut_maxdd"] >= 0.4); e["c0"] = int(e["corr10"] == 0)
# cluster ids (gap>12m across all episodes)
ms = sorted(set(e["month"] for e in eps)); cid = {}; c = 0
for a, b in zip([None] + ms, ms):
    if a is not None and idx[b] - idx[a] > 12: c += 1
    cid[b] = c
for e in eps: e["cl"] = cid[e["month"]]
try:
    from scipy.stats import fisher_exact
except Exception:
    fisher_exact = None
vals = sorted(e["vol"] for e in eps); q1, q2 = vals[len(vals)//3], vals[2*len(vals)//3]
print("== within-vol cells: composition of corr0 vs corr>=1 (mean raw24, accel, mkt_fut_maxdd, n clusters), Fisher p")
for lab, sel in (("low", [e for e in eps if e["vol"] < q1]), ("mid", [e for e in eps if q1 <= e["vol"] < q2]), ("high", [e for e in eps if e["vol"] >= q2])):
    a = [e for e in sel if e["c0"]]; b = [e for e in sel if not e["c0"]]
    ka, kb = sum(e["crash"] for e in a), sum(e["crash"] for e in b)
    p = fisher_exact([[ka, len(a) - ka], [kb, len(b) - kb]])[1] if fisher_exact and a and b else float('nan')
    f = lambda g, k: (np.mean([e[k] for e in g]) if g else float('nan'))
    print(f"vol {lab}: corr0 n={len(a)} crash={ka} ({ka/len(a) if a else 0:.2f}) raw24={f(a,'raw24'):.2f} accel={f(a,'accel'):.2f} mktfutdd={f(a,'mkt_fut_maxdd'):.2f} clusters={len(set(e['cl'] for e in a))} | corr>=1 n={len(b)} crash={kb} ({kb/len(b) if b else 0:.2f}) raw24={f(b,'raw24'):.2f} accel={f(b,'accel'):.2f} mktfutdd={f(b,'mkt_fut_maxdd'):.2f} clusters={len(set(e['cl'] for e in b))} | Fisher p={p:.3f}")
    # which clusters do the corr0 crashes come from
    cc = defaultdict(int)
    for e in a:
        if e["crash"]: cc[e["month"][:4]] += 1
    print("    corr0 crash years:", dict(sorted(cc.items())))
    cc = defaultdict(int)
    for e in b:
        if e["crash"]: cc[e["month"][:4]] += 1
    print("    corr>=1 crash years:", dict(sorted(cc.items())))
print("\n== Mantel-Haenszel pooled OR (corr0 vs crash) across vol terciles")
num = den = 0
for lab, sel in (("low", [e for e in eps if e["vol"] < q1]), ("mid", [e for e in eps if q1 <= e["vol"] < q2]), ("high", [e for e in eps if e["vol"] >= q2])):
    a = sum(e["crash"] and e["c0"] for e in sel); b = sum((not e["crash"]) and e["c0"] for e in sel); c_ = sum(e["crash"] and not e["c0"] for e in sel); d = sum((not e["crash"]) and not e["c0"] for e in sel); n = len(sel)
    num += a * d / n; den += b * c_ / n
print("  MH OR =", round(num / den, 2))
print("\n== logit crash ~ raw24 + vol + corr0 (+accel), cluster bootstrap over", c + 1, "clusters")
X = np.array([[1, e["raw24"], e["vol"], e["c0"], e["accel"] or 0] for e in eps], float); y = np.array([e["crash"] for e in eps], float)
def logit(X, y, it=200):
    b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p) + 1e-9
        H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(X.shape[1]); g = X.T @ (y - p)
        b = b + np.linalg.solve(H, g)
    return b
b = logit(X, y); print("  coef [const, raw24, vol, corr0, accel]:", np.round(b, 2))
cl = np.array([e["cl"] for e in eps]); rng = np.random.default_rng(0); B = []
for _ in range(500):
    pick = rng.choice(c + 1, c + 1, replace=True); rows = np.concatenate([np.where(cl == k)[0] for k in pick])
    try: B.append(logit(X[rows], y[rows]))
    except Exception: pass
B = np.array(B); print("  cluster-bootstrap 5-95%:", np.round(np.percentile(B, [5, 95], axis=0), 2))
print("  P(corr0 coef > 0) =", np.mean(B[:, 3] > 0).round(2))
print("\n== cluster-level view: clusters, episodes, crash rate")
for k in range(c + 1):
    g = [e for e in eps if e["cl"] == k]
    print(f"  cluster {k:2d} {g[0]['month']}-{g[-1]['month']} n={len(g):3d} crash={np.mean([e['crash'] for e in g]):.2f} mkt_fut_dd={np.mean([e['mkt_fut_maxdd'] for e in g]):.2f}")
print("  clusters with crash rate >=50%:", sum(np.mean([e['crash'] for e in eps if e['cl'] == k]) >= 0.5 for k in range(c + 1)))
