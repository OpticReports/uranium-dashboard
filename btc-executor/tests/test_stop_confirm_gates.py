"""Gates for the post-placement stop confirm (2026-11-14).

THE INCIDENT. 2026-11-14 04:01:10 UTC, at the 4-hourly trail ratchet of the
live trend short (0.45387 BTC): the executor placed T-1794182400-S72638-45,
Hyperliquid's exchange accepted it, and the confirm read a fraction of a
second later found NO RECORD of it on the info node that answered
(`unknownOid`). hl.order_status reports that as CANCELLED / 0, so
_maintain_stop took a healthy stop for a dead one: it counted a failure,
CANCELLED the stop itself (cancel-before-clear) 1.0 s after placement,
cleared the refs and paged stop_unconfirmed. The next poll re-placed -46
23 s later. The venue's own historicalOrders show the same self-cancel on
8 of 54 executor stop placements since 2026-09-03, three of them in a row
on 2026-09-18 (T-1789747200-S76265-15/16/17): one more and STOP_UNPLACEABLE
would have halted the executor and flattened a healthy long.

THE FIX (owner-approved scope: "before treating a just-placed stop as dead,
re-check its status a few times over about 3 seconds; keep everything else
as is, including cancel-before-clear when it really is dead"):
  * hl.order_status still answers CANCELLED / 0 for a reply with no venue
    record, but tags it raw=NO_RECORD_RAW ("unknownOid"), so the one caller
    that has just placed the order can tell "not visible yet" from a
    terminal record. Every other caller is unchanged;
  * mirror._confirm_placed replaces the single read at the stop placement:
    OPEN/FILLED on any read confirms at once; a CANCELLED that carries a
    venue record (any other raw, or none at all - Coinbase, DryRun) is final
    at once; no record / UNKNOWN / None / a read that raises is re-read
    after each delay in STOP_CONFIRM_DELAYS_S = (0.5, 0.75, 0.75, 1.0) - at
    most 3.0 s of sleep and 4 extra reads - and then goes down the OLD path
    unchanged (one count per poll, cancel-before-clear, stop_unconfirmed,
    STOP_REPLACE_MAX, the STOP_UNPLACEABLE halt);
  * a late confirm logs INFO stop_confirm_lag (never paged); the
    stop_unconfirmed page keeps its old text and appends what the confirm
    saw (reads, seconds, last raw, and the exchange's own acceptance that
    hl.place_stop now returns - evidence only, it confirms nothing).

GATE   fails on 93f74553 (whose app/ is the live build 709bf17), passes with
       the fix. Two gates added after the independent review gate the FIX'S
       FIRST CUT instead (its ack parser could raise): they say so in their
       docstrings, and the odd-ack gate passes on 93f74553 by design.
TWIN   passes on both: a stop the venue genuinely refuses or kills still
       takes the old path, and nothing else moved.
LATENT strict xfail on both: the same lag at two placement sites OUTSIDE
       the approved scope (pullback maker entry, re-establish). XPASS (a
       failure) the day one of them is fixed - then remove the marker.

No real SDK and no network anywhere in this file: the Hyperliquid tests
build the REAL HyperliquidVenue through its real __init__ over a fake SDK
installed into sys.modules, whose info node lags its exchange by N reads per
order. Run from btc-executor/:
    python -m pytest -q -p no:cacheprovider tests/test_stop_confirm_gates.py
"""
from __future__ import annotations

import sys
import time as _time
import types

import pytest

from app import mirror
from app.hl import derive_cloid
from test_executor_gates import (FakeVenue, mkexec, _hold, _long_pos, NOW,
                                 target, _BlipStatusVenue)
import test_netting_gates as tng

# the base has no window: () there, the approved schedule here
DELAYS = tuple(getattr(mirror, "STOP_CONFIRM_DELAYS_S", ()))
BUDGET_S = 3.0          # "a few times over about 3 seconds" (owner-approved)
NO_RECORD = "unknownOid"
# what hl.order_status answers for a reply with no record, as the mirror
# sees it (the base answered the same, minus `raw`)
MISS = {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None,
        "raw": NO_RECORD}
FILLED = {"status": "FILLED", "filled_qty": 0.01, "avg_price": 74_000.0}


# ------------------------------------------------------------------ fixtures
class _Clock:
    """Stands in for the `time` module INSIDE app.mirror only. Records every
    sleep the executor asks for and advances a virtual clock instead of
    sleeping; real=True also sleeps for real (the measured twin)."""

    def __init__(self, real: bool = False):
        self.sleeps: list[float] = []
        self.offset = 0.0
        self.real = real

    def sleep(self, s):
        s = float(s)
        self.sleeps.append(s)
        if self.real:
            _time.sleep(s)
        else:
            self.offset += s

    def monotonic(self):
        return _time.monotonic() + self.offset

    def time(self):
        return _time.time() + self.offset

    def __getattr__(self, name):
        return getattr(_time, name)


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(mirror, "time", c)
    return c


@pytest.fixture
def pages(monkeypatch):
    """Every phone page the executor sends (app.alerts.send), captured."""
    from app import alerts
    sent: list[str] = []
    monkeypatch.setattr(alerts, "send", lambda m: sent.append(m))
    return sent


def _kinds(ex):
    return [e["kind"] for e in ex.state.events]


def _events(ex, kind):
    return [e for e in ex.state.events if e["kind"] == kind]


def _msgs(ex, kind):
    return [e["msg"] for e in _events(ex, kind)]


# ------------------------------------------- a fake Hyperliquid SDK, linked
MAIN = "0xMAIN0000000000000000000000000000000000ac"


class _Acct:
    # the agent wallet that signs for MAIN (as live: a different address)
    address = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    @staticmethod
    def from_key(k):
        return _Acct()


class _Cloid:
    def __init__(self, raw):
        if not (isinstance(raw, str) and raw.startswith("0x")
                and len(raw) == 34):
            raise TypeError(f"cloid is not 16 bytes: {raw!r}")
        self._raw = raw

    @staticmethod
    def from_str(s):
        return _Cloid(s)

    def to_raw(self):
        return self._raw


_UNSET = object()


