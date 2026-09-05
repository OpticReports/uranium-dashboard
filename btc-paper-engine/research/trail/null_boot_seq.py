"""Null 1 AS LITERALLY REGISTERED: stationary block bootstrap over the blend's
TRADE SEQUENCE, mean block ~10 exits (PREREG.md null #1).

Why this file exists: `null_boot.py` implements 30-day CALENDAR blocks, which
is NOT what the pre-registration says. The registered design cannot be run as
written - it asks for one shared draw across all 21 cells, but the cells have
different-length event streams (77..286 S4 trades), so a shared sequence index
is undefined. Calendar blocks were the closest faithful substitution and the
substitution was undeclared. This file runs the registered estimator the only
way it can be run - each cell resampled on its OWN index blocks, geometric
block length with mean 10 - so the reader can see whether the substitution
changed the answer. Both are reported; neither is quietly dropped.

    python3 research/trail/null_boot_seq.py <trail_sweep.json> [n]
"""
from __future__ import annotations

import json
import sys

import numpy as np

SRC = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
MEAN_BLOCK = 10
SEED = 20260905

d = json.load(open(SRC))
GRID = d["grid"]
EV = d["events_modern"]
W = d["windows"]["modern"]
YEARS = (int(W["t1"]) - int(W["t0"])) / (365.25 * 86400)
keys = [f"{m:.2f}" for m in GRID]
base_k = "5.00"
streams = {k: np.array([e[1] for e in EV[k]], dtype=float) for k in keys}


def mar(rets: np.ndarray) -> float | None:
    if len(rets) < 5:
        return None
    nav = np.cumprod(1.0 + rets)
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    if mdd > -0.005:
        return None
    return (nav[-1] ** (1.0 / YEARS) - 1.0) / abs(mdd)


def resample(rng, x: np.ndarray) -> np.ndarray:
    """Politis-Romano stationary bootstrap: geometric block lengths, wrapped."""
    n = len(x)
    out = np.empty(n)
    i = 0
    while i < n:
        start = int(rng.integers(0, n))
        L = min(int(rng.geometric(1.0 / MEAN_BLOCK)), n - i)
        idx = (start + np.arange(L)) % n
        out[i:i + L] = x[idx]
        i += L
    return out


rng = np.random.default_rng(SEED)
argmax_counts = {k: 0 for k in keys}
gap_max_med, base_rank = [], []
for _ in range(N):
    vals = {}
    for k in keys:
        v = mar(resample(rng, streams[k]))
        if v is not None:
            vals[k] = v
    if base_k not in vals or len(vals) < len(keys) // 2:
        continue
    best = max(vals, key=lambda k: vals[k])
    argmax_counts[best] += 1
    med = float(np.median(list(vals.values())))
    gap_max_med.append(vals[best] - med)
    base_rank.append(sum(1 for v in vals.values() if v > vals[base_k]) + 1)

obs = {k: W["cells"][k]["s6"]["mar"] for k in keys}
ov = np.array([v for v in obs.values() if v is not None])
obs_lift = obs[base_k] - float(np.median(ov))
gm, rk = np.array(gap_max_med), np.array(base_rank)
n_eff = len(gm)
print(f"REGISTERED estimator: stationary bootstrap, mean block {MEAN_BLOCK} "
      f"exits, per-cell streams, {n_eff}/{N} draws, seed {SEED}")
print(f"  observed incumbent lift over grid median: {obs_lift:+.3f}")
print(f"  random best-of-21 lift: median {np.median(gm):+.3f}  "
      f"q95 {np.quantile(gm, .95):+.3f}")
print(f"  P(random best-of-21 lift >= observed) = "
      f"{float((gm >= obs_lift).mean()):.3f}")
print(f"  P(5.00 is argmax) = {argmax_counts[base_k] / n_eff:.3f}  "
      f"(uniform {1/len(keys):.3f})")
json.dump({"base_rank": [int(x) for x in rk],
           "gap_max_med": [float(x) for x in gm],
           "argmax_counts": argmax_counts, "n_eff": n_eff,
           "obs_lift": float(obs_lift)},
          open(SRC.replace(".json", "_nullseq.json"), "w"))
print(f"  5.00 rank among 21: median {np.median(rk):.0f}  "
      f"top-5 {float((rk <= 5).mean()):.3f}  "
      f"bottom-half {float((rk > len(keys)/2).mean()):.3f}")
