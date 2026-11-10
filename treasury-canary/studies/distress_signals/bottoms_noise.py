#!/usr/bin/env python3
"""Irregular noise of the D&B monthly failure counts, by era, for the synthetic
calibration of studies/distress-bottoms.md (SPEC v1 s.6). Noise only: no
growth path, no timing against troughs or equity lows.

    python3 bottoms_noise.py      # -> bottoms_noise.json

Method (after the v1 data review): log counts; 2x12 moving average; seasonal
factors from same-calendar-month residuals within +-L years (local, because the
pre-1914 seasonal pattern drifts; a fixed pattern counts the drift as noise);
Spencer-15 trend-cycle on the seasonally adjusted series; irregular = SA - TC.
The iid sigma is then method-matched: synthetic AR(1) background + a fixed
seasonal + iid noise of known sigma, run through the same decomposition; the
sigma whose mean irregular SD equals the real one is reported. Primary: L = 2.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import load as D  # noqa: E402
from engine import M  # noqa: E402

SEED = 20261012
SPENCER = np.array([-3, -6, -5, 3, 21, 46, 67, 74, 67, 46, 21, 3, -5, -6, -3]) / 320.0
SEASONAL = np.log([1.37, 1.05, 1.03, .90, .91, .88, .89, .85, .89, .95, .96, 1.21])
ERAS = {"1897-1913": (0, M(1897, 1), M(1913, 12)), "1914-1931": (0, M(1914, 1), M(1931, 6)),
        "1947-1962": (2, M(1947, 1), M(1962, 12))}


def decompose(x: np.ndarray, local_years: int | None) -> np.ndarray:
    n = len(x)
    ma = np.full(n, np.nan)
    for i in range(6, n - 6):
        ma[i] = (x[i - 6:i + 6].sum() + x[i - 5:i + 7].sum()) / 24
    r = x - ma
    sf = np.zeros(n)
    for i in range(n):
        same = [j for j in range(i % 12, n, 12)
                if not np.isnan(r[j]) and (local_years is None or abs(j - i) <= 12 * local_years)]
        sf[i] = np.mean([r[j] for j in same])
    sa = x - sf
    tc = np.convolve(sa, SPENCER[::-1], mode="same")
    return sa - tc


def synth_sd(sigma: float, n: int, core: list[int], loc, rng, reps: int) -> float:
    v = []
    for _ in range(reps):
        e = rng.normal(0, 0.012, n)
        bg = np.zeros(n)
        for i in range(1, n):
            bg[i] = 0.98 * bg[i - 1] + e[i]
        seas = np.tile(SEASONAL, n // 12 + 1)[:n]
        v.append(np.std(decompose(bg + seas + rng.normal(0, sigma, n), loc)[core]))
    return float(np.mean(v))


def main():
    segs = D.dnb_count_segments()
    rng = np.random.default_rng(SEED)
    grid = np.arange(0.03, 0.14, 0.0025)
    out: dict = {"method": __doc__.split("Method")[1].strip(), "seed": SEED, "eras": {}}
    for era, (si, lo, hi) in ERAS.items():
        s = segs[si]
        pad = min(42, lo - min(s), max(s) - hi)
        ms = list(range(lo - pad, hi + pad + 1))
        x = np.log(np.array([s[m] for m in ms], float))
        core = [i for i, m in enumerate(ms) if lo <= m <= hi]
        row = {}
        for loc in (None, 1, 2, 3):
            z = decompose(x, loc)[core]
            sd_real = float(np.std(z))
            ac12 = float(np.corrcoef(z[12:], z[:-12])[0, 1])
            sig = float(min(grid, key=lambda q: abs(synth_sd(q, len(ms), core, loc, rng, 40) - sd_real)))
            row["stable" if loc is None else f"local_{loc}y"] = {"irregular_sd": round(sd_real, 4),
                                                                 "lag12_autocorr": round(ac12, 3),
                                                                 "iid_sigma": round(sig, 4)}
        out["eras"][era] = row
        print(era, {k: v["iid_sigma"] for k, v in row.items()}, flush=True)
    pre = out["eras"]["1897-1913"]
    post = [out["eras"][e]["local_2y"]["iid_sigma"] for e in ("1914-1931", "1947-1962")]
    out["primary"] = {"pre1914": pre["local_2y"]["iid_sigma"], "post1914": round(float(np.mean(post)), 4),
                      "pre1914_range_local_1_3y": [min(pre[f"local_{k}y"]["iid_sigma"] for k in (1, 2, 3)),
                                                   max(pre[f"local_{k}y"]["iid_sigma"] for k in (1, 2, 3))],
                      "superseded_stable_seasonal_figure": 0.116}
    with open(os.path.join(HERE, "bottoms_noise.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["primary"]))


if __name__ == "__main__":
    main()
