"""EDGAR debt-filing poll for the AI-debt tab (free, keyless; User-Agent
mandatory).

Per CIK in CIK_WHITELIST: data.sec.gov submissions JSON (cached 12h) -> the
`name` field must match the whitelist (a wrong CIK is dropped and logged) ->
filings of forms FWP / 424B2 / 424B5 / 8-K filed since the seed's last deal
date -> for FWPs (and 424B2s with no FWP in the same week) the primary
document is fetched from www.sec.gov and the tranches regexed out: size,
coupon, maturity, spread to benchmark, ratings. Everything returned is
"auto-extracted, not in tally": a review list for the tab, never a total.

Two SEC hosts. data.sec.gov (submissions) and www.sec.gov (documents) both
answered httpx with the default User-Agent on 2026-10-15; www.sec.gov runs an
"undeclared automated tool" check that refused the same User-Agent sent by
curl, so the refusal is detected here: the poll still lists the filings, the
row's `extracted` is null with the reason in its status, and
doc_access_error() surfaces it for /health. The SEC's documented remedy is a
contact address in the User-Agent — EDGAR_USER_AGENT on Render (BUILD.md).
Failure mode as for the other ride-along sources: any error -> [] (or a stale
cache), never a crash. <= 5 req/s (SEC allows 10).
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_SUB_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
_SUB_TTL = 12 * 3600            # submissions JSON: re-fetch twice a day
_MIN_INTERVAL = 0.2             # seconds between requests -> <= 5 req/s
FORMS = ("FWP", "424B2", "424B5", "8-K")
# 8-K items worth listing: 2.03 creation of a direct financial obligation (the
# pricing 8-K for 144A notes and term loans), 1.01 material definitive agreement
# (credit agreements). Earnings (2.02) and the rest are noise for this list.
_DEBT_8K_ITEMS = ("2.03", "1.01")

# CIK -> (label used on the tab, exact `name` in the submissions JSON as read
# live on 2026-10-15). BUILD.md listed Constellation as 1868941 (= Fluence
# Energy) and Nebius as 1662684 (= KULR Technology); both corrected here from
# the live name field. Microsoft is polled although it has issued nothing.
CIK_WHITELIST: dict[int, tuple[str, str]] = {
    1326801: ("Meta Platforms", "Meta Platforms, Inc."),
    1652044: ("Alphabet", "Alphabet Inc."),
    1018724: ("Amazon", "AMAZON COM INC"),
    1341439: ("Oracle", "ORACLE CORP"),
    789019: ("Microsoft", "MICROSOFT CORP"),
    1045810: ("Nvidia", "NVIDIA CORP"),
    1730168: ("Broadcom", "Broadcom Inc."),
    2488: ("AMD", "ADVANCED MICRO DEVICES INC"),
    50863: ("Intel", "INTEL CORP"),
    723125: ("Micron", "MICRON TECHNOLOGY INC"),
    1101239: ("Equinix", "EQUINIX INC"),
    1297996: ("Digital Realty", "DIGITAL REALTY TRUST, INC."),
    1996810: ("GE Vernova", "GE Vernova Inc."),
    1692819: ("Vistra", "Vistra Corp."),
    1868275: ("Constellation Energy", "Constellation Energy Corp"),
    1769628: ("CoreWeave", "CoreWeave, Inc."),
    1839341: ("Core Scientific", "Core Scientific, Inc./tx"),
    1819989: ("Cipher", "Cipher Digital Inc."),
    1964789: ("Hut 8", "Hut 8 Corp."),
    1859392: ("Galaxy", "Galaxy Digital Inc."),
    1083301: ("TeraWulf", "TERAWULF INC."),
    1144879: ("Applied Digital", "Applied Digital Corp."),
    1878848: ("IREN", "IREN Ltd"),
    1513845: ("Nebius", "Nebius Group N.V."),
}

# ---------------------------------------------------------------- transport

_last_call = {"t": 0.0}
_throttle_lock = threading.Lock()
# host -> the User-Agent refusal text seen on it THIS run (poll_detailed clears
# it at the top of each run; a 200 from the host clears its entry). Keyed by
# host so a data.sec.gov refusal is never reported as the document host's.
_doc_access: dict[str, str] = {}
_DOC_HOST = "www.sec.gov"
# EDGAR fair-access: on a 403/429 rate-threshold block every SEC request pauses
# for 10 minutes (continuing to send requests prolongs the SEC's IP block).
_BLOCK_SECONDS = 600
_blocked_until = {"t": 0.0}


def doc_access_error() -> str | None:
    """The www.sec.gov User-Agent refusal seen in the last poll run, or None —
    surfaced by the metrics layer / health like fred_key_error()."""
    return _doc_access.get(_DOC_HOST)


def rate_limited() -> bool:
    """True while an SEC 403/429 rate-threshold block is being honoured."""
    return time.monotonic() < _blocked_until["t"]


def _throttle() -> None:
    with _throttle_lock:
        wait = _last_call["t"] + _MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call["t"] = time.monotonic()


def _get(url: str) -> httpx.Response | None:
    host = url.split("/")[2]
    if rate_limited():
        logger.warning("EDGAR rate-limited; skipping %s", url)
        return None
    _throttle()
    headers = {"User-Agent": settings.edgar_user_agent, "Accept-Encoding": "gzip, deflate"}
    try:
        r = httpx.get(url, headers=headers, timeout=settings.http_timeout_seconds,
                      follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("EDGAR fetch failed %s: %s", url, exc)
        return None
    if r.status_code == 403 and "Undeclared Automated Tool" in r.text:
        _doc_access[host] = (f"{host} refused User-Agent {settings.edgar_user_agent!r} "
                             "as an undeclared automated tool; set EDGAR_USER_AGENT with a contact address")
        logger.warning("EDGAR %s", _doc_access[host])
        return None
    if r.status_code in (403, 429):
        _blocked_until["t"] = time.monotonic() + _BLOCK_SECONDS
        logger.warning("EDGAR HTTP %s on %s; pausing all SEC requests %d s", r.status_code, url, _BLOCK_SECONDS)
        return None
    if r.status_code != 200:
        logger.warning("EDGAR HTTP %s for %s", r.status_code, url)
        return None
    _doc_access.pop(host, None)        # a 200 from the host proves the UA works there
    return r


# ------------------------------------------------------------- submissions

def _sub_path(cik: int) -> str:
    return os.path.join(settings.cache_dir, f"edgar_sub_CIK{cik:010d}.json")


def submissions(cik: int, use_cache: bool = True) -> dict | None:
    """The submissions JSON for one CIK (disk-cached 12h). A failed fetch falls
    back to an expired cache file, marked '_stale': True; None if neither."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    path = _sub_path(cik)
    if use_cache and os.path.exists(path) and time.time() - os.path.getmtime(path) < _SUB_TTL:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            pass
    r = _get(_SUB_URL.format(cik=cik))
    if r is not None:
        data = None
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("EDGAR submissions CIK%010d unparseable: %s", cik, exc)
        # only a real submissions document may replace the last good cache:
        # a 200 with `{}` or an error object must not be served for 12 h
        if not (isinstance(data, dict) and isinstance(data.get("name"), str)
                and isinstance((data.get("filings") or {}).get("recent"), dict)):
            if data is not None:
                logger.warning("EDGAR submissions CIK%010d: not a submissions document; not cached", cik)
            data = None
        if data is not None:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as exc:  # noqa: BLE001
                logger.warning("EDGAR cache write failed %s: %s", path, exc)
            return data
    if os.path.exists(path):          # stale beats nothing; the caller flags it
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["_stale"] = True
            return data
        except Exception:  # noqa: BLE001
            pass
    return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


