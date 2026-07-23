"""J. Labor / real-economy signals.

Framing that matters: the unemployment RATE is a *lagging* indicator (shown as
context only, excluded from the composite). The useful signals are the rate's
MOMENTUM (the Sahm Rule) and initial jobless CLAIMS (leading). The yield curve
leads a downturn by ~12 months; the Sahm Rule confirms when it actually arrives.
"""
from __future__ import annotations

from datetime import date, timedelta

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


def _yoy_by_date(dates: list[date], vals: list[float | None], *, tol_days: int
                 ) -> tuple[list[date], list[float | None]]:
    """YoY % change matched BY DATE (nearest observation to d-365, within
    tol_days) rather than by index, so it works for monthly and near-daily
    series alike and stays correct across gaps/frequency changes."""
    pts = [(d, v) for d, v in zip(dates, vals) if v is not None]
    out_dates: list[date] = []
    out: list[float | None] = []
    j = 0
    for d, v in pts:
        target = d - timedelta(days=365)
        while (j + 1 < len(pts)
               and abs((pts[j + 1][0] - target).days) <= abs((pts[j][0] - target).days)):
            j += 1
        base_d, base_v = pts[j]
        ok = abs((base_d - target).days) <= tol_days and base_v
        out_dates.append(d)
        out.append(round((v - base_v) / base_v * 100.0, 1) if ok else None)
    return out_dates, out


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

    # --- Labor DEMAND: V/U ratio + openings YoY (leading — openings roll over
    # months before layoffs show up in claims/Sahm) -----------------------------
    od, ov = bundle.get("openings", ([], []))
    ued, uev = bundle.get("unemployed", ([], []))
    unemp_by_date = {d: v for d, v in zip(ued, uev) if v}
    vu_dates: list[date] = []
    vu_series: list[float | None] = []
    for d, v in zip(od, ov):
        u = unemp_by_date.get(d)
        if v is not None and u:
            vu_dates.append(d)
            vu_series.append(round(v / u, 2))
    vu_now = last_valid(vu_series)
    out.append(MetricResult(
        metric_id="labor.vu_ratio", category="J", label="Job openings per unemployed (V/U)",
        value=vu_now,
        status=T.classify("labor.vu_ratio", vu_now) if vu_now is not None else Status.STALE,
        asof=(vu_dates[-1] if vu_dates else None), unit="x",
        delta_1d=delta(vu_series, 1), delta_20d=delta(vu_series, 12),
        percentile=percentile_rank(vu_series, vu_now),
        note="Beveridge-curve regime gauge. Above ~1.2, falling openings is excess-demand "
             "normalization (the 2022-24 soft landing); at or below ~1.0 every lost opening "
             "bites employment — V/U fell through 1.0 into both the 2001 and 2008 recessions.",
        source_series="FRED:JTSJOL / FRED:UNEMPLOY"))

    oy_dates, oy_series = _yoy_by_date(od, ov, tol_days=45)
    oy_now = last_valid(oy_series)
    oy_status = T.classify("labor.openings_yoy", oy_now) if oy_now is not None else Status.STALE
    capped = False
    if vu_now is not None and vu_now >= 1.2 and oy_status.rank > Status.YELLOW.rank:
        # Falling from excess-demand levels is normalization, not deterioration
        # (documented alongside the threshold) — cap at YELLOW while V/U >= 1.2.
        oy_status = Status.YELLOW
        capped = True
    out.append(MetricResult(
        metric_id="labor.openings_yoy", category="J", label="Job openings (YoY)",
        value=oy_now, status=oy_status,
        asof=(oy_dates[-1] if oy_dates else None), unit="%",
        delta_20d=delta(oy_series, 3), percentile=percentile_rank(oy_series, oy_now),
        note=("Labor demand is the FRONT of the deterioration chain: openings fall before "
              "layoffs, claims, and the Sahm trigger. Severity is conditioned on V/U — "
              + ("capped at YELLOW while V/U >= 1.2 (normalization regime)."
                 if capped else
                 f"with V/U at {vu_now}, lost openings translate into unemployment."
                 if vu_now is not None else "V/U unavailable.")),
        source_series="FRED:JTSJOL",
        extra={"vu_ratio": vu_now, "capped_by_vu": capped}))

    # --- Indeed postings: timely (near-daily) read on the same demand signal.
    # Informational: series starts Feb 2020 — no full cycle to validate against.
    idd, idv = bundle.get("indeed_postings", ([], []))
    iy_dates, iy_series = _yoy_by_date(idd, idv, tol_days=10)
    iy_now = last_valid(iy_series)
    level_now = last_valid(idv)  # index, Feb-2020 = 100
    im = MetricResult(
        metric_id="labor.indeed_yoy", category="J", label="Indeed job postings (YoY)",
        value=iy_now,
        status=T.classify("labor.indeed_yoy", iy_now) if iy_now is not None else Status.STALE,
        asof=(iy_dates[-1] if iy_dates else None), unit="%",
        delta_20d=delta(iy_series, 20), percentile=percentile_rank(iy_series, iy_now),
        note=("Near-real-time labor demand (JOLTS confirms with a ~5wk lag). "
              + (f"Index at {level_now:.1f} vs Feb-2020 = 100 — the post-COVID excess-demand "
                 f"cushion is {'gone' if level_now <= 105 else 'still present'}."
                 if level_now is not None else "")),
        source_series="FRED:IHLIDXUS",
        extra={"index_level": level_now})
    im.informational = True
    out.append(im)
    return out
