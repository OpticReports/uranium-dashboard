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

import asyncio
from decimal import Decimal
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
    def __init__(self, execution, commission=None):
        self.execution = execution
        self.commissionReport = (types.SimpleNamespace(commission=commission,
                                                       execId="ex-1",
                                                       currency="USD")
                                 if commission is not None else None)


class FakeTrade:
    def __init__(self, contract, order):
        self.contract = contract
        self.order = order
        self.orderStatus = FakeStatus()
        self.fills = []
        self.log = []
        self.advancedError = ""


class FakeEvent:
    """ib_async Event stand-in: `ev += handler`, `ev.emit(*args)`."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, h):
        self.handlers.append(h)
        return self

    def emit(self, *a):
        for h in list(self.handlers):
            h(*a)


class FakeTicker:
    """B8: a ticker now has the fields the adapter actually reads. The
    defaults keep every pre-existing test byte-identical (marketPrice
    returns the quoted price and nothing else is consulted)."""

    def __init__(self, px, close=None, last=None, market_data_type=1,
                 arrives_after=0):
        self._px = px
        self.close = close
        self.last = last
        self.marketDataType = market_data_type
        self._arrives_after = arrives_after   # ticks of nan before px lands
        self.market_price_calls = 0

    def marketPrice(self):
        self.market_price_calls += 1
        if self.market_price_calls <= self._arrives_after:
            return float("nan")
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
        self.account_rows: list = []      # accountSummary() rows
        self.on_place = None
        self.on_cancel = None
        self.on_sleep = None
        self.errorEvent = FakeEvent()
        self.connect_calls = 0
        self.connect_fails = False        # M5: gateway down (restart window)
        self.tickers: dict[str, FakeTicker] = {}   # B8: explicit override
        self.market_data_types: list[int] = []     # B8: reqMarketDataType log
        self.md_events: list[tuple] = []           # ordered type/sub/cancel log

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

    def reqMarketDataType(self, data_type):
        self.market_data_types.append(data_type)
        self.md_events.append(("type", data_type))

    def reqMktData(self, contract, generic, snapshot, regulatory):
        self.md_events.append(("sub", contract.symbol))
        t = self.tickers.get(contract.symbol)
        if t is not None:
            return t
        return FakeTicker(self.prices.get(contract.symbol, float("nan")))

    def cancelMktData(self, contract):
        self.md_events.append(("cancel", contract.symbol))

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

    def accountSummary(self):
        return list(self.account_rows)

    def accountValues(self):
        return list(self.account_rows)

    def managedAccounts(self):
        return list(getattr(self, "managed", []))

    # venue-side test helpers
    def fill(self, trade, parts, commission=None):
        """parts: [(shares, price), ...] -> executions + Filled status.
        commission (total) is attached to the first execution's report."""
        side = "BOT" if trade.order.action == "BUY" else "SLD"
        for k, (shares, price) in enumerate(parts):
            trade.fills.append(FakeFill(FakeExec(shares, price, side),
                                        commission if k == 0 else None))
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
    # B8: the quote wait is a real bounded wait now, not a fixed sleep(3);
    # FakeIB.sleep never actually sleeps, so shorten the bound the same way
    # every other bounded wait above is shortened.
    # raising=False so this same fixture still boots against a tree that
    # predates the constants — that is how the B8 gates are verified FAILING
    # on their own assertions rather than on a missing attribute.
    monkeypatch.setattr(ib_mod, "QUOTE_WAIT_S", 0.3, raising=False)
    monkeypatch.setattr(ib_mod, "QUOTE_TICK_S", 0.0, raising=False)
    monkeypatch.setattr(ib_mod, "COMMISSION_WAIT_S", 0.05)
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


# --- round 20 (2026-09-11): the venue's price increment ----------------------
# THE live blocker. GH x6 filled at 159.24 and the first protective stop this
# book ever sent live carried the tracker's four-decimal trail level,
# 137.0507. IBKR refuses a price off the increment grid (error 110, "does not
# conform to the minimum price variation") — three attempts, all Cancelled,
# the position naked and every new entry blocked. MUTATION-VERIFIED (see
# docs/verdicts/INDEX.md, round 20): dropping the snap, rounding to NEAREST
# instead of away from the trigger, using cents below $1, and dropping the
# reported `stop_price` each turn a gate below red.

def test_gate_r20_a_sub_tick_stop_reaches_the_venue_on_the_grid(ib_adapter):
    """The GH case, end to end: the price that reaches `placeOrder` is one
    the venue can hold, and the caller is told which price that is."""
    r = ib_adapter.place_stock_order("GH", -6, "STP", stop_price=137.0507,
                                     tif="GTC",
                                     client_order_id="blend-18-stp-137.0507")
    (t,) = ib_adapter.ib.trades()
    assert t.order.auxPrice == 137.05, t.order.auxPrice
    assert Decimal(str(t.order.auxPrice)) % Decimal("0.01") == 0
    assert r["stop_price"] == 137.05, r
    assert t.order.orderType == "STP" and t.order.tif == "GTC"


def test_gate_r20_rounding_never_tightens_a_protective_stop():
    """Direction is not cosmetic: a SELL stop protects a long, so it rounds
    DOWN (trigger later, risk per share never silently reduced below the
    pre-registered `entry_ref - trail`); a BUY stop covering a short rounds
    UP for the same reason. Nearest-rounding would tighten half of all
    stops."""
    from app.ib_adapter import round_stop_to_tick as snap

    assert snap(137.0507, "SELL") == 137.05
    assert snap(137.0507, "BUY") == 137.06
    assert snap(137.0593, "SELL") == 137.05      # nearest would say 137.06
    assert snap(137.0507, "sell") == 137.05      # case-insensitive
    assert snap(44.0, "SELL") == 44.0 and snap(44.0, "BUY") == 44.0


