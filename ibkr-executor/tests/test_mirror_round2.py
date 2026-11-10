"""Merge-blocking gates for the SECOND verification round of the Composer mirror (three independent
re-verifications of the review fixes). One finding, one or more gates, each with its twin. The
doubles are tests/test_mirror.py's; the gates that need the REAL IBAdapter are in
tests/test_mirror_ib.py and tests/test_ib_stock_adapter.py; the flatten's time bound (N-08) and the
dividend pay date (R2) sit with their round-1 neighbours in tests/test_mirror_review.py.

  N-01  the operator's tools: resolve only for an order flagged unresolved, the venue is asked once
        more and its own answer wins, a price that cannot be true is refused; an adjustment or a
        debit that would put a sleeve in debt needs "force"
  N-02  a flatten reads the ACCOUNT before it says "complete"
  N-04  'no such order' is proof for today's order when the venue shows it neither open nor executed
  N-09  what a paper book may cost the loop it shares with a live strategy
  A-23 / A-20 residuals: the commission true-up hands a woken loop back; a stuck run stops spinning
  R3    a LIVE sleeve trades only on a tree the payload's own sync row attests
  R4    a sleeve that was not traded is never an info line
  N4    the brain's token never rides plain http
  V2-B2 shares that change outside a run (a flatten, a split, an adjustment) are in the history a
        later dividend reads its entitlement from
  six gates the mutation pass found missing: the flatten's hold-back of a symbol with an unresolved
        run order; the halt look before an unconfirmed order is sent again; a resolve of a
        never-sent order; the flatten's finish under a racing /kill or /resume (and, in
        tests/test_ib_stock_adapter.py, the MKT fill window and executions of two attempts)
"""
from __future__ import annotations

import os
import threading

import pytest

from app import mirror as mm
from app import mirror_core as mc
from test_mirror import DAY, PX, T1, Crash, Rig, at, live_rig, payload, sound, timedelta
from test_mirror_review import D2, D3, D4, DIV, ROTATE, invested, spy, ticks, with_div

REFUSED = lambda r, kind: [a for a in r.red() if f"{kind} request" in a and "REFUSED" in a]      # noqa: E731


def stuck_buy(tmp_path, symbol="PULS"):
    """a live run whose BUY of `symbol` was acknowledged and then lost by a venue that cannot say
    what became of it: UNRESOLVED"""
    r = live_rig(tmp_path)
    r.venue.hold.add(symbol)
    r.tick("15:55:05")
    oid = f"mirror-{DAY}-B-{symbol}"
    r.venue.history_ok = False
    r.venue.forgotten.add(oid)
    r.tick("15:59:05")
    run = r.m.state["run"]
    assert run["orders"][oid].get("stuck")
    return r, oid, next(o for o in run["plan"]["buys"] if o["id"] == oid)


def stuck_sell(tmp_path, symbol="BIL"):
    """day two rotates every sleeve; the SELL of `symbol` is acknowledged and then lost: UNRESOLVED,
    with the shares still in the book"""
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    r.venue.hold.add(symbol)
    r.tick("15:55:05", day=D2)
    oid = f"mirror-{D2}-S-{symbol}"
    r.venue.history_ok = False
    r.venue.forgotten.add(oid)
    r.tick("15:59:05", day=D2)
    run = r.m.state["run"]
    assert run["orders"][oid].get("stuck") and r.m.book.positions().get(symbol)
    return r, oid, next(o for o in run["plan"]["sells"] if o["id"] == oid)


# =============================================================================================== N-01
def test_n01_a_resolve_price_that_cannot_be_true_is_refused(tmp_path):
    r, oid, o = stuck_buy(tmp_path)
    assert o["ref"] == PX["PULS"] and PX["PULS"] < o["limit"] < 50.0
    cash0 = {n: s.cash for n, s in r.m.book.sleeves.items()}
    cases = ((4960.0, "limit order at"),                       # 49.60 typed without the point
             (round(o["limit"] + 0.01, 2), "limit order at"),  # one cent above the limit: the venue cannot have filled it
             (round(o["ref"] * 0.79, 2), "more than 20%"))     # under the limit, but 21% from the reference
    for k, (px, why) in enumerate(cases):
        n = len(r.red())
        r.m.request_resolve(oid, o["qty"], px, 0.0, "typo")
        r.tick(f"15:59:{10 + 5 * k}")
        assert r.m.state["run"]["orders"][oid]["state"] != "booked" and r.m.state["requests"] == [], px
        assert any("resolve request" in a and "REFUSED" in a and why in a for a in r.red()[n:]), (px, r.red()[n:])
    assert {n: s.cash for n, s in r.m.book.sleeves.items()} == cash0 and "PULS" not in r.m.book.positions()
    assert len([x for x in r.journal() if x["event"] == "request_refused" and x["kind"] == "resolve"]) == 3
    r.venue._positions["PULS"] = o["qty"]                      # the twin: what the statement really says
    r.venue.cash -= o["qty"] * 49.60
    r.m.request_resolve(oid, o["qty"], 49.60, 0.0, "IBKR activity statement")
    r.tick("15:59:40")
    done = next(x for x in r.m.state["last_run"]["orders"] if x["id"] == oid)
    assert r.m.state["run"] is None and (done["filled"], done["price"]) == (o["qty"], 49.60)
    assert "resolved by the operator" in done["how"]
    sound(r)


def test_n01_a_sell_resolved_far_from_its_reference_is_refused(tmp_path):
    r, oid, o = stuck_sell(tmp_path)
    for k, px in enumerate((915.0, round(o["ref"] * 1.21, 2), round(o["ref"] * 0.79, 2))):
        r.m.request_resolve(oid, o["qty"], px, 0.0, "typo: 91.50")
        r.tick(f"15:59:{10 + 5 * k}", day=D2)
        assert r.m.state["run"]["orders"][oid]["state"] != "booked", px
    assert len([a for a in REFUSED(r, "resolve") if "more than 20%" in a and "reference" in a]) == 3
    assert r.m.book.positions()["BIL"] == o["qty"]
    r.venue._positions.pop("BIL")                              # the twin: 19% under the reference is a (bad) fill
    px = round(o["ref"] * 0.81, 2)
    r.venue.cash += o["qty"] * px
    r.m.request_resolve(oid, o["qty"], px, 0.0, "statement")
    r.tick("15:59:30", day=D2)
    assert r.m.state["run"] is None and "BIL" not in r.m.book.positions()
    sound(r)


