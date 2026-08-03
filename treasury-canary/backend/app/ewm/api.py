"""EWM sub-app (folded into the canary service — zero extra hosting cost).

Served under /ewm/* on this service; the genomics proxy exposes it at /exit/
behind the login gate. Canary composite is read IN-PROCESS (no self-HTTP)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .core import (FOMC, HIKES, MODAL_S, MONTHS, PARAMS, Q1END, Q2END,
                   TARGET_M, action_cards, apply_weight_tilt, breakeven,
                   cohort_surface, dirichlet_band, hold_premium, slip_costs,
                   scenario_weights, window_scores)
from .live import live_snapshot
from .mc import simulate

router = APIRouter(prefix="/ewm", tags=["ewm"])
_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ewm")
os.makedirs(_DIR, exist_ok=True)
_INPUTS = os.path.join(_DIR, "inputs.json")
_EVENTS = os.path.join(_DIR, "events.jsonl")

DEFAULT_INPUTS = {"revenue_dec2026": PARAMS["revenue_dec2026"],
                  "target_value_lo": PARAMS["target_value"][0],
                  "target_value_hi": PARAMS["target_value"][1],
                  "pin_report": False,
                  "ebitda_run_rate": 14.0,                # legacy; engine is revenue-basis
                  "stage": "prep", "dissent_cluster": False, "fcix_z": 0.1,
                  "dmhi01": 0.55, "canary01": None, "stress_prob": 0.1,
                  "qofe_ready": False, "today_month": "2026-09",
                  # live-coupling autopilot (CANARY_COUPLING memo): per-field
                  # AUTO flags; a manual POST of the field flips it to False
                  "auto": {"fcix_z": True, "dmhi01": True, "spike_pos": True,
                           "stress_prob": True, "stall_mult": True},
                  "weight_tilt": None}                    # {"toward": h, "pp": x}


def _resolve(inp: dict, live: dict) -> dict:
    """AUTO fields read the live coupling when available; MANUAL (or a dead
    feed) falls back to the stored value. Every resolution carries
    provenance so the UI can show where each number came from."""
    auto = {**DEFAULT_INPUTS["auto"], **(inp.get("auto") or {})}

    def pick(field, leg, key="value"):
        lv = live.get(leg)
        if auto.get(field) and lv is not None and lv.get(key) is not None:
            return lv[key], f"AUTO — {lv.get('source', leg)}"
        return inp.get(field, DEFAULT_INPUTS.get(field)), "MANUAL/stored"

    fcix, fcix_src = pick("fcix_z", "fcix")
    dmhi, dmhi_src = pick("dmhi01", "dmhi")
    stress, stress_src = pick("stress_prob", "stress")
    spike, spike_src = pick("spike_pos", "spike_pos")
    if not isinstance(spike, bool):
        spike, spike_src = False, "MANUAL/off"
    mult, mult_src = 1.0, "MANUAL/off"
    fin = live.get("financing")
    if auto.get("stall_mult") and fin is not None:
        mult, mult_src = fin["stall_mult"], f"AUTO — {fin['source']}"
    return {"fcix_z": float(fcix), "dmhi01": float(dmhi),
            "stress_prob": float(stress), "spike_pos": bool(spike),
            "stall_mult": float(mult),
            "provenance": {"fcix_z": fcix_src, "dmhi01": dmhi_src,
                           "stress_prob": stress_src, "spike_pos": spike_src,
                           "stall_mult": mult_src},
            "auto": auto}


def load_inputs() -> dict:
    try:
        return {**DEFAULT_INPUTS, **json.load(open(_INPUTS))}
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_INPUTS)


def _params_for(inp: dict) -> dict:
    p = dict(PARAMS)
    p["revenue_dec2026"] = float(inp["revenue_dec2026"])
    p["target_value"] = [float(inp["target_value_lo"]), float(inp["target_value_hi"])]
    return p


def _log(kind: str, detail: dict) -> None:
    with open(_EVENTS, "a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "kind": kind, "detail": detail}) + "\n")


def _canary01() -> float | None:
    """In-process composite read (no self-HTTP: same service). compute_all
    takes the FRED bundle and returns (metrics, analyses, composite,
    recession_starts); auctions=[] keeps this call fully offline beyond the
    6h-cached bundle."""
    try:
        from ..jobs.refresh import compute_all
        from ..sources.fred import fetch_bundle
        _, _, composite, _ = compute_all(fetch_bundle(), auctions=[])
        score = getattr(composite, "score", None)
        if getattr(composite, "coverage", 0.0) < 0.3:     # degraded feed: a
            return None                                    # near-empty bundle
        return round(score / 100.0, 3) if score is not None else None
    except Exception:  # noqa: BLE001
        return None


class Inputs(BaseModel):
    revenue_dec2026: float | None = None
    target_value_lo: float | None = None
    target_value_hi: float | None = None
    pin_report: bool | None = None
    ebitda_run_rate: float | None = None
    stage: str | None = None
    dissent_cluster: bool | None = None
    fcix_z: float | None = None
    dmhi01: float | None = None
    stress_prob: float | None = None
    today_month: str | None = None
    auto: dict | None = None                              # per-field AUTO flags
    apply_tilt: bool | None = None                        # accept the nowcast tilt
    clear_tilt: bool | None = None


class SimToggles(BaseModel):
    force_hikes: int | None = None
    crash: str = "none"
    regime_50bp: bool = False
    extra_stall_pp: float = 0.0
    pin_report: bool = False


@router.get("/api/ewm/board")
def board():
    inp = load_inputs()
    canary = inp.get("canary01")
    if canary is None:
        canary = _canary01() or 0.25
    p = _params_for(inp)
    live = live_snapshot(scenario_weights(p, inp["dissent_cluster"]), HIKES,
                         canary)
    res = _resolve(inp, live)
    p["stall_mult"] = res["stall_mult"]
    p = apply_weight_tilt(p, inp.get("weight_tilt"))
    pin = bool(inp.get("pin_report"))
    surface = cohort_surface(p, inp["dissent_cluster"], pin_report=pin)
    be = breakeven(p, inp["dissent_cluster"], pin_report=pin)
    band = dirichlet_band(p, inp["dissent_cluster"], pin_report=pin)
    hp = hold_premium(surface["surface"])
    ws = window_scores(p, surface["weights"], res["fcix_z"], res["dmhi01"],
                       canary, inp["stage"], inp["today_month"],
                       spike_pos_override=res["spike_pos"])
    slip = slip_costs(p, surface["surface"], inp["stage"],
                      inp["today_month"], surface["weights"])
    cards = action_cards(p, {"hike_weights": surface["weights"],
                             "fcix_z": res["fcix_z"],
                             "dissent_cluster": inp["dissent_cluster"],
                             "stress_prob": res["stress_prob"],
                             "financing": live.get("financing"),
                             "breakeven": be})
    q1 = next(r for r in surface["surface"] if r["month"] == Q1END)
    q2 = next(r for r in surface["surface"] if r["month"] == Q2END)
    tgt = next(r for r in surface["surface"] if r["month"] == TARGET_M)
    return {"inputs": inp, "canary01": canary, "surface": surface,
            "live": live, "resolved": res,
            "breakeven": be, "weight_band": band, "hold_premium": hp,
            "windows": ws, "slip": slip, "cards": cards,
            "headline": {"q1_ev": q1["ev"], "q1_lo": q1["ev_lo"], "q1_hi": q1["ev_hi"],
                         "q2_ev": q2["ev"], "target_ev": tgt["ev"],
                         "modal_cell": [q1["cells"][MODAL_S]["lo"],
                                        q1["cells"][MODAL_S]["hi"]],
                         "today_revenue": surface["ramp"]["today_implied"],
                         "target_revenue": surface["ramp"]["target_revenue"]},
            "anchors": {"q1_end": Q1END, "q2_end": Q2END, "target": TARGET_M},
            "fomc": FOMC, "months": MONTHS,
            "epistemic": "Cells are conditional values — the probabilities are "
                         "the model. Surface: operator report-v6 (revenue-"
                         "multiple basis, $105M anchor) + the stated even-"
                         "scaling ramp to the 2027-07-31 target. Estimates "
                         "condition on ~5 rate cycles and quarterly-lagged "
                         "deal data. Decision support, not advice."}


@router.post("/api/ewm/simulate")
def run_simulation(body: SimToggles):
    inp = load_inputs()
    p = _params_for(inp)
    live = live_snapshot(scenario_weights(p, inp.get("dissent_cluster", False)),
                         HIKES, inp.get("canary01"))
    res = _resolve(inp, live)
    p["stall_mult"] = res["stall_mult"]
    p = apply_weight_tilt(p, inp.get("weight_tilt"))
    toggles = body.model_dump()
    toggles["pin_report"] = toggles["pin_report"] or bool(inp.get("pin_report"))
    return simulate(p, inp, toggles)


@router.post("/api/ewm/inputs")
def set_inputs(body: Inputs):
    cur = load_inputs()
    changed = {k: v for k, v in body.model_dump().items() if v is not None}
    prev_rev = cur.get("revenue_dec2026")
    apply_t = changed.pop("apply_tilt", None)
    clear_t = changed.pop("clear_tilt", None)
    auto_upd = changed.pop("auto", None)
    # a manual POST of an auto-wired field is an explicit override: flip AUTO off
    auto = {**DEFAULT_INPUTS["auto"], **(cur.get("auto") or {}), **(auto_upd or {})}
    for f in ("fcix_z", "dmhi01", "stress_prob"):
        if f in changed and not (auto_upd or {}).get(f):
            auto[f] = False
            _log("auto_disabled_by_override", {"field": f, "value": changed[f]})
    cur["auto"] = auto
    cur.update(changed)
    if clear_t:
        cur["weight_tilt"] = None
        _log("tilt_cleared", {})
    elif apply_t:
        nc = live_snapshot(scenario_weights(_params_for(cur),
                                            cur.get("dissent_cluster", False)),
                           HIKES, cur.get("canary01")).get("nowcast")
        if nc and nc.get("suggested_tilt_pp"):
            cur["weight_tilt"] = {"toward": nc["voting_row"],
                                  "pp": abs(nc["suggested_tilt_pp"]),
                                  "basis": nc["source"],
                                  "d2_chg_3m_pp": nc["d2_chg_3m_pp"]}
            _log("tilt_applied", cur["weight_tilt"])
    json.dump(cur, open(_INPUTS, "w"))
    _log("inputs_changed", changed)
    if ("revenue_dec2026" in changed and prev_rev is not None
            and changed["revenue_dec2026"] > prev_rev):
        _log("revenue_raised", {"delta": changed["revenue_dec2026"] - prev_rev})
    return {"ok": True, "inputs": cur}


@router.get("/api/ewm/events")
def events(limit: int = 50):
    try:
        lines = open(_EVENTS).read().strip().split("\n")[-limit:]
        return [json.loads(x) for x in reversed(lines)]
    except Exception:  # noqa: BLE001
        return []


@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse, include_in_schema=False)
def index():
    return open(os.path.join(os.path.dirname(__file__), "static.html")).read()
