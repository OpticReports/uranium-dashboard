"""Suite-wide fixtures.

The blend planner consults a session clock (blend.entry_window_open): MOO/OPG
entries are only planned outside regular trading hours. Every existing gate
was written against a fixed date with no notion of wall-clock time, so pin
the clock OUTSIDE the session for the whole suite (07:00 ET on the fixture
date) - otherwise the suite would pass or fail depending on the hour it was
run. Tests of the guard itself override the pin explicitly."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import blend as blend_mod

PINNED_NOW_UTC = datetime(2026, 8, 20, 11, 0, tzinfo=timezone.utc)   # 07:00 ET


@pytest.fixture(autouse=True)
def _pin_entry_clock(monkeypatch):
    monkeypatch.setattr(blend_mod, "_now_utc", lambda: PINNED_NOW_UTC)


@pytest.fixture(autouse=True)
def _pin_overnight_core_headroom(monkeypatch):
    """The overnight CORE_BUY headroom (2026-10-05) sizes a core buy planned
    outside the regular session 1% above the quote. The clock pin above puts
    EVERY test outside the session, and the legacy gates were written
    against exact $100 multiples (70 SPY for a $7,000 core), so the
    headroom would shift every one of them by a share without testing
    anything they are about. Same pattern as the clock: pinned to 0 for
    the suite; the headroom's own gates (test_blend.py, "overnight core
    buy") set it explicitly."""
    monkeypatch.setattr(blend_mod, "CORE_BUY_OVERNIGHT_HEADROOM", 0.0)


@pytest.fixture(autouse=True)
def _pin_market_buy_cushion_and_cash_reserve(monkeypatch):
    """The market-buy cushion and the sleeve cash reserve (2026-10-26, the
    BIL x56 refusals) size every SPY/BIL market buy 5% above the quote and
    keep 2% of sleeve equity out of the plan's reach. The legacy gates were
    written against exact multiples (70 SPY / 30 BIL on a $10,000 book) and
    exact cash ledgers, so both would shift nearly every one of them without
    testing anything they are about. With both at 0 the planner and the
    executor reduce to the pre-change code exactly; the suite pins them there
    and their own gates (tests/test_buy_cushion.py) set them explicitly -
    the pattern the overnight headroom above already uses."""
    monkeypatch.setattr(blend_mod, "MKT_BUY_CUSHION", 0.0)
    monkeypatch.setattr(blend_mod, "SLEEVE_CASH_RESERVE_FRAC", 0.0)
