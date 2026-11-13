"""C-52, second pass (2026-11-13): the buys' cash guard no longer takes the book's word for its sells.

The first pass (app/mirror.py _cash_cover) let a live book buy in the step its sells were booked by
counting their executed proceeds on the cash read before them (E), while IB's TotalCashValue (F) still
read what it read before the run. An independent safety review found that E trusted the book's record
of the sells and that nothing independent confirmed it while F did not move: a sale the book records
and the account never made funded buys on margin where the rule before held them -
  S2  /mirror/resolve of an UNRESOLVED run sell stating shares that never executed: $28,288.50
      borrowed at 97% of the account (or the right shares at a price above the real one, inside the
      resolve's 20% band: S2b below)
  R5  an IB execution CORRECTION (execId ".01" -> ".02"), which ib_async stores as one more fill: the
      adapter summed both and booked a 100-share partial as 200 sold: $5,257.50 borrowed
  S1b a purchase by hand between the sells and the buys, while F lags
Now E is used only while the account's POSITIONS, read again before the buys, are exactly those of
the pre-trade read (run["pos0"]) less every share the sells were booked at; otherwise, or when they
cannot be read, the rule before (F alone). A sell booked on the operator's word is counted at nothing
until F shows it. The adapter keeps one execution per base execId, the latest correction.

GATES - each FAILS on the first pass (b7c0849d + fixes/buyguard.patch) and passes after:
  P1  S2: a resolve stating a sale that never executed: the buys are held for the session; the
      account never borrows (before: $28,288.50 borrowed)
  P2  S2b: a resolve stating the shares that DID execute (at 74.00) at their 91.50 reference - a price
      above the real one, inside the band - IB's cash lagging: held; never borrows (before: borrowed)
  P3  R5 over the REAL IBAdapter: a corrected 100-share execution is booked as 100, not 200; the buys
      are sized from what the 100 brought; never borrows (before: 200 booked, $5,257.50 borrowed)
  P4  R5 with execIds the adapter cannot pair (a double count it does not catch): the positions
      disagree, the buys fall back to F and are held; never borrows (before: borrowed)
  P5  a purchase by hand between the sells and the buys (S1b): $19.8k - held for the session, never
      borrows (before: $15,218.50 borrowed); one share - held until F shows it, then bought (before:
      bought at once on E)
  P6  the positions cannot be read before the buys: the rule before (held while F lags, bought once F
      covers) (before: bought at once on E, unchecked)
  P7  a run on disk with no pos0 (written before this): the rule before (before: E used)
  P8  the adapter: a corrected execution counts once - stock_order_fills, find_stock_order (a trade
      of the session, and the execution-report fallback) and poll_stock_fills (before: 200 shares,
      the two prices averaged, two commissions)
  P9  _sells_confirmed: agree / disagree / unreadable / not a whole stock lot / no pos0
TWINS - pass before and after:
  T1  at 97% with F lagging 300 s and the positions agreeing, the buys go in the step the sells are
      booked and the record says what confirmed them (the first pass's BG1-BG3 keep the 30-300 s lags)
  T2  a resolve stating the TRUE terms of a sale that executed is bought once F shows it
  T3  two distinct executions, and execIds not in IB's form, are summed as before
Every Venue gate ends on the ACCOUNT never below zero.
"""
from __future__ import annotations

import json
import time
import types

import pytest

import test_mirror as tm
import test_mirror_connection as tc                                   # the REAL IBAdapter's rig (P3, P4)
from app import mirror as mm
from test_ib_stock_adapter import (FakeExec, FakeFill, _exec_fill, _execute, _session,  # noqa: F401
                                   ib_adapter)
from test_mirror import PX, T1, Rig, at, payload

D2 = "2026-11-11"
ACCOUNT = 117_000.0
BOOK97 = round(0.97 * ACCOUNT, 2)                 # $3,510 of the account's cash is outside the book
ROT = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"PULS": 1.0}}
HG_ONLY = dict(T1, HG={"TQQQ": 1.0})             # HG sells its BIL (~$28.8k) and buys TQQQ
WINDOW = ("15:56:40", "15:57:40", "15:58:30", "15:59:05", "15:59:40", "16:00:30")


