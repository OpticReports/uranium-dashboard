#!/usr/bin/env python3
"""Portfolio monitor: snapshot + alerts, designed for scheduled runs.

Each run snapshots per-symphony stats to composer/results/monitor/ and
compares against the previous snapshot. Alerts on:
  - drawdown from the symphony's tracked peak beyond --dd-alert (default 15%)
  - single-period value move beyond --move-alert (default 8%), deposit-aware
  - a queued deploy appearing
  - rebalance scheduled today

Exit code: 0 = quiet, 2 = alerts fired (easy to wire into cron/CI/triggers).
Read-only. State lives in composer/results/monitor/state.json (tracked peaks
persist across runs; snapshots rotate, keeping the last --keep).

Usage: monitor.py [--account UUID] [--dd-alert 0.15] [--move-alert 0.08] [--keep 30]
"""

import argparse
import datetime
import glob
import json
import os
import sys
import composerlib as cl

DIR = "composer/results/monitor"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account")
    p.add_argument("--dd-alert", type=float, default=0.15)
    p.add_argument("--move-alert", type=float, default=0.08)
    p.add_argument("--keep", type=int, default=30)
    # crash-sleeve monetization band (results.md addendum 7): alert when the
    # sleeve's share of the book leaves [lo, hi] so a human can rebalance it
    p.add_argument("--band-symphony", default="nNdBk7hc5NiBzeRvbI5T")
    p.add_argument("--band-lo", type=float, default=0.07)
    p.add_argument("--band-hi", type=float, default=0.15)
    # POLICY.md denominator: family crash-exposed assets = Composer engines +
    # owner-reported IBKR equities (update on owner reports; last 2026-07-07)
    p.add_argument("--ibkr-equities", type=float, default=346000)
    a = p.parse_args()
    acct = a.account or cl.default_account()

    os.makedirs(DIR, exist_ok=True)
    state_path = os.path.join(DIR, "state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"peaks": {}}

    meta = cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]
    total = cl.get(f"/portfolio/accounts/{acct}/total-stats")
    idle = total.get("total_unallocated_cash") or 0.0
    pending = total.get("pending_deploys_cash") or 0.0

    prev = None
    older = sorted(glob.glob(os.path.join(DIR, "snapshot-*.json")))
    last_path = os.path.join(DIR, "last-snapshot.json")  # git-tracked baseline
    if older:
        prev = json.load(open(older[-1]))
    elif os.path.exists(last_path):
        prev = json.load(open(last_path))

    now = datetime.datetime.now(datetime.timezone.utc)
    snap = {"taken_at": now.isoformat(timespec="seconds"),
            "total_stats": total,
            "symphonies": {}}
    alerts = []

    for s in meta:
        sid = s["id"]
        # deposit-adjusted value is comparable across deploys; raw value is not
        dep_val = s.get("deposit_adjusted_value") or s["value"]
        snap["symphonies"][sid] = {
            "name": s["name"], "value": s["value"],
            "deposit_adjusted_value": dep_val,
            "cash": s.get("cash"),
            "holdings": {h["ticker"]: round(h["allocation"], 4)
                         for h in s.get("holdings", [])},
            "next_rebalance_on": s.get("next_rebalance_on"),
            "has_queued_deploy": s.get("has_queued_deploy"),
            "last_percent_change": s.get("last_percent_change"),
        }
        label = f"{s['name'][:45]} [{sid[:8]}]"

        peak = max(state["peaks"].get(sid, 0.0), dep_val)
        state["peaks"][sid] = peak
        if peak > 0:
            dd = 1.0 - dep_val / peak
            if dd > a.dd_alert:
                alerts.append(f"DRAWDOWN {dd:.1%} from tracked peak — {label}")

        if prev and sid in prev.get("symphonies", {}):
            pv = prev["symphonies"][sid].get("deposit_adjusted_value")
            if pv:
                move = dep_val / pv - 1.0
                if abs(move) > a.move_alert:
                    alerts.append(f"MOVE {move:+.1%} since last snapshot — {label}")
            ph = prev["symphonies"][sid].get("holdings", {})
            nh = snap["symphonies"][sid]["holdings"]
            if set(ph) != set(nh):
                alerts.append(f"ROTATION {sorted(ph)} -> {sorted(nh)} — {label}")

        if s.get("has_queued_deploy"):
            alerts.append(f"QUEUED DEPLOY pending — {label}")
        if s.get("may_rebalance_today"):
            alerts.append(f"may rebalance today — {label}")

    if idle > 5000 and pending == 0:
        alerts.append(f"IDLE CASH ${idle:,.0f} unallocated — check POLICY.md "
                      "for a PENDING DEPOSIT block (deployment may be pre-authorized)")

    total_value = sum(s["value"] for s in meta)
    band = next((s for s in meta if s["id"] == a.band_symphony), None)
    if band and total_value > 0:
        crash_exposed = (total_value - band["value"]) + a.ibkr_equities
        w = band["value"] / (crash_exposed + band["value"])
        snap["sleeve_weight"] = round(w, 4)
        if w > a.band_hi:
            alerts.append(f"SLEEVE BAND BREACH: {w:.1%} > {a.band_hi:.1%} — "
                          f"harvest: trim {band['name'][:30]} back to target (sells the pop)")
        elif w < a.band_lo:
            alerts.append(f"SLEEVE BAND BREACH: {w:.1%} < {a.band_lo:.1%} — "
                          f"re-enter: top {band['name'][:30]} back up to target")

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    snap_path = os.path.join(DIR, f"snapshot-{stamp}.json")
    with open(snap_path, "w") as f:
        json.dump(snap, f, indent=2)
    with open(last_path, "w") as f:  # tracked copy — survives fresh clones
        json.dump(snap, f, indent=2)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    for old in sorted(glob.glob(os.path.join(DIR, "snapshot-*.json")))[:-a.keep]:
        os.remove(old)

    print(f"snapshot {stamp} — {len(meta)} symphonies, "
          f"portfolio value ${sum(s['value'] for s in meta):,.0f}")
    for sid, s in snap["symphonies"].items():
        hold = ", ".join(f"{t} {w:.0%}" for t, w in s["holdings"].items())
        print(f"  {s['name'][:52]} [{sid[:8]}]  ${s['value']:,.0f}  -> {hold}")
    if alerts:
        print(f"\n{len(alerts)} ALERT(S):")
        for al in alerts:
            print(f"  !! {al}")
        sys.exit(2)
    print("\nno alerts")


if __name__ == "__main__":
    main()
