"""D-3 harness (SPEC v1 §3): the frozen GARCH(1,1)-t null, p_u for a forward unit, and the look statistics.

Offline only. The panel records firings and archives their input bytes; this harness computes p_u ONCE per unit,
from those archived bytes (each checked against its recorded sha256), before the unit matures (gate G7), and
evaluates a look when n matured units reaches 8 / 16 / 24. Stdlib + numpy + scipy.

    python3 -I d3.py fit    <DTWEXBGS.csv> <DGS10.csv> <through YYYY-MM-DD>                -> frozen params (JSON)
    python3 -I d3.py pu-row <ledger.json> <archive dir> <freeze.json> <kind> <date> [N]     -> the unit's p_u record (JSON)
    python3 -I d3.py look   <looks.json>                                                   -> the look (JSON)

The null brackets the drift it cannot know (stats review v1 S1): PASS is judged with p_u at a pessimistic drift
of -1%/yr, FAIL with p_u at an optimistic +1%/yr, and the zero-drift p_u is reported. Critical values come from
an exact alpha-spending recursion on the recorded p_u (cumulative 0.005 / 0.020 / 0.050); FAIL uses a 98.3%
one-sided bound per look (0.05 / 3). The placebo rule (the same rule without the deceleration clause) is
scored the same way and printed beside any result (stats review v1 S2).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys

import numpy as np
from scipy import optimize, special

HIT_MULT, HORIZON = 1.03, 250
DRIFTS = {"minus1": -1.0 / 250, "zero": 0.0, "plus1": 1.0 / 250}   # %/yr / 250 index days, in 100*dlog units
LOOKS = [8, 16, 24]
ALPHA_CUM = [0.005, 0.020, 0.050]                                     # exact spending, cumulative
FAIL_EDGE, FAIL_LEVEL = 0.10, 0.05 / 3                                # FAIL if the 98.3% upper bound < +0.10
ARCHIVED = ("DTWEXBGS", "DGS10")


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


def rule_calendar(b_path: str, y_path: str, through: str | None = None):
    """(dates, B) on days with DTWEXBGS and DGS10 both published (SPEC v1 §2)."""
    b, y = fred_csv(b_path), fred_csv(y_path)
    ds = sorted(d for d in b if d in y and (through is None or d <= through))
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


def param_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps({k: params[k] for k in ("omega", "alpha", "beta", "nu")}, sort_keys=True).encode()).hexdigest()


def fit(r: np.ndarray) -> dict:
    """MLE of (omega, alpha, beta, nu) on r = 100*dlog B; zero mean."""
    best = None
    for x0 in ([0.01, 0.05, 0.93, 8.0], [0.02, 0.08, 0.90, 6.0], [0.005, 0.03, 0.96, 10.0]):
        res = optimize.minimize(neg_loglik, x0, args=(r,), method="Nelder-Mead",
                                options={"xatol": 1e-10, "fatol": 1e-10, "maxiter": 20000, "maxfev": 40000})
        if best is None or res.fun < best.fun:
            best = res
    w, a, b, nu = (float(x) for x in best.x)
    params = {"omega": round(w, 8), "alpha": round(a, 8), "beta": round(b, 8), "nu": round(nu, 6),
              "loglik": round(-best.fun, 4), "n_returns": int(len(r)), "converged": bool(best.success)}
    params["param_hash"] = param_hash(params)
    return params


def h_next(params: dict, r: np.ndarray) -> float:
    """the conditional variance for the day after the last return, filtered with the frozen parameters."""
    return float(_filter((params["omega"], params["alpha"], params["beta"]), r)[-1])


# ---------------------------------------------------------------------------- p_u under H0 (three drifts, common random numbers)
def p_u(params: dict, h1: float, n_paths: int = 100_000, horizon: int = HORIZON, seed: int = 0, batch: int = 20_000,
        drifts: dict | None = None) -> dict:
    """P(max over the next `horizon` steps of B <= HIT_MULT * B[k]) under the GARCH-t model started at h1, for each
    drift (the innovations drive the variance; the drift only shifts the path). Common random numbers across drifts,
    so p_u(-1%) >= p_u(0) >= p_u(+1%) path by path. Returns {drift: {p_u, mc_se}}, n_paths and seed."""
    drifts = DRIFTS if drifts is None else drifts
    rng = np.random.default_rng(seed)
    w, a, b, nu = params["omega"], params["alpha"], params["beta"], params["nu"]
    scale = math.sqrt((nu - 2) / nu)
    cap = 100.0 * math.log(HIT_MULT)
    hits = {k: 0 for k in drifts}
    done = 0
    while done < n_paths:
        m = min(batch, n_paths - done)
        h = np.full(m, h1)
        x = np.zeros(m)
        mx = {k: np.full(m, -np.inf) for k in drifts}
        for t in range(1, horizon + 1):
            e = np.sqrt(h) * rng.standard_t(nu, size=m) * scale
            x += e
            for k, mu in drifts.items():
                np.maximum(mx[k], x + mu * t, out=mx[k])
            h = w + a * e ** 2 + b * h
        for k in drifts:
            hits[k] += int(np.sum(mx[k] <= cap))
        done += m
    out = {}
    for k in drifts:
        p = hits[k] / n_paths
        out[k] = {"p_u": p, "mc_se": math.sqrt(p * (1 - p) / n_paths)}
    return {"by_drift": out, "n_paths": n_paths, "seed": seed, "drift_per_index_day": dict(drifts)}


# ---------------------------------------------------------------------------- one unit's record, from the archived inputs only (M5)
def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def pu_row(ledger_path: str, archive_dir: str, freeze_path: str, kind: str, date: str, n_paths: int = 100_000) -> dict:
    """p_u for the unit that starts at (kind, date). Refuses unless the row is an admitted unit start, every archived
    input matches its recorded sha256, the frozen parameters match their hash, and the calendar on the archived
    vintage puts the firing at the row's index k."""
    led = json.load(open(ledger_path, encoding="utf-8"))
    row = next((e for e in led.get("entries", []) if e.get("kind") == kind and e.get("date") == date), None)
    if row is None:
        raise SystemExit(f"no {kind} row dated {date}")
    if row.get("d3_eligible") is not True or row.get("unit_first") != date:
        raise SystemExit(f"{kind} {date} is not an admitted unit start (d3_eligible {row.get('d3_eligible')}, unit_first {row.get('unit_first')})")
    if "p_u" in row:
        raise SystemExit(f"{kind} {date} already carries a p_u record: it is computed once")
    fz = json.load(open(freeze_path, encoding="utf-8"))
    params = (fz.get("d3") or {}).get("garch_fit") or {}
    if param_hash(params) != params.get("param_hash"):
        raise SystemExit("frozen GARCH parameters do not match their hash")
    paths = {}
    for sid in ARCHIVED:
        rec = (row.get("inputs") or {}).get(sid) or {}
        h = rec.get("sha256")
        p = os.path.join(archive_dir, h or "missing")
        if not h or not os.path.exists(p):
            raise SystemExit(f"{sid}: archived bytes not found ({h})")
        if _sha256(p) != h:
            raise SystemExit(f"{sid}: archived bytes do not match sha256 {h}")
        paths[sid] = p
    ds, B = rule_calendar(paths["DTWEXBGS"], paths["DGS10"], through=date)      # truncated at k1: nothing after the firing
    if not ds or ds[-1] != date:
        raise SystemExit(f"{date} is not an index day of the archived vintage")
    if isinstance(row.get("k"), int) and len(ds) - 1 != row["k"]:
        raise SystemExit(f"index mismatch: the archived vintage puts {date} at k={len(ds) - 1}, the row says k={row['k']}")
    h1 = h_next(params, returns(B))
    res = p_u(params, h1, n_paths, seed=int(date.replace("-", "")))
    return {"kind": kind, "date": date, "k": len(ds) - 1, "h_next": h1, **res, "garch_param_hash": params["param_hash"],
            "inputs_sha256": {sid: row["inputs"][sid]["sha256"] for sid in ARCHIVED}}


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


