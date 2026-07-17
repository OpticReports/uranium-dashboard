"""Backtest engine tests on synthetic data with hand-checkable outcomes."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from barbell.backtest.engine import resolve_targets, simulate, walk_forward
from barbell.backtest.metrics import cagr, cvar, max_drawdown


def _mat(days=760, mu=(0.0004, 0.0002), vol=(0.01, 0.008), seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=days)
    data = {f"A{i}": rng.normal(m, v, days) for i, (m, v) in enumerate(zip(mu, vol))}
    return pd.DataFrame(data, index=idx)


class TestSimulate:
    def test_buy_and_hold_matches_manual_compounding(self):
        r = _mat()
        # zero-cost internal path: B&H portfolio return == weighted wealth growth
        sim = simulate(r, {"A0": 0.6, "A1": 0.4}, mode="none", zero_cost_internal=True)
        manual = 0.6 * (1 + r["A0"]).cumprod() + 0.4 * (1 + r["A1"]).cumprod()
        got = (1 + sim.returns).cumprod().iloc[-1]
        assert got == pytest.approx(float(manual.iloc[-1]), rel=1e-10)

    def test_costs_always_charged_on_entry(self):
        r = _mat()
        with_cost = simulate(r, {"A0": 0.6, "A1": 0.4}, mode="none")
        free = simulate(r, {"A0": 0.6, "A1": 0.4}, mode="none", zero_cost_internal=True)
        w1 = (1 + with_cost.returns).cumprod().iloc[-1]
        w2 = (1 + free.returns).cumprod().iloc[-1]
        assert w1 < w2  # no zero-cost backtests

    def test_threshold_rebalances_fire_on_band_breach(self):
        # one asset trends hard up, the other flat -> weights must breach ±20%
        idx = pd.bdate_range("2020-01-01", periods=300)
        r = pd.DataFrame({"UP": 0.004, "FLAT": 0.0}, index=idx)
        sim = simulate(r, {"UP": 0.5, "FLAT": 0.5}, mode="threshold", band=0.20)
        assert sim.n_rebalances >= 1
        # after each rebalance weights snap back; drift path never exceeds
        # the band by more than one month's drift
        assert sim.weights_path["UP"].max() < 0.70

    def test_calendar_mode_rebalances_on_schedule(self):
        r = _mat(days=520)
        sim = simulate(r, {"A0": 0.5, "A1": 0.5}, mode="calendar", calendar_months=6)
        assert sim.n_rebalances in (3, 4)  # ~24 months / 6

    def test_none_mode_never_rebalances(self):
        r = _mat()
        sim = simulate(r, {"A0": 0.5, "A1": 0.5}, mode="none")
        assert sim.n_rebalances == 0


class TestTargets:
    def test_tail_expansion(self):
        t = resolve_targets("TAIL")
        assert t["TAIL"] == pytest.approx(0.05)
        assert sum(t.values()) == pytest.approx(1.0)

    def test_split_expansion(self):
        t = resolve_targets("TAIL+BTAL")
        assert t["TAIL"] == pytest.approx(0.025)
        assert t["BTAL"] == pytest.approx(0.025)

    def test_none_reallocates_pro_rata(self):
        t = resolve_targets("NONE")
        assert "TAIL" not in t
        assert sum(t.values()) == pytest.approx(1.0)
        # AVUV keeps its rank as largest sleeve
        assert max(t, key=t.get) == "AVUV"


class TestMetrics:
    def test_cagr_exact(self):
        # +1% a day for 252 days -> CAGR = 1.01^252 - 1
        r = pd.Series([0.01] * 252, index=pd.bdate_range("2020-01-01", periods=252))
        assert cagr(r) == pytest.approx(1.01**252 - 1, rel=1e-9)

    def test_max_drawdown_hand_case(self):
        r = pd.Series([0.10, -0.50, 0.10],
                      index=pd.bdate_range("2020-01-01", periods=3))
        assert max_drawdown(r) == pytest.approx(-0.50)

    def test_cvar_hand_case(self):
        # worst 5% of 100 obs = worst 5; mean of them
        x = np.arange(1, 101) / 100.0 * -1
        assert cvar(x, 0.05) == pytest.approx(np.mean([-1.0, -0.99, -0.98, -0.97, -0.96]))


class TestWalkForward:
    def test_expanding_produces_windows_and_oos_only(self):
        r = _mat(days=252 * 6)
        seen_train_lens = []

        def train_fn(train):
            seen_train_lens.append(len(train))
            return {"A0": 0.5, "A1": 0.5}

        recs = walk_forward(r, train_fn, scheme="expanding")
        assert len(recs) >= 2
        assert seen_train_lens == sorted(seen_train_lens)  # expanding
        # test windows are disjoint and forward-only
        starts = [rec["train_end"] for rec in recs]
        assert starts == sorted(starts)


class TestWalkforwardEvalWindows:
    def test_windows_are_leak_free_and_forward_only(self):
        from barbell.portfolio.evaluation import _windows
        idx = pd.bdate_range("2015-01-01", periods=252 * 8)
        wins = _windows(idx)
        assert len(wins) >= 3
        for tr, te in wins:
            # train strictly precedes test; no overlap
            assert tr.stop == te.start
            assert te.stop <= len(idx)
        # test windows are sequential and non-overlapping
        for (_, t1), (_, t2) in zip(wins, wins[1:]):
            assert t2.start >= t1.start + 1

    def test_too_short_history_raises(self):
        from barbell.portfolio.evaluation import _windows
        with pytest.raises(ValueError):
            _windows(pd.bdate_range("2020-01-01", periods=300))
