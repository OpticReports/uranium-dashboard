#!/usr/bin/env python3
"""BARBELL-TIMER Phase 0 data fetcher — freezes every input series to fixtures/.

Research only. Run once to freeze; re-running overwrites fixtures and stamps a
new fetch timestamp in fixtures/PROVENANCE.md. All downstream scripts read ONLY
from fixtures/ (never hit the network), per the frozen-brief discipline.

Sources
-------
FMP  /stable/historical-price-eod/{light,full,dividend-adjusted}
     GDE, SPY, GLD, BOXX (dividend-adjusted daily -> total-return-ish adjClose),
     GDE also full (raw OHLC, for open-execution checks),
     GCUSD (continuous COMEX gold front-month, light, 1976-02-26 ->),
     ^GSPC (S&P 500 price index daily, light, for daily-maxDD estimates only).
FRED TB3MS, DTB3, DFII10, DTWEXM, DTWEXBGS, CPIAUCSL, FEDFUNDS.
Repo ../fixtures/phase_data.json — Shiller monthly SPX price+dividend
     (MONTHLY-AVERAGE price convention — flagged), datahub gold monthly 1833->
     (monthly-average LBMA convention — flagged).

Known caps: FMP returns max 5000 rows/call, newest first -> paginate by date
windows. Every gap/quirk found at fetch time is appended to the provenance log.
"""
import datetime as dt
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
REPO_FIX = os.path.join(HERE, "..", "fixtures", "phase_data.json")

FMP_KEY = os.environ.get("FMP_KEY", "TQYoJ120E2XRY4jf20NzUx7mmBBp23o5")
FRED_KEY = os.environ.get("FRED_KEY", "697cc828d99500845c7b5056e4a7c5a2")
FMP_BASE = "https://financialmodelingprep.com/stable/historical-price-eod"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

TODAY = dt.date.today().isoformat()
PROV = []  # provenance lines


def log(msg):
    print(msg)
    PROV.append(msg)


def fmp_paged(endpoint, symbol, start, end=TODAY, chunk_years=15):
    """Fetch [start, end] in date windows (5000-row cap per call), oldest-first."""
    rows = {}
    y0 = int(start[:4])
    y1 = int(end[:4])
    for cs in range(y0, y1 + 1, chunk_years):
        f = f"{cs}-01-01" if cs > y0 else start
        t = f"{min(cs + chunk_years - 1, y1)}-12-31"
        if t > end:
            t = end
        url = (f"{FMP_BASE}/{endpoint}?symbol={requests.utils.quote(symbol)}"
               f"&from={f}&to={t}&apikey={FMP_KEY}")
        for attempt in range(3):
            r = requests.get(url, timeout=60)
            if r.status_code == 200:
                break
            time.sleep(2 * (attempt + 1))
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):  # error payload
            raise RuntimeError(f"FMP error for {symbol} {f}->{t}: {data}")
        if len(data) >= 5000:
            log(f"  WARNING {symbol} {f}->{t}: hit 5000-row cap, window truncated"
                " — shrink chunk_years")
        for row in data:
            rows[row["date"]] = row  # dedupe on date, newest call wins
        time.sleep(0.25)
    out = [rows[d] for d in sorted(rows)]
    return out


def fred_series(series_id):
    url = (f"{FRED_BASE}?series_id={series_id}&api_key={FRED_KEY}"
           f"&file_type=json&limit=100000")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    obs = r.json()["observations"]
    out, gaps = [], 0
    for o in obs:
        if o["value"] == ".":
            gaps += 1
            continue  # logged, never interpolated here; alignment handled downstream
        out.append([o["date"], float(o["value"])])
    return out, gaps


def save(name, payload):
    path = os.path.join(FIX, name)
    with open(path, "w") as fh:
        json.dump(payload, fh)
    return path