class Shown:
    """IB's TotalCashValue on the Venue: the account's cash as it stood at the last refresh. Frozen at
    the instant this is made until show() (IB's update cycle). low: the least the TRUE cash ever was."""

    def __init__(self, r):
        self.r, self.value, self.low = r, r.venue.cash, r.venue.cash
        real_fill = r.venue._fill

        def fill(rec, shares):
            real_fill(rec, shares)
            self.low = min(self.low, r.venue.cash)
        r.venue._fill = fill
        r.venue.account_cash = self.read

    def move(self, delta):
        self.r.venue.cash += delta
        self.low = min(self.low, self.r.venue.cash)

    def show(self):
        self.value = self.r.venue.cash

    def read(self):
        if not self.r.venue.cash_claim:
            return None
        return {"total_cash": self.value, "net_liq": None, "available_funds": self.value, "ts": time.time()}


def day_one(tmp_path, targets, book=BOOK97):
    """day one seeded and traded at T1 (the account's other cash outside the book), day two's targets
    set, its 15:00 tick done; $1 commissions reported at the fill from now on"""
    r = Rig(tmp_path, live=True, capital=book, venue_cash=ACCOUNT)
    r.tick("15:00")
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.brain.make = lambda now: payload(now, targets, session=D2)
    r.tick("15:00", day=D2)
    r.venue.commission = 1.0
    return r


def bought(r, n0):
    return [(s, q) for s, q, _ in r.venue.placed[n0:] if q > 0]


def held(r):
    return [a for a in r.red() if "BUYS are HELD" in a]


def before_first_guard(r, fn):
    """fn(run) once, right before the guard's first look (every sell booked, no buy sized)"""
    real, done = r.m._buys_unfunded, []

    def guard(ad, run):
        if not done:
            done.append(1)
            fn(run)
        return real(ad, run)
    r.m._buys_unfunded = guard


def spy_guard(r):
    """every run["buy_cash"] the guard records, in order"""
    real, seen = r.m._buys_unfunded, []

    def guard(ad, run):
        out = real(ad, run)
        seen.append(dict(run.get("buy_cash") or {}, why=out, utc=r.clock.now))
        return out
    r.m._buys_unfunded = guard
    return seen


# ============================================================================== P1 / P2 / T2: resolves
def _never_reaches_the_venue(r, symbol):
    """the sell's placement raises before the venue sees it, and the venue can prove neither that it
    holds it nor that it never saw it: UNRESOLVED (the review's S2)"""
    real = r.venue.place_stock_order

    def place(sym, qty, order_type, **kw):
        if sym == symbol:
            raise RuntimeError("no venue ack within 10s - state UNKNOWN")
        return real(sym, qty, order_type, **kw)
    r.venue.place_stock_order = place
    r.venue.history_ok, r.venue.absent = False, None


def _executes_then_goes_dark(r, symbol):
    """the sell EXECUTES at the venue, its ack never comes back, and the venue then answers for it no
    more (a session boundary): UNRESOLVED, with the shares really sold"""
    real = r.venue.place_stock_order

    def place(sym, qty, order_type, **kw):
        out = real(sym, qty, order_type, **kw)
        if sym == symbol:
            r.venue.forgotten.add(kw["client_order_id"])
            raise RuntimeError("no venue ack within 10s - state UNKNOWN")
        return out
    r.venue.place_stock_order = place
    r.venue.history_ok, r.venue.absent = False, None


def _resolve_bil(r, price, note):
    run = r.m.state["run"]
    cid = f"mirror-{D2}-S-BIL"
    assert run and run["orders"][cid].get("stuck"), run["orders"].get(cid)
    qty = next(o for o in run["plan"]["sells"] if o["symbol"] == "BIL")["qty"]
    r.m.request_resolve(cid, qty, price, 1.0, note)
    return qty


