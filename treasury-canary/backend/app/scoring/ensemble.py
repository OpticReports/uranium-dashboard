"""Weight-sensitivity ensemble — robustness, NOT selection.

Recomputes the composite under ~1,000 random plausible category weightings
(Dirichlet(alpha=2) over the simplex: wide, but discourages degenerate all-in-
one-category draws) plus equal weights, and reports the SPREAD around the
headline (literature-informed priors). Nothing is ever selected from the draws
— picking the "best" weighting against ~3 scoreable recessions would be pure
data-snooping. A tight band proves the weights aren't load-bearing; a wide band
names the category driving the disagreement (weight-vs-score correlation).

Seeded RNG -> deterministic for a given data state (no flicker between reloads).
"""
from __future__ import annotations

import math
import random

from ..metrics.base import MetricResult
from .composite import CATEGORY_WEIGHTS, compute_composite

N_DRAWS = 1000
_ALPHA = 2.0
_SEED = 42


def _dirichlet(rng: random.Random, k: int, alpha: float = _ALPHA) -> list[float]:
    # Gamma(alpha=2, 1) via sum of two exponentials; normalize -> Dirichlet(2,..,2)
    g = [-math.log(rng.random()) - math.log(rng.random()) for _ in range(k)]
    s = sum(g)
    return [x / s for x in g]


def weight_ensemble(metrics: list[MetricResult], n_draws: int = N_DRAWS) -> dict | None:
    cats = sorted(CATEGORY_WEIGHTS)
    headline = compute_composite(metrics)
    if headline.score is None:
        return None

    equal = compute_composite(metrics, {c: 1.0 / len(cats) for c in cats})

    rng = random.Random(_SEED)
    draws: list[tuple[list[float], float]] = []
    for _ in range(n_draws):
        w = _dirichlet(rng, len(cats))
        res = compute_composite(metrics, dict(zip(cats, w)))
        if res.score is not None:
            draws.append((w, res.score))
    if not draws:
        return None

    scores = sorted(s for _, s in draws)
    p5 = scores[int(0.05 * (len(scores) - 1))]
    p95 = scores[int(0.95 * (len(scores) - 1))]

    # Which category drives disagreement: corr(weight_k, score) across draws.
    driver, driver_corr = None, 0.0
    n = len(draws)
    mean_s = sum(s for _, s in draws) / n
    var_s = sum((s - mean_s) ** 2 for _, s in draws)
    for i, c in enumerate(cats):
        ws = [w[i] for w, _ in draws]
        mean_w = sum(ws) / n
        cov = sum((w - mean_w) * (s - mean_s) for w, (_, s) in zip(ws, draws))
        var_w = sum((w - mean_w) ** 2 for w in ws)
        if var_w > 0 and var_s > 0:
            corr = cov / math.sqrt(var_w * var_s)
            if abs(corr) > abs(driver_corr):
                driver, driver_corr = c, corr

    return {
        "band_low": round(p5, 1),
        "band_high": round(p95, 1),
        "equal_weight_score": equal.score,
        "n_draws": len(draws),
        "spread": round(p95 - p5, 1),
        "driver_category": driver,
        "driver_direction": ("raises" if driver_corr > 0 else "lowers") if driver else None,
        "note": "5th-95th pct of the composite across random plausible weightings "
                "(Dirichlet a=2, seeded). Robustness check, never selection: a tight "
                "band means the priors aren't load-bearing; a wide band names the "
                "category whose weighting drives the disagreement.",
    }
