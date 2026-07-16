"""OFR Financial Stress Index — daily cross-asset stress, no key.

CSV verified live 2026-07: columns "Date, OFR FSI, Credit, Equity valuation,
Safe assets, Funding, Volatility, ...". We use the headline index as an
external cross-check on our own composite (category G).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
_URL = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"


def fetch_fsi() -> tuple[list[date], list[float | None]]:
    try:
        r = httpx.get(_URL, timeout=settings.http_timeout_seconds, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OFR FSI fetch failed: %s", exc)
        return [], []
    dates: list[date] = []
    vals: list[float | None] = []
    try:
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            ds = row.get("Date")
            vs = row.get("OFR FSI")
            if not ds:
                continue
            try:
                d = datetime.strptime(ds.strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            try:
                v = float(vs) if vs not in (None, "") else None
            except ValueError:
                v = None
            dates.append(d)
            vals.append(v)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OFR FSI parse failed: %s", exc)
        return [], []
    return dates, vals
