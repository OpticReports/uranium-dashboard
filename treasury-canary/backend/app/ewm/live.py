"""EWM live-signal couplings — canary market data wired per
ewm/CANARY_COUPLING_RESEARCH.md (operator-approved build).

One primary trigger per channel (double-counting rule):
  fcix_z      <- Chicago Fed NFCI, trailing z (raw NFCI would pin the
                 window-score transfer function; z-scoring restores range)
  dmhi01      <- mean of inverted SLOOS C&I tightening and the inverted
                 private-credit pin channel (the implemented proxy for the
                 direct-lending market a ~$200M deal actually prices in)
  spike_pos   <- rate-shock panel SPIKE x POS (labeled recession-risk caution
                 per the frozen study: NOT a stock-sell signal, p=0.21)
  financing   <- HY OAS level + 90d change, three states with dual-threshold
                 hysteresis (2022 episode: the market shut on level AND speed)
                 -> stall-hazard multiplier on the hawk rows
  headwind    <- AJSW elasticity (-4.8%/100bp purchase multiple) x HY move
                 since the report date. DISPLAY-ONLY: report cells are never
                 touched by live data.
  nowcast     <- 2y-yield 3m repricing + financing state -> which cohort row
                 the market is voting for, with a bounded +/-5pp tilt that is
                 OFFERED, never silently applied.
  stress      <- rate-shock simulator run per cohort scenario, weighted;
                 max monthly stress-state occupancy (labeled: understates
                 cumulative P(ever-stress); sim horizon ends 2027-06).

Every getter degrades to None on failure; the API layer falls back to the
stored/manual value and shows the provenance. Snapshot is TTL-cached; the
financing/nowcast hysteresis state persists across restarts.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ewm")
os.makedirs(_DIR, exist_ok=True)
_STATE = os.path.join(_DIR, "live_state.json")

_cache: dict = {"ts": 0.0, "snap": None}
_TTL = 300.0

HY_REF_BP = 284.0            # HY OAS at the report date (2026-07-30, BAMLH0A0HYM2)
AJSW_MULT_PCT_PER_100BP = -4.8   # J.Finance 2013 purchase-multiple elasticity

# financing-state thresholds (enter/exit pairs = hysteresis; memo §3)
FIN = {"tight_enter": 400.0, "tight_exit": 375.0,
       "shut_enter": 500.0, "shut_exit": 425.0,
       "d90_enter": 150.0, "d90_exit": 100.0,
       "stall_mult": {"BENIGN": 1.0, "TIGHT": 4 / 3, "SHUT": 5 / 3}}

# nowcast thresholds on the 2y 3m change (pp); 0.4 is the gate-validated
# accelerate proxy (fired Dec-2021, silent 2019)
NOW = {"hawk2_enter": 0.75, "hawk_enter": 0.40, "lean_enter": 0.25,
       "cut_enter": -0.25, "exit_band": 0.10, "tilt_pp_max": 0.05}


def _load_state() -> dict:
    try:
        return json.load(open(_STATE))
    except Exception:  # noqa: BLE001
        return {"financing": "BENIGN", "nowcast_row": 1}


def _save_state(st: dict) -> None:
    json.dump(st, open(_STATE, "w"))


def _last(pair, n_back=0):
    d, v = pair
    vals = [x for x in v if x is not None]
    if len(vals) <= n_back:
        return None
    return float(vals[-1 - n_back])


def _chg(pair, bdays):
    d, v = pair
    vals = [x for x in v if x is not None]
    if len(vals) <= bdays:
        return None
    return float(vals[-1]) - float(vals[-1 - bdays])


def fcix_from_nfci(bundle) -> dict | None:
    """NFCI trailing z (5y weekly window). Convention matches the EWM input
    exactly: 0 = average, + = tighter."""
    try:
        from ..api.routes_margin_fast import _z_series
        vals = [x for x in bundle.get("nfci", ([], []))[1] if x is not None]
        if len(vals) < 60:
            return None
        z = _z_series(vals, window=260, min_n=52)[-1]
        if z is None:
            return None
        return {"value": round(max(-1.0, min(2.0, z)), 2),
                "raw_nfci": round(vals[-1], 3),
                "source": "FRED:NFCI trailing-z (260w)", }
    except Exception:  # noqa: BLE001
        return None


def dmhi_from_sloos_pins(bundle) -> dict | None:
    """0..1 deal-market health, 1 = healthy. Legs: inverted SLOOS C&I
    tightening (quarterly, clip(1 - sloos/40)) and the inverted
    private-credit pin channel score (daily). Mean of available legs."""
    legs = {}
    try:
        sloos = _last(bundle.get("sloos", ([], [])))
        if sloos is not None:
            legs["sloos"] = max(0.0, min(1.0, 1 - sloos / 40.0))
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..metrics.pins import build_pin_board
        ch = next((c for c in build_pin_board(bundle)["channels"]
                   if c["channel_id"] == "private_credit"), None)
        if ch and ch.get("score") is not None:
            legs["private_credit"] = max(0.0, min(1.0, 1 - ch["score"] / 100.0))
    except Exception:  # noqa: BLE001
        pass
    if not legs:
        return None
    return {"value": round(sum(legs.values()) / len(legs), 3),
            "components": {k: round(v, 3) for k, v in legs.items()},
            "source": "inverted SLOOS C&I + private-credit pin channel"}


def spike_pos_live() -> dict | None:
    """Rate-shock panel state x regime; the deny-Green override fires only on
    SPIKE x POS. Honesty label per the frozen study: recession-odds caution
    (47% vs 21% baseline), not an equity-drawdown call."""
    try:
        from ..api.routes_rates import rates_shock
        cur = rates_shock()["current"]
        if not cur.get("state") or not cur.get("regime"):
            return None                                   # dead feed -> fallback
        return {"value": cur["state"] == "SPIKE" and cur["regime"] == "POS",
                "state": cur["state"], "regime": cur["regime"],
                "d60_bp": cur.get("d60_bp"),
                "source": "rate-shock panel (DGS30 d60 x stock-bond corr)"}
    except Exception:  # noqa: BLE001
        return None


def financing_state(bundle, prev: str) -> dict | None:
    """Three-state HY financing trigger with dual-threshold hysteresis.
    Level AND speed both trigger (2022: the market shut at only ~500-600bp
    because the move was fast)."""
    try:
        hy = bundle.get("hy_oas", ([], []))
        level = _last(hy)
        d90 = _chg(hy, 63)
        if level is None:
            return None
        d90 = d90 if d90 is not None else 0.0
        state = prev if prev in FIN["stall_mult"] else "BENIGN"
        if level >= FIN["shut_enter"] or d90 >= FIN["d90_enter"]:
            state = "SHUT"
        elif state == "SHUT" and level < FIN["shut_exit"] and d90 < FIN["d90_exit"]:
            state = "TIGHT"
        if state != "SHUT":
            if level >= FIN["tight_enter"]:
                state = "TIGHT" if state == "BENIGN" else state
            elif state == "TIGHT" and level < FIN["tight_exit"]:
                state = "BENIGN"
        return {"state": state, "hy_bp": round(level, 0), "d90_bp": round(d90, 0),
                "stall_mult": round(FIN["stall_mult"][state], 3),
                "source": "FRED HY OAS level + 90d change, hysteretic",
                "note": "stall-hazard multiplier on hawk rows; evidence: "
                        "stress stalls processes, it does not kill signed deals"}
    except Exception:  # noqa: BLE001
        return None


def headwind_chip(bundle) -> dict | None:
    """AJSW purchase-multiple headwind vs the report date. Display-only."""
    try:
        level = _last(bundle.get("hy_oas", ([], [])))
        if level is None:
            return None
        delta = level - HY_REF_BP
        return {"hy_now_bp": round(level, 0), "hy_ref_bp": HY_REF_BP,
                "delta_bp": round(delta, 0),
                "multiple_pct": round(AJSW_MULT_PCT_PER_100BP * delta / 100.0, 2),
                "source": "AJSW (J.Fin 2013): -4.8%/100bp purchase multiple; "
                          "ref = report date 2026-07-30"}
    except Exception:  # noqa: BLE001
        return None


def path_nowcast(bundle, fin_state: str, prev_row: int) -> dict | None:
    """Which cohort row is the market voting for? 2y 3m repricing is the
    primary signal (gate-validated accelerate proxy at +0.40pp); the
    financing state confirms. Hysteresis: the voted row only steps when the
    signal clears the threshold +/- exit_band vs the prior vote."""
    try:
        d2 = _chg(bundle.get("2y", ([], [])), 63)
        if d2 is None:
            return None
        band = NOW["exit_band"]

        def _vote(x):
            if x >= NOW["hawk2_enter"]:
                return 3
            if x >= NOW["hawk_enter"]:
                return 2
            if x >= NOW["lean_enter"]:
                return 2 if fin_state != "BENIGN" else 1
            if x <= NOW["cut_enter"]:
                return -1
            return 1
        vote = _vote(d2)
        # hysteresis on the RELEASE side only: entry thresholds are the
        # calibrated triggers; stepping down (less hawkish) requires the
        # signal to clear the previous vote's boundary by exit_band too
        if vote < prev_row and _vote(d2 + band) >= prev_row:
            vote = prev_row
        tilt = 0.0
        if vote >= 2:
            tilt = min(NOW["tilt_pp_max"], 0.02 * (vote - 1) + 0.01)
        elif vote == -1:
            tilt = -min(NOW["tilt_pp_max"], 0.03)
        return {"d2_chg_3m_pp": round(d2, 2), "voting_row": vote,
                "suggested_tilt_pp": round(tilt, 3),
                "source": "DGS2 3m change (gate-validated proxy) + financing state",
                "note": "suggestion only — applied via the Apply button, "
                        "never silently"}
    except Exception:  # noqa: BLE001
        return None


def stress_bridge(weights: list[float], hikes: list[int],
                  canary01: float | None) -> dict | None:
    """Simulator stress odds, weighted across cohort scenarios. Uses max
    monthly stress-state occupancy per scenario (understates cumulative
    P(ever-stress); the sim horizon ends 2027-06, before the sale goal)."""
    try:
        from ..api.routes_shock_sim import _live_inputs
        from ..simulators.mc_core import simulate as sim_run
        from ..simulators.params import defaults
        from ..simulators.rate_paths import SCENARIO_SPAN
        params, inputs = defaults(), dict(_live_inputs())
        if canary01 is not None:
            inputs["canary01"] = canary01     # the fixed hook; never the broken one
        per = []
        for h, w in zip(hikes, weights):
            hh = max(SCENARIO_SPAN[0], min(SCENARIO_SPAN[1], h))
            r = sim_run(hh, params, inputs, seed=42)
            per.append({"hikes": h, "weight": round(w, 3),
                        "max_occupancy": round(max(r["stress_prob"]), 3)})
        agg = sum(x["weight"] * x["max_occupancy"] for x in per)
        return {"value": round(agg, 3), "per_scenario": per,
                "source": "shock-sim per-scenario, cohort-weighted",
                "note": "max monthly stress occupancy — understates cumulative; "
                        "horizon ends 2027-06"}
    except Exception:  # noqa: BLE001
        return None


def live_snapshot(weights: list[float], hikes: list[int],
                  canary01: float | None) -> dict:
    """TTL-cached bundle of every live coupling. Any leg may be None."""
    now = time.time()
    if _cache["snap"] is not None and now - _cache["ts"] < _TTL:
        return _cache["snap"]
    st = _load_state()
    snap: dict = {"asof": datetime.now(timezone.utc).isoformat()}
    try:
        from ..sources.fred import fetch_bundle
        bundle = fetch_bundle()
    except Exception:  # noqa: BLE001
        bundle = {}
    snap["fcix"] = fcix_from_nfci(bundle)
    snap["dmhi"] = dmhi_from_sloos_pins(bundle)
    snap["spike_pos"] = spike_pos_live()
    snap["financing"] = financing_state(bundle, st.get("financing", "BENIGN"))
    snap["headwind"] = headwind_chip(bundle)
    snap["nowcast"] = path_nowcast(
        bundle, (snap["financing"] or {}).get("state", "BENIGN"),
        st.get("nowcast_row", 1))
    snap["stress"] = stress_bridge(weights, hikes, canary01)
    if snap["financing"]:
        st["financing"] = snap["financing"]["state"]
    if snap["nowcast"]:
        st["nowcast_row"] = snap["nowcast"]["voting_row"]
    _save_state(st)
    _cache.update(ts=now, snap=snap)
    return snap
