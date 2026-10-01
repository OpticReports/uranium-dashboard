"""Gates on the Calls Log backtest panel's data.

Three things can go wrong with a frozen-number panel and none shows up in a
passing build: the numbers drift away from the documented record, the file
quietly fails to exist where production looks for it, or the committed
artifact stops matching the code that claims to generate it. All three are
here.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.calls import backtest
from scripts import backtest_summary as S
from scripts.backtest_variants_10y import V0_EXPECTED, V0_TOL


def _clear():
    backtest.load_summary.cache_clear()
    backtest.summary_bytes.cache_clear()


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


def test_gate_the_three_preregistered_subperiods_are_present():
    w = backtest.load_summary()["windows_daily"]
    assert {"full", "2016-2019", "2020-2022", "2023-2026"} <= set(w)
    for k, v in w.items():
        assert {"V0", "XBI", "SPY"} <= set(v["books"]), k


def test_gate_committed_summary_matches_the_generator():
    """Editing CAVEATS or the sizing rows in the script without regenerating
    would ship a page that disagrees with the code while every other test
    passes. trailing_daily is excluded only because it depends on whether
    the bar cache was present at build time; it is pinned separately."""
    built = S.build()
    committed = backtest.load_summary()
    assert set(built) == set(committed), "a key was added or removed without regenerating"
    for k in committed:
        if k in ("generated", "trailing_daily"):
            continue
        assert built[k] == committed[k], f"committed summary stale at key {k!r}"


def test_gate_dollar_and_r_bases_are_labelled_and_never_mixed():
    s = backtest.load_summary()
    assert "REALIZATION" in s["trailing_r"]["basis"]
    for w in s["trailing_r"]["windows"].values():
        assert "sharpe" not in w, "an R-basis window must not carry a Sharpe"
    td = s["trailing_daily"]
    assert td["status"] in ("ok", "partial", "unavailable")
    if td["status"] != "ok":
        assert td["reason"] and td["hint"], "a gap must say why and how to fill it"
        assert "backtest_bars.json" in td["detail"] or "V0 gate" in td["detail"]
    if td["status"] == "partial":
        assert set(td["windows"]) == {"10y"}
        assert td["windows"]["10y"]["books"] == s["windows_daily"]["full"]["books"]


def test_gate_recomputed_trailing_dollars_agree_with_the_copied_full_period():
    """When the bar cache was present, the 10y trailing window IS the full
    replay, recomputed on that cache. It must agree with the full-period row
    copied from the variants run within the machinery gate - otherwise the
    page would show two different Sharpes for one book."""
    s = backtest.load_summary()
    td = s["trailing_daily"]
    if td["status"] != "ok":
        pytest.skip(f"no gate-passing bar cache at build time: {td.get('detail')}")
    assert set(td["windows"]) == {"2y", "5y", "10y"}
    ten, full = td["windows"]["10y"]["books"]["V0"], s["windows_daily"]["full"]["books"]["V0"]
    for k, tol in (("max_dd", V0_TOL["max_dd"]), ("sharpe", V0_TOL["sharpe"]),
                   ("cagr", V0_TOL["cagr"])):
        assert abs(ten[k] - full[k]) <= tol, k
    assert td["v0_gate"]["passed"] is True
    for w in td["windows"].values():
        assert {"V0", "XBI"} <= set(w["books"])


def test_gate_caveats_name_the_biases_that_matter():
    text = " ".join(backtest.load_summary()["caveats"]).lower()
    assert "survivor" in text
    assert "not replayed" in text
    assert "skipped" in text and "cap" in text          # 3,872 of 5,008 fires
    assert "submit" in text                                # the measured PIT lead
    assert "estimate" in text                              # PCD is not a readout date


# --- the generator's own guards ---------------------------------------------------

def test_generator_refuses_when_the_capped_selection_drifts(monkeypatch):
    """If the selection no longer matches the replay's own book, nothing
    downstream is about the documented numbers."""
    real = S.select_capped
    monkeypatch.setattr(S, "select_capped", lambda rows, cap: (real(rows, cap)[0][:-1], 1))
    with pytest.raises(SystemExit, match="drifted"):
        S.build()


def test_v0_gate_accepts_the_documented_book_and_rejects_a_drifted_one():
    """A bar cache fetched later from another lane could put trailing-window
    numbers on the page that silently disagree with the copied full-period
    row. The gate is the same +/-1% rule the variants script enforces."""
    ok = {"end_value": V0_EXPECTED["end"], "cagr": V0_EXPECTED["cagr"],
          "max_dd": V0_EXPECTED["max_dd"], "sharpe": V0_EXPECTED["sharpe"]}
    assert S.v0_mismatch(ok) is None
    bad = {**ok, "max_dd": V0_EXPECTED["max_dd"] + 0.05}
    msg = S.v0_mismatch(bad)
    assert msg and "max_dd" in msg


def test_the_10y_window_is_filled_from_the_full_period_when_the_cache_is_absent():
    """The 10y window IS the full replay; its dollar stats exist regardless
    of the cache. The first draft claimed a gap on the 10y tab that the Full
    tab had already filled."""
    wd = {"full": {"start": "2016-01-04", "end": "2026-08-19", "years": 10.62,
                   "books": {"V0": {"max_dd": 0.655}}}}
    td = S.with_full_as_10y({"status": "unavailable", "windows": None,
                             "reason": "r", "hint": "h"}, wd)
    assert td["status"] == "partial"
    assert td["windows"]["10y"]["books"] == wd["full"]["books"]
    assert "full replay" in td["windows"]["10y"]["note"]
    untouched = {"status": "ok", "windows": {"2y": {}}}
    assert S.with_full_as_10y(untouched, wd) is untouched


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


def test_trailing_start_floors_the_10y_window_at_the_replay_start_and_keeps_2y_exact():
    assert S._trailing_start(date(2026, 8, 19), 10) == S.START
    assert S._trailing_start(date(2026, 8, 19), 5) == date(2021, 8, 19)
    assert S._trailing_start(date(2026, 8, 19), 2) == date(2024, 8, 19)


def test_trailing_windows_in_the_committed_summary_are_consistent():
    """Longer windows contain shorter ones, and the 10y window is the whole
    replay: its n, total R and max DD must equal the combined book's."""
    s = backtest.load_summary()
    w = s["trailing_r"]["windows"]
    assert w["2y"]["n_calls"] <= w["5y"]["n_calls"] <= w["10y"]["n_calls"]
    assert w["10y"]["n_calls"] == s["combined_book"]["n_calls"]
    assert w["10y"]["total_r"] == pytest.approx(s["combined_book"]["total_r"], abs=0.01)
    assert w["10y"]["max_dd_r"] == pytest.approx(s["combined_book"]["max_dd_r"], abs=0.01)


# --- the endpoint ------------------------------------------------------------------

def test_endpoint_serves_the_summary_as_json():
    from fastapi.testclient import TestClient
    from app.main import app

    _clear()
    r = TestClient(app).get("/calls/backtest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["schema"] == S.SCHEMA
    assert body["windows_daily"]["full"]["books"]["V0"]["max_dd"] > 0.5


def test_endpoint_is_a_clear_404_when_the_file_is_missing(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    _clear()
    monkeypatch.setattr(backtest, "SUMMARY_PATH", tmp_path / "nope.json")
    try:
        r = TestClient(app).get("/calls/backtest")
        assert r.status_code == 404
        assert "backtest_summary" in r.json()["detail"]
    finally:
        _clear()
