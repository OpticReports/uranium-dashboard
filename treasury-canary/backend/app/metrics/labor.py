"""J. Labor / real-economy signals.

Framing that matters: the unemployment RATE is a *lagging* indicator (shown as
context only, excluded from the composite). The useful signals are the rate's
MOMENTUM (the Sahm Rule) and initial jobless CLAIMS (leading). The yield curve
leads a downturn by ~12 months; the Sahm Rule confirms when it actually arrives.
"""
from __future__ import annotations

from datetime import date

from ..scoring import thresholds as T
from .assemble import simple_metric
from .base import MetricResult, Status, delta, last_valid, percentile_rank


def _sahm_from_unrate(dates: list[date], unrate: list[float | None]
                      ) -> tuple[list[date], list[float | None]]:
    """Sahm gap series: 3-month avg unemployment minus its low over the PRIOR 12
    months (excluding the current reading — official definition; matches FRED's
    SAHMREALTIME, which can go slightly negative while unemployment is falling).
    Triggers a recession call at >= 0.50pp."""
    pts = [(d, v) for d, v in zip(dates, unrate) if v is not None]
    ma3: list[float | None] = []
    for i in range(len(pts)):
        window = [pts[j][1] for j in range(max(0, i - 2), i + 1)]
        ma3.append(sum(window) / len(window) if len(window) == 3 else None)
    gaps: list[float | None] = []
    out_dates: list[date] = []
    for i in range(len(pts)):
        out_dates.append(pts[i][0])
        cur = ma3[i]
        prior = [ma3[j] for j in range(max(0, i - 12), i) if ma3[j] is not None]
        gaps.append(round(cur - min(prior), 2) if (cur is not None and prior) else None)
    return out_dates, gaps


def build_labor_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []

    # --- Sahm Rule: prefer FRED's official SAHMREALTIME, else compute from UNRATE ---
    sd, sv = bundle.get("sahm", ([], []))
    sahm_val = last_valid(sv)
    if sahm_val is not None:
        sahm_dates, sahm_series = sd, sv
        src = "FRED:SAHMREALTIME"
    else:
        ud, uv = bundle.get("unrate", ([], []))
        sahm_dates, sahm_series = _sahm_from_unrate(ud, uv)
        sahm_val = last_valid(sahm_series)
        src = "computed from FRED:UNRATE"
    asof = next((d for d, v in zip(reversed(sahm_dates), reversed(sahm_series)) if v is not None), None)
    out.append(MetricResult(
        metric_id="labor.sahm", category="J", label="Sahm Rule (recession indicator)",
        value=sahm_val, status=T.classify("labor.sahm", sahm_val) if sahm_val is not None else Status.STALE,
        asof=asof, unit="pp",
        delta_1d=delta(sahm_series, 1), delta_20d=delta(sahm_series, 3),
        percentile=percentile_rank(sahm_series, sahm_val),
        note="3mo-avg unemployment minus its 12mo low. >=0.50 has flagged the START of "
             "every recession since the 1970s. Confirms the curve's ~12mo lead.",
        source_series=src))

    # --- Initial jobless claims: YoY % change of the 4-week MA (leading) ---
    cd, cv = bundle.get("claims_4wk", ([], []))
    claims_now = last_valid(cv)
    # IC4WSA is weekly -> ~52 obs per year
    yoy = None
    vals = [v for v in cv if v is not None]
    if len(vals) > 52 and vals[-53]:
        yoy = round((vals[-1] - vals[-53]) / vals[-53] * 100.0, 1)
    yoy_series = []
    clean = [v for v in cv if v is not None]
    for i in range(len(clean)):
        yoy_series.append(round((clean[i] - clean[i - 52]) / clean[i - 52] * 100.0, 1)
                          if i >= 52 and clean[i - 52] else None)
    out.append(MetricResult(
        metric_id="labor.claims_yoy", category="J", label="Initial claims (YoY, 4wk MA)",
        value=yoy, status=T.classify("labor.claims_yoy", yoy) if yoy is not None else Status.STALE,
        asof=(cd[-1] if cd else None), unit="%",
        delta_20d=delta(yoy_series, 4), percentile=percentile_rank(yoy_series, yoy),
        note=f"Latest 4wk-MA claims: {claims_now:,.0f}. Claims lead the unemployment rate; "
             f"a sustained YoY rise is an early labor-market crack." if claims_now else
             "Claims lead the unemployment rate; a sustained YoY rise is an early crack.",
        source_series="FRED:IC4WSA"))

    # --- Unemployment rate: lagging context (display-only, not in composite) ---
    ud, uv = bundle.get("unrate", ([], []))
    m = simple_metric("labor.unrate", "J", "Unemployment rate", ud, uv, unit="%",
                      source="FRED:UNRATE",
                      note="LAGGING indicator — rises after a recession has begun. Shown for "
                           "context; excluded from the forward-looking stress score.")
    m.informational = True
    m.status = Status.GREEN if m.value is not None else Status.STALE
    out.append(m)
    return out
