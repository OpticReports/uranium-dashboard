"""Asymmetry-score formula pin: the ~60 anchor + monotonicity guarantees."""
from __future__ import annotations

import pytest

from app.engine.scoring import asymmetry_score


def _score(**kw):
    defaults = dict(impact_weight=1.0, days_to_event=21, drift_z10=0.0,
                    iv_ratio=2.0)
    defaults.update(kw)
    return asymmetry_score(**defaults)


def test_anchor_60():
    """PINNED: impact 1.0, 21 days out, drift 0, iv_ratio 2.0 -> 60.0."""
    res = _score()
    assert res.score == pytest.approx(60.0, abs=1e-9)


def test_score_falls_as_abs_drift_rises():
    drifts = [0.0, 0.5, 1.0, 2.0, 3.0]
    scores = [_score(drift_z10=d).score for d in drifts]
    assert all(a >= b for a, b in zip(scores, scores[1:]))
    assert scores[0] > scores[-1]
    # symmetric in sign
    assert _score(drift_z10=-1.5).score == _score(drift_z10=1.5).score


def test_score_falls_as_days_rise():
    days = [0, 7, 21, 42, 60]
    scores = [_score(days_to_event=d).score for d in days]
    assert all(a > b for a, b in zip(scores, scores[1:]))
    # half-life: 42 days scores half of 21 days (other factors fixed)
    assert scores[3] == pytest.approx(scores[2] / 2)


def test_score_falls_as_iv_ratio_rises():
    ratios = [0.8, 1.0, 1.5, 2.0, 3.0, 4.0]
    scores = [_score(iv_ratio=r).score for r in ratios]
    assert all(a >= b for a, b in zip(scores, scores[1:]))
    assert scores[0] > scores[-1]


def test_iv_unknown_is_neutral_and_flagged():
    res = _score(iv_ratio=None)
    assert res.cheapness_factor == 1.0
    assert "IV unknown" in res.flags
    # neutral == the factor an iv_ratio of exactly 2.0 would give
    assert res.score == pytest.approx(_score(iv_ratio=2.0).score)


def test_drift_unknown_is_neutral_and_flagged():
    res = _score(drift_z10=None)
    assert res.quiet_factor == 1.0
    assert "drift unknown" in res.flags


def test_factor_clamps():
    assert _score(drift_z10=10.0).quiet_factor == 0.25
    assert _score(drift_z10=0.0).quiet_factor == 1.25
    assert _score(iv_ratio=0.1).cheapness_factor == 1.5
    assert _score(iv_ratio=10.0).cheapness_factor == 0.5


def test_bounded_0_100():
    # best case everything: clamped to 100
    res = _score(days_to_event=0, drift_z10=0.0, iv_ratio=0.5)
    assert res.score == 100.0
    res = _score(impact_weight=0.0)
    assert res.score == 0.0


def test_no_dated_event_no_score():
    res = asymmetry_score(1.0, None, 0.0, 1.0)
    assert res.score is None
    assert "no dated event in horizon" in res.flags
    assert asymmetry_score(None, 10, 0.0, 1.0).score is None
    assert asymmetry_score(1.0, -1, 0.0, 1.0).score is None


def test_impact_scales_linearly():
    assert _score(impact_weight=0.9).score == pytest.approx(0.9 * 60.0)
