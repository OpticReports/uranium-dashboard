"""D1 round 4 - the open-orders wait (K5) and its alerting, after two independent reviews (2026-11-13).

The reviewers found no safety defect in K5 but these, each gated below (every gate FAILS on the code before this
round and passes after it; the twins, marked, pass on both):
  1  a K5 outage (connected, logged in, its open-orders sync never ending) was read by the service's gateway
     watch as a login stall: a "NOT logged in - almost always a missed IB Key push" page beside the adapter's
     own DOWN page saying the opposite, plus a PRE-OPEN page in the same words           -> part S (s1-s3)
  2  a boot whose sync ended just late left an outage open for good when nothing drove the adapter (no live
     mirror book, blend and ladder off): /health down_since for ever, false stall and PRE-OPEN pages  -> s4
  3  a ONE-OFF lost connect-time answer was kept all night (DOWN + stall + PRE-OPEN pages, then a 20 s wait
     at the decision's first read); a gateway answering every session's sync 45 s late never traded  -> R, M
  4  a guarded read slow enough to cross the cancel instant still placed the order after it        -> part C
  5  the trades re-read after the wait (a second SELL of the same shares otherwise) was pinned by no test;
     wording: the kill bound, the unsynced page, a read ended by a close, a recovery with no reconnect
  6  a socket that died inside _all_trades' REQUIRED reqAllOpenOrders was swallowed: the caller got the
     session's cache without the venue's list (cancel_stock_order then answered "not found")        -> part R
Invariants, gated wherever a scenario can break them: no open-orders request is ever SENT while one is
pending (K4, checked at the client before each request, and on the wire); a healthy session pays nothing
extra (the same messages on the wire, no pump in the guard); the blend and the ladder are untouched on a
healthy gateway (their suites; s4's twin: no open outage, no keepalive).

Part R/S run the REAL IBAdapter over the INSTALLED ib_async on a real localhost socket, scaled: the bound
(VENUE_HISTORY_TIMEOUT_S) 0.3 s for 20 s, the connect's sync wait 0.3 s for 15 s, the backoff 0.6 s up to
1.2 s for 15 s up to the mirror's 30 s, the DOWN page after 2.5 s for 30 min - so the one replacement is
due 0.6 s (2 x the bound) after a connect. Part M: the REAL MirrorManager driving the REAL IBAdapter over
StaleIB on ONE virtual clock, at production values (the reviewer's harness, fixverify/d1_b_work)."""
from __future__ import annotations

import struct
import sys
import threading
import time
from datetime import datetime, timedelta

import pytest

import app.ib_adapter as ib_mod
import test_mirror as tm
import test_mirror_connection as tmc
from app import mirror as mm
from app.outages import OutageLog
from test_mirror import payload
from test_mirror_connection import AFTER, D2, ROT, Rig, StaleIB, _REAL_CONNECT, _RealCfg, sound

try:
    import ib_async as real_ib_async
except Exception:  # noqa: BLE001
    real_ib_async = None

needs_ib_async = pytest.mark.skipif(real_ib_async is None, reason="ib_async is not installed")
BOUND, SYNC, ALERT = 0.3, 0.3, 2.5
UNSYNCED = "open_orders_unsynced"
LOGGED_IN = {"readable": True, "recent_ts": [], "circuit_open": False, "last": {}, "path": "/x"}  # no relaunch


# ============================================================================== the rigs: a real socket
class WireGateway(tmc.Gateway):
    """tests/test_mirror_connection.py's Gateway, plus: the open-orders policy sees the session
    (policy(session, n) -> seconds before the n-th open-orders request's end is sent, 0 = at once,
    None = never), and every message it reads is logged as (session, message id)"""

    def __init__(self, policy=None):
        self.policy = policy or (lambda s, n: 0)
        self.msgs: list = []
        super().__init__()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conn = c
            self.sessions += 1
            threading.Thread(target=self._serve2, args=(c, self.sessions), daemon=True).start()

    def _serve2(self, c, sess):
        enc = tmc._enc
        buf, shook, n_oo = b"", False, 0
        try:
            while True:
                d = c.recv(65536)
                if not d:
                    return
                buf += d
                if not shook:
                    if buf.startswith(b"API\0"):
                        buf = buf[4:]
                    if len(buf) < 4 or len(buf) < 4 + struct.unpack(">I", buf[:4])[0]:
                        continue
                    buf = buf[4 + struct.unpack(">I", buf[:4])[0]:]
                    self._send(c, enc(176, "20261112 09:00:00 EST"))
                    shook = True
                while len(buf) >= 4:
                    n = struct.unpack(">I", buf[:4])[0]
                    if len(buf) < 4 + n:
                        break
                    f, buf = buf[4:4 + n].decode().split("\0"), buf[4 + n:]
                    self.msgs.append((sess, f[0]))
                    if f[0] == "71":                                    # startApi
                        self._send(c, enc(15, 1, "DU1") + enc(9, 1, 1))
                    elif f[0] == "61":                                  # reqPositions
                        self._send(c, self._positions())
                    elif f[0] in ("5", "16"):                           # reqOpenOrders / reqAllOpenOrders
                        n_oo += 1
                        delay = self.policy(sess, n_oo)
                        if delay is None:
                            continue                                    # never answered
                        if delay > 0:
                            threading.Timer(delay, self._send, (c, enc(53, 1))).start()
                        else:
                            self._send(c, enc(53, 1))
                    elif f[0] == "99":                                  # completed orders
                        self._send(c, enc(102))
                    elif f[0] == "6":                                   # account updates
                        self._send(c, enc(6, 2, "TotalCashValue", self.cash, "USD", "DU1")
                                   + enc(6, 2, "AvailableFunds", self.cash, "USD", "DU1") + enc(54, 1, "DU1"))
                    elif f[0] == "76":                                  # account updates multi
                        self._send(c, enc(74, 1, f[2]))
                    elif f[0] == "7":                                   # executions
                        self._send(c, enc(55, 1, f[2]))
                    elif f[0] == "49":                                  # reqCurrentTime
                        self._send(c, enc(49, 1, int(time.time())))
        except OSError:
            return

    def count(self, mid: str, sess: int | None = None) -> int:
        return sum(1 for s, m in self.msgs if m == mid and (sess is None or s == sess))

    def go_down(self):
        """the gateway process goes away: new connections are refused, the current session gets its FIN"""
        import socket
        try:
            self.srv.shutdown(socket.SHUT_RDWR)         # wakes the accept thread; a bare close() does not
        except OSError:
            pass
        self.srv.close()
        self.drop()


