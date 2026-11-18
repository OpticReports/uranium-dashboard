"""Data layer for the B.5 overlay study. Fetches raw series (cached, not committed) and builds panel.pkl.

Sources: Yahoo v8 chart (adjclose, close, volume), FRED fredgraph.csv, multpl.com Shiller PE table.
KMLM 2022-12-28 distribution corrected per barbell-lab/config/data.yaml. Returns chained, never levels.
Run: python prep.py   (set B5_REFRESH=1 to refetch)
"""
import hashlib, io, json, os, pickle, re, sys, time
import httpx, numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
STUDY = os.path.dirname(HERE)
LAB = os.path.dirname(os.path.dirname(STUDY))
CACHE = os.environ.get("B5_CACHE", os.path.join(STUDY, "_cache"))
os.makedirs(CACHE, exist_ok=True)
DATA = yaml.safe_load(open(f"{LAB}/config/data.yaml"))
END = pd.Timestamp("2026-11-17")
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-script"}

YAHOO = ["AVUV", "AVDV", "PHYS", "KMLM", "AVEM", "QUAL", "TAIL", "BIL", "SPY", "GLD", "DFSVX", "DISVX",
         "DFEMX", "ASFYX", "RYMFX", "IWN", "SCZ", "EFA", "EEM", "HYG", "IEF", "^VIX", "^VIX3M", "^SP500TR"]
FRED = ["DTB3", "BAA10Y", "T10Y3M", "DFII10", "DTWEXBGS", "UNRATE"]


def _get(url, params=None):
    err = None
    for a in range(5):
        try:
            r = httpx.get(url, params=params, headers=H, timeout=60, follow_redirects=True)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa
            err = e; time.sleep(2 ** a)
    raise RuntimeError(f"fetch failed {url}: {err!r}")


def _cached(name, fn):
    p = os.path.join(CACHE, name)
    if os.path.exists(p) and not os.environ.get("B5_REFRESH"):
        return open(p, "rb").read()
    b = fn()
    open(p, "wb").write(b)
    return b


def yahoo(sym):
    def f():
        return _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                    {"period1": int(pd.Timestamp("1993-01-01", tz="UTC").timestamp()),
                     "period2": int(pd.Timestamp("2026-11-19", tz="UTC").timestamp()),
                     "interval": "1d", "events": "div,split"}).content
    raw = _cached(f"yahoo_{sym.replace('^', '_')}.json", f)
    res = json.loads(raw)["chart"]["result"][0]
    idx = (pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
           .tz_localize(None).normalize())
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({"adj": res["indicators"]["adjclose"][0]["adjclose"], "raw": q["close"],
                       "volume": q["volume"]}, index=idx)
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["adj", "raw"])
    return df.loc[df.index <= END], hashlib.sha256(raw).hexdigest()[:12]


def fred(sid):
    raw = _cached(f"fred_{sid}.csv", lambda: _get("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": sid}).content)
    df = pd.read_csv(io.BytesIO(raw))
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0])).dropna()
    return s.loc[s.index <= END], hashlib.sha256(raw).hexdigest()[:12]


def pput():
    raw = _cached("cboe_PPUT.csv", lambda: _get("https://cdn.cboe.com/api/global/us_indices/daily_prices/PPUT_History.csv").content)
    df = pd.read_csv(io.BytesIO(raw))
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=pd.to_datetime(df.iloc[:, 0], format="%m/%d/%Y")).dropna()
    return s.loc[s.index <= END], hashlib.sha256(raw).hexdigest()[:12]


def cape():
    raw = _cached("multpl_cape.html", lambda: _get("https://www.multpl.com/shiller-pe/table/by-month").content)
    rows = re.findall(r"<td[^>]*>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td[^>]*>\s*(?:&#x2002;|\s|<[^>]+>)*([\d.,]+)",
                      raw.decode("utf8", "ignore"))
    s = pd.Series({pd.Timestamp(d): float(v.replace(",", "")) for d, v in rows}).sort_index()
    if len(s) < 1500:
        raise RuntimeError(f"CAPE parse returned only {len(s)} rows")
    return s, hashlib.sha256(raw).hexdigest()[:12]


def kmlm_fix(df):
    for c in DATA["distribution_corrections"]:
        if c["ticker"] != "KMLM":
            continue
        ex = pd.Timestamp(str(c["ex_date"])); before = df.index < ex
        prev = float(df.loc[before, "raw"].iloc[-1])
        f = (1 - c["true_amount"] / prev) / (1 - c["vendor_amount"] / prev)
        df = df.copy(); df.loc[before, "adj"] *= f
        return df, f
    raise RuntimeError("no KMLM correction found")


def main():
    px, hashes = {}, {}
    for s in YAHOO:
        px[s], hashes[s] = yahoo(s)
    px["KMLM"], kf = kmlm_fix(px["KMLM"])
    cal = px["SPY"].index                                   # NYSE trading days
    adj = pd.DataFrame({s: px[s]["adj"] for s in YAHOO}).reindex(cal)
    vol = pd.DataFrame({s: px[s]["volume"] for s in YAHOO}).reindex(cal)
    # returns over consecutive OBSERVED closes; a missing day for a symbol gives NaN that day and a
    # multi-day return on the next observed day (no forward-fill of prices into returns).
    ret = pd.DataFrame({s: px[s]["adj"].pct_change() for s in YAHOO}).reindex(cal)
    missing = {s: int(adj[s].loc[px[s].index.min():].isna().sum()) for s in YAHOO}
    fr = {}
    for sid in FRED:
        fr[sid], hashes[sid] = fred(sid)
    cp, hashes["CAPE"] = cape()
    pp, hashes["PPUT"] = pput()
    ret["PPUT"] = pp.pct_change().reindex(cal)
    first = {s: str(px[s].index.min().date()) for s in YAHOO}
    last = {s: str(px[s].index.max().date()) for s in YAHOO}
    big = {s: [(str(d.date()), round(float(v), 4)) for d, v in ret[s].dropna().abs().nlargest(3).items()]
           for s in YAHOO if s not in ("^VIX", "^VIX3M")}
    panel = dict(cal=cal, adj=adj, vol=vol, ret=ret, fred=fr, cape=cp, end=END,
                 meta=dict(first=first, last=last, missing_days=missing, kmlm_factor=kf, hashes=hashes,
                           largest_moves=big, fred_last={k: str(v.index.max().date()) for k, v in fr.items()},
                           cape_first=str(cp.index.min().date()), cape_last=str(cp.index.max().date()),
                           cape_last_value=float(cp.iloc[-1]), n_days=len(cal)))
    pickle.dump(panel, open(os.path.join(CACHE, "panel.pkl"), "wb"))
    json.dump(panel["meta"], open(os.path.join(STUDY, "data_meta.json"), "w"), indent=1)
    print(json.dumps({k: panel["meta"][k] for k in ["first", "last", "missing_days", "kmlm_factor", "fred_last",
                                                    "cape_first", "cape_last", "cape_last_value"]}, indent=1))
    print("largest moves:", json.dumps(big)[:3000])


if __name__ == "__main__":
    main()
