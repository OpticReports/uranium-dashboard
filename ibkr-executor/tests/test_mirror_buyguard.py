"""C-52 re-done (2026-11-12): the buys' cash guard counts the run's own fills from their execution
reports instead of waiting for a TotalCashValue that lags them (app/mirror.py _cash_cover).

IB documents its account updates as sent on a position change and otherwise every three minutes, and
ib_async keeps only the last TotalCashValue, with no time. The guard compared the book's cash with that
reading alone, so once the day's sells exceeded the account's cash outside the book it held the buys
until IB caught up - and for the whole session on a lag past the cancel instant - and a commission not
yet reported (booked at 0) counted as a shortfall.

GATES - each FAILS on the code before this change and passes after:
  BG1  a book at 97% of a $117k account rotates ~$96k, every commission reported late, IB's
       TotalCashValue lagging the fills by 30 / 120 / 180 / 300 s: the buys go in the step the sells are
       booked, sized exactly as on a day with no lag (before: 30 / 120 / 180 s late; none at all on 300)
  BG2  the same over the REAL IBAdapter: the gateway session dies between the sells and the buys and the
       new session's TotalCashValue still shows the cash from before the sells: the buys go once the
       session answers (before: held until the window closed)
  BG3  what the guard counted is on the run (run["buy_cash"]): the cash before the run plus each sell's
       EXECUTED shares, never its planned ones (a rejected sell, a partial one); each unreported
       commission at its bound (before: no such record, and the buys held)
  BT2  at a 300 s lag (below) is a gate too: before, no buys at all
  tests/test_mirror_round3b.py G6 (rewritten): a reading that lags every fill holds nothing

TWINS - what the guard must still refuse or count right; they pass before and after:
  BG1  with no lag (0 s): the buys go at once, as before
  BT1  cash withdrawn by hand that the TotalCashValue shows: held for the session, no buys; one the
       account can afford holds nothing
  BT2  a sell the venue rejects, and one it fills in part and cancels: booked at what executed; the
       sleeve that did not sell buys only with the cash it really had; nobody borrows
  BT3  a sell filled far under its reference with no price reported (the book over-counts it): held,
       lagging TotalCashValue or not
  BT4  the session dies between the sells and the buys: held while it cannot be read, sent when it
       answers; with cash withdrawn by hand meanwhile, held for the session
  BT5  a normal day at $10k and $50k in the $117k account: the orders, sizes and instants the code
       before this change sent (pinned from it)
  tests/test_mirror_round3b.py G6 (rewritten): a reading that has MOVED and does not cover still holds
       the buys until it covers, or for the session
Every gate ends on the ACCOUNT never below zero.
"""
from __future__ import annotations

import time
import types
from datetime import timedelta

import pytest

import test_mirror as tm
import test_mirror_connection as tc                                   # the REAL IBAdapter's rig (BG2, BT4)
from app import mirror as mm
from test_mirror import PX, T1, Rig, at, payload

D2 = "2026-11-11"
ACCOUNT = 117_000.0
BOOK97 = round(0.97 * ACCOUNT, 2)                 # $113,490: $3,510 of the account's cash is outside the book
# day two: HG BIL -> TQQQ, KMLM SOXL/TECL/PULS -> SPY, SLEEVE BOXX -> TQQQ (HARV keeps PULS): five sells, ~$96k
ROT = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"PULS": 1.0}}
LAGS = (0, 30, 120, 180, 300)
AFTER = ("15:55:40", "15:56:40", "15:57:40", "15:58:30", "15:59:05", "15:59:40")


class Tape:
    """the account's TotalCashValue as IB serves it: every change of the venue's cash is stamped with
    the simulated instant it happened and shown `lag` seconds later. `low` is the least the account's
    cash ever was."""

    def __init__(self, r, lag):
        self.r, self.lag = r, lag
        self.tape = [(None, r.venue.cash)]
        self.low = r.venue.cash
        real_fill = r.venue._fill

        def fill(rec, shares):
            real_fill(rec, shares)
            self.mark()
        r.venue._fill = fill
        r.venue.account_cash = self.read

    def mark(self):
        self.tape.append((self.r.clock.now, self.r.venue.cash))
        self.low = min(self.low, self.r.venue.cash)

    def withdraw(self, amount):
        self.r.venue.cash -= amount
        self.mark()

    def read(self):
        if not self.r.venue.cash_claim:
            return None
        cut, cash = self.r.clock.now - timedelta(seconds=self.lag), self.tape[0][1]
        for t, c in self.tape[1:]:
            if t <= cut:
                cash = c
        return {"total_cash": cash, "net_liq": None, "available_funds": cash, "ts": time.time()}


