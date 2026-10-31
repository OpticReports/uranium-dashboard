"""SCOPING ONLY (not pre-registered): the 'earthquake' analogy on Ken French 49 industry
portfolios (VW monthly, 1926-07..2026-09). Run-up = +100% raw over 24 months (first trigger;
no new episode in the same industry for 36 months). Features of the run-up window: number of
intermediate drawdowns >= 10% / >= 20%, max intermediate drawdown, realised vol, acceleration.
Outcome: max drawdown in the next 24 months; CRASH = >= 40% (GSY's definition)."""
import csv, json, math, sys, os
import numpy as np
RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)

def read_block(path, header_line_idx):
    rows = list(csv.reader(open(path)))
    hdr = rows[header_line_idx]
    names = [h.strip() for h in hdr[1:]]
    data = {}
    for r in rows[header_line_idx + 1:]:
        if not r or not r[0].strip().isdigit() or len(r[0].strip()) != 6:
            break
        m = r[0].strip()
        vals = [float(x) for x in r[1:]]
        data[m] = vals
    return names, data

rows = list(csv.reader(open(os.path.join(RAW, "49_Industry_Portfolios.csv"))))
hi = next(i for i, r in enumerate(rows) if r and "Average Value Weighted Returns -- Monthly" in r[0])
names, ind = read_block(os.path.join(RAW, "49_Industry_Portfolios.csv"), hi + 1)
frows = list(csv.reader(open(os.path.join(RAW, "F-F_Research_Data_Factors.csv"))))
fi = next(i for i, r in enumerate(frows) if r and r[0].strip() == "" and "Mkt-RF" in r[1])
mkt = {}
for r in frows[fi + 1:]:
    if not r or len(r[0].strip()) != 6 or not r[0].strip().isdigit():
        break
    mkt[r[0].strip()] = float(r[1]) + float(r[4])
months = sorted(set(ind) & set(mkt))
R = np.array([ind[m] for m in months]) / 100.0          # T x 49
R[R <= -0.99] = np.nan
M = np.array([mkt[m] for m in months]) / 100.0
T, N = R.shape
# price indices (nan-safe cumulative)
P = np.full_like(R, np.nan)
for j in range(N):
    acc = 1.0; started = False
    for t in range(T):
        if np.isnan(R[t, j]):
            started = False; acc = 1.0; continue
        acc *= 1 + R[t, j]; P[t, j] = acc
PM = np.cumprod(1 + M)

def max_dd(x):
    peak = -np.inf; dd = 0.0
    for v in x:
        peak = max(peak, v); dd = max(dd, 1 - v / peak)
    return dd

def count_corrections(x, thr):
    """distinct peak-to-trough declines >= thr inside the window (reset once a new high is made)."""
    peak = x[0]; trough = x[0]; n = 0; in_dd = False
    for v in x[1:]:
        if v >= peak:
            if in_dd: n += 1
            peak = v; trough = v; in_dd = False
        else:
            trough = min(trough, v)
            if 1 - trough / peak >= thr: in_dd = True
    if in_dd: n += 1
    return n

W, H, GAP, RUNUP = 24, 24, 36, 1.0
eps = []
last = [-10**6] * N
for t in range(W, T - 1):
    for j in range(N):
        if np.isnan(P[t, j]) or np.isnan(P[t - W, j]) or t - last[j] < GAP:
            continue
        raw = P[t, j] / P[t - W, j] - 1
        if raw < RUNUP:
            continue
        net = (1 + raw) / (PM[t] / PM[t - W]) - 1
        win = P[t - W:t + 1, j]
        fut = P[t:min(T, t + H + 1), j]
        if np.isnan(fut).any() or len(fut) < 13:
            continue
        futm = PM[t:t + len(fut)]
        r12 = P[t, j] / P[t - 12, j] - 1
        eps.append({"industry": names[j], "month": months[t], "raw24": raw, "net24": net,
                    "corr10": count_corrections(win, 0.10), "corr20": count_corrections(win, 0.20),
                    "max_int_dd": max_dd(win), "vol": float(np.nanstd(R[t - W + 1:t + 1, j]) * math.sqrt(12)),
                    "accel": r12 / raw if raw else None,
                    "fut_maxdd": max_dd(fut), "fut_maxdd_net": max_dd(fut / futm * futm[0]),
                    "fut_ret24": float(fut[-1] / fut[0] - 1), "mkt_fut_maxdd": max_dd(futm), "n_fut": int(len(fut) - 1)})
        last[j] = t
