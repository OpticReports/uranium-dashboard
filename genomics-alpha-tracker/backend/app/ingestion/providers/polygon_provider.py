"""Polygon.io provider (optional, requires POLYGON_API_KEY).

Drops in via MARKET_PROVIDER=polygon. Without the key it degrades gracefully:
validate returns None and data calls return empty, with a logged warning.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from ...config import settings
from ...utils.ratelimit import RateLimiter, with_backoff
from .base import MarketProvider

logger = logging.getLogger(__name__)
_BASE = "https://api.polygon.io"


class PolygonProvider(MarketProvider):
    name = "polygon"

    def __init__(self) -> None:
        self.key = settings.polygon_api_key
        self.enabled = bool(self.key)
        # Free tier: 5 requests/minute.
        self._rl = RateLimiter(max_calls=5, period=60.0)
        if not self.enabled:
            logger.warning("PolygonProvider disabled: POLYGON_API_KEY unset")

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._rl.acquire()
        params = {**(params or {}), "apiKey": self.key}
        resp = with_backoff(
            lambda: httpx.get(
                f"{_BASE}{path}", params=params, timeout=settings.http_timeout_seconds
            )
        )
        resp.raise_for_status()
        return resp.json()

    def validate_symbol(self, symbol: str) -> str | None:
        if not self.enabled:
            return None
        try:
            data = self._get(f"/v3/reference/tickers/{symbol.upper()}")
            return data.get("results", {}).get("name") or symbol
        except Exception as exc:  # noqa: BLE001
            logger.warning("polygon validate(%s) failed: %s", symbol, exc)
            return None

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        if not self.enabled:
            return []
        path = f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        data = self._get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
        out = []
        for bar in data.get("results", []) or []:
            d = date.fromtimestamp(bar["t"] / 1000).isoformat()
            out.append(
                {
                    "date": d,
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "adj_close": bar.get("c"),
                    "volume": bar.get("v"),
                }
            )
        return out

    def get_fundamentals(self, symbol: str) -> dict:
        # Polygon's fundamentals endpoint is limited on free tier; return the
        # market cap snapshot and leave the rest as explicit None (no data).
        empty = {
            "market_cap": None, "cash": None, "quarterly_burn": None,
            "rd_spend": None, "runway_quarters": None, "short_interest_pct": None,
            "iv": None, "iv_skew": None,
        }
        if not self.enabled:
            return empty
        try:
            data = self._get(f"/v3/reference/tickers/{symbol.upper()}")
            res = data.get("results", {})
            empty["market_cap"] = res.get("market_cap")
        except Exception as exc:  # noqa: BLE001
            logger.warning("polygon fundamentals(%s) failed: %s", symbol, exc)
        return empty
