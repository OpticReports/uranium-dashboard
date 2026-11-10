"""drift_z10 math, days_to_event selection, interim-watch, ATM IV plumbing."""
from __future__ import annotations

import math
import statistics
from datetime import date

import pytest

from app.engine.bs import bs_price
from app.engine.signals import (
    ChainRowView, EventView, atm_iv, days_to_event, detect_interim_watch,
    drift_z10, expiry_after, has_interim_watch, iv_ratio, nearest_event,
    realized_vol_20d,
)

ASOF = date(2026, 8, 19)


# --- drift_z10 -----------------------------------------------------------------

def _make_closes(n=40, base=100.0, daily=0.01):
    """Alternating +/- daily moves: known vol, ~zero drift."""
    closes = [base]
    for i in range(n - 1):
        closes.append(closes[-1] * (1 + (daily if i % 2 == 0 else -daily)))
    return closes


def test_drift_z10_matches_hand_math():
    closes = _make_closes()
    got = drift_z10(closes)
    # independent recomputation
    tail = closes[-21:]
    rets = [math.log(tail[i + 1] / tail[i]) for i in range(20)]
    sd = statistics.stdev(rets)
    expected = (closes[-1] / closes[-11] - 1) / (sd * math.sqrt(10))
    assert got == pytest.approx(expected)


def test_drift_z10_detects_a_big_move():
    quiet = _make_closes()
    popped = _make_closes()
    popped[-1] = popped[-2] * 1.30  # +30% pop on the last day
    z_quiet, z_pop = drift_z10(quiet), drift_z10(popped)
    assert z_pop is not None and z_pop > 1.0  # clearly moved...
    assert abs(z_pop) > 5 * abs(z_quiet)      # ...relative to the quiet tape
    # (the pop inflates the 20d vol denominator too — z is damped, by design)


def test_drift_insufficient_data_is_none():
    assert drift_z10([100.0] * 20) is None      # needs >= 21
    assert drift_z10([]) is None
    assert drift_z10(None) is None


def test_drift_flat_series_is_none_not_zero():
    # zero vol -> undefined z, never 0.0
    assert drift_z10([100.0] * 30) is None


def test_realized_vol_annualization():
    closes = _make_closes()
    daily = realized_vol_20d(closes, annualize=False)
    annual = realized_vol_20d(closes, annualize=True)
    assert annual == pytest.approx(daily * math.sqrt(252))


# --- days_to_event ---------------------------------------------------------------

def _ev(d, impact=0.9, watch=False, event_type="phase3_readout"):
    return EventView(date=d, event_type=event_type, impact_weight=impact,
                     watch=watch)


def test_nearest_dated_high_impact_within_horizon():
    events = [
        _ev(date(2026, 9, 10), impact=0.9),          # 22d — the one
        _ev(date(2026, 9, 1), impact=0.5),           # nearer but low impact
        _ev(date(2026, 12, 1), impact=1.0),          # outside 60d horizon
        _ev(None, impact=0.85, watch=True),          # undated watch
        _ev(date(2026, 8, 1), impact=1.0),           # in the past
    ]
    assert days_to_event(events, ASOF, horizon_days=60, min_impact=0.85) == 22
    ev = nearest_event(events, ASOF, 60, 0.85)
    assert ev.date == date(2026, 9, 10)


def test_no_qualifying_event_is_none():
    assert days_to_event([_ev(date(2026, 9, 1), impact=0.5)], ASOF) is None
    assert days_to_event([], ASOF) is None
    assert days_to_event([_ev(None, watch=True)], ASOF) is None


def test_watch_flag_carries_no_fabricated_date():
    events = [_ev(None, impact=0.85, watch=True)]
    assert has_interim_watch(events)
    assert days_to_event(events, ASOF) is None  # watch never becomes a date


# --- interim-watch detection ------------------------------------------------------

def test_interim_watch_detection():
    far_pcd = date(2029, 10, 26)  # V940-001 pattern
    assert detect_interim_watch("ACTIVE_NOT_RECRUITING", far_pcd, ASOF, ["PHASE3"])
    # near PCD (< 12 months) -> a normal dated event, not a watch
    assert not detect_interim_watch("ACTIVE_NOT_RECRUITING", date(2026, 12, 1),
                                    ASOF, ["PHASE3"])
    # recruiting -> not a watch (no interim to read yet)
    assert not detect_interim_watch("RECRUITING", far_pcd, ASOF, ["PHASE3"])
    # phase 2 -> not a watch
    assert not detect_interim_watch("ACTIVE_NOT_RECRUITING", far_pcd, ASOF,
                                    ["PHASE2"])
    assert not detect_interim_watch("ACTIVE_NOT_RECRUITING", None, ASOF,
                                    ["PHASE3"])


# --- ATM IV / iv_ratio ---------------------------------------------------------------

def _row(expiry, strike, sigma, spot=100.0, spread=0.05):
    """Chain row whose mids are exact BS prices at `sigma` (r=0)."""
    T = (expiry - ASOF).days / 365.0
    c = bs_price(spot, strike, T, sigma, kind="call")
    p = bs_price(spot, strike, T, sigma, kind="put")
    return ChainRowView(expiry=expiry, strike=strike,
                        c_bid=c - spread, c_ask=c + spread,
                        p_bid=p - spread, p_ask=p + spread)


def test_atm_iv_recovers_sigma_from_mids():
    event = date(2026, 9, 10)
    rows = [
        _row(date(2026, 9, 4), 100.0, 0.8),    # before event — must be skipped
        _row(date(2026, 9, 18), 100.0, 0.6),   # just after event — the one
        _row(date(2026, 9, 18), 110.0, 0.9),   # not ATM
        _row(date(2026, 10, 16), 100.0, 0.5),  # later expiry
    ]
    iv = atm_iv(rows, spot=100.0, event_date=event, asof=ASOF)
    assert iv == pytest.approx(0.6, abs=0.01)


def test_expiry_after_picks_first_on_or_after():
    rows = [_row(date(2026, 9, 4), 100, 0.5), _row(date(2026, 9, 18), 100, 0.5)]
    assert expiry_after(rows, date(2026, 9, 10)) == date(2026, 9, 18)
    assert expiry_after(rows, date(2026, 9, 18)) == date(2026, 9, 18)
    assert expiry_after(rows, date(2026, 10, 1)) is None


def test_atm_iv_none_when_dark_or_undated():
    assert atm_iv([], 100.0, date(2026, 9, 10), ASOF) is None
    rows = [_row(date(2026, 9, 18), 100.0, 0.6)]
    assert atm_iv(rows, None, date(2026, 9, 10), ASOF) is None
    assert atm_iv(rows, 100.0, None, ASOF) is None


def test_iv_ratio():
    assert iv_ratio(0.8, 0.4) == pytest.approx(2.0)
    assert iv_ratio(None, 0.4) is None
    assert iv_ratio(0.8, None) is None
    assert iv_ratio(0.8, 0.0) is None
