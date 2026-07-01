"""GET /events (log) and /alerts (active RED/CRITICAL)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..store.db import get_session
from ..store.models import EventLog

router = APIRouter(tags=["events"])


def _serialize(r: EventLog) -> dict:
    return {
        "id": r.id, "type": r.event_type, "severity": r.severity,
        "asof": r.asof.isoformat(), "rationale": r.rationale,
        "detail": json.loads(r.detail_json) if r.detail_json else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/events")
def events(limit: int = Query(100, le=500), session: Session = Depends(get_session)):
    rows = session.execute(
        select(EventLog).order_by(EventLog.asof.desc(), EventLog.id.desc()).limit(limit)
    ).scalars().all()
    return [_serialize(r) for r in rows]


@router.get("/alerts")
def alerts(session: Session = Depends(get_session)):
    """Active high-severity events (RED/CRITICAL), newest first."""
    rows = session.execute(
        select(EventLog).where(EventLog.severity.in_(("RED", "CRITICAL")))
        .order_by(EventLog.asof.desc(), EventLog.id.desc()).limit(50)
    ).scalars().all()
    return [_serialize(r) for r in rows]
