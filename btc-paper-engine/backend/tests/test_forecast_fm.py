"""Gate tests for the forecasting study (RESEARCH_FORECAST_FM.md).

A forecasting study fails in exactly two ways that a passing script cannot
show you: the target leaks the future into the features, and the holdout
gets touched. Both are here, and neither is subtle to test - which is the
argument for testing them rather than being careful.
"""
from __future__ import annotations

import numpy as np
import pytest

from research.forecast_fm import data as D
from research.forecast_fm import metrics as M
from research.forecast_fm import models as Mod


def _bars(n=200, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return {"ts": np.arange(n, dtype=np.int64) * D.BAR_SECONDS + 1_640_995_200,
            "open": c, "close": c,
            "high": c * 1.004, "low": c * 0.996}


def test_gate_the_target_is_strictly_forward():
    """THE leakage test. sigma[t] must be built only from bars after t. If
    it ever includes bar t, every model gets a free look at the answer and
    the whole study produces a beautiful, meaningless result."""
    b = _bars()
    y = D.forward_realized_vol(b["close"], horizon=8)
    r = D.log_returns(b["close"])
    for t in (20, 55, 120):
        expect = float(np.std(r[t + 1:t + 9], ddof=1))
        assert y[t] == pytest.approx(expect, rel=1e-12)


def test_gate_a_future_spike_does_not_leak_backwards():
    """Same property, stated the way it would actually break: a violent
    period must not raise the target for bars BEFORE it."""
    n = 200
    c = np.full(n, 100.0)
    c[150:] = 100.0 * np.cumprod(np.r_[1.0, np.repeat(1.05, n - 151)])
    y = D.forward_realized_vol(c, horizon=8)
    assert y[100] == pytest.approx(0.0, abs=1e-12), "calm bar saw the spike"
    assert y[145] > 0, "the bar 5 before the spike should see it"


def test_gate_the_holdout_is_sealed_by_default():
    """A holdout reachable by accident is a validation set with a grander
    name. Section 8 allows ONE touch, deliberately."""
    b = _bars(n=11000)
    m = D.split_masks(b["ts"])
    assert m["holdout"].sum() == 0
    assert D.split_masks(b["ts"], unseal_holdout=True)["holdout"].sum() > 0


def test_gate_the_splits_are_chronological_and_disjoint():
    b = _bars(n=11000)
    m = D.split_masks(b["ts"], unseal_holdout=True)
    assert not (m["train"] & m["validate"]).any()
    assert not (m["validate"] & m["holdout"]).any()
    assert b["ts"][m["train"]].max() < b["ts"][m["validate"]].min()
    assert b["ts"][m["validate"]].max() < b["ts"][m["holdout"]].min()


def test_gate_evaluation_points_do_not_overlap():
    """sigma[t] and sigma[t+1] share 7 of 8 returns. Scoring every bar would
    count one observation eight times and make every difference look far
    more significant than it is."""
    mask = np.ones(1000, dtype=bool)
    idx = D.eval_index(mask, np.ones(1000, dtype=bool), horizon=8)
    assert np.all(np.diff(idx) == 8)


def test_gate_bars_must_be_strictly_ordered(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("ts_open_unix,open,high,low,close,volume\n"
                 "200,1,1,1,1,1\n100,1,1,1,1,1\n")
    with pytest.raises(ValueError, match="strictly increasing"):
        D.load_bars(str(p))


def test_gate_the_spread_cannot_be_used_before_it_is_fitted():
    with pytest.raises(RuntimeError, match="before it was fitted"):
        Mod.QuantileDressing().apply(np.array([0.01]))


def test_gate_the_spread_refuses_a_sample_too_small_to_calibrate():
    d = Mod.QuantileDressing()
    with pytest.raises(ValueError, match="refusing to calibrate"):
        d.fit(np.ones(10), np.ones(10))


def test_gate_pinball_is_asymmetric_in_the_right_direction():
    """At tau=0.9 an outcome ABOVE the forecast must cost more than one
    below - that asymmetry is the only thing stopping the high quantiles
    from being optimistic, which is the failure that under-sizes risk."""
    over = M.pinball(np.array([2.0]), np.array([1.0]), 0.9)
    under = M.pinball(np.array([0.0]), np.array([1.0]), 0.9)
    assert over[0] > under[0]
    assert over[0] == pytest.approx(0.9)
    assert under[0] == pytest.approx(0.1)


def test_gate_the_coverage_gate_matches_the_registered_thresholds():
    """Section 4 rule 1: 0.80 +/- 5pp, and it is a rejection outside that."""
    n = 1000
    Q = np.tile(np.linspace(0.0, 1.0, 9), (n, 1))
    y = np.full(n, 0.5)                       # everything inside the band
    assert M.coverage(y, Q) == pytest.approx(1.0)
    assert not M.passes_coverage_gate(y, Q)   # 1.00 is a FAIL, not a bonus
    y2 = np.where(np.arange(n) < 800, 0.5, 5.0)
    assert M.passes_coverage_gate(y2, Q)


def test_gate_a_perfectly_calibrated_forecast_traces_the_diagonal():
    rng = np.random.default_rng(1)
    y = rng.normal(0, 1, 40000)
    Q = np.tile(np.quantile(y, M.LEVELS), (y.size, 1))
    assert np.allclose(M.coverage_by_level(y, Q), M.LEVELS, atol=0.01)


def test_gate_garch_is_constrained_to_stationarity():
    """alpha+beta >= 1 makes the multi-step forecast diverge instead of
    mean-reverting, and an 8-step forecast would then be nonsense."""
    rng = np.random.default_rng(2)
    a, b, _ = 0, 0, 0
    o, a, b = Mod.garch11_fit(rng.normal(0, 0.01, 1500))
    assert 0 < a + b < 1.0
    assert o > 0


def test_gate_the_range_estimator_sees_what_closes_cannot():
    """A bar that travelled and came back is flat to a close-to-close
    estimator and violent to a range one. This is the difference that
    explained the whole model ranking in stage 1, so it is worth pinning."""
    bars = {"high": np.array([110.0]), "low": np.array([90.0]),
            "close": np.array([100.0])}
    assert Mod.parkinson_sigma(bars)[0] > 0.1
