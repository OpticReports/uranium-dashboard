#!/usr/bin/env python3
"""Measure REALIZED Composer execution slippage from actual account fills.

Pulls the trade-activity report (real fills: avg fill price, qty, side,
timestamp) and benchmarks each fill against the same day's official close --
the price the backtest engine credits. Signed slippage = side x (fill/close-1).
The fill-to-close gap includes ~7min of market drift (fills ~15:53 ET, close
16:00), which is direction-random and averages out across fills; the
notional-weighted mean is the systematic execution cost per side.

Context (addendum 14/14b): Composer's backtest engine ASSUMES 5.0bps/side.
First live measurement 2026-07-29: +1.91bps/side notional-weighted over 224
fills / $9.1M notional (equal-weighted -3.2bps, SE 3.4 -- indistinguishable
from zero). Re-run QUARTERLY as the book scales toward $1M: rising slippage
(>5bps sustained, or thin names ZVOL/VBF/VXZ/VIXM trending worse) is the
tripwire for the thin-ticker swaps / IBKR migration gate in
research/ideas-backlog.md.

Usage: slippage_measure.py [--since 2025-12-01] [--until today] [--account UUID]
Prices come from Yahoo daily closes (as-traded, split-corrected).
"""
import argparse, csv, datetime, io, json, math, time, urllib.request
import collections
import composerlib as cl

def yahoo_closes(t):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t.replace('.','-')}"
           "?period1=1609459200&period2=4102444800&interval=1d&events=div%2Csplit")
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=60))["chart"]["result"][0]
    assert res["meta"]["dataGranularity"] == "1d", f"{t}: granularity degraded"
    q = res["indicators"]["quote"][0]
    splits = (res.get("events") or {}).get("splits") or {}
    sp = sorted(({"d": datetime.datetime.fromtimestamp(int(v["date"]), tz=datetime.timezone.utc).date().isoformat(),
                  "f": float(v["numerator"])/float(v["denominator"])} for v in splits.values()), key=lambda x: x["d"])
    out = {}
    for i, ts in enumerate(res["timestamp"]):
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()
        if q["close"][i] is None: continue
        fut = 1.0
        for s in sp:
            if s["d"] > d: fut *= s["f"]
        out[d] = q["close"][i] * fut
    return out

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--account")
    p.add_argument("--since", default="2025-12-01")
    p.add_argument("--until", default=datetime.date.today().isoformat())
    a = p.parse_args()
    acct = a.account or cl.default_account()
    url = (f"https://api.composer.trade/api/v0.1/reports/{acct}"
           f"?report-type=trade-activity&since={a.since}T00:00:00Z&until={a.until}T23:59:59Z")
    req = urllib.request.Request(url, headers={**cl._headers(), "accept": "text/csv"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))

    px, samples, missing = {}, [], set()
    tot_signed = tot_notional = 0.0
    for r in rows:
        if r["Status"] != "filled" or not r["Average Fill Price"]: continue
        t = r["Symbol"]
        if t not in px:
            try: px[t] = yahoo_closes(t); time.sleep(0.3)
            except Exception: px[t] = {}
        day = r["Filled Date/Time (America/New_York)"][:10]
        close = px[t].get(day)
        if not close: missing.add(f"{t}@{day}"); continue
        fill = float(r["Average Fill Price"]); qty = float(r["Filled Quantity"])
        side = 1 if r["Side"] == "buy" else -1
        samples.append((side*(fill/close-1), fill*qty, t))
        tot_signed += side*(fill-close)*qty; tot_notional += fill*qty

    n = len(samples)
    if n < 20:
        print(f"only {n} fills in window — not enough for a stable estimate"); return
    w_mean = sum(s*w for s, w, _ in samples)/tot_notional
    eq = sum(s for s, _, _ in samples)/n
    se = math.sqrt(sum((s-eq)**2 for s, _, _ in samples)/(n-1)/n)
    print(f"window {a.since}..{a.until}: {n} fills, ${tot_notional:,.0f} notional "
          f"({len(missing)} skipped)")
    print(f"REALIZED SLIPPAGE: {w_mean*1e4:+.2f} bps/side notional-weighted "
          f"(equal {eq*1e4:+.2f} ± {se*1e4:.2f}; engine assumption 5.0)")
    byt = collections.defaultdict(list)
    for s, w, t in samples: byt[t].append((s, w))
    thin = {"ZVOL", "VBF", "VXZ", "VIXM"}
    for t in sorted(thin & set(byt)):
        ws = sum(w for _, w in byt[t])
        print(f"  thin-name {t}: {sum(s*w for s, w in byt[t])/ws*1e4:+.1f} bps/side "
              f"(n={len(byt[t])}, ${ws:,.0f})")
    if w_mean*1e4 > 5.0:
        print("  !! measured slippage above the 5bps engine assumption — "
              "review ideas-backlog.md scale/migration gates")

if __name__ == "__main__":
    main()
