"""Gate tests for the ladder and the alert suppression rules."""
from __future__ import annotations

from app.engine.ladder import (LadderInput, decide_stage, equity_is_moving,
                               is_upgrade, should_alert)
from app.engine.scoring import EquityView

_QUIET = EquityView(price=0.12, change_pct=0.4, volume=5e6, avg_volume=5e6)
_MOVING = EquityView(price=0.50, change_pct=321.0, volume=720e6, avg_volume=5e6)


def test_equity_move_needs_price_AND_volume(cfg):
    """On a sub-$1 name a single tick is several percent, so price alone is
    noise. Both legs are required or the ladder jumps to EQUITY_MOVING — and
    suppresses its own alerts — on nothing."""
    assert equity_is_moving(_MOVING, cfg)
    price_only = EquityView(price=0.15, change_pct=30.0, volume=5e6, avg_volume=5e6)
    assert not equity_is_moving(price_only, cfg)
    vol_only = EquityView(price=0.12, change_pct=1.0, volume=500e6, avg_volume=5e6)
    assert not equity_is_moving(vol_only, cfg)


def test_dark_equity_never_counts_as_moving(cfg):
    assert not equity_is_moving(EquityView(dark=True), cfg)


def test_stages_climb_with_the_evidence(cfg):
    assert decide_stage("TOKENIZED", LadderInput(0, 0.0, _QUIET), cfg) == "TOKENIZED"
    assert decide_stage("TOKENIZED", LadderInput(1, 10.0, _QUIET), cfg) == "PAIRED"
    assert decide_stage("PAIRED", LadderInput(1, 80.0, _QUIET), cfg) == "RAMPING"
    assert decide_stage("PAIRED", LadderInput(4, 80.0, _QUIET), cfg) == "CLUSTER"


def test_equity_moving_wins_over_everything(cfg):
    assert decide_stage("CLUSTER", LadderInput(6, 95.0, _MOVING), cfg) == "EQUITY_MOVING"


def test_hot_stage_does_not_flap_on_one_cool_reading(cfg):
    """Hysteresis: a single quiet tick must not knock a live setup back down."""
    assert decide_stage("RAMPING", LadderInput(2, 30.0, _QUIET), cfg) == "RAMPING"


def test_sustained_cooling_fades(cfg):
    assert decide_stage("RAMPING", LadderInput(2, 5.0, _QUIET), cfg) == "FADED"


def test_alert_fires_only_climbing_onto_a_hot_rung_while_equity_is_quiet(cfg):
    fire, why = should_alert("RAMPING", "PAIRED", 80.0, _QUIET, cfg)
    assert fire and "quiet" in why


def test_alert_suppressed_once_the_equity_is_already_moving(cfg):
    """The single most important suppression: by the time the stock is up 321%
    on 144x volume an alert is an obituary, not a trade."""
    fire, why = should_alert("RAMPING", "PAIRED", 99.0, _MOVING, cfg)
    assert not fire and "window has closed" in why


def test_alert_does_not_repeat_on_the_same_rung(cfg):
    assert not should_alert("RAMPING", "RAMPING", 99.0, _QUIET, cfg)[0]
    assert should_alert("CLUSTER", "RAMPING", 99.0, _QUIET, cfg)[0]


def test_low_score_does_not_alert(cfg):
    assert not should_alert("RAMPING", "PAIRED", 10.0, _QUIET, cfg)[0]


def test_paired_is_not_an_alerting_rung(cfg):
    assert not should_alert("PAIRED", "TOKENIZED", 99.0, _QUIET, cfg)[0]


def test_is_upgrade_ordering():
    assert is_upgrade(None, "TOKENIZED")
    assert is_upgrade("PAIRED", "CLUSTER")
    assert not is_upgrade("CLUSTER", "PAIRED")
    assert is_upgrade("RAMPING", "FADED")
    assert not is_upgrade("FADED", "FADED")


# --- the cold-tokenization rung -------------------------------------------
# On the Farmmi timeline this was the only rung with usable lead (+15.8h to the
# first 5-min bar clearing +12.8%); the meme rungs were +13 min and -1.9h.

_NANOCAP = 82.0     # FAMI scored ~84-88 on live data
_LARGECAP = 8.0     # MU scored ~8


def test_cold_tokenization_alerts_on_a_nanocap_wrapper(cfg):
    fire, why = should_alert("TOKENIZED", None, 78.0, _QUIET, cfg,
                             pumpability=_NANOCAP)
    assert fire and "nanocap" in why


def test_cold_tokenization_ignores_large_caps(cfg):
    """A wrapper appearing for Micron is routine and means nothing. Alerting on
    it would bury the one case that matters under daily noise."""
    fire, _ = should_alert("TOKENIZED", None, 95.0, _QUIET, cfg,
                           pumpability=_LARGECAP)
    assert not fire


def test_cold_tokenization_does_not_repeat_for_a_known_wrapper(cfg):
    assert not should_alert("TOKENIZED", "TOKENIZED", 90.0, _QUIET, cfg,
                            pumpability=_NANOCAP)[0]


def test_cold_tokenization_suppressed_if_the_stock_already_moved(cfg):
    fire, why = should_alert("TOKENIZED", None, 90.0, _MOVING, cfg,
                             pumpability=_NANOCAP)
    assert not fire and "window has closed" in why


def test_cold_score_requires_nanocap_and_says_why(cfg):
    from app.engine.scoring import cold_tokenization_score
    big, reasons = cold_tokenization_score(_LARGECAP, 90.0, "OFFICIAL_ROBINHOOD", cfg)
    assert big == 0.0 and any("not a nanocap" in r for r in reasons)
    small, reasons = cold_tokenization_score(_NANOCAP, 90.0, "UNOFFICIAL", cfg)
    assert small > 55
    assert any("nobody wraps one of these by accident" in r for r in reasons)