def verify_name(sub: dict, expected: str) -> bool:
    """The submissions `name` must equal the whitelist's (case/punctuation
    insensitive); anything else means the CIK points at another company."""
    return _norm(str(sub.get("name", ""))) == _norm(expected)


def filing_url(cik: int, accession: str, primary_doc: str) -> str:
    return _ARCHIVE.format(cik=cik, acc=accession.replace("-", ""), doc=primary_doc)


def list_filings(sub: dict, since: str, forms: tuple[str, ...] = FORMS) -> list[dict]:
    """Filings of `forms` filed on/after `since` (ISO date), newest first, from
    the JSON's `recent` block (its last 1000 filings — far more than a poll
    window needs)."""
    rec = sub.get("filings", {}).get("recent", {})
    n = len(rec.get("form", []))
    cik = int(sub["cik"])
    blank = [""] * n
    out = []
    for i in range(n):
        form, filed = rec["form"][i], rec["filingDate"][i]
        if form not in forms or filed < since:
            continue
        acc, doc = rec["accessionNumber"][i], rec["primaryDocument"][i]
        out.append({
            "filed": filed, "form": form, "accession": acc, "primary_doc": doc,
            "description": rec.get("primaryDocDescription", blank)[i] or None,
            "items": rec.get("items", blank)[i] or None,
            "url": filing_url(cik, acc, doc),
        })
    out.sort(key=lambda f: f["filed"], reverse=True)
    return out


