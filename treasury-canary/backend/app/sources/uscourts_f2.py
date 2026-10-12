"""AO Table F-2: bankruptcy cases commenced by chapter, business vs
non-business, by district (U.S. Courts statistics; free, keyless).

The AO posts each quarter's tables about 3-4 weeks after the quarter ends:
three-month counts at .../files/document/bf_f2.3_MMDD.YYYY.xlsx and
twelve-month (rolling) counts at .../bf_f2_MMDD.YYYY.xlsx (the pattern since
2025Q1). The frozen history in distress_history.json ends where the study's
data end; this module adds the quarters published since. Failure mode, as
for the other ride-along sources: any error -> no new quarter, and the
distress panel shows the frozen history marked stale.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_BASE = "https://www.uscourts.gov/sites/default/files/document/"
_NAMES = {"3month": "bf_f2.3_{mmdd}.{yyyy}.xlsx", "12month": "bf_f2_{mmdd}.{yyyy}.xlsx"}
_MISS_TTL = 24 * 3600           # re-probe an unpublished quarter at most daily
COLUMNS = ("total_all", "total_ch7", "total_ch11", "total_ch13", "total_other",
           "bus_all", "bus_ch7", "bus_ch11", "bus_ch13", "bus_other",
           "nb_all", "nb_ch7", "nb_ch11", "nb_ch13")
TERRITORIES = {"PR", "VI", "GU", "GUAM", "NMI", "MP"}
_ORDINALS = {"1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th"}


def quarter_end(y: int, q: int) -> date:
    return date(y, 3 * q, 31 if q in (1, 4) else 30)


def url(kind: str, qend: date) -> str:
    return _BASE + _NAMES[kind].format(mmdd=f"{qend.month:02d}{qend.day:02d}", yyyy=qend.year)


def _num(v) -> int | None:
    """Cell -> int; '-' (no cases) -> 0; anything else non-numeric -> None."""
    t = str(v).strip() if v is not None else ""
    if t in ("-", "\u2014"):
        return 0
    return int(t) if t.isdigit() else None


def parse_f2(path: str) -> dict:
    """{'national': {col: n}, 'states': {ST: {col: n}}} from an F-2 workbook
    (first sheet). District labels are 'ME' or 'NY,N'; circuit rows ('1st'..)
    are skipped; territories are dropped from the states."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    national: dict[str, int] | None = None
    states: dict[str, dict[str, int]] = {}
    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        label = re.sub(r"[^A-Za-z0-9,]", "", str(row[0]))      # 'AR ²' -> 'AR', '  8th' -> '8th'
        vals = [_num(v) for v in row[1:1 + len(COLUMNS)]]
        if len(vals) < len(COLUMNS) or any(v is None for v in vals):
            continue
        nums = dict(zip(COLUMNS, vals))
        if label.lower() == "total":
            national = nums
            continue
        if label in _ORDINALS:
            continue
        st = label.split(",")[0].strip().upper()
        if st in TERRITORIES or len(st) != 2:
            continue
        acc = states.setdefault(st, dict.fromkeys(COLUMNS, 0))
        for k, v in nums.items():
            acc[k] += v
    if national is None:
        raise ValueError("F-2 workbook without a national Total row")
    return {"national": national, "states": states}


def fetch_quarter(kind: str, qend: date) -> dict | None:
    """Parsed table for one quarter, or None if not (yet) published."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    stem = f"f2_{kind}_{qend.isoformat()}"
    path = os.path.join(settings.cache_dir, stem + ".xlsx")
    miss = os.path.join(settings.cache_dir, stem + ".missing")
    if not os.path.exists(path):
        if os.path.exists(miss) and time.time() - os.path.getmtime(miss) < _MISS_TTL:
            return None
        try:
            r = httpx.get(url(kind, qend), timeout=settings.http_timeout_seconds,
                          follow_redirects=True)
            if r.status_code == 404:
                open(miss, "w").close()
                return None
            r.raise_for_status()
            if not r.content.startswith(b"PK"):          # an HTML error page, not xlsx
                open(miss, "w").close()
                return None
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("F-2 %s %s fetch failed: %s", kind, qend, exc)
            return None
    try:
        return parse_f2(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("F-2 %s %s parse failed: %s", kind, qend, exc)
        return None


def new_quarters(after: tuple[int, int], today: date | None = None) -> dict[str, dict]:
    """F-2 tables for quarters after `after` (year, quarter) that have ended
    by today, stopping at the first one not yet published.
    -> {'2026Q3': {'3month': parsed, '12month': parsed}, ...}"""
    today = today or date.today()
    out: dict[str, dict] = {}
    y, q = after
    while True:
        q += 1
        if q == 5:
            y, q = y + 1, 1
        qe = quarter_end(y, q)
        if qe >= today:
            break
        t3, t12 = fetch_quarter("3month", qe), fetch_quarter("12month", qe)
        if t3 is None or t12 is None:
            break
        out[f"{y}Q{q}"] = {"3month": t3, "12month": t12}
    return out


def load_history() -> dict:
    """The frozen study history shipped with the backend."""
    with open(os.path.join(os.path.dirname(__file__), "distress_history.json")) as f:
        return json.load(f)
