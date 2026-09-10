"""DEX Screener lane — keyless public API (https://docs.dexscreener.com/api/reference).

Endpoints used, with their documented rate limits:
  /latest/dex/search?q=            300/min  — ticker + company-name sweep
  /token-pairs/v1/{chain}/{addr}   300/min  — EVERY pair for one token
  /token-boosts/latest/v1           60/min  — cheap "someone is paying for
                                              attention" lane between sweeps
  /metas/meta/v1/{slug}             60/min  — the "stonks" meta, ditto

Two caps matter and are handled, not assumed away:
  * /latest/dex/search returns at most 30 pairs, so it is a DISCOVERY probe,
    never an enumeration. Enumeration goes through /token-pairs/v1, which is
    keyed on a token address and returns that token's pairs.
  * There is no "list all new pairs on chain X" endpoint. New launches are
    therefore found by sweeping the registry we already hold, plus the boost
    and meta lanes for tokens the registry has not met yet.

Every function degrades to [] / {} with a logged warning: a dark lane must
never take the scan down.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from ..config import settings
from ..utils import cached, with_backoff

logger = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com"
_HEADERS = {"Accept": "application/json"}

# Documented budgets, halved for headroom. One shared limiter per bucket so a
# full registry sweep cannot trip a 429 mid-scan.
_BUCKETS = {"dex": 150.0, "meta": 30.0}
_lock = threading.Lock()
_last_call: dict[str, float] = {}


def _throttle(bucket: str) -> None:
    min_gap = 60.0 / _BUCKETS[bucket]
    with _lock:
        now = time.monotonic()
        wait = _last_call.get(bucket, 0.0) + min_gap - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_call[bucket] = now


def _get(path: str, bucket: str = "dex", params: dict | None = None):
    _throttle(bucket)
    resp = with_backoff(lambda: httpx.get(
        f"{BASE}{path}", params=params, headers=_HEADERS,
        timeout=settings.http_timeout_seconds))
    resp.raise_for_status()
    return resp.json()


def search(query: str, ttl: int = 120) -> list[dict]:
    """Discovery probe. Capped at 30 pairs upstream — see module docstring."""
    try:
        payload = cached(f"dexs:search:{query}",
                         lambda: _get("/latest/dex/search", params={"q": query}),
                         ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dexscreener search DARK for %r: %s", query, exc)
        return []
    return (payload or {}).get("pairs") or []


def token_pairs(chain_id: str, token_address: str, ttl: int = 60) -> list[dict]:
    """Every indexed pair in which `token_address` is one side."""
    try:
        payload = cached(
            f"dexs:tokenpairs:{chain_id}:{token_address.lower()}",
            lambda: _get(f"/token-pairs/v1/{chain_id}/{token_address}"),
            ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dexscreener token-pairs DARK for %s/%s: %s",
                       chain_id, token_address, exc)
        return []
    if isinstance(payload, dict):          # tolerate a {"pairs": [...]} shape
        payload = payload.get("pairs") or []
    return payload if isinstance(payload, list) else []


def token_boosts_latest(ttl: int = 120) -> list[dict]:
    try:
        payload = cached("dexs:boosts:latest",
                         lambda: _get("/token-boosts/latest/v1", bucket="meta"),
                         ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dexscreener boosts DARK: %s", exc)
        return []
    return payload if isinstance(payload, list) else []


def meta_pairs(slug: str, ttl: int = 300) -> list[dict]:
    """Pairs inside a trending meta (we use 'stonks')."""
    try:
        payload = cached(f"dexs:meta:{slug}",
                         lambda: _get(f"/metas/meta/v1/{slug}", bucket="meta"),
                         ttl=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dexscreener meta DARK for %s: %s", slug, exc)
        return []
    return (payload or {}).get("pairs") or []
