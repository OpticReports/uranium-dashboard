"""Gate step 1: point-in-time catalyst table from FMP press releases (source 1).

Implements the extraction frozen in DESIGN_SECTOR_FORWARD_TEST.md ("Source
declarations"). Output: press_catalysts.json.gz - one record per extracted
catalyst window: symbol, publish timestamp (the as-of, America/New_York as
FMP reports it), release title/url, the sentence, the matched time phrase,
window start/end, kind (pdufa / readout).

    cd genomics-alpha-tracker/backend && python -m research.sector_forward.press_catalysts
"""
from __future__ import annotations

import calendar
import gzip
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from research.sector_tier import build_population as P  # noqa: E402

OUT = HERE / "press_catalysts.json.gz"
FROM, TO = "2024-06-01", "2026-09-30"
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MON = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?"
NOT_COMPANY = re.compile(r"(?i)shareholder alert|investor alert|class action|investigat|law firm|\bllp\b|deadline|reminds|"
                         r"securities fraud|lawsuit|losses")
# Amendment (2026-10-06, after the first spot-check sample showed ~4/20 real
# catalysts; before any statistic): clinical/regulatory terms only, no
# financial-calendar sentences, dateline stripped, the date must sit near the
# term, and the window must lie strictly after publication.
TERM = re.compile(r"(?i)\b(pdufa|target action date|top-?line|data readout|readout|read-out|interim (?:analysis|data|results)|"
                  r"pivotal (?:data|results)|phase (?:2|3|ii|iii)\w* (?:data|results)|primary endpoint|clinical data|"
                  r"fda decision|approval decision|advisory committee)\b")
EXCLUDE = re.compile(r"(?i)financial results|earnings|conference call|webcast|runway|fund (?:its )?operations|quarter ended|"
                     r"fiscal|annual meeting|investor (?:day|conference)|fireside")
DATELINE = re.compile(r"^.{0,220}?(?:\(GLOBE NEWSWIRE\)\s*--|/PRNewswire/\s*--|--\(BUSINESS WIRE\)--|\(BUSINESS WIRE\)\s*--|/CNW/\s*--|ACCESSWIRE\s*--)", re.S)
NEAR = 100
CUE = re.compile(r"(?i)\b(expect\w*|anticipat\w*|on track|plan\w*|will|set for|scheduled|target\w*|by)\b")
QW = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


def _end_of_month(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def windows(sentence: str) -> list[tuple[date, date, str]]:
    """Every time expression in the sentence -> (start, end, phrase) per the frozen mapping."""
    s = sentence.lower()
    out = []
    taken: list[tuple[int, int]] = []

    def add(m, a, b):
        if any(m.start() < e and m.end() > st for st, e in taken):
            return
        taken.append((m.start(), m.end()))
        out.append((a, b, m.group(0)))

    for m in re.finditer(rf"\b{MON}\s+(\d{{1,2}}),?\s+(20\d\d)\b", s):
        try:
            key = m.group(1).rstrip(".")
            d = date(int(m.group(3)), MONTHS["sep" if key.startswith("sept") else key], int(m.group(2)))
            add(m, d, d)
        except (ValueError, KeyError):
            pass
    for m in re.finditer(r"\b(?:q([1-4])|(first|second|third|fourth|1st|2nd|3rd|4th) quarter(?: of)?)\s*(?:of\s*)?'?(20\d\d)\b", s):
        q = int(m.group(1)) if m.group(1) else QW[m.group(2)]
        y = int(m.group(3))
        add(m, date(y, 3 * q - 2, 1), _end_of_month(y, 3 * q))
    for m in re.finditer(r"\b(?:([12])h|(first|second) half(?: of)?)\s*(?:of\s*)?'?(20\d\d)\b", s):
        h = int(m.group(1)) if m.group(1) else (1 if m.group(2) == "first" else 2)
        y = int(m.group(3))
        add(m, date(y, 1 if h == 1 else 7, 1), _end_of_month(y, 6 if h == 1 else 12))
    for m in re.finditer(r"\bmid-?\s?(20\d\d)\b", s):
        y = int(m.group(1))
        add(m, date(y, 6, 1), date(y, 7, 31))
    for m in re.finditer(r"\bearly[- ](20\d\d)\b", s):
        y = int(m.group(1))
        add(m, date(y, 1, 1), date(y, 4, 30))
    for m in re.finditer(r"\b(?:late|end of|year-end|year end|by the end of)[- ]?(?:the )?(?:year )?(20\d\d)\b", s):
        y = int(m.group(1))
        add(m, date(y, 9, 1), date(y, 12, 31))
    for m in re.finditer(rf"\b{MON}\s+(20\d\d)\b", s):
        key = m.group(1).rstrip(".")
        key = "sep" if key.startswith("sept") else key
        try:
            y, mo = int(m.group(2)), MONTHS[key]
            add(m, date(y, mo, 1), _end_of_month(y, mo))
        except KeyError:
            pass
    for m in re.finditer(r"\b(?:in|during)\s+(20\d\d)\b", s):
        y = int(m.group(1))
        add(m, date(y, 1, 1), date(y, 12, 31))
    return out


def sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "")
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z(])|\s+[~•▪●]\s+|\s+–\s+|\s+-\s+(?=[A-Z])", text)
    return [p.strip() for p in parts if 20 <= len(p.strip()) <= 600]


