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

from .core import (FOMC, MODAL_S, MONTHS, PARAMS, Q1END, Q2END, TARGET_M,
                   action_cards, breakeven, cohort_surface, cost_of_delay,
                   dirichlet_band, hold_premium, window_scores)
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
                  "qofe_ready": False, "today_month": "2026-09"}


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
    """In-process composite read (no self-HTTP: same service)."""
    try:
        from ..jobs.refresh import compute_all
        from ..store.db import session_scope
        with session_scope() as s:
            comp = compute_all(s).get("composite")
        score = comp.get("score") if isinstance(comp, dict) else getattr(comp, "score", None)
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
    pin = bool(inp.get("pin_report"))
    surface = cohort_surface(p, inp["dissent_cluster"], pin_report=pin)
    be = breakeven(p, inp["dissent_cluster"], pin_report=pin)
    band = dirichlet_band(p, inp["dissent_cluster"], pin_report=pin)
    hp = hold_premium(surface["surface"])
    ws = window_scores(p, surface["weights"], inp["fcix_z"], inp["dmhi01"],
                       canary, inp["stage"], inp["today_month"])
    cod = cost_of_delay(surface["surface"], ws)
    cards = action_cards(p, {"hike_weights": surface["weights"],
                             "fcix_z": inp["fcix_z"],
                             "dissent_cluster": inp["dissent_cluster"],
                             "stress_prob": inp["stress_prob"],
                             "breakeven": be})
    q1 = next(r for r in surface["surface"] if r["month"] == Q1END)
    q2 = next(r for r in surface["surface"] if r["month"] == Q2END)
    tgt = next(r for r in surface["surface"] if r["month"] == TARGET_M)
    return {"inputs": inp, "canary01": canary, "surface": surface,
            "breakeven": be, "weight_band": band, "hold_premium": hp,
            "windows": ws, "cost_of_delay": cod, "cards": cards,
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
    toggles = body.model_dump()
    toggles["pin_report"] = toggles["pin_report"] or bool(inp.get("pin_report"))
    return simulate(p, inp, toggles)


@router.post("/api/ewm/inputs")
def set_inputs(body: Inputs):
    cur = load_inputs()
    changed = {k: v for k, v in body.model_dump().items() if v is not None}
    prev_rev = cur.get("revenue_dec2026")
    cur.update(changed)
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
