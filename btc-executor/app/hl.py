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
import math
import time

logger = logging.getLogger(__name__)

# Protective/entry orders are sent as aggressive IOC limits rather than a
# "market" type (Hyperliquid has none). This is the crossing allowance.
DEFAULT_SLIPPAGE = 0.02

# Hyperliquid rejects any order under $10 notional ("Order must have minimum
# value of $10", MinTradeNtl). The docs do NOT grant reduce-only an
# exemption, so we must assume a sub-$10 position CANNOT BE CLOSED BY ORDER
# - not by its stop, not by the halt's flatten. See MinNotionalRejected.
MIN_NOTIONAL_USD = 10.0


class MinNotionalRejected(RuntimeError):
    """An order was refused for being under the venue's $10 minimum.

    Called out as its own type because of what it means on the PROTECTIVE
    path: a position whose remaining notional is under $10 cannot be closed
    by any order we send, so the stop is unplaceable AND the halt's flatten
    fails too - an open, unprotected residue that only a manual close on
    the Hyperliquid UI clears. Sizing keeps this far away (the smaller leg
    is ~5x the floor at KELLY_M 0.135 on a $1k base), so it takes an
    extreme partial fill to reach; the point of the named error is that
    when it does happen the page says WHY instead of looking like a generic
    rejection storm. Disclosed in EXECUTOR.md rather than engineered
    around: no order-level rail can close a position the venue will not
    accept an order for."""


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
        # WHICH NETWORK. Recorded, not just used, because it was invisible
        # (2026-08-28): with HL_TESTNET truthy every info call answered about
        # a DIFFERENT chain, so extraAgents came back empty and userRole said
        # 'missing' for a key that is properly approved on mainnet - and the
        # agent rail read that as "your key is not approved". The account,
        # the key and the matching logic were all correct; they were being
        # asked about the wrong network, and nothing published which one.
        # Worse than the misdiagnosis: position() answers 0.0 from an empty
        # testnet account as a CONFIRMED FLAT while the real mainnet book
        # sits untouched, with a perfectly fresh venue_read_age_s - the
        # phantom-position shape, reached through a single boolean.
        self.testnet = bool(getattr(cfg, "hl_testnet", False))
        self.network = "testnet" if self.testnet else "mainnet"
        base = (constants.TESTNET_API_URL if self.testnet
                else constants.MAINNET_API_URL)
        # The AGENT (API) wallet signs trades and CANNOT withdraw - the same
        # separation of powers as the Coinbase trade-only key, enforced by
        # the venue rather than by our own care. account_address is the MAIN
        # account the agent trades for; if unset the SDK uses the signer.
        wallet = Account.from_key(cfg.hl_secret_key)
        # HL_ACCOUNT_ADDRESS IS MANDATORY (2026-08-28, caught while Casey was
        # on the API-wallet screen). An agent wallet SIGNS for a main account
        # but HOLDS NOTHING ITSELF, and Hyperliquid's own UI says it: "the
        # account's public address must be used for info requests". Falling
        # back to the signer's address would query the AGENT - which has no
        # positions - so position() would return 0.0 as a CONFIRMED FLAT,
        # forever, while the real account carried the book. That is the
        # 2026-08-26 phantom-position failure mode exactly, re-entered
        # through config instead of through a dead SDK method. There is no
        # safe guess here, so refuse to construct.
        self.address = str(getattr(cfg, "hl_account_address", "") or "").strip()
        if not self.address:
            raise RuntimeError(
                "HL_ACCOUNT_ADDRESS is required: it is the MAIN account's "
                "public address, which is what info/position requests read. "
                "An agent (API) wallet signs on the account's behalf and "
                "holds nothing itself, so defaulting to the signer would "
                "report the book as permanently FLAT.")
        if self.address.lower() == wallet.address.lower():
            # Not fatal - trading with the main account's OWN key is a valid
            # (if less safe) setup - but it means no agent wallet is in play,
            # so the venue is NOT enforcing the no-withdrawal separation and
            # the operator should know which of the two they deployed.
            logger.warning(
                "HL_ACCOUNT_ADDRESS equals the signing key's own address: "
                "this is the MAIN account key, not an agent wallet. Trading "
                "works, but the venue is not enforcing withdrawal separation.")
        self.agent_address = wallet.address
        # set by agent_valid_until when the signer is not an approved
        # agent: the halt page carries it so the operator sees WHICH
        # key was deployed vs which are approved, not just a date
        self.agent_note: str | None = None
        self.info = Info(base, skip_ws=True)
        self.exchange = Exchange(wallet, base, account_address=self.address)
        self._meta = self._coin_meta()
        self._mid_cache: tuple[float, float] | None = None
        self._abs_cache: tuple[float, bool] | None = None
        # last equity read decomposed, for the operator: whether the
        # unified spot figure also carries unrealised perp PnL is
        # UNVERIFIED until a live position exists to measure it against.
        self.equity_parts: dict = {}
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

    def _tick(self, px: float) -> float:
        """Smallest legal price increment at this price level.

        Hyperliquid enforces BOTH rules at once: at most 5 significant
        figures, AND at most (6 - szDecimals) decimal places for a perp.
        Whichever is COARSER binds. BTC has szDecimals=5, so the decimal cap
        is 1 - but at ~$78,000 five significant figures is already whole
        dollars, so the sig-fig rule binds and the grid is $1."""
        if not px or px <= 0:
            raise ValueError(f"price must be positive, got {px}")
        exp = math.floor(math.log10(abs(px)))
        return max(10.0 ** (exp - 4),                       # 5 significant figures
                   10.0 ** -(6 - int(self._meta["sz_decimals"])))   # perp decimal cap

    def _px(self, px: float, mode: str = "nearest") -> float:
        """Snap a price onto Hyperliquid's grid, in a chosen DIRECTION.

        THE ORDER-KILLING BUG (2026-08-29, found by review before the first
        live order). The SDK rounds prices ONLY inside its own
        _slippage_price helper, which serves market_open/market_close -
        `Exchange.order()`, which this adapter calls directly, wires whatever
        float it is given. Every price the engine produces carries decimals,
        so at BTC's $1 grid EVERY order was destined to be rejected:
        entries, protective stops, exits, and - the part that matters - the
        halt's own flatten. A halt that cannot place its flatten is a page
        attached to a book it cannot close, which is the naked-position
        outcome this whole rewrite exists to prevent.

        Direction is not cosmetic:
          - a post-only entry must round AWAY from the market, or snapping
            can push it across the spread and lose maker status (or get the
            Alo rejected, forcing the taker retry);
          - a crossing bound must round TOWARD aggression, or snapping can
            pull it back inside the spread so the protective IOC does not
            fill - a stop that triggers and then rests is not protection;
          - a trigger level is a threshold, not a fill, so nearest is right.
        The final pass is the SDK's own expression, so whatever we do here
        the result is a price the venue will accept."""
        dec = max(0, 6 - int(self._meta["sz_decimals"]))
        px = float(px)
        v = round(float(f"{px:.5g}"), dec)
        if mode != "nearest" and v != px:
            t = self._tick(px)
            if mode == "up" and v < px:
                v = v + t
            elif mode == "down" and v > px:
                v = v - t
            v = round(float(f"{v:.5g}"), dec)
        if v <= 0:
            raise ValueError(f"price {px} snapped to {v}, which is not tradable")
        return v

    # ---------- reads ----------

    def _user_state(self) -> dict:
        st = self.info.user_state(self.address)
        if not isinstance(st, dict):
            raise RuntimeError(f"user_state returned {type(st).__name__}, not a dict")
        return st

    def _is_unified(self) -> bool:
        """Is spot collateral backing perps? Cached briefly, never guessed.

        A wrong answer here is not cosmetic: equity() feeds day_start_equity
        and high_water, so understating it kills the halts and overstating
        it loosens them. If the venue will not tell us, we RAISE - the
        caller treats an unreadable venue as a first-class condition, and a
        silent default is exactly how the 2026-08-26 blind read stayed
        invisible for three days."""
        now = time.time()
        if self._abs_cache and now - self._abs_cache[0] < 60.0:
            return self._abs_cache[1]
        r = self.info.query_user_abstraction_state(self.address)
        mode = r if isinstance(r, str) else str((r or {}).get("abstraction", ""))
        unified = "unified" in str(mode).lower()
        self._abs_cache = (now, unified)
        return unified

    def agent_valid_until(self) -> float | None:
        """Epoch seconds at which our SIGNING key stops being able to trade.

        Hyperliquid agent (API) wallets EXPIRE - ours on 2027-02-24. Expiry
        is not a degraded mode, it is a total loss of write access: every
        order is rejected, including the protective ones. If it lapses with
        a position open, the book is naked and the executor cannot even
        flatten itself - the one failure this whole rewrite exists to
        prevent, arriving on a calendar we already know.

        Returns None when the signer IS the main account, which cannot
        expire. Raises when the venue will not say: an unreadable expiry is
        NOT an absent one, and the caller decides how long to tolerate it."""
        if self.agent_address.lower() == self.address.lower():
            return None
        agents = self.info.extra_agents(self.address) or []
        for a in agents:
            # Match on ADDRESS, never on the display name: the name is
            # operator-chosen, editable, and duplicable in the UI, so a
            # name match can point at a DIFFERENT key than the one we sign
            # with - reporting a healthy expiry for a wallet we do not use.
            if str((a or {}).get("address", "")).lower() \
                    == self.agent_address.lower():
                vu = a.get("validUntil")
                if vu is None:
                    raise RuntimeError(f"agent row carried no validUntil: {a}")
                self.agent_note = None
                return float(vu) / 1000.0          # venue reports ms
        # NOT IN extraAgents IS NOT THE SAME AS NOT APPROVED (2026-08-28,
        # second pass — the first cut of this rail got it wrong and would
        # have halted a healthy book). Hyperliquid has TWO kinds of agent:
        # approveAgent WITH an agentName creates a named "extra" agent, and
        # approveAgent with the field ABSENT creates the unnamed/default API
        # wallet (see Exchange.approve_agent: `if name is None: del
        # action["agentName"]`). `extraAgents` enumerates the EXTRA ones —
        # the name is the contract — so a perfectly valid unnamed agent is
        # simply not in that list. Concluding "not approved" from absence
        # would halt a book whose key signs fine, which is precisely the
        # self-inflicted damage the unreadable-expiry branch exists to
        # avoid. So ask the authoritative, name-independent question first.
        role = self.info.user_role(self.agent_address) or {}
        rname = str(role.get("role", "")).lower()
        master = str(((role.get("data") or {}).get("user")) or "")
        if rname == "agent" and master.lower() == self.address.lower():
            # Approved and able to trade — we just cannot see its expiry,
            # because only extraAgents carries validUntil. Raise into the
            # caller's UNREADABLE branch (WARN, never halt): the key works,
            # what is missing is visibility. HL agents still expire, so this
            # is a real gap and the fix is one UI action.
            self.agent_note = None
            raise RuntimeError(
                f"{self.agent_address} is an approved UNNAMED (default) API "
                f"wallet of {self.address}: it can trade, but only NAMED "
                f"agents appear in extraAgents, which is the only source of "
                f"validUntil - so its expiry cannot be tracked. Approve a "
                f"NAMED API wallet and deploy that key to re-arm the rail")
        # Now absence IS definitive: the agent was revoked, or never
        # approved for this account, or HL_SECRET_KEY belongs to someone
        # else's wallet. No order will ever succeed. Surfaced as expired-now
        # so the caller's expiry rail fires instead of a fresh code path.
        #
        # NAME THE MISMATCH (2026-08-28, the rail's first live boot returned
        # exactly this). As a bare 0.0 it reached the operator as
        # "agent_days_left: -20693" and a halt saying "expires in -496648h",
        # which describes the arithmetic rather than the problem. The two
        # addresses ARE the diagnosis, and both are public on-chain values:
        # what we sign with, and what the account actually approved.
        approved = ", ".join(
            f"{(a or {}).get('name', '?')}={(a or {}).get('address', '?')}"
            for a in agents) or "(none)"
        self.agent_note = (
            f"the deployed HL_SECRET_KEY signs as {self.agent_address}, which "
            f"is NOT an approved agent of {self.address}. Approved: "
            f"{approved}. No order can succeed until HL_SECRET_KEY is the "
            f"private key of an approved agent")
        logger.error("hyperliquid agent mismatch: %s", self.agent_note)
        return 0.0

    def _spot_usdc(self) -> float:
        sp = self.info.spot_user_state(self.address) or {}
        for b in sp.get("balances", []):
            if (b or {}).get("coin") == "USDC":
                return float(b.get("total") or 0.0)
        return 0.0

    def equity(self) -> float:
        """Total USD backing the perp book.

        MUST include spot under a unified account (2026-08-28, caught before
        the first live order). Hyperliquid keeps two pools, and
        marginSummary.accountValue reports ONLY the perp one - it read $0.00
        against a real $998.99 sitting in spot. Every circuit breaker is
        equity-derived (day_start_equity for the 6% daily rail, high_water
        for the 35% drawdown), so a constant zero makes every loss compute
        as zero and NO HALT CAN EVER FIRE. Sizing would have been fine,
        because SIZING_BASE_USD is a fixed number - so the book would have
        traded correctly with its rails silently absent, which is the same
        shape as the incident this whole rewrite is about.

        USDC only: other spot tokens may also collateralise under unified,
        but valuing them here would be speculation. Omitting them understates
        equity, and a CONSISTENT understatement is near-harmless because the
        halts compare a DELTA (equity vs day-start/HWM, both measured the
        same way) against a threshold struck off SIZING_BASE_USD, which is a
        fixed config number. That argument holds only while SIZING_BASE_USD
        is set - unset, _base() falls back to equity and an understatement
        would tighten both rails."""
        st = self._user_state()
        v = ((st.get("marginSummary") or {}).get("accountValue"))
        if v is None:
            raise RuntimeError("user_state carried no marginSummary.accountValue")
        perp = float(v)
        if not self._is_unified():
            return perp
        # INSTEAD OF, not IN ADDITION TO (2026-08-29). The first cut of this
        # summed the two pools, which is right only while FLAT - exactly the
        # state it was written and verified in. Hyperliquid's own docs settle
        # it, on clearinghouseState: "Under unified account or portfolio
        # margin, use spot balances endpoint instead for trading account
        # balance across spot and perps." The spot figure ALREADY SPANS both
        # pools, so adding marginSummary on top double-counts the collateral
        # the moment a position pledges any of it - and equity feeds
        # day_start_equity and high_water, so an equity that jumps when a
        # position opens moves both halt thresholds with it.
        spot = self._spot_usdc()
        self.equity_parts = {"perp": perp, "spot": spot}
        return spot

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
                err = str(s["error"])
                if "minimum value" in err.lower():
                    raise MinNotionalRejected(
                        f"order rejected: {err} - a position under "
                        f"${MIN_NOTIONAL_USD:.0f} cannot be closed by ANY "
                        f"order, including its stop and the halt's flatten; "
                        f"close the residue manually on the Hyperliquid UI "
                        f"(cloid {cloid})")
                raise RuntimeError(f"order rejected: {err}")
        return r

    def place_limit(self, side: str, qty: float, px: float, cloid: str,
                    post_only: bool = True) -> None:
        try:
            self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                       limit_px=self._px(px, "down" if side == "BUY" else "up")
                       if post_only else
                       self._px(px, "up" if side == "BUY" else "down"),
                       reduce_only=False,
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
                           limit_px=self._px(px, "up" if side == "BUY" else "down"),
                           reduce_only=False,
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
        # trigger = a threshold, so nearest. bound = must CROSS when it
        # fires, so snap toward aggression: a bound rounded back inside the
        # spread turns a protective stop into a resting order, which is not
        # protection at all.
        self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                   limit_px=self._px(bound, "up" if side == "BUY" else "down"),
                   reduce_only=True,
                   order_type={"trigger": {"triggerPx": self._px(px),
                                          "isMarket": True,
                                           "tpsl": "sl"}})

    def place_market(self, side: str, qty: float, cloid: str) -> None:
        """Aggressive IOC. Hyperliquid has no market type; crossing by
        DEFAULT_SLIPPAGE is what market_open does internally, done here so
        the cloid and rejection handling stay on one path."""
        mid = self.mid()
        bound = mid * (1 + DEFAULT_SLIPPAGE) if side == "BUY" \
            else mid * (1 - DEFAULT_SLIPPAGE)
        self._send(cloid, is_buy=(side == "BUY"), sz=self._sz(qty),
                   limit_px=self._px(bound, "up" if side == "BUY" else "down"),
                   reduce_only=False,
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
