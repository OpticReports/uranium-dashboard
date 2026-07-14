"""Post-mortem engine tests: excursions, attribution, hindsight verdicts,
and the deterministic summary prose."""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import select

from app.calls.postmortem import build_postmortem, finalize_hindsight, update_postmortems
from app.models import CallPostmortem, PriceBar, ScoreSnapshot, Security, TradeCall


def _seed(session, symbol, rows, start):
    """rows: list of (open, high, low, close) tuples, one bar per day."""
    session.add(Security(symbol=symbol, name=symbol, active=True))
    for i, (o, h, l, c) in enumerate(rows):
        session.add(PriceBar(symbol=symbol, date=start + timedelta(days=i),
                             open=o, high=h, low=l, close=c, volume=1e6))
    session.commit()


def _closed_call(session, symbol="CRSP", status="stopped", entry=100.0, stop=94.0,
                 target=118.0, exit_price=94.0, call_date=None, exit_date=None,
                 composite=80.0):
    call = TradeCall(
        symbol=symbol, call_date=call_date, direction="long", source="auto_flag",
        flag_type="pre_catalyst_sentiment_ramp", entry_price=entry, stop_price=stop,
        target_price=target, expires_on=call_date + timedelta(days=45),
        composite_at_call=composite, status=status, exit_date=exit_date,
        exit_price=exit_price,
        return_pct=(exit_price - entry) / entry,
        r_multiple=(exit_price - entry) / (entry - stop),
    )
    session.add(call)
    session.commit()
    session.refresh(call)
    return call


def test_postmortem_detects_roundtripped_winner(session):
    start = date.today() - timedelta(days=30)
    flat = [(100, 101, 99, 100)] * 5
    # Rallies to +2R (112) then collapses through the stop.
    path = [(100, 106, 99, 105), (105, 112, 104, 111), (110, 111, 93, 94)]
    _seed(session, "CRSP", flat + path, start)
    _seed(session, "XBI", [(100, 101, 99, 100)] * 8, start)
    call = _closed_call(session, call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=7))
    pm = build_postmortem(session, call)
    assert pm.mfe_r is not None and pm.mfe_r >= 1.9   # peaked ~+2R
    assert "WAS working" in pm.summary                 # the give-back story
    assert pm.name_return < 0


def test_postmortem_detects_never_worked(session):
    start = date.today() - timedelta(days=30)
    flat = [(100, 101, 99, 100)] * 5
    path = [(100, 100.5, 97, 98), (98, 98.5, 93, 94)]  # straight down
    _seed(session, "CRSP", flat + path, start)
    _seed(session, "XBI", [(100, 101, 99, 100)] * 7, start)
    call = _closed_call(session, call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=6))
    pm = build_postmortem(session, call)
    assert pm.mfe_r is not None and pm.mfe_r < 0.3
    assert "never worked" in pm.summary


def test_postmortem_attributes_sector_move(session):
    start = date.today() - timedelta(days=30)
    flat = [(100, 101, 99, 100)] * 5
    down = [(98, 99, 93, 94), (94, 95, 93, 94)]
    _seed(session, "CRSP", flat + down, start)
    # XBI falls ~8% over the same window -> mostly beta.
    xbi = [(100, 101, 99, 100)] * 5 + [(96, 97, 92, 93), (93, 94, 91, 92)]
    _seed(session, "XBI", xbi, start)
    call = _closed_call(session, call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=6))
    pm = build_postmortem(session, call)
    assert pm.bench_return is not None and pm.bench_return < -0.05
    assert "sector" in pm.summary.lower()


def test_hindsight_protected_vs_shakeout(session):
    start = date.today() - timedelta(days=60)
    flat = [(100, 101, 99, 100)] * 5
    stop_day = [(98, 98.5, 93, 94)]
    keeps_falling = [(93, 94, 85, 86)] * 10
    _seed(session, "CRSP", flat + stop_day + keeps_falling, start)
    _seed(session, "XBI", [(100, 101, 99, 100)] * 16, start)
    call = _closed_call(session, call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=5))
    pm = build_postmortem(session, call)
    assert finalize_hindsight(session, pm, call) is True
    assert pm.hindsight_verdict == "protected"
    assert "protected capital" in pm.summary

    # Shakeout: price snaps back above entry after the stop.
    snaps_back = [(94, 103, 94, 102)] * 10
    _seed(session, "SHKE", flat + stop_day + snaps_back, start)
    call2 = _closed_call(session, symbol="SHKE", call_date=start + timedelta(days=4),
                         exit_date=start + timedelta(days=5))
    pm2 = build_postmortem(session, call2)
    assert finalize_hindsight(session, pm2, call2) is True
    assert pm2.hindsight_verdict == "shakeout"
    assert "SHAKEOUT" in pm2.summary


def test_hindsight_pending_until_enough_bars(session):
    start = date.today() - timedelta(days=20)
    flat = [(100, 101, 99, 100)] * 5
    stop_day = [(98, 98.5, 93, 94)]
    only_three_after = [(93, 94, 90, 91)] * 3
    _seed(session, "CRSP", flat + stop_day + only_three_after, start)
    _seed(session, "XBI", [(100, 101, 99, 100)] * 9, start)
    call = _closed_call(session, call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=5))
    pm = build_postmortem(session, call)
    assert finalize_hindsight(session, pm, call) is False
    assert pm.hindsight_verdict is None


def test_update_postmortems_is_idempotent(session):
    start = date.today() - timedelta(days=60)
    flat = [(100, 101, 99, 100)] * 5
    path = [(98, 98.5, 93, 94)] + [(93, 94, 85, 86)] * 12
    _seed(session, "CRSP", flat + path, start)
    _seed(session, "XBI", [(100, 101, 99, 100)] * 18, start)
    _closed_call(session, call_date=start + timedelta(days=4),
                 exit_date=start + timedelta(days=5))
    assert update_postmortems(session) >= 1
    assert update_postmortems(session) == 0  # nothing left to do
    pms = session.exec(select(CallPostmortem)).all()
    assert len(pms) == 1 and pms[0].hindsight_complete


def test_time_stop_before_binary_summary(session):
    from app.models import Catalyst

    start = date.today() - timedelta(days=60)
    flat = [(100, 101, 99, 100)] * 20
    _seed(session, "CRSP", flat, start)
    _seed(session, "XBI", flat, start)
    call = _closed_call(session, status="expired", exit_price=100.0,
                        call_date=start + timedelta(days=4),
                        exit_date=start + timedelta(days=15))
    session.add(Catalyst(symbol="CRSP", date=start + timedelta(days=17),
                         event_type="pdufa", title="PDUFA", impact_weight=1.0))
    session.commit()
    pm = build_postmortem(session, call)
    assert pm.catalyst_status == "exited_before_event"
    assert "before the binary" in pm.summary
