"""Gate tests for the Telegram push.

The severity mapping is the load-bearing part and it is deliberately NOT the
intuitive one: it ranks rungs by how much runway they leave, so the noisy
CLUSTER rung (which arrived 1.9h AFTER the tape moved) sits below the quiet
TOKENIZED rung (which led by 15.8h).
"""
from __future__ import annotations

import pytest

from app import alerts


@pytest.fixture
def telegram_on(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.delenv("TELEGRAM_MIN_SEVERITY", raising=False)


ALERT = {
    "ticker": "FAMI", "company": "Farmmi, Inc.", "stage": "TOKENIZED",
    "score": 78.0, "why": "cold tokenization of a nanocap, score 78",
    "meme": "", "url": "", "issuer_class": "UNOFFICIAL",
    "equity_price": 0.1187, "equity_change_pct": -3.5, "equity_rvol": 1.0,
    "float_shares": 31_513_560, "float_turnover": 26.6,
    "reasons": ["wrapper exists for a nanocap with no meme on it yet"],
    "pools": [{"symbol": "JINQIAN", "url": "https://dexscreener.com/robinhood/0xabc",
               "liquidity_usd": 4_433_180, "volume_h24": 93_673_775,
               "trend": "liq +12% since first seen"}],
}


def test_severity_ranks_by_runway_not_by_drama():
    assert alerts.STAGE_SEVERITY["RAMPING"] == "CRITICAL"   # 13-minute window
    assert alerts.STAGE_SEVERITY["TOKENIZED"] == "RED"      # ~15.8h of lead
    assert alerts.STAGE_SEVERITY["CLUSTER"] == "WARN"       # arrived 1.9h late
    assert "EQUITY_MOVING" not in alerts.STAGE_SEVERITY     # never alerts


def test_unconfigured_is_a_silent_no_op(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert alerts.configured() is False
    assert alerts.should_send("CRITICAL") is False
    assert alerts.push(ALERT) is False


def test_min_severity_can_mute_the_lagging_rung(telegram_on, monkeypatch):
    """RED drops CLUSTER notices and keeps the two actionable rungs."""
    monkeypatch.setenv("TELEGRAM_MIN_SEVERITY", "RED")
    assert alerts.should_send("CRITICAL") is True
    assert alerts.should_send("RED") is True
    assert alerts.should_send("WARN") is False


def test_default_severity_lets_everything_through(telegram_on):
    for sev in ("WARN", "RED", "CRITICAL"):
        assert alerts.should_send(sev) is True


def test_message_carries_the_pool_links(telegram_on):
    """A ticker with no way to look at the pool is not an actionable alert."""
    text = alerts.format_alert(ALERT)
    assert "JINQIAN" in text
    assert "https://dexscreener.com/robinhood/0xabc" in text
    assert "$4.4M" in text          # liquidity, humanised
    assert "liq +12% since first seen" in text


def test_message_carries_float_and_turnover(telegram_on):
    text = alerts.format_alert(ALERT)
    assert "31.5M sh" in text
    assert "26.6x turned over today" in text


def test_message_is_explicit_when_there_are_no_pools_yet(telegram_on):
    text = alerts.format_alert({**ALERT, "pools": []})
    assert "nothing built on it" in text


def test_message_survives_a_dark_equity_lane(telegram_on):
    """A dark quote lane must not produce a crash or a fake price."""
    text = alerts.format_alert({**ALERT, "equity_price": None,
                                "equity_change_pct": None, "equity_rvol": None,
                                "float_shares": None, "float_turnover": None})
    assert "tape: ?" in text


def test_push_sends_when_configured(telegram_on, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send", lambda text: sent.append(text))
    assert alerts.push(ALERT) is True
    assert sent and "FAMI" in sent[0]
