"""Shadow-book API — the H11/H8 observe-only live evidence (see calls/shadow.py).

GET /shadow/track-record answers "on the SAME calls, how does the R2-A
trailing exit engine compare to the production fixed-3:1 engine, and what has
the XBI regime gate been doing?" — the record that decides whether R2-A ever
earns a calls.yaml change. Nothing here mutates the live book.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..calls.shadow import evaluate_shadow_calls, log_regime, shadow_track_record
from ..db import get_session
from ..models import RegimeLog

router = APIRouter(prefix="/shadow", tags=["shadow"])


@router.get("/track-record")
def get_track_record(session: Session = Depends(get_session)):
    """Per-engine comparison of closed pairs (production vs trailing exits on
    the same calls), pending buckets, and the regime-gate summary."""
    return shadow_track_record(session)


@router.get("/regime")
def get_regime(
    days: int = Query(90, ge=1, le=1000, description="most recent rows to return"),
    session: Session = Depends(get_session),
):
    """Recent daily regime log (prior-close convention), newest first."""
    rows = session.exec(
        select(RegimeLog).order_by(RegimeLog.date.desc()).limit(days)
    ).all()
    return [
        {
            "date": r.date,
            "xbi_close": r.xbi_close,
            "above_50dma": r.above_50dma,
            "above_200dma": r.above_200dma,
        }
        for r in rows
    ]


@router.post("/evaluate")
def evaluate_now(session: Session = Depends(get_session)):
    """Run the shadow grader + regime logger immediately (also scheduled)."""
    made = evaluate_shadow_calls(session)
    regime = log_regime(session)
    return {
        "shadow_graded": [
            {"call_id": g.call_id, "status": g.status, "exit_date": g.exit_date,
             "exit_price": g.exit_price, "r_multiple": g.r_multiple}
            for g in made
        ],
        "regime_logged": regime.date if regime else None,
    }
