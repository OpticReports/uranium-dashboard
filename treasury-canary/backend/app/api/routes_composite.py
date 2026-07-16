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
    from ..scoring.ensemble import weight_ensemble
    bundle = fetch_bundle()
    metrics, _, comp, _ = compute_all(bundle)
    return {
        "score": comp.score, "band": comp.band, "coverage": comp.coverage,
        "category_scores": comp.category_scores, "contributions": comp.contributions,
        "n_red": comp.n_red, "n_critical": comp.n_critical,
        "ensemble": weight_ensemble(metrics),
    }


@router.get("/recession-prob")
def recession_prob(horizon: int = 12):
    """Recession probability at `horizon` months, from a probit FIT ON FRED DATA
    (3m10y + USREC). Falls back to the published Estrella-Mishkin 12m coefficients
    if the model can't be fit (e.g. no FRED key)."""
    from ..metrics.recession_model import cached_models_and_spread, predict
    models, spread = cached_models_and_spread()
    m = models.get(horizon)
    if m is None:  # fitting unavailable -> published 12m coefficients on the spread
        return {"spread_3m10y": spread, "horizon_months": horizon,
                "probability_pct": recession_probability(spread),
                "model": "Estrella-Mishkin (published 12m coefficients)", "fitted": False}
    r = predict(m["b0"], m["b1"], m["cov"], spread) if spread is not None else {
        "probability_pct": None, "ci_low_pct": None, "ci_high_pct": None}
    return {"spread_3m10y": spread, "horizon_months": horizon, **r,
            "auc": m["auc"], "n_obs": m["n_obs"], "fitted": True,
            "model": "probit fit on FRED 3m10y + USREC"}


@router.get("/recession-model")
def recession_model():
    """All horizons at once for the dial: probability + confidence band + in-sample
    AUC per horizon, plus the fitted coefficients (full transparency)."""
    from ..metrics.recession_model import cached_models_and_spread, predict
    models, spread = cached_models_and_spread()
    horizons = {}
    for h, m in sorted(models.items()):
        r = predict(m["b0"], m["b1"], m["cov"], spread) if spread is not None else {
            "probability_pct": None, "ci_low_pct": None, "ci_high_pct": None}
        horizons[h] = {**r, "auc": m["auc"], "n_obs": m["n_obs"], "n_pos": m["n_pos"],
                       "b0": round(m["b0"], 4), "b1": round(m["b1"], 4)}
    # Term-premium-adjusted variant (expectations component only).
    from ..metrics.recession_model import cached_adjusted
    adj_models, adj_spread, tp_now = cached_adjusted()
    adjusted = {}
    for h, m in sorted(adj_models.items()):
        r = predict(m["b0"], m["b1"], m["cov"], adj_spread) if adj_spread is not None else {
            "probability_pct": None, "ci_low_pct": None, "ci_high_pct": None}
        adjusted[h] = {**r, "auc": m["auc"], "n_obs": m["n_obs"]}
    # Qualitative pins->dial transmission note (worded, never numbered).
    from ..metrics.pins import build_pin_board, transmission_note
    p12 = horizons.get(12, {}).get("probability_pct")
    transmission = transmission_note(build_pin_board(fetch_bundle()), p12)
    return {
        "spread_3m10y": spread,
        "default_horizon": 12,
        "horizons": horizons,
        "transmission": transmission,
        "adjusted": {
            "spread_minus_tp": adj_spread, "acm_tp10": tp_now, "horizons": adjusted,
            "note": "Bernanke critique: when QE pins the term premium negative, the raw "
                    "curve inverts 'too easily'. This variant subtracts the ACM 10y term "
                    "premium so the input is the expectations component only (sample "
                    "starts ~1990 — fewer recessions, wider bands).",
        },
        "spread_input": "3m10y (10y minus 3m), monthly-averaged",
        "method": "probit MLE (IRLS) fit on FRED data; CI via delta method on the index; AUC in-sample",
        "note": "Probabilities are model estimates with confidence bands, not forecasts. "
                "The yield curve's predictive power peaks ~12-18mo; post-2000 lead times are longer/noisier.",
    }


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

    # Recession probability ALWAYS from 3m10y (the probit is calibrated on it), via
    # the same fitted 12m model as /recession-prob — consistent across every pair.
    from ..metrics.recession_model import cached_models_and_spread, predict
    models, latest_3m10y = cached_models_and_spread()
    m12 = models.get(12)
    if m12 is not None and latest_3m10y is not None:
        prob = predict(m12["b0"], m12["b1"], m12["cov"], latest_3m10y)["probability_pct"]
    else:
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
