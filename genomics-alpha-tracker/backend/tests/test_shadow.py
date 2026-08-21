"""H11/H8 shadow-book tests: trailing-exit grading (R2-A conventions), the
prior-close regime gate, live/shadow independence, and the API shape.

Everything offline; the pure grade_trailing cases are hand-derived (the trail
values in comments are computed from the ATR14 arithmetic, not eyeballed).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlmodel import select

import pytest

from app.calls import manager
from app.calls.rules import BarLike
from app.calls.shadow import (
    ENGINE_TRAILING,
    evaluate_shadow_calls,
    grade_trailing,
    log_regime,
    regime_state,
    shadow_track_record,
)
from app.models import PriceBar, RegimeLog, ScoreSnapshot, Security, ShadowGrade, TradeCall
from app.models import FlagEvent


# --- grade_trailing (pure, hand-derived) --------------------------------------

D0 = date(2026, 1, 20)  # entry date (last pre-entry bar's date)


def _pre_entry_bars(n: int = 15, close: float = 100.0):
    """Flat history ending ON the entry date: TR = 2 every bar => ATR14 = 2."""
    start = D0 - timedelta(days=n - 1)
    return [
        BarLike(start + timedelta(days=i), close + 1.0, close - 1.0, close, close)
        for i in range(n)
    ]


def test_trailing_stop_hits_at_level():
    # trail on day 1 = peak(=entry 100) - 3*ATR(2) = 94; low pierces it.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 101.0, 93.0, 95.0, 100.0),
    ]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0)
    assert ex.status == "stopped"
    assert abs(ex.exit_price - 94.0) < 1e-9
    assert ex.exit_date == D0 + timedelta(days=1)


def test_trailing_gap_through_trail_fills_at_open():
    # Open gaps straight through the 94 trail -> fill at the OPEN, not 94.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 92.0, 88.0, 90.0, 90.0),
    ]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0)
    assert ex.status == "stopped"
    assert ex.exit_price == 90.0


def test_trailing_ratchets_up_only():
    # d1 close 105 (TR 6), d2 close 110 (TR 6), d3 a 20-point-range bar.
    # Trail sequence: 94 -> 105-3*(32/14)=98.143 -> 110-3*(36/14)=102.2857.
    # At d4 the blown-out ATR (54/14) would put the raw trail at 99.43 —
    # the ratchet must HOLD 102.2857, and d4's low (101) must stop there.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 106.0, 100.0, 105.0, 100.0),
        BarLike(D0 + timedelta(days=2), 111.0, 105.0, 110.0, 105.0),
        BarLike(D0 + timedelta(days=3), 130.0, 110.0, 111.0, 110.0),
        BarLike(D0 + timedelta(days=4), 104.0, 101.0, 101.0, 104.0),
    ]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0)
    assert ex.status == "stopped"
    assert ex.exit_date == D0 + timedelta(days=4)
    assert abs(ex.exit_price - (110.0 - 3.0 * (36.0 / 14.0))) < 1e-9  # 102.2857...


def test_trailing_time_stop_on_the_deadline_bar():
    # Flat forever: trail 94 never touched; a bar exactly on entry+90
    # calendar days exits at ITS close.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=i), 101.0, 99.0, 100.0, 100.0)
        for i in range(1, 91)
    ]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0)
    assert ex.status == "expired"
    assert ex.exit_date == D0 + timedelta(days=90)
    assert ex.exit_price == 100.0


def test_trailing_time_stop_at_last_bar_at_or_before_deadline():
    # No bar prints on day 90 (weekend); next bar is day 92. The exit must be
    # the close of the LAST bar at-or-before the deadline (day 89) — never the
    # post-deadline bar.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=i), 101.0, 99.0, 100.0, 100.0)
        for i in range(1, 90)
    ] + [BarLike(D0 + timedelta(days=92), 101.0, 99.0, 100.5, 100.0)]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0)
    assert ex.status == "expired"
    assert ex.exit_date == D0 + timedelta(days=89)
    assert ex.exit_price == 100.0


def test_trailing_insufficient_bars_returns_none():
    # No post-entry bars at all -> still open, never a guessed exit.
    assert grade_trailing(_pre_entry_bars(), 100.0, D0, atr_at_entry=2.0) is None
    # A few quiet post-entry bars inside the window -> also still open.
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=i), 101.0, 99.0, 100.0, 100.0) for i in (1, 2, 3)
    ]
    assert grade_trailing(bars, 100.0, D0, atr_at_entry=2.0) is None


def test_trailing_daily_atr_recompute_needs_no_entry_seed():
    # With enough pre-entry history the daily ATR recompute carries the trail
    # even when atr_at_entry is unavailable (pre-feature calls).
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 101.0, 93.0, 95.0, 100.0),
    ]
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=None)
    assert ex.status == "stopped" and abs(ex.exit_price - 94.0) < 1e-9


# --- regime_state (prior-close convention) ------------------------------------

def test_regime_flips_the_day_after_a_cross_not_the_day_of():
    # 50 closes at 100, then the cross day closes 200. On the cross day the
    # PRIOR close (100) is not above the prior SMA (100) -> gate still off.
    closes = [100.0] * 50 + [200.0]
    st = regime_state(closes)
    assert st["above_50dma"] is False
    # The NEXT day the prior close is 200 vs prior SMA 102 -> gate on.
    st = regime_state(closes + [200.0])
    assert st["above_50dma"] is True
    assert abs(st["sma_50"] - 102.0) < 1e-9
    assert st["prior_close"] == 200.0


def test_regime_undefined_sma_never_binds():
    st = regime_state([100.0] * 60)
    assert st["above_50dma"] is False  # 100 > 100 is False (strict)
    assert st["above_200dma"] is None  # <200 closes -> undefined, never binds
    assert st["sma_200"] is None
    st = regime_state([100.0])         # a single close: no PRIOR close at all
    assert st["prior_close"] is None and st["above_50dma"] is None


# --- shadow grading against the DB (independence from the live book) ----------

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


def _make_auto_call(session):
    session.add(FlagEvent(symbol="CRSP", flag_type="pre_catalyst_sentiment_ramp",
                          severity="high", message="test flag"))
    session.commit()
    return manager.generate_calls(session)[0]


def test_generate_snapshots_atr_at_entry(session):
    _seed_name(session)
    call = _make_auto_call(session)
    assert call.atr_at_entry == 2.0        # flat 2-pt-range bars -> ATR14 = 2
    # And the live levels are exactly what they were before the feature.
    assert (call.entry_price, call.stop_price, call.target_price) == (100.0, 94.0, 118.0)


def test_shadow_open_while_live_closed_then_exits_later(session):
    last_bar = _seed_name(session)
    call = _make_auto_call(session)

    # d+1 rips through the live 118 target; the shadow trail (94) is untouched.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=120.0, low=100.0, close=119.0))
    session.commit()
    assert manager.evaluate_calls(session)[0].status == "target_hit"
    assert evaluate_shadow_calls(session) == []          # shadow STILL OPEN
    assert session.exec(select(ShadowGrade)).all() == []

    # d+2: trail has ratcheted to 119 - 3*(46/14) = 109.1428...; the low
    # pierces it while the open (110) does not -> shadow stops at the trail.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=2),
                         open=110.0, high=110.0, low=105.0, close=106.0))
    session.commit()
    made = evaluate_shadow_calls(session)
    assert len(made) == 1
    g = made[0]
    expected_exit = 119.0 - 3.0 * (46.0 / 14.0)
    assert g.engine == ENGINE_TRAILING and g.status == "stopped"
    assert abs(g.exit_price - round(expected_exit, 4)) < 1e-9
    # R uses the LIVE risk unit (entry - stop = 6) so engines are comparable.
    assert abs(g.r_multiple - (expected_exit - 100.0) / 6.0) < 1e-6
    assert g.call_id == call.id


def test_shadow_closes_while_live_still_open(session):
    last_bar = _seed_name(session)
    call = _make_auto_call(session)

    # d+1 runs to 110 (between stop 94 and target 118): live stays open.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=110.0, low=100.0, close=110.0))
    # d+2: trail = 110 - 3*(36/14) = 102.2857...; low 100 pierces it, open
    # 103 does not; the live call sees neither 94 nor 118.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=2),
                         open=103.0, high=103.0, low=100.0, close=101.0))
    session.commit()

    assert manager.evaluate_calls(session) == []         # live STILL OPEN
    made = evaluate_shadow_calls(session)
    assert len(made) == 1
    assert made[0].status == "stopped"
    assert abs(made[0].exit_price - round(110.0 - 3.0 * (36.0 / 14.0), 4)) < 1e-9
    assert session.get(TradeCall, call.id).status == "open"   # book untouched

    # Idempotent: a graded call is never re-graded.
    assert evaluate_shadow_calls(session) == []
    assert len(session.exec(select(ShadowGrade)).all()) == 1


def test_shadow_backfills_missing_atr_at_entry(session):
    last_bar = _seed_name(session)
    # A pre-feature call: no atr_at_entry stored.
    call = TradeCall(symbol="CRSP", call_date=last_bar, direction="long",
                     source="auto_flag", flag_type="pre_catalyst_sentiment_ramp",
                     entry_price=100.0, stop_price=94.0, target_price=118.0,
                     expires_on=last_bar + timedelta(days=45))
    session.add(call)
    session.commit()
    assert evaluate_shadow_calls(session) == []          # no post-entry bars yet
    assert session.get(TradeCall, call.id).atr_at_entry == 2.0  # backfilled


def test_shadow_ignores_manual_calls(session):
    last_bar = _seed_name(session)
    session.add(TradeCall(symbol="CRSP", call_date=last_bar, direction="long",
                          source="manual", entry_price=100.0, stop_price=94.0,
                          target_price=118.0,
                          expires_on=last_bar + timedelta(days=45)))
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=90.0, high=91.0, low=89.0, close=90.0))
    session.commit()
    assert evaluate_shadow_calls(session) == []
    assert session.exec(select(ShadowGrade)).all() == []


# --- regime logging -----------------------------------------------------------

def _seed_xbi(session, n=60, base=100.0, tail=(110.0, 110.0, 110.0, 110.0, 110.0)):
    session.add(Security(symbol="XBI", name="XBI", active=False,
                         subsector=["benchmark"]))
    start = date.today() - timedelta(days=n)
    closes = [base] * (n - len(tail)) + list(tail)
    for i, c in enumerate(closes):
        session.add(PriceBar(symbol="XBI", date=start + timedelta(days=i),
                             open=c, high=c + 1, low=c - 1, close=c))
    session.commit()
    return start + timedelta(days=n - 1)


def test_log_regime_prior_close_and_idempotent(session):
    last = _seed_xbi(session)
    row = log_regime(session)
    assert row.date == last
    assert row.xbi_close == 110.0
    assert row.above_50dma is True       # prior close 110 vs mostly-100 SMA50
    assert row.above_200dma is None      # <200 closes -> undefined, never binds
    # Idempotent: same trading day never gets a second row.
    again = log_regime(session)
    assert again.date == row.date
    assert len(session.exec(select(RegimeLog)).all()) == 1


def test_log_regime_needs_two_closes(session):
    session.add(Security(symbol="XBI", name="XBI", active=False))
    session.add(PriceBar(symbol="XBI", date=date.today(), close=100.0,
                         open=100.0, high=101.0, low=99.0))
    session.commit()
    assert log_regime(session) is None


# --- track record + API -------------------------------------------------------

def _closed_pair(session):
    """One call closed by BOTH engines: production target_hit +3R, shadow
    trailing stop (the d+2 exit from the independence test)."""
    last_bar = _seed_name(session)
    call = _make_auto_call(session)
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=120.0, low=100.0, close=119.0))
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=2),
                         open=110.0, high=110.0, low=105.0, close=106.0))
    session.commit()
    manager.evaluate_calls(session)
    evaluate_shadow_calls(session)
    return call


def test_track_record_compares_engines_on_the_same_calls(session):
    _closed_pair(session)
    # Regime summary counts: 3 gated-off days, 2 on, 1 undefined.
    d = date(2026, 1, 1)
    for i, above in enumerate([False, False, False, True, True, None]):
        session.add(RegimeLog(date=d + timedelta(days=i), xbi_close=90.0,
                              above_50dma=above, above_200dma=above))
    session.commit()

    rec = shadow_track_record(session)
    assert rec["engine"] == ENGINE_TRAILING
    pairs = rec["closed_pairs"]
    assert pairs["n"] == 1
    assert pairs["production"]["by_status"] == {"target_hit": 1}
    assert abs(pairs["production"]["avg_r"] - 3.0) < 1e-9
    assert pairs["production"]["hit_rate"] == 1.0
    trail = pairs[ENGINE_TRAILING]
    assert trail["by_status"] == {"stopped": 1}
    expected_r = (119.0 - 3.0 * (46.0 / 14.0) - 100.0) / 6.0
    assert abs(trail["avg_r"] - expected_r) < 1e-6
    assert abs(trail["total_r"] - expected_r) < 1e-6
    assert rec["pending"] == {"live_open_shadow_closed": 0,
                              "live_closed_shadow_open": 0, "both_open": 0}
    assert rec["regime"]["days_gated_off_200dma"] == 3
    assert rec["regime"]["days_logged"] == 6
    assert rec["regime"]["above_200dma"] is None  # latest logged row


def test_track_record_pending_buckets(session):
    last_bar = _seed_name(session)
    _make_auto_call(session)
    # A quiet bar: neither engine exits -> both open.
    session.add(PriceBar(symbol="CRSP", date=last_bar + timedelta(days=1),
                         open=100.0, high=101.0, low=99.0, close=100.0))
    session.commit()
    manager.evaluate_calls(session)
    evaluate_shadow_calls(session)
    rec = shadow_track_record(session)
    assert rec["closed_pairs"]["n"] == 0
    assert rec["closed_pairs"]["production"]["avg_r"] is None
    assert rec["pending"]["both_open"] == 1


@pytest.fixture
def client(session):
    # Override via the ROUTER's captured reference, not a fresh
    # `from app.db import get_session`: test_migrations.py reloads app.db,
    # so a re-import here would be a different object than the Depends key
    # the route registered at import time (order-dependent test breakage).
    from app.main import app
    from app.routers.shadow import get_session

    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_api_shapes(session, client):
    _closed_pair(session)
    _seed_xbi(session)
    log_regime(session)

    rec = client.get("/shadow/track-record").json()
    assert rec["engine"] == ENGINE_TRAILING
    assert set(rec) >= {"params", "closed_pairs", "pending", "regime", "note"}
    assert rec["closed_pairs"]["n"] == 1
    assert rec["regime"]["above_50dma"] is True

    rows = client.get("/shadow/regime?days=5").json()
    assert len(rows) == 1
    assert set(rows[0]) == {"date", "xbi_close", "above_50dma", "above_200dma"}

    out = client.post("/shadow/evaluate").json()
    assert out["shadow_graded"] == []            # already graded -> idempotent
    assert out["regime_logged"] is not None
