#!/usr/bin/env python3
"""Pre-market rebalance digest: what would my symphonies trade today?

Combines:
  - GET  /deploy/market-hours          — is the market open, next session
  - GET  .../symphony-stats-meta       — which symphonies may rebalance today
  - POST /dry-run                      — Composer's own rebalance simulation
  - POST /dry-run/trade-preview/{id}   — per-symphony trade preview (amount 0)

All simulation endpoints — nothing is queued or executed.

Usage: rebalance-digest.py [--account UUID] [--previews] [--name rebalance-digest]
  --previews additionally pulls a per-symphony trade preview (1 API call each).
"""

import argparse
import json
import composerlib as cl


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account")
    p.add_argument("--previews", action="store_true")
    p.add_argument("--name", default="rebalance-digest")
    a = p.parse_args()
    acct = a.account or cl.default_account()

    hours = cl.get("/deploy/market-hours")["market_hours"]
    today = hours[0] if hours else {}
    print(f"market: {'OPEN' if today.get('is_market_open') else 'closed'} "
          f"({today.get('nyse_market_date')})", end="")
    nxt = next((h for h in hours if h.get("is_market_open")), None)
    if nxt and not today.get("is_market_open"):
        print(f"; next session {nxt.get('nyse_market_date')}", end="")
    print("\n")

    meta = cl.get(f"/portfolio/accounts/{acct}/symphony-stats-meta")["symphonies"]
    print("invested symphonies:")
    for s in meta:
        flags = []
        if s.get("may_rebalance_today"):
            flags.append("MAY REBALANCE TODAY")
        if s.get("skip_rebalance_today"):
            flags.append("skip requested")
        if s.get("has_queued_deploy"):
            flags.append("QUEUED DEPLOY")
        holdings = ", ".join(f"{h['ticker']} {h['allocation']:.0%}"
                             for h in s.get("holdings", [])[:6])
        print(f"  {s['name'][:58]} [{s['id'][:8]}]")
        print(f"      ${s['value']:,.0f}  freq={s['rebalance_frequency']}  "
              f"next={s.get('next_rebalance_on')}  "
              f"{'  '.join(flags) if flags else ''}")
        print(f"      now holding: {holdings}")

    dry = cl.post("/dry-run", {"account_uuids": [acct], "send_segment_event": False})
    print(f"\ndry-run rebalance simulation: "
          f"{len(dry) if isinstance(dry, list) else 1} pending action(s)")
    if dry:
        print(json.dumps(dry, indent=2)[:3000])

    previews = {}
    if a.previews:
        print("\ntrade previews (amount=0 → pure rebalance trades):")
        for s in meta:
            try:
                pv = cl.post(f"/dry-run/trade-preview/{s['id']}",
                             {"amount": 0, "broker_account_uuid": acct})
                previews[s["id"]] = pv
                blob = json.dumps(pv)
                print(f"  {s['id'][:8]} {s['name'][:40]}: {blob[:400]}")
            except SystemExit as e:
                msg = str(e)
                if "dry-run-markets-closed" in msg:
                    msg = "market closed — previews only work during trading hours"
                previews[s["id"]] = {"error": msg}
                print(f"  {s['id'][:8]} {s['name'][:40]}: {msg}")

    cl.write_json(f"composer/results/{a.name}.json",
                  {"market_hours": hours[:3],
                   "symphonies": [{k: s.get(k) for k in
                                   ("id", "name", "value", "rebalance_frequency",
                                    "next_rebalance_on", "may_rebalance_today",
                                    "skip_rebalance_today", "has_queued_deploy")}
                                  for s in meta],
                   "dry_run": dry, "previews": previews})


if __name__ == "__main__":
    main()
