"""Real IBAdapter stock/ETF surfaces (blend3070 paper phase), against a
mocked ib_async module — no live gateway exists here. Gates:
  * order construction: MOO = MarketOrder tif OPG, MKT = MarketOrder DAY,
    STP = StopOrder GTC, orderRef = client_order_id, signed-qty -> BUY/SELL
  * async-fill design: MOO/STP return 'working' immediately; MKT gets one
    bounded synchronous-fill window, else 'working'
  * cancel tri-state incl. RAISE-on-filled and RAISE-on-ambiguous-timeout
  * poll drain-once with partial-fill aggregation; MOO/MKT never emitted
  * no silent zero fill prices (unknown -> None/absent, never 0.0)
  * ExecutorConnectionError on every surface when disconnected
  * contract conformance: DryAdapter and mocked IBAdapter pass the same
    behavioral suite (the pinned adapter contract)
  * blend integration: async MOO adoption via reconcile, stop-fill polling,
    ratchet replace, and the exit-await-fill UNRECONCILED path
"""
from __future__ import annotations

import sys
import types

import pytest

import app.ib_adapter as ib_mod
from app.ib_adapter import DryAdapter, ExecutorConnectionError


# --- fake ib_async venue ------------------------------------------------------

class FakeContract:
    def __init__(self, symbol, exchange="", currency=""):
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency


def FakeStock(symbol, exchange, currency):
    return FakeContract(symbol, exchange, currency)


class FakeOrder:
    def __init__(self, action, qty, order_type, stop_price=None):
        self.action = action
        self.totalQuantity = qty
        self.orderType = order_type
        self.auxPrice = stop_price
        self.tif = ""
        self.orderRef = ""
        self.orderId = 0
        self.permId = 0


def FakeMarketOrder(action, qty):
    return FakeOrder(action, qty, "MKT")


def FakeStopOrder(action, qty, stop_price):
    return FakeOrder(action, qty, "STP", stop_price)


class FakeStatus:
    def __init__(self):
        self.status = "PendingSubmit"
        self.avgFillPrice = 0.0


class FakeExec:
    def __init__(self, shares, price, side):
        self.shares = shares
        self.price = price
        self.side = side


class FakeFill:
    def __init__(self, execution):
        self.execution = execution


class FakeTrade:
    def __init__(self, contract, order):
        self.contract = contract
        self.order = order
        self.orderStatus = FakeStatus()
        self.fills = []


class FakeTicker:
    def __init__(self, px):
        self._px = px

    def marketPrice(self):
        return self._px


class FakePosition:
    """One row of ib_async's account positions (R1 verification basis)."""

    def __init__(self, symbol, position, sec_type="STK"):
        self.contract = FakeContract(symbol)
        self.contract.secType = sec_type
        self.position = position


class FakeIB:
    """Scriptable stand-in for ib_async.IB: on_place/on_cancel/on_sleep hooks
    let tests act as the venue (fills, rejects, silent timeouts)."""

    def __init__(self):
        self._trades: list[FakeTrade] = []
        self._next_id = 1
        self.connected = False
        self.prices: dict[str, float] = {}
        self.position_rows: list[FakePosition] = []
        self.on_place = None
        self.on_cancel = None
        self.on_sleep = None
        self.connect_calls = 0
        self.connect_fails = False        # M5: gateway down (restart window)

    # connection
    def connect(self, host, port, clientId, timeout=15):
        self.connect_calls += 1
        if self.connect_fails:
            raise ConnectionRefusedError("gateway down (simulated)")
        self.connected = True

    def disconnect(self):
        self.connected = False

    def isConnected(self):
        return self.connected

    # contracts / quotes
    def qualifyContracts(self, *contracts):
        return list(contracts)

    def reqMktData(self, contract, generic, snapshot, regulatory):
        return FakeTicker(self.prices.get(contract.symbol, float("nan")))

    def cancelMktData(self, contract):
        pass

    # orders
    def placeOrder(self, contract, order):
        order.orderId = self._next_id
        self._next_id += 1
        t = FakeTrade(contract, order)
        t.orderStatus.status = "Submitted"
        self._trades.append(t)
        if self.on_place:
            self.on_place(t)
        return t

    def cancelOrder(self, order):
        t = next(x for x in self._trades if x.order is order)
        if self.on_cancel:
            self.on_cancel(t)
        else:
            t.orderStatus.status = "Cancelled"

    def sleep(self, secs=0):
        if self.on_sleep:
            self.on_sleep(self)

    def trades(self):
        return list(self._trades)

    def reqAllOpenOrders(self):
        return []

    def reqCompletedOrders(self, apiOnly=True):
        return []

    def positions(self):
        return list(self.position_rows)

    # venue-side test helpers
    def fill(self, trade, parts):
        """parts: [(shares, price), ...] -> executions + Filled status."""
        side = "BOT" if trade.order.action == "BUY" else "SLD"
        for shares, price in parts:
            trade.fills.append(FakeFill(FakeExec(shares, price, side)))
        tot = sum(s for s, _ in parts)
        num = sum(s * p for s, p in parts)
        trade.orderStatus.avgFillPrice = (num / tot) if tot else 0.0
        trade.orderStatus.status = "Filled"

    def trade_by_ref(self, order_ref):
        return next(t for t in self._trades
                    if str(t.order.orderId) == str(order_ref))

    # NOTE: the old auto_fill_mkt() ambient hook is deliberately GONE — it
    # filled every book-order MKT synchronously so no book order ever
    # survived a cycle, masking the M1 duplicate-order defect. Tests that
    # need the venue to fill a working DAY MKT call _fill_working_mkt()
    # EXPLICITLY between cycles (the real async path), or set a narrow
    # on_place hook when the bounded synchronous-fill window itself is
    # under test.