# --------------------------------------------------------------- documents

def fetch_document(url: str) -> str | None:
    """A filing's primary document (HTML), cached for good: filings are
    immutable. None when www.sec.gov refuses or the fetch fails."""
    os.makedirs(settings.cache_dir, exist_ok=True)
    path = os.path.join(settings.cache_dir,
                        "edgar_doc_" + hashlib.sha1(url.encode()).hexdigest()[:16] + ".htm")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:  # noqa: BLE001
            pass
    r = _get(url)
    if r is None:
        return None
    text = r.text
    # a transient error page served with 200 must not be frozen as the filing
    if len(text) < 1500 or _ERROR_PAGE.search(text):
        logger.warning("EDGAR document %s looks like an error page (%d chars); not cached", url, len(text))
        return None
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:  # noqa: BLE001
        pass
    return text


_ERROR_PAGE = re.compile(r"Undeclared Automated Tool|Rate Threshold|Service Unavailable|<title>\s*(?:403|404|5\d\d)", re.I)


def html_to_text(raw: str) -> str:
    """Term-sheet HTML -> text with newlines at block boundaries and ' | ' at
    table cells (so a label and its value stay adjacent)."""
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", t)
    t = re.sub(r"(?i)</td>|</th>", " | ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t).replace("\xa0", " ").replace(" ", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


# --------------------------------------------------------------- extraction

_CCY = {"$": "USD", "US$": "USD", "C$": "CAD", "A$": "AUD", "S$": "SGD", "HK$": "HKD",
        "€": "EUR", "£": "GBP", "¥": "JPY", "CHF": "CHF"}
_CCY_RE = r"(?P<ccy>US\$|C\$|A\$|S\$|HK\$|\$|€|£|¥|CHF)"
_AMT_RE = r"(?P<num>\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?)"          # >= 1,000,000 in full digits
_QUAL = (r"(?:(?:Senior|Subordinated|Junior|Convertible|Exchangeable|Green|Sustainability(?:-Linked)?|"
         r"Sustainable|Guaranteed|Secured|Unsecured|Fixed[\s-]+Rate|Reset|Series\s+[A-Z])\s+){0,4}")
# "$3,000,000,000 4.550% Senior Notes due 2031" / "4.550% Notes due 2031 (the ...)" /
# "$500,000,000 of Floating Rate Notes Due 2029" / "$1,100,000,000 aggregate principal
# amount of 4.800% Senior Notes due 2028" — the amount is optional.
_HEAD = re.compile(
    r"(?:" + _CCY_RE + r"\s?" + _AMT_RE +
    r"\s+(?:of\s+)?(?:(?:in\s+)?aggregate\s+principal\s+amount\s+of\s+(?:its\s+|the\s+)?)?)?"
    r"(?:(?P<cpn>\d{1,2}\.\d{1,3})%\s+|(?P<flt>Floating[\s-]+Rate)\s+|(?P<ser>Series\s+[A-Z])\s+)" + _QUAL +
    r"(?:Notes|Debentures|Bonds)\s+due\s+(?P<yr>2[01]\d\d)", re.I)
# A heading preceded (within the same sentence / table cell) by language about
# the issuer's EXISTING paper names the notes being redeemed or repurchased,
# not a tranche of this deal.
_EXISTING = re.compile(
    r"(?:outstanding|existing|redeem\w*|redemption of|repurchas\w*|tender(?:ing)? for|exchange for|"
    r"holders of (?:our|its|the))(?:[^.|]|\.(?=\d)){0,80}$", re.I)   # a '.' inside a coupon is not a sentence end
# "2031 Notes: $3,000,000,000" / "2028 Floating Rate Notes: $750,000,000"
_LABEL_AMT = re.compile(
    r"(?P<yr>2[01]\d\d)\s+(?P<flt>Floating\s+Rate\s+)?(?:Fixed\s+Rate\s+)?Notes\s*:?\s*" +
    _CCY_RE + r"\s?" + _AMT_RE, re.I)
# "Principal Amount: | | $3,000,000,000" / "Size: | | $1,000,000,000" -> the
# nearest preceding tranche heading (the per-tranche section layout); a label
# row carrying one cell per heading ("Principal Amount: | $850,000,000 | $650,000,000")
# is the column layout and is assigned positionally
_SECTION_AMT = re.compile(
    r"(?:Aggregate\s+)?(?:Principal\s+Amount|Size)(?:\s+Offered)?\s*:?\s*(?:\|\s*)*" +
    _CCY_RE + r"\s?" + _AMT_RE, re.I)
_AMT_CELL = re.compile(r"(?:\s*\|\s*)+(?P<ccy>US\$|C\$|A\$|S\$|HK\$|\$|€|£|¥|CHF)\s?(?P<num>\d{1,3}(?:,\d{3}){2,}(?:\.\d+)?)",
                       re.I)
# "2031 Notes: T + 53 bps" / "2031 Notes: +45 basis points" / "2056 Notes: +110 bps versus ..."
# — the unit is mandatory: "2031 Notes: T+3" is a settlement convention, not a spread
_LABEL_SPREAD = re.compile(
    r"(?P<yr>2[01]\d\d)\s+(?P<flt>Floating\s+Rate\s+)?(?:Fixed\s+Rate\s+)?Notes\s*:\s*"
    r"(?:T\s*\+|UST\s*\+|\+)\s*(?P<bp>\d{1,3}(?:\.\d+)?)\s*(?:bps|bp|basis\s+points)", re.I)
# "Spread to Benchmark Treasury: | | +95 basis points" / "Re-Offer Spread: | | +110 bps"
_SECTION_SPREAD = re.compile(
    r"(?:Spread\s+to\s+(?:the\s+)?(?:Benchmark\s+)?(?P<bm>Treasury|Gilt|Bund|Bond|Mid-?Swap(?:\s+Yield)?|"
    r"Reference\s+Rate)|Re-Offer\s+Spread)\s*:?\s*(?:\|\s*)*(?:T\s*\+|UST\s*\+|\+)\s*"
    r"(?P<bp>\d{1,3}(?:\.\d+)?)\s*(?:bps|bp|basis\s+points)", re.I)
# The spread header that governs the "YYYY Notes: +N bps" labels after it:
# "Spread to Benchmark Treasury" (UST) / "... Bund" / "... Gilt" / "... Reference
# Rate" (swap) / "Re-Offer Spread ... Government of Canada" (GoC). Without a
# header the benchmark is UST only for a USD (or currency-less) sheet.
_SPREAD_HEADER = re.compile(
    r"Spread\s+to\s+(?:the\s+)?(?:Benchmark\s+)?(?P<bm>Treasury|Bund|Gilt|Bond|Reference\s+Rate|Mid-?Swap)"
    r"|Re-Offer\s+Spread(?P<goc>.{0,200}?Government\s+of\s+Canada)?", re.I)
_BENCHMARK_NAME = {"treasury": "UST", "bund": "Bund", "gilt": "Gilt", "bond": "bond",
                   "reference rate": "swap", "mid-swap": "swap", "midswap": "swap", "mid swap": "swap"}
# floating tranches: "2028 Floating Rate Notes: Compounded SOFR ... plus 0.44% per annum"
_FRN_SPREAD = re.compile(
    r"(?:(?P<yr>2[01]\d\d)\s+Floating\s+Rate\s+Notes\s*[:,]\s*)?(?:Compounded\s+|Daily\s+)?"
    r"(?P<bm>SOFR|EURIBOR|SONIA|CORRA|TONA)\b[^|]{0,220}?plus\s+(?P<pct>\d\.\d+)%", re.I)
# "... in the case of the 2029 Floating Rate Notes, Compounded SOFR (as defined ...) ... plus 0.59%":
# the owner of an unlabelled floating spread is the last "YYYY Floating Rate Notes" named in
# the same table cell before it
_FRN_OWNER = re.compile(r"(?P<yr>2[01]\d\d)\s+Floating\s+Rate\s+Notes[^|]*$", re.I)
_RATING_TOKEN = re.compile(
    r"\b(?:Aaa|Aa[1-3]|A[1-3]|Baa[1-3]|Ba[1-3]|B[1-3]|Caa[1-3]|AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|"
    r"B[+-]?|CCC[+-]?)(?![A-Za-z0-9])(?:\s?\((?:sf|stable|positive|negative|pos|neg|\+|-)\))?")
_RATINGS_LABEL = re.compile(
    r"(?:Expected\s+|Anticipated\s+)?Ratings?\s*(?:\([^)]{0,60}\))?\s*[:\*]*\s*(?:\|\s*)*(?P<val>[^|]{0,220})",
    re.I)
# the next "Label:" ends the ratings value — unless it is an agency name
# ("Moody's: Aa2 (Stable); S&P: AA+ (Stable)" is one value)
_NEXT_LABEL = re.compile(r"\s+(?:[A-Z][A-Za-z/&'’()-]*\s?){1,5}:")
_AGENCY = re.compile(r"^\s*(?:Moody|S&P|Standard|Fitch|DBRS|KBRA|Morningstar|JCR|R&I)", re.I)


def _amount_bn(num: str) -> float:
    return round(float(num.replace(",", "")) / 1e9, 4)


def _flat(text: str) -> str:
    t = re.sub(r"\s+", " ", text)
    # "due 20 27": a span split inside the year on some Broadcom sheets
    return re.sub(r"(due\s+)2\s?0\s?(\d)\s?(\d)\b", lambda m: f"{m.group(1)}20{m.group(2)}{m.group(3)}", t, flags=re.I)


def extract_tranches(text: str) -> dict:
    """Best-effort tranche table from a pricing term sheet (FWP) or prospectus
    supplement (424B2) rendered to text. Returns null fields rather than
    guessing: size_bn is the sum of the sized tranches in the dominant
    currency (n_sized says how many; `partial` when a tranche has no amount),
    spreads are bp over the benchmark named per tranche ('UST' for Treasuries,
    'Bund' / 'Gilt' / 'GoC' / 'swap' where the sheet says so; SOFR etc. for
    floaters). Maturities and coupons are the ones MENTIONED as this deal's
    notes; a heading preceded by redemption / repurchase / "holders of our"
    language names existing paper and is skipped."""
    t = _flat(text)
    tranches: dict[tuple[int, object], dict] = {}
    heads: list[tuple[int, tuple[int, object]]] = []         # (position, key) in document order
    for m in _HEAD.finditer(t):
        if _EXISTING.search(t[max(0, m.start() - 100):m.start()]):
            continue
        yr = int(m.group("yr"))
        # key on the NUMERIC coupon so '4.550%' and '4.55%' are one tranche
        key: tuple[int, object] = (yr, "FRN" if m.group("flt") else
                                   m.group("ser").upper() if m.group("ser") else float(m.group("cpn")))
        tr = tranches.setdefault(key, {
            "maturity": yr, "coupon": float(m.group("cpn")) if m.group("cpn") else None,
            "floating": bool(m.group("flt")), "size_bn": None, "ccy": None,
            "spread_bp": None, "benchmark": None})
        if m.group("num") and tr["size_bn"] is None:
            tr["size_bn"], tr["ccy"] = _amount_bn(m.group("num")), _CCY[m.group("ccy").upper()]
        heads.append((m.start(), key))
    order = list(dict.fromkeys(k for _, k in heads))          # tranches in first-appearance order

    def _by_year(yr: int, floating: bool) -> dict | None:
        c = [tr for (y, k), tr in tranches.items() if y == yr and tr["floating"] == floating]
        return c[0] if len(c) == 1 else None

    def _preceding(pos: int) -> dict | None:
        prev = [k for p, k in heads if p < pos]
        return tranches[prev[-1]] if prev else None

    # spread headers in document order: (position, benchmark | None)
    headers: list[tuple[int, str | None]] = []
    for m in _SPREAD_HEADER.finditer(t):
        if m.group("bm"):
            bm = re.sub(r"\s+", " ", m.group("bm").lower())
            headers.append((m.start(), _BENCHMARK_NAME.get(bm, bm)))
        else:
            headers.append((m.start(), "GoC" if m.group("goc") else None))

    def _benchmark_at(pos: int, ccy: str | None) -> str | None:
        prev = [b for p, b in headers if p <= pos]
        if prev and prev[-1] is not None:
            return prev[-1]
        return "UST" if ccy in (None, "USD") else None

    for m in _LABEL_AMT.finditer(t):
        tr = _by_year(int(m.group("yr")), bool(m.group("flt")))
        if tr is not None and tr["size_bn"] is None:
            tr["size_bn"], tr["ccy"] = _amount_bn(m.group("num")), _CCY[m.group("ccy").upper()]
    for m in _SECTION_AMT.finditer(t):
        cells = [(m.group("ccy"), m.group("num"))]
        end = m.end()
        while True:                                   # further amount cells on the same label row
            c = _AMT_CELL.match(t, end)
            if not c:
                break
            cells.append((c.group("ccy"), c.group("num")))
            end = c.end()
        if len(cells) > 1:
            # column layout: one amount per heading, in heading order; anything else stays null
            if len(cells) == len(order):
                for key, (ccy, num) in zip(order, cells):
                    tr = tranches[key]
                    if tr["size_bn"] is None:
                        tr["size_bn"], tr["ccy"] = _amount_bn(num), _CCY[ccy.upper()]
            continue
        prev_pos = [p for p, _ in heads if p < m.start()]
        if (m.group(0).lower().startswith("aggregate") and len(tranches) > 1
                and prev_pos and m.start() - prev_pos[-1] > 300):
            continue                                  # a deal-total line, not a per-tranche section
        tr = _preceding(m.start())
        if tr is not None and tr["size_bn"] is None:
            tr["size_bn"], tr["ccy"] = _amount_bn(m.group("num")), _CCY[m.group("ccy").upper()]
    for m in _LABEL_SPREAD.finditer(t):
        tr = _by_year(int(m.group("yr")), bool(m.group("flt")))
        if tr is not None and tr["spread_bp"] is None:
            tr["spread_bp"], tr["benchmark"] = float(m.group("bp")), _benchmark_at(m.start(), tr["ccy"])
    for m in _SECTION_SPREAD.finditer(t):
        tr = _preceding(m.start())
        if tr is not None and tr["spread_bp"] is None:
            tr["spread_bp"] = float(m.group("bp"))
            if m.group("bm"):
                bm = re.sub(r"\s+", " ", m.group("bm").lower())
                tr["benchmark"] = _BENCHMARK_NAME.get(bm, bm)
            else:
                tr["benchmark"] = _benchmark_at(m.start(), tr["ccy"])
    for m in _FRN_SPREAD.finditer(t):
        tr = None
        owner = _FRN_OWNER.search(t[max(0, m.start() - 400):m.start()])
        yr_s = m.group("yr") or (owner.group("yr") if owner else None)
        if yr_s:
            tr = _by_year(int(yr_s), True)
        else:
            # unlabelled: unambiguous only when the deal has exactly one floater; never
            # "the first FRN without a spread" (a guess that swaps two floaters)
            frns = [x for x in tranches.values() if x["floating"]]
            tr = frns[0] if len(frns) == 1 else None
        if tr is not None and tr["spread_bp"] is None:
            tr["spread_bp"], tr["benchmark"] = round(float(m.group("pct")) * 100, 1), m.group("bm").upper()

    ratings = None
    for m in _RATINGS_LABEL.finditer(t):
        val = m.group("val").strip()
        tok = _RATING_TOKEN.search(val[:60])
        if not tok:
            continue
        for cut in _NEXT_LABEL.finditer(val, tok.end()):
            if not _AGENCY.match(cut.group(0)):
                val = val[:cut.start()]
                break
        ratings = re.sub(r"\s*\*+\s*$", "", val.strip())[:160] or None
        break

    rows = sorted(tranches.values(), key=lambda x: (x["maturity"], not x["floating"]))
    sized = [x for x in rows if x["size_bn"] is not None]
    ccys = sorted({x["ccy"] for x in sized}, key=lambda c: -sum(1 for x in sized if x["ccy"] == c))
    ccy = ccys[0] if ccys else None
    size = round(sum(x["size_bn"] for x in sized if x["ccy"] == ccy), 4) if ccy else None
    return {
        "tranches": rows,
        "n_tranches": len(rows),
        "n_sized": len(sized),
        "partial": bool(rows) and len(sized) < len(rows),   # size_bn sums the sized tranches only
        "size_bn": size,
        "ccy": ccy,
        "size_by_ccy": ({c: round(sum(x["size_bn"] for x in sized if x["ccy"] == c), 4) for c in ccys}
                        if len(ccys) > 1 else None),
        "coupons": [x["coupon"] for x in rows],
        "maturities": [x["maturity"] for x in rows],
        "spreads": [x["spread_bp"] for x in rows],
        "ratings": ratings,
    }


# -------------------------------------------------------------------- poll

def _debt_item(items: str | None) -> bool:
    return any(code in (items or "") for code in _DEBT_8K_ITEMS)


def _days(a: str, b: str) -> int:
    return abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days)