def test_gate_r20_sub_dollar_stocks_use_the_finer_increment():
    """Below $1 the venue quotes in $0.0001 (SEC Rule 612). Snapping those
    to a cent would move a stop by up to 1% of the price - on the penny
    names this sleeve actually holds."""
    from app.ib_adapter import round_stop_to_tick as snap, stock_tick

    assert snap(0.87654, "SELL") == 0.8765
    assert snap(0.87651, "BUY") == 0.8766
    assert snap(0.9999, "SELL") == 0.9999
    assert snap(1.0007, "SELL") == 1.0          # at $1 the grid is cents
    assert stock_tick(Decimal("0.999")) == Decimal("0.0001")
    assert stock_tick(Decimal("1")) == Decimal("0.01")


def test_gate_r20_a_stop_that_cannot_exist_fails_closed():
    """A price that rounds off the board is not a stop. Fail closed (the
    caller's STOP_MISSING path alerts and blocks entries) rather than send
    0.00 - which the venue would either reject or, worse, hold."""
    import pytest
    from app.ib_adapter import round_stop_to_tick as snap

    for bad in (0.0, -1.0, 0.00004):
        with pytest.raises(ValueError):
            snap(bad, "SELL")
    with pytest.raises(ValueError):
        snap(float("nan"), "SELL")


def test_gate_r20_the_dry_adapter_rests_a_price_the_venue_could_hold():
    """The paper double must snap exactly as the live adapter does: a dry
    run that rests 137.0507 is the simulation lying about the one order
    that protects the book - which is how this shipped."""
    from app.ib_adapter import DryAdapter

    a = DryAdapter()
    r = a.place_stock_order("GH", -6, "STP", stop_price=137.0507, tif="GTC",
                            client_order_id="blend-18-stp-137.0507")
    assert r["stop_price"] == 137.05
    assert a._stops[r["order_ref"]]["stop_price"] == 137.05


def test_gate_r20b_huge_price_fails_closed():
    """ROUNDING-5: past Decimal's 28-digit context the quantize itself
    raises InvalidOperation, which is not the ValueError every caller
    catches - it would escape the stop path as an unhandled exception."""
    from app.ib_adapter import round_stop_to_tick

    with pytest.raises(ValueError):
        round_stop_to_tick(1e26, "SELL")


def test_gate_r20b_the_buy_side_is_wired_to_the_other_rounding(ib_adapter):
    """TESTS-4: both adapter gates placed a SELL, so the line that picks the
    direction (`action = "BUY" if qty > 0 else "SELL"`) was untested on one
    side in each adapter. A buy stop covering a short must round UP."""
    from app.ib_adapter import DryAdapter

    r = ib_adapter.place_stock_order("GH", +6, "STP", stop_price=137.0507,
                                     tif="GTC", client_order_id="buy-stp-1")
    (t,) = ib_adapter.ib.trades()
    assert t.order.action == "BUY" and t.order.auxPrice == 137.06
    assert r["stop_price"] == 137.06

    d = DryAdapter()
    rd = d.place_stock_order("GH", +6, "STP", stop_price=137.0507, tif="GTC",
                             client_order_id="buy-stp-2")
    assert rd["stop_price"] == 137.06
    assert d._stops[rd["order_ref"]]["stop_price"] == 137.06


def test_gate_r20b_a_duplicate_reports_the_price_the_prior_order_holds(ib_adapter):
    """TESTS-6 / ROUNDING-3: the duplicate-suppressed early return is the
    path a retry, a crash recovery and a deploy all take. It used to omit
    `stop_price` entirely, so a caller reading it back learned the price it
    had ASKED for rather than the one resting."""
    from app.ib_adapter import DryAdapter

    cid = "blend-9-stp-137.0507"
    first = ib_adapter.place_stock_order("GH", -6, "STP", stop_price=137.0507,
                                         tif="GTC", client_order_id=cid)
    again = ib_adapter.place_stock_order("GH", -6, "STP", stop_price=137.0507,
                                         tif="GTC", client_order_id=cid)
    assert again.get("duplicate") and again["order_ref"] == first["order_ref"]
    assert again["stop_price"] == 137.05, again

    d = DryAdapter()
    f2 = d.place_stock_order("GH", -6, "STP", stop_price=137.0507, tif="GTC",
                             client_order_id=cid)
    a2 = d.place_stock_order("GH", -6, "STP", stop_price=137.0507, tif="GTC",
                             client_order_id=cid)
    assert a2.get("duplicate") and a2["order_ref"] == f2["order_ref"]
    assert a2["stop_price"] == 137.05, a2


def test_gate_r20b_a_rejection_code_is_reported_not_suppressed(ib_adapter):
    """CAUSE-3: 110 — the code that refused all three GH stops — sat in the
    warning-suppression set, so the operator was told "no venue reason
    recorded" and the cause had to be inferred. A code that KILLS an order
    is the reason it died."""
    fake = ib_adapter.ib

    def reject(t):
        t.orderStatus.status = "Cancelled"
        t.log = [types.SimpleNamespace(
            errorCode=110, status="Cancelled",
            message="The price does not conform to the minimum price "
                    "variation for this contract.")]
    fake.on_place = reject
    with pytest.raises(RuntimeError, match=r"110"):
        ib_adapter.place_stock_order("GH", -6, "STP", stop_price=137.05,
                                     tif="GTC", client_order_id="r110")
    assert "110" in ib_adapter.find_stock_order("r110")["reason"]


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


def test_gate_r19_a_cancelled_trade_reports_its_executions(tmp_path, ib_adapter):
    """CASH-3 (round 19): a cancelled order can carry a partial fill. The
    adapter must surface it (filled_qty) so blend's cancelled branch does
    not treat 'cancelled' as 'nothing happened' and re-hold the full cost."""
    fake = ib_adapter.ib
    m = _mgr(tmp_path)
    run_cycle(m, ib_adapter, _payload(), "2026-08-20", alert=lambda _: None)
    (cid,) = list(m.state.pending_book_orders)
    t = fake.trade_by_ref(ib_adapter.find_stock_order(cid)["order_ref"])
    t.orderStatus.status = "Cancelled"
    t.orderStatus.filled = 2
    o = ib_adapter.find_stock_order(cid)
    assert o["status"] == "cancelled" and o["filled_qty"] == 2, o
    t.orderStatus.filled = 0
    assert "filled_qty" not in ib_adapter.find_stock_order(cid)


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