def _fill_working_mkt(fake: FakeIB):
    """Venue action: fill every still-working DAY market order at the
    quoted price — an explicit post-placement event, exercised BETWEEN
    cycles so adoption goes through reconcile pass 2b like on the real
    venue."""
    for t in fake.trades():
        if (t.order.orderType == "MKT" and t.order.tif == "DAY"
                and t.orderStatus.status not in ("Filled", "Cancelled",
                                                 "ApiCancelled", "Inactive")):
            fake.fill(t, [(t.order.totalQuantity,
                           fake.prices.get(t.contract.symbol, 100.0))])


class _Cfg:
    trading_mode = "paper"
    dry_run = True              # mode-guard: tests run a "dry:paper" book
    ib_host = "127.0.0.1"
    ib_client_id = 17
    blend_budget = 0.0
    blend_book_usd = 10_000.0
    tracker_url = ""
    tracker_user = ""
    tracker_password = ""


@pytest.fixture
def ib_adapter(monkeypatch):
    mod = types.ModuleType("ib_async")
    mod.IB = FakeIB
    mod.Stock = FakeStock
    mod.Future = FakeStock          # unused by the stock surfaces
    mod.MarketOrder = FakeMarketOrder
    mod.StopOrder = FakeStopOrder
    monkeypatch.setitem(sys.modules, "ib_async", mod)
    # keep the bounded waits short: FakeIB.sleep never actually sleeps
    monkeypatch.setattr(ib_mod, "PLACE_ACK_TIMEOUT_S", 0.2)
    monkeypatch.setattr(ib_mod, "MKT_FILL_WAIT_S", 0.2)
    monkeypatch.setattr(ib_mod, "CANCEL_ACK_TIMEOUT_S", 0.2)
    monkeypatch.setattr(ib_mod, "WAIT_TICK_S", 0.0)
    a = ib_mod.IBAdapter(_Cfg())
    a.ib.prices = {"SPY": 100.0, "BIL": 100.0, "CRSP": 50.0}
    return a


# --- order construction -------------------------------------------------------

def test_moo_is_market_order_with_opg_tif_and_returns_working(ib_adapter):
    r = ib_adapter.place_stock_order("CRSP", 5, "MOO", tif="OPG",
                                     ref_price=50.0,
                                     client_order_id="blend-1-entry")
    (t,) = ib_adapter.ib.trades()
    assert t.order.orderType == "MKT" and t.order.tif == "OPG"
    assert t.order.action == "BUY" and t.order.totalQuantity == 5
    assert t.order.orderRef == "blend-1-entry"
    assert t.contract.symbol == "CRSP"
    assert t.contract.exchange == "SMART" and t.contract.currency == "USD"
    # async-fill design: never blocks waiting for the open
    assert r["status"] == "working" and r["order_ref"] == str(t.order.orderId)
    assert "fill_price" not in r


def test_stp_is_stop_order_with_gtc_tif(ib_adapter):
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     tif="GTC",
                                     client_order_id="blend-1-stp-44.0000")
    (t,) = ib_adapter.ib.trades()
    assert t.order.orderType == "STP" and t.order.tif == "GTC"
    assert t.order.auxPrice == 44.0
    assert t.order.action == "SELL" and t.order.totalQuantity == 5
    assert r["status"] == "working"


def test_mkt_is_day_market_order_and_signed_qty_maps_sides(ib_adapter):
    ib_adapter.place_stock_order("SPY", 70, "MKT")
    ib_adapter.place_stock_order("SPY", -30, "MKT")
    buy, sell = ib_adapter.ib.trades()
    assert buy.order.orderType == "MKT" and buy.order.tif == "DAY"
    assert buy.order.action == "BUY" and buy.order.totalQuantity == 70
    assert sell.order.action == "SELL" and sell.order.totalQuantity == 30


def test_validation_errors(ib_adapter):
    with pytest.raises(ValueError):
        ib_adapter.place_stock_order("SPY", 1, "LMT")
    with pytest.raises(ValueError):
        ib_adapter.place_stock_order("SPY", 1, "STP")   # STP needs stop_price
    with pytest.raises(ValueError):
        ib_adapter.place_stock_order("SPY", 0, "MKT")


def test_qualified_contracts_are_cached(ib_adapter):
    calls = []
    real = ib_adapter.ib.qualifyContracts

    def counting(*cs):
        calls.append(cs)
        return real(*cs)

    ib_adapter.ib.qualifyContracts = counting
    ib_adapter.place_stock_order("SPY", 1, "MKT")
    ib_adapter.place_stock_order("SPY", 2, "MKT")
    assert len(calls) == 1


# --- placement outcomes -------------------------------------------------------

def test_mkt_synchronous_fill_returns_weighted_average(ib_adapter):
    fake = ib_adapter.ib
    fake.on_place = lambda t: fake.fill(t, [(3, 50.0), (2, 50.5)])
    r = ib_adapter.place_stock_order("CRSP", 5, "MKT")
    assert r["status"] == "filled"
    assert r["fill_price"] == pytest.approx(50.2)


def test_mkt_not_filled_in_window_returns_working_without_price(ib_adapter):
    r = ib_adapter.place_stock_order("CRSP", 5, "MKT")
    assert r["status"] == "working" and "fill_price" not in r


def test_filled_with_unknown_price_has_no_fill_price_never_zero(ib_adapter):
    fake = ib_adapter.ib

    def broken_fill(t):
        t.orderStatus.status = "Filled"      # no executions, avgFillPrice 0.0

    fake.on_place = broken_fill
    r = ib_adapter.place_stock_order("CRSP", 5, "MKT")
    assert r["status"] == "filled"
    assert "fill_price" not in r             # None/absent, NEVER 0.0
    assert r.get("fill_price") is None


