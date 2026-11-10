"""GET /distress — the Distress panel (studies/distress-signals.md).

National bankruptcy filings, bank loan stress and the state map, each with
its measured role. Display only: no series passed the pre-registered test as
a recession warning, so nothing here raises an alert.
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter

from ..metrics.distress import bank_from_bundle, build_distress, qidx
from ..sources.fred import fetch_bundle
from ..sources.uscourts_f2 import load_history, new_quarters

router = APIRouter(tags=["distress"])
_TTL = 6 * 3600
_cache: dict = {"ts": 0.0, "data": None}
_lock = threading.Lock()


def distress_payload(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["data"] is not None and time.time() - _cache["ts"] < _TTL:
            return _cache["data"]
        hist = load_history()
        end = qidx(hist["history_end"])
        try:
            live = new_quarters((end // 4, end % 4 + 1))
        except Exception:  # noqa: BLE001 — a failed probe leaves the frozen history
            live = {}
        bank = bank_from_bundle(fetch_bundle(), hist)
        data = build_distress(hist, live, bank)
        _cache.update(ts=time.time(), data=data)
        return data


@router.get("/distress")
def distress():
    return distress_payload()
