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
