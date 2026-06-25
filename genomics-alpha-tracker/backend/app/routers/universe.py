"""Universe management API.

POST /universe          add a ticker (validate symbol -> auto-name -> backfill)
GET  /universe          list (optionally include inactive)
PATCH /universe/{sym}   toggle active / edit tags / rename
DELETE /universe/{sym}  hard delete (use PATCH active=false to retain history)
POST /universe/reload   re-sync from watchlist.yaml (upsert, never wipes)
GET  /universe/subsectors  distinct free-form theme tags
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import engine, get_session
from ..ingestion.providers.base import get_provider
from ..ingestion.runner import backfill_symbol
from ..schemas import SecurityCreate, SecurityOut, SecurityUpdate
from ..universe import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/universe", tags=["universe"])


def _to_out(sec) -> SecurityOut:
    return SecurityOut(
        symbol=sec.symbol, name=sec.name, subsector=sec.subsector or [],
        active=sec.active, updated_at=sec.updated_at,
    )


def _backfill_task(symbol: str) -> None:
    with Session(engine) as session:
        backfill_symbol(session, symbol)


@router.get("", response_model=list[SecurityOut])
def list_universe(
    include_inactive: bool = Query(True),
    session: Session = Depends(get_session),
):
    return [_to_out(s) for s in manager.list_securities(session, include_inactive)]


@router.get("/subsectors", response_model=list[str])
def list_subsectors(session: Session = Depends(get_session)):
    return manager.all_subsectors(session)


@router.post("", response_model=SecurityOut, status_code=201)
def add_ticker(
    payload: SecurityCreate,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    symbol = payload.symbol.upper()
    if manager.get_security(session, symbol):
        raise HTTPException(409, f"{symbol} already in universe")

    name = payload.name
    if name is None:
        # Validate against the market-data provider and auto-fetch the name.
        provider = get_provider()
        resolved = provider.validate_symbol(symbol)
        if resolved is None:
            raise HTTPException(
                422,
                f"Symbol '{symbol}' could not be validated against provider "
                f"'{provider.name}'. Pass an explicit name to add it anyway.",
            )
        name = resolved

    sec = manager.upsert_security(
        session, symbol=symbol, name=name,
        subsector=payload.subsector, active=payload.active,
    )
    if payload.backfill and payload.active:
        background.add_task(_backfill_task, symbol)
        logger.info("Queued backfill for newly added %s", symbol)
    return _to_out(sec)


@router.patch("/{symbol}", response_model=SecurityOut)
def update_ticker(
    symbol: str,
    payload: SecurityUpdate,
    session: Session = Depends(get_session),
):
    sec = manager.get_security(session, symbol)
    if sec is None:
        raise HTTPException(404, f"{symbol} not found")
    sec = manager.upsert_security(
        session, symbol=symbol.upper(), name=payload.name,
        subsector=payload.subsector, active=payload.active,
    )
    return _to_out(sec)


@router.delete("/{symbol}", status_code=204)
def delete_ticker(symbol: str, session: Session = Depends(get_session)):
    if not manager.delete_security(session, symbol):
        raise HTTPException(404, f"{symbol} not found")


@router.post("/reload")
def reload_universe(session: Session = Depends(get_session)):
    return manager.sync_from_yaml(session)