def test_n01_resolve_is_only_for_an_order_the_book_has_flagged_unresolved(tmp_path):
    """the reviewer's N-01c: an order that is not stuck at all - it filled a second ago and the next
    pass books it from the venue's own record - was booked at whatever the operator typed"""
    r = live_rig(tmp_path)
    r.venue.hold.add("PULS")
    r.tick("15:55:05")
    oid = f"mirror-{DAY}-B-PULS"
    assert r.m.state["run"] is not None and not r.m.state["run"]["orders"][oid].get("stuck")
    r.venue.hold.clear()
    r.venue.release("PULS")                                    # it fills in full at the venue
    r.m.request_resolve(oid, 0, None, 0.0, "wrong order id")
    r.tick("15:55:20")
    assert len([a for a in REFUSED(r, "resolve") if "not UNRESOLVED" in a and "'placed'" in a]) == 1
    assert [x for x in r.journal() if x["event"] == "request_refused" and x["order"] == oid]
    assert r.m.state["run"] is None and r.m.book.positions()["PULS"] == r.venue.stock_position("PULS") > 0
    assert not [x for x in r.journal() if x["event"] in ("resolve", "resolve_from_venue")]
    sound(r)


def test_n01_an_order_that_was_never_sent_cannot_be_resolved(tmp_path):
    """an order still waiting its turn (the loop was woken between two orders) is not 'unresolved': a
    resolve naming it would book a fill for an order the venue never saw, and it would never be sent"""
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    wake = threading.Event()
    n = len(r.orders())
    spy(r, lambda s, q: wake.set() if len(r.orders()) == n + 1 else None)
    r.clock.now = at("15:55:05", D2)
    r.m.tick(r.venue, wake=wake)                               # woken after the FIRST sell: four more wait
    run = r.m.state["run"]
    unsent = [o for o in run["plan"]["sells"] if (run["orders"].get(o["id"]) or {"state": "new"})["state"] == "new"]
    assert len(unsent) == 4 and len(r.orders()) == n + 1
    o = unsent[0]
    r.m.request_resolve(o["id"], o["qty"], o["ref"], 0.0, "wrong order id")
    wake.clear()
    r.clock.now = at("15:55:08", D2)
    r.m.tick(r.venue, wake=wake)
    assert len([a for a in REFUSED(r, "resolve") if "not UNRESOLVED" in a and "'new'" in a]) == 1
    row = r.m.state["last_run"]
    done = next(x for x in row["orders"] if x["id"] == o["id"])
    assert row["outcome"] == "traded" and done["filled"] == o["qty"] and "resolved by the operator" not in done["how"]
    assert [c for _, _, c in r.venue.placed].count(o["id"]) == 1          # ... it went to the venue, once
    sound(r)


def test_n01_the_venue_is_asked_once_more_and_its_own_answer_is_what_is_booked(tmp_path):
    r, oid, o = stuck_buy(tmp_path)
    rec = r.venue._orders[r.venue._by_client[oid]]
    r.venue.hold.clear()
    r.venue._fill(rec, o["qty"])                               # in truth it FILLED, in full, at 49.50 ...
    r.venue.forgotten.clear()                                  # ... and the gateway answers for it again
    r.m.request_resolve(oid, 0, None, 0.0, "it never filled, I checked")
    r.tick("15:59:10")
    done = next(x for x in r.m.state["last_run"]["orders"] if x["id"] == oid)
    assert (done["filled"], done["price"]) == (o["qty"], PX["PULS"]) and "resolved by the operator" not in done["how"]
    said = [a for a in r.alerts if "the VENUE answers for it now" in a]
    assert len(said) == 1 and f"booked {o['qty']} of {o['qty']} PULS" in said[0] and "NOT the 0 stated" in said[0]
    events = [x["event"] for x in r.journal()]
    assert "resolve_from_venue" in events and "resolve" not in events
    assert r.m.state["requests"] == [] and r.m.book.positions()["PULS"] == o["qty"]
    sound(r)
    t, oid, o = stuck_buy(tmp_path / "twin")                   # the twin: the venue still cannot answer -> the statement
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.m.request_resolve(oid, 0, None, 0.0, "expired unfilled, per the statement")
    t.tick("15:59:10")
    done = next(x for x in t.m.state["last_run"]["orders"] if x["id"] == oid)
    assert done["filled"] == 0 and "resolved by the operator" in done["how"]


def test_n01_a_venue_that_says_filled_but_cannot_give_the_price_still_wins_on_the_quantity(tmp_path):
    def rig(path):
        os.makedirs(path, exist_ok=True)
        r, oid, o = stuck_buy(path)
        rec = r.venue._orders[r.venue._by_client[oid]]
        r.venue.hold.clear()
        r.venue._fill(rec, o["qty"])                           # it FILLED; the gateway answers for it again ...
        r.venue.forgotten.clear()
        r.venue.no_price.add("PULS")                           # ... but reports no price, and the executions

        def down(cid):                                         #     cannot be read on this pass
            raise RuntimeError("reqExecutions timed out")
        r.venue.stock_order_fills = down
        return r, oid, o
    r, oid, o = rig(tmp_path / "wrong")
    r.m.request_resolve(oid, 0, None, 0.0, "it never filled")
    r.tick("15:59:10")
    assert len([a for a in REFUSED(r, "resolve") if f"FILLED {o['qty']} of {o['qty']}" in a and "states 0" in a]) == 1
    done = next(x for x in r.m.state["last_run"]["orders"] if x["id"] == oid)          # the run's own pass then books the
    assert done["filled"] == o["qty"] and done["price"] == o["limit"]                  # venue's quantity (at the limit, flagged)
    assert "resolved by the operator" not in done["how"] and r.m.book.positions()["PULS"] == o["qty"]
    t, oid, o = rig(tmp_path / "right")                        # the twin: the venue's quantity, the statement's price
    t.m.request_resolve(oid, o["qty"], 49.55, 1.0, "statement")
    t.tick("15:59:10")
    done = next(x for x in t.m.state["last_run"]["orders"] if x["id"] == oid)
    assert (done["filled"], done["price"]) == (o["qty"], 49.55) and "resolved by the operator" in done["how"]
    assert not REFUSED(t, "resolve")


