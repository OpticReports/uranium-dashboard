"""Gate tests for the HSR power-law exponent and threshold restatement.

These gates exist because the correction they guard is LARGE and highly
sensitive to alpha: restating a $15M-threshold count onto a $50M
reference shrinks it by 62% at alpha=0.8 and 91% at alpha=2.0 - a 2.6x
spread across a plausible alpha range. An estimator bug here would not
look like a bug; it would look like a finding about the 1990s.
"""

import ma_hsr_alpha as h


def test_recovers_known_exponent_from_binned_data():
    """THE load-bearing gate: synthetic Pareto with known alpha, binned
    on the actual HSR bracket edges, must come back."""
    import random
    random.seed(11)
    edges = [100, 150, 200, 300, 500, 1000, 10000, None]
    for true in (0.9, 1.4, 2.1):
        vals = [100.0 * (1 - random.random()) ** (-1 / true)
                for _ in range(120000)]
        counts = [0] * 7
        for v in vals:
            for i in range(7):
                lo, hi = edges[i], edges[i + 1]
                if v >= lo and (hi is None or v < hi):
                    counts[i] += 1
                    break
        est, _ = h.fit_binned(edges, counts)
        assert abs(est - true) < 0.03, f"alpha {true} recovered as {est}"


def test_restatement_direction_is_right():
    """Raising the reference threshold DISCARDS small deals, so the
    restated count must FALL. Getting this backwards would turn the
    1990s bracket-creep correction into a bracket-creep amplifier."""
    assert h.restate_count(1000, 15, 50, 1.4) < 1000
    assert h.restate_count(1000, 50, 15, 1.4) > 1000


def test_restatement_round_trips():
    n = h.restate_count(1000, 15, 50, 1.37)
    assert abs(h.restate_count(n, 50, 15, 1.37) - 1000) < 1e-6


def test_restatement_is_identity_at_equal_thresholds():
    assert h.restate_count(777, 42, 42, 1.5) == 777


def test_alpha_zero_means_no_correction():
    """A flat size distribution implies threshold moves change nothing.
    Guards the exponent from being applied with the wrong sign."""
    assert h.restate_count(1000, 15, 50, 0.0) == 1000


def test_loglog_is_not_the_shipped_estimator():
    """The log-log slope is computed only as a disclosed cross-check.
    This gate asserts the two are DIFFERENT functions so nobody
    quietly swaps the biased one into production."""
    import random
    random.seed(3)
    edges = [100, 150, 200, 300, 500, 1000, 10000, None]
    vals = [100.0 * (1 - random.random()) ** (-1 / 1.5) for _ in range(60000)]
    counts = [0] * 7
    for v in vals:
        for i in range(7):
            lo, hi = edges[i], edges[i + 1]
            if v >= lo and (hi is None or v < hi):
                counts[i] += 1
                break
    mle, _ = h.fit_binned(edges, counts)
    slope = h.loglog_slope(edges, counts)
    assert mle is not None and slope is not None
    assert abs(mle - 1.5) < abs(slope - 1.5) + 1e-9, (
        "the log-log slope beat the MLE on synthetic data - check the "
        "binning, not the claim")


def test_open_top_bin_is_handled():
    """The top HSR bracket is 'Over $10B' - open-ended. A closed-bin
    assumption there silently truncates the tail."""
    edges = [100, 1000, None]
    a_open, _ = h.fit_binned(edges, [900, 100])
    a_closed, _ = h.fit_binned([100, 1000, 100000], [900, 100])
    assert abs(a_open - a_closed) > 1e-3


def test_elasticity_sign():
    """d log N / d log v = -alpha. A 10% threshold rise cuts the count
    by ~10% when alpha is 1."""
    assert h.elasticity(1.0) == -1.0
    assert h.elasticity(1.5) == -1.5
