"""Hyperliquid venue adapter — same Venue protocol as cb.CoinbaseVenue.

WHY THIS EXISTS (2026-08-28, Casey's call after the phantom-position
incident). The whole 2026-08-26 incident class is a Coinbase-shaped
problem, and three of its worst properties simply do not exist here:

  1. `place_stop` on Coinbase is NOT reduce-only, so a stop the venue
     cannot back OPENS a position. Every naked-stop finding in the hotfix
     chain traces to that one fact. Hyperliquid has a native `reduce_only`
     flag, so a stop that fires against a flat book is a NO-OP instead of a
     new position. This adapter sets reduce_only=True on every protective
     order and there is a gate test that fails if it is ever dropped.
  2. Coinbase omits FLAT products from /cfm/positions, so "flat" and
     "the read failed" were the SAME response shape - that ambiguity is
     what blinded the executor for three days. Hyperliquid returns a
     user_state whose assetPositions list either contains our coin or does
     not, inside a response that either arrives or raises. Flat is
     unambiguous.
  3. Coinbase client order ids needed a persisted cloid->order_id map
     (cb_order_map.json), whose non-atomic writes were an open fast-follow.
     Hyperliquid cancels and queries BY cloid natively, and this adapter
     derives the 16-byte cloid deterministically from our own string id -
     so there is no map, no persistence, and no way for a crash to lose
     the handle to a live order.

It also hands us two things we were about to build by hand:
  - `Info.open_orders()` is the F1 open-orders sweep, natively.
  - `Exchange.schedule_cancel()` is a venue-side dead-man's switch: the
     book auto-cancels if we stop heartbeating. NOT wired up here (it is a
     behaviour change, not an adapter concern) but noted for the ramp.

WHAT IS *NOT* FIXED BY THE VENUE CHANGE, and must not be assumed away:
  - Two legs still net into ONE BTC position, so the disclosed netting
    limit in EXECUTOR.md still applies: a ledger whose legs cancel is
    still indistinguishable from a phantom one on a position read alone.
    reduce_only makes the STOP safe there; it does not make the ledger
    true.
  - Hyperliquid margin is isolated/cross USDC with an explicit
    liquidationPx. That is a DIFFERENT risk shape from Coinbase portfolio
    margin and the halt rails were calibrated against the latter.
  - Every mirror-level safety rail (corroboration, halt ordering, ledger
    discipline) still applies. This is an adapter swap, not a rewrite.
"""
from __future__ import annotations

import hashlib
import logging
import time

logger = logging.getLogger(__name__)

# Protective/entry orders are sent as aggressive IOC limits rather than a
# "market" type (Hyperliquid has none). This is the crossing allowance.
DEFAULT_SLIPPAGE = 0.02


def derive_cloid(our_cloid: str) -> str:
    """Our string ids -> Hyperliquid's 16-byte hex cloid, DETERMINISTICALLY.

    Deterministic derivation, not a stored map, is the point: cb.py needed
    cb_order_map.json to translate ids, and a non-atomic write to that file
    could lose the only handle to a live order (open fast-follow F4). Here
    the handle is recomputable from the id at any time, on any process,
    after any crash. sha256 truncated to 16 bytes - collision risk across
    the handful of ids a position ever uses is nil, and our ids already
    carry burned-before-send salts so they never repeat in the first place.
    """
    return "0x" + hashlib.sha256(our_cloid.encode()).hexdigest()[:32]


