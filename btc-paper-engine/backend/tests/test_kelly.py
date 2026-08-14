"""Kelly engine validation gates: closed-form recovery, sanity invariants,
determinism. All synthetic/offline."""
import numpy as np

from app.engine.kelly import (analyze, dd_constrained_m, dd_prob, growth,
                              kelly_star, kelly_uncertainty,
                              stationary_bootstrap_idx)


def test_gate_binary_closed_form():
    """Binary bet p=0.6, b=1 (even money): f* = 2p-1 = 0.2. Build the exact
    empirical stream at unit size f=1 scaled so multiplier recovers f*."""
    rng = np.random.default_rng(1)
    r = np.where(rng.random(200000) < 0.6, 1.0, -1.0)      # per-$ bet outcome
    star = kelly_star(r, cap=1.0)
    assert abs(star - 0.2) < 0.01, star
    # p=0.55, b=1.5: f* = (p*b - q)/b = (0.825-0.45)/1.5 = 0.25
    r2 = np.where(rng.random(200000) < 0.55, 1.5, -1.0)
    assert abs(kelly_star(r2, cap=1.0) - 0.25) < 0.012


def test_gate_lognormal_mu_over_sigma2():
    """Small-return gaussian stream: f* ~ mu/sigma^2."""
    rng = np.random.default_rng(2)
    mu, sd = 0.004, 0.03
    r = rng.normal(mu, sd, 300000)
    expect = mu / sd ** 2                                  # ~4.44
    assert abs(kelly_star(r, cap=8.0) - expect) / expect < 0.05


def test_gate_negative_edge_zero():
    rng = np.random.default_rng(3)
    r = rng.normal(-0.002, 0.03, 5000)
    assert kelly_star(r) == 0.0
    a = analyze(list(r), "loser")
    assert a["kelly_m"] == 0.0 and "NEGATIVE EDGE" in a["verdict"]
    assert a["recommended_m"] == 0.0


def test_gate_dd_monotone_in_m():
    rng = np.random.default_rng(4)
    r = rng.normal(0.004, 0.04, 150)
    ps = [dd_prob(r, m, 0.20) for m in (0.5, 1.0, 2.0, 3.0)]
    assert all(b >= a - 0.02 for a, b in zip(ps, ps[1:])), ps
    # constrained m respects the constraint and loosens with the dd limit
    m20 = dd_constrained_m(r, 0.20, 0.10)
    m30 = dd_constrained_m(r, 0.30, 0.10)
    assert m30 >= m20
    assert dd_prob(r, max(m20 - 0.05, 0.0), 0.20) <= 0.12


def test_gate_ruin_guard_and_feasibility():
    """A stream containing a -60% step must cap feasible m below 1/0.6."""
    r = np.array([0.05] * 50 + [-0.60])
    star = kelly_star(r)
    assert star < 0.99 / 0.60
    assert growth(r, 2.0) == -np.inf                       # ruinous sizing


def test_gate_deterministic_and_asymmetry():
    rng = np.random.default_rng(5)
    r = rng.normal(0.005, 0.05, 120)
    a1, a2 = analyze(list(r), "x"), analyze(list(r), "x")
    assert a1 == a2                                        # seeded end-to-end
    star = kelly_star(r)
    if star > 0:
        # over-betting hurts more than equal under-betting (g-curve asymmetry
        # — the reason fractional Kelly is the safe default)
        assert (growth(r, star * 0.5) - growth(r, star * 1.5)) > -1e-12


def test_gate_bootstrap_and_small_sample():
    rng = np.random.default_rng(6)
    idx = stationary_bootstrap_idx(100, rng)
    assert len(idx) == 100 and idx.min() >= 0 and idx.max() < 100
    r = rng.normal(0.004, 0.04, 60)
    unc = kelly_uncertainty(r, draws=300)
    assert unc["p10"] <= unc["p50"] <= unc["p90"]
    a = analyze(list(rng.normal(0.004, 0.04, 10)), "tiny")
    assert "insufficient sample" in a["verdict"]
    # recommendation never exceeds the DD-constrained or conservative size
    b = analyze(list(rng.normal(0.006, 0.04, 140)), "ok")
    assert b["recommended_m"] <= b["conservative_m"] + 1e-9
    assert b["recommended_m"] <= b["dd_constrained"]["p_maxdd30_le_10pct"] + 1e-9


def test_gate_kill_rule_and_analytic_dd():
    """Verifier round: (1) kill rule — a marginal edge with >25% of bootstrap
    resamples non-positive gets rec 0; (2) empirical DD-constrained m agrees
    with Thorp's infinite-horizon law within ~35% on gaussian streams (the
    law is 'ever', ours is finite-horizon — ours should be >= analytic)."""
    rng = np.random.default_rng(9)
    weak = rng.normal(0.0015, 0.04, 70)                    # SR ~0.04: noise edge
    a = analyze(list(weak), "weak")
    if a["bootstrap"]["prob_negative_edge"] > 0.25:
        assert a["recommended_m"] == 0.0
        assert "NOT DISTINGUISHABLE" in a["verdict"] or "NEGATIVE" in a["verdict"]
    strong = rng.normal(0.006, 0.04, 140)
    b = analyze(list(strong), "strong")
    ad = b["dd_constrained"]["analytic_dd30"]
    em = b["dd_constrained"]["p_maxdd30_le_10pct"]
    if b["kelly_m"] > 0.2 and ad > 0.05:
        assert em >= ad * 0.65                             # finite-horizon looser
    assert b["shrinkage_c_star"] > 0
    assert b["recommended_m"] <= b["shrinkage_c_star"] * b["kelly_m"] + 1e-9 \
        or b["recommended_m"] <= b["bootstrap"]["p10"] + 1e-9 \
        or b["recommended_m"] <= b["half_kelly_m"] + 1e-9