def test_p1_a_resolve_stating_a_sale_that_never_executed_holds_the_buys(tmp_path):
    r = day_one(tmp_path, HG_ONLY)
    cash = Shown(r)                                                   # IB never refreshes inside the window
    _never_reaches_the_venue(r, "BIL")
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    _resolve_bil(r, PX["BIL"], "operator: it filled (wrong: it never reached the venue)")
    seen = spy_guard(r)
    r.tick("15:56:10", day=D2)
    for hms in WINDOW:
        r.tick(hms, day=D2)
    print(f"[P1] buys={bought(r, n0)} low={cash.low:,.2f}")
    assert cash.low >= -1e-6, f"the account borrowed ${-cash.low:,.2f} to fund {bought(r, n0)}"
    assert bought(r, n0) == [] and held(r) and any("NO BUYS are sent this session" in a for a in r.red())
    assert r.venue.positions_snapshot()["stocks"]["BIL"] == r.m.state["last_run"]["orders"][0]["qty"]
    assert seen and all(s["cover"] == s["account"] for s in seen)     # F alone, every look
    assert "BIL: the sells leave 0, the account holds" in seen[0]["positions"]


FELL = 74.0                     # where BIL really sold: 19% under its 91.50 reference


def test_p2_a_resolve_stating_a_price_above_the_real_one_holds_the_buys_while_ib_lags(tmp_path):
    """the BIL sell really sold its 357 shares, at 74.00; the operator states 91.50 (its reference: well
    inside the resolve's 20% band). The positions agree - the shares did go - and only IB's cash can
    show the price, so the sale is counted at nothing until it does. (The buy asks are sized at the
    reference: an overstated price borrows only when the real one is under it, as here.)"""
    r = day_one(tmp_path, HG_ONLY)
    r.venue.fill_px["BIL"] = FELL
    cash = Shown(r)
    _executes_then_goes_dark(r, "BIL")
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    _resolve_bil(r, PX["BIL"], "operator: filled (the price misread)")
    seen = spy_guard(r)
    r.tick("15:56:10", day=D2)
    for hms in WINDOW:
        r.tick(hms, day=D2)
    print(f"[P2] buys={bought(r, n0)} low={cash.low:,.2f}")
    assert cash.low >= -1e-6, f"the account borrowed ${-cash.low:,.2f} to fund {bought(r, n0)}"
    assert bought(r, n0) == [] and held(r)
    assert seen[0].get("positions") == "agree" and seen[0]["cover"] == seen[0]["account"]
    assert "resolved by the operator, counted at nothing" in held(r)[0]


def test_p2_twin_t2_a_resolve_stating_the_true_terms_is_bought_once_ib_shows_the_cash(tmp_path):
    r = day_one(tmp_path, HG_ONLY)
    r.venue.fill_px["BIL"] = FELL
    cash = Shown(r)
    _executes_then_goes_dark(r, "BIL")
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    _resolve_bil(r, FELL, "operator: filled at 74.00, from the statement")
    r.tick("15:56:10", day=D2)
    cash.show()                                                       # IB's cash shows the sale now
    for hms in WINDOW:
        r.tick(hms, day=D2)
    got = dict(bought(r, n0))
    assert got.get("TQQQ", 0) > 300 and cash.low >= -1e-6, (got, cash.low)   # (HARV's idle cash buys 2 PULS)
    tm.sound(r)


