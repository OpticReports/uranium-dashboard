"""Merge-blocking gates for the THIRD verification round of the Composer mirror (reviewer A3b: the
account is a MARGIN account now, so the venue no longer refuses a short sale or an overdraft and the
executor's own arithmetic is the last line). One finding, one or more gates, each with its twin.
The doubles are tests/test_mirror.py's (Venue) and tests/ibrig.py's (the REAL IBAdapter over FakeIB).

  D-01  a /kill flatten sent under a failed state save, then a restart on the stale file: nothing is
        sold twice. A flatten order in state "new" asks the venue first; every flatten sell is cut to
        what the account holds at the moment it is sent, and is not sent when that cannot be read
  C-01  an operator's resolve commission above max($5, 1% of the trade) needs "force"
  C-02  a resolve is never booked while the venue cannot be asked (the lookup raised)
  D-04  a credit that takes a live book's seeded + credited capital above its cap needs "force";
        every credit a live book takes is alerted
  D-05  staged seeding never totals more than MIRROR_CAPITAL_USD
  C-52  live: the account's cash is read before the buys are sized; no buys when the book's exceeds it
  D-03  a live state file that holds shares with no live book built is said in red at boot
  C-10  the flatten's 30 minutes count open time between rounds, not while an order is working
  +     a live sleeve's seeding is a warning; MIRROR_WEIGHTS / MIRROR_MAX_BOOK_USD are in the deploy file
"""
from __future__ import annotations

import json
import os
import types

import pytest

import test_mirror as tm
from app import mirror as mm
from app.config import settings as app_settings
from ibrig import IBRig
from test_mirror import DAY, PX, Rig, at, live_rig, payload, sound, timedelta
from test_mirror_review import D2, ROTATE, invested
from test_mirror_round2 import stuck_buy, stuck_sell

REFUSED = lambda r: [a for a in r.red() if "REFUSED" in a]      # noqa: E731


# =============================================================================================== D-01
def _disk(mp, state_path):
    """the state directory's disk: every write from the k-th on fails (ENOSPC) until it is freed"""
    box = {"n": 0, "fail_from": None, "down": False}
    real = mm.atomic_write

    def write(path, obj):
        if path.startswith(state_path):
            box["n"] += 1
            if box["fail_from"] is not None and box["n"] >= box["fail_from"]:
                box["down"] = True
            if box["down"]:
                raise OSError(28, "No space left on device")
        return real(path, obj)
    mp.setattr(mm, "atomic_write", write)
    return box


def _killed_under_the_latch(tmp_path, monkeypatch, fail_at, completed_available, next_day=False):
    """invested on the REAL adapter; /kill; the fail_at-th state save of the flatten is the first to
    fail (the flatten still goes out: 'sent with NO record on disk'); then the process restarts on
    the stale file with the disk freed"""
    r = IBRig(tmp_path, monkeypatch)
    r.tick("15:00")
    r.tick("15:55:05")
    r.tick("15:56:00")
    assert r.m.state["run"] is None and r.venue_pos() == r.m.book.positions() and r.venue_pos()
    held = dict(r.venue_pos())
    box = _disk(monkeypatch, r.m.cfg.state_path)
    r.m.halt("KILL", flatten=True)
    box["fail_from"] = box["n"] + fail_at
    r.tick("15:57:00")
    for _ in range(3):
        r.clock.now += timedelta(seconds=6)
        r.m.tick(r.ad)
    assert r.venue_pos() == {}                              # the kill itself sold everything, once
    n0 = len(r.acct.orders)
    box["fail_from"], box["down"] = None, False
    if next_day:
        r.clock.now = at("10:00:00", D2)
    r.boot(completed_available=completed_available, next_day=next_day)
    for _ in range(6):
        r.clock.now += timedelta(seconds=6)
        r.m.tick(r.ad)
    again = [(t.contract.symbol, t.order.action, t.order.totalQuantity) for t in r.acct.orders[n0:]]
    return r, held, again


