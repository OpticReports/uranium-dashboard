"""Deribit public API — BTC perpetual funding + open interest (real-time).

The crypto leg of the fast-leverage strip: perp funding flips negative and open
interest collapses within HOURS of a speculative flush — the fastest leverage
gauge that exists. Deribit because its public market-data endpoints serve US
IPs (Binance/Bybit return HTTP 451 from US hosting). Keyless.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_BASE = "https://www.deribit.com/api/v2/public"
_TTL_SECONDS = 30 * 60  # funding updates hourly; OI drifts continuously
_cache: dict[str, object] = {"ts": 0.0, "summary": None, "funding": None}


def fetch_btc_perp() -> dict | None:
    """Current BTC-PERPETUAL snapshot: mark price, open interest ($), funding.

    funding_8h is the raw 8-hour rate; funding_ann_pct annualizes it
    (x3 periods/day x365 x100). None on failure.
    """
    now = time.time()
    if _cache["summary"] is not None and now - float(_cache["ts"]) < _TTL_SECONDS:
        return _cache["summary"]  # type: ignore[return-value]
    try:
        r = httpx.get(f"{_BASE}/get_book_summary_by_instrument",
                      params={"instrument_name": "BTC-PERPETUAL"},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        row = r.json()["result"][0]
        f8 = float(row["funding_8h"])
        out = {
            "mark_price": float(row["mark_price"]),
            "oi_usd": float(row["open_interest"]),
            "funding_8h": f8,
            "funding_ann_pct": round(f8 * 3 * 365 * 100, 2),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deribit summary fetch failed: %s", exc)
        return _cache["summary"]  # type: ignore[return-value]  # stale > nothing
    _cache["summary"] = out
    _cache["ts"] = now
    return out


def fetch_funding_history(days: int = 30) -> tuple[list[date], list[float]]:
    """Daily-sampled annualized funding %, last `days` days (ascending).

    Deribit returns hourly points; we keep each day's LAST 8h reading so the
    series matches what a daily chart can show. Failure -> ([], []).
    """
    cached = _cache.get("funding")
    if cached is not None and time.time() - float(_cache["ts"]) < _TTL_SECONDS:
        return cached  # type: ignore[return-value]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        r = httpx.get(f"{_BASE}/get_funding_rate_history",
                      params={"instrument_name": "BTC-PERPETUAL",
                              "start_timestamp": int(start.timestamp() * 1000),
                              "end_timestamp": int(end.timestamp() * 1000)},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        pts = r.json().get("result", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deribit funding history fetch failed: %s", exc)
        return [], []
    by_day: dict[date, float] = {}
    for p in pts:  # ascending timestamps; later points overwrite -> day's last
        try:
            d = datetime.fromtimestamp(p["timestamp"] / 1000, tz=timezone.utc).date()
            by_day[d] = round(float(p["interest_8h"]) * 3 * 365 * 100, 2)
        except (KeyError, TypeError, ValueError):
            continue
    days_sorted = sorted(by_day)
    out = (days_sorted, [by_day[d] for d in days_sorted])
    _cache["funding"] = out
    return out
