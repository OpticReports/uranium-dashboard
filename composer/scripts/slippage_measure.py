#!/usr/bin/env python3
"""Measure REALIZED Composer execution slippage from actual account fills.

Pulls the trade-activity report (real fills: avg fill price, qty, side,
timestamp) and benchmarks each fill against the same day's official close.

THE IDENTIFICATION PROBLEM (why the naive estimator was wrong, add. 34):
fills run ~15:53 ET, the close is 16:00, so

    fill/close - 1  =  (7-minute market drift)  +  (execution cost)

and on 3x ETFs the drift term is 50-300bps -- orders of magnitude larger
than the cost we want. Notional-weighting concentrated that noise in a few
large fills, so the statistic returned +2.94 / +4.90 / +7.58 bps on the SAME
data depending on which fills were in the window. It was not measuring
execution.

THE FIX -- the two terms have different signatures, so they separate:
  * drift hits buys and sells in the SAME direction, and scales with the
    instrument's market beta (TQQQ drifts ~3x SPY);
  * execution cost is SIGN-dependent: a buy pays up, a sell receives less.
So fit, over all fills jointly,

    fill/close - 1  =  beta_i * m_day  +  c * side_i  +  e

with one free drift term m_day per fill-day (absorbing that day's move) and
a single cost coefficient c. Betas are estimated from daily returns vs SPY,
not hardcoded. c is the execution cost per side; its standard error comes
from the regression residuals. c is identified by days carrying BOTH buys
and sells (a same-side-only day is fully absorbed by its own m_day), so the
report states how many fills actually identify it.

*** STATUS: NOT A TRIPWIRE. ADVISORY ONLY. (addendum 35) ***
Counter-agent review FAILED this estimator for alerting. The algebra is exact
(verified to 1e-19 against a dense solve), and the noise-concentration defect
of the old statistic is genuinely fixed -- but the drift model is misspecified
and LEAKS drift into c:
  * beta_i * m_day absorbs only ~50% of drift variance; the last minutes are
    not one-factor (semis, the vol complex and rates move separately from SPY);
  * side is NOT exogenous -- Composer picks side conditional on the same day's
    move -- so the surviving drift does not cancel between buys and sells;
  * invariance test: re-benchmarking the SAME fills (identical true cost)
    against the PRIOR day's close moves c from +2.03 to -16.79 bps. A correct
    drift model would leave c unchanged.
  * on a zero-cost placebo (fills repriced at real intraday market prices at
    their own fill minute) the counter-agent measured c = +7.36 +/- 2.86 where
    0.00 is correct.
The leakage is the same order as the 5bps effect being policed, so NEITHER this
nor the legacy statistic may fire an alert. Both are printed as advisory.
THE REAL FIX is to benchmark each fill against the intraday price at its own
timestamp, eliminating the drift term rather than modelling it. Until then this
script reports; it does not decide. Full P0 list in results.md addendum 35.

Usage: slippage_measure.py [--since 2025-12-01] [--until today] [--account UUID]
Prices come from Yahoo daily closes (as-traded, split-corrected).
"""
import argparse, csv, datetime, io, json, math, time, urllib.request
import collections
import composerlib as cl

