"""Schwab month-end client margin balances via SEC EDGAR (free, keyless).

Schwab files its Monthly Activity Report as an 8-K ~2-3 weeks before FINRA
publishes the industry aggregate. Each report carries a TRAILING 13-MONTH
table ("Margin Balances at month end (in billions of dollars)"), so a handful
of filings reconstructs years of history and each new filing both adds a
month and restates the recent window.

EDGAR etiquette: declared User-Agent with a contact email (SEC fair-use
policy), <=~6 req/s. Parsed months persist to data/schwab_margin.json so
already-seen accessions are never re-fetched; the submissions index is
re-checked at most daily. Failure -> last parsed data (stale-preferred),
then None: the nowcast layer degrades, nothing else is affected.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

CIK = "0000316709"                                        # Charles Schwab Corp
UA = {"User-Agent": "optic-research canary tool (casey.rondin@gmail.com)"}
_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
os.makedirs(_DIR, exist_ok=True)
_STORE = os.path.join(_DIR, "schwab_margin.json")
_CHECK_TTL = 24 * 3600.0

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


def _get(url: str) -> bytes:
    time.sleep(0.18)                                       # stay well under SEC limits
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=25).read()


def _month_back(y: int, m: int, k: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) - k
    return idx // 12, idx % 12 + 1


def parse_activity_text(text: str) -> dict[str, float] | None:
    """Parse the flattened text of a Monthly Activity Report 8-K into
    {\"YYYY-MM\": margin_balance_$bn}. The 13 values before the first %-token
    after the 'Margin Balances at month end' label are the trailing months,
    newest last, ending at the title month. Footnote markers like '(4)' are
    skipped. Returns None if the filing is not a monthly activity report."""
    title = re.search(r"Monthly Activity Report For ([A-Z][a-z]+) (\d{4})", text)
    if not title or title.group(1) not in _MONTHS:
        return None
    y, m = int(title.group(2)), _MONTHS[title.group(1)]
    i = text.lower().find("margin balances at month end")
    if i < 0:
        return None
    vals: list[float] = []
    for tok in text[i:i + 600].split():
        if "%" in tok:
            break
        if re.fullmatch(r"\(\d+\)", tok):                  # footnote marker
            continue
        if re.fullmatch(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?", tok):
            vals.append(float(tok.replace(",", "")))
    if len(vals) < 6:                                      # need a real window
        return None
    out = {}
    for k, v in enumerate(reversed(vals)):                 # newest -> oldest
        yy, mm = _month_back(y, m, k)
        out[f"{yy:04d}-{mm:02d}"] = v
    return out


def _load() -> dict:
    try:
        return json.load(open(_STORE))
    except Exception:  # noqa: BLE001
        return {"months": {}, "seen": [], "checked": 0.0}


def fetch_schwab_margin(force: bool = False) -> dict[str, float] | None:
    """{\"YYYY-MM\": margin_$bn} across all parsed filings (later filings
    override earlier — restatements win). Stale-preferred on any failure."""
    st = _load()
    now = time.time()
    if not force and st["months"] and now - st.get("checked", 0) < _CHECK_TTL:
        return {k: float(x["v"]) for k, x in st["months"].items()}
    try:
        sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{CIK}.json"))
        rec = sub["filings"]["recent"]
        eights = [(d, acc) for d, f, acc in zip(
            rec["filingDate"], rec["form"], rec["accessionNumber"]) if f == "8-K"]
        seen = set(st.get("seen", []))
        # newest first; parse unseen filings (each carries 13 months, so even
        # a sparse parse converges to full history). Budgeted per call so a
        # cold request path never blocks for minutes — the store converges
        # over successive daily checks. Failed fetches are retried next call.
        budget_t, budget_n = time.time() + 15.0, 6
        for d, acc in eights:
            if acc in seen:
                continue
            if time.time() > budget_t or budget_n <= 0:
                break
            budget_n -= 1
            accn = acc.replace("-", "")
            try:
                idx = json.loads(_get(
                    f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{accn}/index.json"))
                body = ""
                for it in idx["directory"]["item"]:
                    if it["name"].endswith((".htm", ".html")):
                        body += _get(
                            f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{accn}/{it['name']}"
                        ).decode("utf-8", "ignore")
                text = re.sub(r"&#160;|&nbsp;", " ", re.sub(r"<[^>]+>", " ", body))
                text = re.sub(r"\s+", " ", text)
                parsed = parse_activity_text(text)
                if parsed:
                    # a month's value comes from the NEWEST filing that
                    # reported it (restatements win across runs)
                    for k, v in parsed.items():
                        cur = st["months"].get(k)
                        if cur is None or d > cur.get("asof", ""):
                            st["months"][k] = {"v": v, "asof": d}
                seen.add(acc)                              # parsed (or not an MAR)
                st["seen"] = sorted(seen)
                json.dump(st, open(_STORE, "w"))           # incremental persist
            except Exception as exc:  # noqa: BLE001
                logger.warning("schwab filing %s fetch failed (retry next "
                               "check): %s", acc, exc)
                time.sleep(1.0)                            # back off on 503s
        # full check done -> daily cadence; incomplete -> retry in ~30 min so
        # the backfill converges without ever blocking a request for long
        st["checked"] = (now if all(acc in seen for _, acc in eights)
                         else now - _CHECK_TTL + 1800)
        st["seen"] = sorted(seen)
        json.dump(st, open(_STORE, "w"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("schwab EDGAR check failed (stale-preferred): %s", exc)
    return ({k: float(x["v"]) for k, x in st["months"].items()}
            if st["months"] else None)
