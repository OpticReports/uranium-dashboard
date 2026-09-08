"""Placebo #2 (PREREG.md null #2, second form): matched random thinning.

placebo.py's first form was degenerate - the pullback's time_stop_bars stops
binding at 55 bars, so 14 of its 21 cells are byte-identical and the sweep
has no variation to exploit. That is itself a finding (a dead parameter), but
it cannot calibrate a best-of-21 lift.

This form calibrates it properly. The trail multiple's dominant channel is
mechanical: a wider trail means fewer, longer S4 trades. So the matched
placebo is 21 variants that thin the S4 leg by the SAME range of trade counts
the trail grid spans, but choose which trades to keep AT RANDOM. Repeating
the whole 21-variant search many times gives the distribution of best-of-21
MAR lift attributable to search width alone.

    python3 research/trail/placebo_thin.py <trail_sweep.json> [reps]
"""
from __future__ import annotations

import json
import sys

import numpy as np

SRC = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 500
SEED = 20260905

d = json.load(open(SRC))
GRID = d["grid"]
W = d["windows"]["modern"]
T0, T1 = int(W["t0"]), int(W["t1"])
YEARS = (T1 - T0) / (365.25 * 86400)

# the live cell's event stream: [ts, levered blend return, leg] in exit order
EV = d["events_modern"]["5.00"]
N4 = sum(1 for e in EV if e[2] == "T")
counts = [W["cells"][f"{m:.2f}"]["s4"]["n"] for m in GRID]
lo, hi = min(counts), max(counts)
# Thinning can only REMOVE trades, so the reachable range runs from the live
# cell's own count (133) down to the grid's smallest (71). 11 of the 21 real
# cells hold MORE than 133 trades and are unreachable — this placebo covers
# 10 of 21. KEEPS[0] is exactly 1.0, i.e. variant 0 IS the unthinned live
# cell, which is why the "best-of-21 MAR >= observed grid max" statistic is
# pinned at 1.000 by construction and carries no information (counter-agent
# D9/D10, 2026-09-05). It is printed below only so the tautology is visible.
KEEPS = np.linspace(1.0, lo / N4, len(GRID))


def mar(rets) -> float | None:
    if len(rets) < 5:
        return None
    nav = np.cumprod(1.0 + np.array(rets))
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    if mdd > -0.005:
        return None
    return (nav[-1] ** (1.0 / YEARS) - 1.0) / abs(mdd)


rng = np.random.default_rng(SEED)
idx_T = [i for i, e in enumerate(EV) if e[2] == "T"]
lifts, bests, sds = [], [], []
for _ in range(REPS):
    vals = []
    for k in KEEPS:
        drop = set(rng.choice(idx_T, size=int(round((1 - k) * N4)),
                              replace=False)) if k < 1.0 else set()
        v = mar([e[1] for i, e in enumerate(EV) if i not in drop])
        if v is not None:
            vals.append(v)
    if len(vals) < len(GRID) // 2:
        continue
    a = np.array(vals)
    lifts.append(a.max() - np.median(a))
    bests.append(a.max())
    sds.append(float(a.std(ddof=1)))

obs = {f"{m:.2f}": W["cells"][f"{m:.2f}"]["s6"]["mar"] for m in GRID}
ov = np.array([v for v in obs.values() if v is not None])
obs_lift = ov.max() - np.median(ov)
L = np.array(lifts)
print(f"source={SRC} reps={len(L)} seed={SEED}")
print(f"S4 trades at trail=5.00: {N4}; grid spans {lo}..{hi}; "
      f"keep fractions {KEEPS[0]:.2f}..{KEEPS[-1]:.2f}")
print(f"\nplacebo best-of-21 MAR lift over own median: "
      f"median {np.median(L):+.3f}  q90 {np.quantile(L, .90):+.3f}  "
      f"q95 {np.quantile(L, .95):+.3f}")
print(f"observed trail-grid best-of-21 lift: {obs_lift:+.3f}")
print(f"P(random thinning best-of-21 lift >= observed) = "
      f"{float((L >= obs_lift).mean()):.3f}")
print(f"\nplacebo best-of-21 MAR level: median {np.median(bests):.3f}  "
      f"q95 {np.quantile(bests, .95):.3f} | observed grid max {ov.max():.3f}")
print(f"P(random thinning best-of-21 MAR >= observed grid max) = "
      f"{float((np.array(bests) >= ov.max()).mean()):.3f}"
      f"   <- TAUTOLOGY: variant 0 is the unthinned live cell. Ignore.")
# The lift statistic scales with within-search dispersion, and this placebo is
# ~1.6x more dispersed than the real grid (its 21 variants carry INDEPENDENT
# random drop sets, while adjacent trail cells are near-duplicates). Comparing
# raw lifts is therefore not a fair test; standardize by within-search SD.
S = np.array(sds)
obs_sd = float(ov.std(ddof=1))
print(f"\nwithin-search SD: real grid {obs_sd:.3f}  placebo median {np.median(S):.3f} "
      f"({np.median(S)/obs_sd:.2f}x more dispersed)")
zl = L / S
obs_z = obs_lift / obs_sd
print(f"standardized lift: observed {obs_z:.3f}  placebo median {np.median(zl):.3f}")
print(f"P(placebo standardized lift >= observed) = {float((zl >= obs_z).mean()):.3f}"
      f"   <- the fair comparison; the raw figure above is a dispersion artifact")
json.dump({"lifts": [float(x) for x in L], "bests": [float(x) for x in bests],
           "sds": [float(x) for x in S], "obs_sd": obs_sd, "obs_z": float(obs_z),
           "z_lifts": [float(x) for x in zl],
           "obs_lift": float(obs_lift), "obs_max": float(ov.max())},
          open(SRC.replace(".json", "_placebo.json"), "w"))
