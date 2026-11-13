"""C-52, third pass (2026-11-13): what the buying guard's two independent reviews left open - alerts and
observability. What trades does not change: these gates hold the orders, their sizes, limits and
instants to what the code before sent, and test only what is said and recorded.

GATES - each FAILS on 1de7535c and passes after:
  R1  (the liveness review's V3, adapted) 97% of a $117k account rotates ~$96k, IB's TotalCashValue
      never catching up, the account's positions trailing the fills by 5 / 30 / 120 s: the hold is said
      as a WARNING ("not yet confirmed by the account's positions; re-read every step") at the first
      look, and in red only once it has lasted BUYS_UNCONFIRMED_GRACE_S - at 5 s never (before: red at
      the first look, worded as a book/account mismatch)
  R1b the grace, unit by unit: measured from the hold's first look (run["buys_blocked_utc"]), none for
      a stamp that cannot be read (before: no such alert)
  R3  the run's buy_cash records when the account's positions FIRST confirmed the booked sells and how
      many seconds after the last sell was booked, carried on every later look, and logs it once; None
      on a day the cross-check was not needed (before: no such record)
  R4  the adapter logs a corrected execution ONCE per corrected execId, at WARNING, raw: execIds,
      shares, prices, commissions as seen (before: nothing)
TWINS - pass before and after:
  R1t what trades on R1's days: the same buys, sizes and limits as when the positions are current, sent
      in the first step at which the positions show the sales (never before, at most one poll after);
      every held look takes F alone; the account never borrows
  R2  (the safety review's test_a1c; a MUTATION PIN, not a regression gate: 1de7535c is right here) a
      withdrawal TotalCashValue shows before it shows the sells moves F - by $990 (more than the $400
      outside the book) or by 2 cents: F is then the truth, the buys are held for the session and the
      account never borrows. Mutant M7 (the "F has not moved" tolerance loosened from half a cent to
      $1,000) fails both - at $990 it borrows $343.90 - and a tolerance of 5 cents fails the 2-cent case
  R4t a correction's log never changes what _current_fills returns, and distinct executions log nothing
The flake the reviews found is fixed, with its gate, in tests/test_mirror_dividends_property.py.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import pytest

import app.ib_adapter as ib_mod
from app import mirror as mm
from test_ib_stock_adapter import FakeExec, FakeFill, ib_adapter  # noqa: F401  (the adapter fixture)
from test_mirror import Rig, payload

D2 = "2026-11-11"
ACCOUNT = 117_000.0
BOOK97 = round(0.97 * ACCOUNT, 2)                 # $3,510 of the account's cash is outside the book
ROT = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"PULS": 1.0}}
POLL = mm.ORDER_POLL_S
GRACE = getattr(mm, "BUYS_UNCONFIRMED_GRACE_S", 10.0)
UNCONFIRMED = "not yet confirmed by the account's positions; re-read every step"
WINDOW = ("15:56:40", "15:57:40", "15:58:30", "15:59:05", "15:59:40")


class Trail:
    """IB's view of the account on the Venue: TotalCashValue frozen at what it read when this is made (IB
    never catches up inside the window) and the position stream trailing every fill by `d` seconds.
    sells: the instants the sells filled; low: the least the account's TRUE cash ever was."""

    def __init__(self, r, d):
        v = r.venue
        self.r, self.d, self.value, self.low = r, float(d), v.cash, v.cash
        self.hist, self.sells = [(None, dict(v._positions))], []
        real_fill = v._fill

        def fill(rec, shares):
            real_fill(rec, shares)
            self.hist.append((r.clock.now, dict(v._positions)))
            self.low = min(self.low, v.cash)
            if rec["qty"] < 0:
                self.sells.append(r.clock.now)
        v._fill = fill
        v.account_cash = self.cash
        v.positions_snapshot = self.positions

    def cash(self):
        if not self.r.venue.cash_claim:
            return None
        return {"total_cash": self.value, "net_liq": None, "available_funds": self.value, "ts": time.time()}

    def positions(self):
        cut, pos = self.r.clock.now - timedelta(seconds=self.d), self.hist[0][1]
        for t, p in self.hist[1:]:
            if t <= cut:
                pos = p
        return {"stocks": {s: q for s, q in sorted(pos.items()) if q}, "other": []}


