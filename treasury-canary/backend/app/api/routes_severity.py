"""GET /severity — the recession severity index (gun-size gauge)."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.severity import build_severity
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["severity"])


@router.get("/severity")
def severity():
    return build_severity(fetch_bundle())
