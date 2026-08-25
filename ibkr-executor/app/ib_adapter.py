"""IBKR venue adapter (ib_async against the in-container IB Gateway).

Translates the manager's venue-agnostic structures into IBKR combo orders:
  {"underlying": "NG", "kind": "call_spread", "expiry_hint": "2027-02",
   "lo_strike_pct": 1.10, "hi_strike_pct": 1.45}
-> qualify underlying -> option chain -> nearest expiry >= hint -> strikes
   nearest pct-of-spot on the real grid -> 2-leg BAG combo, limit at mid,
   quantity = budget // (net debit per combo).

DryAdapter mirrors the interface with logged intents and synthetic fills so
the service runs green with no gateway and no credentials (OFFLINE mode).
Everything venue-real is validated in the PAPER phase before live matters.
"""
from __future__ import annotations

import logging
import math
import time

logger = logging.getLogger(__name__)

UNDERLYINGS = {
    # symbol -> (secType, exchange, currency, option multiplier)
    "NG": ("FUT", "NYMEX", "USD", 10_000),
    "SB": ("FUT", "NYBOT", "USD", 1_120),     # ICE US softs route as NYBOT
    "SLV": ("STK", "SMART", "USD", 100),
}

# -- stock/ETF (blend3070 paper phase) -----------------------------------------
STOCK_EXCHANGE = "SMART"
STOCK_CURRENCY = "USD"
PLACE_ACK_TIMEOUT_S = 10.0   # no venue ack within this -> raise (idempotent
                             # retry via the deterministic client_order_id)
MKT_FILL_WAIT_S = 5.0        # bounded wait for a synchronous MKT fill (liquid
                             # ETFs fill in well under this during RTH); a MKT
                             # still working after it returns 'working'
CANCEL_ACK_TIMEOUT_S = 10.0  # ambiguous cancel timeout -> RAISE (fail closed)
WAIT_TICK_S = 0.25           # event-loop pump granularity inside waits
RECONNECT_BACKOFF_S = 15.0   # first retry delay after the gateway drops
RECONNECT_BACKOFF_MAX_S = 300.0  # backoff cap (~one attempt per blend cycle)
OUTAGE_ALERT_S = 30 * 60.0   # alert ONLY when down longer than this — the
                             # daily IB gateway auto-restart is far shorter
                             # and must be a non-event (fail closed, then
                             # auto-recover silently)

# IB order states that mean the order can no longer fill.
_IB_CANCELLED = ("Cancelled", "ApiCancelled", "Inactive")


class ExecutorConnectionError(RuntimeError):
    """The gateway connection is down: every stock-order surface raises this
    instead of guessing — the blend cycle FAILS CLOSED on it (reconcile
    raises, no decision is taken against unreconciled venue state)."""


def _map_status(ib_status: str) -> str:
    """IB order state -> the adapter contract's {filled, working, cancelled}."""
    if ib_status == "Filled":
        return "filled"
    if ib_status in _IB_CANCELLED:
        return "cancelled"
    return "working"


def _agg_fill_price(trade) -> float | None:
    """Share-weighted average price over a trade's executions. None when the
    venue reported no usable price — NEVER 0.0 (repo law: a silent zero fill
    price would vaporize proceeds downstream)."""
    fills = list(getattr(trade, "fills", []) or [])
    shares = sum(int(f.execution.shares) for f in fills)
    if shares > 0:
        num = sum(int(f.execution.shares) * float(f.execution.price)
                  for f in fills)
        if num > 0:
            return num / shares
    avg = float(getattr(trade.orderStatus, "avgFillPrice", 0.0) or 0.0)
    return avg if avg > 0 else None


def _order_ref(trade) -> str:
    """The adapter-level order handle: IB's orderId (stable across a
    same-clientId reconnect; permId is accepted as an alias on lookup)."""
    return str(trade.order.orderId)


def pick_expiry(expirations: list[str], hint_ym: str) -> str | None:
    """Nearest expiry on/after the hint month (YYYYMM...)."""
    want = hint_ym.replace("-", "")
    cands = sorted(e for e in expirations if e[:6] >= want[:6])
    return cands[0] if cands else (sorted(expirations)[-1] if expirations else None)


def pick_strike(strikes: list[float], target: float) -> float | None:
    return min(strikes, key=lambda s: abs(s - target)) if strikes else None


