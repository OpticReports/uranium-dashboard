"""Exhaustive gates for the Composer mirror, ported from the adversarial review (reviewer A's
test_s01 / test_s02 / test_s03, which passed on the reviewed commit and must keep passing):

  S01  a crash at EVERY save and EVERY venue call of a session - a rotation with a cross and a
       transfer, credits, a dividend and a split, a window-end cancel with a partial, a flatten (with
       a second round), a halt mid-run, operator repairs - each followed by a restart, never sends an
       id twice, never books an order twice, and always ends with the book equal to the account
       (shares and cash). Where the fills do not depend on WHEN the restart happened, the restarted
       book is the uncrashed one sleeve by sleeve.
  S02  the core over thousands of random sessions (transfers planned, partial and refused; crosses;
       partial and zero fills; a threshold sleeve): no call raises; shares and cash conserve; crosses
       and transfers are zero-sum; never a SELL and a BUY of one symbol at the venue; and - WIDENED
       from the review's version, which only filled inside the old 0.3% cushion - with buys filling
       ANYWHERE at or under their limit the book never spends cash it does not have.
  S03  the paper book restarted at every save ends as the uncrashed paper book does.

The default run is bounded (every crash point, 400 x 10 fuzz sessions: a few seconds); set
MIRROR_SWEEP_FULL=1 for the long fuzz (4,000 x 10 sessions per case).
"""
from __future__ import annotations

import collections
import math
import os
import random

import pytest

import test_mirror as tm
from app import mirror as mm
from app import mirror_core as mc
from test_mirror import DAY, PX, T1, payload, timedelta

D2 = "2026-11-11"
FULL = bool(os.environ.get("MIRROR_SWEEP_FULL"))


# =============================================================================================== S01
class Bomb:
    """raises tm.Crash at the n-th instrumented event (before or after it happens)"""

    VENUE = ("place_stock_order", "place_limit_order", "cancel_stock_order", "find_stock_order",
             "stock_order_fills", "cancel_inactive_stock_order")

    def __init__(self, rig, monkeypatch):
        self.rig, self.n, self.at, self.armed, self.log = rig, 0, None, False, []
        real_write = mm.atomic_write

        def write(path, obj):
            self._hit("save<", path.rsplit("/", 1)[-1])
            real_write(path, obj)
            self._hit("save>", path.rsplit("/", 1)[-1])
        monkeypatch.setattr(mm, "atomic_write", write)
        v = self.rig.venue
        for name in self.VENUE:
            real = getattr(type(v), name).__get__(v)

            def call(*a, _real=real, _name=name, **k):
                self._hit(_name + "<", a[0] if a else "")
                out = _real(*a, **k)
                self._hit(_name + ">", a[0] if a else "")
                return out
            setattr(v, name, call)

    def _hit(self, kind, what):
        if not self.armed:
            return
        self.n += 1
        self.log.append((self.n, kind, what))
        if self.at is not None and self.n == self.at:
            self.armed = False
            raise tm.Crash(f"{kind} {what}")


def scenario_rotation(r):
    """day 2: sells, a cross, a transfer, buys"""
    t2 = dict(T1, HG={"TQQQ": 1.0}, HARV={"BIL": 1.0}, SLEEVE={"TQQQ": 0.5, "BOXX": 0.5})
    r.brain.make = lambda now: payload(now, t2, session=D2, rules={})
    r.m.request_transfer("SLEEVE", "KMLM", 3000.0)
    return [("15:55:05", D2), ("15:55:20", D2), ("15:56:00", D2), ("15:57:00", D2)]


def scenario_credit(r):
    """day 2: a dividend credited to one sleeve and a fee debited from another (sent dividend first:
    debits are applied first), then the plan"""
    r.venue.cash += 61.20 - 12.34                        # the account really received / paid them
    r.m.request_credit("HARV", 61.20, "PULS dividend")
    r.m.request_credit("HG", -12.34, "fee")
    r.brain.make = lambda now: payload(now, session=D2, rules={})
    return [("15:55:05", D2), ("15:55:20", D2), ("15:56:00", D2)]


def scenario_dividend_and_split(r):
    """day 2: BIL goes ex and pays the same day (the account has the cash), PULS goes ex with a later
    pay date (a receivable stays open), and SOXL splits 2:1 (the account already shows the new count)"""
    r.venue.cash += r.m.book.positions()["BIL"] * 0.3
    r.venue._positions["SOXL"] *= 2
    r.venue.quotes["SOXL"] = 20.0
    px2 = dict(PX, SOXL=20.0)
    r.brain.make = lambda now: payload(now, prices=px2, session=D2, rules={},
                                       dividends=[{"ticker": "BIL", "ex_date": D2, "pay_date": D2, "amount": 0.3},
                                                  {"ticker": "PULS", "ex_date": D2, "pay_date": None, "amount": 0.2}],
                                       splits=[{"ticker": "SOXL", "date": D2, "ratio": 2.0}])
    return [("15:55:05", D2), ("15:55:20", D2), ("15:56:00", D2)]