def fetch(sym: str) -> list[dict]:
    rows, page = [], 0
    while page < 50:
        d = P.fmp(f"press/{sym}_{page}", "news/press-releases", symbols=sym, **{"from": FROM, "to": TO},
                  page=page, limit=100) or []
        if not d:
            break
        rows += d
        page += 1   # FMP returns short pages mid-history (98 then 21); stop only on an empty page
    return rows


def main() -> None:
    aliases = json.loads((HERE / "aliases.json").read_text())
    recs, stats = [], {"releases": 0, "company_releases": 0, "with_catalyst": 0}
    for sym in sorted(aliases):
        core = aliases[sym]["core"]
        core_re = re.compile(rf"(?i)\b{re.escape(core)}\b") if core else None
        tick = re.compile(rf"\((?:nasdaq|nyse|nyse american|nyse arca)\s*:\s*{re.escape(sym)}\)", re.I)
        for r in fetch(sym):
            stats["releases"] += 1
            title, text = r.get("title") or "", r.get("text") or ""
            head = (title + " " + text)[:600]
            if NOT_COMPANY.search(title) or not (tick.search(head) or (core_re and core_re.search(head))):
                continue
            stats["company_releases"] += 1
            pub = str(r.get("publishedDate") or "")
            pub_d = date.fromisoformat(pub[:10])
            got = False
            body = DATELINE.sub("", text, count=1)
            for sent in sentences(title + ". " + body):
                if not (TERM.search(sent) and CUE.search(sent)) or EXCLUDE.search(sent):
                    continue
                terms = [(m.start(), m.end()) for m in TERM.finditer(sent)]
                for a, b, phrase in windows(sent):
                    pos = sent.lower().find(phrase)
                    near = any(-60 <= pos - te <= NEAR or 0 <= ts - (pos + len(phrase)) <= 60 for ts, te in terms)
                    if b <= pub_d or not near:
                        continue
                    kind = "pdufa" if re.search(r"(?i)pdufa|target action date|approval decision", sent) else "readout"
                    recs.append({"symbol": sym, "published": pub, "title": title[:200], "url": r.get("url"),
                                 "sentence": sent[:400], "phrase": phrase, "start": a.isoformat(), "end": b.isoformat(), "kind": kind})
                    got = True
            stats["with_catalyst"] += got
        print(f"{sym}: {sum(1 for x in recs if x['symbol'] == sym)} catalyst windows", flush=True)
    OUT.write_bytes(gzip.compress(json.dumps({"stats": stats, "records": recs}).encode()))
    print(stats, "records", len(recs))


if __name__ == "__main__":
    main()
