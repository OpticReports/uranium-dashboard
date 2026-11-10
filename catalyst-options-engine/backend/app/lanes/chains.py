"""Live option-chain lane: Nasdaq's public quote API (keyless, browser UA).

GET https://api.nasdaq.com/api/quote/<TICKER>/option-chain
      ?assetclass=stocks&limit=200&fromdate=all&todate=undefined
      &excode=oprac&callput=callput&money=at&type=all

Response shape (fixture: tests/fixtures/nasdaq_chain_mrna.json, captured live
2026-08-19):
  data.table.rows = mixed list of
    * expiry GROUP HEADER rows: strike is null (expirygroup like
      "August 21, 2026") — SKIPPED as data, but their full date seeds year
      inference for the short "Aug 21" expiryDate on the data rows;
    * data rows: {expiryDate:"Aug 21", strike:"130.00", c_Bid/c_Ask/c_Last,
      p_Bid/p_Ask/p_Last, drillDownURL:".../mrna--260821c00130000"} — the
      drillDownURL encodes the unambiguous yymmdd expiry (primary parse).
  data.lastTrade = "LAST TRADE: $145.57 (AS OF ...)" — underlying price.

Lane-dark behavior (IMPORTANT): this endpoint verifiably works from a dev
container but MAY be blocked from datacenter IPs (Render). Any failure logs a
warning and returns None; the engine then runs with the chain lane dark —
iv_ratio=None (score neutral + "IV unknown"), proposals priced at scenario-IV
Black-Scholes with pricing_basis="bs_scenario" on every affected row.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import httpx

from ..config import BROWSER_UA, settings
from ..engine.signals import ChainRowView
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_BASE = "https://api.nasdaq.com/api/quote/{symbol}/option-chain"
_PARAMS = {"assetclass": "stocks", "limit": "200", "fromdate": "all",
           "todate": "undefined", "excode": "oprac", "callput": "callput",
           "money": "at", "type": "all"}
_HEADERS = {"User-Agent": BROWSER_UA, "Accept": "application/json"}

_URL_EXPIRY_RE = re.compile(r"--(\d{6})[cp]\d")
_LAST_TRADE_RE = re.compile(r"\$([\d,]+\.?\d*)")


def _num(v) -> float | None:
    """Nasdaq money fields: '16.85', '--', '', None, '1,234.00'."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s == "--":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _expiry_from_url(url: str | None) -> date | None:
    if not url:
        return None
    m = _URL_EXPIRY_RE.search(url)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%y%m%d").date()
    except ValueError:
        return None


def _expiry_from_group(group: str | None) -> date | None:
    if not group:
        return None
    try:
        return datetime.strptime(group.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def _expiry_from_short(short: str | None, today: date) -> date | None:
    """'Aug 21' with no year: current year unless that lands >7d in the past."""
    if not short:
        return None
    try:
        md = datetime.strptime(short.strip(), "%b %d")
    except ValueError:
        return None
    cand = date(today.year, md.month, md.day)
    if (today - cand).days > 7:
        cand = date(today.year + 1, md.month, md.day)
    return cand


def parse_chain(payload: dict, today: date) -> tuple[float | None, list[ChainRowView]]:
    """(underlying_price, rows). Group-header rows (null strike) are skipped;
    their expirygroup date seeds year inference for subsequent short dates."""
    data = (payload or {}).get("data") or {}
    table = data.get("table") or {}
    raw_rows = table.get("rows") or []

    underlying = None
    m = _LAST_TRADE_RE.search(str(data.get("lastTrade") or ""))
    if m:
        try:
            underlying = float(m.group(1).replace(",", ""))
        except ValueError:
            underlying = None

    rows: list[ChainRowView] = []
    group_expiry: date | None = None
    for r in raw_rows:
        if r.get("strike") is None:
            # Expiry group header — remember its full date, emit nothing.
            group_expiry = _expiry_from_group(r.get("expirygroup"))
            continue
        strike = _num(r.get("strike"))
        if strike is None:
            continue
        expiry = (_expiry_from_url(r.get("drillDownURL"))
                  or group_expiry
                  or _expiry_from_short(r.get("expiryDate"), today))
        if expiry is None:
            continue
        rows.append(ChainRowView(
            expiry=expiry, strike=strike,
            c_bid=_num(r.get("c_Bid")), c_ask=_num(r.get("c_Ask")),
            c_last=_num(r.get("c_Last")),
            p_bid=_num(r.get("p_Bid")), p_ask=_num(r.get("p_Ask")),
            p_last=_num(r.get("p_Last"))))
    return underlying, rows


def fetch_chain(symbol: str, ttl: int = 1800) -> tuple[float | None, list[ChainRowView]] | None:
    """(underlying, rows) or None when the lane is DARK (blocked/failed)."""
    key = f"chain:{symbol}"

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _BASE.format(symbol=symbol.upper()), params=_PARAMS,
            headers=_HEADERS, timeout=settings.http_timeout_seconds),
            retries=2)
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(key, _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chain lane DARK for %s: %s (engine continues with "
                       "scenario-IV pricing)", symbol, exc)
        return None
    underlying, rows = parse_chain(payload, date.today())
    if not rows:
        logger.warning("chain lane returned no rows for %s — treating as dark",
                       symbol)
        return None
    return underlying, rows