def scenario_window_end(r):
    """day 2: one sell rests and is cancelled at the cancel instant with a partial fill"""
    t2 = dict(T1, HG={"TQQQ": 1.0})
    r.brain.make = lambda now: payload(now, t2, session=D2)
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 100
    r.venue.fill_px["BIL"] = 91.40
    return [("15:55:05", D2), ("15:58:59", D2), ("15:59:05", D2), ("15:59:30", D2)]


def scenario_flatten(r):
    r.m.halt("KILL", flatten=True)
    return [("15:56:00", DAY), ("15:56:10", DAY), ("15:56:30", DAY)]


def scenario_flatten_two_rounds(r):
    """one flatten sell is refused in the first round and sold in the second"""
    r.venue.reject.add("SOXL")
    r.m.halt("KILL", flatten=True)
    return [("15:56:00", DAY), ("UNREJECT", None), ("15:56:10", DAY), ("15:56:20", DAY), ("15:56:30", DAY)]


def scenario_halt_mid_run(r):
    t2 = dict(T1, HG={"TQQQ": 1.0}, SLEEVE={"TQQQ": 1.0})
    r.brain.make = lambda now: payload(now, t2, session=D2)
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 50
    return [("15:55:05", D2), ("HALT", None), ("15:55:30", D2), ("15:56:00", D2)]


def scenario_repairs(r):
    """an operator adjustment (a fee, booked as a cash delta) and then a session"""
    r.venue.cash -= 7.5
    r.m.request_adjust("HG", None, 0, -7.5, "wire fee")
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session=D2, rules={})
    return [("10:00:00", D2), ("15:55:05", D2), ("15:55:20", D2)]


SAME = (scenario_rotation, scenario_credit, scenario_flatten, scenario_dividend_and_split, scenario_repairs)
SCENARIOS = SAME + (scenario_window_end, scenario_halt_mid_run, scenario_flatten_two_rounds)


def _run(tmp_path, monkeypatch, scenario, crash_at):
    r = tm.live_rig(tmp_path)
    r.tick("15:55:05")                                   # day 1: invested
    bomb = Bomb(r, monkeypatch)
    steps = scenario(r)
    bomb.armed, bomb.at = True, crash_at
    crashed = False
    for hms, day in steps:
        if hms == "UNREJECT":
            r.venue.reject.clear()
            continue
        if hms == "HALT":
            try:
                r.m.halt("operator")
            except tm.Crash:                             # died inside the halt write: the operator's call
                crashed = True                           # failed, the process restarts, they send it again
                bomb.armed = False
                r.boot()
                r.m.halt("operator")
            continue
        try:
            r.tick(hms, day=day)
        except tm.Crash:
            crashed = True
            bomb.armed = False
            r.boot()                                     # the process restarts
            r.tick(hms, day=day)
            r.clock.now += timedelta(seconds=3)
            r.m.tick(r.venue)
    for _ in range(4):                                   # settle
        r.clock.now += timedelta(seconds=6)
        r.m.tick(r.venue)
    return r, bomb, crashed


def _sleeves(r):
    return {n: (round(x.cash, 6), dict(x.shares)) for n, x in r.m.book.sleeves.items()}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__)
def test_s01_every_crash_point_restarts_to_a_sound_book(tmp_path, monkeypatch, scenario):
    base, bomb, _ = _run(tmp_path / "base", monkeypatch, scenario, None)
    total = bomb.n
    assert total > 10 and base.m.state["run"] is None
    if scenario is scenario_dividend_and_split:          # (the scenario does what it says)
        assert sorted(x["status"] for x in base.m.state["dividends"]) == ["credited", "open", "open"]
        assert base.m.state["splits_applied"] and base.m.state["last_run"]["session"] == D2
    assert tm.mc.check(base.m.book, base.venue.positions_snapshot()["stocks"], exact=True) == []
    assert abs(base.m.book.cash() - base.venue.cash) < 0.01 and base.venue.cash >= 0
    bad = []
    for k in range(1, total + 1):
        with pytest.MonkeyPatch.context() as mp:
            r, b, crashed = _run(tmp_path / f"k{k}", mp, scenario, k)
        where = b.log[-1] if b.log else None
        ids = collections.Counter(cid for _, _, cid in r.venue.placed)
        dup = {c: n for c, n in ids.items() if n > 1}
        probs = tm.mc.check(r.m.book, r.venue.positions_snapshot()["stocks"], exact=True)
        cash_gap = r.m.book.cash() - r.venue.cash
        # where the fills do not depend on WHEN the restart happened, the restarted book must be the
        # uncrashed one to the cent and to the share, sleeve by sleeve (a transfer, a cross, a credit, a
        # dividend or a split applied twice, or a fill split differently, would all be zero-sum or
        # invisible at the book level)
        same = True
        if scenario in SAME:
            same = (_sleeves(r) == _sleeves(base) and r.m.state["requests"] == base.m.state["requests"]
                    and [(x["id"], x["status"]) for x in r.m.state["dividends"]]
                    == [(x["id"], x["status"]) for x in base.m.state["dividends"]])
        if dup or probs or abs(cash_gap) > 0.01 or r.m.state["run"] is not None or not crashed or not same \
                or r.venue.cash < -1e-6:
            bad.append((k, where, dup, probs, round(cash_gap, 2), r.m.state["run"] is not None, crashed, same))
    assert not bad, f"{len(bad)} of {total} crash points end unsound; first: {bad[:3]}"


