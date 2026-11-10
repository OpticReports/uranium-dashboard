"""Rate-ensemble gates: bucket parsing, weight math, blend normalization,
degradation. All offline."""
from datetime import date

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
# second one too. These gates encode the anchor ladder, the well-conditioned
# leg choice, and the reason strings a dash on the panel now carries.

_QUOTES = {(2026, 9): 96.265, (2026, 10): 96.125, (2026, 11): 96.03,
           (2026, 12): 95.91, (2027, 1): 95.85, (2027, 2): 95.78}
_MEETINGS = ["2026-09-16", "2026-10-28", "2026-12-09", "2027-01-27"]
_TODAY = date(2026, 9, 16)


def _probs(meetings=None, quotes=None, effr=3.63, notes=None, today=_TODAY,
           effr_date=None):
    from app.sources.fed_futures import implied_probs
    return implied_probs(meetings or _MEETINGS, prices=quotes or _QUOTES,
                         effr=effr, notes=notes, today=today,
                         effr_date=effr_date)


def test_gate_expired_prior_contract_does_not_blank_the_near_meetings():
    # August 2026 has settled and no longer quotes, so the September row has no
    # anchor and drops out with a stated reason (October survives on its own
    # because a late-month meeting solves r_start from its own contract)
    notes: dict = {}
    bare = _probs(effr=None, notes=notes)
    assert "2026-09-16" not in bare
    assert "expired" in notes["2026-09-16"] or "not quoted" in notes["2026-09-16"]
    assert "spot EFFR is unavailable" in notes["2026-09-16"]
    # spot EFFR restores it: ZQ settles on the average of exactly this rate
    notes2: dict = {}
    out = _probs(notes=notes2)
    assert set(out) == set(_MEETINGS), "every meeting must price"
    for d in _MEETINGS:
        assert abs(sum(out[d].values()) - 1.0) < 1e-6
    # Sep 16, 30-day month, next month holds a decision so the month average
    # solves r_end: 3.735 = (16/30)*3.63 + (14/30)*r_end -> 3.855, delta +22.5bp
    # -> 0.900 steps -> hold 0.100 / hike 0.900
    assert out["2026-09-16"] == {"cut50p": 0.0, "cut25": 0.0,
                                 "hold": 0.1, "hike25p": 0.9}
    # the anchor note names WHY the contract leg was skipped. Offline the
    # reason is "not quoted" (injected prices have no expiry by design); the
    # live path says "has expired" — both come from the same variable, so the
    # skip note and the anchor note can never disagree
    assert notes2["_anchor:2026-09-16"].startswith("r_start is spot EFFR 3.63%")
    assert "not quoted" in notes2["_anchor:2026-09-16"]
    assert not any(k.startswith("_anchor:") and k != "_anchor:2026-09-16"
                   for k in notes2)


def test_gate_late_month_solves_the_side_the_month_measures():
    # Oct 28 leaves post_frac 0.097: solving r_end would divide by 0.097 and
    # amplify quote error ~10x, so r_end comes off the meeting-free November
    # contract (3.97) and the month average solves r_start (divide by 0.903).
    # r_start = (3.875 - 0.0968*3.97)/0.9032 = 3.8649 -> delta +10.5bp
    # -> 0.4204 steps -> hold 0.5796 / hike 0.4204
    out = _probs()
    assert abs(out["2026-10-28"]["hike25p"] - 0.4204) < 0.001
    # the row must depend on its OWN month's contract — the earlier attempt
    # took r_start from the chain and ignored it entirely
    moved = _probs(quotes={**_QUOTES, (2026, 10): 96.145})
    assert moved["2026-10-28"] != out["2026-10-28"]
    # ...and must NOT inherit the chain: breaking the September row leaves
    # October priced, because the late-month form is self-contained
    q = {k: v for k, v in _QUOTES.items() if k != (2026, 9)}
    solo = _probs(quotes=q)
    assert solo["2026-10-28"] == out["2026-10-28"]
    # the well-conditioned rows are untouched by any of this
    assert abs(out["2026-12-09"]["hike25p"] - 0.6764) < 0.001


def test_gate_ill_conditioned_readings_say_so():
    from app.sources.fed_futures import SOFT_FRAC
    # drop November: October can no longer read r_end off it and must divide
    # by 0.097 — the answer still prints, but flagged with its amplification
    notes: dict = {}
    q = {k: v for k, v in _QUOTES.items() if k != (2026, 11)}
    out = _probs(quotes=q, notes=notes)
    assert "2026-10-28" in out
    soft = notes["_soft:2026-10-28"]
    assert "10x" in soft and "is not quoted" in soft
    assert 3 / 31 < SOFT_FRAC


def test_gate_effr_anchors_only_the_first_upcoming_meeting():
    # the first meeting's own month has no contract, so it cannot price; the
    # second must NOT then borrow spot EFFR — a decision sits in between
    notes: dict = {}
    q = {k: v for k, v in _QUOTES.items() if k != (2026, 9)}
    out = _probs(quotes=q, notes=notes)
    assert "2026-09-16" not in out
    assert "no ZQ contract quoted for 2026-09" in notes["2026-09-16"]
    assert not any(k.startswith("_anchor:") for k in notes)
    # a PAST meeting never takes today's spot rate as its anchor
    notes2: dict = {}
    _probs(meetings=["2026-07-29"] + _MEETINGS, notes=notes2,
           today=date(2026, 9, 16))
    assert "_anchor:2026-07-29" not in notes2


