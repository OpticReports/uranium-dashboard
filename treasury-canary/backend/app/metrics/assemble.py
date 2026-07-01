"""Helper to turn a raw daily series into a fully-populated MetricResult
(value, deltas, percentile, status) using the shared thresholds. Kept separate
from base.py to avoid a base<->thresholds import cycle.
"""
from __future__ import annotations

from datetime import date

from ..scoring import thresholds as T
from .base import MetricResult, Status, delta, last_valid, percentile_rank


def simple_metric(
    metric_id: str, category: str, label: str,
    dates: list[date], vals: list[float | None],
    *, unit: str = "", note: str = "", source: str = "",
    scale: float = 1.0,
) -> MetricResult:
    """Assemble a MetricResult from a series. `scale` converts units before
    thresholding (e.g. 100 to express a spread in bps, or a SOFR-EFFR diff)."""
    scaled = [v * scale if v is not None else None for v in vals]
    value = last_valid(scaled)
    asof = None
    for d, v in zip(reversed(dates), reversed(scaled)):
        if v is not None:
            asof = d
            break
    status = T.classify(metric_id, value) if value is not None else Status.STALE
    return MetricResult(
        metric_id=metric_id, category=category, label=label, value=value,
        status=status, asof=asof, unit=unit,
        delta_1d=delta(scaled, 1), delta_5d=delta(scaled, 5), delta_20d=delta(scaled, 20),
        percentile=percentile_rank(scaled, value), note=note, source_series=source,
    )
