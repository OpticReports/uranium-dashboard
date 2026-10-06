"""GATES: ERC equalises RCs on random PSD matrices to 1e-8 and equals inverse
vol for diagonal S.  Plus every allocator against closed forms / brute force."""
import numpy as np
import pytest
from scipy.optimize import minimize

from holygrail import allocate as A
from holygrail import core
from holygrail.errors import OptimizationError, ValidationError


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("method", ["newton", "ccd"])
def test_erc_equalises_risk_contributions(make_cov, seed, method):
    n = 3 + 2 * seed
    S = make_cov(n, seed)
    w = A.erc(S, method=method)
    prc = core.percent_risk_contributions(w, S)
    assert np.max(np.abs(prc - 1.0 / n)) < 1e-8
    rc = core.risk_contributions(w, S)
    assert np.max(rc) - np.min(rc) < 1e-8 * core.portfolio_vol(w, S)
    assert w.min() > 0 and w.sum() == pytest.approx(1.0)


def test_erc_highly_correlated(make_cov):
    S = core.equal_corr_cov(12, 0.2, 0.97) * np.outer(np.linspace(1, 3, 12), np.linspace(1, 3, 12))
    w = A.erc(S)
    assert np.max(np.abs(core.percent_risk_contributions(w, S) - 1 / 12)) < 1e-8


@pytest.mark.parametrize("vols", [[0.1, 0.2, 0.4], list(np.linspace(0.02, 0.9, 11))])
def test_erc_equals_inverse_vol_for_diagonal(vols):
    S = np.diag(np.asarray(vols) ** 2)
    np.testing.assert_allclose(A.erc(S), A.inverse_vol(S), atol=1e-12)
    np.testing.assert_allclose(A.erc(S, method="ccd"), A.inverse_vol(S), atol=1e-10)


@pytest.mark.parametrize("seed", range(4))
def test_arbitrary_risk_budgets(make_cov, seed):
    n = 7
    S = make_cov(n, seed + 20)
    b = np.random.default_rng(seed).uniform(0.05, 1, n)
    b /= b.sum()
    w = A.risk_budget_weights(S, b)
    np.testing.assert_allclose(core.percent_risk_contributions(w, S), b, atol=1e-10)
    b0 = b.copy(); b0[2] = 0; b0 /= b0.sum()
    w0 = A.risk_budget_weights(S, b0)
    assert w0[2] == 0
    np.testing.assert_allclose(core.percent_risk_contributions(w0, S), b0, atol=1e-10)
    with pytest.raises(ValidationError):
        A.risk_budget_weights(S, -b)


def _brute(S, objective, n, bounds, cons):
    best = None
    rng = np.random.default_rng(0)
    for _ in range(20):
        x0 = rng.dirichlet(np.ones(n))
        r = minimize(objective, x0, bounds=bounds, constraints=cons, method="SLSQP", options={"ftol": 1e-15, "maxiter": 1000})
        if r.success and (best is None or r.fun < best):
            best = r.fun
    return best


@pytest.mark.parametrize("seed", range(4))
def test_min_variance(make_cov, seed):
    n = 6
    S = make_cov(n, seed)
    w_u = A.min_variance(S, long_only=False)
    x = np.linalg.solve(S, np.ones(n))
    np.testing.assert_allclose(w_u, x / x.sum(), atol=1e-12)
    w = A.min_variance(S)
    assert w.min() >= 0 and w.sum() == pytest.approx(1.0)
    cons = [{"type": "eq", "fun": lambda v: v.sum() - 1}]
    best = _brute(S, lambda v: v @ S @ v, n, [(0, None)] * n, cons)
    assert w @ S @ w <= best + 1e-12
    wc = A.min_variance(S, caps=0.25)
    assert wc.max() <= 0.25 + 1e-10
    best_c = _brute(S, lambda v: v @ S @ v, n, [(0, 0.25)] * n, cons)
    assert wc @ S @ wc <= best_c + 1e-12
    with pytest.raises(ValidationError):
        A.min_variance(S, caps=0.1)  # 6 x 0.1 < 1


