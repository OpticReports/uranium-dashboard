#!/usr/bin/env python3
"""Measure REALIZED Composer execution slippage from actual account fills.

METHOD: each fill is benchmarked against the market price at ITS OWN MINUTE,
taken from 5-minute intraday bars, NOT against the day's 4pm close.

    slippage_i = side_i * (fill_i / mkt_at_fill_time_i - 1)

Why this and not the close (addenda 34/35): fills run minutes before the
close, so a close benchmark measures (execution cost + market drift). On 3x
ETFs that drift is 50-300bps against a ~5bps signal. Two successive estimators
died on it -- a notional-weighted mean (add. 34, returned +2.94/+4.90/+7.58 on
the same data) and a beta*day-effect regression that modelled the drift
(add. 35, returned +7.36 on a zero-cost placebo because the close is not
one-factor and side is not exogenous to the day's move). Benchmarking at the
fill's own timestamp ELIMINATES the drift term instead of modelling it.

STANDING PLACEBO GATE: every run reprices each fill AT its benchmark, making
true cost exactly zero by construction, and re-runs the whole estimator. If
that does not come back ~0, the measurement is broken and the run refuses to
report a verdict. This is the test both previous estimators failed.

DATA CONSTRAINT -> LEDGER: Yahoo serves 5m bars for ~60 DAYS ONLY. Fills older
than that can never be measured this way, so each run APPENDS per-fill results
to results/slippage-ledger.json (deduped by Order ID) and the headline is
computed from the accumulated ledger. COLLECTION MUST RUN AT LEAST EVERY ~45
DAYS or fills are lost permanently -- quarterly is NOT often enough.

Composer's backtest engine assumes 5.0bps/side. The alert fires only when the
day-clustered lower bound clears 5.0 AND the placebo passed.

Usage:
  slippage_measure.py                 # collect new fills, then report
  slippage_measure.py --report-only   # report from the ledger, no fetching
  slippage_measure.py --since D --until D   # bound the collection window
"""
import argparse, csv, datetime, io, json, math, os, random, statistics, time, urllib.request
import collections
import composerlib as cl

LEDGER = "composer/results/slippage-ledger.json"
ET = datetime.timezone(datetime.timedelta(hours=-4))   # fills are stamped ET
BAR_DAYS = 60