def _k4_checked(a):
    """K4 at the client: every reqAllOpenOrders the adapter sends is checked, BEFORE it goes, for an
    open-orders request of the session still pending (ib_async would let the new one replace it)"""
    a.k4_violations, a.k4_sent = 0, 0
    real = a.ib.reqAllOpenOrders

    def checked(*args, **kw):
        a.k4_sent += 1
        if "openOrders" in a.ib.wrapper._futures:
            a.k4_violations += 1
        return real(*args, **kw)
    a.ib.reqAllOpenOrders = checked


@pytest.fixture
def wire(monkeypatch, tmp_path):
    """make(policy, boot=True): a real IBAdapter on the installed ib_async, scaled (module docstring), its
    outage ledger on disk, the alerts it sends in make.sent, connected (boot: by the service's own _connect)
    to a WireGateway that follows `policy`"""
    if real_ib_async is None:
        pytest.skip("ib_async is not installed")
    monkeypatch.setitem(sys.modules, "ib_async", real_ib_async)
    monkeypatch.setattr(ib_mod.IBAdapter, "_connect", lambda self: None)
    import app.alerts as alerts_mod
    sent: list = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", BOUND)
    monkeypatch.setattr(ib_mod, "OUTAGE_ALERT_S", ALERT)
    monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 0.6)
    made = []

    def make(policy, boot=True, connect_timeout=SYNC):
        gw = WireGateway(policy)
        a = ib_mod.IBAdapter(_RealCfg())
        a._reconnect_backoff, a.reconnect_backoff_max_s, a.mirror_only = 0.6, 1.2, True
        a.outages = OutageLog(str(tmp_path / f"outages{len(made)}.json"))
        real = a.ib.connect
        a.connects = 0

        def to_gw(host, port, clientId, timeout=15):
            a.connects += 1
            return real("127.0.0.1", gw.port, clientId=clientId, timeout=connect_timeout)
        a.ib.connect = to_gw
        tmc._counted_drops(a)
        _k4_checked(a)
        made.append((a, gw))
        if boot:
            _REAL_CONNECT(a)            # the service's own boot connect
            a.connects = 0
        return a, gw
    make.sent = sent
    yield make
    for a, gw in made:
        try:
            a.ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        gw.close()


def _at(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=mm.ET).timestamp()


def _watch(summ, now, down_min, restarts=None, kind_since_min=None):
    """the service's gateway watch on `summ` (the adapter's ledger), with the outage moved to have begun
    `down_min` minutes before `now` (and its current cause `kind_since_min` before it)"""
    import app.service as svc
    s = dict(summ)
    if s.get("currently_down_since") is not None:
        s["currently_down_since"] = now - down_min * 60
        if s.get("currently_down_kind_since") is not None:
            s["currently_down_kind_since"] = now - (down_min if kind_since_min is None else kind_since_min) * 60
    pages: list = []
    return svc._gateway_watch(now, s, restarts or LOGGED_IN, pages.append, state={}), pages


# ============================================================================== part S: the service's view
@needs_ib_async
def test_s1_a_logged_in_gateway_whose_sync_never_ends_is_not_paged_as_a_login_stall(wire):
    """reviewer A's w1 (and B's r6 below): the boot session's connect-time open-orders request is never answered;
    the session is kept idle by the keepalive. The service's watch reads the SAME ledger. Before: at +31 min it
    paged 'the gateway process is alive but NOT logged in - almost always a missed IB Key push', on a trading
    morning a PRE-OPEN page in the same words too. After: the ledger names the cause, the watch makes no
    diagnosis of its own (the adapter's DOWN page is the one page) and the PRE-OPEN page says what is true."""
    a, gw = wire(lambda s, n: None if n == 1 else 0)
    for _ in range(3):
        assert a.keepalive() is True                   # idle: positions, cash and the round trip all answer
    summ = a.outages.summary()
    assert summ["currently_down_since"] is not None
    tue_1400, tue_0900 = _at(2026, 11, 17, 14, 0), _at(2026, 11, 17, 9, 0)
    fired, pages = _watch(summ, tue_1400, 31)
    assert fired == [] and not any("NOT logged in" in p or "IB Key push" in p for p in pages), pages
    crash_log = dict(LOGGED_IN, recent_ts=[tue_1400 - 60 * m for m in (3, 9, 17, 26)])
    assert _watch(summ, tue_1400, 31, crash_log)[0] == []        # nor the crash-loop / unreadable diagnoses
    assert _watch(summ, tue_1400, 31, {"readable": False, "path": "/x"})[0] == []
    fired, pages = _watch(summ, tue_0900, 31)
    assert fired == ["preopen"], (fired, pages)
    assert ("logged in" in pages[0] and "open-orders sync never ends" in pages[0]
            and "Restart the gateway NOW" in pages[0] and "down 31 min" not in pages[0]), pages
    assert summ.get("currently_down_kind") == UNSYNCED and a.k4_violations == 0


@needs_ib_async
def test_s2_reviewer_b_r6_the_unsynced_session_a_reconnect_brings_is_not_paged_as_a_login_stall(wire):
    """the same through _reconnect's K5 branch: a read on a session the adapter did not connect itself waits,
    fails closed and drops it; the reconnect brings an unsynced session"""
    a, gw = wire(lambda s, n: None if n == 1 else 0, boot=False)
    a.ib.connect("x", 0, clientId=17)
    with pytest.raises(ib_mod.ExecutorConnectionError):
        a.open_sell_qty("SPY")
    a.prove_live()                                      # the reconnect: an unsynced session
    summ = a.outages.summary()
    fired, pages = _watch(summ, _at(2026, 11, 17, 14, 0), 31)
    assert not [p for p in pages if "NOT logged in" in p or "IB Key push" in p] and fired == [], pages
    assert a.ib.isConnected() and gw.sessions == 2 and a.k4_violations == 0


