"""Sector-tier measurements, stage 1: the measured population and its moves.

Pre-registration: docs/DESIGN_SECTOR_TIER.md (rev 3 + amendments of
2026-10-05). This stage only ASSEMBLES data; it classifies nothing and
labels nothing.

Population = today's Nasdaq census (health care + the discovery supplement:
non-health-care rows filed "Biotechnology: ..." or with a genomics keyword in
the name; warrants/units/preferreds dropped) UNION names delisted from a US
exchange inside the window whose FMP profile is Healthcare or whose name
carries a genomics keyword (survivorship: acquired and failed names are the
ones a census taken today forgets).

Per name: FMP profile (industry, description, IPO date), daily historical
market cap, dividend-adjusted daily bars. Every response is cached under
backend/data/sector_tier_cache/ (gitignored) so a rerun costs nothing.

Moves = every single-day adjusted close-to-close move with |r| >= 20% on a
trading day in the window, with the PRIOR day's historical market cap >=
$300M, excluding the first five trading days after an IPO inside the window.
Flags, never silent drops: M&A (the name is the target of an FMP M&A filing
within 5 calendar days), possible bad print (the next day reverses the move
to within 2%), and moves >= 100% (checked by hand in the report).

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.build_population
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion import discovery as D  # noqa: E402

CACHE = BACKEND / "data" / "sector_tier_cache"
OUT_POP = HERE / "population.json"
OUT_MOVES = HERE / "moves.json"
FMP = "https://financialmodelingprep.com/stable"
WINDOW = (date(2025, 10, 1), date(2026, 9, 30))
HIST_FROM = date(2025, 8, 1)          # warm-up for the first window day's prior close
HIST_TO = date(2026, 10, 2)
MOVE_MIN = 0.20
MCAP_MIN = 300e6
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "NYSE American", "NYSEArca", "NYSE ARCA"}
_last_call = [0.0]


def _key() -> str:
    k = os.environ.get("FMP_API_KEY")
    if not k:
        raise SystemExit("FMP_API_KEY not set")
    return k


def _cached_get(name: str, url: str, params: dict, *, browser: bool = False):
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(5):
        wait = 0.11 - (time.time() - _last_call[0])      # <= ~9 calls/s, under the 600/min limiter
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = httpx.get(url, params=params, timeout=45,
                          headers=D._HEADERS if browser else None)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
            return data
        except (httpx.HTTPError, ValueError):
            time.sleep(2 ** attempt)
    return None


def fmp(name: str, endpoint: str, **params):
    params["apikey"] = _key()
    return _cached_get(f"fmp/{name}", f"{FMP}/{endpoint}", params)


def census_today() -> list[dict]:
    data = _cached_get("screener_all_2026-10-05", D._SCREENER_URL,
                       {"tableonly": "true", "download": "true", "limit": "10000"}, browser=True)
    rows = ((data or {}).get("data") or {}).get("rows") or []
    out = []
    for r in rows:
        name = str(r.get("name") or "")
        if not r.get("symbol") or D.is_instrument_row(name):
            continue
        hc = r.get("sector") == "Health Care"
        supp = (not hc) and (str(r.get("industry") or "").startswith("Biotechnology:")
                             or bool(D.genomics_tags_for([name])))
        if hc or supp:
            out.append({"symbol": r["symbol"].strip().upper(), "screener_name": name,
                        "source": "census_hc" if hc else "census_supplement",
                        "screener_industry": r.get("industry"), "mcap_now": D.parse_money(r.get("marketCap"))})
    return out


def delisted_in_window() -> list[dict]:
    out, page = [], 0
    while page < 400:
        rows = fmp(f"delisted/page_{page}", "delisted-companies", page=page, limit=100) or []
        if not rows:
            break
        for r in rows:
            d = str(r.get("delistedDate") or "")[:10]
            if WINDOW[0].isoformat() <= d <= HIST_TO.isoformat() and str(r.get("exchange") or "") in US_EXCHANGES:
                out.append({"symbol": str(r["symbol"]).upper(), "screener_name": r.get("companyName") or "",
                            "source": "delisted", "delisted_date": d, "screener_industry": None, "mcap_now": None})
        oldest = min(str(r.get("delistedDate") or "9999")[:10] for r in rows)
        if oldest < WINDOW[0].isoformat():
            break
        page += 1
    return out


def main() -> None:
    t0 = time.time()
    names = {r["symbol"]: r for r in census_today()}
    print(f"census today: {len(names)} names", flush=True)
    delisted = delisted_in_window()
    print(f"US delistings in window (all sectors): {len(delisted)}", flush=True)

    # profile every name; keep delisted names only when healthcare or genomics-keyword named
    kept_delisted = 0
    for r in delisted:
        if r["symbol"] in names:
            continue
        prof = (fmp(f"profile/{r['symbol']}", "profile", symbol=r["symbol"]) or [None])
        p = prof[0] if prof else None
        sector = (p or {}).get("sector")
        if sector == "Healthcare" or D.genomics_tags_for([r["screener_name"]]):
            names[r["symbol"]] = r
            kept_delisted += 1
    print(f"delisted names kept (healthcare or genomics-named): {kept_delisted}", flush=True)

    pop, moves = [], []
    for i, (sym, r) in enumerate(sorted(names.items())):
        prof = (fmp(f"profile/{sym}", "profile", symbol=sym) or [None])
        p = (prof[0] if prof else None) or {}
        mc = fmp(f"mcap/{sym}", "historical-market-capitalization", symbol=sym,
                 **{"from": HIST_FROM.isoformat(), "to": HIST_TO.isoformat()}) or []
        bars = fmp(f"bars/{sym}", "historical-price-eod/dividend-adjusted", symbol=sym,
                   **{"from": HIST_FROM.isoformat(), "to": HIST_TO.isoformat()}) or []
        mcap = {str(x["date"])[:10]: float(x["marketCap"]) for x in mc if x.get("marketCap")}
        bars = sorted((b for b in bars if b.get("adjClose")), key=lambda b: b["date"])
        win_caps = [v for d, v in mcap.items() if WINDOW[0].isoformat() <= d <= WINDOW[1].isoformat()]
        ipo = str(p.get("ipoDate") or "")[:10] or None
        pop.append({
            "symbol": sym, "name": p.get("companyName") or r["screener_name"], "source": r["source"],
            "delisted_date": r.get("delisted_date"), "screener_industry": r.get("screener_industry"),
            "fmp_sector": p.get("sector"), "fmp_industry": p.get("industry"),
            "description": (p.get("description") or "")[:900], "ipo_date": ipo,
            "is_actively_trading": p.get("isActivelyTrading"), "mcap_now": r.get("mcap_now"),
            "mcap_max_window": max(win_caps) if win_caps else None, "n_bars": len(bars),
        })
        ipo_in_window = bool(ipo and WINDOW[0].isoformat() <= ipo <= WINDOW[1].isoformat())
        sorted_cap_dates = sorted(mcap)
        for j in range(1, len(bars)):
            d = bars[j]["date"][:10]
            if not (WINDOW[0].isoformat() <= d <= WINDOW[1].isoformat()):
                continue
            prev, cur = bars[j - 1]["adjClose"], bars[j]["adjClose"]
            if not prev or not cur:
                continue
            ret = cur / prev - 1.0
            if abs(ret) < MOVE_MIN:
                continue
            prior_day = bars[j - 1]["date"][:10]
            prior_caps = [c for c in sorted_cap_dates if c <= prior_day]
            prior_cap = mcap[prior_caps[-1]] if prior_caps else None
            if prior_cap is None or prior_cap < MCAP_MIN:
                continue
            if ipo_in_window and j < 6:
                continue
            nxt = bars[j + 1]["adjClose"] / cur - 1.0 if j + 1 < len(bars) and bars[j + 1].get("adjClose") else None
            reversal = nxt is not None and abs((1 + ret) * (1 + nxt) - 1.0) <= 0.02
            moves.append({"symbol": sym, "date": d, "prior_date": prior_day, "ret": round(ret, 5),
                          "prior_mcap": prior_cap, "flag_reversal": reversal, "flag_ge_100pct": abs(ret) >= 1.0})
        if i % 100 == 0:
            print(f"  {i}/{len(names)} names, {len(moves)} moves so far, {time.time() - t0:.0f}s", flush=True)

    # M&A flags: FMP's SEC-filing-based feed, paged back past the window start
    ma, page = [], 0
    while page < 200:
        rows = fmp(f"ma/page_{page}", "mergers-acquisitions-latest", page=page, limit=100) or []
        if not rows:
            break
        ma += rows
        if min(str(x.get("transactionDate") or "9999")[:10] for x in rows) < (WINDOW[0] - timedelta(days=30)).isoformat():
            break
        page += 1
    targets: dict[str, list[date]] = {}
    for x in ma:
        s = str(x.get("targetedSymbol") or "").upper()
        try:
            targets.setdefault(s, []).append(datetime.strptime(str(x.get("transactionDate"))[:10], "%Y-%m-%d").date())
        except ValueError:
            continue
    for m in moves:
        md = date.fromisoformat(m["date"])
        m["flag_ma"] = any(abs((td - md).days) <= 5 for td in targets.get(m["symbol"], []))

    OUT_POP.write_text(json.dumps(pop, indent=0))
    OUT_MOVES.write_text(json.dumps(sorted(moves, key=lambda m: (m["date"], m["symbol"])), indent=0))
    n_ok = sum(1 for p in pop if p["n_bars"] > 0)
    print(f"DONE in {time.time() - t0:.0f}s: population {len(pop)} ({n_ok} with bars), moves {len(moves)} "
          f"(M&A-flagged {sum(m['flag_ma'] for m in moves)}, reversal-flagged {sum(m['flag_reversal'] for m in moves)}, "
          f">=100% {sum(m['flag_ge_100pct'] for m in moves)}); M&A filings read {len(ma)}", flush=True)


if __name__ == "__main__":
    main()
