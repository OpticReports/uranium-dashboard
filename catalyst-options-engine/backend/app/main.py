"""FastAPI app — Catalyst Options Engine. PAPER ONLY; KEYLESS by design.

This service is a decision brain: it holds no credentials and has no
execution path (CLAUDE.md separation-of-powers law — any future live options
execution would route through ibkr-executor, never here).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from datetime import date as Date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import scheduler as sched
from .config import engine_config, settings
from .db import get_session, init_db
from .engine import ledger
from .lanes import chains as chains_lane
from .lanes import prices as prices_lane
from .models import Catalyst, EquityPoint, PaperPosition, Setup
from .status_page import render_status_page

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.run_scheduler:
        sched.start_scheduler()
    yield
    sched.shutdown_scheduler()


app = FastAPI(title="Catalyst Options Engine", version="0.1.0",
              description="Paper-only, keyless pre-catalyst asymmetry radar",
              lifespan=lifespan)


def _starting_equity() -> float:
    return float(engine_config().get("paper", {}).get("starting_equity", 100_000))


def _latest_setups(session: Session) -> tuple[date | None, list[Setup]]:
    last = session.exec(select(Setup.asof).order_by(Setup.asof.desc())).first()
    if last is None:
        return None, []
    rows = session.exec(select(Setup).where(Setup.asof == last)).all()
    return last, list(rows)


# --- API -----------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "catalyst-options-engine",
            "paper_only": True, "keyless": True,
            "scheduler": settings.run_scheduler}


@app.get("/radar")
def radar(session: Session = Depends(get_session)):
    """Radar universe with the latest per-name signals."""
    asof, setups = _latest_setups(session)
    by_symbol = {s.symbol: s for s in setups}
    out = []
    for entry in sched.radar_entries():
        sym = entry.get("symbol")
        s = by_symbol.get(sym)
        out.append({"symbol": sym, "name": entry.get("name"),
                    "ctgov_names": entry.get("ctgov_names"),
                    "tags": entry.get("tags"),
                    "setup": None if s is None else s.model_dump(mode="json")})
    return {"asof": asof, "names": out}


@app.get("/setups")
def setups(min_score: float = 0.0, session: Session = Depends(get_session)):
    """Latest scored setups with EVERY input shown (score components, pricing
    basis of any proposal, and lane-dark flags)."""
    asof, rows = _latest_setups(session)
    rows = [r for r in rows if (r.score or 0) >= min_score or r.watch]
    rows.sort(key=lambda r: -(r.score if r.score is not None else -1))
    return {"asof": asof,
            "min_score_for_proposals": engine_config().get("min_score", 55),
            "setups": [r.model_dump(mode="json") for r in rows]}


@app.get("/paper/book")
def paper_book(session: Session = Depends(get_session)):
    positions = list(session.exec(select(PaperPosition)).all())
    s = ledger.summarize(positions, _starting_equity())
    series = session.exec(select(EquityPoint).order_by(EquityPoint.date)).all()
    return {"summary": s.__dict__,
            "equity_series": [{"date": p.date.isoformat(), "equity": p.equity,
                               "cash": p.cash, "open_value": p.open_value}
                              for p in series]}


@app.get("/paper/positions")
def paper_positions(status: Optional[str] = None,
                    session: Session = Depends(get_session)):
    q = select(PaperPosition)
    if status:
        q = q.where(PaperPosition.status == status)
    rows = session.exec(q.order_by(PaperPosition.created_at.desc())).all()
    return [r.model_dump(mode="json") for r in rows]


class CatalystIn(BaseModel):
    """Manual catalyst (PDUFA, AdComm, known interim analysis, conference).

    direction_lean is the ONLY path to a directional (CALL_ONLY/PUT_ONLY)
    proposal — operator judgment, never inferred."""

    symbol: str = Field(min_length=1, max_length=10)
    # NOTE: field named `date` shadows the type inside the class namespace —
    # the aliased Date keeps pydantic from resolving the annotation to None.
    date: Optional[Date] = None
    event_type: str = "interim_analysis"
    title: str = Field(min_length=1, max_length=200)
    impact_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    direction_lean: Optional[str] = None  # bullish | bearish | None
    url: Optional[str] = None


@app.post("/catalysts", status_code=201)
def add_catalyst(body: CatalystIn, session: Session = Depends(get_session)):
    if body.direction_lean is not None and body.direction_lean.lower() not in (
            "bullish", "bearish"):
        raise HTTPException(422, "direction_lean must be bullish|bearish|null")
    weights = engine_config().get("impact_weights", {})
    impact = (body.impact_weight if body.impact_weight is not None
              else weights.get(body.event_type, weights.get("other", 0.2)))
    rec = Catalyst(symbol=body.symbol.upper(), date=body.date,
                   event_type=body.event_type, title=body.title,
                   impact_weight=impact, watch=body.date is None,
                   direction_lean=(body.direction_lean.lower()
                                   if body.direction_lean else None),
                   confirmed=True, source="manual", url=body.url)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec.model_dump(mode="json")


@app.get("/catalysts")
def list_catalysts(symbol: Optional[str] = None,
                   session: Session = Depends(get_session)):
    q = select(Catalyst)
    if symbol:
        q = q.where(Catalyst.symbol == symbol.upper())
    rows = session.exec(q.order_by(Catalyst.date)).all()
    return [r.model_dump(mode="json") for r in rows]


@app.post("/paper/close/{position_id}")
def close_position(position_id: int, session: Session = Depends(get_session)):
    """Operator close at today's chain BID (or intrinsic when the chain lane
    is dark) — same honesty as auto-close."""
    pos = session.get(PaperPosition, position_id)
    if pos is None:
        raise HTTPException(404, "position not found")
    if pos.status != "open":
        raise HTTPException(409, "position already closed")
    res = chains_lane.fetch_chain(pos.symbol)
    chain_rows = None if res is None else res[1]
    spot = prices_lane.last_close(prices_lane.fetch_history(pos.symbol))
    out = ledger.close_position(session, pos, chain_rows, spot, date.today(),
                                reason="manual")
    if out is None:
        raise HTTPException(503, "cannot price a close right now: chain lane "
                                 "dark AND price lane dark — retry later")
    return out.model_dump(mode="json")


@app.post("/scan")
def scan_now(session: Session = Depends(get_session)):
    """Run the full daily sweep on demand (same code path as the scheduler)."""
    return sched.run_daily_scan(session)


# --- status page -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def status_page(session: Session = Depends(get_session)):
    asof, setups_rows = _latest_setups(session)
    positions = list(session.exec(select(PaperPosition)
                                  .order_by(PaperPosition.created_at.desc())).all())
    book = ledger.summarize(positions, _starting_equity())
    series = list(session.exec(select(EquityPoint)
                               .order_by(EquityPoint.date)).all())
    return render_status_page(setups_rows, positions, book, series,
                              asof or date.today())
