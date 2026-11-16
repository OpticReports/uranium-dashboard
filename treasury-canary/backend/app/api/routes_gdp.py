"""GET /gdp-watch — the GDP tab (studies/gdp-watch.md): real GDP growth and growth per capita for the 20 largest
economies with current quarterly data, with the study's 4-quarter projection and its backtest record.

Same stale-while-revalidate contract as /dollar-watch: the payload is cached and warmed by the scheduler; once any
payload exists a page view never pays for a build; a build that raises keeps the last good payload (or, cold, the
payload built from the shipped snapshot) and is retried after the degraded TTL.
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, HTTPException

from ..metrics.gdp_watch import build_gdp_watch
from ..sources.gdp_data import fetch_all, load_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gdp-watch"])
_TTL, _TTL_DEGRADED = 12 * 3600, 30 * 60
_cache: dict = {"ts": 0.0, "data": None, "retry_after": 0.0}
_lock = threading.Lock()
_building = {"on": False}


def _ttl(data: dict | None) -> int:
    return _TTL if data and (data.get("status") or {}).get("overall") == "ok" else _TTL_DEGRADED


def _snapshot_inputs() -> dict:
    snap = load_snapshot()
    keys = ("yoy", "qoq", "pop", "ngdpd", "weo_growth")
    return {**{k: snap.get(k) or {} for k in keys}, "status": {k: "snapshot" if snap.get(k) else "error" for k in keys},
            "snapshot_as_of": snap.get("as_of")}


def _rebuild() -> dict:
    try:
        data = build_gdp_watch(fetch_all())
    except Exception as exc:  # noqa: BLE001
        logger.exception("GDP-watch build failed: %s", exc)
        with _lock:
            prev = _cache["data"]
            _cache["retry_after"] = time.time() + _TTL_DEGRADED
        if prev is not None:
            stale = dict(prev, build_error=f"{type(exc).__name__}: {str(exc)[:200]}",
                         status={**(prev.get("status") or {}), "overall": "stale"})
            with _lock:
                _cache["data"] = stale
            return stale
        try:
            data = build_gdp_watch(_snapshot_inputs())
        except Exception as exc2:  # noqa: BLE001
            logger.exception("GDP-watch snapshot build failed too: %s", exc2)
            raise HTTPException(status_code=503, detail="GDP-watch payload unavailable; see server log") from exc2
        data["build_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    with _lock:
        _cache.update(ts=time.time(), data=data)
    return data


def _rebuild_in_background() -> None:
    try:
        _rebuild()
    except Exception as exc:  # noqa: BLE001
        logger.warning("GDP-watch background rebuild failed: %s", exc)
    finally:
        with _lock:
            _building["on"] = False


def gdp_watch_payload(force: bool = False) -> dict:
    with _lock:
        cached = _cache["data"]
        if cached is not None and not force:
            expired = (time.time() - _cache["ts"] >= _ttl(cached)) and time.time() >= _cache["retry_after"]
            if expired and not _building["on"]:
                _building["on"] = True
                threading.Thread(target=_rebuild_in_background, name="gdp-watch-rebuild", daemon=True).start()
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


def warm_gdp_watch(force: bool = False) -> dict:
    """Scheduler entry point (main._start_scheduler): rebuild off the page path."""
    return gdp_watch_payload(force=force)


@router.get("/gdp-watch")
def gdp_watch():
    return gdp_watch_payload()
