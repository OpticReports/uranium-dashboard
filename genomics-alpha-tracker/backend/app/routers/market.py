"""Market data API: prices, fundamentals, and on-demand refresh."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import engine, get_session
from ..ingestion.runner import run_market
from ..models import Fundamental, PriceBar, Security

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/{symbol}/prices")
def get_prices(
    symbol: str,
    days: int = Query(365, ge=1, le=3650),
    session: Session = Depends(get_session),
):
    symbol = symbol.upper()
    since = date.today() - timedelta(days=days)
    bars = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= since)
        .order_by(PriceBar.date.asc())
    ).all()
    return [
        {
            "date": b.date.isoformat(), "open": b.open, "high": b.high,
            "low": b.low, "close": b.close, "adj_close": b.adj_close, "volume": b.volume,
        }
        for b in bars
    ]


@router.get("/{symbol}/fundamentals")
def get_fundamentals(symbol: str, session: Session = Depends(get_session)):
    symbol = symbol.upper()
    f = session.exec(
        select(Fundamental)
        .where(Fundamental.symbol == symbol)
        .order_by(Fundamental.asof.desc())
        .limit(1)
    ).first()
    if f is None:
        raise HTTPException(404, f"no fundamentals for {symbol}")
    # NOTE: None fields are genuine "no data" (common for thin-float names),
    # NOT zero. The frontend renders these as "n/a".
    return {
        "symbol": f.symbol, "asof": f.asof.isoformat(), "market_cap": f.market_cap,
        "cash": f.cash, "quarterly_burn": f.quarterly_burn, "rd_spend": f.rd_spend,
        "runway_quarters": f.runway_quarters, "short_interest_pct": f.short_interest_pct,
        "short_interest_percentile": f.short_interest_percentile,
        "iv": f.iv, "iv_skew": f.iv_skew, "source": f.source,
    }


def _refresh_task(symbols: list[str] | None) -> None:
    with Session(engine) as session:
        run_market(session, symbols)


@router.post("/refresh")
def refresh_market(
    background: BackgroundTasks,
    symbol: str | None = None,
    session: Session = Depends(get_session),
):
    symbols = [symbol.upper()] if symbol else None
    background.add_task(_refresh_task, symbols)
    return {"status": "market refresh queued", "scope": symbol or "active universe"}
