"""Nightly edge-monitor run: sync -> checks -> state machine -> one-liner.
Called from the barbell-lab nightly job after ingest/monitors/shadow.
Failures alert through the caller's existing job_failure path; a blind feed
is NOT a failure — it is a monitored condition (YELLOW)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from ..config import ROOT
from . import adapter_coinbase, baseline, db, layers, statemachine

# resolve via BARBELL_ROOT (container: /app) — a __file__-relative path
# pointed into site-packages in the image and broke the nightly job
FIXTURE = str(ROOT / "research" / "fixtures" / "s5_backtest_daily.json")
STRATEGIES = (adapter_coinbase.STRATEGY_ID,)


def ensure_registered(con: sqlite3.Connection) -> None:
    """One-time S5-live registration from the frozen replay fixture
    (idempotent: baseline_id is content-hashed)."""
    db.ensure_schema(con)
    con.execute("INSERT OR IGNORE INTO edge_strategies "
                "(strategy_id, venue, cadence) VALUES (?,?,?)",
                (adapter_coinbase.STRATEGY_ID, "coinbase", "per_trade"))
    base = baseline.load(con, adapter_coinbase.STRATEGY_ID)
    stale = base is not None and "periods_per_year" not in base
    if base is None or stale:
        # stale = registered by a pre-fix deploy (old dd statistic/calendar);
        # re-register so the frozen null matches the machine actually running
        fx = json.load(open(os.path.normpath(FIXTURE)))
        bid = baseline.register(con, adapter_coinbase.STRATEGY_ID, fx)
        con.execute("INSERT INTO alerts (ts_utc, kind, message, details) "
                    "VALUES (?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), "edge_baseline",
                     f"edge baseline frozen for S5-live: {bid}", "{}"))
        con.commit()


def run_nightly(con: sqlite3.Connection) -> str:
    ensure_registered(con)
    lines = []
    for sid in STRATEGIES:
        try:
            adapter_coinbase.sync(con)
        except adapter_coinbase.FeedBlind as exc:
            con.execute("INSERT INTO alerts (ts_utc, kind, message, details) "
                        "VALUES (?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), "edge_blind",
                         f"{sid} feed blind: {exc}", "{}"))
            con.commit()
        checks = layers.run_daily(con, sid)
        sm = statemachine.step(con, sid, checks)
        bits = []
        for c in checks:
            if c["status"] == "breach":
                bits.append(f"{c['metric']}!")
            elif c["status"] in ("insufficient", "blind"):
                bits.append(f"{c['metric']}:{c['status'][:5]}")
        line = (f"EDGE {sid}: {sm.get('state', '?')} x{sm.get('size_mult', '?')} "
                + (" ".join(bits) or "all ok"))
        lines.append(line)
        if sm.get("changed"):
            news = ""
            try:
                # descriptive context only (canary news pulse; Tiingo lane) -
                # helps the human triage, feeds NO decision
                import httpx
                pulse = httpx.get("https://treasury-canary.onrender.com"
                                  "/news/pulse", timeout=10).json()
                btc = (pulse.get("themes") or {}).get("btc") or {}
                heads = [h["title"] for h in btc.get("latest", [])[:3]]
                if heads:
                    news = (f" | btc news 24h n={btc.get('n_24h')} "
                            f"z={btc.get('velocity_z')}: " + " / ".join(heads))
            except Exception:  # noqa: BLE001
                pass
            con.execute("INSERT INTO alerts (ts_utc, kind, message, details) "
                        "VALUES (?,?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), "edge_state",
                         f"{sid} -> {sm['state']} (trigger {sm['trigger']}); "
                         f"apply size_mult {sm['size_mult']} via the "
                         f"executor's own controls{news}", json.dumps(sm)))
            con.commit()
    return " | ".join(lines)


def board(con: sqlite3.Connection) -> dict:
    """/api/edge payload."""
    db.ensure_schema(con)
    out = {"strategies": {}}
    for sid in STRATEGIES:
        row = con.execute("SELECT state, size_mult, baseline_id FROM "
                          "edge_strategies WHERE strategy_id=?", (sid,)).fetchone()
        if row is None:
            out["strategies"][sid] = {"registered": False}
            continue
        base = baseline.load(con, sid)
        checks = con.execute(
            "SELECT metric, value, threshold, breach, note FROM edge_checks "
            "WHERE strategy_id=? AND date=(SELECT MAX(date) FROM edge_checks "
            "WHERE strategy_id=?)", (sid, sid)).fetchall()
        out["strategies"][sid] = {
            "registered": True, "state": row[0], "size_mult": row[1],
            "baseline": {k: base.get(k) for k in
                         ("baseline_id", "sr_annual", "mintrl_days", "dsr",
                          "n_trials", "trials_basis", "policy_mc")} if base else None,
            "latest_checks": [{"metric": c[0], "value": c[1], "threshold": c[2],
                               "breach": bool(c[3]), "note": c[4]} for c in checks],
            "unresolved_revisions": db.unresolved_revisions(con, sid),
            "state_log": [dict(zip(("ts", "from", "to", "trigger"), r)) for r in
                          con.execute("SELECT ts_utc, from_state, to_state, trigger "
                                      "FROM edge_state_log WHERE strategy_id=? "
                                      "ORDER BY ts_utc DESC LIMIT 10", (sid,))],
        }
    return out
