"""EWM validation gates (spec §7, merge-blocking) — v2, report-v6 surface.

G1 is now a REPORT-FIDELITY gate: with revenue pinned at the report's $105M
basis, the engine must reproduce the operator's cohort cells, weighted-EV
band ($186-193M) and modal cell ($192-200M) exactly, plus the memo's
closed-form breakeven numbers. The ramp, Dirichlet band and MC fan get their
own gates. Replays (G2/G3) use ONLY frozen as-of fixtures — no look-ahead."""
import json
import os

import numpy as np

from app.ewm.core import (
    HIKES, IDX, MODAL_S, MONTHS, PARAMS, Q1END, Q2END, REV_BASIS, SCEN,
    TARGET_M, action_cards, breakeven, cohort_surface, dirichlet_band,
    hold_premium, multiple_range, rate_risk, revenue_ramp, scenario_weights,
    slip_costs, weight_draws, window_scores,
)
from app.ewm.mc import simulate

FIX = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures_ewm_replays.json")))
COHORT = json.load(open(os.path.join(os.path.dirname(__file__),
                                     "..", "app", "ewm", "cohort_v6.json")))


def test_gate1_report_fidelity_pinned():
    """Revenue pinned at $105M -> the report table reproduces exactly."""
    s = cohort_surface(PARAMS, dissent_cluster=False, pin_report=True)
    q1 = next(r for r in s["surface"] if r["month"] == Q1END)
    q2 = next(r for r in s["surface"] if r["month"] == Q2END)
    for row in COHORT["scenarios"]:
        i = IDX[row["id"]]                                # report rows via hike count
        lo, hi = row["value_close_end_q1_2027_m"]
        assert abs(q1["cells"][i]["lo"] - lo) < 0.1 and abs(q1["cells"][i]["hi"] - hi) < 0.1, (i, q1["cells"][i])
        lo2, hi2 = row["value_close_end_q2_2027_m"]
        assert abs(q2["cells"][i]["lo"] - lo2) < 0.1 and abs(q2["cells"][i]["hi"] - hi2) < 0.1
    # report aggregates: weighted EV ~$186-193M, modal cell $192-200M
    assert 186.0 <= q1["ev"] <= 193.0, q1["ev"]
    assert q1["cells"][MODAL_S]["lo"] == 192.0 and q1["cells"][MODAL_S]["hi"] == 200.0
    # Q1'27 green-amber under calm inputs, process in market (4-month lead)
    ws = window_scores(PARAMS, PARAMS["hike_weights"], fcix_z=0.1, dmhi01=0.55,
                       canary01=0.25, stage="in_market", today_month="2026-09")
    q1w = next(w for w in ws if w["month"] == Q1END)
    assert q1w["band"] in ("GREEN", "AMBER") and q1w["feasible"]


def test_gate1b_breakeven_matches_memo_closed_forms():
    be = breakeven(PARAMS, pin_report=True)
    assert -1.3 <= be["dev_q1_minus_q2"] <= -0.8, be          # memo: -1.05 (Q2 ahead)
    assert 0.13 <= be["flips"]["shift_s1_to_s2_pp"] <= 0.19   # memo: ~16pp
    assert 0.08 <= be["flips"]["shift_s0_to_s3_pp"] <= 0.12   # memo: ~9.5pp
    assert 0.05 <= be["flips"]["extra_stall_pp"] <= 0.09      # memo: ~7pp
    assert be["preferred"] == "Q2" and be["sentence"]


def test_gate1c_ramp_hits_waypoints_and_target():
    ramp = revenue_ramp(PARAMS)
    assert abs(ramp["revenue"]["2026-12"] - PARAMS["revenue_dec2026"]) < 0.01
    rev = [ramp["revenue"][m] for m in MONTHS]
    assert all(b > a for a, b in zip(rev, rev[1:]))           # evenly scaling
    # on-pace: modal-path value at 2027-07 lands inside the $200-225M target
    v = multiple_range(PARAMS["ramp_scenario"], TARGET_M)[1] * ramp["revenue"][TARGET_M]
    assert PARAMS["target_value"][0] <= v <= PARAMS["target_value"][1], v
    # editable: raising the Dec-26 run-rate lifts every month's revenue
    p2 = {**PARAMS, "revenue_dec2026": 110.0}
    r2 = revenue_ramp(p2)
    assert r2["revenue"][Q1END] > ramp["revenue"][Q1END]