def stamped(r):
    """[(symbol, signed qty, limit, instant)] of every order that reaches the venue from now on"""
    out, real = [], r.venue._send

    def send(symbol, qty, client_order_id, limit):
        out.append((symbol, qty, limit, r.clock.now))
        return real(symbol, qty, client_order_id, limit)
    r.venue._send = send
    return out


def day_one(tmp_path, book=BOOK97, account=ACCOUNT):
    """day one seeded and traded (T1); the account's other cash stays outside the book"""
    r = Rig(tmp_path, live=True, capital=book, venue_cash=account)
    r.tick("15:00")
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.book.positions() == r.venue.positions_snapshot()["stocks"]
    assert r.venue.cash - r.m.book.cash() == pytest.approx(account - book, abs=0.01)
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    return r


def rotate(r, lag, late_commissions=True, before=None):
    """day two: the account's cash read through a Tape of `lag` s, $1 commissions charged at the fill and
    (late_commissions) reported only after the run; ticks through the window and the post-trade check"""
    tape = Tape(r, lag)
    r.venue.commission = 1.0
    r.venue.report_commission = not late_commissions
    sent = stamped(r)
    if before:
        before(r, tape)
    r.tick("15:00", day=D2)
    r.tick("15:55:05", day=D2)
    for hms in AFTER:
        if r.m.state.get("run") is None:
            break
        r.tick(hms, day=D2)
    r.venue.report_commission = True                 # the reports arrive; the post-trade check trues them up
    r.tick("15:59:50", day=D2)
    return tape, sent


def buys(sent):
    return [(s, q, lim) for s, q, lim, _ in sent if q > 0]


def held_alerts(r):
    return [a for a in r.red() if "BUYS are HELD" in a or "NO BUYS" in a]


# --------------------------------------------------------------------------------------------- BG1
@pytest.fixture(scope="module")
def no_lag_buys(tmp_path_factory):
    """the buys of the rotation on a day IB's cash shows the fills at once and reports every commission"""
    r = day_one(tmp_path_factory.mktemp("nolag"))
    tape, sent = rotate(r, lag=0, late_commissions=False)
    out = buys(sent)
    assert {s for s, _, _ in out} == {"TQQQ", "SPY"} and tape.low >= 0
    return out


@pytest.mark.parametrize("lag", LAGS)
def test_bg1_a_lagging_cash_reading_and_late_commissions_hold_nothing_at_97pct(tmp_path, lag, no_lag_buys):
    r = day_one(tmp_path)
    tape, sent = rotate(r, lag)
    sells = [x for x in sent if x[1] < 0]
    assert sorted(s for s, *_ in sells) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]
    proceeds = sum(-q * PX[s] for s, q, _, _ in sells)
    assert 90_000 < proceeds < 100_000                               # ~27 times the $3,510 outside the book
    t0 = at("15:55:05", D2)
    assert {t for *_, t in sent} == {t0}, sent                       # sells AND buys in the decision's first step
    assert buys(sent) == no_lag_buys                                 # ... sized exactly as on a day with no lag
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded" and not held_alerts(r), held_alerts(r)
    assert not [n for n in row["notes"] if "buys" in n]
    assert set(r.m.book.positions()) == {"TQQQ", "SPY", "PULS"}
    assert tape.low >= 0 and r.venue.cash >= 0                       # the account never borrowed
    assert r.m.state["commission_pending"] == []                     # the late commissions were trued up after
    tm.sound(r)


