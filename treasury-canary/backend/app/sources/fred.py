"""FRED source — the backbone. Cached, backed off, and gracefully degrading.

No key -> returns empty and logs (the dashboard shows those metrics STALE rather
than crashing). Observations are (date, value|None); FRED's "." missing marker
maps to None so gaps never masquerade as zero.
"""
from __future__ import annotations

import json
import logging
import os
import threading
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


# In-process cache of the assembled bundle. Every API endpoint calls fetch_bundle,
# and the browser fires several at once — without this, each request re-fetches ~25
# FRED series, a thundering herd that times out / OOMs a small (free-tier) instance.
# A lock serializes the cold fetch so concurrent callers share ONE network pass.
_BUNDLE_TTL_SECONDS = 6 * 3600  # data is EOD/daily; a few hours stale is fine
_bundle_cache: dict[str, object] = {"ts": 0.0, "data": None}
_bundle_lock = threading.Lock()


def fetch_bundle(start: str = "1976-01-01", force: bool = False
                 ) -> dict[str, tuple[list[date], list[float | None]]]:
    """Fetch the full FRED catalog into one logical-keyed bundle (memoized).

    Keys are provider-agnostic (tenor labels, "sofr", "hy_oas", ...). Missing key or
    failed series -> that entry is ([], []) and its metrics render STALE.
    """
    now = time.time()
    cached = _bundle_cache["data"]
    if not force and cached is not None and now - float(_bundle_cache["ts"]) < _BUNDLE_TTL_SECONDS:
        return cached  # type: ignore[return-value]
    with _bundle_lock:
        # double-check: another thread may have populated it while we waited
        now = time.time()
        cached = _bundle_cache["data"]
        if not force and cached is not None and now - float(_bundle_cache["ts"]) < _BUNDLE_TTL_SECONDS:
            return cached  # type: ignore[return-value]
        bundle = _fetch_bundle_uncached(start)
        _bundle_cache["data"] = bundle
        _bundle_cache["ts"] = time.time()
        return bundle


def _fetch_bundle_uncached(start: str) -> dict[str, tuple[list[date], list[float | None]]]:
    from concurrent.futures import ThreadPoolExecutor

    from ..config import (
        FRED_BREAKEVENS, FRED_CREDIT, FRED_FLOWS, FRED_FOREIGN, FRED_FUNDING,
        FRED_LABOR, FRED_LEADING, FRED_MACRO, FRED_PINS, FRED_REAL_YIELDS,
        FRED_TENORS, FRED_VOL,
    )
    # logical key -> FRED series id
    plan: dict[str, str] = dict(FRED_TENORS)
    for extra in (FRED_LABOR, FRED_FLOWS, FRED_LEADING, FRED_PINS, FRED_FOREIGN):
        for k, sid in extra.items():
            plan[k] = sid
    plan["real_10y"] = FRED_REAL_YIELDS["10y"]
    plan["breakeven_5y5y"] = FRED_BREAKEVENS["5y5y"]
    for k in ("sofr", "effr", "iorb"):
        plan[k] = FRED_FUNDING[k]
    plan["vix"] = FRED_VOL["vix"]
    plan["hy_oas"] = FRED_CREDIT["hy_oas"]
    plan["ig_oas"] = FRED_CREDIT["ig_oas"]
    plan["sp500"] = FRED_MACRO["sp500"]
    plan["nfci"] = FRED_MACRO["nfci"]
    plan["acm_tp10"] = FRED_MACRO["acm_tp10"]
    plan["recession"] = FRED_MACRO["recession"]

    # Fetch concurrently — ~25 sequential FRED calls would be slow on a cold
    # instance; the disk cache + this pool keep the cold path to a few seconds.
    def _one(item):
        key, sid = item
        return key, fetch_series(sid, start)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(_one, plan.items())
    bundle = {key: series for key, series in results}
    # Non-FRED series ride along in the same bundle (each gracefully []).
    from .fmp import fetch_gold
    from .ofr import fetch_fsi
    bundle["gold"] = fetch_gold()
    bundle["ofr_fsi"] = fetch_fsi()
    return bundle


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
