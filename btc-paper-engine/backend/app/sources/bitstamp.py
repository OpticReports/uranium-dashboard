"""Bitstamp market data — keyless REST. Primary source (matches the research
dataset). All requests time-bounded; failures return empty and the engine's
staleness guard handles degradation.
"""
from __future__ import annotations

import logging
import time

import httpx

from ..engine.core import BAR_SECONDS, Bar

logger = logging.getLogger(__name__)
_OHLC = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
_TICKER = "https://www.bitstamp.net/api/v2/ticker/btcusd/"


def fetch_4h_bars(start_unix: int, timeout: float = 30.0) -> list[Bar]:
    """Ascending 4h bars from start_unix to now (paginated, 1000/page).
    Includes the still-forming bar — callers must filter on closed-ness."""
    out: dict[int, Bar] = {}
    cursor = start_unix
    try:
        with httpx.Client(timeout=timeout) as client:
            for _ in range(30):
                r = client.get(_OHLC, params={"step": BAR_SECONDS, "limit": 1000,
                                              "start": cursor})
                r.raise_for_status()
                data = r.json()["data"]["ohlc"]
                if not data:
                    break
                for c in data:
                    t = int(c["timestamp"])
                    out[t] = Bar(ts=t, open=float(c["open"]), high=float(c["high"]),
                                 low=float(c["low"]), close=float(c["close"]),
                                 volume=float(c["volume"]))
                last = int(data[-1]["timestamp"])
                if len(data) < 1000 or last <= cursor:
                    break
                cursor = last + BAR_SECONDS
                time.sleep(0.2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bitstamp OHLC fetch failed: %s", exc)
    return [out[t] for t in sorted(out)]


def last_price(timeout: float = 10.0) -> float | None:
    try:
        r = httpx.get(_TICKER, timeout=timeout)
        r.raise_for_status()
        return float(r.json()["last"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bitstamp ticker failed: %s", exc)
        return None


def kraken_price(timeout: float = 10.0) -> float | None:
    """Secondary-source sanity check (spec §1.7)."""
    try:
        r = httpx.get("https://api.kraken.com/0/public/Ticker",
                      params={"pair": "XBTUSD"}, timeout=timeout)
        r.raise_for_status()
        res = r.json()["result"]
        return float(next(iter(res.values()))["c"][0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Kraken ticker failed: %s", exc)
        return None