def delta_upper(S: int, ps, level: float = FAIL_LEVEL, grid: float = 0.001) -> float:
    """the largest delta on the 0.001 grid over [-1, 1] with P(S' <= S | p_u + delta, clipped to [0,1]) >= level:
    the one-sided (1 - level) upper bound on the edge (non-increasing in delta, so a bisection is exact)."""
    ps = np.asarray(ps, float)
    cdf = lambda i: pb_pmf(np.clip(ps + i * grid, 0.0, 1.0))[: S + 1].sum()     # noqa: E731
    lo, hi = -1000, 1000
    if cdf(lo) < level:
        return -1.0
    if cdf(hi) >= level:
        return 1.0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if cdf(mid) >= level:
            lo = mid
        else:
            hi = mid
    return round(lo * grid, 3)


def crossing_prob(blocks: list, crit: list) -> float:
    """P_H0(S_{n_l} >= c_l for some look l) for nested looks; blocks[l] = the p_u of the units added at look l."""
    dist = np.array([1.0])
    crossed = 0.0
    for ps, c in zip(blocks, crit):
        dist = np.convolve(dist, pb_pmf(ps))
        if c < len(dist):
            crossed += float(dist[c:].sum())
            dist = dist.copy()
            dist[c:] = 0.0
    return crossed


