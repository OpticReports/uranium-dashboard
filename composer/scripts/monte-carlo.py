#!/usr/bin/env python3
"""Monte Carlo simulation on a Composer symphony's backtest equity curve.

Resamples the strategy's *historical daily returns* (from the backtest
endpoint's dvm_capital series) to project a distribution of outcomes over a
future horizon. Two resampling schemes:

  iid    — classic bootstrap; each simulated day is an independent draw.
  block  — stationary (geometric) block bootstrap; preserves short-range
           autocorrelation and volatility clustering (more realistic tails).

Read-only: the only network call is the same backtest POST the baseline uses.
Pure stdlib (no numpy). Caveat: resampling assumes the historical return
distribution persists — regime changes, ticker decay (e.g. UVXY drag), and
capacity effects are NOT modeled. Treat results as "if the future rhymes with
this backtest," not as a forecast.

Usage:
  monte-carlo.py --id <symphony-id> [--start YYYY-MM-DD] [--capital 10000]
  monte-carlo.py -f results/backtest.json          # reuse a saved backtest
  common: [--sims 5000] [--horizon 252] [--block 10] [--seed 1] [-o out.json]
"""

import argparse
import json
import math
import os
import random
import sys
import urllib.request
import urllib.error

BASE = "https://api.composer.trade/api/v0.1"


def api_backtest(symphony_id, start, end, capital):
    kid = os.environ.get("COMPOSER_API_KEY_ID")
    sec = os.environ.get("COMPOSER_SECRET")
    if not kid or not sec:
        sys.exit("error: COMPOSER_API_KEY_ID / COMPOSER_SECRET not set")
    body = {
        "capital": capital, "apply_reg_fee": True, "apply_taf_fee": True,
        "slippage_percent": 0.0005, "broker": "ALPACA_WHITE_LABEL",
        "backtest_version": "v2",
    }
    if start:
        body["start_date"] = start
    if end:
        body["end_date"] = end
    req = urllib.request.Request(
        f"{BASE}/symphonies/{symphony_id}/backtest", method="POST",
        headers={"x-api-key-id": kid, "authorization": f"Bearer {sec}",
                 "content-type": "application/json",
                 "user-agent": "composer-api-helper/1.0"},
        data=json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: HTTP {e.code}\n{e.read().decode(errors='replace')[:1000]}")


def daily_returns(backtest):
    dvm = backtest["dvm_capital"]
    # take the primary series (first legend entry = the symphony itself)
    key = next(iter(backtest.get("legend") or dvm))
    series = dvm[key]
    days = sorted(int(d) for d in series)
    values = [series[str(d)] for d in days]
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values))
            if values[i - 1] > 0]
    return rets, key


def max_drawdown(path):
    peak, mdd = path[0], 0.0
    for v in path:
        if v > peak:
            peak = v
        dd = 1.0 - v / peak
        if dd > mdd:
            mdd = dd
    return mdd


def simulate(rets, sims, horizon, mean_block, rng):
    n = len(rets)
    out = []  # (terminal_multiple, max_drawdown)
    p_new_block = 1.0 / mean_block
    for _ in range(sims):
        path = [1.0]
        if mean_block <= 1:
            for _ in range(horizon):
                path.append(path[-1] * (1.0 + rets[rng.randrange(n)]))
        else:  # stationary block bootstrap
            i = rng.randrange(n)
            for _ in range(horizon):
                path.append(path[-1] * (1.0 + rets[i]))
                if rng.random() < p_new_block:
                    i = rng.randrange(n)
                else:
                    i = (i + 1) % n
        out.append((path[-1], max_drawdown(path)))
    return out