# ============================================================================== T1: liveness kept
def test_t1_lagging_cash_and_agreeing_positions_buy_in_the_step_the_sells_are_booked(tmp_path):
    r = day_one(tmp_path, ROT)
    r.venue.report_commission = False                                 # every commission reported late
    cash = Shown(r)                                                   # frozen past the window (> 300 s)
    seen = spy_guard(r)
    n0, t0 = len(r.venue.placed), at("15:55:05", D2)
    sent = []
    real = r.venue._send

    def send(symbol, qty, client_order_id, limit):
        sent.append(r.clock.now)
        return real(symbol, qty, client_order_id, limit)
    r.venue._send = send
    r.tick("15:55:05", day=D2)
    assert {s for s, _ in bought(r, n0)} == {"TQQQ", "SPY"} and set(sent) == {t0}, sent
    assert len(seen) == 1 and seen[0]["why"] is None
    assert seen[0]["cover"] == seen[0]["estimate"] > seen[0]["account"] == seen[0]["before"]
    assert seen[0].get("positions", "agree") == "agree"               # (the first pass kept no such record)
    assert not held(r) and cash.low >= -1e-6
    r.venue.report_commission = True
    r.tick("15:59:50", day=D2)
    tm.sound(r)


# ============================================================================== P5 / P6 / P7: the rule before
def _buy_by_hand(r, cash, shares):
    def go(run):
        r.venue._positions["SPY"] = r.venue._positions.get("SPY", 0) + shares
        cash.move(-shares * PX["SPY"])
    return go


def test_p5_a_large_purchase_by_hand_before_the_buys_never_funds_them_on_margin(tmp_path):
    r = day_one(tmp_path, ROT)
    cash = Shown(r)
    before_first_guard(r, _buy_by_hand(r, cash, 33))                  # $19,800 of SPY, the reading lagging it
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    cash.show()                                                       # IB catches up: the sells AND the purchase
    for hms in WINDOW:
        r.tick(hms, day=D2)
    print(f"[P5] buys={bought(r, n0)} low={cash.low:,.2f}")
    assert cash.low >= -1e-6, f"the account borrowed ${-cash.low:,.2f} to fund {bought(r, n0)}"
    assert bought(r, n0) == [] and held(r)


def test_p5_a_small_purchase_by_hand_holds_the_buys_until_ib_shows_it_the_rule_before(tmp_path):
    r = day_one(tmp_path, ROT)
    cash = Shown(r)
    before_first_guard(r, _buy_by_hand(r, cash, 1))                   # one SPY: the slack outside covers it
    seen = spy_guard(r)
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    assert bought(r, n0) == [], "bought on the estimate although the positions disagree with the sells"
    assert seen and seen[0]["cover"] == seen[0]["account"] and seen[0]["why"]
    assert seen[0]["positions"].startswith("the account's positions are not what the booked sells leave (SPY")
    assert held(r) and "is not used: the account's positions are not what" in held(r)[0]
    cash.show()                                                       # IB's cash moves: exactly the rule before
    r.tick("15:57:40", day=D2)
    assert {s for s, _ in bought(r, n0)} == {"TQQQ", "SPY"} and cash.low >= -1e-6
    assert r.m.state["run"] is None or r.m.state["run"]["phase"] == "buys"


def test_p6_positions_that_cannot_be_read_before_the_buys_take_the_rule_before(tmp_path):
    r = day_one(tmp_path, ROT)
    cash = Shown(r)
    real = r.venue.positions_snapshot
    down = {"on": False}

    def snap():
        if down["on"]:
            raise ConnectionError("Socket disconnect")
        return real()
    r.venue.positions_snapshot = snap
    before_first_guard(r, lambda run: down.update(on=True))
    seen = spy_guard(r)
    n0 = len(r.venue.placed)
    r.tick("15:55:05", day=D2)
    assert bought(r, n0) == [] and seen[0]["cover"] == seen[0]["account"]
    assert seen[0]["positions"].startswith("the account's positions cannot be read")
    down["on"] = False
    cash.show()
    r.tick("15:57:40", day=D2)
    assert {s for s, _ in bought(r, n0)} == {"TQQQ", "SPY"} and cash.low >= -1e-6