# --- corrective round: B1 (the session boundary) and B8 (the quote) ----------


class _VenueIB(FakeIB):
    """A venue that OUTLIVES the process.

    `self.ib.trades()` is what ib_async gives a freshly connected client:
    the orders THIS session placed, and nothing else. `reqAllOpenOrders` /
    `reqCompletedOrders` are how a new session learns about orders placed by
    a previous one — which is exactly what a Render deploy, an OOM restart
    or a gateway reconnect creates. `venue` is shared across "restarts"."""

    def __init__(self, venue: list, next_id: int = 1):
        super().__init__()
        self.venue = venue
        self._next_id = next_id
        self.open_order_calls = 0

    def placeOrder(self, contract, order):
        t = super().placeOrder(contract, order)
        self.venue.append(t)
        return t

    def reqAllOpenOrders(self):
        self.open_order_calls += 1
        return [t for t in self.venue
                if t.orderStatus.status in ("Submitted", "PreSubmitted")]

    def reqCompletedOrders(self, apiOnly=True):
        return [t for t in self.venue if t.orderStatus.status == "Filled"]


def _restart(adapter, venue, monkeypatch):
    """Hand the adapter a BRAND NEW client session over the same venue —
    the process boundary, modelled at the one place it actually bites."""
    fresh = _VenueIB(venue, next_id=1_000)
    fresh.connected = True
    fresh.prices = dict(adapter.ib.prices)
    monkeypatch.setattr(adapter, "ib", fresh)
    return fresh


@pytest.fixture
def venue_adapter(ib_adapter, monkeypatch):
    venue: list = []
    fake = _VenueIB(venue)
    fake.connected = True
    fake.prices = {"SPY": 100.0, "BIL": 100.0, "CRSP": 50.0}
    monkeypatch.setattr(ib_adapter, "ib", fake)
    ib_adapter._venue = venue
    return ib_adapter


def test_gate_b1_a_filled_order_still_dedupes_after_a_session_boundary(
        venue_adapter, monkeypatch):
    """B1 / regression R-a — the naked-short path, and the reason this
    branch may not merge as it stood.

    `place_stock_order` resolved its idempotency key with
    `_find_trade_by_client_id(cid)`, whose default `refresh=False` reads
    `self.ib.trades()` — THIS SESSION ONLY. A restart empties that list, so
    a retry under the same deterministic client id saw NO prior and placed
    the order AGAIN. Both halves of the stated no-double-sell law fail
    together at a session boundary: reconcile-first cannot help either,
    because the book it reconciles was destroyed by the very same restart
    (B2).

    The bug is INVISIBLE inside one session, so the gate crosses one."""
    venue = venue_adapter._venue
    first = venue_adapter.place_stock_order(
        "CRSP", -5, "MKT", client_order_id="blend-1-kill")
    venue_adapter.ib.fill(venue[0], [(5, 49.5)])
    assert first["order_ref"] == str(venue[0].order.orderId)
    assert len(venue) == 1

    _restart(venue_adapter, venue, monkeypatch)
    assert venue_adapter.ib.trades() == []          # a new session, truly

    again = venue_adapter.place_stock_order(
        "CRSP", -5, "MKT", client_order_id="blend-1-kill")
    assert again.get("duplicate") is True, again
    assert again["status"] == "filled"
    assert again["fill_price"] == pytest.approx(49.5)
    assert again["order_ref"] == first["order_ref"]
    # THE assertion: the venue never saw a second sell. At cc03347 this list
    # had two SELL orders -> CRSP -10 against a 5-share book position.
    assert len(venue) == 1, [t.order.action for t in venue]
    assert venue_adapter.ib.open_order_calls >= 1   # it ASKED the venue


def test_gate_b1_a_working_order_still_dedupes_after_a_session_boundary(
        venue_adapter, monkeypatch):
    """The same boundary, with the prior order still WORKING rather than
    filled — a resting MKT/MOO the restart interrupted."""
    venue = venue_adapter._venue
    first = venue_adapter.place_stock_order(
        "CRSP", -5, "MOO", tif="OPG", client_order_id="blend-2-kill")
    assert first["status"] == "working"
    _restart(venue_adapter, venue, monkeypatch)
    again = venue_adapter.place_stock_order(
        "CRSP", -5, "MOO", tif="OPG", client_order_id="blend-2-kill")
    assert again.get("duplicate") is True
    assert again["status"] == "working"
    assert len(venue) == 1


def test_gate_b1_a_cancelled_prior_still_re_places_after_a_restart(
        venue_adapter, monkeypatch):
    """CONTROL (passes before and after — it guards against OVER-fixing
    B1): the venue lookup must not turn the adapter into a
    one-shot. A CANCELLED order under the key never binds — before or after
    a restart — so a legitimate re-placement still reaches the venue."""
    venue = venue_adapter._venue
    venue_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0,
                                    client_order_id="blend-3-stp")
    venue[0].orderStatus.status = "Cancelled"
    _restart(venue_adapter, venue, monkeypatch)
    r = venue_adapter.place_stock_order("CRSP", -5, "STP", stop_price=43.0,
                                        client_order_id="blend-3-stp")
    assert r.get("duplicate") is not True
    assert len(venue) == 2


def test_gate_b1_a_different_client_id_still_places_after_a_restart(
        venue_adapter, monkeypatch):
    """CONTROL #2 (passes before and after): the venue lookup matches on orderRef, so an
    unrelated key is never suppressed by somebody else's order."""
    venue = venue_adapter._venue
    venue_adapter.place_stock_order("CRSP", -5, "MKT",
                                    client_order_id="blend-1-kill")
    venue_adapter.ib.fill(venue[0], [(5, 49.5)])
    _restart(venue_adapter, venue, monkeypatch)
    r = venue_adapter.place_stock_order("CRSP", -3, "MKT",
                                        client_order_id="blend-9-kill")
    assert r.get("duplicate") is not True
    assert len(venue) == 2