def test_rejected_placement_raises(ib_adapter):
    fake = ib_adapter.ib

    def reject(t):
        t.orderStatus.status = "Inactive"

    fake.on_place = reject
    with pytest.raises(RuntimeError, match="rejected"):
        ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)


def test_missing_ack_times_out_and_raises(ib_adapter):
    fake = ib_adapter.ib

    def silent(t):
        t.orderStatus.status = "PendingSubmit"   # venue never answers

    fake.on_place = silent
    with pytest.raises(RuntimeError, match="no venue ack"):
        ib_adapter.place_stock_order("CRSP", 5, "MKT")


def test_duplicate_client_order_id_suppressed_by_order_ref(ib_adapter):
    r1 = ib_adapter.place_stock_order("CRSP", 5, "MOO",
                                      client_order_id="blend-1-entry")
    r2 = ib_adapter.place_stock_order("CRSP", 5, "MOO",
                                      client_order_id="blend-1-entry")
    assert r2["order_ref"] == r1["order_ref"] and r2.get("duplicate") is True
    assert len(ib_adapter.ib.trades()) == 1      # one real order only


def test_dedupe_allows_new_order_after_cancel(ib_adapter):
    r1 = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                      client_order_id="blend-1-stp-44.0000")
    assert ib_adapter.cancel_stock_order(r1["order_ref"]) is True
    r2 = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                      client_order_id="blend-1-stp-44.0000")
    assert r2["order_ref"] != r1["order_ref"] and "duplicate" not in r2
    assert len(ib_adapter.ib.trades()) == 2


# --- cancel tri-state ---------------------------------------------------------

def test_cancel_unknown_order_returns_false(ib_adapter):
    assert ib_adapter.cancel_stock_order("never-seen") is False


def test_cancel_working_then_already_cancelled(ib_adapter):
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    assert ib_adapter.cancel_stock_order(r["order_ref"]) is True
    assert ib_adapter.cancel_stock_order(r["order_ref"]) is False


