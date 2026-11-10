"""Japan: BoJ balance-of-payments flows to the US and MOF securities flows
by investor type (free, keyless; verified 2026-10-15).

- BoJ `bp_m_en.zip` (monthly BoP flat file, 100 million yen): series
  BPPI6D3N9US = Japanese residents' net acquisition of US LONG-TERM DEBT
  securities (all issuers); BPPI6D3NAUS = the SOVEREIGN part, which the MOF
  appendix footnote defines as government + government agency + local
  government bonds. The residual (total - sovereign) is therefore ~US
  corporate bonds incl. corporate ABS: the one free series that separates
  "Japan bought Treasuries" from "Japan bought US corporates". 2014-01 ->.
- MOF `monthb3.csv`: residents' net purchases of FOREIGN (all countries)
  long-term debt by designated-investor type — banks, trust banks, trust
  accounts (= pension money), life/non-life insurers, investment trusts,
  financial-instruments firms, others. Columns are mapped BY HEADER NAME,
  never by position. 2005-01 ->.
- MOF `week.csv`: the same flows weekly, by security type only (no investor
  split), one-week lag.
- MOF `jgbcm_all.csv`: JGB par curve, daily since 1974, Japanese-era dates
  (S/H/R); the current month comes from the English `jgbcme.csv`.

All MOF/BoJ files are Shift-JIS (cp932) except the BoJ zip (UTF-8 BOM).
Units: source 100m JPY -> JPY trn here; JGB yields in %.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import unicodedata
import zipfile
from datetime import date

from . import fred_csv

logger = logging.getLogger(__name__)

BOJ_URL = "https://www.stat-search.boj.or.jp/info/bp_m_en.zip"
MOF_BASE = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/"
MOF_MONTHB3_URL = MOF_BASE + "monthb3.csv"
MOF_WEEK_URL = MOF_BASE + "week.csv"
MOF_JGB_ALL_URL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
MOF_JGB_CUR_URL = "https://www.mof.go.jp/english/jgbs/reference/interest_rate/jgbcme.csv"
MOF_SOV_DEF_URL = ("https://www.mof.go.jp/policy/international_policy/reference/"
                   "balance_of_payments/preliminary/bppi202608.pdf")
_TTL = 24 * 3600
_HUNDRED_MN_TO_TRN = 1.0 / 10_000.0

BOJ_TOTAL = "BPPI6D3N9US"      # Portfolio Investment Assets/Long-term debt securities/U.S.A./Net
BOJ_SOVEREIGN = "BPPI6D3NAUS"  # Portfolio Investment Assets/Sovereign(Long-term)/U.S.A./Net

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _num(cell: str | None) -> float | None:
    """'89,060' -> 89060.0; '-', '' -> None (a gap is never a zero)."""
    t = (cell or "").strip().replace(",", "")
    if t in ("", "-", "—", "n.a."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _trn(v: float | None) -> float | None:
    return None if v is None else round(v * _HUNDRED_MN_TO_TRN, 4)


def _norm(cell: str) -> str:
    """Header normaliser: NFKC (full-width parens/letters -> ASCII), drop all
    whitespace, lowercase. 'Banks（Banking Accounts)' -> 'banks(bankingaccounts)'."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", cell or "")).lower()


def _rows(raw: bytes, enc: str = "cp932") -> list[list[str]]:
    return list(csv.reader(io.StringIO(raw.decode(enc, errors="replace"))))


def rolling_12m(values: list[float | None]) -> list[float | None]:
    """Trailing 12-observation sums; None wherever the window has a gap."""
    out: list[float | None] = []
    for i in range(len(values)):
        win = values[max(0, i - 11):i + 1]
        out.append(round(sum(win), 4) if len(win) == 12 and all(v is not None for v in win) else None)
    return out


def sum_last(values: list[float | None], n: int = 12) -> float | None:
    tail = values[-n:]
    if len(tail) < n or any(v is None for v in tail):
        return None
    return round(sum(tail), 4)


