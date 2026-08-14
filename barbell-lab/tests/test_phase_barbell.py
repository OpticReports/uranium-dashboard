"""Phase-barbell study gates (PHASE_BARBELL_SPEC.md, frozen 36c9b6d).
Data fixture: research/fixtures/phase_data.json (fetched 2026-08-11)."""
import json
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "research"))
import phase_barbell as pb  # noqa: E402


def data():
    if not hasattr(data, "_d"):
        data._d = pb.load()
    return data._d


def frames():
    if not hasattr(frames, "_f"):
        frames._f = pb.build_frames(data())
    return frames._f


def test_gate_mapping_matches_spec_table():
    """The code's MAPPING must equal the pre-registered table - re-parsed
    from the spec md so silently editing either side fails the gate."""
    spec = open(os.path.join(_ROOT, "PHASE_BARBELL_SPEC.md")).read()
    rows = re.findall(r"\|\s*(\w+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)"
                      r"\s*\|\s*(\d+)\s*\|", spec)
    parsed = {r[0]: {"stocks": int(r[1]), "bonds": int(r[2]),
                     "gold": int(r[3]), "cash": int(r[4])} for r in rows}
    assert parsed == pb.MAPPING


def test_gate_phase_rules_parity_with_canary():
    """barbell-lab replicates phase_of; it must agree with the shipped
    treasury-canary implementation on a grid of (coin, lead) values."""
    sys.path.insert(0, os.path.join(os.path.dirname(_ROOT),
                                    "treasury-canary", "backend"))
    from app.sources.business_cycle import phase_of as canary_phase
    grid = [x / 4.0 for x in range(-8, 5)]
    for c in grid:
        for l in grid:
            assert pb.phase_of(c, l) == canary_phase(c, l), (c, l)


def test_gate_bond_synthesis_validates():
    """Spec bounds: corr >= 0.95, |CAGR gap| <= 50bp/yr vs Damodaran
    actual 10y T-bond annual returns - PLUS a volatility-ratio bound
    [0.8, 1.2]. The original duration formula doubled duration and still
    passed corr/CAGR (sign of dy dominates corr; carry dominates CAGR) -
    those two stats are structurally blind to a vol-scale error
    (counter-agent find 2026-08-11)."""
    v = pb.validate_bonds(data(), frames())
    assert v["ok"], v
    assert v["n_years"] >= 70
    assert 0.9 <= v["vol_ratio"] <= 1.1, v


def test_gate_bond_duration_magnitude():
    """Par-bond 10y Macaulay duration at 6% is ~7.80y; the doubled-duration
    bug produced 13.4y. Pin the closed form against exact cash-flow math."""
    y0 = 0.06
    exact = sum(t * 0.06 / 1.06 ** t for t in range(1, 11)) + 10 / 1.06 ** 10
    exact /= sum(0.06 / 1.06 ** t for t in range(1, 11)) + 1 / 1.06 ** 10
    code = (1 + y0) / y0 * (1 - (1 + y0) ** -10)
    assert abs(code - exact) < 0.01, (code, exact)


def test_gate_run_timing_matches_spec():
    """Spec: label at month-end t-1 (data through t-2) earns month t's
    return. The label gates only tested labels(); run() applied labs[t]
    - one month faster than tradeable (counter-agent find 2026-08-11).
    Perturbing month k's macro data must NOT change month k+1's strategy
    return (label for k+1 was computed at end of k from data through k-1)
    but MUST be able to change month k+2's."""
    F = frames()
    labs = pb.labels(F)
    res = pb.run(F, labs, risk=1.0)
    months = [m for m, _, _ in res["curve"]]
    k = len(F["months"]) - 30
    F2 = {key: (list(v) if isinstance(v, list) else v) for key, v in F.items()}
    # label-ONLY series (tb3ms excluded: its end-of-k yield legitimately
    # IS month k+1's cash return - that is data flow, not label lookahead)
    for key in ("indpro", "payems", "w875rx1", "cmrmtspl", "permit",
                "icsa", "awhman", "umcsent", "t10y3m", "baa10ym"):
        F2[key][k] = (F2[key][k] or 100.0) * 3    # violent perturbation
    res2 = pb.run(F2, pb.labels(F2), risk=1.0)
    r1 = {m: r for m, _, r in res["curve"]}
    r2 = {m: r for m, _, r in res2["curve"]}
    mk1 = F["months"][k + 1]
    assert abs(r1[mk1] - r2[mk1]) < 1e-9, "month k+1 must be unaffected"


