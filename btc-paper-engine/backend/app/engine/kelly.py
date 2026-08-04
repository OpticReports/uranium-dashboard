"""Kelly position-sizing engine — empirical, not the binary formula.

The web-calculator version of Kelly ((p*b - q)/b) treats every trade as the
same coin flip; real strategies produce a full return distribution with fat
tails, so this engine maximizes the exact growth criterion on the EMPIRICAL
per-step returns:

    g(m) = E[ log(1 + m * R) ]        m* = argmax g(m)

SIZING FRAME: R is the realized per-step equity return at the book's CURRENT
sizing, so m is a multiplier ON TOP of current sizing (m* > 1 = undersized,
m* < 1 = oversized). Books trade sequentially (one position at a time), so
per-step compounding is exact.

Approximations, stated honestly:
  - linear scaling: a trade sized m-times-current is assumed to return m*R.
    Valid near m~1; ignores path effects (stops/halts defined in equity
    terms, margin limits). Recommendations are therefore capped.
  - stationarity: bootstrap resamples the observed 2y window; crypto regime
    shifts outside that window are not represented.

Robustness machinery:
  - stationary block bootstrap (Politis-Romano, geometric blocks) for the
    sampling distribution of m* -> conservative percentile Kelly;
  - fractional (half) Kelly as shrinkage against estimation error — the
    g(m) curve is asymmetric: over-betting destroys growth faster than
    under-betting gives it up;
  - drawdown-constrained sizing: largest m with P(maxDD > d) <= p across
    bootstrap paths;
  - negative-edge sanity: mean(R) <= 0 -> m* = 0 (never size a losing edge).

All draws seeded -> deterministic, gate-testable.
"""
from __future__ import annotations

import math

import numpy as np

SEED = 20260804
M_CAP = 4.0                     # never recommend >4x current sizing (fat tails)
BOOT_DRAWS = 2000
MEAN_BLOCK = 10                 # expected block length (trades cluster by regime)


def growth(returns: np.ndarray, m: float) -> float:
    """Mean log growth per step at sizing multiplier m; -inf if ruinous."""
    x = 1.0 + m * returns
    if np.any(x <= 0):
        return -np.inf
    return float(np.mean(np.log(x)))


def _m_grid(returns: np.ndarray, cap: float = M_CAP) -> np.ndarray:
    mn = returns.min()
    hi = cap if mn >= 0 else min(cap, 0.99 / abs(mn))
    return np.linspace(0.0, hi, 481)


def kelly_star(returns: np.ndarray, cap: float = M_CAP) -> float:
    """Numeric argmax of g(m) on [0, feasible cap]."""
    r = np.asarray(returns, dtype=float)
    if len(r) == 0 or r.mean() <= 0:
        return 0.0
    grid = _m_grid(r, cap)
    g = np.array([growth(r, m) for m in grid])
    return float(grid[int(np.argmax(g))])


def stationary_bootstrap_idx(n: int, rng: np.random.Generator,
                             mean_block: int = MEAN_BLOCK) -> np.ndarray:
    """Politis-Romano stationary bootstrap indices: geometric block lengths
    (restart prob 1/mean_block), wrap-around."""
    p = 1.0 / mean_block
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for i in range(1, n):
        idx[i] = rng.integers(n) if rng.random() < p else (idx[i - 1] + 1) % n
    return idx


def kelly_uncertainty(returns: np.ndarray, draws: int = BOOT_DRAWS,
                      cap: float = M_CAP, seed: int = SEED) -> dict:
    """Bootstrap sampling distribution of m* (the estimation-error picture)."""
    r = np.asarray(returns, dtype=float)
    rng = np.random.default_rng(seed)
    stars = np.array([kelly_star(r[stationary_bootstrap_idx(len(r), rng)], cap)
                      for _ in range(draws)])
    return {"p10": round(float(np.percentile(stars, 10)), 2),
            "p50": round(float(np.percentile(stars, 50)), 2),
            "p90": round(float(np.percentile(stars, 90)), 2),
            "prob_negative_edge": round(float((stars == 0).mean()), 3)}


