#!/usr/bin/env python3
"""Shadow-runner calibration and controls (results.md addendum 48). Three checks, one JSON:

1. reproduction  Composer's own backtest of every approved era tree (POST /backtest, read-only
   simulation), 2026-04-01..2026-10-28, against the shadow on the same dates. Composer's backtest
   decides on closing prices like the shadow, so this isolates the evaluator: semantics + data.
   The one-day-shifted comparison is the control that shows the check has power.
2. late moves    how far decisive tickers move between Composer's ~15:45-15:50 ET decision and the
   close, in units of their 20-session daily sigma (Yahoo 5-minute bars, last ~60 sessions). Sets
   the knife-edge radius (KNIFE_SIGMA = p99).
3. placebo       the classifier on deliberately wrong pairs: the logic at D against Composer's
   holdings from another session (D-1, D+1, D+5). Measures how often a wrong comparison would be
   excused as a knife-edge.

Writes composer/results/shadow-calibration-2026-10-29.json. Usage: calibrate.py
"""
import copy
import datetime
import json
import math
import os
import sys
import urllib.request
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
            res = {"n": 0, "agree": 0, "shifted_agree": 0, "shifted_n": 0, "differ": []}
            for i, d in enumerate(ds):
                if d not in dec or dec[d][0] is None:
                    continue
                live = sr.norm(comp[d])
                res["n"] += 1
                if sr.agrees(dec[d][0], live, cfg.get("corridor")):
                    res["agree"] += 1
                else:
                    e = sr.knife_edge(sim, tree, d, dec[d][1], live, cfg.get("corridor"))
                    res["differ"].append({"date": d, "shadow": dec[d][0], "composer_backtest": live, "edge": e})
                if i + 1 < len(ds):
                    res["shifted_n"] += 1
                    res["shifted_agree"] += sr.agrees(dec[d][0], sr.norm(comp[ds[i + 1]]), cfg.get("corridor"))
            out[f"{eng}:{era['version']}"] = res
            print(f"  reproduction {eng} {era['version'][:8]}: {res['agree']}/{res['n']}  (shifted a day: "
                  f"{res['shifted_agree']}/{res['shifted_n']})", flush=True)
    return out


def late_moves(prices):
    import zoneinfo
    et = zoneinfo.ZoneInfo("America/New_York")
    out = {"per_ticker": {}, "pooled": {}}
    pooled = {"15:45": [], "15:50": []}
    for t in LATE_TICKERS:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=60d&interval=5m"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"}), timeout=30) as r:
            res = json.load(r)["chart"]["result"][0]
        qq = res["indicators"]["quote"][0]
        bars = {}
        for i, ts in enumerate(res["timestamp"]):
            e = datetime.datetime.fromtimestamp(ts, tz=et)
            bars.setdefault(e.date().isoformat(), {})[(e.hour, e.minute)] = (qq["open"][i], qq["close"][i])
        rows = {"15:45": [], "15:50": []}
        for d, b in sorted(bars.items()):
            last = b.get((15, 55))
            if not last or last[1] is None:
                continue
            sg = sr.Shadow({t: prices[t]}).sigma(t, max(x for x in prices[t] if x < d))
            if not sg:
                continue
            for hm, key in (((15, 45), "15:45"), ((15, 50), "15:50")):
                if b.get(hm) and b[hm][0]:
                    rows[key].append(round(abs(last[1] / b[hm][0] - 1) / sg, 4))
        out["per_ticker"][t] = {k: {"n": len(v), "p50": q(v, .5), "p95": q(v, .95), "p99": q(v, .99), "max": max(v)}
                                for k, v in rows.items() if v}
        for k in rows:
            pooled[k] += rows[k]
        out["window"] = [min(bars), max(bars)]
    for k, v in pooled.items():
        out["pooled"][k] = {"n": len(v), "p50": q(v, .5), "p90": q(v, .9), "p95": q(v, .95), "p99": q(v, .99),
                            "max": max(v), "values": sorted(v)}
        print(f"  late move {k}->close: n {len(v)} p50 {q(v, .5):.3f} p95 {q(v, .95):.3f} p99 {q(v, .99):.3f}", flush=True)
    return out


def placebo(cfg_all, prices):
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
                return sr.live_weights({"holdings": [{"ticker": t, "allocation": w}
                                                     for t, w in by_day[d]["symphonies"][sid]["holdings"].items()]})
            for j, d in enumerate(keep):
                target, tr = dec[d]
                for lag in (-1, 1, 5):
                    if not 0 <= j + lag < len(keep):
                        continue
                    other = hold(keep[j + lag])
                    if sr.agrees(hold(d), other, cfg.get("corridor")):
                        continue                     # holdings did not change: not a wrong pair
                    st, det = sr.classify(sim, tree, d, target, tr, other, cfg.get("corridor"))
                    c = counts.setdefault(eng, {})
                    c[st] = c.get(st, 0) + 1
                    if st == "knife-edge":
                        ratios.append(det["edge"]["sigma_ratio"])
    tot = {}
    for c in counts.values():
        for k, v in c.items():
            tot[k] = tot.get(k, 0) + v
    print(f"  placebo (holdings changed): {tot}", flush=True)
    return {"by_engine": counts, "total": tot, "knife_edge_sigma_ratios": sorted(ratios)}


def main():
    cfg_all = sr.load_manifest()
    tick = {"SPY"} | set(LATE_TICKERS)
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            tick |= sr.tree_tickers(sr.load_tree(era))
    prices, bad = sr.fetch_prices(tick, datetime.datetime.now(datetime.timezone.utc))
    if bad:
        print("Yahoo failures:", bad)
    res = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "knife_sigma": sr.KNIFE_SIGMA}
    print("reproduction vs Composer's own backtests", flush=True)
    res["reproduction"] = reproduction(cfg_all, prices)
    print("late moves", flush=True)
    res["late_moves"] = late_moves(prices)
    print("placebo", flush=True)
    res["placebo"] = placebo(cfg_all, prices)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
