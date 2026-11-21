"""GET /stat-regime — unsupervised Treasury-market state (experimental,
descriptive only; see metrics/stat_regime.py for the guardrails)."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.stat_regime import build_stat_regime
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["stat-regime"])


@router.get("/stat-regime")
def stat_regime():
    return build_stat_regime(fetch_bundle())        # the object itself: its TTL follows that bundle
