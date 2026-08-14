#!/usr/bin/env python3
"""SOXL-dispersion Phase 0 data fetcher — freezes every input to fixtures/.

Same frozen-brief discipline as barbell-lab/research/barbell_timer: run once
to freeze, then every downstream script reads ONLY from fixtures/ and never
touches the network. Re-running overwrites fixtures and re-stamps
fixtures/PROVENANCE.md.

Sources (all FMP `stable` endpoints; key from FMP_API_KEY):
  historical-price-eod/dividend-adjusted  total-return proxy (splits + dists)
  historical-price-eod/full               raw OHLC for execution modeling
  historical-market-capitalization        point-in-time caps for PIT ranking
  treasury-rates                          3m bill -> short rebate / financing

NOT available from this vendor, and therefore NOT fabricated here:
  - SOXL borrow-rate history (IBKR SLB / Markit). Handled downstream as a
    swept parameter with a solved breakeven, never as an invented series.
  - Point-in-time SOXX membership. Reconstructed by PIT market-cap rank over
    a candidate set that includes delisted names (see universe.py), then
    validated against today's actual holdings and against SOXX's own return.
"""
import datetime as dt
import json
import os
import sys
import time

import requests

from universe import ALL_TICKERS, DEAD_TICKERS, INSTRUMENTS

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
BASE = "https://financialmodelingprep.com/stable"
KEY = os.environ.get("FMP_API_KEY") or os.environ.get("FMP_KEY")

START = "2009-01-01"        # pre-SOXL history for beta/vol warmup
TODAY = dt.date.today().isoformat()
OHLC_TICKERS = set(INSTRUMENTS)   # raw OHLC only where execution is modeled

PROV = []


def log(msg):
    print(msg, flush=True)
    PROV.append(msg)


def get(path, params, tries=4):
    params = dict(params, apikey=KEY)
    last = None
    for a in range(tries):
        try:
            r = requests.get(f"{BASE}/{path}", params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:160]}"
        except Exception as e:                      # network flake
            last = repr(e)
        time.sleep(2 ** a)
    raise RuntimeError(f"{path} {params.get('symbol')}: {last}")


def paged(path, symbol, start=START, end=TODAY, chunk_years=5, key="date"):
    """Fetch [start, end] in windows (vendor caps ~5000 rows/call)."""
    rows = {}
    y0, y1 = int(start[:4]), int(end[:4])
    for cs in range(y0, y1 + 1, chunk_years):
        f = f"{cs}-01-01" if cs > y0 else start
        t = min(f"{cs + chunk_years - 1}-12-31", end)
        data = get(path, {"symbol": symbol, "from": f, "to": t})
        if isinstance(data, dict):
            raise RuntimeError(f"{symbol}: vendor error {str(data)[:200]}")
        if len(data) >= 5000:
            log(f"  WARN {symbol} {f}->{t}: hit 5000-row cap; shrink chunk")
        for row in data:
            rows[row[key]] = row
        time.sleep(0.12)
    return [rows[d] for d in sorted(rows)]


def truncate_dead(symbol, rows):
    """Hard-truncate acquired names at their deal-close month and report any
    series that ran past it (ticker reuse -> would otherwise contaminate)."""
    through = DEAD_TICKERS.get(symbol)
    if not through:
        return rows
    kept = [r for r in rows if r["date"] <= through]
    dropped = len(rows) - len(kept)
    if dropped:
        last = rows[-1]["date"]
        log(f"  REUSE-GUARD {symbol}: series runs to {last} but company died "
            f"{through} -> dropped {dropped} post-death rows")
    return kept


def main():
    if not KEY:
        sys.exit("FMP_API_KEY not set")
    os.makedirs(FIX, exist_ok=True)
    log(f"# SOXL-dispersion fixture freeze — fetched {TODAY}")
    log(f"# vendor: FMP stable endpoints; window {START} -> {TODAY}")

    prices, ohlc, mcaps = {}, {}, {}
    missing, thin = [], []

    for i, sym in enumerate(ALL_TICKERS, 1):
        try:
            rows = paged("historical-price-eod/dividend-adjusted", sym)
        except Exception as e:
            log(f"  MISSING {sym}: price fetch failed ({e})")
            missing.append(sym)
            continue
        rows = truncate_dead(sym, rows)
        if len(rows) < 60:
            log(f"  THIN {sym}: only {len(rows)} adj rows -> excluded")
            thin.append(sym)
            continue
        prices[sym] = {r["date"]: r["adjClose"] for r in rows
                       if r.get("adjClose")}

        if sym in OHLC_TICKERS:
            raw = truncate_dead(sym, paged("historical-price-eod/full", sym))
            ohlc[sym] = {r["date"]: [r.get("open"), r.get("high"),
                                     r.get("low"), r.get("close"),
                                     r.get("volume")] for r in raw}

        try:
            mc = truncate_dead(
                sym, paged("historical-market-capitalization", sym))
            # month-end sampling is all the PIT ranking needs
            by_month = {}
            for r in mc:
                if r.get("marketCap"):
                    by_month[r["date"][:7]] = (r["date"], r["marketCap"])
            mcaps[sym] = {v[0]: v[1] for v in by_month.values()}
        except Exception as e:
            log(f"  NO-MCAP {sym}: {e}")

        if i % 20 == 0:
            log(f"  ... {i}/{len(ALL_TICKERS)} tickers")

    # Treasury 3m -> short rebate and margin-financing base rate.
    tsy = {}
    y0, y1 = int(START[:4]), int(TODAY[:4])
    for cs in range(y0, y1 + 1, 2):
        data = get("treasury-rates", {"from": f"{cs}-01-01",
                                      "to": min(f"{cs+1}-12-31", TODAY)})
        for r in data:
            if r.get("month3") is not None:
                tsy[r["date"]] = r["month3"]
        time.sleep(0.12)
    log(f"  treasury 3m: {len(tsy)} obs "
        f"{min(tsy) if tsy else '-'} -> {max(tsy) if tsy else '-'}")

    # Today's actual SOXX holdings — the out-of-model check on the PIT rebuild.
    holdings = get("etf/holdings", {"symbol": "SOXX"})
    log(f"  SOXX live holdings: {len(holdings)} lines (reconstruction check)")

    out = {
        "meta": {
            "fetched": TODAY, "vendor": "FMP stable", "start": START,
            "missing": missing, "thin": thin,
            "dead_truncated": DEAD_TICKERS,
        },
        "prices": prices, "ohlc": ohlc, "mcaps": mcaps,
        "treasury_3m": tsy,
        "soxx_holdings_live": [
            {"asset": h.get("asset"), "weight": h.get("weightPercentage")}
            for h in holdings],
    }
    path = os.path.join(FIX, "market_data.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    log(f"  wrote {path} ({os.path.getsize(path)/1e6:.1f} MB), "
        f"{len(prices)} price series, {len(mcaps)} mcap series")

    with open(os.path.join(FIX, "PROVENANCE.md"), "w") as f:
        f.write("# Fixture provenance — SOXL dispersion study\n\n")
        f.write("Frozen by fetch_data.py. Downstream scripts are offline.\n\n")
        f.write("```\n" + "\n".join(PROV) + "\n```\n")


if __name__ == "__main__":
    main()
