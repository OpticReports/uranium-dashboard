"""Ledger accounting: ask-in -> mid-mark -> bid-out, auto-close, book math."""
from __future__ import annotations

from datetime import date

import pytest

from app.engine.bs import bs_price
from app.engine.ledger import (
    add_trading_days, auto_close_date, auto_close_due, close_position,
    has_open_position, mark_position, open_position, snapshot_equity,
    summarize, unit_close_value, unit_mark,
)
from app.engine.proposer import Proposal
from app.engine.signals import ChainRowView

ASOF = date(2026, 8, 19)
EVENT = date(2026, 9, 10)
EXPIRY = date(2026, 9, 18)


def _row(c_bid, c_ask, p_bid, p_ask, strike=100.0, expiry=EXPIRY):
    return ChainRowView(expiry=expiry, strike=strike, c_bid=c_bid, c_ask=c_ask,
                        p_bid=p_bid, p_ask=p_ask)


def _proposal(unit=10.0, contracts=1, basis="chain_ask", entry_iv=None):
    cost = unit * 100 * contracts
    return Proposal(symbol="MRNA", structure="ATM_STRADDLE", strike=100.0,
                    expiry=EXPIRY, event_date=EVENT, contracts=contracts,
                    unit_premium=unit, cost=cost, max_loss=cost,
                    pricing_basis=basis, entry_iv=entry_iv, spot=100.0)


# --- trading-day arithmetic ---------------------------------------------------

def test_add_trading_days_skips_weekends():
    fri = date(2026, 8, 21)
    assert add_trading_days(fri, 3) == date(2026, 8, 26)  # Mon+Tue+Wed
    assert add_trading_days(date(2026, 8, 19), 1) == date(2026, 8, 20)


def test_auto_close_date_is_min_of_expiry_and_event_plus_3td():
    assert auto_close_date(EXPIRY, EVENT, 3) == add_trading_days(EVENT, 3)
    near_expiry = date(2026, 9, 11)
    assert auto_close_date(near_expiry, EVENT, 3) == near_expiry
    assert auto_close_date(EXPIRY, None, 3) == EXPIRY  # undated -> expiry


# --- pure valuation helpers -----------------------------------------------------

def test_unit_mark_prefers_chain_mid():
    row = _row(c_bid=6.0, c_ask=7.0, p_bid=5.0, p_ask=6.0)
    val, basis = unit_mark("ATM_STRADDLE", 100.0, EXPIRY, None, row, 100.0, ASOF)
    assert basis == "chain_mid"
    assert val == pytest.approx(6.5 + 5.5)


def test_unit_mark_falls_back_to_bs_at_entry_iv():
    val, basis = unit_mark("ATM_STRADDLE", 100.0, EXPIRY, 1.0, None, 105.0, ASOF)
    assert basis == "bs_entry_iv"
    T = (EXPIRY - ASOF).days / 365.0
    expected = (bs_price(105, 100, T, 1.0, kind="call")
                + bs_price(105, 100, T, 1.0, kind="put"))
    assert val == pytest.approx(expected)


def test_unit_mark_unmarkable_returns_none():
    assert unit_mark("ATM_STRADDLE", 100.0, EXPIRY, None, None, None, ASOF) is None


def test_unit_close_value_bid_then_intrinsic():
    row = _row(c_bid=6.0, c_ask=7.0, p_bid=5.0, p_ask=6.0)
    val, basis = unit_close_value("ATM_STRADDLE", 100.0, row, 100.0)
    assert basis == "chain_bid" and val == pytest.approx(11.0)  # BID both legs
    val, basis = unit_close_value("ATM_STRADDLE", 100.0, None, 130.0)
    assert basis == "intrinsic" and val == pytest.approx(30.0)
    val, basis = unit_close_value("CALL_ONLY", 100.0, None, 90.0)
    assert basis == "intrinsic" and val == 0.0


# --- full open -> mark -> close cycle against the DB -----------------------------

def test_open_mark_close_accounting(session):
    pos = open_position(session, _proposal(unit=10.0), ASOF)
    assert pos.entry_cost == 1000.0
    assert has_open_position(session, "MRNA", EVENT)
    assert not has_open_position(session, "MRNA", date(2027, 1, 1))

    # mark at chain mid 12.0 -> +200 unrealized
    row = _row(c_bid=6.5, c_ask=7.5, p_bid=4.5, p_ask=5.5)
    mark_position(session, pos, [row], 100.0, ASOF)
    assert pos.mark_basis == "chain_mid"
    assert pos.mark_value == pytest.approx(1200.0)

    s = summarize([pos], 100_000.0)
    assert s.cash == pytest.approx(99_000.0)
    assert s.equity == pytest.approx(100_200.0)
    assert s.hit_rate is None  # nothing graded yet

    # close at chain bid 11.0 -> proceeds 1100, realized +100 (ask in, bid out)
    closed = close_position(session, pos, [row], 100.0, date(2026, 9, 15))
    assert closed.close_basis == "chain_bid"
    assert closed.close_proceeds == pytest.approx(1100.0)
    assert closed.realized_pnl == pytest.approx(100.0)

    s = summarize([closed], 100_000.0)
    assert s.cash == pytest.approx(100_100.0)
    assert s.equity == pytest.approx(100_100.0)
    assert s.hit_rate == 1.0 and s.closed_positions == 1


def test_intrinsic_close_when_chain_dark(session):
    pos = open_position(session, _proposal(unit=8.0), ASOF)
    closed = close_position(session, pos, None, 125.0, date(2026, 9, 15))
    assert closed.close_basis == "intrinsic"
    assert closed.close_proceeds == pytest.approx(25.0 * 100)  # |125-100|
    assert closed.realized_pnl == pytest.approx(2500.0 - 800.0)


def test_close_impossible_returns_none_and_stays_open(session):
    pos = open_position(session, _proposal(), ASOF)
    assert close_position(session, pos, None, None, ASOF) is None
    assert pos.status == "open"


def test_auto_close_due_closes_only_due_positions(session):
    pos = open_position(session, _proposal(), ASOF)
    due = auto_close_date(EXPIRY, EVENT, 3)

    # not yet due
    closed = auto_close_due(session, lambda s: None, lambda s: 120.0,
                            asof=date(2026, 9, 1))
    assert closed == []
    assert pos.status == "open"

    closed = auto_close_due(session, lambda s: None, lambda s: 120.0, asof=due)
    assert len(closed) == 1
    assert closed[0].close_basis == "intrinsic"
    assert closed[0].status == "closed"


def test_snapshot_equity_upserts(session):
    open_position(session, _proposal(unit=5.0), ASOF)
    p1 = snapshot_equity(session, 100_000.0, ASOF)
    p2 = snapshot_equity(session, 100_000.0, ASOF)  # same day -> update in place
    assert p1.id == p2.id
    assert p2.cash == pytest.approx(99_500.0)
