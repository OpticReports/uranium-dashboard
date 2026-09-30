"""GET /severity — the recession severity index (gun-size gauge)."""
from __future__ import annotations

from fastapi import APIRouter

import threading
import time

from ..metrics.severity import build_severity
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["severity"])


@router.get("/severity")
def severity():
    return build_severity(fetch_bundle())


# ~10s to rebuild 480 months; inputs are monthly/quarterly, so cache 12h.
_HIST: dict = {"ts": 0.0, "data": None}
_HIST_LOCK = threading.Lock()
_HIST_TTL = 12 * 3600


@router.get("/severity/history")
def severity_history():
    from ..metrics.severity_history import history_payload
    with _HIST_LOCK:
        if _HIST["data"] is None or time.time() - _HIST["ts"] > _HIST_TTL:
            _HIST["data"] = history_payload(fetch_bundle())
            _HIST["ts"] = time.time()
        return _HIST["data"]
