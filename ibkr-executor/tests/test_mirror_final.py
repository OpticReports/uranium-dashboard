"""The final cross-patch review of the mirror change set (main c1aaca77 -> rounds 4-7), 2026-11-14.

  R1  (its verifier B's MINOR, a TWIN pinning both cases) the buying guard's red after a restart. The hold's start,
      run["buys_blocked_utc"], is stamped and SAVED at the first look that held the buys (mirror.py _advance), and
      the no-warning-after-a-red rule is per process (self._said). So a new process whose first look comes within
      BUYS_UNCONFIRMED_GRACE_S of the hold's start warns once more, then its red comes; a later one - any real
      restart, a new container and an IB Key login taking minutes - is red at its first look, with no warning.
      composer/IBKR_MIRROR.md says exactly this (pinned in test_mirror_buyguard_r5.py test_d8).
  C1  (its verifier B's NOTE, a GATE: fails at 4f4282c1) service._session_close_et falls back to 16:00 when blend's
      early-close table cannot be read; the mirror then refuses every half-day lean (mirror.py _validate). It now
      says so once at WARNING, and its answers are unchanged.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest

import test_mirror as tm
from app import mirror as mm
from app import service

D2 = "2026-11-11"
ROT = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"PULS": 1.0}}


def held_rig(tmp_path):
    """a $50k live book whose second session rotates every engine, with the account's cash and positions frozen at
    their pre-trade values from the first order on: TotalCashValue never moves and the positions never confirm the
    sells, so the buys are held (the round-5 guard's positions cross-check) and alerted"""
    r = tm.Rig(tmp_path, live=True, capital=50_000.0, venue_cash=51_500.0)
    r.tick("15:00")
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    v = r.venue
    box = {"cash": None, "pos": None}

    def account_cash():
        c = v.cash if box["cash"] is None else box["cash"]
        return {"total_cash": c, "net_liq": None, "available_funds": c, "ts": 0.0}

    real_snap = tm.Venue.positions_snapshot.__get__(v)

    def positions_snapshot():
        if box["pos"] is not None:
            return {"stocks": {k: q for k, q in sorted(box["pos"].items()) if q}, "other": []}
        return real_snap()
    real_place = v.place_stock_order

    def place(symbol, qty, *a, **k):
        if box["cash"] is None:
            box["cash"], box["pos"] = v.cash, dict(v._positions)
        return real_place(symbol, qty, *a, **k)
    v.account_cash, v.positions_snapshot, v.place_stock_order = account_cash, positions_snapshot, place
    r.brain.make = lambda now: tm.payload(now, ROT, session=D2)
    r.m._budget_s = 1.0                            # one look per tick: the test steps the clock itself
    r.tick("15:00", D2)
    return r


def looks(r, start_hms, seconds):
    t0 = tm.at(start_hms, D2)
    for s in seconds:
        r.clock.now = t0 + timedelta(seconds=s)
        r.m.tick(r.venue)
        assert r.m.last_error is None, r.m.last_error


def said(r, since):
    out = []
    for a in r.alerts[since:]:
        if "the buys WAIT" in a:
            out.append("warn")
        elif "the BUYS are HELD" in a:
            out.append("red")
    return out


@pytest.mark.parametrize("restart_at,expect", [(3.0, ["warn", "red"]), (30.0, ["red"])])
def test_r1_after_a_restart_the_new_process_warns_only_inside_the_grace(tmp_path, restart_at, expect):
    """TWIN. The first process warns at its first look; past the grace (restart 30 s in) it has also sent its red.
    The new process boots on the same state file: 3 s into the hold it warns once more, then its red comes at the
    grace; 30 s into the hold its first look is red at once, and no warning follows"""
    assert mm.BUYS_UNCONFIRMED_GRACE_S == 10.0
    r = held_rig(tmp_path)
    n0 = len(r.alerts)
    looks(r, "15:54:25", [0.0, 1.5])
    run = r.m.state["run"]
    assert run and run.get("buys_blocked") and run.get("buys_blocked_utc"), run
    assert said(r, n0)[:1] == ["warn"], said(r, n0)
    if restart_at > mm.BUYS_UNCONFIRMED_GRACE_S:
        looks(r, "15:54:25", [12.0])               # the first process's red
        assert said(r, n0)[-1] == "red", said(r, n0)
    n1 = len(r.alerts)
    r.m = r.boot()                                 # a new process, the same state file
    r.m._budget_s = 1.0
    looks(r, "15:54:25", [restart_at, restart_at + 1.5, restart_at + 12.0, restart_at + 13.5])
    assert said(r, n1) == expect, (restart_at, said(r, n1))


def test_c1_an_unreadable_early_close_table_is_said_once_and_answers_16_00(monkeypatch, caplog):
    """GATE (4f4282c1 says nothing). The twin: a readable table answers as before (2026-11-27 closes at 13:00)"""
    assert service._session_close_et(date(2026, 11, 27)) == (13, 0)
    assert service._session_close_et(date(2026, 11, 20)) == (16, 0)
    import app.blend as blend

    def broken(d):
        raise RuntimeError("calendar unreadable (test)")
    monkeypatch.setattr(blend, "session_close_et", broken)
    monkeypatch.setattr(service, "_CLOSE_UNREAD_SAID", False, raising=False)   # on 4f4282c1: fails at the warning
    with caplog.at_level(logging.WARNING, logger=service.logger.name):
        got = [service._session_close_et(date(2026, 11, 27)) for _ in range(3)]
    assert got == [(16, 0)] * 3
    warned = [rec for rec in caplog.records if "early-close calendar" in rec.getMessage()]
    assert len(warned) == 1 and warned[0].levelno == logging.WARNING, [rec.getMessage() for rec in caplog.records]
    assert "calendar unreadable (test)" in warned[0].getMessage()
    assert "refuses any half-day lean" in warned[0].getMessage()
