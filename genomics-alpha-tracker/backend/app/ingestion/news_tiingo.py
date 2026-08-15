"""Tiingo news ingestion for the genomics universe — RATE-BUDGETED.

Casey's Tiingo plan is small: free tier is 50 req/hr / 1,000 req/day / 500
symbols/mo, and the News API itself requires the paid Power add-on (403 on
free) — so this module is built around the strictest budget and degrades
gracefully:
- ONE request per 50 tickers per run (comma-joined), default job cadence
  120 min => ~12-24 requests/day for the whole universe.
- Hard in-process daily cap (TIINGO_DAILY_CAP, default 100). At the cap the
  job logs and skips — stale news is never an error.
- No key, or a key without the news add-on (403): job logs once and returns
  0. Nothing downstream breaks; the router serves what's stored.
- Token scrubbed from any exception text before logging.

Biotech is catalyst-driven; articles land in their own table so the router
can serve per-ticker feeds and 24h-vs-7d velocity (DESCRIPTIVE context for
the catalysts panel — feeds no score; a news-based score would need its own
registered study first, per house rules).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlmodel import Session

from ..models import NewsArticle
from ..universe.manager import list_securities

logger = logging.getLogger(__name__)

_API = "https://api.tiingo.com/tiingo/news"
_CHUNK = 50
_BUDGET = {"day": None, "used": 0}


def _cap() -> int:
    return int(os.environ.get("TIINGO_DAILY_CAP", "100"))


def _redact(msg: str) -> str:
    return re.sub(r"(token=)[A-Za-z0-9]+", r"\1<redacted>", msg)


def _spend() -> bool:
    today = date.today().isoformat()
    if _BUDGET["day"] != today:
        _BUDGET["day"], _BUDGET["used"] = today, 0
    if _BUDGET["used"] >= _cap():
        return False
    _BUDGET["used"] += 1
    return True


def run_news(session: Session, symbols: list[str] | None = None) -> int:
    key = os.environ.get("TIINGO_API_KEY")
    if not key:
        logger.info("news_tiingo: TIINGO_API_KEY unset - skipping")
        return 0
    symbols = symbols or [s.symbol for s in list_securities(session,
                                                           include_inactive=False)]
    start = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    inserted = 0
    for i in range(0, len(symbols), _CHUNK):
        if not _spend():
            logger.warning("news_tiingo: daily cap %d reached - deferring rest",
                           _cap())
            break
        chunk = symbols[i:i + _CHUNK]
        try:
            r = httpx.get(_API, params={"token": key, "startDate": start,
                                        "limit": 500,
                                        "tickers": ",".join(t.lower() for t in chunk)},
                          timeout=30.0)
            if r.status_code == 403:
                logger.warning("news_tiingo: 403 - key has no News add-on "
                               "(paid Power feature); skipping until upgraded")
                return inserted
            r.raise_for_status()
            arts = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("news_tiingo chunk failed: %s", _redact(str(exc)))
            continue
        chunk_l = {t.lower() for t in chunk}
        for a in arts:
            aid = a.get("id")
            if aid is None or session.get(NewsArticle, aid) is not None:
                continue
            tickers = [t for t in (a.get("tickers") or []) if t in chunk_l]
            session.add(NewsArticle(
                id=aid,
                published=a.get("publishedDate"),
                title=(a.get("title") or "")[:500],
                source=(a.get("source") or "")[:100],
                url=(a.get("url") or "")[:500],
                tickers=",".join(tickers),
                description=(a.get("description") or "")[:500]))
            inserted += 1
        session.commit()
    return inserted
