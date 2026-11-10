"""The Composer mirror's manager driven through the REAL IBAdapter (tests/ibrig.py): the gates the
manager's own Venue double cannot give, because it remembers every order and answers every lookup.

  sound   a session, a restart, a partial-then-cancel, a crash after a fill, an Inactive placement, a
          refused cancel, a fill racing the cancel, a lost ack: the same-day paths (the review's
          'checked and found sound' probes, kept as gates)
  limit   the buys reach the venue as DAY LIMIT orders on the price grid, sized at their limit; the
          sells as DAY market orders; a limit the tape has left rests and is cancelled
  A-07    after an overnight outage a FILLED order is never booked 'never reached the venue', and an
          acknowledged one is never a run that silently never ends: both are UNRESOLVED until the
          operator states what they did
  A-11    an order that turns Inactive after its ack is cancelled before it is booked
  A-13    a restart onto bare completed orders books the executions the adapter already holds
  A-16    an execution lookup that fails closed leaves the order unresolved
"""
from __future__ import annotations

import pytest

import test_mirror as tm
from ibrig import IBRig
from test_mirror import DAY, PX, payload

D2 = "2026-11-11"


def sound(r):
    assert r.m.book.positions() == r.venue_pos()
    assert r.m.book.cash() == pytest.approx(r.acct.cash, abs=0.01)          # commissions booked with the fills
    assert r.acct.cash >= 0 and all(s.cash >= 0 for s in r.m.book.sleeves.values())