def critical_value(blocks: list, prev: list, alpha_cum: float) -> int:
    """the smallest c with P_H0(crossing at this look or an earlier one, given the earlier critical values) <= alpha_cum.
    Futility stops are ignored (non-binding), which keeps the type I error at or below alpha_cum."""
    n = sum(len(b) for b in blocks)
    for c in range(n + 2):
        if crossing_prob(blocks, prev + [c]) <= alpha_cum + 1e-15:
            return c
    return n + 1


def evaluate_look(j: int, units: list, prev_crit: list) -> dict:
    """Look j (0, 1, 2) on the first LOOKS[j] matured units, ordered by maturity date. Each unit:
    {"p_u": {"minus1": .., "zero": .., "plus1": ..}, "hit": 0/1}. prev_crit: the critical values recorded at earlier looks."""
    n = LOOKS[j]
    if len(units) < n:
        raise ValueError(f"look {j + 1} needs {n} matured units, have {len(units)}")
    u = units[:n]
    S = int(sum(x["hit"] for x in u))
    bounds = [0] + LOOKS[: j + 1]
    blocks = [[x["p_u"]["minus1"] for x in u[bounds[i]:bounds[i + 1]]] for i in range(j + 1)]
    c = critical_value(blocks, list(prev_crit), ALPHA_CUM[j])
    p = {k: [x["p_u"][k] for x in u] for k in DRIFTS}
    du = delta_upper(S, p["plus1"])
    cls = "PASS" if S >= c else "FAIL" if du < FAIL_EDGE else ("INCONCLUSIVE (final)" if j == len(LOOKS) - 1 else "continue")
    return {"look": j + 1, "n": n, "S": S, "critical_value": c, "alpha_cum": ALPHA_CUM[j],
            "null_crossing_prob": crossing_prob(blocks, list(prev_crit) + [c]),
            "sum_p_u": {k: round(float(sum(v)), 4) for k, v in p.items()},
            "T": {k: round((S - float(sum(v))) / n, 4) for k, v in p.items()},
            "p_plus": {k: p_plus(S, v) for k, v in p.items()},
            "delta_U_plus1": du, "fail_level": FAIL_LEVEL, "class": cls}


def placebo_beside(look: dict, placebo_units: list) -> dict:
    """The placebo rule's units matured by the look date, scored the same way (printed beside any result)."""
    n = len(placebo_units)
    if n == 0:
        return {"n": 0, "note": "no placebo unit matured by the look date"}
    S = int(sum(x["hit"] for x in placebo_units))
    p0 = [x["p_u"]["zero"] for x in placebo_units]
    pm = [x["p_u"]["minus1"] for x in placebo_units]
    T0 = (S - sum(p0)) / n
    passes = p_plus(S, pm) <= ALPHA_CUM[look["look"] - 1]
    generic = bool(passes or T0 >= look["T"]["zero"])
    return {"n": n, "S": S, "T_zero": round(T0, 4), "p_plus_minus1": p_plus(S, pm), "passes": bool(passes),
            "wording": ("post-scramble reversal: not specific to deceleration" if generic else "deceleration flag ON")
            if look["class"] == "PASS" else None}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fit":
        ds, B = rule_calendar(sys.argv[2], sys.argv[3], through=sys.argv[4])
        out = fit(returns(B))
        out.update(calendar="DTWEXBGS & DGS10", first=ds[0], last=ds[-1],
                   inputs_sha256={"DTWEXBGS": _sha256(sys.argv[2]), "DGS10": _sha256(sys.argv[3])})
        print(json.dumps(out, indent=1, sort_keys=True))
    elif cmd == "pu-row":
        n = int(sys.argv[7]) if len(sys.argv) > 7 else 100_000
        print(json.dumps(pu_row(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], n), indent=1))
    elif cmd == "look":
        spec = json.load(open(sys.argv[2], encoding="utf-8"))
        lk = evaluate_look(spec["look"] - 1, spec["units"], spec.get("prev_crit", []))
        lk["placebo"] = placebo_beside(lk, spec.get("placebo_units", []))
        print(json.dumps(lk, indent=1))
    else:
        raise SystemExit(__doc__)