def test_gate_b1_the_flatten_retry_across_a_restart_sells_exactly_once(
        tmp_path, venue_adapter, monkeypatch):
    """B1 end to end, in the shape that actually reaches the account.

    MF3-3 made a flatten that closed nothing RETRY every cycle. Combined
    with B2 (the blend book sat on the ephemeral layer, so every deploy
    re-seeded it) the retry routinely lands in a NEW process. Here: pass 1
    fails at the venue and parks; the process restarts; pass 2 re-issues the
    same `blend-1-kill` client id. Exactly ONE sell may ever exist, and the
    book must end FLAT rather than short."""
    from app.blend import execute_flatten

    venue = venue_adapter._venue
    m = _mgr(tmp_path)
    m.on_entered({"call_id": 1, "symbol": "CRSP", "qty": 5,
                  "entry_ref": 50.0, "stop_level": 44.0}, 50.0,
                 "entry-ref", "2026-08-01")
    # ...and the ACCOUNT holds them, which is what the flatten's venue
    # ceiling (L1-L5) reads. Modelling it is the point of this gate: by
    # pass 2 the lost-ack sell HAS filled and the account is FLAT, so a
    # retry sized from the book alone is the naked short this test names.
    venue_adapter.ib.position_rows = [FakePosition("CRSP", 5)]
    m.request_flatten("2026-08-21")

    # pass 1: the sell reaches the venue, then the ACK never comes back —
    # the adapter raises ("state UNKNOWN; retry is idempotent via orderRef"),
    # the position parks, and the request stays queued.
    venue_adapter.ib.on_place = lambda t: setattr(t.orderStatus, "status",
                                                  "PendingSubmit")
    monkeypatch.setattr(ib_mod, "PLACE_ACK_TIMEOUT_S", 0.0)
    a1: list[str] = []
    execute_flatten(m, venue_adapter, a1.append)
    assert "1" in m.state.positions, "the parked position was booked out"
    assert m.state.flatten_request is not None
    assert len(venue) == 1, "pass 1 should have reached the venue once"

    # the venue fills it anyway — the ack was lost, the ORDER was not.
    venue_adapter.ib.on_place = None
    venue_adapter.ib.fill(venue[0], [(5, 49.0)])
    venue_adapter.ib.position_rows = []          # the account is now FLAT
    # ...and the process restarts before the next cycle (a deploy).
    _restart(venue_adapter, venue, monkeypatch)
    monkeypatch.setattr(ib_mod, "PLACE_ACK_TIMEOUT_S", 0.2)

    a2: list[str] = []
    execute_flatten(m, venue_adapter, a2.append)
    sells = [t for t in venue if t.order.action == "SELL"]
    assert len(sells) == 1, [t.order.action for t in venue]
    assert "1" not in m.state.positions          # booked out at 49.0
    assert m.state.flatten_request is None
    assert m.state.halted == "KILL"
    assert any("flatten complete" in msg for msg in a2), a2


def test_gate_b8_spot_asks_for_a_market_data_type_before_subscribing(
        ib_adapter):
    """B8: without `reqMarketDataType` the gateway rejects an unentitled
    request (error 354) and the ticker never gets a field — reported as
    "no market price", the SAME line a thin quote produces. The book would
    simply never trade, with no distinguishing symptom."""
    # MERGE NOTE (2026-09-10): the branch's B8 requested one fixed type
    # (delayed-frozen, 4) per spot() call. main's market-data work
    # supersedes that: the CONFIGURED type is applied at connect (and
    # re-applied on reconnect — tests/test_market_data.py pins both) and
    # again per spot() call, and spot_ex escalates to DELAYED (3) only when
    # the configured feed is dry and IB_ALLOW_DELAYED permits it. The
    # guarantee this gate exists for is ORDER: a type request precedes the
    # first subscription of THIS call. The connect-time request is cleared
    # first so it cannot satisfy the assertion on the call's behalf
    # (merge review F4/T2: the earlier form was satisfiable by connect()
    # alone, with spot() requesting nothing).
    ib_adapter.ib.md_events.clear()
    ib_adapter.ib.market_data_types.clear()
    assert ib_adapter.spot("SPY") == pytest.approx(100.0)
    kinds = [k for k, _ in ib_adapter.ib.md_events]
    assert "sub" in kinds, "spot() never subscribed"
    assert "type" in kinds[:kinds.index("sub")], (
        f"no reqMarketDataType before the first reqMktData: "
        f"{ib_adapter.ib.md_events}")
    assert all(t in (1, 2, 3, 4) for t in ib_adapter.ib.market_data_types)


def test_gate_b8_spot_falls_back_to_the_previous_close(ib_adapter):
    """B8: `Ticker.marketPrice()` returns last-or-midpoint and has NO close
    fallback - in ANY ib_async release: the 1.0.1 and 2.1.0 sources are
    byte-identical here, and the fallback this code assumed was
    ib_insync's, before the fork (verified at the 2026-09-10 merge review).
    Outside RTH that is nan forever. The close is read explicitly now."""
    ib_adapter.ib.tickers["CRSP"] = FakeTicker(float("nan"), close=48.25)
    assert ib_adapter.spot("CRSP") == pytest.approx(48.25)


def test_gate_b8_spot_prefers_a_live_tick_over_the_close(ib_adapter):
    """CONTROL (passes before and after): the close is a FALLBACK, never a
    substitute for a live tick — the fix must not start marking the book at
    yesterday's close while a real quote is on the wire."""
    ib_adapter.ib.tickers["CRSP"] = FakeTicker(50.5, close=48.25)
    assert ib_adapter.spot("CRSP") == pytest.approx(50.5)