@pytest.mark.parametrize("completed_available", [False, True], ids=["gateway-without-completed-orders", "completed-orders-ok"])
@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_d01_a_flatten_sent_under_the_latch_then_a_restart_never_sells_twice(tmp_path, monkeypatch, fail_at,
                                                                              completed_available):
    """the reviewer's repro: on the gateway that never answers reqCompletedOrders the adapter's own
    dedupe does not see an order filled in an earlier session, and the stale file said 'new'"""
    r, held, again = _killed_under_the_latch(tmp_path, monkeypatch, fail_at, completed_available)
    short = {s: q for s, q in r.acct.pos.items() if q < 0}
    assert not short and again == [], (
        f"disk failed at flatten save #{fail_at}; held {held}; after the restart on the stale file the executor "
        f"sent {again} and the MARGIN account is SHORT {short}")
    if fail_at >= 2:
        # the stale file held the round with its orders 'new': the venue was ASKED and its fills booked
        assert r.m.book.positions() == {} and r.m.state["flatten"]["orders"]
        assert all(o["applied"] and o["filled"] == held[o["symbol"]] for o in r.m.state["flatten"]["orders"])
        assert [a for a in r.red() if "ALREADY at the venue" in a and "not sent again" in a]
        assert r.m.halt_state()["flatten_done"] is True and r.m.halt_state()["account_flat"] is True


@pytest.mark.parametrize("fail_at", [2, 4])
def test_d01_the_restart_comes_a_day_later_and_the_venue_no_longer_answers_for_the_orders(tmp_path, monkeypatch, fail_at):
    """the second belt: yesterday's executions are gone, so the lookup finds nothing - and the account's
    POSITIONS, read before every flatten sell, are what stops it. The book is not guessed at: it
    still shows the shares, and that is said in red."""
    r, held, again = _killed_under_the_latch(tmp_path, monkeypatch, fail_at, completed_available=False, next_day=True)
    assert again == [] and all(q >= 0 for q in r.acct.pos.values()), (again, r.acct.pos)
    assert r.m.book.positions()                             # nothing booked on a guess
    zero = [a for a in r.red() if "is NOT sent: the account holds 0" in a]
    stuck = [a for a in r.red() if "is UNRESOLVED" in a and "mirror-flat-" in a]
    if fail_at == 2:                                        # every order was still 'new' on the stale file
        assert len(zero) == len(held) and not stuck
        assert r.m.halt_state()["flatten_done"] is True
        assert [a for a in r.red() if "flatten NOT complete" in a and "STILL HELD" in a]
    else:                                                   # the file knew the first order as sent: that one is UNRESOLVED
        assert len(stuck) == 1 and len(zero) == len(held) - 1 and not r.m.halt_state().get("flatten_done")


def _after_the_round(r, change):
    """wrap the venue's positions read: `change(k)` runs before the k-th read (1 = the round's own)"""
    real, calls = r.venue.positions_snapshot, {"n": 0}

    def snap():
        calls["n"] += 1
        change(calls["n"])
        return real()
    r.venue.positions_snapshot = snap
    return real, calls


def test_d01_a_flatten_sell_is_cut_to_what_the_account_holds_when_it_is_sent(tmp_path):
    """between the round being built and an order going out the account changed (a sale by hand, a
    fill of an earlier session the book never saw): the sell is cut, never a short"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    assert held["SOXL"] > 100

    def change(k):
        if k == 2:                                          # after the round was built from the full holdings
            r.venue._positions["SOXL"] = 100
            r.venue._positions["TECL"] = 0
    real, _ = _after_the_round(r, change)
    r.m.halt("KILL", flatten=True)
    n = len(r.venue.placed)
    r.tick("15:56:00")
    sent = {s: q for s, q, _ in r.venue.placed[n:]}
    assert sent["SOXL"] == -100 and "TECL" not in sent, sent
    assert all(q >= 0 for q in r.venue._positions.values()), r.venue._positions
    assert [a for a in r.red() if "cut from" in a and "to 100 SOXL" in a]
    assert [a for a in r.red() if "is NOT sent: the account holds 0 TECL" in a]
    assert r.m.book.positions() == {"SOXL": held["SOXL"] - 100, "TECL": held["TECL"]}     # the book is not guessed at
    assert all(s in sent and sent[s] == -q for s, q in held.items() if s not in ("SOXL", "TECL"))   # the twin: the rest in full


def test_d01_a_flatten_sell_is_not_sent_while_the_positions_cannot_be_read(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    down = {"on": True}

    def change(k):
        if k >= 2 and down["on"]:
            raise RuntimeError("positions request timed out")
    _after_the_round(r, change)
    r.m.halt("KILL", flatten=True)
    n = len(r.venue.placed)
    r.tick("15:56:00")
    r.tick("15:56:05")
    assert r.venue.placed[n:] == [] and r.m.book.positions() == held
    assert not r.m.halt_state().get("flatten_done")         # still wanted, still loud
    assert len([a for a in r.red() if "is NOT sent: the account's positions cannot be read" in a]) == len(held)
    down["on"] = False                                      # the twin: readable again, the SAME orders go out
    r.tick("15:56:10")
    r.tick("15:56:15")
    assert sorted((s, q) for s, q, _ in r.venue.placed[n:]) == sorted((s, -q) for s, q in held.items())
    assert r.m.book.positions() == {} and r.m.halt_state()["account_flat"] is True
    sound(r)


def test_d01_a_new_flatten_order_asks_the_venue_before_it_is_sent(tmp_path):
    """the first belt on its own: the venue already holds the order (filled) though the state says
    'new' - it is settled from the venue's record and never placed again"""
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.m.halt("KILL", flatten=True)
    stale = json.load(open(r.m.cfg.state_path))             # the file as it was before the flatten
    r.tick("15:56:00")
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    done = json.load(open(r.m.cfg.state_path))
    # the stale file a failed save leaves behind: the round with every order still 'new'
    stale["flatten"] = dict(done["flatten"], recs={}, tallied=False, sold=[],
                            orders=[{k: v for k, v in o.items() if k in ("id", "side", "symbol", "qty", "asks", "ref")}
                                    | {"applied": False} for o in done["flatten"]["orders"]])
    json.dump(stale, open(r.m.cfg.state_path, "w"))
    halt = json.load(open(r.m.cfg.state_path + ".halt"))
    halt.update(flatten_done=False)
    halt.pop("account_flat", None)
    json.dump(halt, open(r.m.cfg.state_path + ".halt", "w"))
    asked, find = [], r.venue.find_stock_order
    r.venue.find_stock_order = lambda cid: (asked.append(cid), find(cid))[1]
    r.venue._positions.update(held)                         # (so that ONLY the lookup stands between this and a second sale)
    n = len(r.venue.placed)
    r.boot()
    assert r.m.book.positions() == held
    r.tick("15:56:30")
    assert r.venue.placed[n:] == [] and sorted(set(asked)) == sorted(o["id"] for o in done["flatten"]["orders"])
    assert r.m.book.positions() == {} and len([a for a in r.red() if "ALREADY at the venue" in a]) == len(held)


