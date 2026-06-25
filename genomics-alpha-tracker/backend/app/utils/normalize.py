"""Normalization helpers for the scoring engine.

All functions are NULL-aware: `None` means "no data" and is propagated /
excluded rather than coerced to 0.0. This is load-bearing for thin-float names
where a zero in a signal component is NOT the same as an absent observation.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import StatisticsError, mean, pstdev


def zscore(value: float | None, population: Sequence[float | None]) -> float | None:
    """Z-score of `value` within `population`, ignoring None entries.

    Returns None if value is None or the population has no variance / too few
    points to define a z-score.
    """
    if value is None:
        return None
    obs = [x for x in population if x is not None]
    if len(obs) < 2:
        return None
    try:
        mu = mean(obs)
        sigma = pstdev(obs)
    except StatisticsError:
        return None
    if sigma == 0:
        return 0.0
    return (value - mu) / sigma


def percentile_rank(value: float | None, population: Sequence[float | None]) -> float | None:
    """Fraction of the population <= value (0..1). None-aware."""
    if value is None:
        return None
    obs = sorted(x for x in population if x is not None)
    if not obs:
        return None
    below = sum(1 for x in obs if x <= value)
    return below / len(obs)


def zscore_to_0_100(z: float | None, clip: float = 3.0) -> float | None:
    """Map a z-score to 0-100 by clipping to +/-`clip` sigma and rescaling.

    z = 0  -> 50, z = +clip -> 100, z = -clip -> 0.
    """
    if z is None:
        return None
    z = max(-clip, min(clip, z))
    return (z + clip) / (2 * clip) * 100.0


def exp_time_decay(days_until: float, half_life_days: float) -> float:
    """Decay weight in (0, 1]. days_until<=0 (past/now) returns 1.0.

    Uses a half-life: weight halves every `half_life_days` of distance.
    """
    if days_until <= 0:
        return 1.0
    if half_life_days <= 0:
        return 0.0
    lam = math.log(2) / half_life_days
    return math.exp(-lam * days_until)


def exp_age_decay(age_days: float, half_life_days: float) -> float:
    """Decay weight for an observation `age_days` old. Same math as time decay."""
    return exp_time_decay(max(0.0, age_days), half_life_days)


def safe_mean(values: Sequence[float | None]) -> float | None:
    obs = [v for v in values if v is not None]
    if not obs:
        return None
    return mean(obs)