@pytest.mark.parametrize("seed", range(4))
def test_max_diversification(make_cov, seed):
    n = 7
    S = make_cov(n, seed + 5)
    sig = np.sqrt(np.diag(S))
    w_u = A.max_diversification(S, long_only=False)
    x = np.linalg.solve(S, sig)
    np.testing.assert_allclose(w_u, x / x.sum(), atol=1e-12)
    w = A.max_diversification(S)
    dr = core.diversification_ratio(w, S)
    rng = np.random.default_rng(seed)
    for _ in range(500):
        v = rng.dirichlet(np.ones(n) * 0.5)
        assert core.diversification_ratio(v, S) <= dr + 1e-10
    wc = A.max_diversification(S, caps=0.2)
    assert wc.max() <= 0.2 + 1e-9 and core.diversification_ratio(wc, S) <= dr + 1e-12


def test_hrp_inverse_variance_for_diagonal_and_valid():
    S = np.diag(np.array([0.1, 0.2, 0.3, 0.15, 0.25]) ** 2)
    np.testing.assert_allclose(A.hrp(S), A.inverse_variance(S), atol=1e-12)
    # two clean blocks: HRP splits risk across the blocks
    B = np.full((4, 4), 0.0)
    B[:2, :2] = 0.9; B[2:, 2:] = 0.9
    np.fill_diagonal(B, 1.0)
    S2 = B * 0.04
    w = A.hrp(S2)
    assert w.sum() == pytest.approx(1.0) and w.min() > 0
    assert w[:2].sum() == pytest.approx(0.5, abs=1e-12)


def test_apply_caps():
    w = np.array([0.6, 0.25, 0.1, 0.05])
    c = A.apply_caps(w, 0.3)
    assert c.max() <= 0.3 + 1e-12 and c.sum() == pytest.approx(1.0)
    # the two names that never bind keep their ratio (pro-rata redistribution)
    assert c[2] / c[3] == pytest.approx(0.1 / 0.05)
    assert c[0] == pytest.approx(0.3) and c[1] == pytest.approx(0.3)
    with pytest.raises(ValidationError):
        A.apply_caps(w, 0.2)


def test_quadrant_balance_equal_box_risk(make_cov):
    S = make_cov(6, 9)
    boxes = ["growth_up", "growth_down", "inflation_up", "inflation_down"]
    M = np.array([[.5, 0, 0, .5],     # equity
                  [0, .5, 0, .5],     # nominal bond
                  [0, .5, .5, 0],     # ILB
                  [0, 0, 1, 0],       # gold
                  [.5, 0, .5, 0],     # commodity
                  [0, 0, 0, 0]])      # unmapped -> zero weight
    r = A.quadrant_balance(S, M, boxes)
    np.testing.assert_allclose(r.box_shares, 0.25, atol=1e-8)
    assert r.weights[5] == 0
    no_infl_down = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, .5, .5, 0], [0, 0, 1, 0], [.5, 0, .5, 0], [0, 0, 0, 0]])
    with pytest.raises(OptimizationError, match="inflation_down"):
        A.quadrant_balance(S, no_infl_down, boxes)


def test_registry():
    assert set(A.ALLOCATORS) >= {"equal_weight", "inverse_vol", "erc", "min_variance", "max_diversification", "hrp"}
    with pytest.raises(ValidationError):
        A.get_allocator("magic")


def test_qp_failure_is_loud():
    # infeasible: sum to 1 with every weight <= 0.1 over 3 assets
    with pytest.raises(OptimizationError):
        A.solve_qp(np.eye(3), np.zeros(3), np.ones((1, 3)), np.array([1.0]), np.eye(3), np.full(3, 0.1))
