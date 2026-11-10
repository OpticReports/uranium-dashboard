"""Merge-blocking gates for the adversarial review of the Composer mirror (reviewer A: accounting,
crash safety, kill path; reviewer B's executor items). One finding, one or more gates; each was a
runnable repro that FAILED on the reviewed commit. Where a lead decision changed the expected
behaviour the gate says so. The doubles are tests/test_mirror.py's (Rig, Venue, Brain, Clock); the
gates that need the REAL IBAdapter are in tests/test_mirror_ib.py.

  A-01  a halt or /kill landing mid-tick stops the plan; a /resume mid-flatten stops the flatten
  A-03  /kill, /resume, /kill never sells the same shares twice; a flatten's orders are never orphaned
  A-21  the flatten runs in rounds until the book is flat (bounded, loud when it gives up)
  A-02  an unresolved order no longer blocks the flatten of every other symbol; the operator can
        state what it did (resolve) and repair a divergence (adjust)
  A-20  a flatten queued off hours does not spin the service loop
  A-04  a state file that cannot be written latches the book; the inbox can never stop a /kill
  A-05  never borrow: buys are limit orders sized at their limit; a sleeve in debt is repaired
  A-06  an unreadable brain clock is never a silent day
  A-08  the paper book keeps trading after an engine goes live
  A-09  a transfer that moves less than asked is said and re-queued; a small one is not short-changed
  A-10  a halt that could not be written says so
  A-12  a refusal that cannot change inside the window does not hold the loop
  A-14  a rebuilt plan's new symbols are cross-checked; no halt; requests survive any failure
  A-16  an unreadable executed quantity is unresolved, never zero
  A-17  no new order after the cancel instant
  A-19  settings outside their range are clamped (see also test_mirror.py M19)
  D8    credits debits-first; the morning pre-check; which halt a resume lifted
  D9    dividends (receivables, the two rules, the account's cash guard) and splits
"""
from __future__ import annotations

import json
import os

import pytest

from app import mirror as mm
from app import mirror_core as mc
from test_mirror import (DAY, PX, T1, Rig, at, live_rig, payload, sound, timedelta)

D2, D3, D4 = "2026-11-11", "2026-11-12", "2026-11-13"
ROTATE = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"SPY": 1.0}}


def invested(tmp_path, **kw):
    r = live_rig(tmp_path, **kw)
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    return r


def spy(r, on_call):
    """wrap BOTH placement surfaces of the venue; on_call(symbol, qty) runs after each order landed"""
    for name in ("place_stock_order", "place_limit_order"):
        real = getattr(r.venue, name)

        def call(symbol, qty, *a, _real=real, **kw):
            out = _real(symbol, qty, *a, **kw)
            on_call(symbol, qty)
            return out
        setattr(r.venue, name, call)


def ticks(r, n, step, day=None):
    for _ in range(n):
        r.clock.now += timedelta(seconds=step)
        r.m.tick(r.venue)


def disk(r):
    return json.load(open(r.m.cfg.state_path))


# =============================================================================================== A-01
def test_a01a_a_halt_during_the_first_order_of_a_plan_stops_the_rest(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})      # sells first, then buys
    seen = {"at": None}

    def halt_once(symbol, qty):
        if seen["at"] is None:                        # /mirror/halt (an API thread) lands while the FIRST
            r.m.halt("operator halt")                 # order of the plan is at the venue
            seen["at"] = len(r.venue.placed)
    spy(r, halt_once)
    r.tick("15:55:05", day=D2)
    assert r.m.halt_state()["halted"] is True
    assert r.venue.placed[seen["at"]:] == []          # NOTHING new reached the venue after the halt
    r.tick("15:55:10", day=D2)                        # the halt path settles the run
    row = r.m.state["last_run"]
    assert row["outcome"] == "aborted" and r.m.state["run"] is None
    assert sum(1 for o in row["orders"] if o["filled"]) == 1 and any("buys NOT sent" in n for n in row["notes"])
    sound(r)


