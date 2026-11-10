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


# ~10s to rebuild 480 months (longer on a small instance); inputs are
# monthly/quarterly, so cache 12h, warm it from the scheduler, and never cache
# a payload built while any input failed to fetch.
_HIST: dict = {"ts": 0.0, "data": None}
_HIST_LOCK = threading.Lock()
_HIST_TTL = 12 * 3600


def _complete(bundle: dict) -> bool:
    from ..metrics.severity_history import LAGS
    return all(bundle.get(k, ([], []))[0] for k in LAGS)


def warm_history(force: bool = False) -> dict:
    from datetime import date

    from ..metrics.severity_history import history_payload
    with _HIST_LOCK:
        if force or _HIST["data"] is None or time.time() - _HIST["ts"] > _HIST_TTL:
            bundle = fetch_bundle()
            data = history_payload(bundle, end=date.today())
            if not _complete(bundle):
                return data                      # serve, don't cache a degraded build
            _HIST["data"], _HIST["ts"] = data, time.time()
        return _HIST["data"]


@router.get("/severity/history")
def severity_history():
    return warm_history()
