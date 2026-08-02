"""EWM API — serves the engine + a v1 single-page UI (deal-sensitive: deploy
behind the genomics login-gate proxy only)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .engine.core import (
    FOMC, MONTHS, PARAMS, action_cards, cost_of_delay, ev_surface,
    window_scores,
)

app = FastAPI(title="Exit Window Monitor", version="0.1.0")
DATA = os.environ.get("EWM_DATA_DIR", "./data")
os.makedirs(DATA, exist_ok=True)
_INPUTS = os.path.join(DATA, "inputs.json")
_EVENTS = os.path.join(DATA, "events.jsonl")

DEFAULT_INPUTS = {
    "ebitda_run_rate": PARAMS["ebitda_run_rate"], "stage": "prep",
    "dissent_cluster": False, "fcix_z": 0.1, "dmhi01": 0.55,
    "canary01": None, "stress_prob": 0.1, "qofe_ready": False,
    "today_month": "2026-09",
}


def load_inputs() -> dict:
    try:
        return {**DEFAULT_INPUTS, **json.load(open(_INPUTS))}
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_INPUTS)


def _log_event(kind: str, detail: dict) -> None:
    with open(_EVENTS, "a") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "kind": kind, "detail": detail}) + "\n")


def _canary01_live() -> float | None:
    base = os.environ.get("CANARY_UPSTREAM")
    if not base:
        return None
    try:
        r = httpx.get(f"{base.rstrip('/')}/composite", timeout=15)
        score = r.json().get("score")
        return round(score / 100.0, 3) if score is not None else None
    except Exception:  # noqa: BLE001
        return None


class Inputs(BaseModel):
    ebitda_run_rate: float | None = None
    stage: str | None = None
    dissent_cluster: bool | None = None
    fcix_z: float | None = None
    dmhi01: float | None = None
    stress_prob: float | None = None
    today_month: str | None = None


@app.get("/api/ewm/board")
def board():
    """Everything the v1 UI needs in one call."""
    inp = load_inputs()
    canary = inp.get("canary01")
    if canary is None:
        canary = _canary01_live() or 0.25
    surface = ev_surface(PARAMS, inp["ebitda_run_rate"], inp["dissent_cluster"])
    ws = window_scores(PARAMS, surface["weights"], inp["fcix_z"], inp["dmhi01"],
                       canary, inp["stage"], inp["today_month"])
    cod = cost_of_delay(surface["surface"], ws)
    cards = action_cards(PARAMS, {"hike_weights": surface["weights"],
                                  "fcix_z": inp["fcix_z"],
                                  "dissent_cluster": inp["dissent_cluster"],
                                  "stress_prob": inp["stress_prob"]})
    q1 = next(r for r in surface["surface"] if r["month"] == "2027-01")
    return {"inputs": inp, "canary01": canary, "surface": surface,
            "windows": ws, "cost_of_delay": cod, "cards": cards,
            "headline": {"weighted_ev_q1": q1["ev"], "p10": q1["p10"],
                         "p90": q1["p90"], "modal_lo": q1["by_scenario"][1],
                         "modal_hi": q1["by_scenario"][0]},
            "fomc": FOMC, "months": MONTHS,
            "epistemic": "Estimates condition on ~5 rate cycles and quarterly-"
                         "lagged deal data. Decision support, not advice. "
                         "Cohort surface: seeded-from-spec pending report-v6 "
                         "import."}


@app.post("/api/ewm/inputs")
def set_inputs(body: Inputs):
    cur = load_inputs()
    changed = {k: v for k, v in body.model_dump().items() if v is not None}
    prev_e = cur.get("ebitda_run_rate")
    cur.update(changed)
    json.dump(cur, open(_INPUTS, "w"))
    _log_event("inputs_changed", changed)
    if "ebitda_run_rate" in changed and prev_e is not None:
        d = changed["ebitda_run_rate"] - prev_e
        if d > 0:
            _log_event("ebitda_raised", {"delta": d})
    return {"ok": True, "inputs": cur}


@app.get("/api/ewm/events")
def events(limit: int = 50):
    try:
        lines = open(_EVENTS).read().strip().split("\n")[-limit:]
        return [json.loads(x) for x in reversed(lines)]
    except Exception:  # noqa: BLE001
        return []


@app.get("/health")
def health():
    return {"status": "ok", "service": "ewm"}


@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(os.path.dirname(__file__), "static.html")).read()
