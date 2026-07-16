"""Yahoo chart API — S&P 500 (^GSPC) history for drawdown ground truth.

CAUTION (found in QA): requesting interval=1mo with range=max makes Yahoo
silently degrade to QUARTERLY bars (dataGranularity "3mo") — month-precision
claims built on those are wrong by up to a quarter. So we fetch DAILY bars
(~14k, 1970+) and downsample to true monthly bars ourselves: close = last
daily close of the month, low = min daily low — so intra-month troughs
(Oct-1987, Mar-2020) retain their real depth. Gracefully returns ([], [], [])
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

_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
        "?period1=0&period2=4102444800&interval=1d")

_TTL_OK = 6 * 3600
_TTL_FAIL = 600
_cache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_lock = threading.Lock()


def _downsample_monthly(dates: list[date], closes: list[float | None],
                        lows: list[float | None]
                        ) -> tuple[list[date], list[float | None], list[float | None]]:
    """True monthly bars from dailies: last close + min low per month."""
    out: dict[tuple[int, int], list] = {}
    for d, c, l in zip(dates, closes, lows):
        if c is None:
            continue
        k = (d.year, d.month)
        low = l if l is not None else c
        if k not in out:
            out[k] = [d, c, low]
        else:
            out[k][0], out[k][1] = d, c          # last obs of the month wins
            out[k][2] = min(out[k][2], low)
    keys = sorted(out)
    return ([date(y, m, 1) for y, m in keys],
            [out[k][1] for k in keys],
            [out[k][2] for k in keys])


def fetch_spx_monthly() -> tuple[list[date], list[float | None], list[float | None]]:
    """(dates, closes, lows) of TRUE monthly ^GSPC bars, oldest->newest,
    downsampled from daily data (see module docstring for why)."""
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
            r = httpx.get(_URL,
                          headers={"user-agent": "Mozilla/5.0 (canary-dashboard)"},
                          timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            gran = res.get("meta", {}).get("dataGranularity")
            quote = res["indicators"]["quote"][0]
            dates = [datetime.fromtimestamp(ts, tz=timezone.utc).date()
                     for ts in res.get("timestamp", [])]
            if gran != "1d":
                raise ValueError(f"expected daily bars, got granularity {gran!r}")
            result = _downsample_monthly(dates, quote.get("close", []),
                                         quote.get("low", []))
            ok = True
            logger.info("Yahoo ^GSPC: %d daily bars -> %d monthly", len(dates),
                        len(result[0]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Yahoo ^GSPC fetch failed: %s", exc)
        _cache["data"] = result
        _cache["ts"] = time.time()
        _cache["ok"] = ok
        return result
