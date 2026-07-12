"""K. Leading stack — independent, individually-validated recession indicators.

Design contract (anti-overfit, per the dashboard's owner):
  * Each indicator is scored against its OWN historically-grounded rule.
  * They are NEVER jointly fitted (≈8 recessions of history — joint weights would
    be curve-fitting folklore) and NEVER enter the composite (informational=True).
  * The UI lets the user include/exclude each one and reports transparent breadth
    ("X of N included flashing") — no hidden weights anywhere.
Every note states the causal chain, the historical track record, and the known
false-positive modes, so each signal can be judged on its own merits.
"""
from __future__ import annotations

from datetime import date

from ..scoring import thresholds as T
from .base import MetricResult, Status, delta, last_valid, percentile_rank

# Observations per year, per series cadence (for YoY on monthly/weekly series).
_MONTHLY = 12


def _yoy(vals: list[float | None], per_year: int = _MONTHLY) -> list[float | None]:
    clean = [v for v in vals if v is not None]
    out: list[float | None] = []
    for i in range(len(clean)):
        prev = clean[i - per_year] if i >= per_year else None
        out.append(round((clean[i] - prev) / prev * 100.0, 1) if prev else None)
    return out


def _off_peak(vals: list[float | None], window: int = 12) -> list[float | None]:
    """% below the trailing `window`-observation peak (0 when at the peak)."""
    clean = [v for v in vals if v is not None]
    out: list[float | None] = []
    for i in range(len(clean)):
        lo = max(0, i - window + 1)
        peak = max(clean[lo:i + 1])
        out.append(round((clean[i] - peak) / peak * 100.0, 1) if peak else None)
    return out


def _ma(vals: list[float | None], n: int) -> list[float | None]:
    clean = [v for v in vals if v is not None]
    return [round(sum(clean[max(0, i - n + 1):i + 1]) / len(clean[max(0, i - n + 1):i + 1]), 2)
            if i >= n - 1 else None for i in range(len(clean))]


def _metric(metric_id: str, label: str, dates: list[date], series: list[float | None],
            unit: str, note: str, source: str) -> MetricResult:
    value = last_valid(series)
    asof = None
    non_null = [d for d, v in zip(dates, [v for v in series]) if v is not None]
    # series was derived from the clean values; align asof to the last raw date
    asof = dates[-1] if dates else None
    m = MetricResult(
        metric_id=metric_id, category="K", label=label, value=value,
        status=T.classify(metric_id, value) if value is not None else Status.STALE,
        asof=asof, unit=unit, delta_1d=delta(series, 1), delta_20d=delta(series, 3),
        percentile=percentile_rank(series, value), note=note, source_series=source,
    )
    m.informational = True   # display-only: the composite is never touched (by design)
    return m


def build_leading_metrics(bundle: dict[str, tuple[list, list]]) -> list[MetricResult]:
    out: list[MetricResult] = []

    d, v = bundle.get("permits", ([], []))
    out.append(_metric(
        "leading.permits_yoy", "Building permits (YoY)", d, _yoy(v), "%",
        "Housing IS the business cycle (Leamer): rates → permits → construction jobs → "
        "consumption. Strongest single leading indicator in Moody's backtests; leads by "
        "~6-12mo. False-positive mode: supply-constrained slowdowns.", "FRED:PERMIT"))

    d, v = bundle.get("sloos", ([], []))
    out.append(_metric(
        "leading.sloos", "SLOOS: banks tightening C&I (net %)", d, v, "%",
        "Credit supply is causal: banks tightening standards chokes investment with a "
        "~2-3 quarter lag. Net tightening >20% has accompanied every modern recession. "
        "Quarterly — slow but high-signal.", "FRED:DRTSCILM"))

    d, v = bundle.get("temp_help", ([], []))
    out.append(_metric(
        "leading.temp_help_yoy", "Temp-help employment (YoY)", d, _yoy(v), "%",
        "Firms shed temps before permanent staff — labor demand's first crack. CAVEAT: "
        "negative through 2023-25 WITHOUT a recession (structural post-COVID shrink), a "
        "live false-positive mode — read jointly with claims.", "FRED:TEMPHELPS"))

    d, v = bundle.get("heavy_trucks", ([], []))
    out.append(_metric(
        "leading.trucks_off_peak", "Heavy truck sales (% off 12m peak)", d,
        _off_peak(v, 12), "%",
        "Fell before all 7 recessions since 1973 (~13mo avg lead): freight/capex demand "
        "rolls over first. False-positive mode: mid-cycle fleet-replacement pauses.",
        "FRED:HTRUCKSSAAR"))

    d, v = bundle.get("core_capex", ([], []))
    out.append(_metric(
        "leading.core_capex_yoy", "Core capex orders (YoY)", d, _yoy(v), "%",
        "Nondefense capital goods ex-aircraft — business investment intentions in real "
        "time. Sustained negative YoY = firms pulling back before they fire people.",
        "FRED:NEWORDER"))

    d, v = bundle.get("cfnai", ([], []))
    out.append(_metric(
        "leading.cfnai_ma3", "CFNAI (3-month avg)", d, _ma(v, 3), "idx",
        "Chicago Fed's 85-indicator activity factor. Official rule: MA3 below -0.70 "
        "following an expansion = a recession has LIKELY BEGUN (coincident confirmation, "
        "not prediction).", "FRED:CFNAI"))

    d, v = bundle.get("gdpnow", ([], []))
    out.append(_metric(
        "leading.gdpnow", "Atlanta Fed GDPNow", d, v, "% SAAR",
        "Model nowcast of CURRENT-quarter real GDP growth. Noisy early in each quarter, "
        "converges as data arrives. A nowcast, not a forecast — shows where we already are.",
        "FRED:GDPNOW"))

    d, v = bundle.get("cp_prob", ([], []))
    out.append(_metric(
        "leading.cp_prob", "Chauvet-Piger recession prob.", d, v, "%",
        "Dynamic-factor Markov-switching model over the four NBER coincident series — "
        "the econometric gold standard for 'are we in one RIGHT NOW'. ~2mo publication "
        "lag; readings >80% for 3 months have marked every recession start.",
        "FRED:RECPROUSM156N"))

    return out