def test_cancel_of_filled_order_raises(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    fake.fill(fake.trade_by_ref(r["order_ref"]), [(5, 44.0)])
    with pytest.raises(RuntimeError, match="FILLED"):
        ib_adapter.cancel_stock_order(r["order_ref"])


def test_cancel_race_fill_beats_cancel_raises(ib_adapter):
    fake = ib_adapter.ib
    fake.on_cancel = lambda t: fake.fill(t, [(5, 44.0)])   # fill wins the race
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    with pytest.raises(RuntimeError, match="FILLED"):
        ib_adapter.cancel_stock_order(r["order_ref"])


def test_cancel_ack_timeout_raises_fail_closed(ib_adapter):
    fake = ib_adapter.ib
    fake.on_cancel = lambda t: None          # venue never acks the cancel
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    with pytest.raises(RuntimeError, match="UNKNOWN"):
        ib_adapter.cancel_stock_order(r["order_ref"])


# --- poll drain-once ----------------------------------------------------------

def test_poll_aggregates_partial_fills_and_drains_once(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                     client_order_id="blend-1-stp-44.0000")
    assert ib_adapter.poll_stock_fills() == []          # still resting
    fake.fill(fake.trade_by_ref(r["order_ref"]), [(2, 44.0), (3, 43.9)])
    (f,) = ib_adapter.poll_stock_fills()
    assert f["order_ref"] == r["order_ref"]
    assert f["client_order_id"] == "blend-1-stp-44.0000"
    assert f["symbol"] == "CRSP" and f["action"] == "SLD"
    assert f["qty"] == -5                               # aggregated, signed
    assert f["fill_price"] == pytest.approx((2 * 44.0 + 3 * 43.9) / 5)
    assert ib_adapter.poll_stock_fills() == []          # never re-emitted


def test_poll_never_emits_moo_or_mkt_fills(ib_adapter):
    fake = ib_adapter.ib
    r1 = ib_adapter.place_stock_order("SPY", 70, "MKT")
    r2 = ib_adapter.place_stock_order("CRSP", 5, "MOO")
    fake.fill(fake.trade_by_ref(r1["order_ref"]), [(70, 100.0)])
    fake.fill(fake.trade_by_ref(r2["order_ref"]), [(5, 50.0)])
    # journal reconcile adopts these by orderRef; the fill poll stays silent
    assert ib_adapter.poll_stock_fills() == []


def test_poll_cancelled_stop_without_executions_emits_nothing(ib_adapter):
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    assert ib_adapter.cancel_stock_order(r["order_ref"]) is True
    assert ib_adapter.poll_stock_fills() == []


def test_poll_priceless_stop_fill_reports_none_never_zero(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    t = fake.trade_by_ref(r["order_ref"])
    t.fills.append(FakeFill(FakeExec(5, 0.0, "SLD")))   # venue lost the price
    t.orderStatus.status = "Filled"
    (f,) = ib_adapter.poll_stock_fills()
    assert f["fill_price"] is None                      # None, NEVER 0.0


def test_requeue_pushes_fills_back_to_the_front(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    fake.fill(fake.trade_by_ref(r["order_ref"]), [(5, 44.0)])
    (f,) = ib_adapter.poll_stock_fills()
    ib_adapter.requeue_stock_fills([f])
    assert ib_adapter.poll_stock_fills() == [f]         # exactly once, again
    assert ib_adapter.poll_stock_fills() == []


# --- find_stock_order ---------------------------------------------------------

def test_find_stock_order_by_client_id(ib_adapter):
    fake = ib_adapter.ib
    assert ib_adapter.find_stock_order("blend-1-entry") is None
    r = ib_adapter.place_stock_order("CRSP", 5, "MOO",
                                     client_order_id="blend-1-entry")
    o = ib_adapter.find_stock_order("blend-1-entry")
    assert o == {"order_ref": r["order_ref"], "status": "working"}
    fake.fill(fake.trade_by_ref(r["order_ref"]), [(5, 50.3)])
    o = ib_adapter.find_stock_order("blend-1-entry")
    assert o["status"] == "filled" and o["fill_price"] == pytest.approx(50.3)


def test_find_prefers_the_live_order_over_a_dead_earlier_attempt(ib_adapter):
    r1 = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                      client_order_id="blend-1-stp-44.0000")
    ib_adapter.cancel_stock_order(r1["order_ref"])
    r2 = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                      client_order_id="blend-1-stp-44.0000")
    o = ib_adapter.find_stock_order("blend-1-stp-44.0000")
    assert o["order_ref"] == r2["order_ref"] and o["status"] == "working"


# --- connection care ----------------------------------------------------------

def test_every_surface_raises_executor_connection_error_when_down(ib_adapter):
    ib_adapter.ib.connected = False
    ib_adapter.ib.connect_fails = True      # gateway hard-down: reconnect
                                            # attempts fail too (M5)
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.place_stock_order("SPY", 1, "MKT")
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.cancel_stock_order("1")
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.poll_stock_fills()
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.find_stock_order("blend-1-entry")
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.spot("SPY")


def test_spot_quotes_arbitrary_symbols_as_smart_usd_stocks(ib_adapter):
    assert ib_adapter.spot("SPY") == 100.0   # not in the El Nino UNDERLYINGS
    with pytest.raises(RuntimeError):
        ib_adapter.spot("NOQUOTE")           # nan price -> raise, never 0


# R1 (blackout guard): venue POSITIONS are the positive-verification basis.

def test_gate_r1_stock_position_sums_account_rows(ib_adapter):
    fake = ib_adapter.ib
    fake.position_rows = [FakePosition("CRSP", 5), FakePosition("SPY", 70),
                          FakePosition("CRSP", 2)]
    assert ib_adapter.stock_position("CRSP") == 7
    assert ib_adapter.stock_position("SPY") == 70
    assert ib_adapter.stock_position("BIL") == 0
    fake.connected = False
    fake.connect_fails = True               # down: fail closed, never guess
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.stock_position("CRSP")


def test_gate_r1_dry_adapter_tracks_venue_positions():
    a = DryAdapter()
    a.place_stock_order("CRSP", 5, "MKT", ref_price=50.0)
    assert a.stock_position("CRSP") == 5
    s = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    assert a.stock_position("CRSP") == 5     # resting stop: no change
    a.trigger_stop(s["order_ref"])
    assert a.stock_position("CRSP") == 0     # stop fill left the account
    a.place_stock_order("CRSP", 4, "MKT", ref_price=45.0)
    s2 = a.place_stock_order("CRSP", -4, "STP", stop_price=40.0, tif="GTC")
    a.trigger_stop_partial(s2["order_ref"], 3)
    assert a.stock_position("CRSP") == 1     # partial: only 3 left


# --- contract conformance: DryAdapter and (mocked) IBAdapter behave alike -----

class _Venue:
    """Uniform driver over both adapters so the same behavioral suite runs
    against each — the pinned contract, asserted identically."""

    def __init__(self, adapter, kind):
        self.a = adapter
        self.kind = kind

    def trigger_stop(self, order_ref):
        if self.kind == "dry":
            self.a.trigger_stop(order_ref)
        else:
            t = self.a.ib.trade_by_ref(order_ref)
            self.a.ib.fill(t, [(t.order.totalQuantity,
                                float(t.order.auxPrice))])

    def trigger_stop_partial(self, order_ref, shares):
        """Partial fill at the stop, remainder cancelled at the venue
        (adapter review M3)."""
        if self.kind == "dry":
            self.a.trigger_stop_partial(order_ref, shares)
        else:
            t = self.a.ib.trade_by_ref(order_ref)
            side = "SLD" if t.order.action == "SELL" else "BOT"
            t.fills.append(FakeFill(FakeExec(shares,
                                             float(t.order.auxPrice), side)))
            t.orderStatus.status = "Cancelled"


@pytest.fixture(params=["dry", "ib"])
def venue(request, monkeypatch):
    if request.param == "dry":
        return _Venue(DryAdapter(), "dry")
    return _Venue(request.getfixturevalue("ib_adapter"), "ib")


def test_contract_stop_lifecycle_and_cancel_tristate(venue):
    a = venue.a
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                            client_order_id="blend-1-stp-44.0000")
    assert r["status"] == "working" and r["order_ref"]
    assert "fill_price" not in r
    assert a.cancel_stock_order("never-seen-ref") is False    # not found
    assert a.cancel_stock_order(r["order_ref"]) is True       # working -> True
    assert a.cancel_stock_order(r["order_ref"]) is False      # already gone


def test_contract_cancel_of_filled_order_raises(venue):
    a = venue.a
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    venue.trigger_stop(r["order_ref"])
    with pytest.raises(Exception):
        a.cancel_stock_order(r["order_ref"])


def test_contract_poll_drains_each_fill_exactly_once(venue):
    a = venue.a
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    assert a.poll_stock_fills() == []
    venue.trigger_stop(r["order_ref"])
    (f,) = a.poll_stock_fills()
    assert f["order_ref"] == r["order_ref"]
    assert f["symbol"] == "CRSP" and f["qty"] == -5
    assert f["fill_price"] == 44.0
    assert a.poll_stock_fills() == []


def test_contract_requeue_restores_unprocessed_fills(venue):
    a = venue.a
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    venue.trigger_stop(r["order_ref"])
    fills = a.poll_stock_fills()
    a.requeue_stock_fills(fills)
    assert a.poll_stock_fills() == fills
    assert a.poll_stock_fills() == []