def day_one(tmp_path, book=BOOK97, report_commission=False):
    """day one seeded and traded at T1 (the rest of the account's cash outside the book); day two's
    rotation set and its 15:00 tick done; $1 commissions, reported late unless `report_commission`"""
    r = Rig(tmp_path, live=True, capital=book, venue_cash=ACCOUNT)
    r.tick("15:00")
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    r.tick("15:00", day=D2)
    r.venue.commission, r.venue.report_commission = 1.0, report_commission
    return r


def spies(r):
    """(sent, looks, alerts): every order that reaches the venue (symbol, qty, limit, instant), every
    look of the guard (instant, why, buy_cash), every alert (instant, text)"""
    sent, looks, alerts = [], [], []
    send, guard, alert = r.venue._send, r.m._buys_unfunded, r.m._alert

    def _send(symbol, qty, client_order_id, limit):
        sent.append((symbol, qty, limit, r.clock.now))
        return send(symbol, qty, client_order_id, limit)

    def _guard(ad, run):
        out = guard(ad, run)
        looks.append((r.clock.now, out, dict(run.get("buy_cash") or {})))
        return out

    def _alert(text):
        alerts.append((r.clock.now, text))
        return alert(text)
    r.venue._send, r.m._buys_unfunded, r.m._alert = _send, _guard, _alert
    return sent, looks, alerts


def trailing_day(tmp_path, d):
    """the rotation with IB's cash frozen and the positions `d` s behind the fills: one tick (the guard
    looks every ORDER_POLL_S inside it) and the rest of the window"""
    r = day_one(tmp_path)
    trail = Trail(r, d)
    sent, looks, alerts = spies(r)
    r.tick("15:55:05", day=D2)
    for hms in WINDOW:
        if r.m.state.get("run") is None:
            break
        r.tick(hms, day=D2)
    return r, trail, sent, looks, alerts


def buys(sent):
    return [(s, q, lim) for s, q, lim, _ in sent if q > 0]


@pytest.fixture(scope="module")
def current_buys(tmp_path_factory):
    """the rotation's buys when the positions show the sales at once (IB's cash still frozen)"""
    r, trail, sent, looks, alerts = trailing_day(tmp_path_factory.mktemp("current"), 0)
    out = buys(sent)
    assert {s for s, _, _ in out} == {"TQQQ", "SPY"} and trail.low >= 0
    assert len(looks) == 1 and looks[0][1] is None                   # bought at the first look
    return out


# ============================================================================== R1 / R1t
@pytest.mark.parametrize("d", [5, 30, 120])
def test_r1t_positions_that_trail_the_fills_cost_their_delay_and_nothing_else(tmp_path, d, current_buys):
    """TWIN: what trades is the same before and after"""
    r, trail, sent, looks, alerts = trailing_day(tmp_path, d)
    assert buys(sent) == current_buys, buys(sent)
    last_sell, first_buy = max(trail.sells), min(t for s, q, _, t in sent if q > 0)
    release = (first_buy - last_sell).total_seconds()
    assert d <= release <= d + POLL + 0.01, release                  # never before the positions show the sales
    held = [b for _, why, b in looks if why]
    assert held and all(b["cover"] == b["account"] == pytest.approx(trail.value, abs=0.005) for b in held)  # F alone
    assert all(b["positions"].startswith("the account's positions are not what the booked sells leave")
               for b in held)
    assert len([a for _, a in alerts if "covers the book's again" in a]) == 1
    assert not [a for _, a in alerts if "NO BUYS" in a]
    assert r.m.state["last_run"]["outcome"] == "traded" and trail.low >= -1e-6
    assert r.m.last_error is None and not (r.m.halt_state() or {}).get("halted")


