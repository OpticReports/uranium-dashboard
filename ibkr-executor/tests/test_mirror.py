"""Gate tests for app/mirror.py, the Composer mirror's executor strategy (composer/IBKR_MIRROR.md).

Every behavioural gate has a broken twin that must land on the other side. The doubles here (Rig,
Venue, Brain, Clock) are shared by the other mirror test files: tests/test_mirror_review.py (the
adversarial review's findings, one gate each), tests/test_mirror_sweeps.py (crash sweeps and fuzz)
and tests/ibrig.py (the same manager over the REAL IBAdapter).

  M1  a session end to end on the paper book: seeded sleeves, one netted order per symbol, sells
      before buys, the book equal to the account afterwards, nothing repeated on the next tick
  M2  timing and validity (contract v2): nothing before the decision bar ends plus the offset; a
      payload that is not pinned, not as of the decision instant, whose bar is incomplete, built in
      the future or before its own instant, for another session or a replay is never acted on; its
      AGE is no test (a restart at 15:57 trades the payload built at 15:54); the brain's 503 while
      the bar is being published is retried; a missed window is a recorded NO TRADE
  M3  live pre-trade gates: the blend on, a foreign position, cash the account does not have, or no
      cash claim each stop the session; the twin trades
  M4  the venue cross-check: a symbol the venue prices differently takes its sleeves out of the plan
      and nobody else's; a previous-close quote is no cross-check; an estimated price is replaced
  M5  write-ahead and restarts: an id is on disk before the venue sees it; a crash before or after the
      placement books the order exactly once and never sends a second one; a lost ack is adopted; a
      restart onto a venue that has FORGOTTEN the order never books it as zero and never re-sends it
  M6  the window's end: a working order is cancelled, its partial fill booked at the venue's price,
      and the buys are sized from the cash actually there
  M7  a venue rejection books nothing and stops nobody else
  M8  an order that cannot be resolved is never guessed at: the run stays open, nothing new is planned
  M9  the threshold sleeve holds inside its corridor and trades outside it
  M10 halt: nothing new is sent, what is in flight is settled, the halt survives a restart
  M11 /kill's flatten: every share sold, never more than the account holds, queued while the session
      is shut, resumable, restart-safe
  M12 the post-session account check: a mismatch that persists halts a live book; one that clears
      does not
  M13 the state file: unreadable or another book's -> halted, never a fresh book
  M14 requests: a transfer rides the next plan and is zero-sum; a credit is applied once, and a live
      book takes it only from cash the account really has
  M15 sleeves: live seeding needs the account's cash; a removed engine is frozen (live) or dropped
  M16 a commission reported late is debited later, once; one never reported is dropped LOUDLY
  M17 a fill with no reported price is booked at the reference, loudly
  M18 the loop cadence the book asks for
  M19 build(): which engines are live, which paper; bad weights refuse to build; settings clamped
  M20 the brain client: token header, the after instant, the pinned payload kept for the second book
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import mirror as mm
from app import mirror_core as mc
from app.ib_adapter import DryAdapter

UTC = timezone.utc
DAY = "2026-11-10"                       # a Tuesday; EST: the decision bar ends 20:54:00Z
PX = {"BIL": 91.5, "SOXL": 40.0, "TECL": 100.0, "PULS": 49.5, "BOXX": 113.0, "TQQQ": 80.0, "SPY": 600.0}
T1 = {"HG": {"BIL": 1.0}, "KMLM": {"SOXL": 0.375, "TECL": 0.375, "PULS": 0.25}, "SLEEVE": {"BOXX": 1.0},
      "HARV": {"PULS": 1.0}}
RULES = {"KMLM": ("threshold", 0.1)}
ENGINES = ("HG", "KMLM", "SLEEVE", "HARV")
W = {"HG": 0.29, "KMLM": 0.29, "SLEEVE": 0.27, "HARV": 0.15}
DECISION_MINUTES = 6                     # contract v2: decide_utc = close - 6 min EXACTLY (the bar ENDING 15:54:00)


def at(hms: str, day: str = DAY) -> datetime:
    """an ET wall time on `day` as UTC (EST in November: +5h)"""
    h, m, s = (list(map(int, hms.split(":"))) + [0])[:3]
    y, mo, d = map(int, day.split("-"))
    return datetime(y, mo, d, h, m, s, tzinfo=mm.ET).astimezone(UTC)


def decide_utc(session: str = DAY, close: str = "16:00") -> str:
    return mm._iso(at(close, session) - timedelta(minutes=DECISION_MINUTES))


class Clock:
    def __init__(self, now):
        self.now, self.slept, self.interrupt = now, [], False

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += timedelta(seconds=s)
        self.slept.append(s)
        return self.interrupt


def payload(now, targets=None, prices=None, session=DAY, rules=None, close="16:00", **over):
    """a schema-2 intents payload: pinned to the session's decision instant, built at `now`"""
    rules = RULES if rules is None else rules
    engines = {}
    for name, tgt in (T1 if targets is None else targets).items():
        rule, cor = rules.get(name, ("daily", None))
        base = {"symphony": "sym-" + name, "version": "v-" + name, "rule": rule, "corridor": cor}
        engines[name] = (dict(base, status="unavailable", note="no prices for X") if tgt is None else
                         dict(base, status="ok", target=tgt, label="firm", stale=[], caveats=[]))
    t = decide_utc(session, close)
    out = {"schema": 2, "kind": mm.INTENTS_KIND, "session": session, "pinned": True, "asof_utc": t,
           "built_utc": mm._iso(now), "decision_bar": {"end_utc": t, "spy_utc": t, "complete": True},
           "replay": False, "close_et": close, "engines": engines, "prices": dict(PX if prices is None else prices),
           "price_times": {}, "price_notes": {}, "dividends": [], "splits": [],
           "sync": {n: {"state": "ok", "approved_version": "v-" + n, "approved_sha1": "x", "live_version": "v-" + n,
                        "attested_utc": t} for n in engines},
           "quotes": None, "problems": []}
    out.update(over)
    return out


class Brain:
    def __init__(self, clock):
        self.clock, self.make, self.fail, self.session_fail, self.shut, self.calls = clock, payload, None, None, False, []
        self.close = "16:00"
        self.no_session_reason = None

    def session(self):
        if self.session_fail:
            return None, self.session_fail
        now = self.clock.now
        e = now.astimezone(mm.ET)
        day = e.date().isoformat()
        out = {"schema": 2, "kind": mm.SESSION_KIND, "now_utc": mm._iso(now), "session": None}
        if self.no_session_reason:
            return dict(out, reason=self.no_session_reason), "ok"
        if e.weekday() >= 5 or self.shut:
            return out, "ok"
        ch, cm = map(int, self.close.split(":"))
        close = at(f"{ch}:{cm}", day)
        dec = close - timedelta(minutes=DECISION_MINUTES)
        out.update(session=day, open_utc=mm._iso(at("9:30", day)), decide_utc=mm._iso(dec),
                   decide_et=dec.astimezone(mm.ET).strftime("%H:%M"), close_utc=mm._iso(close), close_et=self.close)
        return out, "ok"

    def intents(self, after):
        self.calls.append((after, self.clock.now))
        if self.fail:
            return None, self.fail
        return self.make(self.clock.now), "ok"


class Crash(BaseException):
    """the process dies here (not an Exception: nothing in the manager may catch it)"""


