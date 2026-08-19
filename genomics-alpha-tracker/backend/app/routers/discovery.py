"""Universe discovery API — the visible, auditable candidate queue.

GET  /discovery/candidates            list candidates (optional ?status= filter)
GET  /discovery/summary               counts by status, auto-promote state, last run
POST /discovery/run                   manual sweep (same pipeline as the daily job)
POST /discovery/candidates/{sym}/promote   manual promote (same upsert path as auto)
POST /discovery/candidates/{sym}/dismiss   dismiss with a reason (auditable, refire-suppressed)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..ingestion.discovery import get_cfg, promote_candidate, run_discovery
from ..models import Security, UniverseCandidate
from ..schemas import CandidateDismiss, CandidateOut, DiscoverySummaryOut
from ..utils import cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["discovery"])

_STATUSES = ("new", "watch", "promoted", "dismissed")


def _to_out(c: UniverseCandidate) -> CandidateOut:
    return CandidateOut(
        symbol=c.symbol, name=c.name, market_cap=c.market_cap,
        last_price=c.last_price, score=c.score, status=c.status,
        status_reason=c.status_reason, sources=c.sources or [],
        genomics_tags=c.genomics_tags or [], evidence=c.evidence or {},
        first_seen=c.first_seen, last_seen=c.last_seen,
        status_changed_at=c.status_changed_at,
    )


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(
    status: str | None = None,
    session: Session = Depends(get_session),
):
    if status is not None and status not in _STATUSES:
        raise HTTPException(422, f"status must be one of {_STATUSES}")
    stmt = select(UniverseCandidate)
    if status:
        stmt = stmt.where(UniverseCandidate.status == status)
    cands = list(session.exec(stmt).all())
    cands.sort(key=lambda c: c.score or 0.0, reverse=True)
    return [_to_out(c) for c in cands]


@router.get("/summary", response_model=DiscoverySummaryOut)
def summary(session: Session = Depends(get_session)):
    cfg = get_cfg()
    cands = session.exec(select(UniverseCandidate)).all()
    counts = {s: 0 for s in _STATUSES}
    for c in cands:
        counts[c.status] = counts.get(c.status, 0) + 1
    week_ago = datetime.utcnow() - timedelta(days=7)
    promoted_week = sorted(
        c.symbol for c in cands
        if c.status == "promoted" and c.status_changed_at >= week_ago
    )
    return DiscoverySummaryOut(
        counts=counts,
        auto_promote=bool(cfg["auto_promote"]),
        auto_promote_per_week=int(cfg["auto_promote_per_week"]),
        promoted_this_week=promoted_week,
        # Effectively "most recent sweep" — the file cache entry is written on
        # every run; the huge TTL only bounds staleness display, not behavior.
        last_run=cache.get("discovery:last_run", ttl=10**9),
    )


@router.post("/run")
def run_sweep(session: Session = Depends(get_session)):
    """Manual sweep — same pipeline as the daily scheduler job."""
    return run_discovery(session)


@router.post("/candidates/{symbol}/promote", response_model=CandidateOut)
def promote(symbol: str, session: Session = Depends(get_session)):
    cand = session.get(UniverseCandidate, symbol.upper())
    if cand is None:
        raise HTTPException(404, f"{symbol} not in the candidate queue")
    if cand.status == "promoted":
        raise HTTPException(409, f"{symbol} already promoted")
    if session.get(Security, cand.symbol):
        raise HTTPException(409, f"{symbol} already in the universe")
    promote_candidate(session, cand, reason="manual")
    logger.info("discovery manual promote: %s (%s)", cand.symbol, cand.name)
    return _to_out(cand)


@router.post("/candidates/{symbol}/dismiss", response_model=CandidateOut)
def dismiss(symbol: str, payload: CandidateDismiss,
            session: Session = Depends(get_session)):
    cand = session.get(UniverseCandidate, symbol.upper())
    if cand is None:
        raise HTTPException(404, f"{symbol} not in the candidate queue")
    cand.status = "dismissed"
    cand.status_reason = payload.reason
    cand.status_changed_at = datetime.utcnow()
    session.add(cand)
    session.commit()
    session.refresh(cand)
    return _to_out(cand)
