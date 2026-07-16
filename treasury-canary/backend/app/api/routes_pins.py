"""GET /pins — the Dalio pin board (trigger-channel monitor).
GET /pins/history — monthly severity hindcast + damage-window overlap."""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter

from ..metrics.pin_history import build_pin_history
from ..metrics.pins import build_pin_board
from ..sources.fred import fetch_bundle
from ..sources.fmp import fetch_gold
from ..sources.treasury import fetch_recent_auctions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pins"])


def _assemble_bundle(with_auctions: bool = True) -> dict:
    bundle = dict(fetch_bundle())
    if with_auctions:
        # demand-strike channel: auction tape (FiscalData, keyless, cached 6h)
        bundle["auctions"] = fetch_recent_auctions()
    # passive-concentration channel: cap-weight vs equal-weight (FMP dailies)
    for key, sym in (("spy", "SPY"), ("rsp", "RSP")):
        try:
            bundle[key] = fetch_gold(sym)
        except Exception as exc:  # noqa: BLE001 — channel degrades to STALE
            logger.warning("pin board: %s fetch failed: %s", sym, exc)
            bundle[key] = ([], [])
    return bundle


@router.get("/pins")
def pin_board():
    return build_pin_board(_assemble_bundle())


# The hindcast walks ~50y of daily series with expanding percentiles — cheap
# but not free (~1s), so memoize it on the same clock as the bundle cache.
_HIST_TTL = 6 * 3600
_hist_cache: dict[str, object] = {"ts": 0.0, "data": None}
_hist_lock = threading.Lock()


@router.get("/pins/history")
def pin_history():
    now = time.time()
    if _hist_cache["data"] is not None and now - float(_hist_cache["ts"]) < _HIST_TTL:
        return _hist_cache["data"]
    with _hist_lock:
        now = time.time()
        if _hist_cache["data"] is not None and now - float(_hist_cache["ts"]) < _HIST_TTL:
            return _hist_cache["data"]
        data = build_pin_history(_assemble_bundle(with_auctions=False))
        _hist_cache["data"] = data
        _hist_cache["ts"] = time.time()
        return data
