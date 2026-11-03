"""Gate G6 (SPEC v1 §3.7), reduced: the full D-3 pipeline on synthetic paths from the frozen GARCH-t.

SYNTHETIC ONLY: no data file is read except freeze.json (the frozen fit). For each scenario, P paths of the broad
dollar run until 24 rule units mature (capped at YEARS years; the rest are PENDING). On each path the frozen rule
(unpatched, 120-day cooling, the yield clause on a simulated 10-year yield: a random walk with sd 0.057pp per index
day, independent of the dollar) and its placebo (no deceleration clause) fire; units start at a firing and absorb
later firings with k - k1 < 250; p_u comes from a lookup table on log h per drift, built from the frozen model with
the harness's own Monte Carlo; hits and the look decisions follow SPEC v1 §3.3-3.5 through the harness (d3.py).

Binding (the gate fails otherwise): DGP = model and DGP = model + a -1%/yr drift, cumulative P(PASS) <= 0.05; and
under the model, mean(hit - p_u at zero drift) within +-0.01. Every other row is DESCRIPTIVE.

    python3 -I g6.py <freeze.json> [paths] [years] [scenario,...]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv
from scipy.signal import lfilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d3  # noqa: E402

TOL = 100 * math.log(d3.HIT_MULT)
Y_SD = 0.057                     # pp per index day: the 10-year yield's daily sd 2006-2026 (stats review v1)


def p_tables(model: dict, nodes: int = 40, n: int = 40_000):
    hu = model["omega"] / (1 - model["alpha"] - model["beta"])
    H = hu * np.exp(np.linspace(math.log(0.2), math.log(30.0), nodes))
    T = {k: np.empty(nodes) for k in d3.DRIFTS}
    for i, h in enumerate(H):
        res = d3.p_u(model, float(h), n_paths=n, seed=777 + i)["by_drift"]
        for k in d3.DRIFTS:
            T[k][i] = res[k]["p_u"]
    return np.log(H), T


def simulate(dgp: dict, rng, P: int, T: int) -> np.ndarray:
    mu = dgp.get("mu", 0.0)
    if dgp.get("rw"):
        return mu + dgp["sd"] * rng.standard_normal((P, T))
    w, a, b, nu = dgp["omega"], dgp["alpha"], dgp["beta"], dgp["nu"]
    sc = math.sqrt((nu - 2) / nu)
    X = np.empty((P, T))
    h = np.full(P, w / (1 - a - b))
    for t in range(T):
        e = np.sqrt(h) * rng.standard_t(nu, P) * sc
        X[:, t] = mu + e
        h = w + a * e ** 2 + b * h
    return X


def units_of(x: np.ndarray, rng, logH, tabs, model, decel: bool) -> np.ndarray:
    """rows (p_minus1, p_zero, p_plus1, hit, maturity index) for the matured units of one path, in time order."""
    n = len(x) + 1
    lb = np.concatenate([[0.0], np.cumsum(x) / 100.0])
    B = np.exp(lb)
    Y = 3.0 + np.concatenate([[0.0], np.cumsum(Y_SD * rng.standard_normal(n - 1))])
    roc = np.full(n, np.nan)
    roc[20:] = B[20:] / B[:-20] - 1
    W = swv(roc[20:], 61)
    mx = np.full(n, np.nan)
    mx[80:] = W.max(axis=1)
    kmx = np.full(n, -1)
    kmx[80:] = np.arange(80, n) - 60 + W.argmax(axis=1)
    hx = np.full(n, np.nan)
    hx[60:] = swv(B, 61).max(axis=1)
    k = np.arange(n)
    yref = np.where(kmx >= 0, Y[np.maximum(0, kmx - 20)], np.inf)
    with np.errstate(invalid="ignore"):
        base = (k >= 80) & (mx >= 0.04) & (B >= 0.97 * hx) & (Y < yref)
        cand = np.where(base & (roc <= 0.5 * mx) if decel else base)[0]
    fires, last = [], -10 ** 9
    for c in cand:
        if c - last > 120:
            fires.append(c)
            last = c
    starts = []
    for f in fires:
        if not starts or f - starts[-1] >= 250:
            starts.append(f)
    w, a, b = model["omega"], model["alpha"], model["beta"]
    hn, _ = lfilter([1.0], [1.0, -b], w + a * x ** 2, zi=[b * (w / (1 - a - b))])
    out = []
    for k1 in starts:
        if k1 + 250 >= n:
            break
        lh = math.log(hn[k1 - 1])
        p = [float(np.interp(lh, logH, tabs[d])) for d in ("minus1", "zero", "plus1")]
        hit = int((lb[k1 + 1:k1 + 251].max() - lb[k1]) * 100 <= TOL)
        out.append(p + [hit, k1 + 250])
    return np.array(out).reshape(-1, 5)


def inject(U: np.ndarray, delta: float, rng) -> np.ndarray:
    if delta and len(U):
        U = U.copy()
        flip = (U[:, 3] == 0) & (rng.random(len(U)) < delta / np.maximum(1e-9, 1 - U[:, 1]))
        U[flip, 3] = 1
    return U


def as_units(U: np.ndarray) -> list:
    return [{"p_u": {"minus1": r[0], "zero": r[1], "plus1": r[2]}, "hit": int(r[3])} for r in U]


def decide(D: np.ndarray, Pl: np.ndarray) -> tuple[str, int, str | None]:
    crit = []
    units = as_units(D)
    for j, n in enumerate(d3.LOOKS):
        if len(units) < n:
            return "PENDING", j, None
        lk = d3.evaluate_look(j, units, crit)
        crit.append(lk["critical_value"])
        if lk["class"] == "PASS":
            t_look = D[n - 1, 4]
            pl = d3.placebo_beside(lk, as_units(Pl[Pl[:, 4] <= t_look]))
            return "PASS", j + 1, pl.get("wording")
        if lk["class"] == "FAIL":
            return "FAIL", j + 1, None
    return "INCONCLUSIVE", 3, None


def scenarios(model: dict) -> dict:
    hu = model["omega"] / (1 - model["alpha"] - model["beta"])
    rho = model["alpha"] + model["beta"]
    base = {k: model[k] for k in ("omega", "alpha", "beta", "nu")}

    def hl(f):                       # half-life x f at the same unconditional variance and alpha share
        r2 = rho ** (1 / f)
        return dict(base, omega=hu * (1 - r2), alpha=model["alpha"] * r2 / rho, beta=model["beta"] * r2 / rho)

    def vol(f):
        return dict(base, omega=model["omega"] * f * f)
    return {
        "model": (base, 0.0, 0.0, "BINDING: DGP = model"),
        "drift-1": (dict(base, mu=-1.0 / 250), 0.0, 0.0, "BINDING: drift -1%/yr"),
        "drift+1": (dict(base, mu=1.0 / 250), 0.0, 0.0, "drift +1%/yr"),
        "drift-2": (dict(base, mu=-2.0 / 250), 0.0, 0.0, "drift -2%/yr"),
        "drift+0.9": (dict(base, mu=0.9 / 250), 0.0, 0.0, "drift +0.9%/yr (the fit window's)"),
        "vol0.8": (vol(0.8), 0.0, 0.0, "unconditional vol x0.8"),
        "vol1.2": (vol(1.2), 0.0, 0.0, "unconditional vol x1.2"),
        "hl0.5": (hl(0.5), 0.0, 0.0, "half-life x0.5"),
        "hl2": (hl(2.0), 0.0, 0.0, "half-life x2"),
        "rw": ({"rw": True, "sd": math.sqrt(hu)}, 0.0, 0.0, "constant-vol random walk"),
        "edge10": (base, 0.10, 0.0, "edge +0.10 (deceleration-specific)"),
        "edge20": (base, 0.20, 0.0, "edge +0.20 (deceleration-specific)"),
        "edge30": (base, 0.30, 0.0, "edge +0.30 (deceleration-specific)"),
        "generic20": (base, 0.20, 0.20, "generic reversal +0.20 (rule and placebo)"),
        "drift+0.9_edge20": (dict(base, mu=0.9 / 250), 0.20, 0.0, "drift +0.9%/yr, edge +0.20"),
    }


def run(name, dgp, d_edge, p_edge, model, logH, tabs, paths, years, seed, chunk=100):
    rng = np.random.default_rng(seed)
    T = years * 250
    res, diffs, rate = [], [], []
    t0 = time.time()
    for c0 in range(0, paths, chunk):
        X = simulate(dgp, rng, min(chunk, paths - c0), T)
        for x in X:
            D = inject(units_of(x, rng, logH, tabs, model, True), d_edge, rng)
            Pl = inject(units_of(x, rng, logH, tabs, model, False), p_edge, rng)
            res.append(decide(D, Pl))
            diffs += list(D[:24, 3] - D[:24, 1])
            rate.append(len(D) / years)
    cls = [r[0] for r in res]
    passes = [r for r in res if r[0] == "PASS"]
    return {"scenario": name, "paths": paths, "years_cap": years, "units_per_year": round(float(np.mean(rate)), 3),
            "mean_hit_minus_p0": round(float(np.mean(diffs)), 4), "se": round(float(np.std(diffs, ddof=1) / math.sqrt(len(diffs))), 4),
            "pass_by_look": [round(float(np.mean([r[0] == "PASS" and r[1] <= j for r in res])), 4) for j in (1, 2, 3)],
            "fail": round(cls.count("FAIL") / paths, 4), "inconclusive": round(cls.count("INCONCLUSIVE") / paths, 4),
            "pending": round(cls.count("PENDING") / paths, 4),
            "pass_not_specific_share": round(sum(r[2] != "deceleration flag ON" for r in passes) / len(passes), 3) if passes else None,
            "seconds": round(time.time() - t0)}


if __name__ == "__main__":
    model = json.load(open(sys.argv[1], encoding="utf-8"))["d3"]["garch_fit"]
    paths = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    years = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    S = scenarios(model)
    names = sys.argv[4].split(",") if len(sys.argv) > 4 else list(S)
    t0 = time.time()
    logH, tabs = p_tables(model)
    print(json.dumps({"p_table_seconds": round(time.time() - t0)}), flush=True)
    out = []
    for i, nm in enumerate(names):
        dgp, de, pe, label = S[nm]
        r = run(nm, dgp, de, pe, model, logH, tabs, paths, years, seed=20261103 + i)
        r["label"] = label
        print(json.dumps(r), flush=True)
        out.append(r)
    m = {r["scenario"]: r for r in out}
    gate = {}
    if "model" in m:
        gate["model_size_le_0.05"] = m["model"]["pass_by_look"][2] <= 0.05
        gate["model_calibration_within_0.01"] = abs(m["model"]["mean_hit_minus_p0"]) <= 0.01
    if "drift-1" in m:
        gate["drift-1_size_le_0.05"] = m["drift-1"]["pass_by_look"][2] <= 0.05
    print(json.dumps({"gate": gate, "G6": "PASS" if gate and all(gate.values()) else "FAIL" if gate else "no binding row run"}), flush=True)
