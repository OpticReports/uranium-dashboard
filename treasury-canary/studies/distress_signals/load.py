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


def us_pop(pop: dict[str, dict[int, float]] | None = None) -> dict[int, float]:
    """50 states + DC population (thousands) by year."""
    pop = pop or state_pop()
    years = set.intersection(*(set(v) for v in pop.values()))
    return {y: sum(pop[s][y] for s in STATES) for y in sorted(years)}


def pop_at(pop_by_year: dict[int, float], year: float) -> float:
    """Population at a fractional year. July-1 estimates sit at year + 0.5:
    linear between them, extrapolated at the last year's growth rate. The
    per-capita basis everywhere is 50 states + DC filings over this population
    at the filing window's midpoint (12 months to Jun-2026 -> 2026.0)."""
    y0 = int(year - 0.5)
    if y0 in pop_by_year and y0 + 1 in pop_by_year:
        w = year - 0.5 - y0
        return pop_by_year[y0] * (1 - w) + pop_by_year[y0 + 1] * w
    ys = sorted(pop_by_year)
    last, prev = ys[-1], ys[-2]
    return pop_by_year[last] * (pop_by_year[last] / pop_by_year[prev]) ** (year - 0.5 - last)


def nonbusiness_annual_50dc() -> dict[int, int]:
    """Calendar-year consumer filings in the 50 states + DC (territories
    dropped): ABI district tables 1980-2000, AO F-2 12-month tables (December)
    2001+."""
    out: dict[int, int] = defaultdict(int)
    for r in _rows(os.path.join(DER, "abi_district_annual_1980_2000.csv")):
        if r["row_kind"] == "district" and r["is_territory"] == "0":
            out[int(r["year"])] += int(r["nonbusiness"])
    s12 = f2_state("12month", "nb_all")
    for t in sorted(next(iter(s12.values()))):
        if t % 4 == 3:
            out[t // 4] = sum(s12[s][t] for s in STATES)
    return dict(sorted(out.items()))


def state_claims_weekly() -> dict[str, dict[dt.date, int]]:
    """DOL ETA 539 column c3 (state UI initial claims) by week-ending date."""
    out: dict[str, dict[dt.date, int]] = defaultdict(dict)
    with open(os.path.join(DATA, "dol_ar539", "ar539.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["st"] in STATES and r["c3"] not in ("", None):
                out[r["st"]][dt.date.fromisoformat(r["rptdate"])] = int(r["c3"])
    return dict(out)


# ------------------------------------------------------------ bottoms study (distress-bottoms.md)
DNB_COUNT_SEGMENTS = ("M0929AUSM155NNBR", "M0929BUSM155NNBR", "M0929CUSM474NNBR")
DNB_LIAB_SEGMENTS = ("M0933AUSM144NNBR", "M0933BUSM144NNBR", "M0933CUSM144NNBR")


DNB_COUNT_FIXES = {12 * 1898 + 5: 1149.0}   # 1898-06 printed 1,449: HSUS V24 annual and the
#                                            mfg + trade + other identity give 1,149 (+300 typo)


def dnb_count_segments(fix: bool = True) -> list[dict[int, float]]:
    """D&B number of commercial failures, monthly NSA, as its three separately
    defined segments (1894-01..1938-08, 1934-06..1939-12, 1939-01..1965-06).
    Never spliced: in their overlaps the second runs ~5% above the first and the
    third 24-38% above the second, so growth is computed within a segment only.
    `fix` applies DNB_COUNT_FIXES to the first segment."""
    segs = [dict(nber_monthly(sid)) for sid in DNB_COUNT_SEGMENTS]
    if fix:
        segs[0].update(DNB_COUNT_FIXES)
    return segs


def dnb_liability_segments() -> list[dict[int, float]]:
    """D&B liabilities of commercial failures ($m, nominal, monthly NSA; banks
    and railroads excluded) as two segments: 1894-01..1938-08 (the 1934-39
    segment is dominated by Section 77-B reorganisations and is not used) and
    1939-01..1983-12, continued with BCD series 14 from 1968-02 (the two agree
    within 0.05 over 1953-01..1968-01) and ended before D&B's 1984 change of
    coverage and method."""
    a, _, c = (nber_monthly(sid) for sid in DNB_LIAB_SEGMENTS)
    c = dict(c)
    c.update({m: v for m, v in bcd14().items() if max(c) < m <= 12 * 1983 + 11})
    return [a, c]


def hsus_dnb_annual() -> dict[int, dict[str, float]]:
    """HSUS (Bicentennial ed.) Series V 24 (number of failures) and V 27
    (liabilities, $m) annual totals 1893-1965: the gate for the monthly files."""
    return {int(r["year"]): {"number": int(r["failures_number"]), "liabilities": float(r["liabilities_mil_usd"])}
            for r in _rows(os.path.join(DER, "hsus_v24_v27_dnb_failures_annual_1893_1965.csv"))}


def shiller_monthly() -> tuple[dict[int, float], dict[int, float]]:
    """Shiller S&P composite monthly price P (average of daily closes; Cowles
    before 1926) and annualised dividend D, 1871-01..2024-09. Aug-Nov 1914 are
    dropped: the exchange was closed and the file repeats July."""
    import xlrd
    sh = xlrd.open_workbook(os.path.join(DATA, "shiller", "ie_data.xls")).sheet_by_name("Data")
    P: dict[int, float] = {}
    Dv: dict[int, float] = {}
    for r in range(8, sh.nrows):
        d = sh.cell_value(r, 0)
        if not isinstance(d, float):
            continue
        y = int(d)
        mo = int(round((d - y) * 100))
        m = 12 * y + mo - 1
        if 12 * 1914 + 7 <= m <= 12 * 1914 + 10:
            continue
        if isinstance(sh.cell_value(r, 1), float):
            P[m] = sh.cell_value(r, 1)
        if isinstance(sh.cell_value(r, 2), float):
            Dv[m] = sh.cell_value(r, 2)
    return P, Dv


def equity_total_return() -> dict[int, float]:
    """Total-return index from Shiller P and D: TR(m) = TR(m-1) * (P(m) + D(m)/12)
    / P(m-1); a missing month (1914 closure) carries the price return across it."""
    P, Dv = shiller_monthly()
    ms = sorted(m for m in P if m in Dv)
    tr = {ms[0]: 1.0}
    for prev, m in zip(ms, ms[1:]):
        tr[m] = tr[prev] * (P[m] + Dv[m] / 12 * (m - prev)) / P[prev]
    return tr


def claims_monthly_nsa() -> tuple[dict[int, float], dict[int, int]]:
    """Initial claims (ICNSA): mean weekly claims over the weeks ending
    (Saturday) in each month, and each month's release month = the month of
    its last week-end + 5 days. The latest month is dropped while incomplete."""
    w = claims_weekly(sa=False)
    by: dict[int, list] = defaultdict(list)
    for d, v in w.items():
        by[12 * d.year + d.month - 1].append((d, v))
    last = max(w)
    if (last + dt.timedelta(days=7)).month == last.month:     # the latest month is still incomplete
        by.pop(12 * last.year + last.month - 1, None)
    val = {m: sum(v for _, v in xs) / len(xs) for m, xs in by.items()}
    rel = {}
    for m, xs in by.items():
        r = max(d for d, _ in xs) + dt.timedelta(days=5)
        rel[m] = 12 * r.year + r.month - 1
    return val, rel


def equity_monthly() -> tuple[dict[int, float], dict[int, float]]:
    """Monthly-average stock price levels as two sources, never compared across
    the seam: Cowles/S&P all-common-stocks index 1871-01..1956-12 (NYSE closed
    Aug-Nov 1914) and OECD US share prices 1957-01 onward."""
    return (fred_monthly("M1125AUSM343NNBR", "fred_targets"),
            fred_monthly("SPASTT01USM661N", "fred_targets"))


def claims_weekly(sa: bool = True) -> dict[dt.date, float]:
    """Initial jobless claims by week-ending Saturday, 1967-01-07 onward."""
    return {dt.date.fromisoformat(d): v for d, v in fred("ICSA" if sa else "ICNSA", "fred_targets").items()}
