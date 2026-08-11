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
    actual 10y T-bond annual returns."""
    v = pb.validate_bonds(data(), frames())
    assert v["ok"], v
    assert v["n_years"] >= 70


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
    assert m["cagr_pct"] == pytest.approx(8.63, abs=0.15)
    assert m["max_dd_pct"] == pytest.approx(-21.6, abs=1.0)
    assert spx["max_dd_pct"] < -45
    assert m["max_dd_pct"] > spx["max_dd_pct"] + 20   # the edge under test
    assert abs(m["cagr_pct"] - 8.84) < 1.0            # ~60/40 CAGR class
