"""Treasury FiscalData — auction results (no key). Schema verified live 2026-07.

We pull recent COMPLETED coupon auctions (Notes + Bonds — the duration demand
that matters for the fiscal story; bills are cash-management noise) with the
fields needed for demand metrics: bid-to-cover, primary-dealer takedown, and
indirect (foreign proxy) share of competitive accepted.

In-process cached (6h); failures memoized briefly so an offline instance doesn't
hammer the API on every /metrics render — metrics degrade to STALE.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
        "/v1/accounting/od/auctions_query")
_FIELDS = ("auction_date,security_type,security_term,bid_to_cover_ratio,"
           "primary_dealer_accepted,direct_bidder_accepted,indirect_bidder_accepted,"
           "comp_accepted,total_accepted,high_yield")

_TTL_OK = 6 * 3600
_TTL_FAIL = 600
_cache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_lock = threading.Lock()


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_recent_auctions(limit: int = 60) -> list[dict]:
    """Most-recent completed coupon auctions, oldest->newest. [] on failure."""
    now = time.time()
    ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
    if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
        return _cache["data"]  # type: ignore[return-value]
    with _lock:
        now = time.time()
        ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
        if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
            return _cache["data"]  # type: ignore[return-value]
        rows: list[dict] = []
        ok = False
        try:
            r = httpx.get(_URL, params={
                "filter": f"security_type:in:(Note,Bond),auction_date:lte:{date.today().isoformat()}",
                "sort": "-auction_date",
                "page[size]": str(limit),
                "fields": _FIELDS,
            }, timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            for rec in r.json().get("data", []):
                b2c = _f(rec.get("bid_to_cover_ratio"))
                comp = _f(rec.get("comp_accepted"))
                if b2c is None or not comp:
                    continue  # announced-but-not-run or degenerate records
                rows.append({
                    "auction_date": rec.get("auction_date"),
                    "security_type": rec.get("security_type"),
                    "security_term": rec.get("security_term"),
                    "bid_to_cover": b2c,
                    "dealer_pct": round(100.0 * (_f(rec.get("primary_dealer_accepted")) or 0.0) / comp, 1),
                    "indirect_pct": round(100.0 * (_f(rec.get("indirect_bidder_accepted")) or 0.0) / comp, 1),
                    "direct_pct": round(100.0 * (_f(rec.get("direct_bidder_accepted")) or 0.0) / comp, 1),
                    "high_yield": _f(rec.get("high_yield")),
                })
            rows.reverse()  # oldest -> newest
            ok = True
            logger.info("FiscalData: %d completed coupon auctions", len(rows))
        except Exception as exc:  # noqa: BLE001
            logger.warning("FiscalData auctions fetch failed: %s", exc)
        _cache["data"] = rows
        _cache["ts"] = time.time()
        _cache["ok"] = ok
        return rows