def yahoo_adjusted(t):
    """Split-ADJUSTED daily closes — correct series for estimating betas.
    yahoo_closes() deliberately returns AS-TRADED prices (right for comparing
    against fill prices, wrong for returns: a reverse split shows up as a
    +437% day and corrupts the beta, add. 35 finding 8)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{t.replace('.','-')}"
           "?period1=1609459200&period2=4102444800&interval=1d")
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=60))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = {}
    for i, ts in enumerate(res["timestamp"]):
        if q["close"][i] is None: continue
        d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date().isoformat()
        out[d] = q["close"][i]
    return out


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


def estimate_betas(px, spy, tickers):
    """Market beta of each ticker from overlapping daily returns vs SPY.

    Scales the per-day drift term. A missing/short series falls back to 1.0,
    which under-removes drift for levered names rather than inventing an
    exposure.
    """
    sd = sorted(spy)
    sr = {b: spy[b] / spy[a] - 1 for a, b in zip(sd, sd[1:]) if spy[a]}
    out = {}
    for t in tickers:
        q = px.get(t) or {}
        d = sorted(q)
        sxy = sxx = 0.0
        n = 0
        for aa, bb in zip(d, d[1:]):
            if bb in sr and q[aa]:
                x = sr[bb]; y = q[bb] / q[aa] - 1
                sxy += x * y; sxx += x * x; n += 1
        out[t] = (sxy / sxx) if (n >= 60 and sxx > 0) else 1.0
    return out


def _within(samples, betas, cost_mask):
    """Profile out the per-day drift terms analytically (no numpy).

    Model: raw_i = beta_i * m_day + c * z_i + e_i, with one free m per day.
    For any c the LS m_day is sum(beta*(raw - c*z))/sum(beta^2) over that day,
    so substituting back is exactly a beta-weighted within-day transform:
        v~_i = v_i - beta_i * (sum_j beta_j v_j / sum_j beta_j^2)
    Then c = sum(raw~ * z~) / sum(z~^2). Returns (c, se, dof, n_days).
    """
    byday = collections.defaultdict(list)
    for i, (raw, side, day, t, _) in enumerate(samples):
        byday[day].append(i)
    rt, zt = {}, {}
    for day, ids in byday.items():
        bb = sum(betas.get(samples[i][3], 1.0) ** 2 for i in ids)
        if bb <= 0:
            continue
        pr = sum(betas.get(samples[i][3], 1.0) * samples[i][0] for i in ids) / bb
        pz = sum(betas.get(samples[i][3], 1.0) * cost_mask(samples[i]) for i in ids) / bb
        for i in ids:
            b = betas.get(samples[i][3], 1.0)
            rt[i] = samples[i][0] - b * pr
            zt[i] = cost_mask(samples[i]) - b * pz
    szz = sum(v * v for v in zt.values())
    if szz <= 0:
        return None
    c = sum(rt[i] * zt[i] for i in rt) / szz
    ssr = sum((rt[i] - c * zt[i]) ** 2 for i in rt)
    dof = len(rt) - len(byday) - 1
    if dof <= 0:
        return None
    se = math.sqrt((ssr / dof) / szz)
    return c, se, dof, len(byday)


def fit_cost(samples, betas):
    """Execution cost per side, with the 7-minute drift removed.

    Returns (c, se, n_used, n_identifying, n_mixed_days). c is identified by
    days carrying BOTH buys and sells: a same-side-only day is absorbed
    entirely by its own drift term.
    """
    out = _within(samples, betas, lambda s: s[1])
    if not out:
        return None
    c, se, _, _ = out
    sides = collections.defaultdict(set)
    for _, side, day, _, _ in samples:
        sides[day].add(side)
    mixed = {d for d, v in sides.items() if len(v) > 1}
    n_ident = sum(1 for _, _, d, _, _ in samples if d in mixed)
    return c, se, len(samples), n_ident, len(mixed)


def group_cost(samples, betas, keep):
    """Same model with the cost term restricted to `keep` tickers; all other
    fills still contribute their day's drift term."""
    if not any(t in keep for _, _, _, t, _ in samples):
        return None
    out = _within(samples, betas, lambda s: s[1] if s[3] in keep else 0.0)
    if not out:
        return None
    c, se, _, _ = out
    return c, se, sum(1 for _, _, _, t, _ in samples if t in keep)


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
    tot_notional = 0.0
    legacy_signed = 0.0
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
        notional = fill * qty
        samples.append((fill / close - 1, side, day, t, notional))
        legacy_signed += side * (fill / close - 1) * notional
        tot_notional += notional

    n = len(samples)
    print(f"window {a.since}..{a.until}: {n} fills, ${tot_notional:,.0f} notional "
          f"({len(missing)} skipped)")
    if n < 30:
        print(f"only {n} fills — not enough for a stable estimate"); return

    try:
        spy = yahoo_adjusted("SPY")
    except Exception as e:
        print(f"  !! SPY fetch FAILED ({e}) — every beta falls back to 1.0 and the "
              f"drift model degenerates. Figures below are not usable."); spy = {}
    adj, bad = {}, []
    for t in {t for _, _, _, t, _ in samples}:
        try: adj[t] = yahoo_adjusted(t); time.sleep(0.2)
        except Exception: adj[t] = {}; bad.append(t)
    if bad:
        print(f"  !! adjusted-series fetch failed for {sorted(bad)} — their betas "
              f"fall back to 1.0")
    betas = estimate_betas(adj, spy, {t for _, _, _, t, _ in samples})

    fit = fit_cost(samples, betas)
    if not fit:
        print("estimator could not be identified on this window"); return
    c, se, n_used, n_ident, n_mixed_days = fit
    c_bps, se_bps = c * 1e4, se * 1e4

    print(f"EXECUTION COST: {c_bps:+.2f} +/- {se_bps:.2f} bps/side "
          f"(drift-separated; engine assumption 5.0)")
    lo, hi = c_bps - 2 * se_bps, c_bps + 2 * se_bps
    print(f"  95% interval [{lo:+.2f}, {hi:+.2f}] bps  |  "
          f"{n_ident}/{n_used} fills across {n_mixed_days} mixed-side days identify it")
    verdict = ("ABOVE" if lo > 5.0 else "BELOW" if hi < 5.0 else
               "INDISTINGUISHABLE FROM")
    print(f"  -> nominally {verdict} the 5.0bps engine assumption")
    print("  *** ADVISORY ONLY — this estimator leaks drift into c (add. 35); "
          "it does NOT fire the migration gate. Reported SE is also ~55% too "
          "narrow (day-clustered is ~1.55x wider). ***")

    # legacy statistic, kept for continuity with addenda 14b/34 only
    print(f"  [legacy notional-weighted fill-vs-close: "
          f"{legacy_signed / tot_notional * 1e4:+.2f} bps — drift-contaminated, "
          f"see addendum 34; not the decision number]")

    print("  betas used (drift scaling): " + ", ".join(
        f"{t} {betas[t]:.1f}" for t in sorted(betas, key=lambda x: -betas[x])[:6]))

    thin = {"ZVOL", "VBF", "VXZ", "VIXM"}
    present = sorted(thin & {t for _, _, _, t, _ in samples})
    if present:
        print("  thin names (same model, cost term restricted to each):")
        for t in present:
            g = group_cost(samples, betas, {t})
            if not g:
                continue
            gc, gse, gn = g
            flag = "" if abs(gc * 1e4) <= 2 * gse * 1e4 else "   <- significant"
            print(f"    {t:5s} {gc*1e4:+7.2f} +/- {gse*1e4:5.2f} bps/side "
                  f"(n={gn}){flag}")
        gall = group_cost(samples, betas, thin)
        if gall:
            gc, gse, gn = gall
            print(f"    {'ALL':5s} {gc*1e4:+7.2f} +/- {gse*1e4:5.2f} bps/side "
                  f"(n={gn}) — the capacity canary")

    if lo > 5.0:
        print("  !! point estimate clears 5bps by >2 SE — NOT actionable on its "
              "own: re-run only after the add.-35 P0 fixes (intraday benchmark, "
              "timestamp buckets, clustered SE) and confirm with a placebo run.")


if __name__ == "__main__":
    main()
