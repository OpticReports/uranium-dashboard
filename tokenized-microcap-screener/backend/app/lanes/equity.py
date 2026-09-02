"""Equity lane — keyless.

Two sources, both public:
  * SEC company_tickers.json — the authoritative ticker -> company-title map
    for ~10.4k US registrants. This is what makes the on-chain mapping
    DETERMINISTIC rather than a guess: the tokenized Farmmi token on Robinhood
    Chain is literally named "Farmmi, Inc.", which is byte-for-byte the SEC
    title for FAMI.
  * stockanalysis.com — live quote + daily history (price, today's volume,
    prior close, exchange, market status, average volume).

Neither carries shares-outstanding, so the market-cap gate is OPTIONAL
enrichment via FMP when a key is present; without it the pumpability score
falls back to price + relative volume and the candidate is flagged
`market_cap_dark`. That fallback is disclosed on the dashboard rather than
silently papered over.
"""
from __future__ import annotations

import logging
import statistics

import httpx

from ..config import BROWSER_UA, sec_user_agent, settings
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

_SEC_URL = "https://www.sec.gov/files/company_tickers.json"
_SA_QUOTE = "https://stockanalysis.com/api/quotes/s/{symbol}"
_SA_HIST = "https://stockanalysis.com/api/symbol/s/{symbol}/history"
_SA_HEADERS = {"User-Agent": BROWSER_UA, "Accept": "application/json"}


def sec_universe(ttl: int = 24 * 3600) -> dict[str, str]:
    """{TICKER: "Company Title"} for every SEC registrant. {} when dark."""

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _SEC_URL, headers={"User-Agent": sec_user_agent(settings.sec_contact),
                     "Accept": "application/json"},
            timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached("sec:company_tickers", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC universe lane DARK: %s", exc)
        return {}
    return parse_sec_universe(payload)


def parse_sec_universe(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in (payload or {}).values():
        try:
            ticker = str(row["ticker"]).strip().upper()
            title = str(row["title"]).strip()
        except (KeyError, TypeError, AttributeError):
            continue
        if ticker:
            out.setdefault(ticker, title)
    return out


def quote(symbol: str, ttl: int = 60) -> dict:
    """Live-ish quote. {} when dark.

    Field map (stockanalysis): p=price, cl=previous close, cp=change %,
    v=today's volume, ex=exchange, ms=market status, h52/l52=52-week range.
    """

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _SA_QUOTE.format(symbol=symbol.upper()), headers=_SA_HEADERS,
            timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(f"equity:quote:{symbol.upper()}", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("equity quote lane DARK for %s: %s", symbol, exc)
        return {}
    return parse_quote(payload)


def parse_quote(payload: dict) -> dict:
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        return {}
    return {
        "price": data.get("p"),
        "prev_close": data.get("cl"),
        "change_pct": data.get("cp"),
        "volume": data.get("v"),
        "day_high": data.get("h"),
        "day_low": data.get("l"),
        "high_52w": data.get("h52"),
        "low_52w": data.get("l52"),
        "exchange": data.get("ex") or "",
        "market_status": data.get("ms") or "",
        "asof": data.get("u") or "",
    }


def history(symbol: str, range_: str = "3M", ttl: int = 6 * 3600) -> list[dict]:
    """Oldest-first daily bars. [] when dark."""

    def _producer():
        resp = with_backoff(lambda: httpx.get(
            _SA_HIST.format(symbol=symbol.upper()),
            params={"range": range_, "period": "Daily"},
            headers=_SA_HEADERS, timeout=settings.http_timeout_seconds))
        resp.raise_for_status()
        return resp.json()

    try:
        payload = cached(f"equity:hist:{symbol.upper()}:{range_}", _producer, ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("equity history lane DARK for %s: %s", symbol, exc)
        return []
    return parse_history(payload)


def parse_history(payload: dict) -> list[dict]:
    data = (payload or {}).get("data")
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, list):
        return []
    bars = []
    for row in data:
        if not isinstance(row, dict) or "t" not in row:
            continue
        bars.append({
            "date": row["t"], "open": row.get("o"), "high": row.get("h"),
            "low": row.get("l"), "close": row.get("c"),
            "adj_close": row.get("a", row.get("c")), "volume": row.get("v"),
        })
    bars.sort(key=lambda b: b["date"])   # upstream is newest-first
    return bars


def average_volume(bars: list[dict], lookback: int = 20) -> float | None:
    """Median (not mean) daily volume over the lookback.

    Median because these names spike: one 700M-share day would drag a 20-day
    MEAN up ~35x and make the very event we are hunting look unremarkable.
    """
    vols = [b["volume"] for b in bars[-lookback:]
            if isinstance(b.get("volume"), (int, float)) and b["volume"] > 0]
    if len(vols) < 3:
        return None
    return float(statistics.median(vols))