def test_a01a_twin_without_the_halt_the_whole_plan_goes_out(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    assert len(r.orders()) - n == 7 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_a01b_a_kill_during_the_intents_read_sends_nothing(tmp_path):
    r = live_rig(tmp_path)                             # all cash: the plan would be five buys
    real = r.brain.intents

    def intents(after):
        out = real(after)
        r.m.halt("KILL", flatten=True)                 # /kill lands while the brain is being read
        return out
    r.brain.intents = intents
    r.tick("15:55:05")
    assert r.m.halt_state()["halted"] is True and r.orders() == []
    assert r.m.state["run"] is None and r.m.state["last_session"] is None
    r.tick("15:55:10")                                 # the flatten has nothing to sell and says so
    assert r.m.halt_state()["flatten_done"] is True and r.orders() == []


def test_a01b_a_halt_during_the_quote_check_drops_the_plan_and_restores_the_book(tmp_path):
    """_start is atomic in memory: a halt seen before the run is saved undoes the credits, the
    transfer pop and the sleeve rules - memory equals the disk again, and the requests are still
    queued for the plan that does run"""
    r = invested(tmp_path)
    r.venue.cash += 50.0
    r.m.request_credit("HARV", 50.0, "interest", force=True)   # round 3 (D-04): beyond the seeded cap, so forced
    r.m.request_transfer("HG", "HARV", 2000.0, "op")
    r.tick("15:56:00")                                 # both drained into the state, on disk
    before = (r.m.book.to_dict(), [q["kind"] for q in r.m.state["requests"]], disk(r)["seq"])
    assert sorted(before[1]) == ["credit", "transfer"]
    r.brain.make = lambda now: payload(now, session=D2)
    real = r.venue.spot_ex
    n = {"k": 0}

    def spot(symbol):
        n["k"] += 1
        if n["k"] == 2:
            r.m.halt("operator halt")                  # lands between two quotes of the cross-check
        return real(symbol)
    r.venue.spot_ex = spot
    orders = len(r.orders())
    r.tick("15:55:05", day=D2)
    assert len(r.orders()) == orders and r.m.state["run"] is None
    assert (r.m.book.to_dict(), [q["kind"] for q in r.m.state["requests"]]) == before[:2]
    assert disk(r)["seq"] == before[2] and disk(r)["run"] is None      # nothing of the attempt was written
    assert not any("credited" in a for a in r.alerts)                  # ... and nothing of it was announced
    r.venue.spot_ex = real
    r.m.resume()
    r.tick("15:55:20", day=D2)                         # the twin: resumed inside the window, the SAME requests ride
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and row["transfers"][0]["status"] == "moved"
    assert any("HARV credited $50.00" in x for x in row["notes"]) and r.m.state["requests"] == []
    sound(r)


def test_a01b_a_halt_before_the_buys_are_sized_sends_no_buy(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    real = r.venue.spot_ex

    def spot(symbol):
        run = r.m.state.get("run")
        if run and all(o.get("applied") for o in run["plan"]["sells"]):
            r.m.halt("operator halt")                  # every sell is booked; the buy quotes are being re-read
        return real(symbol)
    r.venue.spot_ex = spot
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    new = r.orders()[n:]
    assert new and all(q < 0 for _, q in new)          # the sells went; not one buy
    r.tick("15:55:10", day=D2)
    assert r.m.state["last_run"]["outcome"] == "aborted" and all(q < 0 for _, q in r.orders()[n:])
    sound(r)


def test_a01c_a_resume_during_a_flatten_stops_the_flatten(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.m.halt("KILL", flatten=True)
    n0 = len(r.venue.placed)
    answer = {}

    def resume_once(symbol, qty):
        if not answer:                                 # /resume lands while the FIRST flatten sell is out
            answer.update(r.m.resume())
    spy(r, resume_once)
    r.tick("15:56:00")
    sold = [(s, q) for s, q, _ in r.venue.placed[n0:]]
    assert answer.get("flatten_cancelled") is True     # what /resume told the operator ...
    assert len(sold) == 1                              # ... is what happened: one sell was out, no other followed
    assert len(r.m.book.positions()) == len(held) - 1 and r.m.halt_state()["flatten_done"] is True
    assert r.m.halt_state()["halted"] is False
    sound(r)


# =============================================================================================== A-03
def test_a03a_kill_resume_kill_never_sells_the_same_shares_twice(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.hold.update(held)                          # the flatten's sells rest (a halt, a thin open, a holiday)
    h1 = r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    assert sorted(s for s, _ in r.orders()[5:]) == sorted(held) and r.m.book.positions() == held
    r.m.resume()                                       # the operator thinks again ...
    r.clock.now += timedelta(seconds=2)
    h2 = r.m.halt("KILL", flatten=True)                # ... and kills again, before the loop's next pass
    assert h2["flatten_id"] == h1["flatten_id"] and h2["flatten_cancelled"] is False      # the SAME flatten, un-cancelled
    r.tick("15:56:04")
    r.venue.hold.clear()
    for sym in held:
        r.venue.release(sym)                           # the venue fills whatever rests
    r.tick("15:56:10")
    r.tick("15:56:20")
    assert r.venue.positions_snapshot()["stocks"] == {} and r.m.book.positions() == {}
    assert sorted(s for s, _ in r.orders()[5:]) == sorted(held)        # each symbol sold exactly once
    assert r.m.halt_state()["flatten_done"] is True
    sound(r)


def test_a03a_a_second_kill_while_the_cancel_is_already_being_settled_waits_for_it(tmp_path):
    """the loop saw the resume first and is cancelling the resting sells when the second kill lands:
    the next round is built only from what is left once every order of the first is booked"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.hold.update(held)
    r.venue.partial["BIL"] = 100                       # one of them fills 100 as its cancel lands
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    r.m.resume()
    r.tick("15:56:02")                                 # the cancels go out and are booked ...
    assert r.m.halt_state()["flatten_done"] is True and r.m.book.positions()["BIL"] == held["BIL"] - 100
    r.venue.hold.clear()
    r.m.halt("KILL", flatten=True)                     # ... then the operator kills again: a NEW flatten
    r.tick("15:56:10")
    assert r.venue.positions_snapshot()["stocks"] == {} and r.m.book.positions() == {}
    sold = {sym: 0 for sym in held}                    # what was really sold, in all, is exactly what was held
    for sym, _, cid in r.venue.placed[5:]:
        sold[sym] += r.venue._orders[r.venue._by_client[cid]].get("filled_qty", 0)
    assert sold == held
    sound(r)


def test_a03b_resume_then_halt_never_orphans_the_flattens_working_sells(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.hold.update(held)
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")                                 # five SELLs rest at the venue
    r.m.resume()                                       # 'a flatten not yet finished is cancelled'
    h = r.m.halt("operator halt")                      # /mirror/halt: 'positions are kept'
    assert h["flatten"] is True and h["flatten_cancelled"] is True     # the cancelled record is CARRIED OVER
    r.tick("15:56:05")
    assert [o for o in r.venue._orders.values() if o["status"] == "working"] == []     # cancelled at the venue
    assert r.m.book.positions() == held and all(o["applied"] for o in r.m.state["flatten"]["orders"])
    assert r.m.halt_state()["halted"] is True and r.m.halt_state()["flatten_done"] is True
    sound(r)


def test_a03_the_states_flatten_is_settled_even_when_the_halt_file_forgot_it(tmp_path, monkeypatch):
    """the STATE's flatten orders are the truth for what is in flight, whatever the halt file says: a
    halt whose write failed is forgotten by a restart, the five resting sells are not"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.hold.update(held)
    real = mm.atomic_write
    monkeypatch.setattr(mm, "atomic_write", lambda p, o: (_ for _ in ()).throw(OSError(30, "ro")) if p.endswith(".halt") else real(p, o))
    assert r.m.halt("KILL", flatten=True)["persisted"] is False
    r.tick("15:56:00")
    monkeypatch.setattr(mm, "atomic_write", real)
    r.boot()                                           # the restart forgets the kill ...
    assert r.m.halt_state() == {}
    assert len([o for o in r.venue._orders.values() if o["status"] == "working"]) == 5
    r.tick("15:56:30")                                 # ... the loop still finds five unbooked flatten orders
    assert [o for o in r.venue._orders.values() if o["status"] == "working"] == []
    assert r.m.book.positions() == held and r.m.state["last_session"] == DAY
    r.venue.hold.clear()
    h = r.m.halt("KILL", flatten=True)                 # a new kill builds a new flatten, never over an unbooked one
    r.tick("15:56:40")
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    assert r.m.state["flatten"]["id"] == h["flatten_id"]
    sound(r)


# =============================================================================================== A-21
def test_a21_a_refused_flatten_sell_is_sold_again_in_the_next_round(tmp_path):
    r = invested(tmp_path)
    r.venue.reject.add("SOXL")                         # the venue refuses one flatten sell
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    r.venue.reject.clear()                             # ... a transient: it is accepted a moment later
    ticks(r, 3, 10)
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    soxl = [(q, cid) for s, q, cid in r.venue.placed if s == "SOXL" and q < 0]
    assert len(soxl) == 2 and soxl[0][1] != soxl[1][1] and "-r2-" in soxl[1][1]        # a NEW id per round
    assert r.m.halt_state()["flatten_done"] is True and r.m.next_wait() is None
    assert any("flatten round 2 (" in a and "open-session minutes used" in a for a in r.red())
    assert r.m.halt_state()["account_flat"] is True
    sound(r)


def test_a21_the_flatten_gives_up_loudly_after_thirty_minutes_of_open_session(tmp_path):
    """round 2 (N-08): the bound was five rounds five seconds apart - about 25 s, and a venue that
    refused for a minute ended the /kill with the book still on. It is OPEN-session time now (30
    minutes), with the rounds further and further apart: 5 s, 15 s, 60 s, then every 5 minutes."""
    r = invested(tmp_path)
    soxl = r.m.book.positions()["SOXL"]
    r.venue.reject.add("SOXL")                         # refused every time
    r.m.halt("KILL", flatten=True)
    t0 = r.clock.now = at("10:00:00", D2)
    sent, gave_up = [], None
    for _ in range(400):
        n = len(r.venue.placed)
        r.m.tick(r.venue)
        if any(sym == "SOXL" for sym, _, _ in r.venue.placed[n:]):
            sent.append((r.clock.now - t0).total_seconds())
        if r.m.halt_state().get("flatten_done"):
            gave_up = (r.clock.now - t0).total_seconds()
            break
        r.clock.now += timedelta(seconds=5)
    assert sent == [0, 5, 20, 80, 380, 680, 980, 1280, 1580]                   # the gaps widen: 5, 15, 60, then 300 s
    # round 3 (C-10): the budget counts open time BETWEEN rounds only. Each of the 9 rounds has one 5 s
    # step in which its refused order is still unbooked, and that step is not counted: 1800 + 9 x 5.
    assert mm.FLATTEN_OPEN_BUDGET_S == 1800.0 and gave_up == 1800.0 + 9 * 5    # ... for 30 minutes of open session
    assert [q for s, q in r.orders() if s == "SOXL" and q < 0] == [-soxl] * 9
    assert r.m.book.positions() == {"SOXL": soxl}
    done = [a for a in r.red() if "GAVE UP after 30 minutes of open session and 9 rounds" in a]
    assert len(done) == 1 and "flatten NOT complete" in done[0] and "STILL HELD" in done[0] and "/kill again" in done[0]
    assert len([a for a in r.red() if "flatten round" in a]) == 8              # one red alert per extra round
    assert r.m.halt_state()["account_flat"] is False and r.m.next_wait() is None
    r.venue.reject.clear()
    assert "account_flat" not in r.m.halt("KILL", flatten=True)                # the twin: a new /kill arms a new flatten
    ticks(r, 2, 5)
    assert r.m.book.positions() == {} and r.m.halt_state()["account_flat"] is True
    sound(r)


def test_n08_a_refusal_that_lasts_a_minute_no_longer_ends_the_kill(tmp_path):
    """the reviewer's scenario: the gateway refuses every order for a minute, then takes them again"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.reject.update(held)
    r.m.halt("KILL", flatten=True)
    r.clock.now = at("10:00:00", D2)
    for i in range(40):
        r.m.tick(r.venue)
        r.clock.now += timedelta(seconds=5)
        if i == 11:
            r.venue.reject.clear()                     # +60 s: the venue takes orders again
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    assert r.m.halt_state()["flatten_done"] is True and any("flatten complete" in a for a in r.alerts)
    sound(r)


def test_n08_only_open_session_time_counts_towards_the_bound(tmp_path):
    """a flatten that starts ten minutes before the close has used ten minutes when the next session
    opens - the night adds nothing - and carries on there"""
    r = invested(tmp_path)
    soxl = r.m.book.positions()["SOXL"]
    r.venue.reject.add("SOXL")
    r.m.halt("KILL", flatten=True)
    r.clock.now = at("15:50:00")
    while r.clock.now < at("16:00:00"):
        r.m.tick(r.venue)
        r.clock.now += timedelta(seconds=5)
    used = r.m.state["flatten"]["open_s"]
    # round 3 (C-10): 5 rounds went out in these ten minutes; the 5 s step in which each one's refused
    # order was still unbooked is not counted
    assert 565 <= used <= 580 and not r.m.halt_state().get("flatten_done")
    for hms in ("16:00:30", "18:00:00", "23:00:00"):   # the session is shut: nothing is sent, nothing is counted
        r.tick(hms)
    r.tick("03:00:00", day=D2)
    assert r.m.state["flatten"]["open_s"] == used and r.m.halt_state().get("flatten_done") is False
    n = len(r.venue.placed)
    r.venue.reject.clear()
    r.tick("09:30:05", day=D2)                         # the next open: the next round goes out at once
    r.tick("09:30:10", day=D2)
    assert [(s, q) for s, q, _ in r.venue.placed[n:]] == [("SOXL", -soxl)] and r.m.book.positions() == {}
    assert r.m.state["flatten"]["open_s"] < used + 60
    sound(r)


def test_n08_a_flatten_queued_into_a_weekday_holiday_sends_nothing_until_the_next_session(tmp_path):
    """a halted book never refreshes the brain's clock, so the kill path falls back to its own: with
    the SERVICE's trading-day calendar (passed in by build) a weekday holiday is not a session"""
    from datetime import date
    holiday = date(2026, 11, 11)

    def rig(path, calendar):
        os.makedirs(path, exist_ok=True)
        r = live_rig(path, poll_s=1e9)
        r.trading_day = calendar
        r.boot()
        r.tick("15:55:05")
        assert r.m.state["last_run"]["outcome"] == "traded"
        r.m.halt("KILL", flatten=True)
        r.tick("17:00:00")                             # queued: the session is shut
        return r
    r = rig(tmp_path / "cal", lambda d: d.weekday() < 5 and d != holiday)
    n = len(r.venue.placed)
    assert r.m.next_wait() == pytest.approx((at("09:30:00", D3) - at("17:00:00")).total_seconds())      # not tomorrow's 09:30
    r.tick("10:00:00", day=D2)                         # the holiday, mid-morning
    assert r.venue.placed[n:] == [] and r.m.book.positions() != {} and not r.m.halt_state().get("flatten_done")
    r.tick("09:30:05", day=D3)
    assert len(r.venue.placed) == n + 5 and r.m.book.positions() == {}
    sound(r)
    t = rig(tmp_path / "none", None)                   # the twin: without the calendar every weekday is a session
    n = len(t.venue.placed)
    assert t.m.next_wait() == pytest.approx((at("09:30:00", D2) - at("17:00:00")).total_seconds())
    t.tick("10:00:00", day=D2)
    assert len(t.venue.placed) == n + 5
    boom = rig(tmp_path / "boom", lambda d: 1 / 0)     # a calendar that raises is not a reason to sit on a kill
    n = len(boom.venue.placed)
    boom.tick("10:00:00", day=D2)
    assert len(boom.venue.placed) == n + 5


def test_a21_a_partial_flatten_fill_at_the_close_is_finished_at_the_next_open(tmp_path):
    r = invested(tmp_path)
    tecl = r.m.book.positions()["TECL"]
    r.venue.hold.add("TECL")
    r.m.halt("KILL", flatten=True)
    r.tick("15:59:30")                                 # TECL's sell rests
    rec = next(o for o in r.venue._orders.values() if o["symbol"] == "TECL" and o["qty"] < 0)
    r.venue._fill(rec, 40)                             # 40 fill; the DAY order dies at the close
    rec["status"] = "cancelled"
    r.venue.hold.clear()
    r.tick("16:00:30")
    assert r.m.book.positions() == {"TECL": tecl - 40} and r.m.halt_state()["flatten_done"] is False
    assert [q for s, q in r.orders() if s == "TECL" and q < 0] == [-tecl]      # nothing is sent into a shut session
    r.tick("09:30:30", day=D2)
    assert r.m.book.positions() == {} and [q for s, q in r.orders() if s == "TECL" and q < 0] == [-tecl, -(tecl - 40)]
    sound(r)


# =============================================================================================== A-02
def test_a02_a_dead_acknowledged_order_no_longer_blocks_the_kill(tmp_path):
    """the reviewer's scenario as written: with today's order history COMPLETE, 'no record' of an
    acknowledged order is proof it died unfilled (decision D3), so the run closes and the kill sells
    everything"""
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")                           # acknowledged, working, never fills
    r.tick("15:55:05")
    cid = f"mirror-{DAY}-B-TECL"
    r.venue.forgotten.add(cid)                         # the DAY order died unfilled across a gateway reconnect
    r.tick("15:59:05")
    assert r.m.state["run"] is None and r.m.state["last_run"]["orders"][-1]["filled"] == 0
    assert "complete order history" in next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")["how"]
    r.m.halt("KILL", flatten=True)
    ticks(r, 3, 5)
    assert r.m.book.positions() == {} and r.m.halt_state()["flatten_done"] is True


def unresolved_rig(tmp_path):
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")
    r.tick("15:55:05")
    cid = f"mirror-{DAY}-B-TECL"
    r.venue.forgotten.add(cid)
    r.venue.history_ok = False                         # ... on a gateway that cannot prove it never filled
    r.tick("15:59:05")
    assert r.m.state["run"]["orders"][cid].get("stuck")
    return r, cid


def test_a02_the_kill_flattens_around_an_unresolved_order_and_names_it(tmp_path):
    r, cid = unresolved_rig(tmp_path)
    held = dict(r.m.book.positions())
    assert set(held) == {"BIL", "BOXX", "PULS", "SOXL"}
    n = len(r.orders())
    r.m.halt("KILL", flatten=True)
    r.tick("15:59:10")
    assert sorted(s for s, q in r.orders()[n:]) == sorted(held)        # every OTHER symbol is sold at once
    assert r.m.book.positions() == {} and r.m.state["run"] is not None
    assert any("held back" in a and "TECL" in a and cid in a and "/mirror/resolve" in a for a in r.red())
    assert r.m.halt_state()["flatten_done"] is True    # nothing of TECL is in the book: the flatten is done
    assert r.m.view()["unresolved"][0]["id"] == cid and r.m.health()["unresolved"] is True
    sound(r)


def test_a02_resolve_books_the_order_the_operator_states_and_the_flatten_takes_it(tmp_path):
    r, cid = unresolved_rig(tmp_path)
    qty = next(q for s, q, c in r.venue.placed if c == cid)
    r.venue._positions["TECL"] = qty                   # in truth it FILLED (the account holds the shares)
    r.venue.cash -= qty * 100.25 + 1.0
    r.m.halt("KILL", flatten=True)
    r.tick("15:59:10")
    assert r.m.halt_state()["flatten_done"] is True and r.m.book.positions() == {}
    req = r.m.request_resolve(cid, qty, 100.25, 1.0, "IBKR activity statement")
    assert req["kind"] == "resolve"
    r.tick("15:59:20")
    assert r.m.state["run"] is None                    # the run closed (aborted by the kill)
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert (tecl["filled"], tecl["price"]) == (qty, 100.25) and "resolved by the operator" in tecl["how"]
    assert r.m.book.positions() == {"TECL": qty}
    assert r.m.book.cash() == pytest.approx(r.venue.cash, abs=0.01)
    assert any("RESOLVED by the operator" in a for a in r.alerts)
    assert [x for x in r.journal() if x["event"] == "resolve" and x["order"] == cid]
    r.venue.hold.clear()
    r.m.halt("KILL", flatten=True)                     # the flatten was done before the shares were known: kill again
    r.tick("15:59:30")
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}


def test_a02_resolve_is_refused_where_it_would_be_a_guess(tmp_path):
    r, cid = unresolved_rig(tmp_path)
    for bad in ((cid, -1, None), (cid, 1.5, 10.0), (cid, 5, None), (cid, 5, 0), ("", 0, None), (cid, "x", None)):
        with pytest.raises(ValueError):
            r.m.request_resolve(*bad)
    with pytest.raises(ValueError):
        r.m.request_resolve(cid, 0, None, -1.0)
    r.m.request_resolve("mirror-2026-11-10-B-NOPE", 0)             # no such unbooked order
    r.m.request_resolve(cid, 500, 100.0)                           # more than the order asked for
    r.tick("15:59:10")
    assert r.m.state["run"]["orders"][cid]["state"] != "booked"
    assert len([a for a in r.red() if "resolve request" in a and "REFUSED" in a]) == 2
    r.venue.forgotten.clear()                          # the venue answers again: it is WORKING
    r.venue.cancel_raises = True
    r.m.request_resolve(cid, 0, note="it is gone, trust me")
    r.tick("15:59:20")
    assert r.m.state["run"]["orders"][cid]["state"] != "booked"
    assert any("still holds order" in a and "WORKING" in a for a in r.red())
    r.venue.cancel_raises = False
    r.tick("15:59:30")                                 # ... and the venue itself then settles it
    assert r.m.state["run"] is None and r.m.state["requests"] == []


def test_a02_an_unresolved_order_is_said_once_a_day_and_the_lost_sessions_are_recorded(tmp_path):
    r, cid = unresolved_rig(tmp_path)
    said = lambda: [a for a in r.red() if "UNRESOLVED" in a and cid in a]      # noqa: E731
    assert len(said()) == 1
    ticks(r, 20, 60)
    assert len(said()) == 1                            # not once a tick
    r.brain.make = lambda now: payload(now, session=D2)
    for hms in ("09:35:00", "12:00:00", "15:55:05", "15:59:30"):
        r.tick(hms, day=D2)
    assert len(said()) == 2                            # the next day: said again
    row = r.m.state["history"][-1]                     # ... and the session it cost is a recorded NO TRADE
    assert (row["session"], row["outcome"]) == (D2, "skipped") and cid in row["reason"]
    assert r.m.state["run"]["session"] == DAY
    r.m.request_resolve(cid, 0, note="expired unfilled, per the activity statement")
    r.tick("16:10:00", day=D2)
    assert r.m.state["run"] is None and r.m.state["last_session"] == D2        # never moves backwards
    r.venue.hold.clear()
    r.brain.make = lambda now: payload(now, session=D3)
    r.tick("15:55:05", day=D3)
    assert r.m.state["last_run"]["session"] == D3 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_d3_adjust_repairs_a_share_count_divergence(tmp_path):
    r = invested(tmp_path)
    tecl = r.m.book.positions()["TECL"]
    r.venue._positions["TECL"] -= 8                    # eight TECL were sold by hand at 99.00
    r.venue.cash += 8 * 99.0
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("10:00:00", day=D2)                         # the morning pre-check says so, long before 15:58
    assert any("today's decision will be refused unless fixed" in a and "TECL" in a for a in r.red())
    for bad in (("KMLM", "TECL", 0, 0.0, "x"), ("KMLM", None, -8, 0.0, "x"), ("NOPE", "TECL", -8, 0.0, "x"),
                ("KMLM", "TECL", -8, 0.0, ""), ("KMLM", "TECL", 1.5, 0.0, "x"), ("KMLM", "TECL", -8, float("nan"), "x")):
        with pytest.raises(ValueError):
            r.m.request_adjust(*bad)
    r.m.request_adjust("KMLM", "TECL", -500, 0.0, "typo")              # more than the sleeve holds
    r.tick("10:01:00", day=D2)
    assert any("adjust request" in a and "REFUSED" in a for a in r.red()) and r.m.book.positions()["TECL"] == tecl
    r.m.request_adjust("KMLM", "TECL", -8, 8 * 99.0, "sold by hand 2026-11-11, statement line 4",
                       force=True)   # V4b D1: cash by hand at a full cap is never netted against shares
    r.tick("10:02:00", day=D2)
    assert r.m.book.sleeves["KMLM"].shares["TECL"] == tecl - 8 and r.m.state["requests"] == []
    assert any("ADJUSTED by the operator" in a for a in r.alerts)
    assert [x for x in r.journal() if x["event"] == "adjust" and x["shares"] == -8]
    r.tick("15:55:05", day=D2)
    assert r.m.state["last_run"]["session"] == D2 and r.m.state["last_run"]["outcome"] != "skipped"
    sound(r)


def test_d3_an_adjustment_waits_for_the_open_run(tmp_path):
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")
    r.tick("15:55:05")
    assert r.m.state["run"] is not None
    cash0 = r.m.book.sleeves["HG"].cash
    r.m.request_adjust("HG", None, 0, -5.0, "wire fee")
    r.tick("15:55:20")
    assert r.m.book.sleeves["HG"].cash == cash0 and len(r.m.state["requests"]) == 1    # queued, not applied
    r.venue.release("TECL")
    r.tick("15:55:40")
    r.tick("15:55:45")
    assert r.m.state["run"] is None and r.m.book.sleeves["HG"].cash == pytest.approx(cash0 - 5.0)
    assert r.m.state["requests"] == []


def test_d3_an_adjustment_keeps_the_paper_account_equal_to_the_paper_book(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    bil = d.m.book.positions()["BIL"]
    d.m.request_adjust("HG", "BIL", -15, 15 * 91.5, "test")
    d.tick("15:56:00")
    assert d.m.book.positions()["BIL"] == bil - 15 and d.m._dry.stock_position("BIL") == bil - 15
    d.brain.make = lambda now: payload(now, session=D2)
    d.tick("15:55:05", day=D2)
    assert d.m.state["last_run"]["session"] == D2 and d.m.state["last_run"]["outcome"] != "skipped"
    sound(d)


# =============================================================================================== A-20
def test_a20_a_flatten_queued_off_hours_does_not_spin_the_loop(tmp_path):
    r = invested(tmp_path)
    r.m.halt("KILL", flatten=True)
    assert r.m.next_wait() == 5.0                      # in the session: every 5 s
    r.tick("17:00:00")                                 # Tuesday after the close
    waits = []
    for day, hms in ((DAY, "23:00:00"), ("2026-11-14", "12:00:00"), ("2026-11-15", "12:00:00")):
        r.clock.now = at(hms, day)                     # ... through the night and a weekend
        waits.append(r.m.next_wait())
    assert waits == [300.0, 300.0, 300.0]              # the poll interval, never 5 s
    r.clock.now = at("09:28:00", D2)
    assert r.m.next_wait() == pytest.approx(120.0)     # ... and exactly the time to the next open when that is nearer
    r.clock.now = at("09:30:00", D2)
    assert r.m.next_wait() == 5.0
    r.tick("09:30:05", day=D2)
    assert r.m.book.positions() == {} and r.m.next_wait() is None


# =============================================================================================== A-04
def break_disk(monkeypatch, match):
    real = mm.atomic_write

    def broken(path, obj):
        if match(path):
            raise OSError(28, "No space left on device")
        return real(path, obj)
    monkeypatch.setattr(mm, "atomic_write", broken)
    return real


def test_a04a_nothing_reaches_the_venue_while_the_state_file_cannot_be_written(tmp_path, monkeypatch):
    r = live_rig(tmp_path)
    state = r.m.cfg.state_path
    before = disk(r)
    real = break_disk(monkeypatch, lambda p: p == state)        # the volume fills up before the decision
    r.tick("15:55:05")
    ticks(r, 40, 2)                                            # the loop comes back every few seconds
    now = disk(r)
    assert now["seq"] == before["seq"] and now["run"] is None  # the disk knows nothing of today ...
    assert r.orders() == []                                    # ... and so does the venue
    assert r.m.state["run"] is None and r.m.book.to_dict() == mc.Book.from_dict(before["book"]).to_dict()
    assert r.m.health()["save_latched"] is True and r.m.view()["save_latched"]["error"]
    said = [a for a in r.red() if "CANNOT BE WRITTEN" in a]
    assert len(said) == 1 and r.m.next_wait() == mm.LATCH_RETRY_S          # said, rate-limited, and retried
    r.clock.now += timedelta(seconds=mm.LATCH_ALERT_EVERY_S + 1)
    r.m.tick(r.venue)
    assert len([a for a in r.red() if "CANNOT BE WRITTEN" in a]) == 2      # ... and said again while it fails
    monkeypatch.setattr(mm, "atomic_write", real)              # the twin: the disk is back
    r.tick("15:57:00")
    assert r.m._latched is None and r.m.state["last_run"]["outcome"] == "traded" and disk(r)["last_session"] == DAY
    assert any("written again" in a for a in r.alerts)
    sound(r)


def test_a04a_a_save_that_fails_mid_run_stops_the_rest_of_the_plan(tmp_path, monkeypatch):
    r = live_rig(tmp_path)
    state = r.m.cfg.state_path
    box = {"broken": False, "armed": True}
    break_disk(monkeypatch, lambda p: p == state and box["broken"])

    def after_first(symbol, qty):
        if box["armed"]:
            box["broken"], box["armed"] = True, False          # the disk dies while the first order is at the venue
    spy(r, after_first)
    r.clock.interrupt = True                                   # (each tick is one pass: the clock stays inside the window)
    r.tick("15:55:05")
    ticks(r, 10, 2)
    assert len(r.orders()) == 1                                # no other order of the run was placed
    recs = r.m.state["run"]["orders"]
    first = r.orders()[0][0]
    assert recs[f"mirror-{DAY}-B-{first}"]["state"] == "booked"            # memory is ahead of the disk ...
    others = [v["state"] for k, v in recs.items() if not k.endswith(first)]
    assert others and set(others) == {"new"}                   # ... and 'intent' never stands without its write-ahead
    assert disk(r)["run"]["orders"][f"mirror-{DAY}-B-{first}"]["state"] == "intent"
    box["broken"] = False                                      # the twin: the save works again -> the book carries on
    r.clock.interrupt = False
    r.tick("15:55:40")
    assert r.m.state["last_run"]["outcome"] == "traded" and len(r.orders()) == 5 and r.m._latched is None
    assert mc.Book.from_dict(disk(r)["book"]).to_dict() == r.m.book.to_dict()
    sound(r)


def test_a04b_a_failing_inbox_can_never_stop_the_kill(tmp_path, monkeypatch):
    r = invested(tmp_path)
    r.m.request_credit("HARV", -1.0, "fee")                    # anything in the inbox
    inbox = r.m._inbox_path()
    r.tick("15:56:00")                                         # drained into the state ...
    assert r.m.state["requests"]
    r.m.request_credit("HARV", -2.0, "fee")                    # ... and one more arrives
    break_disk(monkeypatch, lambda p: p == inbox)              # the inbox alone cannot be rewritten
    n = len(r.orders())
    r.m.halt("KILL", flatten=True)
    ticks(r, 3, 5)
    assert len(r.orders()) == n + 5 and r.m.book.positions() == {}         # the flatten ran all the same
    assert any("inbox could not be processed" in a for a in r.red())
    assert len(r.m.state["requests"]) == 2                     # the request itself was read: nothing is lost


def test_a04_the_flatten_goes_out_under_the_latch_and_says_its_record_is_not_on_disk(tmp_path, monkeypatch):
    r = invested(tmp_path)
    state = r.m.cfg.state_path
    real = break_disk(monkeypatch, lambda p: p == state)
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}     # the emergency stop is not held
    assert any("NO record on disk" in a for a in r.red()) and r.m._latched
    assert disk(r)["flatten"] is None                          # (the disk indeed knows nothing of it)
    monkeypatch.setattr(mm, "atomic_write", real)
    r.tick("15:56:20")
    assert r.m._latched is None and mc.Book.from_dict(disk(r)["book"]).positions() == {}
    sound(r)


# =============================================================================================== A-05
def test_a05a_a_tape_above_the_brains_bar_never_makes_the_account_borrow(tmp_path):
    r = live_rig(tmp_path)                                     # $100,000 in the account, four sleeves in cash
    for sym in PX:
        r.venue.quotes[sym] = round(PX[sym] * 1.012, 2)        # the tape moved 1.2% since the brain's bar:
    r.tick("15:55:05")                                         # INSIDE the 1.5% band, so every symbol passes
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and not row["dropped"]
    assert r.venue.cash >= 0 and all(s.cash >= 0 for s in r.m.book.sleeves.values())
    for o in row["orders"]:                                    # each buy: a LIMIT at the venue's quote x 1.005, on the grid,
        q = r.venue.quotes[o["symbol"]]                        # and sized so quantity x limit fits the cash
        assert o["limit"] == pytest.approx(int(q * 1.005 * 100 + 1e-9) / 100) and o["price"] <= o["limit"]
        assert r.venue.limits[o["id"]] == o["limit"]
    spent = {}
    for o in row["orders"]:
        for name, n in o["split"].items():
            spent[name] = spent.get(name, 0.0) + n * o["limit"]
    for name, cost in spent.items():
        assert cost <= row["sleeves"][name]["pre_equity"] + 1e-6, name
    sound(r)


def test_a05a_a_price_that_runs_away_after_the_quote_is_not_chased(tmp_path):
    r = live_rig(tmp_path)
    for sym in PX:
        r.venue.fill_px[sym] = round(PX[sym] * 1.02, 2)        # the market is 2% up when the orders arrive
    r.tick("15:55:05")
    assert r.m.state["run"] is not None and r.venue.cash == 100_000.0      # nothing filled: every limit rests
    r.tick("15:59:01")
    row = r.m.state["last_run"]
    assert all(o["filled"] == 0 and "cancelled" in o["how"] for o in row["orders"]) and len(row["orders"]) == 5
    assert r.m.book.cash() == pytest.approx(100_000.0) and r.venue.cash == 100_000.0
    sound(r)
    r.venue.fill_px.clear()                                    # the twin: the next session, an ordinary tape
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)
    assert all(o["filled"] == o["qty"] for o in r.m.state["last_run"]["orders"])
    sound(r)


def test_a05_the_buy_quote_is_read_again_and_a_bad_one_falls_back(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}, SLEEVE={"SPY": 1.0}), session=D2)
    r.venue.quotes["TQQQ"] = 80.40                             # the plan's cross-check reads 80.40 (0.5% over the bar)
    real = r.venue.spot_ex
    seen = {"SPY": 0}

    def spot(symbol):
        run = r.m.state.get("run")
        buying = bool(run and all(o.get("applied") for o in run["plan"]["sells"]))
        if buying and symbol == "TQQQ":
            return 80.56, "live"                               # ... and, once the sells are booked, 80.56
        if buying and symbol == "SPY":
            seen["SPY"] += 1
            raise RuntimeError("no market price for SPY")      # SPY's re-read fails
        return real(symbol)
    r.venue.spot_ex = spot
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    tq = next(o for o in row["orders"] if o["symbol"] == "TQQQ")
    sp = next(o for o in row["orders"] if o["symbol"] == "SPY")
    assert tq["limit"] == 80.96                                # floor(80.56 x 1.005 = 80.9628): the FRESH quote
    assert seen["SPY"] == 1 and sp["limit"] == 603.0           # fallback: max(brain 600, plan-time quote 600) x 1.005
    assert tq["ref"] == 80.0 and sp["ref"] == 600.0            # the decision price stays the reference
    sound(r)


