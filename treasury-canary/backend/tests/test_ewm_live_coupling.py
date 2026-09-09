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


# ---------- DMHI on DEAL activity (replaces the credit proxy) ----------

def test_dmhi_is_built_from_deal_data_not_credit():
    """The DMHI carries w_dmhi = 0.20 and is named the Deal Market Health
    Index, but it was computed from inverted SLOOS plus the private-credit
    pin - two CREDIT measures with no deal data in them. Since fcix_z is an
    NFCI z-score and NFCI correlates +0.673 with SLOOS over 146 quarters,
    0.45 of the Window Score sat on one channel while deal activity carried
    0.00. This gate pins the replacement.
    """
    from app.ewm.live import dmhi_from_deal_activity
    d = dmhi_from_deal_activity()
    assert d is not None, "committed deal-activity series is missing"
    assert 0.0 <= d["value"] <= 1.0
    assert set(d["components"]) <= {"edgar_live", "hsr_anchor"}
    assert "edgar_live" in d["components"], "the LIVE leg must be present"
    assert "SLOOS" not in d["source"] and "pin" not in d["source"]


def test_hsr_anchor_is_damped_toward_neutral():
    """A ~10-month-lagged annual figure must not swing a monthly window
    score. The anchor is damped 0.5x toward 0.5 in the GF Data pattern, so
    it can never leave the middle half of the range however extreme the
    underlying percentile is."""
    from app.ewm.live import dmhi_from_deal_activity
    d = dmhi_from_deal_activity()
    a = d["components"].get("hsr_anchor")
    if a is not None:
        assert 0.25 <= a <= 0.75, f"anchor {a} escaped the damped band"


def test_deal_activity_series_are_lag_labelled():
    """Lag honesty is a SACRED item in the spec. Both legs must carry their
    lag in the committed data, because a 10-month-old annual number and a
    1-day-old filing count cannot be read the same way."""
    from app.ewm.live import _deal_activity
    da = _deal_activity()
    assert da is not None
    assert "10 month" in da["hsr_tier_150_300m"]["_lag"].lower().replace("~", "")
    assert "1 day" in da["edgar_merger_proxies"]["_lag"].lower().replace("~", "")
    # the proxy gap must be stated, not implied
    assert "PUBLIC-TARGET" in da["edgar_merger_proxies"]["_proxy_gap"]


def test_hsr_tier_needs_no_threshold_correction():
    """The tier floor is $150M and the HSR reporting threshold has never
    exceeded $133.9M, so every deal in this band was reportable in every
    year. The erosion that contaminates HSR's TOTAL count does not touch
    it. If someone later widens the tier below $150M this gate should fail
    and force them to think about it."""
    from app.ewm.live import _deal_activity
    da = _deal_activity()
    tier = da["hsr_tier_150_300m"]
    assert "150" in tier["_source"]
    assert "133.9" in tier["_why_no_threshold_correction"]
    fy = tier["by_fiscal_year"]
    assert len(fy) >= 30, "tier series should span three decades"
    assert all(int(v) >= 0 for v in fy.values())


def test_percentile_rank_refuses_thin_history():
    """A percentile against a handful of comparators is not a percentile."""
    from app.ewm.live import _pct_rank
    assert _pct_rank(5.0, [1.0, 2.0, 3.0]) is None
    assert _pct_rank(5.0, list(range(20))) is not None


def test_credit_dmhi_survives_only_as_a_labelled_fallback():
    """The old credit proxy is still reachable - a dead data file must not
    take the DMHI to None - but when it is used the provenance has to say
    so, or the UI would silently show a credit number as deal health."""
    from app.ewm.live import dmhi_from_sloos_pins
    d = dmhi_from_sloos_pins({"sloos": _series([10.0] * 4)})
    assert d is not None and "SLOOS" in d["source"]


# ---------- DEAL_STATE boom/stall bands ----------

def test_deal_state_reads_and_is_advisory_about_boom():
    """The bands the operator asked for: is the deal market booming or
    declining. Four states on the same EDGAR series the DMHI uses."""
    from app.ewm.deal_state import deal_state
    d = deal_state()
    assert d is not None
    assert d["state"] in {"BOOM", "NORMAL", "COOLING", "STALL"}
    # BOOM occupancy (10.9%) sits AT its own noise floor (9.5-13.4%), so it
    # must never be presented as actionable
    assert "ADVISORY" in d["note"]