def test_gate_a_skipped_meeting_breaks_the_chain():
    # Strip October's own contract AND November's: October cannot price, so
    # December — whose prior-month anchor is the missing November contract —
    # has only the chain left. That chain now holds SEPTEMBER's r_end, a rate
    # from before the October decision, and must be refused rather than used.
    notes: dict = {}
    q = {k: v for k, v in _QUOTES.items() if k not in ((2026, 10), (2026, 11))}
    out = _probs(quotes=q, notes=notes)
    assert "2026-09-16" in out                      # still anchors on spot EFFR
    assert "2026-10-28" not in out
    assert "2026-12-09" not in out, "a stale chain must never price a row"
    assert "no anchor rate" in notes["2026-12-09"]


def test_gate_meeting_days_come_from_the_fed_not_the_markets():
    from app.sources.fed_futures import (DECISION_DAYS, FOMC_MONTHS,
                                         snap_to_decision, _meeting_month)
    # a market date a day either side of the decision snaps to the Fed's day,
    # so post_frac is not driven by a UTC truncation artifact
    assert snap_to_decision(date(2026, 9, 17)) == date(2026, 9, 16)
    assert snap_to_decision(date(2026, 9, 15)) == date(2026, 9, 16)
    assert snap_to_decision(date(2026, 9, 21)) is None
    off_by_one = _probs(meetings=["2026-09-17"] + _MEETINGS[1:])
    assert off_by_one["2026-09-17"] == {"cut50p": 0.0, "cut25": 0.0,
                                        "hold": 0.1, "hike25p": 0.9}
    # the month set is DERIVED from both days of every meeting, so a meeting
    # spanning a month boundary would mark both months
    assert (2026, 9) in FOMC_MONTHS and (2026, 11) not in FOMC_MONTHS
    assert _meeting_month(2026, 11, set()) is False
    assert _meeting_month(2029, 5, set()) is None      # past the table
    assert date(2027, 12, 8) in DECISION_DAYS          # published through 2027


def test_gate_duplicate_meeting_dates_cannot_corrupt_the_chain():
    dup = _probs(meetings=["2026-09-16", "2026-09-16", "2026-10-28"])
    clean = _probs(meetings=["2026-09-16", "2026-10-28"])
    assert dup == clean


def test_gate_injected_prices_never_hit_the_network():
    import app.sources.fed_futures as ff
    calls = []
    real = ff.current_effr
    ff.current_effr = lambda *a, **k: calls.append(1) or (3.63, _TODAY)  # type: ignore
    try:
        ff.implied_probs(_MEETINGS, prices=_QUOTES, today=_TODAY)
    finally:
        ff.current_effr = real                                           # type: ignore
    assert calls == [], "offline test path must not fetch a live EFFR"


def test_gate_effr_is_never_a_pre_decision_rate():
    import app.sources.fed_futures as ff
    # the NY Fed publishes EFFR for day T on T+1, so for a day after a decision
    # the newest print is still the OLD stance. Anchoring the meeting that IS
    # that decision is fine — the pre-decision rate is exactly r_start — but
    # carrying it to the NEXT meeting is not.
    pre = date(2026, 9, 15)
    assert _probs(notes={}, effr=3.63, effr_date=pre)["2026-09-16"]["hike25p"] == 0.9
    notes: dict = {}
    after = _probs(meetings=["2026-10-28", "2026-12-09"], effr=3.63,
                   effr_date=date(2026, 9, 16), notes=notes,
                   today=date(2026, 9, 17),
                   quotes={k: v for k, v in _QUOTES.items()
                           if k not in ((2026, 11),)})
    assert "2026-10-28" not in after
    assert "has not printed since the 2026-09-16 decision" in notes["2026-10-28"]
    # the median shrugs off a firm month-end print, and the stance filter uses
    # the newest print's own decision boundary
    ff._EFFR_CACHE.clear()
    ff._effr_nyfed = lambda: [(date(2026, 9, 15), 3.63), (date(2026, 9, 14), 3.63),
                              (date(2026, 8, 31), 3.71)]                  # type: ignore
    ff._effr_fred = lambda: []                                            # type: ignore
    try:
        assert ff.current_effr() == (3.63, date(2026, 9, 15))
    finally:
        ff._EFFR_CACHE.clear()


def test_gate_ensemble_payload_carries_the_reasons():
    import app.sources.rate_markets as rm
    two = {"2026-09-16": {"hold": 0.11, "hike25p": 0.89},
           "2027-03-17": {"hold": 0.66, "hike25p": 0.34}}
    orig = (rm.fetch_polymarket, rm.fetch_kalshi, rm._save_store)
    rm.fetch_polymarket = lambda: {"2026-09-16": two["2026-09-16"]}       # type: ignore
    rm.fetch_kalshi = lambda: two                                          # type: ignore
    rm._save_store = lambda d: None                                        # type: ignore
    try:
        out = rm.ensemble()
    finally:
        rm.fetch_polymarket, rm.fetch_kalshi, rm._save_store = orig        # type: ignore
    by = {m["date"]: m for m in out["meetings"]}
    assert "2027-03-17" in by
    far = by["2027-03-17"]
    assert far["missing"]["polymarket"] == "no market listed for this meeting yet"
    assert set(far["sources"]) == {"polymarket", "kalshi", "futures"}
    assert abs(sum(far["blend"].values()) - 1.0) < 1e-6
    for m in out["meetings"]:                      # every empty source explains
        for src, probs in m["sources"].items():
            assert bool(probs) != (src in m["missing"])
