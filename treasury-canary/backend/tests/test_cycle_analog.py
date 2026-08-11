"""Historical-analog layer gates — frozen fixture (FRED 2026-08-07 core +
CPI/FFR/SPX addendum 2026-08-11). Pins the lookahead protections, the
distance/forward-outcome indexing, and the walk-forward skill design."""
import json
import math
import os

import pytest

from app.sources import cycle_analog

_D = os.path.dirname(__file__)
FIX = {**json.load(open(os.path.join(_D, "fixtures_cycle_fred.json"))),
       **json.load(open(os.path.join(_D, "fixtures_analog_extra.json")))}


def vectors():
    if not hasattr(vectors, "_v"):
        vectors._v = cycle_analog.build_vectors(raw_override=FIX)
    return vectors._v


def board():
    if not hasattr(board, "_b"):
        board._b = cycle_analog.board(raw_override=FIX)
    return board._b


def test_gate_vector_shape_and_warmup():
    V = vectors()
    assert len(V["matrix"]) == len(V["months"]) == len(V["spx"])
    assert all(len(row) == 13 for row in V["matrix"])
    # expanding-z warmup: nothing usable in the first Z_MIN months
    assert all(x is None for x in V["matrix"][0])
    # recent months are near-complete (CMRMTSPL may lag by 1-2 months)
    tail = V["matrix"][-2]
    assert sum(1 for x in tail if x is not None) >= cycle_analog.MIN_DIMS


def test_gate_distance_semantics():
    a = [1.0] * 13
    b = [1.0] * 13
    assert cycle_analog._dist(a, b) == 0.0
    c = [2.0] * 13
    assert cycle_analog._dist(a, c) == pytest.approx(1.0)
    sparse = [1.0] * (cycle_analog.MIN_DIMS - 1) + [None] * (
        13 - cycle_analog.MIN_DIMS + 1)
    assert cycle_analog._dist(a, sparse) is None    # too few shared dims


def test_gate_forward_indexing_no_off_by_one():
    """fwd return spans (t, t+h]; recession-within uses months t+1..t+12 -
    the OUTCOME window must never include the forecast month itself."""
    spx = [100.0, 110.0, 121.0]
    assert cycle_analog._fwd_ret(spx, 0, 2) == pytest.approx(21.0)
    assert cycle_analog._fwd_ret(spx, 1, 2) is None          # runs off the end
    rec = [1] + [0] * 12
    assert cycle_analog._rec_within(rec, 0) is False   # own month excluded
    rec2 = [0] * 5 + [1] + [0] * 8
    assert cycle_analog._rec_within(rec2, 0) is True
    assert cycle_analog._rec_within([0] * 10, 0) is None     # window incomplete


def test_gate_exclusion_window():
    V = vectors()
    t = len(V["months"]) - 2
    nbrs = cycle_analog._neighbors(V, t)
    assert nbrs, "no neighbors found"
    assert all(abs(i - t) >= cycle_analog.EXCLUDE_M for _, i in nbrs)


def test_gate_skill_test_uses_only_observable_outcomes():
    """At forecast month t, an analog's 12m outcome must already be history:
    i + 12 <= t. Violating this leaks the future into the 'forecast'."""
    V = vectors()
    t = 400
    nbrs = cycle_analog._neighbors(V, t, known_by=t)
    assert nbrs
    assert all(i + 12 <= t for _, i in nbrs)


def test_gate_board_reproduces_frozen_result():
    """Frozen-fixture regression pin: 2007-07 is the #1 analog of the
    2026-06 state, and the analog recession probability sits far above
    climatology. If an edit moves these, it changed the model - rerun the
    study before shipping."""
    b = board()
    assert b["asof"] == "2026-06"
    assert b["analogs"][0]["month"] == "2007-07"
    months = {a["month"][:4] for a in b["analogs"]}
    assert months & {"1989", "1990"}          # the 1990 cluster is present
    assert b["analog_recession_within_12m_pct"] >= 50
    assert b["climatology_recession_within_12m_pct"] < 30


def test_gate_skill_split_verdict():
    """The honesty box's core claim, recomputed from the fixture: analogs
    BEAT the base rate on recession-within-12m Brier but LOSE to climatology
    on forward-return MAE. Both halves are load-bearing - the second stops
    anyone reading the panel as a return forecast."""
    s = board()["skill"]
    assert s["n_months"] > 400
    assert s["brier_analog"] < s["brier_base_rate"]
    assert s["ret_mae_analog_pp"] > s["ret_mae_climatology_pp"]


def test_gate_match_strength_is_percentile_not_score():
    b = board()
    for a in b["analogs"]:
        assert 0 <= a["closer_than_pct"] <= 100
    d = [a["distance"] for a in b["analogs"]]
    assert d == sorted(d)                      # ranked ascending
    p = [a["closer_than_pct"] for a in b["analogs"]]
    assert p == sorted(p, reverse=True)


def test_gate_missing_extra_series_raises():
    broken = {**FIX, "CPIAUCSL": []}
    with pytest.raises(RuntimeError):
        cycle_analog.build_vectors(raw_override=broken)


def test_gate_spx_paths_anchored_at_zero():
    for a in board()["analogs"]:
        assert a["spx_path_fwd18"][0] == 0.0
        assert len(a["spx_path_fwd18"]) == 19
