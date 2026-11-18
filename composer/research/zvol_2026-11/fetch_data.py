"""Data layer for the ZVOL / volatility-harvester study (2026-11-18). Read-only fetches; caches raw
responses under CACHE (not committed). Sources: Yahoo chart API (prices, adjusted closes, distributions,
CBOE index levels), Cboe per-contract VX futures settlement CSVs (cdn.cboe.com).
Usage: python3 fetch_data.py CACHE_DIR"""
import csv, datetime as dt, io, json, os, sys, time, urllib.request

UA = {"user-agent": "Mozilla/5.0"}
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1=0&period2=9999999999&interval=1d&events=div%2Csplit"
TICKERS = ["ZVOL", "VXZ", "VIXM", "VIXY", "UVXY", "SVXY", "SVIX", "PULS", "BIL", "SPY", "QQQ", "HYG", "IEF", "TLT",
           "TQQQ", "TECL", "SOXL", "SQQQ", "^VIX", "^VIX3M", "^VIX9D", "^VIX6M", "^VVIX", "^SKEW", "^GSPC"]


def get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {err!r}")


def yahoo(t, cache):
    p = os.path.join(cache, "yahoo_" + t.replace("^", "_") + ".json")
    if not os.path.exists(p):
        open(p, "wb").write(get(YAHOO.format(t=t.replace("^", "%5E"))))
    res = json.load(open(p))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = ((res["indicators"].get("adjclose") or [{}])[0] or {}).get("adjclose") or [None] * len(res["timestamp"])
    rows = {}
    for i, ts in enumerate(res["timestamp"]):
        if q["close"][i] is None:
            continue
        d = dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc).date().isoformat()
        rows[d] = {"close": float(q["close"][i]), "adj": float(adj[i]) if adj[i] is not None else None,
                   "volume": q["volume"][i]}
    ev = res.get("events") or {}
    divs = sorted((dt.datetime.fromtimestamp(int(v["date"]), tz=dt.timezone.utc).date().isoformat(), float(v["amount"]))
                  for v in (ev.get("dividends") or {}).values())
    splits = sorted((dt.datetime.fromtimestamp(int(v["date"]), tz=dt.timezone.utc).date().isoformat(),
                     v.get("numerator"), v.get("denominator")) for v in (ev.get("splits") or {}).values())
    return {"rows": rows, "divs": divs, "splits": splits}


def third_friday(y, m):
    d = dt.date(y, m, 15)
    while d.weekday() != 4:
        d += dt.timedelta(days=1)
    return d


def vx_expiry(y, m):
    """final settlement date of the VX contract named for month (y, m): 30 days before the third Friday of
    the following month (a Wednesday, moved a day earlier on a holiday - tried by the caller)"""
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return third_friday(ny, nm) - dt.timedelta(days=30)


def vx_contract(y, m, cache):
    """{date: settle} for one monthly VX contract, or None. Cboe names the file by settlement date."""
    base = vx_expiry(y, m)
    p = os.path.join(cache, f"vx_{y}-{m:02d}.csv")
    if not os.path.exists(p) and y <= 2012:
        open(p, "w").write("")                         # Cboe serves these only from the archive
    if not os.path.exists(p):
        raw = None
        for off in (0, -1, 1, -2):
            d = base + dt.timedelta(days=off)
            try:
                raw = get(f"https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_{d.isoformat()}.csv", tries=2)
                if raw.startswith(b"Trade Date"):
                    break
                raw = None
            except Exception:  # noqa: BLE001
                raw = None
        if raw is None:
            open(p, "w").write("")
        else:
            open(p, "wb").write(raw)
    out = {}
    # 2013-14 contracts: the per-contract file starts in 2013, the archive holds their 2012-13 rows.
    # Archive first, so the current file wins where both have a date.
    for txt in ((vx_archive(y, m, cache) if y <= 2014 else ""), open(p).read()):
        for r in csv.DictReader(io.StringIO(txt)):
            try:
                s = float(r["Settle"])
            except (KeyError, ValueError, TypeError):
                continue
            d = (r.get("Trade Date") or "").strip()
            if "/" in d:                                   # archive files: MM/DD/YYYY
                mm, dd, yy = d.split("/")
                d = f"{yy}-{int(mm):02d}-{int(dd):02d}"
            if s > 0 and d:
                out[d] = s / 10.0 if d < "2007-03-26" else s      # quoted x10 before the 2007-03-26 rescale
    if not out:
        return None
    # an expired contract's last row is its settlement day; one still trading on the study date keeps
    # its scheduled expiry (verifier A: max(out) shortened the last roll period)
    return {"settle": out, "expiry": max(max(out), base.isoformat()) if base.isoformat() > max(out) and max(out) >= "2026-11-10" else max(out)}


def vx_archive(y, m, cache):
    """Cboe's pre-2013 archive, one file per contract: CFE_<month code><yy>_VX.csv"""
    p = os.path.join(cache, f"vxarch_{y}-{m:02d}.csv")
    if not os.path.exists(p):
        code = "FGHJKMNQUVXZ"[m - 1]
        try:
            raw = get(f"https://cdn.cboe.com/resources/futures/archive/volume-and-price/CFE_{code}{y % 100:02d}_VX.csv", tries=2)
            raw = raw if raw.startswith(b"Trade Date") else b""
        except Exception:  # noqa: BLE001
            raw = b""
        open(p, "wb").write(raw)
    return open(p).read()


if __name__ == "__main__":
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    for t in TICKERS:
        y = yahoo(t, cache)
        ds = sorted(y["rows"])
        print(f"{t:7s} {ds[0]} .. {ds[-1]} n={len(ds)} divs={len(y['divs'])} splits={len(y['splits'])}")
    n = 0
    for yy in range(2004, 2028):
        for mm in range(1, 13):
            c = vx_contract(yy, mm, cache)
            if c:
                n += 1
    print("VX monthly contracts fetched:", n)