def test_n01_an_adjustment_that_would_put_a_sleeve_in_debt_needs_force(tmp_path):
    """the reviewer's N-01b: a $29.00 fee typed as 29000 put HG $28,900 in debt, and the next session
    sold its holdings 'to repair a cash debt'"""
    r = invested(tmp_path)
    hg = r.m.book.sleeves["HG"]
    held, cash0 = dict(hg.shares), hg.cash
    r.venue.cash -= 29.0                                       # the account paid a $29.00 fee
    r.m.request_adjust("HG", None, 0, -29000.0, "wire fee 29.00")
    r.tick("15:56:00")
    assert hg.cash == cash0 and r.m.state["requests"] == []
    said = [a for a in REFUSED(r, "adjust") if "IN DEBT" in a and '"force": true' in a]
    assert len(said) == 1 and [x for x in r.journal() if x["event"] == "request_refused" and x["kind"] == "adjust"]
    r.m.request_adjust("HG", None, 0, -29.0, "wire fee 29.00")             # the twin: the amount that was meant
    r.tick("15:56:10")
    assert hg.cash == pytest.approx(cash0 - 29.0) and len(REFUSED(r, "adjust")) == 1
    r.brain.make = lambda now: payload(now, session=D2)
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    assert r.m.state["last_run"]["session"] == D2 and [q for _, q in r.orders()[n:] if q < 0] == [] and hg.shares == held
    forced = r.m.request_adjust("HG", None, 0, -(hg.cash + 100.0), "margin interest, statement line 9", force=True)
    assert forced["force"] is True
    r.tick("15:56:00", day=D2)                                 # the other twin: said twice, it is taken
    assert hg.cash == pytest.approx(-100.0) and len(REFUSED(r, "adjust")) == 1


def test_n01_a_debit_that_would_put_a_sleeve_in_debt_needs_force(tmp_path):
    r = invested(tmp_path)
    k = r.m.book.sleeves["KMLM"]
    held, cash0 = dict(k.shares), k.cash
    fee = round(cash0 + 400.0, 2)
    assert r.m.request_credit("KMLM", -fee, "fee")["force"] is False
    r.brain.make = lambda now: payload(now, session=D2)
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["credits"] == [] and k.cash == cash0 and k.shares == held
    assert row["sleeves"]["KMLM"]["action"] == "hold" and [q for _, q in r.orders()[n:] if q < 0] == []
    assert any("REFUSED" in x and "IN DEBT" in x for x in row["notes"])
    assert len([a for a in r.red() if "refused" in a and "IN DEBT" in a and "force" in a]) == 1
    assert [x for x in r.journal() if x["event"] == "credit_refused"] and r.m.state["requests"] == []
    r.venue.cash -= fee                                        # the twin: it is meant (the account really paid it)
    r.m.request_credit("KMLM", -fee, "fee", force=True)
    r.brain.make = lambda now: payload(now, session=D3)
    r.tick("15:55:05", day=D3)
    row = r.m.state["last_run"]
    assert [c["amount"] for c in row["credits"]] == [-fee] and "debt" in row["sleeves"]["KMLM"]["reason"]
    assert k.cash >= 0 and sum(k.shares.values()) < sum(held.values())
    sound(r)


def test_n01_a_debit_that_will_be_refused_does_not_open_the_cash_gate(tmp_path):
    """the pre-trade cash gate counts the queued debits the plan WILL apply (a fee the account
    already paid must be able to clear it); one the plan will refuse must not count, or the book
    would trade with more cash than the account holds"""
    r = invested(tmp_path)
    k = r.m.book.sleeves["KMLM"]
    r.venue.cash -= 500.0                                      # the account is $500 short of the book
    r.m.request_credit("KMLM", -round(k.cash + 400.0, 2), "fee")           # ... and this debit will be refused (no force)
    r.brain.make = lambda now: payload(now, session=D2)
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    r.tick("15:58:00", day=D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "skipped" and "exceeds the account's" in row["reason"]
    assert r.orders()[n:] == [] and len(r.m.state["requests"]) == 1        # nothing traded; the request still waits
    t = invested(tmp_path / "twin")                            # the twin: a debit the plan applies clears the gate
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.venue.cash -= 20.0
    t.m.request_credit("KMLM", -20.0, "fee")
    t.brain.make = lambda now: payload(now, session=D2)
    t.tick("15:55:05", day=D2)
    assert t.m.state["last_run"]["outcome"] != "skipped" and [c["amount"] for c in t.m.state["last_run"]["credits"]] == [-20.0]
    sound(t)


# =============================================================================================== N-02
def test_n02_a_flatten_never_says_complete_while_the_account_still_holds_stock(tmp_path):
    """the reviewer's scenario: SOXL split 2:1 overnight and no payload has listed it. The flatten
    sells what the BOOK knows; the closing line used to say 'flatten complete' with half the position
    still in the account"""
    r = invested(tmp_path)
    book = dict(r.m.book.positions())
    r.venue._positions["SOXL"] *= 2
    r.alerts.clear()
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    ticks(r, 5, 6)
    h = r.m.halt_state()
    assert h["flatten_done"] is True and h["account_flat"] is False
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {"SOXL": book["SOXL"]}
    line = [a for a in r.alerts if "flatten" in a and "complete" in a]
    assert len(line) == 1 and line[0].startswith("🚨") and "flatten NOT complete" in line[0]
    assert f"the ACCOUNT still holds {{'SOXL': {book['SOXL']}}}" in line[0] and "by hand" in line[0]
    assert r.m.view()["halt"]["account_flat"] is False         # what /status shows
    done = [x for x in r.journal() if x["event"] == "flatten_done"][-1]
    assert done["account_flat"] is False and done["account"] == {"SOXL": book["SOXL"]} and done["left"] == {}
    assert "account_flat" not in r.m.halt("KILL", flatten=True)            # a new /kill starts without the old reading
    t = invested(tmp_path / "twin")                            # the twin: the account IS the book -> complete
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.alerts.clear()
    t.m.halt("KILL", flatten=True)
    t.tick("15:56:00")
    line = [a for a in t.alerts if "flatten" in a and "complete" in a]
    assert len(line) == 1 and line[0].startswith("🪞") and "flatten complete:" in line[0] and "ACCOUNT" not in line[0]
    assert t.m.halt_state()["account_flat"] is True and not t.red()
    sound(t)


def test_n02_an_account_that_cannot_be_read_or_holds_something_else_is_never_complete(tmp_path):
    r = invested(tmp_path)
    real = r.venue.positions_snapshot
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] >= 3:                                    # (1: the round, 2: the round that finds the book flat)
            raise RuntimeError("positions request timed out")
        return real()
    r.venue.positions_snapshot = flaky
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    assert r.m.halt_state()["flatten_done"] is True and r.m.halt_state()["account_flat"] is None
    line = [a for a in r.red() if "flatten NOT complete" in a]
    assert len(line) == 1 and "the ACCOUNT could not be read" in line[0] and "by hand" in line[0]
    o = invested(tmp_path / "other")
    os.makedirs(tmp_path / "other", exist_ok=True)
    real_o = o.venue.positions_snapshot
    o.venue.positions_snapshot = lambda: dict(real_o(), other=["STK SOXL fractional 0.5"])
    o.m.halt("KILL", flatten=True)
    o.tick("15:56:00")
    assert o.m.halt_state()["account_flat"] is False
    assert any("flatten NOT complete" in a and "fractional" in a for a in o.red())


