"""Unit tests for the scoring math with KNOWN inputs/outputs.

These pin the core formulas so retuning weights (config) can't silently break
the mechanics, and so the NULL-vs-zero distinction is enforced.
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from app.scoring import components as C
from app.utils import normalize as N


# --- normalize helpers -------------------------------------------------------

def test_zscore_basic():
    pop = [0.0, 10.0]  # mean 5, pstdev 5
    assert N.zscore(10.0, pop) == pytest.approx(1.0)
    assert N.zscore(0.0, pop) == pytest.approx(-1.0)
    assert N.zscore(5.0, pop) == pytest.approx(0.0)


def test_zscore_none_and_no_variance():
    assert N.zscore(None, [1.0, 2.0]) is None       # value missing
    assert N.zscore(1.0, [None]) is None            # <2 real points
    assert N.zscore(5.0, [5.0, 5.0]) == 0.0         # zero variance -> 0


def test_zscore_ignores_none_in_population():
    assert N.zscore(10.0, [0.0, None, 10.0]) == pytest.approx(1.0)


def test_zscore_to_0_100_mapping():
    assert N.zscore_to_0_100(0.0) == pytest.approx(50.0)
    assert N.zscore_to_0_100(3.0) == pytest.approx(100.0)
    assert N.zscore_to_0_100(-3.0) == pytest.approx(0.0)
    assert N.zscore_to_0_100(99.0) == pytest.approx(100.0)  # clipped
    assert N.zscore_to_0_100(None) is None


def test_percentile_rank():
    pop = [1.0, 2.0, 3.0, 4.0]
    assert N.percentile_rank(4.0, pop) == pytest.approx(1.0)
    assert N.percentile_rank(2.0, pop) == pytest.approx(0.5)
    assert N.percentile_rank(None, pop) is None


def test_exp_time_decay():
    assert N.exp_time_decay(0, 30) == 1.0          # now / past => full weight
    assert N.exp_time_decay(-5, 30) == 1.0
    assert N.exp_time_decay(30, 30) == pytest.approx(0.5)   # one half-life
    assert N.exp_time_decay(60, 30) == pytest.approx(0.25)  # two half-lives


# --- revision velocity -------------------------------------------------------

def test_revision_velocity_none_when_empty():
    assert C.revision_velocity_raw([], date(2026, 1, 1), 90, 30) is None


def test_revision_velocity_net_zero_is_zero_not_none():
    asof = date(2026, 1, 31)
    revs = [
        C.RevisionLike(asof, +1),   # age 0 -> decay 1
        C.RevisionLike(asof, -1),   # age 0 -> decay 1
    ]
    assert C.revision_velocity_raw(revs, asof, 90, 30) == pytest.approx(0.0)


def test_revision_velocity_recency_weighting():
    asof = date(2026, 1, 31)
    revs = [
        C.RevisionLike(asof, +1),                       # decay 1.0
        C.RevisionLike(date(2026, 1, 1), +1),           # age 30 -> decay 0.5
    ]
    assert C.revision_velocity_raw(revs, asof, 90, 30) == pytest.approx(1.5)


def test_revision_velocity_excludes_outside_window():
    asof = date(2026, 1, 31)
    revs = [C.RevisionLike(date(2025, 1, 1), +1)]  # >90d old
    assert C.revision_velocity_raw(revs, asof, 90, 30) is None


# --- catalyst score ----------------------------------------------------------

def test_catalyst_score_zero_when_none_upcoming():
    asof = date(2026, 1, 1)
    assert C.catalyst_score_raw([], asof, 180, 45, {"other": 0.2}) == 0.0


def test_catalyst_score_uses_override_and_decay():
    asof = date(2026, 1, 1)
    weights = {"pdufa": 1.0, "other": 0.2}
    cats = [
        C.CatalystLike(asof, "pdufa"),                      # impact 1.0, decay 1.0
        C.CatalystLike(date(2026, 2, 15), "other", 0.5),   # override 0.5, 45d -> 0.5
    ]
    got = C.catalyst_score_raw(cats, asof, 180, 45, weights)
    assert got == pytest.approx(1.0 * 1.0 + 0.5 * 0.5)


def test_catalyst_score_ignores_past_and_beyond_horizon():
    asof = date(2026, 1, 1)
    weights = {"pdufa": 1.0, "other": 0.2}
    cats = [
        C.CatalystLike(date(2025, 12, 1), "pdufa"),  # past
        C.CatalystLike(date(2027, 1, 1), "pdufa"),   # beyond 180d horizon
    ]
    assert C.catalyst_score_raw(cats, asof, 180, 45, weights) == 0.0


# --- mention acceleration ----------------------------------------------------

def test_mention_acceleration_none_when_too_short():
    assert C.mention_acceleration_raw([1, 2]) is None


def test_mention_acceleration_positive_when_ramping():
    # steadily accelerating series
    accel = C.mention_acceleration_raw([1, 1, 1, 5, 5, 5, 20, 20, 20])
    assert accel is not None and accel > 0


def test_mention_acceleration_linear_is_zero():
    # constant velocity -> zero acceleration
    accel = C.mention_acceleration_raw([0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert accel == pytest.approx(0.0)


# --- price change ------------------------------------------------------------

def test_price_change_fraction():
    assert C.price_change_raw([100.0, 110.0]) == pytest.approx(0.10)


def test_price_change_none_when_insufficient_or_zero_base():
    assert C.price_change_raw([100.0]) is None
    assert C.price_change_raw([0.0, 5.0]) is None


# --- runway penalty ----------------------------------------------------------

def test_runway_penalty_bounds():
    assert C.runway_penalty_magnitude(None, 8, 2) is None    # no data
    assert C.runway_penalty_magnitude(10, 8, 2) == 0.0       # healthy
    assert C.runway_penalty_magnitude(2, 8, 2) == 100.0      # at floor
    assert C.runway_penalty_magnitude(1, 8, 2) == 100.0      # below floor clamps


def test_runway_penalty_linear_midpoint():
    # threshold 8, floor 2 -> midpoint runway 5 -> 50 penalty
    assert C.runway_penalty_magnitude(5, 8, 2) == pytest.approx(50.0)


# --- combine -----------------------------------------------------------------

def test_combine_weighted_mean():
    contribs = {"a": 100.0, "b": 0.0}
    weights = {"a": 3.0, "b": 1.0}
    composite, used = C.combine(contribs, weights)
    assert composite == pytest.approx(75.0)   # (3*100 + 1*0)/4
    assert used == {"a": 3.0, "b": 1.0}


def test_combine_excludes_missing_from_denominator():
    # b is missing -> denominator is only a's weight, NOT dragged toward 0.
    contribs = {"a": 80.0, "b": None}
    weights = {"a": 1.0, "b": 9.0}
    composite, used = C.combine(contribs, weights)
    assert composite == pytest.approx(80.0)
    assert "b" not in used


def test_combine_all_missing_returns_none():
    composite, used = C.combine({"a": None}, {"a": 1.0})
    assert composite is None
    assert used == {}


def test_combine_zero_weight_excluded():
    composite, used = C.combine({"a": 50.0, "b": 90.0}, {"a": 1.0, "b": 0.0})
    assert composite == pytest.approx(50.0)
    assert "b" not in used
