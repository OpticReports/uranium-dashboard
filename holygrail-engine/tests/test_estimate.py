"""GATE: PSD repair -> PSD with unit diagonal.  Plus estimator correctness
(Ledoit-Wolf vs brute-force formulas), calendar alignment, de-smoothing."""
import numpy as np
import pandas as pd
import pytest

from holygrail import estimate as E
from holygrail.errors import CovarianceError, ValidationError


# ------------------------------------------------------------- PSD repair ----
@pytest.mark.parametrize("seed", range(8))
def test_nearest_correlation_is_psd_unit_diagonal(seed):
    rng = np.random.default_rng(seed)
    n = 3 + seed
    A = rng.uniform(-1, 1, (n, n))
    A = (A + A.T) / 2
    np.fill_diagonal(A, 1.0)
    C = E.nearest_correlation(A)
    assert np.all(np.diag(C) == 1.0)
    assert np.array_equal(C, C.T)
    assert np.linalg.eigvalsh(C)[0] >= -1e-12
    # it is (near-)optimal: no random valid correlation matrix is closer
    d = np.linalg.norm(C - A)
    for k in range(50):
        B = rng.normal(size=(n, n + 2))
        Z = B @ B.T
        dz = np.sqrt(np.diag(Z))
        Z = Z / np.outer(dz, dz)
        assert d <= np.linalg.norm(Z - A) + 1e-9


def test_nearest_correlation_higham_example():
    """Higham (2002) 3x3 example A = [[1,1,0],[1,1,1],[0,1,1]]."""
    A = np.array([[1, 1, 0], [1, 1, 1], [0, 1, 1]], float)
    C = E.nearest_correlation(A, tol=1e-13)
    assert C[0, 1] == pytest.approx(0.7607, abs=1e-4)
    assert C[0, 2] == pytest.approx(0.1573, abs=1e-4)
    assert C[1, 2] == pytest.approx(0.7607, abs=1e-4)


def test_nearest_correlation_leaves_valid_matrix_alone():
    C0 = np.array([[1, 0.3, 0.2], [0.3, 1, -0.1], [0.2, -0.1, 1]])
    np.testing.assert_allclose(E.nearest_correlation(C0), C0, atol=1e-12)


def test_repair_covariance_keeps_variances():
    S = np.array([[0.04, 0.05, 0.0], [0.05, 0.04, 0.03], [0.0, 0.03, 0.09]])
    assert np.linalg.eigvalsh(S)[0] < 0
    S2, rep = E.repair_covariance(S)
    assert rep.repaired and rep.min_eig_after >= -1e-14
    np.testing.assert_allclose(np.diag(S2), np.diag(S), rtol=1e-12)
    with pytest.raises(CovarianceError):
        E.nearest_correlation(np.array([[1, np.nan], [np.nan, 1]]))


def test_pairwise_unequal_history_is_repaired():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=400, freq="B")
    X = rng.normal(size=(400, 4)) @ np.array([[1, .9, .8, 0], [0, .4, .1, .5], [0, 0, .5, .3], [0, 0, 0, .7]])
    df = pd.DataFrame(X, index=idx, columns=list("abcd"))
    df.iloc[:250, 2] = np.nan
    df.iloc[300:, 3] = np.nan
    est = E.estimate_cov(df, "sample", history="pairwise", periods_per_year=252)
    assert np.linalg.eigvalsh(est.cov)[0] >= -1e-12
    with pytest.raises(ValidationError, match="pairwise"):
        E.estimate_cov(df, "lw", history="pairwise", periods_per_year=252)
    with pytest.raises(ValidationError, match="common window"):
        df2 = df.copy(); df2.iloc[:, 3] = np.nan; df2.iloc[0, 3] = 1.0
        E.estimate_cov(df2, "sample", periods_per_year=252)


# -------------------------------------------------------------- shrinkage ----
def _lw_identity_brute(X):
    T, N = X.shape
    x = X - X.mean(0)
    S = x.T @ x / T
    m = np.trace(S) / N
    d2 = np.linalg.norm(S - m * np.eye(N)) ** 2 / N
    b2 = sum(np.linalg.norm(np.outer(x[t], x[t]) - S) ** 2 for t in range(T)) / T ** 2 / N
    delta = min(b2, d2) / d2
    return delta * m * np.eye(N) + (1 - delta) * S, delta


