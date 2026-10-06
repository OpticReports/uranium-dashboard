"""Regression gates for the 2026-10-06 adversarial review (findings HG-M*, BT-*).

Each test names the finding it pins.  All offline (synthetic data)."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from holygrail import core
from holygrail import forward as F
from holygrail.book import book_from_dict
from holygrail.cli import main
from holygrail.scorecard import ScoreSettings, scorecard
from holygrail.streams import build_moments


def A(v, conf="medium"):
    return {"value": v, "source": "test", "confidence": conf}


RF_INFO = {"value": 0.04, "basis": "assumption", "source": "t", "confidence": "high"}
SP_INFO = {"value": 0.01, "basis": "assumption", "source": "t", "confidence": "high"}


def _common(tmp_path, loader):
    return ["--cache-dir", str(loader.cache_dir), "--offline", "--out", str(tmp_path / "o")]


# --------------------------------------------------------------------------- #
# HG-M1: gearing a book that holds cash charges the spread on NEW borrowing only
# --------------------------------------------------------------------------- #
def _cashy_book(cash_rate=None, max_leverage=3.0):
    rng = np.random.default_rng(0)
    idx = pd.date_range("2018-01-05", periods=400, freq="W-FRI")
    eq = pd.DataFrame({"EQ": rng.normal(0.0012, 0.15 / math.sqrt(52), 400)}, index=idx)
    cash = {"type": "cash"} if cash_rate is None else {"type": "cash", "rate": A(cash_rate)}
    raw = {"name": "cashy", "settings": {"risk_free": A(0.04), "financing_spread": A(0.01), "target_vol": 0.15,
                                         "max_leverage": max_leverage},
           "streams": {"EQ": {"type": "market", "symbol": "EQ", "expected_return": A(0.08), "asset_class": "equity"},
                       "cash": cash},
           "positions": [{"name": "eq", "value_usd": 60000, "stream": "EQ"},
                         {"name": "cash", "value_usd": 40000, "stream": "cash"}],
           "totals": {"total_usd": 100000}}
    book = book_from_dict(raw)
    v = book.view("investable")
    m = build_moments(book.universe, v.streams, returns=eq, periods_per_year=52, rf=0.04, method="sample")
    return book, v, m


def test_hg_m1_gate_cash_funds_gearing_before_any_borrowing():
    mu, rf, spread = 0.07, 0.04, 0.02
    # 40% cash: the non-cash 60% can be scaled to 1/(1-0.4) with the book's own cash -> zero spread
    L = 1 / (1 - 0.4)
    assert core.new_borrowing(L, 0.4) == pytest.approx(0.0, abs=1e-15)
    assert core.geared_return(mu, rf, L, spread, cash_share=0.4) == pytest.approx(rf + L * (mu - rf))
    # beyond the kink only the excess over the book's cash is borrowed
    assert core.new_borrowing(2.0, 0.4) == pytest.approx(0.2)
    assert core.geared_return(mu, rf, 2.0, spread, cash_share=0.4) == pytest.approx(rf + 2 * (mu - rf) - 0.2 * spread)
    # no cash: identical to the old convention
    assert core.geared_return(mu, rf, 2.5, spread) == pytest.approx(rf + 2.5 * (mu - rf) - 1.5 * spread)


@pytest.mark.parametrize("mu,sig,spread,c0", [(0.0758, 0.0897, 0.01, 0.4), (0.08, 0.10, 0.02, 0.25),
                                              (0.06, 0.12, 0.01, 0.6), (0.09, 0.08, 0.03, -0.2),
                                              (0.05, 0.10, 0.01, 0.4)])
def test_hg_m1_kelly_maximises_log_growth_with_cash(mu, sig, spread, c0):
    rf = 0.04
    Ls = np.linspace(0, 15, 300001)
    g = [core.log_growth(mu, sig, rf, L, spread, cash_share=c0) for L in Ls]
    assert core.kelly_leverage(mu, sig, rf, spread, cash_share=c0) == pytest.approx(Ls[int(np.argmax(g))], abs=1e-4)


def test_hg_m1_scorecard_gearing_with_book_cash():
    book, v, m = _cashy_book(max_leverage=1.2)
    sc = scorecard(book, v, m, ScoreSettings.from_book(book), rf_info=RF_INFO, spread_info=SP_INFO)
    g, pm, pv = sc["gearing"], sc["portfolio"]["exp_return"], sc["portfolio"]["vol"]
    L = 0.15 / pv
    B = max(L * 0.6 - 1, 0.0)
    assert g["leverage_to_target"] == pytest.approx(L)
    assert g["new_borrowing_at_target"] == pytest.approx(B)
    assert g["exp_return_at_target"] == pytest.approx(0.04 + L * (pm - 0.04) - B * 0.01, rel=1e-12)
    Ls = np.linspace(0, 12, 240001)
    gl = 0.04 + Ls * (pm - 0.04) - np.maximum(Ls * 0.6 - 1, 0) * 0.01 - 0.5 * Ls ** 2 * pv ** 2
    assert g["kelly_leverage"] == pytest.approx(Ls[int(np.argmax(gl))], abs=1e-4)
    # max_leverage caps GROSS risky exposure (L x 60%), not the NAV scale factor
    assert g["gross_exposure_at_target"] == pytest.approx(L * 0.6)
    assert g["exceeds_max_leverage"] is False


def test_hg_m1_scorecard_cash_with_stated_rate():
    book, v, m = _cashy_book(cash_rate=0.05)
    sc = scorecard(book, v, m, ScoreSettings.from_book(book), rf_info=RF_INFO, spread_info=SP_INFO)
    g, pm, pv = sc["gearing"], sc["portfolio"]["exp_return"], sc["portfolio"]["vol"]
    L = 0.15 / pv
    e_u = 0.6 * float(m.mu[0]) - 0.6 * 0.04          # excess of the non-cash part
    assert pm == pytest.approx(0.6 * float(m.mu[0]) + 0.4 * 0.05)
    # the cash's premium over rf is carried unchanged; extra exposure costs rf (+ spread past the kink)
    assert g["exp_return_at_target"] == pytest.approx(pm + (L - 1) * e_u - max(L * 0.6 - 1, 0) * 0.01, rel=1e-12)


def test_hg_m1_forward_terms_match_scorecard_geared_mean():
    book, v, m = _cashy_book()
    sc = scorecard(book, v, m, ScoreSettings.from_book(book), rf_info=RF_INFO, spread_info=SP_INFO)
    w = np.array([v.weights()[n] for n in m.names])
    L = sc["gearing"]["leverage_to_target"]
    t = F.book_terms(m, w, leverage=L, spread=0.01)
    assert t["spread_weight"] == pytest.approx(sc["gearing"]["new_borrowing_at_target"])
    assert t["cash_weight"] == pytest.approx(1 - L * 0.6)
    drift = float(t["x"] @ m.base_mu) + t["const"] + t["cash_weight"] * 0.04 - t["spread_weight"] * 0.01
    assert drift == pytest.approx(sc["gearing"]["exp_return_at_target"], rel=1e-12)
    assert t["expected_return"] == pytest.approx(drift, rel=1e-12)


# --------------------------------------------------------------------------- #
# HG-M2: the forward honours a composite's own expected_return
# --------------------------------------------------------------------------- #
def test_hg_m2_forward_drift_equals_scorecard_mu_with_composite_assumption():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2018-01-05", periods=300, freq="W-FRI")
    H = pd.DataFrame({"SPY": rng.normal(0.0015, 0.022, 300), "TLT": rng.normal(0.0003, 0.015, 300)}, index=idx)
    raw = {"name": "t", "settings": {"risk_free": A(0.04)},
           "streams": {"SPY": {"type": "market", "symbol": "SPY", "expected_return": A(0.065)},
                       "TLT": {"type": "market", "symbol": "TLT", "expected_return": A(0.042)},
                       "SYM": {"type": "composite", "components": {"SPY": 0.5, "TLT": 0.5}, "leverage": 3.0,
                               "financing_spread": A(0.004), "expected_return": A(0.25)},
                       "cash": {"type": "cash"}},
           "positions": [{"name": "a", "value_usd": 45, "stream": "SPY"}, {"name": "b", "value_usd": 45, "stream": "SYM"},
                         {"name": "c", "value_usd": 10, "stream": "cash"}],
           "totals": {"total_usd": 100}}
    book = book_from_dict(raw)
    v = book.view("investable")
    m = build_moments(book.universe, v.streams, returns=H, periods_per_year=52, rf=0.04, method="sample")
    w = np.array([v.weights()[n] for n in m.names])
    book_mu = float(w @ m.mu)
    t = F.book_terms(m, w)
    assert t["expected_return"] == pytest.approx(book_mu, rel=1e-12)
    # and the simulation actually drifts there (mvn, per-period mean x 12)
    sim = F.simulate_returns(m.base_mu, m.base_cov, 12, 20000, periods_per_year=12, seed=3)
    port = F.portfolio_returns(sim, t["x"], rf_period=0.04 / 12, spread_period=0.0, const_period=t["const"] / 12,
                               cash_weight=t["cash_weight"], spread_weight=t["spread_weight"])
    se = port.std() / math.sqrt(port.size) * 12
    assert port.mean() * 12 == pytest.approx(book_mu, abs=5 * se)
    # bootstrap replays history: the composite's own assumption is excluded explicitly
    tb = F.book_terms(m, w, include_own_mu=False)
    assert tb["own_mu_ignored"] == ["SYM"]


# --------------------------------------------------------------------------- #
# BT-3: a book view's cash stream is the backtest's cash leg, not an asset
# --------------------------------------------------------------------------- #
CASH_BOOK = """
name: cash book
settings:
  risk_free: "fred:DTB3"
  financing_spread: {value: 0.005, source: test, confidence: medium}
