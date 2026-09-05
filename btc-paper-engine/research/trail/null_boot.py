"""Null calibration for the trail dose curve (PREREG.md, null #1).

The grid max is a best-of-21 statistic on highly correlated variants, so it
is biased upward even when the trail does nothing. This resamples 30-day
CALENDAR blocks (stationary block bootstrap) and takes, for every grid cell,
that cell's own exits inside the sampled blocks - so all 21 cells see the
same calendar draw and the comparison between them is preserved.

    python3 research/trail/null_boot.py <trail_sweep.json> [n_resamples]
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
BLOCK_DAYS = 30
SEED = 20260905                      # fixed; the study is reproducible

d = json.load(open(SRC))
GRID = d["grid"]
EV = d["events_modern"]              # {trail: [[ts, levered_ret, leg], ...]}
W = d["windows"]["modern"]
T0, T1 = int(W["t0"]), int(W["t1"])
BLOCK_S = BLOCK_DAYS * 86400
YEARS = (T1 - T0) / (365.25 * 86400)

# bucket each cell's events by calendar block index
NB = math.ceil((T1 - T0) / BLOCK_S)
buckets = {k: [[] for _ in range(NB)] for k in EV}
for k, evs in EV.items():
    for ts, r, _leg in evs:
        b = int((ts - T0) // BLOCK_S)
        if 0 <= b < NB:
            buckets[k][b].append(r)


def mar_from(rets: list[float]) -> float | None:
    if len(rets) < 5:
        return None
    nav = np.cumprod(1.0 + np.array(rets))
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    if mdd > -0.005:
        return None
    cagr = nav[-1] ** (1.0 / YEARS) - 1.0
    return cagr / abs(mdd)


rng = np.random.default_rng(SEED)
keys = [f"{m:.2f}" for m in GRID]
base_k = "5.00"
argmax_counts = {k: 0 for k in keys}
gap_base_med, gap_max_med, base_rank = [], [], []
for _ in range(N):
    draw = rng.integers(0, NB, size=NB)
    mars = {}
    for k in keys:
        rets = [r for b in draw for r in buckets[k][b]]
        mars[k] = mar_from(rets)
    ok = {k: v for k, v in mars.items() if v is not None}
    if len(ok) < len(keys) // 2 or base_k not in ok:
        continue
    best = max(ok, key=lambda k: ok[k])
    argmax_counts[best] += 1
    med = float(np.median(list(ok.values())))
    gap_base_med.append(ok[base_k] - med)
    gap_max_med.append(ok[best] - med)
    base_rank.append(sum(1 for v in ok.values() if v > ok[base_k]) + 1)

n_eff = len(gap_base_med)
obs = {k: d["windows"]["modern"]["cells"][k]["s6"]["mar"] for k in keys}
obs_med = float(np.median([v for v in obs.values() if v is not None]))
print(f"source={SRC}  resamples={n_eff}/{N}  block={BLOCK_DAYS}d  seed={SEED}")
print(f"observed: MAR(5.00)={obs[base_k]:.3f}  grid median={obs_med:.3f}  "
      f"lift={obs[base_k] - obs_med:+.3f}")
gm = np.array(gap_max_med)
gb = np.array(gap_base_med)
print(f"\nNULL A - how big is a best-of-21 lift over the grid median, by luck?")
print(f"  bootstrap max-minus-median: median {np.median(gm):+.3f}  "
      f"q90 {np.quantile(gm, .90):+.3f}  q95 {np.quantile(gm, .95):+.3f}")
print(f"  observed lift of the INCUMBENT (5.00) over the median: "
      f"{obs[base_k] - obs_med:+.3f}")
print(f"  P(random best-of-21 lift >= incumbent's lift) = "
      f"{float((gm >= obs[base_k] - obs_med).mean()):.3f}")
print(f"\nNULL B - is 5.00 stably the best, or best once?")
print(f"  P(5.00 is the bootstrap argmax) = "
      f"{argmax_counts[base_k] / n_eff:.3f}   (uniform would be {1/len(keys):.3f})")
rk = np.array(base_rank)
print(f"  5.00's rank among 21: median {np.median(rk):.0f}  "
      f"q10 {np.quantile(rk, .10):.0f}  q90 {np.quantile(rk, .90):.0f}")
print(f"  P(5.00 in top 5) = {float((rk <= 5).mean()):.3f}   "
      f"P(5.00 in bottom half) = {float((rk > len(keys)/2).mean()):.3f}")
json.dump({"gap_max_med": [float(x) for x in gm],
           "gap_base_med": [float(x) for x in gb],
           "base_rank": [int(x) for x in base_rank],
           "argmax_counts": argmax_counts, "n_eff": n_eff,
           "obs": obs, "obs_med": obs_med},
          open(SRC.replace(".json", "_null.json"), "w"))
top = sorted(argmax_counts.items(), key=lambda kv: -kv[1])[:6]
print("  most frequent bootstrap argmax: "
      + ", ".join(f"{k}({v/n_eff:.2f})" for k, v in top))