def _lw_cc_brute(X):
    T, N = X.shape
    x = X - X.mean(0)
    S = x.T @ x / T
    sd = np.sqrt(np.diag(S))
    R = S / np.outer(sd, sd)
    rbar = sum(R[i, j] for i in range(N) for j in range(N) if i != j) / (N * (N - 1))
    F = rbar * np.outer(sd, sd)
    np.fill_diagonal(F, np.diag(S))
    pi = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            pi[i, j] = np.mean((x[:, i] * x[:, j] - S[i, j]) ** 2)
    rho = np.trace(pi)
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            th_ii = np.mean((x[:, i] ** 2 - S[i, i]) * (x[:, i] * x[:, j] - S[i, j]))
            th_jj = np.mean((x[:, j] ** 2 - S[j, j]) * (x[:, i] * x[:, j] - S[i, j]))
            rho += rbar / 2 * (np.sqrt(S[j, j] / S[i, i]) * th_ii + np.sqrt(S[i, i] / S[j, j]) * th_jj)
    gamma = np.linalg.norm(F - S) ** 2
    delta = max(0, min(1, (pi.sum() - rho) / gamma / T))
    return delta * F + (1 - delta) * S, delta


@pytest.mark.parametrize("seed,T", [(0, 40), (1, 120), (2, 25)])
def test_ledoit_wolf_matches_brute_force(seed, T):
    rng = np.random.default_rng(seed)
    X = rng.standard_t(5, size=(T, 5)) @ rng.normal(size=(5, 5)) * 0.01
    S1, d1 = E.ledoit_wolf_identity(X)
    S2, d2 = _lw_identity_brute(X)
    np.testing.assert_allclose(S1, S2, rtol=1e-10, atol=1e-14)
    assert d1 == pytest.approx(d2)
    C1, e1 = E.ledoit_wolf_constant_corr(X)
    C2, e2 = _lw_cc_brute(X)
    np.testing.assert_allclose(C1, C2, rtol=1e-10, atol=1e-14)
    assert e1 == pytest.approx(e2)
    assert 0 <= d1 <= 1 and 0 <= e1 <= 1
    np.testing.assert_allclose(np.diag(C1), np.diag(X.T @ (X - X.mean(0)) / T), rtol=1e-10)


def test_shrinkage_vanishes_with_lots_of_data():
    rng = np.random.default_rng(3)
    L = np.array([[1, 0, 0], [0.6, 0.8, 0], [0.2, 0.3, 0.9]])
    X = rng.normal(size=(50_000, 3)) @ L.T
    assert E.ledoit_wolf_constant_corr(X)[1] < 0.01
    assert E.ledoit_wolf_identity(X)[1] < 0.01


def test_ewma_weights():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 3))
    # huge halflife -> equal weights -> biased (1/T) demeaned sample covariance
    S = E.ewma_cov(X, 1e9, demean=True)
    np.testing.assert_allclose(S, np.cov(X.T, ddof=0), rtol=1e-6)
    # halflife h: the observation h periods back carries half the weight of the latest
    Z = np.zeros((11, 1)); Z[-1] = 1.0
    Z2 = np.zeros((11, 1)); Z2[-6] = 1.0
    assert E.ewma_cov(Z2, 5)[0, 0] / E.ewma_cov(Z, 5)[0, 0] == pytest.approx(0.5)


def test_estimate_cov_dispatch_and_annualise():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(rng.normal(0, 0.01, (500, 3)), index=pd.date_range("2020", periods=500, freq="B"))
    for m in ("sample", "lw", "lw_cc"):
        est = E.estimate_cov(df, m, freq="D")
        assert est.annual == pytest.approx(est.cov * 252)
    assert E.estimate_cov(df, "ewma", freq="D", halflife=60).n_obs == 500
    assert E.estimate_cov(df, "lagged", freq="D", lags=3).cov.shape == (3, 3)
    with pytest.raises(ValidationError):
        E.estimate_cov(df, "nope", freq="D")
    with pytest.raises(ValidationError):
        E.estimate_cov(df, "sample")


# -------------------------------------------------------------- calendars ----
def _mixed_levels():
    days = pd.date_range("2024-01-01", "2024-03-31", freq="D")
    rng = np.random.default_rng(0)
    cry = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.03, len(days))), index=days)
    b = days[days.dayofweek < 5]
    eq = pd.Series(50 * np.cumprod(1 + rng.normal(0, 0.01, len(b))), index=b)
    eq = eq.drop(pd.Timestamp("2024-01-15"))  # an equity holiday
    late = eq.loc["2024-02-01":] * 2
    return pd.DataFrame({"CRY": cry, "EQ": eq, "LATE": late}), cry, eq


def test_crypto_vs_equity_calendar_compounds_weekends():
    lv, cry, eq = _mixed_levels()
    cal = E.active_intersection_calendar(lv)
    assert all(d.dayofweek < 5 for d in cal)
    assert pd.Timestamp("2024-01-15") not in cal
    r = E.aligned_returns(lv, "D")
    mon = pd.Timestamp("2024-01-08")
    assert r.loc[mon, "CRY"] == pytest.approx(cry[mon] / cry[pd.Timestamp("2024-01-05")] - 1)
    assert r.loc[pd.Timestamp("2024-01-16"), "CRY"] == pytest.approx(cry["2024-01-16"] / cry["2024-01-12"] - 1)
    # unequal history: LATE is NaN before it starts and does not veto earlier dates
    assert r.loc[:"2024-01-31", "LATE"].isna().all()
    assert r.loc["2024-02-02":, "LATE"].notna().all()


