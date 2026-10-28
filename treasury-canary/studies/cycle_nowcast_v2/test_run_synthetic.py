"""Cycle nowcast v2 — end-to-end dry run of run_study.py on SYNTHETIC inputs (task B3).

  python3 -m pytest studies/cycle_nowcast_v2/test_run_synthetic.py -q     (offline, < 90 s)

What is proved: run_study.py --synthetic end to end on two bundles (noisy, zero-noise) with
the known expectations synthetic.py documents; the DECISION / DESCRIPTIVE tagging of every
results field; the refusal paths (--real without CNV2_SCORED_RUN=1, missing freeze.json, an
unfrozen freeze, a hash mismatch, an existing results.json, usage errors); determinism (two
runs byte-identical except `generated`); and the guard: no scoring function accepts real
panels from this module (StudyInputs refuses provenance 'real' unless armed by a FROZEN
freeze + the environment flag, and refuses synthetic inputs whose manifest hash mismatches).
NEVER passes --real with a real F5; never sets CNV2_SCORED_RUN=1 in a subprocess environment. The
fix-pass guards that only --real reaches (M2 output guard, M3 correction-input check, M6 committed
state, S2 unrevised re-check, M4 raw-vintage integrity) are exercised in-process on temporary dirs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import engine as E            # noqa: E402
import run_study as RS        # noqa: E402
import scoring as S           # noqa: E402
import synthetic as SY        # noqa: E402
import vintages as V          # noqa: E402

PY = sys.executable
SYN = os.path.join(HERE, "synthetic.py")
RUN = os.path.join(HERE, "run_study.py")
DRYRUN = os.path.join(HERE, "dryrun_synthetic_results.json")


def _env():
    env = dict(os.environ)
    env.pop(S.ENV_FLAG, None)                 # never armed in a dry run
    return env


def _run(args, env=None):
    p = subprocess.run([PY, RUN] + args, capture_output=True, text=True, env=env or _env())
    return p.returncode, p.stdout + p.stderr


def _load(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def bundles(tmp_path_factory):
    root = tmp_path_factory.mktemp("cnv2_b3")
    noisy, zero, noisy2 = os.path.join(root, "noisy"), os.path.join(root, "zero"), os.path.join(root, "noisy2")
    gen = [subprocess.Popen([PY, SYN, "--out", noisy], stdout=subprocess.PIPE, stderr=subprocess.PIPE),
           subprocess.Popen([PY, SYN, "--out", zero, "--zero-noise"], stdout=subprocess.PIPE, stderr=subprocess.PIPE),
           subprocess.Popen([PY, SYN, "--out", noisy2], stdout=subprocess.PIPE, stderr=subprocess.PIPE)]
    for p in gen:
        out, err = p.communicate()
        assert p.returncode == 0, err.decode()[-2000:]
    # the generator is reproducible: a second generation hashes identically (every file, the workbook included)
    assert _load(os.path.join(noisy, "hashes.json")) == _load(os.path.join(noisy2, "hashes.json"))
    shutil.rmtree(noisy2)
    runs = [(noisy, os.path.join(root, "res_a.json")), (noisy, os.path.join(root, "res_b.json")), (zero, os.path.join(root, "res_zero.json"))]
    procs = [subprocess.Popen([PY, RUN, "--synthetic", b, "--out", o], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=_env())
             for b, o in runs]
    logs = [p.communicate() for p in procs]
    for p, (b, o), (so, se) in zip(procs, runs, logs):
        assert p.returncode == 0, (o, se[-3000:])
        assert os.path.exists(o)
    return {"root": root, "noisy": noisy, "zero": zero, "man_noisy": _load(os.path.join(noisy, "manifest.json")),
            "man_zero": _load(os.path.join(zero, "manifest.json")), "res_a_path": runs[0][1], "res_b_path": runs[1][1],
            "res_a": _load(runs[0][1]), "res_b": _load(runs[1][1]), "res_zero": _load(runs[2][1]), "logs": logs}


# ----------------------------------------------------------------------------- 1. the dry run and its decisions
def test_dry_run_completes_with_the_known_decisions(bundles):
    a, z = bundles["res_a"], bundles["res_zero"]
    for r in (a, z):
        assert r["mode"] == "synthetic" and r["scored_real_data"] is False
        assert r["gates"]["F1_reproduction"]["blocking"] == []
        assert set(r["gates"]["F1_reproduction"]["hard_fail_ids"]) <= set(RS.RULED_DESCRIPTIVE)
        assert r["inputs"]["hash_verification"]["mismatches"] == 0 and r["inputs"]["hash_verification"]["checked"] > 10
        assert r["tag_audit"]["n_untagged"] == 0
        assert r["freeze"]["source"].startswith("freeze_template.json DEFAULTS")
        assert r["section_order"] == list(S.SECTION_ORDER)
    # noisy: the ensemble beats persistence by far (D-1 PASS), completion beats the partial mean (D-2 PASS),
    # and the near-exact synthetic ADS wins the comparator by more than Y with DM significance (D-3 KILL)
    # (SPEC v1.2: the frozen reading is same_outcome_class, so D-3 is KILL only when the class under
    # target_first agrees with the class under target_latest, else DEFERRED - both recorded)
    cu_a = a["results"]["decision_D3"]["class_under_target_first"]["value"]
    expect_d3 = "KILL" if cu_a["class_first"] == cu_a["class_latest"] else "DEFERRED"
    assert cu_a["class_latest"] == "KILL"
    assert (a["decisions"]["D1_primary"], a["decisions"]["D2_completed_vs_partial"], a["decisions"]["D3_comparator"]) == ("PASS", "PASS", expect_d3)
    # zero-noise: exact members -> D-1 PASS; the partial 3-member mean is itself exact -> D-2 FAIL by construction;
    # ENS error ~0 against a noisy ADS -> D-3 SUCCESS
    assert (z["decisions"]["D1_primary"], z["decisions"]["D2_completed_vs_partial"], z["decisions"]["D3_comparator"]) == ("PASS", "FAIL", "SUCCESS")
    assert "FAIL" not in a["decisions"]["consequences"]["D1"] and "secondary line" in z["decisions"]["consequences"]["D2"]


# ----------------------------------------------------------------------------- 2. known structure: lag simulation
def test_lag_simulation_known_expectations(bundles):
    a, z = bundles["res_a"]["results"], bundles["res_zero"]["results"]
    # zero noise: every member is an exact affine function of g_PAYEMS, -g6(ICSA) == g_PAYEMS, all baselines
    # identical -> COIN == z_claims6 exactly -> the CLAIMS_HH fit is exact at every IS; the IS-C completion
    # of M-1 is the identity; the bridge error is only the z-baseline term (projection z against history
    # through M-L, DT-11), which is O(1/n) and far below the noisy bundle's error
    for IS in "ABC":
        zb, ab = z["lag_simulation"]["per_is"][IS], a["lag_simulation"]["per_is"][IS]
        assert max(zb["CLAIMS_HH"]["rmse_full_1990_ex2020"]["value"]) < 1e-5, (IS, zb["CLAIMS_HH"]["rmse_full_1990_ex2020"]["value"])
        assert zb["BRIDGE_HH"]["rmse_full_1990_ex2020"]["value"][1] < 0.03
        assert zb["ENS_HH"]["rmse_full_1990_ex2020"]["value"][0] < 0.3 * ab["ENS_HH"]["rmse_full_1990_ex2020"]["value"][0]
        assert zb["ENS_HH"]["claims_fallback_months"]["value"] == 0
        assert ab["ENS_HH"]["onsets"]["value"]["summary"]["missed"] == 0
    assert z["lag_simulation"]["per_is"]["C"]["completed_COIN_prev"]["rmse_vs_realized_full_ex2020"]["value"] == [0.0, 0.0]
    # the projection itself is exact (coefficients (alpha, 0, beta) for every lag) on the zero-noise F5
    f5 = E.load_fred_csv_dir(os.path.join(bundles["zero"], "f5"))
    ds = E.build(f5)
    i = ds.i("2019-06")
    for c, L in (("INDPRO", 1), ("W875RX1", 2), ("CMRMTSPL", 3)):
        zz, st, info = E.bridge_member(ds, i, c, L, "scoring")
        assert st == "bridged" and abs(info["proj_g"] - ds.G[c][i]) < 1e-8
        assert abs(info["beta"][0] - SY.ALPHA[c]) < 1e-7 and abs(info["beta"][1]) < 1e-7 and abs(info["beta"][2] - SY.BETA[c]) < 1e-7
    # the §3 diagnostic holds on both bundles (more actual members -> lower error), on every aggregate
    for r in (a, z):
        d = r["lag_simulation"]["diagnostic_rmse_A_ge_B_ge_C"]["value"]
        assert d["holds"] and all(v["holds"] for v in d["aggregates"].values())
        agg = d["aggregates"]["rmse"]
        assert agg["A"] >= agg["B"] >= agg["C"]
    # window: 1972-01 .. the last complete COIN month of F5 (CMRMTSPL ends two months before PAYEMS)
    man = bundles["man_noisy"]
    assert a["windows"]["scored_window"]["value"] == ["1972-01", man["f5_last_months"]["CMRMTSPL"]]
    assert a["windows"]["n_targets"]["value"] == E.mdiff(man["f5_last_months"]["CMRMTSPL"], "1972-01") + 1
    # persistence baselines are descriptive and enter no criterion; the D-1 numbers quote PERS = realized COIN(M-1)
    assert a["lag_simulation"]["per_is"]["A"]["baselines_descriptive"]["tag"] == "DESCRIPTIVE"
    assert "realized COIN(M-1)" in a["decision_D1"]["conditions"]["basis"]


# ----------------------------------------------------------------------------- 3. bands
def test_bands_known_n_widths_and_coverage(bundles):
    a, z = bundles["res_a"]["results"], bundles["res_zero"]["results"]
    pats = a["bands"]["patterns"]
    k1, k2, k3 = (E.pattern_key({"CMRMTSPL": 1}), E.pattern_key({"W875RX1": 1, "CMRMTSPL": 2}),
                  E.pattern_key({"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2}))
    hi = a["windows"]["scored_window"]["value"][1]
    n_primary = E.mdiff(hi, "1990-01") + 1 - 12                       # 1990-01..hi ex the 12 months of 2020
    for k in (k1, k2, k3):
        p = pats[k]["value"]
        assert p["primary_window"] == "primary_1990_ex2020" and p["primary_1990_ex2020"]["n"] == n_primary, (k, p["primary_1990_ex2020"])
        assert p["primary_1990_ex2020"]["p10"] < 0 < p["primary_1990_ex2020"]["p90"]
        cov = p["walk_forward_coverage_1990_ex2020"]
        assert cov["n"] > 300 and 0.6 < cov["share"] < 0.95             # a p10-p90 band covers ~80% walk-forward
    width = lambda k: pats[k]["value"]["primary_1990_ex2020"]["p90"] - pats[k]["value"]["primary_1990_ex2020"]["p10"]  # noqa: E731
    assert width(k1) < width(k2) < width(k3)                             # more bridged members -> wider band
    # the dropped-member band (v1 §2.4) keys on the dropped set and its PRIMARY window is 1977-07+ ex-2020
    kd = E.pattern_key({}, dropped=["CMRMTSPL"])
    assert kd in pats and pats[kd]["value"]["dropped_set"] and pats[kd]["value"]["primary_window"] == "sens_1977_ex2020"
    # board dict: p10/p90 per key with >= 24 errors, consumed by engine.issue(bands=...)
    bb = bundles["res_a"]["board_bands"]
    assert k1 in bb and bb[k1]["n"] >= 24 and bb[k1]["p10"] == pats[k1]["value"]["primary_1990_ex2020"]["p10"]
    r = E.issue(E.load_fred_csv_dir(os.path.join(bundles["noisy"], "f5")), "2026-10-20", bands=bb)
    assert r["completed_prev"]["band"] is not None and r["completed_prev"]["band"][0] < r["completed_prev"]["value"] < r["completed_prev"]["band"][1]
    # zero noise: bands collapse to the z-baseline term
    assert width(k1) > 3 * (z["bands"]["patterns"][k1]["value"]["primary_1990_ex2020"]["p90"] - z["bands"]["patterns"][k1]["value"]["primary_1990_ex2020"]["p10"])
    # D-2 is computed on the SAME 1977-07+ months, full and ex-2020
    d2 = a["decision_D2"]["rmse"]["value"]
    assert d2["pass_full"] and d2["pass_ex2020"] and d2["completed_full"] < d2["partial_full"]
    assert a["decision_D2"]["outcome"]["window"][0] == "1977-07"


# ----------------------------------------------------------------------------- 4. row admission / regime (i)
def test_regime_i_known_lags_K_and_shutdown_flags(bundles):
    a, man = bundles["res_a"]["results"], bundles["man_noisy"]
    exp = man["structure"]["expected_issue_states"]
    cards = a["regime_i"]["scorecards"]["value"]
    assert len(cards) > 90 and a["regime_i"]["basis"]["value"]["is_label_mismatches_panel_vs_engine"] == []
    matched = 0
    for s in cards:
        e = exp.get(s["issue_date"] + "|" + s["IS"])
        if e is None:
            continue
        matched += 1
        assert s["lags"] == e["lags"] and s["K"] == e["K"] and s["M"] == e["M"], s["issue_date"]
        # the CLAIMS_HH fit ends at K(d); canonical rows have K = M-2 (A, B) / M-1 (C)
        assert s["claims_fit"]["rows_through"] == s["K"]
        if s["flags"]["canonical"]:
            assert s["K"] == E.madd(s["M"], -2 if s["IS"] in "AB" else -1)
    assert matched > 90
    by = {(s["issue_date"], s["IS"]): s for s in cards}
    # the synthetic shutdown: CMRMTSPL at lag 3 on the first payrolls day, dropped (lag 4) on the next two
    assert by[("2019-01-04", "A")]["lags"] == {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 3} and by[("2019-01-04", "A")]["flags"]["lag_ge3"] == ["CMRMTSPL"]
    for d in ("2019-02-01", "2019-03-01"):
        s = by[(d, "A")]
        assert s["lags"] == {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 2, "CMRMTSPL": 4} and s["dropped"] == ["CMRMTSPL"]
        assert s["ens_hh"] is not None and s["flags"]["in_shutdown_window"] and s["flags"]["nonstandard_prev_pattern"]
        assert "CMRMTSPL" not in s["members_bridged"] and s["pattern_key_target"].endswith("|dropped[CMRMTSPL]|skipped[]")
    assert all(s["ens_hh"] is not None for s in cards)                  # a reading on every issue date, shutdown included
    # stores (D4): one completion per IS per month, stored at its own issue date; spliced history counts
    for IS in "ABC":
        st = a["regime_i"]["per_is"][IS]["value"]
        assert st["store"]["n_stored"] == st["n_rows"] and st["flag_counts"]["no_nowcast"] == 0
    last = [s for s in cards if s["IS"] == "A"][-1]
    assert last["regressor_history"]["n_stored_used"] > 20 and last["regressor_history"]["n_recomputed"] > 300
    # completion rows (trigger month != M) are a separate table, never a second nowcast row: the delayed
    # W875RX1(2018-12) printing on the 2019-02 payrolls day is one; W875RX1(2019-01) was overtaken by the
    # on-time 2019-02 print (same day) and is never a vintage's latest month (never_latest, no issue date)
    comp = a["regime_i"]["completions"]["value"]
    assert a["regime_i"]["completions"]["n"] == 1 and comp[0]["issue_date"] == "2019-03-01" and comp[0]["trigger_month"] == "2018-12" < comp[0]["M"]
    assert by[("2019-03-29", "C")]["flags"]["canonical"]                    # the 03-29 vintage carries 2019-02 (and CMRMTSPL 2019-01)
    with open(os.path.join(bundles["noisy"], "vintages", "panel", "issue_dates.csv")) as f:
        import csv
        nl = {(r["series"], r["month"]) for r in csv.DictReader(f) if r["status"] == "never_latest"}
    assert ("W875RX1", "2019-01") in nl
    # flags counted per IS; shutdown-window rows at every IS
    assert sum(a["regime_i"]["per_is"][IS]["value"]["flag_counts"]["dropped"] for IS in "ABC") == 4
    assert a["honesty"]["regime_i_counts_per_is"]["value"]["A"]["in_shutdown_window"] >= 3


def test_target_first_vs_latest_known_revision_mechanism(bundles):
    a, z = bundles["res_a"]["results"], bundles["res_zero"]["results"]
    za = [s for s in z["regime_i"]["scorecards"]["value"] if s["target_first"] is not None]
    assert len(za) > 60 and max(abs(s["target_first"] - s["target_latest"]) for s in za) == 0.0     # no revisions -> identical
    assert z["honesty"]["f1_vs_f5_realized_drift"]["value"]["rms"] == 0.0
    na = [s for s in a["regime_i"]["scorecards"]["value"] if s["target_first"] is not None]
    diffs = [abs(s["target_first"] - s["target_latest"]) for s in na]
    assert len(na) > 90 and np.mean(diffs) > 0.01                                                     # first prints revise
    # the only months whose first full print equals the latest are the shutdown months: CMRMTSPL(2018-11/12)
    # first appear inside the multi-month 2019-03-29 vintage, by which date every member is past its first print
    zero_m = sorted({s["M"] for s, d in zip(na, diffs) if d == 0})
    assert zero_m and all("2018-10" <= m <= "2018-12" for m in zero_m), zero_m
    assert all(d > 0 for s, d in zip(na, diffs) if s["flags"]["canonical"] and not ("2018-10" <= s["M"] <= "2019-01"))
    assert all(s["target_first_complete"] for s in na) and all(s["target_first_vintage"] >= s["M"] for s in na)
    dr = a["honesty"]["f1_vs_f5_realized_drift"]["value"]
    assert dr["rms"] > 0 and dr["max_abs_month"] == bundles["man_noisy"]["f1_last_months"]["CMRMTSPL"]  # the F1 first print
    assert a["honesty"]["ens_hh_IS_A_on_F1"]["tag"] == "DESCRIPTIVE"
    # D11: which recessions each regime contains (the synthetic spells: 2001-04 and 2008-01 pseudo, 2020-03 true real-time)
    rr = a["honesty"]["recessions_per_regime"]["value"]
    assert rr["regime_ii_pseudo_real_time"] == ["2001-04", "2008-01"] and rr["regime_i_true_real_time"] == ["2020-03"]
    assert rr["lag_simulation"][-1] == "2020-03" and len(rr["lag_simulation"]) >= 6
    # D5 / N7 / D8: skipped rows are listed (none here), the PERS baseline is labelled final-vintage, raw vintages verified (M4)
    rb = a["regime_i"]["basis"]["value"]
    assert rb["rows_skipped_no_vintage"] == [] and rb["n_rows_skipped_no_vintage"] == 0 and rb["raw_vintages_verified_against_f6_table"] is True
    assert "FINAL-VINTAGE" in a["regime_i"]["per_is"]["A"]["basis"] and "hindsight" in a["regime_i"]["per_is"]["A"]["basis"]


# ----------------------------------------------------------------------------- 5. comparator and D-3
def test_ads_calibration_recovers_the_affine_map_and_d3_outcomes(bundles):
    a, z = bundles["res_a"]["results"], bundles["res_zero"]["results"]
    sa, sz = bundles["man_noisy"]["structure"]["ads"], bundles["man_zero"]["structure"]["ads"]
    Az, Aa = z["comparator"]["per_is"]["A"]["value"], a["comparator"]["per_is"]["A"]["value"]
    # COIN(t) ~ 1 + ADS_avg(t): slope 1/b, intercept -a/b
    assert abs(Az["last_cal_coef_ads"][1] - sz["cal_slope"]) < 0.02 * sz["cal_slope"] and abs(Az["last_cal_coef_ads"][0] - sz["cal_intercept"]) < 0.02
    assert abs(Aa["last_cal_coef_ads"][1] - sa["cal_slope"]) < 0.05 * sa["cal_slope"]
    assert abs(Az["last_cal_coef_ens"][1] - 1.0) < 0.01                 # the identical affine step on an exact ENS_HH is ~identity
    assert Az["last_cal_n"] >= 24 and Aa["last_cal_n"] >= 24
    assert Az["r_ens_over_ads"]["ex2020"] < 0.2 and z["decision_D3"]["outcome"]["value"] == "SUCCESS"
    assert Aa["r_ens_over_ads"]["ex2020"] > 1.25 and a["decision_D3"]["dm_one_sided_ex2020"]["value"]["kill_cand_worse"] is True
    # M7: DESCRIPTIVE DM records carry no verdict; the D-3 verdict is computed in decide_d3 from t
    for blk in (Aa, a["regime_i"]["per_is"]["A"]["value"]["dm_vs_pers_latest"]):
        for dmrec in ([blk["dm_one_sided_ens_worse"]["ex2020"], blk["dm_one_sided_ens_worse"]["with2020"]] if "dm_one_sided_ens_worse" in blk else [blk["full"], blk["ex2020"]]):
            assert "kill_cand_worse" not in dmrec and "primary_pass_cand_better" not in dmrec and "t" in dmrec
    # S1/D1: the calibration warm-up is stated per IS, in the D-3 outcome basis and in the honesty box
    assert Aa["first_row_month"] < Aa["first_calibrated_month"] and Aa["n_rows_without_calibration"] >= 24
    assert Aa["calibration_store"] == S.CAL_STORE_IMPLEMENTED and Aa["spec_expected_n_ex2020"] == 145
    b3 = a["decision_D3"]["outcome"]["basis"]
    assert "calibration warm-up" in b3 and "Q16" in b3 and f"n ≈ {S.SPEC_D3_EXPECTED_N_EX2020}" in b3 and Aa["first_calibrated_month"] in b3
    assert a["honesty"]["d3_calibration_warmup"]["value"]["A"]["first_calibrated_month"] == Aa["first_calibrated_month"]
    assert a["decision_D3"]["calibration_warmup"]["tag"] == "DESCRIPTIVE"
    # D6 / Q17 (RULED, SPEC v1.2): both classes recorded; the frozen reading is same_outcome_class
    cu = a["decision_D3"]["class_under_target_first"]["value"]
    assert cu["reading_used"] == "same_outcome_class" and cu["class_latest"] == "KILL" and cu["class_first"] in ("SUCCESS", "MIDDLE", "KILL")
    assert bundles["res_a"]["decisions"]["D3_comparator"] == ("KILL" if cu["class_first"] == "KILL" else "DEFERRED")
    assert a["decision_D3"]["margins"]["value"] == {"X_pct": 10.0, "Y_pct": 25.0, "success_if_r_le": 1.1, "kill_if_r_gt": 1.25,
                                                    "freeze_source": a["decision_D3"]["margins"]["value"]["freeze_source"]}
    assert a["decision_D3"]["r_with2020_reported_never_decides"]["tag"] == "DESCRIPTIVE"
    # the first 24 months at each IS have no calibrated reading (stored readings accumulate) — and the per-IS
    # block states exactly that warm-up (first_calibrated_month, n_rows_without_calibration)
    rows = a["comparator"]["rows"]["value"]
    first_cal = {IS: next(r["M"] for r in rows if r["IS"] == IS and r["ads_cal"] is not None) for IS in "ABC"}
    first_row = {IS: next(r["M"] for r in rows if r["IS"] == IS) for IS in "ABC"}
    for IS in "ABC":
        assert E.mdiff(first_cal[IS], first_row[IS]) >= 24
        blk = a["comparator"]["per_is"][IS]["value"]
        assert blk["first_calibrated_month"] == first_cal[IS] and blk["first_row_month"] == first_row[IS]
        assert blk["n_rows_without_calibration"] == sum(1 for r in rows if r["IS"] == IS and r["ads_cal"] is None)
        assert blk["n_rows_at_is"] == sum(1 for r in rows if r["IS"] == IS)
    # sensitivities: '< d' and smoothed-fit differ from the primary (the archive revises its end-point);
    # claims-only exclusion equals the primary (no claims-only vintage in the synthetic archive)
    sens = a["comparator_sensitivities"]
    r0 = Aa["r_ens_over_ads"]["ex2020"]
    assert sens["strict_lt_d"]["per_is"]["A"]["value"]["r_ens_over_ads"]["ex2020"] != r0
    assert sens["smoothed_fit"]["per_is"]["A"]["value"]["r_ens_over_ads"]["ex2020"] != r0
    assert sens["excl_claims_only"]["per_is"]["A"]["value"]["r_ens_over_ads"]["ex2020"] == r0
    assert a["comparator"]["basis"]["value"]["n_claims_only_readings"] == 0
    # the margins are read from the freeze: widen Y -> MIDDLE; widen X -> SUCCESS; sign disagreement -> DEFERRED
    comp = {"_per_is": {"A": Aa}}
    assert S.decide_d3(comp, {"X_pct": 10, "Y_pct": 1e6})["outcome"]["value"] == "MIDDLE"
    assert S.decide_d3(comp, {"X_pct": 1e6, "Y_pct": 2e6})["outcome"]["value"] == "SUCCESS"
    flipped = {"_per_is": {"A": {**Aa, "vs_target_first": {**Aa["vs_target_first"], "r_ex2020": 0.5}}}}
    assert S.decide_d3(flipped, {"X_pct": 10, "Y_pct": 25})["outcome"]["value"] == "DEFERRED"
    nd = S.decide_d3({"_per_is": {"A": {}}}, {"X_pct": 10, "Y_pct": 25})
    assert nd["outcome"]["value"] == "NOT_DECIDABLE" and "n/a" in nd["outcome"]["basis"]                       # N4: rf None is stated
    # Q17 readings: the literal sign reading decides KILL here (both ratios > 1); the class reading defers when the
    # class under target_first differs from the class under target_latest; an unknown reading is refused
    comp = {"_per_is": {"A": Aa}}
    rd_sign = S.decide_d3(comp, {"X_pct": 10, "Y_pct": 25, "target_first_agreement": "sign_of_r_minus_1"})["outcome"]["value"]
    rd_cls = S.decide_d3(comp, {"X_pct": 10, "Y_pct": 25, "target_first_agreement": "same_outcome_class"})
    assert rd_sign == "KILL"
    assert rd_cls["outcome"]["value"] == ("KILL" if cu["class_first"] == "KILL" else "DEFERRED")
    with pytest.raises(ValueError):
        S.decide_d3(comp, {"X_pct": 10, "Y_pct": 25, "target_first_agreement": "whatever"})
    # the freeze must carry Q16 / Q17 for a scored run (validate_freeze); the implemented store is the only supported answer
    fz = {k: v for k, v in _load(RS.TEMPLATE).items() if not k.startswith("_")}
    fz.update({"status": "FROZEN", "answered_by": "test", "answered_on": "2026-10-20"})
    assert S.validate_freeze(fz, require_frozen=True) == []
    assert any("comparator_calibration_store" in p for p in S.validate_freeze({k: v for k, v in fz.items() if k != "comparator_calibration_store"}, True))
    assert any("engine change" in p for p in S.validate_freeze({**fz, "comparator_calibration_store": "seeded_from_2008_12_ads_archive_pseudo_ens"}, True))
    assert any("target_first_agreement" in p for p in S.validate_freeze({**fz, "target_first_agreement": "sign"}, True))
    # D-2 FAIL branch on constructed inputs (completed worse than partial)
    months = [E.madd("1990-01", k) for k in range(60)]
    fake = {"_d2": {"months_mask": np.ones(60, bool), "months": months, "e_completed": np.full(60, 0.2), "e_partial": np.full(60, 0.1)}}
    assert S.decide_d2(fake, {})["outcome"]["value"] == "FAIL"


# ----------------------------------------------------------------------------- 6. regime (ii), Chauvet-Piger, availability
def test_regime_ii_points_follow_the_synthetic_lists(bundles):
    a = bundles["res_a"]["results"]["regime_ii"]
    assert a["basis"]["value"]["months_without_point"] == {"A": [], "B": [], "C": []}
    # M1: the proxy's evidence — list-proxy dates vs the content-decided F6 issue dates over the regime-(i) months
    ag = a["basis"]["value"]["list_proxy_vs_content_decided_regime_i_months"]
    assert set(ag) == {"PAYEMS", "INDPRO", "W875RX1"}
    for sid, t in ag.items():
        assert t["n_months"] >= 30 and t["n_mismatch"] == 0 and t["n_agree"] == t["n_months"] and t["mismatches"] == [], sid
    assert "<= <M+3>-01" in a["basis"]["value"]["proxy_window"]
    for row in a["tables"]["A"]["value"][:24]:
        assert row["issue_date"] == SY.first_friday(E.madd(row["M"], 1))
    for row in a["tables"]["B"]["value"][:24]:
        assert row["issue_date"] == SY.day_of(E.madd(row["M"], 1), 15)
    for row in a["tables"]["C"]["value"]:
        assert row["issue_date"] == SY.day_of(E.madd(row["M"], 1), 28)
        assert ("W875RX1" in row["source"]) == (row["issue_date"] >= S.W875_OWN_DATES_FROM)
    cr = a["crossings_calendar_clock"]["value"]
    assert [c["onset"] for c in cr] == ["2001-04", "2008-01"] and all(c["realized_cross_date"] and c["ens_hh_cross_date"] for c in cr)
    assert all(c["ens_hh_cross_date"] < c["realized_cross_date"] for c in cr)       # the nowcast is dated before the full print
    assert a["ads_alignment_2009plus"]["value"]["n"] > 6 and a["ads_alignment_2009plus"]["value"]["corr_ads_avg_vs_realized"] > 0.9


def test_chauvet_piger_known_declarations(bundles):
    cp = bundles["res_a"]["results"]["chauvet_piger"]
    pe = bundles["man_noisy"]["structure"]["piger_expected"]
    decl = cp["declarations_3x80"]["value"]
    start = next(d for d in decl if d["kind"] == "start")
    end = next(d for d in decl if d["kind"] == "end")
    assert start["release_date"] == pe["start_release"] and start["trigger_months"] == pe["start_trigger"]
    assert start["model_first_recession_month"] == pe["first_recession_month"] and start["model_peak_month"] == pe["peak_month"]
    assert start["nber_peak_month"] == "2007-12" and start["days_vs_nber_announcement"] == 0 and start["months_after_nber_peak"] == 9
    assert start["ours"]["pseudo_real_time"] is True and start["days_vs_our_ens_hh_crossing"] > start["days_vs_our_realized_crossing"] > 0
    assert end["release_date"] == pe["end_release"] and end["model_trough_month"] == pe["trough_month"] == end["nber_trough_month"]
    assert cp["onsets_never_declared_3x80"]["value"] == ["2020-03"]
    fires = [(f["release_date"], f["latest_month"]) for f in cp["sensitivity_1m50"]["value"]["firing_releases"]]
    assert [(d, m) for d, m in fires if m.startswith("2020")] == [("2020-06-01", "2020-03"), ("2020-07-01", "2020-04")]
    lg = cp["largest_non_recession_print"]["value"]
    assert lg["latest_month"] == "2021-09" and abs(lg["pct"] - 44.0) < 1e-9
    gl = cp["alfred_glitch_flags"]["value"]["anomalies_gt_1pp"]
    assert len(gl) == 1 and gl[0]["alfred_vintage_date"] == pe["glitch_vintage"]
    assert cp["basis"]["value"]["header_corrections"] == [{"as_in_file": "2018-01-01", "corrected": "2019-01-01"}]
    assert all(v["tag"] == "DESCRIPTIVE" for v in cp.values())


def test_availability_table(bundles):
    av = bundles["res_a"]["results"]["availability"]
    allm = av["all_2013_06plus"]["value"]
    assert allm["share_days"]["v2"] == 1.0 and allm["share_days"]["ads"] == 1.0 and 0.25 < allm["share_days"]["deployed"] < 0.45
    freq = av["lag_pattern_frequency_days"]["value"]
    assert allm["days_with_dropped_member"] == sum(v for k, v in freq.items() if "CMRMTSPL:4" in k) > 0
    assert av["shutdown_2025_10_to_2026_04"]["value"] is None            # the synthetic window has no 2025-26 months
    assert av["dropped_member_frequency_issue_rows"]["value"]["CMRMTSPL"] == 4


# ----------------------------------------------------------------------------- 7. tagging
def _walk(o, path, inside, found, untagged):
    if isinstance(o, dict):
        if "tag" in o and "value" in o:
            found.append(("/".join(path), o))
            inside = True
        for k, v in o.items():
            _walk(v, path + [str(k)], inside, found, untagged)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _walk(v, path + [str(i)], inside, found, untagged)
    elif isinstance(o, (int, float)) and not isinstance(o, bool) and not inside:
        untagged.append("/".join(path))


def test_every_results_field_is_tagged_decision_or_descriptive(bundles):
    for key in ("res_a", "res_zero"):
        R = bundles[key]["results"]
        found, untagged = [], []
        _walk(R, [], False, found, untagged)
        assert untagged == []
        assert len(found) > 200
        for path, rec in found:
            assert rec["tag"] in (S.DECISION, S.DESCRIPTIVE), path
            assert set(rec) == {"tag", "value", "basis", "n", "window", "spec"}, path
            assert isinstance(rec["basis"], str) and rec["basis"], path
        decisions = sorted(p for p, r in found if r["tag"] == S.DECISION)
        expected = sorted([
            "decision_D1/outcome", "decision_D1/conditions", "decision_D1/consequence",
            "decision_D2/outcome", "decision_D2/rmse", "decision_D2/consequence",
            "decision_D3/outcome", "decision_D3/r_ex2020", "decision_D3/margins", "decision_D3/dm_one_sided_ex2020", "decision_D3/consequence",
            "lag_simulation/per_is/A/ENS_HH/rmse_full_1990_ex2020", "lag_simulation/per_is/A/ENS_HH/pct_vs_pers_full_1990_ex2020",
            "lag_simulation/per_is/A/ENS_HH/dm_vs_pers_t_full_ex2020"])
        assert decisions == expected, decisions
        for sec in ("regime_i", "regime_ii", "comparator", "availability", "chauvet_piger", "honesty", "bands"):
            assert all(r["tag"] == S.DESCRIPTIVE for p, r in found if p.startswith(sec + "/")), sec


# ----------------------------------------------------------------------------- 8. refusals
def test_refusal_paths(bundles, tmp_path):
    noisy = bundles["noisy"]
    env_on = dict(_env())
    env_on[S.ENV_FLAG] = "1"
    out = str(tmp_path / "never_written.json")
    # --real without the environment flag: refused before anything is read
    rc, log = _run(["--real", "--f5", os.path.join(noisy, "f5"), "--freeze", RS.TEMPLATE, "--out", out])
    assert rc == RS.EXIT["guard"] and S.ENV_FLAG in log and not os.path.exists(out)
    # flag set, no freeze.json
    rc, log = _run(["--real", "--f5", os.path.join(noisy, "f5"), "--freeze", str(tmp_path / "missing.json"), "--out", out], env=env_on)
    assert rc == RS.EXIT["guard"] and "freeze.json" in log and not os.path.exists(out)
    # flag set, the template (not FROZEN, no answered_by): refused
    rc, log = _run(["--real", "--f5", os.path.join(noisy, "f5"), "--freeze", RS.TEMPLATE, "--out", out], env=env_on)
    assert rc == RS.EXIT["guard"] and "FROZEN" in log and not os.path.exists(out)
    # --skip-f1-gate with --real is a usage error
    rc, log = _run(["--real", "--f5", os.path.join(noisy, "f5"), "--freeze", RS.TEMPLATE, "--skip-f1-gate", "--out", out])
    assert rc == RS.EXIT["usage"] and not os.path.exists(out)
    # existing results.json: refused, the file untouched
    before = open(bundles["res_a_path"], "rb").read()
    rc, log = _run(["--synthetic", noisy, "--out", bundles["res_a_path"]])
    assert rc == RS.EXIT["exists"] and "--correction" in log and open(bundles["res_a_path"], "rb").read() == before
    # --correction without an original
    rc, log = _run(["--synthetic", noisy, "--out", out, "--correction", "typo in a label"])
    assert rc == RS.EXIT["usage"] and not os.path.exists(out)
    # missing / invalid freeze with --synthetic
    rc, log = _run(["--synthetic", noisy, "--out", out, "--freeze", str(tmp_path / "nope.json")])
    assert rc == RS.EXIT["freeze"]
    bad = dict(_load(RS.TEMPLATE))
    bad["shutdown_rule"] = "carry_forward"
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    rc, log = _run(["--synthetic", noisy, "--out", out, "--freeze", str(tmp_path / "bad.json")])
    assert rc == RS.EXIT["freeze"] and "carry_forward" in log and not os.path.exists(out)
    # hash mismatch: a tampered F5 file in a copy of the bundle
    tam = str(tmp_path / "tampered")
    shutil.copytree(noisy, tam)
    with open(os.path.join(tam, "f5", "PAYEMS.csv"), "a") as f:
        f.write("2026-10-01,1\n")
    rc, log = _run(["--synthetic", tam, "--out", out])
    assert rc == RS.EXIT["hash"] and "PAYEMS.csv" in log and not os.path.exists(out)
    # the write itself never overwrites
    p = tmp_path / "once.json"
    RS.write_once(str(p), {"a": 1})
    with pytest.raises(FileExistsError):
        RS.write_once(str(p), {"a": 2})
    path, rec = RS.resolve_output(str(p), "re-labelled a basis string")
    assert path.endswith("once.correction-1.json") and rec["k"] == 1 and rec["supersedes"] == "once.json"
    # a later correction supersedes the LATEST file, and still does so once the original is retired from the tree
    RS.write_once(path, {"a": 1, "correction": rec})
    path2, rec2 = RS.resolve_output(str(p), "second")
    assert path2.endswith("once.correction-2.json") and rec2["k"] == 2 and rec2["supersedes"] == "once.correction-1.json"
    p.unlink()
    path3, rec3 = RS.resolve_output(str(p), "third")
    assert path3.endswith("once.correction-2.json") and rec3["supersedes"] == "once.correction-1.json"
    with pytest.raises(RS.Refusal):
        RS.resolve_output(str(p), None)                                    # a correction exists: never a fresh original


def test_fix_pass_guards_and_helpers(bundles, tmp_path):
    """D2, M1, M2, M3, M4, M6, N2, S2: the helpers run_study.py --real goes through, exercised in-process on
    temporary directories — the environment flag is never set and no real panel is scored."""
    assert S.ENV_FLAG not in os.environ or os.environ[S.ENV_FLAG] != "1"
    noisy = bundles["noisy"]
    # D2: an unreadable / incomplete manifest refuses (4) instead of a traceback
    empty = tmp_path / "empty_data"
    empty.mkdir()
    with pytest.raises(RS.Refusal) as ei:
        RS.expected_hashes_real(str(empty))
    assert ei.value.kind == "hash" and ei.value.code == RS.EXIT["hash"]
    with pytest.raises(RS.Refusal) as ei:
        RS.expected_hashes_synthetic(str(empty))
    assert ei.value.kind == "hash"
    # M5: --ads-matrix enters the expected set with ads_hashes.json's matrix_sha256 (the bundle's ads_hashes.json carries one)
    data_like = tmp_path / "data_like"
    (data_like / "ads_panel").mkdir(parents=True)
    shutil.copy(os.path.join(noisy, "ads", "ads_hashes.json"), data_like / "ads_panel" / "ads_hashes.json")
    with pytest.raises(RS.Refusal):                       # the other manifests are missing -> still a labelled refusal
        RS.expected_hashes_real(str(data_like), os.path.join(noisy, "ads", "ads_monthly_matrix.npz"))
    # M1: the list-proxy window is inclusive of the 1st of M+3
    assert V.list_proxy_issue_dates(["2019-03-01"], ["2018-12"], "W875RX1") == {"2018-12": "2019-03-01"}
    assert V.list_proxy_issue_dates(["2019-03-02"], ["2018-12"], "W875RX1") == {"2018-12": None}
    assert V.list_proxy_issue_dates(["2019-01-19", "2019-01-20"], ["2018-12"], "W875RX1") == {"2018-12": "2019-01-20"}
    # M2: one scored run per study directory
    here = tmp_path / "study"
    here.mkdir()
    assert RS.real_output_guard(str(here / "results.json"), None, here=str(here)) == str(here / "results.json")
    with pytest.raises(RS.Refusal) as ei:
        RS.real_output_guard(str(tmp_path / "elsewhere.json"), None, here=str(here))
    assert ei.value.kind == "usage"
    (here / "results.json").write_text("{}")
    with pytest.raises(RS.Refusal) as ei:
        RS.real_output_guard(str(here / "results_other.json"), None, here=str(here))
    assert ei.value.kind == "exists" and ei.value.code == RS.EXIT["exists"]
    with pytest.raises(RS.Refusal) as ei:
        RS.real_output_guard(str(here / "results_other.json"), "a reason", here=str(here))
    assert ei.value.kind == "usage"
    assert RS.real_output_guard(str(here / "results.json"), "a reason", here=str(here)) == str(here / "results.json")
    (here / "results.json").unlink()
    (here / "corrections.log").write_text("")
    with pytest.raises(RS.Refusal) as ei:
        RS.real_output_guard(str(here / "results.json"), None, here=str(here))
    assert ei.value.kind == "exists"
    # M3: a correction run must share every input hash and the freeze with the file it supersedes
    hashes = {"F1": {"a": "1"}, "F5": {"PAYEMS.csv": "2"}, "F6_F7_F8_verified": {"x": "3"}, "piger_history": "4", "nber_turning_points": "5",
              "ads_matrix": None, "spec_md": "6", "code": {"scoring.py": "7"}}
    orig = tmp_path / "orig.json"
    orig.write_text(json.dumps({"inputs": {"hashes": hashes}, "freeze": {"sha256": "F"}, "run_id": "R0"}))
    rec = RS.check_correction_inputs({"k": 1, "reason": "label"}, str(orig), {**hashes, "code": {"scoring.py": "8"}, "spec_md": "9"}, {"sha256": "F"})
    assert rec["inputs_identical"] and rec["superseded_run_id"] == "R0" and rec["code_identical"] is False and rec["spec_md_identical"] is False
    with pytest.raises(RS.Refusal) as ei:
        RS.check_correction_inputs({"k": 1}, str(orig), {**hashes, "F5": {"PAYEMS.csv": "changed"}}, {"sha256": "F"})
    assert ei.value.kind == "usage" and "F5" in str(ei.value)
    with pytest.raises(RS.Refusal) as ei:
        RS.check_correction_inputs({"k": 1}, str(orig), hashes, {"sha256": "OTHER"})
    assert "freeze.sha256" in str(ei.value)
    # the F6/F7/F8 set is compared by hash VALUES: a relabelled key (correction 1) is the same input, a changed hash is not
    rec = RS.check_correction_inputs({"k": 1}, str(orig), {**hashes, "F6_F7_F8_verified": {"relabelled": "3"}}, {"sha256": "F"})
    assert rec["inputs_identical"]
    with pytest.raises(RS.Refusal) as ei:
        RS.check_correction_inputs({"k": 1}, str(orig), {**hashes, "F6_F7_F8_verified": {"x": "changed"}}, {"sha256": "F"})
    assert "F6_F7_F8_verified" in str(ei.value)
    # M6: the committed-state check reads HEAD and the porcelain status (read-only git); the paths cover the spec, every .py and data/
    st = RS.git_state([RS.SPEC_MD, os.path.join(HERE, "run_study.py")])
    assert st["head"] and len(st["head"]) == 40 and isinstance(st["dirty"], list)
    paths = RS.committed_state_paths(None)
    assert RS.SPEC_MD in paths and RS.DATA in paths and os.path.join(HERE, "scoring.py") in paths and os.path.join(HERE, "test_run_synthetic.py") in paths
    assert os.path.abspath(str(tmp_path / "f.json")) not in RS.committed_state_paths(str(tmp_path / "f.json"))   # outside the repo: not a git path
    # N2: the halt record never overwrites an earlier one
    hd = tmp_path / "halt"
    hd.mkdir()
    p1 = RS.write_halt(str(hd), {"generated": "2026-10-20T00:00:00Z", "halted": True})
    p2 = RS.write_halt(str(hd), {"generated": "2026-10-20T00:00:01Z", "halted": True})
    assert p1 != p2 and os.path.exists(p1) and os.path.exists(p2) and json.load(open(p1))["generated"] == "2026-10-20T00:00:00Z"
    # S2: the §4.1 unrevised re-check — synthetic: the note; 'real' logic without any 2026 vintage: refuses (8);
    # with an F4 file at a LISTED 2026 date: compared and recorded (header validated like a served vintage)
    sp = RS.paths_synthetic(noisy, None)
    assert RS.unrevised_recheck("synthetic", sp)[0]["note"].startswith("no archived vintage")
    lists = tmp_path / "lists"
    lists.mkdir()
    (lists / "vd_T10Y3M.txt").write_text("2025-12-31\n2026-01-09\n")
    (lists / "vd_BAA10YM.txt").write_text("2026-01-02\n")
    pr = {**sp, "lists": str(lists), "cache": str(tmp_path / "nocache"), "f4_dir": None}
    with pytest.raises(RS.Refusal) as ei:
        RS.unrevised_recheck("real", pr)
    assert ei.value.kind == "input" and ei.value.code == RS.EXIT["input"] and "T10Y3M" in str(ei.value)
    f4 = tmp_path / "f4"
    f4.mkdir()
    with open(os.path.join(noisy, "f5", "T10Y3M.csv")) as f:
        body = f.read().splitlines()[1:]
    (f4 / "alf_T10Y3M_2026-01-09.csv").write_text("observation_date,T10Y3M_20260109\n" + "\n".join(body) + "\n")
    with pytest.raises(RS.Refusal) as ei:                 # T10Y3M now has one, BAA10YM still none
        RS.unrevised_recheck("real", {**pr, "f4_dir": str(f4)})
    assert "BAA10YM" in str(ei.value)
    with open(os.path.join(noisy, "f5", "BAA10YM.csv")) as f:
        body = f.read().splitlines()[1:]
    (f4 / "alf_BAA10YM_2026-01-02.csv").write_text("observation_date,BAA10YM_20260102\n" + "\n".join(body[:-1]) + "\n")
    recs = RS.unrevised_recheck("real", {**pr, "f4_dir": str(f4)})
    assert [r["series"] for r in recs] == ["T10Y3M", "BAA10YM"] and all(r["unrevised"] and r["source"].startswith("F4 file") for r in recs)
    assert recs[0]["n_common"] > 100 and recs[0]["vintage_date"] == "2026-01-09" and "note" not in recs[0]
    (f4 / "alf_BAA10YM_2026-01-02.csv").write_text("observation_date,BAA10YM_20260103\n" + "\n".join(body[:-1]) + "\n")   # header echoes another date
    with pytest.raises(V.ValidationFail):
        RS.unrevised_recheck("real", {**pr, "f4_dir": str(f4)})
    # M4: a raw vintage whose bytes differ from the verified F6 table refuses (InputIntegrityError -> exit 8 in run_study)
    man = bundles["man_noisy"]
    f5 = E.load_fred_csv_dir(os.path.join(noisy, "f5"))
    vt = RS._read_csv(os.path.join(sp["panel"], "vintage_table.csv"))
    d0 = next(r["issue_date"] for r in RS._read_csv(os.path.join(sp["panel"], "issue_panel_wide.csv")) if r["IS"] == "A" and r["row_kind"] == "nowcast")
    daily = RS._daily_raw(os.path.join(noisy, "f5"))
    ok = S.StudyInputs("synthetic", f5, manifest=man, f5_daily=daily, as_of=lambda d: V.as_of(d, sp["cache"], sp["lists"]), vintage_table=vt)
    state, used = S._state_from_asof(ok, d0)
    assert all(used[c]["f6_verified"] for c in E.COIN_MEMBERS) and used["BAA10YM"]["basis"].startswith("unrevised") and "strictly before" in used["BAA10YM"]["basis"]
    tampered = [dict(r, sha256="0" * 64) if (r["series"] == "PAYEMS" and r["vintage_date"] == used["PAYEMS"]["vintage_date"]) else r for r in vt]
    bad = S.StudyInputs("synthetic", f5, manifest=man, as_of=lambda d: V.as_of(d, sp["cache"], sp["lists"]), vintage_table=tampered)
    with pytest.raises(S.InputIntegrityError):
        S._state_from_asof(bad, d0)
    with pytest.raises(S.InputIntegrityError):            # no table at all: nothing can be verified
        S._state_from_asof(S.StudyInputs("synthetic", f5, manifest=man, as_of=lambda d: V.as_of(d, sp["cache"], sp["lists"])), d0)
    # D7: monthly-mean unrevised series admit only months strictly before the month of d (changes no number: beyond the PAYEMS axis)
    assert max(state["BAA10YM"]) < d0[:7] and max(state["T10Y3M"]) <= d0[:7]


# ----------------------------------------------------------------------------- 9. determinism
def test_two_runs_byte_identical_except_generated(bundles):
    ta = open(bundles["res_a_path"], encoding="utf-8").read()
    tb = open(bundles["res_b_path"], encoding="utf-8").read()
    ga, gb = bundles["res_a"]["generated"], bundles["res_b"]["generated"]
    assert ta.replace(ga, "T") == tb.replace(gb, "T")
    assert bundles["res_a"]["run_id"] == bundles["res_b"]["run_id"]


# ----------------------------------------------------------------------------- 10. the guard
def test_scoring_guard_refuses_real_panels_from_here(tmp_path):
    assert S.ENV_FLAG not in os.environ or os.environ[S.ENV_FLAG] != "1"
    assert not S.armed()
    with pytest.raises(S.RealDataGuard):
        S.StudyInputs("real", {})
    # the real F1 fixture handed in as 'synthetic' without the generator's manifest hash: refused
    f1 = E.load_fixture_json(RS.G.F1_PATH)
    with pytest.raises(S.RealDataGuard):
        S.StudyInputs("synthetic", f1)
    with pytest.raises(S.RealDataGuard):
        S.StudyInputs("synthetic", f1, manifest={"synthetic_marker": S.SYNTHETIC_MARKER, "bundle_sha256": "0" * 64})
    # every section checks the guard, not only the constructor
    with pytest.raises(S.RealDataGuard):
        S.section_windows({"f5": f1})
    # arming needs the flag AND a FROZEN freeze; the template is refused
    with pytest.raises(S.RealDataGuard):
        S.arm_real_run(RS.TEMPLATE, env={})
    with pytest.raises(S.RealDataGuard):
        S.arm_real_run(RS.TEMPLATE, env={S.ENV_FLAG: "1"})
    with pytest.raises(S.RealDataGuard):
        S.arm_real_run(str(tmp_path / "none.json"), env={S.ENV_FLAG: "1"})
    fz = dict(_load(RS.TEMPLATE))
    fz.update({"status": "FROZEN", "answered_by": "test", "answered_on": "2026-10-20"})
    (tmp_path / "frozen.json").write_text(json.dumps(fz))
    tok = S.arm_real_run(str(tmp_path / "frozen.json"), env={S.ENV_FLAG: "1"})
    try:
        assert tok["freeze_sha256"] and S.armed()
        inp = S.StudyInputs("real", f1)              # constructible while armed; NOT scored here
    finally:
        S.disarm()
    with pytest.raises(S.RealDataGuard):
        S.section_windows(inp)                        # re-verified on every call
    assert S.validate_freeze(fz, require_frozen=True) == []
    assert any("FROZEN" in p for p in S.validate_freeze(_load(RS.TEMPLATE), require_frozen=True))


# ----------------------------------------------------------------------------- 11. the committed record and the template
def test_committed_dry_run_is_current(bundles):
    assert os.path.exists(DRYRUN)
    d = _load(DRYRUN)
    a = bundles["res_a"]
    assert d["mode"] == "synthetic" and d["scored_real_data"] is False and d["tag_audit"]["n_untagged"] == 0
    assert d["run_id"] == a["run_id"], "dryrun_synthetic_results.json is stale: re-run run_study.py --synthetic and commit it (N8/D12: every code edit)"
    assert d["decisions"] == a["decisions"]
    assert "gate_report_F1.json" in d["statement"] and "no study metric" in d["statement"] and "synthetic" in d["statement"]   # N1/D10
    assert d["git"] is None and d["correction"] is None
    # M2 (post-scored state, 2026-10-28): the scored files here are results*.json + corrections.log only;
    # every correction file is logged, and no halt record exists
    scored = sorted(fn for fn in os.listdir(HERE) if fn.startswith("results") and fn.endswith(".json"))
    logged = [json.loads(ln)["file"] for ln in open(os.path.join(HERE, "corrections.log"))] if os.path.exists(os.path.join(HERE, "corrections.log")) else []
    for fn in scored:
        assert fn == "results.json" or fn in logged, fn
    assert not any(fn.startswith("halt") for fn in os.listdir(HERE))


def test_freeze_template_documents_every_field():
    t = _load(RS.TEMPLATE)
    for k in t:
        if k.startswith("_") or k in ("status", "answered_by", "answered_on", "spec_version", "freeze_note"):
            continue
        assert "_" + k in t and t["_" + k], k
    assert S.validate_freeze(t, require_frozen=False) == []
    assert all(k in t for k in S.FREEZE_REQUIRED)
    assert t["X_pct"] == 10 and t["Y_pct"] == 25 and t["status"] != "FROZEN"