print("episodes:", len(eps), "window", months[0], months[-1])
json.dump(eps, open(os.path.join(OUT, "episodes.json"), "w"), indent=1)

def wilson(k, n, z=1.645):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)

def summarise(sel, label):
    n = len(sel); k = sum(e["fut_maxdd"] >= 0.40 for e in sel)
    lo, hi_ = wilson(k, n)
    md = float(np.median([e["fut_maxdd"] for e in sel])) if n else None
    return {"group": label, "n": n, "crash40": k, "p_crash": k / n if n else None, "wilson90": [lo, hi_], "median_fut_maxdd": md,
            "mean_fut_ret24": float(np.mean([e["fut_ret24"] for e in sel])) if n else None}

strict = [e for e in eps if e["net24"] >= 1.0]       # GSY: +100% raw AND +100% net of market
summary = {"all": summarise(eps, "all run-ups (raw +100%/24m)"), "strict_gsy": summarise(strict, "GSY-strict (also +100% net of market)"),
           "strict_by_corr10": [summarise([e for e in strict if e["corr10"] == 0], "strict, 0 corrections >=10%"),
                                summarise([e for e in strict if e["corr10"] >= 1], "strict, >=1 correction >=10%")],
           "by_corr10": [summarise([e for e in eps if e["corr10"] == 0], "0 corrections >=10%"),
                         summarise([e for e in eps if e["corr10"] == 1], "1 correction"),
                         summarise([e for e in eps if e["corr10"] >= 2], ">=2 corrections")],
           "by_corr20": [summarise([e for e in eps if e["corr20"] == 0], "no >=20% correction"),
                         summarise([e for e in eps if e["corr20"] >= 1], ">=1 correction >=20%")]}
# terciles on continuous features
for feat in ("max_int_dd", "raw24", "vol", "accel", "net24"):
    vals = sorted(e[feat] for e in eps if e[feat] is not None)
    q1, q2 = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    summary["by_" + feat] = [summarise([e for e in eps if e[feat] is not None and e[feat] < q1], f"{feat} low (<{q1:.2f})"),
                             summarise([e for e in eps if e[feat] is not None and q1 <= e[feat] < q2], f"{feat} mid"),
                             summarise([e for e in eps if e[feat] is not None and e[feat] >= q2], f"{feat} high (>={q2:.2f})")]
# rank correlations
from itertools import combinations
def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b)); return float(np.corrcoef(ra, rb)[0, 1])
fd = np.array([e["fut_maxdd"] for e in eps])
summary["spearman_vs_fut_maxdd"] = {f: spearman(np.array([e[f] for e in eps], float), fd) for f in ("corr10", "max_int_dd", "raw24", "net24", "vol", "accel")}
# unconditional base rate: all industry-months with data, crash in next 24m
base_k = base_n = 0
for t in range(0, T - 13, 12):
    for j in range(N):
        fut = P[t:min(T, t + H + 1), j]
        if np.isnan(fut).any() or len(fut) < 13: continue
        base_n += 1; base_k += int(max_dd(fut) >= 0.40)
summary["unconditional_base_rate_crash40_24m"] = {"k": base_k, "n": base_n, "p": base_k / base_n}
# current state of the AI-relevant industries as of the last month
cur = {}
t = T - 1
for j, nm in enumerate(names):
    if nm in ("Chips", "Softw", "Hardw", "LabEq", "Telcm", "BusSv", "Util"):
        win = P[t - W:t + 1, j]
        cur[nm] = {"asof": months[t], "raw24": float(P[t, j] / P[t - W, j] - 1), "net24": float((P[t, j] / P[t - W, j]) / (PM[t] / PM[t - W]) - 1),
                   "corr10": count_corrections(win, 0.10), "corr20": count_corrections(win, 0.20), "max_int_dd": max_dd(win),
                   "raw36": float(P[t, j] / P[t - 36, j] - 1)}
summary["current"] = cur
def _py(o):
    if isinstance(o, dict): return {k: _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_py(v) for v in o]
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    return o
summary = _py(summary)
json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)

