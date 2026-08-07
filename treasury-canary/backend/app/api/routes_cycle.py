"""/cycle — business-cycle tracker board (6h in-process cache; FRED is
monthly, so anything fresher is wasted calls)."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from ..sources import business_cycle

router = APIRouter(tags=["cycle"])
_CACHE: dict = {}
_TTL = 6 * 3600


@router.get("/cycle")
def cycle():
    hit = _CACHE.get("board")
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        board = business_cycle.compute()
    except Exception as exc:  # noqa: BLE001
        if hit:
            return hit[1]                     # stale beats a 500 here
        raise HTTPException(status_code=503, detail=f"cycle compute: {exc}")
    _CACHE["board"] = (time.time(), board)
    return board
