"""Proposer: sizing, max-loss invariant, pricing-basis fallback, lean gating."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine.bs import bs_price
from app.engine.proposer import SYNTHETIC_EXPIRY_DAYS_AFTER_EVENT, propose
from app.engine.signals import ChainRowView

ASOF = date(2026, 8, 19)
EVENT = date(2026, 9, 10)
EXPIRY = date(2026, 9, 18)


def _chain(c_ask=4.0, p_ask=3.5, c_bid=3.6, p_bid=3.1, strike=100.0):
    return [ChainRowView(expiry=EXPIRY, strike=strike,
                         c_bid=c_bid, c_ask=c_ask, p_bid=p_bid, p_ask=p_ask)]


def _propose(**kw):
    defaults = dict(score=70.0, event_date=EVENT, asof=ASOF, spot=100.0,
                    chain_rows=_chain(), paper_equity=100_000.0)
    defaults.update(kw)
    return propose("MRNA", **defaults)


def test_chain_ask_entry_and_basis():
    p = _propose()
    assert p is not None
    assert p.pricing_basis == "chain_ask"
    assert p.unit_premium == pytest.approx(4.0 + 3.5)  # ASK both legs
    assert p.structure == "ATM_STRADDLE"
    assert p.strike == 100.0 and p.expiry == EXPIRY


def test_max_loss_equals_premium_always():
    p = _propose()
    assert p.max_loss == p.cost == pytest.approx(p.unit_premium * 100 * p.contracts)


def test_sizing_50bps_budget():
    # budget = 50bps of 100k = $500; per contract = $750 -> min 1 contract,
    # flagged as exceeding the budget.
    p = _propose()
    assert p.contracts == 1
    assert any("exceeds bps budget" in f for f in p.flags)
    # cheap structure: $1.00 unit -> $100/contract -> 5 contracts fit $500
    p2 = _propose(chain_rows=_chain(c_ask=0.6, p_ask=0.4, c_bid=0.5, p_bid=0.3))
    assert p2.contracts == 5
    assert p2.cost == pytest.approx(500.0)


def test_bs_scenario_fallback_when_chain_dark():
    p = _propose(chain_rows=None, scenario_iv=1.0)
    assert p is not None
    assert p.pricing_basis == "bs_scenario"
    assert p.entry_iv == 1.0
    exp = EVENT + timedelta(days=SYNTHETIC_EXPIRY_DAYS_AFTER_EVENT)
    T = (exp - ASOF).days / 365.0
    expected = (bs_price(100, 100, T, 1.0, kind="call")
                + bs_price(100, 100, T, 1.0, kind="put"))
    assert p.unit_premium == pytest.approx(expected, abs=1e-3)
    assert any("chain dark" in f for f in p.flags)


def test_bs_fallback_when_chain_has_no_usable_ask():
    p = _propose(chain_rows=_chain(c_ask=None))  # one leg lacks an ask
    assert p.pricing_basis == "bs_scenario"  # no partial-honesty entries


def test_below_min_score_or_undated_is_none():
    assert _propose(score=54.9) is None
    assert _propose(score=None) is None
    assert _propose(event_date=None) is None
    assert _propose(spot=None) is None


def test_call_only_requires_operator_lean():
    assert _propose().structure == "ATM_STRADDLE"
    p = _propose(direction_lean="bullish")
    assert p.structure == "CALL_ONLY"
    assert p.unit_premium == pytest.approx(4.0)  # call ask only
    p2 = _propose(direction_lean="bearish")
    assert p2.structure == "PUT_ONLY"
    # unknown lean text falls back to the direction-agnostic default
    assert _propose(direction_lean="mystery").structure == "ATM_STRADDLE"
