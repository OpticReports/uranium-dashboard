#!/usr/bin/env python3
"""Shadow-runner calibration and controls (results.md addendum 48). Three checks, one JSON:

1. reproduction  Composer's own backtest of every approved era tree (POST /backtest, read-only
   simulation), 2026-04-01..2026-10-28, against the shadow on the same dates. Composer's backtest
   decides on closing prices like the shadow, so this isolates the evaluator: semantics + data.
   Counted strictly (same tickers, half-L1 <= 0.5%) as well as by the daily agree rule; KMLM's
   backtest holds drifted weights, so it is checked on the corridor path (previous backtest day's
   weights drifted to today, target if more than 10pp off). Controls: the comparison shifted a day,
   and every day Composer's backtest changed allocation.
2. late moves    how far decisive tickers move between Composer's ~15:45-15:55 ET decision and the
   official close, in units of their 20-session daily sigma (Yahoo 5-minute bars, last ~60
   sessions). Sets the fallback search radius (KNIFE_SIGMA = p95).
3. placebo       the classifier on deliberately wrong pairs: the logic at D against Composer's
   holdings from another session (D-1, D+1, D+5) where those holdings differ. Inside the 5-minute
   bar window the daily rule (decision-time prices) applies; before it, the fallback search.

Writes composer/results/shadow-calibration-2026-10-29.json. Usage: calibrate.py
"""
import copy
import datetime
import json
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)
import composerlib as cl  # noqa: E402
import shadow_runner as sr  # noqa: E402
import backfill as bf  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "shadow-calibration-2026-10-29.json")
BT_START, BT_END = "2026-04-01", "2026-10-28"
LATE_TICKERS = ["SPY", "TQQQ", "IEF", "KIE", "TNA", "TECL", "SOXL", "TLT", "SQQQ", "XLK", "KMLM", "UVXY", "SSO"]


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def strict(a, b):
    return set(a) == set(b) and sr.distance(a, b)[0] <= 0.005


def reproduction(cfg_all, prices):
    out = {}
    for eng, cfg in cfg_all.items():
        for era in cfg["eras"]:
            tree = copy.deepcopy(sr.load_tree(era))
            tree["id"] = str(uuid.uuid4())
            bt = cl.backtest_tree(tree, start=BT_START, end=BT_END)
            comp = {}
            for t, m in (bt.get("tdvm_weights") or {}).items():
                for dd, w in m.items():
                    if w:
                        comp.setdefault(cl.epoch_day_to_date(int(dd)).isoformat(), {})[t] = w
            ds = sorted(comp)
            tree = sr.load_tree(era)
            tk = sr.tree_tickers(tree)
            run = sr.common_days(prices, tk, ds[-1])
            run = run[max(0, run.index(ds[0]) - sr.SUB_WARMUP):]
            sim = sr.Shadow({t: prices[t] for t in tk})
            dec = sim.decide(tree, run, set(ds))
            c = cfg.get("corridor")
            res = {"n": 0, "agree": 0, "strict": 0, "shifted_agree": 0, "shifted_n": 0, "changes": 0,
                   "changes_followed": 0, "differ": []}
            for i, d in enumerate(ds):
                if d not in dec or dec[d][0] is None:
                    continue
                cb = sr.norm(comp[d])
                drifted = sr.drift(sr.norm(comp[ds[i - 1]]), prices, ds[i - 1], d) if c and i else None
                res["n"] += 1
                ok = sr.agrees(dec[d][0], cb, c, drifted)
                res["agree"] += ok
                res["strict"] += strict(dec[d][0], cb) if not c else ok
                if not ok:
                    res["differ"].append({"date": d, "shadow": dec[d][0], "composer_backtest": cb})
                if i and not c and set(sr.norm(comp[ds[i - 1]])) != set(cb):
                    res["changes"] += 1
                    res["changes_followed"] += strict(dec[d][0], cb)
                if i + 1 < len(ds):
                    res["shifted_n"] += 1
                    res["shifted_agree"] += sr.agrees(dec[d][0], sr.norm(comp[ds[i + 1]]), c,
                                                      sr.drift(cb, prices, d, ds[i + 1]) if c else None)
            out[f"{eng}:{era['version']}"] = res
            print(f"  reproduction {eng} {era['version'][:8]}: {res['agree']}/{res['n']} (strict {res['strict']}; "
                  f"allocation changes followed {res['changes_followed']}/{res['changes']}; shifted a day "
                  f"{res['shifted_agree']}/{res['shifted_n']})", flush=True)
    return out


