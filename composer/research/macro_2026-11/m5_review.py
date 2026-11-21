"""Post hoc, from the construction review (review A): what the liquidity composite is made of, how
concentrated the gate-off result is, and what the tilt earns with the state always on.
Writes out/review.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m1_run as m1  # noqa: E402

S, E, pos, days = m1.S, m1.E, m1.pos, m1.days
out = {}
# ---- liquidity: which state carries the composite, and where its off-days sit
out["liquidity"] = {}
for which in ("verdict", "shape"):
    ds, r, tb = m1.sample("BOOK", which)
    ii = np.array([pos[d] for d in ds])
    lr = np.log1p(r)
    f, l1, l2 = (np.nan_to_num(S[k][ii]) for k in ("F_LIQUIDITY", "L1", "L2"))
    l2_has = ~np.isnan(S["L2"][ii])
    on = f == 1
    row = {"on_days": int(on.sum()), "on_days_L2_on": int((on & (l2 == 1)).sum()), "on_days_L1_only": int((on & (l1 == 1) & (l2 == 0)).sum()), "days_L2_has_data": int(l2_has.sum()), "n": len(ds)}
    off = np.flatnonzero(f == 0)
    # the longest run of off-days (allowing gaps of under 63 sessions)
    runs, a = [], 0
    for j in range(1, len(off) + 1):
        if j == len(off) or off[j] - off[j - 1] > 63:
            runs.append((off[a], off[j - 1], j - a))
            a = j
    b0, b1, _ = max(runs, key=lambda x: x[2])
    blk = (np.arange(len(ds)) >= b0) & (np.arange(len(ds)) <= b1) & (f == 0)
    row["largest_off_block"] = {"from": ds[b0], "to": ds[b1], "off_days": int(blk.sum()), "all_off_days": int((f == 0).sum()), "off_log": float(lr[blk].sum()), "all_off_log": float(lr[f == 0].sum())}
    for k in ("L1", "L2"):
        res = m1.map_row(S[k][ii], r)
        row[k] = None if res is None else res[0]
    out["liquidity"][which] = row
    print("liquidity", which, {k: v for k, v in row.items() if k not in ("L1", "L2")}, {k: (None if row[k] is None else (round(row[k]["on_share"], 2), round(row[k]["diff_per_yr"], 2), round(row[k]["p_two_sided"], 3))) for k in ("L1", "L2")})
# ---- gate off: the other two engines' on-day growth by year
prev = {b: a for a, b in zip(days, days[1:])}
import m2_followup as m2  # noqa: E402  (re-runs the follow-up; gives gate_off)
ds, _, _ = m1.sample("BOOK", "verdict")
s = np.nan_to_num(np.array([np.nan if m2.gate_off.get(prev.get(d)) is None else float(m2.gate_off[prev[d]]) for d in ds]))
oth = np.array([(0.341 * E["KMLM"][d] + 0.318 * E["SLEEVE"][d]) / 0.659 for d in ds])
lr = np.log1p(oth)
yr = {}
for y in sorted({d[:4] for d in ds}):
    m = np.array([d[:4] == y for d in ds])
    yr[y] = {"on_days": int(s[m].sum()), "on_log": float(lr[m & (s == 1)].sum())}
tot = sum(v["on_log"] for v in yr.values())
top = sorted(yr, key=lambda y: -yr[y]["on_log"])[:2]
keep = np.array([d[:4] not in top for d in ds])
res = m1.map_row(s[keep], oth[keep])
out["x1"] = {"by_year": yr, "on_log_total": tot, "top_two_years": sorted(top), "top_two_on_log": sum(yr[y]["on_log"] for y in top),
             "without_top_two": None if res is None else res[0]}
print("x1", round(tot, 2), top, round(out["x1"]["top_two_on_log"], 2), "without:", None if res is None else (round(res[0]["on_per_yr"], 2), round(res[0]["off_per_yr"], 2), round(res[0]["diff_per_yr"], 2), round(res[0]["p_two_sided"], 3)))
# ---- P2 with the state always on: the static tilt
R = np.array([[E[e][d] for e in ("HG", "KMLM", "SLEEVE")] for d in ds])
ms = [i for i, d in enumerate(ds) if i == 0 or d[:7] != ds[i - 1][:7]]
g = lambda x: float(np.log1p(x).mean() * 252)                                # noqa: E731
pol, W = m1.tilt_path(np.ones(len(ds)), np.log1p(R), R, ms)
dev = np.abs(W - np.array([0.341, 0.341, 0.318])).sum(1) > 1e-9
out["p2_always_on"] = {"d_growth": g(pol) - g((np.array([0.341, 0.341, 0.318]) * R).sum(1)), "first_tilted_day": ds[int(np.argmax(dev))], "days_tilted": int(dev.sum()), "n": len(ds),
                       "avg_weights": [float(v) for v in W[dev].mean(0)]}
print("p2 always on", out["p2_always_on"])
json.dump(out, open(os.path.join(HERE, "out", "review.json.tmp"), "w"), indent=1)
os.replace(os.path.join(HERE, "out", "review.json.tmp"), os.path.join(HERE, "out", "review.json"))
