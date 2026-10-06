"""GATES: no-lookahead mutation test; toy backtest equity equals hand
computation; financing only on the borrowed part (backtest mechanics)."""
import numpy as np
import pandas as pd
import pytest

from holygrail import metrics as M
from holygrail.backtest import BacktestConfig, run_backtest, schedule_mask
from holygrail.errors import ValidationError


def _toy():
    idx = pd.bdate_range("2024-01-01", periods=6)
    return pd.DataFrame({"A": [0.00, 0.01, -0.02, 0.03, 0.01, -0.01],
                         "B": [0.00, 0.005, 0.01, -0.01, 0.00, 0.02]}, index=idx)


def test_toy_backtest_equals_hand_computation():
    R = _toy()
    rf_p = 0.0001
    cfg = BacktestConfig(allocator=lambda S: np.array([0.6, 0.4]), window=2, rebalance=2, cost_bps=10,
                         periods_per_year=252)
    res = run_backtest(R, cfg, rf=pd.Series(rf_p, index=R.index))
    # hand computation (k0 = 1: first date with 2 returns in the window)
    E1 = 1.0 * (1 - 1.0 * 0.001)                      # buy 60/40 from cash: turnover 1.0
    rp2 = 0.6 * -0.02 + 0.4 * 0.01
    E2 = E1 * (1 + rp2)
    wA, wB = 0.6 * 0.98 / (1 + rp2), 0.4 * 1.01 / (1 + rp2)
    rp3 = wA * 0.03 + wB * -0.01 + (1 - wA - wB) * rf_p
    E3 = E2 * (1 + rp3)
    wA, wB = wA * 1.03 / (1 + rp3), wB * 0.99 / (1 + rp3)
    to3 = abs(0.6 - wA) + abs(0.4 - wB)               # rebalance at k = 3
    E3 *= 1 - to3 * 0.001
    rp4 = 0.6 * 0.01 + 0.4 * 0.0
    E4 = E3 * (1 + rp4)
    wA, wB = 0.6 * 1.01 / (1 + rp4), 0.4 * 1.0 / (1 + rp4)
    rp5 = wA * -0.01 + wB * 0.02
    E5 = E4 * (1 + rp5)
    np.testing.assert_allclose(res.equity.to_numpy(), [E1, E2, E3, E4, E5], rtol=0, atol=1e-15)
    assert list(res.targets.index) == [R.index[1], R.index[3]]
    assert res.turnover.iloc[0] == pytest.approx(1.0) and res.turnover.iloc[2] == pytest.approx(to3)
    assert res.turnover.iloc[[1, 3, 4]].sum() == 0  # no trade on the final date
    assert res.metrics["total_return"] == pytest.approx(E5 - 1)


def test_financing_only_on_borrowed_part_in_backtest():
    R = _toy()
    rf_p, spread = 0.0002, 0.0252
    sp = spread / 252
    lev = run_backtest(R, BacktestConfig(allocator=lambda S: np.array([0.9, 0.6]), window=2, rebalance=100,
                                         max_leverage=2.0, financing_spread=spread),
                       rf=pd.Series(rf_p, index=R.index))
    rp2 = 0.9 * -0.02 + 0.6 * 0.01 + (-0.5) * (rf_p + sp)   # borrowed 0.5 pays rf + spread
    assert lev.equity.iloc[1] / lev.equity.iloc[0] - 1 == pytest.approx(rp2, abs=1e-15)
    cash = run_backtest(R, BacktestConfig(allocator=lambda S: np.array([0.3, 0.2]), window=2, rebalance=100,
                                          financing_spread=spread), rf=pd.Series(rf_p, index=R.index))
    rp2c = 0.3 * -0.02 + 0.2 * 0.01 + 0.5 * rf_p             # cash earns rf, no spread
    assert cash.equity.iloc[1] / cash.equity.iloc[0] - 1 == pytest.approx(rp2c, abs=1e-15)
    assert lev.leverage.iloc[0] == pytest.approx(1.5) and cash.cash_weight.iloc[0] == pytest.approx(0.5)


def _synthetic(n=900, seed=0):
    rng = np.random.default_rng(seed)
    L = np.array([[1, 0, 0, 0], [0.5, 0.8, 0, 0], [-0.2, 0.1, 0.9, 0], [0.3, 0.3, 0.3, 0.8]]) * 0.01
    X = rng.normal(0.0003, 1, (n, 4)) @ L.T
    return pd.DataFrame(X, index=pd.bdate_range("2018-01-01", periods=n), columns=list("WXYZ"))


