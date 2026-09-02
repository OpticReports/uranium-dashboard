"""Gate tests for the four score axes and the composite."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from app.engine.detect import detect_launch
from app.engine.scoring import (EquityView, alert_score, credibility, earliness,
                                heat, pumpability)


def _jinqian(fami_pairs, universe, markers, base_assets):
    for p in fami_pairs:
        if p["baseToken"]["symbol"] == "JINQIAN":
            return detect_launch(p, universe, markers, base_assets)
    raise AssertionError("JINQIAN fixture missing")


def test_deep_two_sided_pool_is_credible(fami_pairs, universe, markers,
                                         base_assets, cfg):
    """The real JINQIAN/FAMI pool: $4.4M liquidity, ~95k trades, both ways."""
    score, _ = credibility(_jinqian(fami_pairs, universe, markers, base_assets), cfg)
    assert score > 55


def test_empty_pool_is_not_credible(fami_pairs, universe, markers, base_assets, cfg):
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    launch.liquidity_usd = 0.0
    launch.buys_h24 = launch.sells_h24 = 0
    score, reasons = credibility(launch, cfg)
    assert score < 20
    assert any("thin pool" in r for r in reasons)


def test_credibility_penalises_liquidity_that_is_a_sliver_of_fdv(cfg, fami_pairs,
                                                                 universe, markers,
                                                                 base_assets):
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    launch.liquidity_usd, launch.fdv = 4_000.0, 60_000_000.0
    _, reasons = credibility(launch, cfg)
    assert any("FDV" in r for r in reasons)


def test_heat_reads_acceleration_not_level(fami_pairs, universe, markers,
                                           base_assets, cfg):
    """A pair that printed $93M over the day but only $1.9M in the last hour is
    COOLING, and must not outrank one going the other way on the same totals."""
    cooling = _jinqian(fami_pairs, universe, markers, base_assets)
    hot = _jinqian(fami_pairs, universe, markers, base_assets)
    hot.volume_h1 = cooling.volume_h24 / 3.0
    hot.volume_m5 = hot.volume_h1 / 4.0
    hot.price_change_h1 = 40.0
    assert heat(hot, cfg)[0] > heat(cooling, cfg)[0]
    assert any("cooling" in r for r in heat(cooling, cfg)[1])


def test_pumpability_prefers_the_cheap_thin_beaten_name(cfg):
    fami = EquityView(price=0.1187, avg_volume=5_000_000, volume=5_000_000,
                      high_52w=2.05, low_52w=0.0919, change_pct=0.0)
    mega = EquityView(price=180.0, avg_volume=40_000_000, volume=40_000_000,
                      high_52w=200.0, low_52w=90.0, change_pct=0.0)
    assert pumpability(fami, cfg)[0] > 70
    assert pumpability(mega, cfg)[0] < 30


def test_pumpability_discloses_the_missing_market_cap(cfg):
    _, reasons = pumpability(EquityView(price=0.11, avg_volume=5e6), cfg)
    assert any("market cap dark" in r for r in reasons)


def test_earliness_collapses_once_the_equity_has_run(cfg):
    now = datetime(2026, 9, 2, 18, 0)
    quiet = EquityView(price=0.12, change_pct=0.5, volume=5e6, avg_volume=5e6)
    spent = EquityView(price=0.50, change_pct=321.0, volume=720e6, avg_volume=5e6)
    assert earliness(quiet, now - timedelta(hours=2), now, cfg)[0] > 70
    assert earliness(spent, now - timedelta(hours=2), now, cfg)[0] < 20


def test_alert_score_is_zero_once_the_move_is_spent(cfg):
    """Earliness MULTIPLIES: a perfect setup that has already run is worth
    nothing, not 'still pretty good'."""
    spent, _ = alert_score(90, 90, 90, 0.0, "OFFICIAL_ROBINHOOD", 6, cfg)
    early, _ = alert_score(90, 90, 90, 100.0, "OFFICIAL_ROBINHOOD", 6, cfg)
    assert spent == 0.0
    assert early > 80


def test_alert_score_gates_on_credibility_and_pumpability(cfg):
    junk, reasons = alert_score(5, 99, 99, 99, "UNOFFICIAL", 1, cfg)
    assert junk == 0.0 and any("gated" in r for r in reasons)
    big, reasons = alert_score(99, 99, 5, 99, "UNOFFICIAL", 1, cfg)
    assert big == 0.0 and any("gated" in r for r in reasons)


def test_official_wrapper_outscores_unofficial_all_else_equal(cfg):
    off, off_r = alert_score(70, 70, 70, 80, "OFFICIAL_ROBINHOOD", 1, cfg)
    unoff, unoff_r = alert_score(70, 70, 70, 80, "UNOFFICIAL", 1, cfg)
    assert off > unoff
    assert any("mint/redeem" in r for r in off_r)
    assert any("attention-only" in r for r in unoff_r)


def test_cluster_adds_and_is_capped(cfg):
    one, _ = alert_score(70, 70, 70, 80, "UNOFFICIAL", 1, cfg)
    six, r = alert_score(70, 70, 70, 80, "UNOFFICIAL", 6, cfg)
    huge, _ = alert_score(70, 70, 70, 80, "UNOFFICIAL", 50, cfg)
    assert six > one
    assert huge == six          # capped, so a spam wave cannot run the score up
    assert any("cascade" in x for x in r)


# --- float: "can this stock actually pump?" --------------------------------

def test_small_float_outscores_large_float_all_else_equal(cfg):
    """Float is the most direct read on whether meme flow can move the tape."""
    tight = EquityView(price=0.12, avg_volume=2_500_000, volume=800_000_000,
                       high_52w=2.05, low_52w=0.09, change_pct=0.0,
                       market_cap=5_780_000, float_shares=31_513_560)
    loose = EquityView(price=0.12, avg_volume=2_500_000, volume=800_000_000,
                       high_52w=2.05, low_52w=0.09, change_pct=0.0,
                       market_cap=5_780_000, float_shares=450_000_000)
    assert pumpability(tight, cfg)[0] > pumpability(loose, cfg)[0]


def test_float_turnover_is_computed_and_surfaced(cfg):
    """FAMI: 31.5M float, 837M traded — the float turned over ~26 times."""
    eq = EquityView(price=0.15, volume=837_515_708, avg_volume=2_454_838,
                    float_shares=31_513_560, change_pct=27.0,
                    high_52w=2.05, low_52w=0.09)
    assert eq.float_turnover == pytest.approx(26.58, abs=0.1)
    _, reasons = pumpability(eq, cfg)
    assert any("turned over" in r for r in reasons)
    assert any("free float" in r for r in reasons)


def test_missing_float_is_disclosed_not_guessed(cfg):
    _, reasons = pumpability(EquityView(price=0.12, avg_volume=3e6), cfg)
    assert any("float dark" in r for r in reasons)


def test_float_turnover_is_none_without_the_inputs():
    assert EquityView(price=1.0).float_turnover is None
    assert EquityView(price=1.0, volume=1e6, float_shares=0).float_turnover is None


# --- liquidity trajectory: "is this a credible pair?" ----------------------

def test_draining_liquidity_slashes_credibility(fami_pairs, universe, markers,
                                                base_assets, cfg):
    """One reading cannot tell a pool being built from one being drained. The
    change between readings can, and LP walking out has to cost the score."""
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    flat, _ = credibility(launch, cfg, liquidity_trend_pct=0.0)
    drained, reasons = credibility(launch, cfg, liquidity_trend_pct=-75.0)
    assert drained < flat * 0.6
    assert any("LP is leaving" in r for r in reasons)


def test_building_liquidity_is_noted(fami_pairs, universe, markers, base_assets, cfg):
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    _, reasons = credibility(launch, cfg, liquidity_trend_pct=60.0)
    assert any("depth is being added" in r for r in reasons)


def test_no_trend_reading_leaves_credibility_untouched(fami_pairs, universe,
                                                       markers, base_assets, cfg):
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    assert credibility(launch, cfg)[0] == credibility(launch, cfg, None)[0]
