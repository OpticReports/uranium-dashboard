"""Pure functions for each Alpha Signal component.

These are deliberately ORM-free and side-effect-free so the scoring math can be
unit-tested with known inputs/outputs (see tests/test_scoring.py). Every
function returns None to mean "no data" — never silently substitutes 0.0.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..utils.normalize import exp_age_decay, exp_time_decay


@dataclass
class RevisionLike:
    date: date
    direction: int  # +1 up, -1 down, 0 reiterate


@dataclass
class CatalystLike:
    date: date
    event_type: str
    impact_override: float | None = None


def revision_velocity_raw(
    revisions: Sequence[RevisionLike],
    asof: date,
    window_days: int,
    half_life_days: float,
) -> float | None:
    """Recency-weighted net direction of estimate revisions.

    Σ direction_i * decay(age_i). Positive => upward revision momentum.
    Returns None when there are no revisions in the window (no data), which is
    distinct from 0.0 (revisions present but net-neutral).
    """
    contribs: list[float] = []
    for r in revisions:
        age = (asof - r.date).days
        if age < 0 or age > window_days:
            continue
        contribs.append(r.direction * exp_age_decay(age, half_life_days))
    if not contribs:
        return None
    return sum(contribs)


def catalyst_score_raw(
    catalysts: Sequence[CatalystLike],
    asof: date,
    horizon_days: int,
    half_life_days: float,
    impact_weights: dict[str, float],
) -> float:
    """Σ over upcoming catalysts of (impact * time_decay).

    Returns 0.0 when there are no upcoming catalysts in the horizon — this is a
    genuine zero (the name has no near catalysts), not missing data.
    """
    total = 0.0
    for c in catalysts:
        days_until = (c.date - asof).days
        if days_until < 0 or days_until > horizon_days:
            continue
        if c.impact_override is not None:
            impact = c.impact_override
        else:
            impact = impact_weights.get(c.event_type, impact_weights.get("other", 0.2))
        total += impact * exp_time_decay(days_until, half_life_days)
    return total


def mention_acceleration_raw(counts: Sequence[float]) -> float | None:
    """Second derivative (acceleration) of a daily mention-count series.

    Splits the series into equal thirds (old/mid/new), measures the change in
    average level between consecutive thirds (two velocity points), and returns
    the change between them (acceleration). None if fewer than 3 points.
    """
    n = len(counts)
    if n < 3:
        return None
    third = n // 3
    if third == 0:
        return None
    old = counts[:third]
    mid = counts[third : 2 * third]
    new = counts[2 * third :]
    avg_old = sum(old) / len(old)
    avg_mid = sum(mid) / len(mid)
    avg_new = sum(new) / len(new)
    v1 = avg_mid - avg_old
    v2 = avg_new - avg_mid
    return v2 - v1


def price_change_raw(closes: Sequence[float]) -> float | None:
    """Fractional price change across the window. None if insufficient/zero base."""
    obs = [c for c in closes if c is not None]
    if len(obs) < 2 or obs[0] == 0:
        return None
    return (obs[-1] - obs[0]) / obs[0]


def pullback_from_high_raw(
    highs: Sequence[float | None], last_close: float | None
) -> float | None:
    """Fractional pullback of the last close from the window high.

    0.0 = at the high; 0.10 = 10% below it. None when the high or close is
    unknowable (no data), never a silent zero.
    """
    obs = [h for h in highs if h is not None]
    if not obs or last_close is None:
        return None
    peak = max(obs)
    if peak <= 0:
        return None
    return max(0.0, (peak - last_close) / peak)


def volume_zscore_raw(volumes: Sequence[float | None], min_history: int = 20) -> float | None:
    """Z-score of the LATEST daily volume vs the name's own trailing history.

    Computed on log(volume+1): raw volume is log-normal-ish, so one prior
    blowout day would inflate σ and suppress detection for weeks, while tiny
    absolute uticks on quiet names would clear a raw-volume threshold. The
    latest observation is excluded from the baseline so a genuine spike can't
    inflate its own mean/σ. None with insufficient history or a flat baseline.
    """
    import math

    obs = [math.log(v + 1.0) for v in volumes if v is not None and v >= 0]
    if len(obs) < min_history + 1:
        return None
    latest, base = obs[-1], obs[:-1]
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / len(base)
    std = var ** 0.5
    if std == 0:
        return None
    return (latest - mean) / std


def runway_penalty_magnitude(
    runway_quarters: float | None,
    threshold_quarters: float,
    floor_quarters: float,
) -> float | None:
    """Penalty in [0, 100] that ramps in as runway drops below threshold.

    >= threshold -> 0 (healthy), <= floor -> 100 (cliff), linear between.
    None runway => None (no data; e.g. profitable names have no meaningful burn).
    """
    if runway_quarters is None:
        return None
    if threshold_quarters <= floor_quarters:
        return 0.0
    if runway_quarters >= threshold_quarters:
        return 0.0
    if runway_quarters <= floor_quarters:
        return 100.0
    frac = (threshold_quarters - runway_quarters) / (threshold_quarters - floor_quarters)
    return max(0.0, min(100.0, frac * 100.0))


def combine(
    contributions: dict[str, float | None],
    weights: dict[str, float],
) -> tuple[float | None, dict[str, float]]:
    """Weighted mean of present (non-None) component contributions.

    Components scaled to a common 0-100 range upstream. The denominator is the
    sum of weights of components that ACTUALLY have data, so a missing component
    neither contributes nor drags the composite toward zero.

    Returns (composite_or_None, used_weights_dict).
    """
    num = 0.0
    den = 0.0
    used: dict[str, float] = {}
    for name, contrib in contributions.items():
        if contrib is None:
            continue
        w = weights.get(name, 0.0)
        if w == 0.0:
            continue
        num += w * contrib
        den += w
        used[name] = w
    if den == 0.0:
        return None, used
    return num / den, used
