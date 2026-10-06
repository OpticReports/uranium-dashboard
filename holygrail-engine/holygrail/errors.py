"""Exception hierarchy. Every validation failure in the engine raises one of
these (never a silent default), so callers can catch ``HolyGrailError``."""
from __future__ import annotations


class HolyGrailError(Exception):
    """Base class for all engine errors."""


class ValidationError(HolyGrailError, ValueError):
    """An input is malformed: NaN/inf, wrong shape, weights not summing, etc."""


class CovarianceError(ValidationError):
    """A covariance/correlation matrix is not square, symmetric, finite or PSD."""


class UnknownStreamError(HolyGrailError, KeyError):
    """A position, composite or factor references a stream that is not defined."""

    def __str__(self) -> str:  # KeyError quotes its arg; keep the message readable
        return str(self.args[0]) if self.args else "unknown stream"


class AssumptionError(ValidationError):
    """An assumption is missing its value/source/confidence, or a set of
    assumptions is internally inconsistent (e.g. implies negative variance)."""


class ReconciliationError(ValidationError):
    """Book totals do not reconcile with the sum of positions."""


class DataError(HolyGrailError):
    """A data feed failed, returned malformed data, or a cache entry required in
    offline mode is missing. There is no stale fallback: this always raises."""


class OptimizationError(HolyGrailError):
    """An optimiser failed to converge or its solution failed the KKT /
    risk-contribution verification."""
