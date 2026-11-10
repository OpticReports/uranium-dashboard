"""Merge-blocking gate tests for the exit-curve model.

Gate philosophy: the model may only ship numbers if (1) its base
distribution provably reproduces the published empirical bucket
frequencies, (2) its tail exponent sits inside the published venture
power-law range, (3) the deal tilt matches the ledger's logged
forecasts exactly, and (4) basic probability sanity holds everywhere.
"""

import math

import exit_curve as ec


def test_fit_reproduces_published_buckets_seed():
    ok, details = ec.fit_check("seed", tol=0.015)
    assert ok, f"base fit off empirical anchor: {details}"


def test_fit_reproduces_published_buckets_series_b():
    ok, details = ec.fit_check("series_b", tol=0.015)
    assert ok, f"base fit off empirical anchor: {details}"


def test_tail_alpha_finite_mean_and_in_range():
    """Survival-exponent convention: CSN density alpha = this alpha + 1.

    REVISED 2026-08-20 for the measured stage curves. The exponent
    implied DIRECTLY by PitchBook's measured 20-50x and >50x buckets is
    seed 0.94, A 1.20, B 1.24, C 1.46, D+ 0.76. Two of those are <= 1,
    which means NO FINITE MEAN - the measured top bucket is open-ended
    (50x+) and absorbs outcomes like Uber's 5,230x seed MOIC.

    For seed and D+ those two buckets sit at the +/-0.5pp recovery
    precision floor, so the ratio is not determined by the data and the
    fit is constrained to alpha >= 1.0. Every stage must therefore have
    a finite mean, and must stay under the upper literature bound."""
    cal = ec._load_calibration()
    for stage, spec in cal["stages"].items():
        a = spec["fitted_params"]["alpha"]
        assert a > 1.0, f"{stage} survival alpha {a} <= 1 implies an infinite mean"
        assert a <= 2.0, f"{stage} survival alpha {a} above published range"


def test_series_b_tail_thinner_than_seed():
    """Stage conditioning must be directionally right: B-round tail thinner."""
    for t in (20, 50):
        xs_s, ps_s = ec.base_distribution("seed")
        xs_b, ps_b = ec.base_distribution("series_b")
        p_s = sum(p for x, p in zip(xs_s, ps_s) if x >= t)
        p_b = sum(p for x, p in zip(xs_b, ps_b) if x >= t)
        assert p_b < p_s, (t, p_b, p_s)


def test_tilt_matches_logged_forecasts_exactly():
    xs, ps = ec.base_distribution("seed")
    for p1, p10 in [(0.60, 0.04), (0.65, 0.04), (0.50, 0.10), (0.72, 0.05)]:
        q = ec.tilt_to_forecasts(xs, ps, p1, p10)
        got_lo = sum(p for x, p in zip(xs, q) if x < 1.0)
        got_hi = sum(p for x, p in zip(xs, q) if x >= 10.0)
        assert abs(got_lo - p1) < 1e-6, (p1, got_lo)
        assert abs(got_hi - p10) < 1e-6, (p10, got_hi)


def test_probabilities_sane():
    out = ec.exceedance_curve("seed", 0.60, 0.04)
    g = out["gross_exceedance"]
    keys = sorted(g.keys())
    # monotone non-increasing exceedance
    for a, b in zip(keys, keys[1:]):
        assert g[a] >= g[b] - 1e-12
    assert all(0.0 <= v <= 1.0 for v in g.values())
    # net exceedance never exceeds gross at same threshold (fees only hurt)
    for t in keys:
        assert out["net_exceedance"][t] <= g[t] + 1e-12
    # distribution integrates to 1
    xs, ps = ec.base_distribution("seed")
    assert abs(sum(ps) - 1.0) < 1e-9


def test_untilted_base_is_recovered_when_constraints_match_base():
    """Tilting to the base's own masses must be (near) identity."""
    xs, ps = ec.base_distribution("seed")
    m_lo = sum(p for x, p in zip(xs, ps) if x < 1.0)
    m_hi = sum(p for x, p in zip(xs, ps) if x >= 10.0)
    q = ec.tilt_to_forecasts(xs, ps, m_lo, m_hi)
    max_dev = max(abs(a - b) for a, b in zip(ps, q))
    assert max_dev < 1e-9


def test_fee_mapping_matches_audited_ev_tree_model():
    assert abs(ec.net_multiple(12.25) - 10.0) < 0.01  # "10x net needs ~12.25x gross"
    assert ec.net_multiple(1.0) == 0.95
    assert abs(ec.net_multiple(2.2) - 1.96) < 1e-9


STAGES = ("seed", "series_a", "series_b", "series_c", "series_d_plus")


def test_truncation_mass_bounded():
    """Audit finding 4, REVISED 2026-08-20. The binding constraint is now
    UPPER truncation. base_distribution() pins each stage's measured loss
    mass exactly, so low-end truncation no longer distorts the result -
    but mass discarded above GRID_HI is real upside and biases EV down."""
    for stage in STAGES:
        assert ec.upper_truncation_mass(stage) < 0.005, (
            stage, ec.upper_truncation_mass(stage))


def test_loss_mass_is_pinned_to_the_measured_figure():
    """Each stage's P(<1x) must equal its published measured value to
    within rounding - it is measured, not inferred, so it is pinned."""
    cal = ec._load_calibration()
    for stage in STAGES:
        target = cal["stages"][stage]["target_buckets"]["lt1"]
        xs, ps = ec.base_distribution(stage)
        got = sum(p for x, p in zip(xs, ps) if x < 1.0)
        assert abs(got - target) < 1e-6, (stage, got, target)