@needs_ib_async
def test_s3_an_unsynced_outage_that_becomes_a_plain_one_starts_the_login_stall_clock_then(wire):
    """the remedy the DOWN page names is a gateway restart. A gateway that restarts (or dies) in the middle of an
    unsynced outage is down from THEN: the watch's login-stall clock counts from when the cause changed, not from
    the outage's start - before, a restart 40 min into it was paged 'NOT logged in' the moment it dropped"""
    a, gw = wire(lambda s, n: None if n == 1 else 0)
    gw.go_down()                                        # refused from now on, and the session's FIN
    assert a.keepalive() is False                       # the reconnect attempt is refused
    summ = a.outages.summary()
    now = _at(2026, 11, 17, 14, 0)
    assert _watch(summ, now, 45, kind_since_min=5)[0] == []         # 45 min down, only 5 of them disconnected
    fired, pages = _watch(summ, now, 71, kind_since_min=31)
    assert fired == ["stall"] and "NOT logged in" in pages[0]       # 31 min disconnected: now it is a stall
    assert a.outages.open["kind"] is None and a.outages.open["kind_since"] >= a.outages.open["start_ts"]
    fired, pages = _watch(summ, _at(2026, 11, 17, 9, 0), 71, kind_since_min=31)
    assert "preopen" in fired and "IB gateway down 71 min" in pages[-1]   # the plain PRE-OPEN words again


def _one_loop_iteration(monkeypatch, adapter, ledger, mirror=None):
    """ONE iteration of the real service loop (service._loop), with the boot builds and the feeds stubbed:
    no live mirror book (unless `mirror`), the blend and the ladder disabled. Returns the alerts it sent."""
    import app.service as svc

    class _Stop(BaseException):
        pass

    class _Wake:
        def wait(self, *a):
            raise _Stop()

        def clear(self):
            pass

        def is_set(self):
            return False

    class _Mgr:
        kill_pending = False
        state = type("S", (), {"legs": {}, "halted": None})()

        def save(self):
            pass

    sent: list = []

    def build_adapter():
        svc.ADAPTER, svc.OUTAGES = adapter, ledger
        svc.LAST["mode"] = "PAPER"
    monkeypatch.setattr(svc, "_build_managers", lambda: None)
    monkeypatch.setattr(svc, "_build_adapter", build_adapter)
    monkeypatch.setattr(svc, "MGR", _Mgr())
    monkeypatch.setattr(svc, "MIRROR", mirror or {})
    monkeypatch.setattr(svc, "BLEND", None)
    monkeypatch.setattr(svc, "DISABLED_BOOK", None)
    monkeypatch.setattr(svc.settings, "ladder_enabled", False, raising=False)
    monkeypatch.setattr(svc.settings, "blend_enabled", False, raising=False)
    monkeypatch.setattr(svc, "nino34_weekly", lambda: None)
    monkeypatch.setattr(svc, "_gateway_restarts", lambda *a, **k: dict(LOGGED_IN))
    monkeypatch.setattr(svc, "send", sent.append)
    monkeypatch.setattr(svc, "ADAPTER", None)
    monkeypatch.setattr(svc, "OUTAGES", None)
    svc.LAST["build_fail_since"] = None
    svc.LADDER_KILL.clear()
    with pytest.raises(_Stop):
        svc._loop(svc.LOOP_GEN, _Wake())
    return sent


@needs_ib_async
def test_s4_reviewer_a_w2_a_boot_whose_sync_ended_late_leaves_no_outage_open_when_nothing_drives_the_adapter(
        wire, monkeypatch):
    """the gateway is healthy: the boot session's sync ends 0.2 s after the connect's (scaled) 0.3 s wait. In a
    service where nothing calls the adapter afterwards - no live mirror book, blend and ladder off - the outage the
    boot opened was never closed (/health down_since for ever, a false stall page at 30 min, a PRE-OPEN page every
    trading morning). Now the loop runs the keepalive while the ledger has an outage open: one iteration ends it."""
    a, gw = wire(lambda s, n: 0.5 if (s, n) == (1, 1) else 0)
    assert a.outages.open is not None                   # the boot opened it (K5: the sync had not ended)
    time.sleep(0.8)                                     # the late end is in the socket; nobody reads it
    _one_loop_iteration(monkeypatch, a, a.outages)
    assert not a.outages.open and a._disconnected_since is None, a.outages.open
    assert len(a.outages.history) == 1 and not wire.sent
    for et_h in (9, 14):
        assert _watch(a.outages.summary(), _at(2026, 11, 17, et_h, 0), 31)[0] == []
    assert a.drops == 0 and gw.sessions == 1 and a.k4_violations == 0


def test_s4_twin_no_open_outage_no_keepalive_and_a_live_mirror_keeps_its_own(monkeypatch, tmp_path):
    """the twin (passes before and after): a healthy service loop calls nothing extra on the adapter - no open
    outage, no keepalive (a healthy session pays nothing). With a live mirror book the mirror's own keepalive
    runs once per iteration, whatever the ledger says (never twice)"""
    calls = []

    class Ad:
        _disconnected_since = None

        def keepalive(self):
            calls.append(1)
            return True

    ledger = OutageLog(str(tmp_path / "o.json"))
    _one_loop_iteration(monkeypatch, Ad(), ledger)
    assert calls == []

    class Book:
        cfg = type("C", (), {"live": True, "engines": ("HG",)})()

        def tick(self, *a, **k):
            pass

        def next_wait(self):
            return None
    ledger.start()
    _one_loop_iteration(monkeypatch, Ad(), ledger, mirror={"live": Book()})
    assert calls == [1]


# ============================================================================== part R: the installed library
@needs_ib_async
def test_r1_oneoff_a_lost_connect_time_answer_is_replaced_before_any_page_and_the_decision_does_not_wait(wire):
    """reviewer B's 'oneoff': ONE session (here the boot's) loses its connect-time open-orders answer; every later
    session is healthy. Before: the keepalive kept it all night - the DOWN page at 30 min (and the watch's stall
    and PRE-OPEN pages), then the decision's first read waited the full bound before the drop that cured it.
    After: the keepalive tries ONE fresh session 2 x the bound after the connect: it syncs, the outage ends long
    before the page is due, and the decision's first read does not wait."""
    a, gw = wire(lambda s, n: None if (s, n) == (1, 1) else 0)
    assert a.outages.open is not None and "openOrders" in a.ib.wrapper._futures
    end = time.monotonic() + ALERT + 1.0                # an idle night, well past the DOWN page's due time
    while time.monotonic() < end:
        assert a.keepalive() is True
        time.sleep(0.1)
    assert wire.sent == []                              # no DOWN, no RECONNECTED: nothing at all
    assert a.drops == 1 and a.connects == 1 and gw.sessions == 2        # ONE fresh session, and it synced
    assert not a.outages.open and len(a.outages.history) == 1
    rec = a.outages.history[0]
    assert rec["alerted"] is False and rec["duration_s"] < 2 * BOUND + 0.6
    t = time.monotonic()
    assert a.open_sell_qty("TECL") == 0                 # the decision's first guarded read: no wait at all
    assert time.monotonic() - t < BOUND / 3
    assert a.order_absent_today("mirror-2026-11-13-S-TECL") is True
    assert a.k4_violations == 0 and gw.count("16", sess=1) == 0         # K4: nothing sent while it was pending


