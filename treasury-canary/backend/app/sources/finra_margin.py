"""FINRA monthly margin statistics (free, keyless).

FINRA publishes customer margin balances — debit balances in securities margin
accounts plus free credit balances in cash and margin accounts, $ millions —
as one xlsx with the full history (1997-01..present). The '2021-03' in the URL
is just the upload path; FINRA keeps the file itself current. Monthly data,
published ~3-4 weeks after month end.

Failure mode mirrors the other ride-along sources: any error -> empty series
-> the margin tiles render STALE while everything else keeps working. A stale
cached file is preferred over nothing when the fetch fails.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
# Monthly series published once a month — no reason to re-download hourly.
_TTL_SECONDS = 24 * 3600

Series = tuple[list[date], list[float | None]]


def fetch_margin_stats() -> dict[str, Series]:
    """Return {"margin_debit": ..., "margin_credit": ...} (both $ millions,
    ascending month order; credit = cash-account + margin-account free credit)."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    cache = os.path.join(settings.cache_dir, "finra_margin.xlsx")
    fresh = os.path.exists(cache) and time.time() - os.path.getmtime(cache) < _TTL_SECONDS
    if not fresh:
        try:
            r = httpx.get(_URL, timeout=settings.http_timeout_seconds,
                          follow_redirects=True)
            r.raise_for_status()
            with open(cache, "wb") as f:
                f.write(r.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FINRA margin fetch failed: %s%s", exc,
                           " (using stale cache)" if os.path.exists(cache) else "")
    if not os.path.exists(cache):
        return {"margin_debit": ([], []), "margin_credit": ([], [])}
    try:
        return parse_margin_workbook(cache)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FINRA margin parse failed: %s", exc)
        return {"margin_debit": ([], []), "margin_credit": ([], [])}


def parse_margin_workbook(path: str) -> dict[str, Series]:
    """Parse FINRA's workbook: Year-Month | debit | cash free credit | margin
    free credit (newest first). Kept separate from fetch for offline tests."""
    import openpyxl  # lazy: keeps app import-safe if the dep is ever missing

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[0]
    rows: list[tuple[date, float, float | None]] = []
    for ym, debit, cash_cr, margin_cr in ws.iter_rows(min_row=2, max_col=4,
                                                      values_only=True):
        if ym is None or debit is None:
            continue
        try:
            d = datetime.strptime(str(ym)[:7], "%Y-%m").date()
        except ValueError:
            continue
        credit = float(cash_cr or 0) + float(margin_cr or 0)
        rows.append((d, float(debit), credit if (cash_cr or margin_cr) else None))
    rows.sort(key=lambda r: r[0])
    return {
        "margin_debit": ([r[0] for r in rows], [r[1] for r in rows]),
        "margin_credit": ([r[0] for r in rows], [r[2] for r in rows]),
    }