def test_p7_a_run_on_disk_with_no_record_of_the_positions_takes_the_rule_before(tmp_path):
    """the process restarts mid-run on a state file whose run carries cash0 but no pos0: the estimate
    is not used while IB's cash lags (never sized from a record that cannot be checked)"""
    r = day_one(tmp_path, ROT)
    cash = Shown(r)

    def unreadable(run):                                              # at the first look; the tick hands back
        r.venue.cash_claim = False
        r.clock.interrupt = True
    before_first_guard(r, unreadable)
    n0, held0 = len(r.venue.placed), dict(r.venue.positions_snapshot()["stocks"])
    r.tick("15:55:05", day=D2)
    assert r.m.state["run"]["buys_blocked"] and r.m.state["run"].get("cash0") is not None
    st = json.load(open(r.m.cfg.state_path))
    had = st["run"].pop("pos0", None)
    json.dump(st, open(r.m.cfg.state_path, "w"))
    r.venue.cash_claim = True
    r.boot()
    seen = spy_guard(r)
    r.tick("15:56:00", day=D2)                                        # one look (the clock still interrupts)
    assert bought(r, n0) == [], "bought on an estimate whose sells nothing could check"
    assert seen and seen[-1]["cover"] == seen[-1]["account"]
    assert "no record of the account's positions" in seen[-1]["positions"]
    r.clock.interrupt = False
    cash.show()
    r.tick("15:56:40", day=D2)
    assert {s for s, _ in bought(r, n0)} == {"TQQQ", "SPY"} and cash.low >= -1e-6
    assert had == held0                                               # on disk: what the account held before


# ============================================================================== P9: the cross-check itself
class _Ad:
    def __init__(self, stocks=None, other=(), raises=None):
        self.stocks, self.other, self.raises = dict(stocks or {}), list(other), raises

    def positions_snapshot(self):
        if self.raises:
            raise self.raises
        return {"stocks": dict(self.stocks), "other": list(self.other)}


def _run(pos0, sells, buys=None):
    return {"pos0": pos0, "plan": {"sells": [dict(o, side="SELL") for o in sells],
                                   "buys": None if buys is None else [dict(o, side="BUY") for o in buys]}}


def test_p9_sells_confirmed_answers_only_for_exactly_the_booked_shares(tmp_path):
    m = Rig(tmp_path, live=True).m
    run = _run({"BIL": 315, "PULS": 50}, [{"symbol": "BIL", "filled": 100}, {"symbol": "PULS", "filled": 0}])
    assert m._sells_confirmed(run, _Ad({"BIL": 215, "PULS": 50})) == (True, "agree")
    sold_out = _run({"BIL": 315}, [{"symbol": "BIL", "filled": 315}], buys=[{"symbol": "TQQQ", "filled": 7}])
    assert m._sells_confirmed(sold_out, _Ad({"TQQQ": 7})) == (True, "agree")      # a symbol gone, one new
    ok, why = m._sells_confirmed(run, _Ad({"BIL": 115, "PULS": 50}))               # 200 booked as 100
    assert not ok and "BIL: the sells leave 215, the account holds 115" in why
    ok, why = m._sells_confirmed(run, _Ad({"BIL": 215, "PULS": 50, "SPY": 1}))     # a purchase by hand
    assert not ok and "SPY: the sells leave 0, the account holds 1" in why
    ok, why = m._sells_confirmed(run, _Ad({"BIL": 215, "PULS": 50}, other=["OPT SPY 1"]))
    assert not ok and "not a whole stock lot" in why
    ok, why = m._sells_confirmed(run, _Ad(raises=ConnectionError("Not connected")))
    assert not ok and why.startswith("the account's positions cannot be read")
    ok, why = m._sells_confirmed(dict(run, pos0=None), _Ad({"BIL": 215, "PULS": 50}))
    assert not ok and "no record" in why
    ok, why = m._sells_confirmed(dict(run, pos0={"BIL": "315 shares"}), _Ad({"BIL": 215, "PULS": 50}))
    assert not ok and "cannot be read" in why                        # a damaged record: a no, never a raise


