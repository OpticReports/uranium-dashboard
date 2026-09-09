"""Gate tests for the HSR threshold-drift correction.

These gates exist because the correction they guard is LARGE and highly
sensitive to alpha: restating a $15M-threshold count onto a $50M
reference shrinks it by 62% at alpha=0.8 and 91% at alpha=2.0 - a 2.6x
spread across a plausible alpha range. An estimator bug here would not
look like a bug; it would look like a finding about the 1990s.
"""

import ma_hsr_threshold as h


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


# --- Within-regime drift correction and the ship test ---------------

def test_drift_correction_direction():
    """A year whose threshold was real-terms LOOSER than the reference
    (smaller share of GDP, so catching more small deals) must be
    revised DOWN. Backwards, this would amplify bracket creep instead
    of removing it - and would make the 1990s look like a bigger boom
    than the raw data already does."""
    counts = {1990: 1000, 2000: 1000}
    thr = {1990: 15.0, 2000: 15.0}
    gdp = {1990: 6000.0, 2000: 10000.0}   # threshold erodes as GDP grows
    out = h.correct_drift(counts, thr, gdp, 1.4, 2000)
    assert out[2000] == 1000
    assert out[1990] > 1000, (
        "1990 had a real-terms TIGHTER threshold, so its count must be "
        "revised UP relative to 2000")


def test_drift_correction_is_identity_at_reference():
    counts = {1995: 2778, 2000: 4810}
    thr = {1995: 15.0, 2000: 15.0}
    gdp = {1995: 7640.0, 2000: 10250.0}
    out = h.correct_drift(counts, thr, gdp, 1.3, 2000)
    assert abs(out[2000] - 4810) < 1e-9


def test_drift_correction_vanishes_at_alpha_zero():
    counts = {1990: 1952, 2000: 4810}
    thr = {1990: 15.0, 2000: 15.0}
    gdp = {1990: 5963.0, 2000: 10250.0}
    out = h.correct_drift(counts, thr, gdp, 0.0, 2000)
    assert abs(out[1990] - 1952) < 1e-9


def test_rank_stability_detects_reordering():
    """The ship test must actually FAIL when it should. Measured on the
    real 1990s series across a wide alpha range (0.8-2.0) the ordering
    is NOT stable - 9 distinct orderings, max rank shift 5, with 1990
    (the raw-terms trough) promoted into the top three at alpha=2.0.
    If this gate ever passes on that interval, the test has stopped
    testing."""
    counts = {y: c for y, c in zip(
        range(1990, 2001),
        [1952, 1537, 1621, 1966, 2476, 2778, 3222, 4044, 4577, 4828, 4810])}
    thr = {y: 15.0 for y in counts}
    gdp = {y: g for y, g in zip(range(1990, 2001), [
        5963, 6158, 6520, 6859, 7287, 7640, 8073, 8578, 9063, 9631, 10251])}
    inv, shift, _ = h.rank_stability(counts, thr, gdp, 0.8, 2.0, 2000)
    assert inv > 0 and shift >= 3, (
        "a 1.2-wide alpha interval must reorder the 1990s - if it does "
        "not, the stability test is not measuring anything")


def test_rank_stability_passes_on_a_tight_interval():
    """And must PASS when alpha is pinned. A degenerate interval cannot
    reorder anything."""
    counts = {y: c for y, c in zip(
        range(1990, 2001),
        [1952, 1537, 1621, 1966, 2476, 2778, 3222, 4044, 4577, 4828, 4810])}
    thr = {y: 15.0 for y in counts}
    gdp = {y: g for y, g in zip(range(1990, 2001), [
        5963, 6158, 6520, 6859, 7287, 7640, 8073, 8578, 9063, 9631, 10251])}
    inv, shift, _ = h.rank_stability(counts, thr, gdp, 1.40, 1.40, 2000)
    assert inv == 0 and shift == 0


def test_varying_alpha_matches_fixed_when_alpha_is_constant():
    """The per-year-alpha correction must reduce to the single-alpha one
    when every year carries the same exponent. Guards against the two
    code paths silently diverging."""
    counts = {1990: 1952, 1995: 2778, 2000: 4810}
    thr = {y: 15.0 for y in counts}
    gdp = {1990: 5963.0, 1995: 7640.0, 2000: 10251.0}
    fixed = h.correct_drift(counts, thr, gdp, 0.7, 2000)
    vary = h.correct_drift_varying(counts, thr, gdp,
                                   {y: 0.7 for y in counts}, 2000)
    for y in counts:
        assert abs(fixed[y] - vary[y]) < 1e-9


