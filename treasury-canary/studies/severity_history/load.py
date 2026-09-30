"""Frozen-data bundle for the severity history study, assembled exactly as the
live fetch_bundle does for the severity inputs: every FRED series from
1976-01-01, the ICE BofA HY spread spliced onto its frozen pre-truncation
history, FINRA monthly margin debt."""
from __future__ import annotations

import csv
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))

from app.config import FRED_SEVERITY  # noqa: E402

DATA = os.path.join(HERE, "data")
START = date(1976, 1, 1)
SEVERITY_KEYS = {**FRED_SEVERITY, "gdp": "GDP", "effr": "EFFR", "hy_oas": "BAMLH0A0HYM2"}


def fred(sid: str, start: date = START):
    d, v = [], []
    for r in list(csv.reader(open(os.path.join(DATA, f"{sid}.csv"))))[1:]:
        dd = date.fromisoformat(r[0])
        if dd < start:
            continue
        d.append(dd)
        v.append(float(r[1]) if r[1] not in (".", "") else None)
    return d, v


def bundle() -> dict:
    from app.sources.finra_margin import parse_margin_workbook
    from app.sources.ice_reference import splice
    out = {}
    for key, sid in SEVERITY_KEYS.items():
        path = os.path.join(DATA, f"{sid}.csv")
        if key == "hy_oas":
            d, v = fred(sid) if os.path.exists(path) else ([], [])
            out[key] = splice(sid, d, v)
        elif os.path.exists(path):
            out[key] = fred(sid)
    out["margin_debit"] = parse_margin_workbook(os.path.join(DATA, "finra_margin.xlsx"))["margin_debit"]
    return out