class _LagInfo:
    """Hyperliquid's INFO side. An order the exchange has accepted can be
    unknown to it (`unknownOid`) for its first N status reads - the
    read-after-write lag of 2026-11-14 - after which it answers with the
    order's record, as the live API does for a cancelled order too (a
    public orderStatus read of the incident's cloid answers 'canceled')."""

    def __init__(self, *a, **kw):
        self.net = 0.0
        self.mid = 66_900.0
        self.records: dict[str, dict] = {}   # raw cloid -> {"order","status"}
        self.lag: dict[str, int] = {}        # raw cloid -> no-record replies
        self.lag_next: list[int] = []        # lags for the NEXT trigger orders
        self.reads: dict[str, int] = {}      # raw cloid -> status reads
        self.odd_reply = _UNSET              # a non-record reply, once

    def meta(self, dex=""):
        return {"universe": [{"name": "BTC", "szDecimals": 5,
                              "maxLeverage": 40}]}

    def user_state(self, address, dex=""):
        rows = ([] if abs(self.net) < 1e-12 else
                [{"position": {"coin": "BTC", "szi": f"{self.net:.5f}"}}])
        return {"marginSummary": {"accountValue": "100000.0"},
                "assetPositions": rows}

    def all_mids(self, dex=""):
        return {"BTC": str(self.mid)}

    def query_user_abstraction_state(self, user):
        return "default"                  # not unified: equity() = perp

    def extra_agents(self, user):
        return [{"name": "BTC EXECUTOR", "address": _Acct.address,
                 "validUntil": 1_803_483_076_101}]

    def user_role(self, user):
        return {"role": "agent", "data": {"user": MAIN}}

    def query_order_by_cloid(self, user, cloid):
        raw = cloid.to_raw()
        self.reads[raw] = self.reads.get(raw, 0) + 1
        if self.odd_reply is not _UNSET:
            r, self.odd_reply = self.odd_reply, _UNSET
            return r
        if self.lag.get(raw, 0) > 0:
            self.lag[raw] -= 1
            return {"status": "unknownOid"}
        rec = self.records.get(raw)
        if rec is None:
            return {"status": "unknownOid"}
        return {"status": "order",
                "order": {"order": dict(rec["order"]),
                          "status": rec["status"], "statusTimestamp": 0}}

    def open_orders(self, address, dex=""):
        return [dict(r["order"]) for r in self.records.values()
                if r["status"] == "open"]

    def user_fills(self, address):
        return []


class _LinkedExchange:
    """Hyperliquid's EXCHANGE side: the truth. Orders land in the info's
    records at once (its lag only delays what the info side SAYS); trigger
    orders rest, IOCs fill at mid, reduce-only clamps to the position."""

    def __init__(self, *a, **kw):
        self.info: _LagInfo | None = None   # bound once the venue is built
        self.sent: list[dict] = []
        self.cancelled: list[str] = []
        self.oid = 604_660_860_000
        self.reply_style = "resting"        # what a trigger order answers
        self.statuses_as_object = False     # `statuses` an object, not a list
        self.kill_with = None               # the venue kills new stops: word

    def order(self, name, is_buy, sz, limit_px, order_type,
              reduce_only=False, cloid=None, builder=None):
        self.oid += 1
        raw = cloid.to_raw()
        trig = (order_type or {}).get("trigger")
        o = {"coin": name, "side": "B" if is_buy else "A",
             "limitPx": str(limit_px), "sz": str(sz), "origSz": str(sz),
             "oid": self.oid, "cloid": raw, "reduceOnly": reduce_only,
             "isTrigger": bool(trig),
             "triggerPx": str(trig["triggerPx"]) if trig else "0.0",
             "orderType": "Stop Market" if trig else "Limit"}
        self.sent.append(o)
        if trig:
            self.info.records[raw] = {"order": o,
                                      "status": self.kill_with or "open"}
            if self.info.lag_next:
                self.info.lag[raw] = self.info.lag_next.pop(0)
            s0 = ({"resting": {"oid": self.oid}}
                  if self.reply_style == "resting" else self.reply_style)
            return {"status": "ok", "response": {"type": "order", "data": {
                "statuses": s0 if self.statuses_as_object else [s0]}}}
        q = float(sz)
        if reduce_only:
            reduces = abs(self.info.net) > 1e-12 \
                and (self.info.net > 0) != is_buy
            q = min(q, abs(self.info.net)) if reduces else 0.0
        self.info.net = round(self.info.net + (q if is_buy else -q), 8)
        self.info.records[raw] = {"order": dict(o, sz="0.0"),
                                  "status": "filled"}
        return {"status": "ok", "response": {"type": "order", "data": {
            "statuses": [{"filled": {"totalSz": str(q),
                                     "avgPx": str(self.info.mid),
                                     "oid": self.oid}}]}}}

    def cancel_by_cloid(self, name, cloid):
        raw = cloid.to_raw()
        self.cancelled.append(raw)
        rec = self.info.records.get(raw)
        if rec and rec["status"] == "open":
            rec["status"] = "canceled"
            return {"status": "ok", "response": {"type": "cancel", "data": {
                "statuses": ["success"]}}}
        return {"status": "ok", "response": {"type": "cancel", "data": {
            "statuses": [{"error": "Order was never placed, already "
                                   "canceled, or filled."}]}}}

    def bulk_cancel_by_cloid(self, reqs):
        for r in reqs:
            self.cancel_by_cloid(r["coin"], r["cloid"])
        return {"status": "ok"}

    def cancel(self, name, oid):
        return {"status": "ok"}


