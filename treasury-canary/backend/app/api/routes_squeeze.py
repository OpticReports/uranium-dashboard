"""GET /squeeze/radar — the Duration Squeeze Radar (pre-registered scorecard).

Assembles inputs from cached sources (each degrades to STALE independently)
and calls the pure builder. History endpoints for the two percentile-based
fuel conditions so the card can draw context sparklines.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ..metrics.squeeze import build_squeeze_radar
from ..sources.cftc import fetch_ust_lev_pct_oi
from ..sources.finra import fetch_tlt_short_interest
from ..sources.fmp import fetch_move, fetch_shares_outstanding
from ..sources.fred import fetch_bundle

logger = logging.getLogger(__name__)
router = APIRouter(tags=["squeeze"])


def assemble_radar() -> dict:
    bundle = fetch_bundle()
    try:
        from ..sources.fed_futures import implied_6m_change_bp
        fed6 = implied_6m_change_bp()
    except Exception as exc:  # noqa: BLE001
        logger.warning("fed path fetch failed: %s", exc)
        fed6 = None
    return build_squeeze_radar(
        cot=fetch_ust_lev_pct_oi(),
        si_rows=fetch_tlt_short_interest(),
        shares_outstanding=fetch_shares_outstanding("TLT"),
        tp=bundle.get("acm_tp10", ([], [])),
        fed_chg_6m_bp=fed6,
        payrolls=bundle.get("payrolls", ([], [])),
        sahm=bundle.get("sahm", ([], [])),
        core_pce=bundle.get("core_pce", ([], [])),
        move=fetch_move(),
        hy_oas=bundle.get("hy_oas", ([], [])),
    )


@router.get("/squeeze/radar")
def squeeze_radar():
    return assemble_radar()


@router.get("/squeeze/history")
def squeeze_history():
    """Context series for the card: lev-fund %OI (weekly) and TLT SI (bi-monthly)."""
    cd, cv = fetch_ust_lev_pct_oi()
    si = fetch_tlt_short_interest()
    return {
        "cot": [{"date": d.isoformat(), "pct_oi": round(v, 2)}
                for d, v in zip(cd, cv)],
        "si": [{"date": r["settlement_date"],
                "shares_short_m": round(r["shares_short"] / 1e6, 1)} for r in si],
    }
