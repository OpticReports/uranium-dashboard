"""Rate-shock simulator endpoints (spec §5, repo route conventions).

GET  /shock-sim/scenarios    — scenario span, meetings, implied path, live inputs
POST /shock-sim/run          — {hikes, seed?, overrides?} -> bands/probs/meta
GET  /shock-sim/calibration  — params + sources + amendment verdicts
"""
from __future__ import annotations

import logging
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..metrics.curve import analyze_spread, build_spread
from ..metrics.recession import recession_probability
from ..metrics.volatility import _move_proxy_series
from ..sources.fred import fetch_bundle
from ..simulators import mc_core
from ..simulators.params import apply_overrides, params_hash
from ..simulators.rate_paths import MEETINGS, SCENARIO_SPAN
from ..simulators.calibration import calibration_payload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["shock-sim"])

_cache: dict[str, dict] = {}
_CACHE_MAX = 64


def _last(pair):
    d, v = pair
    for x in reversed(v):
        if x is not None:
            return float(x)
    return None


def _canary01(bundle) -> float:
    """Normalized canary composite for the stress-transition hook (spec 4.2):
    0.5*probit + 0.3*MOVE-z + 0.2*re-steepening flag. Fallback 0.3."""
    try:
        d10, v10 = bundle.get("10y", ([], []))
        d3, v3 = bundle.get("3mo", ([], []))
        sd, sv = build_spread(d10, v10, d3, v3)
        spread_last = next((x for x in reversed(sv) if x is not None), None)
        probit = recession_probability(spread_last) or 0.0
        _, mv = _move_proxy_series(d10, v10)
        mvals = [x for x in mv if x is not None]
        if len(mvals) > 60:
            mean = sum(mvals) / len(mvals)
            sd_ = (sum((x - mean) ** 2 for x in mvals) / len(mvals)) ** 0.5
            mz = max(0.0, min((mvals[-1] - mean) / sd_ if sd_ > 0 else 0.0, 3.0)) / 3.0
        else:
            mz = 0.0
        analysis = analyze_spread("3m10y", sd, sv)
        resteep = 1.0 if "steep" in str(getattr(analysis, "state", "")).lower() else 0.0
        return max(0.0, min(0.5 * probit + 0.3 * mz + 0.2 * resteep, 1.0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("canary01 fallback: %s", exc)
        return 0.3


def _live_inputs() -> dict:
    bundle = fetch_bundle()
    out = {"vix": _last(bundle.get("vix", ([], [])))}
    # ACM term premium 6m change for kappa_t (amendment A1)
    ad, av = bundle.get("acm_tp10", ([], []))
    pts = [(d, v) for d, v in zip(ad, av) if v is not None]
    out["d_acm_tp_6m"] = (round(pts[-1][1] - pts[-127][1], 3)
                          if len(pts) > 127 else None)
    hy = _last(bundle.get("hy_oas", ([], [])))
    out["oas0"] = hy * 100.0 if hy is not None else None      # % -> bp
    # MOVE: FMP ^MOVE if reachable, else the dashboard's realized proxy
    move = None
    try:
        from ..sources.fmp import fetch_gold
        md, mvv = fetch_gold("^MOVE")          # same light endpoint, cached
        move = next((x for x in reversed(mvv) if x is not None), None)
    except Exception:  # noqa: BLE001
        pass
    if move is None:
        d10, v10 = bundle.get("10y", ([], []))
        _, proxy = _move_proxy_series(d10, v10)
        move = next((x for x in reversed(proxy) if x is not None), None)
    out["move"] = move
    # HYG realized 60d vol (annualized) via FMP; fallback None -> MOVE leg only
    try:
        from ..sources.fmp import fetch_gold as _fetch
        hd, hv = _fetch("HYG")
        px = [x for x in hv if x is not None][-61:]
        if len(px) >= 40:
            rets = [math.log(px[i] / px[i - 1]) for i in range(1, len(px))]
            mu = sum(rets) / len(rets)
            var = sum((r - mu) ** 2 for r in rets) / len(rets)
            out["hyg_realized_ann"] = round(math.sqrt(var * 252), 4)
        else:
            out["hyg_realized_ann"] = None
    except Exception:  # noqa: BLE001
        out["hyg_realized_ann"] = None
    out["canary01"] = round(_canary01(bundle), 3)
    return out


class RunBody(BaseModel):
    hikes: int
    seed: int | None = 42
    overrides: dict | None = None


@router.get("/shock-sim/scenarios")
def scenarios():
    from ..simulators.params import defaults
    p = defaults()
    return {
        "span": list(SCENARIO_SPAN),
        "meetings": MEETINGS,
        "implied": {"2026-10-28": p["implied_prob_oct"],
                    "2026-12-09": p["implied_prob_dec"]},
        "live_inputs": _live_inputs(),
        "note": "Scenario hikes/cuts land at consecutive FOMC meetings from "
                "Oct-2026; surprise = scenario minus market-implied path. "
                "Implied probabilities are manual-config params (spec 3).",
    }


@router.post("/shock-sim/run")
def run(body: RunBody):
    params, warnings = apply_overrides(body.overrides)
    if not SCENARIO_SPAN[0] <= body.hikes <= SCENARIO_SPAN[1]:
        raise HTTPException(422, f"hikes must be within {SCENARIO_SPAN}")
    inputs = _live_inputs()
    # QA finding 7: `or 42` mapped seed=0 to 42 and let seed:null/42 collide
    seed = 42 if body.seed is None else int(body.seed)
    key = params_hash(params, {"hikes": body.hikes, "seed": seed,
                               "inputs": inputs})
    if key in _cache:
        return _cache[key]
    result = mc_core.simulate(body.hikes, params, inputs, seed=seed)
    result["meta"]["override_warnings"] = warnings
    result["meta"]["params_used"] = {k: round(v, 6) for k, v in params.items()}
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = result
    return result


@router.get("/shock-sim/calibration")
def calibration():
    return calibration_payload()