def test_a05_a_quote_that_left_the_band_since_the_plan_is_not_followed(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=D2)
    real = r.venue.spot_ex

    def spot(symbol):
        run = r.m.state.get("run")
        if symbol == "TQQQ" and run and all(o.get("applied") for o in run["plan"]["sells"]):
            return 86.0, "live"                                # a spike, or a bad print: 7.5% over the bar
        return real(symbol)
    r.venue.spot_ex = spot
    r.venue.fill_px["TQQQ"] = 86.0
    r.tick("15:55:05", day=D2)
    r.tick("15:59:01", day=D2)
    tq = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TQQQ")
    assert tq["limit"] == 80.4 and tq["filled"] == 0           # the limit stays at the checked price; nothing is chased
    assert r.m.book.sleeves["HG"].cash > 28_000 and r.venue.cash >= 0
    sound(r)


def test_a05_paper_buys_are_limits_at_the_reference_plus_the_cushion_filled_at_the_reference(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    log = [e for e in d.m._dry.log if e["action"] == "place_limit_order"]
    assert len(log) == 5 and not [e for e in d.m._dry.log if e["action"] == "place_stock_order"]
    for e in log:
        ref = PX[e["symbol"]]
        assert e["fill_price"] == ref and e["status"] == "filled"
        assert e["limit_price"] == pytest.approx(int(ref * 1.005 * 100 + 1e-9) / 100)
    for o in d.m.state["last_run"]["orders"]:
        assert o["limit"] == pytest.approx(o["ref"] * (1 + d.m.cfg.core.buy_cushion)) and o["price"] == o["ref"]
    sound(d)


def test_a05b_a_sleeve_in_debt_is_repaired_the_next_session(tmp_path):
    r = invested(tmp_path)
    k = r.m.book.sleeves["KMLM"]
    held = dict(k.shares)
    fee = round(k.cash + 400.0, 2)                             # a fee larger than the sleeve's cash: it is $400 in debt
    r.venue.cash -= fee
    r.m.request_credit("KMLM", -fee, "fee", force=True)   # (a queued debit clears the cash gate it would else be locked out
                                                          # by; one that takes the sleeve into debt needs force - N-01)
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)
    assert r.m.state["last_run"]["session"] == D2
    row = r.m.state["last_run"]["sleeves"]["KMLM"]
    assert row["action"] == "trade" and "debt" in row["reason"]            # in debt: never 'inside the corridor'
    assert k.cash >= 0 and sum(k.shares.values()) < sum(held.values())     # ... and the trims were not dust
    sound(r)
    t = invested(tmp_path / "twin")                            # the twin: no debt, the threshold sleeve holds
    t.brain.make = lambda now: payload(now, session=D2)
    t.tick("15:55:05", day=D2)
    assert t.m.state["last_run"]["sleeves"]["KMLM"]["action"] == "hold"