def test_gate_b8_spot_waits_for_a_late_tick_instead_of_a_fixed_sleep(
        ib_adapter):
    """B8: the fixed `sleep(3)` was a guess in both directions — it burned
    3s on a quote that had already arrived and gave up on one that had not.
    A tick that lands on the fourth poll must be picked up."""
    ib_adapter.ib.tickers["CRSP"] = FakeTicker(51.0, arrives_after=3)
    assert ib_adapter.spot("CRSP") == pytest.approx(51.0)
    assert ib_adapter.ib.tickers["CRSP"].market_price_calls >= 4


def test_gate_b8_no_quote_at_all_names_the_missing_subscription(ib_adapter):
    """B8: the two failures must be DISTINGUISHABLE. A quote that is merely
    thin still carries a close; nothing at all is an entitlement problem,
    and the operator is told which one this is."""
    ib_adapter.ib.tickers["ZZZZ"] = FakeTicker(float("nan"))
    with pytest.raises(RuntimeError) as exc:
        ib_adapter.spot("ZZZZ")
    msg = str(exc.value)
    assert "MISSING MARKET-DATA SUBSCRIPTION" in msg
    assert "NO PREVIOUS CLOSE" in msg


def test_gate_b8_spot_retires_its_subscription_on_the_failure_path(
        ib_adapter):
    """CONTROL (passes before and after): the old body already cancelled
    before it raised on a bad price, and the rewrite must not lose that. It
    now also holds when the WAIT itself raises, which the old straight-line
    body did not — pinned here so a later edit cannot leak a subscription
    per failed quote."""
    ib_adapter.ib.md_events.clear()
    ib_adapter.ib.tickers["ZZZZ"] = FakeTicker(float("nan"))
    with pytest.raises(RuntimeError):
        ib_adapter.spot("ZZZZ")
    # MERGE NOTE (2026-09-10): main's spot_ex makes up to TWO attempts on a
    # dry configured feed (configured type, then DELAYED), each with its own
    # subscription — so "exactly one cancel" was the branch's single-attempt
    # shape, not the invariant. The invariant is: every subscription is
    # retired BEFORE the next is opened and none is retired twice — strict
    # sub/cancel alternation (merge review T3: an equal-multiset check
    # would have passed two subscribes followed by two cancels).
    subs = [e for e in ib_adapter.ib.md_events if e[0] in ("sub", "cancel")]
    assert subs and len(subs) % 2 == 0, subs
    for i in range(0, len(subs), 2):
        assert subs[i][0] == "sub" and subs[i + 1] == ("cancel", subs[i][1]), subs


# --- ValidationError semantics (live find 2026-08-25; corrected same day) ---
# ib_async sets 'ValidationError' CLIENT-SIDE for warning-class error codes
# on an order that is STILL LIVE at the broker (ActiveStates/WorkingStates,
# not DoneStates). The first fix treated it as terminal - counter-agent
# FATAL: dedupe re-placed live orders (180 SPY where the book meant 90) and
# journals cleared working orders whose fills nothing would book. These
# gates encode the CORRECT model.
class _LogEntry:
    def __init__(self, code, message):
        self.errorCode = code
        self.message = message


def _warned_live_ib(ib, code=321, msg="Error validating request: the API "
                                      "interface is currently in Read-Only "
                                      "mode."):
    """Order gets a warning-class error: status ValidationError, order LIVE."""
    def on_place(trade):
        trade.orderStatus.status = "ValidationError"
        trade.log = [_LogEntry(0, "submitted"), _LogEntry(code, msg)]
    ib.on_place = on_place


def test_gate_warned_order_raises_unknown_with_the_reason(ib_adapter):
    """A warned order is neither acked nor dead: the placement must raise
    the UNKNOWN-timeout path (never 'rejected by venue') and carry IB's own
    words so the alert names the cause."""
    import pytest as _pytest
    _warned_live_ib(ib_adapter.ib)
    with _pytest.raises(RuntimeError) as e:
        ib_adapter.place_stock_order("SPY", 10, "MKT",
                                     client_order_id="blend-core-buy-t-0")
    msg = str(e.value)
    assert "state UNKNOWN" in msg
    assert "rejected by venue" not in msg
    assert "321" in msg, "IB's reason must reach the alert"


def test_gate_warned_order_retry_is_duplicate_suppressed(ib_adapter):
    """THE FATAL INVERSION, pinned the right way round: the order may be
    LIVE, so the idempotent retry must be duplicate-suppressed - re-placing
    is the 180-SPY-instead-of-90 route."""
    import pytest as _pytest
    _warned_live_ib(ib_adapter.ib)
    with _pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("SPY", 10, "MKT",
                                     client_order_id="blend-core-buy-t-1")
    ib_adapter.ib.on_place = None
    out = ib_adapter.place_stock_order("SPY", 10, "MKT",
                                       client_order_id="blend-core-buy-t-1")
    assert out.get("duplicate") is True, "re-placed against a possibly-live order"
    placed = [t for t in ib_adapter.ib._trades
              if getattr(t.order, "orderRef", "") == "blend-core-buy-t-1"]
    assert len(placed) == 1, f"venue holds {len(placed)} orders for one intent"


def test_gate_warned_order_reports_working_not_cancelled(ib_adapter):
    """find_stock_order must report 'working' so the journal KEEPS the
    entry; the unwedge is pass 2b's cancel-confirmation, never an assumed
    death."""
    import pytest as _pytest
    _warned_live_ib(ib_adapter.ib)
    with _pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("BIL", 32, "MKT",
                                     client_order_id="blend-sweep-t-2")
    o = ib_adapter.find_stock_order("blend-sweep-t-2")
    assert o is not None and o["status"] == "working", o


