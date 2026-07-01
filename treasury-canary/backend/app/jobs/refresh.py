"""Daily ETL: fetch -> compute -> persist snapshot -> detect & log events.

Pure `compute_all` (used by tests and API) is separated from `run_refresh` (I/O).
Events dedupe on (event_type, dedup_key) so an alert fires exactly once.
"""
from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import FRED_TENORS, settings
from ..metrics.crossasset import build_crossasset_metrics
from ..metrics.curve import build_curve_metrics
from ..metrics.funding import build_funding_metrics
from ..metrics.premium import build_premium_metrics
from ..metrics.recession import build_recession_metrics
from ..metrics.volatility import build_volatility_metrics
from ..scoring.composite import compute_composite
from ..scoring.events import Event, detect_band_cross, detect_curve_events, detect_metric_flip
from ..sources.fred import fetch_bundle, recession_start_dates
from ..store.models import EventLog, MetricSnapshot, utcnow

logger = logging.getLogger(__name__)


def compute_all(bundle: dict):
    """Build every metric + composite from a fetched bundle. No I/O."""
    tenors = {k: bundle[k] for k in FRED_TENORS if k in bundle}
    rec_dates, rec_vals = bundle.get("recession", ([], []))
    recession_starts = recession_start_dates(rec_dates, rec_vals)

    curve_metrics, analyses = build_curve_metrics(tenors, recession_starts=recession_starts)
    metrics = (
        curve_metrics
        + build_funding_metrics(bundle)
        + build_volatility_metrics(bundle)
        + build_premium_metrics(bundle)
        + build_crossasset_metrics(bundle)
        + build_recession_metrics(bundle)
    )
    composite = compute_composite(metrics)
    return metrics, analyses, composite, recession_starts


def _prev_status_map(session: Session) -> dict[str, str]:
    rows = session.execute(select(MetricSnapshot).order_by(MetricSnapshot.asof.asc())).scalars().all()
    return {r.metric_id: r.status for r in rows}


def _prev_band(session: Session) -> str | None:
    rows = session.execute(
        select(MetricSnapshot).where(MetricSnapshot.metric_id == "composite")
        .order_by(MetricSnapshot.asof.asc())
    ).scalars().all()
    return rows[-1].status if rows else None


def _upsert_snapshot(session: Session, **kw) -> None:
    existing = session.execute(
        select(MetricSnapshot).where(MetricSnapshot.metric_id == kw["metric_id"])
        .where(MetricSnapshot.asof == kw["asof"])
    ).scalars().first()
    if existing:
        for k, v in kw.items():
            setattr(existing, k, v)
    else:
        session.add(MetricSnapshot(**kw))


def _persist_event(session: Session, ev: Event) -> bool:
    row = EventLog(
        event_type=ev.event_type, severity=ev.severity, asof=ev.asof,
        dedup_key=ev.dedup_key, rationale=ev.rationale, detail_json=ev.detail_json(),
    )
    session.add(row)
    try:
        session.flush()
        return True
    except IntegrityError:
        session.rollback()   # already logged this transition -> idempotent skip
        return False


def _fire_webhook(ev: Event) -> None:
    if not settings.alert_webhook_url:
        return
    try:
        httpx.post(settings.alert_webhook_url, json={
            "type": ev.event_type, "severity": ev.severity, "asof": ev.asof.isoformat(),
            "rationale": ev.rationale, "detail": ev.detail,
        }, timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alert webhook failed: %s", exc)


def run_refresh(session: Session) -> dict:
    bundle = fetch_bundle()
    metrics, analyses, composite, _ = compute_all(bundle)
    today = utcnow().date()

    prev_status = _prev_status_map(session)
    prev_band = _prev_band(session)

    for m in metrics:
        _upsert_snapshot(
            session, metric_id=m.metric_id, category=m.category, asof=(m.asof or today),
            value=m.value, status=m.status.value, percentile=m.percentile,
            delta_1d=m.delta_1d, delta_5d=m.delta_5d, delta_20d=m.delta_20d, note=m.note)
    _upsert_snapshot(
        session, metric_id="composite", category="Z", asof=today,
        value=composite.score, status=composite.band, percentile=composite.coverage * 100,
        note=json.dumps(composite.contributions))

    # --- events ---
    new_events: list[Event] = []
    med_lag = None
    for pair, a in analyses.items():
        for ev in detect_curve_events(pair, a, today, median_lag_months=med_lag):
            new_events.append(ev)
    bc = detect_band_cross(prev_band, composite.band, composite.score, today)
    if bc:
        new_events.append(bc)
    for m in metrics:
        fe = detect_metric_flip(m, prev_status.get(m.metric_id), today)
        if fe:
            new_events.append(fe)

    fired = 0
    for ev in new_events:
        if _persist_event(session, ev):
            fired += 1
            if ev.severity in ("RED", "CRITICAL"):
                _fire_webhook(ev)
    session.commit()

    return {
        "asof": today.isoformat(),
        "composite": composite.score, "band": composite.band,
        "coverage": composite.coverage, "n_metrics": len(metrics),
        "n_stale": sum(1 for m in metrics if m.status.value == "STALE"),
        "events_logged": fired,
        "fred_key_present": bool(settings.fred_api_key),
    }


def run_backfill(session: Session) -> dict:
    """Warm the FRED cache (full history) and seed today's snapshot. Chart history is
    computed live from the cached bundle, so no per-day snapshot backfill is needed."""
    return run_refresh(session)