# =============================================================================================== N-04
def never_reached(r, symbol="BOXX"):
    """the first placement of `symbol` raises before anything reaches the venue"""
    real, n = r.venue.place_limit_order, {"k": 0}

    def flaky(sym, qty, limit_price, **kw):
        if sym == symbol and not n["k"]:
            n["k"] += 1
            raise RuntimeError("gateway not connected")
        return real(sym, qty, limit_price, **kw)
    r.venue.place_limit_order = flaky
    return f"mirror-{DAY}-B-{symbol}"


@pytest.mark.parametrize("absent, proven", [(True, True), (False, False), (None, False)])
def test_n04_on_a_gateway_without_completed_orders_today_s_order_is_proven_absent_by_open_orders_and_executions(
        tmp_path, absent, proven):
    """the gateway this service runs against never answers reqCompletedOrders: history_complete() is
    False after every lookup, and every order whose placement raised before the venue was UNRESOLVED
    until an operator resolved an order that provably never existed"""
    r = live_rig(tmp_path)
    r.venue.history_ok = False
    r.venue.absent = absent
    oid = never_reached(r)
    r.tick("15:55:05")
    if proven:                                                 # open orders AND today's executions answered: neither has it
        assert r.m.state["last_run"]["outcome"] == "traded" and [s for s, _ in r.orders()].count("BOXX") == 1
        assert r.m.book.positions()["BOXX"] > 0 and not r.red() and r.venue.absent_asked == [oid]
        sound(r)
    else:                                                      # it shows it, or one of the two did not answer
        rec = r.m.state["run"]["orders"][oid]
        assert rec["state"] == "intent" and rec.get("stuck") and [s for s, _ in r.orders()].count("BOXX") == 0
        assert ("did not both answer" if absent is None else "open or executed") in rec["stuck"]
        assert any("UNRESOLVED" in a and oid in a for a in r.red())


def test_n04_an_acknowledged_order_that_is_neither_open_nor_executed_today_died_unfilled(tmp_path):
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")
    r.tick("15:55:05")
    oid = f"mirror-{DAY}-B-TECL"
    r.venue.forgotten.add(oid)
    r.venue.history_ok, r.venue.absent = False, True
    r.tick("15:59:05")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["id"] == oid)
    assert r.m.state["run"] is None and tecl["filled"] == 0
    assert "neither among the venue's open orders nor among today's executions" in tecl["how"]


def test_n04_absence_today_proves_nothing_about_an_order_of_an_earlier_day(tmp_path):
    r = live_rig(tmp_path)
    r.venue.crash_after.add("PULS")                            # it FILLED; the process died before 'placed' was saved
    with pytest.raises(Crash):
        r.tick("15:55:05")
    oid = f"mirror-{DAY}-B-PULS"
    r.venue.crash_after.clear()
    r.venue.forgotten.add(oid)
    r.venue.absent = True                                      # the next day: not open, no execution TODAY
    r.boot()
    r.tick("09:35:00", day=D2)
    r.tick("09:35:05", day=D2)
    rec = r.m.state["run"]["orders"][oid]
    assert rec["state"] == "intent" and "only answers for today" in rec["stuck"]
    assert r.venue.absent_asked == [] and [s for s, _ in r.orders()].count("PULS") == 1


# =============================================================================================== N-08
def test_n08_the_loop_is_asked_back_when_the_next_flatten_round_is_due(tmp_path):
    """the rounds are minutes apart now: between two of them the book asks the loop back for the
    moment the next one is due (never later than the loop's own cadence), not every five seconds"""
    def waits(r):
        r.venue.reject.add("SOXL")
        r.m.halt("KILL", flatten=True)
        t0 = r.clock.now = at("10:00:00", D2)
        out = {}
        for _ in range(18):
            r.m.tick(r.venue)
            out[int((r.clock.now - t0).total_seconds())] = r.m.next_wait()
            r.clock.now += timedelta(seconds=5)
        return out
    w = waits(invested(tmp_path, poll_s=3600.0))
    assert [w[t] for t in (0, 5, 20, 80)] == [5.0] * 4          # a round's order is in flight: the flatten cadence
    assert (w[10], w[15], w[25], w[50], w[85]) == (10.0, 5.0, 55.0, 30.0, 295.0)       # waiting: until the round is due
    os.makedirs(tmp_path / "short", exist_ok=True)
    assert waits(invested(tmp_path / "short", poll_s=120.0))[85] == 120.0     # ... or the loop's own cadence, if shorter


# =============================================================================================== N-09
def test_n09_a_paper_tick_hands_the_loop_back_after_ten_seconds_and_a_live_one_keeps_its_budget(tmp_path):
    """a paper book shares the one loop thread with the live blend: a brain that is down held that
    thread for the whole tick budget (150 s), twice, around the blend's own decision"""
    assert (mm.PAPER_TICK_BUDGET_S, mm.PAPER_RETRY_S) == (20.0, 10.0)
    assert (mm.TICK_BUDGET_S, mm.INTENTS_RETRY_S) == (150.0, 3.0)          # live keeps its values
    p = Rig(tmp_path)
    p.tick("15:00")
    p.brain.fail = "http_503"
    t0 = p.clock.now = at("15:54:25")
    p.m.tick(None)
    assert (p.clock.now - t0).total_seconds() == 10.0 and len(p.brain.calls) == 2 and p.clock.slept == [10.0]
    assert p.m.next_wait() == 2.0                              # ... and asks again through the loop, not inside it
    p.brain.fail = None
    p.clock.now += timedelta(seconds=2)
    p.m.tick(None)
    assert p.m.state["last_run"]["outcome"] == "traded"        # the brain back two seconds later: nothing was lost
    live = live_rig(tmp_path / "live")
    os.makedirs(tmp_path / "live", exist_ok=True)
    live.brain.fail = "http_503"
    t0 = live.clock.now = at("15:54:25")
    live.m.tick(live.venue)
    assert 144.0 <= (live.clock.now - t0).total_seconds() <= 150.0 and len(live.brain.calls) > 40
    assert set(live.clock.slept) == {3.0}


