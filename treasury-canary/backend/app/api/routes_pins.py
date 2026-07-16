"""GET /pins — the Dalio pin board (trigger-channel monitor)."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..metrics.pins import build_pin_board
from ..sources.fred import fetch_bundle
from ..sources.fmp import fetch_gold
from ..sources.treasury import fetch_recent_auctions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pins"])


@router.get("/pins")
def pin_board():
    bundle = dict(fetch_bundle())
    # demand-strike channel: auction tape (FiscalData, keyless, cached 6h)
    bundle["auctions"] = fetch_recent_auctions()
    # passive-concentration channel: cap-weight vs equal-weight (FMP dailies)
    for key, sym in (("spy", "SPY"), ("rsp", "RSP")):
        try:
            bundle[key] = fetch_gold(sym)
        except Exception as exc:  # noqa: BLE001 — channel degrades to STALE
            logger.warning("pin board: %s fetch failed: %s", sym, exc)
            bundle[key] = ([], [])
    return build_pin_board(bundle)
