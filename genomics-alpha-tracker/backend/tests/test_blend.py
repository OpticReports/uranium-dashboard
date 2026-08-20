"""blend3070 intents API tests: shape, gate suppression, trail-level parity
with the shadow reference, and offline safety.

Trail values are the same hand-derived ATR14 arithmetic as test_shadow.py —
the endpoint must publish EXACTLY what shadow.grade_trailing would act on.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.calls import manager
from app.calls.rules import BarLike
from app.calls.shadow import evaluate_shadow_calls, grade_trailing
from app.models import FlagEvent, PriceBar, ScoreSnapshot, Security, ShadowGrade, TradeCall
from app.routers.blend import BOOK_PARAMS, current_trail_level


# --- fixtures -----------------------------------------------------------------

@pytest.fixture
def client(session):
    from app.main import app
    from app.routers.blend import get_session

    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_name(session, symbol="CRSP", n_bars=30, close=100.0):
    """Flat 2-pt-range bars => ATR14 = 2 (same construction as test_shadow)."""
    session.add(Security(symbol=symbol, name=symbol, active=True))
    start = date.today() - timedelta(days=n_bars)
    for i in range(n_bars):
        session.add(PriceBar(symbol=symbol, date=start + timedelta(days=i),
                             open=close, high=close + 1.0, low=close - 1.0,
                             close=close, volume=1e6))
    session.add(ScoreSnapshot(symbol=symbol, composite=80.0))
    session.commit()
    return start + timedelta(days=n_bars - 1)  # latest bar date


def _seed_xbi(session, above: bool, last_date: date, n=220):
    """XBI history with >200 closes so the 200dma is DEFINED; the tail puts
    the PRIOR close decisively above/below the SMA."""
    session.add(Security(symbol="XBI", name="XBI", active=False))
    start = last_date - timedelta(days=n - 1)
    tail_close = 150.0 if above else 50.0
    for i in range(n):
        c = 100.0 if i < n - 5 else tail_close
        session.add(PriceBar(symbol="XBI", date=start + timedelta(days=i),
                             open=c, high=c + 1, low=c - 1, close=c))
    session.commit()


def _fire_call(session):
    session.add(FlagEvent(symbol="CRSP", flag_type="pre_catalyst_sentiment_ramp",
                          severity="high", message="test flag"))
    session.commit()
    return manager.generate_calls(session)[0]


# --- current_trail_level parity with grade_trailing ---------------------------

D0 = date(2026, 1, 20)


def _pre_entry_bars(n=15, close=100.0):
    start = D0 - timedelta(days=n - 1)
    return [BarLike(start + timedelta(days=i), close + 1.0, close - 1.0, close, close)
            for i in range(n)]


def test_current_trail_is_the_level_grade_trailing_stops_at():
    # After entry at 100 (ATR 2) and one 100->110 bar, the trail actionable
    # at the next open is 110 - 3*(36/14) — the shadow reference number.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 110.0, 100.0, 110.0, 100.0),
    ]
    assert grade_trailing(bars, 100.0, D0, atr_at_entry=2.0) is None  # still open
    level = current_trail_level(bars, 100.0, D0, atr_at_entry=2.0)
    assert level == pytest.approx(round(110.0 - 3.0 * (36.0 / 14.0), 4))
    # And a next-day bar whose low pierces exactly that level stops there.
    ex = grade_trailing(
        bars + [BarLike(D0 + timedelta(days=2), 103.0, level - 0.01, 101.0, 103.0)],
        100.0, D0, atr_at_entry=2.0)
    assert ex.status == "stopped" and ex.exit_price == pytest.approx(level, abs=1e-4)


def test_current_trail_day_one_is_entry_minus_3atr():
    bars = _pre_entry_bars()
    assert current_trail_level(bars, 100.0, D0, atr_at_entry=2.0) == pytest.approx(94.0)


def test_current_trail_ratchet_survives_atr_blowout():
    # Same ratchet scenario as test_shadow: the blown-out d3 ATR must not
    # lower the earned 102.2857 level.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 106.0, 100.0, 105.0, 100.0),
        BarLike(D0 + timedelta(days=2), 111.0, 105.0, 110.0, 105.0),
        BarLike(D0 + timedelta(days=3), 130.0, 110.0, 111.0, 110.0),
    ]
    level = current_trail_level(bars, 100.0, D0, atr_at_entry=2.0)
    assert level == pytest.approx(round(110.0 - 3.0 * (36.0 / 14.0), 4))


def test_current_trail_none_without_atr():
    assert current_trail_level([], 100.0, D0, atr_at_entry=None) is None


# --- endpoint behavior --------------------------------------------------------

def test_intents_shape_and_gate_on_entry(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    call = _fire_call(session)

    out = client.get("/blend3070/intents").json()
    assert set(out) == {"as_of", "gate", "entries", "exits", "stops",
                        "rebalance", "book_params", "contract"}
    assert out["as_of"] == last_bar.isoformat()
    assert out["gate"]["xbi_above_200dma_prior"] is True

    assert len(out["entries"]) == 1
    e = out["entries"][0]
    assert e["symbol"] == "CRSP" and e["call_id"] == call.id
    assert e["fire_date"] == last_bar.isoformat()
    assert e["flag_type"] == "pre_catalyst_sentiment_ramp"
    assert e["risk_frac"] == 0.01
    assert e["entry_ref"] == 100.0          # fire-day close, the sizing ref

    # Day-one stop for the fresh position: entry - 3*ATR14 = 94.
    assert out["stops"] == [{"symbol": "CRSP", "call_id": call.id,
                             "trail_level": 94.0}]
    assert out["exits"] == []
    assert out["rebalance"] == {"needed": None, "current_sleeve_weight": None,
                                "target": 0.30}
    assert out["book_params"] == BOOK_PARAMS
    assert "equity" in out["contract"]      # the executor-reconciles contract


def test_gate_off_suppresses_entries_but_not_stops(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=False, last_date=last_bar)
    call = _fire_call(session)

    out = client.get("/blend3070/intents").json()
    assert out["gate"]["xbi_above_200dma_prior"] is False
    assert out["entries"] == []             # gate off -> no new entries
    # Open-position management is gate-independent: the stop still publishes.
    assert out["stops"][0]["call_id"] == call.id


def test_trail_level_tracks_shadow_math_after_a_run_up(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    call = _fire_call(session)
    # d+1 runs 100 -> 110 without touching live levels or the trail.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=110.0, low=100.0, close=110.0))
    session.commit()

    out = client.get("/blend3070/intents").json()
    assert out["exits"] == []
    (stop,) = [s for s in out["stops"] if s["call_id"] == call.id]
    assert stop["trail_level"] == pytest.approx(round(110.0 - 3.0 * (36.0 / 14.0), 4))


def test_trail_exit_intent_when_the_trail_is_pierced(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    call = _fire_call(session)
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=110.0, low=100.0, close=110.0))
    # d+2: low pierces the 102.2857 trail; open does not -> stop at the trail.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=2),
                         open=103.0, high=103.0, low=100.0, close=101.0))
    session.commit()

    out = client.get("/blend3070/intents").json()
    (ex,) = out["exits"]
    assert ex["call_id"] == call.id and ex["reason"] == "trail"
    assert ex["trail_level"] == pytest.approx(round(110.0 - 3.0 * (36.0 / 14.0), 4))
    assert out["stops"] == []               # an exiting position has no stop row


def test_graded_exits_echo_for_late_pollers(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    call = _fire_call(session)
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=110.0, low=100.0, close=110.0))
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=2),
                         open=103.0, high=103.0, low=100.0, close=101.0))
    session.commit()
    # The scheduler's shadow pass grades the exit BEFORE the executor polls.
    assert len(evaluate_shadow_calls(session)) == 1
    g = session.exec(select(ShadowGrade)).one()

    out = client.get("/blend3070/intents").json()
    (ex,) = out["exits"]
    assert ex["call_id"] == call.id and ex["reason"] == "trail"
    assert ex["trail_level"] == pytest.approx(g.exit_price)


def test_time_stop_exit_reason(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    # A stale open call fired long ago (>90 calendar days, quiet bars after).
    old = last_bar - timedelta(days=120)
    session.add(TradeCall(symbol="CRSP", call_date=old, direction="long",
                          source="auto_flag", flag_type="pre_catalyst_sentiment_ramp",
                          entry_price=100.0, stop_price=94.0, target_price=118.0,
                          expires_on=old + timedelta(days=45), atr_at_entry=2.0))
    session.commit()
    out = client.get("/blend3070/intents").json()
    (ex,) = out["exits"]
    assert ex["reason"] == "time_stop" and ex["trail_level"] is None


def test_manual_calls_never_enter_the_blend_book(session, client):
    last_bar = _seed_name(session)
    _seed_xbi(session, above=True, last_date=last_bar)
    session.add(TradeCall(symbol="CRSP", call_date=last_bar, direction="long",
                          source="manual", entry_price=100.0, stop_price=94.0,
                          target_price=118.0,
                          expires_on=last_bar + timedelta(days=45)))
    session.commit()
    out = client.get("/blend3070/intents").json()
    assert out["entries"] == [] and out["stops"] == [] and out["exits"] == []


def test_endpoint_offline_safe_on_empty_db(session, client):
    out = client.get("/blend3070/intents")
    assert out.status_code == 200
    body = out.json()
    assert body["gate"]["xbi_above_200dma_prior"] is None   # undefined, never binds
    assert body["gate"]["since"] is None
    assert body["entries"] == [] and body["stops"] == [] and body["exits"] == []
    assert body["book_params"]["max_open"] == 10
