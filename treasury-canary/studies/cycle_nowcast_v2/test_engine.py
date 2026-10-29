"""Cycle nowcast v2 — merge-blocking gate tests (offline, deterministic, < 60 s).

  python3 -m pytest studies/cycle_nowcast_v2/test_engine.py -q     (from treasury-canary)

What is asserted (SPEC v1 §7.1 / §7.2 and task B1):
  * every PASS/FAIL row of gates.run_all() (the §7.1 reproduction gate on F1 in
    reproduction_mode, the scoring-mode delta row, the identity gates, the
    legacy deployed outputs, the §7.2 engine gates on F1 / F3 / F4) — a row that
    the gate report records as a MISS is marked xfail(strict) with the reason
    'raised to Casey'; the tolerance is never widened and a later unexpected
    pass fails the suite so the row is re-examined;
  * look-ahead: shifting any input series forward one month changes no number
    issued before that month (D1/D2/D4), a synthetic series with a known AR
    structure reproduces its own bridge coefficients, the row-admission rule
    rejects a row whose target needs an unpublished member (D2/D6);
  * IS labels and the shutdown cases (§2.3, §2.4), partial-month invariance;
  * the band machinery on a synthetic pattern (§2.2, §2.4);
  * metric conventions (§1: directional ties, DM, transitions, onsets, ex-2020);
  * determinism (two runs identical).
Nothing here aggregates a v2 member over the evaluation window on any fixture.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import engine as E   # noqa: E402
import gates as G    # noqa: E402
import metrics as X  # noqa: E402

# rows the gate report records as misses on 2026-10-20 (notes_B1.md §3): the
# tolerance stays; the test is xfail(strict) until Casey rules on them.
KNOWN_MISSES = {
    "G04": "ENS_GRID_REPRO 50/50 count 361 vs 354±5 (RMSE row G03 reproduces); 97 near-tie selections; raised",
    "S01_claims": "literal D1+D2+D6 scoring row: CLAIMS |ΔRMSE| 0.031 (2020 leverage of the t ≤ M−2 rows; ex-2020 Δ +0.004); D1+D6 reading (D01_*) passes; raised",
    "S01_ens": "literal D1+D2+D6 scoring row: ENS |ΔRMSE| 0.012; D1+D6 reading passes; raised",
    "S04": "literal D1+D2+D6 scoring row: 4 transition flips + 1 onset move (logged); D1+D6 reading gives exactly {1980-11}; raised",
    "Q01": "SOFT ENS_BC_S −22.1% vs QA −24.2% (A16: the QA harness's S form is not recoverable); raised",
    "Q04": "SOFT ENS_BC_S onsets 4-2-1 vs QA 5-1-1; raised",
}


@pytest.fixture(scope="module")
def report():
    return G.run_all(write=False)


@pytest.fixture(scope="module")
def f1_series():
    return E.load_fixture_json(G.F1_PATH)


def _rows(rep):
    return [r for r in rep["rows"] if r["status"] in ("PASS", "FAIL")]


def pytest_generate_tests(metafunc):
    if "gate_row" in metafunc.fixturenames:
        rep = G.run_all(write=False)
        rows = _rows(rep)
        metafunc.parametrize("gate_row", rows, ids=[r["id"] for r in rows])


# ----------------------------------------------------------------------------
# 1. the gate rows
# ----------------------------------------------------------------------------
def test_gate_row(gate_row):
    r = gate_row
    msg = f"{r['id']} {r['quantity']}: computed {r['computed']} target {r['target']} tol {r['tolerance']}"
    if r["id"] in KNOWN_MISSES:
        if r["status"] == "FAIL":
            pytest.xfail(KNOWN_MISSES[r["id"]] + " | " + msg)
        pytest.fail("known miss now PASSES — remove it from KNOWN_MISSES and re-review: " + msg)
    assert r["status"] == "PASS", msg


def test_no_hard_gate_failures(report):
    """v1 §7 'merge-blocking' / §7.1 'blocks ... raised to Casey': a HARD gate miss
    must turn the suite red, not only the report. The per-row xfails above keep
    the information; this test stays red until Casey rules on every id in
    hard_fail_ids (the ruling is then recorded here and in notes_B1.md §3)."""
    hard = report["summary"]["hard_fail_ids"]
    # RULED (SPEC v1.1, spec owner, 2026-10-20; freeze.json harness_status not_retrievable, 2026-10-28):
    # G04 / S01_claims / S01_ens / S04 are DESCRIPTIVE - recorded, never gated, never widened.
    # run_study.RULED_DESCRIPTIVE carries the same ruling for --real. Any OTHER hard miss stays red.
    from run_study import RULED_DESCRIPTIVE
    unruled = [k for k in hard if k not in RULED_DESCRIPTIVE]
    assert unruled == [], ("HARD gate misses raised to Casey, not widened: "
                           + "; ".join(f"{k}: {KNOWN_MISSES.get(k, 'unlisted miss')}" for k in unruled))
    assert set(hard) == {"G04", "S01_claims", "S01_ens", "S04"}, hard   # the ruled set, exactly


def test_report_shape_and_nothing_scored(report):
    assert report["scored"] is False
    ids = {r["id"] for r in report["rows"]}
    for must in ("P01", "P05", "B01", "C01", "C04", "E01", "E06", "E07", "E09", "G03", "I01", "I02", "L01", "L04",
                 "F3_01", "F3_05", "F4_2025-12-16_e", "X02", "X03", "X04", "X05"):
        assert must in ids, must
    q5 = next(r for r in report["rows"] if r["id"] == "Q05")
    assert q5["status"] == "NOT_RUN"            # ENS_BC_HH is the D-1 quantity: not computed before the scored run
    for r in report["rows"]:
        assert set(r) >= {"id", "section", "quantity", "computed", "target", "tolerance", "status"}
    s = report["summary"]
    assert set(s["hard_fail_ids"]) <= {k for k in KNOWN_MISSES if not k.startswith("Q")}
    assert set(s["soft_fail_ids"]) <= {k for k in KNOWN_MISSES if k.startswith("Q")}


# ----------------------------------------------------------------------------
# 2. look-ahead
# ----------------------------------------------------------------------------
def _perturb(series, name, m0, factor=1.03, shift=0.5):
    out = copy.deepcopy(series)
    for m in list(out[name]):
        if m >= m0:
            out[name][m] = out[name][m] + shift if name == "T10Y3M" else out[name][m] * factor
    return out


@pytest.mark.parametrize("name", ["PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL", "ICSA", "T10Y3M"])
def test_lookahead_shift_changes_nothing_issued_before(f1_series, name):
    """Perturb every observation of one series from m0 on; every number the
    lag simulation issues for a target M at which the perturbed observation is
    not yet in hand (M - L_s(pattern) < m0) must be bit-identical, for all three
    information sets in scoring_mode with the HH claims form. Targets at or
    after m0 + L_s must differ (the test has teeth)."""
    m0 = "2010-01"
    window = ("2005-01", "2012-12")
    base = E.build(f1_series)
    pert = E.build(_perturb(f1_series, name, m0))
    for pname, pat in E.PATTERNS.items():
        Ls = pat.get(name, 0)                       # PAYEMS / ICSA / T10Y3M are lag 0
        tg = E.eval_targets(base, window)
        a = E.simulate(base, pat, "scoring", tg, "hh")
        b = E.simulate(pert, pat, "scoring", tg, "hh")
        cut = E.madd(m0, Ls)                        # first target whose inputs include the perturbed month
        before = np.array([m < cut for m in a["months"]])
        assert before.any() and (~before).any()
        for k in ("bridge", "claims", "ens", "comp_prev", "pers_hh", "pers_avail"):
            assert np.array_equal(a[k][before], b[k][before], equal_nan=True), (name, pname, k)
        changed = any(not np.array_equal(a[k][~before], b[k][~before], equal_nan=True) for k in ("bridge", "claims", "ens"))
        assert changed, (name, pname, "perturbation had no effect after the cut — test has no teeth")


def _synthetic_ar(L, a, b, c, n=420):
    rng = np.random.default_rng(20261020)
    gP = 0.01 * rng.standard_normal(n)
    gc = np.zeros(n)
    for t in range(6, n):
        gc[t] = (a + b * gc[t - L] + c * gP[t]) if t >= 6 + L else 0.02 * rng.standard_normal()
    xP, xc = np.full(n, 100.0), np.full(n, 50.0)
    for t in range(6, n):
        xP[t] = xP[t - 6] * np.exp(gP[t] / 2.0)
        xc[t] = xc[t - 6] * np.exp(gc[t] / 2.0)
    months = [E.madd("1959-01", k) for k in range(n)]
    series = {"PAYEMS": dict(zip(months, xP)), "INDPRO": dict(zip(months, xc)),
              "W875RX1": dict(zip(months, xc)), "CMRMTSPL": dict(zip(months, xc))}
    return series, gc, gP


@pytest.mark.parametrize("L,a,b,c", [(1, -0.002, 0.7, 0.45), (2, 0.004, 0.5, 0.52), (3, 0.006, 0.3, 0.75)])
def test_synthetic_ar_bridge_reproduces_its_own_coefficients(L, a, b, c):
    series, gc, gP = _synthetic_ar(L, a, b, c)
    ds = E.build(series)
    beta, n = E.bridge_fit(ds, "INDPRO", L, ds.n - 1)
    assert n > 300
    assert np.allclose(beta, [a, b, c], atol=1e-8), beta
    i = ds.n - 1
    z, status, info = E.bridge_member(ds, i, "INDPRO", L, "scoring")
    assert status == "bridged"
    assert abs(info["proj_g"] - gc[i]) < 1e-8          # noise-free structure: the projection IS the truth
    assert info["rows_through"] == ds.months[i - L]      # D1: rows t <= M-L
    # reproduction mode uses rows t < M for every lag
    _, st2, info2 = E.bridge_member(ds, i, "INDPRO", L, "reproduction")
    assert info2["rows_through"] == ds.months[i - 1]


def test_row_admission_rejects_unpublished_targets(f1_series):
    """At IS-A on F1 (M = 2026-07) K = 2026-05: rows 2026-06 (3-member partial) and
    2026-07 are rejected. With CMRMTSPL truncated to 2026-04 (lag 3) K = 2026-04
    and the row 2026-05, whose target needs the unpublished CMRMTSPL(2026-05),
    is rejected too; the CLAIMS_HH fit used by issue() ends at K."""
    ds = E.build(f1_series)
    st = E.information_state(ds)
    assert st["K"] == "2026-05" and st["IS"] == "A"
    adm = E.admissible_rows(ds, st["K_i"])
    assert adm[ds.i("2026-05")] and not adm[ds.i("2026-06")] and not adm[ds.i("2026-07")]
    r = E.issue(f1_series, "2026-08-07")
    assert r["claims_fit"]["rows"][1] == "2026-05"
    stale = E.truncate_series(f1_series, "2026-04", ["CMRMTSPL"])
    ds3 = E.build(stale)
    st3 = E.information_state(ds3)
    assert st3["lags"]["CMRMTSPL"] == 3 and st3["K"] == "2026-04"
    adm3 = E.admissible_rows(ds3, st3["K_i"])
    assert adm3[ds3.i("2026-04")] and not adm3[ds3.i("2026-05")]
    r3 = E.issue(stale, "2026-08-07")
    assert r3["claims_fit"]["rows"][1] == "2026-04" and r3["members_bridged"]["CMRMTSPL"] == 3
    # partial-member months are never admissible even below K
    assert not E.admissible_rows(ds, ds.n - 1)[ds.i("2026-06")]
    assert E.admissible_rows(ds, ds.n - 1)[ds.i("1972-01")]          # 3-member 1969-06..1977-05 count as complete


def test_claims_fit_cache_never_aliases_two_designs(f1_series):
    """Same regressor history, two designs (require_complete False / True), same
    T spanning the 2026-06 partial month: the fits must differ (n = 586 admits
    the 3-member 2026-06 target, n = 585 does not), in either call order and on
    one Dataset — the cache key hashes the valid mask, not only the history."""
    for order in ((False, True), (True, False)):
        ds = E.build(f1_series)
        T = ds.i("2026-06")
        got = {}
        for rc in order:
            dsg = E.claims_design(ds, ds.coin, rc, "real")
            beta, n, r0, r1 = E.claims_fit(ds, dsg, T)
            got[rc] = (n, r1, beta)
        assert got[False][0] == 586 and got[False][1] == "2026-06"
        assert got[True][0] == 585 and got[True][1] == "2026-05"
        assert np.max(np.abs(got[True][2] - got[False][2])) > 1e-6
    # the scored-mode simulation on a Dataset that already served a reproduction fit
    ds = E.build(f1_series)
    E.simulate(ds, E.PATTERNS["A"], "reproduction", [ds.i("2026-06")], "original")
    rc_design = E.claims_design(ds, ds.coin, True, "real")
    assert E.claims_fit(ds, rc_design, ds.i("2026-06"))[1] == 585
    sim = E.simulate(ds, E.PATTERNS["A"], "scoring", [ds.i("2026-06")], "original")
    assert sim["claims_n"][0] == E.claims_fit(ds, rc_design, ds.i("2026-06") - 2)[1]   # rows t <= K = M-2


def test_absent_or_empty_member_is_none_with_reason(f1_series, tmp_path):
    """v1 §2.4 'every None carries a reason': a COIN member absent from the
    vintage, or too short for a single z, is never silently dropped from the
    mean ('not_existing' is only for months before a member's first z)."""
    no_c = {s: d for s, d in f1_series.items() if s != "CMRMTSPL"}
    r = E.issue(no_c, "2026-08-07")
    assert r["nowcast"] is None and r["bridge_hh"] is None and "CMRMTSPL" in r["reason"]
    assert r["flags"]["members_absent"] == ["CMRMTSPL"] and r["lags"]["CMRMTSPL"] is None
    short = copy.deepcopy(f1_series)
    short["CMRMTSPL"] = {m: v for m, v in short["CMRMTSPL"].items() if m >= "2018-01"}
    rs = E.issue(short, "2026-08-07")
    assert rs["nowcast"] is None and "CMRMTSPL" in rs["reason"]
    ok = E.issue(f1_series, "2026-08-07")
    assert ok["flags"]["members_absent"] == [] and ok["flags"]["members_ahead"] == []
    # a member observation beyond the last PAYEMS month is flagged, the target stays M
    ahead = _extend(f1_series, "INDPRO", "2026-08")
    ra = E.issue(ahead, "2026-08-07")
    assert ra["target_month"] == "2026-07" and ra["flags"]["members_ahead"] == ["INDPRO"]
    # header-only / all-'.' ALFRED files are refused by the loader (v1 §4.4 '>= 1 data row')
    p = tmp_path / "alf_CMRMTSPL_2026-01-09.csv"
    p.write_text("observation_date,CMRMTSPL_20260109\n")
    with pytest.raises(ValueError):
        E.read_alfred_csv(str(p), "CMRMTSPL", "2026-01-09")
    p.write_text("observation_date,CMRMTSPL_20260109\n2025-01-01,.\n2025-02-01,.\n")
    with pytest.raises(ValueError):
        E.read_alfred_csv(str(p), "CMRMTSPL", "2026-01-09")
    (tmp_path / "alf_INDPRO_2026-01-09.csv").write_text("")
    with pytest.raises(ValueError):
        E.read_alfred_csv(str(tmp_path / "alf_INDPRO_2026-01-09.csv"), "INDPRO", "2026-01-09")
    # the claims half failing is a reason on the nowcast, not a silent None
    no_icsa = {s: d for s, d in f1_series.items() if s != "ICSA"}
    ri = E.issue(no_icsa, "2026-08-07")
    assert ri["bridge_hh"] is not None and ri["nowcast"] is None and ri["reason"].startswith("claims half unavailable")


# ----------------------------------------------------------------------------
# 3. IS labels, shutdown cases, invariances
# ----------------------------------------------------------------------------
def _extend(series, name, month, factor=1.001):
    out = copy.deepcopy(series)
    last = max(out[name])
    out[name][month] = out[name][last] * factor
    return out


def test_is_labels_follow_the_vintage(f1_series):
    s = f1_series
    assert E.issue(s)["info_set"] == "A"
    sB = _extend(s, "INDPRO", "2026-07")
    rB = E.issue(sB)
    assert rB["info_set"] == "B" and rB["lags"] == {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2}
    sC2 = _extend(sB, "W875RX1", "2026-07")                 # IS-C with CMRMTSPL(M-1) not yet in hand (24/160 days)
    rC2 = E.issue(sC2)
    assert rC2["info_set"] == "C" and rC2["lags"]["CMRMTSPL"] == 2 and rC2["flags"]["is_c_cmrmtspl_lag2"]
    assert rC2["K"] == "2026-05" and rC2["completed_prev"]["pattern"] == {"CMRMTSPL": 1}
    sC = _extend(sC2, "CMRMTSPL", "2026-06")                 # canonical IS-C
    rC = E.issue(sC)
    assert rC["info_set"] == "C" and rC["lags"]["CMRMTSPL"] == 1 and not rC["flags"]["is_c_cmrmtspl_lag2"]
    assert rC["K"] == "2026-06" and rC["completed_prev"]["pattern"] == {}
    dsC = E.build(sC)
    assert rC["completed_prev"]["value"] == pytest.approx(dsC.coin[dsC.i("2026-06")], abs=0)   # identity: == realized
    assert rC["persistence"]["realized"] == pytest.approx(dsC.coin[dsC.i("2026-06")], abs=0)
    # all four published for the last PAYEMS month -> None with reason
    done = _extend(sC, "CMRMTSPL", "2026-07")
    rd = E.issue(done)
    assert rd["nowcast"] is None and "complete" in rd["reason"]


def test_shutdown_cases_from_f4(report):
    rows = {r["id"]: r for r in report["rows"]}
    assert rows["F4_2025-12-16_e"]["computed"] == ["CMRMTSPL"]
    assert rows["F4_2025-12-16_d"]["computed"] == {"PAYEMS": 0, "INDPRO": 2, "W875RX1": 2, "CMRMTSPL": 4}
    assert rows["F4_2025-12-16_f"]["detail"]["completed_prev"]["pattern"] == {"INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 3}
    assert rows["F4_2026-01-09_d"]["computed"] == {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 3, "CMRMTSPL": 3}
    for d in G.F4_DATES:                                           # v1 §2.4: F4 carries the ICSA vintages on all four dates
        assert rows[f"F4_{d}_g"]["status"] == "PASS", d           # claims half: value, fit rows end at K(d), reason None
        assert rows[f"F4_{d}_g"]["detail"]["claims_fit"]["rows"][1] == rows[f"F4_{d}_f"]["detail"]["K"]
    assert "listed vintage" in rows["F4_2025-12-16_g"]["detail"]["icsa_source"]
    assert rows["F4_2026-02-06_c"]["computed"] == "B"


def test_stale_input_gate_inverted_and_partial_month_invariance(f1_series):
    base = E.issue(f1_series, "2026-08-07")
    lag3 = E.issue(E.truncate_series(f1_series, "2026-04", ["CMRMTSPL"]), "2026-08-07")
    lag4 = E.issue(E.truncate_series(f1_series, "2026-03", ["CMRMTSPL"]), "2026-08-07")
    assert lag3["bridge_hh"] is not None and lag3["members_bridged"]["CMRMTSPL"] == 3 and lag3["dropped"] == []
    assert lag4["bridge_hh"] is not None and lag4["dropped"] == ["CMRMTSPL"] and "CMRMTSPL" not in lag4["members_bridged"]
    assert lag4["completed_prev"]["pattern"] == {"CMRMTSPL": 3}
    part = copy.deepcopy(f1_series)
    part["ICSA"] = {m: v for m, v in part["ICSA"].items() if m < "2026-08"}
    part["T10Y3M"] = {m: v for m, v in part["T10Y3M"].items() if m < "2026-08"}
    rp = E.issue(part, "2026-08-07")
    assert (rp["bridge_hh"], rp["claims_hh"], rp["ens_hh"]) == (base["bridge_hh"], base["claims_hh"], base["ens_hh"])
    # the deployed-form emulation: F1 issues, lag-3 and F3-like states do not
    assert E.legacy_form_would_issue(f1_series)[0] is True
    assert E.legacy_form_would_issue(E.truncate_series(f1_series, "2026-04", ["CMRMTSPL"]))[0] is False


# ----------------------------------------------------------------------------
# 4. band machinery on a synthetic pattern
# ----------------------------------------------------------------------------
def test_band_machinery_synthetic(f1_series):
    months = [E.madd("1990-01", k) for k in range(200)]
    e = np.concatenate([np.linspace(-0.1, 0.1, 100), np.linspace(-0.4, 0.4, 100)])   # wider errors later
    b = X.band_percentiles(e)
    assert b["n"] == 200 and b["p10"] < b["p50"] < b["p90"] and abs(b["bias"]) < 1e-12
    early = X.expanding_band(months, e, months[100])                 # only the narrow first half is 'before'
    assert early["n"] == 100 and early["p90"] == pytest.approx(np.percentile(e[:100], 90))
    assert X.expanding_band(months, e, months[10]) is None            # < min_n
    full = X.band_percentiles(e, (10, 90))
    assert full["p90"] > early["p90"]                                  # a wider distribution widens the band
    keys = ["bridged[CMRMTSPL:1]|dropped[]|skipped[]"] * 100 + ["bridged[]|dropped[CMRMTSPL]|skipped[]"] * 100
    tab = X.pattern_error_table(months, e, np.zeros(200), keys, require_bridged=False)
    assert set(tab) == set(keys) and tab["bridged[]|dropped[CMRMTSPL]|skipped[]"]["p90"] > tab["bridged[CMRMTSPL:1]|dropped[]|skipped[]"]["p90"]
    assert "bridged[]|dropped[CMRMTSPL]|skipped[]" not in X.pattern_error_table(months, e, np.zeros(200), keys)   # PRIMARY: >= 1 bridged
    # a completion whose bridged member was skipped (short history, 1977-06) is keyed
    # by its skipped set, never as the all-actual pattern
    ds = E.build(f1_series)
    c77 = E.complete_month(ds, ds.i("1977-06"), E.PREV_PATTERNS["A"], "scoring")
    assert c77["skipped"] == ["CMRMTSPL"] and c77["pattern_key"] == "bridged[]|dropped[]|skipped[CMRMTSPL]"
    assert "bridged[]|dropped[]|skipped[CMRMTSPL]" not in X.pattern_error_table(["1977-06"], [0.0], [0.0], [c77["pattern_key"]])
    # the engine draws [completed + p10, completed + p90] keyed to the displayed month's pattern
    assert E.apply_band(1.0, {"p10": -0.2, "p90": 0.3}) == [0.8, 1.3]
    bands = {"bridged[CMRMTSPL:1]|dropped[]|skipped[]": {"p10": -0.123, "p90": 0.117, "basis": "synthetic"},
             "bridged[CMRMTSPL:2,INDPRO:1,W875RX1:1]|dropped[]|skipped[]": {"p10": -0.293, "p90": 0.276, "basis": "synthetic"},
             "bridged[INDPRO:2,W875RX1:2]|dropped[CMRMTSPL]|skipped[]": {"p10": -0.5, "p90": 0.6, "basis": "synthetic-dropped"}}
    r = E.issue(f1_series, "2026-08-07", bands=bands)
    v = r["completed_prev"]["value"]
    assert r["completed_prev"]["pattern_key"] == "bridged[CMRMTSPL:1]|dropped[]|skipped[]"
    assert r["completed_prev"]["band"] == pytest.approx([v - 0.123, v + 0.117])
    assert r["completed_target"]["band"] == pytest.approx([r["bridge_hh"] - 0.293, r["bridge_hh"] + 0.276])
    r0 = E.issue(f1_series, "2026-08-07")
    assert r0["completed_prev"]["band"] is None and r0["completed_prev"]["band_basis"].startswith("pending")
    drop = E.issue(E.truncate_series(E.truncate_series(f1_series, "2026-03", ["CMRMTSPL"]), "2026-05", ["INDPRO", "W875RX1"]),
                   "2026-08-07", bands=bands)
    assert drop["dropped"] == ["CMRMTSPL"] and drop["completed_target"]["pattern_key"] == "bridged[INDPRO:2,W875RX1:2]|dropped[CMRMTSPL]|skipped[]"
    w = drop["completed_target"]["band"]
    assert (w[1] - w[0]) > (r["completed_target"]["band"][1] - r["completed_target"]["band"][0])   # wide band for the dropped case


# ----------------------------------------------------------------------------
# 5. metric conventions
# ----------------------------------------------------------------------------
def test_metric_conventions():
    # directional: ties count as wrong, n reported
    d = X.directional_accuracy([1.0, 0.0, 2.0, 1.0], [2.0, 1.0, 1.0, 1.0], [0.0, 0.0, 1.5, 1.0])
    assert d["n"] == 4 and d["hits"] == 1 and d["ties"] == 2            # row2 pred tie, row4 real tie, row3 wrong sign
    # transitions and transition accuracy
    y = np.array([-0.8, -0.5, 0.1, 0.2, -0.9]); yp = np.array([-0.5, -0.8, -0.5, 0.1, 0.2])
    assert X.transition_accuracy(y, y, yp)["n_transitions"] == 4
    assert X.transition_accuracy(yp, y, yp)["hits"] == 0                  # persistence calls 0 by construction
    # DM: candidate better -> negative t; gap-closed concatenation == pre-concatenated arrays
    rng = np.random.default_rng(7)
    e0 = rng.standard_normal(300); e1 = 0.6 * e0 + 0.1 * rng.standard_normal(300)
    t = X.dm_test(e1, e0)
    assert t["t"] < 0 and t["n"] == 300 and t["primary_pass_cand_better"]
    months = [E.madd("2000-01", k) for k in range(300)]
    mk = X.ex2020_mask(months)
    assert (~mk).sum() == 12
    assert X.dm_test(e1, e0, mask=mk)["t"] == X.dm_test(e1[mk], e0[mk])["t"]
    worse = X.dm_test(e0 * 1.5, e0)
    assert worse["t"] > 0 and worse["kill_cand_worse"]
    # onset table: advantage = (m_c - m_n) + 1; missed when no nowcast crossing
    m = [E.madd("1980-01", k) for k in range(30)]
    real = np.zeros(30); real[12] = -1.0                                  # realized crosses at m[12]
    now = np.zeros(30); now[10] = -1.0                                    # nowcast crosses two months earlier
    ot = X.onset_table(m, real, now, [m[12]])
    assert ot["rows"][0]["calendar_advantage_months"] == 3 and ot["rows"][0]["class"] == "earlier"
    assert X.onset_table(m, real, np.zeros(30), [m[12]])["rows"][0]["class"] == "missed"
    tie = np.zeros(30); tie[13] = -1.0
    assert X.onset_table(m, real, tie, [m[12]])["rows"][0]["calendar_advantage_months"] == 0
    # false alarms: within +/-3 CALENDAR months of a realized crossing it is not an alarm
    assert X.false_alarms(m, real, now) == []
    far = np.zeros(30); far[25] = -1.0
    assert X.false_alarms(m, real, far) == [m[25]]
    # the window is calendar months, not list positions: on a gap-closed list a realized
    # crossing 3 positions but 15 months away does not excuse the alarm
    gm = ["2019-10", "2019-11", "2019-12", "2021-01", "2021-02", "2021-03"]
    g_real = np.array([0.0, 0.0, 0.0, -1.0, 0.0, 0.0]); g_now = np.array([-1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert X.false_alarms(gm, g_real, g_now) == ["2019-10"]
    assert X.false_alarms(gm, g_real, np.array([0.0, 0.0, -1.0, 0.0, 0.0, 0.0])) == ["2019-12"]      # 13 months away
    assert X.false_alarms(gm, g_real, np.array([0.0, 0.0, 0.0, 0.0, -1.0, 0.0])) == []                # 1 month away
    # scored-window end = last complete COIN month (v1 §1 Windows)
    assert E.scored_window_end(E.build(_synthetic_ar(1, -0.002, 0.7, 0.45)[0])) == E.madd("1959-01", 419)
    # leave-one-year-out
    lo = X.loyo_ratio(e1, e0, months)
    assert lo["min"] <= lo["ratio"] <= lo["max"] and 2000 <= lo["min_drop_year"] <= 2024
    # population RMSE
    assert X.rmse([3.0, 4.0]) == pytest.approx(np.sqrt(12.5))


def test_ens_grid_d3_members_build(f1_series):
    """Code-path check only (no metric): the D3 member builder returns the five
    HH/available-form members, finite on a short window, with CLAIMS_HH rows
    ending at K = M - max lag. Nothing is aggregated."""
    ds = E.build(f1_series)
    tg = E.eval_targets(ds, ("1995-01", "1996-12"))
    for pname in ("A", "B"):
        mem = E.ens_grid_d3_members(ds, tg, f1_series, pname)
        assert set(mem) == {"PERS", "AR2", "LEADREG", "BRIDGE", "CLAIMS"}
        for k, v in mem.items():
            assert v.shape == (len(tg),) and np.isfinite(v).all(), (pname, k)
    sim = E.simulate(ds, E.PATTERNS["A"], "scoring", tg[:1], "hh")
    i = tg[0]
    _, n, r0, r1 = E.claims_fit(ds, E.claims_design(ds, E.coin_hh_history(ds, E.PREV_PATTERNS["A"], "scoring"), True, "chk"), i - 2)
    assert r1 == ds.months[i - 2] and sim["claims_status"][0] == "fit" and sim["claims_n"][0] == n


def test_ens_grid_selector_uses_only_past_errors():
    y = np.zeros(60)
    A = np.full(60, 0.1); A[30] = 5.0           # a huge error at index 30
    B = np.full(60, 0.2)
    g1 = E.ens_grid({"PERS": B, "A": A}, y, selector_lag=1, warmup=24)
    g2 = E.ens_grid({"PERS": B, "A": A}, y, selector_lag=2, warmup=24)
    assert g1["chosen"][31] == "PERS" and g2["chosen"][31] == "A"     # lag 2 cannot see the index-30 error yet
    assert g1["chosen"][30] == "A" and g1["n_selected"] == 36
    assert g1["chosen"][23] is None and np.isfinite(g1["forecast"][23])
    assert len(g1["dictionary"]) == 2 + 3 + 1


# ----------------------------------------------------------------------------
# 6. determinism
# ----------------------------------------------------------------------------
def test_two_runs_identical(f1_series, report):
    ds1, ds2 = E.build(f1_series), E.build(f1_series)
    tg = E.eval_targets(ds1, ("1990-01", "2000-12"))
    a = E.simulate(ds1, E.PATTERNS["B"], "scoring", tg, "hh")
    b = E.simulate(ds2, E.PATTERNS["B"], "scoring", tg, "hh")
    for k in ("bridge", "claims", "ens", "comp_prev", "pers_hh"):
        assert np.array_equal(a[k], b[k], equal_nan=True)
    r1, r2 = E.issue(f1_series, "2026-08-07"), E.issue(f1_series, "2026-08-07")
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    rep2 = G.run_all(write=False)
    assert json.dumps(report["rows"], sort_keys=True) == json.dumps(rep2["rows"], sort_keys=True)
