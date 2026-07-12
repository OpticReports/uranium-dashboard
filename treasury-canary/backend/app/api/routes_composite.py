"""GET /composite, /recession-prob, and the canary chart data /curve/canary."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..config import FRED_TENORS
from ..jobs.refresh import compute_all
from ..metrics.curve import PAIRS, analyze_spread, build_spread, lag_months_to_recession
from ..metrics.recession import recession_probability
from ..sources.fred import fetch_bundle, recession_start_dates

router = APIRouter(tags=["composite"])


@router.get("/composite")
def composite():
    bundle = fetch_bundle()
    metrics, _, comp, _ = compute_all(bundle)
    return {
        "score": comp.score, "band": comp.band, "coverage": comp.coverage,
        "category_scores": comp.category_scores, "contributions": comp.contributions,
        "n_red": comp.n_red, "n_critical": comp.n_critical,
    }


@router.get("/recession-prob")
def recession_prob():
    bundle = fetch_bundle()
    d3, v3 = bundle.get("3mo", ([], []))
    d10, v10 = bundle.get("10y", ([], []))
    _, spread = build_spread(d3, v3, d10, v10)
    latest = next((v for v in reversed(spread) if v is not None), None)
    return {"spread_3m10y": latest, "probability_pct": recession_probability(latest),
            "model": "Estrella-Mishkin probit"}


@router.get("/curve/canary")
def canary(
    pair: str = Query("3m10y"),
    min_inversion_days: int = 10,
    steepen_persist_days: int = 60,
):
    """Full-history spread series + inversion/re-steepen episodes + NBER onsets +
    per-episode lag-to-recession, for the ReSteepenAlert chart."""
    if pair not in PAIRS:
        pair = "3m10y"
    short, long = PAIRS[pair]
    bundle = fetch_bundle()
    if short not in bundle or long not in bundle:
        return {"pair": pair, "error": "series unavailable (set FRED_API_KEY)",
                "series": [], "episodes": [], "recessions": [], "state": None}
    da, va = bundle[short]
    db, vb = bundle[long]
    dates, spread = build_spread(da, va, db, vb)
    a = analyze_spread(dates, spread, min_inversion_days=min_inversion_days,
                       steepen_persist_days=steepen_persist_days)
    a.pair = pair

    rec_dates, rec_vals = bundle.get("recession", ([], []))
    starts = recession_start_dates(rec_dates, rec_vals)
    # NBER recession bands as (start, end) runs.
    bands, run_start, prev = [], None, 0.0
    for d, v in zip(rec_dates, rec_vals):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            run_start = d
        if cur != 1.0 and prev == 1.0 and run_start:
            bands.append({"start": run_start.isoformat(), "end": d.isoformat()})
            run_start = None
        prev = cur
    if run_start:
        bands.append({"start": run_start.isoformat(), "end": rec_dates[-1].isoformat()})

    episodes = []
    for e in a.episodes:
        ed = e.as_dict()
        ed["lag_to_recession_months"] = lag_months_to_recession(e, starts)
        episodes.append(ed)

    # Recession probability is ALWAYS from the 3m10y spread — the Estrella-Mishkin
    # probit is calibrated on 3m10y, so applying it to the charted pair (2s10s,
    # 5s10s, ...) would be invalid. This keeps it consistent with /recession-prob.
    d3, v3 = bundle.get("3mo", ([], []))
    d10, v10 = bundle.get("10y", ([], []))
    _, s_3m10y = build_spread(d3, v3, d10, v10)
    latest_3m10y = next((v for v in reversed(s_3m10y) if v is not None), None)
    prob = recession_probability(latest_3m10y)
    # Downsample the series for transport (chart doesn't need every daily point).
    series = [{"date": d.isoformat(), "spread": s}
              for d, s in zip(dates, spread) if s is not None]
    step = max(1, len(series) // 4000)
    return {
        "pair": pair, "state": a.state.value, "current_value": a.current_value,
        "current_depth_bps": a.current_depth_bps, "days_inverted": a.days_inverted,
        "dis_inversion_date": a.dis_inversion_date.isoformat() if a.dis_inversion_date else None,
        "last_change": a.last_change.isoformat() if a.last_change else None,
        "recession_probability_pct": prob,
        "series": series[::step], "episodes": episodes, "recessions": bands,
        "available_pairs": list(PAIRS.keys()),
    }
