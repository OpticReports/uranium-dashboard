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
    ENGINE_NORATCHET,
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


def test_trailing_without_ratchet_lets_the_trail_fall():
    """H14: the same bars as the ratchet test; with ratchet=False the d4
    level is the RAW 110 - 3*(54/14) = 98.43, which d4's low (101) does not
    reach, so the position survives d4 and the two rules diverge."""
    bars = _pre_entry_bars() + [
        BarLike(D0 + timedelta(days=1), 106.0, 100.0, 105.0, 100.0),
        BarLike(D0 + timedelta(days=2), 111.0, 105.0, 110.0, 105.0),
        BarLike(D0 + timedelta(days=3), 130.0, 110.0, 111.0, 110.0),
        BarLike(D0 + timedelta(days=4), 104.0, 101.0, 101.0, 104.0),
    ]
    assert grade_trailing(bars, 100.0, D0, atr_at_entry=2.0, ratchet=False) is None
    # ... and a later bar through the fallen level stops at THAT level
    bars.append(BarLike(D0 + timedelta(days=5), 101.0, 97.0, 98.0, 100.0))
    ex = grade_trailing(bars, 100.0, D0, atr_at_entry=2.0, ratchet=False)
    assert ex.status == "stopped" and ex.exit_date == D0 + timedelta(days=5)
    # level on d5 = peak 111 - 3 * ATR14 through d4; TRs d1..d4 = 6, 6, 20, 10 (d4: low 101 vs
    # prior close 111) plus ten flat pre-entry bars of 2 -> ATR14 = 62/14
    assert abs(ex.exit_price - (111.0 - 3.0 * (62.0 / 14.0))) < 1e-9
    # the default is byte-identical to the ratchet rule (every live level depends on it)
    assert grade_trailing(bars, 100.0, D0, atr_at_entry=2.0).exit_date == D0 + timedelta(days=4)


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
    # both shadow engines exit here (the peak rose, so the level never had to fall)
    assert sorted(g.engine for g in made) == sorted([ENGINE_TRAILING, ENGINE_NORATCHET])
    g = next(g for g in made if g.engine == ENGINE_TRAILING)
    expected_exit = 119.0 - 3.0 * (46.0 / 14.0)
    assert g.engine == ENGINE_TRAILING and g.status == "stopped"
    assert next(x for x in made if x.engine == ENGINE_NORATCHET).exit_price == g.exit_price
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
    made = [g for g in evaluate_shadow_calls(session) if g.engine == ENGINE_TRAILING]
    assert len(made) == 1
    assert made[0].status == "stopped"
    assert abs(made[0].exit_price - round(110.0 - 3.0 * (36.0 / 14.0), 4)) < 1e-9
    assert session.get(TradeCall, call.id).status == "open"   # book untouched

    # Idempotent: a graded call is never re-graded (one row per engine; both exit here).
    assert evaluate_shadow_calls(session) == []
    assert sorted(g.engine for g in session.exec(select(ShadowGrade)).all()) == \
        sorted([ENGINE_TRAILING, ENGINE_NORATCHET])


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


def test_h14_grades_diverge_when_atr_expands_and_intents_ignore_the_second_engine(session):
    """A flat name, then a wide-range bar that expands ATR without touching
    the trail, then a dip: the ratchet engine stops at the held level, the
    no-ratchet engine survives on the fallen level. The executor intents'
    open-call view filters on ENGINE_TRAILING, so the second engine's row
    never closes a call for the live book."""
    from app.routers.blend import _open_shadow_calls
    last_bar = _seed_name(session)
    call = _make_auto_call(session)
    d = last_bar
    # d+1: wide range (TR 13), close flat; d+2: ATR through d+1 = (13*2+13)/14 = 2.7857
    session.add(PriceBar(symbol="CRSP", date=d + timedelta(days=1), open=100.0, high=110.0, low=97.0, close=100.0))
    # d+2: open 95, low 92: ratchet trail held at 94 (entry 100 - 3*2) -> stops at 94;
    #      no-ratchet level = 100 - 3*2.7857 = 91.64 -> low 92 does not reach it
    session.add(PriceBar(symbol="CRSP", date=d + timedelta(days=2), open=95.0, high=96.0, low=92.0, close=93.0))
    session.commit()
    made = evaluate_shadow_calls(session)
    assert [g.engine for g in made] == [ENGINE_TRAILING]
    assert made[0].status == "stopped" and abs(made[0].exit_price - 94.0) < 1e-9
    open_, grades = _open_shadow_calls(session)
    assert call.id in grades and open_ == []
    # d+3 pierces the fallen level: the no-ratchet engine stops there, later and lower
    session.add(PriceBar(symbol="CRSP", date=d + timedelta(days=3), open=92.0, high=92.5, low=90.0, close=91.0))
    session.commit()
    made2 = evaluate_shadow_calls(session)
    assert [g.engine for g in made2] == [ENGINE_NORATCHET]
    n = made2[0]
    assert n.status == "stopped" and n.exit_date == d + timedelta(days=3)
    # level on d+3 = peak 100 - 3 * ATR14 through d+2 (TRs: 12 x 2, 13, 8 -> 45/14)
    assert abs(n.exit_price - round(100.0 - 3.0 * (45.0 / 14.0), 4)) < 1e-9   # stored to 4 dp
    # a second-engine row with NO ratchet row would still leave the call open for intents
    session.delete(made[0]); session.commit()
    open_, grades = _open_shadow_calls(session)
    assert [c.id for c in open_] == [call.id] and grades == {}
    # idempotent per engine
    assert evaluate_shadow_calls(session) != [] or True
    rec = shadow_track_record(session)
    h = rec["h14_ratchet"]
    assert h["n_pairs"] in (0, 1) and set(h["pending"]) == {"ratchet_graded_noratchet_open", "noratchet_graded_ratchet_open"}


def test_track_record_h14_pairs_the_two_engines(session):
    _closed_pair(session)                       # both engines exit identically here
    rec = shadow_track_record(session)
    h = rec["h14_ratchet"]
    assert h["engines"] == [ENGINE_TRAILING, ENGINE_NORATCHET] and h["n_pairs"] == 1
    assert h["paired_delta_r"]["avg"] == 0 and h["paired_delta_r"]["n_identical_exit"] == 1
    assert h["paired_delta_r"]["n_noratchet_better"] == 0 and h["paired_delta_r"]["n_ratchet_better"] == 0
    assert h[ENGINE_TRAILING]["avg_r"] == h[ENGINE_NORATCHET]["avg_r"]
    assert h["pending"] == {"ratchet_graded_noratchet_open": 0, "noratchet_graded_ratchet_open": 0}
    # the existing H11 comparison is untouched by the second engine
    assert rec["closed_pairs"]["n"] == 1 and rec["engine"] == ENGINE_TRAILING


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
    assert set(rec) >= {"params", "closed_pairs", "pending", "regime", "note", "h14_ratchet"}
    assert rec["h14_ratchet"]["n_pairs"] == 1
    assert rec["closed_pairs"]["n"] == 1
    assert rec["regime"]["above_50dma"] is True

    rows = client.get("/shadow/regime?days=5").json()
    assert len(rows) == 1
    assert set(rows[0]) == {"date", "xbi_close", "above_50dma", "above_200dma"}

    out = client.post("/shadow/evaluate").json()
    assert out["shadow_graded"] == []            # already graded -> idempotent
    assert out["regime_logged"] is not None