@needs_ib_async
def test_r2_never_first_one_page_one_cause_fresh_sessions_on_the_schedule_then_every_read_fails_at_once(wire):
    """never_first, the overnight shape then the decision: no session's connect-time request is ever answered.
    Fresh sessions are tried (none syncs) and each is kept until the next is due; the outage pages ONCE, naming the
    cause in true words (open orders unreadable; positions and cash ARE read); the service's watch adds no
    diagnosis at any point. At the decision the first read waits the bound for the session's sync, every later one
    fails at once on the same session (before: 20 s each, and a drop + a 15 s reconnect for most), nothing is ever
    sent while a request is pending, and the gateway restart the page asks for ends it.
    D1 round 5 (counts re-baselined on purpose): round 4 tried ONE fresh session and kept it for good; the schedule
    replaces a kept one 2 x the bound after its connect, then 4 x, 8 x ... So over the 3.5 s night (scaled: the bound
    0.3 s, the connect's sync wait 0.3 s, a keepalive every ~0.1 s): 2 drops, 2 reconnects - the boot session
    (sync given up at ~0 s) at ~0.6 s, the next (~0.9 s) at ~2.1 s - and 3 gateway sessions; the third is due
    only 8 x the bound after its connect (~4.8 s), after the decision's reads below."""
    import app.service as svc
    a, gw = wire(lambda s, n: None if n == 1 else 0)
    pages, st = [], {}
    end = time.monotonic() + ALERT + 1.0
    while time.monotonic() < end:
        assert a.keepalive() is True
        summ = a.outages.summary()
        assert summ["currently_down_since"] is not None
        fired = svc._gateway_watch(float(summ["currently_down_since"]) + 31 * 60, summ, LOGGED_IN,
                                   pages.append, state=st)
        assert fired == [], (fired, pages)
        assert summ.get("currently_down_kind") == UNSYNCED              # one cause, the whole time
        time.sleep(0.1)
    assert len(wire.sent) == 1 and "DOWN for over" in wire.sent[0], wire.sent
    page = wire.sent[0]
    assert ("open orders unreadable" in page and "positions and cash are read normally" in page
            and "CAUSE" in page and "fresh gateway session" in page and "already tried" in page
            and "Restart the gateway" in page and "cannot read the account" not in page), page
    assert a.drops == 2 and a.connects == 2 and gw.sessions == 3, (a.drops, a.connects)   # on the schedule
    assert a.outages.history == []                                      # ONE outage, still open
    t = time.monotonic()
    with pytest.raises(ib_mod.ExecutorConnectionError, match="still unanswered"):
        a.open_sell_qty("TECL")                         # the decision's first read: waits the bound, fails closed
    assert BOUND - 0.05 < time.monotonic() - t < BOUND + 0.3
    for _ in range(10):
        t = time.monotonic()
        with pytest.raises(ib_mod.ExecutorConnectionError, match="session kept"):
            a.open_sell_qty("TECL")
        assert a.order_absent_today("mirror-2026-11-13-S-TECL") is None      # never "absent"
        with pytest.raises(ib_mod.ExecutorConnectionError, match="still unanswered"):
            a._all_trades(refresh=True)
        assert time.monotonic() - t < 0.15                              # all three at once: no second wait
    assert a.drops == 2 and gw.sessions == 3 and len(wire.sent) == 1   # no churn, no second page
    assert gw.count("16") == 0 and a.k4_violations == 0 and a.k4_sent == 0
    gw.policy = lambda s, n: 0                          # the gateway restart the page asks for:
    gw.drop()                                           # its FIN, then a gateway that answers
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            assert a.open_sell_qty("TECL") == 0
            break
        except ib_mod.ExecutorConnectionError:
            time.sleep(0.1)
    assert a.open_sell_qty("TECL") == 0 and not a.outages.open and a._disconnected_since is None
    assert [m for m in wire.sent if "RECONNECTED" in m] and len([m for m in wire.sent if "DOWN" in m]) == 1
    assert a.k4_violations == 0


@needs_ib_async
def test_r3_a_session_that_closes_while_a_read_waits_says_so_not_that_the_wait_ran_out(wire, monkeypatch):
    """reviewer B's r3, worded: a gateway restart's FIN lands 0.2 s into a 3 s wait - the read fails closed at once
    and its text says the session closed (before: 'still unanswered after a 3s wait ... restart the gateway')"""
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", 3.0)
    a, gw = wire(lambda s, n: None if (s, n) == (1, 1) else 0, boot=False)
    a.ib.connect("x", 0, clientId=17)
    threading.Timer(0.2, gw.drop).start()
    t = time.monotonic()
    with pytest.raises(ib_mod.ExecutorConnectionError) as exc:
        a.open_sell_qty("SPY")
    assert time.monotonic() - t < 1.0
    assert "closed while this read waited" in str(exc.value) and "still unanswered" not in str(exc.value)
    assert a.open_sell_qty("SPY") == 0 and gw.sessions == 2 and a.k4_violations == 0


@needs_ib_async
def test_r4_an_outage_that_ends_on_its_own_session_is_not_announced_as_a_reconnect(wire, monkeypatch):
    """the DOWN page went out (scaled: 0.4 s), then the SAME session's late sync ended: no reconnect happened, so
    the closing notice must not say RECONNECTED (before: it did) - it says the open orders are readable again"""
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", 1.0)       # the one replacement only at 2 s
    monkeypatch.setattr(ib_mod, "OUTAGE_ALERT_S", 0.4)
    a, gw = wire(lambda s, n: 1.0 if (s, n) == (1, 1) else 0)
    end = time.monotonic() + 1.6
    while time.monotonic() < end:
        assert a.keepalive() is True
        time.sleep(0.1)
    assert not a.outages.open and gw.sessions == 1 and a.drops == 0 and a.connects == 0
    assert len(wire.sent) == 2 and "DOWN for over" in wire.sent[0], wire.sent
    assert "RECONNECTED" not in wire.sent[1] and "READABLE again" in wire.sent[1], wire.sent[1]
    assert "no reconnect" in wire.sent[1]


