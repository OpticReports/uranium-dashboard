"""EDGAR nowcast layer: monthly merger-proxy filing counts.

WHY THIS EXISTS. The HSR backbone is the official US deal count but
carries a ~10-month publication lag - FY2025, ending Sep-2025, was
published Jul-2026. It cannot nowcast. EDGAR's quarterly form index is
current to yesterday, so it fills the gap between the last HSR month
and today.

WHAT WE COUNT, AND WHY ONLY THESE TWO.
  DEFM14A - definitive merger proxy: the deal is going to a vote
  PREM14A - preliminary merger proxy: the deal has been struck and
            filed, but not yet cleared by staff review

PREM14A leads DEFM14A by roughly a review cycle, so the pair reads as
pipeline against confirmation.

EVERY OTHER FORM WAS REJECTED, and the reason is the whole design.
form.idx has ONE ROW PER FILER, not per filing. A registration with
forty co-registrant subsidiaries emits forty rows for one document.
Counting rows therefore measures corporate structure, not deal
activity, and the distortion is not small - measured inflation factors:

    S-4          up to 8.7x     (2007-06: 418 rows / 48 filings)
    SC 13D          ~2.0x
    SC TO-T   exactly 2.0x
    425             ~1.4x
    DEFM14A         1.00x       <- clean
    PREM14A         1.00x       <- clean

An earlier pass reported an S-4 "collapse" of 1,024 (2007Q2) to 44
(2025Q1) - a 23x swing that looked like a dramatic finding about
stock-financed M&A. On distinct accessions it is 133 to 36, a 3.7x
swing. Most of that headline was co-registrants on high-yield exchange
offers, which are not mergers at all. We de-duplicate on accession
number regardless, but we also decline to use the forms that needed it.

THREE BREAKS THAT WOULD OTHERWISE CORRUPT THE SERIES:
  * ELECTRONIC FILING PHASE-IN. EDGAR became mandatory only in May
    1996. DEFM14A per quarter runs 8 (1994Q1) -> 27 (1996Q1) -> 92
    (2000Q1). A series starting before 1996 measures EDGAR ADOPTION,
    not deal activity. We ingest from 1994 so the ramp is visible and
    the cutoff is arguable from the chart, and SCORE only from 1997Q1.
  * Form 425 does not exist before Jan-2000 (Regulation M-A).
  * SC 14D1 -> SC TO-T (Jan 2000); SC 13D -> SCHEDULE 13D (Dec 2024).
    Both would silently zero a series. Neither form is used here, but
    the alias map is kept so nobody re-adds one unguarded.

USER-AGENT: SEC REQUIRES a descriptive UA with contact info and will
block requests without one. This is the exact OPPOSITE of FRED, which
returns an empty reply to any custom UA. The two fetchers therefore
disagree on purpose - see ma_data._get.
"""

import csv
import json
import os
import re
import subprocess
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_HERE, "ma_cycle_cache")
OUT = os.path.join(_HERE, "edgar_monthly.csv")

IDX = ("https://www.sec.gov/Archives/edgar/full-index/"
       "{year}/QTR{q}/form.idx")

# SEC requires this. Do not remove it.
SEC_UA = "uranium-dashboard research casey.rondin@gmail.com"

FORMS = ("DEFM14A", "PREM14A")

# Ingested from here so the EDGAR adoption ramp is visible on the chart.
INGEST_FROM = (1994, 1)
# Scored only from here. EDGAR was mandatory from May 1996; we allow two
# further quarters for the tail of the phase-in rather than starting the
# moment the rule bit.
SCORE_FROM = "1997Q1"

# Renames that would silently zero a series. None of these forms is in
# FORMS - the map exists so that adding one later is a deliberate act.
KNOWN_RENAMES = {
    "SC 14D1": ("SC TO-T", "2000-01"),
    "SC 13D": ("SCHEDULE 13D", "2024-12"),
}

_ACC = re.compile(r"(\d{10}-\d{2}-\d{6})")


