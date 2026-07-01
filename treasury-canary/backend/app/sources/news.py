"""News — keyless RSS aggregation (Fed, Treasury, markets). Tagged, newest first.

Graceful: a feed that fails is skipped. No third-party RSS lib — stdlib XML parse.
"""
from __future__ import annotations

import logging
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx
from dateutil import parser as dtparser

from ..config import settings

logger = logging.getLogger(__name__)

FEEDS: list[tuple[str, str]] = [
    ("FED", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("FED", "https://www.federalreserve.gov/feeds/speeches.xml"),
    ("TREASURY", "https://home.treasury.gov/rss/press.xml"),
]

_DATA_WORDS = ("cpi", "pce", "payroll", "employment", "gdp", "jobless", "ism", "retail sales")
_AUCTION_WORDS = ("auction", "bill", "note", "bond", "tips", "buyback")
_GEO_WORDS = ("sanction", "tariff", "war", "geopolit")


def _tag(source: str, title: str) -> str:
    t = title.lower()
    if any(w in t for w in _AUCTION_WORDS):
        return "AUCTION"
    if any(w in t for w in _DATA_WORDS):
        return "DATA"
    if any(w in t for w in _GEO_WORDS):
        return "GEO"
    if source in ("FED", "TREASURY"):
        return "FED"
    return "OTHER"


def _parse_feed(source: str, xml: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        try:
            ts = dtparser.parse(pub) if pub else None
        except (ValueError, OverflowError):
            ts = None
        out.append({
            "source": source, "title": title, "link": link,
            "published": ts.isoformat() if ts else None,
            "tag": _tag(source, title),
        })
    return out


def fetch_news(limit: int = 40) -> list[dict]:
    items: list[dict] = []
    for source, url in FEEDS:
        try:
            r = httpx.get(url, timeout=settings.http_timeout_seconds,
                          headers={"User-Agent": "treasury-canary/0.1"})
            r.raise_for_status()
            items.extend(_parse_feed(source, r.text))
        except Exception as exc:  # noqa: BLE001
            logger.info("News feed skipped (%s): %s", url, exc)
    items.sort(key=lambda x: x["published"] or "", reverse=True)
    return items[:limit]
