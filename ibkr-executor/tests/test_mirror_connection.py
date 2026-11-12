"""2026-11-12: the Composer mirror met the gateway's nightly restart at the open, on a connection
ib_async still believed in. Its morning check PASSED "the account holds exactly the mirror book" on
yesterday's cached positions and then alerted "the account reports no cash claim".

What ib_async 2.1.0 does (read in the installed source, and run against a socket - the R tests below):
  a  IB.isConnected() is client.isReady() -> client._apiReady (ib.py:410-412, client.py:144-146). It is
     cleared only by client.reset() (client.py:119-121), reached from client._onSocketDisconnected
     (client.py:418-437) - the handler of Connection.connection_lost (connection.py:62-65), an asyncio
     protocol callback. The sync facade runs the loop only inside ib.sleep() / a request (util.py:397-405,
     ib.py:427-428), so a socket that closed while nobody pumped still reads "connected".
  b  IB.positions() / accountValues() / trades() / fills() read wrapper caches (ib.py:541-552, 501-514,
     594-596, 618-620) that are emptied only by wrapper.reset() (wrapper.py:313-317), called from
     wrapper.connectionClosed (wrapper.py:361-368) and IB.disconnect (ib.py:405-406): until the close
     is processed they hold the dead session's values, afterwards they are EMPTY.
  c  the close is processed in stream order, after whatever the gateway sent before it, and one
     ib.sleep(0) reads a bounded amount: behind a backlog (a night of account updates) the first
     pump leaves the session "connected" with its old caches. Measured on a socket: any backlog up
     to 60 kB is gone in one pump, 200 kB takes two, 1.5 MB three (R1).
  d  the pump that does process the close can raise ConnectionError("Socket disconnect") itself
     (util.py:355-362: globalErrorEvent, emitted by wrapper.connectionClosed, cancels the running task).
  e  a request on a session known closed raises ConnectionError("Not connected") (client.py:150-151,
     164-165, 250-251); one sent while the close is still unprocessed fails with
     ConnectionError("Socket disconnect") once the loop reaches it (wrapper.py:362-365).
  f  IB.connect() re-syncs positions and account values (ib.py:2056, 2065-2067) but only LOGS a sync
     request that times out (ib.py:2077-2084; raiseSyncErrors defaults to False, ib.py:337): it can
     return "connected" with an EMPTY position list. wrapper.positionEnd pops the request
     (wrapper.py:619-620, 383-389), so "positions" stays in wrapper._futures until it arrives.

StaleIB below is tests/ibrig.py's VenueIB with exactly a-f added. C1-C9 drive the real IBAdapter and a
live MirrorManager over it; R1-R4 drive the real IBAdapter over the INSTALLED ib_async on a socket.
"""
from __future__ import annotations

import copy
import inspect
import socket
import struct
import threading
import time
import types
from datetime import timedelta

import pytest

import app.ib_adapter as ib_mod
import test_ib_stock_adapter as tia
import test_mirror as tm
from app import mirror as mm
from app.outages import OutageLog
from ibrig import IBRig, VenueIB
from test_mirror import DAY, payload

try:                                    # the installed library, for the R tests only
    import ib_async as real_ib_async
except Exception:  # noqa: BLE001
    real_ib_async = None

D2 = "2026-11-11"
T2 = dict(tm.T1, HG={"TQQQ": 1.0})      # day 2: HG sells its BIL and buys TQQQ


class StaleIB(VenueIB):
    """VenueIB + a-f of the module docstring. drop(backlog=n): the socket closes now; the client
    learns of it on pump n+1 (n pumps read queued data first), or at its next request."""

    def __init__(self, acct, prices):
        super().__init__(acct, prices)
        self.gateway_up = True
        self.dead = False               # the socket is closed and the client has not processed it
        self.backlog = 0
        self.pump_raises = False        # d
        self.cache_pos, self.cache_vals = [], []
        self.recv = 0
        self.sync_positions = True      # False: the connect-time position download times out (f)
        self.positions_answer = True    # False: an explicit reqPositions times out too
        self.position_requests = 0
        self.silent = False             # the death carried no FIN: a pump learns nothing (g)
        self.blackhole = False          # ... and a request is never answered (no RST either)
        self.requests: list = []        # every request that reached a live session, in order
        self.wrapper = types.SimpleNamespace(_futures={})
        self.client = types.SimpleNamespace(connectionStats=self._stats)

    # --- the connection
    def _stats(self):
        if not self.connected:
            raise ConnectionError("Not connected")
        return types.SimpleNamespace(numBytesRecv=self.recv)

    def drop(self, backlog=0, pump_raises=False, silent=False, blackhole=False):
        self.cache_pos, self.cache_vals = VenueIB.positions(self), VenueIB.accountValues(self)
        self.dead, self.backlog, self.pump_raises = True, backlog, pump_raises
        self.silent, self.blackhole = silent or blackhole, blackhole

    def _closed(self):                  # client.reset() + wrapper.reset()
        self.connected = False
        self._trades = []
        self.wrapper._futures.clear()

    def _req(self, name=""):            # e
        if not self.connected:
            raise ConnectionError("Not connected")
        if self.dead:
            if self.blackhole:          # written into the void: only the caller's own timeout ends it
                assert self.RequestTimeout, f"{name or 'a request'} waits for ever on a session that never answers"
                raise TimeoutError()
            self._closed()
            raise ConnectionError("Socket disconnect")
        self.requests.append(name)

    def connect(self, host, port, clientId, timeout=15):
        self.connect_calls += 1
        if not self.gateway_up:
            raise ConnectionRefusedError("gateway down (simulated)")
        self._closed()
        self.connected, self.dead, self.backlog = True, False, 0
        self.silent = self.blackhole = False
        if not self.sync_positions:
            self.wrapper._futures["positions"] = object()

    def disconnect(self):
        self._closed()

    def sleep(self, secs=0):            # a, c, d
        if self.dead and self.connected and not self.silent:
            if self.backlog > 0:
                self.backlog -= 1
                self.recv += 1
            else:
                self._closed()
                if self.pump_raises:
                    raise ConnectionError("Socket disconnect")
        return super().sleep(secs)

    # --- the session's caches (b, f)
    def positions(self):
        if not self.connected or "positions" in self.wrapper._futures:
            return []
        return list(self.cache_pos) if self.dead else super().positions()

    def accountValues(self):
        if not self.connected:
            return []
        return list(self.cache_vals) if self.dead else super().accountValues()

    def managedAccounts(self):
        return ["DU1"] if self.connected else []

    def fills(self):
        return super().fills() if self.connected else []

    # --- requests
    def reqPositions(self):
        self._req()
        self.position_requests += 1
        if not self.positions_answer:
            raise TimeoutError()
        self.wrapper._futures.pop("positions", None)
        return self.positions()

    def reqCurrentTime(self):
        self._req("reqCurrentTime")
        return super().reqCurrentTime()

    def accountSummary(self):
        self._req()
        return self.accountValues()

    def qualifyContracts(self, *contracts):
        self._req("qualifyContracts")
        return super().qualifyContracts(*contracts)

    def reqMktData(self, contract, generic, snapshot, regulatory):
        if not self.connected:
            raise ConnectionError("Not connected")
        if self.dead:                   # written into a dead socket: no tick ever comes
            return tia.FakeTicker(float("nan"))
        return super().reqMktData(contract, generic, snapshot, regulatory)

    def reqAllOpenOrders(self):
        self._req("reqAllOpenOrders")
        return super().reqAllOpenOrders()

    def reqCompletedOrders(self, apiOnly=True):
        self._req()
        return super().reqCompletedOrders(apiOnly)

    def reqExecutions(self):
        self._req()
        return super().reqExecutions()

    def placeOrder(self, contract, order):
        if not self.connected:
            raise ConnectionError("Not connected")
        assert not self.dead, "an order was written into a dead socket"
        return super().placeOrder(contract, order)

    def cancelOrder(self, order):
        if not self.connected:
            raise ConnectionError("Not connected")
        return super().cancelOrder(order)


class Rig(IBRig):
    ib_cls = StaleIB

    def __init__(self, tmp_path, monkeypatch, **kw):
        monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 0.0)     # every call may retry the connect
        self.sent: list = []                                         # the adapter's own (outage) alerts
        import app.alerts as alerts_mod
        monkeypatch.setattr(alerts_mod, "send", self.sent.append)
        super().__init__(tmp_path, monkeypatch, **kw)

    def invested(self):
        """day 1 traded and checked; the book and the account hold the same five positions"""
        self.tick("15:00")
        self.tick("15:55:05")
        self.tick("15:56:40")
        assert self.m.state["last_run"]["outcome"] == "traded" and self.m.state["check"]["done"] is True
        assert self.m.book.positions() == self.venue_pos() and not self.red()
        self.brain.make = lambda now: payload(now, T2, session=D2)
        return self

    def sell_by_hand(self, symbol):
        """the operator sells a position at the venue while the executor is not connected"""
        q = self.acct.pos.pop(symbol)
        self.acct.cash += q * tm.PX[symbol]
        return q


def sound(r):
    assert r.m.book.positions() == r.venue_pos()
    assert r.m.book.cash() == pytest.approx(r.acct.cash, abs=0.01)


# ------------------------------------------------------------------ C1: the incident, end to end
def test_c0_the_fake_models_a_connection_that_died_while_nobody_pumped(tmp_path, monkeypatch):
    """the reproduction's premise, on the fake alone (a-c): stale "connected", cached positions and
    cash until the close is processed, EMPTY caches and "Not connected" afterwards"""
    r = Rig(tmp_path, monkeypatch).invested()
    held = r.venue_pos()
    r.ib.drop(backlog=1)
    r.sell_by_hand("BIL")
    cached = lambda: {p.contract.symbol: int(p.position) for p in r.ib.positions()}  # noqa: E731
    assert r.ib.isConnected() and cached() == held                  # not pumped: yesterday's list
    r.ib.sleep(0)
    assert r.ib.isConnected() and cached() == held                  # one pump: only the backlog was read
    r.ib.sleep(0)
    assert not r.ib.isConnected() and cached() == {} and r.ib.accountValues() == []
    with pytest.raises(ConnectionError, match="Not connected"):
        r.ib.accountSummary()


@pytest.mark.parametrize("backlog", [0, 1, 3])
def test_c1_the_incident_overnight_drop_then_the_morning_check_reconnects_and_reads_fresh(tmp_path, monkeypatch, backlog):
    """2026-11-12 as it happened (backlog=1): nothing touched the adapter overnight; the first tick
    after the open. Before: positions passed on the cache, then "no cash claim" in red."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop(backlog=backlog)
    r.tick("09:30:05", day=D2)
    assert r.ib.connect_calls == 2 and r.ib.isConnected() and not r.ib.dead
    assert r.m._prechecked == D2 and not r.red()
    assert r.ad.positions_snapshot()["stocks"] == r.venue_pos() == r.m.book.positions()
    assert r.ad.account_cash()["total_cash"] == pytest.approx(r.acct.cash) and r.ad.last_cash_error is None


@pytest.mark.parametrize("backlog", [0, 1, 3])
def test_c2_a_position_sold_by_hand_while_disconnected_is_a_mismatch_not_a_pass_on_the_cache(tmp_path, monkeypatch, backlog):
    """Before: backlog 1 said "no cash claim" (the positions had PASSED on the cache); backlog 3
    said nothing at all - positions and cash both read from the dead session."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop(backlog=backlog)
    sold = r.sell_by_hand("BIL")
    r.tick("09:30:05", day=D2)
    red = r.red()
    assert len(red) == 1 and "today's decision will be refused unless fixed" in red[0]      # at once: no retry
    assert f"BIL: the book holds {sold}, the venue 0" in red[0] and "cash claim" not in red[0]
    assert r.m._prechecked == D2 and r.m._precheck_since is None