@pytest.fixture
def fake_sdk(monkeypatch):
    """Install the fake SDK for the duration of one test (the suite must
    never need the real one: hl.py imports it lazily for that reason)."""
    types_mod = types.ModuleType("hyperliquid.utils.types")
    types_mod.Cloid = _Cloid
    const_mod = types.ModuleType("hyperliquid.utils.constants")
    const_mod.MAINNET_API_URL = "https://api.hyperliquid.xyz"
    const_mod.TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
    utils_mod = types.ModuleType("hyperliquid.utils")
    utils_mod.types, utils_mod.constants = types_mod, const_mod
    info_mod = types.ModuleType("hyperliquid.info")
    info_mod.Info = _LagInfo
    ex_mod = types.ModuleType("hyperliquid.exchange")
    ex_mod.Exchange = _LinkedExchange
    pkg = types.ModuleType("hyperliquid")
    pkg.exchange, pkg.info, pkg.utils = ex_mod, info_mod, utils_mod
    eth_mod = types.ModuleType("eth_account")
    eth_mod.Account = _Acct
    for name, mod in (("hyperliquid", pkg), ("hyperliquid.exchange", ex_mod),
                      ("hyperliquid.info", info_mod),
                      ("hyperliquid.utils", utils_mod),
                      ("hyperliquid.utils.types", types_mod),
                      ("hyperliquid.utils.constants", const_mod),
                      ("eth_account", eth_mod)):
        monkeypatch.setitem(sys.modules, name, mod)


def _hl_exec(tmp_path):
    """The REAL adapter (built through its real __init__, mainnet, agent
    wallet signing for MAIN) under a LIVE-mode executor, flat at boot."""
    from app.hl import HyperliquidVenue

    class Cfg:
        hl_secret_key = "0x" + "11" * 32     # a dummy; the fake ignores it
        hl_account_address = MAIN
        hl_coin = "BTC"
        hl_testnet = False
    hv = HyperliquidVenue(Cfg())
    hv.exchange.info = hv.info
    ex = mkexec(tmp_path, hv, dry_run=False)
    return ex, hv


INC_ENTRY_TS = 1794182400                       # the live trend short
INC_POS = {"side": "S", "entry_price": 74_375.0, "entry_ts": INC_ENTRY_TS,
           "signal_ts": INC_ENTRY_TS - 14_400, "stop": 72_638.6,
           "exit_flag": None}
INC_OLD = "T-1794182400-S73941-44"              # rested 00:01 -> 04:01:09
INC_NEW = "T-1794182400-S72638-45"              # self-cancelled 04:01:11


def _seed_live_short(ex, hv):
    """The live book at 2026-11-14 04:01Z: trend short 0.45387 with its
    stop -44 resting at 73941; the engine's trail has ratcheted to
    72638.6."""
    hv.info.net = -0.45387
    led = ex.state.legs["trend"]
    led.qty, led.stop_n = -0.45387, 44
    hv.place_stop("BUY", 0.45387, 73_941.0, INC_OLD)
    led.stop_cloid, led.stop_px = INC_OLD, 73_941.0
    led.stop_qty, led.stop_mode = 0.45387, "venue"
    return led


def _venue_status(hv, our_cloid):
    return hv.info.records[derive_cloid(our_cloid)]["status"]


# ======================================================================
# GATES - fail on 93f74553, pass with the fix
# ======================================================================

@pytest.mark.parametrize("lag_reads", [1, 2, 3, 4])
def test_gate_incident_replay_fresh_stop_survives_info_lag(
        tmp_path, fake_sdk, clock, pages, lag_reads):
    """2026-11-14 04:01 ratchet, live numbers, the real adapter. The info
    node answers unknownOid for the first `lag_reads` reads of the new stop
    (4 = every read but the window's last). The executor must keep it: no
    self-cancel, ref set, no stop_unconfirmed, nothing counted toward
    STOP_UNPLACEABLE, no second placement, and the late confirm logged
    (INFO, never paged)."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.info.lag_next = [lag_reads]
    n_sent = len(hv.exchange.sent)
    ex._maintain_stop("trend", led, dict(INC_POS))
    assert derive_cloid(INC_NEW) == "0x80c70e3a8e54cce130aef254f4242b2b", \
        "the venue's record of the incident stop"
    assert _venue_status(hv, INC_OLD) == "canceled", "the ratchet replaces -44"
    assert derive_cloid(INC_NEW) not in hv.exchange.cancelled, (
        "the executor cancelled its own healthy stop; pages: "
        + repr(_msgs(ex, "stop_unconfirmed")))
    assert _venue_status(hv, INC_NEW) == "open"
    assert led.stop_cloid == INC_NEW and led.stop_mode == "venue"
    assert led.stop_px == pytest.approx(72_638.6)
    assert "stop_unconfirmed" not in _kinds(ex)
    assert not (ex.state.stop_vanish or {}), ex.state.stop_vanish
    assert len(hv.exchange.sent) == n_sent + 1, "exactly one new order"
    assert hv.info.reads[derive_cloid(INC_NEW)] == lag_reads + 1
    assert sum(clock.sleeps) <= BUDGET_S + 1e-9, clock.sleeps
    lag = _events(ex, "stop_confirm_lag")
    assert len(lag) == 1 and lag[0]["level"] == "INFO", ex.state.events
    assert f"on read {lag_reads + 1}" in lag[0]["msg"]
    assert "venue ack resting oid" in lag[0]["msg"], lag[0]["msg"]
    assert not any("stop_confirm_lag" in p for p in pages), pages


def test_gate_incident_replay_through_a_whole_step(tmp_path, fake_sdk, clock,
                                                   pages):
    """The same ratchet driven through Executor.step() - the poll the live
    loop runs - so every rail around the stop (halts, drift, fill-watch,
    agent expiry) runs too and none of them trips over the window."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.info.lag_next = [1]
    ex.step(target(trend={"pending": None, "position": dict(INC_POS)}))
    assert ex.state.halted is None, ex.state.halted
    assert derive_cloid(INC_NEW) not in hv.exchange.cancelled, (
        "self-cancel: " + repr(_msgs(ex, "stop_unconfirmed")))
    assert led.stop_cloid == INC_NEW and _venue_status(hv, INC_NEW) == "open"
    assert led.qty == pytest.approx(-0.45387)
    assert abs(hv.info.net + 0.45387) < 1e-12
    reds = [e["kind"] for e in ex.state.events if e["level"] == "RED"]
    assert reds == [], reds
    # the next poll: the churn guard holds the confirmed stop, nothing sent
    n = len(hv.exchange.sent)
    ex.step(target(trend={"pending": None, "position": dict(INC_POS)}))
    assert len(hv.exchange.sent) == n and led.stop_cloid == INC_NEW