def test_n09_with_the_clock_unknown_a_paper_book_asks_for_the_loop_every_five_minutes(tmp_path):
    def waits(r):
        r.brain.session_fail = "transport"
        out = []
        for hms in ("09:20:00", "09:30:00", "11:00:00", "15:29:00", "15:30:00", "15:59:00", "16:05:00"):
            r.tick(hms)
            out.append(r.m.next_wait())
        return out
    assert waits(Rig(tmp_path)) == [None, 300.0, 300.0, 300.0, 60.0, 60.0, None]
    os.makedirs(tmp_path / "live", exist_ok=True)
    assert waits(Rig(tmp_path / "live", live=True)) == [None, 60.0, 60.0, 60.0, 20.0, 20.0, None]      # live: unchanged


# =============================================================================================== residuals
def test_a23_the_commission_true_up_hands_a_woken_loop_back_after_one_venue_read(tmp_path):
    r = live_rig(tmp_path)
    r.venue.commission, r.venue.report_commission = 1.0, False
    r.tick("15:55:05")
    assert len(r.m.state["commission_pending"]) == 5
    r.venue.report_commission = True
    wake = threading.Event()
    real, asked = r.venue.stock_order_fills, []

    def fills(cid):
        asked.append(cid)
        if len(asked) == 1:
            wake.set()                                         # /kill pokes the loop during the FIRST read
        return real(cid)
    r.venue.stock_order_fills = fills
    r.clock.now = at("15:56:00")
    r.m.tick(r.venue, wake=wake)
    assert len(asked) == 1 and len(r.m.state["commission_pending"]) == 4   # one read, booked; the loop has the thread
    wake.clear()
    r.clock.now = at("15:56:05")
    r.m.tick(r.venue, wake=wake)
    assert len(asked) == 1                                     # (throttled: not every tick)
    r.clock.now = at("16:06:05")
    r.m.tick(r.venue, wake=wake)                               # the twin: no wake -> the other four, one pass
    assert len(asked) == 5 and r.m.state["commission_pending"] == []
    assert r.m.book.cash() == pytest.approx(r.venue.cash, abs=0.01)


def test_a20_a_stuck_run_stops_spinning_the_loop_once_the_session_has_closed(tmp_path):
    r, oid, _ = stuck_buy(tmp_path)
    cancel = at("15:59:00")
    for dt, want in ((5, 2.0), (mm.STUCK_FAST_S - 1, 2.0), (mm.STUCK_FAST_S, None), (3600, None), (86400, None)):
        r.clock.now = cancel + timedelta(seconds=dt)
        assert r.m.next_wait() == want, dt                     # fast while its DAY orders can still die, then the ordinary cadence
    r.clock.now = at("16:10:00")
    r.m.tick(r.venue)
    assert r.m.state["run"] is not None and r.m.next_wait() is None        # still unresolved; still not spinning
    r.venue.forgotten.clear()                                  # the twin: resolved by the venue at the next ordinary pass
    r.venue.history_ok = True
    r.clock.now = at("16:15:00")
    r.m.tick(r.venue)
    assert r.m.state["run"] is None


# =============================================================================================== R3
BAD_SYNC = [
    (None, ["no sync row in the payload"]),
    ("gone", ["no sync row in the payload"]),
    ({"state": "none", "approved_version": "v-HARV", "approved_sha1": "x", "live_version": None, "attested_utc": None},
     ["sync state 'none'", "approved version 'v-HARV'", "live version None"]),
    ({"state": "stale", "approved_version": "v7", "approved_sha1": "x", "live_version": "v8",
      "attested_utc": "2026-11-10T19:00:00Z"}, ["sync state 'stale'", "approved version 'v7'", "live version 'v8'"]),
    ({"approved_version": "v7", "live_version": "v7"}, ["sync state None", "'v7'"]),
    ({"state": "OK", "approved_version": "v7", "live_version": "v7"}, ["sync state 'OK'"]),
]


def with_sync(row, name="HARV", targets=None, **kw):
    def make(now):
        p = payload(now, targets, **kw)
        if row is None:
            p["sync"].pop(name)
        else:
            p["sync"][name] = row
        return p
    return make


@pytest.mark.parametrize("row, says", BAD_SYNC)
def test_r3_a_live_sleeve_is_not_traded_on_a_tree_the_payload_does_not_attest(tmp_path, row, says):
    """the tree the brain evaluated must be the one live on Composer. The brain can be configured to
    answer 'ok' regardless; the LIVE book reads the payload's own sync row and fails closed"""
    r = live_rig(tmp_path)
    r.brain.make = with_sync(row)
    r.tick("15:55:05")
    run = r.m.state["last_run"]
    harv = run["sleeves"]["HARV"]
    assert harv["action"] == "skip" and "LIVE tree gate" in harv["reason"] and "not traded" in harv["reason"]
    assert all(x in harv["reason"] for x in says), harv["reason"]
    assert r.m.book.sleeves["HARV"].shares == {} and r.m.book.sleeves["HARV"].cash == pytest.approx(15_000.0)
    assert all(run["sleeves"][n]["action"] == "trade" for n in ("HG", "KMLM", "SLEEVE"))     # the attested ones trade
    assert r.m.book.positions()["PULS"] == r.m.book.sleeves["KMLM"].shares["PULS"]
    assert [x for x in r.journal() if x["event"] == "plan"][0]["sleeves"]["HARV"]["action"] == "skip"
    sound(r)


def test_r3_a_payload_with_no_sync_at_all_trades_nothing_live_and_everything_on_paper(tmp_path):
    for sync in (None, {}, "x"):
        path = tmp_path / f"live-{sync!r:.4}".replace("'", "")
        os.makedirs(path, exist_ok=True)
        r = live_rig(path)
        r.brain.make = lambda now, sync=sync: payload(now, sync=sync)
        r.tick("15:55:05")
        row = r.m.state["last_run"]
        assert row["outcome"] == "no-targets" and r.orders() == [] and r.m.book.positions() == {}
        assert all(d["action"] == "skip" and "LIVE tree gate" in d["reason"] for d in row["sleeves"].values())
    p = Rig(tmp_path / "paper")                                # the paper book trades regardless, and notes it
    os.makedirs(tmp_path / "paper", exist_ok=True)
    p.brain.make = lambda now: payload(now, sync=None)
    p.tick("15:55:05")
    row = p.m.state["last_run"]
    assert row["outcome"] == "traded" and len(row["orders"]) == 5
    assert len([n for n in row["notes"] if n.startswith("paper:") and "a live book refuses this" in n]) == 4
    t = live_rig(tmp_path / "twin")                            # the twin: every row "ok" -> the live book trades them all
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.tick("15:55:05")
    assert all(d["action"] == "trade" for d in t.m.state["last_run"]["sleeves"].values()) and not t.red()


