"""Decoupled-book + tearsheet math tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from barbell.portfolio.tearsheet import drawdown_table, risk_contributions


class TestRiskContributions:
    def test_sum_to_one_and_match_variance(self):
        rng = np.random.default_rng(7)
        mat = pd.DataFrame(rng.normal(0, 0.01, (1000, 3)), columns=["A", "B", "C"])
        w = {"A": 0.5, "B": 0.3, "C": 0.2}
        rc = risk_contributions(mat, w)
        assert float(rc.sum()) == pytest.approx(1.0)
        # equal-vol independent assets: contribution ∝ w_i^2
        expected = np.array([0.25, 0.09, 0.04])
        assert np.allclose(rc.values, expected / expected.sum(), atol=0.05)

    def test_high_vol_asset_dominates(self):
        rng = np.random.default_rng(8)
        mat = pd.DataFrame({"CALM": rng.normal(0, 0.002, 2000),
                            "WILD": rng.normal(0, 0.03, 2000)})
        rc = risk_contributions(mat, {"CALM": 0.5, "WILD": 0.5})
        assert rc["WILD"] > 0.95


class TestDrawdownTable:
    def test_hand_case(self):
        idx = pd.bdate_range("2020-01-01", periods=6)
        # up, -20% crash over 2 days, full recovery, new high
        r = pd.Series([0.10, -0.10, -0.1112, 0.20, 0.05, 0.01], index=idx)
        eps = drawdown_table(r)
        assert len(eps) >= 1
        worst = eps[0]
        assert worst["depth"] == pytest.approx(-0.20, abs=0.005)
        assert worst["recovered"] is not None

    def test_ongoing_drawdown_flagged(self):
        idx = pd.bdate_range("2020-01-01", periods=4)
        r = pd.Series([0.05, -0.10, -0.05, -0.02], index=idx)
        eps = drawdown_table(r)
        assert eps[0]["recovered"] is None


@pytest.mark.network
class TestBookLive:
    def _con(self):
        from barbell import db
        if not db.DB_PATH.exists():
            pytest.skip("no ingested store")
        return db.connect()

    def test_sleeve_only_equals_combined_at_zero(self):
        from barbell.portfolio.book import book_frame
        df = book_frame(self._con(), bot_frac=0.0)
        assert (df["sleeve"] == df["combined"]).all()

    def test_fraction_changes_risk_profile(self):
        from barbell.config import load
        from barbell.portfolio.book import book_frame, evaluate_fraction
        con = self._con()
        mc = load("backtest")["monte_carlo"]
        joint = book_frame(con, 0.3, allow_bot_model=True, kill_switch="fails")
        r0 = evaluate_fraction(joint, 0.0, 3000, int(mc["block_len_days"]), 1)
        r3 = evaluate_fraction(joint, 0.3, 3000, int(mc["block_len_days"]), 1)
        # a failing-kill-switch bot at 30% must worsen the left tail vs sleeve-only
        assert r3["cvar5_annual"] < r0["cvar5_annual"]

    def test_bad_fraction_rejected(self):
        from barbell.portfolio.book import book_frame
        with pytest.raises(ValueError):
            book_frame(self._con(), bot_frac=1.0)


class TestChatBackends:
    def test_openai_tool_conversion_shape(self):
        from barbell.chat.agent import TOOLS, _openai_tools
        conv = _openai_tools()
        assert len(conv) == len(TOOLS)
        for t in conv:
            assert t["type"] == "function"
            f = t["function"]
            assert set(f) == {"name", "description", "parameters"}
            assert f["parameters"]["type"] == "object"

    def test_no_keys_raises_clear_error(self, monkeypatch):
        import pytest as _pytest
        from barbell.chat import agent
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with _pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY or"):
            agent.answer([{"role": "user", "content": "hi"}])