@pytest.mark.parametrize("lags", [3, 4])
def test_gate_0918_triple_replay_never_reaches_the_cap(tmp_path, fake_sdk,
                                                       clock, lags):
    """2026-09-18 20:00:24 / 20:00:47 / 20:01:10: three consecutive
    placements on one long each met a lagging info node (live: -15, -16,
    -17 cancelled by us, -18 survived; attempts 1/2/3 - one short of the
    halt). lags=4 is that day with one more lagging read: the base halts
    STOP_UNPLACEABLE and flattens a healthy 0.03134 long. With the window
    the first stop is kept and nothing else is placed."""
    ex, hv = _hl_exec(tmp_path)
    hv.info.net = 0.03134
    led = ex.state.legs["trend"]
    led.qty, led.stop_n = 0.03134, 14
    pos = {"side": "L", "entry_price": 80_751.0, "entry_ts": 1789747200,
           "signal_ts": 1789732800, "stop": 76_265.4, "exit_flag": None}
    hv.info.lag_next = [1] * lags
    for _ in range(4):
        ex._poll_seq += 1
        ex._maintain_stop("trend", led, dict(pos))
        if ex.state.halted:
            break
    failed = _msgs(ex, "stop_unconfirmed")
    assert ex.state.halted is None, f"halted {ex.state.halted}: {failed}"
    assert failed == [], (
        f"{len(failed)} self-cancelled placement(s), count "
        f"{ex.state.stop_vanish}: {failed}")
    assert abs(hv.info.net - 0.03134) < 1e-12, "the healthy long was flattened"
    stops = [o["cloid"] for o in hv.exchange.sent if o["isTrigger"]]
    assert stops == [derive_cloid("T-1789747200-S76265-15")], stops
    assert led.stop_cloid == "T-1789747200-S76265-15"
    assert not (ex.state.stop_vanish or {})


def test_gate_hl_no_record_is_tagged_not_a_terminal_record(tmp_path,
                                                           fake_sdk):
    """ADAPTER CONTRACT. A reply with no record (unknownOid, or a reply that
    is not a record at all) keeps status CANCELLED / 0 for every existing
    caller but carries raw=NO_RECORD_RAW; a real cancel carries the venue's
    own word. The mirror and the adapter spell the marker the same way."""
    from app import hl
    ex, hv = _hl_exec(tmp_path)
    st = hv.order_status("never-sent")
    assert st["status"] == "CANCELLED" and st["filled_qty"] == 0.0
    assert st.get("raw") == NO_RECORD
    assert hl.NO_RECORD_RAW == mirror.NO_RECORD_RAW == NO_RECORD
    for odd in (None, [], 0, "unknownOid"):         # JSON that is no record
        hv.info.odd_reply = odd
        st = hv.order_status("never-sent")
        assert st["status"] == "CANCELLED" and st.get("raw") == NO_RECORD, odd
    hv.place_stop("SELL", 0.01, 70_000.0, "T-1-S70000-1")
    hv.cancel("T-1-S70000-1")
    st = hv.order_status("T-1-S70000-1")
    assert st["status"] == "CANCELLED" and st.get("raw") == "canceled"


def test_gate_hl_place_stop_returns_the_exchange_ack(tmp_path, fake_sdk):
    """hl.place_stop hands back the exchange's own acceptance (evidence for
    the page and the lag event; it confirms nothing). The order it sends is
    unchanged: reduce-only stop-market at the snapped trigger."""
    ex, hv = _hl_exec(tmp_path)
    ack = hv.place_stop("SELL", 0.01, 70_000.4, "T-1-S70000-1")
    sent = hv.exchange.sent[-1]
    assert ack == {"accepted": "resting", "oid": sent["oid"]}
    assert sent["reduceOnly"] is True and sent["isTrigger"] is True
    assert sent["triggerPx"] == "70000.0"
    hv.exchange.reply_style = "waitingForTrigger"
    assert hv.place_stop("SELL", 0.01, 70_000.0, "T-1-S70000-2") == \
        {"accepted": "waitingForTrigger", "oid": None}
    hv.exchange.reply_style = {"weird": 1}
    assert hv.place_stop("SELL", 0.01, 70_000.0, "T-1-S70000-3") is None
    hv.exchange.reply_style = {"error": "Order has invalid price."}
    with pytest.raises(RuntimeError):
        hv.place_stop("SELL", 0.01, 70_000.0, "T-1-S70000-4")


def test_gate_an_odd_ack_shape_never_turns_an_accepted_stop_into_a_raise(
        tmp_path, fake_sdk, clock, pages):
    """GATE (both final reviewers' MINOR: introduced by this fix's first cut,
    fixed before its commit). An 'ok' reply whose `statuses` is an object, not
    a list, made the ack parser raise KeyError AFTER the exchange had accepted
    the stop; _maintain_stop took the raise for a rejection, counted it and
    cancelled the accepted stop - the incident's outcome through a new door.
    The ack is evidence only: a shape it cannot parse is None, and the stop
    is confirmed by its status read as usual. (93f74553 passes this: its
    place_stop returned nothing; the gate is against the first cut.)"""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.exchange.statuses_as_object = True
    ex._maintain_stop("trend", led, dict(INC_POS))
    assert derive_cloid(INC_NEW) not in hv.exchange.cancelled, _kinds(ex)
    assert _venue_status(hv, INC_NEW) == "open"
    assert led.stop_cloid == INC_NEW and led.stop_mode == "venue"
    kinds = _kinds(ex)
    assert "stop_place_failed" not in kinds and "stop_unconfirmed" not in kinds
    assert not (ex.state.stop_vanish or {}), ex.state.stop_vanish


@pytest.mark.parametrize("statuses", [
    {"resting": {"oid": 1}}, {"filled": {"totalSz": "0.01", "avgPx": "1"}},
    {"0": "x"}, "resting", 7])