def test_r3_when_the_brain_holds_the_sleeve_back_too_both_reasons_are_on_the_record(tmp_path):
    r = live_rig(tmp_path)
    r.brain.make = with_sync({"state": "drift", "approved_version": "v7", "live_version": "v9"}, targets=dict(T1, HARV=None))
    r.tick("15:55:05")
    why = r.m.state["last_run"]["sleeves"]["HARV"]["reason"]
    assert "LIVE tree gate" in why and "sync state 'drift'" in why and "the brain also says: no prices for X" in why
    t = live_rig(tmp_path / "twin")                            # the twin: attested, and only the brain holds it back
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.brain.make = lambda now: payload(now, dict(T1, HARV=None))
    t.tick("15:55:05")
    assert t.m.state["last_run"]["sleeves"]["HARV"]["reason"] == "brain: no prices for X"


# =============================================================================================== R4
PROBLEMS = ["HARV: no price for ZVOL at the decision bar", "x" * 500, "third", "fourth", "fifth"]


def test_r4_a_live_session_that_left_an_active_sleeve_out_is_red_and_says_why(tmp_path):
    r = live_rig(tmp_path)
    r.brain.make = lambda now: payload(now, dict(T1, HARV=None), problems=PROBLEMS)       # the brain: HARV unavailable
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert row["sleeves"]["HARV"]["action"] == "skip" and row["outcome"] == "traded"
    assert row["problems"] == [PROBLEMS[0], "x" * 200, "third", "fourth"]                 # the first few, truncated
    line = [a for a in r.alerts if f"{DAY} traded" in a]
    assert len(line) == 1 and line[0].startswith("🚨") and "HARV NOT TRADED — " in line[0]
    assert "THE BRAIN'S PROBLEMS: HARV: no price for ZVOL" in line[0] and "fourth" not in line[0]
    assert len(line[0]) < 2000
    t = live_rig(tmp_path / "twin")                            # the twin: every sleeve traded -> the plain line
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.brain.make = lambda now: payload(now, problems=PROBLEMS)
    t.tick("15:55:05")
    line = [a for a in t.alerts if f"{DAY} traded" in a]
    assert len(line) == 1 and line[0].startswith("🪞") and "NOT TRADED" not in line[0] and "PROBLEMS" not in line[0]
    assert not t.red()
    h = invested(tmp_path / "hold")                            # ... and a threshold sleeve HOLDING is not 'left out'
    os.makedirs(tmp_path / "hold", exist_ok=True)
    h.brain.make = lambda now: payload(now, session=D2)
    h.tick("15:55:05", day=D2)
    assert h.m.state["last_run"]["sleeves"]["KMLM"]["action"] == "hold" and not h.red()


def test_r4_on_paper_it_is_a_warning_and_no_targets_at_all_is_loud_too(tmp_path):
    p = Rig(tmp_path)
    p.brain.make = lambda now: payload(now, dict(T1, HARV=None), problems=PROBLEMS)
    p.tick("15:55:05")
    line = [a for a in p.alerts if f"{DAY} traded" in a]
    assert len(line) == 1 and line[0].startswith("⚠️") and "HARV NOT TRADED" in line[0] and "THE BRAIN'S PROBLEMS" in line[0]
    assert not p.red()
    none = live_rig(tmp_path / "none")
    os.makedirs(tmp_path / "none", exist_ok=True)
    none.brain.make = lambda now: payload(now, {n: None for n in T1}, problems=["FMP: 429 on every quote"])
    none.tick("15:55:05")
    assert none.m.state["last_run"]["outcome"] == "no-targets"
    line = [a for a in none.red() if "no-targets" in a]
    assert len(line) == 1 and "HARV, HG, KMLM, SLEEVE NOT TRADED" in line[0] and "FMP: 429 on every quote" in line[0]


# =============================================================================================== N4
class PlainHttpBrain(mm.HttpBrain):
    pass