# ------------------------------------------------------------------ C3: the adapter's surfaces
SURFACES = {
    "positions_snapshot": lambda a: a.positions_snapshot(),
    "account_cash": lambda a: a.account_cash(),
    "stock_position": lambda a: a.stock_position("BIL"),
    "open_sell_qty": lambda a: a.open_sell_qty("BIL"),
    "spot_ex": lambda a: a.spot_ex("BIL"),
    "find_stock_order": lambda a: a.find_stock_order(f"mirror-{DAY}-B-BIL"),
    "stock_order_fills": lambda a: a.stock_order_fills(f"mirror-{DAY}-B-BIL"),
    "order_absent_today": lambda a: a.order_absent_today("mirror-none"),
    "cancel_stock_order": lambda a: a.cancel_stock_order("987654"),
    "cancel_inactive_stock_order": lambda a: a.cancel_inactive_stock_order("mirror-none"),
    "place_stock_order": lambda a: a.place_stock_order("BIL", -1, "MKT", client_order_id="c3-sell"),
    "place_limit_order": lambda a: a.place_limit_order("BIL", 1, 95.0, client_order_id="c3-buy"),
}


@pytest.mark.parametrize("name", sorted(SURFACES))
@pytest.mark.parametrize("backlog, pump_raises", [(0, False), (2, False), (2, True)])
def test_c3_no_mirror_facing_surface_runs_on_a_dead_connection(tmp_path, monkeypatch, name, backlog, pump_raises):
    """every surface the mirror uses pumps until the socket is drained, THEN requires connected: the
    dead session is replaced before anything is read from it or written to it (StaleIB.placeOrder
    asserts no order goes into a dead socket). Before: none reconnected first - the reads answered
    from the cache, and a lookup that died mid-request was read as "the venue has no such order"."""
    r = Rig(tmp_path, monkeypatch).invested()
    seen = []
    real = r.ib.connect
    monkeypatch.setattr(r.ib, "connect", lambda *a, **k: (seen.append((r.ib.dead, r.ib.backlog)), real(*a, **k))[1])
    r.ib.drop(backlog=backlog, pump_raises=pump_raises)
    r.sell_by_hand("TECL")
    out = SURFACES[name](r.ad)
    assert seen == [(True, 0)]                       # reconnected once, after the backlog was drained
    assert r.ib.isConnected() and not r.ib.dead
    if name == "positions_snapshot":
        assert out["stocks"] == r.venue_pos() and "TECL" not in out["stocks"]
    if name == "account_cash":
        assert out["total_cash"] == pytest.approx(r.acct.cash)
    if name == "find_stock_order":
        assert out["status"] == "filled"             # yesterday's buy, found on the NEW session


