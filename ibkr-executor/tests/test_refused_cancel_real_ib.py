"""The refused-cancel handling against the INSTALLED ib_async 2.1 - not the
fake module the rest of the adapter suite uses. Real IB.placeOrder and
IB.cancelOrder (which logs its own client-side PendingCancel the moment a
cancel is sent), wrapper.error (the Cancelled overlay, then errorEvent),
wrapper.orderStatus and wrapper.execDetails. Only the socket is stubbed: the
venue's replies to a cancel are queued in batches, and one batch is
delivered per ib.sleep() - the adapter's pump. Adapted from verifier A's
harness (2026-10-26)."""
from __future__ import annotations

import pytest

pytest.importorskip("ib_async")
from ib_async import Contract, Execution, Order  # noqa: E402

import app.ib_adapter as ib_mod  # noqa: E402

CID = 17
PERM = 2127961299
R161 = ("Cancel attempted when order is not in a cancellable state.  "
        f"Order permId ={PERM}")
R10148 = "OrderId 7 that needs to be cancelled cannot be cancelled, state: PendingCancel."
CONFIRM_202 = "Order Canceled - reason:"


class _Cfg:
    trading_mode = "paper"
    ib_host = "127.0.0.1"
    ib_client_id = CID
    ib_market_data_type = 1
    ib_allow_delayed = True


class Venue:
    """A real IBAdapter on a real ib_async IB, socket stubbed."""

    def __init__(self, monkeypatch):
        monkeypatch.setattr(ib_mod.IBAdapter, "_connect", lambda self: None)
        monkeypatch.setattr(ib_mod, "CANCEL_ACK_TIMEOUT_S", 0.3)
        monkeypatch.setattr(ib_mod, "WAIT_TICK_S", 0.0)
        self.a = ib_mod.IBAdapter(_Cfg())
        self.ib = self.a.ib
        self.w = self.ib.wrapper
        self.w.clientId = CID
        self.batches: list[list] = []
        self.on_cancel = None            # orderId -> list of reply batches
        monkeypatch.setattr(self.ib, "isConnected", lambda: True)
        monkeypatch.setattr(self.ib, "sleep", self._sleep)
        monkeypatch.setattr(self.ib.client, "placeOrder", lambda *a, **k: None)
        monkeypatch.setattr(self.ib.client, "cancelOrder", self._client_cancel)
        monkeypatch.setattr(self.ib, "reqAllOpenOrders", lambda: [])
        monkeypatch.setattr(self.ib, "reqCompletedOrders", lambda apiOnly=False: [])
        monkeypatch.setattr(self.ib, "reqExecutions", lambda *a, **k: [])

    def _sleep(self, secs=0):
        if self.batches:
            for msg in self.batches.pop(0):
                msg()
        return True

    def _client_cancel(self, orderId, manualCancelOrderTime=""):
        if self.on_cancel:
            self.batches.extend(self.on_cancel(orderId))

    def stop(self, oid=7, qty=5, ref="blend-1-stp-44.0000"):
        """A resting SELL stop placed through the real IB.placeOrder (log:
        PendingSubmit) and acked by the venue (log: Submitted)."""
        c = Contract(symbol="CRSP", secType="STK", exchange="SMART",
                     currency="USD", conId=1)
        o = Order(orderId=oid, action="SELL", totalQuantity=qty,
                  orderType="STP", auxPrice=44.0, orderRef=ref, tif="GTC")
        t = self.ib.placeOrder(c, o)
        self.status(t, "Submitted")()
        assert [e.status for e in t.log] == ["PendingSubmit", "Submitted"]
        return t

    # venue messages, as callables delivered by _sleep
    def err(self, oid, code, text):
        return lambda: self.w.error(oid, code, text, "")

    def status(self, t, status, filled=0.0, avg=0.0):
        return lambda: self.w.orderStatus(
            t.order.orderId, status, filled, t.order.totalQuantity - filled,
            avg, PERM, 0, avg, CID, "", 0.0)

    def execd(self, t, shares, price, n=1):
        def go():
            ex = Execution(execId=f"ex-{t.order.orderId}-{n}",
                           orderId=t.order.orderId, permId=PERM, clientId=CID,
                           shares=shares, price=price, side="SLD",
                           orderRef=t.order.orderRef)
            self.w.execDetails(-1, t.contract, ex)
        return go