# =============================================================================================== A-06
def test_a06a_a_dead_clock_is_never_a_silent_day(tmp_path):
    r = invested(tmp_path)
    r.alerts.clear()
    r.brain.session_fail = "transport"                         # the brain's service is down all of day two
    for hms in ("09:31", "09:36"):
        r.tick(hms, day=D2)
    assert not r.alerts                                        # (five minutes is not yet worth a page)
    r.tick("09:42", day=D2)
    said = [a for a in r.red() if "clock has been unreadable since 09:31" in a]
    assert len(said) == 1                                      # ten minutes of it: said
    for hms in ("12:00", "15:50", "15:55:05", "15:56", "15:57", "15:58", "15:59"):
        r.tick(hms, day=D2)
    assert r.m.state["last_session"] == DAY and len([a for a in r.red() if "clock has been unreadable" in a]) == 1
    r.tick("16:00", day=D2)                                    # the fallback close: a RECORDED no-trade
    row = r.m.state["last_run"]
    assert (row["session"], row["outcome"]) == (D2, "skipped") and "unreadable all session" in row["reason"]
    assert "if today was a session, no trade was made" in row["reason"] and any("NO TRADE" in a for a in r.red())
    r.tick("18:00", day=D2)
    assert len([h for h in r.m.state["history"] if h["session"] == D2]) == 1           # once
    w = Rig(tmp_path / "wk", live=True)                        # the twin: a weekend with the brain down says nothing
    os.makedirs(tmp_path / "wk", exist_ok=True)
    w.brain.session_fail = "transport"
    for hms in ("09:31", "12:00", "16:05"):
        w.tick(hms, day="2026-11-14")
    assert not w.red() and w.m.state["last_session"] is None and w.m.next_wait() is None


