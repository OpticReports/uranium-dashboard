"""Financial Modeling Prep provider (optional, requires FMP_API_KEY).

FMP is the best free-ish source for fundamentals, analyst estimates, and price
targets, so it's also used by the analyst ingestion module. Degrades gracefully
without a key.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from ...config import settings
from ...utils.ratelimit import RateLimiter, with_backoff
from .base import MarketProvider

logger = logging.getLogger(__name__)
_BASE = "https://financialmodelingprep.com/api/v3"


class FMPProvider(MarketProvider):
    name = "fmp"

    def __init__(self) -> None:
        self.key = settings.fmp_api_key
        self.enabled = bool(self.key)
        self._rl = RateLimiter(max_calls=250, period=60.0)  # free tier ~250/day; be gentle
        if not self.enabled:
            logger.warning("FMPProvider disabled: FMP_API_KEY unset")

    def _get(self, path: str, params: dict | None = None):
        self._rl.acquire()
        params = {**(params or {}), "apikey": self.key}
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
            data = self._get(f"/profile/{symbol.upper()}")
            if data and isinstance(data, list):
                return data[0].get("companyName") or symbol
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp validate(%s) failed: %s", symbol, exc)
        return None

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        if not self.enabled:
            return []
        data = self._get(
            f"/historical-price-full/{symbol.upper()}",
            {"from": start.isoformat(), "to": end.isoformat()},
        )
        out = []
        for bar in (data or {}).get("historical", []):
            out.append(
                {
                    "date": bar.get("date"),
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "adj_close": bar.get("adjClose"),
                    "volume": bar.get("volume"),
                }
            )
        return list(reversed(out))  # FMP returns newest-first

    def get_fundamentals(self, symbol: str) -> dict:
        out = {
            "market_cap": None, "cash": None, "quarterly_burn": None,
            "rd_spend": None, "runway_quarters": None, "short_interest_pct": None,
            "iv": None, "iv_skew": None,
        }
        if not self.enabled:
            return out
        try:
            profile = self._get(f"/profile/{symbol.upper()}")
            if profile:
                out["market_cap"] = profile[0].get("mktCap")
            cf = self._get(f"/cash-flow-statement/{symbol.upper()}", {"period": "quarter", "limit": 1})
            bs = self._get(f"/balance-sheet-statement/{symbol.upper()}", {"period": "quarter", "limit": 1})
            inc = self._get(f"/income-statement/{symbol.upper()}", {"period": "quarter", "limit": 1})
            if bs:
                out["cash"] = bs[0].get("cashAndShortTermInvestments")
            if cf:
                fcf = cf[0].get("freeCashFlow")
                if fcf is not None and fcf < 0:
                    out["quarterly_burn"] = -fcf
            if inc:
                out["rd_spend"] = inc[0].get("researchAndDevelopmentExpenses")
            if out["cash"] and out["quarterly_burn"] and out["quarterly_burn"] > 0:
                out["runway_quarters"] = out["cash"] / out["quarterly_burn"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp fundamentals(%s) failed: %s", symbol, exc)
        return out

    # --- analyst layer helpers (used by ingestion/analyst.py) ---
    def get_estimates(self, symbol: str) -> list[dict]:
        if not self.enabled:
            return []
        try:
            return self._get(f"/analyst-estimates/{symbol.upper()}", {"limit": 8}) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp estimates(%s) failed: %s", symbol, exc)
            return []

    def get_price_targets(self, symbol: str) -> list[dict]:
        if not self.enabled:
            return []
        try:
            return self._get(f"/price-target/{symbol.upper()}") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp price targets(%s) failed: %s", symbol, exc)
            return []