class Venue(DryAdapter):
    """a scriptable account: cash, quotes, and orders that fill, rest, reject or lose their ack. SELLS
    arrive as market orders (place_stock_order), BUYS as limit orders (place_limit_order), which - as
    at a real venue - never fill above their limit: one priced above it rests."""

    def __init__(self, cash=0.0):
        super().__init__()
        self.cash = cash
        self.quotes = dict(PX)
        self.source = {}
        self.hold, self.reject, self.ack_lost, self.no_price = set(), set(), set(), set()
        self.partial = {}                  # symbol -> shares that fill when the cancel arrives
        self.fill_px = {}                  # symbol -> the price it really fills at
        self.commission = 0.0
        self.report_commission = True
        self.cash_claim = True
        self.cancel_raises = False
        self.crash_before, self.crash_after = set(), set()
        self.placed = []                   # (symbol, signed qty, client id) of every order that reached the venue
        self.limits = {}                   # client id -> the limit of a buy
        self.history_ok = True             # history_complete(): False = completed orders unavailable
        self.forgotten = set()             # client ids the venue no longer answers for (a session boundary)
        self.absent = None                 # order_absent_today(): None = open orders / executions did not both answer
        self.absent_asked = []
        self.inactive_cancels = []

    def account_cash(self):
        if not self.cash_claim:
            return None
        return {"total_cash": self.cash, "net_liq": None, "available_funds": self.cash, "ts": time.time()}

    def spot_ex(self, symbol):
        if symbol not in self.quotes:
            raise RuntimeError(f"no market price for {symbol}")
        return self.quotes[symbol], self.source.get(symbol, "live")

    def history_complete(self):
        return self.history_ok

    def order_absent_today(self, client_order_id):
        self.absent_asked.append(client_order_id)
        return self.absent(client_order_id) if callable(self.absent) else self.absent

    def _order_result(self, rec):
        out = {"order_ref": rec["order_ref"], "status": rec["status"]}
        if rec["status"] == "filled":
            if rec["symbol"] not in self.no_price:
                out["fill_price"] = rec["fill_price"]
            if self.report_commission:
                out["commission"] = rec.get("commission", 0.0)
        if rec["status"] == "cancelled":
            out["reason"] = rec.get("reason", "cancelled by the executor")
            if rec.get("filled_qty"):
                out["filled_qty"] = rec["filled_qty"]
        return out

    def _px(self, rec):
        return self.fill_px.get(rec["symbol"], self.quotes.get(rec["symbol"], 100.0))

    def _crosses(self, rec):
        return rec.get("limit") is None or self._px(rec) <= rec["limit"] + 1e-12

    def _fill(self, rec, shares):
        sym = rec["symbol"]
        px = self._px(rec)
        sign = 1 if rec["qty"] > 0 else -1
        assert rec.get("limit") is None or px <= rec["limit"] + 1e-12, "a limit order never fills above its limit"
        self._positions[sym] = self._positions.get(sym, 0) + sign * shares
        self.cash -= sign * shares * px + self.commission
        rec["filled_qty"] = rec.get("filled_qty", 0) + shares
        rec["fill_price"], rec["commission"] = px, self.commission
        if rec["filled_qty"] == abs(rec["qty"]):
            rec["status"] = "filled"

    def _send(self, symbol, qty, client_order_id, limit):
        prior = self._orders.get(self._by_client.get(client_order_id, ""))
        if prior is not None and prior["status"] in ("working", "filled"):
            return {**self._order_result(prior), "duplicate": True}
        if symbol in self.crash_before:
            raise Crash(symbol)
        self.placed.append((symbol, qty, client_order_id))
        if limit is not None:
            self.limits[client_order_id] = limit
        ref = f"v-{len(self._orders) + 1}"
        rec = {"order_ref": ref, "symbol": symbol, "qty": qty, "status": "working", "fill_price": None,
               "client_order_id": client_order_id, "filled_qty": 0, "limit": limit}
        self._orders[ref] = rec
        self._by_client[client_order_id] = ref
        if symbol in self.reject:
            rec.update(status="cancelled", reason="[201] Order rejected - insufficient funds")
            raise RuntimeError("order rejected by venue (status Cancelled): [201] Order rejected")
        if symbol not in self.hold and self._crosses(rec):
            self._fill(rec, abs(qty))
        if symbol in self.crash_after:
            raise Crash(symbol)
        if symbol in self.ack_lost:
            self.ack_lost.discard(symbol)
            raise RuntimeError("no venue ack within 10s — state UNKNOWN; retry is idempotent via orderRef")
        return self._order_result(rec)

    def place_stock_order(self, symbol, qty, order_type, stop_price=None, tif="DAY", ref_price=None,
                          client_order_id=None):
        assert order_type == "MKT" and tif == "DAY" and client_order_id
        assert qty < 0, "the mirror's market orders are SELLS; a buy must be a limit order"
        return self._send(symbol, qty, client_order_id, None)

    def place_limit_order(self, symbol, qty, limit_price, tif="DAY", ref_price=None, client_order_id=None):
        assert tif == "DAY" and client_order_id and qty > 0 and limit_price > 0
        assert round(limit_price * 100) == pytest.approx(limit_price * 100, abs=1e-6) or limit_price < 1, \
            f"a limit must be on the venue's price grid: {limit_price!r}"
        out = self._send(symbol, qty, client_order_id, float(limit_price))
        return dict(out, limit_price=float(limit_price))

    def find_stock_order(self, client_order_id):
        if client_order_id in self.forgotten:
            return None
        return super().find_stock_order(client_order_id)

    def open_sell_qty(self, symbol, exclude=None):
        """IBAdapter.open_sell_qty: the unfilled shares of the SELL orders still working for `symbol`"""
        return sum(abs(r["qty"]) - r.get("filled_qty", 0) for r in self._orders.values()
                   if r["symbol"] == symbol and r["qty"] < 0 and r["status"] == "working"
                   and r.get("client_order_id") != exclude and r.get("client_order_id") not in self.forgotten)

    def cancel_stock_order(self, order_ref):
        rec = self._orders.get(order_ref)
        if rec is None or rec["status"] == "cancelled":
            return False
        if rec["status"] == "filled":
            raise RuntimeError(f"cannot cancel {order_ref}: order already FILLED")
        if self.cancel_raises:
            raise RuntimeError(f"cancel of {order_ref} not acknowledged — state UNKNOWN (fail closed)")
        part = min(self.partial.get(rec["symbol"], 0), abs(rec["qty"]) - rec.get("filled_qty", 0))
        if part and self._crosses(rec):
            self._fill(rec, part)
        if rec["status"] == "filled":
            raise RuntimeError(f"cannot cancel {order_ref}: order FILLED before the cancel landed")
        rec["status"] = "cancelled"
        return True

    def cancel_inactive_stock_order(self, client_order_id):
        self.inactive_cancels.append(client_order_id)
        return False

    def stock_order_fills(self, client_order_id):
        rec = self._orders.get(self._by_client.get(client_order_id, ""))
        if rec is None or client_order_id in self.forgotten:
            return None
        got = rec.get("filled_qty", 0)
        return {"filled_qty": got, "avg_price": rec["fill_price"] if got and rec["symbol"] not in self.no_price else None,
                "commission": rec.get("commission") if got and self.report_commission else None,
                "venue_status": {"filled": "Filled", "cancelled": "Cancelled", "working": "Submitted"}[rec["status"]]}

    def release(self, symbol):
        for rec in self._orders.values():
            if rec["symbol"] == symbol and rec["status"] == "working" and self._crosses(rec):
                self._fill(rec, abs(rec["qty"]) - rec.get("filled_qty", 0))


class Rig:
    def __init__(self, tmp_path, live=False, engines=ENGINES, capital=100_000.0, venue_cash=None, **cfg):
        self.tmp, self.live, self.engines, self.capital, self.cfg_over = tmp_path, live, tuple(engines), capital, cfg
        self.clock = Clock(at("15:00"))
        self.brain = Brain(self.clock)
        self.trading_day = None            # the service's holiday calendar (date -> bool); None: weekdays
        self.venue = Venue(capital if venue_cash is None else venue_cash) if live else None
        self.alerts = []
        self.m = self.boot()

    def boot(self):
        cfg = mm.MirrorConfig(name="live" if self.live else "dry", live=self.live, engines=self.engines,
                              capital={e: self.capital * w for e, w in W.items()},
                              state_path=str(self.tmp / ("mirror.json" if self.live else "mirror_dry.json")),
                              **self.cfg_over)
        self.m = mm.MirrorManager(cfg, brain=self.brain, alert=self.alerts.append, clock=self.clock, sleep=self.clock.sleep,
                                  trading_day=self.trading_day)
        return self.m

    @property
    def ad(self):
        return self.venue if self.live else self.m._dry

    def tick(self, hms=None, day=DAY):
        if hms:
            self.clock.now = at(hms, day)
        self.m.tick(self.venue)
        return self.m

    def red(self):
        return [a for a in self.alerts if a.startswith("🚨")]

    def orders(self):
        if self.live:
            return [(s, q) for s, q, _ in self.venue.placed]
        return [(e["symbol"], e["qty"]) for e in self.m._dry.log if e["action"] in ("place_stock_order", "place_limit_order")]

    def journal(self):
        try:
            return [json.loads(x) for x in open(self.m.cfg.state_path + ".journal.jsonl")]
        except FileNotFoundError:
            return []


def sound(rig):
    """the invariants every gate ends on: the book is whole, equals the account, and neither the book
    nor the ACCOUNT ever borrows"""
    assert mc.check(rig.m.book, rig.ad.positions_snapshot()["stocks"], exact=True) == []
    assert rig.m.book.cash() >= -1e-6
    if rig.live:
        assert rig.venue.cash >= -1e-6, f"the account borrowed: ${rig.venue.cash:,.2f}"
        assert rig.m.book.cash() <= rig.venue.cash + 1e-6
        for cid, limit in rig.venue.limits.items():       # no buy ever filled above the price it was sized at
            rec = rig.venue._orders[rig.venue._by_client[cid]]
            assert rec["fill_price"] is None or rec["fill_price"] <= limit + 1e-9, (cid, rec["fill_price"], limit)


