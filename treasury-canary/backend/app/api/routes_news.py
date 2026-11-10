"""GET /news — tagged RSS feed (Fed / Treasury: PRIMARY-source, keyless,
instant). GET /news/pulse — Tiingo market-news lane (ticker-tagged, themed,
velocity vs 30d baseline). The two lanes are complementary by design: RSS
owns official releases the second they post; Tiingo owns breadth, tickers,
and queryable history that RSS structurally cannot provide (feeds hold only
~50 items - no baseline is computable from them). Pulse is DESCRIPTIVE
context only (see sources/tiingo_news.py honesty contract)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..sources.news import fetch_news

router = APIRouter(tags=["news"])


@router.get("/news")
def news(limit: int = Query(40, le=100)):
    return {"items": fetch_news(limit)}


@router.get("/news/pulse")
def news_pulse():
    from ..sources.tiingo_news import news_pulse as pulse
    return pulse()
