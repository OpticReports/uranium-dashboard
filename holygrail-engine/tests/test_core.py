"""GATES: Dalio numbers; RC sums; every N_eff at the extremes; DR^2 closed
form; Sharpe = S*DR; gearing hits target; financing on borrowed part only;
minimum torsion = identity for diagonal S."""
import math

import numpy as np
import pytest
from scipy.optimize import minimize
from scipy.stats import norm

from holygrail import core
from holygrail.allocate import target_vol_gearing
from holygrail.errors import CovarianceError, ValidationError


# ---------------------------------------------------------------- Dalio ----
def test_dalio_numbers_reproduce():
    assert round(100 * core.equal_corr_vol(0.18, 0.0, 5), 3) == 8.050
    assert round(100 * core.equal_corr_vol(0.18, 0.0, 10), 3) == 5.692
    assert round(100 * core.equal_corr_vol(0.18, 0.0, 15), 3) == 4.648
    rows = {r["n"]: r for r in core.dalio_table(0.18, 0.06, (1, 5, 10, 15), (0.0,))}
    assert round(rows[1]["return_to_risk"], 4) == 0.3333
    assert round(rows[15]["return_to_risk"], 4) == 1.2910
    assert rows[15]["improvement"] == pytest.approx(math.sqrt(15), abs=1e-12)
    assert round(rows[15]["improvement"], 3) == 3.873
    assert rows[15]["neff"] == pytest.approx(15.0)


@pytest.mark.parametrize("n,rho", [(1, 0.0), (5, 0.0), (10, 0.3), (15, 0.6), (7, -0.1), (20, 1.0)])
def test_closed_form_matches_matrix(n, rho):
    S = core.equal_corr_cov(n, 0.18, rho)
    w = np.full(n, 1 / n)
    assert core.portfolio_vol(w, S) == pytest.approx(core.equal_corr_vol(0.18, rho, n), rel=1e-12)


def test_vol_floor_is_limit():
    assert core.equal_corr_vol(0.2, 0.25, 10**7) == pytest.approx(core.vol_floor(0.2, 0.25), rel=1e-6)


def test_rho_below_psd_bound_fails():
    with pytest.raises(ValidationError):
        core.equal_corr_vol(0.2, -0.3, 5)


# ---------------------------------------------------------- validation ----
def test_validation_fails_loudly():
    with pytest.raises(CovarianceError, match="positive semi-definite"):
        core.validate_covariance(np.array([[1.0, 2.0], [2.0, 1.0]]))
    with pytest.raises(CovarianceError, match="NaN"):
        core.validate_covariance(np.array([[1.0, np.nan], [np.nan, 1.0]]))
    with pytest.raises(CovarianceError, match="symmetric"):
        core.validate_covariance(np.array([[1.0, 0.5], [0.1, 1.0]]))
    with pytest.raises(ValidationError, match="sum"):
        core.validate_weights([0.5, 0.4], sum_to=1.0)
    with pytest.raises(ValidationError, match="NaN"):
        core.portfolio_vol([np.nan, 1.0], np.eye(2))
    with pytest.raises(ValidationError, match="length"):
        core.portfolio_vol([1.0], np.eye(2))


# ------------------------------------------------------ risk contributions ----
@pytest.mark.parametrize("seed", range(6))
def test_rc_sum_to_sigma_p(make_cov, seed):
    rng = np.random.default_rng(seed)
    n = 3 + seed * 3
    S = make_cov(n, seed)
    w = rng.normal(0.3, 0.5, n)  # long/short, geared, unnormalised
    sp = core.portfolio_vol(w, S)
    assert core.risk_contributions(w, S).sum() == pytest.approx(sp, rel=1e-12)
    assert core.percent_risk_contributions(w, S).sum() == pytest.approx(1.0, abs=1e-12)
    # Euler: marginal risk is the gradient of sigma_p
    g = core.marginal_risk(w, S)
    eps = 1e-7
    num = np.array([(core.portfolio_vol(w + eps * e, S) - core.portfolio_vol(w - eps * e, S)) / (2 * eps)
                    for e in np.eye(n)])
    np.testing.assert_allclose(g, num, rtol=1e-6, atol=1e-9)


