#!/usr/bin/env python3
"""Operator drill runner (RAMP v4) — fires the drillable coverage rows.

Drills are the ONLY rows money can buy: the entry/exit/chase/post_only_cross
rows are organic-only by design (a drill entry is a market order; organic
entries run the limit + post-only + chase machinery, and only the real path
proves the real path). This script closes the rest:

    drill_cycle >= 3 · stop_placed >= 2 · stop_filled >= 1 · slippage >= 10 fills

Cost ~= spread + taker fees ~ $1-2 per drill, one venue contract (0.01 BTC),
hard-bounded in code — no parameter here can raise the size.

Usage:
    EXEC_TOKEN=... python3 scripts/run_drills.py [--url URL] [--cycles N]
                                                 [--stopfill] [--wait-mins M]

The executor refuses a drill unless BOTH legs are flat and the venue position
is ~0, so this waits for a flat book rather than forcing anything. It never
retries a refusal that is not a timing issue (halted, budget exhausted).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "https://btc-executor.onrender.com"
# server-side default; a drill inside the window is refused with "cooldown"
COOLDOWN_S = 300


def _get(url: str, token: str | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(url)
    if token:
        req.add_header("X-Exec-Token", token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _post(url: str, token: str, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("X-Exec-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http_error": exc.code,
                "body": exc.read().decode()[:400]}


def flat(pulse: dict) -> bool:
    return all(not l["in_position"] and not l["entry_open"]
               for l in pulse["legs"].values())


def wait_for_flat(url: str, max_mins: int) -> bool:
    deadline = time.time() + max_mins * 60
    announced = False
    while time.time() < deadline:
        p = _get(f"{url}/pulse")
        if p.get("halted"):
            print(f"  ! executor HALTED ({p['halted']}) — drills refuse while "
                  f"halted; resolve the halt first")
            return False
        if flat(p):
            return True
        if not announced:
            busy = [n for n, l in p["legs"].items()
                    if l["in_position"] or l["entry_open"]]
            print(f"  … book not flat ({', '.join(busy)} open) — waiting; "
                  f"drills cannot touch a real position")
            announced = True
        time.sleep(30)
    return False


def coverage_rows(url: str, token: str) -> dict:
    st = _get(f"{url}/status", token)
    rv = st.get("ramp_v4", {})
    return rv.get("rows", {}), rv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("EXEC_URL", DEFAULT_URL))
    ap.add_argument("--cycles", type=int, default=3,
                    help="cycle drills to run (spec needs 3)")
    ap.add_argument("--stopfill", action="store_true", default=True,
                    help="also run one stopfill drill (spec needs 1)")
    ap.add_argument("--wait-mins", type=int, default=45,
                    help="how long to wait for a flat book before giving up")
    a = ap.parse_args()

    token = os.environ.get("EXEC_TOKEN", "")
    if not token:
        print("EXEC_TOKEN not set — /drill is token-gated. Export it from the "
              "Render dashboard and re-run.", file=sys.stderr)
        return 2

    pulse = _get(f"{a.url}/pulse")
    print(f"executor: dry_run={pulse['dry_run']} halted={pulse['halted']} "
          f"ramp_v4={pulse['ramp_v4_met']}")
    if pulse["dry_run"]:
        print("\nREFUSING: DRY_RUN=true. Drills would run against DryRunVenue "
              "and prove nothing about the venue — synthetic fills cannot "
              "satisfy a coverage row. Flip DRY_RUN in Render first.",
              file=sys.stderr)
        return 3
    if "ramp_v4_unattributed" not in pulse:
        print("\nWARNING: this executor predates the coverage mode guard. "
              "Drills fired now record NO provenance, so they will read as "
              "unattributed once the guard deploys — i.e. wasted. Deploy "
              "first, then drill.", file=sys.stderr)
        if input("proceed anyway? [y/N] ").strip().lower() != "y":
            return 4

    plan = [("cycle", i + 1) for i in range(a.cycles)]
    if a.stopfill:
        plan.append(("stopfill", 1))

    print(f"\nplan: {a.cycles} x cycle + {1 if a.stopfill else 0} x stopfill "
          f"(~${2 * len(plan)} worst case, {COOLDOWN_S // 60}min cooldown "
          f"between)\n")

    for n, (kind, i) in enumerate(plan):
        print(f"[{n + 1}/{len(plan)}] drill {kind} #{i}")
        if not wait_for_flat(a.url, a.wait_mins):
            print("  ! no flat window — stopping cleanly; rerun later",
                  file=sys.stderr)
            return 5
        res = _post(f"{a.url}/drill?kind={kind}", token)
        if not res.get("ok", True) or res.get("refused"):
            print(f"  ! refused: {res.get('refused') or res}")
            if str(res.get("refused", "")).startswith(("halted",
                                                       "daily_budget")):
                return 6
        else:
            print(f"  ✓ {json.dumps(res)[:300]}")
        if n < len(plan) - 1:
            print(f"  … cooldown {COOLDOWN_S}s")
            time.sleep(COOLDOWN_S + 5)

    rows, rv = coverage_rows(a.url, token)
    print("\ncoverage after drills "
          f"({sum(r['met'] for r in rows.values())}/{len(rows)}):")
    for k, r in rows.items():
        extra = ""
        if r.get("unattributed"):
            extra = f"  [{r['unattributed']} unattributed]"
        print(f"  {'✓' if r['met'] else '·'} {k:<22} "
              f"{r['have']}/{r['need']}{extra}")
    organic = [k for k, r in rows.items() if not r["met"]]
    if organic:
        print(f"\nremaining (organic cadence 2-4 signals/wk): "
              f"{', '.join(organic)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