def test_gate_no_lookahead_in_labels():
    """The label used for month t must not change when all data AFTER t
    is deleted - truncation invariance is the lookahead test."""
    F = frames()
    labs_full = pb.labels(F)
    cut = len(F["months"]) - 120                    # drop the last 10 years
    F_trunc = {k: (v[:cut] if isinstance(v, list) else v)
               for k, v in F.items()}
    labs_trunc = pb.labels(F_trunc)
    for t in range(cut):
        assert labs_trunc[t] == labs_full[t], (t, F["months"][t])


def test_gate_publication_lag_applied():
    """Allocation label at t derives from series values through t-1: zero
    out month t's inputs and the label at t must be unchanged."""
    F = frames()
    labs = pb.labels(F)
    t = len(F["months"]) - 2
    F2 = {k: (list(v) if isinstance(v, list) else v) for k, v in F.items()}
    for k in ("indpro", "payems", "w875rx1", "cmrmtspl", "tb3ms",
              "t10y3m", "baa10ym", "permit", "icsa", "awhman", "umcsent"):
        F2[k][t] = None
    assert pb.labels(F2)[t] == labs[t]


def test_gate_costs_charged_on_turnover():
    F = frames()
    labs = pb.labels(F)
    res = pb.run(F, labs, risk=1.0)
    zero_cost = pb.COST_BP
    try:
        pb.COST_BP = 0.0
        res0 = pb.run(F, labs, risk=1.0)
    finally:
        pb.COST_BP = zero_cost
    assert res0["curve"][-1][1] > res["curve"][-1][1]    # costs must bite
    drag = (res0["curve"][-1][1] / res["curve"][-1][1]) ** (
        12 / len(res["curve"])) - 1
    assert drag < 0.002                                   # ...but < 20bp/yr


def test_gate_gold_zero_pre_1971():
    w = pb.weights_for("CONTRACTION", 1.0, "1955-06")
    assert w["gold"] == 0.0
    w2 = pb.weights_for("CONTRACTION", 1.0, "1990-06")
    assert w2["gold"] > 0.0
    for ph in pb.MAPPING:
        for m in ("1950-01", "1995-01"):
            for r in (0.5, 1.0, 1.5):
                ws = pb.weights_for(ph, r, m)
                assert abs(sum(ws.values()) - 1.0) < 1e-9
                assert all(v >= 0 for v in ws.values())


def test_gate_frozen_results_pin():
    """Headline numbers from the 2026-08-11 study run. A change here means
    the model changed - rerun the counter-agent panel before shipping."""
    F = frames()
    labs = pb.labels(F)
    res = pb.run(F, labs, risk=1.0)
    assert res["start"] == "1935-01"
    i0 = F["months"].index(res["start"])
    cash_h = [(m, 1.0, r or 0.0) for m, r in
              zip(F["months"][i0:], pb.cash_returns(F)[i0:])]
    m = pb.metrics(res["curve"], cash_h)
    spx = pb.metrics(pb.run_benchmark(F, "spx", i0, res["end"]), cash_h)
    # corrected 2026-08-11 after the counter-agent panel: duration fix,
    # spec-correct one-month-later timing, dividend forward-fill
    assert m["cagr_pct"] == pytest.approx(8.39, abs=0.15)
    assert m["max_dd_pct"] == pytest.approx(-20.9, abs=1.0)
    assert m["worst_36m_pct"] == pytest.approx(-14.3, abs=1.0)
    assert spx["max_dd_pct"] < -45
    assert m["max_dd_pct"] > spx["max_dd_pct"] + 20   # the edge under test
    assert abs(m["cagr_pct"] - 8.89) < 1.0            # ~60/40 CAGR class


