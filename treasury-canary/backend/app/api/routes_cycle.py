"""/cycle — business-cycle tracker board (6h in-process cache; FRED is
monthly, so anything fresher is wasted calls)."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from ..sources import business_cycle, cycle_analog

router = APIRouter(tags=["cycle"])
_CACHE: dict = {}
_TTL = 6 * 3600


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        board = fn()
    except Exception as exc:  # noqa: BLE001
        if hit:
            return hit[1]                     # stale beats a 500 here
        raise HTTPException(status_code=503, detail=f"{key} compute: {exc}")
    _CACHE[key] = (time.time(), board)
    return board


@router.get("/cycle")
def cycle():
    return _cached("board", business_cycle.compute)


@router.get("/cycle/analog")
def cycle_analog_board():
    """Nearest historical analogs to the current month + walk-forward skill
    stats. Heavier than /cycle (walk-forward backtest inside) but cached on
    the same 6h TTL; first call after a deploy takes a few seconds."""
    return _cached("analog", cycle_analog.board)
