"""GET /flows/destinations — where the money is going (flow compass + regime)."""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.flows import build_flow_snapshot
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["flows"])


@router.get("/flows/destinations")
def flow_destinations():
    return build_flow_snapshot(fetch_bundle())


@router.get("/crossasset/corr")
def stock_bond_corr_series():
    """Rolling 60d stock-bond correlation SERIES computed from the underlying
    daily data (~10y of FRED SP500) — not the snapshot log, which only accrues
    one point per refresh day and resets on free-tier redeploys."""
    from ..metrics.crossasset import _aligned_returns, _rolling_corr
    bundle = fetch_bundle()
    dates, sp_ret, bond_ret = _aligned_returns(
        bundle.get("sp500", ([], [])), bundle.get("10y", ([], [])))
    corr = _rolling_corr(sp_ret, bond_ret)
    series = [{"date": d.isoformat(), "corr": c}
              for d, c in zip(dates, corr) if c is not None]
    step = max(1, len(series) // 2000)
    return {"series": series[::step],
            "current": series[-1]["corr"] if series else None,
            "note": "Rolling 60d correlation of daily S&P returns vs 10y Treasury "
                    "price returns. Negative = hedge intact; positive = regime break."}