# ------------------------------------------------------- effective bets ----
@pytest.mark.parametrize("n", [2, 5, 15])
def test_every_neff_is_n_for_uncorrelated_equal_risk(n):
    vols = np.linspace(0.05, 0.40, n)
    S = np.diag(vols ** 2)
    w = (1 / vols) / (1 / vols).sum()  # equal risk
    eb = core.effective_bets(w, S)
    for m in ("equal_rho", "prc_inverse_hhi", "pca_entropy", "min_torsion", "dr2"):
        assert getattr(eb, m) == pytest.approx(n, rel=1e-9), m
    assert not eb.prc_has_negative and not eb.pca_basis_ambiguous and not eb.min_torsion_regularized


@pytest.mark.parametrize("n", [3, 8])
def test_neff_perfectly_correlated(n):
    """Correlation-aware measures (a), (c), (e) collapse to 1.  The risk-
    balance measures (b), (d) do NOT: they measure balance of risk
    contributions, so with perfect correlation (b) is the inverse HHI of the
    dollar-vol shares w_i sigma_i / w'sigma and (d) is N for an equal-risk book.
    (The contract's 'every N_eff = 1' is false for (b)/(d); this pins the truth.)"""
    rng = np.random.default_rng(n)
    vols = rng.uniform(0.1, 0.3, n)
    S = np.outer(vols, vols)
    w = rng.uniform(0.2, 1.0, n)
    w /= w.sum()
    eb = core.effective_bets(w, S)
    assert eb.equal_rho == pytest.approx(1.0, abs=1e-9)
    assert eb.pca_entropy == pytest.approx(1.0, abs=1e-9)
    assert eb.dr2 == pytest.approx(1.0, abs=1e-9)
    s = w * vols / (w @ vols)
    assert eb.prc_inverse_hhi == pytest.approx(1 / np.sum(s ** 2), rel=1e-9)
    assert eb.min_torsion_regularized
    # equal-risk version: (d) = N
    we = (1 / vols) / (1 / vols).sum()
    assert core.effective_bets(we, S).min_torsion == pytest.approx(n, rel=1e-6)
    assert core.effective_bets(we, S).prc_inverse_hhi == pytest.approx(n, rel=1e-9)


@pytest.mark.parametrize("n", [2, 5, 15, 30])
@pytest.mark.parametrize("rho", [0.0, 0.1, 0.3, 0.6, 0.95])
def test_dr2_equals_closed_form_equal_vol_equal_rho(n, rho):
    S = core.equal_corr_cov(n, 0.2, rho)
    w = np.full(n, 1 / n)
    closed = n / (1 + (n - 1) * rho)
    assert core.diversification_ratio(w, S) ** 2 == pytest.approx(closed, rel=1e-12)
    assert core.diversification_ratio(w, S) == pytest.approx(core.diversification_improvement(n, rho), rel=1e-12)
    eb = core.effective_bets(w, S)
    assert eb.dr2 == pytest.approx(closed, rel=1e-12)
    assert eb.equal_rho == pytest.approx(closed, rel=1e-12)
    assert eb.implied_avg_corr == pytest.approx(rho, abs=1e-12)
    # risk-balance measures are N at any rho for this symmetric book
    assert eb.prc_inverse_hhi == pytest.approx(n, rel=1e-9)
    assert eb.min_torsion == pytest.approx(n, rel=1e-6)


def test_pca_entropy_discontinuity_is_flagged():
    S = core.equal_corr_cov(6, 0.2, 0.3)
    v, amb = core.neff_pca_entropy(np.full(6, 1 / 6), S)
    assert v == pytest.approx(1.0, abs=1e-9) and amb


def test_negative_prc_flag(make_cov):
    S = core.equal_corr_cov(3, 0.2, 0.8)
    w = np.array([1.0, 0.5, -0.4])
    _, neg = core.neff_from_prc(w, S)
    assert neg


