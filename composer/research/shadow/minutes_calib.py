#!/usr/bin/env python3
"""Shadow runner on FMP 1-minute prices (results.md addendum 50): what the minute check changes.

The daily check's decision-time test now reads FMP 1-minute prices at every minute from 15:50 to
15:55 ET (10 to 5 minutes before the close), before Yahoo's 5-minute bars at 15:45/15:50/15:55, before
the 0.3-sigma one-ticker search. Measurements, old rule against new, on the same inputs:

1. sessions  every live-holdings snapshot session from 2026-07-15 (backfill.py's mapping, the daily
   commits of composer/results/monitor/last-snapshot.json), re-classified. The no-rebalance sessions
   (10-26..28) are left out: they are judged on Composer's record, not on prices.
2. placebo   the classifier on deliberately wrong pairs: the logic at D against Composer's holdings
   from another session (D-1, D+1, D+5) where those holdings differ (calibrate.py's design). How many
   wrong pairs each rule excuses as a knife-edge.
3. profile   for every engine-session, the logic re-run at each minute 15:26-16:00 against Composer's
   holdings: how many sessions each minute contradicts (where Composer's decision prices sit)
4. windows   candidate windows read off the same minute tables: disagreements explained, wrong pairs
   excused (the window choice's own evidence)
Each minute knife-edge records the window minutes that reproduce Composer.

FMP minutes are prefetched one session per call for every decision ticker (a range returns only the last
three calendar days up to `to`); only 15:25-16:00 and each day's last bar are kept, cached outside the
repo (env MINUTES_CACHE, else the system temp directory). Writes
composer/results/shadow-minutes-2026-11-01.json. Usage: minutes_calib.py
"""
import concurrent.futures
import datetime
import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)
import shadow_runner as sr  # noqa: E402
import backfill as bf  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "shadow-minutes-2026-11-01.json")
CACHE = os.environ.get("MINUTES_CACHE") or os.path.join(tempfile.gettempdir(), "fmp-minutes-cache.json")
KEEP = ("15:25", "16:00")


def fetch_chunk(t, frm, to, key):
    """{date: {'HH:MM': close}} for the sessions frm..to; an answer that is not a list of bars (a
    rate-limit message) is an error, retried, never read as 'no data'"""
    url = f"{sr.FMP_MINUTES}?" + urllib.parse.urlencode({"symbol": t, "from": frm, "to": to, "apikey": key})
    err = None
    for k in range(5):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                rows = json.load(r)
            if not isinstance(rows, list):
                raise RuntimeError(f"unexpected answer {str(rows)[:120]}")
            out = {}
            for b in rows:
                d, hm = str(b.get("date", ""))[:10], str(b.get("date", ""))[11:16]
                if frm <= d <= to and b.get("close"):
                    out.setdefault(d, {})[hm] = float(b["close"])
            return out
        except Exception as e:  # noqa: BLE001
            err = str(e).replace(key, "***")
            time.sleep(2 * 2 ** k)
    raise RuntimeError(f"FMP {t} {frm}..{to}: {err}")


def prefetch(tickers, cal, key):
    """{ticker: {date: {'HH:MM': close}}} for every session in cal; the window minutes plus each day's
    last bar (the session close comes from SPY's)"""
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
    jobs = []
    for t in sorted(tickers):              # FMP answers a range with the last three CALENDAR days up to
        have = set((cache.get(t) or {}))   # `to` (a weekend inside a range drops sessions): one day a call
        jobs += [(t, d, d) for d in cal if d not in have]
    print(f"FMP minutes: {len(jobs)} calls for {len(tickers)} tickers x {len(cal)} sessions", flush=True)

    failed = []

    def one(job):
        t, frm, to = job
        try:
            return t, fetch_chunk(t, frm, to, key)
        except RuntimeError as e:
            failed.append(str(e))
            return t, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for n, (t, res) in enumerate(ex.map(one, jobs)):
            for d, m in res.items():
                last = max(m, key=sr._min)
                cache.setdefault(t, {})[d] = {k: v for k, v in m.items() if KEEP[0] <= k <= KEEP[1] or k == last}
            if n % 200 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(cache, f)
    if failed:
        print(f"FMP failures ({len(failed)}): {failed[:5]}", flush=True)
    short = {t: [d for d in cal if d not in (cache.get(t) or {})] for t in sorted(tickers)}
    short = {t: ds for t, ds in short.items() if ds}
    print(f"sessions without minutes: {sum(map(len, short.values()))} ticker-days ({ {t: len(v) for t, v in short.items()} })", flush=True)
    return cache


