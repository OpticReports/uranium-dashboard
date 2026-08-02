"""Gates for the canary->EWM live coupling (CANARY_COUPLING memo, operator-
approved build). Everything runs offline: bundles are synthetic, the live
snapshot is monkeypatched at the API layer."""
from datetime import date, timedelta

from app.ewm.core import (HIKES, IDX, PARAMS, Q1END, apply_weight_tilt,
                          breakeven, cohort_surface)
from app.ewm.live import (FIN, NOW, dmhi_from_sloos_pins, fcix_from_nfci,
                          financing_state, headwind_chip, path_nowcast)
from app.ewm.mc import simulate


def _series(vals):
    d0 = date(2026, 1, 1)
    return ([d0 + timedelta(days=i) for i in range(len(vals))], list(vals))


# ---------- financing state machine (hysteresis) ----------

def test_financing_states_and_hysteresis():
    flat = [300.0] * 100
    assert financing_state({"hy_oas": _series(flat)}, "BENIGN")["state"] == "BENIGN"
    # level trigger: TIGHT at 400, stays TIGHT at 380 (inside band), releases <375
    assert financing_state({"hy_oas": _series([300] * 50 + [410] * 50)}, "BENIGN")["state"] == "TIGHT"
    assert financing_state({"hy_oas": _series([380] * 100)}, "TIGHT")["state"] == "TIGHT"
    assert financing_state({"hy_oas": _series([370] * 100)}, "TIGHT")["state"] == "BENIGN"
    # speed trigger: +160bp over 90d shuts the window even at a modest level
    ramp = [300 + i * 2.6 for i in range(100)]             # ~+165bp over 63 obs
    st = financing_state({"hy_oas": _series(ramp)}, "BENIGN")
    assert st["state"] == "SHUT" and st["stall_mult"] == round(5 / 3, 3)
    # SHUT releases only below 425 AND slow: 440 flat stays SHUT (level in band)
    assert financing_state({"hy_oas": _series([440] * 100)}, "SHUT")["state"] == "SHUT"
    assert financing_state({"hy_oas": _series([410] * 100)}, "SHUT")["state"] == "TIGHT"


def test_stall_mult_moves_breakeven_and_fan():
    """SHUT financing (x5/3 hawk stall) must lower stall-adjusted EV and show
    up in the MC fan's no-deal odds — the channel the evidence supports."""
    base = cohort_surface(PARAMS, pin_report=True)
    shut = cohort_surface({**PARAMS, "stall_mult": 5 / 3}, pin_report=True)
    for b, s in zip(base["surface"], shut["surface"]):
        assert s["ev_stall_adj"] <= b["ev_stall_adj"]
        assert s["ev"] == b["ev"]                          # raw EV untouched
    inp = {"today_month": "2026-09"}
    f_base = next(r for r in simulate(PARAMS, inp, {"force_hikes": 4, "pin_report": True})["fan"]
                  if r["month"] == Q1END)
    f_shut = next(r for r in simulate({**PARAMS, "stall_mult": 5 / 3}, inp,
                                      {"force_hikes": 4, "pin_report": True})["fan"]
                  if r["month"] == Q1END)
    assert f_shut["p_no_deal"] > f_base["p_no_deal"]


# ---------- weight tilt (bounded, renormalized, never silent) ----------

def test_weight_tilt_bounded_and_normalized():
    p2 = apply_weight_tilt(PARAMS, {"toward": 2, "pp": 0.03})
    w0, w2 = PARAMS["hike_weights"], p2["hike_weights"]
    assert abs(sum(w2) - 1.0) < 1e-9
    assert abs(w2[IDX[2]] - (w0[IDX[2]] + 0.03)) < 1e-6
    assert all(w2[i] < w0[i] for i in range(len(w0)) if i != IDX[2])
    # cap: a 20pp request clips to 5pp
    p3 = apply_weight_tilt(PARAMS, {"toward": 3, "pp": 0.20})
    assert abs(p3["hike_weights"][IDX[3]] - (w0[IDX[3]] + 0.05)) < 1e-6
    # no-ops: empty tilt, unknown row
    assert apply_weight_tilt(PARAMS, None) is PARAMS
    assert apply_weight_tilt(PARAMS, {"toward": 9, "pp": 0.03}) is PARAMS
    # a hawk tilt moves the breakeven toward Q1 (hawk rows favor closing early)
    be0 = breakeven(PARAMS, pin_report=True)
    be2 = breakeven(apply_weight_tilt(PARAMS, {"toward": 3, "pp": 0.05}),
                    pin_report=True)
    assert be2["dev_q1_minus_q2"] > be0["dev_q1_minus_q2"]


# ---------- nowcast (gate-validated proxy thresholds + hysteresis) ----------