def late_moves(prices, raw, bars):
    out = {"per_ticker": {}, "pooled": {}}
    pooled = {hh: [] for hh in sr.KNIFE_TIMES}
    window = set()
    for t in LATE_TICKERS:
        rows = {hh: [] for hh in sr.KNIFE_TIMES}
        for d, b in sorted((bars.get(t) or {}).items()):
            close = raw.get(t, {}).get(d)
            prior = [x for x in prices[t] if x < d]
            if not close or not prior:
                continue
            sg = sr.Shadow({t: prices[t]}).sigma(t, prior[-1])
            if not sg:
                continue
            window.add(d)
            for hh in sr.KNIFE_TIMES:
                p = sr.bar_price(b, hh)
                if p:
                    rows[hh].append(round(abs(close / p - 1) / sg, 4))
        out["per_ticker"][t] = {hh: {"n": len(v), "p50": q(v, .5), "p95": q(v, .95), "p99": q(v, .99), "max": max(v)}
                                for hh, v in rows.items() if v}
        for hh in rows:
            pooled[hh] += rows[hh]
    out["window"] = [min(window), max(window)] if window else None
    for hh, v in pooled.items():
        out["pooled"][hh] = {"n": len(v), "p50": q(v, .5), "p90": q(v, .9), "p95": q(v, .95), "p99": q(v, .99),
                             "max": max(v), "values": sorted(v)}
        print(f"  late move {hh} -> official close: n {len(v)} p50 {q(v, .5):.3f} p95 {q(v, .95):.3f} "
              f"p99 {q(v, .99):.3f}", flush=True)
    return out


def placebo(cfg_all, prices, raw, bars):
    snaps = bf.snapshots()
    cal = sorted(prices["SPY"])
    by_day = {}
    for taken, h, s in snaps:
        d = bf.session_of(taken, cal)
        if d:
            by_day[d] = s
    days = sorted(by_day)
    counts, ratios = {}, []
    for eng, cfg in cfg_all.items():
        sid = cfg["symphony"]
        for i, era in enumerate(cfg["eras"]):
            nxt = cfg["eras"][i + 1]["from"] if i + 1 < len(cfg["eras"]) else "9999"
            keep = [d for d in days if era["from"] <= d < nxt and sid in by_day[d]["symphonies"]]
            if not keep:
                continue
            tree = sr.load_tree(era)
            tk = sr.tree_tickers(tree)
            run = sr.common_days(prices, tk, max(keep))
            run = run[max(0, run.index(min(keep)) - sr.SUB_WARMUP):]
            sim = sr.Shadow({t: prices[t] for t in tk})
            dec = sim.decide(tree, run, set(keep))

            def hold(d):
                return bf.holdings(by_day[d], sid)
            for j, d in enumerate(keep):
                target, tr = dec[d]
                alts = None
                for lag in (-1, 1, 5):
                    if not 0 <= j + lag < len(keep):
                        continue
                    other = hold(keep[j + lag])
                    if sr.agrees(hold(d), other, cfg.get("corridor")):
                        continue                     # holdings did not change: not a wrong pair
                    if alts is None:
                        alts = sr.at_times(prices, raw, bars(sorted(tk)), tree, d) or {}
                    st, det = sr.classify(sim, tree, d, target, tr, other, cfg.get("corridor"), None,
                                          intraday=(lambda: alts) if alts else None)
                    key = (eng, "bars" if alts else "no bars")
                    c = counts.setdefault(f"{key[0]} / {key[1]}", {})
                    c[st] = c.get(st, 0) + 1
                    if st == "knife-edge" and det["edge"]["basis"] == "search":
                        ratios.append(det["edge"]["sigma_ratio"])
    tot = {"bars": {}, "no bars": {}}
    for k, c in counts.items():
        for s, v in c.items():
            tot[k.split(" / ")[1]][s] = tot[k.split(" / ")[1]].get(s, 0) + v
    print(f"  placebo (holdings changed): {tot}", flush=True)
    return {"by_engine": counts, "total": tot, "search_sigma_ratios": sorted(ratios)}


def main():
    cfg_all = sr.load_manifest()
    tick = {"SPY"} | set(LATE_TICKERS)
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            tick |= sr.tree_tickers(sr.load_tree(era))
    prices, raw, bad = sr.fetch_prices(tick, datetime.datetime.now(datetime.timezone.utc))
    if bad:
        print("Yahoo failures:", bad)
    bars_fn = sr.bars_fetcher("60d")
    res = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "knife_sigma": sr.KNIFE_SIGMA, "knife_times": sr.KNIFE_TIMES}
    print("reproduction vs Composer's own backtests", flush=True)
    res["reproduction"] = reproduction(cfg_all, prices)
    print("late moves", flush=True)
    res["late_moves"] = late_moves(prices, raw, bars_fn(LATE_TICKERS))
    print("placebo", flush=True)
    res["placebo"] = placebo(cfg_all, prices, raw, bars_fn)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
