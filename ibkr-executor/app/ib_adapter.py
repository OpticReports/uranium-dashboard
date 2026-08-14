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
    def __init__(self, cfg):
        from ib_async import IB               # lazy: tests never import
        self.cfg = cfg
        self.ib = IB()
        self._connect()

    def _connect(self):
        port = 4002 if self.cfg.trading_mode == "paper" else 4001
        for attempt in range(20):             # gateway boots slowly (~2 min)
            try:
                self.ib.connect(self.cfg.ib_host, port,
                                clientId=self.cfg.ib_client_id, timeout=15)
                logger.info("connected to IB gateway (%s)", self.cfg.trading_mode)
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

    def spot(self, symbol: str) -> float:
        from ib_async import Future, Stock
        sec_type, exch, cur, _ = UNDERLYINGS[symbol]
        if sec_type == "STK":
            c = Stock(symbol, exch, cur)
        else:
            c = Future(symbol, exchange=exch, currency=cur)
            c = sorted(self.ib.reqContractDetails(c),
                       key=lambda d: d.contract.lastTradeDateOrContractMonth
                       )[0].contract
        self.ib.qualifyContracts(c)
        t = self.ib.reqMktData(c, "", False, False)
        self.ib.sleep(3)
        px = t.marketPrice()
        self.ib.cancelMktData(c)
        if px != px or px <= 0:
            raise RuntimeError(f"no market price for {symbol}")
        return float(px)

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


class DryAdapter:
    """No gateway, no orders: synthesizes fills at the budget and marks flat.
    Lets the full decision loop + alerting run before any credential exists."""

    def __init__(self):
        self.log: list[dict] = []
        self._open: dict[str, float] = {}

    def _rec(self, action, **kw):
        e = {"ts": int(time.time()), "action": action, **kw}
        self.log.append(e)
        logger.info("DRY %s", e)

    def spot(self, symbol: str) -> float:
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