# =============================================================================================== C-01
def test_c01_a_resolve_commission_that_cannot_be_true_is_refused_without_force(tmp_path):
    r, oid, o = stuck_buy(tmp_path)
    cash = {n: s.cash for n, s in r.m.book.sleeves.items()}
    r.m.request_resolve(oid, o["qty"], o["limit"], 4960.0, "commission typo: 4.96")
    r.tick("16:01:00")
    assert r.m.state["run"] is not None and {n: s.cash for n, s in r.m.book.sleeves.items()} == cash
    said = REFUSED(r)
    assert len(said) == 1 and "commission of $4,960.00" in said[0] and "force" in said[0]
    most = max(5.0, 0.01 * o["qty"] * o["limit"])
    r.m.request_resolve(oid, o["qty"], o["limit"], round(most + 0.01, 2), "one cent over the bound")
    r.tick("16:01:10")
    assert r.m.state["run"] is not None and len(REFUSED(r)) == 2
    r.m.request_resolve(oid, o["qty"], o["limit"], round(most, 2), "exactly the bound")     # the twin: a commission that can be true
    r.tick("16:01:20")
    assert r.m.state["run"] is None and len(REFUSED(r)) == 2
    assert r.m.book.cash() == pytest.approx(sum(cash.values()) - o["qty"] * o["limit"] - round(most, 2))


@pytest.mark.parametrize("force", [True, "true", 1])
def test_c01_force_books_a_large_commission_only_as_a_literal_true(tmp_path, force):
    r, oid, o = stuck_buy(tmp_path)
    before = r.m.book.cash()
    row = r.m.request_resolve(oid, o["qty"], o["limit"], 4960.0, "meant", force=force)
    assert row["force"] is (force is True)
    r.tick("16:01:00")
    if force is True:
        assert r.m.state["run"] is None and not REFUSED(r)
        assert r.m.book.cash() == pytest.approx(before - o["qty"] * o["limit"] - 4960.0)
    else:
        assert r.m.state["run"] is not None and REFUSED(r) and r.m.book.cash() == pytest.approx(before)


def test_c01_the_small_orders_floor_is_five_dollars(tmp_path):
    """1% of a small trade is cents; IBKR's minimum commission is not: up to $5 is always taken"""
    r, oid, o = stuck_buy(tmp_path)
    r.m.request_resolve(oid, 1, o["limit"], 5.0, "one share, the venue's minimum")
    r.tick("16:01:00")
    assert r.m.state["run"] is None and not REFUSED(r)