def dd_prob(returns: np.ndarray, m: float, dd_limit: float,
            draws: int = 800, seed: int = SEED) -> float:
    """P(max drawdown > dd_limit) over bootstrap paths of the observed length
    at sizing multiplier m."""
    r = np.asarray(returns, dtype=float)
    rng = np.random.default_rng(seed + 1)
    n = len(r)
    hits = 0
    for _ in range(draws):
        path = 1.0 + m * r[stationary_bootstrap_idx(n, rng)]
        if np.any(path <= 0):
            hits += 1
            continue
        eq = np.cumprod(path)
        peak = np.maximum.accumulate(eq)
        if float(np.min(eq / peak - 1.0)) < -dd_limit:
            hits += 1
    return hits / draws


def dd_constrained_m(returns: np.ndarray, dd_limit: float, p_limit: float,
                     cap: float = M_CAP, seed: int = SEED) -> float:
    """Largest m with P(maxDD > dd_limit) <= p_limit (bisection; dd_prob is
    monotone in m up to bootstrap noise — shared seed keeps it clean)."""
    r = np.asarray(returns, dtype=float)
    if len(r) == 0 or r.mean() <= 0:
        return 0.0
    lo, hi = 0.0, float(_m_grid(r, cap)[-1])
    if dd_prob(r, hi, dd_limit, seed=seed) <= p_limit:
        return round(hi, 2)
    for _ in range(24):
        mid = (lo + hi) / 2
        if dd_prob(r, mid, dd_limit, seed=seed) <= p_limit:
            lo = mid
        else:
            hi = mid
    return round(lo, 2)


def analyze(returns: list[float], label: str, current_desc: str = "",
            cap: float = M_CAP, seed: int = SEED) -> dict:
    """Full Kelly report for one book's per-step return stream."""
    r = np.asarray([x for x in returns if x is not None and math.isfinite(x)],
                   dtype=float)
    n = len(r)
    if n < 30:
        return {"book": label, "n": n,
                "verdict": "insufficient sample (<30 steps) — no sizing claim"}
    star = kelly_star(r, cap)
    unc = kelly_uncertainty(r, seed=seed, cap=cap)
    half = round(star / 2, 2)
    conservative = min(half, unc["p10"])                  # shrinkage: the lesser of
    dd20 = dd_constrained_m(r, 0.20, 0.10, cap, seed)     # half-Kelly and p10 boot
    dd30 = dd_constrained_m(r, 0.30, 0.10, cap, seed)
    rec = round(max(0.0, min(conservative, dd30)), 2)
    if star == 0.0:
        verdict = ("NEGATIVE EDGE at current sizing — Kelly says the correct "
                   "size is zero until the edge itself improves")
    elif rec >= 1.25:
        verdict = f"UNDERSIZED: engine supports ~{rec:.1f}x current size"
    elif rec <= 0.8:
        verdict = f"OVERSIZED: engine supports only ~{rec:.1f}x current size"
    else:
        verdict = "size is roughly right (within the noise band)"
    return {
        "book": label, "current": current_desc, "n": n,
        "mean_pct": round(100 * float(r.mean()), 3),
        "sd_pct": round(100 * float(r.std()), 2),
        "min_pct": round(100 * float(r.min()), 2),
        "worst_feasible_m": round(float(_m_grid(r, cap)[-1]), 2),
        "g_current": round(growth(r, 1.0), 5),
        "kelly_m": round(star, 2),
        "g_at_kelly": round(growth(r, star), 5),
        "bootstrap": unc,
        "half_kelly_m": half,
        "conservative_m": round(conservative, 2),
        "dd_constrained": {"p_maxdd20_le_10pct": dd20,
                           "p_maxdd30_le_10pct": dd30},
        "dd_at_current": {"p_dd_gt_20": round(dd_prob(r, 1.0, 0.20, seed=seed), 3),
                          "p_dd_gt_30": round(dd_prob(r, 1.0, 0.30, seed=seed), 3)},
        "recommended_m": rec,
        "verdict": verdict,
    }