# --- M1 ---------------------------------------------------------------------------------------------
def test_m1_a_session_end_to_end_on_the_paper_book(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:00")
    assert set(r.m.book.sleeves) == set(ENGINES) and r.m.book.positions() == {}
    assert r.m.book.cash() == pytest.approx(100_000.0)
    assert r.orders() == []                                   # the twin: before the decision bar, nothing
    r.tick("15:55:05")
    assert r.m.state["last_session"] == DAY and r.m.state["run"] is None
    got = r.orders()
    assert [s for s, _ in got] == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]       # one order per symbol, all buys
    assert all(q > 0 for _, q in got)
    snap = mc.snapshot(r.m.book, PX)
    for name, tgt in T1.items():
        for sym, w in tgt.items():
            assert snap["sleeves"][name]["weights"][sym] == pytest.approx(w, abs=0.01), (name, sym)
        assert snap["sleeves"][name]["share_of_book"] == pytest.approx(W[name], abs=0.002)
    # PULS is one venue order split across the two sleeves that asked for it
    puls = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "PULS")
    assert set(puls["split"]) == {"KMLM", "HARV"} and sum(puls["split"].values()) == puls["filled"] == puls["qty"]
    assert r.m.state["last_run"]["outcome"] == "traded"
    sound(r)
    n = len(r.orders())
    r.tick("15:55:30")
    r.tick("15:58:00")
    assert len(r.orders()) == n                               # one decision per session
    assert not r.red()


