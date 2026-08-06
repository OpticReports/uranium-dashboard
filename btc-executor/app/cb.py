"""Coinbase Advanced Trade venue adapter (perpetual futures).

Wraps the official coinbase-advanced-py RESTClient behind the Venue protocol
the mirror expects. Key is a CDP trade-only key (view + trade scopes; NO
transfer/withdraw). Supports both product conventions:
  - INTX perps (BTC-PERP-INTX): fractional BTC sizes, USDC collateral
  - US CFM/CDE futures (nano contracts): integer contracts, 0.01 BTC each

Order mapping:
  place_limit  -> limit GTC (post_only honored where the venue allows it)
  place_stop   -> stop-limit GTC; the limit is offset past the trigger so it
                  behaves like a stop-market in practice
  place_market -> market IOC
  cancel       -> cancel by client_order_id (resolved to venue order id)

The adapter keeps a cloid -> order_id map persisted next to executor state, so
restarts can still cancel/inspect orders placed before the restart.
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)


class CoinbaseVenue:
    def __init__(self, cfg):
        from coinbase.rest import RESTClient  # lazy: tests never import this
        self.cfg = cfg
        self.client = RESTClient(api_key=cfg.cb_api_key_name,
                                 api_secret=cfg.cb_api_private_key)
        self.product_id = cfg.cb_product_id
        self._map_path = os.path.join(
            os.path.dirname(cfg.state_path) or ".", "cb_order_map.json")
        try:
            self._orders = json.load(open(self._map_path))
        except Exception:  # noqa: BLE001
            self._orders = {}
        self._meta = self._product_meta()
        self._mid_cache: tuple[float, float] | None = None
        logger.info("coinbase venue ready: %s meta=%s", self.product_id, self._meta)

    # ---------- discovery / meta ----------

    def _product_meta(self) -> dict:
        p = self.client.get_product(self.product_id).to_dict()
        f = p.get("future_product_details") or {}
        mult = float(f.get("contract_size") or 0) or None
        return {"base_increment": float(p.get("base_increment") or 0.0001),
                "price_increment": float(p.get("price_increment") or 0.1),
                "contract_multiplier": mult}   # None => sizes are plain BTC

    def list_perp_candidates(self) -> list[str]:
        """BTC futures/perp products this account can see, across query
        variants - used at boot to pick the right CB_PRODUCT_ID (INTX vs CFM
        dated vs US perpetual-style)."""
        found: dict[str, str] = {}
        for kw in ({"product_type": "FUTURE"},
                   {"product_type": "FUTURE", "contract_expiry_type": "PERPETUAL"},
                   {"product_type": "FUTURE", "product_venue": "FCM"}):
            try:
                out = self.client.get_products(**kw).to_dict()
                for p in out.get("products", []):
                    pid = p.get("product_id", "")
                    if "BTC" in pid.upper() or "BIT" in pid.upper():
                        found.setdefault(
                            pid, f"{pid} [{p.get('product_venue')}"
                                 f"{' view_only' if p.get('view_only') else ''}]")
            except Exception as exc:  # noqa: BLE001
                logger.warning("product discovery %s failed: %s", kw, exc)
        # direct probes for ids the listings sometimes omit
        for pid in ("BTC-PERP-CDE", "BTC-PERP-INTX"):
            if pid in found:
                continue
            try:
                p = self.client.get_product(pid).to_dict()
                if p.get("product_id"):
                    found[pid] = (f"{pid} [{p.get('product_venue')}"
                                  f"{' view_only' if p.get('view_only') else ''}"
                                  f"{' DISABLED' if p.get('trading_disabled') else ''}]")
            except Exception:  # noqa: BLE001
                pass
        return sorted(found.values())

    # ---------- size/price rounding ----------

    def _to_venue_size(self, qty_btc: float) -> str:
        mult = self._meta["contract_multiplier"]
        if mult:                                  # contract-based (CDE)
            return str(max(1, round(qty_btc / mult)))
        inc = self._meta["base_increment"]
        steps = max(1, int(qty_btc / inc))
        return f"{steps * inc:.8f}".rstrip("0").rstrip(".")

    def _to_venue_px(self, px: float) -> str:
        inc = self._meta["price_increment"]
        return f"{round(px / inc) * inc:.10f}".rstrip("0").rstrip(".")

    # ---------- reads ----------

    def equity(self) -> float:
        """Total futures/perp account value in USD(C)."""
        try:
            bal = self.client.get_futures_balance_summary().to_dict()
            bs = bal.get("balance_summary", {})
            v = bs.get("total_usd_balance", {}).get("value")
            if v:
                return float(v)
        except Exception:  # noqa: BLE001
            pass
        # INTX portfolio fallback
        ports = self.client.get_portfolios().to_dict().get("portfolios", [])
        for p in ports:
            if p.get("type") == "INTX" or p.get("uuid") == self.cfg.cb_portfolio:
                bd = self.client.get_portfolio_breakdown(p["uuid"]).to_dict()
                tot = (bd.get("breakdown", {}).get("portfolio_balances", {})
                       .get("total_balance", {}).get("value"))
                if tot:
                    return float(tot)
        raise RuntimeError("could not read account equity")

    def position(self) -> float:
        """Signed BTC position for the product (contracts * multiplier)."""
        mult = self._meta["contract_multiplier"] or 1.0
        try:
            pos = self.client.list_futures_positions().to_dict()
            for p in pos.get("positions", []):
                if p.get("product_id") == self.product_id:
                    n = float(p.get("number_of_contracts") or 0)
                    sgn = 1.0 if p.get("side", "").upper() == "LONG" else -1.0
                    return sgn * n * mult
        except Exception:  # noqa: BLE001
            pass
        try:
            p = self.client.get_intx_position(self.cfg.cb_portfolio,
                                              self.product_id).to_dict()
            n = float(p.get("position", {}).get("net_size") or 0)
            return n
        except Exception:  # noqa: BLE001
            return 0.0

    def mid(self) -> float:
        now = time.time()
        if self._mid_cache and now - self._mid_cache[0] < 5:
            return self._mid_cache[1]
        book = self.client.get_product_book(product_id=self.product_id,
                                            limit=1).to_dict()
        pb = book.get("pricebook", {})
        bid = float(pb["bids"][0]["price"]) if pb.get("bids") else 0.0
        ask = float(pb["asks"][0]["price"]) if pb.get("asks") else 0.0
        mid = (bid + ask) / 2 if bid and ask else (bid or ask)
        self._mid_cache = (now, mid)
        return mid

    def order_status(self, cloid: str) -> dict | None:
        oid = self._orders.get(cloid)
        if not oid:
            return None
        try:
            o = self.client.get_order(oid).to_dict().get("order", {})
            status = {"OPEN": "OPEN", "FILLED": "FILLED"}.get(
                o.get("status"), "CANCELLED")
            mult = self._meta["contract_multiplier"] or 1.0
            filled = float(o.get("filled_size") or 0)
            if self._meta["contract_multiplier"]:
                filled *= mult
            return {"status": status, "filled_qty": filled}
        except Exception as exc:  # noqa: BLE001
            logger.warning("order_status(%s) failed: %s", cloid, exc)
            return None

    # ---------- mutations ----------

    def _remember(self, cloid: str, resp) -> None:
        d = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
        oid = (d.get("success_response") or {}).get("order_id") or d.get("order_id")
        if not d.get("success", oid is not None):
            raise RuntimeError(f"order rejected: {d}")
        self._orders[cloid] = oid
        json.dump(self._orders, open(self._map_path, "w"))

    def place_limit(self, side: str, qty: float, px: float, cloid: str,
                    post_only: bool = True) -> None:
        r = self.client.limit_order_gtc(
            client_order_id=cloid, product_id=self.product_id, side=side,
            base_size=self._to_venue_size(qty), limit_price=self._to_venue_px(px),
            post_only=post_only)
        self._remember(cloid, r)

    def place_stop(self, side: str, qty: float, trigger_px: float,
                   cloid: str) -> None:
        off = self.cfg.stop_limit_offset_pct / 100.0
        limit_px = trigger_px * (1 - off) if side == "SELL" else trigger_px * (1 + off)
        direction = ("STOP_DIRECTION_STOP_DOWN" if side == "SELL"
                     else "STOP_DIRECTION_STOP_UP")
        r = self.client.stop_limit_order_gtc(
            client_order_id=cloid, product_id=self.product_id, side=side,
            base_size=self._to_venue_size(qty),
            limit_price=self._to_venue_px(limit_px),
            stop_price=self._to_venue_px(trigger_px), stop_direction=direction)
        self._remember(cloid, r)

    def place_market(self, side: str, qty: float, cloid: str) -> None:
        r = self.client.market_order(
            client_order_id=cloid, product_id=self.product_id, side=side,
            base_size=self._to_venue_size(qty))
        self._remember(cloid, r)

    def cancel(self, cloid: str) -> None:
        oid = self._orders.get(cloid)
        if oid:
            try:
                self.client.cancel_orders([oid])
            except Exception as exc:  # noqa: BLE001
                logger.warning("cancel(%s) failed: %s", cloid, exc)

    def cancel_all(self) -> None:
        try:
            out = self.client.list_orders(product_ids=[self.product_id],
                                          order_status=["OPEN"]).to_dict()
            oids = [o["order_id"] for o in out.get("orders", [])]
            if oids:
                self.client.cancel_orders(oids)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel_all failed: %s", exc)


class DryRunVenue:
    """Wraps a real (or absent) venue: reads pass through when available,
    mutations only log and simulate naive fills so the state machine cycles.
    With no inner venue (no API key yet), synthesizes a small test account.
    Simulated orders + the intent log persist to disk so a service restart
    keeps the shadow book consistent with the persisted executor ledger."""

    def __init__(self, inner=None, equity_fallback: float = 10_000.0,
                 persist_path: str | None = None):
        self.inner = inner
        self._equity = equity_fallback
        self._last_good: float | None = None
        self.persist_path = persist_path
        self.orders: dict[str, dict] = {}
        self.log: list[dict] = []
        if persist_path:
            try:
                d = json.load(open(persist_path))
                self.orders = d.get("orders", {})
                self.log = d.get("log", [])[-500:]
                self._last_good = d.get("last_good_equity")
            except Exception:  # noqa: BLE001
                pass

    def _persist(self) -> None:
        if not self.persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
            json.dump({"orders": self.orders, "log": self.log[-500:],
                       "last_good_equity": self._last_good},
                      open(self.persist_path, "w"))
        except Exception:  # noqa: BLE001
            pass

    def _rec(self, action: str, **kw) -> None:
        entry = {"ts": int(time.time()), "action": action, **kw}
        self.log.append(entry)
        logger.info("DRY-RUN %s", entry)
        self._persist()

    def equity(self) -> float:
        """Real read when possible; a FAILED or zero read falls back to the
        last-known-good value, never a made-up number — a transient API
        hiccup must not read as a drawdown (the false DRAWDOWN halt of
        2026-08-06). Static fallback only before any real read succeeds."""
        if self.inner:
            try:
                v = self.inner.equity()
                if v > 0:
                    if v != self._last_good:
                        self._last_good = v
                        self._persist()
                    return v
            except Exception:  # noqa: BLE001
                pass
        if self._last_good and self._last_good > 0:
            return self._last_good
        return self._equity

    def position(self) -> float:
        filled = [o for o in self.orders.values() if o["status"] == "FILLED"]
        return sum((1 if o["side"] == "BUY" else -1) * o["qty"] for o in filled)

    def mid(self) -> float:
        if self.inner:
            try:
                return self.inner.mid()
            except Exception:  # noqa: BLE001
                pass
        return 60_000.0

    def order_status(self, cloid: str) -> dict | None:
        o = self.orders.get(cloid)
        if not o:
            return None
        # naive fill model: limits fill when the live mid trades through them
        if o["status"] == "OPEN" and o["type"] == "LIMIT":
            m = self.mid()
            if (o["side"] == "BUY" and m <= o["px"]) or \
                    (o["side"] == "SELL" and m >= o["px"]):
                o["status"] = "FILLED"
        return {"status": o["status"],
                "filled_qty": o["qty"] if o["status"] == "FILLED" else 0.0}

    def place_limit(self, side, qty, px, cloid, post_only=True):
        self.orders[cloid] = {"type": "LIMIT", "side": side, "qty": qty,
                              "px": px, "status": "OPEN"}
        self._rec("place_limit", side=side, qty=qty, px=px, cloid=cloid)

    def place_stop(self, side, qty, trigger_px, cloid):
        self.orders[cloid] = {"type": "STOP", "side": side, "qty": qty,
                              "px": trigger_px, "status": "OPEN"}
        self._rec("place_stop", side=side, qty=qty, trigger=trigger_px, cloid=cloid)

    def place_market(self, side, qty, cloid):
        self.orders[cloid] = {"type": "MARKET", "side": side, "qty": qty,
                              "px": self.mid(), "status": "FILLED"}
        self._rec("place_market", side=side, qty=qty, cloid=cloid)

    def cancel(self, cloid):
        if cloid in self.orders and self.orders[cloid]["status"] == "OPEN":
            self.orders[cloid]["status"] = "CANCELLED"
        self._rec("cancel", cloid=cloid)

    def cancel_all(self):
        for c, o in self.orders.items():
            if o["status"] == "OPEN":
                o["status"] = "CANCELLED"
        self._rec("cancel_all")
