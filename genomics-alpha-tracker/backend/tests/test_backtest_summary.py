"""Gates on the Calls Log backtest panel's data.

Two things can go wrong with a frozen-number panel and neither shows up in a
passing build: the numbers drift away from the documented record, or the
file quietly fails to exist where production looks for it. Both are here.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.calls import backtest
from scripts import backtest_summary as S


# --- the frozen record ---------------------------------------------------------

def test_gate_summary_file_is_committed_inside_the_package():
    """The Render disk mounts over /app/data and hides whatever the image
    carried there. A summary under backend/data/ would pass every local test
    and be missing in production."""
    assert backtest.SUMMARY_PATH.exists(), "run `python -m scripts.backtest_summary`"
    assert "data" not in backtest.SUMMARY_PATH.relative_to(S.BACKEND).parts


def test_gate_full_period_numbers_match_the_documented_addendum():
    """BACKTEST_CALLS_10Y.md: $208,764 / +7.2% / 65.5% / 0.42 (the variants
    machinery reproduces the end value to $4). If a regenerate moves these,
    the page would be quoting a different backtest than the docs."""
    v0 = backtest.load_summary()["windows_daily"]["full"]["books"]["V0"]
    assert abs(v0["end_value"] - 208_764) <= 50
    assert abs(v0["max_dd"] - 0.655) <= 0.0015
    assert abs(v0["sharpe"] - 0.42) <= 0.005
    assert abs(v0["cagr"] - 0.0719) <= 0.0006


def test_gate_benchmarks_are_present_so_the_engine_is_never_shown_alone():
    """The honest reading of this replay is 'about sector beta'. A table
    without XBI on it cannot be read that way."""
    full = backtest.load_summary()["windows_daily"]["full"]["books"]
    assert {"V0", "XBI", "SPY"} <= set(full)
    assert abs(full["XBI"]["max_dd"] - 0.639) <= 0.0015


def test_gate_dollar_and_r_bases_are_labelled_and_never_mixed():
    s = backtest.load_summary()
    assert "REALIZATION" in s["trailing_r"]["basis"]
    for w in s["trailing_r"]["windows"].values():
        assert "sharpe" not in w, "an R-basis window must not carry a Sharpe"
    td = s["trailing_daily"]
    assert td["status"] in ("ok", "unavailable")
    if td["status"] == "unavailable":
        assert "backtest_bars.json" in td["reason"]
        assert td["windows"] is None


def test_gate_caveats_name_the_two_biases_that_matter():
    text = " ".join(backtest.load_summary()["caveats"]).lower()
    assert "survivor" in text
    assert "not replayed" in text or "were not replayed" in text


# --- the trailing-window arithmetic (known answers) --------------------------------

def _row(exit_date: str, r_net: float, sym: str = "A") -> dict:
    return {"exit_date": exit_date, "entry_date": "2020-01-01", "symbol": sym,
            "flag": "f", "r_net": r_net}


def test_trailing_r_window_counts_a_call_in_the_window_it_exited_in():
    rows = [_row("2024-08-18", 1.0), _row("2024-08-19", 2.0), _row("2024-08-20", -1.0)]
    w = S.trailing_r_stats(rows, date(2024, 8, 19), date(2026, 8, 19))
    assert w["n_calls"] == 2
    assert w["total_r"] == pytest.approx(1.0)


def test_trailing_r_drawdown_measures_from_a_zero_peak():
    """An opening losing streak IS a drawdown - the same convention as the
    replay's own max_drawdown_r, so the 10y number on the page and the
    trailing numbers are comparable."""
    rows = [_row("2025-01-01", -1.0), _row("2025-01-02", -1.5), _row("2025-01-03", 4.0),
            _row("2025-01-04", -0.5)]
    w = S.trailing_r_stats(rows, date(2024, 8, 19), date(2026, 8, 19))
    assert w["max_dd_r"] == pytest.approx(2.5)        # 0 -> -2.5
    assert w["total_r"] == pytest.approx(1.0)
    assert w["hit_rate"] == pytest.approx(0.25)


def test_trailing_start_is_floored_at_the_replay_start():
    assert S._trailing_start(date(2026, 8, 19), 10) == S.START
    assert S._trailing_start(date(2026, 8, 19), 2) == date(2024, 8, 19)


def test_trailing_windows_in_the_committed_summary_are_consistent():
    """Longer windows contain shorter ones: n and the realized-R path of the
    10y window must dominate the 5y, which dominates the 2y."""
    w = backtest.load_summary()["trailing_r"]["windows"]
    assert w["2y"]["n_calls"] <= w["5y"]["n_calls"] <= w["10y"]["n_calls"]
    assert w["10y"]["n_calls"] == backtest.load_summary()["combined_book"]["n_calls"]
    assert w["10y"]["total_r"] == pytest.approx(
        backtest.load_summary()["combined_book"]["total_r"], abs=0.01)
    assert w["10y"]["max_dd_r"] == pytest.approx(
        backtest.load_summary()["combined_book"]["max_dd_r"], abs=0.01)


# --- the endpoint ------------------------------------------------------------------

def test_endpoint_serves_the_summary():
    from fastapi.testclient import TestClient
    from app.main import app

    r = TestClient(app).get("/calls/backtest")
    assert r.status_code == 200
    body = r.json()
    assert body["schema"] == S.SCHEMA
    assert body["windows_daily"]["full"]["books"]["V0"]["max_dd"] > 0.5


def test_endpoint_is_a_clear_404_when_the_file_is_missing(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    backtest.load_summary.cache_clear()
    monkeypatch.setattr(backtest, "SUMMARY_PATH", tmp_path / "nope.json")
    try:
        r = TestClient(app).get("/calls/backtest")
        assert r.status_code == 404
        assert "backtest_summary" in r.json()["detail"]
    finally:
        backtest.load_summary.cache_clear()