class HyperliquidVenue:
    def __init__(self, cfg):
        # lazy import: the test suite must never need the SDK installed
        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        self.cfg = cfg
        self.coin = getattr(cfg, "hl_coin", "BTC")
        base = (constants.TESTNET_API_URL if getattr(cfg, "hl_testnet", False)
                else constants.MAINNET_API_URL)
        # The AGENT (API) wallet signs trades and CANNOT withdraw - the same
        # separation of powers as the Coinbase trade-only key, enforced by
        # the venue rather than by our own care. account_address is the MAIN
        # account the agent trades for; if unset the SDK uses the signer.
        wallet = Account.from_key(cfg.hl_secret_key)
        self.address = getattr(cfg, "hl_account_address", "") or wallet.address
        self.info = Info(base, skip_ws=True)
        self.exchange = Exchange(wallet, base, account_address=self.address)
        self._meta = self._coin_meta()
        self._mid_cache: tuple[float, float] | None = None
        self.post_only_crosses: list[str] = []
        logger.info("hyperliquid venue ready: coin=%s addr=%s meta=%s",
                    self.coin, self.address, self._meta)

    @staticmethod
    def _sdk_cloid(our_cloid: str) -> str:
        """Our string id -> the venue's raw 16-byte hex cloid."""
        return derive_cloid(our_cloid)

    # ---------- discovery / meta ----------

    def _coin_meta(self) -> dict:
        for u in (self.info.meta() or {}).get("universe", []):
            if u.get("name") == self.coin:
                return {"sz_decimals": int(u.get("szDecimals", 3)),
                        "max_leverage": u.get("maxLeverage"),
                        "isolated_only": bool(u.get("onlyIsolated"))}
        raise RuntimeError(
            f"{self.coin} is not in the Hyperliquid perp universe - check "
            f"HL_COIN")

    def list_perp_candidates(self) -> list[str]:
        """Diagnostic banner, same contract as cb.py: the CONFIGURED coin is
        always present and labelled, even when discovery fails, because a
        banner that can omit the thing we trade misdirected a live incident
        diagnosis once already (2026-08-27)."""
        found: dict[str, str] = {}
        try:
            for u in (self.info.meta() or {}).get("universe", []):
                nm = u.get("name", "")
                if nm and ("BTC" in nm.upper() or nm == self.coin):
                    found[nm] = (f"{nm} [maxLev {u.get('maxLeverage')}"
                                 f"{' ISOLATED-ONLY' if u.get('onlyIsolated') else ''}"
                                 f"{' DELISTED' if u.get('isDelisted') else ''}]")
        except Exception as exc:  # noqa: BLE001
            logger.warning("hl universe discovery failed: %s", exc)
        if self.coin in found:
            found[self.coin] += " (configured)"
        else:
            found[self.coin] = f"{self.coin} [CONFIGURED but NOT FOUND in universe]"
        return sorted(found.values())

    @property
    def product_flags(self) -> dict:
        """Boot-time tradability, read by the mirror's _check_product_tradable."""
        return {"view_only": False,
                "trading_disabled": bool(self._meta.get("delisted")),
                "venue": "hyperliquid"}

    # ---------- size/price rounding ----------

    def quantize(self, qty_btc: float) -> float:
        """Largest venue-representable size <= qty_btc. Rounds DOWN, always:
        the executor may under-fill its target but must never size above it."""
        step = 10.0 ** -self._meta["sz_decimals"]
        return int(abs(qty_btc) / step + 1e-9) * step * (1 if qty_btc >= 0 else -1)

    def _sz(self, qty: float) -> float:
        q = self.quantize(abs(qty))
        if q <= 0:
            raise ValueError(
                f"size {qty} is below one lot (1e-{self._meta['sz_decimals']})")
        return round(q, self._meta["sz_decimals"])

    # ---------- reads ----------

    def _user_state(self) -> dict:
        st = self.info.user_state(self.address)
        if not isinstance(st, dict):
            raise RuntimeError(f"user_state returned {type(st).__name__}, not a dict")
        return st

    def equity(self) -> float:
        st = self._user_state()
        v = ((st.get("marginSummary") or {}).get("accountValue"))
        if v is None:
            raise RuntimeError("user_state carried no marginSummary.accountValue")
        return float(v)

    def position(self) -> float:
        """Signed BTC position. A clean response with no row for our coin is
        a CONFIRMED FLAT and returns 0.0; only a genuine API failure raises.

        This is the distinction Coinbase could not make - there, flat and
        broken were the same shape, and the executor spent three days unable
        to tell them apart. Here the response either arrives (and either
        lists our coin or does not) or it raises."""
        st = self._user_state()
        for ap in st.get("assetPositions", []):
            p = (ap or {}).get("position") or {}
            if p.get("coin") == self.coin:
                szi = p.get("szi")
                if szi is None:
                    raise RuntimeError(
                        f"{self.coin} position row carried no szi: {p}")
                return float(szi)          # already SIGNED; no side to guess
        return 0.0

    def liquidation_px(self) -> float | None:
        """Isolated-margin liquidation price, or None when flat/cross with
        no estimate. Not part of the Venue protocol - exposed because HL
        margin is a different risk shape from Coinbase portfolio margin and
        the halt rails were calibrated against the latter."""
        try:
            for ap in self._user_state().get("assetPositions", []):
                p = (ap or {}).get("position") or {}
                if p.get("coin") == self.coin and p.get("liquidationPx"):
                    return float(p["liquidationPx"])
        except Exception:  # noqa: BLE001
            return None
        return None

    def mid(self) -> float:
        now = time.time()
        if self._mid_cache and now - self._mid_cache[0] < 5:
            return self._mid_cache[1]
        mids = self.info.all_mids() or {}
        px = mids.get(self.coin)
        if px is None:
            raise RuntimeError(f"all_mids carried no {self.coin}")
        mid = float(px)
        self._mid_cache = (now, mid)
        return mid

    def order_status(self, cloid: str) -> dict | None:
        """OPEN | FILLED | CANCELLED | UNKNOWN, never a bare None on error.

        Same contract cb.py had to be dragged to: an API failure is NOT
        "no such order". None means only "we have no handle" - and since
        cloids are derived deterministically we always have a handle, so in
        practice None never happens here."""
        try:
            from hyperliquid.utils.types import Cloid
            r = self.info.query_order_by_cloid(
                self.address, Cloid.from_str(derive_cloid(cloid)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("order_status(%s) failed: %s", cloid, exc)
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        if not isinstance(r, dict) or r.get("status") == "unknownOid":
            # the venue affirmatively does not know this id
            return {"status": "CANCELLED", "filled_qty": 0.0, "avg_price": None}
        o = (r.get("order") or {})
        inner = (o.get("order") or {})
        raw = (o.get("status") or "").lower()
        # Only TERMINAL states map to CANCELLED. Anything transitional is
        # OPEN, because a transitional order that reads CANCELLED provokes a
        # duplicate placement (the Coinbase QUEUED lesson, unchanged here).
        if raw == "filled":
            status = "FILLED"
        elif raw in ("canceled", "cancelled", "rejected", "marginCanceled".lower(),
                     "expired", "liquidatedcanceled", "vaultwithdrawalcanceled",
                     "openinterestcapcanceled", "selftradecanceled",
                     "reduceonlycanceled", "siblingfilledcanceled",
                     "scheduledcancel"):
            status = "CANCELLED"
        elif raw in ("open", "triggered", "resting", "queued", "pending"):
            status = "OPEN"
        else:
            logger.warning("order_status(%s): unmapped raw status %r", cloid, raw)
            return {"status": "UNKNOWN", "filled_qty": 0.0, "avg_price": None}
        total = float(inner.get("origSz") or 0.0)
        left = float(inner.get("sz") or 0.0)
        filled = max(0.0, total - left) if total else 0.0
        if status == "FILLED" and filled <= 0.0:
            filled = total
        avg = inner.get("avgPx") or o.get("avgPx")
        return {"status": status, "filled_qty": filled,
                "avg_price": float(avg) if avg else None}

    def open_orders(self) -> list[dict]:
        """Every resting order for our coin. This is the F1 open-orders
        sweep the Coinbase build had to plan for and never got: the one
        check that can catch an armed order the ledger has forgotten,
        including on a hedged book where a position read tells us nothing."""
        out = []
        for o in (self.info.open_orders(self.address) or []):
            if o.get("coin") != self.coin:
                continue
            out.append({"oid": o.get("oid"), "cloid": o.get("cloid"),
                        "side": "BUY" if o.get("side") == "B" else "SELL",
                        "sz": float(o.get("sz") or 0.0),
                        "px": float(o.get("limitPx") or 0.0),
                        "trigger_px": float(o.get("triggerPx") or 0.0)
                        if o.get("triggerPx") else None,
                        "reduce_only": bool(o.get("reduceOnly"))})
        return out

    # ---------- mutations ----------

    def _send(self, cloid: str, **kw):
        from hyperliquid.utils.types import Cloid
        r = self.exchange.order(self.coin, cloid=Cloid.from_str(derive_cloid(cloid)),
                                **kw)
        if not isinstance(r, dict) or r.get("status") != "ok":
            raise RuntimeError(f"order rejected: {r}")
        statuses = (((r.get("response") or {}).get("data") or {})
                    .get("statuses") or [])
        for s in statuses:
            if isinstance(s, dict) and "error" in s:
                raise RuntimeError(f"order rejected: {s['error']}")
        return r

    def place_limit(self, side: str, qty: float, px: float, cloid: str,
                    post_only: bool = True) -> None:
        try:
            self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                       limit_px=float(px), reduce_only=False,
                       order_type={"limit": {"tif": "Alo" if post_only else "Gtc"}})
        except RuntimeError as exc:
            # Post-only that would cross is REJECTED, same as Coinbase at a
            # positive basis. Crossing fills at our limit or better, so retry
            # as a normal limit and pay taker - and record the cross for the
            # ramp's post_only_cross coverage row.
            if post_only and "post only" in str(exc).lower():
                logger.warning("Alo rejected (would cross); retrying Gtc: %s", cloid)
                self.post_only_crosses.append(cloid)
                self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                           limit_px=float(px), reduce_only=False,
                           order_type={"limit": {"tif": "Gtc"}})
            else:
                raise

    def place_stop(self, side: str, qty: float, trigger_px: float,
                   cloid: str) -> None:
        """Protective stop as a native REDUCE-ONLY trigger order.

        reduce_only=True is the single most important line in this file. On
        Coinbase this order could OPEN a position when the venue did not
        back the ledger, and every naked-stop finding in the 2026-08 hotfix
        chain descends from that. Here the venue itself refuses: a stop that
        fires against a flat or opposite book cancels instead of trading.
        It is defence in depth, NOT a licence to skip the mirror's
        corroboration - a stop that silently cancels is still a position
        left unprotected, which the mirror must still notice."""
        px = float(trigger_px)
        # isMarket=True: fire at market on trigger. The limit_px is the
        # crossing bound the SDK uses for the resulting IOC.
        bound = px * (1 - DEFAULT_SLIPPAGE) if side == "SELL" \
            else px * (1 + DEFAULT_SLIPPAGE)
        self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                   limit_px=bound, reduce_only=True,
                   order_type={"trigger": {"triggerPx": px, "isMarket": True,
                                           "tpsl": "sl"}})

    def place_market(self, side: str, qty: float, cloid: str) -> None:
        """Aggressive IOC. Hyperliquid has no market type; crossing by
        DEFAULT_SLIPPAGE is what market_open does internally, done here so
        the cloid and rejection handling stay on one path."""
        mid = self.mid()
        bound = mid * (1 + DEFAULT_SLIPPAGE) if side == "BUY" \
            else mid * (1 - DEFAULT_SLIPPAGE)
        self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                   limit_px=bound, reduce_only=False,
                   order_type={"limit": {"tif": "Ioc"}})

    def cancel(self, cloid: str) -> None:
        from hyperliquid.utils.types import Cloid
        try:
            self.exchange.cancel_by_cloid(
                self.coin, Cloid.from_str(derive_cloid(cloid)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel(%s) failed: %s", cloid, exc)

    def cancel_all(self) -> None:
        from hyperliquid.utils.types import Cloid
        try:
            reqs = [{"coin": self.coin, "cloid": Cloid.from_str(o["cloid"])}
                    for o in self.open_orders() if o.get("cloid")]
            if reqs:
                self.exchange.bulk_cancel_by_cloid(reqs)
            # orders placed without a cloid (never by us, but a human might)
            oids = [o["oid"] for o in self.open_orders()
                    if not o.get("cloid") and o.get("oid")]
            for oid in oids:
                self.exchange.cancel(self.coin, oid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel_all failed: %s", exc)
