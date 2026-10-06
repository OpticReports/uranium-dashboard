"""Sector-tier measurement 3: a one-day dry run of what Tier 0 + Tier 1 would add.

Amendments 2-3: one day, not one week; the quota half of the gate is met on
Casey's statement, so this reports calls per day by provider against OUR
client-side limits (FMP 600/minute, CT.gov ~0.22 s between calls), runtime
and database growth. Per-day figures that are extrapolated say so.

  Tier 0: the all-sector screener download the sweep ALREADY makes (zero new
          calls) written as one dated row per name into a scratch SQLite
          table; the file growth is the per-day database cost.
  Tier 1: one weekday's fifth of the weekly CT.gov evaluation run LIVE (no
          cache) for the names >= $300M in today's census; calls, seconds,
          bytes. Classification runtime for every eligible name, timed.
  FMP:    monthly profiles for every census name >= $300M (rule (c)),
          runway refreshes on filings (~4 a year per Tier 1 name), one-time
          60-day backfill per Tier 1 name (Tier 1 size from results.json).

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.m3_dryrun
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
import zlib
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from app.ingestion import discovery as D  # noqa: E402
from research.sector_tier import build_ctgov as C  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402

OUT = HERE / "m3.json"
FMP_LIMIT_PER_MIN = 600
CTGOV_DELAY = 1.25   # CT.gov allows ~50 calls/minute (stage 2 hit 429s faster)


def tier0_growth() -> dict:
    data = json.loads((P.CACHE / "screener_all_2026-10-05.json").read_text())
    rows = ((data or {}).get("data") or {}).get("rows") or []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "t0.db"
        con = sqlite3.connect(db)
        con.execute("create table census_snapshot (asof text, symbol text, name text, last real, pct real,"
                    " market_cap real, volume real, sector text, industry text, primary key (asof, symbol))")
        con.commit()
        con.execute("vacuum")
        base = db.stat().st_size
        sizes = []
        for day in range(5):
            asof = f"2026-10-0{day + 1}"
            con.executemany("insert into census_snapshot values (?,?,?,?,?,?,?,?,?)", [
                (asof, r.get("symbol"), r.get("name"), D.parse_money(r.get("lastsale")), D.parse_pct(r.get("pctchange")),
                 D.parse_money(r.get("marketCap")), D.parse_money(r.get("volume")), r.get("sector"), r.get("industry"))
                for r in rows if r.get("symbol")])
            con.commit()
            sizes.append(db.stat().st_size)
        con.close()
    per_day = (sizes[-1] - base) / len(sizes)
    return {"rows_per_day": len(rows), "bytes_per_trading_day": round(per_day),
            "mb_per_year_252d": round(per_day * 252 / 1e6, 1), "new_calls_per_day": 0,
            "note": "the download call is already made by the census supplement"}


def tier1_ctgov_one_weekday(eligible_today: list[dict], census: dict) -> dict:
    bucket = [p for p in eligible_today if zlib.crc32(p["symbol"].encode()) % 5 == 0]
    calls = 0
    t0 = time.time()
    nbytes = 0
    client = httpx.Client(timeout=30)
    for p in bucket:
        q = D.clean_company_name((census.get(p["symbol"]) or {}).get("screener_name") or p["name"])
        token = None
        while True:
            params = {"query.spons": q, "fields": C.SEARCH_FIELDS, "pageSize": 1000}
            if token:
                params["pageToken"] = token
            for attempt in range(5):
                r = client.get(C.B.V2_SEARCH, params=params)
                calls += 1
                if r.status_code != 429:
                    break
                time.sleep(2 ** (attempt + 1))
            nbytes += len(r.content)
            time.sleep(CTGOV_DELAY)
            if r.status_code != 200:
                break
            token = r.json().get("nextPageToken")
            if not token:
                break
    secs = time.time() - t0
    return {"names_this_weekday": len(bucket), "calls": calls, "seconds": round(secs, 1),
            "mb_downloaded": round(nbytes / 1e6, 1), "measured_live": True,
            "weekly_total_calls_extrapolated": calls * 5}


def main() -> None:
    pop = json.loads(P.OUT_POP.read_text())
    census = {r["symbol"]: r for r in P.census_today()}
    caps_today = {p["symbol"]: (census.get(p["symbol"]) or {}).get("mcap_now") or 0 for p in pop}
    eligible_today = [p for p in pop if p["source"] != "delisted" and caps_today[p["symbol"]] >= P.MCAP_MIN]
    res = json.loads((HERE / "results.json").read_text()) if (HERE / "results.json").exists() else {}
    run = res.get(res.get("verdict_from") == "funnel" and "funnel_titles" or "strict") or {}
    t1 = (run.get("m2") or {}).get("tier1_today")

    t0 = time.time()
    from research.sector_tier.measure import load_ctgov
    ctg = load_ctgov()["names"]
    n_eval = 0
    for p in eligible_today:
        e = ctg.get(p["symbol"]) or {}
        own = [r for r in e.get("studies") or [] if r.get("own_p23")]
        D.genomics_tags_for([p["name"]] + [r["title"] for r in own])
        n_eval += 1
    classify_secs = time.time() - t0

    out = {
        "tier0": tier0_growth(),
        "tier1_ctgov": tier1_ctgov_one_weekday(eligible_today, census),
        "tier1_classification": {"names": n_eval, "seconds_incl_load": round(classify_secs, 2)},
        # Rule (c) needs a monthly profile for EVERY census name >= $300M (that is how
        # a name outside Tier 1 gets in); runway figures refresh on filings, ~4 a year.
        "fmp": None if not t1 else {
            "tier1_size_today": t1,
            "census_names_needing_monthly_profile": len(eligible_today),
            "monthly_profiles_per_weekday": round(len(eligible_today) / 21, 1),
            "runway_refreshes_per_weekday": round(t1 * 4 / 252, 1),
            "one_time_backfill_calls": t1,
            "minutes_at_our_600_per_min_limiter_per_weekday": round((len(eligible_today) / 21 + t1 * 4 / 252) / FMP_LIMIT_PER_MIN, 3),
            "extrapolated": True},
        "quota": "provider quota taken as met on Casey's statement (amendment 2); figures above are against our own client limits",
    }
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
