"""Optional FMP source — gold daily closes (GLD ETF proxy) for the flow compass.

FRED's LBMA gold series were discontinued, so gold needs FMP's /stable API (the
same endpoint family the genomics app uses). No key -> ([], []) and the gold tile
shows STALE; everything else still works.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
_URL = "https://financialmodelingprep.com/stable/historical-price-eod/light"
_SPX_TTL_SECONDS = 24 * 3600  # long history barely changes; one refresh/day


def fetch_gold(symbol: str = "GLD") -> tuple[list[date], list[float | None]]:
    if not settings.fmp_api_key:
        logger.info("FMP_API_KEY not set — gold unavailable (flow tile shows STALE)")
        return [], []
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, f"fmp_gold_{symbol}.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < settings.cache_ttl_seconds:
        try:
            return _parse(json.load(open(cache)))
        except Exception:  # noqa: BLE001
            pass
    try:
        r = httpx.get(_URL, params={"symbol": symbol, "apikey": settings.fmp_api_key},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP gold fetch failed: %s", exc)
        return [], []
    try:
        json.dump(data, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(data)


def fetch_spx_long(symbol: str = "^GSPC") -> tuple[list[date], list[float | None]]:
    """Daily S&P index closes back to 1927 for the leverage chart's long view.

    FMP caps each call at 5,000 rows (most recent first within the window), so
    paginate BACKWARDS: each pass re-requests with `to` = day before the
    earliest row seen. No key -> ([], []) and the caller falls back to FRED's
    ~10y SP500 series; on fetch failure a stale cache is preferred to nothing.
    """
    if not settings.fmp_api_key:
        return [], []
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, "fmp_spx_long.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < _SPX_TTL_SECONDS:
        try:
            return _parse(json.load(open(cache)))
        except Exception:  # noqa: BLE001
            pass
    rows: list = []
    to: str | None = None
    try:
        for _ in range(12):  # 12 x 5000 rows ≈ 230y of trading days — plenty
            params = {"symbol": symbol, "from": "1900-01-01",
                      "apikey": settings.fmp_api_key}
            if to:
                params["to"] = to
            r = httpx.get(_URL, params=params, timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            chunk = r.json()
            if not isinstance(chunk, list) or not chunk:
                break
            rows.extend(chunk)
            earliest = min(str(c.get("date"))[:10] for c in chunk)
            if len(chunk) < 5000:
                break
            to = (datetime.strptime(earliest, "%Y-%m-%d").date()
                  - timedelta(days=1)).isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP long S&P fetch failed: %s%s", exc,
                       " (using stale cache)" if os.path.exists(cache) else "")
        if os.path.exists(cache):
            try:
                return _parse(json.load(open(cache)))
            except Exception:  # noqa: BLE001
                pass
        return [], []
    try:
        json.dump(rows, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(rows)


def _parse(data) -> tuple[list[date], list[float | None]]:
    if not isinstance(data, list):
        return [], []
    rows = []
    for d in data:
        ds = str(d.get("date") or "")[:10]
        px = d.get("price", d.get("close"))
        try:
            rows.append((datetime.strptime(ds, "%Y-%m-%d").date(),
                         float(px) if px is not None else None))
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r[0])
    return [r[0] for r in rows], [r[1] for r in rows]


def fetch_move(start: str = "2015-01-01") -> tuple[list[date], list[float | None]]:
    """Daily ^MOVE closes for the Squeeze Radar's T5 (real MOVE, not the
    realized-vol proxy — T5's registered threshold is on the actual index).
    No key -> ([], []) and the condition degrades to STALE, never the proxy:
    swapping bases silently would un-register the threshold."""
    if not settings.fmp_api_key:
        return [], []
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, "fmp_move.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < settings.cache_ttl_seconds:
        try:
            return _parse(json.load(open(cache)))
        except Exception:  # noqa: BLE001
            pass
    rows: list = []
    to: str | None = None
    try:
        for _ in range(6):
            params = {"symbol": "^MOVE", "from": start,
                      "apikey": settings.fmp_api_key}
            if to:
                params["to"] = to
            r = httpx.get(_URL, params=params,
                          timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            chunk = r.json()
            if not chunk:
                break
            rows.extend(chunk)
            earliest = min(c["date"] for c in chunk)
            if earliest <= start or len(chunk) < 100:
                break
            to = (datetime.strptime(earliest, "%Y-%m-%d").date()
                  - timedelta(days=1)).isoformat()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP MOVE fetch failed: %s", exc)
        if os.path.exists(cache):
            try:
                return _parse(json.load(open(cache)))
            except Exception:  # noqa: BLE001
                pass
        return [], []
    dedup = {c["date"]: c for c in rows}
    data = [dedup[k] for k in sorted(dedup)]
    if not data:
        # a 200 with an empty body must never poison a good disk cache —
        # prefer stale MOVE history over none, and never persist [] over it.
        if os.path.exists(cache):
            try:
                cached = json.load(open(cache))
                if cached:
                    logger.warning("FMP MOVE: 0 rows — keeping stale cache")
                    return _parse(cached)
            except Exception:  # noqa: BLE001
                pass
        return [], []
    try:
        json.dump(data, open(cache, "w"))
    except Exception:  # noqa: BLE001
        pass
    return _parse(data)


def fetch_shares_outstanding(symbol: str = "TLT") -> float | None:
    """Current shares outstanding via FMP quote (F2's denominator). ETF share
    counts move with daily creations/redemptions, so this is TODAY'S count —
    the radar labels the basis. None without a key or on failure (F2 -> its
    %SO-not-computable state, never a guessed denominator)."""
    if not settings.fmp_api_key:
        return None
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, f"fmp_so_{symbol}.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 24 * 3600:
        try:
            v = json.load(open(cache)).get("so")
            if v:
                return float(v)
        except Exception:  # noqa: BLE001
            pass
    try:
        # quote.sharesOutstanding is absent for ETFs and marketCap/price runs
        # ~13% stale (measured 2026-08-25: implied 505M vs iShares' 571.3M).
        # etf/info AUM ÷ NAV reproduces the issuer's official count exactly.
        r = httpx.get("https://financialmodelingprep.com/stable/etf/info",
                      params={"symbol": symbol, "apikey": settings.fmp_api_key},
                      timeout=settings.http_timeout_seconds)
        r.raise_for_status()
        rows = r.json()
        aum = float(rows[0]["assetsUnderManagement"]) if rows else 0.0
        nav = float(rows[0]["nav"]) if rows else 0.0
        so = aum / nav if aum > 0 and nav > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP shares-outstanding fetch failed: %s", exc)
        # stale-preferred (house convention): an expired cache beats None —
        # F2's denominator drifting a few days is labeled on the condition.
        if os.path.exists(cache):
            try:
                v = json.load(open(cache)).get("so")
                if v:
                    return float(v)
            except Exception:  # noqa: BLE001
                pass
        return None
    if so and so > 0:
        try:
            json.dump({"so": so}, open(cache, "w"))
        except Exception:  # noqa: BLE001
            pass
        return so
    return None