# =============================================================================================== S03
def _paper_run(tmp_path, crash_at):
    r = tm.Rig(tmp_path)
    r.tick("15:55:05")
    t2 = dict(T1, HG={"TQQQ": 1.0}, HARV={"BIL": 1.0}, SLEEVE={"TQQQ": 0.5, "BOXX": 0.5})
    r.brain.make = lambda now: payload(now, t2, session=D2, rules={},
                                       dividends=[{"ticker": "PULS", "ex_date": D2, "pay_date": D2, "amount": 0.2}])
    r.m.request_transfer("SLEEVE", "KMLM", 3000.0)
    n = {"k": 0}
    real = mm.atomic_write
    crashed = False
    with pytest.MonkeyPatch.context() as mp:
        def write(path, obj):
            n["k"] += 1
            if n["k"] == crash_at:
                raise tm.Crash("before")
            real(path, obj)
            if crash_at is not None and n["k"] == -crash_at:
                raise tm.Crash("after")
        mp.setattr(mm, "atomic_write", write)
        try:
            r.tick("15:55:05", day=D2)
        except tm.Crash:
            crashed = True
    if crashed:
        r.boot()
    for _ in range(4):
        r.clock.now += timedelta(seconds=3)
        r.m.tick(None)
    return r, n["k"], crashed


def test_s03_the_paper_book_survives_a_restart_at_every_save(tmp_path):
    base, total, _ = _paper_run(tmp_path / "base", None)
    want = _sleeves(base)
    assert base.m.state["last_run"]["outcome"] == "traded" and base.m.state["last_run"]["credits"]
    bad = []
    for k in list(range(1, total + 1)) + [-x for x in range(1, total + 1)]:     # before AND after every save
        r, _, crashed = _paper_run(tmp_path / f"k{k}", k)
        probs = tm.mc.check(r.m.book, r.m._dry.positions_snapshot()["stocks"], exact=True)
        if _sleeves(r) != want or probs or r.m.state["run"] is not None or not crashed:
            bad.append((k, probs, crashed, r.m.state["run"] is not None, r.m.state["last_run"]["outcome"]))
    assert total > 10 and not bad, f"{len(bad)} of {2 * total}: {bad[:3]}"


# =============================================================================================== S02
SYMS = {"BIL": 91.5, "SOXL": 40.0, "TECL": 100.0, "PULS": 49.5, "BOXX": 113.0, "TQQQ": 80.0, "SPY": 600.0, "UVXY": 23.0}
NAMES = ("HG", "KMLM", "SLEEVE", "HARV")


