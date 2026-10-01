"""Hyperliquid adapter for the ETH carry sleeve: long spot UETH, short ETH perp,
both in the MAIN account (unified mode, USDC collateral).

Only what the sleeve needs: one read of both legs, IOC orders on either
market, cross-margin setup and the funding the short has received. The
lessons btc-executor paid for are kept: the account address is mandatory
(an agent wallet holds nothing - reading the signer reports a permanent
FLAT), an unreadable venue raises instead of reading as zero, and every
order price and size is put on the venue's grid before it is sent.
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

PERP_MAX_DECIMALS = 6        # perp px: <= 5 sig figs and <= 6 - szDecimals decimals
SPOT_MAX_DECIMALS = 8        # spot px: <= 5 sig figs and <= 8 - szDecimals decimals


def round_down(qty: float, decimals: int) -> float:
    f = 10 ** decimals
    return math.floor(qty * f + 1e-9) / f


def grid_px(px: float, sz_decimals: int, max_decimals: int, mode: str) -> float:
    """Hyperliquid price grid: at most 5 significant figures and at most
    (max_decimals - szDecimals) decimals; integers always allowed. `mode`
    "down" never rounds above px (an IOC BUY never pays more than its
    limit), "up" never below (an IOC SELL never accepts less)."""
    if px <= 0:
        raise ValueError(f"bad price {px}")
    int_digits = len(str(int(px))) if px >= 1 else 0
    dec = max(0, min(max_decimals - sz_decimals, 5 - int_digits))
    f = 10 ** dec
    v = math.floor(px * f + 1e-9) / f if mode == "down" else math.ceil(px * f - 1e-9) / f
    return round(v, dec)


class HLCarryVenue:
    def __init__(self, cfg):
        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        self.cfg = cfg
        self.testnet = bool(getattr(cfg, "hl_testnet", False))
        self.network = "testnet" if self.testnet else "mainnet"
        base = constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
        wallet = Account.from_key(cfg.hl_secret_key)
        self.address = str(getattr(cfg, "hl_account_address", "") or "").strip()
        if not self.address:
            raise RuntimeError(
                "HL_ACCOUNT_ADDRESS is required: the MAIN account's public "
                "address. An agent wallet holds nothing, so reading the signer "
                "would report the sleeve permanently FLAT.")
        self.agent_address = wallet.address
        self.perp_coin = cfg.perp_coin
        self.spot_token = cfg.spot_token
        self.info = Info(base, skip_ws=True)
        self.exchange = Exchange(wallet, base, account_address=self.address)
        self.spot_pair, self.spot_sz_dec = self._resolve_spot_pair()
        self.perp_sz_dec = self._resolve_perp_decimals()
        logger.info("carry venue ready: %s perp %s / spot %s (%s) addr=%s",
                    self.network, self.perp_coin, self.spot_token,
                    self.spot_pair, self.address)

    # ---------- metadata ----------

    def _resolve_spot_pair(self) -> tuple[str, int]:
        """The spot_token/USDC pair's name (e.g. "@151") and the token's
        szDecimals. Resolved from spotMeta at boot; a missing pair refuses
        to construct rather than trading some other market."""
        m = self.info.spot_meta() or {}
        toks = {t["index"]: t for t in m.get("tokens", [])}
        usdc = next((i for i, t in toks.items() if t["name"] == "USDC"), None)
        for u in m.get("universe", []):
            pair = u.get("tokens") or []
            if (len(pair) == 2 and pair[1] == usdc and pair[0] in toks
                    and toks[pair[0]]["name"] == self.spot_token):
                return u["name"], int(toks[pair[0]]["szDecimals"])
        raise RuntimeError(f"no {self.spot_token}/USDC spot pair in spotMeta")

    def _resolve_perp_decimals(self) -> int:
        for u in (self.info.meta() or {}).get("universe", []):
            if u.get("name") == self.perp_coin:
                return int(u["szDecimals"])
        raise RuntimeError(f"no {self.perp_coin} perp in meta")

    # ---------- reads ----------

    def read(self) -> dict:
        """One snapshot of both legs. Raises on anything unreadable - a
        missing balance row is a confirmed 0, a failed request is not."""
        sp = self.info.spot_user_state(self.address)
        if not isinstance(sp, dict) or "balances" not in sp:
            raise RuntimeError(f"spot_user_state unreadable: {sp!r}")
        spot_qty = spot_hold = usdc = 0.0
        for b in sp["balances"]:
            c = (b or {}).get("coin")
            if c == self.spot_token:
                spot_qty = float(b.get("total") or 0.0)
                spot_hold = float(b.get("hold") or 0.0)
            elif c == "USDC":
                usdc = float(b.get("total") or 0.0)
        st = self.info.user_state(self.address)
        if not isinstance(st, dict) or "assetPositions" not in st:
            raise RuntimeError(f"user_state unreadable: {st!r}")
        perp_qty, liq_px = 0.0, None
        for ap in st["assetPositions"]:
            p = (ap or {}).get("position") or {}
            if p.get("coin") == self.perp_coin:
                if p.get("szi") is None:
                    raise RuntimeError(f"{self.perp_coin} row carried no szi: {p}")
                perp_qty = float(p["szi"])
                liq_px = float(p["liquidationPx"]) if p.get("liquidationPx") else None
        mids = self.info.all_mids() or {}
        if self.perp_coin not in mids or self.spot_pair not in mids:
            raise RuntimeError(f"all_mids missing {self.perp_coin} or {self.spot_pair}")
        return {"spot_qty": spot_qty, "spot_hold": spot_hold, "usdc": usdc,
                "perp_qty": perp_qty, "liq_px": liq_px,
                "perp_mid": float(mids[self.perp_coin]),
                "spot_mid": float(mids[self.spot_pair])}

    def funding_received(self, since_ms: int) -> float:
        """USDC funding the perp leg has received since `since_ms` (positive
        = received). Informational: never used for a trading decision."""
        rows = self.info.user_funding_history(self.address, since_ms) or []
        tot = 0.0
        for r in rows:
            d = (r or {}).get("delta") or {}
            if d.get("coin") == self.perp_coin:
                tot += float(d.get("usdc") or 0.0)
        return tot

    # ---------- mutations ----------

    def ensure_cross(self, leverage: int) -> None:
        """CROSS margin, so the account's USDC backs the short. Isolated
        margin would ring-fence a fixed amount and liquidate the short in a
        rally the rest of the account could easily have carried."""
        r = self.exchange.update_leverage(int(leverage), self.perp_coin, True)
        if not isinstance(r, dict) or r.get("status") != "ok":
            raise RuntimeError(f"update_leverage rejected: {r}")

    def ioc(self, market: str, is_buy: bool, qty: float, ref_px: float,
            slip_bps: float, reduce_only: bool = False) -> dict:
        """Immediate-or-cancel at ref_px +- slip. Returns {'filled', 'avg_px'};
        a partial or zero fill is a normal outcome, a rejection raises."""
        if market == "spot":
            name, dec, maxd = self.spot_pair, self.spot_sz_dec, SPOT_MAX_DECIMALS
            reduce_only = False                  # not a spot concept
        elif market == "perp":
            name, dec, maxd = self.perp_coin, self.perp_sz_dec, PERP_MAX_DECIMALS
        else:
            raise ValueError(market)
        sz = round_down(qty, dec)
        if sz <= 0:
            return {"filled": 0.0, "avg_px": None}
        lim = ref_px * (1 + slip_bps / 1e4) if is_buy else ref_px * (1 - slip_bps / 1e4)
        px = grid_px(lim, dec, maxd, "down" if is_buy else "up")
        r = self.exchange.order(name, is_buy, sz, px, {"limit": {"tif": "Ioc"}},
                                reduce_only=reduce_only)
        if not isinstance(r, dict) or r.get("status") != "ok":
            raise RuntimeError(f"{market} order rejected: {r}")
        statuses = (((r.get("response") or {}).get("data") or {})
                    .get("statuses") or [])
        filled, notional = 0.0, 0.0
        for s in statuses:
            if not isinstance(s, dict):
                continue
            if "error" in s:
                err = str(s["error"])
                # an IOC that found no liquidity inside its limit is a zero
                # fill, not a failure
                if "could not immediately match" in err.lower():
                    continue
                raise RuntimeError(f"{market} order rejected: {err}")
            f = s.get("filled")
            if f:
                q = float(f.get("totalSz") or 0.0)
                filled += q
                notional += q * float(f.get("avgPx") or 0.0)
        return {"filled": filled, "avg_px": notional / filled if filled else None}