def size_combos(budget: float, net_debit: float, multiplier: int) -> int:
    """Whole combos purchasable with budget at the quoted net debit."""
    per = net_debit * multiplier
    return max(0, int(budget // per)) if per > 0 else 0


class IBAdapter:
    def __init__(self, cfg, outage_log=None):
        # The adapter is built inside the service's daemon loop thread:
        # ensure that thread owns an asyncio event loop BEFORE IB() binds
        # one (review sub-note — a constructor raise here used to kill the
        # loop thread silently; service._loop also guards the build now).
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        from ib_async import IB               # lazy: tests inject a mock module
        self.cfg = cfg
        self.ib = IB()
        # stock/ETF surfaces (blend3070): qualified-contract cache, drain-once
        # bookkeeping for poll_stock_fills, and the re-queue buffer blend's
        # _ingest_fills uses on a mid-ingestion failure.
        self._stock_contracts: dict[str, object] = {}
        self._emitted_fill_keys: set[str] = set()
        self._requeued_fills: list[dict] = []
        # M5 reconnect bookkeeping: the gateway's daily auto-restart drops
        # the session — every surface reconnects with backoff via
        # _require_connected instead of staying wedged until a manual
        # container restart. Shared by the stock surfaces AND the combo
        # path (spot() goes through the same gate).
        self._reconnect_backoff = RECONNECT_BACKOFF_S
        self._next_reconnect_ts = 0.0
        self._disconnected_since: float | None = None
        self._outage_alerted = False
        # Persisted outage ledger (optional). Observability must never be
        # able to break trading, so every call site tolerates None.
        self.outages = outage_log
        # market-data posture: which feed IB is actually serving, and whether
        # the operator has been told we fell back to delayed
        self._md_type: int = int(getattr(cfg, "ib_market_data_type", 1))
        self._delayed_announced = False
        # Contradictory or unsafe postures fail AT BOOT, loudly, instead of
        # producing quiet stale pricing (counter-agent A3 + go-live pin):
        # - allow_delayed=False with a delayed type configured is a
        #   contradiction (the config itself asks for what the flag forbids)
        # - live money must never boot with the delayed fallback armed
        allow = bool(getattr(cfg, "ib_allow_delayed", True))
        if not allow and self._md_type != 1:
            raise RuntimeError(
                f"config contradiction: ib_allow_delayed=false but "
                f"ib_market_data_type={self._md_type} (delayed) - refusing "
                f"to boot into silent stale pricing")
        if getattr(cfg, "trading_mode", "paper") == "live" and allow:
            raise RuntimeError(
                "go-live posture violation: trading_mode=live requires "
                "IB_ALLOW_DELAYED=false (live orders must never price on "
                "delayed or prior-close data) - set the env and redeploy")
        self._connect()

    def _connect(self):
        port = 4002 if self.cfg.trading_mode == "paper" else 4001
        for attempt in range(20):             # gateway boots slowly (~2 min)
            try:
                self.ib.connect(self.cfg.ib_host, port,
                                clientId=self.cfg.ib_client_id, timeout=15)
                logger.info("connected to IB gateway (%s)", self.cfg.trading_mode)
                self._apply_market_data_type()
                return
            except Exception as exc:  # noqa: BLE001
                logger.info("gateway not ready (%d/20): %s", attempt + 1, exc)
                time.sleep(15)
        raise RuntimeError("could not connect to IB gateway")

    # -- the adapter's real methods (spot, chain, open_spread, marks, close)
    # are exercised ONLY in the paper phase; each call degrades to an
    # exception the service logs rather than acts on. Implementation uses
    # ib_async primitives: qualifyContracts, reqSecDefOptParams,
    # reqMktData for legs, Bag contract with ComboLegs, LimitOrder at mid.

    def _apply_market_data_type(self, mdt: int | None = None) -> None:
        """Tell IB which data feed to serve. NEVER called before 2026-08-24,
        so IB defaulted to LIVE (type 1); a paper account without market-data
        subscriptions then returned nan for every quote, spot() raised, every
        price went absent, and the book could not seed the SPY core, sweep
        BIL or rebalance - silently, forever."""
        want = int(mdt if mdt is not None
                   else getattr(self.cfg, "ib_market_data_type", 1))
        try:
            self.ib.reqMarketDataType(want)
            self._md_type = want
        except Exception as exc:  # noqa: BLE001
            logger.warning("reqMarketDataType(%d) failed: %s", want, exc)

    def _await_tick(self, ticker, wait_s: float, symbol: str = "?",
                    allow_close: bool = True) -> float:
        """Poll for a usable price until wait_s. The old code slept a flat 3s
        and read once - too short for a delayed feed's first tick, so even a
        working subscription could read as 'no market price'.

        allow_close: IB delivers yesterday's CLOSE in the initial tick
        snapshot even on an otherwise-dry live feed - exactly during feed
        warm-up and pre-open, when the cycle prices. With the delayed
        fallback disallowed (go-live), close is excluded too: a prior-close
        print is stale data by another name (counter-agent A4, executed
        proof: allow_delayed=False still returned 600.0 = yesterday's
        close). When permitted, a close-sourced price is logged per symbol,
        never silent.
        """
        fields = ("last", "bid", "ask") + (("close",) if allow_close else ())
        deadline = time.monotonic() + max(0.5, wait_s)
        px = float("nan")
        while time.monotonic() < deadline:
            self.ib.sleep(WAIT_TICK_S)
            px = ticker.marketPrice()
            if px == px and px > 0:
                return float(px)
            for attr in fields:
                v = getattr(ticker, attr, None)
                if v is not None and v == v and v > 0:
                    if attr == "close":
                        logger.warning("%s priced from PRIOR CLOSE (no live "
                                       "tick yet)", symbol)
                    return float(v)
        return px

    def spot(self, symbol: str) -> float:
        from ib_async import Future, Stock
        self._require_connected()
        # Symbols outside the El Nino table (SPY/BIL/sleeve names from the
        # blend book) quote as plain SMART/USD stocks.
        sec_type, exch, cur, _ = UNDERLYINGS.get(
            symbol, ("STK", STOCK_EXCHANGE, STOCK_CURRENCY, 100))
        if sec_type == "STK":
            c = Stock(symbol, exch, cur)
        else:
            c = Future(symbol, exchange=exch, currency=cur)
            c = sorted(self.ib.reqContractDetails(c),
                       key=lambda d: d.contract.lastTradeDateOrContractMonth
                       )[0].contract
        self.ib.qualifyContracts(c)
        wait = float(getattr(self.cfg, "ib_quote_wait_s", 6.0))
        allow = bool(getattr(self.cfg, "ib_allow_delayed", True))
        configured = int(getattr(self.cfg, "ib_market_data_type", 1))
        # Escalation is PER CALL, bracketed by these two applies: the first
        # heals any session state (IB resets the type per session, so after
        # a gateway restart the old sticky escalation left _md_type lying
        # and every quote wedged on "already active" - the book went
        # quote-dead again daily); the finally guarantees the session is
        # never left parked on delayed for other reqMktData users.
        self._apply_market_data_type(configured)
        try:
            t = self.ib.reqMktData(c, "", False, False)
            px = self._await_tick(t, wait, symbol, allow_close=allow)
            self.ib.cancelMktData(c)
            if px == px and px > 0:
                return float(px)
            # Configured feed returned nothing. Escalate to delayed only if
            # allowed - and say so: a degradation that prices real orders
            # must be visible, never inferred. Disallowed (go-live posture)
            # = hard failure, the cycle fails closed as it should.
            if not allow:
                raise RuntimeError(
                    f"no market price for {symbol} (market-data type "
                    f"{configured}; delayed fallback disabled)")
            if configured == 3:
                raise RuntimeError(
                    f"no market price for {symbol} on the configured "
                    f"DELAYED feed - check this account's IB market-data "
                    f"entitlements")
            self._apply_market_data_type(3)
            t = self.ib.reqMktData(c, "", False, False)
            px = self._await_tick(t, wait, symbol, allow_close=True)
            self.ib.cancelMktData(c)
            if px != px or px <= 0:
                raise RuntimeError(
                    f"no market price for {symbol} on live OR delayed data "
                    f"- check this account's IB market-data subscription")
            if not self._delayed_announced:
                self._delayed_announced = True
                from .alerts import send
                send("🔴 ACTION NEEDED (you) — IBKR is serving DELAYED "
                     "(~15min) quotes: this account has no live market-data "
                     "subscription. The 30/70 book is valuing and "
                     "rebalancing on delayed prices. Acceptable on paper; "
                     "attach a subscription and set IB_ALLOW_DELAYED=false "
                     "BEFORE switching to live money.")
            logger.warning("%s priced on DELAYED data", symbol)
            return float(px)
        finally:
            if getattr(self, "_md_type", configured) != configured:
                self._apply_market_data_type(configured)

    def open_spread(self, structure: dict, budget: float) -> dict:
        """Build+place the combo; returns {order_ref, premium} once filled.
        Raises on anything ambiguous — the service reports, never improvises."""
        raise NotImplementedError(
            "combo construction lands with the paper-phase deploy; "
            "OFFLINE/DRY runs never reach this path")

    def mark(self, order_ref: str) -> float | None:
        raise NotImplementedError

    def close_spread(self, order_ref: str) -> dict:
        raise NotImplementedError

    # -- stock/ETF orders (blend3070 paper phase) ------------------------------
    # Real ib_async implementation of the DryAdapter-pinned contract:
    #   * MOO = MarketOrder tif OPG; MKT = MarketOrder DAY; STP = StopOrder GTC
    #   * client_order_id maps to IB orderRef (idempotency key); placements
    #     dedupe against venue order history by orderRef before placing
    #   * cancel tri-state: FILLED -> RAISE, not-found/already-cancelled ->
    #     False, cancelled -> True; an ambiguous ack timeout RAISES (fail
    #     closed — blend defers the dependent action to the next cycle)
    #   * no silent zero fill prices: an unknown price is None, never 0.0
    #   * every method raises ExecutorConnectionError when the gateway is
    #     down — reconcile raises and the blend cycle FAILS CLOSED
    # ASYNC-FILL DESIGN (differs from DryAdapter ON PURPOSE): DryAdapter's
    # synchronous MOO/MKT fills are a SIMULATION convenience. The real venue
    # fills MOO at the next open, so place_stock_order returns status
    # 'working' immediately (never blocks on OPG) and blend's write-ahead
    # journal + reconcile pass 2/2b adopt the fill from order history by
    # orderRef on a later cycle. MKT gets one bounded MKT_FILL_WAIT_S wait
    # because blend's exit path (_execute_exit / kill) books from the
    # placement result: a MKT that misses the window returns 'working' and
    # the exit routes to the loud UNRECONCILED/provisional paths — never a
    # faked price. Threading follows the combo methods' pattern: plain
    # synchronous ib_async calls (self.ib.sleep pumps the event loop) from
    # the service loop thread that built the adapter.

    def _outage(self, method: str, *args) -> None:
        """Ledger call that can never propagate. OutageLog guards its own
        methods too; this guards the adapter against any other ledger."""
        lg = self.outages
        if lg is None:
            return
        try:
            getattr(lg, method)(*args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("outage ledger %s failed (ignored): %s",
                           method, exc)

    def _require_connected(self) -> None:
        if self.ib.isConnected():
            return
        # M5: the gateway dropped (e.g. its daily auto-restart) — try to
        # reconnect with backoff instead of staying wedged. Still raises
        # while down: the blend cycle FAILS CLOSED, then auto-recovers on
        # a later cycle once the gateway is back.
        self._reconnect()
        if not self.ib.isConnected():
            raise ExecutorConnectionError(
                "IB gateway disconnected — stock-order surface unavailable "
                "(blend cycle fails closed; auto-reconnect with backoff is "
                "running)")

    def _reconnect(self) -> None:
        """One backed-off reconnect attempt. Alerts only when the outage
        exceeds OUTAGE_ALERT_S (the daily gateway restart stays a
        non-event); sends a recovery notice after an alerted outage."""
        now = time.monotonic()
        if self._disconnected_since is None:
            self._disconnected_since = now
            logger.warning("IB gateway connection lost — reconnecting with "
                           "backoff (alert only if down > %d min)",
                           int(OUTAGE_ALERT_S // 60))
            # wall clock, not monotonic: the ledger outlives this process
            self._outage("start", time.time())
        # a blocked adapter call - NOT a cycle: this guard fronts six
        # surfaces and reference_prices loops per symbol
        self._outage("blocked_call")
        if now < self._next_reconnect_ts:
            self._maybe_outage_alert(now)
            return
        try:
            try:
                self.ib.disconnect()
            except Exception:  # noqa: BLE001
                pass
            port = 4002 if self.cfg.trading_mode == "paper" else 4001
            self.ib.connect(self.cfg.ib_host, port,
                            clientId=self.cfg.ib_client_id, timeout=15)
        except Exception as exc:  # noqa: BLE001
            self._next_reconnect_ts = now + self._reconnect_backoff
            self._reconnect_backoff = min(self._reconnect_backoff * 2,
                                          RECONNECT_BACKOFF_MAX_S)
            logger.warning("IB gateway reconnect failed (next attempt in "
                           "%.0fs): %s", self._next_reconnect_ts - now, exc)
            self._maybe_outage_alert(now)
            return
        # IB's market-data type is PER SESSION: without this, the fresh
        # session serves live while _md_type still says delayed, and every
        # spot() wedges on the "already escalated" state - the book went
        # quote-dead again after each daily gateway restart (counter-agent
        # 2026-08-24, CRITICAL).
        self._apply_market_data_type()
        down_s = now - self._disconnected_since
        logger.info("IB gateway reconnected after %.0fs (same clientId: "
                    "orderIds stay monotone, drain-once keys persist)",
                    down_s)
        if self._outage_alerted:
            from .alerts import send
            send(f"🧬 IB gateway RECONNECTED after {down_s / 60:.0f} min — "
                 f"executor resumed (cycles were failing closed meanwhile; "
                 f"GTC stops rested at the venue throughout)")
        # State resets come FIRST. Closing the ledger before them meant a
        # raise inside end() left the adapter permanently believing it was
        # mid-outage while actually connected - the next real drop would then
        # skip the outage start and fire a spurious DOWN alert with a bogus
        # multi-hour duration (counter-agent 2026-08-24, CRITICAL).
        self._disconnected_since = None
        self._outage_alerted = False
        self._reconnect_backoff = RECONNECT_BACKOFF_S
        self._next_reconnect_ts = 0.0
        self._outage("end", time.time())

    def _maybe_outage_alert(self, now: float) -> None:
        if (self._outage_alerted or self._disconnected_since is None
                or now - self._disconnected_since <= OUTAGE_ALERT_S):
            return
        self._outage_alerted = True
        self._outage("mark_alerted")
        from .alerts import send
        send(f"🚨 IB gateway DOWN for over {int(OUTAGE_ALERT_S // 60)} min "
             f"— executor is failing closed (no entries/exits/stop "
             f"ratchets); GTC stops still rest at the venue. Auto-reconnect "
             f"keeps retrying with backoff; check the gateway container if "
             f"this persists")

    def _pump(self) -> None:
        """Process pending gateway messages (ib_async sync facade)."""
        self.ib.sleep(0)

    def _stock_contract(self, symbol: str):
        c = self._stock_contracts.get(symbol)
        if c is None:
            from ib_async import Stock
            qualified = self.ib.qualifyContracts(
                Stock(symbol, STOCK_EXCHANGE, STOCK_CURRENCY))
            if not qualified:
                raise RuntimeError(f"cannot qualify stock contract {symbol}")
            c = qualified[0]
            self._stock_contracts[symbol] = c
        return c

    def _all_trades(self, refresh: bool = False) -> list:
        """This session's trades; refresh=True additionally asks the venue
        for open + completed orders (covers orders placed in a previous
        session that the connect-time sync missed)."""
        trades = list(self.ib.trades())
        if refresh:
            seen = {(t.order.orderId, getattr(t.order, "permId", 0))
                    for t in trades}
            for fn, args in (("reqAllOpenOrders", ()),
                             ("reqCompletedOrders", (True,))):
                try:
                    extra = getattr(self.ib, fn)(*args) or []
                except Exception as exc:  # noqa: BLE001
                    logger.debug("%s failed: %s", fn, exc)
                    continue
                for t in extra:
                    key = (t.order.orderId, getattr(t.order, "permId", 0))
                    if key not in seen:
                        seen.add(key)
                        trades.append(t)
        return trades

    def _find_trade_by_ref(self, order_ref: str, refresh: bool = False):
        ref = str(order_ref)
        for t in self._all_trades(refresh):
            if str(t.order.orderId) == ref:
                return t
            perm = getattr(t.order, "permId", 0)
            if perm and str(perm) == ref:
                return t
        return None

    def _find_trade_by_client_id(self, client_order_id: str,
                                 refresh: bool = False):
        """Latest, most-alive trade carrying this orderRef (idempotency key):
        filled > working > cancelled — the dedupe/journal passes care about
        the order that still binds, not a dead earlier attempt."""
        rank = {"cancelled": 0, "working": 1, "filled": 2}
        best = None
        for t in self._all_trades(refresh):
            if (getattr(t.order, "orderRef", "") or "") != client_order_id:
                continue
            if (best is None or rank[_map_status(t.orderStatus.status)]
                    >= rank[_map_status(best.orderStatus.status)]):
                best = t
        return best

    def _trade_result(self, trade) -> dict:
        out = {"order_ref": _order_ref(trade),
               "status": _map_status(trade.orderStatus.status)}
        if out["status"] == "filled":
            px = _agg_fill_price(trade)
            if px is not None:              # unknown price -> NO key, never 0.0
                out["fill_price"] = float(px)
        return out

    def _await_placement(self, trade, order_type: str) -> None:
        """Bounded post-placement wait: surfaces rejections as exceptions
        (the stop-retry/STOP_MISSING paths need them), gives MKT one bounded
        chance at a synchronous fill, and NEVER blocks waiting for MOO/OPG.
        A missing ack past PLACE_ACK_TIMEOUT_S raises — the deterministic
        client_order_id makes the caller's retry idempotent (venue-side
        dedupe by orderRef adopts the order if it did land)."""
        ack_deadline = time.monotonic() + PLACE_ACK_TIMEOUT_S
        fill_deadline = (time.monotonic() + MKT_FILL_WAIT_S
                         if order_type == "MKT" else None)
        while True:
            self._pump()
            s = trade.orderStatus.status
            if s == "Filled":
                return
            if s in _IB_CANCELLED:
                raise RuntimeError(
                    f"order rejected by venue (status {s})")
            if s in ("PreSubmitted", "Submitted"):
                # Acked and resting. MOO/STP return 'working' right away;
                # MKT keeps one bounded window open for the synchronous fill.
                if fill_deadline is None or time.monotonic() >= fill_deadline:
                    return
            elif time.monotonic() >= ack_deadline:
                raise RuntimeError(
                    f"no venue ack within {PLACE_ACK_TIMEOUT_S:.0f}s "
                    f"(status {s!r}) — state UNKNOWN; retry is idempotent "
                    f"via orderRef")
            self.ib.sleep(WAIT_TICK_S)

    def place_stock_order(self, symbol: str, qty: int, order_type: str,
                          stop_price: float | None = None, tif: str = "DAY",
                          ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        """qty signed (+buy/-sell); order_type in {MOO, MKT, STP}. Returns
        {order_ref, status, fill_price?}: MOO/STP come back 'working' (the
        journal/reconcile design adopts async fills); MKT returns 'filled'
        with the venue's average price when it fills inside the bounded
        wait, else 'working'. ref_price is the caller's sizing reference —
        never used as a fill price here."""
        if order_type not in ("MOO", "MKT", "STP"):
            raise ValueError(f"unsupported stock order type {order_type}")
        if order_type == "STP" and stop_price is None:
            raise ValueError("STP order requires stop_price")
        qty = int(qty)
        if qty == 0:
            raise ValueError("qty must be non-zero (signed +buy/-sell)")
        self._require_connected()
        if client_order_id:
            self._pump()
            prior = self._find_trade_by_client_id(client_order_id)
            if (prior is not None
                    and _map_status(prior.orderStatus.status) != "cancelled"):
                # Venue-side dedupe by orderRef (pinned contract): a working
                # or filled order under this idempotency key is returned,
                # never re-placed.
                logger.info("stock order %s duplicate-suppressed by orderRef "
                            "(prior %s)", client_order_id, _order_ref(prior))
                return {**self._trade_result(prior), "duplicate": True}
        from ib_async import MarketOrder, StopOrder
        action = "BUY" if qty > 0 else "SELL"
        if order_type == "STP":
            order = StopOrder(action, abs(qty), float(stop_price))
            order.tif = "GTC"               # protective stops always rest GTC
        else:
            order = MarketOrder(action, abs(qty))
            order.tif = "OPG" if order_type == "MOO" else "DAY"
        if client_order_id:
            order.orderRef = client_order_id
        contract = self._stock_contract(symbol)
        trade = self.ib.placeOrder(contract, order)
        self._await_placement(trade, order_type)
        out = self._trade_result(trade)
        logger.info("stock order placed: %s %s x%d %s -> %s (%s)",
                    action, symbol, abs(qty), order_type, out["status"],
                    out["order_ref"])
        return out

    def cancel_stock_order(self, order_ref: str) -> bool:
        """CONTRACT (order-safety law #8): cancelling an order that has
        FILLED must RAISE, never return False. False is reserved for 'order
        not found / already cancelled'. True only after the venue ACKS the
        cancel; an ambiguous ack timeout RAISES (fail closed) — the blend
        exit path defers the dependent sell and the next reconcile settles
        the truth (a silent False on a filled stop would be the double-sell
        race, counter-agent N2/N14)."""
        self._require_connected()
        self._pump()
        trade = self._find_trade_by_ref(order_ref)
        if trade is None:
            trade = self._find_trade_by_ref(order_ref, refresh=True)
        if trade is None:
            return False
        s = trade.orderStatus.status
        if s == "Filled":
            raise RuntimeError(
                f"cannot cancel {order_ref}: order already FILLED")
        if s in _IB_CANCELLED:
            return False
        self.ib.cancelOrder(trade.order)
        deadline = time.monotonic() + CANCEL_ACK_TIMEOUT_S
        while True:
            self._pump()
            s = trade.orderStatus.status
            if s in ("Cancelled", "ApiCancelled"):
                return True
            if s == "Filled":
                # The fill won the race with the cancel: surface it exactly
                # like a cancel-of-filled (the caller's raising path books
                # the fill via reconcile before any market sell).
                raise RuntimeError(
                    f"cannot cancel {order_ref}: order FILLED before the "
                    f"cancel landed")
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"cancel of {order_ref} not acknowledged within "
                    f"{CANCEL_ACK_TIMEOUT_S:.0f}s — state UNKNOWN "
                    f"(fail closed)")
            self.ib.sleep(WAIT_TICK_S)

    def poll_stock_fills(self) -> list[dict]:
        """Drain-once fill events for resting protective stops, derived from
        venue order history (self.ib.trades(), synced on connect): each DONE
        STP order with executions is emitted EXACTLY once as
        {order_ref, client_order_id, symbol, qty, fill_price, action}, with
        partial fills aggregated per order at the share-weighted average
        price (qty signed by side). MOO/MKT fills are deliberately NOT
        emitted here — blend's journal reconcile (pass 2/2b) adopts them by
        orderRef, so they never surface as unknown-order alerts. A restart
        can re-emit an already-booked stop fill (the emitted-set is
        in-memory): blend's unknown-order branch turns that into RED noise,
        never a double booking — the documented tradeoff."""
        self._require_connected()
        self._pump()
        out, self._requeued_fills = self._requeued_fills, []
        for trade in self._all_trades():
            if getattr(trade.order, "orderType", "") != "STP":
                continue
            if trade.orderStatus.status not in ("Filled", "Cancelled",
                                                "ApiCancelled"):
                continue                      # still resting: nothing final yet
            keys = {str(trade.order.orderId)}
            perm = getattr(trade.order, "permId", 0)
            if perm:
                keys.add(str(perm))
            if keys & self._emitted_fill_keys:
                continue                      # never re-emit
            self._emitted_fill_keys |= keys
            fills = list(getattr(trade, "fills", []) or [])
            shares = sum(int(f.execution.shares) for f in fills)
            if shares <= 0:
                continue                      # cancelled untouched: no event
            side = fills[0].execution.side    # 'BOT' | 'SLD'
            out.append({
                "order_ref": _order_ref(trade),
                "client_order_id": getattr(trade.order, "orderRef", "") or None,
                "symbol": trade.contract.symbol,
                "qty": shares if side == "BOT" else -shares,
                "fill_price": _agg_fill_price(trade),   # None, never 0.0
                "action": side,
            })
        return out

    def requeue_stock_fills(self, fills: list[dict]) -> None:
        """Push un-ingested fill events back to the FRONT of the queue —
        blend's _ingest_fills re-queues on a mid-ingestion failure so a
        raising save()/alert never loses a venue fill (counter-agent N3)."""
        self._requeued_fills[:0] = list(fills)

    def find_stock_order(self, client_order_id: str) -> dict | None:
        """Look up a stock order by its idempotency key (IB orderRef).
        Returns {order_ref, status, fill_price?} or None if the venue never
        saw it — the boot/crash reconcile checks this before re-placing."""
        self._require_connected()
        self._pump()
        trade = self._find_trade_by_client_id(client_order_id)
        if trade is None:
            trade = self._find_trade_by_client_id(client_order_id,
                                                  refresh=True)
        return self._trade_result(trade) if trade is not None else None

    def stock_position(self, symbol: str) -> int:
        """Net venue holding for a SMART/USD stock — what the ACCOUNT
        actually holds NOW. The R1 blackout guard's positive-verification
        basis: order history has a horizon, positions do not."""
        self._require_connected()
        self._pump()
        qty = 0
        for p in self.ib.positions():
            c = getattr(p, "contract", None)
            if (c is not None and getattr(c, "symbol", "") == symbol
                    and getattr(c, "secType", "STK") in ("", "STK")):
                qty += int(p.position)
        return qty


class DryAdapter:
    """No gateway, no orders: synthesizes fills at the budget and marks flat.
    Lets the full decision loop + alerting run before any credential exists."""

    def __init__(self):
        self.log: list[dict] = []
        self._open: dict[str, float] = {}
        self._stops: dict[str, dict] = {}   # working GTC stock stops (blend)
        self._orders: dict[str, dict] = {}  # order_ref -> full stock-order record
        self._by_client: dict[str, str] = {}  # client_order_id -> order_ref
        self._fills: list[dict] = []        # stop-fill events awaiting poll
        self._last_px: dict[str, float] = {}  # last ref/fill price per symbol
        self._positions: dict[str, int] = {}  # net venue holdings from filled
                                              # orders (stock_position surface)

    def _rec(self, action, **kw):
        e = {"ts": int(time.time()), "action": action, **kw}
        self.log.append(e)
        logger.info("DRY %s", e)

    def spot(self, symbol: str) -> float:
        # Sleeve names quote at the last reference/fill price seen, so dry
        # exit fills and P&L are anchored to real inputs rather than a
        # fictional flat 100 (counter-agent minor finding).
        if symbol in self._last_px:
            return self._last_px[symbol]
        return {"NG": 2.6, "SB": 15.6, "SLV": 55.9}.get(symbol, 100.0)

    def open_spread(self, structure: dict, budget: float) -> dict:
        ref = f"dry-{structure['underlying']}-{int(time.time())}"
        self._open[ref] = budget
        self._rec("open_spread", structure=structure, budget=budget, ref=ref)
        return {"order_ref": ref, "premium": budget}

    def mark(self, order_ref: str) -> float | None:
        return self._open.get(order_ref)

    def close_spread(self, order_ref: str) -> dict:
        v = self._open.pop(order_ref, 0.0)
        self._rec("close_spread", ref=order_ref, value=v)
        return {"value": v}

    # -- stock/ETF orders (blend3070) -----------------------------------------
    # MOO/MKT fill immediately at the provided reference price (fall back to
    # spot); STP rests as a working GTC order until cancelled or triggered
    # via trigger_stop() (tests / simulated stop-outs). Triggered stops queue
    # a fill event that poll_stock_fills() drains — the blend cycle's
    # reconciliation-first pass. Two resting stops for the same symbol may
    # coexist transiently (place-new-then-cancel-old replace ordering).
    # client_order_id is the idempotency key: a duplicate placement while the
    # prior order is working/filled returns the PRIOR order (venue-side
    # dedupe, mirroring what the paper IBAdapter must do with orderRef).

    def _order_result(self, rec: dict) -> dict:
        out = {"order_ref": rec["order_ref"], "status": rec["status"]}
        if rec.get("fill_price") is not None:
            out["fill_price"] = rec["fill_price"]
        return out

    def place_stock_order(self, symbol: str, qty: int, order_type: str,
                          stop_price: float | None = None, tif: str = "DAY",
                          ref_price: float | None = None,
                          client_order_id: str | None = None) -> dict:
        if order_type not in ("MOO", "MKT", "STP"):
            raise ValueError(f"unsupported stock order type {order_type}")
        if client_order_id:
            prior = self._orders.get(self._by_client.get(client_order_id, ""))
            if prior is not None and prior["status"] in ("working", "filled"):
                self._rec("duplicate_suppressed", symbol=symbol, qty=qty,
                          client_order_id=client_order_id,
                          ref=prior["order_ref"])
                return {**self._order_result(prior), "duplicate": True}
        ref = f"dry-stk-{symbol}-{len(self.log)}-{int(time.time())}"
        if order_type == "STP":
            if stop_price is None:
                raise ValueError("STP order requires stop_price")
            self._stops[ref] = {"symbol": symbol, "qty": qty,
                                "stop_price": stop_price, "tif": tif}
            rec = {"order_ref": ref, "symbol": symbol, "qty": qty,
                   "order_type": "STP", "stop_price": stop_price, "tif": tif,
                   "status": "working", "fill_price": None,
                   "client_order_id": client_order_id}
            self._orders[ref] = rec
            if client_order_id:
                self._by_client[client_order_id] = ref
            self._rec("place_stock_order", symbol=symbol, qty=qty,
                      order_type=order_type, stop_price=stop_price, tif=tif,
                      ref=ref, status="working")
            return {"order_ref": ref, "status": "working"}
        fill = ref_price if ref_price is not None else self.spot(symbol)
        self._last_px[symbol] = fill
        self._positions[symbol] = self._positions.get(symbol, 0) + qty
        rec = {"order_ref": ref, "symbol": symbol, "qty": qty,
               "order_type": order_type, "tif": tif, "status": "filled",
               "fill_price": fill, "client_order_id": client_order_id}
        self._orders[ref] = rec
        if client_order_id:
            self._by_client[client_order_id] = ref
        self._rec("place_stock_order", symbol=symbol, qty=qty,
                  order_type=order_type, tif=tif, ref=ref, status="filled",
                  fill_price=fill)
        return {"order_ref": ref, "status": "filled", "fill_price": fill}

    def cancel_stock_order(self, order_ref: str) -> bool:
        rec = self._orders.get(order_ref)
        if rec is not None and rec["status"] == "filled":
            # Pinned contract (order-safety law #8): a cancel of a FILLED
            # order RAISES — mirroring IB, which errors on such a cancel —
            # so the caller's raising-cancel deferral path handles it. A
            # bool False stays reserved for not-found/already-cancelled.
            self._rec("cancel_stock_order", ref=order_ref, error="filled")
            raise RuntimeError(f"cannot cancel {order_ref}: order already "
                               f"FILLED")
        found = self._stops.pop(order_ref, None) is not None
        if found and order_ref in self._orders:
            self._orders[order_ref]["status"] = "cancelled"
        self._rec("cancel_stock_order", ref=order_ref, found=found)
        return found

    def trigger_stop(self, order_ref: str) -> dict:
        """Simulate the market touching a resting stop: fills AT the stop and
        queues a fill event for the next poll_stock_fills()."""
        o = self._stops.pop(order_ref)
        if order_ref in self._orders:
            self._orders[order_ref]["status"] = "filled"
            self._orders[order_ref]["fill_price"] = o["stop_price"]
        self._last_px[o["symbol"]] = o["stop_price"]
        self._positions[o["symbol"]] = (self._positions.get(o["symbol"], 0)
                                        + o["qty"])
        self._fills.append({"order_ref": order_ref, "symbol": o["symbol"],
                            "qty": o["qty"], "fill_price": o["stop_price"]})
        self._rec("stop_triggered", ref=order_ref, symbol=o["symbol"],
                  qty=o["qty"], fill_price=o["stop_price"])
        return {"order_ref": order_ref, "status": "filled",
                "fill_price": o["stop_price"]}

    def trigger_stop_partial(self, order_ref: str, shares: int) -> dict:
        """Simulate a PARTIAL fill at the stop followed by a venue cancel
        (adapter review M3): `shares` fill AT the stop, the remainder is
        cancelled at the venue; ONE aggregated fill event with the SIGNED
        PARTIAL qty queues for the poll — mirroring the real adapter's
        terminal-order emission of a partially-filled-then-cancelled STP."""
        o = self._stops.pop(order_ref)
        sign = -1 if o["qty"] < 0 else 1
        shares = min(shares, abs(o["qty"]))
        if order_ref in self._orders:
            self._orders[order_ref]["status"] = "cancelled"
            self._orders[order_ref]["fill_price"] = o["stop_price"]
        self._last_px[o["symbol"]] = o["stop_price"]
        self._positions[o["symbol"]] = (self._positions.get(o["symbol"], 0)
                                        + sign * shares)
        self._fills.append({"order_ref": order_ref, "symbol": o["symbol"],
                            "qty": sign * shares,
                            "fill_price": o["stop_price"]})
        self._rec("stop_triggered", ref=order_ref, symbol=o["symbol"],
                  qty=sign * shares, fill_price=o["stop_price"],
                  partial=True)
        return {"order_ref": order_ref, "status": "cancelled",
                "fill_price": o["stop_price"]}

    def poll_stock_fills(self) -> list[dict]:
        """Drain queued stop-fill events (read-only: not logged as an intent)."""
        out, self._fills = self._fills, []
        return out

    def requeue_stock_fills(self, fills: list[dict]) -> None:
        """Push un-ingested fill events back to the FRONT of the queue —
        reconcile re-queues on a mid-ingestion failure so a raising save()
        or alert callback never loses a venue fill (counter-agent N3)."""
        self._fills[:0] = list(fills)

    def find_stock_order(self, client_order_id: str) -> dict | None:
        rec = self._orders.get(self._by_client.get(client_order_id, ""))
        return self._order_result(rec) if rec is not None else None

    def stock_position(self, symbol: str) -> int:
        """Net venue holding for symbol, from filled orders — mirrors the
        IBAdapter positions surface (the R1 blackout guard's positive-
        verification basis)."""
        return self._positions.get(symbol, 0)
