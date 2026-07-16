"""Shared metric contract + pure helpers.

Every metric module returns MetricResult objects so scoring/API/UI treat them
uniformly. Helpers here are the ONLY place delta/percentile/status logic lives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Status(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    CRITICAL = "CRITICAL"      # reserved for override events (e.g. re-steepening)
    STALE = "STALE"            # no/late data -> excluded from composite denominator

    @property
    def rank(self) -> int:
        return {"GREEN": 0, "YELLOW": 1, "RED": 2, "CRITICAL": 3, "STALE": -1}[self.value]


@dataclass
class Threshold:
    """A green/yellow/red band. `higher_is_worse` picks comparison direction.

    Bands are expressed as the yellow/red cut points; everything is
    config-overridable via scoring.thresholds so retuning needs no code edits.
    """
    yellow: float
    red: float
    higher_is_worse: bool = True
    critical: float | None = None

    def classify(self, value: float | None) -> Status:
        if value is None:
            return Status.STALE
        if self.higher_is_worse:
            if self.critical is not None and value >= self.critical:
                return Status.CRITICAL
            if value >= self.red:
                return Status.RED
            if value >= self.yellow:
                return Status.YELLOW
            return Status.GREEN
        # lower is worse (e.g. spreads: more negative = worse)
        if self.critical is not None and value <= self.critical:
            return Status.CRITICAL
        if value <= self.red:
            return Status.RED
        if value <= self.yellow:
            return Status.YELLOW
        return Status.GREEN


@dataclass
class MetricResult:
    metric_id: str                       # e.g. "curve.3m10y"
    category: str                        # "A".."I"
    label: str
    value: float | None
    status: Status
    asof: date | None = None
    unit: str = ""
    delta_1d: float | None = None
    delta_5d: float | None = None
    delta_20d: float | None = None
    percentile: float | None = None      # 0-100, vs own history
    note: str = ""                       # what it means / historical lead time
    source_series: str = ""              # provenance (e.g. "FRED:T10Y3M")
    informational: bool = False          # display-only; excluded from the composite
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "metric_id": self.metric_id, "category": self.category, "label": self.label,
            "value": self.value, "status": self.status.value,
            "asof": self.asof.isoformat() if self.asof else None, "unit": self.unit,
            "delta_1d": self.delta_1d, "delta_5d": self.delta_5d, "delta_20d": self.delta_20d,
            "percentile": self.percentile, "note": self.note,
            "source_series": self.source_series, "informational": self.informational,
            "extra": self.extra,
        }


# --- pure helpers ------------------------------------------------------------

def delta(series: list[float | None], lag: int) -> float | None:
    """Latest minus value `lag` steps back (skipping trailing Nones on latest)."""
    vals = series
    if not vals or vals[-1] is None or len(vals) <= lag or vals[-1 - lag] is None:
        return None
    return vals[-1] - vals[-1 - lag]


def percentile_rank(series: list[float | None], value: float | None) -> float | None:
    """Percentile (0-100) of `value` within the non-null history."""
    if value is None:
        return None
    hist = [v for v in series if v is not None]
    if not hist:
        return None
    below = sum(1 for v in hist if v <= value)
    return round(100.0 * below / len(hist), 1)


def last_valid(series: list[float | None]) -> float | None:
    for v in reversed(series):
        if v is not None:
            return v
    return None
