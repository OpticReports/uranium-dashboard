"""GET /news — Tiingo-backed universe news (DESCRIPTIVE context only; feeds
no score). /news/pulse ranks tickers by 24h article velocity vs their own 7d
baseline — biotech catalysts usually arrive as a news burst before they
arrive as a price bar."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models import NewsArticle

router = APIRouter(prefix="/news", tags=["news"])


def _rows(session: Session, since: datetime) -> list[NewsArticle]:
    return list(session.exec(select(NewsArticle)
                             .where(NewsArticle.published >= since.isoformat())
                             .order_by(NewsArticle.published.desc())).all())


@router.get("/pulse")
def pulse(session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    week = _rows(session, now - timedelta(days=7))
    day_iso = (now - timedelta(hours=24)).isoformat()
    per: dict[str, dict] = {}
    for a in week:
        for t in (a.tickers or "").split(","):
            if not t:
                continue
            d = per.setdefault(t.upper(), {"n_7d": 0, "n_24h": 0, "latest": []})
            d["n_7d"] += 1
            if a.published and a.published >= day_iso:
                d["n_24h"] += 1
            if len(d["latest"]) < 3:
                d["latest"].append({"ts": a.published, "title": a.title,
                                    "source": a.source, "url": a.url})
    for t, d in per.items():
        base = (d["n_7d"] - d["n_24h"]) / 6.0
        d["baseline_per_day"] = round(base, 2)
        d["velocity_x"] = round(d["n_24h"] / base, 1) if base > 0 else None
    movers = sorted((t for t in per if per[t]["n_24h"] >= 3),
                    key=lambda t: -(per[t]["velocity_x"] or 0))
    return {"asof": now.isoformat(), "tickers": per, "movers": movers[:10],
            "note": "DESCRIPTIVE context only - article velocity vs own 7d "
                    "baseline; feeds no score. Sourced from Tiingo news "
                    "(rate-budgeted, ~2h cadence)."}


@router.get("/{symbol}")
def ticker_news(symbol: str, limit: int = Query(20, le=50),
                session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    week = _rows(session, now - timedelta(days=14))
    sym = symbol.lower()
    items = [{"ts": a.published, "title": a.title, "source": a.source,
              "url": a.url, "description": a.description}
             for a in week if sym in (a.tickers or "").split(",")][:limit]
    return {"symbol": symbol.upper(), "items": items}