def test_a06b_with_the_clock_unknown_the_book_asks_for_the_loop(tmp_path):
    r = Rig(tmp_path, live=True)
    r.brain.session_fail = "transport"                         # down since midnight
    r.tick("08:00")
    assert r.m.next_wait() is None                             # before 09:25 ET: the ordinary cadence
    r.tick("10:00")
    assert r.m.next_wait() == mm.UNKNOWN_WAIT_S == 60.0
    r.tick("15:53:20")
    assert r.m.next_wait() == mm.UNKNOWN_WAIT_LATE_S == 20.0   # from 15:30 ET: every 20 s
    r.tick("16:06:00")
    assert r.m.next_wait() is None
    k = Rig(tmp_path / "k", live=True)                         # the twin: a known session asks for its decision instant
    os.makedirs(tmp_path / "k", exist_ok=True)
    k.tick("15:53:20")
    assert k.m.next_wait() == pytest.approx(65.2)


def test_a06c_a_brain_back_at_1554_is_not_missed(tmp_path):
    r = Rig(tmp_path, live=True)
    r.brain.session_fail = "transport"
    r.tick("15:00")
    r.tick("15:53:20")
    r.brain.session_fail = None                                # the brain is back at 15:54
    for _ in range(8):                                         # the loop does what next_wait() asks of it
        wait = r.m.next_wait()
        assert wait is not None and wait <= 65.2
        r.clock.now += timedelta(seconds=wait)
        r.m.tick(r.venue)
        if r.m.state["last_session"]:
            break
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and r.clock.now < at("15:56:00")
    sound(r)


# =============================================================================================== A-08
def test_a08_the_paper_book_keeps_trading_when_an_engine_goes_live(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")                                         # all four engines on paper, invested
    harv = dict(d.m.book.sleeves["HARV"].shares)
    d.engines = ("HG", "KMLM", "SLEEVE")                       # HARV named in MIRROR_LIVE_ENGINES: redeploy
    d.boot()
    d.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=D2)
    d.tick("15:55:05", day=D2)
    row = d.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded"
    assert d.m._dry.stock_position("PULS") == d.m.book.positions()["PULS"] and harv["PULS"] > 0
    sound(d)


# =============================================================================================== A-09
def test_a09_a_small_transfer_moves_what_was_asked(tmp_path):
    r = invested(tmp_path)
    eq0 = mc.snapshot(r.m.book, PX)["sleeves"]
    r.m.request_transfer("KMLM", "HARV", 300.0, "POLICY op")   # 1% of the sleeve: under the dust floor of every leg
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert row["transfers"][0]["status"] == "moved" and row["transfers"][0]["moved"] == 300.0
    assert row["sleeves"]["KMLM"]["action"] == "trade"         # a transfer-forced plan is exempt from the dust rule
    eq1 = mc.snapshot(r.m.book, PX)["sleeves"]
    assert eq1["KMLM"]["equity"] == pytest.approx(eq0["KMLM"]["equity"] - 300.0, abs=0.01)
    assert eq1["HARV"]["equity"] == pytest.approx(eq0["HARV"]["equity"] + 300.0, abs=0.01)
    assert r.m.book.sleeves["KMLM"].cash >= 0 and r.m.state["requests"] == []
    sound(r)


def test_a09_a_transfer_that_moves_less_than_asked_is_said_and_re_queued(tmp_path):
    r = invested(tmp_path)
    r.m.request_transfer("HG", "HARV", 5_000.0, "POLICY op 3")
    r.brain.make = lambda now: payload(now, session=D2)
    r.venue.reject.add("BIL")                                  # the giver's sell is refused: it raises nothing
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    t = row["transfers"][0]
    assert t["status"] == "partial" and t["moved"] < 200.0
    line = next(n for n in row["notes"] if "transfer" in n)
    assert f"${t['moved']:,.2f} of $5,000.00 moved" in line and "queued again" in line and "try 2 of 3" in line
    assert any("transfer" in a and "queued again" in a for a in r.red())   # ... and the operator is told
    again = r.m.state["requests"]
    assert len(again) == 1 and again[0]["amount"] == pytest.approx(5_000.0 - t["moved"], abs=0.01) and again[0]["tries"] == 2
    r.venue.reject.clear()
    r.brain.make = lambda now: payload(now, session=D3)
    r.tick("15:55:05", day=D3)                                 # the remainder rides the next plan
    assert r.m.state["last_run"]["transfers"][0]["status"] == "moved" and r.m.state["requests"] == []
    eq = mc.snapshot(r.m.book, PX)["sleeves"]
    assert eq["HARV"]["equity"] == pytest.approx(20_000.0, abs=1.0) and eq["HG"]["equity"] == pytest.approx(24_000.0, abs=1.0)
    sound(r)


def test_a09_a_transfer_is_given_up_loudly_after_three_plans(tmp_path):
    r = invested(tmp_path)
    r.m.request_transfer("HG", "HARV", 5_000.0)
    r.venue.reject.add("BIL")
    for day in (D2, D3, D4):
        r.brain.make = lambda now, day=day: payload(now, session=day)
        r.tick("15:55:05", day=day)
    assert r.m.state["requests"] == []
    assert any("was NOT moved after 3 plans: re-submit it" in a for a in r.red())
    assert len([x for x in r.journal() if x["event"] == "transfer_requeued"]) == 2


def test_a09_a_transfer_caught_by_an_aborted_run_is_re_queued(tmp_path):
    r = invested(tmp_path)
    r.m.request_transfer("HG", "HARV", 5_000.0)
    r.brain.make = lambda now: payload(now, session=D2)
    r.venue.hold.add("BIL")                                    # the giver's sell rests ...
    r.tick("15:55:05", day=D2)
    assert r.m.state["run"] is not None
    r.m.halt("operator halt")                                  # ... and the run is aborted under it
    r.tick("15:55:30", day=D2)
    row = r.m.state["last_run"]
    assert row["outcome"] == "aborted" and row["transfers"][0]["status"] == "partial"
    assert any("the run was aborted" in n and "queued again" in n for n in row["notes"])
    assert len(r.m.state["requests"]) == 1 and r.m.state["requests"][0]["kind"] == "transfer"


# =============================================================================================== A-10
def test_a10_a_halt_that_could_not_be_written_says_so(tmp_path, monkeypatch):
    r = invested(tmp_path)
    real = mm.atomic_write

    def broken(path, obj):
        if path.endswith(".halt"):
            raise OSError(30, "Read-only file system")
        return real(path, obj)
    monkeypatch.setattr(mm, "atomic_write", broken)
    h = r.m.halt("KILL", flatten=True)
    assert h["halted"] is True and h["persisted"] is False     # in force in this process, and it SAYS it is not on disk
    assert r.m.halt_state()["halted"] is True
    assert r.m.resume()["persisted"] is False
    monkeypatch.setattr(mm, "atomic_write", real)
    assert r.m.halt("KILL", flatten=True)["persisted"] is True             # the twin
    r.boot()
    assert r.m.halt_state()["halted"] is True


# =============================================================================================== A-12
def held_for(r):
    r.clock.slept.clear()
    t0 = r.clock.now = at("15:55:05")
    r.m.tick(r.venue)
    return (r.clock.now - t0).total_seconds()


def test_a12a_the_blend_refusal_does_not_hold_the_loop(tmp_path):
    r = live_rig(tmp_path, blend_enabled=True)
    assert held_for(r) == 0.0                                  # no retry: nothing inside the window can change it
    row = r.m.state["last_run"]
    assert row["outcome"] == "skipped" and "blend" in row["reason"] and r.m.next_wait() is None
    assert any("today's decision will be refused unless fixed" in a and "blend" in a for a in r.red())     # said at 15:00


def test_a12b_a_book_with_no_capital_does_not_hold_the_loop(tmp_path):
    r = Rig(tmp_path, capital=0.0)                             # MIRROR_ENABLED=true, MIRROR_CAPITAL_USD left at 0
    r.tick("15:00")
    assert held_for(r) == 0.0
    row = r.m.state["last_run"]
    assert row["outcome"] == "skipped" and "no sleeve to trade" in row["reason"] and "no capital configured" in row["reason"]


def test_a12_a_transient_refusal_is_still_retried(tmp_path):
    r = live_rig(tmp_path)
    r.venue.cash_claim = False                                 # the account reports no cash: it can come back
    assert held_for(r) > 100 and r.m.state["last_session"] is None and len(r.clock.slept) > 30
    r.venue.cash_claim = True
    r.tick("15:57:40")
    assert r.m.state["last_run"]["outcome"] == "traded"


