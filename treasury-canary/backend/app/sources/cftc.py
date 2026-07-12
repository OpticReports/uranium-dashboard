"""CFTC Traders-in-Financial-Futures — leveraged-fund Treasury futures positioning.

The basis-trade proxy: hedge funds run enormous NET SHORT Treasury-futures books
against cash bonds (the cash-futures basis trade). When it unwinds it unwinds
violently (March 2020). Weekly, free, keyless (Socrata; schema verified live
2026-07: lev_money_positions_long/short, contract_market_name,
report_date_as_yyyy_mm_dd).

We aggregate net short across the UST futures complex, in millions of contracts.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
_CONTRACTS = ("UST 2Y NOTE", "UST 5Y NOTE", "UST 10Y NOTE",
              "ULTRA UST 10Y", "UST BOND", "ULTRA UST BOND")

_TTL_OK = 6 * 3600
_TTL_FAIL = 600
_cache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_lock = threading.Lock()


def fetch_lev_net_short() -> tuple[list[date], list[float | None]]:
    """Weekly aggregate leveraged-fund net short (millions of contracts),
    oldest->newest. ([], []) on failure."""
    now = time.time()
    ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
    if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
        return _cache["data"]  # type: ignore[return-value]
    with _lock:
        now = time.time()
        ttl = _TTL_OK if _cache["ok"] else _TTL_FAIL
        if _cache["data"] is not None and now - float(_cache["ts"]) < ttl:
            return _cache["data"]  # type: ignore[return-value]
        result: tuple[list[date], list[float | None]] = ([], [])
        ok = False
        try:
            names = ",".join(f"'{c}'" for c in _CONTRACTS)
            r = httpx.get(_URL, params={
                "$where": f"contract_market_name in({names})",
                "$select": ("report_date_as_yyyy_mm_dd,contract_market_name,"
                            "lev_money_positions_long,lev_money_positions_short"),
                "$limit": "50000",
            }, timeout=settings.http_timeout_seconds)
            r.raise_for_status()
            result = aggregate_net_short(r.json())
            ok = True
            logger.info("CFTC TFF: %d weekly observations", len(result[0]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("CFTC TFF fetch failed: %s", exc)
        _cache["data"] = result
        _cache["ts"] = time.time()
        _cache["ok"] = ok
        return result


def aggregate_net_short(rows: list[dict]) -> tuple[list[date], list[float | None]]:
    """Sum (short - long) across contracts per report date -> millions of contracts."""
    by_date: dict[date, float] = defaultdict(float)
    for row in rows:
        ds = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        try:
            short = float(row.get("lev_money_positions_short") or 0)
            long = float(row.get("lev_money_positions_long") or 0)
        except (TypeError, ValueError):
            continue
        by_date[d] += (short - long) / 1_000_000.0
    dates = sorted(by_date)
    return dates, [round(by_date[d], 3) for d in dates]
