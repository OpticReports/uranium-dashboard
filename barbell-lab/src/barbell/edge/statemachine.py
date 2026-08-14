"""Traffic-light state machine — BLUEPRINT §4, all rules pre-committed and
pinned (2026-08-14): return-CUSUM resets on entering YELLOW; YELLOW->GREEN
requires ALL FEEDS FRESH + 20 clean days (a blind feed cannot vacuously
recover); RED requires human re-promotion (never automatic — the lane that
makes the policy's null drag ~4x smaller must be operationally real, so RED
here only ever moves by Casey's hand via re_promote())."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import db

CLEAN_DAYS = 20
DUAL_CONFIRM_DAYS = 30


def _log(con, sid, frm, to, trigger, note=""):
    con.execute("INSERT INTO edge_state_log VALUES (?,?,?,?,?,?)",
                (sid, datetime.now(timezone.utc).isoformat(), frm, to,
                 trigger, note))


def step(con: sqlite3.Connection, sid: str, checks: list[dict],
         today: str | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date().isoformat()
    row = con.execute("SELECT state, size_mult FROM edge_strategies "
                      "WHERE strategy_id=?", (sid,)).fetchone()
    if row is None:
        return {"state": "UNREGISTERED"}
    state, size = row
    c = {x["metric"]: x for x in checks}

    esc_breaches = [x for x in checks
                    if x.get("escalates") and x["status"] == "breach"]
    blind = any(x["status"] == "blind" for x in checks) or \
        c.get("freshness", {}).get("status") == "breach"
    dd_red = c.get("dd_percentile", {}).get("red", False)

    # dual-confirmation bookkeeping. Stamps use the strategy's latest DATA
    # date, never the run date (referee: run-date stamps kept refreshing on
    # frozen data through blind outages), and are not written while RED.
    data_date = con.execute(
        "SELECT MAX(date) FROM edge_nav_daily WHERE strategy_id=?",
        (sid,)).fetchone()[0] or today
    if state != "RED":
        for m in ("return_cusum", "slip_cusum", "dd_percentile"):
            if c.get(m, {}).get("status") == "breach":
                db.kv_set(con, sid, f"last_breach_{m}", data_date)
    def _days_since(m):
        d = db.kv_get(con, sid, f"last_breach_{m}")
        if not d:
            return 10_000
        return (datetime.fromisoformat(today).date()
                - datetime.fromisoformat(d).date()).days
    dual = sum(_days_since(m) <= DUAL_CONFIRM_DAYS
               for m in ("return_cusum", "slip_cusum", "dd_percentile")) >= 2

    new_state, new_size, trigger = state, size, None
    if state != "RED":
        if dd_red or (state == "YELLOW" and dual):
            new_state, new_size = "RED", 0.0
            trigger = "dd_p99" if dd_red else "dual_confirmation"
        elif state == "GREEN" and (esc_breaches or blind):
            ramp = float(db.kv_get(con, sid, "ramp_level", 1.0))
            new_state, new_size = "YELLOW", round(0.5 * ramp, 4)
            trigger = "blind_feed" if blind and not esc_breaches else \
                esc_breaches[0]["metric"]
            # pinned rule: return-CUSUM resets on entering YELLOW
            n = con.execute("SELECT COUNT(*) FROM edge_nav_daily WHERE "
                            "strategy_id=? AND ret IS NOT NULL", (sid,)).fetchone()[0]
            db.kv_set(con, sid, "cusum_reset_i", n)
            db.kv_set(con, sid, "clean_days", 0)
        elif state == "YELLOW":
            half_ok = c.get("return_cusum", {}).get("half_threshold_ok", True)
            clean_today = (not esc_breaches) and (not blind) and half_ok
            clean = db.kv_get(con, sid, "clean_days", 0) + 1 if clean_today else 0
            db.kv_set(con, sid, "clean_days", clean)
            if clean >= CLEAN_DAYS:
                ramp = float(db.kv_get(con, sid, "ramp_level", 1.0))
                new_state, new_size = "GREEN", ramp
                trigger = "20_clean_days_feeds_fresh"
                for m in ("return_cusum", "slip_cusum", "dd_percentile"):
                    db.kv_set(con, sid, f"last_breach_{m}", None)

    if state == "GREEN" and new_state == "GREEN":
        ramp = float(db.kv_get(con, sid, "ramp_level", 1.0))
        if ramp < 1.0:
            ok_day = not esc_breaches and not blind
            g = db.kv_get(con, sid, "green_clean", 0) + 1 if ok_day else 0
            db.kv_set(con, sid, "green_clean", g)
            if g >= CLEAN_DAYS:
                ramp = min(1.0, ramp * 2)
                db.kv_set(con, sid, "ramp_level", ramp)
                db.kv_set(con, sid, "green_clean", 0)
                new_size = ramp
                con.execute("UPDATE edge_strategies SET size_mult=? "
                            "WHERE strategy_id=?", (ramp, sid))
                _log(con, sid, "GREEN", "GREEN", "ramp_advance",
                     f"ramp -> {ramp}")

    if new_state != state:
        con.execute("UPDATE edge_strategies SET state=?, size_mult=? "
                    "WHERE strategy_id=?", (new_state, new_size, sid))
        _log(con, sid, state, new_state, trigger or "?",
             "; ".join(f"{x['metric']}={x['status']}" for x in checks))
    con.commit()
    return {"state": new_state, "size_mult": new_size, "changed": new_state != state,
            "trigger": trigger, "blind": blind}


def re_promote(con: sqlite3.Connection, sid: str, note: str) -> None:
    """RED -> GREEN at ramp size 0.25. HUMAN-ONLY entry point (Casey's
    written rationale required in `note`); never called by the scheduler."""
    if not note or len(note) < 10:
        raise ValueError("re-promotion requires a written rationale")
    row = con.execute("SELECT state FROM edge_strategies WHERE strategy_id=?",
                      (sid,)).fetchone()
    if not row or row[0] != "RED":
        raise ValueError("re_promote only applies to RED strategies")
    con.execute("UPDATE edge_strategies SET state='GREEN', size_mult=0.25 "
                "WHERE strategy_id=?", (sid,))
    db.kv_set(con, sid, "ramp_level", 0.25)
    db.kv_set(con, sid, "green_clean", 0)
    for m in ("return_cusum", "slip_cusum", "dd_percentile"):
        db.kv_set(con, sid, f"last_breach_{m}", None)
    n = con.execute("SELECT COUNT(*) FROM edge_nav_daily WHERE strategy_id=? "
                    "AND ret IS NOT NULL", (sid,)).fetchone()[0]
    db.kv_set(con, sid, "cusum_reset_i", n)
    db.kv_set(con, sid, "clean_days", 0)
    _log(con, sid, "RED", "GREEN", "human_re_promotion", note)
    con.commit()
