"""Operator tool: quarantine broken slippage measurements on the LIVE db.

Why a CLI and not an automatic rule: quarantining rows is the one edge-monitor
operation that can make a decaying strategy look healthy. It stays a
deliberate, human, rationale-carrying act (same posture as
db.resolve_revisions), so it lives here rather than in the nightly run.

Origin: the 2026-08-26 phantom-position incident wrote two chase fills at
1320bps of "slippage" measured against a days-stale reference price - one of
which never executed at all. btc-executor now marks such fills `void` and the
S5 adapter skips them, but that only stops RE-ingestion; rows already in
edge_trades (and any slip_norms frozen from them) still had to be cleaned.
Those norms gate the CUSUM that authorizes KELLY_M sizing.

Usage (read-only by default - ALWAYS look before you purge):

    python -m barbell.edge.purge_cli --db /path/to/barbell.db
    python -m barbell.edge.purge_cli --db ... --apply \
        --note "2026-08-26 phantom incident: ref_px days-stale, one fill never happened"

Add --strategy to target something other than S5-live, --threshold to change
the |slip_bps| cutoff (default 500, matching the executor's void rule), or
--trade-id (repeatable) to name rows explicitly instead of scanning.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from . import db
from .adapter_coinbase import STRATEGY_ID


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="barbell.edge.purge_cli")
    ap.add_argument("--db", required=True, help="path to the sqlite db")
    ap.add_argument("--strategy", default=STRATEGY_ID)
    ap.add_argument("--threshold", type=float, default=500.0,
                    help="|slip_bps| above which a row is a candidate")
    ap.add_argument("--trade-id", action="append", default=[],
                    help="quarantine these exact ids instead of scanning")
    ap.add_argument("--apply", action="store_true",
                    help="actually quarantine (default: dry run)")
    ap.add_argument("--note", default="",
                    help="written rationale, >=10 chars; required with --apply")
    a = ap.parse_args(argv)

    con = sqlite3.connect(a.db)
    db.ensure_schema(con)          # also runs the quarantine-column migration

    if a.trade_id:
        ids = list(a.trade_id)
        rows = [{"trade_id": i, "note": "named explicitly"} for i in ids]
    else:
        rows = db.find_absurd_slippage(con, a.strategy, a.threshold)
        ids = [r["trade_id"] for r in rows]

    norms = db.kv_get(con, a.strategy, "slip_norms")
    total = con.execute(
        "SELECT COUNT(*) FROM edge_trades WHERE strategy_id=? AND quarantined=0",
        (a.strategy,)).fetchone()[0]
    already = con.execute(
        "SELECT COUNT(*) FROM edge_trades WHERE strategy_id=? AND quarantined=1",
        (a.strategy,)).fetchone()[0]

    print(json.dumps({"strategy": a.strategy, "db": a.db,
                      "clean_rows": total, "already_quarantined": already,
                      "candidates": rows,
                      "slip_norms_currently_frozen": norms}, indent=2,
                     default=str))

    if not a.apply:
        print("\nDRY RUN - nothing changed. Re-run with --apply --note '...' "
              "to quarantine the candidates above.", file=sys.stderr)
        return 0
    if not ids:
        print("\nnothing to quarantine.", file=sys.stderr)
        return 0
    try:
        rep = db.quarantine_trades(con, a.strategy, ids, a.note)
    except ValueError as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        return 2
    print("\n" + json.dumps(rep, indent=2))
    if rep["slip_norms_dropped"]:
        print("slip_norms dropped - they re-freeze from the surviving rows on "
              "the next run_daily once >=10 clean trades exist.", file=sys.stderr)
    return 0


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(main())