def test_gate1d_ranges_hawk_skewed_not_flat():
    """Cell ranges must come from the report (hawk rows widest), not flat noise."""
    s = cohort_surface(PARAMS, pin_report=True)
    q1 = next(r for r in s["surface"] if r["month"] == Q1END)
    widths = [c["hi"] - c["lo"] for c in q1["cells"]]
    hawk_w = [widths[i] for i, h in enumerate(HIKES) if h >= 2]
    dove_w = [widths[i] for i, h in enumerate(HIKES) if h <= 1]
    assert max(hawk_w) > max(dove_w) + 5, widths              # hawk rows widest
    assert q1["ev_lo"] < q1["ev"] < q1["ev_hi"]


def test_gate1e_dirichlet_band_mean_preserving_and_deterministic():
    band1 = dirichlet_band(PARAMS, pin_report=True)
    band2 = dirichlet_band(PARAMS, pin_report=True)
    assert band1 == band2                                      # seeded
    s = cohort_surface(PARAMS, pin_report=True)
    for row, b in zip(s["surface"], band1["band"]):
        assert b["p10"] <= row["ev"] <= b["p90"], (row["month"], b, row["ev"])
    rng = np.random.default_rng(3)
    w = weight_draws(PARAMS, False, 20000, rng)
    assert np.allclose(w.mean(0), scenario_weights(PARAMS, False), atol=0.005)


def test_gate1f_mc_fan_toggles():
    inp = {"dissent_cluster": False, "today_month": "2026-09"}
    base = simulate(PARAMS, inp, {})
    assert base == simulate(PARAMS, inp, {})                   # deterministic
    fq1 = next(r for r in base["fan"] if r["month"] == Q1END)
    assert fq1["p10"] < fq1["p50"] < fq1["p90"]
    # forced 4-hike path, pinned: fan inside the report's row-4 Q1 cell (+/- stall recut)
    f4 = next(r for r in simulate(PARAMS, inp, {"force_hikes": 4, "pin_report": True})["fan"]
              if r["month"] == Q1END)
    lo, hi = COHORT["scenarios"][4]["value_close_end_q1_2027_m"]
    assert lo * 0.93 <= f4["p10"] and f4["p90"] <= hi + 0.5, f4
    # severe crash compresses the median materially
    fc = next(r for r in simulate(PARAMS, inp, {"crash": "severe"})["fan"]
              if r["month"] == Q1END)
    assert fc["p50"] < fq1["p50"] * 0.80, (fc["p50"], fq1["p50"])
    # 50bp regime branch: pinned Q1 fan inside the report's $145-170M gap band
    fr = next(r for r in simulate(PARAMS, inp, {"regime_50bp": True, "pin_report": True})["fan"]
              if r["month"] == Q1END)
    assert 145 * 0.93 <= fr["p10"] and fr["p90"] <= 170.5, fr
    assert fr["p_no_deal"] > 0.01                              # 40% stall x 13% death x exposure


def test_gate1g_scenario_count_stress():
    """Memo e3: the preferred window must be stable under (i) tail rows merged
    and (ii) row 2 split into benign/tight halves — else the answer is
    scenario-structure noise."""
    def pref(weights, q1cells, q2cells):
        ev1 = sum(w * v for w, v in zip(weights, q1cells))
        ev2 = sum(w * v for w, v in zip(weights, q2cells))
        return "Q1" if ev1 > ev2 else "Q2"

    q1 = [sum(s["value_close_end_q1_2027_m"]) / 2 for s in COHORT["scenarios"]]
    q2 = [sum(s["value_close_end_q2_2027_m"]) / 2 for s in COHORT["scenarios"]]
    w = [s["probability"] for s in COHORT["scenarios"]]
    base = pref(w, q1, q2)
    # (i) tail merged at weight-average value
    wt = w[3] + w[4]
    q1m = q1[:3] + [(w[3] * q1[3] + w[4] * q1[4]) / wt]
    q2m = q2[:3] + [(w[3] * q2[3] + w[4] * q2[4]) / wt]
    assert pref(w[:3] + [wt], q1m, q2m) == base
    # (ii) row 2 split into halves of its range
    s2 = COHORT["scenarios"][2]
    q1s = q1[:2] + [s2["value_close_end_q1_2027_m"][1] - 2.5,
                    s2["value_close_end_q1_2027_m"][0] + 2.5] + q1[3:]
    q2s = q2[:2] + [s2["value_close_end_q2_2027_m"][1] - 2.875,
                    s2["value_close_end_q2_2027_m"][0] + 2.875] + q2[3:]
    ws = w[:2] + [w[2] / 2, w[2] / 2] + w[3:]
    assert pref(ws, q1s, q2s) == base