# =============================================================================================== C-02
def test_c02_a_resolve_is_not_booked_while_the_venue_cannot_be_asked(tmp_path):
    """'the venue is asked once more and its own answer wins' - a lookup that RAISES is not an answer"""
    r, oid, o = stuck_sell(tmp_path)
    held = r.m.book.positions()[o["symbol"]]
    r.venue.forgotten.discard(oid)                          # the venue DOES know it again: it is WORKING ...
    real = r.venue.find_stock_order
    assert real(oid)["status"] == "working"

    def down(cid):
        raise ConnectionError("gateway reconnecting")
    r.venue.find_stock_order = down                         # ... but this pass of the resolve cannot reach it
    req = r.m.request_resolve(oid, 0, None, 0.0, "account shows nothing")
    r.tick("16:01:00", day=D2)
    rec = r.m.state["run"]["orders"][oid]
    assert rec["state"] != "booked" and r.m.book.positions()[o["symbol"]] == held
    assert [q["id"] for q in r.m.state["requests"]] == [req["id"]]          # still queued, not consumed
    said = [a for a in r.red() if "is NOT booked: the venue could not be asked" in a]
    assert len(said) == 1 and "gateway reconnecting" in said[0] and not REFUSED(r)
    r.tick("16:01:05", day=D2)
    assert len([a for a in r.red() if "is NOT booked" in a]) == 1           # said once, asked again every pass
    r.venue.find_stock_order = real                         # the twin: the venue answers - and its answer wins
    r.tick("16:01:10", day=D2)
    assert r.m.state["requests"] == [] and r.m.book.positions()[o["symbol"]] == held
    assert [a for a in REFUSED(r) if "still holds order" in a and "WORKING" in a]


# =============================================================================================== D-04 / D-05 / D-03
def _settings(tmp, **over):
    base = dict(mirror_weights="HG:0.29,KMLM:0.29,SLEEVE:0.27,HARV:0.15", mirror_capital_usd=10000.0,
                mirror_live_engines="HG,KMLM,SLEEVE,HARV", mirror_dividend_rule="composer",
                tws_userid="u", tws_password="p", dry_run=False, mirror_brain_url="https://b", mirror_api_token="t",
                mirror_state_path=str(tmp / "mirror.json"), mirror_dry_state_path=str(tmp / "mirror_dry.json"),
                mirror_decide_offset_s=25.0, mirror_cancel_before_close_s=60.0, mirror_quote_band=0.015,
                blend_enabled=False, poll_seconds=300)
    base.update(over)
    return types.SimpleNamespace(**base)


class World:
    """the books as the SERVICE builds them (mm.build from settings) over one account"""

    def __init__(self, tmp, cash=118000.0):
        self.tmp = tmp
        self.clock = tm.Clock(at("15:00"))
        self.brain = tm.Brain(self.clock)
        self.venue = tm.Venue(cash)
        self.alerts = []

    def build(self, **over):
        self.books = mm.build(_settings(self.tmp, **over), alert=self.alerts.append, brain=self.brain)
        for b in self.books.values():
            b.clock, b._sleep = self.clock, self.clock.sleep
        return self.books

    def tick(self, hms, day=DAY):
        self.clock.now = at(hms, day)
        for n in ("live", "dry"):
            if n in self.books:
                self.books[n].tick(self.venue)

    def red(self):
        return [a for a in self.alerts if a.startswith("🚨")]

    def session(self, day):
        self.brain.make = lambda now: payload(now, session=day)
        self.tick("15:55:05", day=day)
        self.tick("15:56:00", day=day)


def _funded(tmp_path, **over):
    w = World(tmp_path)
    live = w.build(**over)["live"]
    w.session(DAY)
    assert live.state["last_run"]["outcome"] == "traded" and live.state["funded_usd"] == 10000.0
    return w, live


def test_d04_a_credit_typo_cannot_scale_the_real_book(tmp_path):
    """the reviewer's repro: 'scale HG up by 1,000.00' typed with two zeros too many; the account has
    $108k of spare cash, which used to be the only bound"""
    w, live = _funded(tmp_path)
    cash0 = live.book.cash()
    live.request_credit("HG", 100000.0, "scale HG up by 1,000.00")
    w.session(D2)
    assert 118000.0 - w.venue.cash <= 10000.0 and live.book.cash() == pytest.approx(cash0, abs=50.0)
    said = [a for a in w.red() if "credit of $100000.0 to HG refused" in a]
    assert len(said) == 1 and "cap of $10,000.00" in said[0] and "MIRROR_MAX_BOOK_USD" in said[0] and "force" in said[0]
    assert live.state["funded_usd"] == 10000.0 and any("REFUSED" in n for n in live.state["last_run"]["notes"])