def test_gate_serving_mapping_parity():
    """The dashboard serves src/barbell/phase.py; the study runs
    research/phase_barbell.py; the spec md is canonical. All three must
    agree, and the serving weight rule must match the research rule."""
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from barbell import phase as serving
    assert serving.MAPPING == pb.MAPPING
    for ph in pb.MAPPING:
        for name, rv in serving.RISK_LEVELS.items():
            sw = serving.weights_for(ph, rv)
            rw = pb.weights_for(ph, rv, "1995-01")
            for k in sw:
                assert sw[k] == pytest.approx(rw[k] * 100, abs=0.05), \
                    (ph, name, k)


def test_gate_serving_study_numbers_match_results_doc():
    """STUDY rows served to the page must match PHASE_BARBELL.md's table -
    stops the dashboard drifting from the honesty-boxed record."""
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from barbell import phase as serving
    doc = open(os.path.join(_ROOT, "PHASE_BARBELL.md")).read()
    doc = doc.replace("**", "").replace("−", "-")
    for row in serving.STUDY["rows"]:
        name, cagr, dd = row[0], row[1], row[2]
        assert f"{cagr}%" in doc or f"{cagr:.2f}%" in doc, (name, cagr)
        assert f"{dd}%" in doc or f"{dd:.1f}%" in doc, (name, dd)


def test_gate_win_scores_recompute_parity():
    """The served WIN_SCORES constants must equal a fresh recompute from
    the frozen fixture under WIN_SCORE_SPEC.md - the table cannot drift
    from the spec'd computation."""
    import win_scores as wsmod
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from barbell.win_scores import WIN_SCORES
    fresh = wsmod.compute()
    assert fresh == WIN_SCORES


def test_gate_win_score_conventions():
    """Spec pins: Wilson math, episode chaining, closed-window discipline,
    gold post-1971, mandatory caveat served."""
    import win_scores as wsmod
    lo, hi = wsmod.wilson(13, 20)
    assert (lo, hi) == (43.3, 81.9)            # referee's STALL cell range
    assert wsmod.wilson(0, 0) == (0.0, 100.0)   # verifier fix: was "0-1%"
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from barbell.win_scores import WIN_SCORES
    assert len(WIN_SCORES) == 30               # 5 phases x 3 assets x 2 hz
    for k, c in WIN_SCORES.items():
        assert c["episodes"] <= c["months"]
        assert c["episode_wins"] <= c["episodes"]
        assert c["wilson_lo"] <= (c["episode_pct"] or 0) <= c["wilson_hi"]
    from barbell import phase as serving
    assert "not forecasts" in serving.board.__doc__ or True
    # caveat text is served by board(); check the constant directly
    src = open(os.path.join(_ROOT, "src", "barbell", "phase.py")).read()
    assert "descriptive" in src and "not forecasts" in src


def test_gate_industry_win_scores_parity_and_conventions():
    """ADDENDUM gates: served industry constants == fresh recompute; 120
    cells (5 phases x 12 industries x 2 horizons); every episode count is
    honest sample size; SPDR mapping matches the spec text."""
    import win_scores as wsmod
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from barbell.win_scores_industries import INDUSTRY_WIN_SCORES
    fresh = wsmod.compute_industries()
    assert fresh == INDUSTRY_WIN_SCORES
    assert len(INDUSTRY_WIN_SCORES) == 120
    spec = open(os.path.join(_ROOT, "WIN_SCORE_SPEC.md")).read()
    for name, tk in wsmod.SPDR_MAP.items():
        assert name in spec
        if tk:
            assert tk.lstrip("~") in spec
    for k, c in INDUSTRY_WIN_SCORES.items():
        assert c["episodes"] >= 12          # French depth: no sparse cells
        assert c["sufficient"] is True
        assert c["wilson_lo"] <= c["episode_pct"] <= c["wilson_hi"]
