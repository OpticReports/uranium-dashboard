"""MirrorManager (live) driving the REAL app.ib_adapter.IBAdapter over the repo's own FakeIB
(tests/test_ib_stock_adapter.py). Ported from the adversarial review's harness (reviewer A), which is
what found A-07, A-11, A-13 and A-16: the manager's own Venue double (tests/test_mirror.py) remembers
every order for ever and answers every lookup, which a real gateway session does not.

The fake is extended only so that it behaves like one ACCOUNT across sessions:
- fills move positions and cash, and executions carry orderRef / orderId / execId as ib_async's do
- a new session (a process restart or a gateway reconnect) starts with an EMPTY trade list and learns
  of earlier orders only through reqAllOpenOrders / reqCompletedOrders / fills()
- completed orders can be unavailable (the gateway that never answers reqCompletedOrders), or 'bare'
  exactly as ib_async 2.1.0 builds them for an order the session did not place: a status, NO fills,
  filled == 0, and an execution already stored is never attached afterwards
- reqExecutions answers for the current day only (boot(next_day=True))
- a LIMIT order (the mirror's buys) fills only at or under its limit; otherwise it rests

Changes from the reviewer's file: the fake ib_async module gains LimitOrder (the buys are limit orders
now) and placeOrder honours a limit. Nothing else.
"""
from __future__ import annotations

import sys
import types

import test_ib_stock_adapter as tia
import test_mirror as tm
import app.ib_adapter as ib_mod
from app import mirror as mm


class Account:
    def __init__(self, cash=100_000.0):
        self.cash = cash
        self.pos: dict = {}
        self.orders: list = []          # every trade ever placed (the venue's own record)
        self.execs: list = []           # today's executions (reqExecutions / ib.fills())
        self.next_id = 1
        self.exec_n = 0


class VenueIB(tia.FakeIB):
    def __init__(self, acct: Account, prices: dict):
        super().__init__()
        self.acct = acct
        self.prices = dict(prices)
        self.fill_px: dict = {}
        self.hold: set = set()
        self.reject: dict = {}          # symbol -> status the venue answers with
        self.crash_after: set = set()
        self.completed_available = True
        self.bare_completed = False
        self.RequestTimeout = 0
        self.placed: list = []
        self.cancels: list = []

    # --- the account ---
    def managedAccounts(self):
        return ["DU1"]

    def accountValues(self):
        row = lambda tag: types.SimpleNamespace(tag=tag, currency="USD", account="DU1", value=str(self.acct.cash))  # noqa: E731
        return [row("TotalCashValue"), row("AvailableFunds")]

    def positions(self):
        return [tia.FakePosition(s, float(q)) for s, q in self.acct.pos.items()]

    # --- orders ---
    def _px(self, t):
        return self.fill_px.get(t.contract.symbol) or self.prices[t.contract.symbol]

    def _crosses(self, t):
        if t.order.orderType != "LMT":
            return True
        px, lim = self._px(t), float(t.order.lmtPrice)
        return px <= lim + 1e-12 if t.order.action == "BUY" else px >= lim - 1e-12

    def placeOrder(self, contract, order):
        order.orderId = self.acct.next_id
        self.acct.next_id += 1
        order.permId = 9000 + order.orderId
        t = tia.FakeTrade(contract, order)
        t.orderStatus.status = "Submitted"
        t.orderStatus.filled = 0
        self._trades.append(t)
        self.acct.orders.append(t)
        self.placed.append((contract.symbol, order.action, order.totalQuantity, order.orderRef))
        if self.on_place:
            self.on_place(t)
        if contract.symbol in self.reject:
            t.orderStatus.status = self.reject[contract.symbol]
            return t
        if contract.symbol not in self.hold and self._crosses(t) and t.orderStatus.status == "Submitted":
            self.execute(t, order.totalQuantity)
        if contract.symbol in self.crash_after:
            raise tm.Crash(contract.symbol)
        return t

    def execute(self, t, shares, price=None, commission=1.0):
        sym = t.contract.symbol
        px = price or self._px(t)
        if t.order.orderType == "LMT" and t.order.action == "BUY":
            assert px <= float(t.order.lmtPrice) + 1e-12, "a limit buy never fills above its limit"
        side = "BOT" if t.order.action == "BUY" else "SLD"
        sign = 1 if side == "BOT" else -1
        self.acct.exec_n += 1
        ex = tia.FakeExec(shares, px, side)
        ex.orderRef, ex.orderId, ex.permId, ex.execId = t.order.orderRef, t.order.orderId, t.order.permId, f"e{self.acct.exec_n}"
        f = tia.FakeFill(ex, commission)
        f.commissionReport.execId = ex.execId
        t.fills.append(f)
        self.acct.execs.append(f)
        self.acct.pos[sym] = self.acct.pos.get(sym, 0) + sign * shares
        self.acct.cash -= sign * shares * px + commission
        t.orderStatus.filled = getattr(t.orderStatus, "filled", 0) + shares
        if t.orderStatus.filled >= t.order.totalQuantity:
            t.orderStatus.status = "Filled"

    def cancelOrder(self, order):
        t = next(x for x in self.acct.orders if x.order is order)
        self.cancels.append((t.contract.symbol, t.orderStatus.status))
        if self.on_cancel:
            self.on_cancel(t)
        elif t.orderStatus.status not in ("Filled", "Cancelled"):
            t.orderStatus.status = "Cancelled"

    def reqAllOpenOrders(self):
        return [t for t in self.acct.orders if t.orderStatus.status in ("Submitted", "PreSubmitted")]

    def reqCompletedOrders(self, apiOnly=True):
        if not self.completed_available:
            raise TimeoutError("reqCompletedOrders: no completedOrdersEnd")
        done = [t for t in self.acct.orders if t.orderStatus.status in ("Filled", "Cancelled", "Inactive")]
        if not self.bare_completed:
            return done
        # exactly what ib_async 2.1.0 builds for a completed order this session did not place
        # (wrapper.completedOrder: OrderStatus(orderId, status) and NO fills; an execution already in
        # wrapper.fills is never attached afterwards - wrapper.execDetails, 'first time we see this')
        out = []
        for t in done:
            b = tia.FakeTrade(t.contract, t.order)
            b.orderStatus.status = t.orderStatus.status
            b.orderStatus.filled = 0
            out.append(b)
        return out

    def reqExecutions(self):
        return list(self.acct.execs)

    def fills(self):
        return list(self.acct.execs)


