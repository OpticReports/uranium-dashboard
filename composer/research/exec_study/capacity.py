#!/usr/bin/env python3
"""Portfolio capacity analysis: max book size before slippage/liquidity bites.

Method (results.md addendum 15):
- Trade profile: from the exec-study ledgers (drift-adjusted daily deltas),
  each ticker's daily traded fraction of the TOTAL book (delta x symphony
  weight, summed across symphonies trading the same ticker the same day —
  Composer batches all symphonies into one window). Distribution per ticker:
  median / p95 / max.
- Liquidity: per-ticker median daily $ volume over the last 6 months (ADV),
  plus p25 (thin-day liquidity). NOTE: Composer trades in a 15-minute window
  before the close; that window typically carries only ~10-20% of daily
  volume, so participation caps are set vs FULL-day ADV at conservative
  levels: 1% of ADV = "invisible" (fills at ~quoted spread), 5% = "tolerable"
  (pays measurable impact), >10% = "moving the market".
- Ceiling per ticker: B_max = cap x ADV / p95_traded_fraction.
- Impact curve: square-root market-impact model, added cost per trade
  ~ daily_vol_bps x sqrt(participation); annualized added drag summed over
  the actual ledger at book sizes 0.25/0.5/1/2/5M, per ticker and blended.
Caveats printed with the results: screen ADV understates true ETF capacity
(create/redeem vs deep underlyings, esp. VIX-futures funds); leveraged-ETF
ADVs are enormous and never bind; the model is for RANKING and thresholds,
not precise cost prediction.
"""
import csv, json, math, os, collections, datetime, statistics

SC = "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/scratchpad/exec_study"
HERE = os.path.dirname(os.path.abspath(__file__))
W = {"HG": .29, "KMLM": .29, "SLEEVE": .27, "HARV": .15}

def vol_stats(t):
    res = json.load(open(f"{SC}/px/{t}.json"))
    q = res["indicators"]["quote"][0]
    rows = [(c, v) for c, v in zip(q["close"], q["volume"]) if c and v]
    dollar = [c*v for c, v in rows[-126:]]
    rets = [rows[i][0]/rows[i-1][0]-1 for i in range(max(1, len(rows)-126), len(rows))]
    sigma = statistics.pstdev(rets) if len(rets) > 2 else 0.02
    ds = sorted(dollar)
    return {"adv50": ds[len(ds)//2], "adv25": ds[len(ds)//4], "sigma_bps": sigma*1e4}

# daily traded fraction of the BOOK per ticker (summed across symphonies)
frac = collections.defaultdict(lambda: collections.defaultdict(float))
years = {}
for lab, w in W.items():
    dates = set()
    for r in csv.DictReader(open(f"{HERE}/trades-{lab}.csv")):
        f = abs(float(r["delta_weight_pct"]))/100 * w
        frac[r["ticker"]][r["date"]] += f
        dates.add(r["date"])
    ds = sorted(dates)
    years[lab] = (datetime.date.fromisoformat(ds[-1]) - datetime.date.fromisoformat(ds[0])).days/365.25
YRS = max(years.values())

CAP_LOW, CAP_TOL = 0.01, 0.05
out = []
for t, days in frac.items():
    fs = sorted(days.values())
    p95 = fs[int(0.95*(len(fs)-1))]
    vs = vol_stats(t)
    b_low = CAP_LOW * vs["adv50"] / p95
    b_tol = CAP_TOL * vs["adv50"] / p95
    out.append({"ticker": t, "n_days": len(fs), "p95_frac_pct": p95*100,
                "adv50_m": vs["adv50"]/1e6, "adv25_m": vs["adv25"]/1e6,
                "sigma_bps": vs["sigma_bps"],
                "b_low_m": b_low/1e6, "b_tol_m": b_tol/1e6})

out.sort(key=lambda x: x["b_low_m"])
print(f"{'ticker':7} {'days':>5} {'p95 %bk':>8} {'ADV $M':>8} {'ceil-LOW':>9} {'ceil-TOL':>9}")
for r in out:
    print(f"{r['ticker']:7} {r['n_days']:>5} {r['p95_frac_pct']:>7.2f}% "
          f"{r['adv50_m']:>7.1f}M {r['b_low_m']:>8.2f}M {r['b_tol_m']:>8.2f}M")

# impact curve: added annual drag (bps of book) vs book size, sqrt model
print("\nadded execution drag vs book size (sqrt-impact, bps/yr of book):")
BOOKS = [0.25e6, 0.5e6, 1e6, 2e6, 5e6]
hdr = "  ".join(f"{b/1e6:>6.2f}M" for b in BOOKS)
print(f"{'ticker':7} {hdr}")
tot = {b: 0.0 for b in BOOKS}
per = {}
for r in sorted(out, key=lambda x: -sum(frac[x['ticker']].values())):
    t = r["ticker"]
    vals = []
    for B in BOOKS:
        drag = 0.0
        for f in frac[t].values():
            q = f * B / (r["adv50_m"]*1e6)
            drag += f * r["sigma_bps"] * math.sqrt(q)
        drag /= YRS
        tot[B] += drag
        vals.append(drag)
    per[t] = vals
    if max(vals) > 3:
        print(f"{t:7} " + "  ".join(f"{v:>7.1f}" for v in vals))
print(f"{'TOTAL':7} " + "  ".join(f"{tot[b]:>7.1f}" for b in BOOKS))
json.dump({"tickers": out, "impact_curve_bps_yr": {f"{b/1e6}M": round(tot[b],1) for b in BOOKS},
           "per_ticker_impact": {t: [round(v,1) for v in vs] for t, vs in per.items()}},
          open(f"{HERE}/capacity_results.json", "w"), indent=1)
