"""Tiingo news lane gates: no-key graceful, velocity math, keyword themes,
token redaction, and the honesty contract (descriptive-only note served)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.sources import tiingo_news as tn

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _art(hours_ago, title="Fed set to cut rates", desc=""):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"id": 1, "ts": ts, "title": title, "source": "x", "url": "u",
            "tickers": [], "tags": [], "description": desc}


def test_gate_no_key_graceful(monkeypatch):
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    tn._CACHE.clear()
    out = tn.news_pulse(now=NOW)
    assert out == {"available": False, "note": "TIINGO_API_KEY unset on this service"}


def test_gate_velocity_math():
    # 30 days of 2/day baseline, then a 10-article burst in the last 24h
    arts = [_art(24 * d + h) for d in range(2, 32) for h in (1, 2)]
    arts = [_art(h) for h in range(1, 11)] + arts
    p = tn.theme_pulse(arts, (), NOW)
    assert p["n_24h"] == 10
    assert 1.8 <= p["baseline_per_day"] <= 2.2
    assert p["velocity_z"] > 4          # burst detected
    assert len(p["latest"]) == 5
    # quiet day: velocity near/below zero
    q = tn.theme_pulse(arts[10:], (), NOW)
    assert q["n_24h"] == 0 and q["velocity_z"] <= 0


def test_gate_partial_day_not_in_baseline():
    arts = [_art(1)] * 50                     # huge burst TODAY only
    p = tn.theme_pulse(arts, (), NOW)
    assert p["baseline_per_day"] == 0.0       # today's burst never self-baselines
    assert p["velocity_z"] > 10


def test_gate_keyword_filter():
    arts = [_art(2, "Powell signals FOMC pause"),
            _art(3, "Team wins championship", "sports")]
    p = tn.theme_pulse(arts, ("fomc", "powell"), NOW)
    assert p["n_24h"] == 1


def test_gate_token_redaction():
    msg = tn._redact("boom https://api.tiingo.com/tiingo/news?token=SECRET123abc&x=1")
    assert "SECRET123abc" not in msg and "token=<redacted>" in msg


def test_gate_honesty_note_served(monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "k")
    tn._CACHE.clear()
    monkeypatch.setattr(tn, "fetch_articles", lambda t, s, limit=1000: [])
    out = tn.news_pulse(now=NOW)
    assert out["available"] is True
    assert "DESCRIPTIVE" in out["note"] and "no backtested signal" in out["note"]
    assert set(out["themes"]) == set(tn.THEMES)
    tn._CACHE.clear()
