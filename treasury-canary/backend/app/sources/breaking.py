"""Breaking indicators for the AI-debt tab — what would show the complex
cracking, from the free daily series down to dated press prints.

  Spreads    ICE BofA OAS by rating (AAA..CCC, IG, HY) and effective yields via
             FRED's keyless CSV. FRED serves a ROLLING ~3 years of every ICE
             series (notice on the series page; ALFRED vintages were rewritten
             too), so "2026 high/low" is the honest range and nothing here ranks
             against "history". The CCC-minus-B gap is computed on matching
             dates only. Units: percentage points (12.82 = 1,282 bp).
  BAA10Y     Moody's Baa minus 10y Treasury — the long-history (1986->) spread
             substitute now that FRED cut the ICE history.
  EBP        Fed excess bond premium (Gilchrist-Zakrajsek; monthly, 1973->).
  OFR FSI    Office of Financial Research stress index + its credit sub-index.
  MOVE       ^MOVE via the Yahoo chart endpoint (same request style as
             sources/yahoo.py; Yahoo's longName for the symbol is wrong but the
             values match the investing.com MOVE page exactly).
  BDC        six listed private-credit lenders: Yahoo price against a FROZEN
             NAV table. A NAV is published only when it is sourced to an SEC
             filing (8-K exhibit or 10-Q) with the quoted text; otherwise nav
             and p_nav are null — never an aggregator's number.
  Events     app/sources/ai_debt_events.json: the frozen Jun-Oct 2026 log of
             CDS prints, bond prices, rating actions, deal concessions and
             official responses, each with a provenance badge
             (primary | press | aggregator), the source URL and the retrieval
             date. CDS and single-name prices are dated press prints, not a
             feed; the Reuters CDS article of 2026-10-15 changed intraday.

Everything is CONTEXT, not a signal — status language is "watch". Every
fetch degrades to the last cached copy ("stale") or to nulls ("error"); a gap
is None, never 0.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import date, datetime, timezone
from urllib.parse import quote

from . import fred_csv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FRED series
# ---------------------------------------------------------------------------
# bucket key -> (FRED id, label). Order is the display order (IG to junk).
OAS: dict[str, tuple[str, str]] = {
    "aaa": ("BAMLC0A1CAAA", "ICE BofA AAA US Corporate OAS"),
    "aa": ("BAMLC0A2CAA", "ICE BofA AA US Corporate OAS"),
    "a": ("BAMLC0A3CA", "ICE BofA Single-A US Corporate OAS"),
    "bbb": ("BAMLC0A4CBBB", "ICE BofA BBB US Corporate OAS"),
    "ig": ("BAMLC0A0CM", "ICE BofA US Corporate (IG) OAS"),
    "bb": ("BAMLH0A1HYBB", "ICE BofA BB US High Yield OAS"),
    "b": ("BAMLH0A2HYB", "ICE BofA Single-B US High Yield OAS"),
    "ccc": ("BAMLH0A3HYC", "ICE BofA CCC & Lower US High Yield OAS"),
    "hy": ("BAMLH0A0HYM2", "ICE BofA US High Yield OAS"),
}
YIELDS: dict[str, tuple[str, str]] = {
    "ig": ("BAMLC0A0CMEY", "ICE BofA US Corporate effective yield"),
    "hy": ("BAMLH0A0HYM2EY", "ICE BofA US High Yield effective yield"),
}
BAA10Y = "BAA10Y"
_OAS_START = "2023-10-01"      # FRED's rolling window starts 2023-10-16; asking earlier is harmless
_LONG_START = "1986-01-01"
_YEAR = 2026                   # the range year the tiles quote ("2026 high / low")

OAS_BASIS = ("ICE BofA option-adjusted spreads vs the Treasury spot curve, percentage points, daily "
             "close; FRED serves a rolling ~3 years so highs/lows are 2026 only, not history")
YIELD_BASIS = "ICE BofA effective yield, percent, daily close (all-in funding cost; rates + spread)"
BAA10Y_BASIS = "Moody's seasoned Baa corporate yield minus 10y Treasury constant maturity, percentage points, daily (1986->)"

# ---------------------------------------------------------------------------
# Other free files
# ---------------------------------------------------------------------------
EBP_URL = "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"
OFR_FSI_URL = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
EBP_BASIS = ("Fed excess bond premium (Gilchrist-Zakrajsek, FEDS Notes update): the part of the GZ "
             "corporate spread not explained by default risk, percentage points, monthly; "
             "est_prob = model recession probability")
OFR_BASIS = ("OFR Financial Stress Index, daily; 0 = average stress, positive = above average; "
             "credit = the credit sub-index")
_TTL_DAILY = 6 * 3600
_TTL_MONTHLY = 24 * 3600

# Yahoo chart endpoint — the request style of sources/yahoo.py (daily bars,
# granularity asserted). 2y daily is what the scoping pass verified.
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
_YAHOO_HEADERS = {"user-agent": "Mozilla/5.0 (canary-dashboard)"}
MOVE_SYMBOL = "^MOVE"
MOVE_BASIS = ("ICE BofA MOVE index (Treasury implied vol) via Yahoo chart daily close; the last bar can "
              "be the current session; Yahoo's longName for the symbol is mislabelled, values cross-"
              "checked against investing.com on 2026-10-14 (99.06 both)")
MOVE_XCHECK_URL = "https://www.investing.com/indices/ice-bofaml-move"

BDC_TICKERS = ["ARCC", "OBDC", "BXSL", "FSK", "MAIN", "GBDC"]
# Frozen NAV table. Only filing-sourced values are published; the others stay
# null until an 8-K / 10-Q is read (never an aggregator's number).
BDC_NAV: dict[str, dict] = {
    "ARCC": {"nav": 19.35, "nav_asof": "2026-06-30", "nav_form": "10-Q",
             "nav_src": "https://www.sec.gov/Archives/edgar/data/1287750/000162828026050307/arcc-20260630.htm",
             "quote": "NET ASSET VALUE PER SHARE $19.35 (June 30, 2026 column of the balance sheet)",
             "nav_retrieved": "2026-10-15"},
    "OBDC": {"nav": None, "nav_asof": None, "nav_form": None, "nav_src": None, "quote": None,
             "note": "no SEC filing fetched in the scoping pass; aggregator-only value not used"},
    "BXSL": {"nav": 25.53, "nav_asof": "2026-06-30", "nav_form": "8-K ex99.1 (filed 2026-08-06)",
             "nav_src": "https://www.sec.gov/Archives/edgar/data/1736035/000121390026085889/ea0300654-01_ex991.htm",
             "quote": "NAV per share on June 30, 2026 ($25.53)", "nav_retrieved": "2026-10-15"},
    "FSK": {"nav": None, "nav_asof": None, "nav_form": None, "nav_src": None, "quote": None,
            "note": "no SEC filing fetched in the scoping pass; aggregator-only value not used"},
    "MAIN": {"nav": None, "nav_asof": None, "nav_form": None, "nav_src": None, "quote": None,
             "note": "no SEC filing fetched in the scoping pass; aggregator-only value not used"},
    "GBDC": {"nav": 14.25, "nav_asof": "2026-06-30", "nav_form": "8-K earnings presentation (filed 2026-08-03)",
             "nav_src": "https://www.sec.gov/Archives/edgar/data/1476765/000147676526000047/gbdcfy2026q3epfinal.htm",
             "quote": "Net asset value of $14.25 per share, a decrease of $0.10 per share from $14.35 as of March 31, 2026",
             "nav_retrieved": "2026-10-15"},
}
BDC_BASIS = ("Price = Yahoo chart last daily close (can be the current session); NAV = last quarterly NAV "
             "per share stated in an SEC filing (frozen table, as-of and URL per row); p_nav = price / NAV; "
             "a NAV without a filing is null, so is its p_nav")

EVENTS_PATH = os.path.join(os.path.dirname(__file__), "ai_debt_events.json")
# the repo blob of the frozen log: the payload's `sources` map carries URLs only
EVENTS_SRC_URL = ("https://github.com/OpticReports/uranium-dashboard/blob/main/treasury-canary/"
                  "backend/app/sources/ai_debt_events.json")
PROVENANCE = ("primary", "press", "aggregator")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _latest(dates: list[date], values: list[float | None]) -> tuple[str | None, float | None]:
    last = fred_csv.latest(dates, values)
    return (_iso(last[0]), last[1]) if last else (None, None)


def year_range(dates: list[date], values: list[float | None], year: int = _YEAR) -> dict:
    """{hi, hi_date, lo, lo_date} over the observations in `year`; all None when
    the year has no observation (never 0)."""
    hi = lo = None
    hi_d = lo_d = None
    for d, v in zip(dates, values):
        if v is None or d.year != year:
            continue
        if hi is None or v > hi:
            hi, hi_d = v, d
        if lo is None or v < lo:
            lo, lo_d = v, d
    return {"hi": hi, "hi_date": _iso(hi_d), "lo": lo, "lo_date": _iso(lo_d)}


def _series(dates: list[date], values: list[float | None]) -> dict:
    return {"dates": [d.isoformat() for d in dates], "values": list(values)}


def _end_of_prior_year(dates: list[date], values: list[float | None], year: int = _YEAR) -> float | None:
    """Last non-missing observation dated before Jan 1 of `year` (the YTD anchor)."""
    out = None
    for d, v in zip(dates, values):
        if d.year < year and v is not None:
            out = v
    return out


def gap_on_matching_dates(a: tuple[list[date], list[float | None]],
                          b: tuple[list[date], list[float | None]]
                          ) -> tuple[list[date], list[float]]:
    """a - b on the dates where BOTH have a value. A date missing on either side
    is dropped, never filled or carried forward."""
    bm = {d: v for d, v in zip(*b) if v is not None}
    dates: list[date] = []
    vals: list[float] = []
    for d, v in zip(*a):
        if v is None or d not in bm:
            continue
        dates.append(d)
        vals.append(round(v - bm[d], 4))
    return dates, vals


def _range_fields(dates: list[date], values: list[float | None]) -> dict:
    """The memo-named hi_2026 / lo_2026 / end_2025 keys describe calendar 2026
    by construction; these data-driven aliases say which year the range covers
    so the tiles cannot quietly describe last year after 2027-01-01."""
    yr = next((d.year for d, v in zip(reversed(dates), reversed(values)) if v is not None), None)
    if yr is None:
        return {"range_year": None, "hi_ytd": None, "hi_ytd_date": None, "lo_ytd": None, "lo_ytd_date": None,
                "end_prior_year": None}
    cur = year_range(dates, values, yr)
    return {"range_year": yr, "hi_ytd": cur["hi"], "hi_ytd_date": cur["hi_date"], "lo_ytd": cur["lo"],
            "lo_ytd_date": cur["lo_date"], "end_prior_year": _end_of_prior_year(dates, values, yr)}


def _bucket(dates: list[date], values: list[float | None], sid: str, label: str, basis: str) -> dict:
    asof, latest = _latest(dates, values)
    rng = year_range(dates, values)
    return {"id": sid, "label": label, "latest": latest, "asof": asof,
            "hi_2026": rng["hi"], "hi_2026_date": rng["hi_date"],
            "lo_2026": rng["lo"], "lo_2026_date": rng["lo_date"],
            "end_2025": _end_of_prior_year(dates, values), **_range_fields(dates, values),
            "series": _series(dates, values), "basis": basis, "src": fred_csv.url(sid),
            "status": fred_csv.status(sid) or "error"}


# ---------------------------------------------------------------------------
# FRED blocks
# ---------------------------------------------------------------------------
def fetch_spreads(start: str = _OAS_START) -> tuple[dict, dict]:
    """(spreads by bucket, ccc_b_gap). Each bucket: latest, as-of, 2026 hi/lo
    with dates, end-2025 anchor, full series, source URL and status."""
    ids = [sid for sid, _ in OAS.values()]
    raw = fred_csv.fetch_many(ids, start)
    spreads = {k: _bucket(*raw.get(sid, ([], [])), sid, label, OAS_BASIS) for k, (sid, label) in OAS.items()}
    ccc, b = raw.get(OAS["ccc"][0], ([], [])), raw.get(OAS["b"][0], ([], []))
    gd, gv = gap_on_matching_dates(ccc, b)
    asof, latest = _latest(gd, gv)
    rng = year_range(gd, gv)
    gap = {"latest": latest, "asof": asof, "hi_2026": rng["hi"], "hi_2026_date": rng["hi_date"],
           "lo_2026": rng["lo"], "lo_2026_date": rng["lo_date"], "end_2025": _end_of_prior_year(gd, gv),
           **_range_fields(gd, gv), "n_dates": len(gd), "series": _series(gd, gv),
           "basis": "CCC & lower OAS minus single-B OAS, percentage points, on dates where both print",
           "src": {"ccc": fred_csv.url(OAS["ccc"][0]), "b": fred_csv.url(OAS["b"][0])},
           "status": fred_csv.worst_status([OAS["ccc"][0], OAS["b"][0]])}
    return spreads, gap


def fetch_yields(start: str = _OAS_START) -> dict:
    ids = [sid for sid, _ in YIELDS.values()]
    raw = fred_csv.fetch_many(ids, start)
    return {k: _bucket(*raw.get(sid, ([], [])), sid, label, YIELD_BASIS) for k, (sid, label) in YIELDS.items()}


def fetch_baa10y(start: str = _LONG_START) -> dict:
    d, v = fred_csv.fetch_csv(BAA10Y, start)
    return _bucket(d, v, BAA10Y, "Moody's Baa minus 10y Treasury", BAA10Y_BASIS)


# ---------------------------------------------------------------------------
# Fed EBP and OFR FSI (CSV files, header-mapped)
# ---------------------------------------------------------------------------
def _rows(body: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig", errors="replace"))))


def _num(raw) -> float | None:
    try:
        return None if raw in (None, "", ".", "NA", "NaN") else float(raw)
    except (TypeError, ValueError):
        return None


def parse_ebp(body: bytes) -> dict:
    """ebp_csv.csv: date,gz_spread,ebp,est_prob (monthly, first of month).
    Every column is resolved from the header case-insensitively; a file
    without an `ebp` column, or with an all-empty one, raises rather than
    parsing to a healthy-looking block of nulls."""
    rows = _rows(body)
    if not rows:
        raise ValueError("EBP csv: no rows")
    cols = {(k or "").strip().lower(): k for k in rows[0].keys() if k}
    dk, ek = cols.get("date"), cols.get("ebp")
    if dk is None:
        raise ValueError("EBP csv: no date column")
    if ek is None:
        raise ValueError(f"EBP csv: ebp column not found in {sorted(cols)}")
    gk, pk = cols.get("gz_spread"), cols.get("est_prob")
    months, ebp, gz, prob = [], [], [], []
    for r in rows:
        try:
            d = datetime.strptime((r.get(dk) or "").strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        months.append(d)
        ebp.append(_num(r.get(ek)))
        gz.append(_num(r.get(gk)) if gk else None)
        prob.append(_num(r.get(pk)) if pk else None)
    if not months:
        raise ValueError("EBP csv: no rows")
    if all(v is None for v in ebp):
        raise ValueError("EBP csv: ebp column empty")
    return {"dates": months, "ebp": ebp, "gz_spread": gz, "est_prob": prob}


def fetch_ebp(start: str = "1990-01-01") -> dict:
    body, st = fred_csv.download_cached("fed_ebp.csv", EBP_URL, _TTL_MONTHLY,
                                        validate=lambda b: b[:64].lower().lstrip(b"\xef\xbb\xbf").startswith(b"date,"))
    out = {"asof": None, "latest": None, "gz_spread_latest": None, "est_prob_latest": None,
           "months": [], "ebp": [], "gz_spread": [], "est_prob": [], "unit": "percentage points",
           "basis": EBP_BASIS, "src": EBP_URL, "status": "error"}
    if body is None:
        return out
    try:
        p = parse_ebp(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("EBP parse failed: %s", exc)
        return out
    lo = datetime.strptime(start, "%Y-%m-%d").date()
    keep = [i for i, d in enumerate(p["dates"]) if d >= lo]
    dates = [p["dates"][i] for i in keep]
    asof, latest = _latest(dates, [p["ebp"][i] for i in keep])
    out.update({"asof": asof, "latest": latest,
                "gz_spread_latest": _latest(dates, [p["gz_spread"][i] for i in keep])[1],
                "est_prob_latest": _latest(dates, [p["est_prob"][i] for i in keep])[1],
                "months": [f"{d.year:04d}-{d.month:02d}" for d in dates],
                "ebp": [p["ebp"][i] for i in keep], "gz_spread": [p["gz_spread"][i] for i in keep],
                "est_prob": [p["est_prob"][i] for i in keep], "status": st})
    return out


def parse_ofr_fsi(body: bytes) -> dict:
    """fsi.csv: Date, OFR FSI, Credit, Equity valuation, Safe assets, Funding, Volatility, ..."""
    dates, fsi, credit = [], [], []
    for r in _rows(body):
        dk = next((k for k in r if k and k.strip().lower() == "date"), None)
        fk = next((k for k in r if k and k.strip().lower() == "ofr fsi"), None)
        ck = next((k for k in r if k and k.strip().lower() == "credit"), None)
        if dk is None or fk is None:
            raise ValueError("OFR FSI csv: Date / OFR FSI columns not found")
        try:
            d = datetime.strptime(r[dk].strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        dates.append(d)
        fsi.append(_num(r.get(fk)))
        credit.append(_num(r.get(ck)) if ck else None)
    if not dates:
        raise ValueError("OFR FSI csv: no rows")
    return {"dates": dates, "fsi": fsi, "credit": credit}


def fetch_ofr_fsi(start: str = "2015-01-01") -> dict:
    body, st = fred_csv.download_cached("ofr_fsi.csv", OFR_FSI_URL, _TTL_DAILY,
                                        validate=lambda b: b[:64].lower().lstrip(b"\xef\xbb\xbf").startswith(b"date,"))
    out = {"asof": None, "latest": None, "credit_latest": None, "dates": [], "fsi": [], "credit": [],
           "unit": "index (0 = average)", "basis": OFR_BASIS, "src": OFR_FSI_URL, "status": "error"}
    if body is None:
        return out
    try:
        p = parse_ofr_fsi(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OFR FSI parse failed: %s", exc)
        return out
    lo = datetime.strptime(start, "%Y-%m-%d").date()
    keep = [i for i, d in enumerate(p["dates"]) if d >= lo]
    dates = [p["dates"][i] for i in keep]
    fsi = [p["fsi"][i] for i in keep]
    asof, latest = _latest(dates, fsi)
    out.update({"asof": asof, "latest": latest, "credit_latest": _latest(dates, [p["credit"][i] for i in keep])[1],
                "dates": [d.isoformat() for d in dates], "fsi": fsi,
                "credit": [p["credit"][i] for i in keep], "status": st})
    return out


# ---------------------------------------------------------------------------
# Yahoo chart: MOVE and BDC prices
# ---------------------------------------------------------------------------
def yahoo_url(symbol: str) -> str:
    return YAHOO_CHART.format(sym=quote(symbol, safe=""))   # ^MOVE -> %5EMOVE


def parse_yahoo_chart(body: bytes) -> tuple[list[date], list[float | None], dict]:
    """(dates, closes, meta) from a chart response; refuses non-daily bars (the
    Yahoo quirk documented in sources/yahoo.py)."""
    res = json.loads(body.decode("utf-8", errors="replace"))["chart"]["result"][0]
    meta = res.get("meta") or {}
    gran = meta.get("dataGranularity")
    if gran != "1d":
        raise ValueError(f"expected daily bars, got granularity {gran!r}")
    quote_ = (res.get("indicators") or {}).get("quote", [{}])[0]
    ts = res.get("timestamp") or []
    closes = quote_.get("close") or []
    dates = [datetime.fromtimestamp(t, tz=timezone.utc).date() for t in ts]
    closes = [None if c is None else float(c) for c in closes[:len(dates)]]
    return dates, closes, {"symbol": meta.get("symbol"), "regular_market_price": meta.get("regularMarketPrice"),
                           "regular_market_time": meta.get("regularMarketTime"),
                           "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
                           "fifty_two_week_low": meta.get("fiftyTwoWeekLow")}


def fetch_yahoo_daily(symbol: str) -> dict:
    """{dates, closes, meta, status} for one symbol; cached 6h, stale on failure."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in symbol)
    # validate = the parser: a 200 carrying {"chart": {"result": null, "error": ...}} or
    # non-daily bars is never written over the last good copy (stale stays recoverable)
    body, st = fred_csv.download_cached(f"yahoo_{safe}.json", yahoo_url(symbol), _TTL_DAILY,
                                        headers=_YAHOO_HEADERS, validate=fred_csv.parses(parse_yahoo_chart))
    if body is None:
        return {"dates": [], "closes": [], "meta": {}, "status": "error"}
    try:
        dates, closes, meta = parse_yahoo_chart(body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo %s parse failed: %s", symbol, exc)
        return {"dates": [], "closes": [], "meta": {}, "status": "error"}
    return {"dates": dates, "closes": closes, "meta": meta, "status": st}


def fetch_move() -> dict:
    y = fetch_yahoo_daily(MOVE_SYMBOL)
    asof, latest = _latest(y["dates"], y["closes"])
    rng = year_range(y["dates"], y["closes"])
    return {"latest": latest, "asof": asof, "hi_2026": rng["hi"], "hi_2026_date": rng["hi_date"],
            "lo_2026": rng["lo"], "lo_2026_date": rng["lo_date"],
            "end_2025": _end_of_prior_year(y["dates"], y["closes"]), **_range_fields(y["dates"], y["closes"]),
            "wk52_high": y["meta"].get("fifty_two_week_high"), "wk52_low": y["meta"].get("fifty_two_week_low"),
            "series": _series(y["dates"], y["closes"]), "basis": MOVE_BASIS,
            "src": yahoo_url(MOVE_SYMBOL), "cross_check": MOVE_XCHECK_URL, "status": y["status"]}


def p_nav(price: float | None, nav: float | None) -> float | None:
    """price / NAV, 3 dp; None whenever either side is missing or NAV is not positive."""
    if price is None or nav is None or nav <= 0:
        return None
    return round(price / nav, 3)


def fetch_bdc(tickers: list[str] | None = None) -> list[dict]:
    rows = []
    for t in tickers or BDC_TICKERS:
        y = fetch_yahoo_daily(t)
        asof, price = _latest(y["dates"], y["closes"])
        nav = BDC_NAV.get(t, {})
        rows.append({"ticker": t, "price": price, "asof": asof,
                     "nav": nav.get("nav"), "nav_asof": nav.get("nav_asof"), "nav_form": nav.get("nav_form"),
                     "p_nav": p_nav(price, nav.get("nav")), "nav_src": nav.get("nav_src"),
                     "nav_quote": nav.get("quote"), "nav_note": nav.get("note"),
                     "wk52_high": y["meta"].get("fifty_two_week_high"), "wk52_low": y["meta"].get("fifty_two_week_low"),
                     "series": _series(y["dates"], y["closes"]),
                     "src": yahoo_url(t), "status": y["status"]})
    return rows


# ---------------------------------------------------------------------------
# Frozen event log
# ---------------------------------------------------------------------------
def validate_event(e: dict) -> list[str]:
    """Problems with one event row (empty list = ok): date, text, provenance
    badge, http(s) source URL and retrieval date are all mandatory."""
    bad = []
    try:
        datetime.strptime(str(e.get("date", "")), "%Y-%m-%d")
    except ValueError:
        bad.append("date")
    if not isinstance(e.get("text"), str) or not e["text"].strip():
        bad.append("text")
    if e.get("provenance") not in PROVENANCE:
        bad.append("provenance")
    src = e.get("src")
    if not isinstance(src, str) or not src.startswith(("http://", "https://")):
        bad.append("src")
    try:
        datetime.strptime(str(e.get("retrieved", "")), "%Y-%m-%d")
    except ValueError:
        bad.append("retrieved")
    return bad


def load_events(path: str = EVENTS_PATH) -> dict:
    """{rev, frozen, rule, events: [...], status}. Rows failing validation are
    dropped and logged; a missing/unreadable file gives an empty log, status error."""
    out = {"rev": None, "frozen": None, "rule": None, "events": [], "n_dropped": 0, "status": "error",
           "src": EVENTS_SRC_URL}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict) or not isinstance(raw.get("events", []), list):
            raise ValueError("events log is not an object with an `events` list")
    except Exception as exc:  # noqa: BLE001
        logger.warning("events log unreadable: %s", exc)
        return out
    events = []
    dropped = 0
    for e in raw.get("events", []):
        if not isinstance(e, dict):                 # one bad line must not take the whole block down
            dropped += 1
            logger.warning("event dropped (not an object): %s", str(e)[:120])
            continue
        problems = validate_event(e)
        if problems:
            dropped += 1
            logger.warning("event dropped (%s): %s", ",".join(problems), str(e)[:120])
            continue
        events.append(e)
    events.sort(key=lambda e: (e["date"], e.get("category", ""), e["text"]))
    out.update({"rev": raw.get("rev"), "frozen": raw.get("frozen"), "rule": raw.get("rule"),
                "events": events, "n_dropped": dropped, "status": "ok" if events else "error"})
    return out


