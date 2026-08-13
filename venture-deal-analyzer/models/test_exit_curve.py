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


def test_tail_alpha_in_literature_range():
    cal = ec._load_calibration()
    for stage, spec in cal["stages"].items():
        a = spec["fitted_params"]["alpha"]
        assert 1.4 <= a <= 2.6, f"{stage} tail alpha {a} outside published venture range"


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