def _replay(tag):
    """Walk the fixture month by month using only data <= t (no look-ahead):
    hike pressure from trailing 3m 2y-yield change; financing stress from the
    HY proxy's z vs its own trailing history."""
    f = FIX[tag]
    rows = []
    for i in range(3, len(f["months"])):
        d2_chg_3m = f["dgs2"][i] - f["dgs2"][i - 3]
        hy_hist = f["hy_oas_proxy_bp"][:i + 1]
        mu = sum(hy_hist) / len(hy_hist)
        sd = (sum((x - mu) ** 2 for x in hy_hist) / len(hy_hist)) ** 0.5 or 1.0
        hy_z = (hy_hist[-1] - mu) / sd
        # map to engine inputs: hawkish surprise pressure -> tail-heavy weights
        if d2_chg_3m > 0.75:
            hw = [0.00, 0.05, 0.10, 0.25, 0.35, 0.25]
        elif d2_chg_3m > 0.25:
            hw = [0.00, 0.15, 0.30, 0.30, 0.15, 0.10]
        else:
            hw = [0.05, 0.30, 0.35, 0.20, 0.07, 0.03]
        fcix = max(-1.0, min(2.0, hy_z + (0.5 if d2_chg_3m > 0.75 else 0.0)))
        vix01 = min(1.0, max(0.0, (f["vix"][i] - 12) / 25))
        dmhi01 = max(0.0, 0.5 - 0.2 * max(hy_z, 0.0))
        ws = window_scores(PARAMS, hw, fcix_z=fcix, dmhi01=dmhi01,
                           canary01=vix01, stage="prep", today_month="2026-09")
        # acceleration proxy: hawkish repricing underway (2y +40bp/3m fired
        # Dec-2021, never fired in 2019 — see fixture debug values)
        cards = action_cards(PARAMS, {"hike_weights": hw, "fcix_z": fcix,
                                      "dissent_cluster": d2_chg_3m > 0.4,
                                      "stress_prob": 0.1 + 0.2 * max(hy_z, 0)})
        rows.append({"asof": f["months"][i],
                     "min_score": min(w["score"] for w in ws),
                     "median_band": sorted(w["band"] for w in ws)[len(ws) // 2],
                     "urgent": any("Accelerate" in c["action"] or
                                   "hard deadline" in c["action"] for c in cards)})
    return rows


def test_gate2_2022_replay_turns_red_and_accelerates():
    rows = _replay("replay2022")
    by = {r["asof"]: r for r in rows}
    # windows red by Q1-2022 (min window score in RED territory)
    assert by["2022-03"]["min_score"] < PARAMS["amber_min"], by["2022-03"]
    # acceleration recommended by Q4-2021 (2y already ripping vs priced path)
    q4_21 = [r for r in rows if r["asof"] in ("2021-10", "2021-11", "2021-12")]
    assert any(r["urgent"] for r in q4_21), q4_21


def test_gate3_2019_placebo_stays_calm():
    # score 2019 proper: Jan/Feb still carry the Q4-2018 selloff hangover in
    # the trailing-z warmup (documented; the 'benign year' claim is 2019)
    rows = [r for r in _replay("placebo2019") if r["asof"] >= "2019-03"]
    # benign easing year: no month's minimum score reaches RED, no urgent cards
    assert all(r["min_score"] >= PARAMS["amber_min"] - 5 for r in rows), rows[-3:]
    assert not any(r["urgent"] for r in rows), [r for r in rows if r["urgent"]]


def test_gate4_feasibility_and_trigger_logging():
    for stage, lead in PARAMS["lead_by_stage"].items():
        ws = window_scores(PARAMS, PARAMS["hike_weights"], 0.0, 0.5, 0.3,
                           stage, "2026-09")
        infeasible = [w["month"] for w in ws if not w["feasible"]]
        assert len(infeasible) == min(lead, len(MONTHS)), (stage, infeasible)
    # every card carries a machine-checkable trigger string
    cards = action_cards(PARAMS, {"hike_weights": [0.0, 0.1, 0.1, 0.3, 0.3, 0.2],
                                  "fcix_z": 1.0, "dissent_cluster": True,
                                  "stress_prob": 0.3, "revenue_delta": 1.0,
                                  "breakeven": {"within_5pp_of_flip": True,
                                                "dev_q1_minus_q2": -0.4}})
    assert len(cards) == 6 and all(c["trigger"] for c in cards)


def test_dissent_bump_tail_only_and_gate1_safe():
    w0 = scenario_weights(PARAMS, False)
    w1 = scenario_weights(PARAMS, True)
    assert w1[IDX[3]] > w0[IDX[3]] and w1[IDX[4]] > w0[IDX[4]]   # tail up
    assert all(w1[IDX[h]] < w0[IDX[h]] for h in (-1, 0, 1))      # funded from doves
    assert abs(sum(w1) - 1.0) < 1e-9
    s = cohort_surface(PARAMS, dissent_cluster=True, pin_report=True)
    q1 = next(r for r in s["surface"] if r["month"] == Q1END)
    assert 184.0 <= q1["ev"] <= 193.0                     # tail bump stays in band


def test_slip_costs_cliff_and_hold_premium():
    s = cohort_surface(PARAMS)
    w = scenario_weights(PARAMS, False)
    sl = slip_costs(PARAMS, s["surface"], "prep", "2026-09", w)
    # stage prep (6mo lead) from Sep-26: earliest close IS Q1-end -> the
    # Q1 option dies after ONE month of slippage
    assert sl["rows"][0]["earliest_close"] == Q1END and sl["rows"][0]["q1_open"]
    assert sl["cliff_months"] == 1 and not sl["rows"][1]["q1_open"]
    # hawk-conditional slip costs are monotone non-decreasing
    hc = [r["hawk_cost"] for r in sl["rows"]]
    assert all(b >= a for a, b in zip(hc, hc[1:])) and hc[0] == 0.0
    # sign-by precedes the close by the tilt-dependent gap; hawk tilt >30%
    # at base weights -> 4.5-month gap
    assert sl["gap_months"] == PARAMS["gap_months_hawkish"]
    assert sl["q1"]["sign_by"] < Q1END and sl["q2"]["sign_by"] < Q2END
    # unsigned event exposure grows with the later window
    assert sl["q2"]["fomc_to_sign"] > sl["q1"]["fomc_to_sign"]
    assert sl["forfeit_hawk_value"] >= 0.0
    # a later stage relaxes the cliff: in_market (4mo lead) tolerates 2 slips
    sl2 = slip_costs(PARAMS, s["surface"], "in_market", "2026-09", w)
    assert sl2["cliff_months"] == 3 and sl2["rows"][2]["q1_open"]
    # hold premium unchanged by the slip refactor
    hp = hold_premium(s["surface"])
    tgt = next(h for h in hp if h["month"] == TARGET_M)
    assert tgt["premium"] == 0.0
    q1p = next(h for h in hp if h["month"] == Q1END)
    assert q1p["premium"] > 0


def test_cut_extension_row():
    """v2.1: benign-easing cut row is an EXTENSION (tagged, not report), 5pp
    carved from the holds row; report probabilities otherwise preserved."""
    cut = SCEN[IDX[-1]]
    assert cut["source"] != "report-v6" and cut["stall_p"] == 0.0
    w = PARAMS["hike_weights"]
    assert abs(sum(w) - 1.0) < 1e-9
    assert w[IDX[-1]] == 0.05 and w[IDX[0]] == 0.25          # carve from holds
    for row in COHORT["scenarios"][1:]:                      # other rows untouched
        assert w[IDX[row["id"]]] == row["probability"]
    # cut row sits above the holds row and keeps the +5M dove drift
    s = cohort_surface(PARAMS, pin_report=True)
    q1 = next(r for r in s["surface"] if r["month"] == Q1END)
    q2 = next(r for r in s["surface"] if r["month"] == Q2END)
    assert q1["cells"][IDX[-1]]["mid"] > q1["cells"][IDX[0]]["mid"]
    assert q2["cells"][IDX[-1]]["mid"] > q1["cells"][IDX[-1]]["mid"]
    # forced-cut MC fan lands inside the cut cell at Q1-end (pinned)
    fcut = next(r for r in simulate(PARAMS, {"today_month": "2026-09"},
                                    {"force_hikes": -1, "pin_report": True})["fan"]
                if r["month"] == Q1END)
    assert 205 * 0.93 <= fcut["p10"] and fcut["p90"] <= 218.5, fcut
