"""Fed-decision probability ensemble endpoint (display-only; never feeds the
composite or playbook)."""
from __future__ import annotations

import time

from fastapi import APIRouter

from ..sources.rate_markets import ensemble

router = APIRouter(prefix="/rates", tags=["rates"])

_CACHE: dict = {}
_TTL = 600


@router.get("/ensemble")
def rate_ensemble():
    hit = _CACHE.get("v")
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    out = ensemble()
    _CACHE["v"] = (time.time(), out)
    return out
