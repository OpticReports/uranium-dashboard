#!/usr/bin/env python3
"""Shadow-runner backfill (results.md addendum 48): replay the approved logic, era by era, against
every live-holdings snapshot the daily monitor committed to git (composer/results/monitor/
last-snapshot.json, 2026-07-15 onward), on the same Yahoo prices the daily check uses, with the
daily check's classifier: knife-edges confirmed on actual 15:45/15:50/15:55 ET prices where Yahoo
still has 5-minute bars (the last ~60 sessions), the 0.3-sigma one-ticker search before that; KMLM
on its corridor path when the previous session has a snapshot.

Each snapshot is mapped to the session whose rebalance it shows: taken at or after 16:00 ET on a
session day -> that session; otherwise the previous session. The latest snapshot per session wins.
The snapshots do not record Composer's rebalance-attempt date, so a past session with no attempt
and unchanged logic would read as agree. The three sessions Composer skipped (2026-10-26..28;
symphony-stats-meta on 2026-10-29 showed last_rebalance_attempted_on = 2026-10-23 for all four)
are added as no-rebalance rows: Composer's frozen 10-23 holdings against what the logic wanted.

Writes composer/results/shadow-backfill-2026-10-29.json and upserts src=backfill rows into the
shadow ledger. Usage: backfill.py [--no-ledger]
"""
import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import shadow_runner as sr  # noqa: E402

SNAP = "composer/results/monitor/last-snapshot.json"
OUT = os.path.join(HERE, "..", "..", "results", "shadow-backfill-2026-10-29.json")
SKIPPED = ["2026-10-26", "2026-10-27", "2026-10-28"]
LAST_ATTEMPT = "2026-10-23"


def snapshots():
    shas = subprocess.check_output(["git", "log", "--format=%H", "--", SNAP], cwd=ROOT, text=True).split()
    out = []
    for h in shas:
        try:
            s = json.loads(subprocess.check_output(["git", "show", f"{h}:{SNAP}"], cwd=ROOT, text=True))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        out.append((s["taken_at"], h, s))
    return sorted(out)


def session_of(taken_at, cal):
    """the session whose rebalance a snapshot taken at `taken_at` shows"""
    e = sr.et_now(datetime.datetime.fromisoformat(taken_at))
    day = e.date().isoformat()
    if day in cal and (e.hour, e.minute) >= (16, 0):
        return day
    prev = [d for d in cal if d < day]
    return prev[-1] if prev else None


def holdings(snap, sid):
    h = snap["symphonies"][sid]["holdings"]
    return sr.live_weights({"holdings": [{"ticker": t, "allocation": w} for t, w in h.items()]})


def main():
    write = "--no-ledger" not in sys.argv
    cfg_all = sr.load_manifest()
    snaps = snapshots()
    tick = {"SPY"}
    for cfg in cfg_all.values():
        for era in cfg["eras"]:
            tick |= sr.tree_tickers(sr.load_tree(era))
    now = datetime.datetime.now(datetime.timezone.utc)
    prices, raw, bad = sr.fetch_prices(tick, now)
    if bad:
        print("Yahoo failures:", bad)
    bars = sr.bars_fetcher("60d")
    cal = sorted(prices["SPY"])
    by_day = {}
    for taken, h, s in snaps:
        d = session_of(taken, cal)
        if d:
            by_day[d] = (taken, h, s)                  # later snapshots overwrite earlier ones
    days = sorted(by_day)
    print(f"{len(snaps)} snapshots -> {len(days)} sessions {days[0]}..{days[-1]}")

    rows = []
    for eng, cfg in cfg_all.items():
        sid = cfg["symphony"]
        for i, era in enumerate(cfg["eras"]):
            nxt = cfg["eras"][i + 1]["from"] if i + 1 < len(cfg["eras"]) else "9999"
            keep = [d for d in days if era["from"] <= d < nxt and sid in by_day[d][2]["symphonies"]]
            keep += [d for d in SKIPPED if era["from"] <= d < nxt]
            if not keep:
                continue
            tree = sr.load_tree(era)
            tk = sr.tree_tickers(tree)
            run_days = sr.common_days(prices, tk, max(keep))
            run_days = run_days[max(0, run_days.index(min(keep)) - sr.SUB_WARMUP):]
            sim = sr.Shadow({t: prices[t] for t in tk})
            dec = sim.decide(tree, run_days, set(keep))
            for d in sorted(keep):
                base = {"date": d, "engine": eng, "version": era["version"][:8], "src": "backfill"}
                if d not in dec:
                    rows.append(dict(base, status="unavailable", note="no common close"))
                    continue
                target, tr = dec[d]
                if d in SKIPPED:
                    rows.append(dict(base, status="no-rebalance", target=target, attempted=LAST_ATTEMPT,
                                     live=holdings(by_day[LAST_ATTEMPT][2], sid), live_asof=LAST_ATTEMPT))
                    continue
                live = holdings(by_day[d][2], sid)
                row = dict(base, target=target, live=live, snapshot=by_day[d][0])
                if target is None:
                    rows.append(dict(row, status="unavailable", note=tr))
                    continue
                prev_d = cal[cal.index(d) - 1]
                drifted = None
                if cfg.get("corridor") and prev_d in by_day and sid in by_day[prev_d][2]["symphonies"]:
                    drifted = sr.drift(holdings(by_day[prev_d][2], sid), prices, prev_d, d)
                status, det = sr.classify(sim, tree, d, target, tr, live, cfg.get("corridor"), drifted,
                                          intraday=lambda: sr.at_times(prices, raw, bars(sorted(tk)), tree, d))
                row.update(status=status, **det)
                if cfg.get("corridor"):
                    row["corridor_check"] = "path" if drifted else "lenient"
                if status != "agree":
                    row["path"] = sr.explain(tr, 6)
                rows.append(row)
    rows.sort(key=lambda r: (r["date"], list(cfg_all).index(r["engine"])))
    summ = {}
    for r in rows:
        k = r["status"] + (f" ({r['edge']['basis']})" if r["status"] == "knife-edge" else "")
        summ.setdefault(r["engine"], {}).setdefault(k, 0)
        summ[r["engine"]][k] += 1
    res = {"generated": now.isoformat(timespec="seconds"), "sessions": [days[0], SKIPPED[-1]],
           "snapshots": len(snaps), "summary": summ, "rows": rows}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(summ, indent=1))
    for r in rows:
        if r["status"] != "agree":
            e = r.get("edge") or {}
            how = (f"@{e['time']}" if e.get("basis") == "intraday" else
                   f"{e.get('ticker')} {e.get('move', 0):+.3%} ({e.get('sigma_ratio')} sigma)" if e else r.get("note", ""))
            print(f"{r['date']} {r['engine']:6s} {r['status']:12s} live {sr.fmt_w(r.get('live') or {})} | logic "
                  f"{sr.fmt_w(r.get('target') or {})} | {how} {r.get('corridor_check', '')} {r.get('why', '')[:200]}")
    if write:
        sr.write_ledger(rows)
        print("ledger rows written:", len(rows))


if __name__ == "__main__":
    main()
