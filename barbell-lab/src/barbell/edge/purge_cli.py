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
import os
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

    # REFUSE a path that is not already a database. sqlite happily CREATES
    # an empty file, so a mistyped --db used to print "0 candidates, nothing
    # quarantined, slip_norms null" and exit 0 — which reads exactly like
    # "the live DB is clean". That is the worst possible failure for the one
    # command an operator runs at 2am against real money (panel 2026-08-27).
    if not os.path.isfile(a.db):
        print(f"REFUSED: {a.db} does not exist. sqlite would silently create "
              f"an empty DB and this tool would report it clean.",
              file=sys.stderr)
        return 2
    con = sqlite3.connect(a.db)
    if not con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                       "AND name='edge_trades'").fetchone():
        print(f"REFUSED: {a.db} has no edge_trades table — this is not the "
              f"edge-monitor database.", file=sys.stderr)
        return 2
    db.ensure_schema(con)          # also runs the quarantine-column migration

    if a.trade_id:
        # RESOLVE named ids against the DB (2026-08-27 panel, BINDING): a
        # typo used to be quarantined silently - rc 0, "success" printed, and
        # the append-only audit row naming an id that matched nothing, while
        # the row the operator meant to purge survived.
        ids = list(a.trade_id)
        found = {r[0]: r for r in con.execute(
            f"SELECT trade_id, ts_utc, slip_bps, quarantined FROM edge_trades "
            f"WHERE strategy_id=? AND trade_id IN ({','.join('?' * len(ids))})",
            (a.strategy, *ids))}
        rows = [{"trade_id": i,
                 "ts_utc": found[i][1] if i in found else None,
                 "slip_bps": found[i][2] if i in found else None,
                 "status": ("already quarantined" if i in found and found[i][3]
                            else "found" if i in found else "MISSING")}
                for i in ids]
        missing = [r["trade_id"] for r in rows if r["status"] == "MISSING"]
    else:
        rows = db.find_absurd_slippage(con, a.strategy, a.threshold)
        ids = [r["trade_id"] for r in rows]
        missing = []

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

    if missing:
        print(f"\nREFUSED: {len(missing)} named trade_id(s) do not exist on "
              f"this strategy: {missing}\nNothing was changed. trade_id is "
              f"'<cloid>:<role>' - check the ids and re-run.", file=sys.stderr)
        return 2
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
    if rep.get("cusum_reset_i_restored") is not None:
        print(f"cusum_reset_i RESTORED to {rep['cusum_reset_i_restored']}: the "
              f"purged rows had driven a YELLOW transition that erased the "
              f"return-CUSUM history. That evidence is back.", file=sys.stderr)
    if rep.get("unresolved_residue"):
        # rc 3, not 0: the purge succeeded but the account is NOT safe to
        # size on until a human resolves this. Exiting 0 here is how the
        # 'quarantine silently re-authorizes size' path stayed invisible.
        print("\n*** UNRESOLVED RESIDUE - DO NOT TRUST CLEAN-DAY COUNTS ***",
              file=sys.stderr)
        for r in rep["unresolved_residue"]:
            print(f"  - {r}", file=sys.stderr)
        print("Resolve by hand before the next run_daily, or the state "
              "machine may promote on evidence that was destroyed.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":            # pragma: no cover
    raise SystemExit(main())