def test_contract_partial_fill_then_cancel_emits_partial_qty(venue):
    """M3: a partially-filled-then-cancelled stop emits ONE event with the
    SIGNED PARTIAL qty (never the full order qty) on BOTH adapters — blend
    books only the filled shares and re-protects the remainder."""
    a = venue.a
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC")
    venue.trigger_stop_partial(r["order_ref"], 3)
    (f,) = a.poll_stock_fills()
    assert f["order_ref"] == r["order_ref"]
    assert f["qty"] == -3                    # the PARTIAL qty, signed
    assert f["fill_price"] == 44.0
    assert a.poll_stock_fills() == []        # drained once


def test_contract_find_stock_order_by_idempotency_key(venue):
    a = venue.a
    assert a.find_stock_order("never-seen") is None
    r = a.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                            client_order_id="blend-1-stp-44.0000")
    o = a.find_stock_order("blend-1-stp-44.0000")
    assert o["order_ref"] == r["order_ref"] and o["status"] == "working"
    venue.trigger_stop(r["order_ref"])
    o = a.find_stock_order("blend-1-stp-44.0000")
    assert o["status"] == "filled" and o["fill_price"] == 44.0


def test_contract_duplicate_placement_suppressed(venue):
    a = venue.a
    r1 = a.place_stock_order("CRSP", 5, "MOO", ref_price=50.0,
                             client_order_id="blend-1-entry")
    r2 = a.place_stock_order("CRSP", 5, "MOO", ref_price=50.0,
                             client_order_id="blend-1-entry")
    assert r2["order_ref"] == r1["order_ref"] and r2.get("duplicate") is True


def test_contract_validation(venue):
    a = venue.a
    with pytest.raises(ValueError):
        a.place_stock_order("SPY", 1, "LMT")
    with pytest.raises(ValueError):
        a.place_stock_order("SPY", 1, "STP")             # STP needs stop_price


# --- blend gate integration against the mocked IBAdapter ----------------------

from app.blend import Blend3070Manager, run_cycle   # noqa: E402


def _payload(entries=(), stops=(), exits=()):
    return {
        "as_of": "2026-08-20",
        "gate": {"xbi_above_200dma_prior": True, "since": None},
        "entries": list(entries), "exits": list(exits), "stops": list(stops),
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": {"max_open": 10, "risk_frac": 0.01, "band": 0.05,
                        "cash_vehicle": "BIL", "core": "SPY"},
    }


ENTRY = {"symbol": "CRSP", "call_id": 1, "fire_date": "2026-08-20",
         "flag_type": "pre_catalyst_sentiment_ramp", "risk_frac": 0.01,
         "entry_ref": 50.0, "note": "test"}
STOP = {"symbol": "CRSP", "call_id": 1, "trail_level": 44.0}


def _mgr(tmp_path):
    m = Blend3070Manager(_Cfg(), str(tmp_path / "blend.json"))
    m.state.initialized = True
    m.state.sleeve_cash = 3_000.0
    m.state.spy_qty = 70
    return m