def test_d04_a_credit_within_the_cap_or_forced_is_taken_and_always_said(tmp_path):
    # the twin 1: MIRROR_MAX_BOOK_USD raised first - the credit is inside the cap
    w, live = _funded(tmp_path / "raised", mirror_max_book_usd=11000.0)
    assert live.cfg.max_book_usd == 11000.0
    live.request_credit("HG", 1000.0, "scale HG up")
    w.session(D2)
    assert live.state["funded_usd"] == 11000.0 and not [a for a in w.red() if "refused" in a]
    said = [a for a in w.alerts if a.startswith("⚠️") and "sleeve HG CREDITED $1,000.00" in a]
    assert len(said) == 1 and "total $11,000.00 of a cap of $11,000.00" in said[0]
    live.request_credit("HG", 2.0, "one more")              # ... and the next one is over it (beyond the $1 tolerance)
    w.session("2026-11-12")
    assert live.state["funded_usd"] == 11000.0 and [a for a in w.red() if "credit of $2.0 to HG refused" in a]
    # the twin 2: no cap raised, "force": true - taken, said, and marked
    w, live = _funded(tmp_path / "forced")
    w.venue.cash += 61.20
    live.request_credit("HARV", 61.20, "a dividend the brain did not list", force=True)
    live.request_credit("HG", -12.34, "a fee")
    w.venue.cash -= 12.34
    w.session(D2)
    assert live.state["funded_usd"] == 10061.20 and not [a for a in w.red() if "refused" in a]
    assert [a for a in w.alerts if a.startswith("⚠️") and "sleeve HARV CREDITED $61.20" in a and "[FORCED]" in a]
    assert [a for a in w.alerts if a.startswith("⚠️") and "sleeve HG DEBITED $12.34" in a]      # every live credit is said
    # the twin 3: force lifts the CAP only - the account's own cash still bounds a credit
    w, live = _funded(tmp_path / "nocash")
    live.request_credit("HG", 200000.0, "more than the account has", force=True)
    w.session(D2)
    assert live.state["funded_usd"] == 10000.0 and [a for a in w.red() if "does not cover the book's plus the credit" in a]


def test_d04_force_is_strict_and_a_paper_book_has_no_cap(tmp_path):
    w, live = _funded(tmp_path)
    for force in ("true", 1):
        assert live.request_credit("HG", 500.0, "not a literal true", force=force)["force"] is False
    w.session(D2)
    assert live.state["funded_usd"] == 10000.0 and len([a for a in w.red() if "to HG refused" in a]) == 2
    r = Rig(tmp_path / "paper")                             # the paper book: a credit is just a number
    r.tick("15:00")
    r.tick("15:55:05")
    r.m.request_credit("HG", 50000.0, "paper")
    r.brain.make = lambda now: payload(now, session=D2)
    r.tick("15:55:05", day=D2)
    assert any("HG credited $50,000.00" in n for n in r.m.state["last_run"]["notes"]) and not r.red()


def test_d04_a_state_file_written_before_the_total_existed_still_loads(tmp_path):
    w, live = _funded(tmp_path)
    path = live.cfg.state_path
    raw = json.load(open(path))
    assert raw.pop("funded_usd") == 10000.0 and raw["schema"] == mm.STATE_SCHEMA
    json.dump(raw, open(path, "w"))
    before = json.dumps(raw["book"], sort_keys=True)
    live = w.build()["live"]
    assert live.archived_state is None and not live.halt_state().get("halted")
    assert json.dumps(live.book.to_dict(), sort_keys=True) == before
    assert live.state["funded_usd"] == 10000.0              # defaulted from the seeds the file records
    live.request_credit("HG", 100000.0, "typo")
    w.session(D2)
    assert [a for a in w.red() if "to HG refused" in a and "cap of $10,000.00" in a]
    assert json.load(open(path))["funded_usd"] == 10000.0


def test_d04_a_refused_plan_takes_its_credit_total_back(tmp_path):
    """the total moves with the credit: a plan that is rolled back (here: halted before it is saved)
    leaves it where the disk has it"""
    r = invested(tmp_path, max_book_usd=200_000.0)
    r.venue.cash += 50.0
    r.m.request_credit("HARV", 50.0, "interest")
    r.m.request_transfer("HG", "HARV", 2000.0, "op")       # (a plan with something to cross-check at the venue)
    r.tick("15:56:00")                                      # both drained into the state, on disk
    r.brain.make = lambda now: payload(now, session=D2)
    real, n = r.venue.spot_ex, {"k": 0}

    def spot(symbol):
        n["k"] += 1
        if n["k"] == 2:
            r.m.halt("operator halt")
        return real(symbol)
    r.venue.spot_ex = spot
    r.tick("15:55:05", day=D2)
    assert r.m.state["run"] is None and r.m.state["funded_usd"] == 100_000.0
    assert not any("CREDITED" in a for a in r.alerts)
    r.venue.spot_ex = real
    r.m.resume()
    r.tick("15:55:20", day=D2)
    assert r.m.state["funded_usd"] == 100_050.0 and len([a for a in r.alerts if "sleeve HARV CREDITED $50.00" in a]) == 1


