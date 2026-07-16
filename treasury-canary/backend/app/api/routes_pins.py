"""GET /pins — the Dalio pin board (trigger-channel monitor)."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.pins import build_pin_board
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["pins"])


@router.get("/pins")
def pin_board():
    return build_pin_board(fetch_bundle())
