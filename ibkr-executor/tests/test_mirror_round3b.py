"""Merge-blocking gates for round 3b of the Composer mirror: what the two INDEPENDENT verifiers of the
round-3 commit found (V3a: the flatten / order path; V3b: the capital caps and operator tools). One
finding, one gate (with its twin where a twin exists); each fails on the round-3 code. The doubles are
tests/test_mirror.py's (Venue), tests/ibrig.py's (the REAL IBAdapter over FakeIB) and round 3's World.

  G1   the flatten cap counts SELL orders already open at the venue: a second flatten id over a sell
       that still rests (a halted symbol) never takes the position short; open orders unreadable -> no sell
  G2   a "new" flatten order is looked up at the venue BEFORE it is booked "not sent" (restart on a
       stale file, then /resume): the sell that rests there is cancelled, not forgotten
  G3   kill latency: a flatten THIS process armed is not looked up twice (one ~20 s wait per symbol,
       not two); a flatten armed by an earlier process still is (D-01)
  G4   flatten orders that just keep working are said in red after 10 minutes, and every 10 minutes
  G5   an account that reads EMPTY against a book with shares is read again before the flatten ends,
       and a flatten that sold nothing never reports account_flat True
  G6   C-52 is not one look: the buys are held while the account's cash lags and go when it covers
  G7   /mirror/adjust: cash added to a live book is capped like a credit (F1)
  G8   staged rollout: credits are capped at the capital of THIS book's engines, and a seed counts
       what the book has already taken (F2)
  G9   MIRROR_MAX_BOOK_USD below the capital bounds the seeds (F3)
  G10  a dividend above 10% of the position's value is not credited (F4)
  G11  a blank MIRROR_MAX_BOOK_USD / MIRROR_CAPITAL_USD is the default, not a crash at import (F5)
  G12  a huge integer is "not a number", not an OverflowError (F7)
"""
from __future__ import annotations

import pytest

import app.ib_adapter as ib_mod
import test_mirror as tm
from app import mirror as mm
from ibrig import IBRig, VenueIB
from test_mirror import DAY, PX, T1, Rig, at, payload, timedelta
from test_mirror_review import D2, D3, invested
from test_mirror_round3 import World, _disk, _funded

ODD = "HG:0.343,KMLM:0.268,SLEEVE:0.265,HARV:0.124"      # the weights of the real day one
CAP = 10000.0


def _ib_invested(tmp_path, mp):
    r = IBRig(tmp_path, mp)
    r.tick("15:00"); r.tick("15:55:05"); r.tick("15:56:00")
    assert r.m.state["run"] is None and r.venue_pos() == r.m.book.positions() and len(r.venue_pos()) == 5
    return r


def _step(r, n=1, s=6):
    for _ in range(n):
        r.clock.now += timedelta(seconds=s)
        r.m.tick(r.ad)


def _book_value(m):
    return m.book.cash() + sum(q * PX[s] for s, q in m.book.positions().items())


# =============================================================================================== G1
@pytest.mark.parametrize("rekill", ["resume-then-kill", "halt-file-lost"])
def test_g1_a_second_flatten_over_a_sell_that_still_rests_never_goes_short(tmp_path, monkeypatch, rekill):
    """V3a's repro: TECL is halted when /kill lands, so its sell RESTS at the venue; the disk fails and
    the process restarts on the stale file; the operator kills again (a NEW flatten id). When TECL
    reopens every resting order fills: the cap must have counted the sell already there."""
    r = _ib_invested(tmp_path, monkeypatch)
    held = r.venue_pos()["TECL"]
    r.ib.hold.add("TECL")
    box = _disk(monkeypatch, r.m.cfg.state_path)
    if rekill == "halt-file-lost":
        box["fail_from"] = box["n"] + 1                      # the disk is full when /kill lands
        assert r.m.halt("KILL", flatten=True)["persisted"] is False
    else:
        r.m.halt("KILL", flatten=True)
        box["fail_from"] = box["n"] + 1
    r.tick("15:57:00")
    _step(r, 2)
    assert r.ad.open_sell_qty("TECL") == held
    box["fail_from"], box["down"] = None, False
    r.boot(completed_available=False)
    r.ib.hold.add("TECL")
    if rekill == "resume-then-kill":
        r.m.resume()
        _step(r, 2)
    r.clock.now += timedelta(seconds=2)
    r.m.halt("KILL again", flatten=True)
    _step(r, 4)
    resting = [t for t in r.acct.orders if t.contract.symbol == "TECL" and t.orderStatus.status == "Submitted"]
    assert sum(t.order.totalQuantity for t in resting) <= held, [(t.order.orderRef, t.order.totalQuantity) for t in resting]
    for t in resting:                                        # TECL reopens
        r.ib.execute(t, t.order.totalQuantity - t.orderStatus.filled)
    _step(r, 4)
    assert not {s: q for s, q in r.acct.pos.items() if q < 0}, r.acct.pos