class IBRig:
    """one account, one state directory; boot() = a new process and a new gateway session"""
    ib_cls = None                       # a VenueIB subclass (tests/test_mirror_connection.py)

    def __init__(self, tmp_path, monkeypatch, cash=100_000.0, engines=tm.ENGINES, **cfg):
        self.tmp, self.mp, self.engines, self.cfg_over = tmp_path, monkeypatch, tuple(engines), cfg
        self.acct = Account(cash)
        self.clock = tm.Clock(tm.at("15:00"))
        self.brain = tm.Brain(self.clock)
        self.alerts: list = []
        for k, v in (("PLACE_ACK_TIMEOUT_S", 0.05), ("MKT_FILL_WAIT_S", 0.02), ("CANCEL_ACK_TIMEOUT_S", 0.05),
                     ("WAIT_TICK_S", 0.0), ("COMMISSION_WAIT_S", 0.01), ("QUOTE_WAIT_S", 0.05)):
            monkeypatch.setattr(ib_mod, k, v, raising=False)
        self.boot()

    def boot(self, next_day=False, completed_available=True, bare_completed=False):
        if next_day:
            self.acct.execs = []                      # reqExecutions answers for the current day only
        old = getattr(self, "ib", None)
        self.ib = (self.ib_cls or VenueIB)(self.acct, tm.PX)
        self.ib.completed_available = completed_available
        self.ib.bare_completed = bare_completed
        if old is not None:
            self.ib.fill_px, self.ib.hold, self.ib.prices = old.fill_px, old.hold, old.prices
        mod = types.ModuleType("ib_async")
        mod.IB = lambda: self.ib
        mod.Stock = tia.FakeStock
        mod.Future = tia.FakeStock
        mod.MarketOrder = tia.FakeMarketOrder
        mod.StopOrder = tia.FakeStopOrder
        mod.LimitOrder = tia.FakeLimitOrder
        self.mp.setitem(sys.modules, "ib_async", mod)
        self.ad = ib_mod.IBAdapter(tia._Cfg())
        cfg = mm.MirrorConfig(name="live", live=True, engines=self.engines,
                              capital={e: 100_000.0 * w for e, w in tm.W.items()},
                              state_path=str(self.tmp / "mirror.json"), **self.cfg_over)
        self.m = mm.MirrorManager(cfg, brain=self.brain, alert=self.alerts.append, clock=self.clock,
                                  sleep=self.clock.sleep)
        return self.m

    def tick(self, hms=None, day=tm.DAY):
        if hms:
            self.clock.now = tm.at(hms, day)
        self.m.tick(self.ad)
        return self.m

    def venue_pos(self):
        return {s: q for s, q in sorted(self.acct.pos.items()) if q}

    def red(self):
        return [a for a in self.alerts if a.startswith("🚨")]

    def trade(self, symbol, action=None):
        return next(x for x in self.acct.orders
                    if x.contract.symbol == symbol and (action is None or x.order.action == action))