def test_m1_day_two_sells_first_crosses_internally_and_nets(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:55:05")
    held = dict(r.m.book.positions())
    t2 = dict(T1, HG={"TQQQ": 1.0}, HARV={"BIL": 1.0})        # HG leaves BIL, HARV enters it
    r.brain.make = lambda now: payload(now, t2, session="2026-11-11")
    before = len(r.orders())
    r.tick("15:55:05", day="2026-11-11")
    new = r.orders()[before:]
    row = r.m.state["last_run"]
    assert row["session"] == "2026-11-11"
    cross = {c["symbol"]: c for c in row["crosses"]}
    assert set(cross) == {"BIL"} and cross["BIL"]["sellers"].keys() == {"HG"} and cross["BIL"]["buyers"].keys() == {"HARV"}
    sides = {s: q for s, q in new}
    assert sides["BIL"] < 0 and abs(sides["BIL"]) == held["BIL"] - cross["BIL"]["qty"]    # only the NET goes out
    assert sides["PULS"] < 0 and sides["TQQQ"] > 0
    assert [q < 0 for _, q in new] == sorted([q < 0 for _, q in new], reverse=True)      # every sell before any buy
    assert r.m.book.sleeves["HG"].shares.keys() == {"TQQQ"} and r.m.book.sleeves["HARV"].shares.keys() == {"BIL"}
    sound(r)


# --- M2 ---------------------------------------------------------------------------------------------
def test_m2_nothing_before_the_decision_bar_plus_the_offset_and_only_the_decision_instant_is_asked(tmp_path):
    r = Rig(tmp_path)
    assert r.m.cfg.decide_offset_s == 25.0                    # contract v2: FMP publishes the bar 10-25 s late
    r.tick("15:53:59")
    r.tick("15:54:00")                                        # the bar has ended; the offset has not
    r.tick("15:54:24")
    assert r.orders() == [] and r.brain.calls == []
    wrong = lambda now: payload(now, asof_utc="2026-11-10T20:55:00Z")      # noqa: E731  the NEXT bar's end
    r.brain.make = wrong
    r.tick("15:54:25")
    assert r.orders() == [] and r.m.state["last_session"] is None
    assert "not the decision instant" in r.m._why
    assert all(a == "2026-11-10T20:54:00Z" for a, _ in r.brain.calls)          # decide_utc used AS GIVEN
    assert len(r.brain.calls) == 2                            # N-09: a PAPER book asks at +0 s and +10 s, then hands the loop back
    r.brain.make = payload                                    # the twin: the decision as of that instant
    r.tick()
    assert r.m.state["last_session"] == DAY and r.orders()
    row = r.m.state["last_run"]                               # the run records which bar and which sync it traded on
    assert row["decision_bar"] == {"end_utc": "2026-11-10T20:54:00Z", "spy_utc": "2026-11-10T20:54:00Z", "complete": True}
    assert row["sync"]["HG"]["state"] == "ok" and row["intents_asof"] == "2026-11-10T20:54:00Z"


@pytest.mark.parametrize("bad, why", [
    (lambda now: payload(now, session="2026-11-09"), "session"),
    (lambda now: payload(now, replay=True), "replay"),
    (lambda now: {k: v for k, v in payload(now).items() if k != "replay"}, "replay"),
    (lambda now: payload(at("15:52:30")), "before the instant it decides"),     # built 90 s BEFORE the bar it claims
    (lambda now: payload(now, kind="something-else"), "not a mirror intents"),
    (lambda now: payload(now, schema=1), "not a mirror intents"),
    (lambda now: payload(now + timedelta(seconds=300)), "future"),
    (lambda now: {k: v for k, v in payload(now).items() if k != "prices"}, "no engines or no prices"),
    (lambda now: payload(now, pinned=False), "not pinned"),
    (lambda now: {k: v for k, v in payload(now).items() if k != "pinned"}, "not pinned"),
    (lambda now: payload(now, asof_utc=mm._iso(now)), "not the decision instant"),
    (lambda now: payload(now, decision_bar={"end_utc": decide_utc(), "spy_utc": "2026-11-10T20:38:00Z", "complete": False}),
     "decision bar is not complete"),
    (lambda now: payload(now, decision_bar=None), "decision bar is not complete"),
    (lambda now: {k: v for k, v in payload(now).items() if k != "built_utc"}, "no built_utc"),
])
def test_m2_a_payload_that_fails_a_contract_check_is_refused(tmp_path, bad, why):
    r = Rig(tmp_path)
    r.brain.make = bad
    r.tick("15:57:00")
    assert r.orders() == [] and why in r.m._why
    r2 = Rig(tmp_path / "twin")                               # the twin: the same instant, a payload that passes
    os.makedirs(tmp_path / "twin", exist_ok=True)
    r2.tick("15:57:00")
    assert r2.orders()


def test_m2_a_pinned_payload_is_traded_however_long_ago_it_was_built(tmp_path):
    """contract v2 (clarified): a pinned payload is immutable - the brain caches it by its instant and
    never rebuilds it - so its age says nothing. Lateness is bounded by plan_by alone."""
    built = payload(at("15:54:32"))                           # what the brain built once, and serves for ever
    r = live_rig(tmp_path)
    r.brain.make = lambda now: built
    r.venue.seed_position("AAPL", 3)                          # the account is not the book ...
    r.tick("15:54:35")
    assert r.orders() == [] and "AAPL" in r.m._why and len(r.brain.calls) == 1      # asked once, then held
    r.venue._positions.pop("AAPL")                            # ... until 15:57:10, 158 s after the build
    r.tick("15:57:10")
    assert r.m.state["last_run"]["outcome"] == "traded" and len(r.brain.calls) == 1
    assert r.m.state["last_run"]["built_utc"] == "2026-11-10T20:54:32Z"
    late = Rig(tmp_path / "late", live=True)                  # a RESTART at 15:57: the new process asks again and
    os.makedirs(tmp_path / "late", exist_ok=True)             # is given the payload built at 15:54:32
    late.tick("15:00")
    late.brain.make = lambda now: built
    late.boot()
    late.tick("15:57:30")
    assert late.m.state["last_run"]["outcome"] == "traded" and late.m.state["last_run"]["built_utc"] == "2026-11-10T20:54:32Z"
    sound(late)
    gone = Rig(tmp_path / "gone", live=True)                  # the twin: what bounds lateness is plan_by
    os.makedirs(tmp_path / "gone", exist_ok=True)
    gone.tick("15:00")
    gone.brain.make = lambda now: built
    gone.tick("15:58:00")
    assert gone.orders() == [] and gone.m.state["last_run"]["outcome"] == "skipped"


def test_m2_the_brains_503_while_the_decision_bar_is_published_is_retried_not_final(tmp_path):
    """with a 25 s offset the first read can still be a 503 ('decision bar not published yet', for up
    to 45 s past the instant): a transient reason, asked again every 3 s inside the same tick"""
    r = live_rig(tmp_path)
    real = r.brain.intents
    answers = []

    def intents(after):
        if r.clock.now < at("15:54:44"):                      # FMP publishes the bar 44 s after it ended
            answers.append(r.clock.now)
            r.brain.calls.append((after, r.clock.now))
            return None, "http_503"
        return real(after)
    r.brain.intents = intents
    r.tick("15:54:25")
    assert len(answers) == 7 and r.clock.slept[:7] == [mm.INTENTS_RETRY_S] * 7     # 15:54:25 .. 15:54:43, every 3 s
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and row["session"] == DAY                    # ... and then it trades, same tick
    assert r.m.state["history"][-1]["outcome"] == "traded" and not r.red()
    sound(r)
    down = Rig(tmp_path / "down")                             # the twin: it never comes -> a recorded NO TRADE that says why
    os.makedirs(tmp_path / "down", exist_ok=True)
    down.brain.fail = "http_503: decision bar not published yet — SPY's 15:53 bar is missing"     # R6: the 503's own body
    down.tick("15:54:25")
    assert "the brain is not ready (503: decision bar not published yet — SPY's 15:53 bar is missing)" in down.m._why
    assert down.m.state["last_session"] is None and len(down.brain.calls) == 2      # ... carried, and still retried
    down.tick("15:57:00")
    down.tick("15:58:00")
    row = down.m.state["last_run"]
    assert row["outcome"] == "skipped" and "SPY's 15:53 bar is missing" in row["reason"]          # the day's record says why
    bare = Rig(tmp_path / "bare")                             # a 503 with no body is still transient, and says so
    os.makedirs(tmp_path / "bare", exist_ok=True)
    bare.brain.fail = "http_503"
    bare.tick("15:54:25")
    assert "503: no reason given" in bare.m._why and len(bare.brain.calls) == 2


def test_m2_sync_rows_and_price_times_are_recorded_verbatim_and_gate_nothing_on_paper(tmp_path):
    r = Rig(tmp_path)
    sync = {"HG": {"state": "ok", "approved_version": "v1", "approved_sha1": "abc", "live_version": "v1",
                   "attested_utc": "2026-11-10T20:50:00Z"},
            "KMLM": {"state": "ok", "approved_version": "v2", "approved_sha1": "def", "live_version": "v2",
                     "attested_utc": "2026-11-10T20:50:00Z", "paused": True},
            "SLEEVE": {"state": "none", "approved_version": "v3", "approved_sha1": "x", "live_version": None, "attested_utc": None}}
    times = {"BIL": "2026-11-10T20:54:00Z", "PULS": None, "SOXL": "2026-11-09T21:00:00Z", "TECL": "2026-11-10T20:54:00Z",
             "BOXX": "2026-11-10T20:54:00Z", "NOPE": "2026-11-10T20:54:00Z"}
    r.brain.make = lambda now: payload(now, sync=sync, price_times=times)
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert row["outcome"] == "traded" and len(row["orders"]) == 5              # a null or an old price time stops nobody
    assert row["sync"] == sync                                                 # verbatim, 'paused' included
    assert row["price_times"] == {k: v for k, v in times.items() if k != "NOPE"}
    assert row["sleeves"]["KMLM"]["action"] == "trade"                         # 'paused' is the brain's business
    assert row["sleeves"]["SLEEVE"]["action"] == "trade" and row["sleeves"]["HARV"]["action"] == "trade"
    noted = [n for n in row["notes"] if n.startswith("paper:") and "not attested" in n]     # R3: a live book refuses these two
    assert len(noted) == 2 and any("SLEEVE" in n and "'none'" in n for n in noted) and any("HARV" in n and "no sync row" in n for n in noted)


def test_m2_a_missed_window_is_a_recorded_no_trade(tmp_path):
    r = Rig(tmp_path)
    r.brain.fail = "transport"
    r.tick("15:55:05")
    assert r.m.state["last_session"] is None                  # still trying inside the window
    r.tick("15:57:00")
    r.tick("15:58:00")                                        # plan_by: one minute before the cancel instant
    row = r.m.state["last_run"]
    assert (row["outcome"], r.m.state["last_session"]) == ("skipped", DAY) and "no intents (transport)" in row["reason"]
    assert r.orders() == []
    r.brain.fail = None
    r.tick("15:58:30")
    assert r.orders() == []                                   # the day is decided: no late trade
    r2 = Rig(tmp_path / "b")                                  # the twin: the executor only wakes after the window
    os.makedirs(tmp_path / "b", exist_ok=True)
    r2.tick("15:59:30")
    assert r2.m.state["last_run"]["outcome"] == "skipped" and "missed the decision window" in r2.m.state["last_run"]["reason"]


def test_m2_no_session_no_decision_and_the_half_day_clock(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:55:05", day="2026-11-14")                      # a Saturday
    assert r.orders() == [] and r.m.state["last_session"] is None
    r.brain.close = "13:00"
    r.brain.make = lambda now: payload(now, session="2026-11-27", close="13:00")
    r.tick("12:54:24", day="2026-11-27")                      # the half day's bar ends 12:54:00; + 25 s
    assert r.orders() == []
    r.tick("12:54:25", day="2026-11-27")
    assert r.orders() and r.m.state["last_session"] == "2026-11-27"


def test_m2_a_null_session_with_a_reason_is_reported(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:00")
    r.brain.no_session_reason = "the calendar table ends 2027-12-31"
    r.clock.now += timedelta(seconds=mm.SESSION_TTL_S + 1)
    r.tick()
    r.tick("15:55:05")
    assert r.orders() == [] and any("calendar table ends" in a for a in r.red())
    assert r.m._rth(at("11:00")) is True                      # the kill path does not take that "no session" as a fact
    q = Rig(tmp_path / "wk")                                  # the twin: a plain weekend says nothing
    os.makedirs(tmp_path / "wk", exist_ok=True)
    q.tick("15:55:05", day="2026-11-14")
    assert not q.red() and not any("NO session" in a for a in q.alerts)


def test_m2_the_brains_clock_must_agree_with_this_one(tmp_path):
    r = Rig(tmp_path)
    real = r.brain.session

    def skewed():
        info, why = real()
        info["now_utc"] = mm._iso(r.clock.now + timedelta(seconds=mm.CLOCK_SKEW_S + 30))
        return info, why
    r.brain.session = skewed
    r.tick("15:55:05")
    assert r.orders() == [] and r.m.brain_status["session"]["ok"] is False
    r.brain.session = real
    r.clock.now += timedelta(seconds=mm.SESSION_FAIL_TTL_S + 1)
    r.tick()
    assert r.orders()


def test_m2_a_schema_1_clock_is_not_read(tmp_path):
    r = Rig(tmp_path)
    real = r.brain.session
    r.brain.session = lambda: (dict(real()[0], schema=1), "ok")
    r.tick("15:55:05")
    assert r.orders() == [] and "schema 2" in r.m.brain_status["session"]["reason"]


# --- M3 ---------------------------------------------------------------------------------------------
def live_rig(tmp_path, **kw):
    r = Rig(tmp_path, live=True, **kw)
    r.tick("15:00")
    return r


def test_m3_live_trades_when_the_account_is_the_book(tmp_path):
    r = live_rig(tmp_path)
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded" and len(r.orders()) == 5
    sound(r)
    assert not r.red()


@pytest.mark.parametrize("breakit, why", [
    (lambda r: r.venue.seed_position("AAPL", 3), "AAPL: the book holds 0, the venue 3"),
    (lambda r: setattr(r.venue, "cash", 90_000.0), "exceeds the account's"),
    (lambda r: setattr(r.venue, "cash_claim", False), "no cash claim"),
])
def test_m3_live_pre_trade_gates_stop_the_session(tmp_path, breakit, why):
    r = live_rig(tmp_path)
    breakit(r)
    r.tick("15:55:05")
    assert r.orders() == [] and why in r.m._why
    r.tick("15:58:00")
    assert r.m.state["last_run"]["outcome"] == "skipped" and why in r.m.state["last_run"]["reason"]
    assert r.red()


def test_m3_the_mirror_only_observes_while_the_blend_runs(tmp_path):
    r = live_rig(tmp_path, blend_enabled=True)
    r.tick("15:55:05")
    r.tick("15:58:00")
    assert r.orders() == [] and "blend" in r.m.state["last_run"]["reason"]
    d = Rig(tmp_path / "d", blend_enabled=True)               # the twin: the paper book never touches the account
    d.tick("15:55:05")
    assert d.orders()


# --- M4 ---------------------------------------------------------------------------------------------
def test_m4_a_symbol_the_venue_prices_differently_takes_only_its_sleeves_out(tmp_path):
    r = live_rig(tmp_path)
    r.venue.quotes["BOXX"] = PX["BOXX"] * 1.03                # 3% away: a split, a bad print, a wrong symbol
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert row["sleeves"]["SLEEVE"]["action"] == "skip" and "BOXX" in row["dropped"]
    assert {s for s, _ in r.orders()} == {"BIL", "PULS", "SOXL", "TECL"}
    assert r.m.book.sleeves["SLEEVE"].shares == {} and r.m.book.sleeves["HG"].shares
    sound(r)


def test_m4_a_previous_close_is_no_cross_check_and_no_quote_is_no_trade(tmp_path):
    r = live_rig(tmp_path)
    r.venue.source["BIL"] = "close"
    del r.venue.quotes["PULS"]
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    assert {n for n, d in row["sleeves"].items() if d["action"] == "skip"} == {"HG", "KMLM", "HARV"}
    assert {s for s, _ in r.orders()} == {"BOXX"}
    sound(r)


def test_m4_an_estimated_price_is_replaced_by_the_venues_quote(tmp_path):
    r = live_rig(tmp_path)
    r.brain.make = lambda now: payload(now, prices=dict(PX, BOXX=110.0), price_notes={"BOXX": "BOXX 15:20 -> via SGOV"})
    r.tick("15:55:05")                                        # 2.7% away: outside the plain band, inside the estimate's
    row = r.m.state["last_run"]
    assert row["sleeves"]["SLEEVE"]["action"] == "trade" and row["prices"]["BOXX"] == PX["BOXX"]
    boxx = next(o for o in row["orders"] if o["symbol"] == "BOXX")
    assert boxx["ref"] == PX["BOXX"] and boxx["filled"] == boxx["qty"]
    sound(r)


# --- M5 ---------------------------------------------------------------------------------------------
def test_m5_the_id_is_on_disk_before_the_venue_sees_it_and_a_crash_never_doubles_an_order(tmp_path):
    r = live_rig(tmp_path)
    r.venue.crash_before.add("BOXX")                          # the process dies just before BOXX reaches the venue
    with pytest.raises(Crash):
        r.tick("15:55:05")
    disk = json.load(open(r.m.cfg.state_path))
    rec = disk["run"]["orders"][f"mirror-{DAY}-B-BOXX"]
    assert rec["state"] == "intent" and disk["run"]["phase"] == "buys"
    r.venue.crash_before.clear()
    r.boot()
    r.tick("15:55:20")
    assert [s for s, _ in r.orders()].count("BOXX") == 1 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_m5_a_crash_after_the_venue_filled_books_the_fill_once(tmp_path):
    r = live_rig(tmp_path)
    r.venue.crash_after.add("PULS")                           # filled at the venue; the process dies before booking
    with pytest.raises(Crash):
        r.tick("15:55:05")
    assert r.venue.stock_position("PULS") > 0 and r.m.book.positions().get("PULS") is None
    r.venue.crash_after.clear()
    r.boot()
    r.tick("15:55:20")
    assert [s for s, _ in r.orders()].count("PULS") == 1      # adopted by its id, never sent again
    assert r.m.book.positions()["PULS"] == r.venue.stock_position("PULS")
    sound(r)


def test_m5_a_lost_ack_is_adopted_not_repeated(tmp_path):
    r = live_rig(tmp_path)
    r.venue.ack_lost.add("SOXL")
    r.tick("15:55:05")
    assert [s for s, _ in r.orders()].count("SOXL") == 1 and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


@pytest.mark.parametrize("how", ["history unavailable", "the next day"])
def test_m5_a_restart_onto_a_venue_that_forgot_the_order_never_books_zero_and_never_resends(tmp_path, how):
    """the gates above restart onto a venue whose order memory survived. A real one forgets: a new
    gateway session answers only for today, and only when its completed-order history is available.
    'No such order' is then no proof - the order (which FILLED here) stays unresolved."""
    r = live_rig(tmp_path)
    r.venue.crash_after.add("PULS")                           # filled at the venue; the process dies before 'placed' is saved
    with pytest.raises(Crash):
        r.tick("15:55:05")
    cid = f"mirror-{DAY}-B-PULS"
    held = r.venue.stock_position("PULS")
    assert held > 0
    r.venue.crash_after.clear()
    r.venue.forgotten.add(cid)                                # the new session has no row for it ...
    day2 = DAY
    if how == "history unavailable":
        r.venue.history_ok = False                            # ... and cannot prove it never filled
    else:
        day2 = "2026-11-11"                                   # ... or it can, but only for TODAY's orders
    r.boot()
    r.tick("09:35:00" if day2 != DAY else "15:55:20", day=day2)
    r.tick("09:35:05" if day2 != DAY else "15:55:25", day=day2)
    run = r.m.state["run"]
    assert run is not None and run["orders"][cid]["state"] == "intent" and run["orders"][cid].get("stuck")
    assert [s for s, _ in r.orders()].count("PULS") == 1      # never sent again
    assert r.m.book.positions().get("PULS") is None           # never booked as zero-and-done, never guessed
    assert any("UNRESOLVED" in a and cid in a and "/mirror/resolve" in a for a in r.red())
    r.venue.forgotten.clear()                                 # the twin: the venue answers after all -> adopted once
    r.venue.history_ok = True
    r.tick("09:36:00" if day2 != DAY else "15:55:40", day=day2)
    r.tick("16:00:30", day=day2)
    assert r.m.state["run"] is None and r.m.book.positions()["PULS"] == held
    assert [s for s, _ in r.orders()].count("PULS") == 1


def test_m5_an_order_that_provably_never_reached_the_venue_today_is_sent_again_once(tmp_path):
    """the other side of D3: today's order, complete history, no record -> it never got there"""
    r = live_rig(tmp_path)
    real = r.venue.place_limit_order
    n = {"k": 0}

    def flaky(symbol, qty, limit_price, **kw):
        if symbol == "BOXX" and not n["k"]:
            n["k"] += 1
            raise RuntimeError("gateway not connected")       # raised before anything reached the venue
        return real(symbol, qty, limit_price, **kw)
    r.venue.place_limit_order = flaky
    r.tick("15:55:05")
    assert r.m.state["last_run"]["outcome"] == "traded" and [s for s, _ in r.orders()].count("BOXX") == 1
    assert r.m.book.positions()["BOXX"] > 0
    sound(r)


def test_m5_a_restart_between_sessions_changes_nothing(tmp_path):
    r = live_rig(tmp_path)
    r.tick("15:55:05")
    before = (r.m.book.to_dict(), r.m.state["last_session"], len(r.orders()))
    r.boot()
    r.tick("15:56:00")
    assert (r.m.book.to_dict(), r.m.state["last_session"], len(r.orders())) == before


# --- M6 ---------------------------------------------------------------------------------------------
def invested(tmp_path):
    r = live_rig(tmp_path)
    r.tick("15:55:05")
    return r


def test_m6_a_sell_still_working_at_the_cancel_instant_is_cancelled_and_its_partial_booked(tmp_path):
    r = invested(tmp_path)
    t2 = dict(T1, HG={"TQQQ": 1.0})
    r.brain.make = lambda now: payload(now, t2, session="2026-11-11")
    held = r.m.book.sleeves["HG"].shares["BIL"]
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 100
    r.venue.fill_px["BIL"] = 91.40                            # the venue's price, not the reference
    r.tick("15:55:05", day="2026-11-11")
    assert r.m.state["run"]["phase"] == "sells"               # resting: no buy is sized on money not yet there
    assert not any(s == "TQQQ" for s, _ in r.orders())
    assert r.clock.now < at("15:59:00", "2026-11-11")         # the tick gave the loop back inside its budget
    r.tick("15:58:50", day="2026-11-11")                      # ... and this one waits into the cancel instant
    row = r.m.state["last_run"]
    bil = next(o for o in row["orders"] if o["symbol"] == "BIL")
    assert (bil["filled"], bil["price"]) == (100, 91.40) and "cancelled" in bil["how"]
    booked = [json.loads(x) for x in open(r.m.cfg.state_path + ".journal.jsonl")]
    booked = next(x for x in booked if x["event"] == "fill" and x["id"] == "mirror-2026-11-11-S-BIL")
    assert booked["utc"] >= "2026-11-11T20:59:00Z"            # not a second before the cancel instant
    hg = r.m.book.sleeves["HG"]
    assert hg.shares == {"BIL": held - 100}                   # the window closed: no buys were sent at all
    assert any("buys NOT sent" in n for n in row["notes"])
    sound(r)


def test_m6_buys_are_sized_from_the_cash_actually_there(tmp_path):
    r = invested(tmp_path)
    t2 = dict(T1, HG={"TQQQ": 1.0})
    r.brain.make = lambda now: payload(now, t2, session="2026-11-11")
    r.venue.fill_px["BIL"] = 80.0                             # the sell fills 12.6% below the reference
    r.tick("15:55:05", day="2026-11-11")
    row = r.m.state["last_run"]
    tq = next(o for o in row["orders"] if o["symbol"] == "TQQQ")
    hg = r.m.book.sleeves["HG"]
    planned = int(row["sleeves"]["HG"]["pre_equity"] * (1 - r.m.cfg.core.cash_reserve_frac) / PX["TQQQ"])
    assert tq["filled"] < planned and hg.cash >= 0            # scaled to the proceeds; the twin is `planned`
    sound(r)


# --- M7 ---------------------------------------------------------------------------------------------
def test_m7_a_rejected_order_books_nothing_and_stops_nobody_else(tmp_path):
    r = live_rig(tmp_path)
    r.venue.reject.add("BOXX")
    r.tick("15:55:05")
    row = r.m.state["last_run"]
    boxx = next(o for o in row["orders"] if o["symbol"] == "BOXX")
    assert boxx["filled"] == 0 and "insufficient funds" in boxx["how"]
    assert r.m.book.sleeves["SLEEVE"].shares == {} and r.m.book.sleeves["SLEEVE"].cash == pytest.approx(27_000.0)
    assert all(o["filled"] == o["qty"] for o in row["orders"] if o["symbol"] != "BOXX")
    assert [s for s, _ in r.orders()].count("BOXX") == 1      # not re-sent
    sound(r)


# --- M8 ---------------------------------------------------------------------------------------------
def test_m8_an_unresolved_order_is_never_guessed_at(tmp_path):
    r = live_rig(tmp_path)
    r.venue.hold.add("TECL")
    r.venue.cancel_raises = True
    r.tick("15:55:05")
    r.tick("15:59:00")
    run = r.m.state["run"]
    assert run is not None and run["orders"][f"mirror-{DAY}-B-TECL"].get("stuck")
    assert r.m.book.positions().get("TECL") is None and r.m.state["last_session"] is None
    assert any("UNRESOLVED" in a for a in r.red())
    r.brain.make = lambda now: payload(now, session="2026-11-11")
    n = len(r.orders())
    r.tick("15:55:05", day="2026-11-11")
    assert len(r.orders()) == n and r.m.state["run"]["session"] == DAY       # nothing new is planned over it
    r.venue.cancel_raises = False                             # the venue answers at last: cancelled, nothing filled
    r.tick("15:55:10", day="2026-11-11")
    assert r.m.state["run"] is None and r.m.state["last_session"] == DAY
    assert r.m.book.positions().get("TECL") is None
    sound(r)


# --- M9 ---------------------------------------------------------------------------------------------
def test_m9_the_threshold_sleeve_holds_inside_its_corridor_and_trades_outside(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:55:05")
    k0 = dict(r.m.book.sleeves["KMLM"].shares)
    drift = dict(PX, SOXL=PX["SOXL"] * 1.25)                  # SOXL +25%: its weight moves ~4.6pp, inside 10pp
    r.brain.make = lambda now: payload(now, prices=drift, session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")
    row = r.m.state["last_run"]["sleeves"]["KMLM"]
    assert row["action"] == "hold" and "inside the corridor" in row["reason"] and r.m.book.sleeves["KMLM"].shares == k0
    far = dict(PX, SOXL=PX["SOXL"] * 2.0)                     # SOXL doubles: ~17pp away
    r.brain.make = lambda now: payload(now, prices=far, session="2026-11-12")
    r.tick("15:55:05", day="2026-11-12")
    row = r.m.state["last_run"]["sleeves"]["KMLM"]
    assert row["action"] == "trade" and r.m.book.sleeves["KMLM"].shares["SOXL"] < k0["SOXL"]
    daily = Rig(tmp_path / "x")                               # the twin: the same drift on a daily sleeve trades
    daily.brain.make = lambda now: payload(now, rules={})
    daily.tick("15:55:05")
    d0 = dict(daily.m.book.sleeves["KMLM"].shares)
    daily.brain.make = lambda now: payload(now, prices=drift, session="2026-11-11", rules={})
    daily.tick("15:55:05", day="2026-11-11")
    assert daily.m.book.sleeves["KMLM"].shares != d0


def test_m9_an_unknown_rule_leaves_the_sleeve_alone(tmp_path):
    r = Rig(tmp_path)
    r.brain.make = lambda now: payload(now, rules={"KMLM": ("weekly", None)})
    r.tick("15:55:05")
    assert r.m.state["last_run"]["sleeves"]["KMLM"]["action"] == "skip" and r.m.book.sleeves["KMLM"].shares == {}
    assert r.m.book.sleeves["HG"].shares


# --- M10 --------------------------------------------------------------------------------------------
def test_m10_halted_nothing_is_sent_and_the_halt_survives_a_restart(tmp_path):
    r = live_rig(tmp_path)
    r.m.halt("operator")
    r.tick("15:55:05")
    r.tick("15:58:30")
    assert r.orders() == [] and r.m.state["last_session"] is None
    r.boot()
    assert r.m.halt_state()["halted"] is True
    r.tick("15:56:00")
    assert r.orders() == []
    assert r.m.resume()["was_halted"] is True
    r.tick("15:56:30")
    assert r.orders() and r.m.state["last_session"] == DAY    # the twin: resumed inside the window, it trades


def test_m10_a_halt_mid_run_settles_what_is_in_flight_and_sends_nothing_new(tmp_path):
    r = invested(tmp_path)
    t2 = dict(T1, HG={"TQQQ": 1.0}, SLEEVE={"TQQQ": 1.0})
    r.brain.make = lambda now: payload(now, t2, session="2026-11-11")
    r.venue.hold.add("BIL")
    r.venue.partial["BIL"] = 50
    r.tick("15:55:05", day="2026-11-11")
    assert r.m.state["run"]["phase"] == "sells"
    n = len(r.orders())
    r.m.halt("operator")
    r.tick("15:55:30", day="2026-11-11")
    row = r.m.state["last_run"]
    assert row["outcome"] == "aborted" and len(r.orders()) == n               # no buy went out
    bil = next(o for o in row["orders"] if o["symbol"] == "BIL")
    assert bil["filled"] == 50
    assert r.m.state["run"] is None
    sound(r)


# --- M11 --------------------------------------------------------------------------------------------
def test_m11_kill_flattens_every_share_and_only_what_the_account_holds(tmp_path):
    r = invested(tmp_path)
    held = dict(r.m.book.positions())
    h = r.m.halt("kill", flatten=True)
    assert h["halted"] and h["flatten"] and not h["flatten_done"]
    assert r.m.next_wait() == 5.0
    r.tick("15:56:00")
    assert r.m.book.positions() == {} and r.m.halt_state()["flatten_done"] is True
    sold = {s: -q for s, q in r.orders()[5:]}
    assert sold == held
    assert r.m.book.cash() == pytest.approx(r.venue.cash, abs=0.01)
    sound(r)
    r.tick("15:57:00")
    assert len(r.orders()) == 5 + len(held)                   # flattened once
    assert r.m.halt_state()["halted"] is True                 # ... and still halted until /resume


def test_m11_flatten_never_sells_more_than_the_account_holds(tmp_path):
    r = invested(tmp_path)
    book_bil = r.m.book.positions()["BIL"]
    r.venue._positions["BIL"] = book_bil - 40                 # someone sold 40 by hand
    r.m.halt("kill", flatten=True)
    r.tick("15:56:00")
    assert dict((s, q) for s, q in r.orders()[5:])["BIL"] == -(book_bil - 40)
    assert r.venue.stock_position("BIL") == 0                 # flat, not short
    assert r.m.book.positions() == {"BIL": 40}                # the book keeps what it could not prove
    assert any("STILL HELD" in a for a in r.alerts)


def test_m11_flatten_waits_for_the_session_and_resume_cancels_it(tmp_path):
    r = invested(tmp_path)
    n = len(r.orders())
    r.m.halt("kill", flatten=True)
    r.tick("17:30:00")                                        # after the close: nothing is sent
    assert len(r.orders()) == n and not r.m.halt_state()["flatten_done"]
    r.m.resume()                                              # the operator thinks again before the open
    r.tick("09:31:00", day="2026-11-11")
    assert len(r.orders()) == n and r.m.halt_state()["flatten_done"] is True and r.m.book.positions()
    r.m.halt("kill", flatten=True)                            # the twin: left alone, it goes at the open
    r.clock.now = at("09:31:01", "2026-11-11")
    r.m.halt("kill", flatten=True)
    r.tick("09:31:05", day="2026-11-11")
    assert r.m.book.positions() == {}


def test_m11_a_flatten_survives_a_restart_mid_way(tmp_path):
    r = invested(tmp_path)
    r.m.halt("kill", flatten=True)
    r.venue.crash_after.add("PULS")
    with pytest.raises(Crash):
        r.tick("15:56:00")
    r.venue.crash_after.clear()
    r.boot()
    r.tick("15:56:10")
    assert r.m.book.positions() == {} and r.venue.positions_snapshot()["stocks"] == {}
    assert sorted(s for s, _ in r.orders()[5:]) == ["BIL", "BOXX", "PULS", "SOXL", "TECL"]    # each sold once
    sound(r)


def test_m11_the_paper_book_halts_but_has_nothing_to_flatten(tmp_path):
    r = Rig(tmp_path)
    r.tick("15:55:05")
    h = r.m.halt("kill", flatten=True)
    assert h["halted"] and not h.get("flatten")
    r.tick("15:56:00")
    assert r.m.book.positions()


# --- M12 --------------------------------------------------------------------------------------------
def test_m12_a_mismatch_that_persists_halts_a_live_book(tmp_path):
    r = invested(tmp_path)
    r.venue._positions["TECL"] -= 5                           # the account no longer holds what the book says
    r.tick("15:56:00")
    assert r.m.state["check"]["strikes"] == 1 and not r.m.halt_state().get("halted")
    r.tick("15:56:10")                                        # too soon to count as a second look
    assert r.m.state["check"]["strikes"] == 1
    r.tick("15:57:00")
    assert r.m.halt_state()["halted"] is True and "TECL" in r.m.halt_state()["reason"]
    assert any("does NOT hold" in a for a in r.red())


def test_m12_a_mismatch_that_clears_does_not_halt(tmp_path):
    r = invested(tmp_path)
    real = r.venue._positions["TECL"]
    r.venue._positions["TECL"] = real - 5                     # a position report in flight
    r.tick("15:56:00")
    r.venue._positions["TECL"] = real
    r.tick("15:57:00")
    assert r.m.state["check"]["done"] is True and not r.m.halt_state().get("halted")
    r.tick("15:58:00")
    assert not r.red()


# --- M13 --------------------------------------------------------------------------------------------
def test_m13_an_unreadable_state_file_is_never_a_fresh_book(tmp_path):
    r = invested(tmp_path)
    path = r.m.cfg.state_path
    open(path, "w").write("{not json")
    r.boot()
    assert r.m.archived_state and r.m.halt_state()["halted"] is True
    assert r.m.book.sleeves == {}
    n = len(r.orders())
    r.tick("15:56:00")
    assert len(r.orders()) == n and r.m.book.sleeves == {}    # halted: not even re-seeded
    assert any(f.startswith("mirror.json.unreadable-") for f in os.listdir(tmp_path))


def test_m13_another_books_file_is_refused(tmp_path):
    d = Rig(tmp_path)
    d.tick("15:55:05")
    os.replace(d.m.cfg.state_path, tmp_path / "mirror.json")  # the paper book's file where the live one is read
    r = Rig(tmp_path, live=True)
    assert r.m.archived_state and "not 'live'" in r.m.archived_state and r.m.halt_state()["halted"] is True


def test_m13_the_save_is_atomic_and_round_trips(tmp_path):
    r = invested(tmp_path)
    assert not os.path.exists(r.m.cfg.state_path + ".tmp")
    disk = json.load(open(r.m.cfg.state_path))
    assert mc.Book.from_dict(disk["book"]).to_dict() == r.m.book.to_dict()
    lines = [json.loads(x) for x in open(r.m.cfg.state_path + ".journal.jsonl")]
    assert {x["event"] for x in lines} >= {"sleeve_seeded", "plan", "fill", "session"}
    assert sum(x["event"] == "fill" for x in lines) == 5


# --- M14 --------------------------------------------------------------------------------------------
def test_m14_a_transfer_rides_the_next_plan_and_is_zero_sum(tmp_path):
    r = invested(tmp_path)
    eq0 = mc.snapshot(r.m.book, PX)
    req = r.m.request_transfer("HG", "HARV", 5_000.0, "POLICY op 3")
    assert req["id"].startswith("transfer-")
    r.boot()                                                  # the inbox is on disk: a restart keeps it
    r.brain.make = lambda now: payload(now, session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")
    eq1 = mc.snapshot(r.m.book, PX)
    assert eq1["sleeves"]["HG"]["equity"] == pytest.approx(eq0["sleeves"]["HG"]["equity"] - 5_000.0, abs=1.0)
    assert eq1["sleeves"]["HARV"]["equity"] == pytest.approx(eq0["sleeves"]["HARV"]["equity"] + 5_000.0, abs=1.0)
    assert eq1["equity"] == pytest.approx(eq0["equity"], abs=0.01)
    assert r.m.state["last_run"]["transfers"][0]["status"] == "moved" and r.m.state["requests"] == []
    r.brain.make = lambda now: payload(now, session="2026-11-12")
    r.tick("15:55:05", day="2026-11-12")
    assert r.m.state["last_run"]["transfers"] == []           # applied once
    sound(r)
    with pytest.raises(ValueError):
        r.m.request_transfer("HG", "HG", 10)
    with pytest.raises(ValueError):
        r.m.request_transfer("HG", "NOPE", 10)
    with pytest.raises(ValueError):
        r.m.request_transfer("HG", "HARV", -5)


def test_m14_a_credit_is_applied_once_and_only_from_cash_the_account_has(tmp_path):
    r = invested(tmp_path)
    # round 3 (D-04): the book is seeded to its cap; a credit beyond it is meant, so it is forced
    # (force lifts the capital cap only: the account's own cash still bounds the credit, as below)
    c0 = r.m.book.sleeves["HARV"].cash
    r.m.request_credit("HARV", 61.20, "PULS dividend", force=True)
    r.brain.make = lambda now: payload(now, session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")
    assert any("REFUSED" in n for n in r.m.state["last_run"]["notes"])        # the account never received it
    assert r.m.book.sleeves["HARV"].cash == pytest.approx(c0) and r.red()
    r.venue.cash += 61.20                                     # the twin: the dividend is in the account
    r.m.request_credit("HARV", 61.20, "PULS dividend", force=True)
    r.brain.make = lambda now: payload(now, session="2026-11-12")
    r.tick("15:55:05", day="2026-11-12")
    eq = mc.snapshot(r.m.book, PX)["sleeves"]["HARV"]
    assert any("HARV credited $61.20" in n for n in r.m.state["last_run"]["notes"])
    assert eq["cash"] + sum(q * PX[s] for s, q in eq["shares"].items()) == pytest.approx(15_000.0 + 61.20, abs=0.01)
    r.brain.make = lambda now: payload(now, session="2026-11-13")
    r.tick("15:55:05", day="2026-11-13")
    assert not r.m.state["last_run"]["notes"]                 # once
    sound(r)


# --- M15 --------------------------------------------------------------------------------------------
def test_m15_live_seeding_needs_the_accounts_cash(tmp_path):
    r = Rig(tmp_path, live=True, venue_cash=50_000.0)         # the account covers HG and HARV, not all four
    r.tick("15:00")
    assert set(r.m.book.sleeves) == {"HG", "HARV"}            # 29k + 15k fit; KMLM and SLEEVE do not
    assert r.m.book.cash() == pytest.approx(44_000.0) and r.red()
    r.venue.cash = 100_000.0
    r.tick("15:01")
    assert set(r.m.book.sleeves) == set(ENGINES)
    r2 = Rig(tmp_path / "n", live=True)
    r2.venue.cash_claim = False                               # no claim: nothing is seeded on a guess
    r2.tick("15:00")
    assert r2.m.book.sleeves == {}


def test_m15_a_removed_engine_is_frozen_live_and_dropped_on_paper(tmp_path):
    r = invested(tmp_path)
    r.engines = ("HG", "KMLM", "SLEEVE")                      # HARV taken out of MIRROR_LIVE_ENGINES
    r.boot()
    harv = dict(r.m.book.sleeves["HARV"].shares)
    r.brain.make = lambda now: payload(now, dict(T1, HARV={"BIL": 1.0}), session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")
    assert r.m.state["frozen"] == ["HARV"] and r.m.book.sleeves["HARV"].shares == harv      # kept, never traded
    assert any("FROZEN" in a for a in r.red())
    sound(r)
    d = Rig(tmp_path / "d")
    d.tick("15:55:05")
    d.engines = ("HG", "KMLM", "SLEEVE")
    d.boot()
    d.tick("15:56:00")
    assert "HARV" not in d.m.book.sleeves


# --- M16 --------------------------------------------------------------------------------------------
def test_m16_a_commission_reported_late_is_debited_once(tmp_path):
    r = live_rig(tmp_path)
    r.venue.commission = 1.0
    r.venue.report_commission = False
    r.tick("15:55:05")
    assert r.m.book.cash() == pytest.approx(r.venue.cash + 5.0, abs=0.01)     # five orders, $1 each, not yet known
    assert len(r.m.state["commission_pending"]) == 5
    r.venue.report_commission = True
    r.tick("15:56:00")
    assert r.m.book.cash() == pytest.approx(r.venue.cash, abs=0.01) and r.m.state["commission_pending"] == []
    r.tick("16:30:00")
    assert r.m.book.cash() == pytest.approx(r.venue.cash, abs=0.01)           # once
    r2 = live_rig(tmp_path / "t")                             # the twin: reported with the fill, booked with it
    r2.venue.commission = 1.0
    r2.tick("15:55:05")
    assert r2.m.state["commission_pending"] == [] and r2.m.book.cash() == pytest.approx(r2.venue.cash, abs=0.01)


def test_m16_a_commission_never_reported_is_dropped_loudly_after_three_days(tmp_path):
    r = live_rig(tmp_path)
    r.venue.commission = 1.0
    r.venue.report_commission = False
    r.tick("15:55:05")
    ids = sorted(p["id"] for p in r.m.state["commission_pending"])
    assert len(ids) == 5
    r.brain.shut = True                                       # (no further session: only the true-up runs)
    r.tick("15:56:00")
    r.tick("15:56:00", day="2026-11-12")                      # two days on: still asked for, nothing said
    assert len(r.m.state["commission_pending"]) == 5 and not any("never reported" in a for a in r.alerts)
    r.venue.forgotten.update(ids)                             # the venue no longer answers for those orders
    r.m.state["last_session"] = "2026-11-13"                  # (reach the post-session path on the 13th)
    r.brain.shut = False
    r.tick("16:30:00", day="2026-11-13")                      # three days after the fills
    assert r.m.state["commission_pending"] == []
    said = [a for a in r.alerts if "never reported" in a]
    assert len(said) == 5 and all(any(i in a for a in said) for i in ids) and all("/mirror/credit" in a for a in said)
    assert any(x["event"] == "commission_dropped" for x in r.journal())


# --- M17 --------------------------------------------------------------------------------------------
def test_m17_a_fill_with_no_reported_price_is_booked_at_the_limit_or_the_reference_loudly(tmp_path):
    r = live_rig(tmp_path)
    r.venue.no_price.add("BIL")
    r.tick("15:55:05")
    bil = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "BIL")
    limit = r.venue.limits[f"mirror-{DAY}-B-BIL"]
    # a BUY is booked at its LIMIT, the most it can have cost: the book's cash can never exceed the account's
    assert bil["price"] == limit > PX["BIL"] and bil["filled"] == bil["qty"]
    assert any("LIMIT price" in a and "BIL" in a for a in r.red()) and not any("REFERENCE price" in a for a in r.red())
    assert r.m.book.cash() <= r.venue.cash and r.venue.cash - r.m.book.cash() == pytest.approx(bil["qty"] * (limit - PX["BIL"]))
    assert [x for x in r.journal() if x["event"] == "fill" and x["symbol"] == "BIL"][0]["price_estimated"] is True
    r.tick("15:56:00")
    assert not r.m.halt_state().get("halted")                 # the shares are right; only the cash basis is flagged
    r.venue.no_price = {"BIL"}
    r.brain.make = lambda now: payload(now, dict(T1, HG={"TQQQ": 1.0}), session="2026-11-11")
    r.tick("15:55:05", day="2026-11-11")                      # the twin: a SELL has no limit - its reference, flagged
    sold = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "BIL")
    assert sold["side"] == mc.SELL and sold["price"] == PX["BIL"]
    assert any("REFERENCE price" in a and "BIL" in a for a in r.red())


# --- M18 --------------------------------------------------------------------------------------------
def test_m18_the_cadence_the_book_asks_for(tmp_path):
    r = live_rig(tmp_path)
    r.tick("15:50:05")
    assert r.m.next_wait() == pytest.approx(260.2, abs=0.01)  # wake exactly at decision (15:54:00) + offset (25 s)
    r.venue.hold.add("BIL")
    r.tick("15:55:05")
    assert r.m.state["run"] is not None and r.m.next_wait() == 2.0
    r.venue.release("BIL")
    r.tick("15:55:10")
    assert r.m.state["run"] is None and r.m.next_wait() is None
    r.m.halt("x")
    assert r.m.next_wait() is None


def test_m18_a_woken_loop_interrupts_the_wait(tmp_path):
    r = Rig(tmp_path)
    r.brain.fail = "deadline"
    r.clock.interrupt = True                                  # /kill poked the loop
    r.tick("15:55:05")
    assert len(r.brain.calls) == 1                            # one read, then straight back to the loop
    assert r.m.state["last_session"] is None


# --- M19 --------------------------------------------------------------------------------------------
class S:
    mirror_weights = "HG:0.29,KMLM:0.29,SLEEVE:0.27,HARV:0.15"
    mirror_capital_usd = 118_000.0
    mirror_live_engines = "HARV"
    mirror_brain_url = "https://brain"
    mirror_api_token = "t"
    mirror_decide_offset_s = 25.0
    mirror_cancel_before_close_s = 60.0
    mirror_quote_band = 0.015
    mirror_dividend_rule = "composer"
    poll_seconds = 300
    blend_enabled = False
    tws_userid = "u"
    tws_password = "p"
    dry_run = False


def test_m19_build_splits_live_and_paper(tmp_path):
    s = S()
    s.mirror_state_path, s.mirror_dry_state_path = str(tmp_path / "l.json"), str(tmp_path / "d.json")
    books = mm.build(s)
    assert books["live"].cfg.engines == ("HARV",) and books["live"].cfg.live is True
    assert books["dry"].cfg.engines == ("HG", "KMLM", "SLEEVE") and books["dry"]._dry is not None
    assert books["live"].cfg.capital["HARV"] == pytest.approx(17_700.0)
    assert books["live"].brain is books["dry"].brain
    s.dry_run = True                                          # the service is not trading for real: all paper
    books = mm.build(s)
    assert set(books) == {"dry"} and books["dry"].cfg.engines == ENGINES
    s.dry_run, s.mirror_live_engines = False, ""
    assert set(mm.build(s)) == {"dry"}
    s.mirror_live_engines = "HG,KMLM,SLEEVE,HARV"
    assert set(mm.build(s)) == {"live"}
    s.mirror_live_engines = "NOPE"
    with pytest.raises(ValueError):
        mm.build(s)
    s.mirror_live_engines, s.mirror_weights = "", "HG:0.5,KMLM:0.4"
    with pytest.raises(ValueError):
        mm.build(s)


def test_m19_settings_outside_their_range_are_clamped_and_said(tmp_path, caplog):
    s = S()
    s.mirror_state_path, s.mirror_dry_state_path = str(tmp_path / "l.json"), str(tmp_path / "d.json")
    s.mirror_cancel_before_close_s, s.mirror_decide_offset_s, s.mirror_quote_band = 240.0, 900.0, 0.5
    said = []
    with caplog.at_level("WARNING"):
        books = mm.build(s, alert=said.append)
    cfg = books["live"].cfg
    assert (cfg.cancel_before_close_s, cfg.decide_offset_s, cfg.quote_band) == (120.0, 120.0, 0.05)
    assert "cancel_before_close_s" in caplog.text and len(books["live"].clamped) == 3
    assert any("clamped" in a for a in said) and books["live"].view()["settings_clamped"]
    s.mirror_cancel_before_close_s, s.mirror_decide_offset_s, s.mirror_quote_band = 5.0, -3.0, 0.0
    cfg = mm.build(s)["dry"].cfg
    assert (cfg.cancel_before_close_s, cfg.decide_offset_s, cfg.quote_band) == (20.0, 0.0, 0.001)
    s.mirror_cancel_before_close_s, s.mirror_decide_offset_s, s.mirror_quote_band = 60.0, 25.0, 0.015
    assert mm.build(s)["live"].clamped == []                  # the twin: defaults are inside the range
    s.mirror_dividend_rule = "nope"
    with pytest.raises(ValueError):
        mm.build(s)


# --- M20 --------------------------------------------------------------------------------------------
def test_m20_the_brain_client(monkeypatch):
    seen = []
    T = "2026-11-10T20:54:00Z"
    body = {"schema": 2, "kind": mm.INTENTS_KIND, "pinned": True, "asof_utc": T, "built_utc": "2026-11-10T20:54:21Z",
            "decision_bar": {"end_utc": T, "spy_utc": T, "complete": True}}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append((url, params, headers))
        req = httpx.Request("GET", url)
        if headers.get("X-API-Token") != "tok":
            return httpx.Response(401, json={"error": "unauthorized"}, request=req)
        if url.endswith("/mirror/session"):
            return httpx.Response(200, json={"kind": mm.SESSION_KIND}, request=req)
        if (params or {}).get("after") == "early":
            return httpx.Response(503, json={"error": "decision bar not published yet",
                                             "detail": "SPY's 15:53 bar is missing"}, request=req)
        if (params or {}).get("after") == "early-bare":
            return httpx.Response(503, text="upstream", request=req)
        if (params or {}).get("after") == "adhoc":
            return httpx.Response(200, json=dict(body, pinned=False, decision_bar=None, asof_utc="adhoc"), request=req)
        return httpx.Response(200, json=body, request=req)
    monkeypatch.setattr(mm.httpx, "get", fake_get)
    b = mm.HttpBrain(" https://brain/ ", " tok ")
    assert b.session() == ({"kind": mm.SESSION_KIND}, "ok")
    p, why = b.intents(T)
    assert why == "ok" and seen[-1] == ("https://brain/mirror/intents", {"after": T}, {"X-API-Token": "tok"})
    n = len(seen)
    assert b.intents(T)[0] is p and len(seen) == n            # the second book reuses the read (the SAME object)
    said = "http_503: decision bar not published yet — SPY's 15:53 bar is missing"       # R6: the body's error and detail
    assert b.intents("early") == (None, said)                 # the bar is not published yet: the manager retries
    assert b.intents("early") == (None, said) and len(seen) == n + 2           # ... and a 503 is never kept
    assert b.intents("early-bare") == (None, "http_503")      # a 503 whose body is not JSON: still a 503
    n += 1
    q, _ = b.intents("adhoc")                                 # nor is an unpinned payload
    assert q["pinned"] is False and len(seen) == n + 3
    b.intents("adhoc")
    assert len(seen) == n + 4
    assert mm.HttpBrain("https://brain", "wrong").session() == (None, "auth")
    assert mm.HttpBrain("", "tok").session() == (None, "no_url")
    n = len(seen)                                             # N4: the token never rides plain http ...
    for url in ("http://brain", "http://brain.example.com:8080/", "ftp://brain", "brain", "http://localhost.evil.example",
                "http://127.0.0.1.evil.example"):
        b = mm.HttpBrain(url, "tok")
        assert b.session() == (None, "insecure_url") and b.intents(T) == (None, "insecure_url"), url
    assert len(seen) == n                                     # ... NOTHING was sent
    for url in ("http://localhost:8000", "http://127.0.0.1:8000/", "https://brain.example.com"):      # the twins
        assert mm.HttpBrain(url, "tok").session() == ({"kind": mm.SESSION_KIND}, "ok"), url
    assert len(seen) == n + 3

    def boom(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(mm.httpx, "get", boom)
    assert mm.HttpBrain("https://brain", "tok").intents("x") == (None, "transport")
    monkeypatch.setattr(mm.httpx, "get", lambda *a, **k: httpx.Response(200, text="[1]", request=httpx.Request("GET", "http://b")))
    assert mm.HttpBrain("https://brain", "tok").session() == (None, "decode")


def test_view_and_health_never_raise(tmp_path):
    r = invested(tmp_path)
    v = r.m.view(history=5)
    assert v["mode"] == "live" and v["book"]["positions"] == r.m.book.positions() and len(v["history"]) == 1
    assert v["book"]["equity"] == pytest.approx(100_000.0, rel=0.002)
    h = r.m.health()
    assert h["halted"] is False and h["last_session"] == DAY and h["brain_ok"] is True
    json.dumps(v), json.dumps(h)
    r.m._view = None
    assert "error" in r.m.health() or r.m.health()