def _session(rnd, book, venue, prices, tag, slip, fee):
    """one random session; buys fill at slip(order) - never above the order's limit, as at a venue"""
    targets = {}
    for name in book.sleeves:
        if rnd.random() < 0.08:
            continue
        if rnd.random() < 0.05:
            targets[name] = {"status": "unavailable", "note": "x"}
            continue
        picks = rnd.sample(list(SYMS), rnd.randint(1, 4))
        ws = [rnd.random() + 0.05 for _ in picks]
        targets[name] = {"status": "ok", "target": {a: w / sum(ws) for a, w in zip(picks, ws)}, "version": "v"}
    transfers = []
    for _ in range(rnd.choice([0, 0, 1, 2])):
        a, b = rnd.sample(NAMES, 2)
        transfers.append({"from": a, "to": b, "amount": rnd.choice([50.0, 500.0, 5000.0, 1e7])})
    cash0 = book.cash()
    plan = mc.build_plan(book, targets, prices, tag, transfers=transfers)
    mc.apply_crosses(book, plan)
    assert math.isclose(book.cash(), cash0, abs_tol=1e-6)                       # crosses are zero-sum
    vcash = 0.0
    for o in plan["sells"]:
        q = int(o["qty"] * rnd.choice([1.0, 1.0, 1.0, 0.4, 0.0]))
        px = o["ref"] * (1 + rnd.uniform(-0.01, 0.01))
        c = fee if q else 0.0
        mc.book_fill(book, o, q, px if q else None, c)
        venue[o["symbol"]] = venue.get(o["symbol"], 0) - q
        vcash += q * px - c
    before = book.cash()
    mc.apply_transfers(book, plan)
    assert math.isclose(book.cash(), before, abs_tol=1e-6)                      # transfers are zero-sum
    limits = None
    if rnd.random() < 0.5:                                                      # the venue's quote has moved: the caller's limits
        limits = {s: round(p * (1 + rnd.uniform(-0.015, 0.015)) * 1.005, 2) for s, p in plan["prices"].items()}
    buys = mc.size_buys(book, plan, limits=limits)
    sold, bought = {o["symbol"] for o in plan["sells"]}, {o["symbol"] for o in buys}
    assert not (sold & bought), (sold, bought)                                  # netted: never both sides
    assert len(sold) == len(plan["sells"]) and len(bought) == len(buys)          # one order per symbol and side
    spendable = max(book.cash(), 0.0)
    assert sum(o["qty"] * o["limit"] for o in buys) <= spendable + 1e-6          # sized AT the limit, inside the book's cash
    for o in buys:
        q = int(o["qty"] * rnd.choice([1.0, 1.0, 1.0, 0.4, 0.0]))
        px = slip(rnd, o)
        assert px <= o["limit"] + 1e-12
        c = fee if q else 0.0
        mc.book_fill(book, o, q, px if q else None, c)
        venue[o["symbol"]] = venue.get(o["symbol"], 0) + q
        vcash -= q * px + c
    mc.finish(book, plan)
    assert mc.check(book, {k: v for k, v in venue.items() if v}) == []
    assert math.isclose(book.cash(), cash0 + vcash, abs_tol=1e-6)
    return plan


def _fuzz(slip, fee, seed, trials):
    rnd = random.Random(seed)
    worst = 0.0
    for trial in range(trials):
        book = mc.Book.seed(rnd.choice([20_000.0, 118_000.0]), {"HG": 0.29, "KMLM": 0.29, "SLEEVE": 0.27, "HARV": 0.15},
                            {"KMLM": {"rule": "threshold", "corridor": 0.10}})
        venue: dict = {}
        prices = dict(SYMS)
        for day in range(10):
            prices = {s: p * math.exp(rnd.gauss(0, 0.05)) for s, p in prices.items()}
            _session(rnd, book, venue, prices, f"t{trial}d{day}", slip, fee)
            worst = min(worst, book.cash())
    return worst


SLIPS = {
    "near the reference": lambda rnd, o: min(o["limit"], o["ref"] * (1 + rnd.uniform(-0.01, 0.003))),
    "anywhere up to the limit": lambda rnd, o: o["limit"] * (1 - rnd.choice([0.0, 0.0, rnd.uniform(0, 0.02)])),
    "always AT the limit": lambda rnd, o: o["limit"],
}


@pytest.mark.parametrize("how", list(SLIPS))
def test_s02_conservation_netting_and_no_borrow_wherever_a_limit_buy_fills(how):
    worst = _fuzz(SLIPS[how], fee=0.0, seed=1, trials=4000 if FULL else 400)
    assert worst >= -1e-6, f"book cash went as low as ${worst:,.2f}"


def test_s02_commissions_are_paid_from_the_reserve(tmp_path):
    """with a commission on every order the book's cash still never goes below zero by more than the
    fees a tiny sleeve's reserve cannot cover (the reserve is 0.1% of the sleeve)"""
    worst = _fuzz(SLIPS["always AT the limit"], fee=0.35, seed=2, trials=4000 if FULL else 400)
    assert worst >= -5.0, f"book cash went as low as ${worst:,.2f}"


def test_s02_twin_a_fill_above_the_limit_is_what_would_borrow():
    """the property rests on the limit: a (physically impossible) fill above it does overdraw"""
    rnd = random.Random(3)
    book = mc.Book.seed(118_000.0, {"HG": 1.0})
    plan = mc.build_plan(book, {"HG": {"status": "ok", "target": {"SPY": 1.0}}}, SYMS, "s")
    mc.apply_crosses(book, plan)
    (o,) = mc.size_buys(book, plan)
    mc.book_fill(book, o, o["qty"], o["limit"] * (1 + rnd.uniform(0.005, 0.01)), 0.0)
    assert book.cash() < 0