# ---------------------------------------------------------------------------
# BoJ BoP: US long-term debt, sovereign vs residual
# ---------------------------------------------------------------------------
def parse_boj_csv(text: str, codes: tuple[str, ...] = (BOJ_TOTAL, BOJ_SOVEREIGN)
                  ) -> dict[str, dict[str, float | None]]:
    """bp_m_en.csv -> {code: {YYYY-MM: value in 100m JPY | None}}.
    Row 0 carries YYYYMM dates from column 4; data rows are
    [code, dataset, name, unit, v...]. Empty cells (future months) -> None."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    dates = [c.strip() for c in rows[0]]
    out: dict[str, dict[str, float | None]] = {}
    for r in rows[1:]:
        if r and r[0].strip() in codes:
            series: dict[str, float | None] = {}
            for d, v in zip(dates[4:], r[4:]):
                if re.fullmatch(r"\d{6}", d):
                    series[f"{d[:4]}-{d[4:]}"] = _num(v)
            out[r[0].strip()] = series
    return out


def _is_zip(body: bytes) -> bool:
    return body[:2] == b"PK"


def fetch_boj_us_ltdebt(start: str = "2014-01") -> dict:
    """Monthly Japanese net purchases of US long-term debt: total, sovereign
    and the non-sovereign residual (JPY trn). Residual == total - sovereign
    for every month, None where either side is missing."""
    body, st = fred_csv.download_cached("boj_bp_m_en.zip", BOJ_URL, _TTL, validate=_is_zip)
    base = {"asof": None, "months": [], "total": [], "sovereign": [], "nonsovereign": [],
            "unit": "JPY trn", "basis": ("BoJ BoP (BPM6), Japanese residents' net acquisition "
                                         "(+ = bought) of US long-term debt securities; sovereign = "
                                         "government + government agency + local government bonds "
                                         "(MOF footnote); non-sovereign = residual, ~corporate incl. ABS"),
            "series": {"total": BOJ_TOTAL, "sovereign": BOJ_SOVEREIGN},
            "src": {"boj": BOJ_URL, "sovereign_definition": MOF_SOV_DEF_URL}, "status": "error"}
    if body is None:
        return base
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            text = zf.read(name).decode("utf-8-sig", errors="replace")
        parsed = parse_boj_csv(text)
        tot, sov = parsed.get(BOJ_TOTAL, {}), parsed.get(BOJ_SOVEREIGN, {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("BoJ bp_m_en parse failed: %s", exc)
        return base
    if not tot:
        return base
    months = sorted(m for m, v in tot.items() if m >= start and v is not None)
    if not months:          # every value cell empty / format drift: an empty panel is an error, not "ok"
        logger.warning("BoJ bp_m_en: no data rows for %s from %s", BOJ_TOTAL, start)
        return base
    total = [_trn(tot.get(m)) for m in months]
    sovereign = [_trn(sov.get(m)) for m in months]
    nonsov = [round(t - s, 4) if t is not None and s is not None else None
              for t, s in zip(total, sovereign)]
    base.update({"asof": months[-1] if months else None, "months": months, "total": total,
                 "sovereign": sovereign, "nonsovereign": nonsov,
                 "total_12m": sum_last(total), "sovereign_12m": sum_last(sovereign),
                 "nonsovereign_12m": sum_last(nonsov), "status": st})
    return base


# ---------------------------------------------------------------------------
# MOF monthb3: by investor type (header-name mapping)
# ---------------------------------------------------------------------------
# payload key -> the normalised English header cell that names the group.
# "all" is the leftmost group, headed 各部門計 / (a+b+c+d) in the MOF file.
MOF_INVESTOR_HEADERS: dict[str, tuple[str, ...]] = {
    "all": ("各部門計", "(a+b+c+d)"),
    "banks": ("banks(bankingaccounts)",),
    "trust_banks_banking": ("trustbanks(bankingaccounts)",),
    "trust_accounts": ("banksandtrustbanks(trustaccounts)",),
    "fin_instruments": ("financialinstrumentsfirms",),
    "life": ("lifeinsurancecompanies",),
    "nonlife": ("non-lifeinsurancecompanies",),
    "inv_trusts": ("investmenttrustmanagementcompanies",),
    "others": ("others",),
}
MOF_INVESTOR_LABELS = {
    "all": "All sectors", "banks": "Banks (banking accounts)",
    "trust_banks_banking": "Trust banks (banking accounts)",
    "trust_accounts": "Banks & trust banks, trust accounts (pension and other trust money)",
    "fin_instruments": "Financial instruments firms", "life": "Life insurers",
    "nonlife": "Non-life insurers", "inv_trusts": "Investment trust management companies",
    "others": "Others",
}


def _net_columns(rows: list[list[str]]) -> tuple[int, dict[str, int], dict[str, str]]:
    """Locate the Acquisition/Disposition/Net sub-header row and, for every
    wanted investor group, the column of its Net cell — found by the header
    text above it, not by position. Returns (net_row_index, key->col, key->header)."""
    net_row = next((i for i, r in enumerate(rows[:40])
                    if sum(1 for c in r if c.strip() == "Net") >= 5), None)
    if net_row is None:
        raise ValueError("monthb3: no Acquisition/Disposition/Net header row")
    net_cells = rows[net_row]
    wanted = {h: key for key, hs in MOF_INVESTOR_HEADERS.items() for h in hs}
    cols: dict[str, int] = {}
    names: dict[str, str] = {}
    for r in rows[:net_row]:
        for c, cell in enumerate(r):
            key = wanted.get(_norm(cell))
            if key is None or key in cols:
                continue
            for j in range(c, min(c + 3, len(net_cells))):
                if net_cells[j].strip() == "Net":
                    cols[key] = j
                    names[key] = cell.strip()
                    break
    missing = [k for k in MOF_INVESTOR_HEADERS if k not in cols]
    if missing:
        raise ValueError(f"monthb3: header(s) not found: {missing}")
    return net_row, cols, names


def parse_monthb3(raw: bytes) -> dict:
    """MOF monthb3.csv (cp932) -> {months, <key>: [JPY trn], column_map, ...}.
    Data rows: [year|'', '1月', 'Jan', acquisition, disposition, net, ...];
    the year is printed on January rows only and carried forward."""
    rows = _rows(raw)
    net_row, cols, names = _net_columns(rows)
    series: dict[str, dict[str, float | None]] = {k: {} for k in cols}
    year: int | None = None
    for r in rows[net_row + 1:]:
        if len(r) < 6:
            continue
        y = r[0].strip()
        if re.fullmatch(r"\d{4}", y):
            year = int(y)
        mon = _MONTHS.get(r[2].strip())
        if mon is None or year is None:
            continue
        ym = f"{year:04d}-{mon:02d}"
        if ym in series["all"]:
            continue  # a repeated month block (keep the first printing)
        for key, j in cols.items():
            series[key][ym] = _trn(_num(r[j]) if j < len(r) else None)
    months = sorted(series["all"])
    # the file pre-prints the rest of the calendar year as "-": drop unpublished months
    while months and series["all"][months[-1]] is None:
        months.pop()
    if not months:
        raise ValueError("monthb3: headers found but no data rows parsed")
    out: dict = {"months": months}
    for key in cols:
        out[key] = [series[key].get(m) for m in months]
    out["column_map"] = {key: {"header": names[key], "net_column": cols[key]} for key in cols}
    return out


def fetch_mof_by_investor_type(start: str = "2015-01") -> dict:
    """Monthly net purchases of foreign long-term debt by Japanese investor
    type (JPY trn; + = bought). Trust accounts are the pension-money line."""
    # validate = the parser itself: an HTML error page (which may well contain
    # the words "Net" or "Acquisition") can never overwrite the last good file
    body, st = fred_csv.download_cached("mof_monthb3.csv", MOF_MONTHB3_URL, _TTL,
                                        validate=fred_csv.parses(parse_monthb3))
    base = {"asof": None, "months": [], "unit": "JPY trn",
            "basis": ("MOF designated-major-investors report; residents' net acquisition of "
                      "FOREIGN long-term debt securities, all countries and issuers (not US-"
                      "specific); 100m JPY at source"),
            "labels": MOF_INVESTOR_LABELS, "src": MOF_MONTHB3_URL, "status": "error"}
    for k in MOF_INVESTOR_HEADERS:
        base[k] = []
    if body is None:
        return base
    try:
        parsed = parse_monthb3(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MOF monthb3 parse failed: %s", exc)
        return base
    keep = [i for i, m in enumerate(parsed["months"]) if m >= start]
    base["months"] = [parsed["months"][i] for i in keep]
    for k in MOF_INVESTOR_HEADERS:
        base[k] = [parsed[k][i] for i in keep]
        base[f"{k}_12m"] = sum_last(base[k])
    base.update({"asof": base["months"][-1] if base["months"] else None,
                 "column_map": parsed["column_map"],
                 "status": st if base["months"] else "error"})   # zero rows is never "ok"
    return base


# ---------------------------------------------------------------------------
# MOF week.csv: weekly by security type (assets side)
# ---------------------------------------------------------------------------
_PERIOD_RE = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*~\s*(?:(\d{4})\.\s*)?(\d{1,2})\.\s*(\d{1,2})")
_WEEK_HEADERS = {"lt_debt": "long-termdebtsecurities", "equity": "equityandinvestmentfundshares",
                 "st_debt": "short-termdebtsecurities"}


def _week_end(period: str) -> date | None:
    m = _PERIOD_RE.search(unicodedata.normalize("NFKC", period or ""))
    if not m:
        return None
    y1, m1, _d1, y2, m2, d2 = m.groups()
    year = int(y2) if y2 else int(y1) + (1 if int(m2) < int(m1) else 0)
    try:
        return date(year, int(m2), int(d2))
    except ValueError:
        return None


def parse_week(raw: bytes) -> dict:
    """MOF week.csv (cp932) -> {weeks: [YYYY-MM-DD week end], lt_debt_net,
    equity_net, st_debt_net (JPY trn)}. The first block of columns is
    '1. Portfolio Investment Assets' (residents' purchases abroad); columns
    are located by header text, Net = the sub-header cell under the group."""
    rows = _rows(raw)
    name_row = next((i for i, r in enumerate(rows[:40])
                     if any("long-termdebt" in _norm(c) for c in r)), None)
    if name_row is None:
        raise ValueError("week.csv: security-type header row not found")
    sub_row = next((i for i in range(name_row + 1, min(name_row + 4, len(rows)))
                    if sum(1 for c in rows[i] if c.strip() == "Net") >= 3), None)
    if sub_row is None:
        raise ValueError("week.csv: Acquisition/Disposition/Net row not found")
    cols: dict[str, int] = {}
    for key, h in _WEEK_HEADERS.items():
        c = next((j for j, cell in enumerate(rows[name_row]) if _norm(cell) == h), None)
        if c is None:
            raise ValueError(f"week.csv: header {h!r} not found")
        cols[key] = next(j for j in range(c, c + 3) if rows[sub_row][j].strip() == "Net")
    weeks: list[str] = []
    out: dict[str, list[float | None]] = {k: [] for k in cols}
    for r in rows[sub_row + 1:]:
        if not r:
            continue
        we = _week_end(r[0])
        if we is None:
            continue
        weeks.append(we.isoformat())
        for k, j in cols.items():
            out[k].append(_trn(_num(r[j]) if j < len(r) else None))
    if not weeks:
        raise ValueError("week.csv: headers found but no data rows parsed")
    return {"weeks": weeks, "lt_debt_net": out["lt_debt"], "equity_net": out["equity"],
            "st_debt_net": out["st_debt"]}


def fetch_mof_weekly(start: str = "2023-01-01") -> dict:
    body, st = fred_csv.download_cached("mof_week.csv", MOF_WEEK_URL, _TTL,
                                        validate=fred_csv.parses(parse_week))
    base = {"asof": None, "weeks": [], "lt_debt_net": [], "equity_net": [], "st_debt_net": [],
            "unit": "JPY trn", "basis": ("MOF weekly, residents' net acquisition of foreign "
                                         "securities by type, all countries; no investor split"),
            "src": MOF_WEEK_URL, "status": "error"}
    if body is None:
        return base
    try:
        p = parse_week(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MOF week.csv parse failed: %s", exc)
        return base
    keep = [i for i, w in enumerate(p["weeks"]) if w >= start]
    for k in ("weeks", "lt_debt_net", "equity_net", "st_debt_net"):
        base[k] = [p[k][i] for i in keep]
    base.update({"asof": base["weeks"][-1] if base["weeks"] else None,
                 "status": st if base["weeks"] else "error"})
    return base


# ---------------------------------------------------------------------------
# JGB curve
# ---------------------------------------------------------------------------
_ERA_BASE = {"S": 1925, "H": 1988, "R": 2018}   # Showa 1 = 1926, Heisei 1 = 1989, Reiwa 1 = 2019


def _jgb_date(cell: str) -> date | None:
    t = unicodedata.normalize("NFKC", (cell or "").strip())
    m = re.fullmatch(r"([SHR])(\d{1,2})\.(\d{1,2})\.(\d{1,2})", t)
    if m:
        try:
            return date(_ERA_BASE[m.group(1)] + int(m.group(2)), int(m.group(3)), int(m.group(4)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_jgb(raw: bytes, tenors: tuple[str, ...] = ("10", "30")) -> dict:
    """jgbcm_all.csv / jgbcme.csv -> {dates, y10, y30} (%). Columns found by
    header ('10年' or '10Y'); era dates S/H/R or YYYY/M/D."""
    rows = _rows(raw)
    hdr_i = next((i for i, r in enumerate(rows[:5]) if any(_norm(c) in ("10年", "10y") for c in r)), None)
    if hdr_i is None:
        raise ValueError("jgb csv: header row not found")
    hdr = [_norm(c) for c in rows[hdr_i]]
    cols = {t: next(j for j, h in enumerate(hdr) if h in (f"{t}年", f"{t}y")) for t in tenors}
    dates: list[str] = []
    out: dict[str, list[float | None]] = {f"y{t}": [] for t in tenors}
    for r in rows[hdr_i + 1:]:
        if not r:
            continue
        d = _jgb_date(r[0])
        if d is None:
            continue
        dates.append(d.isoformat())
        for t, j in cols.items():
            out[f"y{t}"].append(_num(r[j]) if j < len(r) else None)
    if not dates:
        raise ValueError("jgb csv: header found but no dated rows parsed")
    return {"dates": dates, **out}


def fetch_jgb_curve(start: str = "2015-01-01") -> dict:
    """Daily JGB 10y and 30y (%). jgbcm_all.csv ends at the prior month-end;
    the English current-month file is spliced on when it parses."""
    body, st = fred_csv.download_cached("mof_jgbcm_all.csv", MOF_JGB_ALL_URL, _TTL,
                                        validate=fred_csv.parses(parse_jgb))
    base = {"asof": None, "dates": [], "y10": [], "y30": [], "unit": "%",
            "basis": "MOF JGB par-yield curve (daily)", "src": {"history": MOF_JGB_ALL_URL,
                                                                "current_month": MOF_JGB_CUR_URL},
            "status": "error"}
    if body is None:
        return base
    try:
        p = parse_jgb(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("JGB jgbcm_all parse failed: %s", exc)
        return base
    cur, _ = fred_csv.download_cached("mof_jgbcme.csv", MOF_JGB_CUR_URL, _TTL,
                                      validate=fred_csv.parses(parse_jgb))
    if cur is not None:
        try:
            q = parse_jgb(cur)
            last = p["dates"][-1] if p["dates"] else ""
            for i, d in enumerate(q["dates"]):
                if d > last:
                    p["dates"].append(d)
                    p["y10"].append(q["y10"][i])
                    p["y30"].append(q["y30"][i])
        except Exception as exc:  # noqa: BLE001
            logger.info("JGB current-month file skipped: %s", exc)
    keep = [i for i, d in enumerate(p["dates"]) if d >= start]
    base.update({"dates": [p["dates"][i] for i in keep], "y10": [p["y10"][i] for i in keep],
                 "y30": [p["y30"][i] for i in keep]})
    base["asof"] = base["dates"][-1] if base["dates"] else None
    base["status"] = st if base["dates"] else "error"
    return base
