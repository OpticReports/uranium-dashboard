"""Decision journal — append-only memos tied to names, calls, and flags.

"What did I think at entry" only works if the record can't be rewritten:
entries are immutable (no PATCH/PUT), and deletion is deliberately absent.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session
from ..models import JournalEntry, Security

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalCreate(BaseModel):
    symbol: Optional[str] = None
    title: str = Field("", max_length=200)
    content: str = Field(..., min_length=1)
    source: str = "manual"          # chat | manual
    model: Optional[str] = None
    call_id: Optional[int] = None
    flag_id: Optional[int] = None


class JournalOut(BaseModel):
    id: int
    symbol: Optional[str]
    created_at: str
    title: str
    content: str
    source: str
    model: Optional[str]
    call_id: Optional[int]
    flag_id: Optional[int]


def _out(e: JournalEntry) -> JournalOut:
    return JournalOut(
        id=e.id, symbol=e.symbol, created_at=e.created_at.isoformat(),
        title=e.title, content=e.content, source=e.source, model=e.model,
        call_id=e.call_id, flag_id=e.flag_id,
    )


@router.post("", response_model=JournalOut, status_code=201)
def create_entry(payload: JournalCreate, session: Session = Depends(get_session)):
    symbol = payload.symbol.upper() if payload.symbol else None
    if symbol and session.get(Security, symbol) is None:
        raise HTTPException(404, f"{symbol} is not in the universe")
    entry = JournalEntry(
        symbol=symbol, title=payload.title.strip(), content=payload.content,
        source=payload.source if payload.source in ("chat", "manual") else "manual",
        model=payload.model, call_id=payload.call_id, flag_id=payload.flag_id,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _out(entry)


@router.get("", response_model=list[JournalOut])
def list_entries(
    symbol: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    stmt = select(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(JournalEntry.symbol == symbol.upper())
    return [_out(e) for e in session.exec(stmt).all()]
