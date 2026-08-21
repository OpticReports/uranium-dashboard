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


class FakeIB:
    """Scriptable stand-in for ib_async.IB: on_place/on_cancel/on_sleep hooks
    let tests act as the venue (fills, rejects, silent timeouts)."""

    def __init__(self):
        self._trades: list[FakeTrade] = []
        self._next_id = 1
        self.connected = False
        self.prices: dict[str, float] = {}
        self.on_place = None
        self.on_cancel = None
        self.on_sleep = None

    # connection
    def connect(self, host, port, clientId, timeout=15):
        self.connected = True

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

    def auto_fill_mkt(self, price_of=None):
        """Fill DAY market orders synchronously at prices[symbol] (the
        DryAdapter-like convenience for tests that need a tidy book)."""
        def _hook(trade):
            if trade.order.orderType == "MKT" and trade.order.tif == "DAY":
                px = (price_of or self.prices.get)(trade.contract.symbol)
                self.fill(trade, [(trade.order.totalQuantity, px)])
        self.on_place = _hook


class _Cfg:
    trading_mode = "paper"
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
    fake.auto_fill_mkt()                     # book orders (sweep) fill tidily
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
    # the venue fills at the open (at a price != entry_ref)
    fake.fill(moo, [(5, 50.3)])
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
    fake.auto_fill_mkt()
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
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
    fake.auto_fill_mkt()
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
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
    fake.auto_fill_mkt()
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    fake.on_place = None                     # MKT no longer fills in-window
    cash_before = m.state.sleeve_cash
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
    fake.auto_fill_mkt()
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(entries=[ENTRY], stops=[STOP]),
              "2026-08-20", alert=lambda _: None)
    fake.fill(fake.trade_by_ref(
        ib_adapter.find_stock_order("blend-1-entry")["order_ref"]),
        [(5, 50.0)])
    run_cycle(m, ib_adapter, _payload(stops=[STOP]), "2026-08-21",
              alert=lambda _: None)
    fake.prices["CRSP"] = 47.5
    total_before = m.state.sleeve_cash + m.state.bil_qty * 100.0
    run_cycle(m, ib_adapter,
              _payload(exits=[{"symbol": "CRSP", "call_id": 1,
                               "reason": "trail", "trail_level": 47.0}]),
              "2026-08-22", alert=lambda _: None)
    assert "1" not in m.state.positions and not m.state.unreconciled
    total_after = m.state.sleeve_cash + m.state.bil_qty * 100.0
    assert total_after - total_before == pytest.approx(5 * 47.5)
