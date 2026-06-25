"""Catalyst calendar API (auto-ingested + manual, with impact overrides)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models import Catalyst, Security
from ..schemas import CatalystCreate, CatalystOut, CatalystUpdate

router = APIRouter(prefix="/catalysts", tags=["catalysts"])


def _to_out(c: Catalyst) -> CatalystOut:
    return CatalystOut(
        id=c.id, symbol=c.symbol, date=c.date, event_type=c.event_type,
        title=c.title, impact_weight=c.impact_weight, impact_override=c.impact_override,
        effective_impact=c.effective_impact, confirmed=c.confirmed, status=c.status,
        url=c.url, source=c.source,
    )


@router.get("", response_model=list[CatalystOut])
def list_catalysts(
    days: int = Query(90, ge=1, le=720),
    symbol: str | None = None,
    subsector: str | None = None,
    min_impact: float = Query(0.0, ge=0.0, le=1.0),
    session: Session = Depends(get_session),
):
    horizon = date.today() + timedelta(days=days)
    stmt = (
        select(Catalyst)
        .where(Catalyst.date >= date.today())
        .where(Catalyst.date <= horizon)
        .order_by(Catalyst.date.asc())
    )
    if symbol:
        stmt = stmt.where(Catalyst.symbol == symbol.upper())
    cats = session.exec(stmt).all()

    if subsector:
        syms = {
            s.symbol
            for s in session.exec(select(Security)).all()
            if subsector in (s.subsector or [])
        }
        cats = [c for c in cats if c.symbol in syms]

    return [_to_out(c) for c in cats if c.effective_impact >= min_impact]


@router.post("", response_model=CatalystOut, status_code=201)
def create_catalyst(payload: CatalystCreate, session: Session = Depends(get_session)):
    if not session.get(Security, payload.symbol.upper()):
        raise HTTPException(404, f"{payload.symbol} not in universe")
    cat = Catalyst(
        symbol=payload.symbol.upper(), date=payload.date, event_type=payload.event_type,
        title=payload.title, impact_override=payload.impact_override,
        confirmed=payload.confirmed, url=payload.url, source=payload.source,
    )
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return _to_out(cat)


@router.patch("/{catalyst_id}", response_model=CatalystOut)
def update_catalyst(
    catalyst_id: int, payload: CatalystUpdate, session: Session = Depends(get_session)
):
    cat = session.get(Catalyst, catalyst_id)
    if cat is None:
        raise HTTPException(404, "catalyst not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return _to_out(cat)


@router.delete("/{catalyst_id}", status_code=204)
def delete_catalyst(catalyst_id: int, session: Session = Depends(get_session)):
    cat = session.get(Catalyst, catalyst_id)
    if cat is None:
        raise HTTPException(404, "catalyst not found")
    session.delete(cat)
    session.commit()