def test_trailing_crypto_weekend_is_truncated():
    lv, cry, eq = _mixed_levels()  # crypto runs to Sun 2024-03-31, equities to Fri 03-29
    cal = E.active_intersection_calendar(lv)
    assert cal[-1] == pd.Timestamp("2024-03-29")
    r = E.aligned_returns(lv, "D")
    assert r.iloc[-1].notna().all()


def test_weekly_and_monthly_returns_compound_daily():
    lv, cry, eq = _mixed_levels()
    w = E.aligned_returns(lv, "W")
    d = E.aligned_returns(lv[["CRY"]], "D")
    wk = w.index[3]
    prev = w.index[2]
    exp = cry.loc[:wk].iloc[-1] / cry.loc[:prev].iloc[-1] - 1
    assert w.loc[wk, "CRY"] == pytest.approx(exp)
    # labels are actual last observation dates, never future period ends
    assert w.index[-1] <= lv.index[-1]
    m = E.aligned_returns(lv, "M")
    assert m.loc[m.index[0], "EQ"] == pytest.approx(eq.loc[:"2024-02-29"].iloc[-1] / eq.loc[:"2024-01-31"].iloc[-1] - 1)
    assert d.shape[0] > w.shape[0]


def test_union_and_explicit_calendar():
    lv, cry, eq = _mixed_levels()
    u = E.align_levels(lv, "D", "union")
    assert u.loc[pd.Timestamp("2024-01-06"), "EQ"] == eq.loc["2024-01-05"]  # forward-filled weekend
    cal = pd.date_range("2024-01-02", "2024-01-31", freq="W-WED")
    x = E.align_levels(lv, "D", cal)
    assert list(x.index) == list(cal)
    with pytest.raises(ValidationError):
        E.align_levels(lv, "D", "bogus")


def test_levels_validation():
    df = pd.DataFrame({"a": [1.0, -1.0, 2.0]}, index=pd.date_range("2020", periods=3))
    with pytest.raises(ValidationError, match="> 0"):
        E.aligned_returns(df)
    assert E.infer_periods_per_year(pd.date_range("2020", periods=366, freq="D")) == pytest.approx(365 / (365 / 365.25), rel=1e-3)


# ------------------------------------------------------------ stale marks ----
def test_geltner_inverts_smoothing():
    rng = np.random.default_rng(0)
    true = pd.Series(rng.normal(0.02, 0.05, 200), index=pd.date_range("2000", periods=200, freq="QE"))
    phi = 0.6
    obs = true.copy()
    for t in range(1, len(true)):
        obs.iloc[t] = (1 - phi) * true.iloc[t] + phi * obs.iloc[t - 1]
    rec, ph = E.geltner_desmooth(obs, phi)
    np.testing.assert_allclose(rec.to_numpy(), true.iloc[1:].to_numpy(), atol=1e-12)
    rec2, ph2 = E.geltner_desmooth(obs)  # estimated phi
    assert 0.4 < ph2 < 0.8 and rec2.std() > obs.std()
    with pytest.raises(ValidationError):
        E.geltner_desmooth(obs, 0.995)


def test_dimson_beta_corrects_stale_bias():
    rng = np.random.default_rng(1)
    n = 5000
    m = pd.Series(rng.normal(0, 0.01, n), index=pd.date_range("2000", periods=n, freq="B"))
    beta = 1.2
    a = beta * (0.5 * m + 0.5 * m.shift(1)).fillna(0) + rng.normal(0, 0.004, n)
    res = E.dimson_beta(a, m, lags=2)
    assert res.ols_beta == pytest.approx(0.6, abs=0.05)
    assert res.beta == pytest.approx(beta, abs=0.05)


def test_lagged_cov_recovers_stale_correlation():
    rng = np.random.default_rng(2)
    n = 20_000
    f = rng.normal(0, 0.01, n)
    a = f + rng.normal(0, 0.002, n)
    b = np.r_[0.0, f[:-1]] + rng.normal(0, 0.002, n)  # b reflects f one period late
    X = np.column_stack([a, b])
    S0 = E.sample_cov(X)
    S1 = E.lagged_cov(X, 2, "bartlett")
    S2 = E.lagged_cov(X, 1, "flat")
    corr = lambda S: S[0, 1] / np.sqrt(S[0, 0] * S[1, 1])  # noqa: E731
    assert abs(corr(S0)) < 0.05
    assert corr(S2) > 0.9 and corr(S1) > corr(S0)
    assert np.linalg.eigvalsh(S1)[0] >= 0