def test_d05_staged_seeding_never_totals_more_than_the_capital(tmp_path):
    """the reviewer's repro: HARV live first, the weights edited, then the rest. Each seed is capital x
    the weight OF THAT DAY; the sum used to be checked against the account's cash only."""
    w = World(tmp_path)
    live = w.build(mirror_live_engines="HARV")["live"]
    w.tick("15:00")
    assert live.state["seeded"]["HARV"]["amount"] == 1500.0
    live = w.build(mirror_weights="HG:0.343,KMLM:0.268,SLEEVE:0.265,HARV:0.124",
                   mirror_live_engines="HG,KMLM,SLEEVE,HARV")["live"]
    w.tick("15:01:00")
    total = sum(v["amount"] for v in live.state["seeded"].values())
    assert total <= 10000.0 + 1.0, f"seeded {live.state['seeded']} = ${total:,.2f} with MIRROR_CAPITAL_USD=10000"
    assert sorted(live.book.sleeves) == ["HARV", "HG", "KMLM"] and live.state["funded_usd"] == total == 7610.0
    said = [a for a in w.red() if "cannot seed SLEEVE with $2,650.00" in a]
    assert len(said) == 1 and "MIRROR_CAPITAL_USD is $10,000.00" in said[0] and "$7,610.00" in said[0]
    w.tick("15:02:00")
    assert len([a for a in w.red() if "cannot seed SLEEVE" in a]) == 1      # said once, not every tick


def test_d05_the_twin_a_staged_rollout_on_unchanged_weights_seeds_every_sleeve(tmp_path):
    w = World(tmp_path)
    live = w.build(mirror_live_engines="HARV")["live"]
    w.tick("15:00")
    live = w.build()["live"]
    w.tick("15:01:00")
    assert {n: s.cash for n, s in live.book.sleeves.items()} == {"HARV": 1500.0, "HG": 2900.0, "KMLM": 2900.0, "SLEEVE": 2700.0}
    assert live.state["funded_usd"] == 10000.0 and not w.red()


def test_d03_a_live_state_file_with_shares_and_no_live_book_is_said_in_red(tmp_path):
    """the reviewer's repro: MIRROR_LIVE_ENGINES emptied (or DRY_RUN / no credentials) while the live
    book holds real shares: build() makes NO live book, and /kill has no book to flatten"""
    w, live = _funded(tmp_path)
    held = live.book.positions()
    assert held and w.venue.positions_snapshot()["stocks"] == held
    for over, why in ((dict(mirror_live_engines=""), "MIRROR_LIVE_ENGINES names no engine"),
                      (dict(dry_run=True), "DRY_RUN"), (dict(tws_userid=""), "no TWS credentials")):
        w.alerts.clear()
        books = w.build(**over)
        assert "live" not in books
        said = [a for a in w.red() if "NO LIVE BOOK is built" in a]
        assert len(said) == 1 and why in said[0] and "/kill will NOT sell" in said[0], (over, w.alerts)
        assert all(f"'{s}': {q}" in said[0] for s, q in held.items())       # the holdings, by name
    # the twins: the live book is built / the live file holds no share / there is no live file
    w.alerts.clear()
    assert "live" in w.build() and not [a for a in w.alerts if "NO LIVE BOOK" in a]
    e = World(tmp_path / "empty")
    e.build()
    e.tick("15:00")                                         # seeded, nothing bought
    e.alerts.clear()
    assert "live" not in e.build(mirror_live_engines="") and not [a for a in e.alerts if "NO LIVE BOOK" in a]
    n = World(tmp_path / "none")
    assert "live" not in n.build(dry_run=True) and not [a for a in n.alerts if "NO LIVE BOOK" in a]


def test_d03_a_live_state_file_that_cannot_be_read_is_said_too(tmp_path):
    w = World(tmp_path)
    open(tmp_path / "mirror.json", "w").write("{not json")
    w.build(mirror_live_engines="")
    assert [a for a in w.red() if "NO LIVE BOOK is built" in a and "cannot be read" in a]