@needs_ib_async
def test_r5_a_socket_that_dies_inside_the_required_open_orders_request_fails_the_refresh_closed(wire, monkeypatch):
    """reviewer A's NOTE 6: the FIN lands while _all_trades' REQUIRED reqAllOpenOrders is in flight. Before: the
    ConnectionError was logged at debug and skipped - the refresh returned the session's cache without the
    venue's list, and cancel_stock_order answered False ("not found / already cancelled") for an order it never
    saw, the answer on which the blend's stop ratchet places a second stop. After: ExecutorConnectionError, the
    exception every caller already gets from the same call when the gateway is down."""
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", 2.0)       # the FIN, never the timeout, ends it
    a, gw = wire(lambda s, n: None if (s, n) == (1, 2) else 0, boot=False)
    a.ib.connect("x", 0, clientId=17)
    threading.Timer(0.1, gw.drop).start()
    with pytest.raises(ib_mod.ExecutorConnectionError, match="closed while it was in flight"):
        a._all_trades(refresh=True)
    b, gw2 = wire(lambda s, n: None if (s, n) == (1, 2) else 0, boot=False)
    b.ib.connect("x", 0, clientId=17)
    threading.Timer(0.1, gw2.drop).start()
    with pytest.raises(ib_mod.ExecutorConnectionError):
        b.cancel_stock_order("424242")                  # never "False: already gone" on a dead socket
    assert a.k4_violations == 0 and b.k4_violations == 0


# what a healthy session sends for five rounds, measured on the code before this round: the twin below pins it
# (16 reqAllOpenOrders, 99 reqCompletedOrders, 7 reqExecutions, 49 reqCurrentTime)
HEALTHY_WIRE = {"16": 15, "99": 5, "7": 5, "49": 5}


@needs_ib_async
def test_r6_twin_a_healthy_session_sends_exactly_what_it_sent_before_and_never_pumps_in_the_guard(wire,
                                                                                                    monkeypatch):
    """the twin (passes before and after): five rounds of the three guarded reads and a keepalive on a healthy
    gateway - the same messages on the wire as before this round, not one ib.sleep inside the guard, no outage,
    no drop, no page (every keepalive proves the session here: PROVE_FRESH_S 0, so the count does not depend on
    how fast the rounds run)"""
    monkeypatch.setattr(ib_mod, "PROVE_FRESH_S", 0.0)
    a, gw = wire(lambda s, n: 0)
    sleeps = []
    real_sleep, orig = a.ib.sleep, a._open_orders_unanswered

    def guard():
        a.ib.sleep = lambda secs=0: (sleeps.append(secs), real_sleep(secs))[1]
        try:
            return orig()
        finally:
            a.ib.sleep = real_sleep
    a._open_orders_unanswered = guard
    before = {m: gw.count(m) for m in HEALTHY_WIRE}
    for _ in range(5):
        assert a.open_sell_qty("TECL") == 0
        assert a.order_absent_today("mirror-2026-11-13-S-TECL") is True
        assert isinstance(a._all_trades(refresh=True), list)
        assert a.keepalive() is True
        time.sleep(0.25)                                # under ib_async's 45 requests/s client throttle
    time.sleep(0.1)
    sent = {m: gw.count(m) - before[m] for m in HEALTHY_WIRE}
    assert sent == HEALTHY_WIRE, sent
    assert sleeps == [] and a.drops == 0 and a.connects == 0 and gw.sessions == 1
    assert not wire.sent and not a.outages.open and a.outages.history == [] and a.k4_violations == 0


# ============================================================================== part M: the mirror, virtual time
CONNECT_SYNC_S = 15.0


class VT:
    """one virtual clock: the adapter's time.monotonic and the mirror's clock advance together"""

    def __init__(self, clock):
        self.clock, self.mono = clock, 1_000_000.0

    def now(self):
        return self.mono

    def advance(self, s):
        if s > 0:
            self.mono += s
            self.clock.now += timedelta(seconds=s)


class PendingIB(StaleIB):
    """what ib_async 2.1.0 does with a connect-time open-orders request not answered within IB.connect's timeout:
    the connect waits that timeout (15 s), only logs it, and the request stays in wrapper._futures under
    "openOrders" until its end pops it - processed only when something pumps. policy(n) for the n-th session from
    now on: 0 = answered inside the connect; x > 0 = its end arrives x s after the connect began; None = never.
    Counts every reqAllOpenOrders sent while one is pending (K4: must never happen)."""

    def __init__(self, acct, prices):
        super().__init__(acct, prices)
        self.policy, self.n_sessions, self.oo_end, self.vt = None, 0, None, None
        self.violations, self.pumps = 0, 0

    def connect(self, host, port, clientId, timeout=15):
        super().connect(host, port, clientId, timeout)
        self.oo_end = None
        if self.policy is None or self.vt is None:
            return
        self.n_sessions += 1
        late = self.policy(self.n_sessions)
        if late == 0:
            return
        start = self.vt.now()
        self.wrapper._futures["openOrders"] = object()
        self.vt.advance(CONNECT_SYNC_S)                 # IB.connect waited its timeout for it, then only logged it
        self.oo_end = None if late is None else start + late

    def sleep(self, secs=0):
        self.pumps += 1
        if self.vt is not None:
            self.vt.advance(secs)
            if self.oo_end is not None and self.connected and not self.dead and self.vt.now() >= self.oo_end:
                self.wrapper._futures.pop("openOrders", None)
                self.oo_end = None
        return super().sleep(secs)

    def reqAllOpenOrders(self):
        if "openOrders" in self.wrapper._futures:
            self.violations += 1
        return super().reqAllOpenOrders()


class PendingRig(Rig):
    ib_cls = PendingIB


def _rig(tmp_path, monkeypatch):
    r = PendingRig(tmp_path, monkeypatch).invested()
    vt = VT(r.clock)
    monkeypatch.setattr(ib_mod.time, "monotonic", vt.now)
    r.ib.vt, r.vt = vt, vt
    # production values for everything this round touches (Rig zeroes the backoff, IBRig the pump tick)
    monkeypatch.setattr(ib_mod, "WAIT_TICK_S", 0.25)
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", 20.0)
    monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 15.0)
    monkeypatch.setattr(ib_mod, "OUTAGE_ALERT_S", 30 * 60.0)
    r.ad._reconnect_backoff, r.ad._next_reconnect_ts = 15.0, 0.0
    r.ad.reconnect_backoff_max_s, r.ad.mirror_only = 30.0, True        # service._mirror_keepalive's setting
    r.ad.outages = OutageLog(str(tmp_path / "outages.json"))

    def pause(s):
        vt.advance(s)
        r.clock.slept.append(s)
        return r.clock.interrupt
    r.m._sleep = pause
    r.ticks = []
    r.guard_pumps = []                                  # per guarded read: the pumps spent waiting in the guard
    orig = ib_mod.IBAdapter._open_orders_unanswered

    def counted(self):
        p0 = r.ib.pumps
        out = orig(self)
        r.guard_pumps.append(r.ib.pumps - p0)
        return out
    monkeypatch.setattr(ib_mod.IBAdapter, "_open_orders_unanswered", counted)
    return r