@pytest.mark.parametrize("d", [5, 30, 120])
def test_r1_a_hold_for_positions_that_trail_is_a_warning_first_and_red_only_after_the_grace(tmp_path, d):
    r, trail, sent, looks, alerts = trailing_day(tmp_path, d)
    t0 = looks[0][0]                                                 # the first look: it held the buys
    assert looks[0][1]
    hold = [(t, a) for t, a in alerts if "BUYS are HELD" in a or "buys WAIT" in a]
    warn = [(t, a) for t, a in hold if a.startswith("⚠️")]
    red = [(t, a) for t, a in hold if a.startswith("\U0001f6a8")]
    assert len(warn) == 1 and warn[0][0] == t0, hold                 # said at once, as a warning ...
    assert f"the buys WAIT — the booked sells are {UNCONFIRMED}" in warn[0][1]
    assert "BIL: the sells leave 0, the account holds" in warn[0][1]    # ... naming what the positions show
    if d < GRACE:
        assert red == [], red                                        # ... and never red: it cleared first
    else:
        assert len(red) == 1, red                                    # ... red once, after the grace
        assert GRACE <= (red[0][0] - t0).total_seconds() <= GRACE + POLL + 0.01, (red[0][0], t0)
        assert "the BUYS are HELD — after" in red[0][1] and UNCONFIRMED in red[0][1]
        assert "no buys are sent this session" in red[0][1]
    assert len([a for _, a in alerts if "covers the book's again" in a]) == 1


@pytest.mark.parametrize("stamp,level", [(None, "warn"), (-5.0, "warn"), (-9.0, "warn"), (-10.0, "red"),
                                         (-60.0, "red"), ("not a time", "red"), (+30.0, "warn")])
def test_r1b_the_grace_runs_from_the_holds_first_look_and_a_damaged_stamp_has_none(tmp_path, stamp, level):
    """the grace is measured from run["buys_blocked_utc"] (the first look that held the buys; absent at
    that look itself); a stamp that cannot be read gets none; a clock behind the stamp is inside it"""
    r = Rig(tmp_path, live=True)
    now = r.clock.now
    run = {"session": D2, "cancel_utc": "2026-11-11T20:59:00Z"}
    if isinstance(stamp, float):
        run["buys_blocked_utc"] = mm._iso(now + timedelta(seconds=stamp))
    elif stamp is not None:
        run["buys_blocked_utc"] = stamp
    n = len(r.alerts)
    r.m._say_unconfirmed(run, "the account's positions are not what the booked sells leave (BIL: ...)",
                         4_450.5, 98_920.22, 96_511.5)
    (said,) = r.alerts[n:]
    assert said.startswith({"warn": "⚠️", "red": "\U0001f6a8"}[level]) and UNCONFIRMED in said, said
    assert "$92,061.00 short of the book's $96,511.50" in said and "($98,920.22) is not used" in said


# ============================================================================== R2: the "F has not moved" pin
@pytest.mark.parametrize("amount", [0.02, 990.0])
def test_r2_a_withdrawal_ib_shows_before_the_sells_moves_f_and_holds_the_buys(tmp_path, amount):
    """MUTATION PIN (passes on 1de7535c and after; fails on M7). $400 outside the book; `amount` is
    withdrawn after the pre-trade read (B) and before the first sell, and IB's TotalCashValue shows it
    then, and never the sells: F = B - amount has MOVED, so it is the truth - the buys are held for the
    session and the account never borrows. Under M7 both cases buy on the estimate, and at $990, with
    the buys filling at their limits, the account borrowed $343.90"""
    r = day_one(tmp_path, book=round(ACCOUNT - 400.0, 2), report_commission=True)
    trail = Trail(r, 0)
    b0, real_px = trail.value, r.venue._px
    r.venue._px = lambda rec: rec["limit"] if rec.get("limit") is not None else real_px(rec)  # buys fill AT their limit
    real, done = r.venue.place_stock_order, []

    def place(sym, qty, order_type, **kw):                           # after B was read, before the first sell
        if not done:
            done.append(1)
            r.venue.cash -= amount
            trail.low = min(trail.low, r.venue.cash)
            trail.value = r.venue.cash                               # IB shows the withdrawal ... not the sells
        return real(sym, qty, order_type, **kw)
    r.venue.place_stock_order = place
    sent, looks, alerts = spies(r)
    r.tick("15:55:05", day=D2)
    for hms in WINDOW + ("16:00:30",):
        r.tick(hms, day=D2)
    assert sorted(s for s, q, _, _ in sent if q < 0) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]
    assert trail.low >= -1e-6, f"the account borrowed ${-trail.low:,.2f} to fund {buys(sent)}"
    assert buys(sent) == [], buys(sent)
    assert looks and all(b["account"] == pytest.approx(b0 - amount, abs=0.005) and b["cover"] == b["account"]
                         and b.get("positions") is None for _, _, b in looks)                 # never cross-checked
    assert all("which has moved since the sells" in why for _, why, _ in looks)
    assert len([a for _, a in alerts if "NO BUYS are sent this session" in a]) == 1