def minutes_from(cache):
    """a minutes callable over the prefetched bars, vetted with the daily check's rule (sr.vet_minutes).
    The cache keeps only 15:25-16:00 and each day's last bar, so a feed cut before 15:25 is not seen
    here; every cached last bar is at 15:53 or later, so the 69 sessions are unaffected"""
    def get(tickers, d):
        day = {t: (cache.get(t) or {}).get(d) for t in set(tickers) | {"SPY"}}
        usable, _ = sr.vet_minutes({t: m for t, m in day.items() if m}, d)
        return {t: usable[t] for t in tickers if t in usable}
    return get


PROFILE = [sr._hm(m) for m in range(sr._min("15:26"), sr._min("16:00") + 1)]
WINDOWS = {"15:44-15:56 (first draft)": (16, 4), "15:45-15:55": (15, 5), "15:50-15:55 (shipped)": (10, 5),
           "15:51-15:54": (9, 6)}


def logic_by_minute(prices, raw, minutes, tree, d):
    """{hh:mm: target} for every minute in PROFILE that prices every decision ticker"""
    tk = sorted(sr.decision_tickers(tree))
    got = minutes(tk, d)
    out = {}
    for hh in PROFILE:
        px = {t: sr.minute_price(((got.get(t) or {}).get(d)) or {}, hh) for t in tk}
        if any(v is None for v in px.values()) or any(not (raw.get(t) or {}).get(d) for t in tk):
            continue
        p = dict(prices)
        for t in tk:
            p[t] = dict(prices[t])
            p[t][d] = prices[t][d] * px[t] / raw[t][d]
        out[hh] = sr.run_engine(p, tree, d)[1]
    return out


def in_window(hh, w):
    return sr._min("16:00") - w[0] <= sr._min(hh) <= sr._min("16:00") - w[1]


def label(status, det):
    e = (det or {}).get("edge") or {}
    if status != "knife-edge":
        return status
    return f"knife-edge ({e.get('src') or e.get('basis')})" if e.get("basis") == "intraday" else "knife-edge (search)"