# =============================================================================================== A-14
def test_a14_a_rebuilt_plans_new_symbols_are_cross_checked_and_the_book_does_not_halt(tmp_path):
    """the 'cannot happen' guard: the cross-check drops the giver of a transfer, the rebuilt plan
    refuses the transfer, and the taker - at target in SOXL WITH the inflow - now trims SOXL, a symbol
    the first pass never asked the venue about. It used to raise and HALT the book."""
    r = Rig(tmp_path, live=True)
    r.brain.make = lambda now: payload(now, rules={})          # every sleeve daily, for a plain arithmetic
    r.tick("15:00")
    r.tick("15:55:05")
    px2 = dict(PX, SOXL=PX["SOXL"] * 1.06)                     # SOXL +6%: KMLM is overweight in it ...
    k = r.m.book.sleeves["KMLM"]
    per = px2["SOXL"] / ((1 - r.m.cfg.core.cash_reserve_frac) * 0.375)
    amount = round((k.shares["SOXL"] + 0.5) * per - mc.equity(k, px2), 2)  # ... unless exactly this much arrives
    first = mc.build_plan(r.m.book, {n: {"status": "ok", "target": t} for n, t in T1.items()}, px2, D2, r.m.cfg.core,
                          [{"from": "HG", "to": "KMLM", "amount": amount}])
    assert "SOXL" not in r.m._plan_symbols(first)              # (with the inflow the first plan does not touch SOXL)
    r.venue.quotes["SOXL"] = px2["SOXL"]
    r.venue.source["BIL"] = "close"                            # HG's only symbol fails the cross-check today
    r.m.request_transfer("HG", "KMLM", amount, "POLICY op")
    r.brain.make = lambda now: payload(now, prices=px2, session=D2, rules={})
    asked = []
    real = r.venue.spot_ex
    r.venue.spot_ex = lambda sym: (asked.append(sym), real(sym))[1]
    r.tick("15:55:05", day=D2)                                 # HG is out, the transfer is refused, SOXL is trimmed
    assert not r.m.halt_state().get("halted")
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded" and row["sleeves"]["HG"]["action"] == "skip"
    soxl = next(o for o in row["orders"] if o["symbol"] == "SOXL")
    assert soxl["side"] == "SELL" and soxl["filled"] == soxl["qty"]
    assert asked.index("SOXL") > asked.index("TECL")           # asked in a SECOND pass: the rebuilt plan added it
    assert row["transfers"][0]["status"] == "refused" and any("REFUSED" in a and "re-submit" in a for a in r.red())
    sound(r)


def test_a14_a_plan_that_keeps_adding_unchecked_symbols_skips_the_session(tmp_path, monkeypatch):
    r = invested(tmp_path)
    r.m.request_transfer("HG", "HARV", 1000.0)
    r.tick("15:56:00")
    r.brain.make = lambda now: payload(now, session=D2)
    k = {"n": 0}

    def growing(plan):                                         # a plan that never converges
        k["n"] += 1
        return {f"X{k['n']}"}
    monkeypatch.setattr(r.m, "_plan_symbols", growing)
    cash = r.m.book.cash()
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert not r.m.halt_state().get("halted")                  # a NO TRADE, not a halt
    assert row["outcome"] == "skipped" and "venue cross-check had not seen" in row["reason"]
    assert len(r.m.state["requests"]) == 1 and r.m.book.cash() == cash     # the transfer is still queued


