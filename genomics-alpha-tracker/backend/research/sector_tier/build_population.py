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
$300M, excluding the first five trading days on or after the IPO date (by date).
Flags, never silent drops: M&A (the name is the target of an FMP M&A filing
within 5 calendar days), possible bad print (the next day reverses the move
to within 2%), and moves >= 100% (checked by hand in the report).

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.build_population
"""
from __future__ import annotations

import json
import re
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
ARTIFACT_MISMATCH = 0.5   # |price change vs cap change| beyond this is a data artifact, not a move
MCAP_MIN = 300e6
US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "NYSE American", "NYSEArca", "NYSE ARCA"}
# M&A days are TARGET days (counter-agent DA-2). Forms only the target files:
# its tender-offer response (SC14D9C on announcement, SC 14D9) and merger
# proxies. Acquirer-filed forms (SC TO-T/TO-C, 425) also list under the
# acquirer, so they are left out; headlines must NAME the company as the one
# being bought. DEFA14A is left out: it is also every proxy season's filler.
MA_FORMS = {"SC14D9C", "SC 14D9", "PREM14A", "DEFM14A", "PREMM14A", "DEFM14C"}
_GENERIC = {"therapeutics", "pharmaceuticals", "pharmaceutical", "pharma", "biosciences", "bioscience",
            "biotherapeutics", "biopharmaceuticals", "biopharma", "biotech", "biotechnology", "bio", "medical",
            "health", "healthcare", "holdings", "group", "technologies", "technology", "sciences", "labs",
            "laboratories", "diagnostics", "oncology", "genomics", "medicines", "biologics", "the", "corp", "inc"}
# Headlines that use deal words without a deal on the name: fund 13F lines
# ("... Acquires Shares of"), and speculation ("takeover target", "next buyout").
NOT_MA_HEADLINE = re.compile(
    r"(?i)\b(acquires?|buys|sells|purchases?) (new |additional )?(\$?[\d,.]+[kmb]? )?(shares|stake|position)|"
    r"(takeover|buyout|acquisition) (target|speculation|candidate|chatter|appeal)|next (buyout|takeover)|"
    r"shares (acquired|sold|bought|purchased) by|"
    r"deal for .{0,40}\b(to (sell|distribute|market|commercialize|offer|supply)|drug|asset|program|candidate|rights)\b|"
    r"'s [\w\s-]{0,40}\b(business|unit|division|assets?|portfolio|product lines?|lab products|segment|franchise|brand)\b")


def name_core(name: str) -> str:
    """'Verve Therapeutics, Inc.' -> 'Verve'; 'Day One Biopharmaceuticals' -> 'Day One'."""
    words = D.clean_company_name(name or "").split()
    while len(words) > 1 and words[-1].lower() in _GENERIC:
        words.pop()
    return " ".join(words)


def target_headline(title: str, symbol: str, name: str) -> bool:
    """A deal headline that names this company as the one being bought."""
    if not title or NOT_MA_HEADLINE.search(title):
        return False
    core = name_core(name)
    n = "(?:" + "|".join(re.escape(x) for x in {core, symbol} if x and len(x) >= 2) + ")"
    pats = [
        rf"\b(to acquire|acquires|acquiring|to buy|buys|buyout of|takeover of|bid for|offer for|deal for|"
        rf"to merge with|merger with|acquisition of|sale of|merger of|purchase of)\b.{{0,40}}\b{n}\b",
        rf"\b{n}\b.{{0,80}}\b(to be acquired|agrees? to be (acquired|bought)|acquired by|to be bought|sold to|"
        rf"merger agreement|(buyout|takeover) (offer|bid|deal|talks?|battle|approach|proposal)|in talks to be acquired|"
        rf"go[- ]private|take[- ]private|tender offer)\b",
        rf"\b{n}\b.{{0,30}}\b(buyout|takeover)\b",
        rf"\bwhether\b.{{0,40}}\b{n}\b.{{0,80}}\b(fair|obtaining)\b",
    ]
    return any(re.search(x, title, re.I) for x in pats)


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


def is_instrument(symbol: str, name: str, known: set[str]) -> bool:
    """FMP's delisted list carries warrants, units and rights under the issuer's
    own name (WGSWW 'GeneDx Holdings Corp.'): a name that says so, or a symbol
    that is a listed symbol plus a W/WW/WS/U/R suffix."""
    if D.is_instrument_row(name or "") or re.search(r"(?i)\brights?\b", name or ""):
        return True
    if len(symbol) == 5 and symbol.isalpha() and symbol[-1] in "WRUZVP":
        return True   # Nasdaq fifth-letter instrument codes (warrant, right, unit, misc, when-issued, preferred)
    return any(symbol.endswith(suf) and symbol[:-len(suf)] in known
               for suf in ("-WT", "-WS", "-U", "-P", ".WS", ".U", "WW", "WS", "W", "U", "R", "P", "V", "Z"))


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
    kept_delisted = dropped_instruments = 0
    known = set(names) | {r["symbol"] for r in delisted}
    for r in delisted:
        if r["symbol"] in names:
            continue
        if is_instrument(r["symbol"], r["screener_name"], known):
            dropped_instruments += 1
            continue
        prof = (fmp(f"profile/{r['symbol']}", "profile", symbol=r["symbol"]) or [None])
        p = prof[0] if prof else None
        sector = (p or {}).get("sector")
        if sector == "Healthcare" or D.genomics_tags_for([r["screener_name"]]):
            names[r["symbol"]] = r
            kept_delisted += 1
    print(f"delisted names kept (healthcare or genomics-named): {kept_delisted}; "
          f"warrants/units/rights dropped: {dropped_instruments}", flush=True)

    pop, moves = [], []
    closes: dict[str, dict[str, float]] = {}
    ciks: dict[str, str | None] = {}
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
        # IPO exclusion by DATE (the first five trading days on or after the IPO date),
        # for any IPO from two weeks before the bar history starts: bars begin at
        # HIST_FROM for older names, so a bar index is not days since IPO, and an
        # uplisting can have bars before its FMP ipoDate.
        ipo_skip: set[str] = set()
        if ipo and ipo >= (HIST_FROM - timedelta(days=14)).isoformat():
            k = next((j for j, b in enumerate(bars) if b["date"][:10] >= ipo), None)
            if k is not None:
                ipo_skip = {b["date"][:10] for b in bars[k:k + 5]}   # amendment 7: first five on or after
        if bars and bars[0]["date"][:10] > (HIST_FROM + timedelta(days=7)).isoformat():
            # listing began inside the history (when-issued trading, spin-offs, uplistings)
            ipo_skip |= {b["date"][:10] for b in bars[:5]}
        closes[sym] = {b["date"][:10]: float(b["adjClose"]) for b in bars}
        ciks[sym] = p.get("cik")
        sorted_cap_dates = sorted(mcap)
        for j in range(1, len(bars)):
            d = bars[j]["date"][:10]
            if not (WINDOW[0].isoformat() <= d <= WINDOW[1].isoformat()):
                continue
            prev, cur = bars[j - 1]["adjClose"], bars[j]["adjClose"]
            if not prev or not cur:
                continue
            ret = cur / prev - 1.0
            if round(abs(ret), 9) < MOVE_MIN:   # an exact 20.00% is 0.19999... in floating point
                continue
            prior_day = bars[j - 1]["date"][:10]
            prior_caps = [c for c in sorted_cap_dates if c <= prior_day]
            prior_cap = mcap[prior_caps[-1]] if prior_caps else None
            if prior_cap is None or prior_cap < MCAP_MIN:
                continue
            if d in ipo_skip:
                continue
            nxt = bars[j + 1]["adjClose"] / cur - 1.0 if j + 1 < len(bars) and bars[j + 1].get("adjClose") else None
            reversal = nxt is not None and abs((1 + ret) * (1 + nxt) - 1.0) <= 0.02
            # Price vs market cap: FMP's cap moves with the price on a real move; an
            # adjustment-factor break (ESPR +15,949% with the cap +1%) does not.
            cap_today = mcap.get(d)
            mismatch = (abs((1 + ret) / (cap_today / prior_cap) - 1.0)
                        if cap_today and prior_caps and prior_caps[-1] == prior_day else None)
            moves.append({"symbol": sym, "date": d, "prior_date": prior_day, "ret": round(ret, 5),
                          "prior_mcap": prior_cap, "flag_reversal": reversal, "flag_ge_100pct": abs(ret) >= 1.0,
                          "price_cap_mismatch": round(mismatch, 4) if mismatch is not None else None,
                          "flag_artifact": bool(mismatch is not None and mismatch > ARTIFACT_MISMATCH)})
        if i % 100 == 0:
            print(f"  {i}/{len(names)} names, {len(moves)} moves so far, {time.time() - t0:.0f}s", flush=True)

    # Ticker changes FMP backfilled under the new symbol (GLTO -> DMRA, same CIK,
    # identical closes): the delisted old symbol duplicates the census name.
    by_cik: dict[str, list[str]] = {}
    for sym, c in ciks.items():
        if c:
            by_cik.setdefault(str(c), []).append(sym)
    src = {x["symbol"]: x["source"] for x in pop}
    dup: set[str] = set()
    dup_days: set[tuple[str, str]] = set()
    for group in by_cik.values():
        for old_sym in [g for g in group if src[g] == "delisted"]:
            for new_sym in [g for g in group if g != old_sym and src[g] != "delisted"]:
                common = set(closes[old_sym]) & set(closes[new_sym])
                same = sum(1 for t in common if abs(closes[old_sym][t] - closes[new_sym][t]) <= 1e-3 * max(1e-9, closes[new_sym][t]))
                if len(common) >= 20 and same >= 0.9 * len(common):
                    if len(common) >= 0.9 * len(closes[old_sym]):
                        dup.add(old_sym)                              # whole history duplicated
                    else:
                        dup_days |= {(old_sym, t) for t in common}    # only the shared stretch
    pop = [x for x in pop if x["symbol"] not in dup]
    moves = [m for m in moves if m["symbol"] not in dup and (m["symbol"], m["date"]) not in dup_days]
    print(f"ticker-change duplicates dropped: {sorted(dup)}; partial overlaps trimmed: "
          f"{sorted({s for s, _ in dup_days})}", flush=True)

    # M&A flags. FMP's mergers-acquisitions feed (kept below as `ma_s4`) is
    # S-4 registrations only: stock deals, dated weeks after announcement -
    # it flagged 0 of the first run's 781 moves. Cash tender offers, the usual
    # way a biotech is bought, never appear in it. So each move also reads
    # (1) the SEC filings filed by or about the name within 5 calendar days:
    # tender-offer and merger forms, and (2) FMP stock-news headlines from the
    # day before to the day after (deal announcements, "takeover", and the
    # law-firm "is the sale fair" alerts that follow nearly every deal).
    # Evidence is kept on each move for the hand check.
    for m in moves:
        md = date.fromisoformat(m["date"])
        fil = fmp(f"filings/{m['symbol']}_{m['date']}", "sec-filings-search/symbol", symbol=m["symbol"],
                  **{"from": (md - timedelta(days=5)).isoformat(), "to": (md + timedelta(days=5)).isoformat(),
                     "limit": 100}) or []
        news = fmp(f"news/{m['symbol']}_{m['date']}", "news/stock", symbols=m["symbol"],
                   **{"from": (md - timedelta(days=1)).isoformat(), "to": (md + timedelta(days=1)).isoformat(),
                      "limit": 50}) or []
        m["ma_forms"] = sorted({str(f.get("formType") or "").replace("/A", "").strip() for f in fil
                                if str(f.get("formType") or "").replace("/A", "").strip() in MA_FORMS})
        nm = next((x["name"] for x in pop if x["symbol"] == m["symbol"]), "")
        m["ma_headlines"] = sorted({str(n.get("title") or "")[:160] for n in news
                                    if target_headline(str(n.get("title") or ""), m["symbol"], nm)})[:5]

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
        m["ma_s4"] = any(abs((td - md).days) <= 5 for td in targets.get(m["symbol"], []))
        m["flag_ma"] = bool(m["ma_s4"] or m["ma_forms"] or m["ma_headlines"])

    OUT_POP.write_text(json.dumps(pop, indent=0))
    OUT_MOVES.write_text(json.dumps(sorted(moves, key=lambda m: (m["date"], m["symbol"])), indent=0))
    n_ok = sum(1 for p in pop if p["n_bars"] > 0)
    print(f"DONE in {time.time() - t0:.0f}s: population {len(pop)} ({n_ok} with bars), moves {len(moves)} "
          f"(M&A-flagged {sum(m['flag_ma'] for m in moves)}, reversal-flagged {sum(m['flag_reversal'] for m in moves)}, "
          f">=100% {sum(m['flag_ge_100pct'] for m in moves)}, artifacts {sum(m['flag_artifact'] for m in moves)}); "
          f"M&A filings read {len(ma)}", flush=True)


if __name__ == "__main__":
    main()
