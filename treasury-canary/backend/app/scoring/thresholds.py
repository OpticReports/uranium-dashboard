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
    # E. Auctions (trailing-8 coupon-auction averages)
    "auctions.bid_to_cover": Threshold(yellow=2.4, red=2.2, higher_is_worse=False),
    "auctions.dealer_takedown": Threshold(yellow=15.0, red=20.0, higher_is_worse=True),
    "auctions.indirect_share": Threshold(yellow=60.0, red=50.0, higher_is_worse=False),
    # F. Foreign flows
    "foreign.custody_26w": Threshold(yellow=-2.0, red=-5.0, higher_is_worse=False),
    # G. Liquidity
    "liquidity.on_off_run": Threshold(yellow=5.0, red=12.0, higher_is_worse=True),
    "liquidity.ofr_fsi": Threshold(yellow=1.0, red=3.0, higher_is_worse=True),
    # H. Cross-asset
    "crossasset.stock_bond_corr": Threshold(yellow=0.0, red=0.30, higher_is_worse=True),
    "crossasset.flight_to_quality": Threshold(yellow=0.6, red=0.4, higher_is_worse=False),
    "crossasset.hy_oas": Threshold(yellow=350.0, red=550.0, higher_is_worse=True),
    "crossasset.ig_oas": Threshold(yellow=130.0, red=180.0, higher_is_worse=True),
    "crossasset.erp": Threshold(yellow=1.0, red=0.0, higher_is_worse=False),
    # Margin-debt excess growth (FINRA margin YoY minus S&P YoY, pp). Backtest
    # 1997-2026: >+25pp preceded negative 12m S&P returns in 16/17 months
    # (2000/2007/2021 clusters). Composite member; 12m-horizon signal.
    "crossasset.margin_excess_yoy": Threshold(yellow=15.0, red=25.0, higher_is_worse=True),
    # Raw margin YoY (informational context; blowoff bands from the same study).
    "crossasset.margin_yoy": Threshold(yellow=30.0, red=40.0, higher_is_worse=True),
    # (crossasset.margin_coverage is deliberately unthresholded — the ratio
    # trends structurally lower, so its "record lows" are not a signal.)
    # I. Recession model (%)
    "recession.prob": Threshold(yellow=30.0, red=50.0, higher_is_worse=True),
    "recession.nfci": Threshold(yellow=0.0, red=0.7, higher_is_worse=True),
    # J. Labor (Sahm gap in pp; claims YoY in %). Sahm rule triggers at 0.50.
    "labor.sahm": Threshold(yellow=0.30, red=0.50, higher_is_worse=True),
    "labor.claims_yoy": Threshold(yellow=10.0, red=25.0, higher_is_worse=True),
    # Vacancies per unemployed person (JOLTS starts 2000-12: fell decisively
    # under ~1.0 into both the 2001 and 2008 recessions; ~1.2 pre-COVID 2019).
    "labor.vu_ratio": Threshold(yellow=1.10, red=0.90, higher_is_worse=False),
    # Openings YoY %: sustained double-digit contraction = labor demand rolling
    # over. (Status is additionally capped at YELLOW while V/U >= 1.2 — falling
    # from excess-demand levels is normalization, not deterioration.)
    "labor.openings_yoy": Threshold(yellow=-5.0, red=-15.0, higher_is_worse=False),
    # Indeed postings YoY (informational: series starts 2020 — no full cycle).
    "labor.indeed_yoy": Threshold(yellow=-5.0, red=-15.0, higher_is_worse=False),
    # K. Leading stack (each vs its OWN historical rule; display-only — never
    # jointly fitted and never in the composite, by design).
    "leading.permits_yoy": Threshold(yellow=-10.0, red=-20.0, higher_is_worse=False),
    "leading.sloos": Threshold(yellow=10.0, red=20.0, higher_is_worse=True),
    "leading.temp_help_yoy": Threshold(yellow=-2.0, red=-8.0, higher_is_worse=False),
    "leading.trucks_off_peak": Threshold(yellow=-10.0, red=-20.0, higher_is_worse=False),
    "leading.core_capex_yoy": Threshold(yellow=0.0, red=-5.0, higher_is_worse=False),
    "leading.cfnai_ma3": Threshold(yellow=-0.35, red=-0.70, higher_is_worse=False),
    "leading.gdpnow": Threshold(yellow=1.0, red=0.0, higher_is_worse=False),
    "leading.cp_prob": Threshold(yellow=20.0, red=50.0, higher_is_worse=True),
    "leading.wei": Threshold(yellow=1.0, red=0.0, higher_is_worse=False),
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
