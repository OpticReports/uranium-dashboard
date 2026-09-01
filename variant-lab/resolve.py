#!/usr/bin/env python3
"""Close the loop on variant-lab/ledger.csv — the half that never gets built.

venture-deal-analyzer/ledger.csv has 6 rows and 0 resolved outcomes because the
R1/R2 Routines that were supposed to score them were never created. BLUEPRINT.md
makes the closing loop a merge-blocking condition on the first row for exactly
that reason. This is that loop.

Keyless. Reads the ledger, resolves every OPEN row whose horizon has passed,
writes the outcome and the Brier score back, and prints a calibration summary.
Idempotent: re-running never double-resolves or changes a settled row.

    python3 variant-lab/resolve.py              # resolve + summary
    python3 variant-lab/resolve.py --dry-run    # show what would change
    python3 variant-lab/resolve.py --status     # summary only, no writes

Primitive grammar (column `primitive`), all resolving to a 0/1 outcome:
    P(<TICKER> >= <LEVEL> at <YYYY-MM-DD> close)
    P(<TICKER> <= <LEVEL> at <YYYY-MM-DD> close)
Anything else is left OPEN and reported as UNRESOLVABLE rather than guessed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LEDGER = Path(__file__).with_name("ledger.csv")
UA = "variant-lab-resolver/1.0 (research; keyless)"

# P(TLT >= 88.34 at 2026-12-18 close)
PRIMITIVE = re.compile(
    r"P\(\s*(?P<ticker>[A-Za-z0-9.^=-]+)\s*(?P<op>>=|<=)\s*(?P<level>[0-9.]+)\s*"
    r"at\s*(?P<on>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


class Unresolved(Exception):
    """The row cannot be settled yet, or not from a source we trust."""


def _fetch_closes(ticker: str, around: date) -> dict[date, float]:
    """Daily closes for a window around `around`. Keyless Yahoo chart endpoint —
    the same source treasury-canary/backend/app/sources/yahoo.py already uses.

    NOTE: `close`, deliberately not `adjclose`. Yahoo rewrites adjusted closes on
    every distribution, so a settled row scored against adjclose would silently
    change value after the fact. TLT pays monthly, so this matters here.
    """
    lo = int(datetime(around.year, around.month, around.day, tzinfo=timezone.utc).timestamp()) - 14 * 86400
    hi = lo + 40 * 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={lo}&period2={hi}&interval=1d")
    req = urllib.request.Request(url, headers={"user-agent": UA, "accept-encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            if r.headers.get("content-encoding") == "gzip":
                raw = gzip.decompress(raw)
        res = json.loads(raw)["chart"]["result"][0]
    except Exception as exc:  # noqa: BLE001
        raise Unresolved(f"price fetch failed for {ticker}: {exc}") from exc

    quote = res["indicators"]["quote"][0]
    out: dict[date, float] = {}
    for i, ts in enumerate(res["timestamp"]):
        close = quote["close"][i]
        if close is not None:
            out[datetime.fromtimestamp(ts, timezone.utc).date()] = float(close)
    if not out:
        raise Unresolved(f"no closes returned for {ticker}")
    return out


def settle(primitive: str, today: date) -> tuple[int, str]:
    """-> (outcome 0/1, evidence string). Raises Unresolved if it cannot settle."""
    m = PRIMITIVE.search(primitive or "")
    if not m:
        raise Unresolved("primitive does not match the supported grammar")
    on = date.fromisoformat(m.group("on"))
    if on > today:
        raise Unresolved(f"horizon {on} has not passed")

    ticker, level = m.group("ticker").upper(), float(m.group("level"))
    closes = _fetch_closes(ticker, on)

    # The exact session, or the last session on or before it (holidays/halts).
    eligible = [d for d in closes if d <= on]
    if not eligible:
        raise Unresolved(f"no session on or before {on}")
    settle_on = max(eligible)
    if (on - settle_on).days > 5:
        raise Unresolved(f"nearest session {settle_on} is >5d before {on} — refusing to settle")

    px = closes[settle_on]
    hit = px >= level if m.group("op") == ">=" else px <= level
    return int(hit), f"{ticker} closed {px:.4f} on {settle_on} vs {m.group('op')} {level:g}"


def brier(forecast_p: float, outcome: int) -> float:
    return (forecast_p - outcome) ** 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    ap.add_argument("--status", action="store_true", help="summary only, never writes")
    ap.add_argument("--today", help="override today (YYYY-MM-DD), for tests")
    args = ap.parse_args()
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()

    if not LEDGER.exists():
        print(f"no ledger at {LEDGER}", file=sys.stderr)
        return 1
    with LEDGER.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows, fields = list(reader), reader.fieldnames or []

    changed = 0
    for row in rows:
        if row.get("status", "").upper() != "OPEN":
            continue
        try:
            outcome, evidence = settle(row.get("primitive", ""), today)
        except Unresolved as exc:
            horizon = row.get("horizon_date", "?")
            # An expired row that still cannot be settled is a failure, not a shrug.
            try:
                overdue = date.fromisoformat(horizon) < today - timedelta(days=7)
            except ValueError:
                overdue = False
            level = "STALE" if overdue else "open"
            print(f"  [{level}] {row['row_id']:8s} horizon {horizon}: {exc}")
            continue

        p = float(row["forecast_p"])
        row["resolved_on"] = today.isoformat()
        row["outcome"] = str(outcome)
        row["brier"] = f"{brier(p, outcome):.4f}"
        row["status"] = "RESOLVED"
        row["notes"] = (row.get("notes", "") + f" || RESOLVED {today}: {evidence}").strip()
        changed += 1
        print(f"  [resolved] {row['row_id']}: outcome={outcome}  p={p:.2f}  "
              f"brier={row['brier']}  ({evidence})")

    if changed and not (args.dry_run or args.status):
        with LEDGER.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {changed} resolution(s) to {LEDGER}")
    elif changed:
        print(f"\n{changed} resolution(s) NOT written ({'--status' if args.status else '--dry-run'})")

    # ── calibration summary (R2) ──────────────────────────────────────────
    done = [r for r in rows if r.get("status", "").upper() == "RESOLVED" and r.get("brier")]
    open_rows = [r for r in rows if r.get("status", "").upper() == "OPEN"]
    print(f"\nledger: {len(rows)} row(s) — {len(done)} resolved, {len(open_rows)} open")
    if not done:
        print("calibration: nothing resolved yet. No skill claim is possible and none is made.")
        return 0

    mean_brier = sum(float(r["brier"]) for r in done) / len(done)
    mean_p = sum(float(r["forecast_p"]) for r in done) / len(done)
    hit = sum(int(r["outcome"]) for r in done) / len(done)
    ref = mean_p * (1 - mean_p)  # Brier of a constant forecast at our own mean
    bss = 1 - mean_brier / ref if ref > 0 else float("nan")
    print(f"  mean Brier          {mean_brier:.4f}")
    print(f"  mean forecast       {mean_p:.3f}   realised frequency {hit:.3f}")
    print(f"  calibration-in-large {abs(mean_p - hit) * 100:+.1f}pp   (BLUEPRINT bar: <= 18.6pp)")
    print(f"  Brier skill score   {bss:+.4f} vs a constant forecast")
    if len(done) < 30:
        print(f"\n  NOT statistically distinguishable from the constant — n={len(done)}.")
        print("  Per BLUEPRINT this is printed, never suppressed: no significance-based")
        print("  skill gate is reachable at ~35 independent forecasts/year.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