# ============================================================================== R3: when the positions confirmed
@pytest.mark.parametrize("d", [0, 5, 30])
def test_r3_the_run_records_when_the_positions_first_confirmed_the_sells(tmp_path, d, caplog):
    caplog.set_level(logging.INFO, logger="app.mirror")
    r, trail, sent, looks, alerts = trailing_day(tmp_path, d)
    last_sell = max(trail.sells)
    for t, why, b in looks:
        assert "positions_confirmed_after_s" in b and "positions_confirmed_utc" in b, b
        if why:                                                      # held: not confirmed yet
            assert b["positions_confirmed_after_s"] is None and b["positions_confirmed_utc"] is None
    t, why, b = looks[-1]
    assert why is None and b["positions"] == "agree"
    assert b["positions_confirmed_utc"] == mm._iso(t)
    assert b["positions_confirmed_after_s"] == pytest.approx((t - last_sell).total_seconds(), abs=1.0)
    assert d <= b["positions_confirmed_after_s"] <= d + POLL + 0.01
    said = [x.getMessage() for x in caplog.records if "positions confirmed the booked sells" in x.getMessage()]
    assert len(said) == 1, said                                      # (day one sold nothing: not logged)
    assert f"{D2}: the account's positions confirmed the booked sells {b['positions_confirmed_after_s']:.1f} s " \
           f"after the last sell was booked" in said[0]


def test_r3_the_first_confirmation_is_kept_on_later_looks_and_none_when_f_had_moved(tmp_path):
    """the positions confirm at once but the estimate does not cover (the sells' commissions are
    unreported and the cash outside the book is under their bound): every later look keeps the first
    instant; a day whose TotalCashValue already moved records None (no cross-check was made)"""
    r = day_one(tmp_path, book=round(ACCOUNT - 60.0, 2))              # $60: under 5 x ($10 + 1.1% of a fill)
    trail = Trail(r, 0)
    sent, looks, alerts = spies(r)
    r.tick("15:55:05", day=D2)
    held = [(t, b) for t, why, b in looks if why]
    assert len(held) > 3 and all(b["positions"] == "agree" for _, b in held)
    first = held[0][1]["positions_confirmed_utc"]
    assert first == mm._iso(looks[0][0]) and held[0][1]["positions_confirmed_after_s"] == 0.0
    assert all(b["positions_confirmed_utc"] == first and b["positions_confirmed_after_s"] == 0.0 for _, b in held)
    r2 = day_one(tmp_path / "moved")                                  # the Venue's own cash: IB shows the fills
    _, looks2, _ = spies(r2)
    r2.tick("15:55:05", day=D2)
    assert len(looks2) == 1 and looks2[0][1] is None                  # bought on F, which has moved
    b = looks2[0][2]
    assert b.get("positions") is None and "positions_confirmed_utc" in b
    assert b["positions_confirmed_utc"] is None and b["positions_confirmed_after_s"] is None


# ============================================================================== R4 / R4t: the correction log
CID = "mirror-2026-11-11-S-BIL"