def test_g1_the_adapter_counts_the_unfilled_remainder_of_open_sells_only(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    held = r.venue_pos()["TECL"]
    assert r.ad.open_sell_qty("TECL") == 0                   # filled buys, no sell
    r.ib.hold.add("TECL")
    r.m.halt("KILL", flatten=True)
    r.tick("15:57:00")
    t = next(x for x in r.acct.orders if x.contract.symbol == "TECL" and x.order.action == "SELL")
    assert r.ad.open_sell_qty("TECL") == held and r.ad.open_sell_qty("BIL") == 0
    assert r.ad.open_sell_qty("TECL", exclude=t.order.orderRef) == 0
    r.ib.execute(t, 3)
    assert r.ad.open_sell_qty("TECL") == held - 3
    r.boot(completed_available=False)                        # a new session learns of it from the venue's open orders
    assert r.ad.open_sell_qty("TECL") == held - 3
    monkeypatch.setattr(VenueIB, "reqAllOpenOrders", lambda self: (_ for _ in ()).throw(TimeoutError("no openOrderEnd")))
    with pytest.raises(TimeoutError):
        r.ad.open_sell_qty("TECL")


def test_g1_no_flatten_sell_while_the_open_orders_cannot_be_read_and_the_cut_twin(tmp_path):
    r = invested(tmp_path)
    bil = r.m.book.positions()["BIL"]
    real = r.venue.open_sell_qty
    r.venue.open_sell_qty = lambda sym, exclude=None: (_ for _ in ()).throw(RuntimeError("open orders timed out"))
    n = len(r.venue.placed)
    r.m.halt("KILL", flatten=True)
    r.tick("15:56:00")
    assert r.venue.placed[n:] == [] and r.m.book.positions()["BIL"] == bil
    assert [a for a in r.red() if "open orders cannot be read" in a]
    # the twin: 40 BIL are already being sold by an order placed by hand -> the flatten sells the rest only
    r.venue.open_sell_qty = lambda sym, exclude=None: 40 if sym == "BIL" else real(sym, exclude)
    r.tick("15:56:06")
    sent = {s: q for s, q, _ in r.venue.placed[n:]}
    assert sent["BIL"] == -(bil - 40) and r.venue.stock_position("BIL") == 40
    assert [a for a in r.red() if "cut from" in a and "already open at the venue" in a]


# =============================================================================================== G2
def test_g2_a_new_flatten_order_is_looked_up_before_it_is_booked_not_sent(tmp_path, monkeypatch):
    r = invested(tmp_path)
    r.venue.hold.add("TECL")
    real = mm.atomic_write
    box = {"n": 0, "fail_from": None, "down": False}

    def write(path, obj):
        if path == r.m.cfg.state_path:                       # the state file only: the halt file is written
            box["n"] += 1
            if box["fail_from"] is not None and box["n"] >= box["fail_from"]:
                box["down"] = True
            if box["down"]:
                raise OSError(28, "No space left on device")
        return real(path, obj)
    monkeypatch.setattr(mm, "atomic_write", write)
    r.m.halt("kill", flatten=True)
    box["fail_from"] = box["n"] + 2                          # the round is on disk; every write-ahead after it is not
    r.tick("15:56:00")
    assert any(c.endswith("TECL") and "flat" in c for _, _, c in r.venue.placed)
    box["fail_from"], box["down"] = None, False
    r.boot()
    r.m.resume()
    r.tick("15:56:10")
    fl = r.m.state["flatten"]
    how = {o["symbol"]: fl["recs"][o["id"]].get("how") for o in fl["orders"]}
    working = [x for x in r.venue._orders.values() if x["symbol"] == "TECL" and x["status"] == "working"]
    assert not working, f"booked {how.get('TECL')!r} while the venue still WORKS a TECL sell"
    assert how["TECL"].startswith("cancelled") and r.m.book.positions().get("TECL")      # cancelled unfilled: kept
    assert [a for a in r.red() if "ALREADY at the venue" in a and "TECL" in a]


def test_g2_the_twin_absent_at_the_venue_is_booked_not_sent_and_a_lookup_that_fails_waits(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    r.m.halt("kill", flatten=True)
    r.m._flat_here.clear()                                   # as after a restart: this process did not arm it
    find, n = r.venue.find_stock_order, len(r.venue.placed)
    r.venue.find_stock_order = lambda cid: (_ for _ in ()).throw(ConnectionError("gateway down"))
    r.venue.positions_snapshot = lambda: {"stocks": dict(held), "other": []}
    r.tick("15:56:00")                                       # the round is built; nothing can be asked: nothing is sent
    assert r.venue.placed[n:] == [] and not any(o.get("applied") for o in r.m.state["flatten"]["orders"])
    r.m.resume()
    r.tick("15:56:06")                                       # stopped, and the venue still cannot be asked: it WAITS
    assert not any(o.get("applied") for o in r.m.state["flatten"]["orders"])
    r.venue.find_stock_order = find
    r.tick("15:56:12")                                       # the venue answers "no such order": booked not sent
    fl = r.m.state["flatten"]
    assert all(o["applied"] and "the venue holds no such order" in fl["recs"][o["id"]]["how"] for o in fl["orders"])
    assert r.venue.placed[n:] == [] and r.m.book.positions() == held


# =============================================================================================== G3
def _slow_gateway(r, monkeypatch):
    """the gateway that never answers reqCompletedOrders: each call burns VENUE_HISTORY_TIMEOUT_S"""
    log, calls, t0 = [], {"completed": 0}, {}
    real_place = VenueIB.placeOrder

    def completed(self, apiOnly=True):
        calls["completed"] += 1
        r.clock.now += timedelta(seconds=ib_mod.VENUE_HISTORY_TIMEOUT_S)
        raise TimeoutError("no completedOrdersEnd")

    def place(self, contract, order):
        t = real_place(self, contract, order)
        log.append((contract.symbol, (r.clock.now - t0["at"]).total_seconds()))
        return t
    monkeypatch.setattr(VenueIB, "reqCompletedOrders", completed)
    monkeypatch.setattr(VenueIB, "placeOrder", place)
    return log, calls, t0


def test_g3_a_kill_waits_one_history_timeout_per_symbol_not_two(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    r.boot(completed_available=False)                        # a fresh session (the service restarted since the buys)
    log, calls, t0 = _slow_gateway(r, monkeypatch)
    r.clock.now = at("10:00:00", D2)
    t0["at"] = r.clock.now
    r.m.halt("KILL", flatten=True)
    for _ in range(40):
        r.m.tick(r.ad)
        if r.m.halt_state().get("flatten_done"):
            break
        r.clock.now += timedelta(seconds=5)
    T = ib_mod.VENUE_HISTORY_TIMEOUT_S
    assert [s for s, _ in log] == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]
    assert [t for _, t in log] == [T, 2 * T, 3 * T, 4 * T, 5 * T], log      # 20/40/60/80/100 s, as before round 3
    assert calls["completed"] == 5 and r.venue_pos() == {} and r.m.halt_state()["account_flat"] is True


def test_g3_the_twin_a_flatten_armed_by_an_earlier_process_is_still_looked_up(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    r.m.halt("KILL", flatten=True)
    r.boot(completed_available=False)                        # the halt file carries the flatten; THIS process did not arm it
    asked, find = [], r.ad.find_stock_order
    monkeypatch.setattr(r.ad, "find_stock_order", lambda cid: (asked.append(cid), find(cid))[1])
    r.tick("15:57:00")
    assert sorted(asked) == sorted(o["id"] for o in r.m.state["flatten"]["orders"]) and len(asked) == 5
    assert r.venue_pos() == {}


# =============================================================================================== G4
def test_g4_flatten_orders_that_keep_working_are_said_every_ten_minutes(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    qty = r.venue_pos()["TECL"]
    r.ib.hold.add("TECL")
    r.m.halt("KILL", flatten=True)
    r.clock.now = at("10:00:00", D2)
    r.m.tick(r.ad)
    n0 = len(r.alerts)
    _step(r, 12 * 9, 5)                                      # nine minutes: nothing yet
    assert not [a for a in r.alerts[n0:] if "STILL NOT BOOKED" in a]
    _step(r, 12 * 51 + 1, 5)                                 # ... one hour in all
    said = [a for a in r.alerts[n0:] if "STILL NOT BOOKED" in a]
    assert len(said) == 6 and all(a.startswith("🚨") and f"SELL {qty} TECL" in a for a in said), said
    assert "BIL" not in said[0]                              # only what is still unbooked is named
    t = next(x for x in r.acct.orders if x.contract.symbol == "TECL" and x.orderStatus.status == "Submitted")
    r.ib.execute(t, qty)                                     # the twin: it fills -> nothing more is said
    _step(r, 12 * 30, 5)
    assert len([a for a in r.alerts[n0:] if "STILL NOT BOOKED" in a]) == 6 and r.venue_pos() == {}


# =============================================================================================== G5
def _positions_empty(r, monkeypatch, looks):
    real = type(r.ib).positions
    left = {"n": looks}

    def positions(self):
        if left["n"] > 0:
            left["n"] -= 1
            return []
        return real(self)
    monkeypatch.setattr(type(r.ib), "positions", positions)


def test_g5_an_account_that_reads_empty_after_a_reconnect_is_read_again_and_then_sold(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    _positions_empty(r, monkeypatch, 3)
    r.m.halt("KILL", flatten=True)
    r.tick("15:57:00")
    assert r.m.halt_state()["flatten_done"] is False and [a for a in r.red() if "reads as holding NONE" in a]
    _step(r, 10, 6)
    h = r.m.halt_state()
    assert r.venue_pos() == {} and r.m.book.positions() == {} and h["flatten_done"] is True and h["account_flat"] is True


def test_g5_a_flatten_that_sold_nothing_never_reports_the_account_flat(tmp_path, monkeypatch):
    r = _ib_invested(tmp_path, monkeypatch)
    held = dict(r.m.book.positions())
    _positions_empty(r, monkeypatch, 10 ** 6)                # the account never reads as holding anything
    r.m.halt("KILL", flatten=True)
    r.tick("15:57:00")
    _step(r, 10, 6)
    h = r.m.halt_state()
    assert h["flatten_done"] is True and h["account_flat"] is None and r.m.book.positions() == held
    assert not [p for p in r.ib.placed if p[1] == "SELL"]
    assert [a for a in r.red() if "flatten NOT complete" in a and "STILL HELD" in a and "reads empty" in a]


# =============================================================================================== G6
def _rotation(tmp_path, stale_reads):
    """day two: HG rotates BIL -> TQQQ. After the sell fills the account's cash is reported as it stood
    BEFORE the fill for the first `stale_reads` reads (None: for ever)."""
    r = Rig(tmp_path, live=True, venue_cash=100_000.0)
    r.tick("15:00"); r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=D2)
    r.tick("15:00", day=D2)
    stale, real, seen = r.venue.account_cash(), r.venue.account_cash, {"n": 0}

    def cash():
        if r.m.state.get("run") and r.m.state["run"]["phase"] == "sells":
            seen["n"] += 1
            if stale_reads is None or seen["n"] <= stale_reads:
                return dict(stale)
        return real()
    r.venue.account_cash = cash
    return r, seen


def _bought(r):
    row = r.m.state["last_run"]
    return row["session"] == D2 and any(o["symbol"] == "TQQQ" and o.get("filled") for o in row["orders"])


def test_g6_the_buys_wait_for_the_accounts_cash_and_go_when_it_covers(tmp_path):
    r, seen = _rotation(tmp_path, stale_reads=3)
    r.tick("15:55:05", day=D2)
    assert _bought(r) and seen["n"] == 4, (seen, r.alerts)   # asked again on every step; sent on the first that covers
    assert len([a for a in r.red() if "BUYS are HELD" in a]) == 1 and not [a for a in r.red() if "NO BUYS" in a]
    assert len([a for a in r.alerts if "covers the book's again" in a]) == 1
    assert any("buys were held for" in n for n in r.m.state["last_run"]["notes"])
    tm.sound(r)


def test_g6_the_twins_never_covered_means_no_buys_and_the_normal_path_is_one_read(tmp_path):
    r, seen = _rotation(tmp_path / "never", stale_reads=None)
    r.tick("15:55:05", day=D2)
    assert r.m.state["run"] and r.m.state["run"]["buys_blocked"] and r.m.state["run"]["phase"] == "sells"
    assert r.clock.now < at("15:59:00", D2) and seen["n"] > 50          # read on every step of the tick's budget
    r.boot()                                                 # a restart in between keeps waiting (the run is on disk)
    assert r.m.state["run"]["buys_blocked"] and r.m.state["run"]["phase"] == "sells"
    r.tick("15:58:00", day=D2)                               # ... to the cancel instant: the final state, as before
    assert r.clock.now == at("15:59:00", D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and not _bought(r) and any(n.startswith("buys NOT sent: the book's cash") for n in row["notes"])
    assert len([a for a in r.red() if "NO BUYS are sent this session" in a]) == 1
    n, seen = _rotation(tmp_path / "normal", stale_reads=0)  # the account's cash is right at the first read
    t0 = n.clock.now = at("15:55:05", D2)
    n.m.tick(n.venue)
    assert _bought(n) and seen["n"] == 1 and n.clock.now == t0 and not [a for a in n.alerts if "HELD" in a]


# =============================================================================================== G7
def test_g7_cash_added_by_an_adjustment_is_capped_like_a_credit(tmp_path):
    w, live = _funded(tmp_path)
    v0 = _book_value(live)
    live.request_adjust("HG", None, 0, 50000.0, "fix 50.00 interest")       # the slipped decimal
    w.session(D2)
    assert _book_value(live) == pytest.approx(v0, abs=60) and live.state["funded_usd"] == CAP
    assert len([a for a in w.red() if "adjust request" in a and "REFUSED" in a and "cap of $10,000.00" in a]) == 1
    for truthy in (1, "true"):                               # force is the literal true only
        live.request_adjust("HG", None, 0, 500.0, "x", force=truthy)
    w.tick("16:10:00", day=D2)
    assert live.state["funded_usd"] == CAP and len([a for a in w.red() if "adjust request" in a and "REFUSED" in a]) == 3
    live.request_adjust("HG", None, 0, 500.0, "meant", force=True)
    w.tick("16:11:00", day=D2)
    assert live.state["funded_usd"] == CAP + 500.0 and live.book.sleeves["HG"].cash >= 500.0


def test_g7_the_twins_cash_that_replaces_removed_shares_and_a_paper_book(tmp_path):
    """V4b D1: cash by hand is never netted against shares the same adjustment removes. At a book
    sitting at its cap a sale by hand is refused without force and taken with it; and adding shares
    then 'undoing' them as a sale for cash cannot turn into uncapped cash."""
    w, live = _funded(tmp_path)
    bil = live.book.sleeves["HG"].shares["BIL"]
    cash0 = live.book.sleeves["HG"].cash
    live.request_adjust("HG", "BIL", +500, 0.0, "wrong repair")
    w.tick("16:09:00")
    live.request_adjust("HG", "BIL", -500, 45750.0, "undo, typed as a sale")
    w.tick("16:09:30")
    assert live.book.sleeves["HG"].cash == pytest.approx(cash0) and live.state["funded_usd"] == CAP
    assert len([a for a in w.red() if "REFUSED" in a]) == 1
    live.request_adjust("HG", "BIL", -500, 0.0, "undo the wrong repair")
    w.tick("16:09:45")
    assert live.book.sleeves["HG"].shares["BIL"] == bil
    w.venue._positions["BIL"] -= 2                           # two BIL sold by hand at 91.00
    w.venue.cash += 2 * 91.0
    live.request_adjust("HG", "BIL", -2, 2 * 91.0, "sold by hand, statement line 4")
    w.tick("16:10:00")
    assert live.book.sleeves["HG"].shares["BIL"] == bil and len([a for a in w.red() if "REFUSED" in a]) == 2
    live.request_adjust("HG", "BIL", -2, 2 * 91.0, "sold by hand, statement line 4", force=True)
    w.tick("16:11:00")
    assert live.book.sleeves["HG"].shares["BIL"] == bil - 2 and live.state["funded_usd"] == CAP + 182.0
    assert live.book.sleeves["HG"].cash == pytest.approx(cash0 + 182.0)
    p = Rig(tmp_path / "paper")
    p.tick("15:00")
    p.m.request_adjust("HG", None, 0, 50000.0, "paper has no cap")
    p.tick("15:01:00")
    assert p.m.book.sleeves["HG"].cash == pytest.approx(29000.0 + 50000.0)


# =============================================================================================== G8
def test_g8_a_staged_books_credit_cap_is_its_own_engines_capital(tmp_path):
    """V3b's repro: HARV alone is live ($1,240); 'credit HARV 80.00' typed 8000"""
    w = World(tmp_path)
    live = w.build(mirror_weights=ODD, mirror_live_engines="HARV")["live"]
    w.session(DAY)
    assert live.state["last_run"]["outcome"] == "traded" and live.state["funded_usd"] == 1240.0
    live.request_credit("HARV", 8000.0, "PULS dividend 80.00")
    w.session(D2)
    assert live.state["funded_usd"] == 1240.0 and [a for a in w.red() if "refused" in a and "cap of $1,240.00" in a]
    live = w.build(mirror_weights=ODD)["live"]
    w.tick("15:00", day=D3)
    w.session(D3)
    assert sorted(live.book.sleeves) == ["HARV", "HG", "KMLM", "SLEEVE"]
    assert _book_value(live) <= CAP * 1.02 and live.state["funded_usd"] == pytest.approx(CAP, abs=0.01)


def test_g8_a_forced_credit_counts_against_the_later_seeds(tmp_path):
    w = World(tmp_path)
    live = w.build(mirror_weights=ODD, mirror_live_engines="HARV")["live"]
    w.session(DAY)
    live.request_credit("HARV", 8000.0, "meant", force=True)
    w.session(D2)
    assert live.state["funded_usd"] == 9240.0
    live = w.build(mirror_weights=ODD)["live"]
    w.tick("15:00", day=D3)
    assert sorted(live.book.sleeves) == ["HARV"] and live.state["funded_usd"] == 9240.0      # 9,240 + any seed > 10,000
    assert len([a for a in w.red() if "cannot seed" in a]) == 3


def test_g8_the_twins_day_one_and_a_staged_rollout_still_seed_every_sleeve(tmp_path):
    w = World(tmp_path / "day1")
    live = w.build(mirror_weights=ODD)["live"]
    w.tick("15:00")
    assert {n: s.cash for n, s in live.book.sleeves.items()} == pytest.approx(
        {"HG": 3430.0, "KMLM": 2680.0, "SLEEVE": 2650.0, "HARV": 1240.0})
    assert live.state["funded_usd"] == pytest.approx(CAP, abs=0.01) and not w.red()
    w.session(DAY)
    assert live.state["last_run"]["outcome"] == "traded" and not w.red() and 118000.0 - w.venue.cash <= CAP + 1
    s = World(tmp_path / "staged")
    for stage in ("HARV", "HARV,SLEEVE", "HARV,SLEEVE,KMLM", "HG,KMLM,SLEEVE,HARV"):
        live = s.build(mirror_weights=ODD, mirror_live_engines=stage)["live"]
        s.tick("15:00")
        assert sorted(live.book.sleeves) == sorted(stage.split(",")), (stage, s.alerts)
        assert live._book_cap_usd() == pytest.approx(sum(live.cfg.capital[e] for e in stage.split(",")))
    assert live.book.cash() == pytest.approx(CAP, abs=0.01) and not s.red()


# =============================================================================================== G9
def test_g9_a_max_book_below_the_capital_bounds_the_seeds(tmp_path):
    w = World(tmp_path)
    live = w.build(mirror_max_book_usd=5000.0)["live"]
    w.tick("15:00")
    # HG 2,900 and HARV 1,500 fit under 5,000; KMLM (2,900) and SLEEVE (2,700) would each pass it
    assert live.book.cash() == 4400.0 and sorted(live.book.sleeves) == ["HARV", "HG"] and live.state["funded_usd"] == 4400.0
    assert [a for a in w.red() if "cannot seed KMLM" in a and "MIRROR_MAX_BOOK_USD $5,000.00" in a]
    t = World(tmp_path / "twin")                             # at or above the capital it bounds no seed
    live = t.build(mirror_max_book_usd=10500.0)["live"]
    t.tick("15:00")
    assert live.book.cash() == pytest.approx(CAP) and not t.red()


# =============================================================================================== G10
@pytest.mark.parametrize("live", [True, False])
def test_g10_a_dividend_that_cannot_be_true_is_not_credited(tmp_path, live):
    """V3b's repro: the feed lists PULS $20/sh instead of $0.20 (PULS is $49.50)"""
    if live:
        w, m = _funded(tmp_path)
        alerts, tick = w.alerts, w.tick
        w.venue.cash += 5000.0                               # (the account's cash WOULD cover it)
    else:
        r = Rig(tmp_path)
        r.tick("15:00"); r.tick("15:55:05")
        m, alerts, tick = r.m, r.alerts, (lambda hms, day: r.tick(hms, day=day))
    v0 = _book_value(m)
    shares = {n: s.shares.get("PULS", 0) for n, s in m.book.sleeves.items() if s.shares.get("PULS")}
    for amount, day in ((20.0, D2), (0.2, D3)):
        div = {"ticker": "PULS", "ex_date": day, "pay_date": day, "amount": amount}
        make = lambda now, day=day, div=div: payload(now, session=day, dividends=[dict(div)])     # noqa: E731
        if live:
            w.brain.make = make
        else:
            r.brain.make = make
        tick("15:55:05", day=day)
        tick("15:56:00", day=day)
        if amount == 20.0:
            assert _book_value(m) == pytest.approx(v0, abs=60), "a $20/sh 'dividend' on a $49.50 fund was credited"
            said = [a for a in alerts if "is NOT credited" in a]
            assert len(said) == len(shares) and all(a.startswith("🚨") and "PULS" in a and "$20 per share" in a for a in said)
            assert any(f"${20.0 * q:,.2f} in total" in a for a in said for q in shares.values())
            assert {x["status"] for x in m.state["dividends"]} == {"refused"}
    # the twin: a real distribution ($0.20 on $49.50) is credited as before
    assert sorted(x["status"] for x in m.state["dividends"] if x["ex_date"] == D3) == ["credited"] * len(shares)
    assert len([a for a in alerts if "is NOT credited" in a]) == len(shares)


# =============================================================================================== G11
@pytest.mark.parametrize("key", ["MIRROR_MAX_BOOK_USD", "MIRROR_CAPITAL_USD"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_g11_a_blank_env_value_is_the_default_not_a_crash(monkeypatch, key, blank):
    from app.config import Settings
    monkeypatch.setenv(key, blank)
    s = Settings(_env_file=None)
    assert getattr(s, key.lower()) == 0.0
    monkeypatch.setenv(key, "10500")                         # the twins: a number is read; garbage is still refused
    assert getattr(Settings(_env_file=None), key.lower()) == 10500.0
    monkeypatch.setenv(key, "ten thousand")
    with pytest.raises(Exception):
        Settings(_env_file=None)


# =============================================================================================== G12
def test_g12_a_huge_integer_is_not_a_number_and_the_route_answers_400(tmp_path, monkeypatch):
    huge = 10 ** 400
    assert mm._num(huge) is None and mm._num(-huge) is None and mm._num(10 ** 30) == 1e30
    r = invested(tmp_path)
    for call in (lambda: r.m.request_resolve("x", 1, 10, huge), lambda: r.m.request_credit("HG", huge),
                 lambda: r.m.request_adjust("HG", None, 0, huge, "x"), lambda: r.m.request_transfer("HG", "HARV", huge)):
        with pytest.raises(ValueError):
            call()
    from test_mirror_service import T, _boot, _ready
    client, service, sent = _boot(tmp_path / "svc", monkeypatch)
    with client:
        _ready(service)
        body = '{"id":"x","filled":1,"price":10,"commission":1' + "0" * 400 + "}"
        out = client.post("/mirror/resolve", params=T, content=body, headers={"content-type": "application/json"})
        assert out.status_code == 400, out.text
