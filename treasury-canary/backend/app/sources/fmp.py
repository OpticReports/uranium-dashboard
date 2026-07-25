"""Optional FMP source — gold daily closes (GLD ETF proxy) for the flow compass.

FRED's LBMA gold series were discontinued, so gold needs FMP's /stable API (the
same endpoint family the genomics app uses). No key -> ([], []) and the gold tile
shows STALE; everything else still works.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
_URL = "https://financialmodelingprep.com/stable/historical-price-eod/light"
_SPX_TTL_SECONDS = 24 * 3600  # long history barely changes; one refresh/day


def fetch_gold(symbol: str = "GLD") -> tuple[list[date], list[float | None]]:
    if not settings.fmp_api_key:
        logger.info("FMP_API_KEY not set — gold unavailable (flow tile shows STALE)")
        return [], []
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, f"fmp_gold_{symbol}.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < settings.cache_ttl_seconds:
        try:
            return _parse(json.load(open(cache)))
        except Exception:  # noqa: BLE001
            pass
    try:
        r = httpx.get(_URL, params={"symbol": symbol, "apikey": settings.fmp_api_key},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP gold fetch failed: %s", exc)
        return [], []
    try:
        json.dump(data, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(data)


def fetch_spx_long(symbol: str = "^GSPC") -> tuple[list[date], list[float | None]]:
    """Daily S&P index closes back to ~1951 for the leverage chart's long view.

    FMP caps each call at 5,000 rows (most recent first within the window), so
    paginate BACKWARDS: each pass re-requests with `to` = day before the
    earliest row seen. No key -> ([], []) and the caller falls back to FRED's
    ~10y SP500 series; on fetch failure a stale cache is preferred to nothing.
    """
    if not settings.fmp_api_key:
        return [], []
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, "fmp_spx_long.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < _SPX_TTL_SECONDS:
        try:
            return _parse(json.load(open(cache)))
        except Exception:  # noqa: BLE001
            pass
    rows: list = []
    to: str | None = None
    try:
        for _ in range(12):  # 12 x 5000 rows ≈ 230y of trading days — plenty
            params = {"symbol": symbol, "from": "1900-01-01",
                      "apikey": settings.fmp_api_key}
            if to:
                params["to"] = to
            r = httpx.get(_URL, params=params, timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            chunk = r.json()
            if not isinstance(chunk, list) or not chunk:
                break
            rows.extend(chunk)
            earliest = min(str(c.get("date"))[:10] for c in chunk)
            if len(chunk) < 5000:
                break
            to = (datetime.strptime(earliest, "%Y-%m-%d").date()
                  - timedelta(days=1)).isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP long S&P fetch failed: %s%s", exc,
                       " (using stale cache)" if os.path.exists(cache) else "")
        if os.path.exists(cache):
            try:
                return _parse(json.load(open(cache)))
            except Exception:  # noqa: BLE001
                pass
        return [], []
    try:
        json.dump(rows, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(rows)


def _parse(data) -> tuple[list[date], list[float | None]]:
    if not isinstance(data, list):
        return [], []
    rows = []
    for d in data:
        ds = str(d.get("date") or "")[:10]
        px = d.get("price", d.get("close"))
        try:
            rows.append((datetime.strptime(ds, "%Y-%m-%d").date(),
                         float(px) if px is not None else None))
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r[0])
    return [r[0] for r in rows], [r[1] for r in rows]