# ---------------------------------------------------------------------------
# The breaking block
# ---------------------------------------------------------------------------
BASIS = ("Index OAS and yields: ICE BofA via FRED (3y rolling window, daily close, percentage points); "
         "BAA10Y daily 1986->; EBP monthly; OFR FSI daily; MOVE and BDC prices: Yahoo chart last daily "
         "close; BDC NAV: frozen per-filing table; events: dated press prints with provenance, not a feed")


def fetch_block() -> dict:
    spreads, gap = fetch_spreads()
    yields = fetch_yields()
    baa = fetch_baa10y()
    ebp = fetch_ebp()
    fsi = fetch_ofr_fsi()
    move = fetch_move()
    bdc = fetch_bdc()
    events = load_events()
    asofs = [b["asof"] for b in spreads.values() if b["asof"]]
    return {
        "asof": max(asofs) if asofs else None,
        "spreads": spreads,
        "ccc_b_gap": gap,
        "yields": yields,
        "baa10y": baa,
        "ebp": ebp,
        "ofr_fsi": fsi,
        "move": move,
        "bdc": bdc,
        "events": events["events"],
        "events_meta": {k: events[k] for k in ("rev", "frozen", "rule", "n_dropped", "src")},
        "basis": BASIS,
        "src": {"fred_pattern": fred_csv.url("<SERIES>"), "fred_notice": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
                "ebp": EBP_URL, "ofr_fsi": OFR_FSI_URL, "move": yahoo_url(MOVE_SYMBOL),
                "bdc_pattern": YAHOO_CHART.format(sym="<TICKER>"),
                "bdc_nav": {t: v.get("nav_src") for t, v in BDC_NAV.items()}},
        "status": {
            "spreads": fred_csv.worst_status([sid for sid, _ in OAS.values()]),
            "yields": fred_csv.worst_status([sid for sid, _ in YIELDS.values()]),
            "baa10y": baa["status"], "ebp": ebp["status"], "ofr_fsi": fsi["status"], "move": move["status"],
            "bdc": ("error" if any(r["status"] == "error" for r in bdc)
                    else "stale" if any(r["status"] == "stale" for r in bdc) else "ok"),
            "events": events["status"],
        },
    }