def test_loss_mass_decreases_monotonically_with_stage():
    """Measured structural fact: later stages lose money less often.
    81.2 / 66.0 / 55.4 / 50.7 / 48.4 across seed -> D+."""
    cal = ec._load_calibration()
    lt1 = [cal["stages"][s]["target_buckets"]["lt1"] for s in STAGES]
    assert lt1 == sorted(lt1, reverse=True), lt1


def test_validation_lock_series_c_plus_reproduces_pitchbook_labels():
    """The recovered values are only trustworthy because mean(C, D+)
    reproduces PitchBook's PRINTED Series C+ labels 50/41/6/2/1/0. If a
    future edit breaks that, the recovery is no longer corroborated."""
    cal = ec._load_calibration()
    c = cal["stages"]["series_c"]["target_buckets"]
    d = cal["stages"]["series_d_plus"]["target_buckets"]
    printed = [0.50, 0.41, 0.06, 0.02, 0.01, 0.00]
    for i, k in enumerate(["lt1", "1_5", "5_10", "10_20", "20_50", "gt50"]):
        assert abs((c[k] + d[k]) / 2 - printed[i]) < 0.006, (k, (c[k] + d[k]) / 2)


def test_validation_lock_seed_matches_pitchbook_prose():
    """PitchBook prose: 'as much as 81% of seed investments return less
    than the original cost.' Recovered seed lt1 must agree."""
    cal = ec._load_calibration()
    assert abs(cal["stages"]["seed"]["target_buckets"]["lt1"] - 0.81) < 0.01


def test_input_validation():
    """Audit finding 5: impossible forecasts must raise, not produce garbage."""
    xs, ps = ec.base_distribution("seed")
    import pytest
    for bad in [(-0.1, 0.04), (1.1, 0.04), (0.6, 0.5), (0.7, 0.35)]:
        with pytest.raises(ValueError):
            ec.tilt_to_forecasts(xs, ps, *bad)


def test_ev_reconciles_with_audited_tree():
    """Audit finding 12, REWRITTEN 2026-08-20.

    The old form compared the curve's UNCAPPED EV to the audited
    discrete tree's 1.645 and allowed a +/-0.35 band. That compares
    unlike objects: the tree tops out at a finite best-case branch, the
    curve carries an unbounded Pareto tail. The band had to be wide to
    accommodate the mismatch - and it was wide enough to conceal a real
    tail-underfit in the seed base curve (the >50x bucket was fitted
    39% below its published target while every gate passed).

    Capping the curve at the tree's top branch makes the comparison
    like-for-like.

    REBASED 2026-08-20 AGAIN: the audited tree's 1.645 was derived when
    the base curve was the vector mislabeled 'seed' (actually
    Correlation's all-stages pooled figure). The measured stage curves
    carry materially more mass in the 1-20x region, so capped EV now
    sits ~0.30 above the tree. That is a REAL divergence, recorded
    rather than re-banded away: the curve must still exceed the tree
    (it has continuous mass the tree's discrete branches miss) but by a
    bounded amount.

    FOLLOW-UP OWED: re-derive the audited discrete trees against the
    measured stage curves. Until then the TREE headlines on any display
    and this gate only bounds the divergence.
    """
    capped = ec.ev_capped("seed", 0.60, 0.04, cap=20.0)
    assert capped > 1.645, capped
    assert capped - 1.645 < 0.40, capped


def test_uncapped_tail_premium_is_disclosed_and_bounded():
    """The EV the curve earns above the tree's top branch is real but
    rides on a very small probability mass. It must be reportable, and
    it must not come to dominate the estimate.

    BOUND RAISED 25% -> 40% on 2026-08-20, with cause. At the measured
    survival exponents (1.05-1.35) the tail legitimately carries about a
    third of uncapped EV on ~2% of outcomes. That is what the data says,
    and it is precisely why CAPPED EV is the headline statistic and
    uncapped EV is not a robust one."""
    premium, mass = ec.uncapped_tail_premium("seed", 0.60, 0.04, cap=20.0)
    full = ec.exceedance_curve("seed", 0.60, 0.04)["ev_net"]
    assert premium > 0, premium
    assert mass < 0.03, mass
    assert premium / full < 0.40, (premium, full, premium / full)


def test_base_curves_fit_published_buckets_in_relative_terms():
    """The absolute gate is structurally blind to the tail: at tol=0.015
    a bucket whose published target is 0.004 can be underfit by 375% and
    pass. Base-rate answers are read straight off these curves with no
    deal-level tilt to protect them, so the tail must fit in RELATIVE
    terms too."""
    for stage in ("seed", "series_b"):
        ok, details = ec.fit_check_relative(stage, rel_tol=0.10)
        assert ok, (stage, details)


def test_series_b_loss_mass_is_the_measured_value():
    """SUPERSEDED AND INVERTED 2026-08-20. The old gate required B loss
    mass in [0.40, 0.50], from a CONSTRUCTED vector whose 0.40 floor was
    cited to a 'CV dollar-basis 37%' that is actually Correlation's
    ALL-STAGES POOLED dollar-weighted figure, not a Series B figure.

    Measured Series B loss mass is 0.554 - the old construction was
    14pp OPTIMISTIC, and the old gate would now REJECT the true value.
    A gate built on a mislabeled source defended the wrong number."""
    cal = ec._load_calibration()
    lt1 = cal["stages"]["series_b"]["target_buckets"]["lt1"]
    assert abs(lt1 - 0.554) < 0.002, lt1
