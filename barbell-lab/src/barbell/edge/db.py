"""edge-monitor store (BLUEPRINT.md §2) inside barbell-lab's SQLite.

Integrity law (referee 2026-08-14, F7): nav_daily and trades are
APPEND-ONLY through record_* helpers. A re-pull that disagrees with a
stored row never overwrites it — the conflict lands in edge_revisions and
surfaces as a data-integrity flag. NAV restatements are the #1 source of
spurious dual-confirmation REDs; they must scream, not merge.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS edge_strategies (
    strategy_id TEXT PRIMARY KEY, venue TEXT NOT NULL, cadence TEXT NOT NULL,
    inception TEXT, baseline_id TEXT, state TEXT NOT NULL DEFAULT 'GREEN',
    size_mult REAL NOT NULL DEFAULT 1.0);
CREATE TABLE IF NOT EXISTS edge_trades (
    strategy_id TEXT NOT NULL, trade_id TEXT NOT NULL, ts_utc TEXT NOT NULL,
    side TEXT, qty REAL, notional_usd REAL, fill_px REAL, model_px REAL,
    slip_bps REAL, fees_usd REAL, pnl_usd REAL,
    PRIMARY KEY (strategy_id, trade_id));
CREATE TABLE IF NOT EXISTS edge_nav_daily (
    strategy_id TEXT NOT NULL, date TEXT NOT NULL, nav REAL NOT NULL,
    ret REAL, source TEXT NOT NULL,
    PRIMARY KEY (strategy_id, date));
CREATE TABLE IF NOT EXISTS edge_baselines (
    baseline_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL,
    frozen_at TEXT NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edge_checks (
    strategy_id TEXT NOT NULL, date TEXT NOT NULL, layer TEXT NOT NULL,
    metric TEXT NOT NULL, value REAL, threshold REAL, breach INTEGER,
    note TEXT, PRIMARY KEY (strategy_id, date, metric));
CREATE TABLE IF NOT EXISTS edge_state_log (
    strategy_id TEXT NOT NULL, ts_utc TEXT NOT NULL, from_state TEXT,
    to_state TEXT, trigger TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS edge_kv (
    strategy_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    PRIMARY KEY (strategy_id, key));
CREATE TABLE IF NOT EXISTS edge_revisions (
    strategy_id TEXT NOT NULL, table_name TEXT NOT NULL, row_key TEXT NOT NULL,
    stored TEXT NOT NULL, incoming TEXT NOT NULL, seen_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0, resolution_note TEXT);
"""

REL_TOL = 1e-9


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(_SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_nav(con: sqlite3.Connection, strategy_id: str, date: str,
               nav: float, source: str) -> str:
    """'inserted' | 'unchanged' | 'REVISION'. Never overwrites."""
    row = con.execute("SELECT nav FROM edge_nav_daily WHERE strategy_id=? AND date=?",
                      (strategy_id, date)).fetchone()
    if row is None:
        prev = con.execute(
            "SELECT nav FROM edge_nav_daily WHERE strategy_id=? AND date<? "
            "ORDER BY date DESC LIMIT 1", (strategy_id, date)).fetchone()
        ret = nav / prev[0] - 1.0 if prev and prev[0] else None
        con.execute("INSERT INTO edge_nav_daily VALUES (?,?,?,?,?)",
                    (strategy_id, date, nav, ret, source))
        return "inserted"
    if abs(row[0] - nav) <= REL_TOL * max(abs(row[0]), 1.0):
        return "unchanged"
    con.execute("INSERT INTO edge_revisions (strategy_id, table_name, "
                "row_key, stored, incoming, seen_at) VALUES (?,?,?,?,?,?)",
                (strategy_id, "edge_nav_daily", date,
                 json.dumps({"nav": row[0]}), json.dumps({"nav": nav}), _now()))
    return "REVISION"


def record_trade(con: sqlite3.Connection, strategy_id: str, t: dict) -> str:
    row = con.execute(
        "SELECT slip_bps, fill_px FROM edge_trades WHERE strategy_id=? AND trade_id=?",
        (strategy_id, t["trade_id"])).fetchone()
    if row is None:
        con.execute(
            "INSERT INTO edge_trades VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (strategy_id, t["trade_id"], t["ts_utc"], t.get("side"),
             t.get("qty"), t.get("notional_usd"), t.get("fill_px"),
             t.get("model_px"), t.get("slip_bps"), t.get("fees_usd"),
             t.get("pnl_usd")))
        return "inserted"
    if (abs((row[0] or 0) - (t.get("slip_bps") or 0)) <= 1e-6
            and abs((row[1] or 0) - (t.get("fill_px") or 0)) <= 1e-6):
        return "unchanged"
    con.execute("INSERT INTO edge_revisions (strategy_id, table_name, "
                "row_key, stored, incoming, seen_at) VALUES (?,?,?,?,?,?)",
                (strategy_id, "edge_trades", t["trade_id"],
                 json.dumps({"slip_bps": row[0], "fill_px": row[1]}),
                 json.dumps({"slip_bps": t.get("slip_bps"),
                             "fill_px": t.get("fill_px")}), _now()))
    return "REVISION"


def unresolved_revisions(con: sqlite3.Connection, strategy_id: str) -> int:
    return con.execute("SELECT COUNT(*) FROM edge_revisions WHERE strategy_id=? "
                       "AND resolved=0", (strategy_id,)).fetchone()[0]


def resolve_revisions(con: sqlite3.Connection, strategy_id: str,
                      note: str) -> int:
    """HUMAN-ONLY acknowledgement of investigated revisions (like
    re_promote: a written rationale is mandatory — this is the only exit
    from a data-integrity YELLOW, so it must never be automatic)."""
    if not note or len(note) < 10:
        raise ValueError("revision resolution requires a written rationale")
    cur = con.execute("UPDATE edge_revisions SET resolved=1, resolution_note=? "
                      "WHERE strategy_id=? AND resolved=0", (note, strategy_id))
    con.commit()
    return cur.rowcount


def kv_get(con: sqlite3.Connection, strategy_id: str, key: str, default=None):
    r = con.execute("SELECT value FROM edge_kv WHERE strategy_id=? AND key=?",
                    (strategy_id, key)).fetchone()
    return json.loads(r[0]) if r else default


def kv_set(con: sqlite3.Connection, strategy_id: str, key: str, value) -> None:
    con.execute("INSERT INTO edge_kv VALUES (?,?,?) ON CONFLICT(strategy_id,key) "
                "DO UPDATE SET value=excluded.value",
                (strategy_id, key, json.dumps(value)))