def test_deal_state_never_enters_the_window_score():
    """Load-bearing gate. window_scores() takes fcix_z, dmhi01, canary01 and
    stage - deal_state is NOT among them, and must not become one without a
    deliberate recalibration. BOOM fires no more often on the real market
    than on a null series with the same persistence; wiring it into the
    score would be acting on noise."""
    import inspect
    from app.ewm.core import window_scores
    params = set(inspect.signature(window_scores).parameters)
    assert "deal_state" not in params
    assert not any("deal" in p for p in params)


def test_hsr_corroboration_is_publication_gated():
    """FY y is only readable from (y+1)Q3 - a ~10 month lag. Without the
    gate, standing at 2026Q2 the ledger hands back FY2025, which does not
    publish until 2026Q3: a live look-ahead leak. This bug was introduced
    once during porting and caught by inspection."""
    from app.ewm.deal_state import hsr_asof
    led = {2022: {}, 2023: {}, 2024: {}, 2025: {}}
    assert hsr_asof(led, (2026, 2)) == 2024, "FY2025 is not published yet"
    assert hsr_asof(led, (2026, 3)) == 2025, "FY2025 publishes in 2026Q3"
    # FY2023 publishes 2024Q3, so at 2024Q1 the newest readable is FY2022
    assert hsr_asof(led, (2024, 1)) == 2022
    assert hsr_asof(led, (2024, 3)) == 2023
    # nothing published yet -> None, and the caller must handle it
    assert hsr_asof({2025: {}}, (2020, 1)) is None


def test_hsr_ledger_lands_exactly_on_the_stall_years():
    """The arrears ledger's discriminating power is the reason it was
    grafted in: 4 corroborations in 32 evaluable years, landing on exactly
    the ground-truth stall list with zero extras, and declining every year
    across the declared not-a-stall window FY2012-2019."""
    from app.ewm.deal_state import hsr_ledger, _deal_activity
    led = hsr_ledger(_deal_activity()["hsr_tier_150_300m"]["by_fiscal_year"])
    fired = {y for y, r in led.items() if r["corroborates"]}
    assert fired == {2001, 2009, 2020, 2023}, fired
    assert not any(2012 <= y <= 2019 for y in fired)


def test_state_machine_cannot_latch_on_a_secular_decline():
    """THE bug this design exists to prevent. A series declining steadily at
    ANY rate, with no cycle in it, must read NORMAL forever - a percentile-
    on-level machine latched into 12 consecutive quarters of false STALL
    across 2012Q1-2015Q1. Every coordinate here is measured against the
    series' own trailing trend, so a log-linear trend is absorbed exactly by
    the OLS fit."""
    from app.ewm.deal_state import step
    state, pend = "NORMAL", None
    for _ in range(80):
        # steady decline -> drift-adjusted speed and trend deviation are 0
        state, pend = step(state, pend, 0.0, 0.0, 0.0)
    assert state == "NORMAL", f"latched to {state} on a pure trend"


def test_exits_are_not_confirmation_gated():
    """Entering a state that alters a sale decision needs 2 quarters; LEAVING
    a stall must be prompt. An exit held hostage to confirmation keeps the
    'market closed' flag up after it reopens."""
    from app.ewm.deal_state import step
    s, p = step("STALL", None, 0.0, 0.0, 0.0)
    assert s == "COOLING", "stall exit was confirmation-gated"


def test_boom_reversal_lands_in_cooling_not_normal():
    """A BOOM whose downside entry condition is already met has REVERSED,
    not lapsed. Routing it through NORMAL prints 'no signal' in the quarter
    the reversal is most extreme - it did exactly that at 2022Q3
    (zs = -1.98) before this correction."""
    from app.ewm.deal_state import step
    s, _ = step("BOOM", None, -1.98, -0.79, 0.5)
    assert s == "COOLING", f"reversal printed {s}"


