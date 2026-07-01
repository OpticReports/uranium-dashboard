"""FRED source — the backbone. Cached, backed off, and gracefully degrading.

No key -> returns empty and logs (the dashboard shows those metrics STALE rather
than crashing). Observations are (date, value|None); FRED's "." missing marker
maps to None so gaps never masquerade as zero.
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
_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _cache_path(series_id: str, start: str) -> str:
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"fred_{series_id}_{start}.json")


def _get_with_backoff(params: dict, tries: int = 4) -> dict | None:
    delay = 1.0
    for attempt in range(tries):
        try:
            r = httpx.get(_BASE, params=params, timeout=settings.http_timeout_seconds)
            if r.status_code == 400:
                logger.warning("FRED 400 for %s (series may not exist): %s",
                               params.get("series_id"), r.text[:160])
                return None
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            if attempt == tries - 1:
                logger.warning("FRED fetch failed for %s: %s", params.get("series_id"), exc)
                return None
            time.sleep(delay)
            delay *= 2
    return None


def fetch_series(
    series_id: str, start: str = "1976-01-01", use_cache: bool = True
) -> tuple[list[date], list[float | None]]:
    """Return (dates, values) for a FRED series. Empty on missing key/failure."""
    if not settings.fred_api_key:
        logger.info("FRED_API_KEY not set — skipping %s (metric will show STALE)", series_id)
        return [], []

    cache = _cache_path(series_id, start)
    if use_cache and os.path.exists(cache):
        age = time.time() - os.path.getmtime(cache)
        if age < settings.cache_ttl_seconds:
            try:
                raw = json.load(open(cache))
                return _parse(raw)
            except Exception:  # noqa: BLE001
                pass

    data = _get_with_backoff({
        "series_id": series_id, "api_key": settings.fred_api_key,
        "file_type": "json", "observation_start": start,
    })
    if data is None:
        return [], []
    try:
        json.dump(data, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(data)


def _parse(data: dict) -> tuple[list[date], list[float | None]]:
    dates: list[date] = []
    vals: list[float | None] = []
    for obs in data.get("observations", []):
        try:
            d = datetime.strptime(obs["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        raw = obs.get("value", ".")
        try:
            v = None if raw in (".", "", None) else float(raw)
        except ValueError:
            v = None
        dates.append(d)
        vals.append(v)
    return dates, vals


def recession_start_dates(dates: list[date], usrec: list[float | None]) -> list[date]:
    """First day of each USREC==1 run (NBER recession onsets) for chart annotation."""
    starts: list[date] = []
    prev = 0.0
    for d, v in zip(dates, usrec):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            starts.append(d)
        prev = cur
    return starts
