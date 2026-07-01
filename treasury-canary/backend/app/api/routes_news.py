"""GET /news — tagged RSS feed (Fed / Treasury / markets)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..sources.news import fetch_news

router = APIRouter(tags=["news"])


@router.get("/news")
def news(limit: int = Query(40, le=100)):
    return {"items": fetch_news(limit)}
