"""Financial Modeling Prep provider — FMP "stable" API.

FMP retired the legacy /api/v3/ endpoints for subscriptions created after
2025-08-31 (they 403 with a "Legacy Endpoint" message). This provider targets
the current /stable/ API. It powers market data AND the analyst layer
(estimates / price targets). Degrades gracefully without a key.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from ...config import settings
from ...utils.ratelimit import RateLimiter, with_backoff
from .base import MarketProvider

logger = logging.getLogger(__name__)
_BASE = "https://financialmodelingprep.com/stable"


class FMPProvider(MarketProvider):
    name = "fmp"

    def __init__(self) -> None:
        self.key = settings.fmp_api_key
        self.enabled = bool(self.key)
        self._rl = RateLimiter(max_calls=600, period=60.0)  # well under paid limits
        if not self.enabled:
            logger.warning("FMPProvider disabled: FMP_API_KEY unset")

    def _get(self, path: str, params: dict | None = None):
        self._rl.acquire()
        params = {**(params or {}), "apikey": self.key}
        resp = with_backoff(
            lambda: httpx.get(f"{_BASE}{path}", params=params, timeout=settings.http_timeout_seconds)
        )
        resp.raise_for_status()
        return resp.json()

    def validate_symbol(self, symbol: str) -> str | None:
        if not self.enabled:
            return None
        try:
            data = self._get("/profile", {"symbol": symbol.upper()})
            if data and isinstance(data, list):
                return data[0].get("companyName") or symbol
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp validate(%s) failed: %s", symbol, exc)
        return None

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        if not self.enabled:
            return []
        data = self._get(
            "/historical-price-eod/full",
            {"symbol": symbol.upper(), "from": start.isoformat(), "to": end.isoformat()},
        )
        out = []
        for bar in data or []:
            out.append({
                "date": bar.get("date"),
                "open": bar.get("open"), "high": bar.get("high"), "low": bar.get("low"),
                "close": bar.get("close"), "adj_close": bar.get("close"),  # stable EOD is adjusted
                "volume": bar.get("volume"),
            })
        return list(reversed(out))  # stable returns newest-first

    def get_fundamentals(self, symbol: str) -> dict:
        out = {
            "market_cap": None, "cash": None, "quarterly_burn": None,
            "rd_spend": None, "runway_quarters": None, "short_interest_pct": None,
            "iv": None, "iv_skew": None,
        }
        if not self.enabled:
            return out
        sym = symbol.upper()
        try:
            profile = self._get("/profile", {"symbol": sym})
            if profile:
                out["market_cap"] = profile[0].get("marketCap")
            bs = self._get("/balance-sheet-statement", {"symbol": sym, "period": "quarter", "limit": 1})
            cf = self._get("/cash-flow-statement", {"symbol": sym, "period": "quarter", "limit": 1})
            inc = self._get("/income-statement", {"symbol": sym, "period": "quarter", "limit": 1})
            if bs:
                out["cash"] = bs[0].get("cashAndShortTermInvestments") or bs[0].get("cashAndCashEquivalents")
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
            return self._get("/analyst-estimates",
                             {"symbol": symbol.upper(), "period": "annual", "limit": 8}) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp estimates(%s) failed: %s", symbol, exc)
            return []

    def get_price_targets(self, symbol: str) -> list[dict]:
        if not self.enabled:
            return []
        try:
            return self._get("/price-target-news", {"symbol": symbol.upper(), "limit": 50}) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("fmp price targets(%s) failed: %s", symbol, exc)
            return []
