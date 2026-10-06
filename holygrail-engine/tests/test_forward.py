"""GATES: MC moments converge; block bootstrap preserves marginals.  Plus
stress, scenario replay, horizon statistics and determinism."""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import chisquare, ks_2samp

from holygrail import forward as F
from holygrail.errors import ValidationError

MU = np.array([0.06, 0.03, 0.08])
COV = np.array([[0.0324, 0.0036, 0.0108], [0.0036, 0.0064, -0.0012], [0.0108, -0.0012, 0.0400]])


@pytest.mark.parametrize("method", ["mvn", "t"])
def test_mc_moments_converge(method):
    q = 12
    sim = F.simulate_returns(MU, COV, 120, 4000, periods_per_year=q, method=method, df=6, seed=1)
    X = sim.reshape(-1, 3)
    n = X.shape[0]
    se_mean = np.sqrt(np.diag(COV) / q / n)
    assert np.all(np.abs(X.mean(0) - MU / q) < 5 * se_mean)
    np.testing.assert_allclose(np.cov(X.T), COV / q, rtol=0.03, atol=2e-5)
    # Student-t has fatter tails than normal
    k = ((X[:, 0] - X[:, 0].mean()) ** 4).mean() / X[:, 0].var() ** 2
    assert (k > 3.5) if method == "t" else (abs(k - 3) < 0.1)


def test_mc_deterministic_seeds():
    a = F.simulate_returns(MU, COV, 10, 50, periods_per_year=12, seed=5)
    b = F.simulate_returns(MU, COV, 10, 50, periods_per_year=12, seed=5)
    c = F.simulate_returns(MU, COV, 10, 50, periods_per_year=12, seed=6)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    cfg = F.SimConfig(years=2, n_paths=3000, seed=4)
    r1 = F.run_forward(np.array([0.4, 0.4, 0.2]), cfg, mu=MU, cov=COV, chunk=700)
    r2 = F.run_forward(np.array([0.4, 0.4, 0.2]), cfg, mu=MU, cov=COV, chunk=700)
    assert r1.stats["cagr_quantiles"] == r2.stats["cagr_quantiles"]


def test_jumps_preserve_mean_and_fire_at_rate():
    jv = 0.05 * 0.95 * 0.25
    jumps = [{"base_index": 1, "prob": 0.05, "loss": 0.5, "jump_variance": jv}]
    cov = np.diag([0.0324, 0.0004, 0.04])
    sim = F.simulate_returns(MU, cov, 120, 5000, periods_per_year=12, seed=2, jumps=jumps)
    x = sim[:, :, 1].ravel()
    assert x.mean() == pytest.approx(MU[1] / 12, abs=4 * np.sqrt((0.0004 / 12 + 0.25 * 0.05 / 12) / x.size))
    # annual two-point model: P(default in a year) = p, at most once, so the
    # per-period hit rate is p/q and the annual jump variance is p(1-p)L^2
    assert np.mean(x < -0.3) == pytest.approx(0.05 / 12, rel=0.05)
    yearly = sim[:, :, 1].reshape(5000, 10, 12)
    assert (yearly < -0.3).sum(axis=2).max() <= 1
    annual = yearly.sum(axis=2).ravel()
    assert annual.var() == pytest.approx(0.0004 + jv, rel=0.05)  # diffusive + jump = declared variance


def test_block_bootstrap_preserves_marginals():
    rng = np.random.default_rng(0)
    T = 500
    H = np.column_stack([rng.standard_t(4, T) * 0.02, rng.normal(0, 0.01, T), rng.exponential(0.01, T) - 0.01])
    sim = F.bootstrap_returns(H, 240, 400, mean_block=12, seed=3)
    rows = {tuple(r) for r in H}
    assert all(tuple(r) in rows for r in sim.reshape(-1, 3)[:5000])  # every row is a real joint row
    for j in range(3):
        assert ks_2samp(sim[:, :, j].ravel(), H[:, j]).statistic < 0.02
    ix = F.stationary_bootstrap_indices(T, 240, 400, 12, np.random.default_rng(3))
    counts = np.bincount(ix.ravel(), minlength=T)
    assert chisquare(counts).pvalue > 1e-4  # uniform marginal over historical rows
    starts = np.mean(np.diff(ix, axis=1) % T != 1)
    assert starts == pytest.approx(1 / 12, rel=0.05)  # geometric blocks, mean 12
    with pytest.raises(ValidationError):
        F.bootstrap_returns(np.array([[np.nan]] * 5), 10, 2, mean_block=2)


def test_portfolio_returns_cash_and_borrowing():
    r = np.full((1, 1, 2), 0.01)
    assert F.portfolio_returns(r, [0.3, 0.2], rf_period=0.001, spread_period=0.002)[0, 0] == pytest.approx(
        0.005 + 0.5 * 0.001)
    assert F.portfolio_returns(r, [0.9, 0.6], rf_period=0.001, spread_period=0.002)[0, 0] == pytest.approx(
        0.015 - 0.5 * (0.001 + 0.002))
    # look-through: leaf leverage inside const, book cash leg explicit -> no double-counted spread
    assert F.portfolio_returns(r, [1.5, 1.5], rf_period=0.001, spread_period=0.002, const_period=-0.0005,
                               cash_weight=0.0)[0, 0] == pytest.approx(0.03 - 0.0005)