def test_blend_async_moo_entry_adopted_by_reconcile(tmp_path, ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    alerts: list[str] = []
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=alerts.append)
    # async venue: the MOO is accepted but NOT filled -> journal stays,
    # no position is booked, and nothing was booked at a fake price
    assert m.state.positions == {}
    assert "1" in m.state.pending_entries
    assert any("awaiting fill" in msg for msg in alerts)
    moo = fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"])
    assert moo.order.tif == "OPG"
    # the venue fills at the open (at a price != entry_ref); the working
    # sweep MKT fills too and is adopted by reconcile pass 2b
    fake.fill(moo, [(5, 50.3)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=alerts.append)
    pos = m.state.positions["1"]
    assert pos.qty == 5 and pos.fill_price == pytest.approx(50.3)
    assert m.state.pending_entries == {}     # journal fulfilled
    # protective stop restored by reconcile pass 4, resting GTC at the venue
    stop_trade = fake.trade_by_ref(pos.stop_order_ref)
    assert stop_trade.order.orderType == "STP"
    assert stop_trade.order.tif == "GTC"
    assert stop_trade.orderStatus.status == "Submitted"
    # exactly one MOO ever reached the venue (dedupe + journal)
    moos = [t for t in fake.trades() if t.order.tif == "OPG"]
    assert len(moos) == 1


def test_blend_stop_fill_polled_and_booked_once(tmp_path, ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    pos = m.state.positions["1"]
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    fake.fill(fake.trade_by_ref(pos.stop_order_ref), [(5, 44.0)])
    run_cycle(m, ib_adapter, None, "2026-08-22", alert=lambda _: None)
    assert "1" not in m.state.positions      # closed from the venue fill
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 44.0)
    run_cycle(m, ib_adapter, None, "2026-08-23", alert=lambda _: None)
    assert (m.state.sleeve_cash + m.state.bil_qty * 100.0
            == pytest.approx(total_after))   # never re-booked


def test_blend_stop_ratchet_replaces_new_first_on_ib(tmp_path, ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    old_ref = m.state.positions["1"].stop_order_ref
    run_cycle(m, ib_adapter,
              _payload(stops=[{"symbol": "CRSP", "call_id": 1,
                               "trail_level": 47.0}]),
              "2026-08-22", alert=lambda _: None)
    pos = m.state.positions["1"]
    assert pos.stop_level == 47.0 and pos.stop_order_ref != old_ref
    assert fake.trade_by_ref(old_ref).orderStatus.status == "Cancelled"
    new_trade = fake.trade_by_ref(pos.stop_order_ref)
    assert new_trade.order.auxPrice == 47.0
    assert new_trade.orderStatus.status == "Submitted"    # never naked
    stops = [t for t in fake.trades() if t.order.orderType == "STP"]
    assert [t.order.orderId for t in stops] == sorted(
        t.order.orderId for t in stops)      # new placed before old cancelled


def test_blend_exit_mkt_without_sync_fill_parks_unreconciled(tmp_path,
                                                             ib_adapter):
    """Documented blend<->async mismatch: _execute_exit books from the
    placement result, so a MKT sell that misses the bounded synchronous-fill
    window routes to the LOUD UNRECONCILED path (proceeds not booked, RED
    alert, manual reconciliation) — never a faked or 0.0 price."""
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    cash_before = m.state.sleeve_cash        # exit MKT will NOT fill in-window
    alerts: list[str] = []
    run_cycle(m, ib_adapter,
              _payload(exits=[{"symbol": "CRSP", "call_id": 1,
                               "reason": "trail", "trail_level": 47.0}]),
              "2026-08-22", alert=alerts.append)
    assert "1" not in m.state.positions
    assert "1" in m.state.unreconciled       # parked, not booked
    assert m.state.sleeve_cash == pytest.approx(cash_before)
    assert any("UNRECONCILED" in msg for msg in alerts)


def test_blend_exit_with_sync_mkt_fill_books_normally(tmp_path, ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    fake.prices["CRSP"] = 47.5
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0

    # the exit MKT fills INSIDE the bounded synchronous window this time
    def sync_fill(t):
        if t.order.orderType == "MKT" and t.order.tif == "DAY":
            fake.fill(t, [(t.order.totalQuantity,
                           fake.prices.get(t.contract.symbol))])
    fake.on_place = sync_fill
    run_cycle(m, ib_adapter,
              _payload(exits=[{"symbol": "CRSP", "call_id": 1,
                               "reason": "trail", "trail_level": 47.0}]),
              "2026-08-22", alert=lambda _: None)
    assert "1" not in m.state.positions and not m.state.unreconciled
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 47.5)


# --- adapter-review regression gates (M1/M3/M5 + escalated minors) ------------
# Each scenario is derived from the failed IB-adapter review's attack notes:
# the attacks that CONFIRMED the defects are now merge-blocking gates.


# M1: a working (unfilled) book-order MKT must NEVER be re-planned/re-placed
# on later cycles — the journal suppresses its kind until reconcile pass 2b
# adopts or clears it, and the client id is stable per INTENT.

def test_gate_m1_working_core_buy_places_exactly_one_order_across_cycles(
        tmp_path, ib_adapter):
    """THE M1 gate: two consecutive cycles with an unfilled working CORE_BUY
    (and SWEEP) place exactly ONE venue order each — the old code re-placed
    every cycle (~12/hour overnight), stacking duplicates that all filled
    at the open."""
    fake = ib_adapter.ib
    m = Blend3070Manager(_Cfg(), str(tmp_path / "blend.json"))  # fresh boot
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    # boot plans CORE_BUY 70 SPY + SWEEP 30 BIL; both MKTs stay 'working'
    # (e.g. placed outside RTH)
    assert len([t for t in fake.trades() if t.order.orderType == "MKT"]) == 2
    assert len(m.state.pending_book_orders) == 2
    cids = set(m.state.pending_book_orders)
    # cycles 2 and 3: SAME working orders — nothing re-placed, cids stable
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=lambda _: None)
    assert len([t for t in fake.trades() if t.order.orderType == "MKT"]) == 2
    assert set(m.state.pending_book_orders) == cids
    assert m.state.spy_qty == 0 and m.state.bil_qty == 0  # nothing booked yet
    # the venue fills at the open -> adopted exactly once by pass 2b
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=lambda _: None)
    assert m.state.pending_book_orders == {}
    assert m.state.spy_qty == 70 and m.state.bil_qty == 30
    assert m.state.core_cash == pytest.approx(0.0)
    assert m.state.sleeve_cash == pytest.approx(0.0)
    assert len([t for t in fake.trades() if t.order.orderType == "MKT"]) == 2


def test_gate_m1_working_rebalance_core_sell_not_duplicated(tmp_path,
                                                            ib_adapter):
    """The review's worst case: repeated core-rebal-sells clamp to the
    un-debited spy_qty and can liquidate the entire core. One intent = one
    venue order, adopted once."""
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    m.state.sleeve_cash = 0.0
    m.state.bil_qty = 20
    m.state.spy_qty = 80          # w = 20% -> core_to_sleeve $1,000 SPY sell
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)

    def spy_sells():
        return [t for t in fake.trades()
                if t.order.orderType == "MKT" and t.order.action == "SELL"
                and t.contract.symbol == "SPY"]

    assert len(spy_sells()) == 1 and spy_sells()[0].order.totalQuantity == 10
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=lambda _: None)
    assert len(spy_sells()) == 1              # never re-placed while working
    assert m.state.spy_qty == 80              # nothing booked off absent fills
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=lambda _: None)
    assert len(spy_sells()) == 1
    assert m.state.spy_qty == 70              # booked exactly once
    # proceeds transferred exactly once (cash or swept BIL)
    assert m.sleeve_value({"SPY": 100.0, "BIL": 100.0}) == pytest.approx(
        3_000.0)


def test_gate_m1_ack_timeout_retry_adopts_same_intent_not_a_new_order(
        tmp_path, ib_adapter):
    """The client id is deterministic per INTENT: a placement whose ack
    timed out (order actually landed) keeps its journal and cid — the next
    cycles adopt the SAME venue order, never re-placing under a fresh seq."""
    fake = ib_adapter.ib
    m = _mgr(tmp_path)

    def silent(t):
        t.orderStatus.status = "PendingSubmit"    # venue never acks in-window
    fake.on_place = silent
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    # the sweep placement raised after journaling; the order DID land
    assert len(m.state.pending_book_orders) == 1
    (cid,) = m.state.pending_book_orders
    assert len(fake.trades()) == 1
    fake.on_place = None
    # a re-run while the order is still merely working: nothing new placed
    for t in fake.trades():
        t.orderStatus.status = "Submitted"
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    assert len(fake.trades()) == 1
    assert list(m.state.pending_book_orders) == [cid]
    # the venue fills the SAME order -> adopted, no duplicate ever placed
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=lambda _: None)
    assert m.state.pending_book_orders == {}
    assert m.state.bil_qty == 30
    assert len(fake.trades()) == 1


