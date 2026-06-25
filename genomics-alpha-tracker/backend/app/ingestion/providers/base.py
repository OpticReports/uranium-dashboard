"""Market-data provider abstraction.

yfinance is the free baseline. Polygon / FMP / Tiingo drop in by setting
MARKET_PROVIDER in .env (plus the matching key) — no code changes. Every method
returns plain dicts/lists so providers are interchangeable.

CRITICAL: providers return None for unavailable fields (e.g. options skew /
short interest on thin-float names) — they NEVER zero-fill. A zero is a real
observation; None means "no data".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date


class MarketProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def validate_symbol(self, symbol: str) -> str | None:
        """Return the company name if the symbol resolves, else None."""

    @abstractmethod
    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[dict]:
        """List of {date, open, high, low, close, adj_close, volume}."""

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict:
        """Dict with keys: market_cap, cash, quarterly_burn, rd_spend,
        runway_quarters, short_interest_pct, iv, iv_skew. Missing => None."""


def get_provider(name: str | None = None):
    """Factory: resolve the configured provider, falling back to yfinance."""
    from ...config import settings

    name = (name or settings.market_provider or "yfinance").lower()
    if name == "polygon":
        from .polygon_provider import PolygonProvider

        return PolygonProvider()
    if name == "fmp":
        from .fmp_provider import FMPProvider

        return FMPProvider()
    if name == "tiingo":
        from .tiingo_provider import TiingoProvider

        return TiingoProvider()
    from .yfinance_provider import YFinanceProvider

    return YFinanceProvider()
