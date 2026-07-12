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
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
_URL = "https://financialmodelingprep.com/stable/historical-price-eod/light"


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