def test_real_a_refusal_is_undone_and_raises(monkeypatch):
    """The 161 lands, ib_async overlays Cancelled, the adapter undoes it -
    back to the venue's Submitted, past ib_async's own PendingCancel - and
    with neither a fill nor a cancel in the window the cancel raises. Every
    reader then sees a working order, and the next cancel is sent and ACKed."""
    v = Venue(monkeypatch)
    t = v.stop()
    v.on_cancel = lambda oid: [[v.err(oid, 161, R161)]]
    with pytest.raises(RuntimeError, match=r"^cancel of 7 REFUSED by IBKR \(\[161\] "
                                           r"Cancel attempted.*neither a fill nor a "
                                           r"cancel followed"):
        v.a.cancel_stock_order("7")
    assert t.orderStatus.status == "Submitted"
    assert [(e.status, e.errorCode) for e in t.log][-2:] == [("PendingCancel", 0),
                                                             ("Cancelled", 161)]
    assert v.a.find_stock_order("blend-1-stp-44.0000")["status"] == "working"
    assert v.a.poll_stock_fills() == []
    v.on_cancel = lambda oid: [[v.err(oid, 202, CONFIRM_202)],
                               [v.status(t, "Cancelled")]]
    assert v.a.cancel_stock_order("7") is True


def test_real_a_fill_after_the_refusal_raises_filled(monkeypatch):
    v = Venue(monkeypatch)
    t = v.stop()
    v.on_cancel = lambda oid: [[v.err(oid, 161, R161)],
                               [v.execd(t, 5, 44.0), v.status(t, "Filled", 5, 44.0)]]
    with pytest.raises(RuntimeError, match=r"FILLED before the cancel landed \(IBKR "
                                           r"refused the cancel: \[161\]"):
        v.a.cancel_stock_order("7")
    assert [f["qty"] for f in v.a.poll_stock_fills()] == [-5]


@pytest.mark.parametrize("replies", [
    "pending_202_cancelled", "cancelled_then_202", "202_only",
    "warning_then_cancelled", "api_cancelled", "202_and_cancelled_one_pump",
    "refusal_then_cancelled", "refusal_then_api_cancelled"])
def test_real_every_ack_order_is_an_ack(monkeypatch, replies):
    """The venue's own word, in every order it arrives - and a refusal
    followed by the venue's Cancelled (a cancel already pending completes)."""
    v = Venue(monkeypatch)
    t = v.stop()
    seq = {
        "pending_202_cancelled": lambda oid: [[v.status(t, "PendingCancel")],
                                              [v.err(oid, 202, CONFIRM_202)],
                                              [v.status(t, "Cancelled")]],
        "cancelled_then_202": lambda oid: [[v.status(t, "Cancelled")],
                                           [v.err(oid, 202, CONFIRM_202)]],
        "202_only": lambda oid: [[v.err(oid, 202, CONFIRM_202)]],
        "warning_then_cancelled": lambda oid: [[v.err(oid, 2109, "Order Event Warning")],
                                               [v.status(t, "Cancelled")]],
        "api_cancelled": lambda oid: [[v.status(t, "ApiCancelled")]],
        "202_and_cancelled_one_pump": lambda oid: [[v.err(oid, 202, CONFIRM_202),
                                                    v.status(t, "Cancelled")]],
        "refusal_then_cancelled": lambda oid: [[v.err(oid, 161, R161)],
                                               [v.status(t, "Cancelled")]],
        "refusal_then_api_cancelled": lambda oid: [[v.err(oid, 161, R161)],
                                                   [v.status(t, "ApiCancelled")]],
    }[replies]
    v.on_cancel = seq
    assert v.a.cancel_stock_order("7") is True


