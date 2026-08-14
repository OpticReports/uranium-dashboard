"""Portfolio lab tests: scenario engines, optimizers, bot model mechanics."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from barbell.portfolio.simulate import (
    _stationary_indices,
    bootstrap_paths,
    mvt_paths,
    path_metrics,
)
from barbell.portfolio.optimizers import hrp_weights, nco_weights


def _hist(days=1500, k=3, seed=2):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=days)
    cols = {f"A{i}": rng.normal(0.0003, 0.008 + 0.002 * i, days) for i in range(k)}
    return pd.DataFrame(cols, index=idx)


class TestStationaryBootstrap:
    def test_indices_valid_and_blocky(self):
        rng = np.random.default_rng(0)
        idx = _stationary_indices(rng, 200, 500, 1000, 21)
        assert idx.shape == (200, 500)
        assert idx.min() >= 0 and idx.max() < 1000
        # consecutive-continuation frequency ≈ 1 - 1/block
        cont = (np.diff(idx, axis=1) % 1000 == 1).mean()
        assert 0.90 < cont < 0.98

    def test_bootstrap_preserves_mean_roughly(self):
        h = _hist()
        w = np.array([0.5, 0.3, 0.2])
        paths = bootstrap_paths(h, w, 4000, 1, 21, seed=1)
        sim_mean = paths["annual_returns"].mean()
        hist_annual = (h.values @ w).mean() * 252
        assert sim_mean == pytest.approx(hist_annual, abs=0.02)


class TestMVT:
    def test_moments_match_history(self):
        h = _hist()
        w = np.array([0.4, 0.4, 0.2])
        paths = mvt_paths(h, w, 4000, 1, df=5, seed=3)
        hist_daily = h.values @ w
        assert paths["annual_returns"].mean() == pytest.approx(
            hist_daily.mean() * 252, abs=0.02)
        # annual vol in the right ballpark
        assert paths["annual_returns"].std() == pytest.approx(
            hist_daily.std() * np.sqrt(252), rel=0.25)

    def test_df_must_exceed_2(self):
        with pytest.raises(ValueError):
            mvt_paths(_hist(), np.array([1, 0, 0.0]), 100, 1, df=2.0)


class TestPathMetrics:
    def test_deterministic_path(self):
        # constant +10% years, zero drawdown
        paths = {
            "terminal_wealth": np.array([1.1**10] * 100),
            "annual_returns": np.array([0.10] * 1000),
            "max_drawdowns": np.zeros(100),
            "n_paths": 100, "horizon_years": 10,
        }
        m = path_metrics(paths)
        assert m["cagr_median"] == pytest.approx(0.10)
        assert m["cvar5_annual"] == pytest.approx(0.10)
        assert m["prob_loss_10y"] == 0.0


class TestHRPNCO:
    def test_weights_sum_to_one_and_long_only(self):
        h = _hist(k=6)
        for fn in (hrp_weights, nco_weights):
            w = fn(h)
            assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)
            assert all(v >= 0 for v in w.values())

    def test_hrp_prefers_low_vol_asset(self):
        # two independent assets, one much riskier -> HRP tilts to the calm one
        rng = np.random.default_rng(9)
        idx = pd.bdate_range("2020-01-01", periods=1000)
        h = pd.DataFrame({"CALM": rng.normal(0, 0.005, 1000),
                          "WILD": rng.normal(0, 0.02, 1000)}, index=idx)
        w = hrp_weights(h)
        assert w["CALM"] > 0.7


@pytest.mark.network
class TestBotModel:
    """Bot-model mechanics need real VIX history from the ingested store."""

    def _con(self):
        from barbell import db
        if not db.DB_PATH.exists():
            pytest.skip("no ingested store")
        return db.connect()

    def test_kill_switch_ordering_in_crises(self):
        from barbell.portfolio.combined import model_bot_returns
        con = self._con()
        perfect = model_bot_returns(con, "perfect")
        lag1 = model_bot_returns(con, "lag1")
        fails = model_bot_returns(con, "fails")
        # cumulative outcome must order: perfect >= lag1 >= fails
        wp = float((1 + perfect).prod())
        wl = float((1 + lag1).prod())
        wf = float((1 + fails).prod())
        assert wp >= wl >= wf
        # and the spike months must actually hurt the no-kill-switch bot
        assert wf < wp * 0.9

    def test_spike_months_compound_to_configured_loss(self):
        from barbell.portfolio.combined import model_bot_returns, _vix_frames
        from barbell.config import load
        con = self._con()
        m = load("portfolio")["bot_model"]
        fails = model_bot_returns(con, "fails")
        v = _vix_frames(con)
        # find one spike month and verify compounded return ≈ configured
        by_month = v["vix"].groupby(v.index.to_period("M"))
        spikes = [p for p, g in by_month
                  if g.max() >= m["vix_spike_threshold"]
                  and g.max() / g.iloc[0] >= m["vix_spike_month_rise"]]
        assert spikes, "expected at least one VIX spike month in history (e.g. 2020-03)"
        p = spikes[0]
        month_ret = float((1 + fails[fails.index.to_period("M") == p]).prod() - 1)
        assert month_ret == pytest.approx(m["spike_month_return"], abs=0.02)