def _quarters(upto_year, upto_q):
    y, q = INGEST_FROM
    out = []
    while (y, q) <= (upto_year, upto_q):
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def fetch_quarter(year, q, tries=3):
    """Stream one form.idx and return {month: set(accessions)}.

    Streamed and filtered in the pipe rather than saved: each index is
    37-53MB and a full rebuild is ~130 of them. We never need the file,
    only the handful of rows matching FORMS.
    """
    url = IDX.format(year=year, q=q)
    pat = "^(" + "|".join(FORMS) + ") "
    last = None
    for i in range(tries):
        try:
            p = subprocess.run(
                f'curl -sS --http1.1 --max-time 180 -A "{SEC_UA}" "{url}" '
                f'| grep -E "{pat}" || true',
                shell=True, capture_output=True, text=True, timeout=240)
            if p.returncode == 0:
                break
            last = RuntimeError(f"rc={p.returncode} {p.stderr[:200]}")
        except Exception as e:      # noqa: BLE001
            last = e
        if i < tries - 1:
            time.sleep(2 ** (i + 1))
    else:
        raise RuntimeError(f"EDGAR fetch failed: {url}") from last

    return parse_index_lines(p.stdout.splitlines())


def parse_index_lines(lines, forms=None):
    """Parse form.idx rows into {(month, form): set(accession)}.

    Split out from the fetch so the DEDUPE - the whole point of this
    module - is testable without a network round trip.

    form.idx emits ONE ROW PER FILER. A registration with forty
    co-registrant subsidiaries produces forty rows bearing the SAME
    accession number for one document. Collecting accessions into a set
    is what turns rows back into filings.
    """
    forms = forms or FORMS
    months = {}
    for line in lines:
        parts = line.split()
        form = parts[0] if parts else ""
        if form not in forms:
            continue
        d = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        a = _ACC.search(line)
        if not d or not a:
            continue
        months.setdefault((d.group(1)[:7], form), set()).add(a.group(1))
    return months


def build(upto_year=2026, upto_q=3, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    monthly = {}
    for (y, q) in _quarters(upto_year, upto_q):
        path = os.path.join(CACHE, f"edgar_{y}Q{q}.json")
        # The CURRENT quarter is always refetched - it is still filling.
        is_current = (y, q) == (upto_year, upto_q)
        if refresh or is_current or not os.path.exists(path):
            got = fetch_quarter(y, q)
            ser = {f"{m}|{f}": sorted(a) for (m, f), a in got.items()}
            with open(path, "w") as fh:
                json.dump({"quarter": f"{y}Q{q}", "fetched": time.strftime("%Y-%m-%d"),
                           "source_url": IDX.format(year=y, q=q),
                           "counts": {k: len(v) for k, v in ser.items()}}, fh)
        with open(path) as fh:
            for k, n in json.load(fh)["counts"].items():
                m, f = k.split("|")
                monthly.setdefault(m, {}).setdefault(f, 0)
                monthly[m][f] += n
    return monthly


def write_csv(monthly, path=OUT):
    rows = sorted(monthly)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month", "DEFM14A", "PREM14A", "merger_proxies"])
        for m in rows:
            d = monthly[m].get("DEFM14A", 0)
            p = monthly[m].get("PREM14A", 0)
            w.writerow([m, d, p, d + p])
    return path


def scoreable(quarter):
    qy, qq = int(quarter[:4]), int(quarter[5])
    fy, fq = int(SCORE_FROM[:4]), int(SCORE_FROM[5])
    return (qy, qq) >= (fy, fq)


if __name__ == "__main__":
    m = build()
    p = write_csv(m)
    ks = sorted(m)
    print(f"{len(ks)} months, {ks[0]} .. {ks[-1]} -> {p}\n")
    print("EDGAR phase-in (why we score only from 1997Q1):")
    for probe in ("1994-01", "1995-01", "1996-01", "1996-06", "1997-01",
                  "2000-01", "2007-06", "2021-03", "2025-01"):
        if probe in m:
            d, pr = m[probe].get("DEFM14A", 0), m[probe].get("PREM14A", 0)
            print(f"  {probe}  DEFM14A {d:>3}  PREM14A {pr:>3}  total {d+pr:>3}")
    print("\nmost recent 8 months:")
    for k in ks[-8:]:
        d, pr = m[k].get("DEFM14A", 0), m[k].get("PREM14A", 0)
        print(f"  {k}  DEFM14A {d:>3}  PREM14A {pr:>3}  total {d+pr:>3}")