def main():
    os.makedirs(FIX, exist_ok=True)
    log(f"# BARBELL-TIMER fixture provenance log — fetched {TODAY}")
    log("")
    log("Rule: every series below is FROZEN as of the fetch date. Downstream")
    log("scripts read fixtures only. Gaps are logged, never interpolated at")
    log("fetch time.")
    log("")

    # ---------------- FMP dailies ----------------
    fmp_jobs = [
        # (fixture name, endpoint, symbol, start, note)
        ("fmp_gde_dividend_adjusted.json", "dividend-adjusted", "GDE", "2022-03-01",
         "GDE ETF daily, dividend-adjusted (adjClose ~= total-return index). "
         "Inception 2022-03-15 (first trade 2022-03-16/17 on exchanges)."),
        ("fmp_gde_full.json", "full", "GDE", "2022-03-01",
         "GDE ETF daily raw OHLC (unadjusted close/open) — for open-execution "
         "and dividend cross-checks."),
        ("fmp_spy_dividend_adjusted.json", "dividend-adjusted", "SPY", "1993-01-29",
         "SPY daily dividend-adjusted (total-return proxy incl. dividends, "
         "gross of nothing — SPY's 9bp ER is already inside the NAV)."),
        ("fmp_gld_dividend_adjusted.json", "dividend-adjusted", "GLD", "2004-11-18",
         "GLD daily (physical gold minus 40bp/yr fee) — cross-check series."),
        ("fmp_boxx_dividend_adjusted.json", "dividend-adjusted", "BOXX", "2022-12-01",
         "BOXX daily adj — actual bills-proxy vehicle post-2022 per brief."),
        ("fmp_dgl_dividend_adjusted.json", "dividend-adjusted", "DGL", "2007-01-05",
         "Invesco DB Gold (DGL): REAL gold-futures fund (futures + T-bill "
         "collateral, ~0.75-0.78%/yr ER). Used to REALIZE the futures-vs-spot"
         " carry gap: DGL_TR - GLD_TR ~= lease - ER_DGL + ER_GLD, so realized"
         " lease ~= (DGL-GLD) + 0.78% - 0.40%. Brief lists lease rates as"
         " optional Phase 0 data; this is the measurement instrument chosen"
         " (documented amendment: extra ticker, same endpoint)."),
        ("fmp_gcusd_light.json", "light", "GCUSD", "1976-02-26",
         "COMEX gold continuous front-month, PRICE-SPLICED (not back-adjusted):"
         " level tracks the front contract so LEVEL returns ~= spot returns and"
         " do NOT embed the carry a real long-futures position pays. FLAGGED —"
         " replication.py subtracts financing carry explicitly instead."),
        ("fmp_gspc_light.json", "light", "^GSPC", "1970-01-01",
         "S&P 500 price index daily (NO dividends) — used only for daily-maxDD"
         " shape estimates pre-1993, with dividends smeared from monthly."),
    ]
    for name, endpoint, symbol, start, note in fmp_jobs:
        rows = fmp_paged(endpoint, symbol, start)
        save(name, {"source": f"FMP /stable/historical-price-eod/{endpoint}",
                    "symbol": symbol, "fetched": TODAY, "note": note,
                    "rows": rows})
        log(f"- {name}: {symbol} {rows[0]['date']} -> {rows[-1]['date']}"
            f" ({len(rows)} rows). {note}")

    # GDE cash dividends (to sanity-check adjClose vs raw close)
    r = requests.get("https://financialmodelingprep.com/stable/dividends"
                     f"?symbol=GDE&apikey={FMP_KEY}", timeout=60)
    r.raise_for_status()
    divs = r.json()
    save("fmp_gde_dividends.json",
         {"source": "FMP /stable/dividends", "symbol": "GDE", "fetched": TODAY,
          "rows": divs})
    log(f"- fmp_gde_dividends.json: {len(divs)} GDE distributions (cross-check"
        " for the adjusted series; GDE pays semi-annual, incl. large cap-gain"
        " distributions from futures gains).")

    # ---------------- FRED ----------------
    fred_jobs = [
        ("TB3MS", "3M T-bill secondary-market rate, monthly avg, %/yr, 1934->"),
        ("DTB3", "3M T-bill secondary-market rate, DAILY, %/yr — bills leg for"
         " the daily replication"),
        ("DFII10", "10Y TIPS constant-maturity real yield, daily, 2003-> "
         "(pre-2003 proxy is a Phase-2 concern, not fetched here)"),
        ("DTWEXM", "Trade-weighted USD major currencies (goods), daily,"
         " 1973-01 -> 2020-01 (DISCONTINUED — splice partner below)"),
        ("DTWEXBGS", "Trade-weighted USD broad goods&services, daily, 2006-01"
         " -> present (splice onto DTWEXM at 2006-01 via ratio; splice done"
         " downstream and flagged wherever used)"),
        ("CPIAUCSL", "CPI-U SA monthly, for real-rate work in Phase 2"),
        ("FEDFUNDS", "Effective fed funds, monthly avg, 1954->"),
    ]
    for sid, note in fred_jobs:
        obs, gaps = fred_series(sid)
        save(f"fred_{sid.lower()}.json",
             {"source": f"FRED {sid}", "fetched": TODAY, "note": note,
              "rows": obs})
        log(f"- fred_{sid.lower()}.json: {sid} {obs[0][0]} -> {obs[-1][0]}"
            f" ({len(obs)} obs, {gaps} missing-value rows dropped-and-logged)."
            f" {note}")

    # ---------------- repo long-history fixtures (copied, provenance kept) ---
    with open(REPO_FIX) as fh:
        repo = json.load(fh)
    shiller = repo["shiller"]
    gold_m = repo["gold"]
    save("longhist_shiller_spx.json",
         {"source": "repo ../fixtures/phase_data.json <- Shiller ie_data",
          "fetched": TODAY,
          "note": ("Shiller monthly S&P composite. PRICE IS THE MONTHLY AVERAGE"
                   " of daily closes, NOT month-end — FLAGGED: understates vol"
                   " and maxDD, smears turning points ~half a month. Dividends"
                   " are trailing annualized rates, monthly interpolated."
                   " Used only pre-1993 (SPY splice after)."),
          "px": shiller["px"], "div": shiller["div"], "cpi": shiller["cpi"]})
    log(f"- longhist_shiller_spx.json: px {shiller['px'][0][0]} ->"
        f" {shiller['px'][-1][0]}, div -> {shiller['div'][-1][0]}."
        " MONTHLY-AVERAGE price convention FLAGGED. div series ends"
        f" {shiller['div'][-1][0]} — post-1993 uses SPY adj so no gap in the"
        " spliced series.")
    save("longhist_gold_monthly.json",
         {"source": "repo ../fixtures/phase_data.json <- datahub gold-prices",
          "fetched": TODAY,
          "note": ("Gold monthly 1833->, LBMA/London MONTHLY-AVERAGE fix in USD"
                   " — FLAGGED (same smearing caveat as Shiller). Used only"
                   " pre-1976-03 (GCUSD month-end daily after)."),
          "rows": gold_m})
    log(f"- longhist_gold_monthly.json: {gold_m[0][0]} -> {gold_m[-1][0]}"
        f" ({len(gold_m)} obs). MONTHLY-AVERAGE convention FLAGGED.")

    # ---------------- provenance file ----------------
    log("")
    log("## Standing approximations (fixed at fetch time)")
    log("1. GCUSD is a price-spliced continuous front-month: its returns are")
    log("   spot-like; futures-position excess return must be built as")
    log("   spot-return minus financing carry (bills - lease). replication.py")
    log("   quantifies and documents the lease haircut; VALIDATION_REPORT.md")
    log("   verifies the whole construction against actual GDE NAV.")
    log("2. Shiller SPX price and datahub gold are monthly AVERAGES, not")
    log("   month-end. Splices to daily month-end data occur 1993-01 (SPY) and")
    log("   1976-03 (GCUSD). Every consumer restates this caveat.")
    log("3. FRED daily series have holiday gaps ('.' rows dropped here);")
    log("   downstream alignment forward-fills RATES only (never prices),")
    log("   which is standard for yields and flagged in code.")
    with open(os.path.join(FIX, "PROVENANCE.md"), "w") as fh:
        fh.write("\n".join(PROV) + "\n")
    print(f"\nWrote {len(os.listdir(FIX))} files to {FIX}")


if __name__ == "__main__":
    sys.exit(main())
