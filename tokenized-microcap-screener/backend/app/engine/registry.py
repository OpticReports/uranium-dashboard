"""Tokenized-equity registry: decide whether an on-chain token REPRESENTS a
listed company, and if so which one and on whose authority.

This is the load-bearing step. Everything downstream — the meme-launch
detector, the ladder, the alert — is only as good as this classification, and
the failure mode that matters is TICKER SQUATTING: a memecoin that adopts a
listed ticker as its symbol ("MU MU THE BULL" trading as symbol MU) is not a
tokenized equity, and treating it as one would map every meme to a blue chip.

So a symbol match alone is never enough. A token is an equity token only when
EITHER of these holds:

  OFFICIAL   the token name carries an issuer marker — "NVIDIA • Robinhood
             Token", "Apple xStock" — and the symbol resolves to a real US
             listing. An official wrapper has a mint/redeem path, so on-chain
             buying can actually transmit to the tape.

  UNOFFICIAL no issuer marker, but the symbol resolves to a real listing AND
             the token name matches that listing's SEC-registered company
             title. This is the Farmmi case: the token quoting JINQIAN is
             named exactly "Farmmi, Inc.", the SEC title for FAMI, but carries
             no Robinhood marker. There is no redemption path, so the loop is
             pure attention — which is a materially different trade and is
             scored differently, not filtered out.

"MU MU THE BULL" normalizes to "mumuthebull", the SEC title for MU normalizes
to "microntechnology", so it fails the name test and is correctly left as a
meme.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Whole-word legal/structural suffixes dropped before comparing names. Matched
# as tokens, never as substrings, so "Coca" is never shortened by "co".
_LEGAL_TOKENS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "plc", "llc", "lp", "holdings", "holding", "group",
    "sa", "nv", "ag", "ab", "oyj", "spa", "se", "the", "trust", "fund",
    "class", "a", "b", "c", "common", "stock", "shares", "ordinary", "adr",
    "ads", "technologies", "technology", "international",
}
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_company(name: str) -> str:
    """"Farmmi, Inc." -> "farmmi";  "MICRON TECHNOLOGY INC" -> "micron"."""
    if not name:
        return ""
    s = _PUNCT.sub(" ", name.lower())
    s = _WS.sub(" ", s).strip()
    kept = [t for t in s.split(" ") if t and t not in _LEGAL_TOKENS]
    if not kept:                      # name was ALL legal tokens — keep it raw
        kept = s.split(" ")
    return "".join(kept)


def names_match(token_name: str, sec_title: str, min_ratio: float = 0.6) -> bool:
    """True when the on-chain token name denotes the SEC-registered company.

    Exact normalized equality, or a containment where the shorter side is at
    least `min_ratio` of the longer — so "NVIDIA" matches "NVIDIA CORP" but
    "AI" does not match "APPLIED INDUSTRIAL TECHNOLOGIES".
    """
    a, b = normalize_company(token_name), normalize_company(sec_title)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < 4:                # too short to be evidence of anything
        return False
    return short in long and len(short) / len(long) >= min_ratio


@dataclass(frozen=True)
class IssuerMarker:
    marker: str        # matched case-insensitively anywhere in the token name
    issuer: str
    symbol_suffix: str = ""   # stripped from the symbol, e.g. xStocks' "AAPLx"


@dataclass(frozen=True)
class EquityTokenView:
    chain_id: str
    address: str
    symbol: str
    token_name: str
    ticker: str
    company: str
    issuer_class: str   # "OFFICIAL_<ISSUER>" | "UNOFFICIAL"
    issuer: str


def _strip_marker(name: str, marker: str) -> str:
    out = re.sub(re.escape(marker), " ", name, flags=re.IGNORECASE)
    return _WS.sub(" ", out.replace("•", " ")).strip(" -–—•")


def classify_token(token: dict, chain_id: str, universe: dict[str, str],
                   markers: list[IssuerMarker],
                   base_assets: set[str]) -> EquityTokenView | None:
    """Classify one DEX Screener token dict. None => not a tokenized equity."""
    symbol = str(token.get("symbol") or "").strip()
    name = str(token.get("name") or "").strip()
    address = str(token.get("address") or "").strip()
    if not symbol or not address:
        return None
    if symbol.upper() in base_assets:          # ETH / USDG / SOL / ...
        return None

    # 1. Issuer-marked wrappers.
    for m in markers:
        if m.marker.lower() in name.lower():
            sym = symbol.upper()
            if m.symbol_suffix and sym.endswith(m.symbol_suffix.upper()):
                sym = sym[: -len(m.symbol_suffix)]
            company = universe.get(sym)
            if not company:
                continue
            # Guard the marker against being copied into a squatter's name:
            # the de-marked name must still denote the company.
            if not names_match(_strip_marker(name, m.marker), company):
                continue
            return EquityTokenView(
                chain_id=chain_id, address=address, symbol=symbol,
                token_name=name, ticker=sym, company=company,
                issuer_class=f"OFFICIAL_{m.issuer.upper()}", issuer=m.issuer)

    # 2. Unmarked: symbol must resolve AND the name must denote the company.
    sym = symbol.upper()
    company = universe.get(sym)
    if company and names_match(name, company):
        return EquityTokenView(
            chain_id=chain_id, address=address, symbol=symbol, token_name=name,
            ticker=sym, company=company, issuer_class="UNOFFICIAL",
            issuer="unknown")
    return None


def markers_from_config(rows: list[dict]) -> list[IssuerMarker]:
    return [IssuerMarker(marker=r["marker"], issuer=r.get("issuer", "unknown"),
                         symbol_suffix=r.get("symbol_suffix", ""))
            for r in rows or [] if r.get("marker")]
