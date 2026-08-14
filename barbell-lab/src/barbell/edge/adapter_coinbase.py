"""S5-live adapter: btc-executor /status -> canonical edge rows.

KEYLESS trading-wise; needs only EXEC_TOKEN (the executor's read-status
shared secret, sync:false env). Without it the feed is BLIND — reported as
a first-class condition, never a crash.

Sources inside /status:
- equity            -> today's NAV sample (one point per nightly run)
- marks[]           -> {d, equity} daily history: NAV BACKFILL (append-only;
                       disagreements with stored rows land in edge_revisions)
- fills[]           -> {ts, leg, role, cloid, side, px, ref_px, slip_bps}
                       (adverse-positive) -> edge_trades rows, trade_id=cloid+role
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

import httpx

from . import db

STRATEGY_ID = "S5-live"
STATUS_URL = os.environ.get("BTC_EXECUTOR_STATUS_URL",
                            "https://btc-executor.onrender.com/status")


class FeedBlind(RuntimeError):
    pass


def fetch_status() -> dict:
    token = os.environ.get("EXEC_TOKEN", "")
    if not token:
        raise FeedBlind("EXEC_TOKEN unset — executor feed blind")
    try:
        r = httpx.get(STATUS_URL, headers={"X-Exec-Token": token}, timeout=30.0)
        r.raise_for_status()
        out = r.json()
    except Exception as exc:  # noqa: BLE001
        raise FeedBlind(f"executor status unreachable: {exc}") from exc
    if not out.get("ready"):
        raise FeedBlind("executor not ready")
    return out


def sync(con: sqlite3.Connection, status: dict | None = None) -> dict:
    """Pull once, append-only. Returns a sync report incl. revision count."""
    db.ensure_schema(con)
    status = status or fetch_status()
    today = datetime.now(timezone.utc).date().isoformat()
    rep = {"nav": 0, "trades": 0, "revisions": 0, "blind": False}

    for m in status.get("marks", []):
        out = db.record_nav(con, STRATEGY_ID, m["d"], float(m["equity"]),
                            "executor_marks")
        rep["nav"] += out == "inserted"
        rep["revisions"] += out == "REVISION"
    eq = status.get("equity")
    if eq is not None:
        out = db.record_nav(con, STRATEGY_ID, today, float(eq), "executor_live")
        rep["nav"] += out == "inserted"
        rep["revisions"] += out == "REVISION"

    for f in status.get("fills", []):
        t = {"trade_id": f"{f.get('cloid', '?')}:{f.get('role', '?')}",
             "ts_utc": datetime.fromtimestamp(f["ts"], tz=timezone.utc).isoformat(),
             "side": f.get("side"), "fill_px": f.get("px"),
             "model_px": f.get("ref_px"), "slip_bps": f.get("slip_bps")}
        out = db.record_trade(con, STRATEGY_ID, t)
        rep["trades"] += out == "inserted"
        rep["revisions"] += out == "REVISION"

    con.execute("INSERT OR IGNORE INTO edge_strategies "
                "(strategy_id, venue, cadence) VALUES (?,?,?)",
                (STRATEGY_ID, "coinbase", "per_trade"))
    db.kv_set(con, STRATEGY_ID, "last_sync_utc",
              datetime.now(timezone.utc).isoformat())
    con.commit()
    return rep