def test_gate_reply_parsers_never_raise_on_an_odd_shape(statuses):
    """GATE. Both reply parsers are evidence parsers: the ack (place_stop) and
    the IOC fill (place_market, whose None means "no usable answer, settle
    later"). Neither may raise on a reply shape it does not know - a raise
    there comes AFTER the exchange acted. The first cut and 93f74553 caught
    only (TypeError, ValueError, AttributeError, IndexError), so an object
    `statuses` raised KeyError out of both: the three object-shaped cases
    gate the first cut; the string and integer cases pass on it and pin the
    behaviour."""
    from app.hl import HyperliquidVenue
    r = {"status": "ok", "response": {"type": "order",
                                      "data": {"statuses": statuses}}}
    ack = HyperliquidVenue._ack_from_response(r)
    assert ack is None or isinstance(ack, dict), ack
    assert HyperliquidVenue._fill_from_response(r) is None


def test_gate_unconfirmed_page_says_what_the_confirm_saw(tmp_path, fake_sdk,
                                                        clock, pages):
    """A lag longer than the window still takes the old path - but the page
    now carries the evidence an operator needs: how many reads over how
    long, the last raw answer, and that the exchange HAD accepted the
    order. The old text is kept as its prefix (no consumer parses it; any
    external alert filter keyed on it still matches)."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.info.lag_next = [10]
    ex._maintain_stop("trend", led, dict(INC_POS))
    (msg,) = _msgs(ex, "stop_unconfirmed")
    old = (f"trend stop {INC_NEW} not confirmed working (status=CANCELLED) - "
           f"cancelled best-effort; position may be UNPROTECTED; attempt 1")
    assert msg.startswith(old), msg
    assert f"{1 + len(DELAYS)} status read(s) over 3.0s" in msg, msg
    assert f"last raw {NO_RECORD}" in msg and "venue ack resting oid" in msg


class _LagVenue(FakeVenue):
    """Stops rest OPEN; the first `lag` reads of each stop answer what
    hl.order_status answers for a reply with no record. lag=None: every
    read, forever. `first`: a scripted answer per read (None = the truth)."""

    def __init__(self, lag=None, first=None, **kw):
        super().__init__(**kw)
        self.lag, self.first = lag, first
        self.reads: dict[str, int] = {}
        self.cancels: list[str] = []

    def order_status(self, cloid):
        o = self.orders.get(cloid)
        if o and o["type"] == "STOP":
            n = self.reads[cloid] = self.reads.get(cloid, 0) + 1
            if self.first is not None:
                if n <= len(self.first) and self.first[n - 1] is not None:
                    return dict(self.first[n - 1])
            elif self.lag is None or n <= self.lag:
                return dict(MISS)
        return super().order_status(cloid)

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


def _seed(v, ex, qty=0.01):
    _hold(v, qty)
    led = ex.state.legs["trend"]
    led.qty = qty
    return led


def _stops(v):
    return [c for c, o in v.orders.items() if o["type"] == "STOP"]


def test_gate_slow_confirm_resets_the_count_like_a_fast_one(tmp_path, clock):
    """A stop confirmed on a later read is protection that WORKED: it must
    clear an earlier failure count exactly as a first-read confirm does
    (re-gate N1), or lagging reads would still march toward the cap."""
    v = _LagVenue(lag=None, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())          # attempt 1 fails
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1
    v.lag = 2                                              # next: slow but OK
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert not ex.state.stop_vanish.get(f"trend:{NOW}"), ex.state.stop_vanish


def test_gate_unknown_reads_shorter_than_the_window_confirm(tmp_path, clock):
    """UNKNOWN (an API failure, not a lag) on three reads: the base read
    once, slept 1 s, read once more, then cancelled a stop that rested the
    whole time. The window gives UNKNOWN the same patience as no-record."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    v.blips = 3
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert not v.cancels and "stop_unconfirmed" not in _kinds(ex)
    assert sum(clock.sleeps) <= BUDGET_S + 1e-9


class _RaisingReadVenue(FakeVenue):
    """order_status RAISES (mode "raise") or answers something that is not
    a status dict (mode "junk") for the first `fail` reads of a stop.
    Neither shipping adapter is meant to, but hl.order_status can raise on a
    malformed record (`o.get` on a non-dict, float() on a bad size)."""

    def __init__(self, fail=1, mode="raise", **kw):
        super().__init__(**kw)
        self.fail, self.mode = fail, mode
        self.cancels: list[str] = []

    def order_status(self, cloid):
        o = self.orders.get(cloid)
        if o and o["type"] == "STOP" and self.fail > 0:
            self.fail -= 1
            if self.mode == "junk":
                return "OPEN"
            raise AttributeError("'str' object has no attribute 'get'")
        return super().order_status(cloid)

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


