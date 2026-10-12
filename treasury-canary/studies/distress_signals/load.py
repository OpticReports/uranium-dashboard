"""Loaders for the frozen distress-signals data (data/MANIFEST.md).

Every file under data/ is a downloaded or derived table; this module only
parses CSVs. Quarters are keyed by qi = 4*year + (quarter - 1), months by the
engine's month index, years by the integer year.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DER = os.path.join(DATA, "derived")

STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
          "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY").split()
TERRITORIES = {"PR", "VI", "GU", "MP"}
# Census divisions (DC in South Atlantic)
DIVISIONS = {
    "New England": "CT ME MA NH RI VT", "Middle Atlantic": "NJ NY PA",
    "East North Central": "IL IN MI OH WI", "West North Central": "IA KS MN MO NE ND SD",
    "South Atlantic": "DE DC FL GA MD NC SC VA WV", "East South Central": "AL KY MS TN",
    "West South Central": "AR LA OK TX", "Mountain": "AZ CO ID MT NV NM UT WY",
    "Pacific": "AK CA HI OR WA"}
DIVISION_OF = {s: d for d, ss in DIVISIONS.items() for s in ss.split()}
assert sorted(DIVISION_OF) == sorted(STATES)


def qi(y: int, q: int) -> int:
    return 4 * y + q - 1


def qi_of_date(d: str) -> int:
    y, m = int(d[:4]), int(d[5:7])
    return qi(y, (m - 1) // 3 + 1)


def qstr(i: int) -> str:
    return f"{i // 4}Q{i % 4 + 1}"


def q_end_month(i: int) -> int:
    """Month index of a quarter's last month."""
    return 12 * (i // 4) + 3 * (i % 4) + 2


def mi_of_date(d: str) -> int:
    return 12 * int(d[:4]) + int(d[5:7]) - 1


def _rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def fred(sid: str, folder: str = "fred") -> dict[str, float]:
    """FRED fredgraph CSV -> {date string: value} (missing '.' dropped)."""
    out = {}
    with open(os.path.join(DATA, folder, f"{sid}.csv"), newline="") as f:
        for r in csv.reader(f):
            if r and r[0][:1].isdigit() and r[1] not in ("", "."):
                out[r[0]] = float(r[1])
    return out


def fred_monthly(sid, folder="fred"):
    return {mi_of_date(d): v for d, v in fred(sid, folder).items()}


def fred_quarterly(sid, folder="fred"):
    return {qi_of_date(d): v for d, v in fred(sid, folder).items()}


# ------------------------------------------------------------ national filings
def abi_quarterly_business() -> dict[int, int]:
    return {qi(int(r["year"]), int(r["quarter"])): int(r["business_filings"])
            for r in _rows(os.path.join(DER, "abi_quarterly_business_filings_1980_2025.csv"))}


def abi_quarterly_nonbusiness() -> dict[int, int]:
    return {qi(int(r["year"]), int(r["quarter"])): int(r["nonbusiness_total"])
            for r in _rows(os.path.join(DER, "abi_quarterly_nonbusiness_by_chapter_1994_2025.csv"))}


def abi_annual() -> dict[int, dict[str, int]]:
    return {int(r["year"]): {"total": int(r["total_filings"]), "business": int(r["business_filings"]),
                             "nonbusiness": int(r["nonbusiness_filings"])}
            for r in _rows(os.path.join(DER, "abi_annual_business_nonbusiness_1980_2025.csv"))}


def chapter12_annual() -> dict[int, int]:
    return {int(r["year"]): int(r["chapter12_filings"])
            for r in _rows(os.path.join(DER, "abi_chapter12_annual_1986_2025.csv"))}


_F2_FILES = {"3month": "uscourts_f2_3month_by_district_2001Q1_2026Q2.csv",
             "12month": "uscourts_f2_12month_by_district_2001Q1_2026Q2.csv",
             "1month": "uscourts_f2_1month_by_district_2013M01_2026M06.csv"}
_f2_cache: dict[str, list[dict]] = {}


def f2(kind: str) -> list[dict]:
    if kind not in _f2_cache:
        _f2_cache[kind] = _rows(os.path.join(DER, _F2_FILES[kind]))
    return _f2_cache[kind]


def f2_national(kind: str, col: str) -> dict[int, int]:
    """AO F-2 national row by quarter (period_end) for 3month / 12month."""
    return {qi_of_date(r["period_end"]): int(r[col]) for r in f2(kind) if r["row_kind"] == "national"}


def f2_state(kind: str, col: str) -> dict[str, dict[int, int]]:
    """Sum of district rows by state postal code (territories dropped)."""
    out: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in f2(kind):
        if r["row_kind"] != "district" or r["state"] in TERRITORIES or not r["state"]:
            continue
        out[r["state"]][qi_of_date(r["period_end"])] += int(r[col])
    assert set(out) == set(STATES), sorted(set(out) ^ set(STATES))
    return {s: dict(v) for s, v in out.items()}


# ------------------------------------------------------------ D&B / BCD
def bcd14() -> dict[int, float]:
    return {mi_of_date(r["month"] + "-01"): float(r["value_mil_usd"])
            for r in _rows(os.path.join(DER, "bcd_series14_liabilities_monthly_1953_1986.csv"))}


def nber_monthly(sid: str) -> dict[int, float]:
    return fred_monthly(sid, "fred_nber")


# ------------------------------------------------------------ state labour data
def state_ur() -> dict[str, dict[int, float]]:
    return {s: fred_monthly(f"{s}UR", "fred_state_ur") for s in STATES}


def state_payroll_nsa() -> dict[str, dict[int, float]]:
    return {s: fred_monthly(f"{s}NAN", "fred_state_payroll_nsa") for s in STATES}


def state_pop() -> dict[str, dict[int, float]]:
    """Census July-1 resident population (thousands), keyed by year."""
    return {s: {int(d[:4]): v for d, v in fred(f"{s}POP", "fred_state_pop").items()} for s in STATES}


def state_claims_weekly() -> dict[str, dict[dt.date, int]]:
    """DOL ETA 539 column c3 (state UI initial claims) by week-ending date."""
    out: dict[str, dict[dt.date, int]] = defaultdict(dict)
    with open(os.path.join(DATA, "dol_ar539", "ar539.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["st"] in STATES and r["c3"] not in ("", None):
                out[r["st"]][dt.date.fromisoformat(r["rptdate"])] = int(r["c3"])
    return dict(out)
