"""Q5 (added after the independent review; DEVIATIONS.md 8): how much this test could have seen, and how
far the readings of the window surface carry. Reads out/cells_ab.json, cells_c.json, stats.json; writes
out/robust.json. Nothing here selects a cell.
 power      per cell, the true gain (log-points a year) the family-wise 10% bar would catch half the time
            (critical t x standard error) and four times in five ((critical t + 0.84) x standard error)
 long       the fourteen longer-window cells (14 to 60 days, switch and switch+picks) averaged into one
            series: its gain in tier A, in tier B, and the share of the tier-B shortfall from single days
 short      the same for the windows 3 to 8
 tier_c     the family-wise p of tier C's best cell (max-statistic bootstrap over its 62 cells) and the
            long-window average there
"""
import json
import math
import os

import numpy as np

from q2_stats import boot_idx

HERE = os.path.dirname(os.path.abspath(__file__))
ab = json.load(open(os.path.join(HERE, "out", "cells_ab.json")))
cc = json.load(open(os.path.join(HERE, "out", "cells_c.json")))
st = json.load(open(os.path.join(HERE, "out", "stats.json")))
days = ab["days"]
a_mask = np.array([d > ab["a_start"] for d in days])
lb = np.log1p(np.array(ab["cells"]["base"]["ret"]))
D = {c: np.log1p(np.array(v["ret"])) - lb for c, v in ab["cells"].items() if c != "base"}
crit = st["beside"]["max_stat_90"]
out = {"critical_t_90": crit, "power": {}}
for c, d in D.items():
    se = d.std(ddof=1) / math.sqrt(len(d)) * 252
    if se > 0:
        out["power"][c] = {"se_per_yr": se, "mde50": crit * se, "mde80": (crit + 0.84) * se}
mde = sorted(v["mde50"] for v in out["power"].values())
out["power_median_mde50"] = mde[len(mde) // 2]


def tstat(x):
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if x.std() > 0 else 0.0


def group(ns):
    cells = [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in ns]
    g = np.mean([D[c] for c in cells], axis=0)
    a, b = g[a_mask], g[~a_mask]
    worst = np.argsort(b)[:5]
    bd = [d for d, m in zip(days, a_mask) if not m]
    return {"cells": len(cells), "A_per_yr": float(a.mean() * 252), "A_t": tstat(a), "B_per_yr": float(b.mean() * 252), "B_t": tstat(b),
            "A_cells_above": int(sum(D[c][a_mask].mean() > 0 for c in cells)), "B_cells_above": int(sum(D[c][~a_mask].mean() > 0 for c in cells)),
            "B_total_log": float(b.sum()), "B_worst_days": [[bd[i], float(b[i])] for i in worst],
            "B_share_of_worst_day": float(b[worst[0]] / b.sum()) if b.sum() else None}


out["long"] = group((14, 17, 20, 25, 30, 40, 60))
out["short"] = group((3, 5, 7, 8))
# tier C
cb = np.log1p(np.array(cc["cells"]["base"]["ret"]))
ids = [c for c in cc["cells"] if c != "base"]
M = np.array([np.log1p(np.array(cc["cells"][c]["ret"])) - cb for c in ids]).T
n = len(M)
mean, se = M.mean(0), M.std(0, ddof=1) / math.sqrt(n)
t = np.where(se > 0, mean / np.where(se > 0, se, 1), 0.0)
rng = np.random.default_rng(20261120)
mx = np.empty(2000)
for b in range(2000):
    Mb = M[boot_idx(n, rng)]
    sb = Mb.std(0, ddof=1) / math.sqrt(n)
    ok = sb > 0
    mx[b] = np.max(np.where(ok, (Mb.mean(0) - mean) / np.where(ok, sb, 1), -np.inf))
best = int(np.argmax(t))
lw = np.mean([M[:, ids.index(f"{f}.rsi{k}")] for f in ("F1a", "F1b") for k in (14, 17, 20, 25, 30, 40, 60)], axis=0)
out["tier_c"] = {"best": ids[best], "best_t": float(t[best]), "best_p_fw": float((mx >= t[best]).mean()),
                 "long_per_yr": float(lw.mean() * 252), "long_t": tstat(lw), "cells_above": int((mean > 0).sum()), "cells": len(ids),
                 "top10_days_share": float(np.sort(lw)[-10:].sum() / lw.sum())}
json.dump(out, open(os.path.join(HERE, "out", "robust.json"), "w"), indent=1)
p = out["power"]
print("critical t", round(crit, 2), "| median MDE50", round(out["power_median_mde50"], 2))
for c in ("F1a.rsi11", "F1b.rsi12", "F1a.rsi14", "F1a.rsi20", "F5.ema50"):
    print(f"  {c:12s} se {p[c]['se_per_yr']:.3f}  MDE50 {p[c]['mde50']:.2f}  MDE80 {p[c]['mde80']:.2f}")
print("long", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["long"].items()})
print("short", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["short"].items()})
print("tier C", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["tier_c"].items()})