def test_gate_warned_order_cancel_actually_sends_the_cancel(ib_adapter):
    """PROBE B's first half: cancel_stock_order on a warned order used to
    return False WITHOUT sending cancelOrder, leaving a live stop resting
    while the caller believed it gone (double-stop route)."""
    import pytest as _pytest
    _warned_live_ib(ib_adapter.ib)
    with _pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("SPY", -10, "STP", stop_price=90.0,
                                     client_order_id="blend-stop-t-3")
    cancels = []
    orig_cancel = ib_adapter.ib.cancelOrder
    ib_adapter.ib.on_cancel = None
    def counting_cancel(order):
        cancels.append(order)
        orig_cancel(order)
    ib_adapter.ib.cancelOrder = counting_cancel
    # cancel takes the adapter's orderId handle (what _trade_result returns),
    # not the client id
    trade = ib_adapter._find_trade_by_client_id("blend-stop-t-3")
    ok = ib_adapter.cancel_stock_order(str(trade.order.orderId))
    assert cancels, "cancelOrder was never sent for a possibly-live order"
    assert ok is True


def test_gate_hard_reject_still_fast_with_reason(ib_adapter):
    """A REAL rejection (status Cancelled) fails fast and names the code."""
    import pytest as _pytest
    import time as _time
    def on_place(trade):
        trade.orderStatus.status = "Cancelled"
        trade.log = [_LogEntry(201, "Order rejected - reason: simulated")]
    ib_adapter.ib.on_place = on_place
    t0 = _time.monotonic()
    with _pytest.raises(RuntimeError) as e:
        ib_adapter.place_stock_order("SPY", 10, "MKT",
                                     client_order_id="blend-core-buy-t-4")
    assert "rejected by venue" in str(e.value) and "201" in str(e.value)
    assert _time.monotonic() - t0 < 2.0


def test_gate_status_mapping_matches_ib_async_semantics(ib_adapter):
    import app.ib_adapter as m
    assert m._map_status("ValidationError") == "working"   # LIVE per ib_async
    assert m._map_status("Cancelled") == "cancelled"
    assert m._map_status("SomeFutureTransitionalState") == "working"


def test_rejection_reason_surfaces_without_error_code(ib_adapter):
    """An opening-auction order refused after the bell is cancelled with a
    plain 'Order Canceled - reason: ...' log line and NO errorCode. Both the
    synchronous raise and the reconcile-path lookup must carry it; before
    this the five 2026-09-03 MRK rejections said only 'status Cancelled'.
    MUTATION-VERIFIED: reverting the `dead` fallback in _trade_errors, or
    the `reason` key in _trade_result, turns this red."""
    fake = ib_adapter.ib

    def reject(t):
        t.orderStatus.status = "Cancelled"
        t.log = [types.SimpleNamespace(
            errorCode=0, status="Cancelled",
            message="Order Canceled - reason: OPG order received after the open")]

    fake.on_place = reject
    with pytest.raises(RuntimeError, match="received after the open"):
        ib_adapter.place_stock_order("MRK", 4, "MOO", tif="OPG",
                                     client_order_id="blend-entry-16")
    o = ib_adapter.find_stock_order("blend-entry-16")
    assert o["status"] == "cancelled"
    assert "received after the open" in o["reason"]


def _acct(tag, value, currency="USD", account=""):
    return types.SimpleNamespace(tag=tag, value=str(value), currency=currency,
                                 account=account)


def test_account_cash_reads_total_cash_value(ib_adapter):
    """MUTATION-VERIFIED: reading AvailableFunds instead, or raising on a
    missing tag, turns this red."""
    fake = ib_adapter.ib
    fake.account_rows = [_acct("AvailableFunds", 51000.0),
                         _acct("TotalCashValue", 49680.58),
                         _acct("NetLiquidation", 99680.58),
                         _acct("TotalCashValue", 12.5, currency="EUR")]
    out = ib_adapter.account_cash()
    assert out["total_cash"] == 49680.58 and out["net_liq"] == 99680.58
    fake.account_rows = [_acct("AvailableFunds", 51000.0)]
    assert ib_adapter.account_cash() is None          # no claim, no raise
    fake.account_rows = None                           # venue returns junk
    assert ib_adapter.account_cash() is None


def test_commission_reaches_fill_results(ib_adapter):
    fake = ib_adapter.ib
    fake.on_place = lambda t: fake.fill(t, [(20, 91.42)], commission=1.0)
    r = ib_adapter.place_stock_order("BIL", 20, "MKT", client_order_id="c1")
    assert r["status"] == "filled" and r["commission"] == 1.0
    assert ib_adapter.find_stock_order("c1")["commission"] == 1.0


def test_rejection_reason_comes_from_error_event_not_status_echo(ib_adapter):
    """Counter-agent round 1: ib_async delivers an order rejection's REASON on
    errorEvent (keyed by orderId) / trade.advancedError; trade.log holds
    status changes. A bare 'Cancelled' log line is not a reason.
    MUTATION-VERIFIED: dropping the errorEvent hook, or letting a status
    echo through as the reason, turns this red."""
    fake = ib_adapter.ib

    def reject(t):
        t.orderStatus.status = "Cancelled"
        t.log = [types.SimpleNamespace(errorCode=0, message="Cancelled",
                                       status="Cancelled")]
        fake.errorEvent.emit(t.order.orderId, 10147,
                             "Order to be Cancelled: OPG order after the open",
                             t.contract)

    fake.on_place = reject
    with pytest.raises(RuntimeError, match="OPG order after the open"):
        ib_adapter.place_stock_order("MRK", 12, "MOO", tif="OPG",
                                     client_order_id="blend-entry-16")
    o = ib_adapter.find_stock_order("blend-entry-16")
    assert "[10147]" in o["reason"] and "OPG order after the open" in o["reason"]
    assert "Cancelled;" not in o["reason"]

    def reject_silent(t):
        t.orderStatus.status = "Cancelled"
        t.log = [types.SimpleNamespace(errorCode=0, message="Cancelled",
                                       status="Cancelled")]
    fake.on_place = reject_silent
    with pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("MRK", 12, "MOO", tif="OPG",
                                     client_order_id="blend-entry-17")
    assert ib_adapter.find_stock_order("blend-entry-17")["reason"] == "no venue reason recorded"


