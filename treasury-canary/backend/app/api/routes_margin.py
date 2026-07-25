"""GET /margin/leverage — the leverage-cycle chart + prescriptive playbook.

Serves the FINRA margin series (YoY, excess-vs-S&P, coverage), NBER bands, the
current leverage-cycle state (BLOWOFF/ELEVATED/NEUTRAL/SQUEEZE/WASHOUT) and
what happened after each state historically, so the chart answers both "is
leverage building dangerously?" and "has the leverage been squeezed out yet?"
"""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.base import last_valid
from ..metrics.crossasset import (
    LEVERAGE_PLAYBOOK, _month_end_closes, leverage_state, margin_series,
)
from ..sources.fred import fetch_bundle

router = APIRouter(tags=["margin"])

THRESHOLDS = {"blowoff_excess": 25.0, "elevated_excess": 15.0,
              "squeeze_yoy": 0.0, "washout_yoy": -15.0}


@router.get("/margin/leverage")
def margin_leverage():
    bundle = fetch_bundle()
    dates, yoy, excess, cov = margin_series(bundle, bundle.get("sp500", ([], [])))

    # Price overlays (toggleable in the UI to eyeball correlation): month-end
    # S&P and BTC closes, each ALSO indexed to 100 at its first charted month so
    # both fit one axis despite wildly different scales/growth.
    spx_me = _month_end_closes(bundle.get("sp500", ([], [])))
    btc_me = _month_end_closes(bundle.get("btc", ([], [])))

    series = []
    spx_base = btc_base = None
    for d, y, e, c in zip(dates, yoy, excess, cov):
        if y is None and e is None:
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        spx, btc = spx_me.get(ym), btc_me.get(ym)
        if spx and spx_base is None:
            spx_base = spx
        if btc and btc_base is None:
            btc_base = btc
        series.append({
            "date": d.isoformat(), "margin_yoy": y, "excess_yoy": e, "coverage": c,
            "spx": spx, "btc": btc,
            "spx_idx": round(100.0 * spx / spx_base, 1) if (spx and spx_base) else None,
            "btc_idx": round(100.0 * btc / btc_base, 1) if (btc and btc_base) else None,
        })

    cur_yoy, cur_excess, cur_cov = last_valid(yoy), last_valid(excess), last_valid(cov)
    state = leverage_state(cur_yoy, cur_excess)

    # NBER recession bands (same shape the Sahm chart uses)
    rd, rv = bundle.get("recession", ([], []))
    bands, run_start, prev = [], None, 0.0
    for d, v in zip(rd, rv):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            run_start = d
        if cur != 1.0 and prev == 1.0 and run_start:
            bands.append({"start": run_start.isoformat(), "end": d.isoformat()})
            run_start = None
        prev = cur
    if run_start and rd:
        bands.append({"start": run_start.isoformat(), "end": rd[-1].isoformat()})

    return {
        "series": series,
        "recessions": bands,
        "current": {
            "date": dates[-1].isoformat() if dates else None,
            "margin_yoy": cur_yoy, "excess_yoy": cur_excess, "coverage": cur_cov,
            "state": state,
        },
        "playbook": LEVERAGE_PLAYBOOK,
        "thresholds": THRESHOLDS,
        "source": "FINRA margin statistics (monthly, ~3-4wk lag) / FRED:SP500,CBBTCUSD",
        "note": "Excess YoY (margin growth minus S&P growth) is the validated gauge; "
                "it needs the S&P leg, so it only spans FRED's SP500 history (~10y). "
                "Margin YoY spans the full FINRA history (1997+). Stats in the playbook "
                "are from the 1997-2026 SPY study (MARGIN_DEBT.md) — descriptive, "
                "overlapping windows, ~3 independent blowoff episodes.",
    }
