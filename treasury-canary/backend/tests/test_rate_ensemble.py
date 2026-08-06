"""Rate-ensemble gates: bucket parsing, weight math, blend normalization,
degradation. All offline."""
from app.sources.rate_markets import (BACKTEST, BUCKETS, blend, brier,
                                      _bucket_kalshi, _bucket_pm, _norm,
                                      source_weights)


def test_gate_bucket_parsers():
    assert _bucket_pm("Fed decreases interest rates by 50+ bps after X?") == "cut50p"
    assert _bucket_pm("Fed decreases interest rates by 25 bps after X?") == "cut25"
    assert _bucket_pm("No change in Fed interest rates after X?") == "hold"
    assert _bucket_pm("Fed increases interest rates by 25+ bps after X?") == "hike25p"
    assert _bucket_pm("Will CPI exceed 3%?") is None
    # 2026+ phrasing
    assert _bucket_pm("Will the Fed decrease interest rates by 50+ bps after the September 2026 meeting?") == "cut50p"
    assert _bucket_pm("Will the Fed decrease interest rates by 25 bps after the September 2026 meeting?") == "cut25"
    assert _bucket_pm("Will there be no change in Fed interest rates after the September 2026 meeting?") == "hold"
    assert _bucket_pm("Will the Fed increase interest rates by 25 bps after the September 2026 meeting?") == "hike25p"
    assert _bucket_pm("Will the Fed increase interest rates by 50+ bps after the September 2026 meeting?") == "hike25p"
    assert _bucket_kalshi({"Cut": ">25"}) == "cut50p"
    assert _bucket_kalshi({"Cut": "25"}) == "cut25"
    assert _bucket_kalshi({"Hike": "0"}) == "hold"
    assert _bucket_kalshi({"Hike": "25"}) == "hike25p"
    assert _bucket_kalshi({"Hike": ">25"}) == "hike25p"
    assert _bucket_kalshi(None) is None


def test_gate_weights_earned_from_accuracy():
    w = source_weights()
    # backtest: PM brier 0.011 (n=7) beats Kalshi 0.060 (n=2) -> PM majority,
    # but shrinkage keeps Kalshi meaningfully represented
    assert w["polymarket"]["weight"] > w["kalshi"]["weight"]
    assert 0.60 < w["polymarket"]["weight"] < 0.90
    assert abs(sum(v["weight"] for v in w.values()) - 1.0) < 0.01
    assert w["polymarket"]["n"] == BACKTEST["polymarket"]["n"]
    # new scored meetings shift the weights: feed Kalshi perfect scores
    w2 = source_weights({"kalshi": [0.001] * 10})
    assert w2["kalshi"]["weight"] > w["kalshi"]["weight"]


def test_gate_blend_and_norm():
    w = source_weights()
    per = {"polymarket": {"hold": 0.9, "cut25": 0.1},
           "kalshi": {"hold": 0.7, "cut25": 0.3}}
    b = blend(per, w)
    assert abs(sum(b.values()) - 1.0) < 0.01
    assert 0.7 < b["hold"] < 0.9              # between the sources, PM-tilted
    assert b["hold"] > 0.8                    # PM carries ~3/4 of the weight
    # one dead source -> blend equals the live one
    b2 = blend({"polymarket": {}, "kalshi": {"hold": 0.7, "cut25": 0.3}}, w)
    assert abs(b2["hold"] - 0.7) < 0.01
    # both dead -> empty, never a fake number
    assert blend({"polymarket": {}, "kalshi": {}}, w) == {}


def test_gate_brier_and_norm_guards():
    assert brier({"hold": 1.0}, "hold") == 0.0
    assert brier({"hold": 1.0}, "cut25") == 2.0          # max miss
    perfect = brier({"hold": 0.97, "cut25": 0.03}, "hold")
    poor = brier({"hold": 0.6, "cut25": 0.4}, "hold")
    assert perfect < poor
    assert _norm({"hold": 0.5}) == {}                     # <3 buckets -> reject
    assert _norm({"hold": 0.0, "cut25": 0.0, "cut50p": 0.0}) == {}
    n = _norm({"hold": 2.0, "cut25": 1.0, "cut50p": 1.0})
    assert abs(sum(n.values()) - 1.0) < 1e-6


def test_gate_shift_detection():
    from app.sources.rate_markets import detect_shifts
    prev = {"date": "2026-09-16",
            "blend": {"cut50p": 0.01, "cut25": 0.01, "hold": 0.52, "hike25p": 0.45}}
    # quiet drift (<10pp): no events
    cur = {"date": "2026-09-16",
           "blend": {"cut50p": 0.01, "cut25": 0.02, "hold": 0.48, "hike25p": 0.49}}
    assert detect_shifts(prev, cur) == []
    # 15pp hold->hike swing: WARN on both buckets
    cur2 = {"date": "2026-09-16",
            "blend": {"cut50p": 0.01, "cut25": 0.01, "hold": 0.37, "hike25p": 0.60}}
    evs = detect_shifts(prev, cur2)
    assert {e["bucket"] for e in evs} == {"hold", "hike25p"}
    assert all(e["severity"] == "WARN" for e in evs)
    # 25pp move: RED
    cur3 = {"date": "2026-09-16",
            "blend": {"cut50p": 0.01, "cut25": 0.01, "hold": 0.27, "hike25p": 0.70}}
    assert any(e["severity"] == "RED" for e in detect_shifts(prev, cur3))
    # meeting rolled over (new front meeting): baseline resets, no false alarm
    cur4 = {"date": "2026-10-28",
            "blend": {"cut50p": 0.02, "cut25": 0.05, "hold": 0.68, "hike25p": 0.25}}
    assert detect_shifts(prev, cur4) == []
    # cold start: nothing to compare
    assert detect_shifts(None, cur2) == []


def test_gate_telegram_policy(monkeypatch):
    from app import alerts
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert not alerts.should_send("CRITICAL")          # unset env -> never
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    assert alerts.should_send("WARN")                  # default floor WARN
    assert alerts.should_send("RED")
    assert not alerts.should_send("INFO")
    monkeypatch.setenv("TELEGRAM_MIN_SEVERITY", "RED")
    assert not alerts.should_send("WARN")
    assert "🔴" in alerts.format_event("band_cross", "RED", "x")


def test_gate_buckets_stable():
    # frontend contract: exactly these four, in this order
    assert BUCKETS == ["cut50p", "cut25", "hold", "hike25p"]
