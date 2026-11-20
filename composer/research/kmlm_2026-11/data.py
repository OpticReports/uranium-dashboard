"""Price data for the KMLM switcher study (PREREG.md). Read-only toward everything but its own cache.

fetch()      Yahoo full daily history (research/crash/yh_fetch's request) into this study's OWN cache
             ($KMLM_CACHE, default the session scratchpad): the shared crash cache other studies froze
             their numbers on is never rewritten.
panel_ab()   tiers A and B: every fund real where it exists; before its launch SVIX = (2 x SVXY's daily
             return) x 0.953 - 3.6 bp and ZVOL = -0.971 x VXZ's daily return, exactly the long panel's
             constructions (research/longrun/long_panel.py build_long_prices; add. 39, 47).
panel_c()    tier C: the repo's long panel as built (KMLM = the real fund <- RYMFX <- proxy), on the
             shared cache (ends 2026-11-04; tier C ends 2020-12-01).
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad"
CACHE = os.environ.get("KMLM_CACHE", f"{SCRATCH}/kmlm/yh")
TREE_TICKERS = ("QQQE VTV VOX TECL VOOG VOOV XLP TQQQ XLY FAS SPY SOXL SPXL LABU XLK KMLM SVIX SQQQ TLT UVXY "
                "ZVOL VXZ PULS").split()
EXTRA = "SVXY RYMFX BIL HYG IEF ^VIX ^VIX3M DX-Y.NYB ^IRX ^TNX".split()
KMLM_START, SVIX_START, ZVOL_START = "2020-12-02", "2022-03-30", "2023-04-19"


def _file(t):
    return f"{CACHE}/{t.replace('^', '_').replace('=', '_')}.json"


def fetch(t, force=False):
    fn = _file(t)
    if os.path.exists(fn) and not force:
        return json.load(open(fn))
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}"
           f"?period1=0&period2=4102444800&interval=1d&events=div%7Csplit")
    res = err = None
    for _ in range(4):
        try:
            rq = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            res = json.load(urllib.request.urlopen(rq, timeout=60))["chart"]["result"][0]
            break
        except Exception as ex:  # noqa: BLE001
            err = ex
            time.sleep(3)
    if res is None:
        raise RuntimeError(f"Yahoo fetch failed for {t}: {err}")
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    ac = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    out = {"dates": [], "close": [], "adjclose": [], "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    for i, x in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        out["dates"].append(dt.datetime.fromtimestamp(x, tz=dt.timezone.utc).date().isoformat())
        out["close"].append(float(c))
        out["adjclose"].append(float(ac[i] if ac and ac[i] is not None else c))
    os.makedirs(CACHE, exist_ok=True)
    json.dump(out, open(fn, "w"))
    return out


def series(t, end=None, field="adjclose"):
    o = fetch(t)
    return {d: v for d, v in zip(o["dates"], o[field]) if v and (end is None or d <= end)}


def rets(s):
    ds = sorted(s)
    return {ds[i]: s[ds[i]] / s[ds[i - 1]] - 1 for i in range(1, len(ds))}


def _chain_back(real, syn_rets, days):
    """levels on `days` before real's first date, chained backwards through syn_rets (keyed by the day a
    return ENDS on)"""
    out = dict(real)
    first = min(real)
    before = [d for d in days if d < first]
    nxt, lvl = first, real[first]
    for d in reversed(before):
        r = syn_rets.get(nxt)
        if r is None:
            break
        lvl = lvl / (1 + r)
        out[d] = lvl
        nxt = d
    return out


def panel_ab(end):
    """NOT for dates before 2018-02-28: SVXY was -1x until then (the long panel switches there); every span
    this study uses starts later"""
    P = {t: series(t, end) for t in TREE_TICKERS}
    svxy, vxz = series("SVXY", end), series("VXZ", end)
    days = sorted(svxy)
    P["SVIX"] = _chain_back(P["SVIX"], {d: 2 * r * 0.953 - 0.00036 for d, r in rets(svxy).items()}, days)
    P["ZVOL"] = _chain_back(P["ZVOL"], {d: -0.971 * r for d, r in rets(vxz).items()}, sorted(vxz))
    return P


def panel_c():
    sys.path.insert(0, os.path.join(HERE, "..", "longrun"))
    import long_panel as lp
    P, _ = lp.build_long_prices()
    return P


if __name__ == "__main__":
    force = "--force" in sys.argv
    for t in TREE_TICKERS + EXTRA:
        o = fetch(t, force)
        print(f"{t:10s} {len(o['dates']):6d} {o['dates'][0]} .. {o['dates'][-1]}  last {o['adjclose'][-1]:.4f}")
