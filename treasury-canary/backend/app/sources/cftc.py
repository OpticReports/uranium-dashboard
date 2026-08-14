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


# ── E-mini S&P leveraged funds (fast-leverage strip) ─────────────────────────
# Same dataset, equity complex: hedge funds' net e-mini positioning as % of open
# interest. The group is STRUCTURALLY net short (short futures against long
# cash/swap books), so the raw sign means nothing — the signal lives in the
# %-of-OI z-score, computed by the caller.
_EMINI = "E-MINI S&P 500"
_ecache: dict[str, object] = {"ts": 0.0, "data": None, "ok": False}
_elock = threading.Lock()


def fetch_emini_leveraged() -> tuple[list[date], list[float]]:
    """Full weekly history (2006+) of leveraged-fund net position as % of OI,
    oldest->newest. ([], []) on failure."""
    now = time.time()
    ttl = _TTL_OK if _ecache["ok"] else _TTL_FAIL
    if _ecache["data"] is not None and now - float(_ecache["ts"]) < ttl:
        return _ecache["data"]  # type: ignore[return-value]
    with _elock:
        now = time.time()
        ttl = _TTL_OK if _ecache["ok"] else _TTL_FAIL
        if _ecache["data"] is not None and now - float(_ecache["ts"]) < ttl:
            return _ecache["data"]  # type: ignore[return-value]
        result: tuple[list[date], list[float]] = ([], [])
        ok = False
        try:
            rows: list = []
            for off in range(0, 20000, 5000):
                r = httpx.get(_URL, params={
                    "$select": ("report_date_as_yyyy_mm_dd,lev_money_positions_long,"
                                "lev_money_positions_short,open_interest_all"),
                    "$where": f"contract_market_name='{_EMINI}'",
                    "$order": "report_date_as_yyyy_mm_dd ASC",
                    "$limit": "5000", "$offset": str(off),
                }, timeout=settings.http_timeout_seconds)
                r.raise_for_status()
                chunk = r.json()
                rows.extend(chunk)
                if len(chunk) < 5000:
                    break
            result = parse_emini_pct_oi(rows)
            ok = True
            logger.info("CFTC e-mini TFF: %d weekly observations", len(result[0]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("CFTC e-mini TFF fetch failed: %s", exc)
            # stale-preferred (QA finding): a transient Socrata failure must
            # not overwrite a good full history with ([], []) and null the
            # composite state for the fail-TTL window.
            if _ecache["data"] is not None and _ecache["data"][0]:  # type: ignore[index]
                _ecache["ts"] = time.time()
                _ecache["ok"] = False
                return _ecache["data"]  # type: ignore[return-value]
        _ecache["data"] = result
        _ecache["ts"] = time.time()
        _ecache["ok"] = ok
        return result


def parse_emini_pct_oi(rows: list[dict]) -> tuple[list[date], list[float]]:
    """(long - short) / open_interest * 100 per report date, ascending."""
    out = []
    for r in rows:
        ds = str(r.get("report_date_as_yyyy_mm_dd") or "")[:10]
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            oi = float(r["open_interest_all"])
            if oi <= 0:
                continue
            net = (float(r["lev_money_positions_long"])
                   - float(r["lev_money_positions_short"]))
            out.append((d, net / oi * 100.0))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda t: t[0])
    return [t[0] for t in out], [t[1] for t in out]


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