def test_real_a_late_refusal_is_undone(monkeypatch):
    """No reply inside the window (the wait raises); the 161 lands later and
    is pumped by the next reader. It is undone there too."""
    v = Venue(monkeypatch)
    t = v.stop()
    v.on_cancel = lambda oid: []
    with pytest.raises(RuntimeError, match="not acknowledged"):
        v.a.cancel_stock_order("7")
    assert t.orderStatus.status == "PendingCancel"     # ib_async's own, client-side
    v.batches.append([v.err(7, 161, R161)])
    assert v.a.find_stock_order("blend-1-stp-44.0000")["status"] == "working"
    assert t.orderStatus.status == "Submitted"
    v.on_cancel = lambda oid: [[v.err(oid, 202, CONFIRM_202)], [v.status(t, "Cancelled")]]
    assert v.a.cancel_stock_order("7") is True


def test_real_a_10148_refusal_is_undone(monkeypatch):
    v = Venue(monkeypatch)
    t = v.stop()
    v.on_cancel = lambda oid: [[v.err(oid, 10148, R10148)]]
    with pytest.raises(RuntimeError, match=r"REFUSED by IBKR \(\[10148\] OrderId 7"):
        v.a.cancel_stock_order("7")
    assert t.orderStatus.status == "Submitted"


@pytest.mark.parametrize("confirm", ["orderstatus", "202"])
def test_real_a_refusal_after_a_real_cancel_is_not_undone(monkeypatch, confirm):
    """The undo's guard (verifier A, round 2): a 161 that lands AFTER the
    venue's own Cancelled or 202 - a duplicate cancel's reply - must leave
    the order cancelled. Without the guard it flipped back to Submitted."""
    v = Venue(monkeypatch)
    t = v.stop()
    first = (v.status(t, "Cancelled") if confirm == "orderstatus"
             else v.err(7, 202, CONFIRM_202))
    v.on_cancel = lambda oid: [[first]]
    assert v.a.cancel_stock_order("7") is True
    v.batches.append([v.err(7, 161, R161)])          # the late duplicate reply
    assert v.a.find_stock_order("blend-1-stp-44.0000")["status"] == "cancelled"
    assert t.orderStatus.status == "Cancelled"


def test_real_an_error_the_undo_leaves_and_a_fill_that_follows(monkeypatch):
    """10147 ("not found") is not undone: the wait still refuses it as the
    ack, and the fill poll does not mark the fill-less 'Cancelled' stop
    emitted, so a fill that lands afterwards is booked."""
    v = Venue(monkeypatch)
    t = v.stop()
    v.on_cancel = lambda oid: [[v.err(oid, 10147, "OrderId 7 that needs to be "
                                                  "cancelled is not found.")]]
    with pytest.raises(RuntimeError, match=r"REFUSED by IBKR \(\[10147\] OrderId 7"):
        v.a.cancel_stock_order("7")
    assert t.orderStatus.status == "Cancelled"
    assert v.a.poll_stock_fills() == []
    v.batches.append([v.execd(t, 5, 44.0), v.status(t, "Filled", 5, 44.0)])
    assert [f["qty"] for f in v.a.poll_stock_fills()] == [-5]
    assert v.a.poll_stock_fills() == []


def test_real_a_partial_fill_then_the_cancel(monkeypatch):
    v = Venue(monkeypatch)
    t = v.stop()
    v.batches.append([v.execd(t, 2, 44.0), v.status(t, "Submitted", 2, 44.0)])
    v.on_cancel = lambda oid: [[v.err(oid, 202, CONFIRM_202)],
                               [v.status(t, "Cancelled", 2, 44.0)]]
    assert v.a.cancel_stock_order("7") is True
    assert v.a._trade_result(t)["filled_qty"] == 2