# --------------------------------------------------------------------------------------------- BG3
def _partial_then_cancelled(r, symbol, shares):
    """the venue fills `shares` of the symbol's sell and cancels the rest within the window"""
    real = r.venue.place_stock_order

    def place(sym, qty, order_type, **kw):
        if sym != symbol:
            return real(sym, qty, order_type, **kw)
        r.venue.hold.add(sym)
        try:
            real(sym, qty, order_type, **kw)
        finally:
            r.venue.hold.discard(sym)
        rec = r.venue._orders[r.venue._by_client[kw["client_order_id"]]]
        r.venue._fill(rec, shares)
        rec.update(status="cancelled", reason="[202] the rest was cancelled by the venue")
        return r.venue._order_result(rec)
    r.venue.place_stock_order = place


def _sell_ends(r, how):
    if how == "rejected":
        r.venue.reject.add("BOXX")
    elif how == "partial":
        _partial_then_cancelled(r, "BOXX", 100)


@pytest.mark.parametrize("how", ["filled", "rejected", "partial"])
def test_bg3_the_estimate_counts_what_executed_never_the_plan_and_is_on_the_run(tmp_path, how):
    """IB's TotalCashValue lags 300 s and every commission is late: what the guard counted - the cash
    before the run plus each sell's EXECUTED shares at its reported price, less each unreported
    commission at its bound - is on the run (run["buy_cash"]), and a rejected sell, or the part of one the
    venue cancelled, is not in it"""
    r = day_one(tmp_path)
    seen = {}
    real = r.m._buys_unfunded

    def spy(ad, run):
        out = real(ad, run)
        seen.update(run.get("buy_cash") or {}, cash0=run.get("cash0"), why=out)
        return out

    def setup(r, tape):
        r.m._buys_unfunded = spy
        _sell_ends(r, how)
    tape, sent = rotate(r, lag=300, before=setup)
    before = tape.tape[0][1]
    fills = [rec for rec in r.venue._orders.values() if rec["qty"] < 0 and rec.get("filled_qty")]
    assert len(fills) == (4 if how == "rejected" else 5)
    boxx = next(rec for rec in r.venue._orders.values() if rec["symbol"] == "BOXX" and rec["qty"] < 0)
    assert boxx.get("filled_qty", 0) == {"filled": -boxx["qty"], "rejected": 0, "partial": 100}[how]
    net = sum(rec["filled_qty"] * rec["fill_price"] for rec in fills)
    bound = sum(mm.COMMISSION_WORST_FRAC * rec["filled_qty"] * rec["fill_price"] + mm.COMMISSION_WORST_USD
                for rec in fills)                                    # every commission was still unreported
    assert seen["why"] is None and seen["cash0"] == pytest.approx(before) and seen["before"] == pytest.approx(before)
    assert seen["account"] == pytest.approx(before)                  # the reading still showed none of the fills
    assert seen["estimate"] == pytest.approx(before + net - bound, abs=0.01)
    assert seen["cover"] == seen["estimate"] and seen["book"] <= seen["cover"] + mm.CASH_TOL_USD
    assert tape.low >= 0 and r.venue.cash >= 0


# --------------------------------------------------------------------------------------------- BT1
def _withdraw_before_the_guard(r, tape, amount):
    real, done = r.m._buys_unfunded, []

    def guard(ad, run):
        if not done:                                                 # every sell is booked; no buy is sized
            done.append(1)
            tape.withdraw(amount)
        return real(ad, run)
    r.m._buys_unfunded = guard


def test_bt1_cash_withdrawn_by_hand_that_the_account_shows_holds_the_buys_for_the_session(tmp_path):
    r = day_one(tmp_path)
    tape, sent = rotate(r, lag=0, late_commissions=False,
                        before=lambda r, tape: _withdraw_before_the_guard(r, tape, 20_000.0))
    assert buys(sent) == [] and sorted(s for s, q, *_ in sent if q < 0) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]
    row = r.m.state["last_run"]
    assert any(n.startswith("buys NOT sent: the book's cash") for n in row["notes"])
    assert any("BUYS are HELD" in a and "exceeds the account's" in a for a in r.red())
    assert len([a for a in r.red() if "NO BUYS are sent this session" in a]) == 1
    assert tape.low >= 0 and r.venue.cash >= 0