def test_fast_chip_is_display_only():
    """The chip catches single-quarter air pockets the trailing-year measure
    is structurally blind to (2025Q2, z = -1.95). It fires 5.9% of the time,
    which is what an uncorrected pointwise 5% test does BY CONSTRUCTION, so
    it must never reach the state machine."""
    import inspect
    from app.ewm.deal_state import step
    src = inspect.getsource(step)
    assert "chip" not in src


# ---------- driver overlays ----------

def _fake_bundle():
    """Synthetic bundle: one driver that tracks a ramp, one that opposes it."""
    from datetime import date
    ds = [date(1998 + i // 4, 1 + 3 * (i % 4), 1) for i in range(112)]
    up = [float(i) for i in range(112)]
    return {"sloos": (ds, [-v for v in up]), "nfci": (ds, up), "2y": (ds, up)}


def test_drivers_are_served_as_z_scores_not_levels():
    """Two reasons that coincide. Overlays need ONE shared axis - a dual-axis
    chart can manufacture any apparent relationship by choice of scaling.
    And NFCI (Chicago Fed) and VIX (Cboe) are licence-restricted for
    redistribution as LEVELS, while a z-score is a derived statistic. If raw
    levels ever start being served this gate should fail."""
    from app.ewm.drivers import build
    out = build(_fake_bundle())
    assert out is not None
    for _label, ser in out["drivers"].items():
        vals = [v for v in ser.values()]
        assert vals, "empty driver series"
        # z-scores live in single digits; raw NFCI/VIX/yield levels would not
        assert max(abs(v) for v in vals) < 12, "looks like levels, not z"


def test_driver_zscore_is_causal():
    """Expanding window: the value at t is standardised only against history
    up to t. Appending future data must not change any past reading, or the
    overlay is a hindsight chart."""
    from app.ewm.drivers import _zscore
    base = {(2000 + i // 4, 1 + i % 4): float(i % 7) for i in range(40)}
    ext = dict(base)
    ext.update({(2020 + i // 4, 1 + i % 4): 999.0 for i in range(8)})
    a, b = _zscore(base), _zscore(ext)
    for k in a:
        assert abs(a[k] - b[k]) < 1e-12, f"look-ahead leak at {k}"


def test_rolling_correlation_tracks_a_decaying_relationship():
    """The whole point of the strip. A relationship that holds then breaks
    must show as a falling trailing correlation - a single full-sample number
    averages exactly that away."""
    from app.ewm.drivers import rolling_corr
    deal, drv = {}, {}
    for i in range(60):
        k = (2000 + i // 4, 1 + i % 4)
        deal[k] = float(i % 5)
        # tracks for the first half, then inverts
        drv[k] = deal[k] if i < 30 else -deal[k]
    r = rolling_corr(drv, deal, window=12)
    ks = sorted(r)
    assert r[ks[0]] > 0.8, "should start correlated"
    assert r[ks[-1]] < -0.5, "should end anti-correlated"


def test_inverted_drivers_are_flagged_and_oriented():
    """Every overlay must read UP = better for deals, or comparing two lines
    on one axis is meaningless. Inversion has to be declared, not silent."""
    from app.ewm.drivers import DRIVERS, build
    assert DRIVERS["lending standards"][1] is True, "tightening must invert"
    assert DRIVERS["2y yield"][1] is False
    out = build(_fake_bundle())
    assert out["meta"]["lending standards"]["inverted"] is True


def test_rates_are_documented_as_the_weak_driver():
    """Guards the finding against quiet reversion. Measured over 97 quarters,
    the 2y yield correlates -0.03 with deal activity's deviation from its own
    trend - indistinguishable from nothing - while bank lending standards
    lead by a quarter at -0.60. Rates are a confounded proxy, not a channel.
    The note must keep saying so."""
    from app.ewm.drivers import DRIVERS
    note = DRIVERS["2y yield"][2]
    assert "WEAK" in note and "-0.03" in note
    assert "confounded" in note


def test_drivers_degrade_rather_than_zero_fill():
    """A dead feed must drop that driver, never contribute zeros - a flat
    zero line reads as 'no relationship' when it means 'no data'."""
    from app.ewm.drivers import build
    out = build({})
    assert out is None or out["drivers"] == {}
