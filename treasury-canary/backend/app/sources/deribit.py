"""Deribit public API — BTC perpetual funding + open interest (real-time).

The crypto leg of the fast-leverage strip: perp funding flips negative and open
interest collapses within HOURS of a speculative flush — the fastest leverage
gauge that exists. Deribit because its public market-data endpoints serve US
IPs (Binance/Bybit return HTTP 451 from US hosting). Keyless.

QA notes (adversarial review 2026-07): summary and funding history keep
SEPARATE cache timestamps — a shared ts let every summary refresh mark the
funding cache fresh, freezing the funding chart at process start. And the
funding-history endpoint caps ~744 hourly points (~31 days) per call no matter
the requested range, so long histories must be fetched in ≤30-day windows.
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
_scache: dict[str, object] = {"ts": 0.0, "data": None}   # summary
_fcache: dict[str, object] = {"ts": 0.0, "data": None}   # funding history


def fetch_btc_perp() -> dict | None:
    """Current BTC-PERPETUAL snapshot: mark price, open interest (USD — the
    instrument is inverse with $10 contracts; the API reports USD amounts),
    funding. funding_ann_pct = interest_8h x 3 x 365 x 100. None on failure."""
    now = time.time()
    if _scache["data"] is not None and now - float(_scache["ts"]) < _TTL_SECONDS:
        return _scache["data"]  # type: ignore[return-value]
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
        return _scache["data"]  # type: ignore[return-value]  # stale > nothing
    _scache["data"] = out
    _scache["ts"] = now
    return out


def fetch_funding_history(days: int = 180) -> tuple[list[date], list[float]]:
    """Daily-sampled annualized funding %, last `days` days (ascending).

    Fetched in 30-day windows (the endpoint caps ~744 hourly points/call).
    Each day keeps its LAST 8h reading. Partial failure keeps whatever windows
    succeeded; total failure -> stale cache, else ([], [])."""
    now = time.time()
    cached = _fcache["data"]
    if cached is not None and now - float(_fcache["ts"]) < _TTL_SECONDS:
        return cached  # type: ignore[return-value]
    end = datetime.now(timezone.utc)
    by_day: dict[date, float] = {}
    got_any = False
    win_end = end
    while (end - win_end).days < days:
        win_start = max(win_end - timedelta(days=30), end - timedelta(days=days))
        try:
            r = httpx.get(f"{_BASE}/get_funding_rate_history",
                          params={"instrument_name": "BTC-PERPETUAL",
                                  "start_timestamp": int(win_start.timestamp() * 1000),
                                  "end_timestamp": int(win_end.timestamp() * 1000)},
                          timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            pts = r.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deribit funding window %s failed: %s",
                           win_start.date(), exc)
            pts = []
        for p in pts:  # ascending; later points overwrite -> day's last
            try:
                d = datetime.fromtimestamp(p["timestamp"] / 1000, tz=timezone.utc).date()
                by_day[d] = round(float(p["interest_8h"]) * 3 * 365 * 100, 2)
            except (KeyError, TypeError, ValueError):
                continue
        got_any = got_any or bool(pts)
        if win_start <= end - timedelta(days=days):
            break
        win_end = win_start
    if not got_any:
        return cached if cached is not None else ([], [])  # type: ignore[return-value]
    days_sorted = sorted(by_day)
    out = (days_sorted, [by_day[d] for d in days_sorted])
    _fcache["data"] = out
    _fcache["ts"] = now
    return out