def test_d03_the_service_says_it_at_boot(tmp_path, monkeypatch):
    """the hook: the service builds the books with its own Telegram sender"""
    from test_mirror_service import _boot, _ready
    r = live_rig(tmp_path)                                  # the live book's file: tmp_path/mirror.json
    r.tick("15:55:05")
    held = r.m.book.positions()
    assert held and json.load(open(tmp_path / "mirror.json"))["live"] is True
    client, service, sent = _boot(tmp_path, monkeypatch)    # no TWS credentials: every engine on paper
    with client:
        _ready(service)
        assert sorted(service.MIRROR) == ["dry"]
        said = [m for m in sent if "NO LIVE BOOK is built" in m]
        assert len(said) == 1 and all(s in said[0] for s in held)


# =============================================================================================== C-52
def _strip(res):
    return {k: v for k, v in res.items() if k not in ("fill_price", "avg_price")} if isinstance(res, dict) else res


def _unpriced_sells(r, slip):
    """day two rotates every sleeve; the sells fill `slip` under their reference and the venue reports
    no price for them (they are booked at the reference, in red)"""
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    for s in ("BIL", "SOXL", "TECL", "PULS", "BOXX"):
        r.venue.fill_px[s] = round(PX[s] * (1 - slip), 4)
    place, find, fills = r.venue.place_stock_order, r.venue.find_stock_order, r.venue.stock_order_fills
    r.venue.place_stock_order = lambda *a, **k: _strip(place(*a, **k))
    r.venue.find_stock_order = lambda cid: _strip(find(cid)) if "-S-" in cid else find(cid)
    r.venue.stock_order_fills = lambda cid: _strip(fills(cid)) if "-S-" in cid else fills(cid)


@pytest.mark.parametrize("slip", [0.004, 0.008])
def test_c52_no_buys_when_the_books_cash_exceeds_the_accounts(tmp_path, slip):
    r = invested(tmp_path)
    _unpriced_sells(r, slip)
    r.venue.fill_px.update(SPY=603.0, TQQQ=80.4)            # the buys would fill AT their limits
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    r.tick("15:56:00", day=D2)
    assert r.m.state["run"] and r.m.state["run"]["buys_blocked"]   # round 3b: HELD and re-read, not given up at once
    r.tick("15:59:05", day=D2)                              # ... until the cancel instant: then the final state
    row = r.m.state["last_run"]
    sent = r.orders()[n:]
    assert sent and all(q < 0 for _, q in sent), sent       # the sells went; not one buy
    assert r.venue.cash >= 0 and all(q >= 0 for q in r.venue._positions.values())
    gap = r.m.book.cash() - r.venue.cash
    assert gap > 1.0
    said = [a for a in r.red() if "NO BUYS are sent this session" in a]
    assert len(said) == 1 and f"${r.m.book.cash():,.2f}" in said[0] and f"${r.venue.cash:,.2f}" in said[0], said
    assert any(x.startswith("buys NOT sent: the book's cash") for x in row["notes"])
    assert r.m.book.positions() == {} and not [o for o in row["orders"] if o["side"] == "BUY"]


def test_c52_no_buys_when_the_accounts_cash_cannot_be_read(tmp_path):
    r = invested(tmp_path)
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    n = len(r.orders())
    real = r.venue.account_cash
    r.venue.account_cash = lambda: None if len(r.orders()) > n else real()       # no claim once the sells are out
    r.tick("15:55:05", day=D2)
    r.tick("15:56:00", day=D2)
    r.tick("15:59:05", day=D2)                              # round 3b: re-read until the cancel instant
    sent = r.orders()[n:]
    assert sent and all(q < 0 for _, q in sent), sent
    assert len([a for a in r.red() if "NO BUYS are sent this session" in a and "cannot be read" in a]) == 1

    def boom():
        raise RuntimeError("account values timed out")
    o = invested(tmp_path / "raises")                       # ... and an adapter that raises is the same thing
    o.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    m, real_o = len(o.orders()), o.venue.account_cash
    o.venue.account_cash = lambda: boom() if len(o.orders()) > m else real_o()
    o.tick("15:55:05", day=D2)
    o.tick("15:56:00", day=D2)
    o.tick("15:59:05", day=D2)
    assert all(q < 0 for _, q in o.orders()[m:]) and [a for a in o.red() if "NO BUYS are sent this session" in a]


