"""D-3 harness (SPEC v1 §3): the frozen GARCH(1,1)-t null, p_u for a forward unit, and the look statistics.

Offline only: the panel records firings and archives their inputs; this harness computes p_u ONCE per unit,
from the archived firing inputs, before the unit matures (gate G7), and evaluates a look when n matured
units reaches 8 / 16 / 24. Stdlib + numpy + scipy.

    python3 -I d3.py fit  <DTWEXBGS.csv> <DGS10.csv> <VIXCLS.csv> <through YYYY-MM-DD>   -> frozen params (JSON)
    python3 -I d3.py pu   <params.json> <DTWEXBGS.csv> <DGS10.csv> <VIXCLS.csv> <firing YYYY-MM-DD> [N]
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys

import numpy as np
from scipy import optimize, special

HIT_MULT, HORIZON = 1.03, 250


# ---------------------------------------------------------------------------- the rule calendar
def fred_csv(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8") as fh:
        rd = csv.reader(fh)
        next(rd, None)
        for row in rd:
            if len(row) >= 2 and row[1] not in ("", "."):
                out[row[0]] = float(row[1])
    return out


def rule_calendar(b_path: str, y_path: str, v_path: str, through: str | None = None):
    """(dates, B) on days with DTWEXBGS, DGS10 and VIXCLS all published (the frozen calendar)."""
    b, y, v = fred_csv(b_path), fred_csv(y_path), fred_csv(v_path)
    ds = sorted(d for d in b if d in y and d in v and (through is None or d <= through))
    return ds, np.array([b[d] for d in ds])


def returns(B: np.ndarray) -> np.ndarray:
    return 100.0 * np.diff(np.log(B))


# ---------------------------------------------------------------------------- GARCH(1,1) with standardised Student-t innovations
def _filter(params, r):
    w, a, b = params[:3]
    h = np.empty(len(r) + 1)
    h[0] = np.var(r)
    for t in range(len(r)):
        h[t + 1] = w + a * r[t] ** 2 + b * h[t]
    return h                                   # h[t] is the conditional variance of r[t]; h[-1] is the next day's


def neg_loglik(params, r):
    w, a, b, nu = params
    if w <= 0 or a < 0 or b < 0 or a + b >= 0.9999 or nu <= 2.05:
        return 1e12
    h = _filter(params, r)[:-1]
    c = special.gammaln((nu + 1) / 2) - special.gammaln(nu / 2) - 0.5 * math.log(math.pi * (nu - 2))
    ll = c - 0.5 * np.log(h) - (nu + 1) / 2 * np.log1p(r ** 2 / ((nu - 2) * h))
    return -float(np.sum(ll))


def fit(r: np.ndarray) -> dict:
    """MLE of (omega, alpha, beta, nu) on r = 100*dlog B; zero mean (the null is a martingale)."""
    best = None
    for x0 in ([0.01, 0.05, 0.93, 8.0], [0.02, 0.08, 0.90, 6.0], [0.005, 0.03, 0.96, 10.0]):
        res = optimize.minimize(neg_loglik, x0, args=(r,), method="Nelder-Mead",
                                options={"xatol": 1e-10, "fatol": 1e-10, "maxiter": 20000, "maxfev": 40000})
        if best is None or res.fun < best.fun:
            best = res
    w, a, b, nu = (float(x) for x in best.x)
    params = {"omega": round(w, 8), "alpha": round(a, 8), "beta": round(b, 8), "nu": round(nu, 6),
              "loglik": round(-best.fun, 4), "n_returns": int(len(r)), "converged": bool(best.success)}
    params["param_hash"] = hashlib.sha256(json.dumps({k: params[k] for k in ("omega", "alpha", "beta", "nu")},
                                                     sort_keys=True).encode()).hexdigest()
    return params


def h_next(params: dict, r: np.ndarray) -> float:
    """the conditional variance for the day after the last return, filtered with the frozen parameters."""
    return float(_filter((params["omega"], params["alpha"], params["beta"]), r)[-1])


# ---------------------------------------------------------------------------- p_u under H0
def p_u(params: dict, h1: float, n_paths: int = 100_000, horizon: int = HORIZON, seed: int = 0, batch: int = 20_000) -> dict:
    """P(max over the next `horizon` steps of B <= HIT_MULT * B[k]) under the GARCH-t martingale started at h1.
    Log-price path; standardised t innovations (unit variance). Returns value and Monte-Carlo SE."""
    rng = np.random.default_rng(seed)
    w, a, b, nu = params["omega"], params["alpha"], params["beta"], params["nu"]
    scale = math.sqrt((nu - 2) / nu)
    cap = 100.0 * math.log(HIT_MULT)
    hits = 0
    done = 0
    while done < n_paths:
        m = min(batch, n_paths - done)
        h = np.full(m, h1)
        x = np.zeros(m)
        mx = np.full(m, -np.inf)
        for _ in range(horizon):
            z = rng.standard_t(nu, size=m) * scale
            e = np.sqrt(h) * z
            x += e
            np.maximum(mx, x, out=mx)
            h = w + a * e ** 2 + b * h
        hits += int(np.sum(mx <= cap))
        done += m
    p = hits / n_paths
    return {"p_u": p, "n_paths": n_paths, "seed": seed, "mc_se": math.sqrt(p * (1 - p) / n_paths)}


# ---------------------------------------------------------------------------- the look statistics (exact)
def pb_pmf(ps) -> np.ndarray:
    """Poisson-binomial pmf of the number of hits."""
    pmf = np.array([1.0])
    for p in ps:
        pmf = np.convolve(pmf, [1 - p, p])
    return pmf


def p_plus(S: int, ps) -> float:
    """P(S' >= S) under H0."""
    return float(pb_pmf(ps)[S:].sum())


def delta_upper(S: int, ps, grid: float = 0.001, level: float = 0.05) -> float:
    """largest delta on the grid with P(S' <= S | p_u + delta, clipped to [0,1]) >= level: the one-sided 95% upper bound."""
    best = -1.0
    for i in range(-1000, 1001):
        d = i * grid
        q = np.clip(np.asarray(ps) + d, 0.0, 1.0)
        if pb_pmf(q)[: S + 1].sum() >= level:
            best = d
    return round(best, 3)


LOOKS = [(8, 0.005), (16, 0.015), (24, 0.030)]


def classify(S: int, ps, n: int) -> str:
    alpha = dict(LOOKS).get(n)
    if alpha is None:
        return "no look at this n"
    if p_plus(S, ps) <= alpha:
        return "PASS"
    if delta_upper(S, ps) < 0.10:
        return "FAIL"
    return "INCONCLUSIVE (final)" if n == 24 else "continue"


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fit":
        ds, B = rule_calendar(*sys.argv[2:5], through=sys.argv[5])
        out = fit(returns(B))
        out.update(calendar="DTWEXBGS & DGS10 & VIXCLS", first=ds[0], last=ds[-1])
        print(json.dumps(out, indent=1, sort_keys=True))
    elif cmd == "pu":
        params = json.load(open(sys.argv[2]))
        ds, B = rule_calendar(*sys.argv[3:6], through=sys.argv[6])
        n = int(sys.argv[7]) if len(sys.argv) > 7 else 100_000
        h1 = h_next(params, returns(B))
        print(json.dumps({"firing": ds[-1], "h_next": h1, **p_u(params, h1, n, seed=int(ds[-1].replace("-", "")))}, indent=1))