def test_bt1_twin_a_withdrawal_the_account_can_afford_holds_nothing(tmp_path, no_lag_buys):
    r = day_one(tmp_path)
    tape, sent = rotate(r, lag=0, late_commissions=False,
                        before=lambda r, tape: _withdraw_before_the_guard(r, tape, 1_000.0))
    assert buys(sent) == no_lag_buys and not held_alerts(r)
    assert tape.low >= 0 and r.venue.cash >= 0


# --------------------------------------------------------------------------------------------- BT2
@pytest.mark.parametrize("how", ["rejected", "partial"])
@pytest.mark.parametrize("lag", [0, 300])
def test_bt2_a_sell_that_did_not_fill_is_booked_at_what_executed_and_buys_only_with_cash_there(tmp_path, how, lag):
    r = day_one(tmp_path)
    boxx, idle = r.m.book.positions()["BOXX"], r.m.book.sleeves["SLEEVE"].cash
    tape, sent = rotate(r, lag, late_commissions=False, before=lambda r, tape: _sell_ends(r, how))
    rec = next(x for x in r.venue._orders.values() if x["symbol"] == "BOXX" and x["qty"] < 0)
    got = rec.get("filled_qty", 0)
    assert got == (0 if how == "rejected" else 100) and got < boxx
    row = r.m.state["last_run"]
    assert next(o for o in row["orders"] if o["symbol"] == "BOXX")["filled"] == got
    assert r.m.book.positions()["BOXX"] == boxx - got                # SLEEVE still holds the rest, and bought
    spent = sum(o["split"].get("SLEEVE", 0) * o["price"] for o in row["orders"] if o["side"] == "BUY" and o["price"])
    assert spent <= idle + got * PX["BOXX"]                          # ... only with the cash it really had
    assert buys(sent) and tape.low >= 0 and r.venue.cash >= 0       # the other sleeves bought; nobody borrowed
    tm.sound(r)


# --------------------------------------------------------------------------------------------- BT3
@pytest.mark.parametrize("lag", [0, 300])
def test_bt3_a_sell_booked_at_its_reference_with_no_price_reported_holds_the_buys(tmp_path, lag):
    r = day_one(tmp_path)

    def setup(r, tape):
        r.venue.fill_px["BIL"] = 80.0                               # 12.6% under its 91.50 reference ...
        r.venue.no_price.add("BIL")                                 # ... and the venue reports no price
    tape, sent = rotate(r, lag, late_commissions=False, before=setup)
    assert buys(sent) == []
    row = r.m.state["last_run"]
    assert any(n.startswith("buys NOT sent: the book's cash") for n in row["notes"])
    assert any("booked at its REFERENCE" in a for a in r.red())
    assert len([a for a in r.red() if "NO BUYS are sent this session" in a]) == 1
    assert tape.low >= 0 and r.venue.cash >= 0


# --------------------------------------------------------------------------------------------- BT5
# what the code before this change sent on this day (run on it): a $10k and a $50k book inside the $117k
# account, every order at 15:55:05
PINNED = {
    10_000.0: [("BIL", -31, None), ("BOXX", -23, None), ("PULS", -14, None), ("SOXL", -27, None),
               ("TECL", -10, None), ("SPY", 4, 603.0), ("TQQQ", 69, 80.4)],
    50_000.0: [("BIL", -157, None), ("BOXX", -118, None), ("PULS", -72, None), ("SOXL", -135, None),
               ("TECL", -54, None), ("SPY", 24, 603.0), ("TQQQ", 347, 80.4)],
}


@pytest.mark.parametrize("book", sorted(PINNED))
def test_bt5_a_normal_day_at_10k_and_50k_sends_what_it_sent_before(tmp_path, book):
    r = day_one(tmp_path, book=book)
    tape, sent = rotate(r, lag=0, late_commissions=False)
    assert [(s, q, lim) for s, q, lim, _ in sent] == PINNED[book]
    assert {t for *_, t in sent} == {at("15:55:05", D2)} and not held_alerts(r)
    assert tape.low >= 0
    tm.sound(r)


# --------------------------------------------------------------------------------------------- BG2 / BT4
ROT_REAL = dict(T1, HG={"TQQQ": 1.0})                                  # HG sells its BIL and buys TQQQ