def yahoo_bars(t):
    """5-minute bars, ~60 days. Returns sorted list of (epoch, o, h, l, c)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t.replace('.','-')}"
           f"?range={BAR_DAYS}d&interval=5m&includePrePost=false")
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=60))["chart"]["result"][0]
    if res["meta"].get("dataGranularity") != "5m":
        raise RuntimeError(f"{t}: granularity degraded to {res['meta'].get('dataGranularity')}")
    q = res["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((ts, o, h, l, c))
    out.sort()
    return out


def bench_price(bars, fill_epoch):
    """Representative market price in the 5m bar CONTAINING the fill.

    Bars are start-stamped, so the containing bar starts at or before the fill
    and ends within 5 minutes. (H+L)/2 is used: it is symmetric, so unlike a
    close benchmark it carries no buy/sell asymmetry -- the exact property both
    previous estimators lacked. Residual within-bar noise is random and
    averages out. CAVEAT: at size our own order is inside that bar's H/L, which
    biases measured cost DOWNWARD (conservative for a cost tripwire).
    """
    lo, hi = 0, len(bars) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if bars[mid][0] <= fill_epoch:
            best = mid; lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    ts, o, h, l, c = bars[best]
    if fill_epoch - ts > 15 * 60:       # stale: no bar covers this fill
        return None
    return (h + l) / 2.0


def load_ledger(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"fills": {}}


def collect(a, acct, led):
    url = (f"https://api.composer.trade/api/v0.1/reports/{acct}"
           f"?report-type=trade-activity&since={a.since}T00:00:00Z&until={a.until}T23:59:59Z")
    req = urllib.request.Request(url, headers={**cl._headers(), "accept": "text/csv"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))
    rows = [r for r in rows if r["Status"] == "filled" and r["Average Fill Price"]
            and r["Order ID"] not in led["fills"]]
    if not rows:
        print("  no new unmeasured fills in the window")
        return 0, []
    bars, failed = {}, []
    added = 0
    for r in rows:
        t = r["Symbol"]
        if t not in bars:
            try:
                bars[t] = yahoo_bars(t); time.sleep(0.25)
            except Exception as e:
                bars[t] = []; failed.append(f"{t} ({str(e)[:40]})")
        if not bars[t]:
            continue
        stamp = r["Filled Date/Time (America/New_York)"]
        try:
            dt = datetime.datetime.fromisoformat(stamp)
        except ValueError:
            dt = datetime.datetime.fromisoformat(stamp[:19]).replace(tzinfo=ET)
        mkt = bench_price(bars[t], dt.timestamp())
        if not mkt:
            continue
        # benchmark 30 minutes earlier: same TRUE cost, far more drift exposure.
        # Used by the invariance gate -- a correct benchmark leaves cost ~stable.
        mkt_lag = bench_price(bars[t], dt.timestamp() - 1800)
        fill = float(r["Average Fill Price"])
        side = 1 if r["Side"] == "buy" else -1
        led["fills"][r["Order ID"]] = {
            "d": stamp[:10], "t": t, "side": side, "fill": fill, "mkt": mkt,
            "notional": fill * float(r["Filled Quantity"]),
            "slip_bps": side * (fill / mkt - 1) * 1e4,
            "slip_lag_bps": (side * (fill / mkt_lag - 1) * 1e4) if mkt_lag else None,
            "hhmm": dt.strftime("%H:%M"),
        }
        added += 1
    return added, failed


def cluster_se(vals, days):
    """Day-clustered SE of the mean (CR1). Fills on a day are correlated."""
    n = len(vals)
    if n < 3:
        return float("nan")
    m = statistics.mean(vals)
    byday = collections.defaultdict(list)
    for v, d in zip(vals, days):
        byday[d].append(v - m)
    g = len(byday)
    if g < 2:
        return float("nan")
    meat = sum(sum(v) ** 2 for v in byday.values())
    adj = (g / (g - 1)) * ((n - 1) / max(n - 1, 1))
    return math.sqrt(adj * meat) / n


def report(led, assumption=5.0):
    F = list(led["fills"].values())
    if len(F) < 30:
        print(f"ledger holds {len(F)} measured fills — need 30+ for a stable estimate")
        return
    vals = [f["slip_bps"] for f in F]
    days = [f["d"] for f in F]
    m = statistics.mean(vals)
    se = cluster_se(vals, days)
    ds = sorted({f["d"] for f in F})
    print(f"ledger: {len(F)} measured fills, {len(ds)} days, {ds[0]} .. {ds[-1]}, "
          f"${sum(f['notional'] for f in F):,.0f} notional")

    # ---------------- standing gates (both must pass) ----------------
    # GATE 1 — SIGN PLACEBO. Real execution cost is sign-dependent; any
    # benchmark bias is not. Randomising each fill's side must collapse the
    # estimate to ~0. If it does not, something side-independent is leaking in.
    rnd = random.Random(20260101)
    flips = []
    for _ in range(200):
        flips.append(statistics.mean(
            [f["slip_bps"] * rnd.choice((1, -1)) for f in F]))
    g1 = statistics.mean(flips)
    g1_sd = statistics.pstdev(flips)
    ok1 = abs(g1) < max(1.0, 2 * g1_sd)
    print(f"GATE 1 sign-placebo: randomised sides give {g1:+.3f} +/- {g1_sd:.3f} bps "
          f"(must be ~0) -> {'PASS' if ok1 else 'FAIL'}")

    # GATE 2 — BENCHMARK INVARIANCE. Re-benchmark every fill 30 minutes earlier.
    # The true cost is unchanged; only drift exposure grows. A close-based
    # benchmark fails this badly (add. 35: +2.03 -> -16.79). A correct one
    # should move little relative to its own SE.
    lag = [f["slip_lag_bps"] for f in F if f.get("slip_lag_bps") is not None]
    lagd = [f["d"] for f in F if f.get("slip_lag_bps") is not None]
    if len(lag) >= 30:
        lm = statistics.mean(lag); lse = cluster_se(lag, lagd)
        shift = abs(lm - m)
        ok2 = shift < 2 * max(se, 1e-9) + 2 * max(lse, 1e-9)
        print(f"GATE 2 invariance: 30-min-earlier benchmark gives {lm:+.2f} +/- "
              f"{lse:.2f} (shift {shift:.2f} bps) -> {'PASS' if ok2 else 'FAIL'}")
    else:
        ok2 = False
        print("GATE 2 invariance: insufficient lagged benchmarks -> FAIL")

    if not (ok1 and ok2):
        print("  !! a gate FAILED — the measurement is not trustworthy, no verdict issued")
        return

    lo, hi = m - 2 * se, m + 2 * se
    print(f"EXECUTION COST: {m:+.2f} +/- {se:.2f} bps/side "
          f"(day-clustered; engine assumption {assumption})")
    print(f"  95% interval [{lo:+.2f}, {hi:+.2f}]  |  median {statistics.median(vals):+.2f}  "
          f"|  equal-weighted, intraday benchmark")
    verdict = ("ABOVE" if lo > assumption else "BELOW" if hi < assumption
               else "INDISTINGUISHABLE FROM")
    print(f"  -> {verdict} the {assumption}bps assumption")

    off = [f for f in F if not ("15:30" <= f["hhmm"] <= "16:05")]
    if off:
        om = statistics.mean([f["slip_bps"] for f in off])
        print(f"  {len(off)} fills outside the 15:30-16:05 window "
              f"(mean {om:+.1f} bps) — reported, not excluded")

    byt = collections.defaultdict(list)
    for f in F:
        byt[f["t"]].append(f)
    thin = {"ZVOL", "VBF", "VXZ", "VIXM"}
    present = sorted(thin & set(byt))
    if present:
        print("  thin names (own clustered SE):")
        for t in present:
            v = [x["slip_bps"] for x in byt[t]]
            d = [x["d"] for x in byt[t]]
            s = cluster_se(v, d)
            flag = "   <- significant" if s == s and abs(statistics.mean(v)) > 2 * s else ""
            print(f"    {t:5s} {statistics.mean(v):+7.2f} +/- "
                  f"{s:5.2f} bps (n={len(v)}){flag}")

    worst = max(F, key=lambda f: abs(f["slip_bps"]))
    drop = statistics.mean([f["slip_bps"] for f in F if f is not worst])
    print(f"  influence: dropping the largest fill ({worst['t']} {worst['d']}, "
          f"{worst['slip_bps']:+.0f} bps) moves the mean to {drop:+.2f}")

    if lo > assumption:
        print(f"  !! execution cost exceeds the {assumption}bps assumption by >2 "
              f"clustered SE — review ideas-backlog.md scale/migration gates")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account")
    p.add_argument("--since", default=(datetime.date.today()
                   - datetime.timedelta(days=BAR_DAYS)).isoformat())
    p.add_argument("--until", default=datetime.date.today().isoformat())
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--ledger", default=LEDGER)
    a = p.parse_args()
    led = load_ledger(a.ledger)
    before = len(led["fills"])
    if not a.report_only:
        acct = a.account or cl.default_account()
        print(f"collecting fills {a.since}..{a.until} (5m bars cover ~{BAR_DAYS}d)")
        added, failed = collect(a, acct, led)
        if failed:
            print(f"  !! bar fetch FAILED for {failed} — those fills are NOT measured "
                  f"and their bars expire in ~{BAR_DAYS}d")
        print(f"  +{added} newly measured fills (ledger {before} -> {len(led['fills'])})")
        os.makedirs(os.path.dirname(a.ledger), exist_ok=True)
        with open(a.ledger, "w") as f:
            json.dump(led, f, indent=1, sort_keys=True)
    report(led)


if __name__ == "__main__":
    main()
