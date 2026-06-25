"""Tiingo provider (optional, requires TIINGO_API_KEY). EOD prices + metadata."""
from __future__ import annotations

import logging
from datetime import date

import httpx

from ...config import settings
from ...utils.ratelimit import RateLimiter, with_backoff
from .base import MarketProvider

logger = logging.getLogger(__name__)
_BASE = "https://api.tiingo.com"


class TiingoProvider(MarketProvider):
    name = "tiingo"

    def __init__(self) -> None:
        self.key = settings.tiingo_api_key
        self.enabled = bool(self.key)
        self._rl = RateLimiter(max_calls=50, period=3600.0)  # free tier hourly cap
        if not self.enabled:
            logger.warning("TiingoProvider disabled: TIINGO_API_KEY unset")

    def _get(self, path: str, params: dict | None = None):
        self._rl.acquire()
        headers = {"Content-Type": "application/json"}
        params = {**(params or {}), "token": self.key}
        resp = with_backoff(
            lambda: httpx.get(
                f"{_BASE}{path}", params=params, headers=headers,
                timeout=settings.http_timeout_seconds,
            )
        )
        resp.raise_for_status()
        return resp.json()

    def validate_symbol(self, symbol: str) -> str | None:
        if not self.enabled:
            return None
        try:
            data = self._get(f"/tiingo/daily/{symbol.lower()}")
            return data.get("name") or symbol
        except Exception as exc:  # noqa: BLE001
            logger.warning("tiingo validate(%s) failed: %s", symbol, exc)
            return None

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        if not self.enabled:
            return []
        data = self._get(
            f"/tiingo/daily/{symbol.lower()}/prices",
            {"startDate": start.isoformat(), "endDate": end.isoformat()},
        )
        out = []
        for bar in data or []:
            out.append(
                {
                    "date": (bar.get("date") or "")[:10],
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "adj_close": bar.get("adjClose"),
                    "volume": bar.get("volume"),
                }
            )
        return out

    def get_fundamentals(self, symbol: str) -> dict:
        # Tiingo fundamentals require an add-on; return explicit None fields.
        return {
            "market_cap": None, "cash": None, "quarterly_burn": None,
            "rd_spend": None, "runway_quarters": None, "short_interest_pct": None,
            "iv": None, "iv_skew": None,
        }
