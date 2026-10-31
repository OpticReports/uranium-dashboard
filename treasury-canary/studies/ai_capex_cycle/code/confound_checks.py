import json, sys, numpy as np
from collections import Counter, defaultdict
eps = json.load(open(sys.argv[1]))
# Need market drawdown preceding the run-up window: recompute from FF factors
import csv, os
RAW = sys.argv[2]
frows = list(csv.reader(open(os.path.join(RAW, "F-F_Research_Data_Factors.csv"))))
fi = next(i for i, r in enumerate(frows) if r and r[0].strip() == "" and "Mkt-RF" in r[1])
mkt = {}
for r in frows[fi + 1:]:
    if not r or len(r[0].strip()) != 6 or not r[0].strip().isdigit(): break
    mkt[r[0].strip()] = (float(r[1]) + float(r[4])) / 100
months = sorted(mkt); PM = np.cumprod([1 + mkt[m] for m in months]); idx = {m: i for i, m in enumerate(months)}
def mkt_dd_before(m, look=36):
    # max drawdown of market from its peak in the 36 months before the window start to window start (how far below prior high the market was at t-24)
    t = idx[m]; s = max(0, t - 24 - look); e = t - 24
    hi = PM[s:e + 1].max(); return 1 - PM[e] / hi
def mkt_ret_win(m):
    t = idx[m]; return PM[t] / PM[t - 24] - 1
for e in eps:
    e["mkt_dd_at_start"] = mkt_dd_before(e["month"]); e["mkt_ret24"] = mkt_ret_win(e["month"]); e["crash"] = e["fut_maxdd"] >= 0.4
    e["crash_net"] = e["fut_maxdd_net"] >= 0.4; e["dec"] = e["month"][:3] + "0s"
def summ(sel, lab):
    n = len(sel); k = sum(e["crash"] for e in sel); kn = sum(e["crash_net"] for e in sel)
    print(f"{lab:55s} n={n:4d} crash={k/n if n else float('nan'):.2f} crash_net={kn/n if n else float('nan'):.2f} medDD={np.median([e['fut_maxdd'] for e in sel]) if n else float('nan'):.2f}")
print("== decade distribution of episodes and crash rate")
for d, grp in sorted(defaultdict(list, {d: [e for e in eps if e['dec'] == d] for d in set(e['dec'] for e in eps)}).items()): summ(grp, d)
print("\n== calendar clusters (episode months grouped, gap>12m)")
ms = sorted(set(e["month"] for e in eps)); clusters = []; cur = [ms[0]]
for a, b in zip(ms, ms[1:]):
    if idx[b] - idx[a] > 12: clusters.append(cur); cur = []
    cur.append(b)
clusters.append(cur)
print(len(clusters), "clusters; sizes:", [(c[0], c[-1], sum(1 for e in eps if c[0] <= e["month"] <= c[-1])) for c in clusters])
print("\n== rebound confound: market drawdown at window start (how far below prior 3y high the market was when the run-up began)")
summ([e for e in eps if e["mkt_dd_at_start"] >= 0.40], "rebound from >=40% market drawdown")
summ([e for e in eps if e["mkt_dd_at_start"] < 0.40], "NOT rebound")
summ([e for e in eps if e["mkt_dd_at_start"] < 0.20], "market within 20% of high at start")
print("\n== market itself in the window")
summ([e for e in eps if e["mkt_ret24"] >= 0.5], "market +50% or more in same 24m")
summ([e for e in eps if e["mkt_ret24"] < 0.5], "market < +50%")
print("\n== corrections vs crash, within vol terciles (vol-matched)")
vals = sorted(e["vol"] for e in eps); q1, q2 = vals[len(vals)//3], vals[2*len(vals)//3]
for lab, sel in (("vol low", [e for e in eps if e["vol"] < q1]), ("vol mid", [e for e in eps if q1 <= e["vol"] < q2]), ("vol high", [e for e in eps if e["vol"] >= q2])):
    for c, lab2 in ((0, "0 corr"), (1, "1 corr"), (2, ">=2 corr")):
        s = [e for e in sel if (e["corr10"] == c if c < 2 else e["corr10"] >= 2)]
        summ(s, f"{lab} / {lab2}")
print("\n== spearman corr10 vs vol, corr10 vs raw24, vol vs raw24")
def sp(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b)); return np.corrcoef(ra, rb)[0, 1]
A = {k: np.array([e[k] for e in eps], float) for k in ("corr10", "vol", "raw24", "net24", "max_int_dd", "fut_maxdd", "fut_maxdd_net", "mkt_fut_maxdd", "mkt_dd_at_start")}
for a, b in (("corr10", "vol"), ("corr10", "raw24"), ("vol", "raw24"), ("corr10", "max_int_dd"), ("fut_maxdd", "mkt_fut_maxdd"), ("corr10", "fut_maxdd_net"), ("vol", "fut_maxdd_net"), ("raw24", "fut_maxdd_net"), ("net24", "fut_maxdd_net"), ("mkt_dd_at_start", "fut_maxdd")):
    print(f"  spearman({a},{b}) = {sp(A[a], A[b]):+.3f}")
