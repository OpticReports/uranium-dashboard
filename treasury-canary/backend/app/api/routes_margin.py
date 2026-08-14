"""GET /margin/leverage — the leverage-cycle chart + prescriptive playbook.

Serves the margin series (YoY, excess-vs-S&P, coverage), NBER bands, the
current leverage-cycle state (BLOWOFF/ELEVATED/NEUTRAL/SQUEEZE/WASHOUT) and
what happened after each state historically, so the chart answers both "is
leverage building dangerously?" and "has the leverage been squeezed out yet?"

Long view: the margin leg splices Fed Z.1 household security credit (annual
1945-51, quarterly 1952-1997; ~2% level gap vs FINRA at the splice) onto FINRA
monthly (1997+); the S&P leg uses FMP ^GSPC daily (1927+) with FRED's ~10y
SP500 as fallback. First-FINRA-year YoY is suppressed (cross-source base).
BTC exists from 2014 (Coinbase series) — there is no earlier price to show.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..metrics.crossasset import (
    LEVERAGE_PLAYBOOK, POST_BLOWOFF_W, _month_end_closes, leverage_state,
    leverage_states_path, margin_series,
)
from ..metrics.labor import _yoy_by_date
from ..sources.fmp import fetch_spx_long
from ..sources.fred import fetch_bundle, fetch_series

router = APIRouter(tags=["margin"])

THRESHOLDS = {"blowoff_excess": 25.0, "elevated_excess": 15.0,
              "squeeze_yoy": 0.0, "washout_yoy": -15.0}

# Blowoff corroboration (MARGIN_DEBT.md study): six late-cycle flags separate
# real blowoffs from false positives. Historical outcomes are FROZEN study
# constants; the flags themselves compute LIVE so the count moves with data.
CORROBORATION_STATS = {
    "high_flags": {"label": ">=4 flags (late-cycle: 1967/1998/2000/2007)",
                   "bears": 4, "n": 4, "prob_note": "4/4 became bears — est. 65-85% (small n)"},
    "low_flags": {"label": "<=2 flags (early-cycle re-leveraging)",
                  "bears": 4, "n": 12, "prob_note": "4/12 became bears (~33%)"},
    "unconditional": {"label": "any blowoff", "bears": 8, "n": 16,
                      "prob_note": "8/16 (~50%)"},
}


def _last(series):
    d, v = series
    for x in reversed(v):
        if x is not None:
            return x
    return None


def _value_days_ago(series, days):
    from datetime import timedelta
    d, v = series
    pts = [(dd, vv) for dd, vv in zip(d, v) if vv is not None]
    if not pts:
        return None
    target = pts[-1][0] - timedelta(days=days)
    best = min(pts, key=lambda t: abs((t[0] - target).days))
    return best[1] if abs((best[0] - target).days) <= 45 else None


def late_cycle_flags(bundle, cur_excess) -> dict:
    """The six corroboration flags, computed live. None = data unavailable
    (excluded from the count denominator)."""
    y10, m3 = _last(bundle.get("10y", ([], []))), _last(bundle.get("3mo", ([], [])))
    curve = (y10 - m3) if (y10 is not None and m3 is not None) else None
    m3_ago = _value_days_ago(bundle.get("3mo", ([], [])), 365)
    d_rate = (m3 - m3_ago) if (m3 is not None and m3_ago is not None) else None
    un = _last(bundle.get("unrate", ([], [])))
    sp = bundle.get("sp500", ([], []))
    sp_now, sp_3y = _last(sp), _value_days_ago(sp, 1095)
    spx3y = (sp_now / sp_3y - 1) * 100 if (sp_now and sp_3y) else None
    rd, rv = bundle.get("recession", ([], []))
    mo_since = None
    ends = [d for d, v in zip(rd, rv) if v == 1.0]
    if ends and rd:
        mo_since = (rd[-1].year - ends[-1].year) * 12 + rd[-1].month - ends[-1].month
    flags = {
        "flat_curve": (curve < 1.0) if curve is not None else None,
        "fed_tightened": (d_rate > 0.5) if d_rate is not None else None,
        "late_expansion": (mo_since >= 48) if mo_since is not None else None,
        "low_unemployment": (un < 5.0) if un is not None else None,
        "extended_market": (spx3y > 50) if spx3y is not None else None,
        "high_excess": (cur_excess >= 25) if cur_excess is not None else None,
    }
    known = {k: v for k, v in flags.items() if v is not None}
    n_true = sum(1 for v in known.values() if v)
    return {"flags": flags, "n_true": n_true, "n_known": len(known),
            "values": {"curve_10y3m": curve and round(curve, 2),
                       "d_rate_12m": d_rate and round(d_rate, 2),
                       "months_since_recession": mo_since,
                       "unemployment": un, "spx_3y_pct": spx3y and round(spx3y),
                       "excess": cur_excess},
            "stats": CORROBORATION_STATS,
            "reading": ("late-cycle configuration — matches the 1967/1998/2000/"
                        "2007 bear cluster" if n_true >= 4 else
                        "early/mid-cycle configuration — matches the false-"
                        "positive (fizzle) cluster" if n_true <= 2 else
                        "mixed configuration")}

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
    # Splice-year suppression (QA finding): months in the first FINRA year have
    # a FINRA numerator over a Z.1 base — sources differ by up to ~7% in level,
    # distorting those YoY by up to ~8pp. Null them rather than show a
    # cross-source artifact.
    first_finra = mdates[n_z1] if 0 < n_z1 < len(mdates) else None
    if first_finra is not None:
        from datetime import timedelta
        cutoff = first_finra + timedelta(days=360)
        yv = [None if (v is not None and first_finra <= d < cutoff) else v
              for d, v in zip(yd, yv)]
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
    # path-aware state over the WHOLE monthly history (user finding
    # 2026-08-15: a snapshot classifier read the blowoff rollover - the
    # historically dangerous transition - as de-escalation)
    path = leverage_states_path([p["margin_yoy"] for p in series],
                                [p["excess_yoy"] for p in series])
    cur_i = next((i for i in range(len(series) - 1, -1, -1)
                  if series[i]["margin_yoy"] is not None), None)
    state = path[cur_i] if cur_i is not None else None
    path_ctx = None
    if state == "POST_BLOWOFF":
        j = max(i for i in range(cur_i) if path[i] == "BLOWOFF")
        k = j
        while k >= 0 and path[k] == "BLOWOFF":
            k -= 1
        run = series[k + 1:j + 1]
        peak = max((p["excess_yoy"] for p in run if p["excess_yoy"] is not None),
                   default=None)
        path_ctx = {
            "last_blowoff_month": series[j]["date"][:7],
            "blowoff_peak_excess_pp": peak,
            "months_since_blowoff": cur_i - j,
            "window_m": POST_BLOWOFF_W,
            "reinflate_rule": "excess >= +25pp or YoY >= 40% -> back to BLOWOFF",
            "squeeze_rule": "margin YoY < 0 -> SQUEEZE (post-crash reset leg)",
            "fizzle_rule": f"no re-entry within {POST_BLOWOFF_W}m -> plain level state",
        }
    # Staleness guard (QA finding): if FINRA fails cold (no cache), the series
    # tail is the 2015 Z.1 splice end — presenting an 11-year-old state as
    # "current" with playbook advice would mislead. FINRA publishes ~3-4 weeks
    # after month-end; 120 days = clearly broken, not just lagging.
    from datetime import date as _date, datetime as _datetime
    if cur_date is not None:
        age = (_date.today() - _datetime.strptime(cur_date, "%Y-%m-%d").date()).days
        if age > 120:
            state = None
            path_ctx = None      # referee: stale payload must not carry path

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

    # --- nowcast (display-only): estimate the months FINRA hasn't printed ---
    nowcast = None
    try:
        from ..metrics.margin_nowcast import build_margin_nowcast
        from ..sources.schwab_margin import fetch_schwab_margin
        try:
            schwab = fetch_schwab_margin()
        except Exception:  # noqa: BLE001
            schwab = None
        nowcast = build_margin_nowcast(bundle.get("margin_debit", ([], [])),
                                       spx_pair, schwab)
    except Exception:  # noqa: BLE001
        nowcast = None

    return {
        "series": series,
        "nowcast": nowcast,
        "corroboration": late_cycle_flags(bundle, cur_excess),
        "recessions": bands,
        "current": {
            "date": cur_date, "margin_yoy": cur_yoy, "excess_yoy": cur_excess,
            "coverage": cur_cov, "state": state, "path": path_ctx,
        },
        "playbook": LEVERAGE_PLAYBOOK,
        "thresholds": THRESHOLDS,
        "source": f"FINRA margin stats (1997+) / FRED:{_Z1_MARGIN} (1945-1997, "
                  f"annual then quarterly) / {spx_source} / FRED:CBBTCUSD",
        "z1_points": n_z1,
        "note": "Excess YoY (margin growth minus S&P growth) is the validated gauge — "
                "validated on the FINRA era (1997-2026, MARGIN_DEBT.md); the pre-1997 "
                "stretch is quarterly Z.1 data shown for historical context, not part "
                "of the backtest. Playbook stats: descriptive, overlapping windows, "
                "~3 independent blowoff episodes. BTC price exists from 2014.",
    }
