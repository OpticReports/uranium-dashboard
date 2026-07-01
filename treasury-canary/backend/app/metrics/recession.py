"""Recession model — Estrella-Mishkin probit on the 3m10y spread.

P(recession within 12 months) = Φ(β0 + β1 · spread), spread = 10y − 3m in pct pts.
Coefficients (β0 = −0.5333, β1 = −0.6330) reproduce the standard NY Fed table:
~30% at spread 0, ~50% at ≈ −0.82, single digits at strongly positive spreads.
"""
from __future__ import annotations

import math

BETA0 = -0.5333
BETA1 = -0.6330


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def recession_probability(spread_3m10y_pct: float | None) -> float | None:
    """12-month-ahead recession probability (percent, 0-100). None if no spread."""
    if spread_3m10y_pct is None:
        return None
    return round(100.0 * _norm_cdf(BETA0 + BETA1 * spread_3m10y_pct), 1)


def build_recession_metrics(bundle: dict[str, tuple[list, list]]) -> list:
    """MetricResults for the recession model + NFCI cross-check."""
    from .assemble import simple_metric
    from .base import MetricResult, Status, last_valid
    from .curve import build_spread
    from ..scoring import thresholds as T

    out: list = []
    d3, v3 = bundle.get("3mo", ([], []))
    d10, v10 = bundle.get("10y", ([], []))
    dates, spread = build_spread(d3, v3, d10, v10)  # 10y - 3m
    latest = last_valid(spread)
    prob = recession_probability(latest)
    out.append(MetricResult(
        metric_id="recession.prob", category="I", label="Recession prob (12mo, Estrella-Mishkin)",
        value=prob, status=T.classify("recession.prob", prob) if prob is not None else Status.STALE,
        asof=(dates[-1] if dates else None), unit="%", source_series="FRED:T10Y3M (probit)",
        note="Probit on 3m10y. ~30% at spread 0, ~50% near -0.82pp. Model, not a forecast."))

    nfci = bundle.get("nfci", ([], []))
    out.append(simple_metric(
        "recession.nfci", "I", "Chicago Fed NFCI", nfci[0], nfci[1], unit="idx",
        source="FRED:NFCI", note="External cross-check: >0 = tighter-than-average financial conditions."))
    return out


def near_term_forward_spread(
    fwd_3m_in_6q_pct: float | None, current_3m_pct: float | None
) -> float | None:
    """Engstrom-Sharpe near-term forward spread: 6-quarter-ahead implied 3m rate
    minus the current 3m. Negative = market pricing near-term cuts (distress).
    Provided when a forward rate is derivable; else None.
    """
    if fwd_3m_in_6q_pct is None or current_3m_pct is None:
        return None
    return round(fwd_3m_in_6q_pct - current_3m_pct, 3)
