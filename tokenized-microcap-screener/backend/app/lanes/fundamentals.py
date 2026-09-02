"""Optional market-cap / float enrichment via FMP (financialmodelingprep).

This is the ONE credentialed lane, and it is optional on purpose: without a key
the screener still runs and simply proxies company size by price and volume,
saying so on the dashboard. With a key, pumpability gets the input that matters
most for this pattern — Farmmi's entire market cap was $5.75M on the day the
JINQIAN token pooled against it carried a $5.9M fully-diluted value, i.e. the
memecoin was notionally worth more than the company it was named after.

Endpoint: GET /stable/profile?symbol=<T>&apikey=... . The pre-2025 /api/v3/
routes are legacy and refuse newer keys, so only /stable is used here.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_PROFILE = "https://financialmodelingprep.com/stable/profile"
_FLOAT = "https://financialmodelingprep.com/stable/shares-float"
_SCREENER = "https://financialmodelingprep.com/stable/company-screener"


def enabled() -> bool:
    return bool(settings.fmp_api_key)


def profile(symbol: str, ttl: int = 12 * 3600) -> dict:
    """{market_cap, avg_volume, company, exchange, industry}. {} when dark or
    when no key is configured — never raises, never blocks a scan."""
    if not enabled():
        return {}

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _PROFILE, params={"symbol": symbol.upper(),
                              "apikey": settings.fmp_api_key},
            timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(f"fmp:profile:{symbol.upper()}", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP profile lane DARK for %s: %s", symbol, exc)
        return {}
    return parse_profile(payload)


def shares_float(symbol: str, ttl: int = 24 * 3600) -> dict:
    """{float_shares, outstanding_shares, free_float_pct}. {} when dark.

    Float is the input that most directly answers "can this thing actually
    move". Farmmi's float was 31.5M shares against 837M traded on 2026-09-02 —
    the entire float changed hands about 26 times in one session. A name with a
    200M-share float cannot do that on meme flow.

    NOTE: short interest would be the natural companion here and is NOT
    wired, because FMP returns an empty array for these microcaps on this
    plan. Rather than proxy it with something that is not short interest, the
    squeeze leg is simply absent and the dashboard says so.
    """
    if not enabled():
        return {}

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _FLOAT, params={"symbol": symbol.upper(),
                            "apikey": settings.fmp_api_key},
            timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(f"fmp:float:{symbol.upper()}", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP float lane DARK for %s: %s", symbol, exc)
        return {}
    return parse_float(payload)


def parse_float(payload) -> dict:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        return {}
    row = payload[0]
    if not isinstance(row, dict):
        return {}
    return {
        "float_shares": row.get("floatShares"),
        "outstanding_shares": row.get("outstandingShares"),
        "free_float_pct": row.get("freeFloat"),
    }


def parse_profile(payload) -> dict:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        return {}
    row = payload[0]
    if not isinstance(row, dict):
        return {}
    return {
        "market_cap": row.get("marketCap"),
        "avg_volume": row.get("averageVolume"),
        "company": row.get("companyName") or "",
        "exchange": row.get("exchange") or "",
        "industry": row.get("industry") or "",
    }


# US venues only. A tokenized wrapper for a foreign listing would not trade
# against the Nasdaq/NYSE tape this service watches.
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}


def microcap_universe(bands: list[dict] | None = None, ttl: int = 12 * 3600
                      ) -> list[str]:
    """US operating companies under a market-cap ceiling, SMALLEST FIRST.

    Exists to fix a coverage problem, not to add a datapoint. The keyless
    fallback sweeps the SEC ticker list alphabetically, which needs roughly
    two days to reach every name — so on a fresh deploy the wrappers that
    actually matter (unofficial ones on nanocaps, the Farmmi shape) would
    surface last. Ordering the sweep by market cap ascending puts them first
    and gets the interesting half covered inside an hour.

    Queried in BANDS rather than one call because the screener returns the
    largest names under a ceiling first; banding guarantees the smallest are
    present regardless of how the endpoint orders a page. Returns [] without a
    key, and the caller falls back to the alphabetical sweep.
    """
    if not enabled():
        return []
    bands = bands or [
        {"marketCapLowerThan": 25_000_000},
        {"marketCapMoreThan": 25_000_000, "marketCapLowerThan": 75_000_000},
        {"marketCapMoreThan": 75_000_000, "marketCapLowerThan": 250_000_000},
    ]

    def _producer():
        out = []
        for band in bands:
            params = dict(band)
            params.update({"isEtf": "false", "isFund": "false",
                           "isActivelyTrading": "true", "limit": 1000,
                           "apikey": settings.fmp_api_key})
            resp = with_backoff(lambda p=params: httpx.get(
                _SCREENER, params=p, timeout=settings.http_timeout_seconds))
            resp.raise_for_status()
            rows = resp.json()
            out.append(rows if isinstance(rows, list) else [])
        return out

    try:
        payload = cached("fmp:microcap_universe", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP screener lane DARK: %s", exc)
        return []
    return parse_microcap_universe(payload)


def parse_microcap_universe(payload) -> list[str]:
    """Flatten the banded payload to US tickers, smallest market cap first."""
    rows: list[dict] = []
    for band in (payload or []):
        if isinstance(band, list):
            rows.extend(r for r in band if isinstance(r, dict))
    keep = []
    for r in rows:
        sym = str(r.get("symbol") or "").strip().upper()
        cap = r.get("marketCap")
        if not sym or not isinstance(cap, (int, float)) or cap <= 0:
            continue
        if r.get("exchangeShortName") not in _US_EXCHANGES:
            continue
        if r.get("isEtf") or r.get("isFund"):
            continue
        keep.append((cap, sym))
    keep.sort()
    seen, out = set(), []
    for _, sym in keep:
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out
