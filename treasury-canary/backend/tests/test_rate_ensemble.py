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
    # backtest: PM brier 0.011 (n=7) beats Kalshi 0.060 (n=2) and the
    # no-history futures prior -> PM plurality, others meaningfully present
    assert w["polymarket"]["weight"] > w["kalshi"]["weight"]
    assert w["polymarket"]["weight"] > w["futures"]["weight"]
    assert 0.45 < w["polymarket"]["weight"] < 0.90
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


def test_gate_futures_implied_math():
    from app.sources.fed_futures import implied_probs
    # Sep 16 2026 meeting, 30-day month. Anchor Aug (meeting-free) at 96.40
    # -> r_start 3.60. Sep contract 96.325 -> r_month 3.675:
    # 3.675 = (16/30)*3.60 + (14/30)*r_end -> r_end 3.7607 -> delta +0.161
    # -> steps +0.643 -> P(hold)=0.357, P(hike25p)=0.643
    prices = {(2026, 8): 96.40, (2026, 9): 96.325}
    out = implied_probs(["2026-09-16"], prices=prices)
    p = out["2026-09-16"]
    assert abs(p["hike25p"] - 0.643) < 0.01
    assert abs(p["hold"] - 0.357) < 0.01
    assert p["cut25"] == 0 and p["cut50p"] == 0
    # a cut-priced curve maps to the cut buckets
    prices2 = {(2026, 8): 96.40, (2026, 9): 96.47}   # r_month 3.53 < r_start
    p2 = implied_probs(["2026-09-16"], prices=prices2)["2026-09-16"]
    assert p2["cut25"] > 0.5 and p2["hike25p"] == 0
    # chaining: Oct meeting anchors off Sep's implied r_end, not raw Sep avg
    prices3 = {(2026, 8): 96.40, (2026, 9): 96.325, (2026, 10): 96.20}
    out3 = implied_probs(["2026-09-16", "2026-10-28"], prices=prices3)
    assert "2026-10-28" in out3
    assert abs(sum(out3["2026-10-28"].values()) - 1.0) < 0.01
    # missing contract -> meeting skipped, no fake numbers
    assert implied_probs(["2026-09-16"], prices={(2026, 9): 96.3}) == {}


def test_gate_futures_prior_weight():
    w = source_weights()
    assert "futures" in w
    assert w["futures"]["n"] == 0 and w["futures"]["brier"] is None
    # no history -> pure prior: weight must sit below both scored sources'
    # combined... specifically below polymarket, and > 0
    assert 0 < w["futures"]["weight"] < w["polymarket"]["weight"]
    assert abs(sum(v["weight"] for v in w.values()) - 1.0) < 0.01


def test_gate_buckets_stable():
    # frontend contract: exactly these four, in this order
    assert BUCKETS == ["cut50p", "cut25", "hold", "hike25p"]


# --- futures-column regression gates (2026-09-16) -----------------------------
# The panel showed "2/3 sources" on the two NEAREST meetings: the prior
# meeting-free month's ZQ contract had expired and stopped quoting, which left
# the first meeting with no r_start, and the broken chain then took out the
# second one too. These gates encode the anchor ladder and the late-month rule.

_QUOTES = {(2026, 9): 96.265, (2026, 10): 96.125, (2026, 11): 96.03,
           (2026, 12): 95.91, (2027, 1): 95.85, (2027, 2): 95.78}
_MEETINGS = ["2026-09-16", "2026-10-28", "2026-12-09", "2027-01-27"]


def test_gate_expired_prior_contract_does_not_blank_the_near_meetings():
    from app.sources.fed_futures import implied_probs
    # August 2026 has settled and no longer quotes -> without a spot anchor
    # BOTH nearest meetings drop out, each with a stated reason
    notes: dict = {}
    bare = implied_probs(_MEETINGS, prices=_QUOTES, notes=notes)
    assert "2026-09-16" not in bare and "2026-10-28" not in bare
    assert "anchor" in notes["2026-09-16"] and "anchor" in notes["2026-10-28"]
    # spot EFFR restores them: ZQ settles on the average of exactly this rate
    notes2: dict = {}
    out = implied_probs(_MEETINGS, prices=_QUOTES, effr=3.63, notes=notes2)
    assert set(out) == set(_MEETINGS), "every meeting must price"
    for d in _MEETINGS:
        assert abs(sum(out[d].values()) - 1.0) < 1e-6
    # Sep 16, 30-day month: 3.735 = (16/30)*3.63 + (14/30)*r_end -> r_end 3.855
    # -> delta +0.225 -> 0.900 steps -> hold 0.100 / hike 0.900
    assert abs(out["2026-09-16"]["hike25p"] - 0.900) < 0.005
    assert abs(out["2026-09-16"]["hold"] - 0.100) < 0.005
    assert notes2["_anchor:2026-09-16"].startswith("r_start anchored on spot EFFR")
    # the anchor note is for the FIRST meeting only
    assert not any(k.startswith("_anchor:") and k != "_anchor:2026-09-16"
                   for k in notes2)


