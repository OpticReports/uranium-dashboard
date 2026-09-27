#!/usr/bin/env python3
"""Power of THE confirmatory gate (spec A1), measured BEFORE the real run.

Uses the REAL feature paths (their real persistence, real OOS design) and
replaces the outcome with a synthetic 12-month return:

    R_t = sum of 12 iid monthly shocks after t  +  beta * x_t

x_t is a standardized linear combination of the SMALL features, so the
synthetic effect lives exactly where the gate looks. beta is set so x_t
explains a share R2 of the 12-month return variance. Overlap is reproduced
because consecutive origins share 11 of their 12 monthly shocks. Monthly
shock: mean 0.75%, sd 4.4% (12m: mean ~9%, sd ~15% — S&P-like).

    python3 power.py [n_sims_per_effect]      (default 100; 4 processes)
"""
from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

import panel as P
import study as S

MU, SIG, H = 0.0075, 0.044, 12
EFFECTS = (0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30)


def _panel() -> pd.DataFrame:
    p = P.build()
    o = P.outcomes(p, (H,))
    d = p.join(o).loc[P.START:]
    return d[d[f"r{H}"].notna()].copy()


D = _panel()
Zs = (D[S.SMALL] - D[S.SMALL].mean()) / D[S.SMALL].std(ddof=0)
X = Zs.sum(axis=1)
X = ((X - X.mean()) / X.std(ddof=0)).values


def one(args) -> dict:
    r2, sim = args
    rng = np.random.default_rng(1_000_000 * int(r2 * 100) + sim)
    n = len(D)
    e = rng.normal(MU, SIG, n + H)
    fwd = np.array([e[i + 1:i + 1 + H].sum() for i in range(n)])
    beta = np.sqrt(r2 * H * SIG ** 2 / (1 - r2)) if r2 > 0 else 0.0
    R = fwd + beta * X
    d = D.copy()
    d["syn"] = (R > 0).astype(float)
    g = S.gate_small(d, H, ycol="syn", seed=sim)
    return {"r2": r2, "sim": sim, "pass": g["pass"], "c1": g["c1"],
            "c2": g["c2"], "r1": g["r1"], "r3": g["r3"], "bss": g["bss"]}


if __name__ == "__main__":
    nsim = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    jobs = [(r2, s) for r2 in EFFECTS for s in range(nsim)]
    with Pool(4) as pool:
        rows = pool.map(one, jobs, chunksize=4)
    df = pd.DataFrame(rows)
    summ = df.groupby("r2").agg(power=("pass", "mean"), c1=("c1", "mean"),
                                c2=("c2", "mean"), r1=("r1", "mean"),
                                r3=("r3", "mean"), bss_med=("bss", "median"),
                                n=("pass", "size"))
    print(summ.to_string())
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json")
    json.dump({"nsim": nsim, "mu": MU, "sig": SIG,
               "summary": summ.reset_index().to_dict(orient="records")},
              open(out, "w"), indent=1)
