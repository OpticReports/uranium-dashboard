"""Monitor tests: rebalance band math and trade-list integrity."""
from __future__ import annotations

import pytest

from barbell import db
from barbell.backtest.engine import resolve_targets
from barbell.config import load
from barbell.monitor.rebalance import check_rebalance


@pytest.fixture()
def con(tmp_path):
    return db.connect(tmp_path / "t.db")


def _positions_at_targets(total=1_000_000):
    tail = load("portfolio")["tail_sleeve"]["current"]
    return {"asof": "2026-01-01",
            "positions": {t: w * total for t, w in resolve_targets(tail).items()}}


class TestRebalance:
    def test_on_target_no_alert(self, con):
        res = check_rebalance(con, _positions_at_targets())
        assert not res["alert"]
        assert all(abs(r["trade_usd"]) < 1e-6 for r in res["rows"])

    def test_breach_fires_and_trades_net_to_zero(self, con):
        snap = _positions_at_targets()
        # push AVUV 30% above its dollar target and take it from PHYS
        delta = snap["positions"]["AVUV"] * 0.30
        snap["positions"]["AVUV"] += delta
        snap["positions"]["PHYS"] -= delta
        res = check_rebalance(con, snap)
        assert res["alert"]
        assert "AVUV" in res["breached"]
        # buying and selling back to target conserves total value
        assert sum(r["trade_usd"] for r in res["rows"]) == pytest.approx(0, abs=1e-6)
        # alert persisted
        n = con.execute("SELECT COUNT(*) FROM alerts WHERE kind='rebalance'").fetchone()[0]
        assert n == 1

    def test_unknown_ticker_rejected(self, con):
        snap = _positions_at_targets()
        snap["positions"]["GME"] = 5000
        with pytest.raises(ValueError, match="outside the sleeve"):
            check_rebalance(con, snap)