def _working_sell(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("BIL", -300, "MKT", client_order_id=CID)
    assert r["status"] == "working"
    return fake.trade_by_ref(r["order_ref"])


def _fill(trade, shares, price, exec_id, commission=1.0):
    ex = FakeExec(shares, price, "SLD")
    ex.orderRef, ex.orderId, ex.execId = trade.order.orderRef, trade.order.orderId, exec_id
    f = FakeFill(ex, commission)
    if f.commissionReport is not None:
        f.commissionReport.execId = exec_id
    trade.fills.append(f)
    return f


def _corrections(caplog):
    return [x for x in caplog.records if x.name == "app.ib_adapter" and x.levelno == logging.WARNING
            and "CORRECTED" in x.getMessage()]


def test_r4_a_corrected_execution_is_logged_once_raw(ib_adapter, monkeypatch, caplog):
    monkeypatch.setattr(ib_mod, "_CORRECTIONS_LOGGED", set(), raising=False)
    caplog.set_level(logging.WARNING, logger="app.ib_adapter")
    t = _working_sell(ib_adapter)
    _fill(t, 100, 91.50, "0000e0d5.6556c9aa.01.01", commission=1.0)
    late = _fill(t, 100, 91.40, "0000e0d5.6556c9aa.01.02", commission=None)    # its report has not come yet
    t.orderStatus.filled, t.orderStatus.status = 100, "Cancelled"
    for _ in range(3):                                               # polled again and again: said once
        got = ib_adapter.stock_order_fills(CID)
        assert got["filled_qty"] == 100 and got["avg_price"] == pytest.approx(91.40)
    ib_adapter.find_stock_order(CID)
    (one,) = _corrections(caplog)
    msg = one.getMessage()
    assert "'0000e0d5.6556c9aa.01.01' superseded by '0000e0d5.6556c9aa.01.02', which alone is counted" in msg
    assert "execId '0000e0d5.6556c9aa.01.01' SLD 100 @ 91.5, commission 1.0 USD" in msg
    assert "execId '0000e0d5.6556c9aa.01.02' SLD 100 @ 91.4, commission not reported yet" in msg
    late.commissionReport = FakeFill(FakeExec(100, 91.4, "SLD"), 1.25).commissionReport
    late.commissionReport.execId = "0000e0d5.6556c9aa.01.02"
    ib_adapter.stock_order_fills(CID)
    assert len(_corrections(caplog)) == 1                           # once per corrected execId
    _fill(t, 100, 91.45, "0000e0d5.6556c9aa.01.03", commission=1.5)  # corrected again: .02 is now corrected
    got = ib_adapter.stock_order_fills(CID)
    assert got["avg_price"] == pytest.approx(91.45)
    logs = _corrections(caplog)
    assert len(logs) == 2 and "'0000e0d5.6556c9aa.01.02' superseded by '0000e0d5.6556c9aa.01.03'" in logs[1].getMessage()
    assert "commission 1.25 USD" in logs[1].getMessage()             # the report that came since, as seen now


def test_r4t_the_log_never_changes_what_is_counted_and_distinct_executions_log_nothing(ib_adapter, monkeypatch,
                                                                                      caplog):
    """TWIN: the same results with the log working, and with it raising"""
    monkeypatch.setattr(ib_mod, "_CORRECTIONS_LOGGED", set(), raising=False)
    caplog.set_level(logging.WARNING, logger="app.ib_adapter")
    t = _working_sell(ib_adapter)
    _fill(t, 100, 91.50, "0000e0d5.6556c9bb.01.01")
    _fill(t, 100, 91.40, "0000e0d5.6556c9bc.01.01")                  # another execution, not a correction
    _fill(t, 30, 91.30, "e7")
    _fill(t, 20, 91.30, "")
    t.orderStatus.filled, t.orderStatus.status = 250, "Cancelled"
    got = ib_adapter.stock_order_fills(CID)
    assert got["filled_qty"] == 250 and _corrections(caplog) == []
    _fill(t, 100, 91.35, "0000e0d5.6556c9bb.01.02")                  # now a correction of the first
    want = ib_adapter.stock_order_fills(CID)
    assert want["filled_qty"] == 250                                 # the correction replaces, never adds
    assert want["avg_price"] == pytest.approx((100 * 91.35 + 100 * 91.40 + 50 * 91.30) / 250)

    def broken(*a, **k):
        raise RuntimeError("the log is broken")
    monkeypatch.setattr(ib_mod, "_log_corrections", broken, raising=False)
    monkeypatch.setattr(ib_mod, "_CORRECTIONS_LOGGED", set(), raising=False)
    assert ib_adapter.stock_order_fills(CID) == want
    assert ib_mod._current_fills(t.fills) == [f for f in t.fills if f.execution.execId != "0000e0d5.6556c9bb.01.01"]