def test_nowcast_votes_and_hysteresis():
    def bump(pp):                                          # 2y path: +pp over last 63 obs
        return {"2y": _series([4.0] * 40 + [4.0 + pp * (i + 1) / 63 for i in range(63)])}
    assert path_nowcast(bump(0.0), "BENIGN", 1)["voting_row"] == 1
    assert path_nowcast(bump(0.5), "BENIGN", 1)["voting_row"] == 2   # accelerate proxy
    assert path_nowcast(bump(0.9), "BENIGN", 1)["voting_row"] == 3
    assert path_nowcast(bump(-0.4), "BENIGN", 1)["voting_row"] == -1
    # financing state conditions the lean band
    assert path_nowcast(bump(0.3), "TIGHT", 1)["voting_row"] == 2
    assert path_nowcast(bump(0.3), "BENIGN", 1)["voting_row"] == 1
    # hysteresis: 0.42 from prior row 1 steps up, but 0.42 from prior row 2
    # does NOT step down when 0.42-0.10 would re-vote row 2's boundary
    assert path_nowcast(bump(0.42), "BENIGN", 1)["voting_row"] == 2
    assert path_nowcast(bump(0.38), "BENIGN", 2)["voting_row"] == 2  # sticky
    assert path_nowcast(bump(0.10), "BENIGN", 2)["voting_row"] == 1  # clean release
    # tilt is bounded by the cap
    assert abs(path_nowcast(bump(1.2), "BENIGN", 1)["suggested_tilt_pp"]) <= NOW["tilt_pp_max"]


# ---------- input mappers ----------

def test_fcix_and_dmhi_mappers():
    # NFCI trailing z: a spike above a long calm history reads tight (+z)
    calm = [-0.5] * 200 + [0.3] * 5
    f = fcix_from_nfci({"nfci": _series(calm)})
    assert f is not None and f["value"] > 1.0
    assert fcix_from_nfci({"nfci": _series([-0.5] * 10)}) is None   # too short
    # dmhi: SLOOS 0 -> healthy 1.0; SLOOS 40+ -> 0; missing feeds -> None
    d = dmhi_from_sloos_pins({"sloos": _series([0.0] * 4)})
    assert d is not None and d["components"]["sloos"] == 1.0
    d2 = dmhi_from_sloos_pins({"sloos": _series([44.0] * 4)})
    assert d2["components"]["sloos"] == 0.0
    assert dmhi_from_sloos_pins({}) is None


def test_headwind_chip_ajsw():
    hw = headwind_chip({"hy_oas": _series([284.0] * 70)})
    assert hw["delta_bp"] == 0 and hw["multiple_pct"] == 0.0
    hw2 = headwind_chip({"hy_oas": _series([284.0] * 10 + [384.0] * 60)})
    assert hw2["delta_bp"] == 100 and abs(hw2["multiple_pct"] - (-4.8)) < 0.01


# ---------- API resolution: AUTO uses live, MANUAL wins, dead feed falls back ----------

def test_api_auto_manual_precedence(monkeypatch, tmp_path):
    import app.ewm.api as api
    monkeypatch.setattr(api, "_INPUTS", str(tmp_path / "inputs.json"))
    monkeypatch.setattr(api, "_EVENTS", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(api, "_canary01", lambda: 0.30)
    live = {"fcix": {"value": 1.5, "source": "NFCI-z"},
            "dmhi": {"value": 0.8, "source": "sloos+pins"},
            "spike_pos": {"value": True, "state": "SPIKE", "regime": "POS",
                          "source": "panel"},
            "financing": {"state": "TIGHT", "hy_bp": 420, "d90_bp": 30,
                          "stall_mult": round(4 / 3, 3), "source": "hy"},
            "headwind": None,
            "nowcast": {"voting_row": 2, "suggested_tilt_pp": 0.03,
                        "d2_chg_3m_pp": 0.5, "source": "2y"},
            "stress": {"value": 0.4, "source": "sim"}}
    monkeypatch.setattr(api, "live_snapshot", lambda w, h, c: live)
    b = api.board()
    assert b["resolved"]["fcix_z"] == 1.5 and "AUTO" in b["resolved"]["provenance"]["fcix_z"]
    assert b["resolved"]["stall_mult"] == round(4 / 3, 3)
    assert b["resolved"]["spike_pos"] is True
    # SPIKExPOS denies GREEN on every feasible window
    assert all(w["score"] <= 69.0 for w in b["windows"])
    # financing card present, stress card present (0.4 > 0.25)
    acts = " | ".join(c["action"] for c in b["cards"])
    assert "Financing window" in acts and "hard deadline" in acts
    # manual override flips AUTO off and wins
    api.set_inputs(api.Inputs(fcix_z=-0.5))
    b2 = api.board()
    assert b2["resolved"]["fcix_z"] == -0.5
    assert b2["resolved"]["provenance"]["fcix_z"] == "MANUAL/stored"
    # re-enable AUTO
    api.set_inputs(api.Inputs(auto={"fcix_z": True}))
    assert api.board()["resolved"]["fcix_z"] == 1.5
    # tilt: apply stores the bounded suggestion, board reweights, clear removes
    api.set_inputs(api.Inputs(apply_tilt=True))
    b3 = api.board()
    assert b3["inputs"]["weight_tilt"]["toward"] == 2
    w = b3["surface"]["weights"]
    assert w[IDX[2]] > PARAMS["hike_weights"][IDX[2]] + 0.02
    api.set_inputs(api.Inputs(clear_tilt=True))
    assert api.board()["inputs"]["weight_tilt"] is None
    # dead feed: every live leg None -> stored defaults, MANUAL provenance
    monkeypatch.setattr(api, "live_snapshot",
                        lambda w, h, c: {k: None for k in live})
    b4 = api.board()
    assert b4["resolved"]["provenance"]["fcix_z"] == "MANUAL/stored"
    assert b4["resolved"]["stall_mult"] == 1.0 and b4["resolved"]["spike_pos"] is False