def test_c3_positions_are_never_read_before_the_new_sessions_download_has_ended(tmp_path, monkeypatch):
    """f: IB.connect() can return with the position download timed out. The adapter then asks once
    more, bounded - and RAISES rather than answer an empty account. Before: {} (a flat account)."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop()
    r.ib.sync_positions, r.ib.positions_answer = False, False
    with pytest.raises(ib_mod.ExecutorNotSyncedError, match="not yet synced"):
        r.ad.positions_snapshot()
    with pytest.raises(ib_mod.ExecutorNotSyncedError):
        r.ad.stock_position("BIL")
    assert r.ib.positions() == []                    # what the old code returned
    r.ib.positions_answer = True
    r.ad._positions_failed = None                    # (m1: a failed download is not asked for again for 30 s)
    assert r.ad.positions_snapshot()["stocks"] == r.venue_pos()
    n = r.ib.position_requests
    r.ad.positions_snapshot()
    assert r.ib.position_requests == n               # asked once per session, not per read
    # a session whose connect-time download DID end costs no extra request
    r.ib.sync_positions = True
    r.ib.drop()
    assert r.ad.positions_snapshot()["stocks"] == r.venue_pos() and r.ib.position_requests == n


def test_c3_account_cash_never_raises_and_keeps_its_reason(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    assert r.ad.account_cash() and (r.ad.last_cash_error, r.ad.last_cash_kind) == (None, None)
    r.ib.drop(backlog=1)
    r.ib.gateway_up = False
    assert r.ad.account_cash() is None
    assert r.ad.last_cash_kind == "disconnected" and "IB gateway disconnected" in r.ad.last_cash_error
    assert mm.MirrorManager._no_cash_why(r.ad) == ("the IB gateway is not connected", True)
    r.ib.gateway_up = True
    monkeypatch.setattr(r.ib, "accountValues", lambda: [])
    monkeypatch.setattr(r.ib, "accountSummary", lambda: (_ for _ in ()).throw(TimeoutError("no summary")))
    assert r.ad.account_cash() is None and r.ad.last_cash_kind == "unreadable"
    why, unread = mm.MirrorManager._no_cash_why(r.ad)
    assert why.startswith("the account's cash could not be read: TimeoutError") and unread is True
    monkeypatch.setattr(r.ib, "accountSummary", lambda: [])
    assert r.ad.account_cash() is None and r.ad.last_cash_kind == "no_claim"
    why, unread = mm.MirrorManager._no_cash_why(r.ad)
    assert why.startswith("the account reports no cash claim (") and unread is False
    monkeypatch.undo()                                                # (the rig's own patches go with it)
    assert mm.MirrorManager._no_cash_why(object()) == ("the account reports no cash claim", False)


# ------------------------------------------------------------------ C4: keepalive
def test_c4_keepalive_reconnects_in_idle_hours_and_reuses_the_outage_accounting(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    log = OutageLog(str(tmp_path / "outages.json"))
    r.ad.outages = log
    assert r.ad.keepalive() is True and r.ib.connect_calls == 1 and log.summary()["outages"] == 0
    # 23:45: the gateway's nightly restart. Nobody but the keepalive touches the adapter.
    r.ib.drop(backlog=2)
    r.ib.gateway_up = False
    assert r.ad.keepalive() is False                 # never raises; the outage has started
    s = log.summary()
    assert s["currently_down_since"] and r.ad._disconnected_since is not None
    assert r.ad.keepalive() is False and not r.sent  # the nightly restart stays a non-event
    r.ad._disconnected_since -= ib_mod.OUTAGE_ALERT_S + 1
    assert r.ad.keepalive() is False
    assert len(r.sent) == 1 and "IB gateway DOWN" in r.sent[0]                  # the existing 30-min page
    r.ib.gateway_up = True
    assert r.ad.keepalive() is True and r.ib.isConnected()
    assert len(r.sent) == 2 and "RECONNECTED" in r.sent[1]
    s = log.summary()
    assert s["outages"] == 1 and not s["currently_down_since"]
    # ... so the morning check meets a live session and a fresh account
    r.tick("09:30:05", day=D2)
    assert not r.red() and r.m._prechecked == D2


def test_c4_keepalive_respects_the_reconnect_backoff(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    monkeypatch.setattr(r.ad, "_reconnect_backoff", 60.0)
    r.ib.drop()
    r.ib.gateway_up = False
    assert r.ad.keepalive() is False and r.ib.connect_calls == 2
    for _ in range(5):
        assert r.ad.keepalive() is False
    assert r.ib.connect_calls == 2                   # inside the backoff: no connect attempt, no block


def test_c4_the_service_loop_runs_the_keepalive_only_for_a_live_mirror_on_a_real_adapter(monkeypatch):
    from app import service

    class Ad:
        calls, boom = 0, False

        def keepalive(self):
            Ad.calls += 1
            if Ad.boom:
                raise RuntimeError("keepalive blew up")
            return True

    monkeypatch.setattr(service, "ADAPTER", Ad())
    monkeypatch.setattr(service, "BLEND", None)
    monkeypatch.setattr(service, "MIRROR", {"live": object(), "dry": object()})
    service._mirror_keepalive()
    assert Ad.calls == 1
    Ad.boom = True
    service._mirror_keepalive()                      # swallowed and logged
    assert Ad.calls == 2
    Ad.boom = False
    monkeypatch.setattr(service, "MIRROR", {"dry": object()})
    service._mirror_keepalive()                      # a paper book alone: no gateway is needed
    monkeypatch.setattr(service, "MIRROR", {"live": object()})
    monkeypatch.setattr(service, "BLEND", object())
    service._mirror_keepalive()                      # the blend cycle touches the adapter itself
    monkeypatch.setattr(service, "BLEND", None)
    monkeypatch.setattr(service, "ADAPTER", service.DryAdapter())
    service._mirror_keepalive()                      # no gateway behind a DryAdapter
    assert Ad.calls == 2
    # on the loop thread, every iteration, BETWEEN mirror ticks (after the cycle, before the feeds)
    src = inspect.getsource(service._loop)
    assert src.index("_mirror_cycle(gen, wake)") < src.index("_mirror_keepalive()") < src.index("nino34_weekly()")
    assert "_build_adapter()" in src                 # the same thread builds the adapter (and so owns its loop)


# ------------------------------------------------------------------ C5: the morning check
def test_c5_a_gateway_that_is_down_at_the_open_is_retried_ten_minutes_then_said_with_its_reason(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop(backlog=1)
    r.ib.gateway_up = False
    r.tick("09:30:05", day=D2)
    assert not r.red() and r.m._prechecked != D2
    assert r.m.next_wait() == pytest.approx(mm.MORNING_RETRY_EVERY_S)          # the loop is asked back
    for hms in ("09:31:05", "09:35:05", "09:40:04"):
        r.tick(hms, day=D2)
        assert not r.red() and r.m._prechecked != D2
    r.tick("09:40:05", day=D2)
    red = r.red()
    assert len(red) == 1 and "today's decision will be refused unless fixed: the IB gateway is not connected" in red[0]
    assert "still so 10 min" in red[0] and "cash claim" not in red[0]
    assert r.m._prechecked == D2
    r.tick("09:45:05", day=D2)
    assert len(r.red()) == 1                         # said once
    assert r.m.next_wait() > mm.MORNING_RETRY_EVERY_S


def test_c5_a_gateway_that_comes_back_inside_the_ten_minutes_is_never_an_alert(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop()
    r.ib.gateway_up = False
    r.tick("09:30:05", day=D2)
    r.tick("09:31:05", day=D2)
    assert not r.red() and r.m._prechecked != D2
    r.ib.gateway_up = True
    r.tick("09:32:05", day=D2)
    assert not r.red() and r.m._prechecked == D2 and r.m._precheck_since is None
    # ... and a real mismatch found on that retry is said at once
    r2 = Rig(tmp_path / "b", monkeypatch).invested()
    r2.ib.drop()
    r2.ib.gateway_up = False
    r2.tick("09:30:05", day=D2)
    r2.sell_by_hand("BIL")
    r2.ib.gateway_up = True
    r2.tick("09:31:05", day=D2)
    assert len(r2.red()) == 1 and "BIL: the book holds" in r2.red()[0]


def test_c5_cash_that_cannot_be_read_is_named_as_that(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    monkeypatch.setattr(r.ib, "accountValues", lambda: [])
    monkeypatch.setattr(r.ib, "accountSummary", lambda: (_ for _ in ()).throw(TimeoutError("no summary")))
    r.tick("09:30:05", day=D2)
    assert not r.red()
    r.tick("09:40:05", day=D2)
    assert len(r.red()) == 1 and "the account's cash could not be read: TimeoutError" in r.red()[0]


# ------------------------------------------------------------------ C6-C8: the decision at 15:54
@pytest.mark.parametrize("backlog, pump_raises", [(0, False), (1, False), (3, False), (3, True)])
def test_c6_the_decision_after_an_idle_drop_trades_normally(tmp_path, monkeypatch, backlog, pump_raises):
    """nothing touched the adapter since the drop (no morning tick, no keepalive): the 15:54 decision
    reconnects first and trades the whole plan. Before (backlog 3): the gates passed on the cache and
    the first quote died on the dead socket - its sleeve sat the session out."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(backlog=backlog, pump_raises=pump_raises)
    r.tick("15:55:05", day=D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded"
    assert [(s, a) for s, a, _, _ in r.ib.placed[n:]] == [("BIL", "SELL"), ("TQQQ", "BUY")]
    assert not r.m.state["history"][-1].get("dropped") and r.ib.connect_calls == 2
    sound(r)
    assert not r.red()


@pytest.mark.parametrize("backlog", [0, 1, 3])
def test_c7_the_decision_never_trades_on_a_cached_account(tmp_path, monkeypatch, backlog):
    """the account changed while the executor was not connected (BIL sold by hand) and the decision
    would SELL that BIL. Before (backlog 3): the gates passed on yesterday's positions and cash."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(backlog=backlog)
    sold = r.sell_by_hand("BIL")
    r.tick("15:55:05", day=D2)
    assert r.ib.placed[n:] == [] and f"BIL: the book holds {sold}, the venue 0" in r.m._why
    r.tick("15:58:00", day=D2)
    row = r.m.state["last_run"]
    assert row["outcome"] == "skipped" and "does not hold exactly the mirror book" in row["reason"]
    assert r.ib.placed[n:] == [] and r.acct.pos.get("BIL", 0) == 0          # nothing sent, nothing short


def test_c7_the_short_the_old_gates_let_through(tmp_path, monkeypatch):
    """the worst the cache could do, reproduced on the pre-fix code with this very sequence: SOXL and
    TECL sold by hand while the executor was not connected, a backlog of three pumps, and a decision
    that sells both. The gates passed on yesterday's positions AND cash, the first quote (BIL) died on
    the dead socket and reconnected the session, and the sells went out on the new one: the account
    ended SOXL -270, TECL -107. Now: refused as a mismatch, nothing sent."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, dict(tm.T1, HG={"TQQQ": 1.0}, KMLM={"PULS": 1.0}), session=D2)
    n = len(r.ib.placed)
    r.ib.drop(backlog=3)
    r.sell_by_hand("SOXL"), r.sell_by_hand("TECL")
    r.tick("15:55:05", day=D2)
    assert r.ib.placed[n:] == [] and all(q >= 0 for q in r.acct.pos.values())
    assert "SOXL: the book holds 270, the venue 0" in r.m._why and "TECL: the book holds 107, the venue 0" in r.m._why


def test_c7_a_backlog_that_cannot_be_drained_in_time_is_an_error_not_a_read(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    monkeypatch.setattr(ib_mod, "DRAIN_MAX_S", 0.0)
    r.ib.drop(backlog=10_000)
    r.sell_by_hand("BIL")
    with pytest.raises(ib_mod.ExecutorNotSyncedError, match="backlog still being read"):
        r.ad.positions_snapshot()
    assert r.ad.account_cash() is None and r.ad.last_cash_kind == "unreadable"
    r.tick("15:55:05", day=D2)
    assert r.m._why.startswith("the account's positions could not be read:") and r.ib.placed[n:] == []


def test_c8_gateway_down_at_the_decision_is_refused_with_the_real_reason_and_nothing_is_sent(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(backlog=1)
    r.ib.gateway_up = False
    r.tick("15:55:05", day=D2)
    assert r.m._why.startswith("the IB gateway is not connected") and not r.m.state.get("run")
    assert not [a for a in r.red() if "tick failed" in a]            # a refusal with its reason, not a crash
    r.tick("15:58:00", day=D2)
    row = r.m.state["last_run"]
    assert row["outcome"] == "skipped" and "the IB gateway is not connected" in row["reason"]
    assert any("NO TRADE" in a and "the IB gateway is not connected" in a for a in r.red())
    assert r.ib.placed[n:] == [] and r.m.book.positions() == r.venue_pos()


def test_c8_a_gateway_that_returns_inside_the_window_is_traded(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    r.ib.drop()
    r.ib.gateway_up = False
    r.tick("15:55:05", day=D2)
    assert r.m._why.startswith("the IB gateway is not connected")
    r.ib.gateway_up = True
    r.tick("15:56:00", day=D2)
    assert r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_c9_a_flatten_after_an_idle_drop_sells_what_the_account_holds_now(tmp_path, monkeypatch):
    """/kill after a drop: the flatten's positions and open-order reads are the new session's, so a
    position already sold by hand is not sold again. Before: capped against the cached list."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(backlog=3)
    r.sell_by_hand("BIL")
    r.m.halt("kill", flatten=True)
    for hms in ("11:00:00", "11:00:10", "11:00:30", "11:02:00"):
        r.tick(hms, day=D2)
    sells = [(s, a) for s, a, _, _ in r.ib.placed[n:]]
    assert sells and all(a == "SELL" for _, a in sells) and "BIL" not in [s for s, _ in sells]
    assert r.venue_pos() == {} and all(q >= 0 for q in r.acct.pos.values())


# =========================================================================== the installed ib_async
def _enc(*fields):
    msg = ("\0".join(str(f) for f in fields) + "\0").encode()
    return struct.pack(">I", len(msg)) + msg


class Gateway:
    """the least of an IB gateway the installed ib_async will connect to and sync against, on a real
    socket: the handshake, nextValidId + managedAccounts, and the END of every connect-time request."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self.pos = {"SPY": 10, "BIL": 20}
        self.cash = 5000.0
        self.conn = None
        self.sessions = 0
        self.skip_position_requests = 0             # this many reqPositions get no answer
        self.position_requests = 0
        self.silent = False                         # True: every session stops answering (and never closes)
        self.mute = False                           # True: a NEW connection's handshake is never answered
        self.time_requests = 0
        self.time_min_gap = 0.0                     # > 0: a reqCurrentTime asked sooner than this after the last
        self.time_dropped = 0                       # one answered is read and ignored (ib_insync #479, K3b's
        self._time_answered = None                  # fake_gw3 'rate49'), on every session
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conn = c
            self.sessions += 1
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _positions(self):
        return b"".join(_enc(61, 3, "DU1", 1000 + i, s, "STK", "", 0, "", "", "SMART", "USD", s, s, q, 100.0)
                        for i, (s, q) in enumerate(sorted(self.pos.items()))) + _enc(62, 1)

    def _serve(self, c):
        buf, shook = b"", False
        try:
            while True:
                d = c.recv(65536)
                if not d:
                    return
                buf += d
                if self.silent or (self.mute and not shook):
                    buf = b""                                           # read and dropped: a black hole
                    continue
                if not shook:
                    if buf.startswith(b"API\0"):
                        buf = buf[4:]
                    if len(buf) < 4 or len(buf) < 4 + struct.unpack(">I", buf[:4])[0]:
                        continue
                    buf = buf[4 + struct.unpack(">I", buf[:4])[0]:]
                    c.sendall(_enc(176, "20261112 09:00:00 EST"))
                    shook = True
                while len(buf) >= 4:
                    n = struct.unpack(">I", buf[:4])[0]
                    if len(buf) < 4 + n:
                        break
                    f, buf = buf[4:4 + n].decode().split("\0"), buf[4 + n:]
                    if f[0] == "71":                                    # startApi
                        c.sendall(_enc(15, 1, "DU1") + _enc(9, 1, 1))
                    elif f[0] == "61":                                  # reqPositions
                        self.position_requests += 1
                        if self.position_requests > self.skip_position_requests:
                            c.sendall(self._positions())
                    elif f[0] in ("5", "16"):                           # open orders
                        c.sendall(_enc(53, 1))
                    elif f[0] == "99":                                  # completed orders
                        c.sendall(_enc(102))
                    elif f[0] == "6":                                   # account updates
                        c.sendall(_enc(6, 2, "TotalCashValue", self.cash, "USD", "DU1")
                                  + _enc(6, 2, "AvailableFunds", self.cash, "USD", "DU1") + _enc(54, 1, "DU1"))
                    elif f[0] == "76":                                  # account updates multi
                        c.sendall(_enc(74, 1, f[2]))
                    elif f[0] == "7":                                   # executions
                        c.sendall(_enc(55, 1, f[2]))
                    elif f[0] == "49":                                  # reqCurrentTime
                        self.time_requests += 1
                        now = time.monotonic()
                        if (self.time_min_gap and self._time_answered is not None
                                and now - self._time_answered < self.time_min_gap):
                            self.time_dropped += 1                      # never answered
                            continue
                        self._time_answered = now
                        c.sendall(_enc(49, 1, int(time.time())))
        except OSError:
            return

    def stream(self, nbytes):
        """account updates nobody reads (the subscription keeps sending through the night)"""
        one = _enc(6, 2, "TotalCashValue", self.cash, "USD", "DU1")
        t = threading.Thread(target=lambda: self.conn.sendall(one * (nbytes // len(one) + 1)), daemon=True)
        t.start()
        t.join(5)
        assert not t.is_alive(), "the backlog did not fit the socket buffers"

    def drop(self):
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.conn.close()
        time.sleep(0.2)                              # the FIN is in the client's socket buffer

    def close(self):
        self.srv.close()


class _RealCfg:
    trading_mode = "paper"
    ib_host = "127.0.0.1"
    ib_client_id = 17
    ib_market_data_type = 1
    ib_allow_delayed = True


needs_ib_async = pytest.mark.skipif(real_ib_async is None, reason="ib_async is not installed")


@pytest.fixture
def real(monkeypatch):
    """a real IBAdapter on the installed ib_async, connected to a Gateway on a socket"""
    import sys
    monkeypatch.setitem(sys.modules, "ib_async", real_ib_async)
    monkeypatch.setattr(ib_mod.IBAdapter, "_connect", lambda self: None)
    monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 0.0)
    gw = Gateway()
    a = ib_mod.IBAdapter(_RealCfg())
    connect = a.ib.connect
    a.connects = []

    def to_gateway(host, port, clientId, timeout=15):
        a.connects.append(a.ib.isConnected())
        return connect("127.0.0.1", gw.port, clientId=clientId, timeout=a.connect_timeout)
    a.connect_timeout = 5
    monkeypatch.setattr(a.ib, "connect", to_gateway)
    yield a, gw
    try:
        a.ib.disconnect()
    except Exception:  # noqa: BLE001
        pass
    gw.close()


def _symbols(ib):
    return {p.contract.symbol: int(p.position) for p in ib.positions()}


@needs_ib_async
def test_r1_ib_async_keeps_a_dead_session_connected_and_cached_until_it_is_pumped_past_the_backlog(real):
    """a, b, c on the installed library: the assumptions StaleIB is built on"""
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    assert _symbols(a.ib) == {"SPY": 10, "BIL": 20}
    gw.stream(600_000)
    gw.drop()
    gw.pos = {"SPY": 10}                             # BIL sold by hand while nobody was connected
    assert a.ib.isConnected() and _symbols(a.ib) == {"SPY": 10, "BIL": 20}             # a: not pumped
    a.ib.sleep(0)
    assert a.ib.isConnected() and _symbols(a.ib) == {"SPY": 10, "BIL": 20}             # c: one pump is not enough
    assert [v.value for v in a.ib.accountValues() if v.tag == "TotalCashValue"] == ["5000.0"]
    for _ in range(50):
        try:
            a.ib.sleep(0)
        except ConnectionError as exc:               # d
            assert "Socket disconnect" in str(exc)
        if not a.ib.isConnected():
            break
    assert not a.ib.isConnected() and a.ib.positions() == [] and a.ib.accountValues() == []   # b
    with pytest.raises(ConnectionError, match="Not connected"):                        # e
        a.ib.accountSummary()


@needs_ib_async
@pytest.mark.parametrize("backlog", [0, 600_000])
def test_r2_the_adapter_reads_the_new_sessions_account_never_the_dead_ones(real, backlog):
    """the incident's two reads, on the installed library. Before (backlog): positions_snapshot
    answered {"SPY": 10, "BIL": 20} from the dead session and account_cash None ("Not connected")."""
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    if backlog:
        gw.stream(backlog)
    gw.drop()
    gw.pos, gw.cash = {"SPY": 10}, 6830.0
    assert a.positions_snapshot() == {"stocks": {"SPY": 10}, "other": []}
    assert len(a.connects) == 1 and gw.sessions == 2
    cash = a.account_cash()
    assert cash["total_cash"] == 6830.0 and a.last_cash_error is None and len(a.connects) == 1
    assert a.keepalive() is True and len(a.connects) == 1


@needs_ib_async
def test_r3_keepalive_on_the_installed_library_notices_the_drop_and_reconnects(real):
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    assert a.keepalive() is True and a.connects == []
    gw.stream(600_000)
    gw.drop()
    assert a.ib.isConnected()                        # stale
    assert a.keepalive() is True and len(a.connects) == 1 and gw.sessions == 2
    assert a.ib.isConnected() and _symbols(a.ib) == {"SPY": 10, "BIL": 20}


@needs_ib_async
def test_r4_a_connect_whose_position_download_timed_out_is_not_read_as_an_empty_account(real, monkeypatch):
    """f on the installed library: connect() returns with no positions and says so only in its log.
    The adapter asks again (bounded); a session that still has not delivered them raises."""
    a, gw = real
    a.connect_timeout = 0.5
    gw.skip_position_requests = 1                    # the connect-time download gets no answer
    a.ib.connect("x", 0, clientId=17)
    assert a.ib.isConnected() and a.ib.positions() == [] and a._positions_pending() is True
    assert a.positions_snapshot() == {"stocks": {"BIL": 20, "SPY": 10}, "other": []}
    assert gw.position_requests == 2 and a._positions_pending() is False
    # ... and when the second request is not answered either
    monkeypatch.setattr(ib_mod, "POSITIONS_SYNC_TIMEOUT_S", 0.5)
    gw.drop()
    gw.skip_position_requests = 99
    with pytest.raises(ib_mod.ExecutorNotSyncedError, match="not yet synced"):
        a.positions_snapshot()
    assert a.ib.isConnected() and a.ib.positions() == []


# =========================================================================== the independent review of 7a8829c0
# Two reviewers probed the fix above. What they found, each with the gate that fails on 7a8829c0:
#   D2  only a FLATTEN sell was checked against the account right before it went; a RUN sell went on the
#       plan alone (a gateway outage inside the window + a sale by hand -> SELL 315 BIL, venue -315)
#   D1  _require_live only LISTENS; a connection that died with no FIN (g) stays "connected" and cached
#       until something writes to it -> prove_live(): a bounded round trip (reqCurrentTime)
#   D3  the reconnect backoff: counted from the START of a failed attempt, and a 300 s ceiling that can
#       cost the mirror its one decision of the day
#   m1-m4  a 10 s block on every read of an unsynced session; "tick failed" for a post-check without a
#       gateway; the keepalive inflating the outage ledger; outage alerts speaking of the blend's stops
def _once(fn):
    done = []

    def run(*a, **k):
        if not done:
            done.append(1)
            fn(*a, **k)
    return run


def _after_the_plan(r, monkeypatch, fn):
    """fn() runs once, right after the run's plan is saved: the pre-trade gate has passed, no order is out"""
    real_journal, fn = r.m._journal, _once(fn)

    def hook(event, **kw):
        if event == "plan":
            fn()
        return real_journal(event, **kw)
    monkeypatch.setattr(r.m, "_journal", hook)


def _never_short(r):
    assert all(q >= 0 for q in r.acct.pos.values()), r.acct.pos


# ------------------------------------------------------------------ D2: every run SELL is checked at the order
def test_d2_gateway_down_after_the_plan_then_a_sale_by_hand_the_run_sell_is_refused_at_the_order(tmp_path, monkeypatch):
    """Reviewer D2 as probed. Before: at 15:57:30 SELL 315 BIL went out on the plan, the venue ended
    at -315 BIL and 360 TQQQ were bought with the proceeds."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)

    def outage():
        r.ib.drop(backlog=1)
        r.ib.gateway_up = False
    _after_the_plan(r, monkeypatch, outage)
    r.tick("15:55:05", day=D2)
    assert r.ib.placed[n:] == [] and r.m.state["run"]                 # not sent, not booked: asked again
    red = [a for a in r.red() if "mirror-2026-11-11-S-BIL" in a]
    assert len(red) == 1 and "is NOT sent: the account's open orders cannot be read" in red[0]
    r.sell_by_hand("BIL")
    r.ib.gateway_up = True
    r.tick("15:57:30", day=D2)
    assert [(s, a) for s, a, _, _ in r.ib.placed[n:] if a == "SELL"] == []
    _never_short(r)
    said = [a for a in r.red() if "the book holds 315 BIL, the account holds 0" in a]
    assert len(said) == 1 and "(SELL 315 BIL) is NOT sent" in said[0] and "nothing is sold for BIL" in said[0]
    row = r.m.state["last_run"]
    bil = next(o for o in row["orders"] if o["symbol"] == "BIL")
    assert bil["filled"] == 0 and bil["how"].startswith("not sent: the book holds 315 BIL, the account holds 0")
    # the buys were sized from the cash the book really has (HG's few hundred dollars), not from proceeds
    bought = sum(q * tm.PX[s] for s, a, q, _ in r.ib.placed[n:] if a == "BUY")
    assert bought <= 814.5 + 0.01 and r.m.book.cash() >= -0.01
    for hms in ("15:59:30", "16:00:40", "16:01:40"):
        r.tick(hms, day=D2)
    assert r.m.halt_state().get("halted") and any("BIL: the book holds 315, the venue 0" in a for a in r.red())


def test_d2_a_sale_by_hand_between_the_gate_and_the_sell_is_refused_without_any_outage(tmp_path, monkeypatch):
    """the same with the gateway up throughout (a blip the adapter reconnects through in one call)"""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)

    def blip():
        r.ib.drop()
        r.sell_by_hand("BIL")
    _after_the_plan(r, monkeypatch, blip)
    r.tick("15:55:05", day=D2)
    assert [x for x in r.ib.placed[n:] if x[1] == "SELL"] == []
    _never_short(r)
    assert any("the book holds 315 BIL, the account holds 0" in a for a in r.red())
    assert not [a for a in r.red() if "tick failed" in a]


def test_d2_reviewer_d1s_end_state_sells_planned_on_a_dead_sessions_cache_are_refused_at_the_order(tmp_path, monkeypatch):
    """Reviewer D1's end state: a silent death, SOXL and TECL sold by hand, the gates passing on the
    cache -> SELL 270 SOXL / SELL 107 TECL, venue -270 / -107. The liveness round trip (D1) now stops
    that at the gate; with it DISABLED here, the sells still do not go: the check at the order asks
    the venue, finds the session dead, and on the new session finds no shares."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, dict(tm.T1, HG={"TQQQ": 1.0}, KMLM={"PULS": 1.0}), session=D2)
    monkeypatch.setattr(r.ad, "prove_live", lambda timeout=0: None)
    n = len(r.ib.placed)
    r.ib.drop(silent=True)
    r.sell_by_hand("SOXL"), r.sell_by_hand("TECL")
    r.tick("15:55:05", day=D2)
    r.tick("15:56:40", day=D2)
    assert [x for x in r.ib.placed[n:] if x[1] == "SELL" and x[0] in ("SOXL", "TECL")] == []
    _never_short(r)
    assert any("the book holds 270 SOXL, the account holds 0" in a for a in r.red())
    assert any("the book holds 107 TECL, the account holds 0" in a for a in r.red())


def test_d2_an_account_that_cannot_be_read_holds_the_sell_and_it_goes_on_the_next_step(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    real_open, fails = r.ad.open_sell_qty, [TimeoutError("no openOrderEnd")]

    def open_sell_qty(sym, exclude=None):
        if fails:
            raise fails.pop()
        return real_open(sym, exclude=exclude)
    monkeypatch.setattr(r.ad, "open_sell_qty", open_sell_qty)
    r.tick("15:55:05", day=D2)                       # the run's own loop steps again inside this tick
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.state["last_run"]["session"] == D2
    assert [(s, a, q) for s, a, q, _ in r.ib.placed[n:]][0] == ("BIL", "SELL", 315)
    red = [a for a in r.red() if "is NOT sent" in a]
    assert len(red) == 1 and "open orders cannot be read (no openOrderEnd)" in red[0]
    sound(r)


def test_d2_an_account_unreadable_until_the_window_closes_sends_nothing_and_books_not_sent(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)

    def positions_snapshot():
        raise ib_mod.ExecutorNotSyncedError("no positionEnd")
    _after_the_plan(r, monkeypatch, lambda: monkeypatch.setattr(r.ad, "positions_snapshot", positions_snapshot))
    r.tick("15:55:05", day=D2)
    r.tick("15:59:30", day=D2)
    assert r.ib.placed[n:] == []
    row = r.m.state["last_run"]
    assert [(o["symbol"], o["filled"], o["how"]) for o in row["orders"]] == [("BIL", 0, "not sent: the window closed")]
    assert any("the account's positions cannot be read (no positionEnd)" in a for a in r.red())
    assert r.m.book.positions()["BIL"] == 315 and not [a for a in r.red() if "tick failed" in a]


def test_d2_a_sell_already_resting_at_the_venue_counts_against_what_the_account_holds(tmp_path, monkeypatch):
    """315 BIL in the account, a SELL 100 BIL placed by hand and still working: selling 315 more would
    leave -100 when both fill. Nothing is cut: the symbol is not sold at all."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    hand = tia.FakeTrade(tia.FakeStock("BIL", "SMART", "USD"), tia.FakeMarketOrder("SELL", 100))
    hand.order.orderId, hand.order.permId, hand.order.orderRef = 900, 9900, ""
    hand.orderStatus.status, hand.orderStatus.filled = "Submitted", 0
    r.acct.orders.append(hand)
    r.tick("15:55:05", day=D2)
    assert [x for x in r.ib.placed[n:] if x[1] == "SELL"] == []
    said = [a for a in r.red() if "the book holds 315 BIL, the account holds 315 and SELL orders for 100" in a]
    assert len(said) == 1


def test_d2_a_normal_rotation_is_unchanged_but_for_one_venue_read_per_sell(tmp_path, monkeypatch):
    """the same orders, in the same order, the book and the account sound; the only additions are one
    reqAllOpenOrders per sell (before it is placed), one reqCurrentTime per account gate and (K3a N2) one
    before the buys' cash is read - free on a session proven < PROVE_FRESH_S before; this double has no
    connection object, so every proof is a round trip here"""
    r = Rig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, dict(tm.T1, HG={"TQQQ": 1.0}, KMLM={"PULS": 1.0},
                                                 SLEEVE={"TECL": 1.0}), session=D2)
    n = len(r.ib.placed)
    order: list = []
    real_place, real_open, real_time = r.ib.placeOrder, r.ib.reqAllOpenOrders, r.ib.reqCurrentTime
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (order.append(f"{o.action} {c.symbol}"), real_place(c, o))[1])
    monkeypatch.setattr(r.ib, "reqAllOpenOrders", lambda: (order.append("open?"), real_open())[1])
    monkeypatch.setattr(r.ib, "reqCurrentTime", lambda: (order.append("alive?"), real_time())[1])
    del r.ib.requests[:]
    r.tick("15:55:05", day=D2)
    assert [(s, a, q) for s, a, q, _ in r.ib.placed[n:]] == [
        ("BIL", "SELL", 315), ("BOXX", "SELL", 237), ("SOXL", "SELL", 270),
        ("PULS", "BUY", 438), ("TECL", "BUY", 161), ("TQQQ", "BUY", 360)]
    for sym in ("BIL", "BOXX", "SOXL"):              # each sell: the venue is asked, then it is placed
        i = order.index(f"SELL {sym}")
        assert order[i - 1] == "open?"
    assert r.ib.requests.count("reqCurrentTime") == 2
    gate, cash = [i for i, x in enumerate(order) if x == "alive?"]   # the decision's account gate; the buys' cash
    assert gate < order.index("SELL BIL") and order.index("SELL SOXL") < cash < order.index("BUY PULS")
    assert not r.red() and r.m.state["last_run"]["outcome"] == "traded"
    sound(r)


def test_d2_a_paper_book_and_a_buy_are_not_checked(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    monkeypatch.setattr(r.ad, "open_sell_qty", lambda *a, **k: 1 / 0)
    assert r.m._sell_check(r.ad, {"id": "b", "side": mm.mc.BUY, "symbol": "BIL", "qty": 9}, {}) is True
    monkeypatch.setattr(r.m, "_dry", object())
    assert r.m._sell_check(r.ad, {"id": "s", "side": mm.mc.SELL, "symbol": "BIL", "qty": 9}, {}) is True


# ------------------------------------------------------------------ D1: a liveness round trip
def test_d1_a_connection_that_died_with_no_fin_is_found_by_the_keepalive(tmp_path, monkeypatch):
    """Before: keepalive() answered True for ever (a pump hears nothing) and connect was never tried."""
    r = Rig(tmp_path, monkeypatch).invested()
    del r.ib.requests[:]
    assert r.ad.keepalive() is True and r.ib.requests == ["reqCurrentTime"] and r.ib.connect_calls == 1
    r.ib.drop(silent=True)
    r.ib.sleep(0)
    assert r.ib.isConnected() and r.ib.dead          # the premise: pumping learns nothing
    assert r.ad.keepalive() is True and r.ib.connect_calls == 2 and not r.ib.dead
    r.ib.drop(blackhole=True)                        # ... nor does the request get an RST: it times out
    r.ib.gateway_up = False
    assert r.ad.keepalive() is False and not r.ib.isConnected() and r.ad._disconnected_since is not None
    with pytest.raises(ib_mod.ExecutorConnectionError):
        r.ad.positions_snapshot()
    r.ib.gateway_up = True
    assert r.ad.keepalive() is True and r.ad.positions_snapshot()["stocks"] == r.venue_pos()


def test_d1_prove_live_bounds_the_request_and_restores_the_timeout(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    seen = []
    monkeypatch.setattr(r.ib, "reqCurrentTime", lambda: seen.append(r.ib.RequestTimeout))
    r.ad.prove_live()
    r.ad.prove_live(timeout=2.5)
    assert seen == [ib_mod.PROVE_LIVE_TIMEOUT_S, 2.5] == [5.0, 2.5] and r.ib.RequestTimeout == 0
    assert r.ib.connect_calls == 1
    assert ib_mod.DryAdapter().prove_live() is None  # a paper adapter has no session to prove


@pytest.mark.parametrize("blackhole", [False, True])
def test_d1_the_morning_check_and_the_decision_do_not_pass_on_a_silently_dead_sessions_cache(tmp_path, monkeypatch, blackhole):
    """Reviewer D1 (explore3 h1). Before: no red in the morning, then SELL 270 SOXL / 107 TECL at
    15:55 on positions the account no longer held (venue -270 / -107)."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, dict(tm.T1, HG={"TQQQ": 1.0}, KMLM={"PULS": 1.0}), session=D2)
    n = len(r.ib.placed)
    r.ib.drop(silent=True, blackhole=blackhole)
    r.sell_by_hand("SOXL"), r.sell_by_hand("TECL")
    r.tick("09:30:05", day=D2)
    assert r.ib.connect_calls == 2 and not r.ib.dead
    red = r.red()
    assert len(red) == 1 and "SOXL: the book holds 270, the venue 0" in red[0]
    r.tick("15:55:05", day=D2)
    r.tick("15:58:01", day=D2)
    assert r.ib.placed[n:] == [] and r.m.state["last_run"]["outcome"] == "skipped"
    _never_short(r)


def test_d1_a_black_hole_with_no_gateway_behind_it_refuses_the_gates_as_not_connected(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(blackhole=True)
    r.ib.gateway_up = False
    r.sell_by_hand("BIL")
    r.tick("09:30:05", day=D2)
    assert not r.red() and r.m._prechecked != D2 and r.m._precheck_since[0] == D2      # retried, not passed
    r.tick("15:55:05", day=D2)
    assert r.m._why.startswith("the IB gateway is not connected") and r.ib.placed[n:] == []
    assert not [a for a in r.red() if "tick failed" in a]


def test_d1_the_account_gate_proves_the_session_once_per_evaluation_before_it_reads(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    calls: list = []
    real_prove, real_snap = r.ad.prove_live, r.ad.positions_snapshot
    monkeypatch.setattr(r.ad, "prove_live", lambda *a, **k: (calls.append("prove"), real_prove(*a, **k))[1])
    monkeypatch.setattr(r.ad, "positions_snapshot", lambda: (calls.append("positions"), real_snap())[1])
    assert r.m._pretrade_account(r.ad) is None
    assert calls == ["prove", "positions"]
    del calls[:]
    for surface in (lambda: r.ad.stock_position("BIL"), r.ad.account_cash, lambda: r.ad.spot_ex("BIL"),
                    lambda: r.ad.find_stock_order("nope"), lambda: r.ad.open_sell_qty("BIL")):
        surface()
    assert "prove" not in calls                      # not on every surface: their cost is what it was


def test_d1_a_flatten_round_is_built_from_a_proven_session_not_from_the_cache(tmp_path, monkeypatch):
    """Reviewer D1 (explore3 h2). Before: the round was built on the dead session's list, so it held a
    SELL 270 SOXL (only the cap at the order refused it). Now the round itself has no such order."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    r.ib.drop(silent=True)
    r.sell_by_hand("SOXL")
    rounds = []
    real_journal = r.m._journal
    monkeypatch.setattr(r.m, "_journal", lambda event, **kw: (
        rounds.append([o["symbol"] for o in kw["orders"]]) if event == "flatten" else None, real_journal(event, **kw))[1])
    r.m.halt("kill", flatten=True)
    for hms in ("11:00:00", "11:00:10", "11:00:30", "11:02:00"):
        r.tick(hms, day=D2)
    assert rounds and all("SOXL" not in syms for syms in rounds)
    assert sorted(s for s, a, _, _ in r.ib.placed[n:]) == ["BIL", "BOXX", "PULS", "TECL"]
    assert any("the book holds 270 SOXL, the account 0" in a for a in r.red())
    assert not [a for a in r.red() if "is NOT sent" in a]
    _never_short(r)


def test_d1_spot_ex_bounds_its_contract_lookup(tmp_path, monkeypatch):
    """Before: qualifyContracts ran with ib_async's default RequestTimeout 0 - for ever on a session
    that stopped answering, on the loop thread."""
    r = Rig(tmp_path, monkeypatch).invested()
    seen = []
    real = r.ib.qualifyContracts
    monkeypatch.setattr(r.ib, "qualifyContracts", lambda *c: (seen.append(r.ib.RequestTimeout), real(*c))[1])
    assert r.ad.spot_ex("BIL")[0] == tm.PX["BIL"]
    assert seen == [ib_mod.QUALIFY_TIMEOUT_S] and r.ib.RequestTimeout == 0
    r.ib.drop(blackhole=True)
    with pytest.raises(ib_mod.ExecutorConnectionError, match="did not answer the contract lookup for BIL"):
        r.ad.spot_ex("BIL")
    assert r.ib.RequestTimeout == 0


@needs_ib_async
def test_d1_r5_a_healthy_session_is_proven_with_one_message_and_nothing_else_changes(real):
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    sent = a.ib.client.connectionStats().numMsgSent
    t0 = time.monotonic()
    a.prove_live()
    assert time.monotonic() - t0 < 1.0
    assert a.ib.client.connectionStats().numMsgSent == sent + 1 and gw.time_requests == 1
    assert a.connects == [] and gw.sessions == 1 and a.ib.RequestTimeout == 0
    # the loop's keepalive right after it: this connection answered < PROVE_FRESH_S ago - no message (K3b)
    assert a.keepalive() is True and gw.time_requests == 1 and a.connects == []
    a._proven = (a._proven[0] - ib_mod.PROVE_FRESH_S, a._proven[1])      # ... and once that is older: one
    assert a.keepalive() is True and gw.time_requests == 2 and a.connects == []
    assert a.positions_snapshot() == {"stocks": {"BIL": 20, "SPY": 10}, "other": []}
    assert a.ib.client.connectionStats().numMsgSent == sent + 2      # the read itself still sends nothing


@needs_ib_async
def test_d1_r6_a_silent_black_hole_is_found_within_the_timeout_and_reconnected(real, monkeypatch):
    """the installed ib_async on a socket whose peer handshook, synced, and then stopped answering
    WITHOUT closing. Before: keepalive True, positions and cash from the cache, nothing ever sent."""
    a, gw = real
    monkeypatch.setattr(ib_mod, "PROVE_LIVE_TIMEOUT_S", 0.5)
    a.connect_timeout = 1
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    assert a.positions_snapshot()["stocks"] == {"BIL": 20, "SPY": 10}
    gw.silent = True
    gw.pos, gw.cash = {"SPY": 10}, 6830.0            # BIL sold by hand; the silent peer says nothing
    assert a.ib.isConnected() and _symbols(a.ib) == {"SPY": 10, "BIL": 20}      # the premise
    old = gw.conn
    t0 = time.monotonic()
    with pytest.raises(ib_mod.ExecutorConnectionError):
        a.prove_live(timeout=0.5)                    # the gateway answers nobody: the reconnect fails too
    took = time.monotonic() - t0
    assert 0.5 <= took < 0.5 + a.connect_timeout + 1.5 and not a.ib.isConnected()
    assert a.ib.positions() == [] and a.ib.RequestTimeout == 0
    with pytest.raises(ib_mod.ExecutorConnectionError):
        a.positions_snapshot()                       # never the dead session's list
    assert a.account_cash() is None and a.last_cash_kind == "disconnected"
    assert a.keepalive() is False
    gw.silent = False                                # the gateway answers again (a new session)
    assert a.keepalive() is True and gw.conn is not old
    assert a.positions_snapshot() == {"stocks": {"SPY": 10}, "other": []}
    assert a.account_cash()["total_cash"] == 6830.0
    old.close()


@needs_ib_async
def test_d1_r7_a_black_hole_on_one_connection_only_costs_one_reconnect(real):
    """the old connection is a black hole (a dropped NAT mapping); the gateway itself is fine"""
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    gw.silent = True
    threading.Timer(0.6, lambda: setattr(gw, "silent", False)).start()
    gw.pos = {"SPY": 10}
    t0 = time.monotonic()
    a.prove_live(timeout=1.0)
    assert 1.0 <= time.monotonic() - t0 < 4.0 and len(a.connects) == 1 and gw.sessions == 2
    assert a.positions_snapshot() == {"stocks": {"SPY": 10}, "other": []}


@needs_ib_async
def test_d1_r8_spot_ex_does_not_wedge_on_a_black_hole(real, monkeypatch):
    a, gw = real
    monkeypatch.setattr(ib_mod, "QUALIFY_TIMEOUT_S", 0.5)
    a.ib.connect("x", 0, clientId=17)
    gw.silent = True
    t0 = time.monotonic()
    with pytest.raises(ib_mod.ExecutorConnectionError, match="did not answer the contract lookup for SPY"):
        a.spot_ex("SPY")
    assert time.monotonic() - t0 < 3.0 and a.ib.RequestTimeout == 0


# ------------------------------------------------------------------ D3: the reconnect backoff
def _mirror_only_service(monkeypatch, r):
    from app import service
    monkeypatch.setattr(service, "ADAPTER", r.ad)
    monkeypatch.setattr(service, "BLEND", None)
    monkeypatch.setattr(service, "MIRROR", {"live": r.m})
    return service


def test_d3_the_backoff_counts_from_the_end_of_a_failed_attempt(tmp_path, monkeypatch):
    """Before: from its start - a connect that hung for its 15 s timeout had used up the whole first
    step, and the next call tried (and blocked) again at once."""
    r = Rig(tmp_path, monkeypatch).invested()
    mono = [1000.0]
    monkeypatch.setattr(ib_mod.time, "monotonic", lambda: mono[0])
    r.ad._reconnect_backoff = 15.0
    r.ib.drop()
    r.ib.gateway_up = False

    def hung_connect(host, port, clientId, timeout=15):
        r.ib.connect_calls += 1
        mono[0] += 15.0
        raise TimeoutError()
    monkeypatch.setattr(r.ib, "connect", hung_connect)
    assert r.ad.keepalive() is False and r.ib.connect_calls == 2
    assert r.ad._next_reconnect_ts == pytest.approx(1000.0 + 15.0 + 15.0)
    assert r.ad.keepalive() is False and r.ib.connect_calls == 2     # inside the backoff: no second block


def test_d3_the_ceiling_is_the_blends_300s_unless_only_the_mirror_trades(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch).invested()
    assert r.ad.reconnect_backoff_max_s == ib_mod.RECONNECT_BACKOFF_MAX_S == 300.0 and r.ad.mirror_only is False
    service = _mirror_only_service(monkeypatch, r)
    monkeypatch.setattr(service, "BLEND", object())
    service._mirror_keepalive()
    monkeypatch.setattr(service, "BLEND", None)
    monkeypatch.setattr(service, "MIRROR", {"dry": r.m})
    service._mirror_keepalive()
    monkeypatch.setattr(service, "MIRROR", {"live": r.m})
    monkeypatch.setattr(service.settings, "ladder_enabled", True)
    service._mirror_keepalive()                      # the options ladder shares the adapter: its backoff stays
    assert r.ad.reconnect_backoff_max_s == 300.0 and r.ad.mirror_only is False      # the blend's, untouched
    monkeypatch.setattr(service.settings, "ladder_enabled", False)
    service._mirror_keepalive()
    assert r.ad.reconnect_backoff_max_s == service.MIRROR_RECONNECT_BACKOFF_MAX_S == 30.0 and r.ad.mirror_only is True


@pytest.mark.parametrize("mirror_only", [True, False])
def test_d3_a_gateway_back_at_15_53_30_after_a_long_outage_is_traded_at_15_54(tmp_path, monkeypatch, mirror_only):
    """Reviewer D3 (explore2 b1): the gateway is down from 15:10; the loop's keepalive fails every 300 s
    and saturates the backoff; the last failed attempt is at 15:53:00; the gateway is back at 15:53:30.
    Before: the next attempt was not allowed before 15:58:00 - NO TRADE. With the blend's ceiling
    (mirror_only False) that is still so: the blend's behaviour is not changed."""
    r = Rig(tmp_path, monkeypatch).invested()
    service = _mirror_only_service(monkeypatch, r)
    if not mirror_only:
        monkeypatch.setattr(service, "BLEND", object())              # the keepalive is the blend's cycle then
    n = len(r.ib.placed)
    mono = [1000.0]
    monkeypatch.setattr(ib_mod.time, "monotonic", lambda: mono[0])
    monkeypatch.setattr(ib_mod, "RECONNECT_BACKOFF_S", 15.0)
    r.ad._reconnect_backoff = 15.0
    r.ib.drop()
    r.ib.gateway_up = False
    for _ in range(9):                               # 15:13 .. 15:53, every 300 s (the loop's cadence)
        service._mirror_keepalive() if mirror_only else r.ad.keepalive()
        mono[0] += 300.0
    mono[0] -= 300.0                                 # 15:53:00: the last failed attempt was just now
    assert r.ib.connect_calls == 10
    assert r.ad._next_reconnect_ts - mono[0] == (30.0 if mirror_only else 300.0)
    r.ib.gateway_up = True                           # 15:53:30
    mono[0] += 86.0
    r.tick("15:54:26", day=D2)
    if mirror_only:
        assert r.m.state["last_run"]["session"] == D2 and r.m.state["last_run"]["outcome"] == "traded"
        assert [(s, a) for s, a, _, _ in r.ib.placed[n:]] == [("BIL", "SELL"), ("TQQQ", "BUY")]
        sound(r)
    else:
        assert r.m._why.startswith("the IB gateway is not connected") and r.ib.placed[n:] == []


# ------------------------------------------------------------------ the minors
def test_m1_a_position_download_that_timed_out_is_not_asked_for_again_for_30s(tmp_path, monkeypatch):
    """Before: every read of a session that never delivers positionEnd blocked a fresh 10 s."""
    r = Rig(tmp_path, monkeypatch).invested()
    mono = [5000.0]
    monkeypatch.setattr(ib_mod.time, "monotonic", lambda: mono[0])
    r.ib.drop()
    r.ib.sync_positions, r.ib.positions_answer = False, False
    for _ in range(4):
        with pytest.raises(ib_mod.ExecutorNotSyncedError, match="not yet synced"):
            r.ad.positions_snapshot()
        mono[0] += 5.0
    with pytest.raises(ib_mod.ExecutorNotSyncedError):
        r.ad.stock_position("BIL")
    assert r.ib.position_requests == 1               # one 10 s wait, not five
    mono[0] += 11.0                                  # 31 s after the failure: asked again
    with pytest.raises(ib_mod.ExecutorNotSyncedError):
        r.ad.positions_snapshot()
    assert r.ib.position_requests == 2
    r.ib.sync_positions = True                       # a NEW session owes nothing to the old one's failure
    r.ib.drop()
    assert r.ad.positions_snapshot()["stocks"] == r.venue_pos() and r.ad._positions_failed is None
    # ... and a download that ends late (positionEnd after the timeout) is read at once
    r.ib.sync_positions = False
    r.ib.drop()
    with pytest.raises(ib_mod.ExecutorNotSyncedError):
        r.ad.positions_snapshot()
    r.ib.wrapper._futures.pop("positions")
    assert r.ad.positions_snapshot()["stocks"] == r.venue_pos()


def test_m2_a_post_check_without_a_gateway_is_a_named_reason_retried_with_no_strike(tmp_path, monkeypatch):
    """Reviewer (explore1 t4). Before: red "tick failed: ExecutorConnectionError(...)" on every tick."""
    r = Rig(tmp_path, monkeypatch).invested()
    real_finish = r.m._finish

    def finish(ad):
        real_finish(ad)
        r.ib.drop()
        r.ib.gateway_up = False
    monkeypatch.setattr(r.m, "_finish", finish)
    r.tick("15:55:05", day=D2)
    assert r.m.state["last_run"]["session"] == D2
    for hms in ("15:56:40", "15:57:40", "16:10:00"):
        r.tick(hms, day=D2)
    assert not r.red() and r.m.last_error is None
    assert not r.m.state.get("check")                # nothing recorded: no strike, not done
    said = [a for a in r.alerts if "the post-trade check" in a]
    assert len(said) == 1 and said[0].startswith("⚠️") and "the IB gateway is not connected" in said[0]
    r.ib.gateway_up = True
    r.tick("16:11:00", day=D2)
    assert r.m.state["check"] == {**r.m.state["check"], "session": D2, "strikes": 0, "done": True}
    assert not r.m.halt_state().get("halted")
    sound(r)


def test_m3_the_keepalive_does_not_count_blocked_calls(tmp_path, monkeypatch):
    """Before: one blocked call per loop iteration for the whole outage."""
    r = Rig(tmp_path, monkeypatch).invested()
    log = OutageLog(str(tmp_path / "outages.json"))
    r.ad.outages = log
    monkeypatch.setattr(r.ad, "_reconnect_backoff", 60.0)
    r.ib.drop()
    r.ib.gateway_up = False
    for _ in range(25):
        assert r.ad.keepalive() is False
    assert log.open and log.open.get("blocked_calls", 0) == 0
    for _ in range(3):                               # a surface something was waiting on still counts
        with pytest.raises(ib_mod.ExecutorConnectionError):
            r.ad.positions_snapshot()
    assert log.open["blocked_calls"] == 3 and r.ad._in_keepalive is False


@pytest.mark.parametrize("mirror_only", [False, True])
def test_m4_the_outage_alerts_say_what_is_true_for_the_book_that_trades(tmp_path, monkeypatch, mirror_only):
    r = Rig(tmp_path, monkeypatch).invested()
    r.ad.mirror_only = mirror_only
    r.ib.drop()
    r.ib.gateway_up = False
    assert r.ad.keepalive() is False
    r.ad._disconnected_since -= ib_mod.OUTAGE_ALERT_S + 1
    assert r.ad.keepalive() is False
    r.ib.gateway_up = True
    assert r.ad.keepalive() is True
    down, back = r.sent
    assert "IB gateway DOWN for over 30 min" in down and "RECONNECTED after 30 min" in back
    if mirror_only:
        assert "GTC" not in down + back and "ratchet" not in down
        assert "NO resting stops" in down and "will NOT trade" in down and "no resting stops" in back
    else:                                            # the blend's wording, to the letter
        assert down.endswith("— executor is failing closed (no entries/exits/stop ratchets); GTC stops still rest "
                             "at the venue. Auto-reconnect keeps retrying with backoff; check the gateway "
                             "container if this persists")
        assert back.endswith("— executor resumed (cycles were failing closed meanwhile; GTC stops rested at the "
                             "venue throughout)")


def test_d2_a_session_that_goes_silent_inside_the_run_is_reconnected_and_the_sells_go(tmp_path, monkeypatch):
    """after the gate, before the sells: the session stops answering (no FIN, no RST). The check's
    venue read times out - nothing is sent on that - and the liveness round trip that follows a failed
    read reconnects, so the run's next step sells on a session that answers."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    _after_the_plan(r, monkeypatch, lambda: r.ib.drop(blackhole=True))
    r.tick("15:55:05", day=D2)
    assert r.ib.connect_calls == 2 and r.m.state["last_run"]["outcome"] == "traded"
    assert [(s, a, q) for s, a, q, _ in r.ib.placed[n:]] == [("BIL", "SELL", 315), ("TQQQ", "BUY", 360)]
    red = r.red()
    assert len(red) == 1 and "is NOT sent: the account's open orders cannot be read" in red[0]
    sound(r)


# =========================================================================== the independent review of d51ad80a
# Two reviewers (K3a: the run-sell check; K3b: the liveness round trip and the reconnect backoff) found nothing
# blocking. What they did find, each with the gate that fails on d51ad80a:
#   K3b     the account gate and the loop's keepalive prove the session ms apart: on a gateway that ignores a
#           reqCurrentTime asked < ~1 s after the last one (ib_insync #479, TWS 10.16.1f) every such pair cost a
#           5 s stall and the disconnect of a healthy session -> PROVE_FRESH_S
#   K3a M2  open_sell_qty never dropped a session whose reqAllOpenOrders timed out: every sell waited 20 s again
#   K3a M4  open_sell_qty counted the session's cache: a hand sell cancelled since an earlier read still counted
#   K3a M3  the post-trade check read the positions of a session that had died silently
#   K3a N2  the buys' cash read did too (pre-existing): $20,000 withdrawn by hand -> the account at -$19,369
#   K3a M1  a sell held up only by orders resting at the venue was called a disagreement, to repair with adjust
#   K3a N1  a halt that landed during the check's round trips did not stop the sell
ROT = dict(tm.T1, HG={"TQQQ": 1.0}, KMLM={"PULS": 1.0}, SLEEVE={"TECL": 1.0})    # 3 sells, 3 buys; TECL crosses
AFTER = ("15:56:40", "15:57:40", "15:58:40", "15:59:30", "16:00:40", "16:01:40", "16:03:00")


def _hand_order(r, sym, qty, filled=0, status="Submitted"):
    """a SELL placed by hand (another client): it rests at the venue under no orderRef"""
    t = tia.FakeTrade(tia.FakeStock(sym, "SMART", "USD"), tia.FakeMarketOrder("SELL", qty))
    t.order.orderId, t.order.orderRef, t.order.permId = 0, "", 70000 + len(r.acct.orders)
    t.orderStatus.status, t.orderStatus.filled = status, filled
    r.acct.orders.append(t)
    if filled:
        r.acct.pos[sym] -= filled
        r.acct.cash += filled * tm.PX[sym]
    return t


class ProvenIB(StaleIB):
    """StaleIB with what prove_live's freshness keys on, as ib_async 2.1.0 has it (client.conn.transport: a new
    object per TCP connection, None once it is closed - IBAdapter._connection), and a gateway that ignores a
    reqCurrentTime asked less than 1 s after the last one it answered (ib_insync #479; K3b's fake_gw3 'rate49'):
    only the caller's own timeout ends such a request. Time is the test's (ib_mod.time.monotonic)."""

    def __init__(self, acct, prices):
        super().__init__(acct, prices)
        self.client = types.SimpleNamespace(connectionStats=self._stats, conn=types.SimpleNamespace(transport=None))
        self.answered_at, self.time_dropped = None, 0

    def _closed(self):
        super()._closed()
        self.client.conn.transport = None

    def connect(self, host, port, clientId, timeout=15):
        super().connect(host, port, clientId, timeout)
        self.client.conn.transport = object()        # a new TCP connection

    def reqCurrentTime(self):
        self._req("reqCurrentTime")
        now = ib_mod.time.monotonic()
        if self.answered_at is not None and 0.0 <= now - self.answered_at < 1.0:
            self.time_dropped += 1
            raise TimeoutError()
        self.answered_at = now
        return tia.FakeIB.reqCurrentTime(self)


class ProvenRig(Rig):
    ib_cls = ProvenIB


def test_k3b_the_gate_and_the_loops_keepalive_prove_the_session_once_not_twice(tmp_path, monkeypatch):
    """K3b (S4 and its spacing probe), deterministic: the real mirror ticks, each followed by the service loop's
    keepalive as service._loop runs them, on a gateway that ignores a reqCurrentTime asked < 1 s after the last
    one it answered; the test's clock stands still inside an iteration (the calls are ms apart). Before: in every
    iteration the second proof went unanswered - a 5 s stall, then the disconnect of a healthy session and a
    full resync (K3b measured 4 reconnects in 4 pairs; a flatten tick proves three times)."""
    r = ProvenRig(tmp_path, monkeypatch).invested()
    service = _mirror_only_service(monkeypatch, r)
    mono = [ib_mod.time.monotonic() + 3600.0]
    monkeypatch.setattr(ib_mod.time, "monotonic", lambda: mono[0])
    connects = r.ib.connect_calls

    def iteration(hms, day=D2):
        mono[0] += 30.0                              # the loop parked since the last iteration
        n = r.ib.requests.count("reqCurrentTime")
        r.tick(hms, day=day)
        service._mirror_keepalive()
        return r.ib.requests.count("reqCurrentTime") - n

    assert iteration("09:30:05") == 1 and r.m._prechecked == D2 and not r.red()      # the morning check
    r.brain.make = lambda now: payload(now, tm.T1, session=D2)                        # nothing to trade
    assert iteration("15:55:05") == 1 and r.m.state["last_run"]["outcome"] == "held"
    assert iteration("15:56:40") == 1 and r.m.state["check"]["done"]                 # the post-trade check
    r.m.halt("kill", flatten=True)
    assert iteration("10:00:00", day="2026-11-12") == 1                               # a flatten tick
    assert r.venue_pos() == {} and r.m.halt_state().get("flatten_done")
    assert r.ib.time_dropped == 0 and r.ib.connect_calls == connects                  # no stall, no reconnect
    # a session proven 3 s ago is proven again; one proven 1.9 s ago is not
    mono[0] += 3.0
    n = r.ib.requests.count("reqCurrentTime")
    assert r.ad.keepalive() is True and r.ib.requests.count("reqCurrentTime") == n + 1
    mono[0] += 1.9
    assert r.ad.keepalive() is True and r.ib.requests.count("reqCurrentTime") == n + 1
    # a reconnect invalidates the record: the new session (1.9 s after that proof) gets its own round trip
    r.ib.drop()                                      # the gateway closed the session (a FIN)
    assert r.ad.keepalive() is True and r.ib.connect_calls == connects + 1
    assert r.ib.requests.count("reqCurrentTime") == n + 2 and r.ib.time_dropped == 0


@needs_ib_async
def test_k3b_r9_gate_then_keepalive_on_a_gateway_that_ignores_a_second_request_within_1s(real):
    """the same on the installed ib_async, against a socket gateway with K3b's 'rate49' (s4_pairing.py). Before:
    each gate-then-keepalive pair = an unanswered request, a 5 s stall, a disconnect and a full resync."""
    a, gw = real
    gw.time_min_gap = 1.0
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    took = []
    for i in range(2):
        if i:
            time.sleep(2.1)                          # the loop parks between iterations (2 s during a run)
        t0 = time.monotonic()
        a.prove_live()                               # the account gate (_pretrade_account -> _prove)
        a.positions_snapshot(), a.account_cash()     # what the gate reads: the session's caches
        assert a.keepalive() is True                 # service._mirror_keepalive, right after the tick
        took.append(time.monotonic() - t0)
    assert gw.time_dropped == 0 and a.connects == [] and gw.sessions == 1 and max(took) < 1.0
    assert gw.time_requests == 2                     # one per iteration: the second's gate proved it again
    # a reconnect invalidates the record: the new session gets its own round trip at once (the gateway's
    # 1 s rule is off here - its last answer was the old session's, a moment ago)
    gw.time_min_gap = 0.0
    old = a.ib.client.conn.transport
    gw.drop()
    a.prove_live()
    assert len(a.connects) == 1 and gw.sessions == 2 and a.ib.client.conn.transport is not old
    assert gw.time_requests == 3 and a._proven[1] is a.ib.client.conn.transport


class WedgedIB(StaleIB):
    """K3a's probe 4d: the CURRENT session answers the liveness round trip but never openOrderEnd - every
    reqAllOpenOrders times out after its RequestTimeout, charged to the rig's clock; a NEW session answers"""
    clock = None

    def __init__(self, acct, prices):
        super().__init__(acct, prices)
        self.wedged, self.open_timeouts = False, 0

    def reqAllOpenOrders(self):
        if self.wedged and self.connected and not self.dead:
            self.open_timeouts += 1
            if self.clock is not None:
                self.clock.now += timedelta(seconds=float(self.RequestTimeout or 0))
            raise TimeoutError()
        return super().reqAllOpenOrders()

    def connect(self, host, port, clientId, timeout=15):
        super().connect(host, port, clientId, timeout)
        self.wedged = False


class WedgedRig(Rig):
    ib_cls = WedgedIB


def test_k3a_open_orders_that_time_out_drop_the_session_and_the_sells_go_inside_the_window(tmp_path, monkeypatch):
    """K3a MINOR-2 (probe 4d). Before: open_sell_qty let the raw TimeoutError out and kept the session; the check's
    liveness pass found it answering, so every step asked it again - 20 s per sell - until the window closed:
    BIL, BOXX and SOXL 'not sent: the window closed', no buy at all. The old path recovered because placement
    dropped such a session (_all_trades); a timeout in open_sell_qty now does the same."""
    r = WedgedRig(tmp_path, monkeypatch).invested()
    r.ib.clock = r.clock
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    n = len(r.ib.placed)
    stamps: list = []
    real = r.ib.placeOrder
    monkeypatch.setattr(r.ib, "placeOrder", lambda c, o: (stamps.append(r.clock.now), real(c, o))[1])
    r.ib.wedged = True
    r.tick("15:55:05", day=D2)
    for hms in AFTER[:3]:
        r.tick(hms, day=D2)
    row = r.m.state["last_run"]
    assert row["session"] == D2 and row["outcome"] == "traded"
    assert sorted((s, a, q) for s, a, q, _ in r.ib.placed[n:]) == [
        ("BIL", "SELL", 315), ("BOXX", "SELL", 237), ("PULS", "BUY", 438), ("SOXL", "SELL", 270),
        ("TECL", "BUY", 161), ("TQQQ", "BUY", 360)]
    assert r.ib.open_timeouts == 1 and r.ib.connect_calls == 2       # one 20 s wait, then a new session
    assert max(stamps) < tm.at("15:59:00", D2)                       # inside the window (the cancel instant)
    red = [a for a in r.red() if "is NOT sent" in a]
    assert len(red) == 1 and "the account's open orders cannot be read (reqAllOpenOrders timed out" in red[0]
    sound(r)


class CachingIB(StaleIB):
    """what ib_async 2.1.0 does with ANOTHER client's open orders (wrapper.py:685-712, 728-730; ib.py:942-948):
    each one a reqAllOpenOrders answer lists is stored in the session's trade list - a copy, refreshed only while
    the venue still lists it; a later cancel or fill is never sent to this client. This client's own orders are
    the venue's objects themselves (kept in sync), as in VenueIB. (K3a's FaithfulIB.)"""

    def _closed(self):
        super()._closed()
        self._snaps = {}

    def reqAllOpenOrders(self):
        self._req("reqAllOpenOrders")
        snaps = self.__dict__.setdefault("_snaps", {})
        out = []
        for t in self.acct.orders:
            if t.orderStatus.status not in ("Submitted", "PreSubmitted"):
                continue
            if any(t is x for x in self._trades) or t.order.orderRef:
                out.append(t)                        # this client's own: the same object
                continue
            s = snaps.get(t.order.permId)
            if s is None:
                s = snaps[t.order.permId] = tia.FakeTrade(t.contract, copy.copy(t.order))
                self._trades.append(s)
            s.orderStatus.status, s.orderStatus.filled = t.orderStatus.status, t.orderStatus.filled
            out.append(s)
        return out


class CachingRig(Rig):
    ib_cls = CachingIB


def test_k3a_a_hand_sell_cancelled_since_an_earlier_read_no_longer_blocks_the_run(tmp_path, monkeypatch):
    """K3a MINOR-4 (test_k3_stale_snapshot.py, the run). After the plan two SELLs are placed by hand, 270 SOXL and
    100 BOXX. The first sell's check (BIL) reads the venue's open orders - both are listed, and cached - and the
    operator then cancels the SOXL one. Before: SOXL was refused all the same ('SELL orders for 270 are already
    open') on the session's stale copy. Now it is sold; the BOXX order, still live, still blocks BOXX."""
    r = CachingRig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    n = len(r.ib.placed)
    hand: dict = {}

    def by_hand():
        hand["SOXL"], hand["BOXX"] = _hand_order(r, "SOXL", 270), _hand_order(r, "BOXX", 100)
    _after_the_plan(r, monkeypatch, by_hand)
    real = r.ib.placeOrder

    def place(contract, order):
        t = real(contract, order)
        if contract.symbol == "BIL" and "SOXL" in hand:
            hand["SOXL"].orderStatus.status = "Cancelled"        # cancelled by hand at the venue
        return t
    monkeypatch.setattr(r.ib, "placeOrder", place)
    r.tick("15:55:05", day=D2)
    for hms in AFTER[:3]:
        r.tick(hms, day=D2)
    assert [t.orderStatus.status for t in r.ib.trades()
            if t.order.permId == hand["SOXL"].order.permId] == ["Submitted"]      # the premise: a stale copy
    assert [(s, q) for s, a, q, _ in r.ib.placed[n:] if a == "SELL"] == [("BIL", 315), ("SOXL", 270)]
    said = [a for a in r.red() if "is NOT sent" in a]
    assert len(said) == 1 and "S-BOXX" in said[0] and "SELL orders for 100 are already open at the venue" in said[0]
    _never_short(r)


def test_k3a_a_flatten_sells_a_symbol_once_its_hand_sell_is_cancelled(tmp_path, monkeypatch):
    """K3a MINOR-4, the flatten: round one does not sell SOXL - a hand SELL 270 rests there - and the operator
    cancels it, as the alert asks. Before: every later round still counted the session's stale copy, until the
    flatten 'GAVE UP after 30 minutes' with 270 SOXL still held. Now round two sells it."""
    r = CachingRig(tmp_path, monkeypatch).invested()
    stop = _hand_order(r, "SOXL", 270)
    r.m.halt("kill", flatten=True)
    r.tick("11:00:00", day=D2)
    assert r.venue_pos() == {"SOXL": 270}
    assert any("NOT sent: the account holds 270 SOXL and SELL orders for 270 are already open" in a for a in r.red())
    stop.orderStatus.status = "Cancelled"
    for hms in ("11:00:10", "11:00:30", "11:01:00", "11:02:30"):
        r.tick(hms, day=D2)
    h = r.m.halt_state()
    assert r.venue_pos() == {} and h.get("flatten_done") and h.get("account_flat") is True
    _never_short(r)


def test_k3a_open_sell_qty_counts_the_venues_answer_and_this_clients_working_orders(tmp_path, monkeypatch):
    """K3a MINOR-4 at the adapter: counted are (a) the venue's answer to THIS request and (b) this client's own
    orders still working in the session - never another client's order that only the cache still holds. A live
    order is never missed (that would allow a short)."""
    r = CachingRig(tmp_path, monkeypatch).invested()
    hand = _hand_order(r, "BIL", 100)
    assert r.ad.open_sell_qty("BIL") == 100                      # a live hand sell: on the venue's list
    mine = tia.FakeTrade(tia.FakeStock("BIL", "SMART", "USD"), tia.FakeMarketOrder("SELL", 50))
    mine.order.orderId, mine.order.permId, mine.order.orderRef = 990, 0, "mirror-x-S-BIL"
    mine.order.clientId = tia._Cfg.ib_client_id                  # ib_async sets it at placeOrder (ib.py:805)
    mine.orderStatus.status = "PendingSubmit"                    # just sent: the venue does not list it yet
    r.ib._trades.append(mine)
    assert r.ad.open_sell_qty("BIL") == 150                      # this client's own working sell counts too
    assert r.ad.open_sell_qty("BIL", exclude="mirror-x-S-BIL") == 100
    hand.orderStatus.status = "Cancelled"                        # cancelled by hand since the last read
    assert [t.orderStatus.status for t in r.ib.trades() if t.order.permId == hand.order.permId] == ["Submitted"]
    assert r.ad.open_sell_qty("BIL") == 50                       # Before: 150 - the stale copy counted
    mine.orderStatus.status = "Cancelled"
    assert r.ad.open_sell_qty("BIL") == 0
    # this client's own sell RESTING at the venue: on the venue's list and in the session as ours - counted once
    r.ib.hold.add("BIL")
    r.ad.place_stock_order("BIL", -30, "MKT", client_order_id="k3a-own-resting")
    own = next(t for t in r.ib.trades() if t.order.orderRef == "k3a-own-resting")
    own.order.clientId = tia._Cfg.ib_client_id
    assert own.orderStatus.status == "Submitted" and r.ad.open_sell_qty("BIL") == 30


@pytest.mark.parametrize("blackhole", [False, True])
def test_k3a_the_post_trade_check_proves_the_session_before_it_reads_the_positions(tmp_path, monkeypatch, blackhole):
    """K3a MINOR-3 (probe 5b): the run is booked, then the session dies with no FIN and the TQQQ just bought is
    sold by hand. Before: the check read the dead session's cached positions and concluded 'done, no problems' -
    the book kept 360 TQQQ the account no longer held, and traded on. Now it proves the session first (which
    reconnects it) and finds the difference: two strikes, halted."""
    r = Rig(tmp_path, monkeypatch).invested()
    real = r.m._finish

    def finish(ad):
        out = real(ad)
        r.ib.drop(silent=True, blackhole=blackhole)
        r.sell_by_hand("TQQQ")
        return out
    monkeypatch.setattr(r.m, "_finish", finish)
    r.tick("15:55:05", day=D2)
    assert r.m.state["last_run"]["outcome"] == "traded" and r.m.state.get("check") is None
    r.tick("15:56:40", day=D2)
    chk = r.m.state["check"]
    assert chk["strikes"] == 1 and not chk["done"] and "TQQQ: the book holds 360, the venue 0" in chk["problems"]
    assert r.ib.connect_calls == 2 and not r.ib.dead
    r.tick("15:57:40", day=D2)
    assert r.m.state["check"]["done"] and r.m.halt_state().get("halted")
    assert any("the account does NOT hold the mirror book" in a and "TQQQ" in a for a in r.red())


def test_k3a_the_buys_cash_read_proves_the_session_first(tmp_path, monkeypatch):
    """K3a N2 (probe P-cash, pre-existing): the session dies with no FIN right after the last sell fills, and
    $20,000 leaves the account by hand. Before: the buys were sized against the dead session's cached cash -
    PULS 438, TECL 161, TQQQ 360 bought, the account left at -$19,369 (borrowed on margin). Now the cash read
    proves the session first: on the new session the account's cash does not cover the book's and the buys
    are HELD until the window closes."""
    r = Rig(tmp_path, monkeypatch).invested()
    r.brain.make = lambda now: payload(now, ROT, session=D2)
    n = len(r.ib.placed)
    real = r.ib.placeOrder

    def place(contract, order):
        t = real(contract, order)
        if contract.symbol == "SOXL" and order.action == "SELL":      # the last sell has filled
            r.ib.drop(silent=True)
            r.acct.cash -= 20_000.0                                    # withdrawn by hand meanwhile
        return t
    monkeypatch.setattr(r.ib, "placeOrder", place)
    r.tick("15:55:05", day=D2)
    for hms in AFTER:
        r.tick(hms, day=D2)
    assert [(s, q) for s, a, q, _ in r.ib.placed[n:] if a == "SELL"] == [("BIL", 315), ("BOXX", 237), ("SOXL", 270)]
    assert [x for x in r.ib.placed[n:] if x[1] == "BUY"] == [] and r.acct.cash >= 0
    assert any("the BUYS are HELD" in a and "exceeds the account's" in a for a in r.red())
    assert any("NO BUYS are sent this session" in a for a in r.red())
    assert not [a for a in r.red() if "tick failed" in a]
    # a proof that FAILS is cash that cannot be read: held, asked again on every step, sent once it answers
    r2 = Rig(tmp_path / "down", monkeypatch).invested()
    r2.brain.make = lambda now: payload(now, ROT, session=D2)
    n2 = len(r2.ib.placed)
    real2 = r2.ib.placeOrder

    def place2(contract, order):
        t = real2(contract, order)
        if contract.symbol == "SOXL" and order.action == "SELL":
            r2.ib.drop(silent=True)
            r2.ib.gateway_up = False                                    # ... and the gateway is gone
        return t
    monkeypatch.setattr(r2.ib, "placeOrder", place2)
    r2.tick("15:55:05", day=D2)
    assert [x for x in r2.ib.placed[n2:] if x[1] == "BUY"] == [] and r2.m.state["run"]["buys_blocked"]
    assert any("the BUYS are HELD — the account's cash cannot be read" in a for a in r2.red())
    r2.ib.gateway_up = True
    r2.tick("15:56:40", day=D2)
    assert [(s, a) for s, a, _, _ in r2.ib.placed[n2:] if a == "BUY"] == [("PULS", "BUY"), ("TECL", "BUY"), ("TQQQ", "BUY")]
    assert not [a for a in r2.red() if "tick failed" in a]
    sound(r2)
    # a normal day: the buys still go at the same instant as the sells, in the decision's first step
    r3 = Rig(tmp_path / "normal", monkeypatch).invested()
    r3.brain.make = lambda now: payload(now, ROT, session=D2)
    n3, stamps = len(r3.ib.placed), []
    real3 = r3.ib.placeOrder
    monkeypatch.setattr(r3.ib, "placeOrder", lambda c, o: (stamps.append((o.action, r3.clock.now)), real3(c, o))[1])
    r3.tick("15:55:05", day=D2)
    assert [(s, a, q) for s, a, q, _ in r3.ib.placed[n3:]] == [
        ("BIL", "SELL", 315), ("BOXX", "SELL", 237), ("SOXL", "SELL", 270),
        ("PULS", "BUY", 438), ("TECL", "BUY", 161), ("TQQQ", "BUY", 360)]
    assert {t for _, t in stamps} == {tm.at("15:55:05", D2)} and not r3.red()
    sound(r3)


def test_k3a_a_sell_held_up_only_by_orders_resting_at_the_venue_is_not_called_a_disagreement(tmp_path, monkeypatch):
    """K3a MINOR-1 (probe 2e): the account holds exactly the book's 315 BIL, and a SELL stop for 315 placed by
    hand rests there. Before: 'The book and the account disagree ... repair the difference with POST
    /mirror/adjust' - there was nothing to repair. A real shortfall keeps that text."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    _hand_order(r, "BIL", 315)
    r.tick("15:55:05", day=D2)
    said = [a for a in r.red() if "mirror-2026-11-11-S-BIL" in a and "is NOT sent" in a]
    assert len(said) == 1 and [x for x in r.ib.placed[n:] if x[1] == "SELL"] == []
    s = said[0]
    assert "the book holds 315 BIL, the account holds 315 and SELL orders for 315 are already open at the venue" in s
    assert "Cancel the open order(s) for 315 BIL at the venue, or let them fill" in s
    assert "nothing is sold for BIL today" in s
    assert "disagree" not in s and "/mirror/adjust" not in s
    # a real shortfall: a hand SELL 200 of which 50 have filled - the account holds 265 of the book's 315
    r2 = Rig(tmp_path / "short", monkeypatch).invested()
    _after_the_plan(r2, monkeypatch, lambda: _hand_order(r2, "BIL", 200, filled=50))
    r2.tick("15:55:05", day=D2)
    said2 = [a for a in r2.red() if "mirror-2026-11-11-S-BIL" in a and "is NOT sent" in a]
    assert len(said2) == 1 and "the book holds 315 BIL, the account holds 265 and SELL orders for 150" in said2[0]
    assert "The book and the account disagree" in said2[0] and "repair the difference with POST /mirror/adjust" in said2[0]


def test_k3a_a_halt_landing_during_the_sells_check_stops_that_sell(tmp_path, monkeypatch):
    """K3a N1 (probe 4c): a halt (no flatten) lands while the check asks the venue. Before: SELL 315 BIL went out
    after it - the halt had been read before the check's round trips, not after them. Both places a run sell is
    sent from: a new order, and one whose first placement never reached the venue."""
    r = Rig(tmp_path, monkeypatch).invested()
    n = len(r.ib.placed)
    real_open = r.ad.open_sell_qty

    def open_sell_qty(sym, exclude=None):
        if sym == "BIL" and not r.m._halted():
            r.m.halt("operator: stop trading (no flatten)")
        return real_open(sym, exclude=exclude)
    monkeypatch.setattr(r.ad, "open_sell_qty", open_sell_qty)
    r.tick("15:55:05", day=D2)
    assert r.ib.placed[n:] == [] and r.m._halted()
    r.tick("15:55:30", day=D2)
    bil = next(o for o in r.m.state["last_run"]["orders"] if o["symbol"] == "BIL")
    assert bil["filled"] == 0 and bil["how"] == "not sent: stopped" and r.ib.placed[n:] == []
    # the re-placement of an order that never reached the venue (state 'intent'), on the next step
    r2 = Rig(tmp_path / "intent", monkeypatch).invested()
    n2, lost = len(r2.ib.placed), []
    real_place, real_open2 = r2.ib.placeOrder, r2.ad.open_sell_qty

    def place(contract, order):
        if contract.symbol == "BIL" and not lost:
            lost.append(1)
            r2.ib._closed()                          # the socket died under the write: nothing reached the venue
            raise ConnectionError("Socket disconnect")
        return real_place(contract, order)

    def open_sell_qty2(sym, exclude=None):
        if sym == "BIL" and lost and not r2.m._halted():
            r2.m.halt("operator: stop trading (no flatten)")
        return real_open2(sym, exclude=exclude)
    monkeypatch.setattr(r2.ib, "placeOrder", place)
    monkeypatch.setattr(r2.ad, "open_sell_qty", open_sell_qty2)
    r2.tick("15:55:05", day=D2)
    assert lost and r2.m._halted() and r2.ib.placed[n2:] == []
    r2.tick("15:55:30", day=D2)
    bil = next(o for o in r2.m.state["last_run"]["orders"] if o["symbol"] == "BIL")
    assert bil["filled"] == 0 and bil["how"].startswith("never reached the venue") and r2.ib.placed[n2:] == []
    _never_short(r2)


# ------------------------------------------------------------------ K4: an earlier open-orders request left unanswered
# ib_async keys EVERY open-orders request "openOrders" and openOrderEnd carries no request id: an earlier request
# still unanswered (the connect-time sync's, whose timeout is only logged, or one that timed out and kept the
# session) would end the next one with a PARTIAL list - a resting hand SELL read as gone (a short), or an order
# read as absent and placed again. Every open-orders read fails closed while one is pending and drops the session.
def test_k4_the_sell_count_fails_closed_while_an_earlier_open_orders_request_is_unanswered(real):
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    assert a.open_sell_qty("TECL") == 0 and a.connects == []           # the twin: nothing pending, an honest answer
    a.ib.wrapper.startReq("openOrders")                               # an earlier request, still unanswered
    with pytest.raises(ib_mod.ExecutorConnectionError, match="still unanswered"):
        a.open_sell_qty("TECL")
    assert not a.ib.isConnected() and a._proven is None
    assert a.open_sell_qty("TECL") == 0                               # the next read runs on a fresh session
    assert a.ib.isConnected() and len(a.connects) == 1 and "openOrders" not in a.ib.wrapper._futures


def test_k4_order_absent_today_proves_nothing_while_an_earlier_open_orders_request_is_unanswered(real):
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    a.connects.clear()
    a.ib.wrapper.startReq("openOrders")
    assert a.order_absent_today("mirror-2026-11-12-S-TECL") is None   # nothing proven: never "absent"
    assert not a.ib.isConnected()
    assert a.order_absent_today("mirror-2026-11-12-S-TECL") is True   # fresh session: both requests answered
    assert len(a.connects) == 1


def test_k4_the_order_history_refresh_fails_closed_while_an_earlier_open_orders_request_is_unanswered(real):
    a, gw = real
    a.ib.connect("x", 0, clientId=17)
    assert isinstance(a._all_trades(refresh=True), list)              # the twin: a normal refresh
    a.ib.wrapper.startReq("openOrders")
    with pytest.raises(ib_mod.ExecutorConnectionError, match="still unanswered"):
        a._all_trades(refresh=True)
    assert not a.ib.isConnected()
