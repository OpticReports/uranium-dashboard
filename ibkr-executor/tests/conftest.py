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