def _tick_at(r, hms, day=D2, keepalive=True):
    """one service-loop iteration: the mirror's tick, then the keepalive (service._loop: _mirror_cycle, then
    _mirror_keepalive), with the loop parked until `hms`"""
    r.vt.advance((tm.at(hms, day) - r.clock.now).total_seconds())
    t0 = r.vt.now()
    r.m.tick(r.ad)
    took = r.vt.now() - t0
    if keepalive:
        r.ad.keepalive()
    r.ticks.append((hms, round(took, 2)))
    return took


def _night(r, policy, every=300.0):
    """day 1 after the close: at 23:45 the gateway's nightly restart drops the session and every new session
    follows `policy`; the service loop parks `every` s between iterations and runs the keepalive, until 09:30"""
    r.vt.advance((tm.at("23:45:00", tm.DAY) - r.clock.now).total_seconds())
    r.ib.policy = policy
    r.ib.drop()
    until = tm.at("09:30:00", D2)
    while r.clock.now < until:
        r.ad.keepalive()
        r.vt.advance(every)


def _decision(r, monkeypatch, blip_policy=None):
    """day 2: three sells and three buys (ROT). The morning check at 09:30:05; with blip_policy, the gateway drops
    at 15:54:20 and every NEW session follows it; the decision tick at 15:54:26 and the loop's ticks after it.
    Returns (orders placed, the virtual instants they were placed at)."""
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    n = len(r.ib.placed)
    stamps = []
    real = r.ib.placeOrder
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (stamps.append(r.clock.now), real(c, o))[1])
    _tick_at(r, "09:30:05")
    r.vt.advance((tm.at("15:54:20", D2) - r.clock.now).total_seconds())
    if blip_policy is not None:
        r.ib.policy = blip_policy
        r.ib.drop()
    r.guard_pumps.clear()
    _tick_at(r, "15:54:26")
    for hms in AFTER:
        _tick_at(r, hms)
    return r.ib.placed[n:], stamps


ROT_ORDERS = [("BIL", "SELL", 315), ("BOXX", "SELL", 237), ("PULS", "BUY", 438), ("SOXL", "SELL", 270),
              ("TECL", "BUY", 161), ("TQQQ", "BUY", 360)]


def test_m1_slow_first_45_a_gateway_answering_every_sessions_sync_45s_late_trades_inside_the_window(tmp_path,
                                                                                                     monkeypatch):
    """reviewer B's NOTE 4 (slow_first_45): a reconnect right before the decision whose connect-time open-orders
    end comes 45 s after the connect began (30 s after IB.connect gave up on it), on EVERY new session. Before: the
    first read waited 20 s, dropped the session, and every new session brought the same late request back -
    nothing traded. After: a read that waited for the session's own sync fails closed and KEEPS the session, the
    late end lands, the run trades - every order inside the cancel instant, nothing sent while one was pending."""
    r = _rig(tmp_path, monkeypatch)
    placed, stamps = _decision(r, monkeypatch, blip_policy=lambda n: 45.0)
    row = r.m.state["last_run"]
    assert sorted((s, a, q) for s, a, q, _ in placed) == ROT_ORDERS, (row, r.red()[-3:], r.ticks)
    assert row["session"] == D2 and row["outcome"] == "traded"
    assert max(stamps) < tm.at("15:59:00", D2)
    assert r.ib.violations == 0 and r.ib.n_sessions == 1            # ONE session: kept for its late end
    assert r.ad._disconnected_since is None and not r.ad.outages.open
    assert not [m for m in r.sent if "DOWN" in m]
    sound(r)


def test_m2_twin_slow_first_25_still_trades_on_the_first_session(tmp_path, monkeypatch):
    """the twin (passes before and after): the end 25 s after the connect began lands inside the first read's
    wait; the session trades at once"""
    r = _rig(tmp_path, monkeypatch)
    placed, stamps = _decision(r, monkeypatch, blip_policy=lambda n: 25.0)
    assert sorted((s, a, q) for s, a, q, _ in placed) == ROT_ORDERS
    assert r.m.state["last_run"]["outcome"] == "traded" and max(stamps) < tm.at("15:59:00", D2)
    assert r.ib.violations == 0 and r.ib.n_sessions == 1
    sound(r)


def test_m3_oneoff_overnight_is_cured_before_any_page_and_the_decision_trades_with_no_wait(tmp_path, monkeypatch):
    """the nightly restart's reconnect loses its connect-time answer (one session; every later one is healthy).
    Before: that session was kept all night - the DOWN page at 00:15, then the decision's first sell check waited
    the full 20 s for an answer that never came. After: the keepalive replaces it once (2 x the bound after its
    connect, within one loop iteration), the outage ends with no page, and the decision runs as on a normal day:
    no wait in any guarded read, every order inside the window."""
    r = _rig(tmp_path, monkeypatch)
    _night(r, lambda n: None if n == 1 else 0)
    assert not r.ad.outages.open and len(r.ad.outages.history) == 1 and r.ib.n_sessions == 2
    assert r.ad.outages.history[0]["alerted"] is False
    placed, stamps = _decision(r, monkeypatch)
    assert sorted((s, a, q) for s, a, q, _ in placed) == ROT_ORDERS
    assert r.m.state["last_run"]["outcome"] == "traded" and max(stamps) < tm.at("15:54:30", D2)
    assert r.guard_pumps and set(r.guard_pumps) == {0}, r.guard_pumps       # not one wait
    assert r.sent == [], r.sent                                             # no DOWN, no RECONNECTED
    assert r.ib.violations == 0
    sound(r)


