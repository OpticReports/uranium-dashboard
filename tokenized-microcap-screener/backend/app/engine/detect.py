"""Meme-launch detection.

The structural signal this whole service rests on: on Robinhood Chain the
memecoins that moved listed stocks were not merely NAMED after a company —
they were POOLED AGAINST a tokenized share of it. JINQIAN's deepest pair
quotes in FAMI; "MU MU THE BULL" quotes in tokenized MU; "Artificial Inu"
quotes in tokenized NVDA. That makes the mapping from meme to ticker a
property of the pool itself rather than an inference from a name, which is why
it can be detected mechanically instead of guessed at.

A LAUNCH is therefore a pair where exactly one side classifies as a tokenized
equity and the other side is neither an equity token nor a chain base asset.
Both-sides-equity (FAMI/FAMI, NVDA/NVDA) is an arb or wrapper pool, not a
launch, and is skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .registry import (EquityTokenView, IssuerMarker, classify_token,
                       normalize_company)


@dataclass
class LaunchView:
    chain_id: str
    pair_address: str
    dex_id: str
    url: str
    equity: EquityTokenView
    meme_address: str
    meme_symbol: str
    meme_name: str
    pair_created_at: datetime | None
    liquidity_usd: float
    fdv: float
    volume_h24: float
    volume_h6: float
    volume_h1: float
    volume_m5: float
    buys_h1: int
    sells_h1: int
    buys_h24: int
    sells_h24: int
    price_change_h1: float
    price_change_h24: float
    socials: list = field(default_factory=list)
    websites: list = field(default_factory=list)


def _f(node, *path, default=0.0) -> float:
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return float(cur) if isinstance(cur, (int, float)) else default


def _i(node, *path) -> int:
    return int(_f(node, *path, default=0.0))


def _ts(ms) -> datetime | None:
    if not isinstance(ms, (int, float)) or ms <= 0:
        return None
    try:
        return datetime.utcfromtimestamp(ms / 1000.0)
    except (ValueError, OverflowError, OSError):
        return None


def detect_launch(pair: dict, universe: dict[str, str],
                  markers: list[IssuerMarker],
                  base_assets: set[str]) -> LaunchView | None:
    """None unless this pair is a meme pooled against a tokenized equity."""
    chain_id = str(pair.get("chainId") or "")
    base, quote = pair.get("baseToken") or {}, pair.get("quoteToken") or {}
    if not chain_id or not base or not quote:
        return None

    base_eq = classify_token(base, chain_id, universe, markers, base_assets)
    quote_eq = classify_token(quote, chain_id, universe, markers, base_assets)
    if (base_eq is None) == (quote_eq is None):
        return None                      # neither side, or both sides: not a launch

    equity = base_eq or quote_eq
    meme = quote if base_eq else base
    meme_symbol = str(meme.get("symbol") or "")
    if meme_symbol.upper() in base_assets:
        return None                      # equity/stable or equity/ETH pool

    # Bare-echo impersonation: a token whose ENTIRE identity is the wrapper's
    # ticker — symbol "FAMI", name "FAMI", pooled against the real tokenized
    # FAMI. That is a lookalike or a wrapper-arb pool, not a meme, and a few
    # empty ones would otherwise fake the cluster signature.
    #
    # Symbol collision ALONE is not enough to exclude: "MU MU THE BULL" also
    # trades as symbol MU against the official Micron wrapper, and that is
    # exactly the pattern being hunted. The meme must merely have an identity
    # of its own beyond the ticker.
    if meme_symbol.strip().upper() == equity.symbol.strip().upper():
        meme_identity = normalize_company(str(meme.get("name") or ""))
        echoes = {equity.symbol.strip().lower(),
                  normalize_company(equity.token_name), ""}
        if meme_identity in echoes:
            return None

    info = pair.get("info") or {}
    return LaunchView(
        chain_id=chain_id,
        pair_address=str(pair.get("pairAddress") or ""),
        dex_id=str(pair.get("dexId") or ""),
        url=str(pair.get("url") or ""),
        equity=equity,                                  # type: ignore[arg-type]
        meme_address=str(meme.get("address") or ""),
        meme_symbol=meme_symbol,
        meme_name=str(meme.get("name") or ""),
        pair_created_at=_ts(pair.get("pairCreatedAt")),
        liquidity_usd=_f(pair, "liquidity", "usd"),
        fdv=_f(pair, "fdv"),
        volume_h24=_f(pair, "volume", "h24"),
        volume_h6=_f(pair, "volume", "h6"),
        volume_h1=_f(pair, "volume", "h1"),
        volume_m5=_f(pair, "volume", "m5"),
        buys_h1=_i(pair, "txns", "h1", "buys"),
        sells_h1=_i(pair, "txns", "h1", "sells"),
        buys_h24=_i(pair, "txns", "h24", "buys"),
        sells_h24=_i(pair, "txns", "h24", "sells"),
        price_change_h1=_f(pair, "priceChange", "h1"),
        price_change_h24=_f(pair, "priceChange", "h24"),
        socials=list(info.get("socials") or []),
        websites=list(info.get("websites") or []),
    )


def detect_launches(pairs: list[dict], universe: dict[str, str],
                    markers: list[IssuerMarker],
                    base_assets: set[str]) -> list[LaunchView]:
    out: list[LaunchView] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs or []:
        launch = detect_launch(pair, universe, markers, base_assets)
        if launch is None:
            continue
        key = (launch.chain_id, launch.pair_address.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(launch)
    return out


def equity_tokens_in(pairs: list[dict], universe: dict[str, str],
                     markers: list[IssuerMarker],
                     base_assets: set[str]) -> list[EquityTokenView]:
    """Every tokenized equity appearing on either side — how the registry
    grows itself from the discovery lanes."""
    found: dict[tuple[str, str], EquityTokenView] = {}
    for pair in pairs or []:
        chain_id = str(pair.get("chainId") or "")
        if not chain_id:
            continue
        for side in ("baseToken", "quoteToken"):
            view = classify_token(pair.get(side) or {}, chain_id, universe,
                                  markers, base_assets)
            if view is not None:
                found.setdefault((chain_id, view.address.lower()), view)
    return list(found.values())