def test_varying_alpha_skips_years_without_an_estimate():
    """A year with no fitted exponent must be DROPPED, never silently
    given a neighbour's or a pooled default - that would smuggle an
    assumption into a series whose whole point is being measured."""
    counts = {1990: 1952, 1995: 2778}
    thr = {y: 15.0 for y in counts}
    gdp = {1990: 5963.0, 1995: 7640.0}
    out = h.correct_drift_varying(counts, thr, gdp, {1990: 0.73}, 1990)
    assert 1995 not in out and 1990 in out


# --- The SHIPPED, model-free correction ----------------------------

BR_1995 = [(15, 25, 607), (25, 50, 697), (50, 100, 465), (100, 150, 209),
           (150, 200, 136), (200, 300, 127), (300, 500, 102),
           (500, 1000, 74), (1000, None, 79)]


def test_survival_matches_bracket_edges_exactly():
    """At a bracket boundary the interpolation must return the exact
    published survival - no smoothing across the edge."""
    total = sum(c for _, _, c in BR_1995)
    assert abs(h.survival_at(BR_1995, 15) - total) < 1e-9
    assert abs(h.survival_at(BR_1995, 25) - (total - 607)) < 1e-9
    assert abs(h.survival_at(BR_1995, 50) - (total - 607 - 697)) < 1e-9


def test_survival_is_monotone_decreasing():
    prev = float("inf")
    for v in (15, 18, 25, 40, 50, 90, 100, 175, 250, 400, 900, 1500):
        cur = h.survival_at(BR_1995, v)
        assert cur <= prev, f"survival rose at {v}"
        prev = cur


def test_survival_interpolates_inside_a_bracket():
    """Strictly between edges, strictly between the edge values."""
    hi = h.survival_at(BR_1995, 15)
    lo = h.survival_at(BR_1995, 25)
    mid = h.survival_at(BR_1995, 20)
    assert lo < mid < hi


def test_drift_factors_are_at_most_one_with_earliest_reference():
    """With the reference at the EARLIEST year, every later year is
    compared against a real-terms tighter bar, so every factor must be
    <= 1. A factor above 1 means the reference is not the earliest and
    the correction has become an extrapolation below the data."""
    brackets = {1990: BR_1995, 1995: BR_1995, 2000: BR_1995}
    gdp = {1990: 5963.0, 1995: 7640.0, 2000: 10251.0}
    f = h.drift_factors(brackets, gdp, 15.0, 1990)
    assert abs(f[1990] - 1.0) < 1e-9
    for y in (1995, 2000):
        assert f[y] < 1.0


def test_correction_shrinks_the_apparent_1990s_boom():
    """The headline: raw fiscal-year rise 2.18x, corrected 1.70x, so
    bracket creep explains ~22% - NOT the 33% the rejected power-law
    version claimed. Pinned so a regression cannot quietly restore the
    overcorrection."""
    counts = {1990: 2262.0, 2000: 4926.0}
    factors = {1990: 1.000, 2000: 0.780}
    out = h.correct_measured(counts, factors)
    raw = counts[2000] / counts[1990]
    corr = out[2000] / out[1990]
    creep = 1 - corr / raw
    assert 0.18 < creep < 0.26, f"creep {creep:.3f} outside the measured band"


def test_correct_measured_drops_years_without_a_factor():
    """An uncorrected year silently mixed among corrected ones is the
    exact artifact this module removes."""
    out = h.correct_measured({1990: 100.0, 1999: 200.0}, {1990: 1.0})
    assert 1999 not in out and 1990 in out


def test_closed_top_bin_likelihood_is_normalized():
    """Latent defect found by adversarial review: with a closed final
    edge the bin probabilities summed to 0.90, so the 'likelihood' was
    not one and the restricted-range MLE was badly wrong (1.221 against
    a correct 0.335 on one test case). Recovery on a truncated sample
    is the check that it is now normalized."""
    import random
    random.seed(5)
    true, b0, bk = 0.8, 15.0, 100.0
    vals = []
    while len(vals) < 60000:
        v = b0 * (1 - random.random()) ** (-1 / true)
        if v < bk:
            vals.append(v)
    edges = [15, 25, 50, 100]
    counts = [0, 0, 0]
    for v in vals:
        for i in range(3):
            if edges[i] <= v < edges[i + 1]:
                counts[i] += 1
                break
    est, _ = h.fit_binned(edges, counts)
    assert abs(est - true) < 0.03, f"truncated MLE off: {est}"


def test_open_bin_fits_unchanged_by_the_normalization_fix():
    """Regression pin: the shipped diagnostic exponents must not have
    moved when the closed-bin path was fixed."""
    edges = [15, 25, 50, 100, 150, 200, 300, 500, 1000, None]
    counts = [607, 697, 465, 209, 136, 127, 102, 74, 79]
    est, _ = h.fit_binned(edges, counts)
    assert abs(est - 0.6906) < 0.002