def test_implied_average_correlation_general(make_cov):
    S = make_cov(6, 3)
    w = np.random.default_rng(3).uniform(0.1, 1, 6)
    rho = core.implied_average_correlation(w, S)
    sig = np.sqrt(np.diag(S))
    C = np.full((6, 6), rho)
    np.fill_diagonal(C, 1)
    assert core.portfolio_vol(w, C * np.outer(sig, sig)) == pytest.approx(core.portfolio_vol(w, S), rel=1e-10)


def test_zero_variance_streams_dropped_from_neff():
    S = np.diag([0.04, 0.09, 0.0])
    w = np.array([0.3, 0.2, 0.5])
    eb = core.effective_bets(w, S)
    assert eb.dropped_zero_variance == [2] and eb.n == 2


# ------------------------------------------------------ minimum torsion ----
@pytest.mark.parametrize("vols", [[0.1, 0.2, 0.3], [0.05] * 4, list(np.linspace(0.01, 1, 9))])
def test_min_torsion_identity_for_diagonal(vols):
    S = np.diag(np.asarray(vols) ** 2)
    tr = core.minimum_torsion(S)
    assert tr.converged and not tr.regularized
    np.testing.assert_allclose(tr.t, np.eye(len(vols)), atol=1e-12)
    w = np.random.default_rng(0).uniform(0.1, 1, len(vols))
    prc = core.percent_risk_contributions(w, S)
    v, _ = core.neff_minimum_torsion(w, S)
    assert v == pytest.approx(math.exp(-np.sum(prc * np.log(prc))), rel=1e-12)


@pytest.mark.parametrize("seed", range(5))
def test_min_torsion_properties(make_cov, seed):
    n = 4 + seed
    S = make_cov(n, seed)
    tr = core.minimum_torsion(S)
    assert tr.converged
    M = tr.t @ S @ tr.t.T
    assert np.max(np.abs(M - np.diag(np.diag(M)))) < 1e-12 * np.max(np.abs(M))  # uncorrelated
    w = np.random.default_rng(seed).uniform(0.05, 1, n)
    p = core.minimum_torsion_distribution(w, S, tr)
    p_direct = np.linalg.solve(tr.t.T, w) * (tr.t @ S @ w) / (w @ S @ w)  # published formula
    np.testing.assert_allclose(p, p_direct, atol=1e-12)
    assert p.min() >= 0 and p.sum() == pytest.approx(1.0)
    # beats the Riccati (Mahalanobis) root, which is the D = I, q = I uncorrelated set
    assert tr.objective <= np.linalg.norm(np.eye(n) - tr.c, "fro") + 1e-12


def test_min_torsion_is_global_optimum_3x3(make_cov):
    """Brute force: min over rotations q (Euler angles) with optimal D of ||Dq - c||."""
    S = make_cov(3, 11)
    tr = core.minimum_torsion(S)
    c = tr.c

    def rot(a):
        cx, sx, cy, sy, cz, sz = np.cos(a[0]), np.sin(a[0]), np.cos(a[1]), np.sin(a[1]), np.cos(a[2]), np.sin(a[2])
        Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        return Rz @ Ry @ Rx

    def f(a):
        q = rot(a)
        d = np.einsum("ij,ji->i", q, c)
        return np.linalg.norm(d[:, None] * q - c, "fro")

    rng = np.random.default_rng(0)
    best = min(minimize(f, rng.uniform(-np.pi, np.pi, 3), method="Nelder-Mead",
                        options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 5000}).fun for _ in range(40))
    assert tr.objective <= best + 1e-8