def test_account_cash_multi_account_is_no_claim_and_filters_managed(ib_adapter):
    fake = ib_adapter.ib
    fake.account_rows = [_acct("TotalCashValue", 100.0, account="DU1"),
                         _acct("TotalCashValue", 200.0, account="DU2")]
    assert ib_adapter.account_cash() is None            # two accounts: no claim
    fake.managed = ["DU2"]
    assert ib_adapter.account_cash()["total_cash"] == 200.0


def test_commission_sentinel_is_ignored_and_report_is_awaited(ib_adapter):
    """IB's UNSET sentinel (~1.8e308) must never reach the ledger; and a
    report that lands one pump AFTER the fill is still read (the adapter
    waits COMMISSION_WAIT_S for execId)."""
    fake = ib_adapter.ib
    fake.on_place = lambda t: fake.fill(t, [(20, 91.42)], commission=1.7976931348623157e308)
    r = ib_adapter.place_stock_order("BIL", 20, "MKT", client_order_id="c-sent")
    assert "commission" not in r          # ignored report = UNREPORTED (round 3)
    # report lands late: first pump attaches it
    def late(t):
        fake.fill(t, [(20, 91.42)])                       # no report yet
        fake.on_sleep = lambda ib: setattr(
            t.fills[0], "commissionReport",
            types.SimpleNamespace(commission=1.0, execId="ex-late", currency="USD"))
    fake.on_place = late
    r = ib_adapter.place_stock_order("BIL", 20, "MKT", client_order_id="c-late")
    assert r["commission"] == 1.0
    fake.on_sleep = None


def test_warning_codes_are_not_venue_reasons(ib_adapter):
    fake = ib_adapter.ib

    def reject(t):
        fake.errorEvent.emit(t.order.orderId, 399, "Order will not be placed at the exchange until ...", t.contract)
        t.orderStatus.status = "Cancelled"
        # the real wrapper ALSO writes the warning into trade.log (round 3)
        t.log = [types.SimpleNamespace(errorCode=399, status="ValidationError",
                                       message="Warning 399, reqId 1: Order Message: ..."),
                 types.SimpleNamespace(errorCode=0, message="Cancelled", status="Cancelled")]
    fake.on_place = reject
    with pytest.raises(RuntimeError):
        ib_adapter.place_stock_order("MRK", 1, "MOO", tif="OPG", client_order_id="w1")
    assert ib_adapter.find_stock_order("w1")["reason"] == "no venue reason recorded"


# --- counter-agent round 3 ---------------------------------------------------

def test_error_map_is_order_only_and_cleared_on_reconnect(ib_adapter):
    fake = ib_adapter.ib
    # a market-data request id (same counter) errors: not an order -> ignored
    fake.errorEvent.emit(350, 10197, "No market data during competing live session", None)
    assert ib_adapter._order_errors == {}
    # an order id IS recorded ...
    fake.on_place = None
    ib_adapter.place_stock_order("CRSP", -5, "STP", stop_price=44.0, tif="GTC",
                                 client_order_id="r3-stp")
    oid = fake._trades[-1].order.orderId
    fake.errorEvent.emit(oid, 201, "Order rejected - reason: ...", None)
    assert ib_adapter._order_errors[oid].startswith("[201]")
    # ... and the map is cleared by a reconnect (ids restart at nextValidId)
    fake.connected = False
    assert ib_adapter.spot("SPY") == 100.0                   # reconnects
    assert ib_adapter._order_errors == {}


def test_completed_order_without_fills_is_unreported():
    t = types.SimpleNamespace(fills=[], orderStatus=types.SimpleNamespace(status="Filled"))
    assert ib_mod._commission_reported(t) is False


def test_two_managed_accounts_is_no_claim(ib_adapter):
    fake = ib_adapter.ib
    fake.account_rows = [_acct("TotalCashValue", 100.0, account="DU1"),
                         _acct("TotalCashValue", 200.0, account="DU2")]
    fake.managed = ["DU1", "DU2"]
    assert ib_adapter.account_cash() is None
    # a BASE row in a non-USD base is not ours either
    fake.managed = ["DU1"]
    fake.account_rows = [_acct("TotalCashValue", 100.0, currency="BASE", account="DU1")]
    assert ib_adapter.account_cash() is None


def test_dry_fill_reports_a_zero_commission():
    a = DryAdapter()
    r = a.place_stock_order("BIL", 3, "MKT", client_order_id="d-1")
    assert r["status"] == "filled" and r["commission"] == 0.0


# --- 2026-09-08: venue order-history requests are bounded --------------------
# MUTATION-VERIFIED: dropping the RequestTimeout assignment turns
# test_order_history_refresh_is_bounded red (the fake sees 0 = forever);
# turning the OPEN-orders timeout into `continue` turns it red (a timeout
# there must fail CLOSED, never read as "venue never saw the order");
# dropping the ib.disconnect() turns it red; dropping the executions
# fallback turns test_completed_orders_timeout_falls_back_to_executions
# red; reading a reqExecutions timeout as "no fills" turns it red.
# NOT catchable here: narrowing the except to the builtin TimeoutError
# alone - on 3.11+ asyncio.TimeoutError IS TimeoutError.

def _exec_fill(ref, shares, price, order_id=77, exec_id="ex-1", commission=1.0):
    return types.SimpleNamespace(
        execution=types.SimpleNamespace(orderRef=ref, shares=shares, price=price,
                                        orderId=order_id, execId=exec_id, side="SLD"),
        commissionReport=types.SimpleNamespace(commission=commission, execId=exec_id,
                                               currency="USD"))


