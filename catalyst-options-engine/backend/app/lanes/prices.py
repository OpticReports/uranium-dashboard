"""Daily price lane: stockanalysis.com history API (keyless, browser UA).

GET https://stockanalysis.com/api/symbol/s/<TICKER>/history?range=2Y&period=Daily
-> {"status": 200, "data": [{t,o,h,l,c,a,v,ch}, ...]}  (NEWEST FIRST; 'a' is
the adjusted close). Normalized here to oldest-first bars.

Lane-dark behavior: any failure logs a warning and returns [] — signals that
need prices come back None and the setup carries prices_dark=True.
"""
from __future__ import annotations

import logging

import httpx

from ..config import BROWSER_UA, settings
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_BASE = "https://stockanalysis.com/api/symbol/s/{symbol}/history"
_HEADERS = {"User-Agent": BROWSER_UA, "Accept": "application/json"}


def fetch_history(symbol: str, range_: str = "1Y", ttl: int = 6 * 3600) -> list[dict]:
    """Oldest-first daily bars: [{date, open, high, low, close, adj_close,
    volume}]. [] when the lane is dark."""
    key = f"prices:{symbol}:{range_}"

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _BASE.format(symbol=symbol.upper()),
            params={"range": range_, "period": "Daily"},
            headers=_HEADERS, timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(key, _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("price lane DARK for %s: %s", symbol, exc)
        return []
    return parse_history(payload)


def parse_history(payload: dict) -> list[dict]:
    """Normalize the raw payload; tolerant of the data being a list or nested."""
    data = (payload or {}).get("data")
    if isinstance(data, dict):  # some responses nest as {"data": {"data": [...]}}
        data = data.get("data")
    if not isinstance(data, list):
        return []
    bars = []
    for row in data:
        try:
            bars.append({
                "date": row["t"],
                "open": row.get("o"), "high": row.get("h"), "low": row.get("l"),
                "close": row.get("c"), "adj_close": row.get("a", row.get("c")),
                "volume": row.get("v"),
            })
        except (KeyError, TypeError):
            continue
    bars.sort(key=lambda b: b["date"])  # newest-first upstream -> oldest-first
    return bars


def adj_closes(bars: list[dict]) -> list[float]:
    return [b["adj_close"] for b in bars if b.get("adj_close") is not None]


def last_close(bars: list[dict]) -> float | None:
    closes = adj_closes(bars)
    return closes[-1] if closes else None
