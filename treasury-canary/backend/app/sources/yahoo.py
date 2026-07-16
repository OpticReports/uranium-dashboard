"""Yahoo chart API — monthly S&P 500 (^GSPC) history for drawdown ground truth.

Keyless. Monthly bars reach back to 1927; we keep closes AND monthly lows so
intra-month troughs (Oct-1987, Mar-2020) retain their real depth instead of
being smoothed away by close-to-close sampling. Gracefully returns ([], [], [])
on failure — drawdown markers simply vanish, nothing else degrades.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"

_TTL_OK = 6 * 3600
_TTL_FAIL = 600
_cache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_lock = threading.Lock()


def fetch_spx_monthly() -> tuple[list[date], list[float | None], list[float | None]]:
    """(dates, closes, lows) of monthly ^GSPC bars, oldest->newest."""
    now = time.time()
    ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
    if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
        return _cache["data"]  # type: ignore[return-value]
    with _lock:
        now = time.time()
        ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
        if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
            return _cache["data"]  # type: ignore[return-value]
        result: tuple[list[date], list[float | None], list[float | None]] = ([], [], [])
        ok = False
        try:
            r = httpx.get(_URL, params={"range": "max", "interval": "1mo"},
                          headers={"user-agent": "Mozilla/5.0 (canary-dashboard)"},
                          timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            quote = res["indicators"]["quote"][0]
            dates = [datetime.fromtimestamp(ts, tz=timezone.utc).date()
                     for ts in res.get("timestamp", [])]
            result = (dates, quote.get("close", []), quote.get("low", []))
            ok = True
            logger.info("Yahoo ^GSPC: %d monthly bars", len(dates))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Yahoo ^GSPC fetch failed: %s", exc)
        _cache["data"] = result
        _cache["ts"] = time.time()
        _cache["ok"] = ok
        return result
