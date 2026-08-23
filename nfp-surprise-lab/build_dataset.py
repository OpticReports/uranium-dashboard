"""Rebuild data/nfp_surprises.json from the frozen FMP pull.

The raw pull (data/fmp_payroll_events_raw.json) came from FMP's economic
calendar, queried in ONE-MONTH windows. That matters: FMP caps rows per
response and silently drops the OLDEST part of a wide window, so half-year
windows returned only 6 prints/year instead of 12. Anything wider than a
month is unsafe.

  python3 build_dataset.py            # rebuild from frozen raw
  python3 build_dataset.py --refetch  # re-pull from FMP (needs FMP_API_KEY)
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).parent
RAW = HERE / "data" / "fmp_payroll_events_raw.json"
OUT = HERE / "data" / "nfp_surprises.json"
CUTOFF = dt.date(2026, 8, 23)

# Reference-month overrides where "release month minus one" is wrong.
# 2025-11-20 was the SEPTEMBER 2025 Employment Situation (+119k), delayed ~6
# weeks by the October 2025 lapse in appropriations. October 2025 has no
# standalone release at all -- its establishment data was published alongside
# November on 2025-12-16. Verified against the BLS news-release archive.
REF_MONTH_OVERRIDES = {"2025-11-20": "2025-09"}


def refetch() -> list[dict]:
    key = os.environ["FMP_API_KEY"]
    found: dict[tuple, dict] = {}
    for year in range(2010, CUTOFF.year + 1):
        for month in range(1, 13):
            if (year, month) > (CUTOFF.year, CUTOFF.month):
                break
            last = calendar.monthrange(year, month)[1]
            url = (f"https://financialmodelingprep.com/stable/economic-calendar"
                   f"?from={year}-{month:02d}-01&to={year}-{month:02d}-{last}"
                   f"&apikey={key}")
            payload = []
            for attempt in range(3):
                try:
                    payload = json.load(urllib.request.urlopen(url, timeout=60))
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        print(f"  ERR {year}-{month:02d}: {exc}", file=sys.stderr)
                    else:
                        time.sleep(2 * (attempt + 1))
            for row in payload:
                if row.get("country") == "US" and "payroll" in str(row.get("event", "")).lower():
                    found[(row["date"], row["event"])] = row
            time.sleep(0.2)
    RAW.write_text(json.dumps(list(found.values()), indent=1))
    return list(found.values())


def build(raw: list[dict]) -> list[dict]:
    rows: dict[dt.date, dict] = {}
    for item in raw:
        if not item["event"].startswith("Non Farm Payrolls"):
            continue
        if item["estimate"] is None or item["actual"] is None:
            continue
        rel = dt.datetime.strptime(item["date"][:10], "%Y-%m-%d").date()
        if rel > CUTOFF:
            continue
        ref = (rel.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
        ref = REF_MONTH_OVERRIDES.get(str(rel), ref)
        consensus, actual = float(item["estimate"]), float(item["actual"])
        rows.setdefault(rel, dict(release=str(rel), ref_month=ref,
                                  consensus=consensus, actual=actual,
                                  surprise=round(actual - consensus, 1)))
    return [rows[k] for k in sorted(rows)]


if __name__ == "__main__":
    source = refetch() if "--refetch" in sys.argv else json.loads(RAW.read_text())
    built = build(source)
    OUT.write_text(json.dumps(built, indent=1))
    print(f"wrote {OUT} - {len(built)} releases, "
          f"{built[0]['release']} -> {built[-1]['release']}")