streams:
  EQA: {type: market, symbol: EQA, asset_class: equity}
  BND: {type: market, symbol: BND, asset_class: nominal_bond}
  cash: {type: cash}
positions:
  - {name: A, value_usd: 60000, stream: EQA}
  - {name: B, value_usd: 0.01, stream: BND}
  - {name: C, value_usd: 39999.99, stream: cash}
totals: {total_usd: 100000}
"""


def test_bt3_erc_backtest_never_weights_cash(tmp_path, offline_loader, capsys):
    p = tmp_path / "cash.yaml"
    p.write_text(CASH_BOOK)
    args = ["backtest", "--book", str(p), "--allocator", "erc", "--target-vol", "0.10", "--max-leverage", "2",
            "--rf", "0.03", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    tg = pd.read_csv(tmp_path / "o" / "targets.csv")
    assert "cash" not in tg.columns
    assert set(tg.columns) - {"date"} == {"EQA", "BND"}
    assert "cash" in capsys.readouterr().out  # the mapping to the cash leg is printed


def test_bt3_book_allocator_cash_funds_gearing(tmp_path, offline_loader):
    p = tmp_path / "cash.yaml"
    p.write_text(CASH_BOOK)
    args = ["backtest", "--book", str(p), "--allocator", "book", "--target-vol", "0.12", "--max-leverage", "3",
            "--rf", "0.03", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    tg = pd.read_csv(tmp_path / "o" / "targets.csv")
    assert "cash" not in tg.columns
    # EQA vol ~18%: 0.12 target -> ~0.67 of NAV in EQA, the rest stays cash (no borrowing, gross < 1)
    assert bt["avg_gross_leverage"] < 1.0
    assert (tg[["EQA", "BND"]].sum(axis=1) < 1.0).all()


# --------------------------------------------------------------------------- #
# HG-M3: a correlation stress never lowers a correlation, and runs at leaf level
# --------------------------------------------------------------------------- #
def test_hg_m3_floor_stress_never_lowers_correlations_or_vol():
    S = np.array([[0.04, 0.9 * 0.2 * 0.6], [0.9 * 0.2 * 0.6, 0.36]])  # corr 0.90
    w = np.array([0.6, 0.4])
    for rs in (0.5, 0.8, 0.95):
        S2 = F.stress_correlation(S, method="floor", rho=rs)
        c2 = S2[0, 1] / math.sqrt(S2[0, 0] * S2[1, 1])
        assert c2 == pytest.approx(max(0.9, rs))
        assert w @ S2 @ w >= w @ S @ w - 1e-15
    # a floor that would break PSD falls back to a common-factor lift (still never lowers, still PSD)
    rng = np.random.default_rng(1)
    for _ in range(200):
        X = rng.normal(size=(6, 6)) @ np.diag(rng.uniform(0.1, 2, 6))
        Sx = X @ X.T
        S3, info = F.stress_correlation(Sx, method="floor", rho=0.6, return_info=True)
        sx, s3 = np.sqrt(np.diag(Sx)), np.sqrt(np.diag(S3))
        Cx, C3 = Sx / np.outer(sx, sx), S3 / np.outer(s3, s3)
        assert np.all(C3 >= Cx - 1e-12) and np.all(C3 >= 0.6 - 1e-12)
        assert np.linalg.eigvalsh(S3)[0] >= -1e-12
        np.testing.assert_allclose(s3, sx)
        assert info["method"] in ("floor", "common_factor_lift")


def test_hg_m3_stress_at_leaf_level_keeps_look_through_identities():
    vols = np.array([0.16, 0.25, 0.06, 0.6])  # SPY, QQQ, TLT, BTC
    C = np.array([[1, .9, -.2, .3], [.9, 1, -.2, .35], [-.2, -.2, 1, 0], [.3, .35, 0, 1]])
    Sb = C * np.outer(vols, vols)
    Am = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 3, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], float)  # + QQQ3X
    S2 = F.stress_look_through(Am, Sb, method="floor", rho=0.6)
    corr = S2[1, 2] / math.sqrt(S2[1, 1] * S2[2, 2])
    assert corr == pytest.approx(1.0)
    w = np.array([0.3, 0.1, 0.1, 0.3, 0.2])
    assert w @ S2 @ w > w @ (Am @ Sb @ Am.T) @ w


def test_hg_m3_cli_stress_vol_never_falls(tmp_path, test_book_yaml, offline_loader, capsys):
    runs = [["--tickers", "EQA,EQB", "--corr-rho", "0.3"],   # base corr ~0.6: replacing it by 0.3 LOWERED vol
            ["--book", str(test_book_yaml), "--missing", "cash", "--corr-rho", "0.5"]]
    for extra in runs:
        args = ["stress", *extra, "--scenarios", "covid", *_common(tmp_path, offline_loader)]
        assert main(args) == 0
        row = json.loads((tmp_path / "o" / "corr_stress.json").read_text())[0]
        assert row["vol_stress"] >= row["vol_base"] - 1e-12
        assert row["dr2_stress"] <= row["dr2_base"] + 1e-9
    assert "floor" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# HG-M6: simulated default jumps reproduce the declared two-point annual variance
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("p", [0.02, 0.10, 0.25])
def test_hg_m6_jump_variance_matches_two_point_model(p):
    loss = 0.5
    sims = F.simulate_returns(np.array([0.08]), np.array([[1e-14]]), 12 * 5, 40000, periods_per_year=12, seed=1,
                              jumps=[{"base_index": 0, "prob": p, "loss": loss}])
    yearly = sims[:, :, 0].reshape(40000, 5, 12)
    annual = yearly.sum(axis=2).ravel()
    jv = p * (1 - p) * loss ** 2
    assert annual.var() == pytest.approx(jv, rel=0.03)
    assert annual.mean() == pytest.approx(0.08, abs=4 * math.sqrt(jv / annual.size))
    defaults = (yearly < -0.2).sum(axis=2)
    assert defaults.max() <= 1                       # at most one default per simulated year
    assert np.mean(defaults) == pytest.approx(p, rel=0.03)


# --------------------------------------------------------------------------- #
# HG-M4 / BT-2: periods per year come from the calendar actually used
# --------------------------------------------------------------------------- #
def test_hg_m4_crypto_backtest_annualises_on_its_7_day_calendar(tmp_path, offline_loader):
    args = ["backtest", "--tickers", "CRYX", "--allocator", "equal_weight", "--target-vol", "0.40",
            "--max-leverage", "3", "--rf", "0.04", "--cost-bps", "0", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    assert bt["config"]["periods_per_year"] == pytest.approx(365.25, rel=0.005)
    eq = pd.read_csv(tmp_path / "o" / "equity.csv", parse_dates=[0], index_col=0).iloc[:, 0]
    r = eq.pct_change().dropna()
    true_vol = r.std() * math.sqrt(len(r) / ((r.index[-1] - r.index[0]).days / 365.25))
    assert bt["metrics"]["vol"] == pytest.approx(true_vol, rel=0.01)


def test_hg_m4_constant_rf_and_composite_constants_accrue_by_calendar_days(offline_loader):
    from argparse import Namespace
    from holygrail.cli import _daily_stream_returns, _rf_daily
    from holygrail.streams import CompositeStream, MarketStream, Universe
    for idx in (pd.date_range("2020-01-01", "2023-12-31", freq="D"), pd.bdate_range("2020-01-01", "2023-12-31")):
        rf, _ = _rf_daily(Namespace(rf="0.04"), None, idx)
        assert rf.loc["2021"].sum() == pytest.approx(0.04, rel=0.01)
    uni = Universe([MarketStream(name="CRYX", symbol="CRYX"),
                    CompositeStream(name="FEE", components={"CRYX": 1.0}, fee=A(0.02))])
    R, _ = _daily_stream_returns(uni, ["CRYX", "FEE"], offline_loader)
    drag = (R["FEE"] - R["CRYX"]).loc["2021"].sum()
    assert drag == pytest.approx(-0.02, rel=0.01)  # a 2% fee costs 2% a year, not 2% x 365/252


def test_hg_m4_mixed_calendar_backtest_annualises_on_the_traded_segment(tmp_path, offline_loader):
    # CRYX trades 7 days from 2014; LATE (business days) starts 2019-06, so the
    # calendar is 7-day then 5-day.  Trading starts only once both streams have
    # history: ppy must be the 5-day segment's (~261), not the whole index's (~305).
    args = ["backtest", "--tickers", "CRYX,LATE", "--allocator", "erc", "--target-vol", "0.20",
            "--max-leverage", "3", "--rf", "0.04", "--cost-bps", "0", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    eq = pd.read_csv(tmp_path / "o" / "equity.csv", parse_dates=[0], index_col=0).iloc[:, 0]
    r = eq.pct_change().dropna()
    obs = len(r) / ((r.index[-1] - r.index[0]).days / 365.25)
    assert bt["config"]["periods_per_year"] == pytest.approx(obs, rel=0.01)
    assert bt["metrics"]["vol"] == pytest.approx(r.std() * math.sqrt(obs), rel=0.01)


def test_hg_m4_scorecard_daily_mixed_calendar_uses_common_rows(offline_loader):
    from holygrail.scorecard import prepare_moments
    raw = {"name": "c", "settings": {"risk_free": A(0.04)},
           "streams": {"CRYX": {"type": "market", "symbol": "CRYX"}, "LATE": {"type": "market", "symbol": "LATE"}},
           "positions": [{"name": "c", "value_usd": 1, "stream": "CRYX"}, {"name": "l", "value_usd": 1, "stream": "LATE"}],
           "totals": {"total_usd": 2}}
    book = book_from_dict(raw)
    m, *_ = prepare_moments(book, book.view("investable"), offline_loader,
                            ScoreSettings(freq="D", window_years=10, estimator="sample"))
    assert m.estimate.periods_per_year == pytest.approx(260.9, rel=0.01)  # business days, not ~300


def test_hg_m4_scorecard_daily_freq_uses_observed_periods(offline_loader):
    from holygrail.scorecard import prepare_moments
    raw = {"name": "c", "settings": {"risk_free": A(0.04)},
           "streams": {"CRYX": {"type": "market", "symbol": "CRYX"}},
           "positions": [{"name": "c", "value_usd": 1, "stream": "CRYX"}], "totals": {"total_usd": 1}}
    book = book_from_dict(raw)
    m, *_ = prepare_moments(book, book.view("investable"), offline_loader,
                            ScoreSettings(freq="D", window_years=2, estimator="sample"))
    assert m.estimate.periods_per_year == pytest.approx(365.25, rel=0.01)


# --------------------------------------------------------------------------- #
# HG-M5: a series sampled more coarsely than the analysis frequency fails loudly
# --------------------------------------------------------------------------- #
def _spy_and_monthly_copy():
    rng = np.random.default_rng(0)
    bd = pd.bdate_range("2019-01-01", "2025-12-31")
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.012, len(bd))), index=bd)
    return spy, spy.resample("BME").last()


def test_hg_m5_month_end_copy_of_a_daily_series_is_refused_at_weekly_freq():
    from holygrail.errors import ValidationError
    from holygrail.estimate import aligned_returns, native_sampling_days
    spy, fund = _spy_and_monthly_copy()
    lv = pd.DataFrame({"SPY": spy, "FUND": fund})
    for freq in ("W", "D"):
        with pytest.raises(ValidationError, match="FUND"):
            aligned_returns(lv, freq)
    M = aligned_returns(lv, "M").dropna()
    assert M.corr().iloc[0, 1] == pytest.approx(1.0)
    gaps = native_sampling_days(lv)
    assert gaps["SPY"] == pytest.approx(1.0) and 28 <= gaps["FUND"] <= 31


def test_hg_m5_provenance_records_native_sampling(tmp_path, offline_loader):
    from holygrail.streams import SeriesStream, Universe
    spy, fund = _spy_and_monthly_copy()
    uni = Universe([SeriesStream(name="FUND", levels=fund, source="statement")])
    _, prov = offline_loader.stream_levels(uni, ["FUND"])
    assert 28 <= prov["FUND"]["native_median_gap_days"] <= 31


# --------------------------------------------------------------------------- #
# HG-M7 / BT-1: benchmark moves on dates the strategy calendar skips are kept
# --------------------------------------------------------------------------- #
def test_bt1_benchmark_total_return_equals_its_level_ratio(tmp_path, offline_loader):
    args = ["backtest", "--tickers", "EQA,BND", "--allocator", "erc", "--benchmark", "CRYX", "--rf", "0.03",
            *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    cry = offline_loader.yahoo("CRYX").values   # trades 7 days; the strategy calendar is business days
    start, end = pd.Timestamp(bt["metrics"]["start"]), pd.Timestamp(bt["metrics"]["end"])
    assert bt["benchmark"]["benchmark"]["total_return"] == pytest.approx(cry[end] / cry[start] - 1, rel=1e-9)


# --------------------------------------------------------------------------- #
# BT-4: a Yahoo price index is labelled price-only even though it has adjclose
# --------------------------------------------------------------------------- #
def _yahoo_payload(sym, closes, adj, instrument=None):
    ts = [int(pd.Timestamp(d, tz="UTC").replace(hour=14, minute=30).timestamp())
          for d in ["2024-01-02", "2024-01-03", "2024-01-04"]]
    meta = {"dataGranularity": "1d", "exchangeTimezoneName": "America/New_York", "symbol": sym}
    if instrument:
        meta["instrumentType"] = instrument
    return {"chart": {"result": [{"meta": meta, "timestamp": ts,
                                  "indicators": {"quote": [{"close": closes}], "adjclose": [{"adjclose": adj}]}}],
                      "error": None}}


def test_bt4_yahoo_index_with_adjclose_is_not_total_return():
    from holygrail.data import parse_yahoo_chart
    _, info = parse_yahoo_chart(_yahoo_payload("^GSPC", [10, 11, 12], [10, 11, 12], "INDEX"), "^GSPC")
    assert info["total_return"] is False and any("price index" in w for w in info["warnings"])
    _, info = parse_yahoo_chart(_yahoo_payload("^VIX", [10, 11, 12], [10, 11, 12]), "^VIX")
    assert info["total_return"] is False
    _, info = parse_yahoo_chart(_yahoo_payload("GLD", [10, 11, 12], [10, 11, 12], "ETF"), "GLD")
    assert info["total_return"] is True  # adjclose == close is fine for a fund with no distributions


# --------------------------------------------------------------------------- #
# BT-5: a declared proxy must actually reach the splice date
# --------------------------------------------------------------------------- #
def test_bt5_splice_refuses_a_proxy_that_stops_before_the_splice():
    from holygrail.data import DataSeries, Provenance, splice_levels
    from holygrail.errors import DataError

    def ds(s, ident):
        return DataSeries(s, Provenance("yahoo", ident, None, "adjclose", True, str(s.index[0].date()),
                                        str(s.index[-1].date()), len(s)))
    idx = pd.bdate_range("2019-01-01", "2020-12-31")
    primary = pd.Series(np.linspace(100, 200, len(idx)), index=idx).loc["2020-06-01":]
    proxy = pd.Series(np.linspace(50, 60, len(idx)), index=idx)
    with pytest.raises(DataError, match="gap"):
        splice_levels(ds(primary, "P"), ds(proxy.loc[:"2020-01-31"], "Q"), "2020-06-01")
    ok = splice_levels(ds(primary, "P"), ds(proxy.loc[:"2020-05-29"], "Q"), "2020-06-01")  # Fri before Mon
    assert ok.values.index[0] == idx[0]


# --------------------------------------------------------------------------- #
# HG-M14: calendar-year completeness is judged by the first period's START
# --------------------------------------------------------------------------- #
def test_hg_m14_month_end_labels_keep_the_first_year():
    from holygrail.metrics import calendar_year_returns, performance_metrics
    mr = pd.Series(0.01, index=pd.date_range("2015-01-31", "2020-12-31", freq="ME"))
    cy = calendar_year_returns(mr)
    assert cy["complete"].all()
    assert performance_metrics(mr, periods_per_year=12)["n_complete_years"] == 6
    late = pd.Series(0.01, index=pd.date_range("2015-02-28", "2020-12-31", freq="ME"))
    assert not calendar_year_returns(late).loc[2015, "complete"]
    daily = pd.Series(0.0, index=pd.bdate_range("2015-03-02", "2016-12-30"))
    assert calendar_year_returns(daily)["complete"].to_dict() == {2015: False, 2016: True}


# --------------------------------------------------------------------------- #
# HG-M8: PCA-entropy ambiguity flag uses sampling error (North et al. 1982)
# --------------------------------------------------------------------------- #
def test_hg_m8_pca_flag_fires_on_estimated_near_degenerate_spectrum():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 0.01, (5000, 8))                 # 8 IID equal-vol streams: true N_eff = 8
    S = np.cov(X.T)
    w = np.full(8, 1 / 8)
    eb = core.effective_bets(w, S, n_obs=5000)
    assert eb.pca_basis_ambiguous
    row = next(r for r in eb.rows() if r["measure"] == "pca_entropy")
    assert row["class"] == "eigenbasis-dependent" and "sampling error" in row["flag"]
    # a well-separated spectrum is not flagged
    Q, _ = np.linalg.qr(rng.normal(size=(4, 4)))
    S2 = Q @ np.diag([0.04, 0.02, 0.01, 0.004]) @ Q.T
    assert not core.effective_bets(np.full(4, 0.25), S2, n_obs=1000).pca_basis_ambiguous


# --------------------------------------------------------------------------- #
# HG-M9: DR-based N_eff is flagged for short books and for N_eff > N
# --------------------------------------------------------------------------- #
def test_hg_m9_dr_flags_shorts_and_neff_above_n():
    S = core.equal_corr_cov(2, 0.2, 0.5)
    eb = core.effective_bets(np.array([1.0, -1.5]), S)
    assert eb.has_short
    dr2_row = next(r for r in eb.rows() if r["measure"] == "dr2")
    assert "short" in dr2_row["flag"]
    S = core.equal_corr_cov(2, 0.2, -0.8)
    eb = core.effective_bets(np.array([0.5, 0.5]), S)
    assert eb.dr2 == pytest.approx(10.0)
    rows = {r["measure"]: r for r in eb.rows()}
    assert "exceeds" in rows["dr2"]["flag"] and "exceeds" in rows["equal_rho"]["flag"]


def test_hg_m9_scorecard_flags_neff_above_stream_count():
    rng = np.random.default_rng(2)
    z = rng.normal(size=(300, 2))
    a = z[:, 0]
    b = -0.8 * a + 0.6 * z[:, 1]
    H = pd.DataFrame({"X": 0.02 * a, "Y": 0.02 * b}, index=pd.date_range("2019-01-04", periods=300, freq="W-FRI"))
    raw = {"name": "n", "settings": {"risk_free": A(0.04)},
           "streams": {"X": {"type": "market", "symbol": "X", "expected_return": A(0.06)},
                       "Y": {"type": "market", "symbol": "Y", "expected_return": A(0.06)}},
           "positions": [{"name": "x", "value_usd": 50, "stream": "X"}, {"name": "y", "value_usd": 50, "stream": "Y"}],
           "totals": {"total_usd": 100}}
    book = book_from_dict(raw)
    v = book.view("investable")
    m = build_moments(book.universe, v.streams, returns=H, periods_per_year=52, rf=0.04, method="sample")
    sc = scorecard(book, v, m, ScoreSettings(), rf_info=RF_INFO)
    assert sc["effective_bets"]["dr2"] > 2
    assert any(f["type"] == "neff_unreliable" for f in sc["flags"])


# --------------------------------------------------------------------------- #
# HG-M11: score --estimator ewma works (with --halflife) and fails clearly without
# --------------------------------------------------------------------------- #
def test_hg_m11_score_ewma(tmp_path, test_book_yaml, offline_loader, capsys):
    base = ["score", "--book", str(test_book_yaml), "--estimator", "ewma", *_common(tmp_path, offline_loader)]
    assert main(base + ["--halflife", "26"]) == 0
    sc = json.loads((tmp_path / "o" / "scorecard.json").read_text())
    assert sc["honesty"]["measurement_basis"]["covariance"]["estimator"] == "ewma"
    assert sc["settings"]["halflife"] == 26
    capsys.readouterr()
    assert main(base) == 2
    assert "--halflife" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# HG-M12: Newton ERC on a perfectly hedged pair raises the engine's own error
# --------------------------------------------------------------------------- #
def test_hg_m12_erc_newton_singular_raises_optimization_error():
    from holygrail.allocate import erc
    from holygrail.errors import OptimizationError
    for S in (np.array([[0.04, -0.04], [-0.04, 0.04]]), np.array([[0.04, -0.06], [-0.06, 0.09]])):  # rho = -1
        for method in ("newton", "ccd"):
            with pytest.raises(OptimizationError):
                erc(S, method=method)


# --------------------------------------------------------------------------- #
# HG-M13: envs Sharpe is an EXCESS-return Sharpe
# --------------------------------------------------------------------------- #
def test_hg_m13_envs_sharpe_uses_rf(tmp_path, offline_loader):
    from argparse import Namespace
    from holygrail.cli import _rf_daily
    from holygrail.environments import RegimeDefinition, monthly_returns, quadrant_table, regimes_from_fred
    from holygrail.streams import MarketStream, Universe
    assert main(["envs", "--tickers", "BND,EQA", "--rf", "0.03", *_common(tmp_path, offline_loader)]) == 0
    got = pd.read_csv(tmp_path / "o" / "environment_heatmap.csv")
    surpr, _ = regimes_from_fred(offline_loader, RegimeDefinition())
    lv, _ = offline_loader.stream_levels(Universe([MarketStream(name=s, symbol=s) for s in ("BND", "EQA")]),
                                         ["BND", "EQA"])
    mret = monthly_returns(lv)
    rf_m, _ = _rf_daily(Namespace(rf="0.03"), None, mret.index)
    assert rf_m.mean() * 12 == pytest.approx(0.03, rel=0.02)
    exp = quadrant_table(mret, surpr["quadrant"], rf_monthly=rf_m)
    np.testing.assert_allclose(got["sharpe"].to_numpy(), exp["sharpe"].to_numpy(), rtol=1e-9)
    raw = quadrant_table(mret, surpr["quadrant"])
    assert np.nanmax(np.abs(got["sharpe"].to_numpy() - raw["sharpe"].to_numpy())) > 0.05


# --------------------------------------------------------------------------- #
# BT-6 / BT-7: book schema holes
# --------------------------------------------------------------------------- #
def _example_raw():
    return {"name": "e", "settings": {"risk_free": A(0.04)},
            "streams": {"SPY": {"type": "market", "symbol": "SPY"}},
            "positions": [{"name": "s", "value_usd": 1060000, "stream": "SPY"}], "totals": {"total_usd": 1060000}}


def test_bt6_totals_without_anything_to_reconcile_fail():
    from holygrail.errors import HolyGrailError
    raw = _example_raw()
    raw["totals"] = {"tolerance_usd": 1.0}
    with pytest.raises(HolyGrailError, match="total_usd"):
        book_from_dict(raw)
    raw["totals"] = {"total_usd": 1060000, "typo_key": 1}
    with pytest.raises(HolyGrailError, match="typo_key"):
        book_from_dict(raw)


@pytest.mark.parametrize("proxies,match", [([{"symbol": "VUSTX"}], "until"), ([{"until": "2002-07-30"}], "symbol"),
                                            ([{"symbol": "VUSTX", "until": "notadate"}], "date"),
                                            ([{"symbol": "VUSTX", "until": "2002-07-30", "bogus": 1}], "bogus"),
                                            ({"symbol": "VUSTX"}, "list")])
def test_bt7_malformed_proxy_spec_is_a_validation_error(proxies, match):
    from holygrail.errors import ValidationError
    raw = _example_raw()
    raw["streams"]["SPY"]["proxies"] = proxies
    with pytest.raises(ValidationError, match=match):
        book_from_dict(raw)


# --------------------------------------------------------------------------- #
# BT-8: data provenance is printed, not only written to JSON
# --------------------------------------------------------------------------- #
def test_bt8_provenance_lines_cover_splices_price_only_cache_age_and_warnings():
    from holygrail.report import provenance_lines
    prov = {"SPY": {"source": "spliced", "identifier": "SPY", "total_return": True, "from_cache": True,
                    "fetched_at": "2026-01-01T00:00:00+00:00", "warnings": ["dropped final bar: session in progress"],
                    "proxies": [{"proxy": "VFINX", "used_before": "1993-01-29"}], "native_median_gap_days": 1.0},
            "^GSPC": {"source": "yahoo", "identifier": "^GSPC", "total_return": False, "from_cache": False,
                      "fetched_at": "2026-10-06T00:00:00+00:00", "warnings": [], "proxies": []},
            "FUND": {"source": "user", "identifier": "FUND", "total_return": None, "warnings": ["source: statement"],
                     "proxies": [], "native_median_gap_days": 30.0}}
    text = "\n".join(provenance_lines(prov, now=pd.Timestamp("2026-10-06", tz="UTC")))
    assert "VFINX" in text and "1993-01-29" in text
    assert "^GSPC" in text and "price-only" in text
    assert "cache" in text and "278 days" in text
    assert "session in progress" in text and "every ~30 days" in text


def test_bt8_cli_and_scorecard_print_provenance(tmp_path, test_book_yaml, offline_loader, capsys):
    args = ["backtest", "--tickers", "EQA,BND", "--rf", "0.03", *_common(tmp_path, offline_loader)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "data provenance" in out and "SYNTHETIC test series" in out and "cache" in out
    assert main(["score", "--book", str(test_book_yaml), *_common(tmp_path, offline_loader)]) == 0
    assert "data provenance" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# BT-9: honest labels -- selection bias always; 'book' is hindsight, not walk-forward
# --------------------------------------------------------------------------- #
def test_bt9_backtest_honesty_labels(tmp_path, offline_loader, capsys):
    p = tmp_path / "cash.yaml"
    p.write_text(CASH_BOOK)
    assert main(["backtest", "--book", str(p), "--allocator", "book", "--rf", "0.03",
                 *_common(tmp_path, offline_loader)]) == 0
    out = capsys.readouterr().out
    assert "hindsight" in out and "walk-forward" not in out and "survivorship" in out
    assert main(["backtest", "--tickers", "EQA,BND", "--rf", "0.03", *_common(tmp_path, offline_loader)]) == 0
    out = capsys.readouterr().out
    assert "walk-forward" in out and "survivorship" in out
    bt = json.loads((tmp_path / "o" / "backtest.json").read_text())
    assert any("survivorship" in n for n in bt["notes"])
