"""Gate tests for the four score axes and the composite."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from app.engine.detect import detect_launch
from app.engine.scoring import (EquityView, alert_score, credibility, earliness,
                                heat, pumpability, pumpability_factors)


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
    assert any("market cap missing" in r for r in reasons)


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
    _, factors, reasons = pumpability_factors(eq, cfg)
    assert any("turned over" in r for r in reasons)
    # Float is now a reported FACTOR, not a prose aside — the breakdown is the
    # deliverable, so the number can be argued with.
    flt = [f for f in factors if f["key"] == "float"]
    assert flt and "31.5M shares" in flt[0]["display"]


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


# --- aliveness: posted liquidity vs traded liquidity -----------------------

def test_seeded_but_dead_pool_gets_no_credibility(cfg, universe, markers, base_assets):
    """REAL payload, 2026-09-02: tokens named "Micron Technology Inc. Common
    Stock" and "Dell Technologies Inc." on Ethereum posting $852M and $302M of
    liquidity against WETH — each with ONE trade and $0.01 of 24h volume.

    Displayed liquidity is a number anyone can manufacture. Scored on depth
    alone these reached ~55 and cleared the credibility gate; nothing that
    nobody trades may do that."""
    from app.engine.detect import LaunchView
    from app.engine.registry import EquityTokenView
    from tests.conftest import load

    for pair in load("dead_liquidity_pools.json"):
        liq = pair["liquidity"]["usd"]
        assert liq > 1e8, "fixture should be a huge posted-liquidity pool"
        assert pair["txns"]["h24"]["buys"] + pair["txns"]["h24"]["sells"] <= 2
        launch = LaunchView(
            chain_id=pair["chainId"], pair_address=pair["pairAddress"],
            dex_id=pair["dexId"], url=pair["url"],
            equity=EquityTokenView(chain_id=pair["chainId"], address="0x0",
                                   symbol=pair["baseToken"]["symbol"], token_name="",
                                   ticker="MU", company="", issuer_class="UNOFFICIAL",
                                   issuer=""),
            meme_address="0x1", meme_symbol="FAKE", meme_name="Fake",
            pair_created_at=None, liquidity_usd=liq, fdv=pair.get("fdv", 0.0),
            volume_h24=pair["volume"]["h24"], volume_h6=0.0, volume_h1=0.0,
            volume_m5=0.0, buys_h1=0, sells_h1=0,
            buys_h24=pair["txns"]["h24"]["buys"],
            sells_h24=pair["txns"]["h24"]["sells"],
            price_change_h1=0.0, price_change_h24=0.0)
        score, reasons = credibility(launch, cfg)
        assert score < cfg["alert"]["gates"]["min_credibility"], (
            f"a pool with {launch.buys_h24 + launch.sells_h24} trades scored {score}")
        assert any("not being traded" in r for r in reasons)


def test_aliveness_does_not_punish_a_genuinely_busy_pool(fami_pairs, universe,
                                                         markers, base_assets, cfg):
    """JINQIAN did ~95k trades in 24h — the guard must not touch it."""
    launch = _jinqian(fami_pairs, universe, markers, base_assets)
    score, reasons = credibility(launch, cfg)
    assert score > 55
    assert not any("barely alive" in r or "not being traded" in r for r in reasons)


# --- pumpability as a multi-factor, inspectable score ----------------------
# Real 2-year stats measured 2026-09-02.

_WHLR = dict(price=0.5254, dollar_volume=108_146, max_1d_gain_pct=97.8,
             days_over_30=2, daily_vol_pct=11.5, float_shares=21_783,
             market_cap=14_000_000, high_52w=9.0, low_52w=0.5, change_pct=0.0)
_NTIC = dict(price=7.90, dollar_volume=17_779, max_1d_gain_pct=9.9,
             days_over_30=0, daily_vol_pct=1.6, float_shares=8_000_000,
             market_cap=72_000_000, high_52w=14.0, low_52w=7.0, change_pct=0.0)
_MU = dict(price=956.08, dollar_volume=26_626_714_226, max_1d_gain_pct=19.3,
           days_over_30=0, daily_vol_pct=6.1, float_shares=1_124_600_000,
           market_cap=1_079_787_000_000, high_52w=1000.0, low_52w=300.0,
           change_pct=0.0)


def test_illiquid_but_dead_is_not_pumpable(cfg):
    """NTIC is the control: the SMALLEST dollar volume of the set, and it has
    never moved. Cheap and illiquid must not read as pumpable — a name also has
    to be capable of moving."""
    whlr, _, _ = pumpability_factors(EquityView(**_WHLR), cfg)
    ntic, factors, reasons = pumpability_factors(EquityView(**_NTIC), cfg)
    assert whlr > ntic + 20
    assert any("does not move" in r for r in reasons)
    cap = [f for f in factors if f["key"] == "capable"][0]
    assert cap["score"] < 10


def test_dollar_volume_separates_where_share_count_does_not(cfg):
    """MU's share volume is only ~4x FAMI's; its DOLLAR volume is 5 orders
    larger. Cost-to-move has to carry that."""
    mu, factors, _ = pumpability_factors(EquityView(**_MU), cfg)
    cost = [f for f in factors if f["key"] == "cost"][0]
    assert cost["score"] == 0.0
    assert mu < 25


def test_prior_squeeze_history_counts(cfg):
    """Names that have squeezed tend to squeeze again. WHLR has printed +97.8%
    in a session and two days over +30%."""
    _, factors, reasons = pumpability_factors(EquityView(**_WHLR), cfg)
    sq = [f for f in factors if f["key"] == "squeeze"][0]
    assert sq["score"] > 90
    assert any("+98% in a session" in r for r in reasons)


def test_factors_are_reported_and_ranked_by_contribution(cfg):
    """The breakdown IS the deliverable — a score you cannot interrogate is
    not analysis."""
    score, factors, _ = pumpability_factors(EquityView(**_WHLR), cfg)
    assert len(factors) == 6
    contribs = [f["contribution"] for f in factors]
    assert contribs == sorted(contribs, reverse=True)
    assert sum(contribs) == pytest.approx(score, abs=1.0)
    for f in factors:
        assert f["display"] and f["label"]


def test_missing_inputs_renormalise_rather_than_score_as_bad(cfg):
    """A dark lane must lower CONFIDENCE, not silently mark the name down."""
    full = EquityView(**_WHLR)
    partial = EquityView(price=_WHLR["price"], dollar_volume=_WHLR["dollar_volume"],
                         daily_vol_pct=_WHLR["daily_vol_pct"],
                         max_1d_gain_pct=_WHLR["max_1d_gain_pct"],
                         days_over_30=_WHLR["days_over_30"])
    a, fa, _ = pumpability_factors(full, cfg)
    b, fb, rb = pumpability_factors(partial, cfg)
    assert len(fb) == 4 and len(fa) == 6
    assert any("scored on 4 of 6" in r for r in rb)
    assert abs(a - b) < 30, "dropping float/mcap must not collapse the score"


def test_zero_market_cap_is_a_gap_not_a_tiny_company(cfg):
    """FMP reports marketCap 0 for WHLR. Read as "tiny" that handed it a free
    100/100 on size; it has to drop out of the score instead."""
    eq = EquityView(**{**_WHLR, "market_cap": 0})
    score, factors, reasons = pumpability_factors(eq, cfg)
    assert not [f for f in factors if f["key"] == "size"]
    assert any("market cap missing" in r for r in reasons)


def test_sub_million_counts_do_not_render_as_zero(cfg):
    """WHLR's float is 21,783 shares — the most interesting thing about it, and
    "0.0M shares" hides it."""
    _, factors, _ = pumpability_factors(EquityView(**_WHLR), cfg)
    flt = [f for f in factors if f["key"] == "float"][0]
    assert flt["display"] == "21,783 shares"


def test_implausible_market_cap_is_dropped_not_rewarded(cfg):
    """FMP reports a $13,605 cap for WHLR, a NASDAQ-listed REIT — stale share
    data after reverse splits, not a $13k company. Nasdaq's continued-listing
    standards make that impossible, so it must not score as maximally small."""
    eq = EquityView(**{**_WHLR, "market_cap": 13_605})
    score, factors, reasons = pumpability_factors(eq, cfg)
    assert not [f for f in factors if f["key"] == "size"]
    assert any("implausible" in r for r in reasons)
    real = EquityView(**{**_WHLR, "market_cap": 14_000_000})
    assert pumpability_factors(real, cfg)[0] >= score - 5