# ---------------------------------------------------------------------------------------- sound paths
def test_ib_a_session_on_the_real_adapter_is_sound(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and len(r.ib.placed) == 5
    sound(r)
    r.boot()
    r.tick("15:56:40")
    assert not r.m.halt_state().get("halted") and r.m.state["check"]["done"] is True
    assert not r.red()


def test_ib_buys_are_day_limit_orders_on_the_grid_and_sells_are_day_market_orders(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.prices.update({s: round(p * 1.004, 2) for s, p in PX.items()})     # the tape is 0.4% over the brain's bar
    r.tick("15:55:05")
    for t in r.acct.orders:                                                  # day 1: five buys
        o = t.order
        q = r.ib.prices[t.contract.symbol]
        assert (o.orderType, o.tif, o.action) == ("LMT", "DAY", "BUY") and o.orderRef == f"mirror-{DAY}-B-{t.contract.symbol}"
        assert o.lmtPrice == pytest.approx(int(q * 1.005 * 100 + 1e-9) / 100)          # quote x 1.005, floored to the cent
        assert all(f.execution.price <= o.lmtPrice for f in t.fills)
    cost = sum(t.order.totalQuantity * t.order.lmtPrice for t in r.acct.orders)
    assert cost <= 100_000.0                                                 # sized AT the limit: it cannot overdraw
    sound(r)
    n = len(r.acct.orders)
    r.ib.prices.update(PX)
    r.brain.make = lambda now: payload(now, dict(tm.T1, HG={"TQQQ": 1.0}), session=D2)
    r.tick("15:55:05", day=D2)
    new = r.acct.orders[n:]
    sells = [t for t in new if t.order.action == "SELL"]
    assert [t.contract.symbol for t in sells] == ["BIL"] and sells[0].order.orderType == "MKT" and sells[0].order.tif == "DAY"
    assert [(t.contract.symbol, t.order.orderType) for t in new if t.order.action == "BUY"] == [("TQQQ", "LMT")]
    assert new.index(sells[0]) == 0                                          # sells before buys
    sound(r)


def test_ib_a_limit_the_tape_has_left_rests_and_is_cancelled_at_the_window_end(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.fill_px["TECL"] = 102.5                                             # TECL trades 2.5% up when the order arrives
    r.tick("15:55:05")
    t = r.trade("TECL")
    assert t.orderStatus.status == "Submitted" and r.m.state["run"] is not None
    r.tick("15:59:01")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert tecl["filled"] == 0 and "cancelled" in tecl["how"] and t.orderStatus.status == "Cancelled"
    assert r.m.book.sleeves["KMLM"].cash > 10_000                            # the money stayed in the sleeve
    sound(r)


def test_ib_partial_then_cancel_at_the_window_end_is_booked_at_the_venues_price(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")
    assert r.m.state["run"] is not None
    r.ib.execute(r.trade("TECL"), 40, price=100.4)
    r.tick("15:59:01")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert (tecl["filled"], tecl["price"]) == (40, 100.4)
    sound(r)


@pytest.mark.parametrize("completed", [True, False])
def test_ib_crash_after_the_fill_same_day_restart_adopts_it_once(tmp_path, monkeypatch, completed):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.crash_after.add("PULS")
    with pytest.raises(tm.Crash):
        r.tick("15:55:05")
    r.boot(completed_available=completed)
    r.tick("15:55:40")
    assert [t.contract.symbol for t in r.acct.orders].count("PULS") == 1
    assert r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_ib_a_buy_the_venue_answers_inactive_books_zero_and_is_not_resent(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.reject["BOXX"] = "Inactive"
    r.tick("15:55:05")
    r.tick("15:55:10")
    boxx = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "BOXX")
    assert boxx["filled"] == 0 and [t.contract.symbol for t in r.acct.orders].count("BOXX") == 1
    assert ("BOXX", "Inactive") in r.ib.cancels                              # the placement path cancelled it on sight
    sound(r)


def test_ib_a_refused_cancel_keeps_the_run_open_until_the_venue_speaks(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")
    r.ib.on_cancel = lambda t: None                       # the venue never acks the cancel
    r.tick("15:59:01")
    assert r.m.state["run"] is not None
    r.ib.on_cancel = None
    r.trade("TECL").orderStatus.status = "Cancelled"      # the DAY order dies at the close
    r.tick("16:00:05")
    assert r.m.state["run"] is None
    sound(r)


def test_ib_a_fill_that_wins_the_race_with_the_window_cancel_is_booked_whole(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")
    r.ib.on_cancel = lambda tr: r.ib.execute(tr, tr.order.totalQuantity)
    r.tick("15:59:01")
    assert r.m.state["run"] is None and r.m.book.positions()["TECL"] == r.trade("TECL").order.totalQuantity
    sound(r)


def test_ib_a_placement_that_raises_no_ack_after_the_order_landed_is_adopted_not_resent(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("SOXL")

    def silent(t):                                        # the order lands, the ack never arrives
        if t.contract.symbol == "SOXL":
            t.orderStatus.status = "PendingSubmit"
    r.ib.on_place = silent
    r.tick("15:55:05")
    rec = r.m.state["run"]["orders"][f"mirror-{DAY}-B-SOXL"]
    assert rec["state"] in ("intent", "placed") and "no venue ack" in (rec.get("error") or "")
    t = r.trade("SOXL")
    r.ib.on_place = None
    r.ib.hold.clear()
    r.ib.execute(t, t.order.totalQuantity)                # it was live all along, and fills
    r.tick("15:55:20")
    assert [x.contract.symbol for x in r.acct.orders].count("SOXL") == 1
    assert r.m.state["run"] is None
    sound(r)


# ---------------------------------------------------------------------------------------- A-07
def test_ib_a07a_a_filled_order_is_never_booked_never_sent_after_an_overnight_restart(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.crash_after.add("BIL")                   # the venue fills BIL; the process dies before 'placed' is saved
    with pytest.raises(tm.Crash):
        r.tick("15:55:05")
    bil = r.venue_pos()["BIL"]
    px = r.trade("BIL").fills[0].execution.price
    assert set(r.venue_pos()) == {"BIL"}
    # the service is back the next morning; this gateway does not answer reqCompletedOrders
    # (ib_adapter.py: 'on 2026-09-08 this gateway never answered') and reqExecutions covers today only
    r.boot(next_day=True, completed_available=False)
    r.tick("09:35:00", day=D2)
    assert r.ad.history_complete() is False       # the adapter KNOWS it cannot prove 'never filled' ...
    cid = f"mirror-{DAY}-B-BIL"
    run = r.m.state["run"]
    assert run is not None and run["orders"][cid]["state"] == "intent" and run["orders"][cid]["stuck"]    # ... and the manager asks it
    assert r.m.book.positions() == {} and len(r.acct.orders) == 1            # not booked as zero; not sent again
    assert any("UNRESOLVED" in a and cid in a for a in r.red())
    r.m.request_resolve(cid, bil, px, 1.0, "activity statement 2026-11-10")
    r.tick("09:36:00", day=D2)                    # the operator states what the account shows
    assert r.m.state["run"] is None and r.m.book.positions() == {"BIL": bil}
    assert r.m.book.cash() == pytest.approx(r.acct.cash, abs=0.01)
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)                    # the book equals the account again: the next session trades
    assert r.m.state["last_run"]["session"] == D2 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_ib_a07a_with_a_complete_history_the_next_day_is_still_no_proof(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.crash_after.add("BIL")
    with pytest.raises(tm.Crash):
        r.tick("15:55:05")
    r.acct.orders.clear()                         # the venue's completed orders no longer list yesterday's
    r.boot(next_day=True, completed_available=True)
    r.tick("09:35:00", day=D2)
    assert r.ad.history_complete() is True        # complete - for TODAY
    assert r.m.state["run"] is not None and r.m.book.positions() == {}
    assert "only answers for today" in r.m.state["run"]["orders"][f"mirror-{DAY}-B-BIL"]["stuck"]


def test_ib_a07_twin_the_same_crash_restarted_the_same_day_needs_nobody(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.crash_after.add("BIL")
    with pytest.raises(tm.Crash):
        r.tick("15:55:05")
    r.boot(completed_available=False)             # same day: today's executions answer
    r.tick("15:55:40")
    assert r.m.state["last_run"]["outcome"] == "traded" and not r.red()
    sound(r)


def test_ib_a07b_an_acknowledged_order_the_venue_forgot_is_unresolved_and_the_day_is_recorded(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("BIL")                          # acknowledged and resting: 'placed' IS on disk
    r.tick("15:55:05")
    cid = f"mirror-{DAY}-B-BIL"
    assert r.m.state["run"]["orders"][cid]["state"] == "placed"
    t = r.trade("BIL")
    r.ib.execute(t, t.order.totalQuantity)        # it fills at 15:56 while the service is restarting
    r.boot(next_day=True, completed_available=False)
    for hms in ("09:35:00", "12:00:00", "15:55:05", "15:59:30"):
        r.tick(hms, day=D2)
    assert r.m.state["run"] is not None           # never guessed at ...
    assert len([a for a in r.red() if "UNRESOLVED" in a and cid in a]) == 1          # ... said (once that day) ...
    row = r.m.state["history"][-1]
    assert (row["session"], row["outcome"]) == (D2, "skipped") and cid in row["reason"]    # ... and the lost session recorded
    r.m.request_resolve(cid, t.order.totalQuantity, t.fills[0].execution.price, 1.0)
    r.tick("16:05:00", day=D2)
    assert r.m.state["run"] is None
    sound(r)


# ---------------------------------------------------------------------------------------- A-11
def test_ib_a11_an_order_that_turns_inactive_after_its_ack_is_cancelled_before_it_is_booked(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")                            # TECL acknowledged (Submitted), resting
    t = r.trade("TECL")
    t.orderStatus.status = "Inactive"             # IBKR parks it (the BIL x56 shape, blend.py)
    r.tick("15:55:10")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert tecl["filled"] == 0 and r.m.state["run"] is None and "Inactive" in tecl["how"]
    assert r.ib.cancels == [("TECL", "Inactive")]             # the cancel WAS sent: it cannot go live unrecorded
    assert t.orderStatus.status == "Cancelled"
    sound(r)


def test_ib_a11_an_inactive_order_that_went_live_and_filled_is_booked_as_filled(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")
    t = r.trade("TECL")
    t.orderStatus.status = "Inactive"
    r.ib.on_cancel = lambda tr: r.ib.execute(tr, tr.order.totalQuantity)     # it went live and filled as the cancel arrived
    r.tick("15:55:10")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert tecl["filled"] == tecl["qty"] and r.m.state["run"] is None
    sound(r)


# ---------------------------------------------------------------------------------------- A-13
def test_ib_a13a_a_partial_fill_cancelled_at_the_close_is_booked_after_a_restart(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")                                  # TECL acknowledged and resting; the rest filled
    t = r.trade("TECL")
    r.ib.execute(t, 40, price=100.4)                    # 40 fill ...
    t.orderStatus.status = "Cancelled"                  # ... the service is mid-redeploy; the DAY order dies at the close
    r.boot(bare_completed=True)                         # back at 16:02, same day: executions known, trade rebuilt bare
    r.tick("16:02:00")
    tecl = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "TECL")
    assert (tecl["filled"], tecl["price"], tecl["commission"]) == (40, 100.4, 1.0)
    sound(r)


def test_ib_a13b_a_filled_order_is_booked_at_the_venues_price_after_a_restart(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.fill_px["PULS"] = 49.70                        # the venue fills 0.4% above the 49.50 reference
    r.ib.crash_after.add("PULS")
    with pytest.raises(tm.Crash):
        r.tick("15:55:05")
    r.boot(bare_completed=True)
    r.tick("15:55:40")
    puls = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "PULS")
    assert puls["price"] == pytest.approx(49.70) and puls["commission"] == 1.0
    assert r.m.state["commission_pending"] == [] and not any("REFERENCE price" in a for a in r.alerts)
    sound(r)


# ---------------------------------------------------------------------------------------- A-16
def test_ib_a16_an_execution_lookup_that_fails_closed_leaves_the_order_unresolved(tmp_path, monkeypatch):
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.ib.hold.add("TECL")
    r.tick("15:55:05")
    t = r.trade("TECL")
    r.ib.execute(t, 40, price=100.4)
    t.orderStatus.status = "Cancelled"
    r.boot(bare_completed=True)

    def hang():
        raise TimeoutError("execDetailsEnd never arrived")
    r.ib.reqExecutions = hang                           # the venue's history cannot be read
    r.tick("16:02:00")
    cid = f"mirror-{DAY}-B-TECL"
    assert r.m.state["run"] is not None and r.m.state["run"]["orders"][cid]["state"] != "booked"
    assert r.m.book.positions().get("TECL") is None     # NOT booked as zero
    r.boot(bare_completed=True)                         # the twin: the gateway answers again
    r.tick("16:03:00")
    assert r.m.state["run"] is None and r.m.book.positions()["TECL"] == 40
    sound(r)
