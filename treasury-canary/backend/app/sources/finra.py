"""FINRA consolidated short interest — TLT bi-monthly settlements, no key.

Public POST endpoint (verified live 2026-08-25; returns CSV): the same series
the Squeeze Radar's F2 condition and DTC context read. Bi-monthly cadence
means a ~2-4 week publication lag is inherent — the radar states the
settlement date rather than pretending freshness.

In-process cached (12h; the series only changes twice a month), failures
memoized 10 min, stale-preferred: a transient FINRA outage must not blank a
condition that last changed weeks ago.
"""
from __future__ import annotations

import csv
import io
import logging
import threading
import time

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_URL = ("https://api.finra.org/data/group/otcMarket/name/"
        "consolidatedShortInterest")

_TTL_OK = 12 * 3600
_TTL_FAIL = 600
_cache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_lock = threading.Lock()


def parse_rows(text: str) -> list[dict]:
    """CSV -> [{settlement_date, shares_short, adv, dtc}], ascending, deduped."""
    out: dict[str, dict] = {}
    for r in csv.DictReader(io.StringIO(text)):
        try:
            d = str(r["settlementDate"])[:10]
            out[d] = {
                "settlement_date": d,
                "shares_short": int(float(r["currentShortPositionQuantity"])),
                "adv": (int(float(r["averageDailyVolumeQuantity"]))
                        if r.get("averageDailyVolumeQuantity") else None),
                "dtc": (float(r["daysToCoverQuantity"])
                        if r.get("daysToCoverQuantity") else None),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return [out[k] for k in sorted(out)]


def fetch_tlt_short_interest(start: str = "2017-12-01") -> list[dict]:
    """All TLT settlements since `start`, oldest->newest. [] on failure."""
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
            r = httpx.post(_URL, json={
                "limit": 500,
                "compareFilters": [{"compareType": "EQUAL",
                                    "fieldName": "symbolCode",
                                    "fieldValue": "TLT"}],
                "dateRangeFilters": [{"fieldName": "settlementDate",
                                      "startDate": start,
                                      "endDate": "2099-01-01"}],
            }, timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            rows = parse_rows(r.text)
            ok = bool(rows)
            logger.info("FINRA TLT SI: %d settlements", len(rows))
        except Exception as exc:  # noqa: BLE001
            logger.warning("FINRA SI fetch failed: %s", exc)
            if _cache["data"]:
                _cache["ts"] = time.time()
                _cache["ok"] = False
                return _cache["data"]  # type: ignore[return-value]
        _cache["data"] = rows
        _cache["ts"] = time.time()
        _cache["ok"] = ok
        return rows