# ---------------------------------------------------- Sharpe and gearing ----
@pytest.mark.parametrize("seed", range(4))
def test_sharpe_equals_s_times_dr(make_cov, seed):
    n = 6
    S = make_cov(n, seed)
    rng = np.random.default_rng(seed)
    w = rng.uniform(0.05, 1, n)
    w /= w.sum()
    s, rf = 0.35, 0.03
    mu = rf + s * np.sqrt(np.diag(S))
    assert core.portfolio_sharpe(w, mu, S, rf) == pytest.approx(s * core.diversification_ratio(w, S), rel=1e-12)
    assert core.equal_sharpe_identity(s, w, S) == pytest.approx(core.portfolio_sharpe(w, mu, S, rf), rel=1e-12)


@pytest.mark.parametrize("target", [0.05, 0.10, 0.25])
def test_gearing_hits_target_vol(make_cov, target):
    S = make_cov(5, 2)
    w = np.full(5, 0.2)
    g = target_vol_gearing(w, S, target)
    assert core.portfolio_vol(g.weights, S) == pytest.approx(target, rel=1e-12)
    assert g.leverage == pytest.approx(target / core.portfolio_vol(w, S))
    assert g.cash_weight == pytest.approx(1 - g.leverage)
    capped = target_vol_gearing(w, S, 10.0, max_leverage=2.0)
    assert capped.cap_binding and capped.leverage == pytest.approx(2.0)
    assert core.leverage_for_target(0.05, 0.10) == pytest.approx(2.0)
    assert core.leverage_for_target(0.05, 0.10, max_leverage=1.5) == pytest.approx(1.5)


def test_financing_only_on_borrowed_part():
    mu, rf = 0.07, 0.04
    for spread in (0.0, 0.01, 0.05):
        # unlevered / cash-holding: spread irrelevant
        assert core.geared_return(mu, rf, 0.5, spread) == pytest.approx(rf + 0.5 * (mu - rf))
        assert core.geared_return(mu, rf, 1.0, spread) == pytest.approx(mu)
        # levered: spread on (L - 1) only
        assert core.geared_return(mu, rf, 2.5, spread) == pytest.approx(rf + 2.5 * (mu - rf) - 1.5 * spread)
    assert core.log_growth(mu, 0.1, rf, 2.0, 0.01) == pytest.approx(rf + 2 * 0.03 - 0.01 - 0.5 * 4 * 0.01)


@pytest.mark.parametrize("mu,sig,spread", [(0.08, 0.10, 0.0), (0.08, 0.10, 0.01), (0.06, 0.15, 0.0),
                                           (0.055, 0.10, 0.02), (0.03, 0.10, 0.0)])
def test_kelly_maximises_log_growth(mu, sig, spread):
    rf = 0.04
    Ls = np.linspace(0, 8, 160001)
    g = [core.log_growth(mu, sig, rf, L, spread) for L in Ls]
    assert core.kelly_leverage(mu, sig, rf, spread) == pytest.approx(Ls[int(np.argmax(g))], abs=1e-4)


def test_prob_loss():
    assert core.prob_loss(0.06, 0.18) == pytest.approx(norm.cdf(-1 / 3))
    assert core.prob_loss(0.06, 0.18, model="lognormal") == pytest.approx(norm.cdf(-(0.06 - 0.0162) / 0.18))
    assert core.prob_loss(0.06, 0.18, years=4) == pytest.approx(norm.cdf(-0.06 * 2 / 0.18))
    rng = np.random.default_rng(0)
    sim = rng.normal(0.06, 0.18, 400_000)
    assert np.mean(sim < 0) == pytest.approx(core.prob_loss(0.06, 0.18), abs=0.003)


def test_estimation_error_helpers():
    assert core.sharpe_se(0.5, 20) == pytest.approx(math.sqrt((1 + 0.125) / 20))
    # annualised form equals per-period Lo SE scaled by sqrt(q)
    q, yrs, sa = 52, 10, 0.8
    sp = sa / math.sqrt(q)
    assert core.sharpe_se_annualized(sa, yrs, q) == pytest.approx(math.sqrt(q) * core.sharpe_se(sp, q * yrs))
    assert core.corr_se(0.5, 100) == pytest.approx(0.075)
    lo, hi = core.corr_ci(0.5, 100)
    assert lo < 0.5 < hi
