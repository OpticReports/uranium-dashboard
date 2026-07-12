"""Weighted Treasury Stress Score (0-100, higher = more stress).

Explainable by construction: returns per-category and per-metric contributions,
and reweights over only the categories that have live (non-STALE) data so a dead
source lowers coverage rather than silently dragging or crashing the score.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..metrics.base import MetricResult, Status

# Category weights (curve highest; funding/vol next; flows/liquidity lower).
CATEGORY_WEIGHTS: dict[str, float] = {
    "A": 0.30,  # curve
    "B": 0.12,  # volatility
    "C": 0.08,  # term premium / real rates
    "D": 0.15,  # funding / plumbing
    "E": 0.08,  # auctions
    "F": 0.05,  # foreign / flows
    "G": 0.07,  # liquidity
    "H": 0.10,  # cross-asset
    "I": 0.05,  # recession model
    "J": 0.08,  # labor (Sahm / claims)
}

# Status -> stress points (0 best, 100 worst).
STATUS_POINTS: dict[Status, float] = {
    Status.GREEN: 0.0, Status.YELLOW: 50.0, Status.RED: 90.0, Status.CRITICAL: 100.0,
}


@dataclass
class CompositeResult:
    score: float | None                  # 0-100 stress, None if no data at all
    band: str                            # LOW | ELEVATED | HIGH | SEVERE | NO_DATA
    coverage: float                      # fraction of category weight with live data
    category_scores: dict[str, float]    # category -> 0-100
    contributions: dict[str, float]      # category -> points contributed to composite
    n_red: int
    n_critical: int


def _band(score: float | None) -> str:
    if score is None:
        return "NO_DATA"
    if score >= 75:
        return "SEVERE"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "ELEVATED"
    return "LOW"


def compute_composite(metrics: list[MetricResult]) -> CompositeResult:
    by_cat: dict[str, list[float]] = {}
    n_red = n_crit = 0
    for m in metrics:
        if m.status is Status.CRITICAL:
            n_crit += 1
        elif m.status is Status.RED:
            n_red += 1
        if m.status is Status.STALE or m.informational:
            continue  # informational metrics (e.g. lagging unemployment rate) are display-only
        by_cat.setdefault(m.category, []).append(STATUS_POINTS[m.status])

    cat_scores: dict[str, float] = {
        c: round(sum(v) / len(v), 1) for c, v in by_cat.items() if v
    }
    live_weight = sum(CATEGORY_WEIGHTS.get(c, 0.0) for c in cat_scores)
    if live_weight <= 0:
        return CompositeResult(None, "NO_DATA", 0.0, {}, {}, n_red, n_crit)

    contributions: dict[str, float] = {}
    score = 0.0
    for c, s in cat_scores.items():
        w = CATEGORY_WEIGHTS.get(c, 0.0) / live_weight  # renormalize over available
        contrib = round(w * s, 2)
        contributions[c] = contrib
        score += w * s

    total_weight = sum(CATEGORY_WEIGHTS.values())
    coverage = round(live_weight / total_weight, 3)
    score = round(score, 1)
    return CompositeResult(score, _band(score), coverage, cat_scores, contributions, n_red, n_crit)