def test_c52_the_twins_a_priced_rotation_buys_and_a_paper_book_is_unaffected(tmp_path):
    r = invested(tmp_path / "live")
    r.venue.commission = 1.0
    r.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    n = len(r.orders())
    r.tick("15:55:05", day=D2)
    r.tick("15:56:00", day=D2)
    assert [s for s, q in r.orders()[n:] if q > 0] and not [a for a in r.alerts if "NO BUYS" in a]
    assert set(r.m.book.positions()) == {"SPY", "TQQQ"}
    sound(r)
    p = Rig(tmp_path / "paper")
    p.tick("15:00")
    p.tick("15:55:05")
    asked = []
    p.m._dry.account_cash = lambda: asked.append(1)         # a paper book never reads an account
    p.brain.make = lambda now: payload(now, ROTATE, session=D2, rules={})
    n = len(p.orders())
    p.tick("15:55:05", day=D2)
    assert [s for s, q in p.orders()[n:] if q > 0] and set(p.m.book.positions()) == {"SPY", "TQQQ"}
    assert asked == [] and not [a for a in p.alerts if "NO BUYS" in a]


# =============================================================================================== C-10
def test_c10_time_spent_waiting_on_a_working_order_does_not_use_up_the_budget(tmp_path):
    """the reviewer's repro: the 30 minutes bound REFUSALS. A flatten order that simply rests (a
    trading halt, a LULD pause) used them up too, and when it then died unfilled the flatten gave up
    without one further attempt."""
    r = invested(tmp_path)
    tecl = r.m.book.positions()["TECL"]
    r.venue.hold.add("TECL")                                # TECL is halted: the MKT sell rests
    r.m.halt("KILL", flatten=True)
    r.clock.now = at("14:00:00", D2)
    while r.clock.now < at("14:45:00", D2):                 # 45 minutes: the others sold at once, TECL rests
        r.m.tick(r.venue)
        r.clock.now += timedelta(seconds=30)
    assert r.m.book.positions() == {"TECL": tecl} and not r.m.halt_state().get("flatten_done")
    assert r.m.state["flatten"]["open_s"] == 0.0            # nothing counted while it worked
    rec = next(o for o in r.venue._orders.values() if o["symbol"] == "TECL" and o["qty"] < 0 and o["status"] == "working")
    rec["status"] = "cancelled"                             # the venue cancels it unfilled (halt -> cancel)
    r.venue.hold.clear()                                    # ... and TECL trades again
    n = len(r.venue.placed)
    for _ in range(6):
        r.m.tick(r.venue)
        r.clock.now += timedelta(seconds=30)
    assert [(s, q) for s, q, _ in r.venue.placed[n:]] == [("TECL", -tecl)]
    assert r.m.book.positions() == {} and r.m.halt_state()["flatten_done"] is True
    assert not [a for a in r.red() if "GAVE UP" in a]
    sound(r)
    # (the twin - refusals still end the flatten after 30 open minutes - is
    #  test_mirror_review.py::test_a21_the_flatten_gives_up_loudly_after_thirty_minutes_of_open_session)


# =============================================================================================== seeding / deploy file
def test_seeding_a_live_sleeve_is_a_warning_naming_the_sleeve_and_the_dollars(tmp_path):
    r = live_rig(tmp_path / "live")
    for name, w in tm.W.items():
        said = [a for a in r.alerts if f"sleeve {name} seeded with ${100_000.0 * w:,.2f}" in a]
        assert len(said) == 1 and said[0].startswith("⚠️ mirror[live]"), (name, r.alerts)
    assert r.m.state["funded_usd"] == 100_000.0
    p = Rig(tmp_path / "paper")                             # the twin: a paper seed stays an info line
    p.tick("15:00")
    said = [a for a in p.alerts if "seeded with" in a]
    assert len(said) == 4 and all(a.startswith("🪞") for a in said)


def test_the_deploy_file_declares_the_weights_and_the_book_cap():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(os.path.dirname(here), "render.yaml")).read()
    start = text.index("name: ibkr-executor")
    nxt = text.find("\n  - type:", start)
    block = text[start:] if nxt == -1 else text[start:nxt]
    for key in ("MIRROR_WEIGHTS", "MIRROR_MAX_BOOK_USD"):
        assert f"key: {key}\n        sync: false" in block, key
    fields = app_settings.__class__.model_fields
    assert fields["mirror_max_book_usd"].default == 0.0     # 0: MIRROR_CAPITAL_USD is the cap
    assert mm.parse_weights(fields["mirror_weights"].default) == tm.W


def test_the_services_resolve_route_passes_force_only_as_a_literal_true(tmp_path, monkeypatch):
    from test_mirror_service import T, _boot, _ready
    client, service, sent = _boot(tmp_path, monkeypatch)
    with client as c:
        _ready(service)
        body = {"id": "mirror-x-B-PULS", "filled": 10, "price": 49.6, "commission": 4960.0}
        for force, want in ((None, False), ("true", False), (1, False), (True, True)):
            got = c.post("/mirror/resolve", params=T, json=body if force is None else dict(body, force=force)).json()
            assert got["ok"] and got["request"]["force"] is want, (force, got)