def test_m4_never_first_overnight_then_the_decision_one_page_fresh_sessions_on_the_schedule(tmp_path, monkeypatch):
    """never_first from the nightly restart on: the keepalive tries fresh sessions (none syncs) and keeps each until
    the next is due; the DOWN page goes out once overnight, naming the cause; at the decision nothing is sold or
    bought (fail closed), each session met there waits its bound once and every later read on it fails at once -
    before, every read waited 20 s and most dropped the session for a 15 s reconnect.
    D1 round 5 (counts re-baselined on purpose): round 4 tried ONE fresh session all night and kept it for good (2
    sessions); the schedule replaces a kept one 40 s after its connect gave up, then 80, 160, 320, 640 s, then every
    900 s (the cap), each at the first keepalive (every 300 s here, the loop's poll) once due. So 41 sessions from
    23:45 to 09:30: the reconnect after the nightly drop (23:45:00), five doubling steps (23:50:15, 23:55:30,
    00:00:45, 00:11:00, 00:26:15), then one per 915 s - the 900 s cap met by the 300 s keepalive cadence after the
    15 s connect - 35 more (00:41:30 ... 09:20:00): 3.9 sessions an hour, each holding the loop 15 s. At the
    decision the session kept since 09:20 is overdue (this harness runs no keepalive between 09:30 and 15:54): the
    first guarded read waits its bound for it, then takes the replacement; the fresh session's first read waits
    its bound; every later read fails at once - 2 full waits, 1 reconnect, 42 sessions in all. The next
    replacement is due 900 s after that connect, past the window."""
    r = _rig(tmp_path, monkeypatch)
    connects = []
    real_connect = r.ib.connect

    def connect(*args, **kw):
        connects.append(r.vt.now())
        return real_connect(*args, **kw)
    monkeypatch.setattr(r.ib, "connect", connect)
    _night(r, lambda n: None)
    downs = [m for m in r.sent if "DOWN for over" in m]
    assert len(downs) == 1 and "open orders unreadable" in downs[0] and "already tried" in downs[0], r.sent
    assert r.ib.n_sessions == len(connects) == 41, len(connects)
    gaps = [round(b - a) for a, b in zip(connects, connects[1:])]
    assert gaps[:5] == [315, 315, 315, 615, 915] and set(gaps[5:]) == {915}, gaps
    assert r.ad.outages.open is not None and r.ad.outages.history == []
    assert r.ad.outages.summary()["currently_down_kind"] == UNSYNCED
    placed, _ = _decision(r, monkeypatch)
    assert placed == [] and r.ib.violations == 0
    assert r.m.state["last_run"]["session"] == D2
    waits = [p for p in r.guard_pumps if p > 0]
    assert len(waits) == 2 and len(r.guard_pumps) > 10, r.guard_pumps        # one full wait per session, then at once
    assert r.ib.n_sessions == 42                                            # one replacement at the decision
    assert len([m for m in r.sent if "DOWN" in m]) == 1 and not [m for m in r.sent if "RECONNECTED" in m]


def test_m5_twin_oneoff_met_at_the_decision_still_trades_inside_the_window(tmp_path, monkeypatch):
    """the twin (passes before and after): the reconnect right before the decision loses its answer, the next
    session is healthy. The session is replaced once (here by the read that meets it 2 x the bound after its
    connect) and the run trades inside the window"""
    r = _rig(tmp_path, monkeypatch)
    placed, stamps = _decision(r, monkeypatch, blip_policy=lambda n: None if n == 1 else 0)
    assert sorted((s, a, q) for s, a, q, _ in placed) == ROT_ORDERS, (r.red()[-3:], r.ticks)
    assert r.m.state["last_run"]["outcome"] == "traded" and max(stamps) < tm.at("15:59:00", D2)
    assert r.ib.violations == 0
    sound(r)


# ============================================================================== part C: the cancel instant
CANCEL = tm.at("15:59:00", D2)


def _stamped(r, monkeypatch):
    stamps = []
    real = r.ib.placeOrder
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (stamps.append(r.clock.now), real(c, o))[1])
    return stamps


def _slow_after(r, real_open, slow_from, first_ok=False):
    """open_sell_qty that fails closed (an unsynced session's read) until `slow_from`, then answers - but only
    after 20 s of waiting for an earlier request (K5's bound): a check that starts before the cancel instant and
    ends after it"""
    calls = []

    def open_sell_qty(sym, exclude=None):
        calls.append(r.clock.now)
        if first_ok and len(calls) == 1:
            return real_open(sym, exclude=exclude)
        if r.clock.now < slow_from:
            raise ib_mod.ExecutorConnectionError("this session's connect-time open-orders sync is still unanswered: "
                                                 "nothing read, session kept for its late answer")
        r.clock.now += timedelta(seconds=20)
        return real_open(sym, exclude=exclude)
    return open_sell_qty


def test_c1_a_sell_check_that_outlasts_the_cancel_instant_sends_nothing_after_it(tmp_path, monkeypatch):
    """reviewer A's NOTE 3: _work looked at the cancel instant once, on entry. A sell check that began at 15:58:50
    and answered (after a 20 s wait) at 15:59:10 was followed by the write-ahead and a MKT DAY sell AFTER the
    cancel instant. Now the instant is looked at again right before the write-ahead: the order is booked exactly
    as one met past it on entry ("not sent: the window closed")"""
    r = Rig(tmp_path, monkeypatch).invested()
    stamps = _stamped(r, monkeypatch)
    slow = _slow_after(r, r.ad.open_sell_qty, tm.at("15:58:50", D2))
    tmc._after_the_plan(r, monkeypatch, lambda: monkeypatch.setattr(r.ad, "open_sell_qty", slow))
    r.tick("15:55:05", day=D2)
    assert stamps == []                                 # every check so far failed closed
    r.tick("15:58:50", day=D2)
    r.tick("15:59:30", day=D2)
    assert [s for s in stamps if s >= CANCEL] == [], stamps
    row = r.m.state["last_run"]
    assert [(o["symbol"], o["filled"], o["how"]) for o in row["orders"]] == [("BIL", 0, "not sent: the window closed")]
    assert r.m.book.positions()["BIL"] == 315 and r.venue_pos()["BIL"] == 315
    sound(r)