def test_horizon_stats_hand_values():
    port = np.full((4, 24), 0.01)
    port[0, :] = -0.01
    s = F.horizon_stats(port, 12)
    assert s["p_loss_horizon"] == pytest.approx(0.25)
    assert s["cagr_quantiles"]["0.5"] == pytest.approx(1.01 ** 12 - 1)
    assert s["p_losing_year"] == pytest.approx(0.25) and s["p_any_losing_year"] == pytest.approx(0.25)
    # path max DDs are [0.99^24 - 1, 0, 0, 0]: the 5% quantile interpolates between them
    assert s["max_dd_quantiles"]["0.05"] == pytest.approx(np.quantile([0.99 ** 24 - 1, 0, 0, 0], 0.05), rel=1e-12)
    rng = np.random.default_rng(0)
    p = rng.normal(0.005, 0.04, (2000, 120))
    st = F.horizon_stats(p, 12)
    W = np.prod(1 + p, axis=1)
    cagr = np.sort(W ** (1 / 10) - 1)
    assert st["cvar_0.05_cagr"] == pytest.approx(cagr[:100].mean())
    wipe = np.zeros((2, 12)); wipe[0, 3] = -1.2
    assert F.horizon_stats(wipe, 12)["p_wipeout"] == pytest.approx(0.5)


def test_run_forward_gearing_and_bootstrap():
    w = np.array([0.3, 0.5, 0.2])
    base = F.run_forward(w, F.SimConfig(years=5, n_paths=4000, seed=1), mu=MU, cov=COV, rf=0.03, spread=0.01)
    geared = F.run_forward(2 * w, F.SimConfig(years=5, n_paths=4000, seed=1), mu=MU, cov=COV, rf=0.03, spread=0.01)
    assert geared.stats["cagr_quantiles"]["0.95"] > base.stats["cagr_quantiles"]["0.95"]
    assert geared.stats["cagr_quantiles"]["0.05"] < base.stats["cagr_quantiles"]["0.05"]
    hist = pd.DataFrame(np.random.default_rng(0).normal(0.005, 0.03, (240, 3)))
    bs = F.run_forward(w, F.SimConfig(years=5, n_paths=500, method="bootstrap", seed=2), history=hist)
    assert "bootstrap replays history" in " ".join(bs.notes)
    with pytest.raises(ValidationError):
        F.run_forward(w, F.SimConfig(method="t", df=2))


def test_correlation_stress():
    S = F.stress_correlation(COV, method="uniform", rho=0.7)
    sig = np.sqrt(np.diag(COV))
    np.testing.assert_allclose(np.sqrt(np.diag(S)), sig)
    assert S[0, 1] / (sig[0] * sig[1]) == pytest.approx(0.7)
    crisis = np.full((3, 3), 0.9); np.fill_diagonal(crisis, 1)
    Sb = F.stress_correlation(COV, method="blend", crisis_corr=crisis, alpha=0.5, vol_multiplier=1.5)
    C0 = COV[0, 2] / (sig[0] * sig[2])
    assert Sb[0, 2] / (1.5 * sig[0] * 1.5 * sig[2]) == pytest.approx(0.5 * C0 + 0.45)
    assert np.linalg.eigvalsh(Sb)[0] >= 0
    with pytest.raises(ValidationError):
        F.stress_correlation(COV, method="uniform", rho=-0.9)


def test_replay_scenario_hand_and_missing():
    idx = pd.bdate_range("2020-02-17", periods=6)
    R = pd.DataFrame({"A": [0.0, -0.1, 0.05, -0.02, 0.0, 0.01], "B": [0.0, 0.02, 0.0, 0.01, -0.01, 0.0]}, index=idx)
    out = F.replay_scenario(R, {"A": 0.5, "B": 0.3}, "2020-02-17", "2020-02-21", label="t")
    gA = 0.9 * 1.05 * 0.98 * 1.0
    gB = 1.02 * 1.0 * 1.01 * 0.99
    assert out["cum_return"] == pytest.approx(0.5 * gA + 0.3 * gB + 0.2 - 1)  # buy and hold, cash 0
    assert out["contributions"]["A"] == pytest.approx(0.5 * (gA - 1))
    daily = F.replay_scenario(R, {"A": 0.5, "B": 0.5}, "2020-02-17", "2020-02-21", rebalance="daily")
    assert daily["cum_return"] == pytest.approx(np.prod(1 + 0.5 * R["A"].iloc[1:5] + 0.5 * R["B"].iloc[1:5]) - 1)
    R2 = R.copy(); R2.iloc[2, 1] = np.nan
    with pytest.raises(ValidationError, match="missing"):
        F.replay_scenario(R2, {"A": 0.5, "B": 0.5}, "2020-02-17", "2020-02-21")
    ok = F.replay_scenario(R2, {"A": 0.5, "B": 0.5}, "2020-02-17", "2020-02-21", missing="cash")
    assert ok["notes"]
    assert set(F.SCENARIOS) == {"gfc", "covid", "inflation_2022"}