@pytest.mark.parametrize("mode", ["raise", "junk"])
def test_gate_a_raising_confirm_read_is_retried_not_escaped(tmp_path, clock,
                                                           mode):
    """A raise (or a non-dict answer) used to escape _maintain_stop with
    the stop placed but neither believed nor cancelled (a later poll could
    arm a second one). Read as UNKNOWN it is re-read like any blip; one that
    never resolves takes the old path - cancelled before cleared, counted,
    paged."""
    v = _RaisingReadVenue(fail=1, mode=mode, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert not v.cancels and "stop_unconfirmed" not in _kinds(ex)
    v2 = _RaisingReadVenue(fail=10_000, mode=mode, mult=0.01)
    ex2 = mkexec(tmp_path / "b", v2)
    led2 = _seed(v2, ex2)
    ex2._maintain_stop("trend", led2, _long_pos())
    (placed,) = _stops(v2)
    assert placed in v2.cancels and led2.stop_cloid is None
    assert ex2.state.stop_vanish.get(f"trend:{NOW}") == 1
    assert "status=UNKNOWN" in _msgs(ex2, "stop_unconfirmed")[0]


# --- the Coinbase adapter: its REAL order_status mapping over a scripted
#     client. Coinbase has no no-record answer: an explicit terminal status
#     is a record (final at once), an API failure is UNKNOWN (re-read).
class _CbResp:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class _CbClient:
    def __init__(self):
        self.script: list = []        # per get_order: a status or a raise
        self.calls = 0

    def get_order(self, oid):
        self.calls += 1
        ans = self.script.pop(0) if self.script else "OPEN"
        if isinstance(ans, Exception):
            raise ans
        return _CbResp({"order": {"order_id": oid, "status": ans,
                                  "filled_size": "0",
                                  "average_filled_price": None}})


class _CbStatusVenue(FakeVenue):
    """FakeVenue for positions and placements; STOP status reads go through
    the real cb.CoinbaseVenue.order_status."""

    def __init__(self, **kw):
        super().__init__(**kw)
        from app.cb import CoinbaseVenue
        self.cb = CoinbaseVenue.__new__(CoinbaseVenue)
        self.cb.client = _CbClient()
        self.cb._orders = {}
        self.cb._meta = {"contract_multiplier": None}
        self.cancels: list[str] = []

    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        self.cb._orders[cloid] = f"cb-{cloid}"

    def order_status(self, cloid):
        o = self.orders.get(cloid)
        if o and o["type"] == "STOP":
            return self.cb.order_status(cloid)
        return super().order_status(cloid)

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


def test_gate_coinbase_unknown_reads_get_the_window_too(tmp_path, clock):
    """Two API failures on Coinbase (cb.order_status -> UNKNOWN), then the
    stop reads OPEN: the base's read + one retry cancelled it."""
    v = _CbStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    v.cb.client.script = [RuntimeError("503"), RuntimeError("503"), "OPEN"]
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and not v.cancels, _msgs(ex, "stop_unconfirmed")
    assert v.cb.client.calls == 3


def test_gate_a_fill_inside_the_window_confirms(tmp_path, clock):
    """No record, then FILLED (the stop fired within the window): working,
    as a first-read FILLED is - the ref is set so the next poll's head read
    books the fill. The base read the miss as dead and cleared the ref."""
    v = _LagVenue(first=[MISS, FILLED], mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    (placed,) = _stops(v)
    assert led.stop_cloid == placed and placed not in v.cancels
    assert "stop_unconfirmed" not in _kinds(ex)


# ======================================================================
# TWINS - pass on both: a genuinely dead stop still takes the OLD path
# ======================================================================

class _KillVenue(FakeVenue):
    """Accepts every stop and the venue itself kills it at once; the
    status read returns a terminal RECORD carrying `raw` (the venue's own
    word), or no raw at all (Coinbase/DryRun shape)."""

    def __init__(self, raw="reduceOnlyCanceled", **kw):
        super().__init__(**kw)
        self.raw = raw
        self.cancels: list[str] = []
        self.reads: dict[str, int] = {}

    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        self.orders[cloid]["status"] = "CANCELLED"

    def order_status(self, cloid):
        st = super().order_status(cloid)
        if st and cloid in self.orders and \
                self.orders[cloid]["type"] == "STOP":
            self.reads[cloid] = self.reads.get(cloid, 0) + 1
            if st["status"] == "CANCELLED" and self.raw:
                st["raw"] = self.raw
        return st

    def cancel(self, cloid):
        self.cancels.append(cloid)
        super().cancel(cloid)


@pytest.mark.parametrize("raw", ["reduceOnlyCanceled", "canceled",
                                 "rejected", None])
def test_twin_a_terminal_record_is_final_at_once(tmp_path, clock, pages, raw):
    """The venue KNOWS the order and says it is dead (any Hyperliquid word,
    or Coinbase's raw-less CANCELLED): one read, no sleep, then the old
    path - cancel BEFORE clear, refs cleared, one count, a RED page."""
    v = _KillVenue(raw=raw, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    (placed,) = _stops(v)
    assert placed in v.cancels, "cancel-before-clear"
    assert led.stop_cloid is None and led.stop_px is None
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1
    (msg,) = _msgs(ex, "stop_unconfirmed")
    assert "(status=CANCELLED)" in msg and "attempt 1" in msg, msg
    assert v.reads[placed] == 1, "a record must not be re-read"
    assert clock.sleeps == [], clock.sleeps
    assert any("stop_unconfirmed" in p for p in pages), "RED pages as before"


def test_twin_explicit_kill_storm_still_halts_at_the_cap(tmp_path, clock):
    """STOP_REPLACE_MAX + 1 dead placements, then STOP_UNPLACEABLE with the
    last cloid handed to the halt - exactly as before, and with no sleep."""
    v = _KillVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    for _ in range(8):
        if ex.state.halted:
            break
        ex._poll_seq += 1
        ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.halted == "STOP_UNPLACEABLE"
    assert len(_stops(v)) == mirror.STOP_REPLACE_MAX + 1
    assert [m.rsplit("attempt ", 1)[1][:1] for m in
            _msgs(ex, "stop_unconfirmed")] == ["1", "2", "3"]
    assert "stop_unplaceable" in _kinds(ex)
    assert clock.sleeps == [], clock.sleeps


def test_twin_no_record_forever_still_halts_at_the_cap(tmp_path, clock):
    """A venue that never shows the stop: each attempt waits out the window
    (bounded), cancels before it clears, counts once; the fourth halts."""
    v = _LagVenue(lag=None, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    for _ in range(8):
        if ex.state.halted:
            break
        ex._poll_seq += 1
        ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.halted == "STOP_UNPLACEABLE"
    placed = _stops(v)
    assert len(placed) == mirror.STOP_REPLACE_MAX + 1
    assert all(c in v.cancels for c in placed[:-1]), "cancel-before-clear"
    assert sum(clock.sleeps) <= \
        (mirror.STOP_REPLACE_MAX + 1) * BUDGET_S + 1e-9, clock.sleeps


def test_twin_hl_lag_longer_than_the_window_cancels_before_clearing(
        tmp_path, fake_sdk, clock):
    """The residual the window does not cover, on the real adapter: the info
    node lags past the last read. The OLD path runs unchanged - our cancel
    lands on the venue, refs clear, one count - and the next poll arms
    exactly one fresh stop, so two can never rest."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.info.lag_next = [1 + len(DELAYS)]           # every read of the window
    ex._maintain_stop("trend", led, dict(INC_POS))
    assert derive_cloid(INC_NEW) in hv.exchange.cancelled
    assert _venue_status(hv, INC_NEW) == "canceled"
    assert led.stop_cloid is None and led.stop_px is None
    assert ex.state.stop_vanish.get(f"trend:{INC_ENTRY_TS}") == 1
    assert sum(clock.sleeps) == pytest.approx(sum(DELAYS))
    ex._poll_seq += 1
    ex._maintain_stop("trend", led, dict(INC_POS))        # the next poll
    resting = [r["order"]["cloid"] for r in hv.info.records.values()
               if r["status"] == "open" and r["order"]["isTrigger"]]
    assert resting == [derive_cloid("T-1794182400-S72638-46")], resting
    assert led.stop_cloid == "T-1794182400-S72638-46"


@pytest.mark.parametrize("word", ["reduceOnlyCanceled", "canceled",
                                  "marginCanceled"])
def test_twin_hl_venue_killed_stop_is_final_at_once(tmp_path, fake_sdk,
                                                    clock, word):
    """End to end on the real adapter: the venue ACCEPTED the stop and then
    killed it, and its record says so. That is a record, not a lag: one
    read, no sleep, then the old path - our cancel sent anyway
    (cancel-before-clear), refs cleared, one count, the page."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    hv.exchange.kill_with = word
    ex._maintain_stop("trend", led, dict(INC_POS))
    assert hv.info.reads[derive_cloid(INC_NEW)] == 1
    assert clock.sleeps == []
    assert derive_cloid(INC_NEW) in hv.exchange.cancelled
    assert led.stop_cloid is None and led.stop_px is None
    assert ex.state.stop_vanish.get(f"trend:{INC_ENTRY_TS}") == 1
    (msg,) = _msgs(ex, "stop_unconfirmed")
    assert "(status=CANCELLED)" in msg and "attempt 1" in msg


def test_twin_healthy_first_read_never_sleeps(tmp_path, fake_sdk, clock):
    """The common path (46 of the 54 live placements were never
    self-cancelled) keeps today's timing and today's events exactly."""
    ex, hv = _hl_exec(tmp_path)
    led = _seed_live_short(ex, hv)
    ex._maintain_stop("trend", led, dict(INC_POS))
    assert led.stop_cloid == INC_NEW and _venue_status(hv, INC_NEW) == "open"
    assert hv.info.reads[derive_cloid(INC_NEW)] == 1
    assert clock.sleeps == []
    assert "stop_confirm_lag" not in _kinds(ex)
    assert "stop_unconfirmed" not in _kinds(ex)


def test_twin_first_open_wins_over_a_later_miss(tmp_path, clock):
    """Reads behind a load balancer are not monotonic: once a read says
    OPEN, nothing is read again, so a later miss cannot undo it."""
    v = _LagVenue(first=[None, MISS, MISS], mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert v.reads[led.stop_cloid] == 1 and clock.sleeps == []


def test_twin_a_record_inside_the_window_is_final(tmp_path, clock):
    """A miss, then the venue's own terminal record: stop re-reading at the
    record and take the old path (no waiting out the rest of the window)."""
    dead = {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None,
            "raw": "reduceOnlyCanceled"}
    v = _LagVenue(first=[MISS, dead, dead, dead, dead, dead], mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    (placed,) = _stops(v)
    assert placed in v.cancels and led.stop_cloid is None
    assert "stop_unconfirmed" in _kinds(ex)
    assert v.reads[placed] <= 2 and len(clock.sleeps) <= 1, clock.sleeps


def test_twin_a_fill_on_the_first_read_confirms(tmp_path, clock):
    """FILLED is "working" exactly as before: the ref is set (no cancel, no
    page) so the next poll's head read books the fill."""
    v = _LagVenue(first=[FILLED], mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    (placed,) = _stops(v)
    assert led.stop_cloid == placed and placed not in v.cancels
    assert "stop_unconfirmed" not in _kinds(ex) and clock.sleeps == []


def test_twin_one_poll_still_counts_one_failure(tmp_path, clock):
    """Head vanish (an explicit record) + a replacement that never
    confirms in the same poll is ONE failed attempt (re-gate N1)."""
    v = _LagVenue(lag=None, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    v._add("STOP", "SELL", 0.01, "T-1-S74089-0", px=74_089.0)
    v.orders["T-1-S74089-0"]["status"] = "CANCELLED"
    v.reads["T-1-S74089-0"] = 99                # past any lag: a real record
    led.stop_cloid, led.stop_px = "T-1-S74089-0", 74_089.0
    ex._maintain_stop("trend", led, _long_pos())
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1, ex.state.stop_vanish


def test_twin_single_unknown_blip_is_retried(tmp_path, clock):
    """The base already re-read one UNKNOWN after 1 s (_ostat); the window
    must never do less than that."""
    v = _BlipStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    v.blips = 1
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert "stop_unconfirmed" not in _kinds(ex)


class _RejectingStopVenue(_LagVenue):
    def place_stop(self, side, qty, trigger_px, cloid):
        super().place_stop(side, qty, trigger_px, cloid)
        raise RuntimeError("order rejected: Order has invalid price.")


def test_twin_a_rejected_place_is_not_read_at_all(tmp_path, clock):
    """place_stop RAISED: unchanged - no confirm read, no sleep, the
    REJECTED path (stop_place_failed + stop_unconfirmed, cancel-before-
    clear, one count)."""
    v = _RejectingStopVenue(lag=0, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    ex._maintain_stop("trend", led, _long_pos())
    (placed,) = _stops(v)
    assert v.reads.get(placed, 0) == 0 and clock.sleeps == []
    assert placed in v.cancels and led.stop_cloid is None
    assert "stop_place_failed" in _kinds(ex)
    (msg,) = _msgs(ex, "stop_unconfirmed")
    assert "(status=REJECTED)" in msg and msg.endswith("attempt 1")
    assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1


@pytest.mark.parametrize("word,final", [("CANCELLED", True),
                                        ("EXPIRED", True),
                                        ("FAILED", True),
                                        ("QUEUED", False)])
def test_twin_coinbase_records_are_unchanged(tmp_path, clock, word, final):
    """The Coinbase adapter's own words: a terminal status is a record,
    final on the first read with no sleep; a transitional one is OPEN."""
    v = _CbStatusVenue(mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    v.cb.client.script = [word]
    ex._maintain_stop("trend", led, _long_pos())
    assert v.cb.client.calls == 1 and clock.sleeps == []
    if final:
        assert led.stop_cloid is None and v.cancels
        assert ex.state.stop_vanish.get(f"trend:{NOW}") == 1
    else:
        assert led.stop_cloid and not v.cancels


def test_twin_dry_run_never_waits(tmp_path, clock):
    """DRY_RUN (the shadow venue) confirms on its first read, as before."""
    from app.cb import DryRunVenue
    v = DryRunVenue(None)
    v.orders["seed"] = {"type": "MARKET", "side": "BUY", "qty": 0.01,
                        "px": 60_000.0, "status": "FILLED"}
    ex = mkexec(tmp_path, v, dry_run=True)
    led = ex.state.legs["trend"]
    led.qty = 0.01
    ex._maintain_stop("trend", led, _long_pos())
    assert led.stop_cloid and v.orders[led.stop_cloid]["status"] == "OPEN"
    assert clock.sleeps == []


def test_twin_the_window_is_bounded_and_measured(tmp_path, monkeypatch):
    """REAL sleeps, real clock. Worst case for one placement: every read of
    the window finds no record. The added wait is the schedule's sum (3.0 s
    with the fix, 0 on the base, which cancelled on the first read) plus
    the reads themselves; the schedule itself never exceeds the approved
    ~3 s. The healthy path asks for no sleep at all."""
    real = _Clock(real=True)
    monkeypatch.setattr(mirror, "time", real)
    assert sum(DELAYS) <= BUDGET_S + 1e-9, DELAYS
    v = _LagVenue(lag=None, mult=0.01)
    ex = mkexec(tmp_path, v)
    led = _seed(v, ex)
    t0 = _time.monotonic()
    ex._maintain_stop("trend", led, _long_pos())
    took = _time.monotonic() - t0
    assert real.sleeps == list(DELAYS), real.sleeps
    assert sum(DELAYS) - 1e-3 <= took <= sum(DELAYS) + 1.0, took
    print(f"\nMEASURED worst-case confirm: {took:.3f}s for "
          f"{1 + len(DELAYS)} reads (schedule {DELAYS}, sum "
          f"{sum(DELAYS):.2f}s)")
    v2 = _LagVenue(lag=0, mult=0.01)
    ex2 = mkexec(tmp_path / "b", v2)
    led2 = _seed(v2, ex2)
    real.sleeps.clear()
    t0 = _time.monotonic()
    ex2._maintain_stop("trend", led2, _long_pos())
    took2 = _time.monotonic() - t0
    assert real.sleeps == [] and led2.stop_cloid
    print(f"MEASURED healthy confirm: {took2:.3f}s, no sleep")


# ======================================================================
# LATENT - same lag, placement sites OUTSIDE the approved scope.
# Pinned (strict xfail) so they are not forgotten; the owner decides
# whether to widen the scope. Found by the 2026-11-14 counter-agent review.
# ======================================================================

class _LimitLagVenue(FakeVenue):
    """Pullback maker entries rest OPEN; their first `lag` reads answer as
    hl.order_status answers a reply with no record (CANCELLED / 0)."""

    def __init__(self, lag=2, **kw):
        super().__init__(**kw)
        self.lag = lag
        self.reads: dict[str, int] = {}

    def order_status(self, cloid):
        o = self.orders.get(cloid)
        if o and o["type"] == "LIMIT":
            n = self.reads[cloid] = self.reads.get(cloid, 0) + 1
            if n <= self.lag:
                return dict(MISS)
        return super().order_status(cloid)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="LATENT, out of scope: the pullback "
                   "entry confirm (mirror._sync_leg, the `stat = "
                   "self._ostat(cloid)` after place_limit) clears the entry "
                   "ref on two immediate no-record reads, so the next poll "
                   "sends a second maker entry beside a live one")
def test_latent_pullback_entry_no_record_sends_a_second_entry(tmp_path,
                                                              clock):
    v = _LimitLagVenue(lag=2)
    ex = mkexec(tmp_path, v, dry_run=False)
    pend = target(pull={"pending": {"side": "L", "limit": 59_000.0,
                                    "signal_ts": NOW - 14_400},
                        "position": None})
    ex.step(pend)
    ex.step(pend)
    limits = [c for c in v.calls if c[0] == "LIMIT"]
    assert len(limits) == 1, f"duplicate maker entries resting: {limits}"


class _ReestLagVenue(tng.HLFake2):
    """HLFake2 whose R order's first `lag` reads answer as hl.order_status
    answers a reply with no record - CANCELLED / 0, not UNKNOWN."""

    def __init__(self, *a, lag=1, **k):
        super().__init__(*a, **k)
        self.r_lag = lag

    def order_status(self, cloid):
        if "-R" in cloid and self.r_lag > 0 and cloid in self.orders:
            self.r_lag -= 1
            return dict(MISS)
        return super().order_status(cloid)


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="LATENT, out of scope: _reestablish "
                   "settles its IOC from an immediate status read "
                   "(_settle_reest) and ignores place_market's own fill "
                   "answer; one no-record read books the filled R order as "
                   "unfilled and leaves the venue leg with no ledger row and "
                   "no stop")
def test_latent_reestablish_no_record_leaves_the_leg_unbooked(tmp_path,
                                                             clock):
    ex, v0, s3, s4 = tng._seed_inc1(tmp_path)
    v = _ReestLagVenue(mid=76_600.0, lag=1)
    v.orders, v.calls = v0.orders, v0.calls
    ex.venue = v
    ex.step(target(pull=s3, trend=s4))
    v.fire_stop(ex.state.legs["pullback"].stop_cloid)
    for _ in range(4):
        ex.step(target(pull=s3, trend=s4))
    t = ex.state.legs["trend"]
    assert abs(v.position() + tng.INC1_T) < 1e-9, "the R order did fill"
    assert abs(t.qty + tng.INC1_T) < 1e-9, (
        f"venue holds -{tng.INC1_T} the ledger never booked (qty {t.qty}); "
        f"kinds {sorted(set(_kinds(ex)))}")
    assert any(o["type"] == "STOP" and o["status"] == "OPEN"
               for o in v.orders.values()), "the re-established leg is stopless"