def test_n4_a_brain_url_that_is_not_https_is_never_asked_and_the_book_says_so_once(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(mm.httpx, "get", lambda *a, **k: sent.append(a) or (_ for _ in ()).throw(AssertionError("sent")))
    for live in (True, False):
        path = tmp_path / str(live)
        os.makedirs(path, exist_ok=True)
        r = Rig(path, live=live)
        r.brain = PlainHttpBrain("http://mirror-brain.internal:8000", "tok")
        r.boot()
        for hms in ("10:00:00", "12:00:00", "15:55:05", "15:59:30"):
            r.tick(hms)
        said = [a for a in r.red() if "MIRROR_BRAIN_URL is not https" in a]
        assert len(said) == 1 and "token" in said[0] and r.orders() == []
        assert r.m.brain_status["session"] == {"ok": False, "reason": "insecure_url", "utc": mm._iso(at("15:59:30"))}
    assert sent == []                                          # nothing ever left the process


# =============================================================================================== V2-B2
def test_v2b2_a_dividend_that_goes_ex_after_a_flatten_is_not_owed_to_the_sleeves_that_were_sold_out(tmp_path):
    """the history a dividend reads its entitlement from held only planned sessions: a book flattened
    on Tuesday still 'held' PULS at Tuesday's close for a dividend going ex on Thursday"""
    r = invested(tmp_path)
    held = r.m.book.sleeves["HARV"].shares["PULS"]
    r.m.halt("KILL", flatten=True)
    r.tick("15:57:00")
    assert r.m.book.positions() == {}
    row = r.m.state["history"][-1]
    assert (row["session"], row["outcome"], row["reason"]) == (DAY, "holdings", "flatten")
    assert all(d["shares"] == {} for d in row["sleeves"].values())
    r.m.resume()
    r.brain.fail = "transport"                                 # D2's session is lost; the dividend is first seen on D3
    r.tick("15:55:05", day=D2)
    r.tick("15:58:00", day=D2)
    r.brain.fail = None
    r.brain.make = with_div(D3, {n: None for n in T1})
    r.tick("15:55:05", day=D3)
    assert r.m.state["dividends"] == [] and r.m.state["div_seen"] == [f"div-PULS-{D2}"]       # ex D2: nobody held it
    k = invested(tmp_path / "kept")                            # the twin: no flatten -> the receivable is owed
    os.makedirs(tmp_path / "kept", exist_ok=True)
    k.brain.fail = "transport"
    k.tick("15:55:05", day=D2)
    k.tick("15:58:00", day=D2)
    k.brain.fail = None
    k.brain.make = with_div(D3)
    k.tick("15:55:05", day=D3)
    assert {x["sleeve"]: x["shares"] for x in k.m.state["dividends"]}["HARV"] == held


def test_v2b2_a_flatten_on_the_ex_date_itself_does_not_lose_the_entitlement(tmp_path):
    """the other edge: the shares were held at the close BEFORE the ex-date and sold on it"""
    r = invested(tmp_path)
    held = r.m.book.sleeves["HARV"].shares["PULS"]
    r.m.halt("KILL", flatten=True)
    r.tick("10:00:00", day=D2)                                 # flattened on D2, the ex-date
    assert r.m.book.positions() == {} and r.m.state["history"][-1]["session"] == D2
    r.m.resume()
    r.tick("10:00:10", day=D2)
    r.brain.make = with_div(D3, {n: None for n in T1})
    r.tick("15:55:05", day=D3)
    assert {x["sleeve"]: x["shares"] for x in r.m.state["dividends"]}["HARV"] == held


def test_v2b2_a_dividend_after_a_split_is_owed_on_the_split_adjusted_shares(tmp_path):
    """a split applied by a session that then did not trade (or whose row is not the last before the
    ex-date) left the pre-split share count as the entitlement of a dividend that goes ex after it"""
    d = Rig(tmp_path)
    d.tick("15:55:05")
    before = {n: s.shares.get("PULS", 0) for n, s in d.m.book.sleeves.items()}
    px2 = dict(PX, PULS=PX["PULS"] / 2)
    split = [{"ticker": "PULS", "date": D2, "ratio": 2.0}]
    d.brain.make = lambda now: payload(now, {n: None for n in T1}, prices=px2, session=D2, splits=split)
    d.tick("15:55:05", day=D2)                                 # the split is applied; no sleeve trades this session
    after = {n: s.shares.get("PULS", 0) for n, s in d.m.book.sleeves.items()}
    assert after == {n: 2 * q for n, q in before.items()} and after["HARV"] > 0
    rows = [x for x in d.m.state["history"] if x["outcome"] == "holdings"]
    assert len(rows) == 1 and rows[0]["session"] == D2 and rows[0]["reason"] == "split PULS x2" and rows[0]["from_open"] is True
    assert rows[0]["sleeves"]["HARV"]["shares"]["PULS"] == after["HARV"]
    d.brain.fail = "transport"                                 # D3, the ex-date, is lost
    d.tick("15:55:05", day=D3)
    d.tick("15:58:00", day=D3)
    d.brain.fail = None
    div = {"ticker": "PULS", "ex_date": D3, "pay_date": D4, "amount": 0.10}
    d.brain.make = lambda now: payload(now, prices=px2, session=D4, splits=split, dividends=[div])
    d.tick("15:55:05", day=D4)
    recs = {x["sleeve"]: x for x in d.m.state["dividends"]}
    assert recs["HARV"]["shares"] == after["HARV"] and recs["KMLM"]["shares"] == after["KMLM"]     # post-split
    assert recs["HARV"]["total"] == pytest.approx(after["HARV"] * 0.10)
    same = {"ticker": "PULS", "ex_date": D2, "pay_date": D4, "amount": 0.20}      # ex ON the split date, seen late:
    d.brain.make = lambda now: payload(now, prices=px2, session="2026-11-16", splits=split, dividends=[div, same])
    d.tick("15:55:05", day="2026-11-16")                       # what that day's own plan would have seen (post-split)
    late = [x for x in d.m.state["dividends"] if x["ex_date"] == D2]
    assert {x["sleeve"]: x["shares"] for x in late} == {n: q for n, q in after.items() if q}
    early = {"ticker": "PULS", "ex_date": DAY, "pay_date": D4, "amount": 0.30}    # the twin: ex BEFORE the split -> the
    t = Rig(tmp_path / "twin")                                 # shares at the close before THAT (none: a new book)
    os.makedirs(tmp_path / "twin", exist_ok=True)
    t.tick("15:55:05")
    t.brain.make = lambda now: payload(now, {n: None for n in T1}, prices=px2, session=D2, splits=split)
    t.tick("15:55:05", day=D2)
    pre = {"ticker": "PULS", "ex_date": D2, "pay_date": D4, "amount": 0.30}
    t.m.state["history"] = [dict(x, from_open=False) if x.get("outcome") == "holdings" else x for x in t.m.state["history"]]
    t.brain.make = lambda now: payload(now, prices=px2, session=D3, splits=split, dividends=[pre, early])
    t.tick("15:55:05", day=D3)                                 # (a row NOT from the open answers only for later ex-dates)
    got = {x["sleeve"]: x["shares"] for x in t.m.state["dividends"] if x["ex_date"] == D2}
    assert got == {n: q for n, q in before.items() if q}
    assert [x for x in t.m.state["dividends"] if x["ex_date"] == DAY] == []


def test_v2b2_a_split_applied_late_is_recorded_on_its_own_date(tmp_path):
    """the second verifier's scenario: neither the split's session nor the ex-date's is planned (the
    brain was down); the split is applied two sessions late and must still be in force for the
    dividend that went ex in between"""
    r = invested(tmp_path)
    before = {n: s.shares.get("PULS", 0) for n, s in r.m.book.sleeves.items()}
    r.venue._positions["PULS"] *= 3                            # PULS splits 3:1 on D2 ...
    r.venue.quotes["PULS"] = PX["PULS"] / 3
    r.brain.fail = "transport"                                 # ... and D2 and D3 (the ex-date) are both lost
    for day in (D2, D3):
        r.tick("15:55:05", day=day)
        r.tick("15:58:00", day=day)
    r.brain.fail = None
    px3 = dict(PX, PULS=PX["PULS"] / 3)
    div = {"ticker": "PULS", "ex_date": D3, "pay_date": "2026-11-20", "amount": 0.10}
    r.brain.make = lambda now: payload(now, prices=px3, session=D4, splits=[{"ticker": "PULS", "date": D2, "ratio": 3.0}],
                                       dividends=[div])
    r.tick("15:55:05", day=D4)
    row = next(x for x in r.m.state["history"] if x["outcome"] == "holdings")
    assert (row["session"], row["from_open"]) == (D2, True)    # dated the SPLIT's day, not the session that applied it
    recs = {x["sleeve"]: x["shares"] for x in r.m.state["dividends"]}
    assert recs == {n: 3 * q for n, q in before.items() if q}  # what the venue will pay on
    sound(r)


def test_v2b2_an_adjustment_of_shares_is_in_the_history_too(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    held = d.m.book.sleeves["HARV"].shares["PULS"]
    d.m.request_adjust("HARV", "PULS", -100, 100 * PX["PULS"], "sold by hand")
    d.m.request_adjust("HG", None, 0, -1.0, "fee")             # cash only: no row
    d.tick("16:30:00")
    rows = [x for x in d.m.state["history"] if x["outcome"] == "holdings"]
    assert len(rows) == 1 and (rows[0]["session"], rows[0]["reason"], rows[0]["from_open"]) == (DAY, "adjust", False)
    assert rows[0]["sleeves"]["HARV"]["shares"]["PULS"] == held - 100
    d.brain.fail = "transport"
    d.tick("15:55:05", day=D2)
    d.tick("15:58:00", day=D2)
    d.brain.fail = None
    d.brain.make = with_div(D3)
    d.tick("15:55:05", day=D3)
    assert {x["sleeve"]: x["shares"] for x in d.m.state["dividends"]}["HARV"] == held - 100


# =============================================================================================== missing gates
def test_gate_the_flatten_holds_back_a_symbol_whose_run_order_is_unresolved(tmp_path):
    """an unresolved SELL may or may not have sold the shares: selling them again could go short.
    (Round 1's gate used an unresolved BUY of a symbol the book did not hold, which the hold-back
    never touches.)"""
    r, oid, o = stuck_sell(tmp_path)
    n = len(r.venue.placed)
    r.m.halt("KILL", flatten=True)
    r.tick("15:59:10", day=D2)
    r.tick("15:59:15", day=D2)
    assert [s for s, _, _ in r.venue.placed[n:]] == []         # BIL is all the book holds, and it is held back
    assert r.m.book.positions() == {"BIL": o["qty"]} and r.m.halt_state()["flatten_done"] is False
    said = [a for a in r.red() if "held back" in a]
    assert len(said) == 1 and "BIL" in said[0] and oid in said[0] and "/mirror/resolve" in said[0]
    r.venue.hold.clear()
    r.m.request_resolve(oid, 0, None, 0.0, "cancelled unfilled, per the statement")
    r.tick("15:59:20", day=D2)                                 # the twin: once it is resolved the flatten takes it
    r.tick("15:59:25", day=D2)
    flat = [(s, q, c) for s, q, c in r.venue.placed[n:]]
    assert len(flat) == 1 and flat[0][:2] == ("BIL", -o["qty"]) and "mirror-flat-" in flat[0][2]
    assert r.m.book.positions() == {} and r.m.halt_state()["flatten_done"] is True
    sound(r)


def test_gate_a_halt_that_lands_while_the_venue_is_asked_about_an_unconfirmed_order_stops_its_resend(tmp_path):
    r = live_rig(tmp_path)
    oid = never_reached(r)
    find = r.venue.find_stock_order

    def find_then_halt(cid):
        out = find(cid)
        if cid == oid and not r.m.halt_state().get("halted"):
            r.m.halt("operator halt")                          # /mirror/halt lands while the venue is being asked
        return out
    r.venue.find_stock_order = find_then_halt
    r.tick("15:55:05")
    assert r.m.halt_state()["halted"] is True and r.m.state["run"] is not None
    assert [s for s, _ in r.orders()].count("BOXX") == 0       # NOT sent again under the halt
    r.tick("15:55:10")                                         # the halt path settles the run
    row = r.m.state["last_run"]
    boxx = next(x for x in row["orders"] if x["id"] == oid)
    assert row["outcome"] == "aborted" and boxx["filled"] == 0 and "never reached the venue" in boxx["how"]
    assert [s for s, _ in r.orders()].count("BOXX") == 0
    sound(r)
    t = live_rig(tmp_path / "twin")                            # the twin: no halt -> sent again, once
    os.makedirs(tmp_path / "twin", exist_ok=True)
    never_reached(t)
    t.tick("15:55:05")
    assert [s for s, _ in t.orders()].count("BOXX") == 1 and t.m.state["last_run"]["outcome"] == "traded"


def test_gate_a_rekill_that_lands_as_a_cancelled_flatten_is_being_closed_is_not_lost(tmp_path):
    """_flatten_finish marks the halt's flatten done only if it is still what the tick saw: an API
    thread's /kill between the tick's read of the halt and the finish must leave the flatten armed"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.m.halt("KILL", flatten=True)
    r.tick("17:00:00")                                         # queued: the session is shut
    r.m.resume()                                               # the operator thinks again: cancelled ...
    real, seen = r.m.halt_state, {"n": 0}

    def racy():
        out = real()
        if out.get("flatten_cancelled") and not out.get("flatten_done"):
            seen["n"] += 1
            if seen["n"] == 2:                                 # ... and kills again right AFTER the loop read 'cancelled'
                r.m.halt("KILL", flatten=True)
        return out
    r.m.halt_state = racy
    r.tick("17:02:00")
    r.m.halt_state = real
    h = r.m.halt_state()
    assert seen["n"] == 2 and h["halted"] is True and h["flatten_cancelled"] is False
    assert h["flatten_done"] is False                          # NOT closed as 'cancelled': the kill stands
    assert not any("flatten cancelled" in a for a in r.alerts)
    r.tick("09:30:05", day=D2)
    assert r.m.book.positions() == {} and sorted(s for s, q in r.orders()[5:]) == sorted(held)
    assert r.m.halt_state()["flatten_done"] is True
    sound(r)


def test_gate_a_resume_that_lands_as_a_flatten_is_being_closed_is_reported_as_cancelled(tmp_path):
    r = invested(tmp_path)
    r.m.halt("KILL", flatten=True)
    real, calls, answer = r.venue.positions_snapshot, {"n": 0}, {}

    def racy():
        calls["n"] += 1
        if calls["n"] == 3:                                    # the finish's own read of the account
            answer.update(r.m.resume())                        # /resume lands here: 'flatten_cancelled'
        return real()
    r.venue.positions_snapshot = racy
    r.tick("15:56:00")
    assert answer["flatten_cancelled"] is True and r.m.book.positions() == {}
    assert r.m.halt_state()["flatten_done"] is False and not any("flatten complete" in a for a in r.alerts)
    r.tick("15:56:05")                                         # the next tick closes it as what the operator was told
    assert r.m.halt_state()["flatten_done"] is True and "account_flat" not in r.m.halt_state()
    assert len([a for a in r.alerts if "flatten cancelled" in a]) == 1
