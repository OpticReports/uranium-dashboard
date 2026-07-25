"""GET /margin/leverage — the leverage-cycle chart + prescriptive playbook.

Serves the margin series (YoY, excess-vs-S&P, coverage), NBER bands, the
current leverage-cycle state (BLOWOFF/ELEVATED/NEUTRAL/SQUEEZE/WASHOUT) and
what happened after each state historically, so the chart answers both "is
leverage building dangerously?" and "has the leverage been squeezed out yet?"

Long view: the margin leg splices Fed Z.1 household security credit (quarterly,
1945-1997, tracks FINRA near-1:1 at the splice) onto FINRA monthly (1997+);
the S&P leg uses FMP ^GSPC daily (~1951+) with FRED's ~10y SP500 as fallback.
BTC exists from 2014 (Coinbase series) — there is no earlier price to show.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.crossasset import (
    LEVERAGE_PLAYBOOK, _month_end_closes, leverage_state, margin_series,
)
from ..metrics.labor import _yoy_by_date
from ..sources.fmp import fetch_spx_long
from ..sources.fred import fetch_bundle, fetch_series

router = APIRouter(tags=["margin"])

THRESHOLDS = {"blowoff_excess": 25.0, "elevated_excess": 15.0,
              "squeeze_yoy": 0.0, "washout_yoy": -15.0}

# Dollar-level households security credit (see config FRED_SEVERITY note).
_Z1_MARGIN = "HNOSCIQ027S"
_DEEP_START = "1945-01-01"


def _long_margin(bundle) -> tuple[list, list, int]:
    """FINRA monthly (1997+) with Z.1 quarterly spliced in front. Both $mm.
    Returns (dates, values, n_z1_points)."""
    fd, fv = bundle.get("margin_debit", ([], []))
    zd, zv = fetch_series(_Z1_MARGIN, start=_DEEP_START)
    first_finra = next((d for d, v in zip(fd, fv) if v is not None), None)
    dates: list = []
    vals: list = []
    for d, v in zip(zd, zv):
        if v is None or (first_finra and d >= first_finra):
            continue
        dates.append(d)
        vals.append(v)
    n_z1 = len(dates)
    for d, v in zip(fd, fv):
        if v is not None:
            dates.append(d)
            vals.append(v)
    return dates, vals, n_z1


@router.get("/margin/leverage")
def margin_leverage():
    bundle = fetch_bundle()

    # --- margin leg: Z.1 (quarterly, pre-1997) + FINRA (monthly). YoY is
    # date-matched so the quarterly and monthly stretches are both correct.
    mdates, mvals, n_z1 = _long_margin(bundle)
    # tol 20d: monthly and quarterly first-of-period dates both land within ~2
    # days of an exact year back; anything looser lets series edges slip to an
    # 11-month base and fabricate a YoY.
    yd, yv = _yoy_by_date(mdates, mvals, tol_days=20)
    yoy_by_month = {f"{d.year:04d}-{d.month:02d}": v for d, v in zip(yd, yv)}

    # coverage (cash/debt) exists only in the FINRA era
    cdates, _, _, cov = margin_series(bundle, ([], []))
    cov_by_month = {f"{d.year:04d}-{d.month:02d}": c for d, c in zip(cdates, cov)}

    # --- S&P leg: FMP ^GSPC (~1951+), FRED SP500 (~10y) as fallback
    spx_pair = fetch_spx_long()
    spx_source = "FMP:^GSPC"
    if not spx_pair[0]:
        spx_pair = bundle.get("sp500", ([], []))
        spx_source = "FRED:SP500"
    spx_me = _month_end_closes(spx_pair)
    btc_me = _month_end_closes(bundle.get("btc", ([], [])))

    # --- one row per month wherever ANY line has data --------------------------
    months = sorted(set(yoy_by_month) | set(spx_me) | set(btc_me))
    series = []
    spx_base = btc_base = None
    for ym in months:
        y = yoy_by_month.get(ym)
        spx, btc = spx_me.get(ym), btc_me.get(ym)
        prev = f"{int(ym[:4]) - 1}-{ym[5:]}"
        spx_yoy = ((spx / spx_me[prev] - 1) * 100
                   if (spx and spx_me.get(prev)) else None)
        e = round(y - spx_yoy, 1) if (y is not None and spx_yoy is not None) else None
        if spx and spx_base is None:
            spx_base = spx
        if btc and btc_base is None:
            btc_base = btc
        series.append({
            "date": f"{ym}-01", "margin_yoy": y, "excess_yoy": e,
            "coverage": cov_by_month.get(ym),
            "spx": spx, "btc": btc,
            "spx_idx": round(100.0 * spx / spx_base, 1) if (spx and spx_base) else None,
            "btc_idx": round(100.0 * btc / btc_base, 1) if (btc and btc_base) else None,
        })

    cur_yoy = next((p["margin_yoy"] for p in reversed(series)
                    if p["margin_yoy"] is not None), None)
    cur_excess = next((p["excess_yoy"] for p in reversed(series)
                       if p["excess_yoy"] is not None), None)
    cur_cov = next((p["coverage"] for p in reversed(series)
                    if p["coverage"] is not None), None)
    cur_date = next((p["date"] for p in reversed(series)
                     if p["margin_yoy"] is not None), None)
    state = leverage_state(cur_yoy, cur_excess)

    # NBER recession bands — fetched from 1945 so the deep view has them too
    # (the shared bundle starts at 1976).
    rd, rv = fetch_series("USREC", start=_DEEP_START)
    if not rd:
        rd, rv = bundle.get("recession", ([], []))
    bands, run_start, prev_v = [], None, 0.0
    for d, v in zip(rd, rv):
        cur = v or 0.0
        if cur == 1.0 and prev_v != 1.0:
            run_start = d
        if cur != 1.0 and prev_v == 1.0 and run_start:
            bands.append({"start": run_start.isoformat(), "end": d.isoformat()})
            run_start = None
        prev_v = cur
    if run_start and rd:
        bands.append({"start": run_start.isoformat(), "end": rd[-1].isoformat()})

    return {
        "series": series,
        "recessions": bands,
        "current": {
            "date": cur_date, "margin_yoy": cur_yoy, "excess_yoy": cur_excess,
            "coverage": cur_cov, "state": state,
        },
        "playbook": LEVERAGE_PLAYBOOK,
        "thresholds": THRESHOLDS,
        "source": f"FINRA margin stats (1997+) / FRED:{_Z1_MARGIN} (1945-1997, quarterly) "
                  f"/ {spx_source} / FRED:CBBTCUSD",
        "z1_points": n_z1,
        "note": "Excess YoY (margin growth minus S&P growth) is the validated gauge — "
                "validated on the FINRA era (1997-2026, MARGIN_DEBT.md); the pre-1997 "
                "stretch is quarterly Z.1 data shown for historical context, not part "
                "of the backtest. Playbook stats: descriptive, overlapping windows, "
                "~3 independent blowoff episodes. BTC price exists from 2014.",
    }
