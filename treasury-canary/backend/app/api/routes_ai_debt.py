"""GET /ai-debt — the AI-debt tab (studies/ai_debt_flows/BUILD.md phase 1).

Issuance tally and EDGAR filings, Z.1 holders, TIC foreign bid, Japan, public
funds and pensions, crowding gauges and breaking indicators, all from free
keyless sources. Context only: nothing here alerts, status language is "watch".

A cold build is ~45-70 s of fetches (TIC 60 FRED series, Z.1 47, the CSLT zip,
24 EDGAR CIKs, the ACM workbook), so the payload is built in process, cached
6 h and warmed by the scheduler like the severity history. Once any payload
exists a page view NEVER pays for a build: an expired cache is served as-is
(its `generated` stamp and status pills say how old / degraded it is) while
ONE background thread rebuilds it (stale-while-revalidate). A build in which
some block failed is kept for a shorter spell so a transient outage is
retried without hammering the sources. Only a cold start — or the scheduler's
forced warm — builds synchronously. A build that raises keeps the last good
payload (or, cold, the all-null payload) and is retried after the degraded
TTL instead of 500-ing on every request and re-running the fetches each time.
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, HTTPException

from ..metrics.ai_debt import build_ai_debt, fetch_inputs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-debt"])
_TTL = 6 * 3600
_TTL_DEGRADED = 30 * 60       # any block stale/error: retry sooner, but not per request
_cache: dict = {"ts": 0.0, "data": None, "retry_after": 0.0}
_lock = threading.Lock()      # guards _cache and _building
_building = {"on": False}


def _ttl(data: dict | None) -> int:
    return _TTL if data and (data.get("status") or {}).get("overall") == "ok" else _TTL_DEGRADED


def _expired() -> bool:
    """Call under _lock."""
    return (time.time() - _cache["ts"] >= _ttl(_cache["data"])) and time.time() >= _cache["retry_after"]


def _rebuild() -> dict:
    """Fetch + assemble, then publish to the cache. A build that raises keeps the
    last good payload (or installs the all-null payload on a cold start) and
    schedules the next attempt after the degraded TTL."""
    try:
        data = build_ai_debt(fetch_inputs())
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI-debt build failed: %s", exc)
        with _lock:
            prev = _cache["data"]
            _cache["retry_after"] = time.time() + _TTL_DEGRADED
        if prev is not None:
            return prev
        try:
            data = build_ai_debt({})      # every block "error", frozen pieces still ship (proven offline)
        except Exception as exc2:  # noqa: BLE001
            logger.exception("AI-debt all-null build failed too: %s", exc2)
            raise HTTPException(status_code=503, detail="AI-debt payload unavailable; see server log") from exc2
        data["build_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    with _lock:
        _cache.update(ts=time.time(), data=data)
    return data


def _rebuild_in_background() -> None:
    try:
        _rebuild()
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI-debt background rebuild failed: %s", exc)
    finally:
        with _lock:
            _building["on"] = False


def ai_debt_payload(force: bool = False) -> dict:
    with _lock:
        cached = _cache["data"]
        if cached is not None and not force:
            if not _expired():
                return cached
            if not _building["on"]:
                _building["on"] = True
                threading.Thread(target=_rebuild_in_background, name="ai-debt-rebuild", daemon=True).start()
            return cached                 # stale-while-revalidate: never build on a page view once warm
        wait = cached is None and not force and _building["on"]
        if not wait:
            _building["on"] = True
    if wait:                              # cold, but a rebuild is already running: wait for it, do not start a second
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
        return _rebuild()                 # cold start, or the scheduler's forced warm
    finally:
        with _lock:
            _building["on"] = False


def warm_ai_debt(force: bool = False) -> dict:
    """Scheduler entry point (main._start_scheduler): rebuild off the page path."""
    return ai_debt_payload(force=force)


@router.get("/ai-debt")
def ai_debt():
    return ai_debt_payload()