# M3: partial-fill-then-cancel on the exit path — the MKT sell sizes from
# the venue-truth REMAINING qty, never the step-time full book qty.

def test_gate_m3_partial_fill_then_cancel_exit_sells_only_remaining(
        tmp_path, ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    _fill_working_mkt(fake)
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    pos = m.state.positions["1"]
    stop_trade = fake.trade_by_ref(pos.stop_order_ref)
    # venue: 3 of 5 shares fill at the stop...
    stop_trade.fills.append(FakeFill(FakeExec(3, 44.0, "SLD")))

    # ...then the cancel wins for the remainder
    def cancel_partial(t):
        t.orderStatus.status = "Cancelled"
    fake.on_cancel = cancel_partial

    # the exit MKT fills synchronously in-window (CRSP at 45.0)
    def sync_fill(t):
        if t.order.orderType == "MKT" and t.order.tif == "DAY":
            px = (45.0 if t.contract.symbol == "CRSP"
                  else fake.prices.get(t.contract.symbol, 100.0))
            fake.fill(t, [(t.order.totalQuantity, px)])
    fake.on_place = sync_fill

    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    run_cycle(m, ib_adapter,
              _payload(exits=[{"symbol": "CRSP", "call_id": 1,
                               "reason": "trail", "trail_level": 47.0}]),
              "2026-08-22", alert=lambda _: None)
    assert "1" not in m.state.positions
    mkt_sells = [t for t in fake.trades()
                 if t.order.orderType == "MKT" and t.order.tif == "DAY"
                 and t.order.action == "SELL" and t.contract.symbol == "CRSP"]
    assert len(mkt_sells) == 1
    assert mkt_sells[0].order.totalQuantity == 2       # REMAINING, not 5
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    # 3 @ 44 (partial stop) + 2 @ 45 (MKT remainder) — booked exactly once
    assert total_after - total_before == pytest.approx(3 * 44.0 + 2 * 45.0)
    partial_rows = [t for t in m.state.trades
                    if t["kind"].endswith("_partial")]
    assert len(partial_rows) == 1 and partial_rows[0]["qty"] == 3


# M5: gateway reconnect with backoff — the daily restart window is a
# non-event (fail closed during, auto-recover after, alert only > 30 min).

def test_gate_m5_auto_reconnect_after_gateway_restart(ib_adapter):
    fake = ib_adapter.ib
    fake.connected = False                    # daily gateway restart done
    assert ib_adapter.spot("SPY") == 100.0    # transparently reconnected
    assert fake.isConnected()


def test_gate_m5_reconnect_backoff_limits_attempts(ib_adapter):
    fake = ib_adapter.ib
    fake.connected = False
    fake.connect_fails = True
    before = fake.connect_calls
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.poll_stock_fills()
    assert fake.connect_calls == before + 1
    with pytest.raises(ExecutorConnectionError):      # inside backoff window
        ib_adapter.poll_stock_fills()
    assert fake.connect_calls == before + 1           # no hammering
    ib_adapter._next_reconnect_ts = 0.0               # backoff expires
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.poll_stock_fills()
    assert fake.connect_calls == before + 2


def test_gate_m5_outage_alert_only_after_30_min_then_recovery(
        ib_adapter, monkeypatch):
    import app.alerts as alerts_mod
    sent: list[str] = []
    monkeypatch.setattr(alerts_mod, "send", sent.append)
    fake = ib_adapter.ib
    fake.connected = False
    fake.connect_fails = True
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.find_stock_order("blend-1-entry")
    assert sent == []                         # short outage: NO alert
    # the outage has now lasted > 30 min
    ib_adapter._disconnected_since -= (ib_mod.OUTAGE_ALERT_S + 60)
    ib_adapter._next_reconnect_ts = 0.0
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.find_stock_order("blend-1-entry")
    assert len(sent) == 1 and "DOWN" in sent[0]
    ib_adapter._next_reconnect_ts = 0.0
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.find_stock_order("blend-1-entry")
    assert len(sent) == 1                     # alerted exactly ONCE
    # gateway back: recovery notice, backoff reset, surfaces work again
    fake.connect_fails = False
    ib_adapter._next_reconnect_ts = 0.0
    assert ib_adapter.find_stock_order("blend-1-entry") is None
    assert len(sent) == 2 and "RECONNECTED" in sent[1]
    assert ib_adapter._reconnect_backoff == ib_mod.RECONNECT_BACKOFF_S
    assert ib_adapter._disconnected_since is None


def test_gate_m5_drain_once_survives_reconnect(ib_adapter):
    fake = ib_adapter.ib
    r = ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0)
    fake.fill(fake.trade_by_ref(r["order_ref"]), [(5, 44.0)])
    assert len(ib_adapter.poll_stock_fills()) == 1
    fake.connected = False                    # gateway restart
    assert ib_adapter.poll_stock_fills() == []  # reconnected, NOT re-emitted
    assert fake.isConnected()


