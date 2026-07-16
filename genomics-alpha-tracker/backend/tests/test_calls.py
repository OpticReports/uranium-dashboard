"""Trade-call tests: level math, grading rules, generation gates, scorecard."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import select

from app.calls import manager
from app.calls.rules import (
    BarLike,
    atr,
    build_levels,
    call_r_multiple,
    call_return,
    grade_call,
)
from app.models import Catalyst, FlagEvent, PriceBar, ScoreSnapshot, Security, TradeCall


# --- pure rules ---------------------------------------------------------------

def _flat_bars(n: int, close: float = 100.0, spread: float = 2.0, start=date(2026, 1, 1)):
    return [
        BarLike(start + timedelta(days=i), close + spread / 2, close - spread / 2, close)
        for i in range(n)
    ]


def test_atr_flat_series():
    bars = _flat_bars(20, close=100.0, spread=2.0)
    assert abs(atr(bars, 14) - 2.0) < 1e-9


def test_atr_insufficient_data_returns_none():
    assert atr(_flat_bars(5), 14) is None


def test_build_levels_long_with_atr():
    lv = build_levels(100.0, "long", atr_value=2.0, stop_atr_mult=2.0,
                      fallback_stop_pct=0.08, reward_risk=2.0)
    assert lv.stop == 96.0          # 100 - 2*2
    assert lv.target == 108.0       # 100 + 2*(100-96)


def test_build_levels_falls_back_to_pct_stop():
    lv = build_levels(100.0, "long", atr_value=None, stop_atr_mult=2.0,
                      fallback_stop_pct=0.08, reward_risk=2.0)
    assert lv.stop == 92.0
    assert lv.target == 116.0


def test_build_levels_short_mirrors():
    lv = build_levels(100.0, "short", atr_value=2.0, stop_atr_mult=2.0,
                      fallback_stop_pct=0.08, reward_risk=2.0)
    assert lv.stop == 104.0
    assert lv.target == 92.0


def test_build_levels_risk_capped_so_stop_stays_positive():
    lv = build_levels(10.0, "long", atr_value=8.0, stop_atr_mult=2.0,
                      fallback_stop_pct=0.08, reward_risk=2.0)
    assert lv.stop == 5.0           # risk capped at 50% of entry
    assert lv.stop > 0


def test_grade_target_hit():
    bars = [BarLike(date(2026, 1, 2), 109.0, 99.0, 108.5)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "target_hit" and ex.exit_price == 108.0


def test_grade_stop_hit():
    bars = [BarLike(date(2026, 1, 2), 101.0, 95.0, 96.5)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped" and ex.exit_price == 96.0


def test_grade_both_touched_same_bar_is_stopped():
    # Daily bar spans both levels -> order unknowable -> conservative: stopped.
    bars = [BarLike(date(2026, 1, 2), 110.0, 95.0, 100.0)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars)
    assert ex.status == "stopped"


def test_grade_expiry_at_close():
    bars = [BarLike(date(2026, 1, 2) + timedelta(days=i), 101.0, 99.0, 100.5)
            for i in range(10)]
    ex = grade_call("long", 100.0, 96.0, 108.0, date(2026, 1, 5), bars)
    assert ex.status == "expired" and ex.exit_price == 100.5
    assert ex.exit_date == date(2026, 1, 5)


def test_grade_still_open():
    bars = [BarLike(date(2026, 1, 2), 101.0, 99.0, 100.5)]
    assert grade_call("long", 100.0, 96.0, 108.0, date(2026, 2, 1), bars) is None


def test_return_and_r_multiple():
    assert abs(call_return("long", 100.0, 108.0) - 0.08) < 1e-9
    assert abs(call_return("short", 100.0, 92.0) - 0.08) < 1e-9
    assert abs(call_r_multiple("long", 100.0, 96.0, 108.0) - 2.0) < 1e-9
    assert abs(call_r_multiple("long", 100.0, 96.0, 96.0) - (-1.0)) < 1e-9
    assert abs(call_r_multiple("short", 100.0, 104.0, 92.0) - 2.0) < 1e-9


# --- generation + lifecycle (DB) -----------------------------------------------

def _seed_name(session, symbol="CRSP", composite=80.0, n_bars=30, close=100.0):
    session.add(Security(symbol=symbol, name=symbol, active=True))
    start = date.today() - timedelta(days=n_bars)
    for i in range(n_bars):
        d = start + timedelta(days=i)
        session.add(PriceBar(symbol=symbol, date=d, open=close, high=close + 1.0,
                             low=close - 1.0, close=close, volume=1e6))
    session.add(ScoreSnapshot(symbol=symbol, composite=composite))
    session.commit()
    return start + timedelta(days=n_bars - 1)  # latest bar date


def _fire_flag(session, symbol="CRSP", flag_type="pre_catalyst_sentiment_ramp",
               evidence=None):
    session.add(FlagEvent(symbol=symbol, flag_type=flag_type, severity="high",
                          message="test flag", evidence=evidence or {}))
    session.commit()


def test_generate_call_from_fresh_flag(session):
    last_bar = _seed_name(session)
    _fire_flag(session)
    made = manager.generate_calls(session)
    assert len(made) == 1
    call = made[0]
    assert call.symbol == "CRSP" and call.direction == "long"
    assert call.source == "auto_flag" and call.flag_type == "pre_catalyst_sentiment_ramp"
    assert call.entry_price == 100.0
    assert call.stop_price == 94.0            # ATR=2 (flat 2pt range), 3*ATR stop
    assert call.target_price == 118.0         # 3R target
    assert call.call_date == last_bar
    assert call.composite_at_call == 80.0
    assert call.status == "open"


def test_generate_skips_low_composite(session):
    _seed_name(session, composite=30.0)
    _fire_flag(session)
    assert manager.generate_calls(session) == []


def test_generate_skips_non_trigger_flags(session):
    _seed_name(session)
    _fire_flag(session, flag_type="runway_cliff_approaching")
    assert manager.generate_calls(session) == []


def test_generate_respects_revision_cluster_direction(session):
    _seed_name(session)
    _fire_flag(session, flag_type="analyst_revision_cluster",
               evidence={"direction": "downward"})
    assert manager.generate_calls(session) == []
    _fire_flag(session, flag_type="analyst_revision_cluster",
               evidence={"direction": "upward"})
    assert len(manager.generate_calls(session)) == 1


def test_generate_no_duplicate_while_open_or_in_cooldown(session):
    _seed_name(session)
    _fire_flag(session)
    assert len(manager.generate_calls(session)) == 1
    _fire_flag(session)  # second fresh flag on the same name
    assert manager.generate_calls(session) == []  # open call blocks

    # Close it; the cooldown window still blocks a new auto-call.
    call = session.exec(select(TradeCall)).one()
    manager.close_call_manual(session, call, exit_price=101.0)
    _fire_flag(session)
    assert manager.generate_calls(session) == []


def test_expiry_exits_before_binary_catalyst(session):
    last_bar = _seed_name(session)
    session.add(Catalyst(symbol="CRSP", date=last_bar + timedelta(days=10),
                         event_type="phase3_readout", title="P3 readout",
                         impact_weight=0.9))
    session.commit()
    _fire_flag(session)
    call = manager.generate_calls(session)[0]
    # Time-stop lands the day BEFORE the binary event (sell into the event).
    assert call.expires_on == last_bar + timedelta(days=9)


def test_evaluate_target_hit_lifecycle(session):
    last_bar = _seed_name(session)
    _fire_flag(session)
    call = manager.generate_calls(session)[0]

    # A post-call bar rips through the target (118 with the 3xATR/3R config).
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=120.0, low=100.0, close=119.0))
    session.commit()
    closed = manager.evaluate_calls(session)
    assert len(closed) == 1
    got = closed[0]
    assert got.status == "target_hit"
    assert got.exit_price == call.target_price
    assert abs(got.return_pct - 0.18) < 1e-9
    assert abs(got.r_multiple - 3.0) < 1e-9


def test_evaluate_ignores_call_date_bar(session):
    # The call-date bar itself must never grade the call (entry = that close).
    _seed_name(session)
    _fire_flag(session)
    manager.generate_calls(session)
    assert manager.evaluate_calls(session) == []


def test_scorecard_aggregates_by_signal(session):
    last_bar = _seed_name(session)
    _fire_flag(session)
    manager.generate_calls(session)
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=120.0, low=100.0, close=119.0))
    session.commit()
    manager.evaluate_calls(session)

    card = manager.scorecard(session)
    assert card["overall"]["calls"] == 1
    assert card["overall"]["target_hit"] == 1
    assert card["overall"]["win_rate"] == 1.0
    assert abs(card["overall"]["avg_r"] - 3.0) < 1e-9
    assert "pre_catalyst_sentiment_ramp" in card["by_signal"]
