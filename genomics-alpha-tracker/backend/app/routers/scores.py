"""Alpha Signal scores + flags API.

Every score response exposes the full formula and intermediate values so each
score is auditable — you see WHY a name lit up, not just the number.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..config import _load_yaml_cached
from ..db import get_session
from ..models import FlagEvent, ScoreSnapshot, Security
from ..schemas import FlagOut, ScoreOut
from ..scoring.engine import compute_scores

router = APIRouter(tags=["scores"])


def _latest_snapshots(session: Session) -> dict[str, ScoreSnapshot]:
    latest: dict[str, ScoreSnapshot] = {}
    for snap in session.exec(select(ScoreSnapshot).order_by(ScoreSnapshot.asof.asc())).all():
        latest[snap.symbol] = snap
    return latest


@router.post("/scores/recompute", response_model=list[ScoreOut])
def recompute(session: Session = Depends(get_session)):
    compute_scores(session)
    return list_scores(session=session)


@router.post("/scores/reload")
def reload_config():
    """Hot-reload scoring/flags/intervals YAML (clears the config cache)."""
    _load_yaml_cached.cache_clear()
    return {"status": "config caches cleared"}


@router.get("/scores", response_model=list[ScoreOut])
def list_scores(
    active_only: bool = Query(True),
    session: Session = Depends(get_session),
):
    secs = {s.symbol: s for s in session.exec(select(Security)).all()}
    latest = _latest_snapshots(session)
    out: list[ScoreOut] = []
    for symbol, snap in latest.items():
        sec = secs.get(symbol)
        if sec is None or (active_only and not sec.active):
            continue
        out.append(ScoreOut(
            symbol=symbol, name=sec.name, subsector=sec.subsector or [],
            asof=snap.asof, composite=snap.composite, components=snap.components,
            missing=snap.missing, formula=snap.formula,
        ))
    out.sort(key=lambda s: (s.composite is None, -(s.composite or 0)))
    return out


@router.get("/scores/{symbol}", response_model=ScoreOut)
def get_score(symbol: str, session: Session = Depends(get_session)):
    from fastapi import HTTPException

    symbol = symbol.upper()
    sec = session.get(Security, symbol)
    if sec is None:
        raise HTTPException(404, f"{symbol} not found")
    snap = session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.symbol == symbol)
        .order_by(ScoreSnapshot.asof.desc())
        .limit(1)
    ).first()
    if snap is None:
        raise HTTPException(404, f"no score yet for {symbol}; run /scores/recompute")
    return ScoreOut(
        symbol=symbol, name=sec.name, subsector=sec.subsector or [],
        asof=snap.asof, composite=snap.composite, components=snap.components,
        missing=snap.missing, formula=snap.formula,
    )


@router.get("/flags", response_model=list[FlagOut])
def list_flags(
    days: int = Query(7, ge=1, le=90),
    symbol: str | None = None,
    flag_type: str | None = None,
    session: Session = Depends(get_session),
):
    since = datetime.utcnow() - timedelta(days=days)
    stmt = select(FlagEvent).where(FlagEvent.asof >= since).order_by(FlagEvent.asof.desc())
    if symbol:
        stmt = stmt.where(FlagEvent.symbol == symbol.upper())
    if flag_type:
        stmt = stmt.where(FlagEvent.flag_type == flag_type)
    return [
        FlagOut(
            id=f.id, symbol=f.symbol, asof=f.asof, flag_type=f.flag_type,
            severity=f.severity, message=f.message, evidence=f.evidence,
        )
        for f in session.exec(stmt).all()
    ]
