"""Gate tests for app/mirror.py on an NYSE HALF-DAY (a 13:00 close; composer/IBKR_MIRROR.md). The next
are Fri 2026-11-27 and Thu 2026-12-24. The doubles are tests/test_mirror.py's.

  E1  the brain's clock drives the day: nothing before 12:54:25 (the bar ending 12:54:00 plus 25 s), the
      sells at 12:54:25, the cancel instant 12:59:00 (the close minus 60 s): a sell still resting then is
      cancelled and its partial booked at or after 12:59:00 and before 13:00, no buy is sent, and nothing
      is sent after the cancel instant
  E2  the FALLBACK clock (the brain's not read today: a /kill's flatten carried over from an earlier day
      never reads it) ends an early close at 13:00 by the service's own calendar: a flatten queued on the
      Wednesday before Thanksgiving sends nothing into the closed market at 13:05 on the half-day and
      waits for Monday's open. Twins: a regular Friday at 13:05 sells; without the calendar, so did the
      half-day (the defect)
  E3  an unreadable brain clock on a half-day: the loop is asked back at the late cadence from 12:30 (the
      window ends at 13:00), and the day's NO TRADE is recorded at 13:00, not 16:00. Twin: a regular day
      at 12:40 keeps the ordinary cadence and records nothing at 13:00
  E4  the service builds the books with its own early-close calendar (blend.session_close_et)
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from app import mirror as mm
from app.blend import session_close_et
from test_mirror import T1, Rig, at, payload, sound

HALF = "2026-11-27"                       # the Friday after Thanksgiving: a 13:00 close
WED, THU, MON = "2026-11-25", "2026-11-26", "2026-11-30"
FRI = "2026-11-20"                        # a regular Friday


class HalfRig(Rig):
    """the shared rig, its manager given the service's early-close calendar (None: no calendar)"""

    def __init__(self, tmp_path, session_close=None, **kw):
        self.session_close = session_close
        super().__init__(tmp_path, **kw)

    def boot(self):
        m = super().boot()
        m._session_close = self.session_close
        return m


def test_e1_a_half_day_decides_at_12_54_25_and_cancels_at_12_59_before_the_close(tmp_path):
    r = HalfRig(tmp_path, session_close_et, live=True)
    r.tick("15:00")
    r.tick("15:55:05")                                         # invested on a full day
    assert r.m.state["last_run"]["outcome"] == "traded"
    held = r.m.book.sleeves["HG"].shares["BIL"]
    r.brain.close = "13:00"
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=HALF, close="13:00")
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 100
    r.venue.fill_px["BIL"] = 91.40
    n = len(r.venue.placed)
    r.tick("12:54:24", day=HALF)
    assert r.venue.placed[n:] == [] and not [c for c in r.brain.calls if c[0] == "2026-11-27T17:54:00Z"]
    r.tick("12:54:25", day=HALF)
    run = r.m.state["run"]
    assert (run["session"], run["decide_utc"], run["cancel_utc"], run["close_utc"]) == \
        (HALF, "2026-11-27T17:54:00Z", "2026-11-27T17:59:00Z", "2026-11-27T18:00:00Z")
    assert [(s, q) for s, q, _ in r.venue.placed[n:]] == [("BIL", -held)]   # the sell first; it rests
    assert run["phase"] == "sells" and r.clock.now < at("12:59:00", HALF)
    r.tick("12:58:50", day=HALF)                               # ... and this tick waits into the cancel instant
    row = r.m.state["last_run"]
    bil = next(o for o in row["orders"] if o["symbol"] == "BIL")
    assert (bil["filled"], bil["price"]) == (100, 91.40) and "cancelled" in bil["how"]
    fill = next(x for x in r.journal() if x["event"] == "fill" and x["id"] == f"mirror-{HALF}-S-BIL")
    assert "2026-11-27T17:59:00Z" <= fill["utc"] < "2026-11-27T18:00:00Z"      # 12:59:00 <= booked < 13:00 ET
    assert not any(s == "TQQQ" for s, _, _ in r.venue.placed) and any("buys NOT sent" in x for x in row["notes"])
    m = len(r.venue.placed)
    for hms in ("12:59:30", "13:00:30", "15:55:05"):          # nothing after the cancel instant, nor at 15:54 + 25 s
        r.tick(hms, day=HALF)
    assert len(r.venue.placed) == m and r.m.state["last_session"] == HALF
    sound(r)


