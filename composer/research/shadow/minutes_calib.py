#!/usr/bin/env python3
"""Shadow runner on FMP 1-minute prices (results.md addendum 50): what the minute check changes.

The daily check's decision-time test now reads FMP 1-minute prices at every minute from 15:44 to
15:56 ET (16 to 4 minutes before the close), before Yahoo's 5-minute bars at 15:45/15:50/15:55, before
the 0.3-sigma one-ticker search. Two measurements, old rule against new, on the same inputs:

1. sessions  every live-holdings snapshot session from 2026-07-15 (backfill.py's mapping, the daily
   commits of composer/results/monitor/last-snapshot.json), re-classified. The no-rebalance sessions
   (10-26..28) are left out: they are judged on Composer's record, not on prices.
2. placebo   the classifier on deliberately wrong pairs: the logic at D against Composer's holdings
   from another session (D-1, D+1, D+5) where those holdings differ (calibrate.py's design). How many
   wrong pairs each rule excuses as a knife-edge.
Each minute knife-edge also records how many of the 13 minutes reproduce Composer and whether any lies
inside 15:45-15:55 (not only on the margin minutes 15:44 / 15:56).

FMP minutes are prefetched one session per call for every decision ticker (a range returns only the last
three calendar days up to `to`); only 15:25-16:00 and each day's last bar are kept, cached in the
scratchpad (not the repo). Writes
composer/results/shadow-minutes-2026-11-01.json. Usage: minutes_calib.py
"""
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)
import shadow_runner as sr  # noqa: E402
import backfill as bf  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "shadow-minutes-2026-11-01.json")
CACHE = os.environ.get("MINUTES_CACHE", "/tmp/claude-0/-home-user-uranium-dashboard/6d96d78e-807c-545a-8c5b-9d9d8e765587/"
                       "scratchpad/fmp-minutes-cache.json")
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
    """a minutes callable over the prefetched bars, with SPY's last bar as every ticker's session close"""
    def get(tickers, d):
        spy = (cache.get("SPY") or {}).get(d) or {}
        close = sr._hm(max(sr._min(k) for k in spy) + 1) if spy else None
        out = {}
        for t in tickers:
            m = (cache.get(t) or {}).get(d)
            if m:
                out[t] = {d: dict(m, _close=close) if close else dict(m)}
        return out
    return get


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
                    row["new_time"] = n_det["edge"]["time"]
                    hits = [k for k, v in alts_new(d).items() if k != "_src" and v and sr.agrees(v, live, corridor, drifted)]
                    row.update(minutes_matched=len(hits), first=hits[0], last=hits[-1],
                               inner=any("15:45" <= k <= "15:55" for k in hits))
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
                    placebo["old"][lo] = placebo["old"].get(lo, 0) + 1
                    placebo["new"][ln] = placebo["new"].get(ln, 0) + 1
                    if lo != ln:
                        placebo["changed"].append({"date": d, "engine": eng, "lag": lag, "old": lo, "new": ln,
                                                   "time": (e2.get("edge") or {}).get("time")})
    trans = {}
    for r in rows:
        k = f"{r['old']} -> {r['new']}"
        trans[k] = trans.get(k, 0) + 1
    ke = [x for x in rows if "minutes_matched" in x]
    res = {"generated": now.isoformat(timespec="seconds"), "sessions": [days[0], days[-1]], "n_sessions": len(days),
           "minute_knife_edges": {"n": len(ke), "margin_only": sum(not x["inner"] for x in ke),
                                  "matched_minutes": sorted(x["minutes_matched"] for x in ke)},
           "window": sr.decision_minutes(), "transitions": trans, "placebo": placebo, "rows": rows}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({"transitions": trans, "placebo_old": placebo["old"], "placebo_new": placebo["new"],
                      "placebo_pairs": placebo["pairs"]}, indent=1))


if __name__ == "__main__":
    main()