# ============================================================================== P3 / P4: the REAL IBAdapter
def _real(tmp_path, monkeypatch, cash=103_100.0):
    """the real IBAdapter over StaleIB: a $100k book in a $103,100 account ($3,100 outside the book)"""
    r = tc.Rig(tmp_path, monkeypatch, cash=cash)
    r.tick("15:00")
    r.tick("15:55:05")
    r.tick("15:56:40")
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.state["check"]["done"] is True
    r.brain.make = lambda now: payload(now, HG_ONLY, session=D2)
    return r


class Frozen:
    """the gateway's TotalCashValue frozen at freeze() on every session; low: the least the account's
    TRUE cash ever was (at every execution and every read)"""

    def __init__(self, r, monkeypatch):
        self.r, self.value, self.low = r, None, r.acct.cash
        real_vals, real_exec, me = type(r.ib).accountValues, type(r.ib).execute, self

        def values(ib):
            rows = real_vals(ib)
            me.low = min(me.low, r.acct.cash)
            if me.value is None:
                return rows
            return [types.SimpleNamespace(tag=x.tag, currency=x.currency, account=x.account,
                                          value=str(me.value) if x.tag == "TotalCashValue" else x.value) for x in rows]

        def execute(ib, t, shares, price=None, commission=1.0):
            real_exec(ib, t, shares, price, commission)
            me.low = min(me.low, r.acct.cash)
        monkeypatch.setattr(type(r.ib), "accountValues", values)
        monkeypatch.setattr(type(r.ib), "execute", execute)

    def freeze(self):
        self.value = self.r.acct.cash


def _corrected_partial(monkeypatch, r, first, second):
    """the BIL sell executes 100 shares (execId `first`), IB then CORRECTS that execution (`second`:
    the same 100 shares re-reported - it moves no share and no cash a second time) and the rest of the
    order is cancelled"""
    real = type(r.ib).placeOrder

    def place(ib, contract, order):
        if order.action != "SELL":
            return real(ib, contract, order)
        ib.hold.add(contract.symbol)
        try:
            t = real(ib, contract, order)
        finally:
            ib.hold.discard(contract.symbol)
        ib.execute(t, 100)
        a = t.fills[-1]
        a.execution.execId = a.commissionReport.execId = first
        ib.execute(t, 100)
        b = t.fills[-1]
        b.execution.execId = b.commissionReport.execId = second
        ib.acct.pos[contract.symbol] += 100
        ib.acct.cash -= 100 * b.execution.price - 1.0
        t.orderStatus.filled = 100
        t.orderStatus.status = "Cancelled"
        return t
    monkeypatch.setattr(type(r.ib), "placeOrder", place)


def _real_window(r):
    r.tick("15:55:05", day=D2)
    for hms in ("15:55:40", "15:56:40", "15:57:40", "15:58:30", "15:59:05", "15:59:40"):
        if r.m.state.get("run") is None:
            break
        r.tick(hms, day=D2)


def test_p3_a_corrected_execution_is_booked_once_and_buys_only_what_it_brought(tmp_path, monkeypatch):
    r = _real(tmp_path, monkeypatch)
    cash = Frozen(r, monkeypatch)
    n = len(r.ib.placed)
    _corrected_partial(monkeypatch, r, "0000e0d5.6556c9f3.01.01", "0000e0d5.6556c9f3.01.02")
    r.tick("15:00", day=D2)
    cash.freeze()
    hg = r.m.book.sleeves["HG"].cash
    _real_window(r)
    sold = [(o["symbol"], o["filled"]) for o in (r.m.state.get("last_run") or {}).get("orders", []) if o["side"] == "SELL"]
    buys = [(s, q) for s, a, q, _ in r.ib.placed[n:] if a == "BUY"]
    print(f"[P3] booked={sold} buys={buys} low={cash.low:,.2f}")
    assert sold == [("BIL", 100)], sold
    assert cash.low >= -1e-6, f"the account borrowed ${-cash.low:,.2f}"
    assert [s for s, _ in buys] == ["TQQQ"] and buys[0][1] * 80.4 <= hg + 100 * PX["BIL"] - 1.0
    assert r.m.book.positions() == r.venue_pos()                     # the book holds what the account holds


