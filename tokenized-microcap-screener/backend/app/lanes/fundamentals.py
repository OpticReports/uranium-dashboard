"""Optional market-cap / float enrichment via FMP (financialmodelingprep).

This is the ONE credentialed lane, and it is optional on purpose: without a key
the screener still runs and simply proxies company size by price and volume,
saying so on the dashboard. With a key, pumpability gets the input that matters
most for this pattern — Farmmi's entire market cap was $5.75M on the day the
JINQIAN token pooled against it carried a $5.9M fully-diluted value, i.e. the
memecoin was notionally worth more than the company it was named after.

Endpoint: GET /stable/profile?symbol=<T>&apikey=... . The pre-2025 /api/v3/
routes are legacy and refuse newer keys, so only /stable is used here.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_PROFILE = "https://financialmodelingprep.com/stable/profile"


def enabled() -> bool:
    return bool(settings.fmp_api_key)


def profile(symbol: str, ttl: int = 12 * 3600) -> dict:
    """{market_cap, avg_volume, company, exchange, industry}. {} when dark or
    when no key is configured — never raises, never blocks a scan."""
    if not enabled():
        return {}

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _PROFILE, params={"symbol": symbol.upper(),
                              "apikey": settings.fmp_api_key},
            timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(f"fmp:profile:{symbol.upper()}", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP profile lane DARK for %s: %s", symbol, exc)
        return {}
    return parse_profile(payload)


def parse_profile(payload) -> dict:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        return {}
    row = payload[0]
    if not isinstance(row, dict):
        return {}
    return {
        "market_cap": row.get("marketCap"),
        "avg_volume": row.get("averageVolume"),
        "company": row.get("companyName") or "",
        "exchange": row.get("exchange") or "",
        "industry": row.get("industry") or "",
    }
