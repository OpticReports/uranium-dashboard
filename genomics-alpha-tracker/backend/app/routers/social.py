"""Social / hype diagnostics — verify which feeds are live (keys never echoed)."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..ingestion.social import SocialIngestion, _apewisdom_snapshot
from ..models import SocialMention

router = APIRouter(prefix="/social", tags=["social"])


def _sample(items: list[dict], n: int = 3) -> list[dict]:
    return [{"date": it.get("date"), "text": (it.get("text") or "")[:120]} for it in items[:n]]


@router.get("/diag")
def diagnose(
    symbol: str = Query("NVDA", description="Ticker to test-pull (a liquid name shows the most)"),
    session: Session = Depends(get_session),
):
    """Live diagnostics: makes one real pull per configured social source for `symbol`
    and reports counts + a small sample, plus stored-row counts per platform. Use to
    tell "key invalid" from "no chatter" from "ingestion not running".
    Auth-gated (not /health) and keys are never echoed — only their presence/status.
    """
    sym = symbol.upper()
    src = SocialIngestion()

    # Which X route is active, and a live pull.
    x_route = ("official" if settings.x_bearer_token
               else "twitterapi.io" if settings.twitterapi_io_key else None)
    x_items = src._x_source(sym) if x_route else []

    ape_snapshot = _apewisdom_snapshot()
    ape_items = src._apewisdom(sym) if settings.apewisdom_enabled else []
    st_items = src._stocktwits(sym) if settings.stocktwits_enabled else []
    fmp_items = (src._fmp_social(sym)
                 if (settings.fmp_social_enabled and settings.fmp_api_key) else [])

    sources = {
        "x": {
            "route": x_route,
            "key_present": bool(settings.x_bearer_token or settings.twitterapi_io_key),
            "live_posts": len(x_items),
            "max_posts_cap": settings.twitterapi_io_max_posts,
            "lookback_days": settings.twitterapi_io_lookback_days,
            "sample": _sample(x_items),
        },
        "apewisdom": {
            "enabled": settings.apewisdom_enabled,
            "snapshot_tickers": len(ape_snapshot),
            "symbol_in_snapshot": sym in ape_snapshot,
            "records": ape_items,
        },
        "stocktwits": {"enabled": settings.stocktwits_enabled, "live_msgs": len(st_items)},
        "fmp_social": {
            "enabled": bool(settings.fmp_social_enabled and settings.fmp_api_key),
            "live_records": len(fmp_items),
        },
    }

    rows = session.exec(select(SocialMention)).all()
    by_platform = Counter(r.platform for r in rows)
    stored = {
        "total_rows": len(rows),
        "by_platform": dict(by_platform),
        "latest_date": max((r.date.isoformat() for r in rows), default=None),
    }
    return {"symbol": sym, "sources": sources, "stored": stored}