def test_gate_m5_cycle_fails_closed_then_auto_recovers(tmp_path, ib_adapter):
    """The daily restart window end-to-end: the cycle fails CLOSED while
    the gateway is down (no orders, no journals), then the next cycle
    reconnects and proceeds normally."""
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    fake.connected = False
    fake.connect_fails = True
    with pytest.raises(ExecutorConnectionError):
        run_cycle(m, ib_adapter, _payload(), "2026-08-20",
                  alert=lambda _: None)
    assert fake.trades() == []                # nothing reached the venue
    assert m.state.pending_book_orders == {}
    # gateway restart completes: the next cycle reconnects and proceeds
    fake.connect_fails = False
    ib_adapter._next_reconnect_ts = 0.0
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    assert fake.isConnected()
    assert len(fake.trades()) == 1            # the idle-cash sweep went out


# m1 (escalated): a venue-REJECTED journaled order must release its slot
# and surface loudly — never sit pending forever.

def test_gate_m1min_rejected_entry_releases_slot_and_logs(tmp_path,
                                                          ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    assert "1" in m.state.pending_entries
    moo = fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"])
    moo.orderStatus.status = "Inactive"       # venue rejects overnight
    alerts: list[str] = []
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=alerts.append)
    assert m.state.pending_entries == {}      # max_open slot RELEASED
    assert "1" not in m.state.positions
    assert any("REJECTED" in msg for msg in alerts)
    rows = [t for t in m.state.trades if t["kind"] == "entry_rejected"]
    assert len(rows) == 1 and rows[0]["symbol"] == "CRSP"
    # the same fire republished retries cleanly (venue dedupe excludes the
    # rejected prior)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-21", alert=lambda _: None)
    assert "1" in m.state.pending_entries
    moos = [t for t in fake.trades() if t.order.tif == "OPG"]
    assert len(moos) == 2                     # a fresh retry order


def test_gate_m1min_rejected_book_order_cleared_and_replanned(tmp_path,
                                                              ib_adapter):
    fake = ib_adapter.ib
    m = _mgr(tmp_path)                        # idle sleeve cash -> sweep 30
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    (cid,) = list(m.state.pending_book_orders)
    t = fake.trade_by_ref(ib_adapter.find_stock_order(cid)["order_ref"])
    t.orderStatus.status = "Inactive"         # venue rejects the sweep
    alerts: list[str] = []
    run_cycle(m, ib_adapter, _payload(), "2026-08-21", alert=alerts.append)
    assert cid not in m.state.pending_book_orders
    assert any("REJECTED" in msg for msg in alerts)
    # replanned as a FRESH intent (new cid), exactly one live venue order
    pend = list(m.state.pending_book_orders)
    assert len(pend) == 1 and pend[0] != cid
    live = [t for t in fake.trades()
            if t.orderStatus.status not in ("Inactive", "Cancelled",
                                            "ApiCancelled", "Filled")]
    assert len(live) == 1


# --- ValidationError wedge (live find 2026-08-25) ---------------------------
class _LogEntry:
    def __init__(self, code, message):
        self.errorCode = code
        self.message = message


def _validation_reject_ib(ib):
    """Venue that refuses every placement at validation, with a reason in
    the trade log - what the gateway did to the book's first-ever orders."""
    def on_place(trade):
        trade.orderStatus.status = "ValidationError"
        trade.log = [_LogEntry(0, "submitted"),
                     _LogEntry(10331, "order validation failed: precautionary "
                                      "constraint (simulated)")]
    ib.on_place = on_place


def test_gate_validation_error_is_terminal_and_names_the_reason(ib_adapter):
    """Pre-fix: 'ValidationError' fell through _map_status to 'working', so
    the placement spun the full ack timeout and raised 'state UNKNOWN' with
    IB's actual reason discarded in trade.log."""
    import pytest as _pytest
    import time as _time
    _validation_reject_ib(ib_adapter.ib)
    t0 = _time.monotonic()
    with _pytest.raises(RuntimeError) as e:
        ib_adapter.place_stock_order("SPY", 10, "MKT",
                                     client_order_id="blend-CORE_BUY-x-0")
    took = _time.monotonic() - t0
    assert "rejected by venue" in str(e.value)
    assert "10331" in str(e.value), "IB's reason must reach the alert"
    assert took < 2.0, f"spun the ack timeout instead of failing fast ({took:.1f}s)"


def test_gate_validation_error_never_suppresses_the_retry(ib_adapter):
    """THE WEDGE: the dead order mapped 'working', so orderRef dedupe
    returned it as a duplicate and the idempotent retry never re-placed -
    while the journal kept pending_book true, blocking CORE_BUY/sweep/
    rebalance forever, silently."""
    import pytest as _pytest
    _validation_reject_ib(ib_adapter.ib)
    with _pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("SPY", 10, "MKT",
                                     client_order_id="blend-CORE_BUY-x-1")
    # venue heals (whatever blocked validation is gone): retry must PLACE
    ib_adapter.ib.on_place = None
    out = ib_adapter.place_stock_order("SPY", 10, "MKT",
                                       client_order_id="blend-CORE_BUY-x-1")
    assert not out.get("duplicate"), "retry was duplicate-suppressed by a dead order"
    assert out["status"] in ("filled", "working")


def test_gate_dead_journaled_book_order_unwedges_via_find(ib_adapter):
    """find_stock_order must report the dead order as 'cancelled' so the
    journal's existing rejection branch clears it and step() re-plans."""
    _validation_reject_ib(ib_adapter.ib)
    import pytest as _pytest
    with _pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("BIL", 32, "MKT",
                                     client_order_id="blend-SWEEP-x-2")
    o = ib_adapter.find_stock_order("blend-SWEEP-x-2")
    assert o is not None and o["status"] == "cancelled", o


def test_gate_unknown_status_still_conservative(ib_adapter):
    """A genuinely unknown transitional status must keep mapping 'working'
    (never re-place on ambiguity) - only known-terminal states are dead."""
    import app.ib_adapter as m
    assert m._map_status("SomeFutureTransitionalState") == "working"
    assert m._map_status("ValidationError") == "cancelled"