def test_a14_any_failure_inside_the_plan_restores_the_queued_requests(tmp_path, monkeypatch):
    r = invested(tmp_path)
    r.venue.cash += 10.0
    r.m.request_transfer("HG", "HARV", 1000.0)
    r.m.request_credit("HARV", 10.0, "interest")
    r.tick("15:56:00")
    before = r.m.book.to_dict()
    r.brain.make = lambda now: payload(now, session=D2)
    real = mc.build_plan
    monkeypatch.setattr(mc, "build_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r.tick("15:55:05", day=D2)
    assert "boom" in (r.m.last_error or "") and r.m.state["run"] is None
    assert sorted(q["kind"] for q in r.m.state["requests"]) == ["credit", "transfer"]      # memory == disk
    assert r.m.book.to_dict() == before and sorted(q["kind"] for q in disk(r)["requests"]) == ["credit", "transfer"]
    monkeypatch.setattr(mc, "build_plan", real)
    r.tick("15:55:20", day=D2)
    assert r.m.state["last_run"]["transfers"][0]["status"] == "moved" and r.m.state["requests"] == []
    sound(r)


# =============================================================================================== A-16
def test_a16_an_unreadable_executed_quantity_is_unresolved_never_zero(tmp_path):
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")
    r.venue.partial["TECL"] = 40                               # 40 shares fill as the cancel lands
    real_result = r.venue._order_result

    def bare(rec):                                             # a cancelled row can lack the executions it carries
        out = real_result(rec)
        if rec["status"] == "cancelled":
            out.pop("filled_qty", None)
        return out
    r.venue._order_result = bare
    real_fills = r.venue.stock_order_fills

    def boom(cid):
        raise RuntimeError("reqExecutions timed out after 20s - cycle fails closed")
    r.venue.stock_order_fills = boom
    r.tick("15:55:05")
    r.tick("15:59:01")
    cid = f"mirror-{DAY}-B-TECL"
    rec = r.m.state["run"]["orders"][cid]
    assert rec["state"] != "booked" and "cannot be read" in rec["stuck"]   # the lookup RAISED: not 'it executed nothing'
    r.venue.stock_order_fills = lambda c: dict(real_fills(c), filled_qty=None)
    r.tick("15:59:10")
    assert "neither its record nor the executions" in r.m.state["run"]["orders"][cid]["stuck"]     # nor is None a zero
    r.venue.stock_order_fills = real_fills                     # the twin: readable -> the 40 are booked
    r.tick("15:59:20")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert tecl["filled"] == 40 and r.m.book.positions()["TECL"] == r.venue.stock_position("TECL") == 40
    sound(r)


# =============================================================================================== A-17
def test_a17_no_new_order_is_sent_at_or_after_the_cancel_instant(tmp_path):
    r = live_rig(tmp_path)
    sent_at = []
    for name in ("place_stock_order", "place_limit_order"):
        real = getattr(r.venue, name)

        def slow(symbol, qty, *a, _real=real, **kw):
            sent_at.append((symbol, r.clock.now))
            r.clock.now += timedelta(seconds=26)               # a gateway answering slowly
            return _real(symbol, qty, *a, **kw)
        setattr(r.venue, name, slow)
    r.tick("15:57:55")                                         # 5 s before plan_by: the plan is allowed to start
    cancel_at = at("15:59:00")
    assert len(sent_at) == 3 and all(t < cancel_at for _, t in sent_at)    # the window is looked at for EVERY order
    row = r.m.state["last_run"]
    unsent = [o for o in row["orders"] if o["how"] == "not sent: the window closed"]
    assert len(unsent) == 2 and all(o["filled"] == 0 for o in unsent)
    sound(r)


# =============================================================================================== A-19
def test_a19_a_cancel_lead_of_four_minutes_is_clamped_not_a_silent_no_trade(tmp_path):
    r = live_rig(tmp_path, cancel_before_close_s=240.0)        # MIRROR_CANCEL_BEFORE_CLOSE_S=240
    assert r.m.cfg.cancel_before_close_s == 120.0 and "cancel_before_close_s" in r.m.clamped[0]
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    assert r.m.state["history"][-1]["session"] == DAY


# =============================================================================================== D8
def test_d8_credits_are_applied_debits_first(tmp_path):
    r = invested(tmp_path)
    r.venue.cash += 61.20 - 12.34                              # the account received a dividend and paid a fee
    r.m.request_credit("HARV", 61.20, "PULS dividend", force=True)   # sent in the 'wrong' order: alone, the dividend
    r.m.request_credit("HG", -12.34, "fee")                    # exceeds what the account holds beyond the book
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert not any("REFUSED" in n for n in row["notes"]) and not [a for a in r.red() if "credit" in a]
    assert [c["amount"] for c in row["credits"]] == [-12.34, 61.20]        # the history row carries them, in that order
    sound(r)


def test_d8_the_morning_pre_check_runs_once_and_only_reads(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("09:00:00", day=D2)                                 # before the open: not yet
    r.venue.seed_position("AAPL", 3)
    seq = disk(r)["seq"]
    r.tick("09:31:00", day=D2)
    r.tick("11:00:00", day=D2)
    said = [a for a in r.red() if "today's decision will be refused unless fixed" in a]
    assert len(said) == 1 and "AAPL" in said[0] and D2 in said[0]
    assert disk(r)["seq"] == seq and r.orders().__len__() == 5             # read-only
    h = invested(tmp_path / "ok")                              # the twin: a healthy book says nothing
    h.brain.make = lambda now: payload(now, session=D2)
    h.tick("09:31:00", day=D2)
    assert not h.red()


def test_d8_a_resume_says_which_halt_it_lifted(tmp_path):
    r = invested(tmp_path)
    r.venue._positions["TECL"] -= 5
    r.tick("15:56:00")
    r.tick("15:57:00")                                         # the book halted ITSELF on the mismatch
    assert r.m.halt_state()["by"] == "mirror"
    out = r.m.resume()
    assert out["was_halted"] is True and out["lifted"]["by"] == "mirror" and "TECL" in out["lifted"]["reason"]
    assert r.m.resume()["lifted"] is None                      # the twin: nothing was halted


# =============================================================================================== D9 dividends
DIV = {"ticker": "PULS", "ex_date": D2, "pay_date": D3, "amount": 0.20}


def with_div(session, targets=None, div=DIV, **kw):
    return lambda now: payload(now, targets, session=session, dividends=[dict(div)], **kw)


def test_d9_a_dividend_becomes_a_receivable_per_sleeve_and_is_credited_from_the_pay_date(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    held = {n: s.shares.get("PULS", 0) for n, s in d.m.book.sleeves.items()}
    assert held["KMLM"] > 0 and held["HARV"] > 0 and held["HG"] == 0
    eq = lambda name, m=None: mc.equity((m or d.m).book.sleeves[name], PX)     # noqa: E731  (paper fills at PX, no fees)
    eq0 = {n: eq(n) for n in d.m.book.sleeves}
    d.brain.make = with_div(D2)
    d.tick("15:55:05", day=D2)                                 # the ex-date: receivables, nothing credited yet
    recs = {x["sleeve"]: x for x in d.m.state["dividends"]}
    assert set(recs) == {"KMLM", "HARV"} and recs["HARV"]["id"] == f"div-PULS-{D2}-HARV"
    assert recs["HARV"]["shares"] == held["HARV"] and recs["HARV"]["total"] == pytest.approx(held["HARV"] * 0.20)
    assert eq("HARV") == pytest.approx(eq0["HARV"]) and d.m.state["last_run"]["credits"] == []
    assert any("receivable" in n and "PULS" in n for n in d.m.state["last_run"]["notes"])
    d.boot()                                                   # a restart in between changes nothing
    d.brain.make = with_div(D3)
    d.tick("15:55:05", day=D3)                                 # the pay date: credited at the start of the plan
    row = d.m.state["last_run"]
    assert sorted(c["sleeve"] for c in row["credits"]) == ["HARV", "KMLM"] and all(c["kind"] == "dividend" for c in row["credits"])
    assert eq("HARV") == pytest.approx(eq0["HARV"] + held["HARV"] * 0.20)
    assert eq("KMLM") == pytest.approx(eq0["KMLM"] + held["KMLM"] * 0.20) and eq("HG") == pytest.approx(eq0["HG"])
    assert [x["status"] for x in d.m.state["dividends"]] == ["credited", "credited"]
    d.boot()
    d.brain.make = with_div(D4)
    d.tick("15:55:05", day=D4)                                 # still listed by the brain: never counted twice
    assert d.m.state["last_run"]["credits"] == [] and len(d.m.state["dividends"]) == 2
    assert eq("HARV") == pytest.approx(eq0["HARV"] + held["HARV"] * 0.20)
    assert {x["event"] for x in d.journal()} >= {"dividend", "dividend_credited"}
    sound(d)


@pytest.mark.parametrize("rule, harv_gets_it", [("composer", False), ("holder", True)])
def test_d9_the_dividend_rule_decides_what_a_sleeve_that_sold_the_payer_gets(tmp_path, rule, harv_gets_it):
    d = Rig(tmp_path, dividend_rule=rule)
    d.tick("15:55:05")
    held = d.m.book.sleeves["HARV"].shares["PULS"]
    out = dict(T1, HARV={"BIL": 1.0})                          # on the ex-date HARV leaves PULS; KMLM keeps it
    d.brain.make = with_div(D2, out)
    d.tick("15:55:05", day=D2)
    assert "PULS" not in d.m.book.sleeves["HARV"].shares
    eq = lambda: mc.equity(d.m.book.sleeves["HARV"], PX)       # noqa: E731
    eq0 = eq()
    d.brain.make = with_div(D3, out)
    d.tick("15:55:05", day=D3)
    status = {x["sleeve"]: x["status"] for x in d.m.state["dividends"]}
    assert status["KMLM"] == "credited"
    if harv_gets_it:                                           # 'holder': whoever held the shares at the ex-date
        assert status["HARV"] == "credited" and eq() == pytest.approx(eq0 + held * 0.20)
    else:                                                      # 'composer': the cash stays unallocated, as on Composer
        assert status["HARV"] == "leaked" and eq() == pytest.approx(eq0)
        assert any("left unallocated" in n for n in d.m.state["last_run"]["notes"])


def test_d9_an_ex_date_missed_by_a_skipped_session_uses_the_last_recorded_close(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    held = d.m.book.sleeves["HARV"].shares["PULS"]
    d.brain.fail = "transport"                                 # the ex-date's session is lost
    d.tick("15:55:05", day=D2)
    d.tick("15:58:00", day=D2)
    assert d.m.state["last_run"]["outcome"] == "skipped" and d.m.state["dividends"] == []
    d.brain.fail = None
    d.brain.make = with_div(D3)
    d.tick("15:55:05", day=D3)                                 # first seen the day after: the close BEFORE the ex-date counts
    recs = {x["sleeve"]: x for x in d.m.state["dividends"]}
    assert recs["HARV"]["shares"] == held and recs["HARV"]["status"] == "credited"
    assert "last recorded close" in recs["HARV"]["basis"]
    new = Rig(tmp_path / "new")                                # the twin: a book with no row before the ex-date gets nothing
    os.makedirs(tmp_path / "new", exist_ok=True)
    new.brain.make = with_div(D3)
    new.tick("15:55:05", day=D3)
    assert new.m.state["dividends"] == [] and new.m.state["div_seen"] == [f"div-PULS-{D2}"]


def test_d9_a_live_book_credits_a_dividend_only_from_cash_the_account_received(tmp_path):
    r = invested(tmp_path)
    held = r.m.book.sleeves["HARV"].shares["PULS"]
    total = sum(s.shares.get("PULS", 0) for s in r.m.book.sleeves.values()) * 0.20
    r.brain.make = with_div(D2)
    r.tick("15:55:05", day=D2)
    eq = lambda: mc.equity(r.m.book.sleeves["HARV"], PX)       # noqa: E731
    eq0 = eq()
    r.brain.make = with_div(D3)
    r.tick("15:55:05", day=D3)                                 # the pay date: IBKR has not posted it
    assert all(x["status"] == "open" and x["waited"] == 1 for x in r.m.state["dividends"])
    assert eq() == pytest.approx(eq0) and not r.red()
    days = ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    for day in days:
        r.brain.make = with_div(day)
        r.tick("15:55:05", day=day)
    said = [a for a in r.red() if "still unpaid after 7 sessions" in a]
    assert len(said) == 2 and eq() == pytest.approx(eq0)       # one alert per receivable, and still nothing credited
    r.brain.make = with_div("2026-11-23")
    r.tick("15:55:05", day="2026-11-23")
    assert len([a for a in r.red() if "still unpaid" in a]) == 2                           # ... once
    r.venue.cash += total                                      # the twin: the cash arrives
    r.brain.make = with_div("2026-11-24")
    r.tick("15:55:05", day="2026-11-24")
    assert all(x["status"] == "credited" for x in r.m.state["dividends"])
    assert eq() == pytest.approx(eq0 + held * 0.20)
    sound(r)


def test_d9_a_receivable_never_paid_expires_with_an_alert(tmp_path):
    r = invested(tmp_path)
    r.brain.make = with_div(D2)
    r.tick("15:55:05", day=D2)
    r.brain.make = lambda now: payload(now, session="2026-12-14")
    r.tick("15:55:05", day="2026-12-14")                       # 32 days after the pay date, nothing received
    assert all(x["status"] == "expired" for x in r.m.state["dividends"])
    assert len([a for a in r.red() if "CLOSED as expired" in a]) == 2
    sound(r)


def test_r2_a_pay_date_never_listed_is_assumed_only_ten_days_after_the_ex_date(tmp_path):
    """round 2 (R2): ex + 7 used to be FINALISED the day the dividend was first seen. Now the
    receivable stays open with no pay date; only ten calendar days after the ex-date is ex + 7 assumed"""
    d = Rig(tmp_path)
    d.tick("15:55:05")
    d.brain.make = with_div(D2, div=dict(DIV, pay_date=None))                  # ex-date 2026-11-11, pay date unknown
    d.tick("15:55:05", day=D2)
    assert {x["pay_date"] for x in d.m.state["dividends"]} == {None}
    assert any("pay date NOT KNOWN YET" in n for n in d.m.state["last_run"]["notes"])
    for day in ("2026-11-18", "2026-11-19", "2026-11-20"):                     # ex + 7, + 8, + 9: the old rule paid on the 18th
        d.brain.make = lambda now, day=day: payload(now, session=day)
        d.tick("15:55:05", day=day)
        assert all(x["status"] == "open" and x["pay_date"] is None for x in d.m.state["dividends"]), day
        assert d.m.state["last_run"]["credits"] == []
    d.brain.make = lambda now: payload(now, session="2026-11-23")              # the first session ten days after it
    d.tick("15:55:05", day="2026-11-23")
    recs = d.m.state["dividends"]
    assert all(x["status"] == "credited" and x["pay_date"] == "2026-11-18" and x["pay_date_assumed"] is True for x in recs)
    assert [x for x in d.journal() if x["event"] == "dividend_pay_date" and x.get("assumed") is True]
    sound(d)


def test_r2_a_pay_date_learnt_from_a_later_payload_is_the_one_used(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    held = d.m.book.sleeves["HARV"].shares["PULS"]
    eq = lambda: mc.equity(d.m.book.sleeves["HARV"], PX)                       # noqa: E731
    eq0 = eq()
    d.brain.make = with_div(D2, div=dict(DIV, pay_date=None))
    d.tick("15:55:05", day=D2)
    for day in (D3, D4):                                                       # still not known: open, nothing assumed
        d.brain.make = with_div(day, div=dict(DIV, pay_date=None))
        d.tick("15:55:05", day=day)
        assert all(x["status"] == "open" and x["pay_date"] is None for x in d.m.state["dividends"])
    d.brain.make = with_div("2026-11-16", div=dict(DIV, pay_date="2026-11-24"))        # a LATER listing carries it
    d.tick("15:55:05", day="2026-11-16")
    assert {x["pay_date"] for x in d.m.state["dividends"]} == {"2026-11-24"}
    assert not any(x.get("pay_date_assumed") for x in d.m.state["dividends"])
    assert [x for x in d.journal() if x["event"] == "dividend_pay_date" and x.get("learnt") == "2026-11-16"]
    d.boot()
    d.brain.make = lambda now: payload(now, session="2026-11-23")              # ex + 12: NOT the ex + 7 fallback any more
    d.tick("15:55:05", day="2026-11-23")
    assert all(x["status"] == "open" for x in d.m.state["dividends"]) and eq() == pytest.approx(eq0)
    d.brain.make = lambda now: payload(now, session="2026-11-24")
    d.tick("15:55:05", day="2026-11-24")
    assert all(x["status"] == "credited" for x in d.m.state["dividends"]) and eq() == pytest.approx(eq0 + held * 0.20)
    sound(d)


def test_r2_an_incomplete_actions_list_is_recorded_and_said_once(tmp_path):
    r = live_rig(tmp_path)
    r.brain.make = lambda now: payload(now, actions_complete=False)
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and row["actions_complete"] is False     # it trades; the record says what it lacked
    said = [a for a in r.alerts if "dividend and split lists are INCOMPLETE" in a]
    assert len(said) == 1 and said[0].startswith("⚠️") and DAY in said[0]
    r.tick("15:56:00")
    r.tick("16:30:00")
    assert len([a for a in r.alerts if "INCOMPLETE" in a]) == 1                # once that day
    t = live_rig(tmp_path / "twin")                    # the twin: complete (or not stated): recorded, nothing said
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.brain.make = lambda now: payload(now, actions_complete=True)
    t.tick("15:55:05")
    assert t.m.state["last_run"]["actions_complete"] is True and not any("INCOMPLETE" in a for a in t.alerts)


# =============================================================================================== D9 splits
def test_d9_a_split_rescales_the_sleeves_before_the_pre_trade_gate(tmp_path):
    r = invested(tmp_path)
    soxl = r.m.book.positions()["SOXL"]
    r.venue._positions["SOXL"] = soxl * 2                      # SOXL splits 2:1: the account shows twice the shares ...
    px2 = dict(PX, SOXL=20.0)                                  # ... at half the price
    r.venue.quotes["SOXL"] = 20.0
    eq0 = mc.equity(r.m.book.sleeves["KMLM"], PX)
    r.brain.make = lambda now: payload(now, prices=px2, session=D2, splits=[{"ticker": "SOXL", "date": D2, "ratio": 2.0}])
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] != "skipped"            # the account IS the book again
    assert r.m.book.positions()["SOXL"] == soxl * 2
    assert mc.equity(r.m.book.sleeves["KMLM"], px2) == pytest.approx(eq0, abs=1.0)         # a split changes no value
    assert row["sleeves"]["KMLM"]["action"] == "hold"          # ... so the threshold sleeve does not trade on it
    ev = next(x for x in r.journal() if x["event"] == "split")
    assert ev["total_before"] == soxl and ev["total_after"] == soxl * 2 and ev["fraction"] == 0
    r.tick("15:56:00", day=D2)
    assert r.m.state["splits_applied"] == [f"split-SOXL-{D2}"] and r.m.book.positions()["SOXL"] == soxl * 2   # once
    sound(r)
    t = invested(tmp_path / "twin")                            # the twin: the brain does not list it -> the book refuses
    t.venue._positions["SOXL"] = soxl * 2
    t.venue.quotes["SOXL"] = 20.0
    t.brain.make = lambda now: payload(now, prices=px2, session=D2)
    t.tick("15:55:05", day=D2)
    t.tick("15:58:00", day=D2)
    assert t.m.state["last_run"]["outcome"] == "skipped" and "SOXL" in t.m.state["last_run"]["reason"]


def test_d9_a_reverse_split_floors_the_book_total_and_records_the_cash_in_lieu(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    puls = {n: s.shares.get("PULS", 0) for n, s in d.m.book.sleeves.items() if s.shares.get("PULS")}
    total = sum(puls.values())
    assert total % 5 != 0                                      # (else the gate would not see a fraction)
    px2 = dict(PX, PULS=247.5)
    d.brain.make = lambda now: payload(now, prices=px2, session=D2, splits=[{"ticker": "PULS", "date": D2, "ratio": 0.2}])
    cash = d.m.book.cash()
    d.tick("15:55:05", day=D2)
    assert d.m.state["last_run"]["session"] == D2
    ev = next(x for x in d.journal() if x["event"] == "split")
    assert ev["total_after"] == total // 5 and ev["fraction"] == pytest.approx(total / 5 - total // 5)
    assert sum(ev["after"].values()) == total // 5 and ev["cash_in_lieu_owed"] == pytest.approx(ev["fraction"] * 247.5, abs=0.01)
    assert any("cash in lieu" in a and "NOT booked" in a for a in d.alerts)
    assert d.m.book.cash() == pytest.approx(cash, abs=600)     # nothing was booked for the fraction (only the day's trims)
    assert d.m._dry.stock_position("PULS") == d.m.book.positions()["PULS"]                 # the paper account was rebuilt
    sound(d)


def test_d9_a_split_published_late_is_not_applied_to_a_book_that_already_ran_on_the_new_price(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    px2 = dict(PX, SOXL=20.0)
    d.brain.make = lambda now: payload(now, prices=px2, session=D2)        # the split day, and the brain does not list it:
    d.tick("15:55:05", day=D2)                                             # the paper book trades on a stale count
    soxl = d.m.book.positions().get("SOXL", 0)
    d.brain.make = lambda now: payload(now, prices=px2, session=D3, splits=[{"ticker": "SOXL", "date": D2, "ratio": 2.0}])
    d.tick("15:55:05", day=D3)
    assert d.m.book.positions().get("SOXL", 0) != soxl * 2 or soxl == 0    # NOT doubled on top of the wrong count
    said = [a for a in d.red() if "published after this book had already run" in a and "/mirror/adjust" in a]
    assert len(said) == 1 and d.m.state["splits_applied"] == [f"split-SOXL-{D2}"]
    d.tick("15:56:00", day=D3)
    assert len([a for a in d.red() if "published after" in a]) == 1        # said once


# =============================================================================================== A-23
def test_a23_a_wake_before_the_run_is_saved_drops_the_attempt_and_the_next_tick_retries(tmp_path):
    """nothing in a tick holds the loop thread behind a set wake: /kill's other stages (the blend's
    flatten, the ladder's closes) run on that thread. A decision not yet on disk is simply dropped."""
    import threading
    r = invested(tmp_path)
    r.venue.cash += 20.0
    r.m.request_credit("HARV", 20.0, "interest")
    r.tick("15:56:00")
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    wake = threading.Event()
    real = r.venue.spot_ex
    asked = []

    def spot(symbol):
        asked.append(symbol)
        if len(asked) == 2:
            wake.set()                                 # the loop is woken between two quotes of the cross-check
        return real(symbol)
    r.venue.spot_ex = spot
    n, seq, book = len(r.orders()), disk(r)["seq"], r.m.book.to_dict()
    r.clock.now = at("15:55:05", D2)
    r.m.tick(r.venue, wake=wake)
    assert len(asked) == 2                             # it stopped asking at once ...
    assert len(r.orders()) == n and r.m.state["run"] is None and disk(r)["seq"] == seq    # ... nothing sent, nothing written
    assert r.m.book.to_dict() == book and len(r.m.state["requests"]) == 1                 # ... and the credit is still queued
    wake.clear()                                       # (the service loop clears it before its next pass)
    r.venue.spot_ex = real
    r.clock.now = at("15:55:10", D2)
    r.m.tick(r.venue, wake=wake)
    assert r.m.state["last_run"]["session"] == D2 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_a23_a_wake_mid_run_hands_the_loop_back_between_two_orders(tmp_path):
    import threading
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    wake = threading.Event()
    n = len(r.orders())

    def wake_once(symbol, qty):
        if len(r.orders()) == n + 2:
            wake.set()                                 # woken while the second order of the plan is out
    spy(r, wake_once)
    r.clock.now = at("15:55:05", D2)
    r.m.tick(r.venue, wake=wake)
    assert len(r.orders()) == n + 2                    # the order in flight finished; no further one was started
    assert r.m.state["run"] is not None and disk(r)["run"]["session"] == D2               # the run is on disk
    wake.clear()
    r.clock.now = at("15:55:08", D2)
    r.m.tick(r.venue, wake=wake)                       # the next tick carries on where it stopped
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and len(r.orders()) == n + 7
    assert len({c for _, _, c in r.venue.placed}) == len(r.venue.placed)                  # no order twice
    sound(r)


def test_a23_the_flatten_is_not_interrupted_by_the_wake_that_asked_for_it(tmp_path):
    import threading
    r = invested(tmp_path)
    wake = threading.Event()
    r.m.halt("KILL", flatten=True)
    wake.set()                                         # /kill sets the wake; the emergency stop itself must run
    r.clock.now = at("15:56:00")
    r.m.tick(r.venue, wake=wake)
    assert r.m.book.positions() == {} and r.m.halt_state()["flatten_done"] is True


def test_a23_a_brain_read_runs_on_a_worker_and_the_tick_waits_on_the_wake(tmp_path):
    import threading
    import time as _time
    r = Rig(tmp_path)
    r.tick("15:00")
    wake, entered, release = threading.Event(), threading.Event(), threading.Event()
    real = r.brain.intents

    def slow(after):
        entered.set()
        release.wait(10)                               # the brain is building
        return real(after)
    r.brain.intents = slow
    r.clock.now = at("15:55:05")
    done = []
    t = threading.Thread(target=lambda: (r.m.tick(None, wake=wake), done.append(_time.monotonic())), daemon=True)
    t.start()
    assert entered.wait(5)
    t0 = _time.monotonic()
    wake.set()
    t.join(5)
    assert done and done[0] - t0 < 1.0                 # the tick came back at once, the read still in flight
    assert r.orders() == [] and r.m.state["last_session"] is None
    release.set()
    wake.clear()
    r.brain.intents = real
    r.tick("15:55:10")
    assert r.m.state["last_run"]["outcome"] == "traded"


# =============================================================================================== mutation-found gaps
# (each of these pins ONE of two protections that masked each other in the gates above: found by
# breaking the fixes by hand and seeing no gate fail)
def test_a01_a_halt_during_the_intents_read_stops_a_paper_book_before_the_plan(tmp_path):
    """D1 'in _decide before _start': a paper book has no quote cross-check to notice the halt later"""
    d = Rig(tmp_path)
    d.tick("15:00")
    real = d.brain.intents
    planned = []
    real_plan = d.m._plan
    d.m._plan = lambda *a, **k: (planned.append(1), real_plan(*a, **k))[1]

    def intents(after):
        out = real(after)
        d.m.halt("operator halt")
        return out
    d.brain.intents = intents
    d.tick("15:55:05")
    assert d.orders() == [] and d.m.state["run"] is None and d.m.state["last_session"] is None
    assert planned == []                               # the halt was seen BEFORE the plan was even built
    d.brain.intents = real
    d.m.resume()
    d.tick("15:55:20")
    assert d.m.state["last_run"]["outcome"] == "traded" and planned == [1]


def test_a01_a_halt_during_the_last_quote_of_the_cross_check_is_seen_before_the_run_is_saved(tmp_path):
    """D1 'in _start again just before the run is saved': after the last quote nothing else looks"""
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    real = r.venue.spot_ex
    asked = []

    def spot(symbol):
        asked.append(symbol)
        if symbol == "TQQQ" and r.m.state.get("run") is None:  # the cross-check's LAST symbol (they are asked in order)
            r.m.halt("operator halt")
        return real(symbol)
    r.venue.spot_ex = spot
    n, seq = len(r.orders()), disk(r)["seq"]
    r.tick("15:55:05", day=D2)
    assert asked[-1] == "TQQQ" and len(r.orders()) == n and r.m.state["run"] is None and disk(r)["seq"] == seq
    sound(r)


def test_a03_no_second_round_is_built_while_a_flatten_order_is_still_at_the_venue(tmp_path):
    """state['flatten'] is never replaced while it has an unbooked order - however long that takes
    (the round gap is 5 s; these sells rest for two minutes)"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.venue.hold.update(held)
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    ticks(r, 24, 5)
    sells = [(s, q) for s, q in r.orders()[5:]]
    assert sorted(s for s, _ in sells) == sorted(held)         # ONE sell per symbol, still: never a second over it
    assert r.m.state["flatten"]["round"] == 1 and r.m.book.positions() == held
    r.venue.hold.clear()
    for sym in held:
        r.venue.release(sym)
    r.tick("15:58:10")
    assert r.venue.positions_snapshot()["stocks"] == {} and r.m.book.positions() == {}
    sound(r)


def test_a04_an_order_whose_write_ahead_save_fails_is_not_sent(tmp_path, monkeypatch):
    """'intent' stands only if its write-ahead save succeeded: here that save is the FIRST one to
    fail, so no latch is in force yet when the order is about to go"""
    r = live_rig(tmp_path)
    real = mm.atomic_write

    def write(path, obj):
        orders = ((obj.get("run") or {}).get("orders") or {}) if isinstance(obj, dict) else {}
        if any(v.get("state") == "intent" for v in orders.values()):
            raise OSError(28, "No space left on device")       # the disk fills exactly at the first write-ahead
        return real(path, obj)
    monkeypatch.setattr(mm, "atomic_write", write)
    r.clock.interrupt = True
    r.tick("15:55:05")
    assert r.orders() == []                                    # the venue saw nothing ...
    recs = r.m.state["run"]["orders"]
    assert recs and {v["state"] for v in recs.values()} == {"new"}         # ... and 'intent' was taken back
    assert disk(r)["run"]["phase"] == "buys" and r.m._latched
    monkeypatch.setattr(mm, "atomic_write", real)
    r.clock.interrupt = False
    r.tick("15:55:20")
    assert r.m.state["last_run"]["outcome"] == "traded" and len(r.orders()) == 5
    sound(r)