def pct(sorted_vals, q):
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def summarize(results, horizon):
    terms = sorted(t for t, _ in results)
    dds = sorted(d for _, d in results)
    years = horizon / 252.0
    def cagr(mult):
        return mult ** (1.0 / years) - 1.0 if mult > 0 else -1.0
    qs = [0.05, 0.25, 0.50, 0.75, 0.95]
    return {
        "terminal_multiple": {f"p{int(q*100):02d}": round(pct(terms, q), 4) for q in qs},
        "cagr": {f"p{int(q*100):02d}": round(cagr(pct(terms, q)), 4) for q in qs},
        "max_drawdown": {f"p{int(q*100):02d}": round(pct(dds, q), 4) for q in qs},
        "prob_loss": round(sum(1 for t in terms if t < 1.0) / len(terms), 4),
        "prob_max_drawdown_gt": {
            "20pct": round(sum(1 for d in dds if d > 0.20) / len(dds), 4),
            "30pct": round(sum(1 for d in dds if d > 0.30) / len(dds), 4),
            "50pct": round(sum(1 for d in dds if d > 0.50) / len(dds), 4),
        },
        "horizon_return_var95": round(pct(terms, 0.05) - 1.0, 4),
        "horizon_return_cvar95": round(
            sum(terms[: max(1, len(terms) // 20)]) / max(1, len(terms) // 20) - 1.0, 4),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--id", help="symphony id — runs a fresh backtest via the API")
    src.add_argument("-f", "--file", help="saved backtest JSON (results/*.json with dvm_capital, or full API response)")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--capital", type=float, default=10000)
    p.add_argument("--sims", type=int, default=5000)
    p.add_argument("--horizon", type=int, default=252, help="trading days to project")
    p.add_argument("--block", type=int, default=10, help="mean block length; 1 = iid only")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("-o", "--out", help="write full JSON results here")
    a = p.parse_args()

    if a.file:
        doc = json.load(open(a.file))
        backtest = doc if "dvm_capital" in doc else doc.get("backtest") or sys.exit(
            "error: file has no dvm_capital — save the full backtest response")
    else:
        backtest = api_backtest(a.id, a.start, a.end, a.capital)

    rets, key = daily_returns(backtest)
    if len(rets) < 60:
        sys.exit(f"error: only {len(rets)} daily returns — too short to resample")
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    hist = {
        "symphony": key,
        "n_days": len(rets),
        "daily_mean": round(mean, 6),
        "daily_stdev": round(math.sqrt(var), 6),
        "annualized_return": round((1 + mean) ** 252 - 1, 4),
        "annualized_vol": round(math.sqrt(var) * math.sqrt(252), 4),
        "worst_day": round(min(rets), 4),
        "best_day": round(max(rets), 4),
        "historical_max_drawdown": None,
    }
    # historical max drawdown from the curve itself
    dvm = backtest["dvm_capital"][key]
    curve = [dvm[str(d)] for d in sorted(int(x) for x in dvm)]
    hist["historical_max_drawdown"] = round(max_drawdown(curve), 4)

    rng = random.Random(a.seed)
    methods = {}
    methods["iid"] = summarize(simulate(rets, a.sims, a.horizon, 1, rng), a.horizon)
    if a.block > 1:
        methods[f"block{a.block}"] = summarize(
            simulate(rets, a.sims, a.horizon, a.block, rng), a.horizon)

    result = {
        "params": {"sims": a.sims, "horizon_days": a.horizon,
                   "mean_block_length": a.block, "seed": a.seed},
        "historical_sample": hist,
        "methods": methods,
        "caveat": ("Bootstrap of historical strategy returns; assumes the "
                   "sampled regime persists. Not a forecast."),
    }

    print(f"Monte Carlo — {key}  ({len(rets)} hist days, {a.sims} sims, "
          f"{a.horizon}d horizon)")
    for name, s in methods.items():
        c, d = s["cagr"], s["max_drawdown"]
        print(f"  [{name}]")
        print(f"    CAGR        p05 {c['p05']:+8.1%}   median {c['p50']:+8.1%}   p95 {c['p95']:+8.1%}")
        print(f"    max DD      p50 {d['p50']:8.1%}   p95 {d['p95']:8.1%}")
        print(f"    P(loss) {s['prob_loss']:.1%}   P(DD>30%) {s['prob_max_drawdown_gt']['30pct']:.1%}   "
              f"P(DD>50%) {s['prob_max_drawdown_gt']['50pct']:.1%}")
    if a.out:
        with open(a.out, "w") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