def test_p4_a_double_count_the_adapter_cannot_see_is_caught_by_the_positions(tmp_path, monkeypatch):
    """the same correction, with execIds that are not in IB's correction form (different bases): the
    adapter cannot pair them and the book books 200 sold. The account's positions show 100 sold: the
    estimate is not used and the buys wait for IB's cash, which never comes inside the window"""
    r = _real(tmp_path, monkeypatch)
    cash = Frozen(r, monkeypatch)
    n = len(r.ib.placed)
    _corrected_partial(monkeypatch, r, "0000e0d5.6556c9f3.01.01", "0000e0d5.6556c9f4.01.01")
    r.tick("15:00", day=D2)
    cash.freeze()
    _real_window(r)
    buys = [(s, q) for s, a, q, _ in r.ib.placed[n:] if a == "BUY"]
    print(f"[P4] buys={buys} low={cash.low:,.2f}")
    assert cash.low >= -1e-6, f"the account borrowed ${-cash.low:,.2f}"
    assert buys == [] and any("the BUYS are HELD" in a and "BIL: the sells leave" in a for a in r.red())


# ============================================================================== P8 / T3: the adapter
CID = "mirror-2026-11-11-S-BIL"


def _sell_working(ib_adapter):
    """a BIL MKT sell that the venue holds as working (no fill inside the placement's wait)"""
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("BIL", -300, "MKT", client_order_id=CID)
    assert r["status"] == "working"
    return fake.trade_by_ref(r["order_ref"])


def _fill(trade, shares, price, exec_id, commission=1.0):
    ex = FakeExec(shares, price, "SLD")
    ex.orderRef, ex.orderId, ex.execId = trade.order.orderRef, trade.order.orderId, exec_id
    f = FakeFill(ex, commission)
    f.commissionReport.execId = exec_id
    trade.fills.append(f)
    return f


def test_p8_stock_order_fills_counts_a_corrected_execution_once(ib_adapter):
    t = _sell_working(ib_adapter)
    _fill(t, 100, 91.50, "0000e0d5.6556c9f3.01.01")
    _fill(t, 100, 91.40, "0000e0d5.6556c9f3.01.02")                  # the correction: 100 at 91.40
    t.orderStatus.filled, t.orderStatus.status = 100, "Cancelled"
    got = ib_adapter.stock_order_fills(CID)
    assert got["filled_qty"] == 100, got                              # never 200
    assert got["avg_price"] == pytest.approx(91.40) and got["commission"] == pytest.approx(1.0)
    found = ib_adapter.find_stock_order(CID)
    assert found["status"] == "cancelled" and found["filled_qty"] == 100


def test_p8_a_filled_trade_reports_the_corrected_terms(ib_adapter):
    t = _sell_working(ib_adapter)
    t.order.totalQuantity = 100
    _fill(t, 100, 91.50, "0000e0d5.6556c9f3.01.01", commission=1.0)
    _fill(t, 100, 91.40, "0000e0d5.6556c9f3.01.02", commission=1.25)
    _fill(t, 100, 91.45, "0000e0d5.6556c9f3.01.03", commission=1.5)  # corrected twice: the last one stands
    t.orderStatus.filled, t.orderStatus.status = 100, "Filled"
    found = ib_adapter.find_stock_order(CID)
    assert found["status"] == "filled" and found["fill_price"] == pytest.approx(91.45)
    assert found["commission"] == pytest.approx(1.5)
    got = ib_adapter.stock_order_fills(CID)
    assert (got["filled_qty"], got["avg_price"], got["commission"]) == (100, pytest.approx(91.45), pytest.approx(1.5))


def test_p8_a_correction_whose_report_has_not_come_is_unreported_not_the_first_ones(ib_adapter):
    t = _sell_working(ib_adapter)
    _fill(t, 100, 91.50, "0000e0d5.6556c9f3.01.01", commission=1.0)
    late = _fill(t, 100, 91.50, "0000e0d5.6556c9f3.01.02", commission=1.0)
    late.commissionReport = None                                      # the correction's report is not in yet
    t.orderStatus.filled, t.orderStatus.status = 100, "Cancelled"
    got = ib_adapter.stock_order_fills(CID)
    assert got["filled_qty"] == 100 and got["commission"] is None


