"""Price lane parser against the real stockanalysis.com response shape
(tests/fixtures/stockanalysis_mrna_history.json, captured live 2026-08-19)."""
from __future__ import annotations

import pytest

from app.engine.signals import drift_z10, realized_vol_20d
from app.lanes import prices
from tests.conftest import FakeResponse, load_fixture


@pytest.fixture()
def fixture():
    return load_fixture("stockanalysis_mrna_history.json")


def test_parse_history_orders_oldest_first(fixture):
    bars = prices.parse_history(fixture)
    assert len(bars) == 40
    dates = [b["date"] for b in bars]
    assert dates == sorted(dates)          # upstream is newest-first; we flip
    assert bars[-1]["date"] == "2026-08-18"


def test_adjusted_close_used(fixture):
    bars = prices.parse_history(fixture)
    # 'a' is the adjusted close in the raw payload
    raw_by_date = {r["t"]: r for r in fixture["data"]}
    for b in bars[:5]:
        assert b["adj_close"] == raw_by_date[b["date"]]["a"]


def test_last_close(fixture):
    bars = prices.parse_history(fixture)
    assert prices.last_close(bars) == bars[-1]["adj_close"]
    assert prices.last_close([]) is None


def test_real_series_feeds_signals(fixture):
    closes = prices.adj_closes(prices.parse_history(fixture))
    assert drift_z10(closes) is not None
    assert realized_vol_20d(closes) is not None


def test_parse_tolerates_garbage():
    assert prices.parse_history({}) == []
    assert prices.parse_history({"data": "nope"}) == []
    assert prices.parse_history(None) == []


def test_fetch_dark_lane_returns_empty(monkeypatch, caplog):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(prices.httpx, "get", boom)
    monkeypatch.setattr(prices, "cached", lambda key, producer, ttl=None: producer())
    monkeypatch.setattr(prices, "with_backoff", lambda fn, **k: fn())
    with caplog.at_level("WARNING"):
        assert prices.fetch_history("MRNA") == []
    assert any("DARK" in r.message for r in caplog.records)


def test_fetch_parses_fixture(monkeypatch, fixture):
    monkeypatch.setattr(prices.httpx, "get",
                        lambda *a, **k: FakeResponse(fixture))
    monkeypatch.setattr(prices, "cached", lambda key, producer, ttl=None: producer())
    bars = prices.fetch_history("MRNA")
    assert len(bars) == 40
