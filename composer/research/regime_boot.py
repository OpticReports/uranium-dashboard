#!/usr/bin/env python3
"""55-year regime-bootstrap of the engine blend — RE-RUNNABLE (addendum 13).

Self-contained: fetches S&P dailies from Yahoo (spine 1971+), engine curves
from live Composer backtests (longest window each supports), the harvester's
guarded 2018-23 sim from harv_guard_sim.json (same dir), and stitches the
live harvester record on top. Pure stdlib.

Method: real monthly regime labels (TREND-UP / CHOP / CRASH) from S&P dailies;
each engine's regime-conditional monthly returns resampled through the actual
1971-2026 regime sequence. Joint sampling: each simulated month picks ONE real
month of the same regime; engines alive that month use their actual return
(preserves cross-correlation), others draw from their marginal bucket.
CONSERVATIVE variant: KMLM's CRASH/CHOP buckets replaced by HG's (its short
record contains no hostile regime; this bounds the optimism).

Cadence (POLICY.md standing analysis): re-run QUARTERLY (Oct/Jan/Apr/Jul) and
mandatorily at the Jan-2027 review. As live hostile-regime months accumulate
for KMLM and the harvester, the AS-MEASURED vs CONSERVATIVE gap should
shrink — that convergence (or its failure) is the finding. Output ranks
allocations; any reallocation remains an owner decision.

Usage: python3 composer/research/regime_boot.py   (from repo root; needs
       COMPOSER_API_KEY_ID / COMPOSER_SECRET for the backtests)
"""
import datetime
import json
import os
import random
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import composerlib as cl  # noqa: E402

ENGINES = {  # label: (symphony id, earliest sensible backtest start)
    "HG": ("mbkiXcuNDjueXpiox5Av", "2011-10-05"),
    "KMLM": ("YPTSJFJwD2ZKfAeYJUbW", "2021-01-01"),
    "SLEEVE": ("nNdBk7hc5NiBzeRvbI5T", "2011-10-05"),
    "HARV": ("ORQNCfZnA18wmsMWVhf8", "2023-04-19"),  # guarded harvester
}
ALLOCS = {
    "current 19/39/27/15": {"HG": .19, "KMLM": .39, "SLEEVE": .27, "HARV": .15},
    "tripwire 29/29/27/15": {"HG": .29, "KMLM": .29, "SLEEVE": .27, "HARV": .15},
    "old book 45/27/27/0": {"HG": .453, "KMLM": .273, "SLEEVE": .274, "HARV": 0},
    "balanced 25/25/27/23": {"HG": .25, "KMLM": .25, "SLEEVE": .27, "HARV": .23},
    "defensive 15/25/27/33": {"HG": .15, "KMLM": .25, "SLEEVE": .27, "HARV": .33},
}


def spx_daily():
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"
           "?period1=0&period2=4102444800&interval=1d")
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)["chart"]["result"][0]
    assert res["meta"]["dataGranularity"] == "1d", "Yahoo degraded granularity"
    q = res["indicators"]["quote"][0]
    out = {}
    for ts, c in zip(res["timestamp"], q["close"]):
        if c is not None:
            d = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).date()
            out[d.isoformat()] = c
    return out


def monthly_from_curve(curve):
    me = {}
    for dt in sorted(curve):
        me[dt[:7]] = curve[dt]
    yms = sorted(me)
    return {yms[i]: me[yms[i]] / me[yms[i - 1]] - 1 for i in range(1, len(yms))}


def main():
    spx = spx_daily()
    sd = sorted(spx)
    by_m = {}
    for i, dt in enumerate(sd):
        by_m.setdefault(dt[:7], []).append((spx[dt], spx[sd[i - 1]] if i else spx[dt]))
    regime = {}
    for ym, rows in sorted(by_m.items()):
        mret = rows[-1][0] / rows[0][1] - 1
        worst = min(a / b - 1 for a, b in rows)
        regime[ym] = ("CRASH" if (mret < -0.05 or worst < -0.03)
                      else "TREND-UP" if mret > 0.025 else "CHOP")
    this_m = datetime.date.today().isoformat()[:7]
    months = [ym for ym in sorted(regime) if "1971-01" <= ym < this_m]
    print(f"spine {months[0]}..{months[-1]} ({len(months)} months)")

    eng = {}
    for label, (sid, start) in ENGINES.items():
        bt = cl.backtest_by_id(sid, start=start)
        d, v = cl.equity_curve(bt)
        eng[label] = monthly_from_curve(
            {cl.epoch_day_to_date(x).isoformat(): y for x, y in zip(d, v)})
        print(f"  {label}: {len(eng[label])} months of record")
    # stitch the harvester's guarded 2018-23 sim UNDER its real record
    sim = json.load(open(os.path.join(HERE, "harv_guard_sim.json")))
    for ym, r in sim.items():
        eng["HARV"].setdefault(ym, r)

    buckets = {k: {"TREND-UP": [], "CHOP": [], "CRASH": []} for k in eng}
    for k, m in eng.items():
        for ym, ret in m.items():
            if ym in regime:
                buckets[k][regime[ym]].append((ym, ret))
    for k in eng:
        print(f"  {k} bucket sizes:", {r: len(v) for r, v in buckets[k].items()})
    donor = {r: sorted({ym for ym, _ in buckets["HG"][r]})
             for r in ("TREND-UP", "CHOP", "CRASH")}

    def draw(regm, rng, conservative):
        m_star = rng.choice(donor[regm])
        out = {}
        for k in eng:
            if conservative and k == "KMLM" and regm in ("CRASH", "CHOP"):
                out[k] = rng.choice(buckets["HG"][regm])[1]
                continue
            hit = dict(buckets[k][regm]).get(m_star)
            out[k] = hit if hit is not None else rng.choice(buckets[k][regm])[1]
        return out

    def run(w, K=800, conservative=False, seed=11):
        rng = random.Random(seed)
        seq = [regime[m] for m in months]
        cagrs, mdds = [], []
        for _ in range(K):
            cur, peak, mdd = 1.0, 1.0, 0.0
            for regm in seq:
                d = draw(regm, rng, conservative)
                r_ = sum(w[k] * d[k] for k in w)
                cur *= (1 + r_)
                peak = max(peak, cur)
                mdd = max(mdd, 1 - cur / peak)
            cagrs.append(cur ** (12 / len(seq)) - 1)
            mdds.append(mdd)
        cagrs.sort()
        mdds.sort()
        p = lambda a, q: a[int(q * (len(a) - 1))]  # noqa: E731
        return p(cagrs, .05), p(cagrs, .5), p(mdds, .5), p(mdds, .95)

    for label, conservative in (("AS-MEASURED", False), ("CONSERVATIVE-KMLM", True)):
        print(f"\n=== 55y regime-bootstrap — {label} ===")
        print(f"{'allocation':24} {'CAGR p05':>9} {'CAGR med':>9} {'DD med':>8} {'DD p95':>8}")
        for name, w in ALLOCS.items():
            a = run(w, conservative=conservative)
            print(f"{name:24} {a[0]:>+9.1%} {a[1]:>+9.1%} {a[2]:>8.1%} {a[3]:>8.1%}")
    print("\nNote: backtest-derived buckets — a RANKING tool, not a forecast. "
          "Compare the AS-MEASURED vs CONSERVATIVE gap with last quarter's run: "
          "convergence as live hostile months accumulate is the finding.")


if __name__ == "__main__":
    main()