def test_p8_the_execution_report_fallback_counts_a_correction_once(ib_adapter):
    """completed orders unavailable and the trade not in this session: 'did it fill?' is answered from
    the execution store, which holds the execution AND its correction"""
    fake = ib_adapter.ib
    fake.reqCompletedOrders = lambda apiOnly=False: (_ for _ in ()).throw(TimeoutError("x"))
    fake.fills = lambda: [_exec_fill(CID, 100, 91.50, exec_id="0000e0d5.6556c9f3.01.01"),
                          _exec_fill(CID, 100, 91.40, exec_id="0000e0d5.6556c9f3.01.02"),
                          _exec_fill(CID, 40, 91.60, exec_id="0000e0d5.6556c9f9.01.01")]
    fake.reqExecutions = lambda *a, **k: []
    r = ib_adapter.find_stock_order(CID)
    assert r["status"] == "filled" and r["filled_qty"] == 140, r
    assert r["fill_price"] == pytest.approx((100 * 91.40 + 40 * 91.60) / 140) and r["commission"] == 2.0


def test_p8_a_restart_counts_a_correction_once_across_the_trade_and_the_store(ib_adapter, monkeypatch):
    """after a restart the trade's own fills and the execution store can each hold one of the pair"""
    venue, execs = [], []
    fake = _session(ib_adapter, monkeypatch, venue, execs)
    r = ib_adapter.place_limit_order("TECL", 108, 100.5, client_order_id="mirror-2026-11-11-B-TECL")
    t = fake.trade_by_ref(r["order_ref"])
    _execute(fake, t, 40, 100.5, "0000e0d5.6556c9f3.01.01", commission=1.0)
    _execute(fake, t, 40, 100.25, "0000e0d5.6556c9f3.01.02", commission=1.0)
    t.orderStatus.filled, t.orderStatus.status = 40, "Cancelled"
    assert ib_adapter.stock_order_fills("mirror-2026-11-11-B-TECL")["filled_qty"] == 40
    _session(ib_adapter, monkeypatch, venue, execs, next_id=1000)    # the restart: a bare completed row
    got = ib_adapter.stock_order_fills("mirror-2026-11-11-B-TECL")
    assert got == {"filled_qty": 40, "avg_price": 100.25, "commission": 1.0, "venue_status": "Cancelled"}


def test_p8_a_stop_fill_with_a_correction_is_polled_once_at_its_shares(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0, client_order_id="blend-1-stp-44.0000")
    t = fake.trade_by_ref(r["order_ref"])
    _fill(t, 5, 44.0, "00018037.5d7b2e1c.01.01")
    _fill(t, 5, 43.95, "00018037.5d7b2e1c.01.02")
    t.orderStatus.status = "Filled"
    (f,) = ib_adapter.poll_stock_fills()
    assert f["qty"] == -5 and f["fill_price"] == pytest.approx(43.95)


def test_t3_distinct_executions_and_ids_not_in_ibs_form_are_summed_as_before(ib_adapter):
    t = _sell_working(ib_adapter)
    _fill(t, 100, 91.50, "0000e0d5.6556c9f3.01.01")
    _fill(t, 100, 91.40, "0000e0d5.6556c9f4.01.01")                  # another execution, not a correction
    _fill(t, 30, 91.30, "e7")
    _fill(t, 20, 91.30, "")                                           # no execId at all
    t.orderStatus.filled, t.orderStatus.status = 250, "Cancelled"
    got = ib_adapter.stock_order_fills(CID)
    assert got["filled_qty"] == 250
    assert got["avg_price"] == pytest.approx((100 * 91.5 + 100 * 91.4 + 50 * 91.3) / 250)