@pytest.mark.parametrize("estimator", ["sample", "lw_cc", "ewma"])
def test_no_lookahead_mutation(estimator):
    R = _synthetic()
    cfg = BacktestConfig(allocator="erc", window=120, estimator=estimator, halflife=40, rebalance="M",
                         target_vol=0.10, max_leverage=3.0)
    base = run_backtest(R, cfg)
    t = base.targets.index[len(base.targets) // 2]
    R2 = R.copy()
    rng = np.random.default_rng(99)
    R2.loc[R2.index > t] = rng.normal(0, 0.05, R2.loc[R2.index > t].shape)
    mut = run_backtest(R2, cfg)
    a, b = base.targets.loc[:t], mut.targets.loc[:t]
    assert len(a) > 3
    assert np.array_equal(a.to_numpy(), b.to_numpy())  # bit-for-bit
    assert np.array_equal(base.equity.loc[:t].to_numpy(), mut.equity.loc[:t].to_numpy())
    assert not np.allclose(base.targets.loc[base.targets.index > t].to_numpy(),
                           mut.targets.loc[mut.targets.index > t].to_numpy())
    # data AT t is used (estimation on data strictly before t+1)
    R3 = R.copy()
    R3.loc[t] = R3.loc[t] * 25
    assert not np.allclose(run_backtest(R3, cfg).targets.loc[t].to_numpy(), base.targets.loc[t].to_numpy())


def test_vol_targeting_realised():
    R = _synthetic(n=2500, seed=3)
    res = run_backtest(R, BacktestConfig(allocator="erc", window=252, rebalance="M", target_vol=0.10,
                                         max_leverage=5.0))
    assert res.metrics["vol"] == pytest.approx(0.10, abs=0.012)
    np.testing.assert_allclose(res.ex_ante_vol.to_numpy(), 0.10, rtol=1e-12)


def test_band_rebalancing():
    R = _synthetic(n=400, seed=1)
    wide = run_backtest(R, BacktestConfig(allocator="inverse_vol", window=60, rebalance="M", band=1.0))
    assert (wide.turnover.iloc[1:] == 0).all() and wide.turnover.iloc[0] > 0
    tight = run_backtest(R, BacktestConfig(allocator="inverse_vol", window=60, rebalance="M", band=0.0))
    assert (tight.turnover.iloc[1:-1] > 0).mean() > 0.95
    cal = run_backtest(R, BacktestConfig(allocator="inverse_vol", window=60, rebalance="M"))
    assert ((cal.turnover > 0).sum()) == len(cal.targets)


def test_schedule_mask():
    idx = pd.bdate_range("2024-01-01", "2024-04-30")
    m = schedule_mask(idx, "M")
    assert list(idx[m]) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29"), pd.Timestamp("2024-03-29")]
    assert not m[-1]
    assert schedule_mask(idx, 5, start=2)[2] and schedule_mask(idx, 5, start=2)[7]


def test_unequal_history_and_held_nan():
    R = _synthetic(n=500)
    R.iloc[:200, 3] = np.nan
    res_any = run_backtest(R, BacktestConfig(allocator="erc", window=60, rebalance="M", start_when="any"))
    assert res_any.targets.iloc[0, 3] == 0 and res_any.targets.iloc[-1, 3] > 0
    res_all = run_backtest(R, BacktestConfig(allocator="erc", window=60, rebalance="M"))
    assert res_all.equity.index[0] > R.index[200]
    R2 = R.copy()
    R2.iloc[400, 0] = np.nan
    with pytest.raises(ValidationError, match="no return"):
        run_backtest(R2, BacktestConfig(allocator="erc", window=60, rebalance="M"))


def test_benchmark_and_config_validation():
    R = _synthetic(n=600)
    res = run_backtest(R, BacktestConfig(allocator="hrp", window=100, rebalance="Q", cost_bps=5), benchmark=R["W"])
    for k in ("tracking_error", "information_ratio", "beta", "excess_cagr"):
        assert k in res.benchmark
    for bad in (dict(window=1), dict(estimator="x"), dict(estimator="ewma"), dict(rebalance="X"),
                dict(cost_bps=-1), dict(max_leverage=0)):
        with pytest.raises(ValidationError):
            run_backtest(R, BacktestConfig(**{"allocator": "erc", **bad}))


# ----------------------------------------------------------------- metrics ----
def test_metrics_hand_values():
    idx = pd.to_datetime(["2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06"])
    r = pd.Series([0.10, -0.20, 0.05, 0.10], index=idx)
    eq = M.equity_curve(r)
    assert eq.iloc[-1] == pytest.approx(1.1 * 0.8 * 1.05 * 1.1)
    assert M.max_drawdown(eq) == pytest.approx(-0.20)
    dd = M.drawdown(eq).to_numpy()
    assert M.ulcer_index(eq) == pytest.approx(np.sqrt(np.mean(dd ** 2)))
    tuw = M.time_under_water(eq)
    assert tuw["fraction_under_water"] == pytest.approx(0.75) and tuw["max_days"] == 3  # Jan 3 peak, unrecovered by Jan 6
    m = M.performance_metrics(r, periods_per_year=252, start_date=pd.Timestamp("2023-01-02"))
    assert m["cagr"] == pytest.approx((1.1 * 0.8 * 1.05 * 1.1) ** (365.25 / 4) - 1)
    assert m["vol"] == pytest.approx(r.std(ddof=1) * np.sqrt(252))
    assert m["max_drawdown"] == pytest.approx(-0.20)


def test_calendar_years_and_loss_years():
    idx = pd.bdate_range("2019-03-01", "2023-06-30")
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0002, 0.01, len(idx)), index=idx)
    cy = M.calendar_year_returns(r)
    assert not cy.loc[2019, "complete"] and not cy.loc[2023, "complete"] and cy.loc[2020:2022, "complete"].all()
    m = M.performance_metrics(r, periods_per_year=252)
    full = cy[cy["complete"]]["return"]
    assert m["worst_year"] == pytest.approx(full.min()) and m["p_loss_year"] == pytest.approx((full < 0).mean())
    with pytest.raises(ValidationError):
        M.performance_metrics(pd.Series([0.1, np.nan], index=idx[:2]), periods_per_year=252)
