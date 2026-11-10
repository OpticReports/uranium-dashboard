"""Treasury supply and the crowding gauges (free, keyless; verified 2026-10-15).

- MSPD Table 1 (FiscalData `mspd_table_1`): marketable debt outstanding by
  class, monthly since 2001-01, with the "Total Marketable" row the API also
  serves — so class sum == total is checked against the Treasury's own total,
  not assumed. Gross of Fed holdings (TREAST is fetched separately for that).
  Net issuance = change in outstanding between month-ends (fiscal year ends
  Sep-30).
- Term premium: Kim-Wright 10y (FRED THREEFYTP10) is primary; the NY Fed ACM
  10y comes from a 10 MB .xls (every "csv"/"xlsx" variant of the URL serves
  the same BIFF workbook), parsed with xlrd when installed, else null.
- Yields and Fed holdings: DGS10, DGS30, T10YIE, TREAST via fred_csv.
- Auctions: a thin wrapper over the existing sources/treasury.py fetcher
  (FiscalData auctions_query) — not duplicated.

Units: $ millions at source -> $bn here; yields and term premia in %.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from . import fred_csv
from .treasury import fetch_recent_auctions

logger = logging.getLogger(__name__)

MSPD_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/"
            "mspd_table_1?filter=security_type_desc:in:(Marketable,Total%20Marketable),"
            "record_date:gte:{start}&sort=record_date&page[size]=10000"
            "&fields=record_date,security_type_desc,security_class_desc,total_mil_amt")
ACM_URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"
KW_SERIES = "THREEFYTP10"
YIELD_SERIES = {"dgs10": "DGS10", "dgs30": "DGS30", "t10yie": "T10YIE"}
FED_SERIES = {"treast": "TREAST"}
_TTL = 24 * 3600

# FiscalData class description -> payload class. The inflation-indexed names
# changed over the years; FFB is listed under Marketable in Table 1.
_CLASS_MAP = {
    "Bills": "bills", "Notes": "notes", "Bonds": "bonds",
    "Treasury Inflation-Protected Securities": "tips", "Inflation-Indexed Notes": "tips",
    "Inflation-Indexed Bonds": "tips", "Floating Rate Notes": "frn",
    "Federal Financing Bank": "ffb",
}
CLASSES = ("bills", "notes", "bonds", "tips", "frn", "ffb")
COUPON_CLASSES = ("notes", "bonds", "tips", "frn")
_GAP_TOL_BN = 0.005   # 5 $mn on a ~$32tn total: the API's own rounding (one 2000s month differs by 1.1 $mn)


def _bn(v) -> float | None:
    try:
        return round(float(v) / 1000.0, 4)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# MSPD
# ---------------------------------------------------------------------------
def parse_mspd(records: list[dict]) -> dict:
    """FiscalData rows -> {months, classes: {cls: [$bn]}, coupons, bills,
    total_marketable (the API's own total row), class_sum, gap_bn}.
    Missing class in a month -> None (never 0); class_sum uses present classes."""
    by_month: dict[str, dict[str, float | None]] = {}
    totals: dict[str, float | None] = {}
    for rec in records:
        d = rec.get("record_date")
        if not d:
            continue
        typ = rec.get("security_type_desc")
        if typ == "Total Marketable":
            totals[d] = _bn(rec.get("total_mil_amt"))
        elif typ == "Marketable":
            cls = _CLASS_MAP.get(rec.get("security_class_desc", ""))
            if cls:
                cur = by_month.setdefault(d, {})
                v = _bn(rec.get("total_mil_amt"))
                cur[cls] = (cur.get(cls) or 0.0) + v if v is not None else cur.get(cls)
    months = sorted(set(by_month) | set(totals))
    classes = {c: [by_month.get(m, {}).get(c) for m in months] for c in CLASSES}
    class_sum = []
    coupons = []
    for m in months:
        row = by_month.get(m, {})
        present = [v for v in row.values() if v is not None]
        class_sum.append(round(sum(present), 4) if present else None)
        cp = [row.get(c) for c in COUPON_CLASSES if row.get(c) is not None]
        coupons.append(round(sum(cp), 4) if cp else None)
    total = [totals.get(m) for m in months]
    gap = [None if a is None or b is None else round(a - b, 4) for a, b in zip(class_sum, total)]
    return {"months": months, "classes": classes, "coupons": coupons, "bills": classes["bills"],
            "total_marketable": total, "class_sum": class_sum, "gap_bn": gap}


def fetch_mspd(start: str = "2001-01-01") -> dict:
    """Marketable Treasury debt outstanding by class, monthly, $bn."""
    u = MSPD_URL.format(start=start)
    body, st = fred_csv.download_cached("mspd_table1.json", u, _TTL,
                                        validate=lambda b: b[:1] == b"{" and b'"data"' in b[:200])
    base = {"asof": None, "months": [], "classes": {c: [] for c in CLASSES}, "coupons": [],
            "bills": [], "total_marketable": [], "class_sum": [], "gap_bn": [], "unit": "$bn",
            "basis": ("MSPD Table 1, marketable Treasury debt outstanding by class, month-end, "
                      "gross of Fed holdings; coupons = notes + bonds + TIPS + FRNs; total = the "
                      "API's own Total Marketable row"),
            "src": u, "status": "error", "checks": {}}
    if body is None:
        return base
    try:
        recs = json.loads(body.decode("utf-8")).get("data", [])
        p = parse_mspd(recs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MSPD parse failed: %s", exc)
        return base
    gaps = [abs(g) for g in p["gap_bn"] if g is not None]
    no_total = sum(g is None for g in p["gap_bn"])     # a month without a Total Marketable row = check failed
    ok = bool(p["months"]) and no_total == 0 and bool(gaps) and max(gaps) <= _GAP_TOL_BN
    if not ok:
        logger.warning("MSPD: class sum vs Total Marketable check failed (max gap %.4f $bn, %d months without total)",
                       max(gaps) if gaps else float("nan"), no_total)
    base.update(p)
    base.update({"asof": p["months"][-1] if p["months"] else None,
                 "status": st if p["months"] else "error",            # zero rows is never "ok"
                 "checks": {"class_sum_equals_total": ok,
                            "max_abs_gap_bn": round(max(gaps), 4) if gaps else None,
                            "months_without_total": no_total}})
    return base


def net_issuance(mspd: dict) -> dict:
    """Change in outstanding by fiscal year (Oct-Sep, keyed by FY) and calendar
    year, $bn: {fy: {year: {net_marketable, coupons, bills, ffb, from, to,
    complete}}, cy: {...}}. A year whose end month is not yet published is
    marked complete=False and measured to the latest month."""
    months = mspd.get("months", [])
    idx = {m: i for i, m in enumerate(months)}

    def _at(key: str, m: str) -> float | None:
        if m not in idx:
            return None
        if key == "ffb":
            return mspd["classes"]["ffb"][idx[m]]
        return mspd[key][idx[m]]

    def _delta(a: str, b: str) -> dict:
        out: dict = {"from": a, "to": b}
        for key, name in (("total_marketable", "net_marketable"), ("coupons", "coupons"),
                          ("bills", "bills"), ("ffb", "ffb")):
            x, y = _at(key, a), _at(key, b)
            out[name] = None if x is None or y is None else round(y - x, 3)
        return out

    def _end(year: int, month: int) -> str | None:
        cands = [m for m in months if m.startswith(f"{year:04d}-{month:02d}")]
        return cands[-1] if cands else None

    latest = months[-1] if months else None
    fy: dict[int, dict] = {}
    cy: dict[int, dict] = {}
    if latest:
        for y in range(int(months[0][:4]) + 1, int(latest[:4]) + 2):
            for book, end_month in ((fy, 9), (cy, 12)):
                a, b = _end(y - 1, end_month), _end(y, end_month)
                to = b or latest           # an unfinished year runs to the latest month
                if a and to > a:
                    book[y] = {**_delta(a, to), "complete": b is not None}
    return {"fy": fy, "cy": cy, "unit": "$bn",
            "basis": "change in MSPD marketable outstanding between month-ends; FY ends Sep-30"}


# ---------------------------------------------------------------------------
# Term premium
# ---------------------------------------------------------------------------
def _series_block(dates: list[date], values: list[float | None], src: str, status: str | None,
                  unit: str = "%") -> dict:
    lat = fred_csv.latest(dates, values)
    return {"dates": [d.isoformat() for d in dates], "values": values,
            "latest": lat[1] if lat else None, "asof": lat[0].isoformat() if lat else None,
            "unit": unit, "src": src, "status": status or "error"}


def parse_acm_rows(rows: list[tuple[object, object]], start: str | None = None
                   ) -> tuple[list[date], list[float | None]]:
    """(date-ish, tp10-ish) rows -> (dates, values). Dates may be ISO strings,
    'DD-Mon-YYYY' strings or date objects; non-numeric values -> None."""
    lo = datetime.strptime(start, "%Y-%m-%d").date() if start else None
    out_d: list[date] = []
    out_v: list[float | None] = []
    for d_raw, v_raw in rows:
        d: date | None = None
        if isinstance(d_raw, datetime):
            d = d_raw.date()
        elif isinstance(d_raw, date):
            d = d_raw
        else:
            t = str(d_raw).strip()
            for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%m/%d/%Y"):
                try:
                    d = datetime.strptime(t, fmt).date()
                    break
                except ValueError:
                    continue
        if d is None or (lo and d < lo):
            continue
        try:
            v = float(v_raw) if v_raw not in (None, "") else None
        except (TypeError, ValueError):
            v = None
        out_d.append(d)
        out_v.append(v)
    order = sorted(range(len(out_d)), key=lambda i: out_d[i])
    return [out_d[i] for i in order], [out_v[i] for i in order]


def _acm_rows_from_xls(body: bytes) -> list[tuple[object, object]]:
    """'ACM Daily' sheet -> [(date, ACMTP10)]; needs xlrd (BIFF workbook)."""
    import xlrd  # optional dependency; ImportError handled by the caller

    wb = xlrd.open_workbook(file_contents=body)
    sh = wb.sheet_by_name("ACM Daily")
    hdr = [str(c.value).strip().upper() for c in sh.row(0)]
    di, vi = hdr.index("DATE"), hdr.index("ACMTP10")
    rows: list[tuple[object, object]] = []
    for i in range(1, sh.nrows):
        c = sh.cell(i, di)
        if c.ctype == xlrd.XL_CELL_DATE:
            d: object = xlrd.xldate_as_datetime(c.value, wb.datemode).date()
        elif isinstance(c.value, float):
            d = xlrd.xldate_as_datetime(c.value, wb.datemode).date()
        else:
            d = c.value
        rows.append((d, sh.cell(i, vi).value))
    return rows


def fetch_acm_tp10(start: str = "2015-01-01") -> dict | None:
    """NY Fed ACM 10y term premium (daily, %). None when the workbook cannot
    be fetched or parsed (xlrd missing) — the panel then shows KW only."""
    body, st = fred_csv.download_cached("acm_term_premium.xls", ACM_URL, _TTL,
                                        validate=lambda b: b[:4] == b"\xd0\xcf\x11\xe0")
    if body is None:
        return None
    try:
        rows = _acm_rows_from_xls(body)
    except ImportError:
        logger.warning("ACM term premium skipped: xlrd is not installed")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("ACM xls parse failed: %s", exc)
        return None
    ds, vs = parse_acm_rows(rows, start)
    if not ds:
        return None
    return _series_block(ds, vs, ACM_URL, st)


def fetch_term_premium(start: str = "2015-01-01") -> dict:
    """{kw10: {...}, acm10: {...}|None}. Kim-Wright is the primary gauge."""
    ds, vs = fred_csv.fetch_csv(KW_SERIES, start)
    kw = _series_block(ds, vs, fred_csv.url(KW_SERIES), fred_csv.status(KW_SERIES))
    kw["basis"] = "Kim-Wright 10y term premium (Fed), daily, %"
    acm = fetch_acm_tp10(start)
    if acm is not None:
        acm["basis"] = "Adrian-Crump-Moench 10y term premium (NY Fed), daily, %"
    return {"kw10": kw, "acm10": acm}


# ---------------------------------------------------------------------------
# Yields, Fed holdings
# ---------------------------------------------------------------------------
def fetch_yields(start: str = "2015-01-01") -> dict:
    """DGS10 / DGS30 / T10YIE (%) and TREAST ($bn, weekly Fed Treasury holdings)."""
    ids = list(YIELD_SERIES.values()) + list(FED_SERIES.values())
    raw = fred_csv.fetch_many(ids, start)
    out: dict = {}
    for key, sid in YIELD_SERIES.items():
        ds, vs = raw.get(sid, ([], []))
        out[key] = _series_block(ds, vs, fred_csv.url(sid), fred_csv.status(sid))
    ds, vs = raw.get(FED_SERIES["treast"], ([], []))
    out["fed_treast"] = _series_block(ds, [_bn(v) if v is not None else None for v in vs],
                                      fred_csv.url(FED_SERIES["treast"]),
                                      fred_csv.status(FED_SERIES["treast"]), unit="$bn")
    out["fed_treast"]["basis"] = "Fed H.4.1 Treasury securities held outright, weekly, $bn"
    return out


# ---------------------------------------------------------------------------
# Auctions (wrapper over sources/treasury.py)
# ---------------------------------------------------------------------------
def tenor_label(term: str | None) -> str | None:
    """'10-Year' -> '10y'; a reopening '29-Year 10-Month' -> '30y'."""
    if not term:
        return None
    t = term.strip().lower()
    years = months = 0
    for part in t.split():
        if part.endswith("-year"):
            try:
                years = int(part.split("-")[0])
            except ValueError:
                return term
        elif part.endswith("-month"):
            try:
                months = int(part.split("-")[0])
            except ValueError:
                return term
    if years == 0 and months == 0:
        return term
    return f"{years + (1 if months else 0)}y"


def fetch_auctions(limit: int = 60) -> list[dict]:
    """Recent completed coupon auctions, oldest -> newest:
    {date, tenor, term, high_yield (%), btc, indirect_pct}. [] on failure."""
    out = []
    for a in fetch_recent_auctions(limit):
        out.append({"date": a.get("auction_date"), "tenor": tenor_label(a.get("security_term")),
                    "term": a.get("security_term"), "security_type": a.get("security_type"),
                    "high_yield": a.get("high_yield"), "btc": a.get("bid_to_cover"),
                    "indirect_pct": a.get("indirect_pct"), "dealer_pct": a.get("dealer_pct"),
                    "direct_pct": a.get("direct_pct")})
    return out


AUCTION_SRC = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
               "auctions_query")
