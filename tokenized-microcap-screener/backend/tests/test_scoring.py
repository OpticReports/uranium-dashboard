"""Gate tests for the four score axes and the composite."""
from __future__ import annotations

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
