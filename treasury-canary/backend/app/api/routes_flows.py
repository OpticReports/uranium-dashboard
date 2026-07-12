"""GET /flows/destinations — where the money is going (flow compass + regime)."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.flows import build_flow_snapshot
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["flows"])


@router.get("/flows/destinations")
def flow_destinations():
    return build_flow_snapshot(fetch_bundle())
