"""C-52, fourth pass (2026-11-13): what the round-4 review of the buying guard found (FIX-THEN-SHIP: four
MINOR errors in the risk text, and NOTEs). What trades does not change - the twins hold the orders, sizes
and the account to what 170191c0 sent - except G1: a damaged buy_cash record no longer stops the buys.

The account model is the round-4 verifier's (Acct): the account's TRUE cash and positions are the Venue's;
IB's TotalCashValue (F) reads what it read when Acct is made, until `show_at`; the positions show each
change `delay` s after it happened (the run's own fills: Acct.d; a trade by hand or a bust: its own).

GATES - each FAILS on 170191c0 and passes after:
  G1  (NOTE 5, the verifier's V9) a run whose buy_cash is not a dict, as a damaged state file would carry
      it: the guard never raises and the buys go at the first look, as with no damage (before: an
      AttributeError at every look, no buys, and the note "the window closed before the sells were booked")
  G2  (NOTE 7, V4) a hold first said in red (the positions agree, the estimate is short) that later turns
      into "not yet confirmed": no warning after the red (before: a warning promising a red that never came)
  G3  (NOTE 6) a disagreement reading the positions again cannot change - no record of them from before the
      run, a record that cannot be read, a holding that is not a whole stock lot - is said in red at the
      first look, never as a wait (before: a warning, and red only after the grace)
  G4  (NOTE 6, V2) the wait's warning names both causes, "IB's lag, or a real difference" (before: it put
      the difference down to TotalCashValue's "update lag")
  D1  (MINOR 1) a bust is not exposure (3): it moves a position, closed once IB reports it, (2)'s exposure
      before that; "measured" only for what the safety review measured (price corrections)
  D2  (MINOR 2) (3) is new with this guard: the rule before never borrowed on it; the comparison kept for
      (1) and (2)
  D3  (MINOR 3) a reported trade by hand: TotalCashValue alone, waited for only on a day the sells exceed
      the cash outside the book; on any other day it is (2)'s exposure, and the post-trade check halts
  D4  (MINOR 4) positions_confirmed_after_s: recorded only while TotalCashValue had not moved at that look;
      an upper bound on how far the positions trailed the last sell's booking, to a 1.5 s step
  D5  (NOTE 8) "the buys wait" only on a day the sells exceed the cash outside the book
  D6  (NOTE 9) the commission bound "may not hold for a large order of a name under about $3.40 a share"
  D7  (NOTE 10) the proof: a withdrawal is outside (A1) or (A3)
  D8  (NOTE 6) the doc says the warning's words and the red at once
TWINS - pass on 170191c0 and after (what trades, and the risk text's claims, measured):
  T1  (V5) exposure (3), a price correction after booking: C-52 borrows only on a day the sells exceed the
      cash outside the book and only by more than it; the F-alone rule before it never does
  T2  (V6) a hand purchase IB HAS reported, TotalCashValue lagging: a $50k day buys at the first look on
      the stale TotalCashValue and borrows, then the post-trade check halts; a 97% day waits all window
  T3  (V7, and the $50k day) a bust of a sell after booking: once reported, TotalCashValue alone, and the
      post-trade check halts on the shares; never reported, C-52 borrows on a 97% day only; the rule before
      never borrows, and nothing borrows on a day the sells fit in the cash outside the book
  T4  what trades on G2, G3 and G4's days: the same orders, the account never borrows
"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

import test_mirror as tm
from app import mirror as mm
from test_mirror import PX, Rig, payload

D2 = "2026-11-11"
ACCOUNT = 117_000.0
BOOK97 = round(0.97 * ACCOUNT, 2)                 # $3,510 of the account's cash is outside the book
ROT = {"HG": {"TQQQ": 1.0}, "KMLM": {"SPY": 1.0}, "SLEEVE": {"TQQQ": 1.0}, "HARV": {"PULS": 1.0}}
WINDOW = ("15:56:40", "15:57:40", "15:58:30", "15:59:05", "15:59:40", "16:00:30")
AFTER = ("16:01:10", "16:01:45", "16:02:20", "16:03:00")
RED, WARN = "\U0001f6a8", "⚠️"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC_PATH = os.path.join(REPO, "composer", "IBKR_MIRROR.md")


class Acct:
    """the round-4 verifier's account model (tests/test_mirror_buyguard_r5's docstring)"""

    def __init__(self, r, d=0.0):
        v = r.venue
        self.r, self.d = r, float(d)
        self.F, self.show_at, self.low = v.cash, None, v.cash
        self.base = dict(v._positions)
        self.upd, self.last_vis, self.other = [], {}, []
        real_fill = v._fill

        def fill(rec, shares):
            real_fill(rec, shares)
            self.note(rec["symbol"], self.d)
        v._fill = fill
        v.account_cash = self.cash
        v.positions_snapshot = self.positions

    def note(self, sym=None, delay=0.0):
        v, now = self.r.venue, self.r.clock.now
        self.low = min(self.low, v.cash)
        if sym is not None:
            vis = max(now + timedelta(seconds=delay), self.last_vis.get(sym, now - timedelta(days=9)))
            self.last_vis[sym] = vis
            self.upd.append((vis, sym, v._positions.get(sym, 0)))

    def cash(self):
        v = self.r.venue
        if not v.cash_claim:
            return None
        c = v.cash if (self.show_at is not None and self.r.clock.now >= self.show_at) else self.F
        return {"total_cash": c, "net_liq": None, "available_funds": c, "ts": 0.0}

    def positions(self):
        now, view = self.r.clock.now, dict(self.base)
        for vis, s, q in self.upd:
            if vis <= now:
                view[s] = q
        return {"stocks": {k: q for k, q in sorted(view.items()) if q}, "other": list(self.other)}

    def hand(self, sym, qty, px, delay=0.0):
        """a trade by hand: `qty` shares of `sym` at `px` (+ $1)"""
        v = self.r.venue
        v._positions[sym] = v._positions.get(sym, 0) + qty
        v.cash -= qty * px + 1.0
        self.note(sym, delay)

    def bust(self, sym, shares, px, delay=0.0):
        """a sale of `shares` at `px` the venue BUSTS after it was booked: the shares come back, the
        proceeds go"""
        v = self.r.venue
        v._positions[sym] = v._positions.get(sym, 0) + shares
        v.cash -= shares * px
        self.note(sym, delay)


def day_one(tmp_path, book=BOOK97, report_commission=True):
    """day one seeded and traded at T1 (the rest of the account's cash outside the book); day two's
    rotation set and its 15:00 tick done; $1 commissions"""
    r = Rig(tmp_path, live=True, capital=book, venue_cash=ACCOUNT)
    r.tick("15:00")
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded"
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    r.tick("15:00", day=D2)
    r.venue.commission, r.venue.report_commission = 1.0, report_commission
    return r


def spies(r):
    """(sent, looks, alerts): every order that reaches the venue (symbol, qty, limit, instant), every look
    of the guard (instant, why, buy_cash), every alert (instant, text)"""
    sent, looks, alerts = [], [], []
    send, guard, alert = r.venue._send, r.m._buys_unfunded, r.m._alert

    def _send(symbol, qty, cid, limit):
        sent.append((symbol, qty, limit, r.clock.now))
        return send(symbol, qty, cid, limit)

    def _guard(ad, run):
        out = guard(ad, run)
        rec = run.get("buy_cash")
        looks.append((r.clock.now, out, dict(rec) if isinstance(rec, dict) else rec))
        return out

    def _alert(text):
        alerts.append((r.clock.now, text))
        return alert(text)
    r.venue._send, r.m._buys_unfunded, r.m._alert = _send, _guard, _alert
    return sent, looks, alerts


def at_first_look(r, fn):
    """fn(run) once, at the guard's first look, before it reads anything"""
    inner, done = r.m._buys_unfunded, []

    def g(ad, run):
        if not done:
            done.append(1)
            fn(run)
        return inner(ad, run)
    r.m._buys_unfunded = g


def overbook(r, symbol, short):
    """the venue answers FILLED for the whole sell of `symbol` while `short` fewer shares executed"""
    v = r.venue
    real = v._fill

    def fill(rec, shares):
        if rec["symbol"] == symbol and rec["qty"] < 0:
            real(rec, shares - short)
            rec["filled_qty"], rec["status"] = abs(rec["qty"]), "filled"
            return
        real(rec, shares)
    v._fill = fill


def run_window(r, times=WINDOW + AFTER):
    """the service loop's later ticks - never moving the clock BACK (a live tick drives up to 150 s)"""
    for hms in times:
        if tm.at(hms, D2) <= r.clock.now:
            continue
        r.tick(hms, day=D2)


def buys(sent):
    return [(s, q, lim) for s, q, lim, _ in sent if q > 0]


def holds(alerts):
    return [(t, x) for t, x in alerts if "BUYS are HELD" in x or "buys WAIT" in x]


def rel(t, t0):
    return round((t - t0).total_seconds(), 2)


def f_alone(monkeypatch):
    """the rule before C-52: TotalCashValue alone"""
    monkeypatch.setattr(mm.MirrorManager, "_cash_cover",
                        lambda self, run, have, ad=None: (have, None, "its TotalCashValue (the rule before)", None))


# ============================================================================== G1: a damaged buy_cash record
@pytest.mark.parametrize("damaged", [["not", "a", "dict"], "a string", 42])
def test_g1_a_buy_cash_record_that_is_not_a_dict_never_stops_the_guard(tmp_path, damaged):
    """the verifier's V9: at 170191c0 `prev = run.get("buy_cash") or {}` raised on every look - no buys,
    a 'tick failed' red, and a note saying the sells were not booked (they were)"""
    clean = day_one(tmp_path / "clean")
    Acct(clean)
    want, _, _ = spies(clean)
    clean.tick("15:55:05", day=D2)
    assert buys(want), "the twin day buys at the first look"

    r = day_one(tmp_path / "damaged")
    a = Acct(r)
    sent, looks, alerts = spies(r)
    raised = []
    inner = r.m._buys_unfunded

    def g(ad, run):
        if not raised and not looks:
            run["buy_cash"] = damaged                          # as a damaged state file would carry it
        try:
            return inner(ad, run)
        except Exception as exc:  # noqa: BLE001
            raised.append(repr(exc))
            raise
    r.m._buys_unfunded = g
    r.tick("15:55:05", day=D2)
    run_window(r, WINDOW)
    assert raised == [], raised
    assert buys(sent) == buys(want), (buys(sent), buys(want))  # the same buys as with no damage, at the first look
    assert looks[0][1] is None and isinstance(looks[0][2], dict) and "positions_confirmed_utc" in looks[0][2]
    assert not [x for _, x in alerts if "tick failed" in x], alerts
    notes = (r.m.state.get("last_run") or {}).get("notes") or []
    assert not [n for n in notes if "buys NOT sent" in n], notes
    assert r.m.state["last_run"]["outcome"] == "traded" and a.low >= -1.0


def test_g1_the_record_reader_reads_a_damaged_record_as_none(tmp_path):
    r = Rig(tmp_path, live=True)
    run = {"session": D2, "plan": {"sells": []}, "orders": {}}
    for damaged in (["x"], "x", 7, 1.5, True):
        run["buy_cash"] = damaged
        assert r.m._positions_confirmed(run, "not agree") == {"positions_confirmed_utc": None,
                                                              "positions_confirmed_after_s": None}
        got = r.m._positions_confirmed(run, "agree")
        assert set(got) == {"positions_confirmed_utc", "positions_confirmed_after_s"}
        assert got["positions_confirmed_utc"] == mm._iso(r.clock.now) and got["positions_confirmed_after_s"] is None


# ============================================================================== G2: no warning after a red
def _red_then_unconfirmed(tmp_path):
    """$60 outside the book (under five unreported commissions' bound): the positions agree but the
    estimate does not cover - a generic red at the first look. At the third look a trade by hand (AAPL +1)
    shows in the positions: the hold is now 'not yet confirmed' (the verifier's V4)"""
    r = day_one(tmp_path, book=round(ACCOUNT - 60.0, 2), report_commission=False)
    a = Acct(r)
    sent, looks, alerts = spies(r)
    inner, k = r.m._buys_unfunded, {"n": 0}

    def g(ad, run):
        k["n"] += 1
        if k["n"] == 3:
            a.hand("AAPL", 1, 230.0)
        return inner(ad, run)
    r.m._buys_unfunded = g
    r.tick("15:55:05", day=D2)
    run_window(r, WINDOW)
    return r, a, sent, looks, alerts


def test_g2_a_hold_said_in_red_gets_no_warning_after_it(tmp_path):
    r, a, sent, looks, alerts = _red_then_unconfirmed(tmp_path)
    held = [x for x in looks if x[1]]
    t0 = held[0][0]
    assert held[0][2]["positions"] == "agree" and held[-1][2]["positions"].startswith(
        "the account's positions are not what the booked sells leave (AAPL")          # it did turn
    h = [(rel(t, t0), x[:1], "WAIT" if "buys WAIT" in x else "HELD") for t, x in holds(alerts)]
    assert h == [(0.0, RED[:1], "HELD")], h                  # before: + (3.0, warn, WAIT), a red promised that never came


# ============================================================================== G3: red at once when re-reading cannot change it
def _final_day(tmp_path, kind):
    r = day_one(tmp_path)
    a = Acct(r)                                              # IB's TotalCashValue frozen: a 97% day holds on F alone
    sent, looks, alerts = spies(r)

    def damage(run):
        if kind == "no_pos0":
            run.pop("pos0", None)                            # a run from before its pos0 was recorded
        elif kind == "unreadable_record":
            run["pos0"] = dict(run["pos0"], BIL="a hundred")
        else:
            a.other.append("OPT SPY 1")                      # the account holds an option
    at_first_look(r, damage)
    r.tick("15:55:05", day=D2)
    run_window(r)
    return r, a, sent, looks, alerts


FINAL = {"no_pos0": "this run has no record of the account's positions before its sells",
         "unreadable_record": "this run's record of its positions cannot be read (",
         "not_stock": "the account holds what is not a whole stock lot: OPT SPY 1"}


@pytest.mark.parametrize("kind", sorted(FINAL))
def test_g3_a_disagreement_reading_again_cannot_change_is_red_at_the_first_look(tmp_path, kind):
    r, a, sent, looks, alerts = _final_day(tmp_path, kind)
    held = [x for x in looks if x[1]]
    t0 = held[0][0]
    assert all(FINAL[kind] in b["positions"] for _, _, b in held)
    h = holds(alerts)
    assert not [x for _, x in h if "buys WAIT" in x], h      # never said as a wait ...
    assert len(h) == 1 and h[0][0] == t0 and h[0][1].startswith(RED), h      # ... red at the first look, once
    assert "the BUYS are HELD — the book's cash" in h[0][1] and FINAL[kind] in h[0][1]


def test_g3_the_classification_is_by_the_reasons_own_words(tmp_path):
    """the reasons reading again cannot change are _sells_confirmed's own (the constants it returns); a
    positions read that fails, or positions that differ, are not among them (they may change: the grace)"""
    r = Rig(tmp_path, live=True)
    assert r.m._sells_confirmed({"plan": {"sells": []}}, None) == (False, mm.UNCONFIRMED_NO_POS0)
    ok, why = r.m._sells_confirmed({"pos0": {"BIL": "x"}, "plan": {"sells": []}}, None)
    assert not ok and why.startswith(mm.UNCONFIRMED_NO_RECORD + " (")

    class Ad:
        def __init__(self, snap):
            self.snap = snap

        def positions_snapshot(self):
            if isinstance(self.snap, Exception):
                raise self.snap
            return self.snap
    run = {"pos0": {"BIL": 10}, "plan": {"sells": []}}
    ok, why = r.m._sells_confirmed(run, Ad({"stocks": {"BIL": 10}, "other": ["FUT ES 1"]}))
    assert not ok and why == mm.UNCONFIRMED_NOT_STOCK + ": FUT ES 1"
    for snap in (TimeoutError("slow"), {"stocks": {"BIL": 9}, "other": []}):
        ok, why = r.m._sells_confirmed(run, Ad(snap))
        assert not ok and not why.startswith(mm.UNCONFIRMED_FINAL), why


# ============================================================================== G4: the warning's words
def _real_difference_that_clears(tmp_path):
    """the verifier's V2: 10 BIL over-booked ($915, under the $3,510 outside the book); IB's TotalCashValue
    catches up 4.5 s after the first look"""
    r = day_one(tmp_path)
    a = Acct(r)
    overbook(r, "BIL", 10)
    sent, looks, alerts = spies(r)
    at_first_look(r, lambda run: setattr(a, "show_at", r.clock.now + timedelta(seconds=4.5)))
    r.tick("15:55:05", day=D2)
    run_window(r)
    return r, a, sent, looks, alerts


def test_g4_the_wait_is_said_as_ibs_lag_or_a_real_difference(tmp_path):
    r, a, sent, looks, alerts = _real_difference_that_clears(tmp_path)
    (w,) = [x for _, x in holds(alerts)]
    assert w.startswith(WARN) and "the buys WAIT — the booked sells are not yet confirmed by the account's " \
                                  "positions; re-read every step" in w
    assert "(BIL: the sells leave 0, the account holds 10) (IB's lag, or a real difference). IB's TotalCashValue " \
           "still reads $4,450.50, as before the sells: $" in w, w
    assert "update lag" not in w


# ============================================================================== D1-D8: the risk text
def flat(text):
    return " ".join((text or "").split())


KNOWN = flat(mm.__doc__)
PROOF = flat(mm.MirrorManager._cash_cover.__doc__)
RECORD = flat(mm.MirrorManager._positions_confirmed.__doc__)


@pytest.fixture(scope="module")
def guard_doc():
    """IBKR_MIRROR.md's two guard paragraphs, from "Live only: seeding" to "GET /mirror/feed" """
    if not os.path.isfile(DOC_PATH):
        pytest.skip("composer/IBKR_MIRROR.md is not in this checkout")
    text = flat(open(DOC_PATH).read())
    return text.split("- Live only: seeding never totals")[1].split("- GET /mirror/feed")[0]


def test_d1_a_bust_is_not_exposure_3_and_measured_is_what_was_measured(guard_doc):
    for where, text in (("KNOWN LIMITS", KNOWN), ("the proof", PROOF), ("IBKR_MIRROR.md", guard_doc)):
        assert "or bust" not in text, where
        assert "each measured by the 2026-11-13 safety review" not in text, where
    assert "(measured by the 2026-11-13 safety review)" not in KNOWN
    assert "3 a price correction of a sell after it was booked: up to its size beyond that cash" in KNOWN
    assert ("(the 2026-11-13 safety review measured 1, 2 and, of 3, corrections of the price)" in KNOWN)
    assert ("A bust of a sell moves a position (its shares come back): it is closed once IB reports that position "
            "(the guard takes TotalCashValue alone; the post-trade check halts on the shares); before that it is 2's "
            "exposure") in KNOWN
    assert "(no correction of a sell's price arrives after it was booked)" in PROOF        # (A2)
    assert "the 2026-11-13 safety review measured the first two and, of the third, corrections of the price" in PROOF
    assert "outside (A2), a price correction of a sell after it was booked - up to its size beyond that cash" in PROOF
    assert ("A bust of a sell moves a position (its shares come back): once IB reports it, P differs and L = F (the "
            "post-trade check then halts on the shares); before that it is outside (A5)") in PROOF
    assert "(3) a price correction of a sell after it was booked - up to its size beyond that cash" in guard_doc
    assert "The 2026-11-13 safety review measured (1), (2) and, of (3), corrections of the price." in guard_doc
    assert ("A bust of a sell moves a position (its shares come back): it is closed once IB reports that position "
            "(the guard takes TotalCashValue alone; the post-trade check halts on the shares); before that it is (2)'s "
            "exposure") in guard_doc
    # round 6 (the round-5 review's NOTE): the operating rule covers withdrawals and trades by hand, not IB's busts
    for where, text in (("KNOWN LIMITS", KNOWN), ("IBKR_MIRROR.md", guard_doc)):
        assert ("Nothing closes a bust before IB reports it, by the guard's first look (in the step the sells are "
                "booked): the operating rule covers withdrawals and trades by hand, not IB's busts.") in text, where
    assert ("nothing closes a bust before IB reports it, by the first look (the operating rule below covers "
            "withdrawals and trades by hand, not IB's busts)") in PROOF


def test_d2_exposure_3_is_new_with_this_guard_and_the_comparison_stays_for_1_and_2(guard_doc):
    assert ("For 1 and 2, the rule before this held such a day's buys until IB caught up only on a day the sells "
            "exceeded the account's cash outside the book. 3 is new with this guard: the rule before never borrowed "
            "on it, and it can happen only on a day the sells exceed the cash outside the book") in KNOWN
    assert ("The first two the rule before this caught only on a day the sells exceeded the account's cash outside "
            "the book") in PROOF
    assert ("The third is new with this guard: a correction is at most the day's sells, so the rule before never "
            "borrowed on it, and it can happen only on a day the sells exceed the cash outside the book.") in PROOF
    assert ("For (1) and (2), the rule before this held such a day's buys until IB caught up only when the day's "
            "sells exceeded the cash outside the book. (3) is new with this guard: the rule before never borrowed on "
            "it (a correction is at most the day's sells), and it can happen only on a day the sells exceed the cash "
            "outside the book.") in guard_doc
    assert "up to its size beyond that cash. The rule before this held such a day's buys" not in guard_doc


def test_d3_a_reported_trade_by_hand_is_waited_for_only_on_a_big_sells_day(guard_doc):
    for where, text, two in (("KNOWN LIMITS", KNOWN, "2's"), ("IBKR_MIRROR.md", guard_doc, "(2)'s")):
        assert ("moves a position once IB has reported its position: the guard then takes TotalCashValue alone and "
                "waits for it only on a day the sells exceed the cash outside the book; on any other day a purchase "
                f"TotalCashValue does not yet show is {two} exposure, as under the rule before, and the post-trade "
                "check then halts the book") in text, where
    assert "the guard then waits for TotalCashValue" not in guard_doc


def test_d4_the_positions_record_is_described_as_what_it_measures(guard_doc):
    assert ("The run's buy_cash.positions_confirmed_after_s records it - the seconds from the last sell's booking, to "
            "the second, to the first look at which the positions agree: an upper bound on how far they trailed that "
            "booking, to a 1.5 s step - only when TotalCashValue had not yet moved at that look (None otherwise, "
            "nothing logged)") in guard_doc
    assert "until the first live rotation, which records it" not in guard_doc
    assert "recorded only when TotalCashValue had not moved at that look (None otherwise, and nothing logged" in RECORD
    assert "an upper bound on how far the positions trailed that booking, to an ORDER_POLL_S step" in RECORD
    assert "(the instant this book saw its fill, to the second)" in RECORD
    assert mm.ORDER_POLL_S == 1.5


def test_d5_the_buys_wait_only_on_a_day_the_sells_exceed_the_cash_outside_the_book(guard_doc):
    assert ("gets the rule before too: on a day the sells it does not show yet exceed the cash outside the book, the "
            "buys wait for IB's next update") in guard_doc
    assert ("While TotalCashValue lags, on a day the sells exceed the cash outside the book, the buys wait as long as "
            "the positions trail the fills") in guard_doc
    assert "On any other day TotalCashValue alone covers the book and the buys go at the first look." in guard_doc
    assert "gets the rule before too: the buys wait" not in guard_doc
    assert "While TotalCashValue lags, the buys wait" not in guard_doc
    assert ("for as long as it lags: on a day the sells exceed the account's cash outside the book they wait that "
            "long") in PROOF
    assert "on any other day F alone covers the book and they go at the first look" in PROOF
    assert ("On a day the sells exceed the cash outside the book, a P that trails the sales holds them until the first "
            "step at which it shows them") in PROOF
    assert "for as long as it lags: they wait that long" not in PROOF


def test_d6_the_commission_bound_may_not_hold_for_a_large_order_under_3_40(guard_doc):
    for where, text in (("KNOWN LIMITS", KNOWN), ("IBKR_MIRROR.md", guard_doc)):
        assert ("it may not hold for a large order of a name under about $3.40 a share, and does not on another "
                "pricing plan") in text, where
        assert "it does not hold for a name under about $3.40" not in text, where


def test_d7_a_withdrawal_is_outside_a1_or_a3():
    assert "outside (A1) or (A3), cash that leaves with no position moving" in PROOF
    assert "outside (A3), cash that leaves with no position moving" not in PROOF


def test_d8_the_doc_says_the_warnings_words_and_the_red_at_once(guard_doc):
    """round 6 (the round-5 review's NOTE): all three red-at-once reasons (an unreadable record too, as the code
    says: UNCONFIRMED_NO_RECORD), 'not expected to change' (a non-stock lot can go away on a later look), and the
    no-warning-after-a-red rule is per process (self._said), but the hold's start is on disk (run.buys_blocked_utc):
    a new process warns once more only when its first look comes within the 10 s grace (the final cross-patch
    review; tests/test_mirror_final.py pins both cases)"""
    assert ('as a warning ("not yet confirmed by the account\'s positions; re-read every step": IB\'s lag, or a real '
            'difference) and in red only once it has lasted 10 s; a disagreement reading the positions again is not '
            'expected to change (no record of them from before the run, a record of them that cannot be read, a '
            'holding that is not a whole stock lot) in red at once, and no warning follows a red this process already '
            "sent (the hold's start, run.buys_blocked_utc, is kept on disk: after a restart, a new process whose "
            "first look comes within 10 s of it warns once more, then its red comes; later, its first look is red at "
            "once, as after any real restart)") in guard_doc
    assert "after a restart the new process warns once more, then its red comes)" not in guard_doc
    assert "no warning follows a red already sent" not in guard_doc


# ============================================================================== T1: exposure (3), measured
@pytest.mark.parametrize("rule", ["c52", "f_alone"])
@pytest.mark.parametrize("case", ["97pct_drop6pct", "97pct_drop2pct", "50k_drop100pct"])
def test_t1_a_price_correction_after_booking(tmp_path, monkeypatch, rule, case):
    """TWIN (the verifier's V5). 97%: $3,510 outside the book; a 6% correction of every sell ($5,734.26)
    borrows on C-52, a 2% one ($1,911.42) does not; $50k: $67,000 outside, a 100% correction of every sell
    ($42,063.50) does not. The F-alone rule before C-52 never borrows"""
    book, drop = {"97pct_drop6pct": (BOOK97, 0.06), "97pct_drop2pct": (BOOK97, 0.02),
                  "50k_drop100pct": (50_000.0, 1.0)}[case]
    r = day_one(tmp_path, book=book)
    if rule == "f_alone":
        f_alone(monkeypatch)
    a = Acct(r)
    sent, looks, alerts = spies(r)
    corr = {}

    def correct(run):
        for rec in r.venue._orders.values():
            if rec["qty"] < 0 and rec.get("filled_qty") and rec["client_order_id"].startswith(f"mirror-{D2}"):
                c = rec["filled_qty"] * rec["fill_price"] * drop
                corr[rec["symbol"]] = round(c, 2)
                r.venue.cash -= c
        a.note()
    at_first_look(r, correct)
    r.tick("15:55:05", day=D2)
    run_window(r)
    assert corr and bool(buys(sent)) == (not (rule == "f_alone" and book == BOOK97))   # F alone holds a 97% day
    if rule == "f_alone" or case != "97pct_drop6pct":
        assert a.low >= -1.0, (rule, case, a.low)
    else:
        assert a.low < -1_000.0, a.low                        # C-52 borrows c - outside; the rule before never did


# ============================================================================== T2: a hand purchase IB has reported
@pytest.mark.parametrize("book", [50_000.0, BOOK97])
def test_t2_a_reported_hand_purchase_with_total_cash_value_lagging(tmp_path, book):
    """TWIN (the verifier's V6): the positions show the purchase at once (IB has reported it),
    TotalCashValue does not. The guard takes F alone; it waits for it only on a 97% day"""
    r = day_one(tmp_path, book=book)
    a = Acct(r)
    sent, looks, alerts = spies(r)
    qty = 125 if book == 50_000.0 else 33                      # $75,000 (outside $67,000) / $19,800 (outside $3,510)
    at_first_look(r, lambda run: a.hand("SPY", qty, PX["SPY"]))
    r.tick("15:55:05", day=D2)
    run_window(r)
    first = looks[0][2]
    assert first["cover"] == first["account"] and "SPY" in (first.get("positions") or "")     # F alone
    mism = [x for _, x in alerts if "does NOT hold the mirror book" in x]
    if book == 50_000.0:
        assert buys(sent) and looks[0][1] is None             # bought at the first look, on the stale F ...
        assert a.low < -5_000.0, a.low                        # ... and borrowed: (2)'s exposure, as before C-52
    else:
        assert buys(sent) == [] and a.low >= -1.0             # a day whose sells exceed the outside: it waits
    assert mism and r.m.halt_state().get("halted")            # the post-trade check then halts the book


# ============================================================================== T3: a bust after booking
@pytest.mark.parametrize("rule", ["c52", "f_alone"])
@pytest.mark.parametrize("book,reported", [(BOOK97, True), (BOOK97, False), (50_000.0, True), (50_000.0, False)])
def test_t3_a_bust_of_a_sell_after_booking(tmp_path, monkeypatch, book, reported, rule):
    """TWIN (the verifier's V7, with the $50k day and the rule before). The BIL sale is busted after it
    was booked: its shares come back, its proceeds go. Reported as a position at once, or never"""
    r = day_one(tmp_path, book=book)
    if rule == "f_alone":
        f_alone(monkeypatch)
    a = Acct(r)
    sent, looks, alerts = spies(r)
    got = {}

    def bust(run):
        rec = next(x for x in r.venue._orders.values()
                   if x["symbol"] == "BIL" and x["qty"] < 0 and x["client_order_id"].startswith(f"mirror-{D2}"))
        got["value"] = rec["filled_qty"] * rec["fill_price"]
        a.bust("BIL", rec["filled_qty"], rec["fill_price"], 0.0 if reported else 1e6)
    at_first_look(r, bust)
    r.tick("15:55:05", day=D2)
    run_window(r)
    mism = [x for _, x in alerts if "does NOT hold the mirror book" in x]
    borrows = a.low < -1.0
    assert borrows == (rule == "c52" and book == BOOK97 and not reported), (a.low, got)
    if borrows:
        assert buys(sent) and a.low < -20_000.0               # E is used, nothing shows the bust
    if reported:
        assert mism and r.m.halt_state().get("halted")        # the post-trade check halts on the shares
        if rule == "c52":
            assert "BIL" in (looks[0][2].get("positions") or "") and looks[0][2]["cover"] == looks[0][2]["account"]
    else:
        assert not mism                                       # never reported: the post-trade check sees nothing
    assert bool(buys(sent)) == (book == 50_000.0 or borrows)   # a 97% day on F alone holds the buys all window


# ============================================================================== T4: what trades on G2-G4's days
def test_t4_the_red_then_unconfirmed_day_trades_as_before(tmp_path):
    r, a, sent, looks, alerts = _red_then_unconfirmed(tmp_path)
    assert buys(sent) == [] and a.low >= -1.0
    assert len([x for _, x in alerts if "NO BUYS are sent this session" in x]) == 1
    assert sorted(s for s, q, _, _ in sent if q < 0) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]


@pytest.mark.parametrize("kind", sorted(FINAL))
def test_t4_the_days_a_disagreement_cannot_change_trade_as_before(tmp_path, kind):
    r, a, sent, looks, alerts = _final_day(tmp_path, kind)
    assert buys(sent) == [] and a.low >= -1.0
    assert sorted(s for s, q, _, _ in sent if q < 0) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]
    assert all(b["cover"] == b["account"] for _, why, b in looks if why)      # F alone at every held look
    assert len([x for _, x in alerts if "NO BUYS are sent this session" in x]) == 1


def test_t4_the_real_difference_that_clears_trades_as_before(tmp_path):
    r, a, sent, looks, alerts = _real_difference_that_clears(tmp_path)
    t0 = [x for x in looks if x[1]][0][0]
    first_buy = min(t for s, q, _, t in sent if q > 0)
    assert rel(first_buy, t0) == 4.5 and a.low >= -1e-6
    funded = [(t, x) for t, x in alerts if "covers the book's again" in x]
    assert len(funded) == 1 and rel(funded[0][0], t0) == 4.5
    mism = [x for _, x in alerts if "does NOT hold the mirror book" in x]
    assert mism and mism[0].startswith(RED) and "BIL" in mism[0] and r.m.halt_state().get("halted")