def test_c2_an_unconfirmed_placement_whose_check_outlasts_the_cancel_instant_is_not_placed_again(tmp_path,
                                                                                                monkeypatch):
    """the 'intent' branch: the first placement raised before it reached the venue (state intent, proven absent
    on the next pass), and the re-check before placing it again began before the cancel instant and answered after
    it. Before: placed at 15:59:10. Now: booked exactly as such an order met past the cancel instant on entry
    ("never reached the venue (...)")"""
    r = Rig(tmp_path, monkeypatch).invested()
    stamps = _stamped(r, monkeypatch)
    slow = _slow_after(r, r.ad.open_sell_qty, tm.at("15:58:50", D2), first_ok=True)
    real_place, tries = r.ad.place_stock_order, []

    def place_stock_order(*a, **k):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("no venue ack within 10s (status 'PendingSubmit') - state UNKNOWN")
        return real_place(*a, **k)

    def install():
        monkeypatch.setattr(r.ad, "open_sell_qty", slow)
        monkeypatch.setattr(r.ad, "place_stock_order", place_stock_order)
    tmc._after_the_plan(r, monkeypatch, install)
    r.tick("15:55:05", day=D2)
    assert stamps == [] and len(tries) == 1
    rec = next(iter(r.m.state["run"]["orders"].values()))
    assert rec["state"] == "intent"
    r.tick("15:58:50", day=D2)
    r.tick("15:59:30", day=D2)
    assert [s for s in stamps if s >= CANCEL] == [] and len(tries) == 1, (stamps, tries)
    row = r.m.state["last_run"]
    assert [(o["symbol"], o["filled"]) for o in row["orders"]] == [("BIL", 0)]
    assert row["orders"][0]["how"].startswith("never reached the venue (no venue ack"), row["orders"][0]["how"]
    assert r.venue_pos()["BIL"] == 315
    sound(r)


# ============================================================================== part F and the words
class _DedupeFifo(ib_mod.IBAdapter):
    """the installed ib_async session (IB, Client, Wrapper, util.run, the trades cache) with only Client.send
    replaced (tests/test_mirror_connection._FifoAdapter's pattern), plus: openOrder carries the orderRef,
    completed orders are never answered (the 2026-09-08 gateway)"""

    def _connect(self):
        import asyncio
        import types as _t
        from ib_async import Order, OrderState
        from ib_async.client import Client
        self.venue, self.delays = [], []
        ib, loop, busy = self.ib, asyncio.get_event_loop(), [0.0]
        ib.client._apiReady, ib.client.connState, ib.client._serverVersion = True, Client.CONNECTED, 176
        ib.wrapper.clientId = ib.client.clientId = 17
        ib.client.conn.transport = _t.SimpleNamespace(write=lambda d: None, write_eof=lambda: None,
                                                      close=lambda: None)
        ib.client._reqIdSeq = 1000

        def send(*fields, makeEmpty=True):
            mid, now = int(fields[0]), loop.time()
            if mid in (5, 16):
                start_delay, gap = self.delays.pop(0) if self.delays else (0.01, 0.0)
                t = max(now, busy[0]) + start_delay
                for o in [o for o in self.venue if mid == 16 or o.clientId == 17]:
                    oo = Order(orderId=o.orderId, clientId=o.clientId, permId=o.permId, action=o.action,
                               totalQuantity=o.totalQuantity, orderType=o.orderType, orderRef=o.orderRef)
                    c = real_ib_async.Stock("TECL", "SMART", "USD")
                    c.conId = 12345
                    loop.call_at(t, ib.wrapper.openOrder, oo.orderId, c, oo, OrderState(status="Submitted"))
                    loop.call_at(t, ib.wrapper.orderStatus, oo.orderId, "Submitted", 0.0,
                                 float(oo.totalQuantity), 0.0, oo.permId, 0, 0.0, oo.clientId, "", 0.0)
                    t += gap
                loop.call_at(t, ib.wrapper.openOrderEnd)
                busy[0] = t
            elif mid == 7:
                loop.call_at(max(now, busy[0]) + 0.001, ib.wrapper.execDetailsEnd, int(fields[2]))
            # 99 (reqCompletedOrders): never answered
        ib.client.send = send


@needs_ib_async
def test_f1_twin_an_order_the_late_sync_delivers_during_the_wait_is_deduped_not_placed_again(monkeypatch):
    """reviewer B's test_f1, the twin that PINS _all_trades' re-read of the session's trades after the wait
    ('the wait above may have pumped'; passes before and after this round, fails with that line removed): our own
    SELL from an earlier session is delivered by the connect-time sync's LATE answer during the placement's dedupe
    wait and fills a moment later, before the refresh's own reqAllOpenOrders; completed orders do not answer. The
    dedupe must still find it - a second SELL of the same shares would be a short."""
    import asyncio
    monkeypatch.setitem(sys.modules, "ib_async", real_ib_async)
    monkeypatch.setattr(ib_mod, "VENUE_HISTORY_TIMEOUT_S", 0.3)
    monkeypatch.setattr(ib_mod, "PLACE_ACK_TIMEOUT_S", 0.05)
    a = _DedupeFifo(_RealCfg())
    oid = "mirror-2026-11-12-S-TECL"
    x = real_ib_async.Order(orderId=41, clientId=17, permId=80041, action="SELL", totalQuantity=50,
                            orderType="MKT", orderRef=oid)
    a.venue.append(x)
    c = real_ib_async.Stock("TECL", "SMART", "USD")
    c.conId = 12345
    a._stock_contracts["TECL"] = c
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    a.delays[:] = [(0.5, 0.0)]                          # the connect-time sync's answer arrives at +0.5 s

    def fills():
        a.venue.remove(x)                               # filled at the venue: no longer open
        a.ib.wrapper.orderStatus(41, "Filled", 50.0, 0.0, 40.0, 80041, 0, 40.0, 17, "", 0.0)
    loop.call_at(t0 + 0.51, fills)
    a.ib.RequestTimeout = 0.3
    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        a.ib.reqOpenOrders()                            # the connect-time sync: timed out, only logged
    a.ib.RequestTimeout = 0
    placed = []
    monkeypatch.setattr(a.ib, "placeOrder", lambda contract, order: placed.append(order) or (_ for _ in ()).throw(
        RuntimeError("a second order was placed")))
    out = a.place_stock_order("TECL", -50, "MKT", client_order_id=oid)
    assert placed == [], placed
    assert out.get("duplicate") is True and out.get("status") == "filled", out


def test_w1_the_kill_alert_names_the_open_orders_wait():
    """reviewer B's NOTE 3: the /kill alert's bound did not mention that an open-orders read can first wait up to
    the bound for an earlier request"""
    import app.service as svc
    assert "open-orders read can first wait up to 20s" in svc.MIRROR_KILL_BOUND
    assert f"{ib_mod.VENUE_HISTORY_TIMEOUT_S:.0f}s" == "20s"         # the number it quotes is the adapter's
