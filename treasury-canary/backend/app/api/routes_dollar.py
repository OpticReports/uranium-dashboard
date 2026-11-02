"""GET /dollar-watch — the Dollar watch tab (studies/dollar-watch.md §5).

Descriptive only: no probabilities, warning colours or lamps. A cold build is
~20-30 s of keyless fetches (30 FRED series, the OFR FSI csv, Yahoo/FMP dailies,
five BIS SDMX files), so the payload is cached and warmed by the scheduler,
with the same stale-while-revalidate contract as /ai-debt: once any payload
exists a page view never pays for a build; an expired cache is served as-is
while ONE background thread rebuilds it; a build that raises keeps the last
good payload (or, cold, the all-null payload) and is retried after the
degraded TTL.
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, HTTPException

from ..metrics.dollar_watch import build_dollar_watch
from ..sources.dollar_data import fetch_all

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dollar-watch"])
_TTL = 6 * 3600
_TTL_DEGRADED = 30 * 60
_cache: dict = {"ts": 0.0, "data": None, "retry_after": 0.0}
_lock = threading.Lock()
_building = {"on": False}


def _ttl(data: dict | None) -> int:
    return _TTL if data and (data.get("status") or {}).get("overall") == "ok" else _TTL_DEGRADED


def _expired() -> bool:
    """Call under _lock."""
    return (time.time() - _cache["ts"] >= _ttl(_cache["data"])) and time.time() >= _cache["retry_after"]


def _rebuild() -> dict:
    try:
        data = build_dollar_watch(fetch_all())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Dollar-watch build failed: %s", exc)
        with _lock:
            prev = _cache["data"]
            _cache["retry_after"] = time.time() + _TTL_DEGRADED
        if prev is not None:              # serve the last good payload, but never as if it were fresh
            stale = dict(prev, build_error=f"{type(exc).__name__}: {str(exc)[:200]}",
                         status={**(prev.get("status") or {}), "overall": "stale"})
            with _lock:
                _cache["data"] = stale
            return stale
        try:
            data = build_dollar_watch({})     # every live block "error"; the frozen record still ships
        except Exception as exc2:  # noqa: BLE001
            logger.exception("Dollar-watch all-null build failed too: %s", exc2)
            raise HTTPException(status_code=503, detail="Dollar-watch payload unavailable; see server log") from exc2
        data["build_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    with _lock:
        _cache.update(ts=time.time(), data=data)
    return data


def _rebuild_in_background() -> None:
    try:
        _rebuild()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dollar-watch background rebuild failed: %s", exc)
    finally:
        with _lock:
            _building["on"] = False


def dollar_watch_payload(force: bool = False) -> dict:
    with _lock:
        cached = _cache["data"]
        if cached is not None and not force:
            if not _expired():
                return cached
            if not _building["on"]:
                _building["on"] = True
                threading.Thread(target=_rebuild_in_background, name="dollar-watch-rebuild", daemon=True).start()
            return cached
        wait = cached is None and not force and _building["on"]
        if not wait:
            _building["on"] = True
    if wait:
        while True:
            time.sleep(0.5)
            with _lock:
                if _cache["data"] is not None or not _building["on"]:
                    break
        with _lock:
            if _cache["data"] is not None:
                return _cache["data"]
            _building["on"] = True
    try:
        return _rebuild()
    finally:
        with _lock:
            _building["on"] = False


def warm_dollar_watch(force: bool = False) -> dict:
    """Scheduler entry point (main._start_scheduler): rebuild off the page path.
    It also appends any new live firing to the forward ledger the day it appears."""
    return dollar_watch_payload(force=force)


@router.get("/dollar-watch")
def dollar_watch():
    return dollar_watch_payload()