def test_order_history_refresh_is_bounded(ib_adapter):
    fake = ib_adapter.ib
    fake.RequestTimeout = 0                        # ib_async default: forever
    seen = {}

    def open_hang():
        seen["timeout"] = fake.RequestTimeout
        if not fake.RequestTimeout:
            raise AssertionError("reqAllOpenOrders issued with no timeout: "
                                 "this is the 2026-09-08 loop hang")
        raise TimeoutError("openOrderEnd never arrived")
    fake.reqAllOpenOrders = open_hang
    with pytest.raises(ExecutorConnectionError) as e:
        ib_adapter.find_stock_order("blend-sweep-wedged")
    assert "timed out" in str(e.value) and "fails closed" in str(e.value)
    assert seen["timeout"] == ib_mod.VENUE_HISTORY_TIMEOUT_S
    assert fake.RequestTimeout == 0                # restored
    assert not fake.isConnected(), "session must be dropped so _reconnect pages"
    # a venue that answers "nothing" is still "venue never saw it" (the
    # adapter reconnects transparently), timeout restored on success too
    fake.reqAllOpenOrders = lambda: []
    assert ib_adapter.find_stock_order("blend-sweep-wedged") is None
    assert fake.RequestTimeout == 0 and fake.isConnected()
    # a non-timeout venue error on either refresh is still tolerated
    def boom(*a, **k):
        raise RuntimeError("gateway said no")
    fake.reqCompletedOrders = boom
    assert ib_adapter.find_stock_order("blend-sweep-wedged") is None
    fake.reqCompletedOrders = lambda apiOnly=True: []


def test_completed_orders_timeout_falls_back_to_executions(ib_adapter):
    """The 2026-09-08 gateway never answered reqCompletedOrders on any
    session. That request is best effort: the fill question is answered
    from execution reports, the session is KEPT, the cycle completes."""
    fake = ib_adapter.ib

    def completed_hang(apiOnly=False):
        assert fake.RequestTimeout == ib_mod.VENUE_HISTORY_TIMEOUT_S
        raise asyncio.TimeoutError("completedOrdersEnd never arrived")   # 3.10 class
    fake.reqCompletedOrders = completed_hang
    fake.fills = lambda: [_exec_fill("blend-sweep-32", 20, 91.20, exec_id="a"),
                          _exec_fill("blend-sweep-32", 12, 91.30, exec_id="b"),
                          _exec_fill("blend-other", 5, 50.0, exec_id="c")]
    fake.reqExecutions = lambda *a, **k: [_exec_fill("blend-sweep-32", 12, 91.30, exec_id="b")]
    r = ib_adapter.find_stock_order("blend-sweep-32")
    assert r["status"] == "filled" and r["filled_qty"] == 32      # exec b not double counted
    assert r["fill_price"] == pytest.approx((20 * 91.20 + 12 * 91.30) / 32)
    assert r["commission"] == 2.0 and r["source"] == "executions"
    assert fake.isConnected() and fake.RequestTimeout == 0
    # no execution carries the ref -> the venue never filled it
    assert ib_adapter.find_stock_order("blend-sweep-never") is None
    # executions ALSO unanswered -> fail closed, session dropped
    def exec_hang(*a, **k):
        raise TimeoutError("execDetailsEnd never arrived")
    fake.reqExecutions = exec_hang
    with pytest.raises(ExecutorConnectionError):
        ib_adapter.find_stock_order("blend-sweep-32")
    assert not fake.isConnected()


def test_cancel_of_an_executed_order_raises_when_history_is_unavailable(ib_adapter):
    """Law #8 under the 2026-09-08 gateway: a stop that FILLED during an
    outage is not open and not in the session; with completed orders
    unavailable the execution reports must turn "not found" into RAISE."""
    fake = ib_adapter.ib
    fake.reqCompletedOrders = lambda apiOnly=False: (_ for _ in ()).throw(TimeoutError("x"))
    fake.fills = lambda: [_exec_fill("blend-1-stp-44.0000", 5, 43.9, order_id=910, exec_id="s1")]
    fake.reqExecutions = lambda *a, **k: []
    with pytest.raises(RuntimeError) as e:
        ib_adapter.cancel_stock_order("910")
    assert "already FILLED" in str(e.value)
    assert ib_adapter.cancel_stock_order("911") is False      # truly unknown


def test_execution_refresh_reads_the_store_and_keeps_the_commission(ib_adapter):
    """ib_async appends a fresh Fill with an EMPTY CommissionReport for an
    already-known execId on reqExecutions: the request's return value must
    never overwrite the store, and the store is re-read AFTER the refresh."""
    fake = ib_adapter.ib
    fake.reqCompletedOrders = lambda apiOnly=False: (_ for _ in ()).throw(TimeoutError("x"))
    store = [_exec_fill("blend-sweep-x", 10, 100.0, exec_id="a", commission=1.0)]
    called = {"n": 0}

    def req_exec(*a, **k):
        called["n"] += 1
        store.append(_exec_fill("blend-sweep-x", 5, 101.0, exec_id="b", commission=0.5))
        return [_exec_fill("blend-sweep-x", 10, 100.0, exec_id="a", commission=None)]
    fake.reqExecutions = req_exec
    fake.fills = lambda: list(store)
    r = ib_adapter.find_stock_order("blend-sweep-x")
    assert called["n"] == 1 and r["filled_qty"] == 15                # late fill seen
    assert r["commission"] == 1.5                                      # not overwritten
    # a rejected-then-retried ref: only the LATEST orderId binds
    store[:] = [_exec_fill("blend-sweep-y", 3, 100.0, order_id=5, exec_id="c"),
                _exec_fill("blend-sweep-y", 9, 100.0, order_id=8, exec_id="d")]
    fake.reqExecutions = lambda *a, **k: []
    r = ib_adapter.find_stock_order("blend-sweep-y")
    assert r["filled_qty"] == 9 and r["order_ref"] == "8"
    assert ib_adapter.history_complete() is False
    # ANY failure of the completed-orders request engages the fallback, not
    # only a timeout (counter-agent LOW)
    def refused(apiOnly=False):
        raise RuntimeError("not supported by this gateway")
    fake.reqCompletedOrders = refused
    r = ib_adapter.find_stock_order("blend-sweep-y")
    assert r is not None and r["filled_qty"] == 9
    assert ib_adapter.history_complete() is False