def main():
    key = os.environ.get("FMP_API_KEY")
    if not key:
        sys.exit("FMP_API_KEY not set")
    now = datetime.datetime.now(datetime.timezone.utc)
    cfg_all = sr.load_manifest()
    snaps = bf.snapshots()
    tick = {"SPY"}
    dec_tick = {"SPY"}
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            tree = sr.load_tree(era)
            tick |= sr.tree_tickers(tree)
            dec_tick |= sr.decision_tickers(tree)
    prices, raw, bad = sr.fetch_prices(tick, now)
    print("Yahoo failures:", bad or "none", flush=True)
    cal = sorted(prices["SPY"])
    by_day = {}
    for taken, h, s in snaps:
        d = bf.session_of(taken, cal)
        if d:
            by_day[d] = s
    days = sorted(d for d in by_day if d not in bf.SKIPPED)
    print(f"{len(snaps)} snapshots -> {len(days)} sessions {days[0]}..{days[-1]}", flush=True)
    cache = prefetch(dec_tick, [d for d in cal if days[0] <= d <= days[-1]], key)
    minutes = minutes_from(cache)
    ybars = sr.bars_fetcher("60d")

    rows, placebo = [], {"old": {}, "new": {}, "pairs": 0, "changed": []}
    for eng, cfg in cfg_all.items():
        sid, corridor = cfg["symphony"], cfg.get("corridor")
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
            cache_alts = {}

            def alts_old(d):
                if ("old", d) not in cache_alts:
                    cache_alts[("old", d)] = sr.at_times(prices, raw, ybars(sorted(tk)), tree, d)
                return cache_alts[("old", d)]

            def alts_new(d):
                if ("new", d) not in cache_alts:
                    cache_alts[("new", d)] = sr.intraday_check(prices, raw, tree, d, minutes, ybars)
                return cache_alts[("new", d)]

            def by_minute(d):
                if ("min", d) not in cache_alts:
                    cache_alts[("min", d)] = logic_by_minute(prices, raw, minutes, tree, d)
                return cache_alts[("min", d)]
            for j, d in enumerate(keep):
                target, tr = dec[d]
                if target is None:
                    continue
                live = bf.holdings(by_day[d], sid)
                prev_d = cal[cal.index(d) - 1]
                drifted = None
                if corridor and prev_d in by_day and sid in by_day[prev_d]["symphonies"]:
                    drifted = sr.drift(bf.holdings(by_day[prev_d], sid), prices, prev_d, d)
                o_st, o_det = sr.classify(sim, tree, d, target, tr, live, corridor, drifted,
                                          intraday=(lambda d=d: alts_old(d)))
                n_st, n_det = sr.classify(sim, tree, d, target, tr, live, corridor, drifted,
                                          intraday=(lambda d=d: alts_new(d)))
                row = {"date": d, "engine": eng, "version": era["version"][:8], "old": label(o_st, o_det),
                       "new": label(n_st, n_det), "live": sr.fmt_w(live), "logic": sr.fmt_w(target)}
                if n_st == "knife-edge" and n_det["edge"].get("time"):
                    row.update(new_time=n_det["edge"]["time"], new_times=n_det["edge"].get("times"))
                bm = by_minute(d)
                row["agree_at"] = [hh for hh, alt in bm.items() if alt and sr.agrees(alt, live, corridor, drifted)]
                row["priced"] = sorted(bm, key=sr._min)
                row["close_agrees"] = sr.agrees(target, live, corridor, drifted)
                if o_st != "agree" or n_st != "agree":
                    print(f"  {d} {eng:6s} old {row['old']:24s} new {row['new']:24s} {row.get('new_time', '')}", flush=True)
                rows.append(row)
                # placebo: Composer's holdings from another session where they differ
                for lag in (-1, 1, 5):
                    if not 0 <= j + lag < len(keep):
                        continue
                    other = bf.holdings(by_day[keep[j + lag]], sid)
                    if sr.agrees(live, other, corridor):
                        continue
                    placebo["pairs"] += 1
                    o2, d2 = sr.classify(sim, tree, d, target, tr, other, corridor, None, intraday=(lambda d=d: alts_old(d)))
                    n2, e2 = sr.classify(sim, tree, d, target, tr, other, corridor, None, intraday=(lambda d=d: alts_new(d)))
                    lo, ln = label(o2, d2), label(n2, e2)
                    if not sr.agrees(target, other, corridor):
                        bm = by_minute(d)
                        placebo.setdefault("minute_pairs", []).append(
                            [hh for hh, alt in bm.items() if alt and sr.agrees(alt, other, corridor)])
                    else:                                  # not a wrong pair: the logic's own answer, or KMLM lenient
                        why = "kmlm-lenient" if corridor and not sr.agrees(target, other) else "logic-equal"
                        placebo.setdefault("not_wrong", {}).setdefault(why, []).append(f"{d} {eng} lag {lag:+d}")
                    placebo["old"][lo] = placebo["old"].get(lo, 0) + 1
                    placebo["new"][ln] = placebo["new"].get(ln, 0) + 1
                    if lo != ln:
                        placebo["changed"].append({"date": d, "engine": eng, "lag": lag, "old": lo, "new": ln,
                                                   "time": (e2.get("edge") or {}).get("time")})
    trans = {}
    for r in rows:
        k = f"{r['old']} -> {r['new']}"
        trans[k] = trans.get(k, 0) + 1
    profile = [{"t": hh, "bad": sum(1 for x in rows if hh in x["priced"] and hh not in x["agree_at"]),
                "n": sum(1 for x in rows if hh in x["priced"])} for hh in PROFILE]
    dis = [x for x in rows if not x["close_agrees"]]
    windows = {name: {"explained": sum(1 for x in dis if any(in_window(hh, w) for hh in x["agree_at"])), "of": len(dis),
                      "placebo_excused": sum(1 for hs in placebo.get("minute_pairs", []) if any(in_window(hh, w) for hh in hs)),
                      "placebo_of": len(placebo.get("minute_pairs", []))} for name, w in WINDOWS.items()}
    ke = [x for x in rows if x.get("new_times")]
    res = {"generated": now.isoformat(timespec="seconds"), "sessions": [days[0], days[-1]], "n_sessions": len(days),
           "minute_knife_edges": {"n": len(ke), "matched_minutes": sorted(len(x["new_times"]) for x in ke),
                                  "times": sorted(x["new_time"] for x in ke)},
           "window": sr.decision_minutes(), "transitions": trans, "profile": profile, "windows": windows,
           "placebo_not_wrong": {k: len(v) for k, v in (placebo.get("not_wrong") or {}).items()},
           "placebo": {k: v for k, v in placebo.items() if k != "minute_pairs"}, "rows": rows}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({"transitions": trans, "placebo_old": placebo["old"], "placebo_new": placebo["new"],
                      "placebo_pairs": placebo["pairs"], "not_wrong": res["placebo_not_wrong"], "windows": windows,
                      "profile_15:40+": {x["t"]: x["bad"] for x in profile if x["t"] >= "15:40"},
                      "knife_edge_times": res["minute_knife_edges"]}, indent=1))


if __name__ == "__main__":
    main()