def _killed_on_wednesday(path, close):
    """invested on the Wednesday before Thanksgiving, /kill after its close: the flatten is queued"""
    os.makedirs(path, exist_ok=True)
    r = HalfRig(path, close, live=True, poll_s=1e9)
    r.trading_day = lambda d: d.weekday() < 5 and d.isoformat() != THU      # the service's holiday calendar
    r.boot()
    r.brain.make = lambda now: payload(now, session=now.astimezone(mm.ET).date().isoformat())
    r.tick("15:00", day=WED)
    r.tick("15:55:05", day=WED)
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.m.halt("KILL", flatten=True)
    r.tick("17:00:00", day=WED)                                # queued: the session is shut
    assert r.m.book.positions() and not r.m.halt_state().get("flatten_done")
    return r


def test_e2_a_flatten_on_the_fallback_clock_sends_nothing_after_an_early_close(tmp_path):
    r = _killed_on_wednesday(tmp_path / "half", session_close_et)
    n = len(r.venue.placed)
    r.tick("13:05:00", day=HALF)                               # the brain's clock was last read on Wednesday
    assert r.m._today_info(r.clock.now) is None and r.m._rth(r.clock.now) is False
    assert r.venue.placed[n:] == [] and r.m.book.positions() != {}            # nothing into the closed market
    assert r.m.next_wait() == pytest.approx(min((at("09:30:00", MON) - at("13:05:00", HALF)).total_seconds(), 1e9))
    assert r.m._rth(at("12:59:59", HALF)) is True and r.m._rth(at("09:29:59", HALF)) is False
    r.tick("09:30:05", day=MON)                                # Monday's open: the sells go
    assert len(r.venue.placed) == n + 5 and r.m.book.positions() == {}
    sound(r)
    # twins: a REGULAR Friday at 13:05 is an open market; and with no calendar the half-day was one too
    f = _killed_on_wednesday(tmp_path / "fri", session_close_et)
    n = len(f.venue.placed)
    f.tick("13:05:00", day=FRI)
    assert len(f.venue.placed) == n + 5
    b = _killed_on_wednesday(tmp_path / "none", None)
    n = len(b.venue.placed)
    b.tick("13:05:00", day=HALF)
    assert len(b.venue.placed) == n + 5                        # the old fallback: orders after the 13:00 close


@pytest.mark.parametrize("live, before, now", [(True, mm.UNKNOWN_WAIT_S, mm.UNKNOWN_WAIT_LATE_S),
                                               (False, mm.PAPER_UNKNOWN_WAIT_S, mm.UNKNOWN_WAIT_S)])
def test_e3_an_unreadable_clock_on_a_half_day_runs_to_its_13_00_close(tmp_path, live, before, now):
    r = HalfRig(tmp_path / "half", session_close_et, live=live)
    r.brain.session_fail = "deadline"
    r.tick("12:20:00", day=HALF)
    assert r.m.next_wait() == before                           # half an hour before the window: the ordinary cadence
    r.tick("12:40:00", day=HALF)
    assert r.m.next_wait() == now                              # inside the half-day's last half hour: the late one
    r.tick("13:00:30", day=HALF)
    row = r.m.state["last_run"]
    assert (row["session"], row["outcome"]) == (HALF, "skipped") and "unreadable all session" in row["reason"]
    r.tick("13:05:00", day=HALF)
    assert r.m.next_wait() is None                             # five minutes past the close: the loop's own cadence
    assert len(r.m.state["history"]) == 1                      # recorded once
    t = HalfRig(tmp_path / "fri", session_close_et, live=live)                 # the twin: a regular Friday
    t.brain.session_fail = "deadline"
    t.tick("12:40:00", day=FRI)
    assert t.m.next_wait() == before
    t.tick("13:00:30", day=FRI)
    assert t.m.state.get("last_run") is None
    t.tick("16:00:30", day=FRI)
    assert t.m.state["last_run"]["outcome"] == "skipped"


def test_e4_the_service_builds_the_books_with_its_early_close_calendar(tmp_path, monkeypatch):
    from test_mirror_service import _boot, _ready
    client, service, _ = _boot(tmp_path, monkeypatch)
    with client:
        _ready(service)
        assert service.MIRROR and all(b._session_close is service._session_close_et for b in service.MIRROR.values())
    assert (service._session_close_et(date(2026, 11, 27)), service._session_close_et(date(2026, 12, 24)),
            service._session_close_et(date(2026, 11, 20))) == ((13, 0), (13, 0), (16, 0))