def _seed_match(label: str, filed: str, seed_deals: list[dict]) -> str | None:
    """A seed deal by the same issuer within a week of the filing, so a filing
    for a deal already in the tally is not read as new money."""
    for d in seed_deals:
        if d["issuer"].startswith(label) and d["date"] and _days(d["date"], filed) <= 7:
            return f"{d['date']} {d['issuer']} {d['size_bn']} {d['ccy']}"
    return None


def poll_detailed(since: str | None = None, ciks: dict[int, tuple[str, str]] | None = None,
                  fetch_docs: bool = True) -> dict:
    """The poll with its bookkeeping: filings plus which CIKs were checked,
    failed, served stale or mis-named, and the document-access error if any.
    `since` defaults to the seed's last deal date."""
    if since is None:
        from .ai_debt_seed import load_seed
        since = load_seed()["last_deal_date"]
    try:
        from .ai_debt_seed import included
        seed_deals = included()
    except Exception:  # noqa: BLE001
        seed_deals = []
    _doc_access.clear()               # per-run evidence only: a refusal is reported for the run it happened in
    out: dict = {"since": since, "asof": date.today().isoformat(), "filings": [],
                 "checked": [], "failed": [], "stale": [], "name_mismatch": [], "doc_failed": 0,
                 "doc_access_error": None, "rate_limited": False, "status": "error"}
    for cik, (label, expected) in (CIK_WHITELIST if ciks is None else ciks).items():
        try:
            sub = submissions(cik)
            if sub is None:
                out["failed"].append(label)
                continue
            if not verify_name(sub, expected):
                logger.warning("EDGAR CIK %d is %r, not %r — dropped", cik, sub.get("name"), expected)
                out["name_mismatch"].append(label)
                continue
            if sub.get("_stale"):
                out["stale"].append(label)
            out["checked"].append(label)
            filings = list_filings(sub, since)
            fwp_days = [f["filed"] for f in filings if f["form"] == "FWP"]
            for f in filings:
                if f["form"] == "8-K" and not _debt_item(f["items"]):
                    continue
                row = {"filed": f["filed"], "issuer": label, "cik": cik, "form": f["form"],
                       "url": f["url"], "description": f["description"], "items": f["items"],
                       "extracted": None, "status": "listed, not parsed; not in tally",
                       "seed_match": _seed_match(label, f["filed"], seed_deals)}
                parse = f["form"] == "FWP" or (
                    f["form"] == "424B2" and not any(_days(f["filed"], d) <= 3 for d in fwp_days))
                if parse and not f["primary_doc"]:
                    parse = False                     # a folder URL would fetch the EDGAR index page
                    row["status"] = "listed; no primary document; not in tally"
                if parse and fetch_docs:
                    doc = fetch_document(f["url"])
                    if doc is None:
                        why = doc_access_error() or "document fetch failed"
                        row["status"] = f"listed; {why}; not in tally"
                        out["doc_failed"] += 1
                    else:
                        row["extracted"] = extract_tranches(html_to_text(doc))
                        row["status"] = ("auto-extracted (partial), not in tally" if row["extracted"]["partial"]
                                         else "auto-extracted, not in tally")
                elif parse:
                    row["status"] = "listed, not fetched; not in tally"
                out["filings"].append(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("EDGAR poll failed for %s (CIK %d): %s", label, cik, exc)
            out["failed"].append(label)
    out["filings"].sort(key=lambda r: (r["filed"], r["issuer"]), reverse=True)
    out["doc_access_error"] = doc_access_error()
    out["rate_limited"] = rate_limited()
    if out["checked"]:
        degraded = (out["failed"] or out["stale"] or out["name_mismatch"] or out["doc_access_error"]
                    or out["doc_failed"] or out["rate_limited"])
        out["status"] = "stale" if degraded else "ok"
    return out


def poll(since: str | None = None, ciks: dict[int, tuple[str, str]] | None = None,
         fetch_docs: bool = True) -> list[dict]:
    """[{filed, issuer, form, url, extracted, status, ...}] for the whitelist
    since the seed's last deal date; [] on total failure."""
    try:
        return poll_detailed(since, ciks, fetch_docs)["filings"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("EDGAR poll failed: %s", exc)
        return []