def test_gate_effr_anchors_only_the_first_meeting():
    from app.sources.fed_futures import implied_probs
    # the first meeting's own month has no contract, so it cannot price; the
    # second must NOT then borrow spot EFFR — a decision sits in between
    q = {k: v for k, v in _QUOTES.items() if k != (2026, 9)}
    notes: dict = {}
    out = implied_probs(_MEETINGS, prices=q, effr=3.63, notes=notes)
    assert "2026-09-16" not in out and "2026-10-28" not in out
    assert "no ZQ contract quoted for 2026-09" in notes["2026-09-16"]
    assert "2026-12-09" in out          # re-anchors on meeting-free November


def test_gate_late_month_meeting_uses_the_next_contract():
    from app.sources.fed_futures import implied_probs, NEXT_MONTH_PREF
    # Oct 28 of a 31-day month leaves post_frac 0.097: solving the month
    # average would amplify quote error ~10x, so r_end must come from the
    # meeting-free November contract instead (96.03 -> 3.97)
    assert 3 / 31 < NEXT_MONTH_PREF
    out = implied_probs(_MEETINGS, prices=_QUOTES, effr=3.63)
    # r_start = Sep's implied r_end 3.8551, r_end = 3.97 -> delta 0.1149
    # -> 0.4596 steps -> hold 0.540 / hike 0.460
    assert abs(out["2026-10-28"]["hike25p"] - 0.460) < 0.01
    # perturbing ONLY the October contract must barely move the answer; under
    # the month-average solve the same perturbation moves it ~10x as far
    q2 = {**_QUOTES, (2026, 10): 96.125 - 0.02}
    out2 = implied_probs(_MEETINGS, prices=q2, effr=3.63)
    assert abs(out2["2026-10-28"]["hike25p"] - out["2026-10-28"]["hike25p"]) < 1e-9


def test_gate_next_month_anchor_refuses_a_meeting_month():
    from app.sources.fed_futures import implied_probs, _meeting_month
    # December 2026 holds a meeting, so a late-November meeting could not read
    # r_end off it; and a month outside the verified table is never "free"
    assert _meeting_month(2026, 12, set()) is True
    assert _meeting_month(2026, 11, set()) is False
    assert _meeting_month(2029, 5, set()) is None
    assert _meeting_month(2026, 11, {(2026, 11)}) is True    # caller-supplied
    # a late-month meeting whose next month is a meeting month falls back to
    # the month-average solve rather than borrowing a blended contract
    out = implied_probs(["2026-11-25"], prices={(2026, 10): 96.125,
                                                (2026, 11): 96.03}, effr=3.63)
    assert out and abs(sum(out["2026-11-25"].values()) - 1.0) < 1e-6


def test_gate_injected_prices_never_hit_the_network():
    import app.sources.fed_futures as ff
    calls = []
    real = ff.current_effr
    ff.current_effr = lambda: calls.append(1) or 3.63          # type: ignore
    try:
        ff.implied_probs(_MEETINGS, prices=_QUOTES)
    finally:
        ff.current_effr = real                                  # type: ignore
    assert calls == [], "offline test path must not fetch a live EFFR"


def test_gate_missing_sources_state_a_reason():
    from app.sources.rate_markets import blend
    # the ensemble payload shape the panel reads: every empty source carries a
    # reason, and the blend renormalizes over the sources that DID price
    per = {"polymarket": {}, "kalshi": {"hold": 0.6, "hike25p": 0.4},
           "futures": {"hold": 0.5, "hike25p": 0.5}}
    missing = {s: "no market listed for this meeting yet"
               for s, p in per.items() if not p}
    assert list(missing) == ["polymarket"]
    b = blend(per, source_weights())
    assert abs(sum(b.values()) - 1.0) < 1e-6
    assert 0.4 < b["hike25p"] < 0.5
