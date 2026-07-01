"""Single source of truth for all green/yellow/red cutoffs.

Defaults are grounded in rates-desk convention; every band is overridable at
runtime via a JSON file pointed to by THRESHOLDS_FILE (no code edits to retune).
"""
from __future__ import annotations

import json
import logging
import os

from ..metrics.base import Status, Threshold

logger = logging.getLogger(__name__)

# metric_id -> Threshold. Spreads use higher_is_worse=False (more negative = worse).
DEFAULTS: dict[str, Threshold] = {
    # A. Curve spreads (percentage points). RE-STEEPEN override handled in events.
    "curve.3m10y": Threshold(yellow=0.50, red=0.0, higher_is_worse=False),
    "curve.2s10s": Threshold(yellow=0.50, red=0.0, higher_is_worse=False),
    "curve.5s30s": Threshold(yellow=0.20, red=0.0, higher_is_worse=False),
    "curve.2s5s": Threshold(yellow=0.20, red=0.0, higher_is_worse=False),
    "curve.3m2y": Threshold(yellow=0.20, red=0.0, higher_is_worse=False),
    "curve.5s10s": Threshold(yellow=0.20, red=0.0, higher_is_worse=False),
    # B. Volatility (MOVE proxy scaled to MOVE units; ratio)
    "vol.move": Threshold(yellow=100.0, red=140.0, higher_is_worse=True),
    "vol.move_vix": Threshold(yellow=6.0, red=8.0, higher_is_worse=True),
    "vol.vix": Threshold(yellow=20.0, red=30.0, higher_is_worse=True),
    # C. Term premium & real rates (informational direction; flag extremes)
    "premium.acm_tp10": Threshold(yellow=0.75, red=1.25, higher_is_worse=True),
    "premium.real_10y": Threshold(yellow=2.0, red=2.75, higher_is_worse=True),
    # D. Funding / plumbing (bps)
    "funding.sofr_effr": Threshold(yellow=5.0, red=15.0, higher_is_worse=True),
    "funding.sofr_iorb": Threshold(yellow=5.0, red=15.0, higher_is_worse=True),
    # E. Auctions
    "auctions.bid_to_cover": Threshold(yellow=2.4, red=2.2, higher_is_worse=False),
    # G. Liquidity
    "liquidity.on_off_run": Threshold(yellow=5.0, red=12.0, higher_is_worse=True),
    "liquidity.ofr_fsi": Threshold(yellow=1.0, red=3.0, higher_is_worse=True),
    # H. Cross-asset
    "crossasset.stock_bond_corr": Threshold(yellow=0.0, red=0.30, higher_is_worse=True),
    "crossasset.hy_oas": Threshold(yellow=350.0, red=550.0, higher_is_worse=True),
    "crossasset.ig_oas": Threshold(yellow=130.0, red=180.0, higher_is_worse=True),
    "crossasset.erp": Threshold(yellow=1.0, red=0.0, higher_is_worse=False),
    # I. Recession model (%)
    "recession.prob": Threshold(yellow=30.0, red=50.0, higher_is_worse=True),
    "recession.nfci": Threshold(yellow=0.0, red=0.7, higher_is_worse=True),
}


def _load_overrides() -> dict[str, Threshold]:
    path = os.environ.get("THRESHOLDS_FILE")
    if not path or not os.path.exists(path):
        return {}
    try:
        raw = json.load(open(path))
        out = {}
        for mid, cfg in raw.items():
            out[mid] = Threshold(
                yellow=cfg["yellow"], red=cfg["red"],
                higher_is_worse=cfg.get("higher_is_worse", True),
                critical=cfg.get("critical"),
            )
        logger.info("Loaded %d threshold overrides from %s", len(out), path)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load THRESHOLDS_FILE=%s: %s", path, exc)
        return {}


THRESHOLDS: dict[str, Threshold] = {**DEFAULTS, **_load_overrides()}


def classify(metric_id: str, value: float | None) -> Status:
    t = THRESHOLDS.get(metric_id)
    if t is None:
        return Status.STALE if value is None else Status.GREEN
    return t.classify(value)


def get(metric_id: str) -> Threshold | None:
    return THRESHOLDS.get(metric_id)
