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

import inspect
import socket
import struct
import threading
import time
import types

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
        self.wrapper = types.SimpleNamespace(_futures={})
        self.client = types.SimpleNamespace(connectionStats=self._stats)

    # --- the connection
    def _stats(self):
        if not self.connected:
            raise ConnectionError("Not connected")
        return types.SimpleNamespace(numBytesRecv=self.recv)

    def drop(self, backlog=0, pump_raises=False):
        self.cache_pos, self.cache_vals = VenueIB.positions(self), VenueIB.accountValues(self)
        self.dead, self.backlog, self.pump_raises = True, backlog, pump_raises

    def _closed(self):                  # client.reset() + wrapper.reset()
        self.connected = False
        self._trades = []
        self.wrapper._futures.clear()

    def _req(self):                     # e
        if not self.connected:
            raise ConnectionError("Not connected")
        if self.dead:
            self._closed()
            raise ConnectionError("Socket disconnect")

    def connect(self, host, port, clientId, timeout=15):
        self.connect_calls += 1
        if not self.gateway_up:
            raise ConnectionRefusedError("gateway down (simulated)")
        self._closed()
        self.connected, self.dead, self.backlog = True, False, 0
        if not self.sync_positions:
            self.wrapper._futures["positions"] = object()

    def disconnect(self):
        self._closed()

    def sleep(self, secs=0):            # a, c, d
        if self.dead and self.connected:
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

    def accountSummary(self):
        self._req()
        return self.accountValues()

    def qualifyContracts(self, *contracts):
        self._req()
        return super().qualifyContracts(*contracts)

    def reqMktData(self, contract, generic, snapshot, regulatory):
        if not self.connected:
            raise ConnectionError("Not connected")
        if self.dead:                   # written into a dead socket: no tick ever comes
            return tia.FakeTicker(float("nan"))
        return super().reqMktData(contract, generic, snapshot, regulatory)

    def reqAllOpenOrders(self):
        self._req()
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