print("\n== how much of 'crash' is the market crashing: episodes where market itself fell >=30% in the next 24m")
summ([e for e in eps if e["mkt_fut_maxdd"] >= 0.30], "market fell >=30% in next 24m")
summ([e for e in eps if e["mkt_fut_maxdd"] < 0.30], "market did NOT fall >=30%")
print("  share of crashes that coincide with market >=30% dd:", sum(e["crash"] and e["mkt_fut_maxdd"] >= 0.3 for e in eps) / sum(e["crash"] for e in eps))
print("\n== size terciles when market did NOT fall >=30% (does size still predict?)")
sub = [e for e in eps if e["mkt_fut_maxdd"] < 0.30]
vals = sorted(e["raw24"] for e in sub); q1, q2 = vals[len(vals)//3], vals[2*len(vals)//3]
summ([e for e in sub if e["raw24"] < q1], "size low"); summ([e for e in sub if q1 <= e["raw24"] < q2], "size mid"); summ([e for e in sub if e["raw24"] >= q2], "size high")
vals = sorted(e["vol"] for e in sub); q1, q2 = vals[len(vals)//3], vals[2*len(vals)//3]
summ([e for e in sub if e["vol"] < q1], "vol low"); summ([e for e in sub if q1 <= e["vol"] < q2], "vol mid"); summ([e for e in sub if e["vol"] >= q2], "vol high")
for c, lab2 in ((0, "0 corr"), (1, "1 corr"), (2, ">=2 corr")):
    summ([e for e in sub if (e["corr10"] == c if c < 2 else e["corr10"] >= 2)], lab2)
print("\n== post-1945 only")
sub = [e for e in eps if e["month"] >= "194601"]
summ(sub, "all post-1945")
for c, lab2 in ((0, "0 corr"), (1, "1 corr"), (2, ">=2 corr")):
    summ([e for e in sub if (e["corr10"] == c if c < 2 else e["corr10"] >= 2)], lab2)
vals = sorted(e["raw24"] for e in sub); q1, q2 = vals[len(vals)//3], vals[2*len(vals)//3]
summ([e for e in sub if e["raw24"] < q1], "post45 size low"); summ([e for e in sub if q1 <= e["raw24"] < q2], "post45 size mid"); summ([e for e in sub if e["raw24"] >= q2], "post45 size high")
print("\n== 1930s share of all episodes:", sum(e["dec"] == "1930s" for e in eps) / len(eps))
print("== the 'unrelieved' extreme: corr10==0 AND max_int_dd<0.05")
summ([e for e in eps if e["corr10"] == 0 and e["max_int_dd"] < 0.05], "very smooth (no 10% corr, max dd<5%)")
summ([e for e in eps if e["corr10"] == 0 and e["max_int_dd"] < 0.05 and e["month"] >= "194601"], "very smooth post-1945")
print("\n== current AI-relevant: Hardw corr10=1, max_int_dd 0.149, raw24 1.49, vol?")