def _real_97(tmp_path, monkeypatch):
    """the REAL IBAdapter over the connection tests' StaleIB: a $100k book in a $103,100 account (97%)"""
    r = tc.Rig(tmp_path, monkeypatch, cash=103_100.0)
    r.tick("15:00")
    r.tick("15:55:05")
    r.tick("15:56:40")
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.state["check"]["done"] is True
    r.brain.make = lambda now: payload(now, ROT_REAL, session=D2)
    return r


def _die_after_the_last_sell(r, monkeypatch, then=None):
    real, sells = r.ib.placeOrder, {}

    def place(contract, order):
        t = real(contract, order)
        if order.action == "SELL":
            sells[contract.symbol] = 1
            if len(sells) == 1:                                     # ROT_REAL sells BIL alone
                r.ib.drop(silent=True)
                if then:
                    then()
        return t
    monkeypatch.setattr(r.ib, "placeOrder", place)


def _stale_cash_after_reconnect(r, monkeypatch, reads):
    """once the session the sells went out on is gone, the new one's TotalCashValue shows the account as it
    stood before the sells, for `reads` reads"""
    before, real, n, first = r.acct.cash, type(r.ib).accountValues, {"k": 0}, r.ib.connect_calls

    def values(self):
        rows = real(self)
        if self.dead or not self.connected or self.connect_calls <= first or n["k"] >= reads:
            return rows
        n["k"] += 1
        return [types.SimpleNamespace(tag=x.tag, currency=x.currency, account=x.account,
                                      value=str(before) if x.tag == "TotalCashValue" else x.value) for x in rows]
    monkeypatch.setattr(type(r.ib), "accountValues", values)


def test_bg2_a_session_that_dies_after_the_sells_and_reads_stale_cash_still_buys(tmp_path, monkeypatch):
    r = _real_97(tmp_path, monkeypatch)
    n, sessions = len(r.ib.placed), r.ib.connect_calls
    _die_after_the_last_sell(r, monkeypatch)
    _stale_cash_after_reconnect(r, monkeypatch, reads=10 ** 6)        # IB never catches up inside the window
    r.tick("15:55:05", day=D2)
    for hms in AFTER:
        if r.m.state.get("run") is None:
            break
        r.tick(hms, day=D2)
    placed = [(s, a, q) for s, a, q, _ in r.ib.placed[n:]]
    assert placed == [("BIL", "SELL", 315), ("TQQQ", "BUY", 360)], placed
    assert r.ib.connect_calls == sessions + 1                        # the buys went out on the NEW session
    assert not [a for a in r.red() if "BUYS are HELD" in a or "NO BUYS" in a]
    assert r.acct.cash >= 0


def test_bt4_the_session_dies_and_cash_is_withdrawn_by_hand_held_for_the_session(tmp_path, monkeypatch):
    r = _real_97(tmp_path, monkeypatch)
    n = len(r.ib.placed)
    _die_after_the_last_sell(r, monkeypatch, then=lambda: setattr(r.acct, "cash", r.acct.cash - 20_000.0))
    r.tick("15:55:05", day=D2)
    for hms in AFTER:
        r.tick(hms, day=D2)
    assert [x for x in r.ib.placed[n:] if x[1] == "BUY"] == [] and r.acct.cash >= 0
    assert any("the BUYS are HELD" in a and "exceeds the account's" in a for a in r.red())
    assert len([a for a in r.red() if "NO BUYS are sent this session" in a]) == 1


def test_bt4_twin_the_gateway_gone_holds_the_buys_until_it_answers(tmp_path, monkeypatch):
    r = _real_97(tmp_path, monkeypatch)
    n = len(r.ib.placed)
    _die_after_the_last_sell(r, monkeypatch, then=lambda: setattr(r.ib, "gateway_up", False))
    r.tick("15:55:05", day=D2)
    assert [x for x in r.ib.placed[n:] if x[1] == "BUY"] == [] and r.m.state["run"]["buys_blocked"]
    assert any("the BUYS are HELD — the account's cash cannot be read" in a for a in r.red())
    r.ib.gateway_up = True
    r.tick("15:56:40", day=D2)
    assert [(s, a) for s, a, _, _ in r.ib.placed[n:] if a == "BUY"] == [("TQQQ", "BUY")]
    assert r.acct.cash >= 0
