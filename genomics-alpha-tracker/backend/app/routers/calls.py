"""Trade Calls API — the tracker's own logged, graded track record.

Every call is an exact, immutable trade expression (entry/stop/target/time-stop)
recorded at fire-time and graded against subsequent daily bars. GET /calls is
the log; GET /calls/scorecard answers "which signals actually pay".
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..calls import manager
from ..calls.postmortem import update_postmortems
from ..calls.rules import atr, build_levels, call_r_multiple, call_return
from ..config import calls_config
from ..db import get_session
from ..models import CallPostmortem, Security, TradeCall
from ..schemas import CallsScorecardOut, TradeCallClose, TradeCallCreate, TradeCallOut

router = APIRouter(prefix="/calls", tags=["calls"])


def _to_out(session: Session, call: TradeCall) -> TradeCallOut:
    sec = session.get(Security, call.symbol)
    out = TradeCallOut(
        id=call.id, symbol=call.symbol, name=sec.name if sec else "",
        created_at=call.created_at, call_date=call.call_date,
        direction=call.direction, source=call.source, flag_type=call.flag_type,
        thesis=call.thesis, entry_price=call.entry_price,
        stop_price=call.stop_price, target_price=call.target_price,
        expires_on=call.expires_on, composite_at_call=call.composite_at_call,
        status=call.status, exit_date=call.exit_date, exit_price=call.exit_price,
        return_pct=call.return_pct, r_multiple=call.r_multiple,
    )
    if call.status == "open":
        latest = manager._latest_close(session, call.symbol)
        if latest is not None:
            _, last = latest
            out.last_price = last
            out.unrealized_pct = call_return(call.direction, call.entry_price, last)
            out.unrealized_r = call_r_multiple(
                call.direction, call.entry_price, call.stop_price, last
            )
    else:
        pm = session.exec(
            select(CallPostmortem).where(CallPostmortem.call_id == call.id)
        ).first()
        if pm is not None:
            out.postmortem = {
                "summary": pm.summary,
                "mfe_r": pm.mfe_r,
                "mae_r": pm.mae_r,
                "alpha": pm.alpha,
                "bench_return": pm.bench_return,
                "signal_decay": pm.signal_decay,
                "catalyst_status": pm.catalyst_status,
                "hindsight_verdict": pm.hindsight_verdict,
                "hindsight_complete": pm.hindsight_complete,
            }
    return out


@router.get("", response_model=list[TradeCallOut])
def list_calls(
    status: str | None = Query(None, description="open | target_hit | stopped | expired | closed_manual"),
    symbol: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(TradeCall).order_by(TradeCall.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(TradeCall.status == status)
    if symbol:
        stmt = stmt.where(TradeCall.symbol == symbol.upper())
    return [_to_out(session, c) for c in session.exec(stmt).all()]


@router.get("/scorecard", response_model=CallsScorecardOut)
def get_scorecard(session: Session = Depends(get_session)):
    return manager.scorecard(session)


@router.get("/performance")
def get_performance(session: Session = Depends(get_session)):
    """Call accuracy/strength over time: equity curve (cumulative R), rolling
    win rate & avg R, entry-month cohorts (the learning metric), and flag
    fire-month cohorts (the fast early signal)."""
    from ..calls.performance import calls_performance

    return calls_performance(session)


@router.post("/generate", response_model=list[TradeCallOut])
def generate_now(session: Session = Depends(get_session)):
    """Run auto-generation immediately (also runs on the scheduler)."""
    made = manager.generate_calls(session)
    return [_to_out(session, c) for c in made]


@router.post("/evaluate", response_model=list[TradeCallOut])
def evaluate_now(session: Session = Depends(get_session)):
    """Grade open calls against the latest bars immediately; returns calls closed.
    Also builds/refreshes post-mortems so 'why' appears with the outcome."""
    closed = manager.evaluate_calls(session)
    update_postmortems(session)
    return [_to_out(session, c) for c in closed]


@router.post("", response_model=TradeCallOut, status_code=201)
def create_call(payload: TradeCallCreate, session: Session = Depends(get_session)):
    """Log a manual call. Missing levels are filled the same way auto calls are
    (entry = latest close, ATR stop, reward:risk target) so every logged call
    is gradeable."""
    symbol = payload.symbol.upper()
    sec = session.get(Security, symbol)
    if sec is None:
        raise HTTPException(404, f"{symbol} is not in the universe")
    if payload.direction not in ("long", "short"):
        raise HTTPException(422, "direction must be 'long' or 'short'")

    latest = manager._latest_close(session, symbol)
    if latest is None and payload.entry_price is None:
        raise HTTPException(422, f"no price data for {symbol}; provide entry_price")
    call_date = latest[0] if latest else date.today()
    entry = payload.entry_price if payload.entry_price is not None else latest[1]

    stop, target = payload.stop_price, payload.target_price
    if stop is None or target is None:
        cfg = calls_config().get("risk", {})
        atr_window = cfg.get("atr_window", 14)
        bars = manager._recent_bars(session, symbol, call_date - timedelta(days=atr_window * 3))
        levels = build_levels(
            entry=entry, direction=payload.direction,
            atr_value=atr(bars, atr_window),
            stop_atr_mult=cfg.get("stop_atr_mult", 2.0),
            fallback_stop_pct=cfg.get("fallback_stop_pct", 0.08),
            reward_risk=cfg.get("reward_risk", 2.0),
        )
        if levels is None:
            raise HTTPException(422, "could not derive levels; provide stop_price and target_price")
        stop = stop if stop is not None else levels.stop
        target = target if target is not None else levels.target

    if payload.direction == "long" and not (stop < entry < target):
        raise HTTPException(422, "long call requires stop < entry < target")
    if payload.direction == "short" and not (target < entry < stop):
        raise HTTPException(422, "short call requires target < entry < stop")

    call = TradeCall(
        symbol=symbol, call_date=call_date, direction=payload.direction,
        source=payload.source if payload.source in ("manual", "chat") else "manual",
        thesis=payload.thesis,
        entry_price=round(entry, 4), stop_price=round(stop, 4),
        target_price=round(target, 4),
        expires_on=call_date + timedelta(days=payload.horizon_days),
        composite_at_call=manager._latest_composite(session, symbol),
    )
    session.add(call)
    session.commit()
    session.refresh(call)
    return _to_out(session, call)


@router.post("/{call_id}/close", response_model=TradeCallOut)
def close_call(call_id: int, payload: TradeCallClose, session: Session = Depends(get_session)):
    call = session.get(TradeCall, call_id)
    if call is None:
        raise HTTPException(404, f"call {call_id} not found")
    if call.status != "open":
        raise HTTPException(409, f"call {call_id} is already {call.status}")
    try:
        call = manager.close_call_manual(session, call, payload.exit_price, payload.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    update_postmortems(session)
    return _to_out(session, call)
