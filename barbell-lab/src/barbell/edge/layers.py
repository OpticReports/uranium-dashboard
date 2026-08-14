"""Layer-1 daily checks. Contract (BLUEPRINT §6): every check returns a dict
with status in {"ok","breach","insufficient","blind"} — insufficiency is a
first-class output; silence is banned.

Escalation gates (frozen): return CUSUM can escalate state only after 60
live days (logs before that); slippage after 10 trades; DD after 5 days.
Behavior-drift and vol-band are INFORMATIONAL ONLY (referee F3a: ops
tripwire, not a detector).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone

import numpy as np

from . import baseline as bl
from . import db, dd_percentile

MIN_RET_DAYS, MIN_SLIP_TRADES, MIN_DD_DAYS = 60, 10, 5
FRESH_MAX_DAYS = 2
SLIP_K_SIGMA, SLIP_ARL_TRADES = 0.5, 200.0


def _live_returns(con, sid) -> np.ndarray:
    rows = con.execute(
        "SELECT ret FROM edge_nav_daily WHERE strategy_id=? AND ret IS NOT NULL "
        "ORDER BY date", (sid,)).fetchall()
    return np.array([r[0] for r in rows], dtype=float)


def check_freshness(con, sid, today) -> dict:
    last = db.kv_get(con, sid, "last_sync_utc")
    nav = con.execute("SELECT MAX(date) FROM edge_nav_daily WHERE strategy_id=?",
                      (sid,)).fetchone()[0]
    if last is None or nav is None:
        return {"metric": "freshness", "status": "blind", "note": "never synced"}
    age = (datetime.fromisoformat(today).date()
           - datetime.fromisoformat(nav).date()).days
    return {"metric": "freshness", "status": "breach" if age > FRESH_MAX_DAYS else "ok",
            "value": age, "threshold": FRESH_MAX_DAYS,
            "note": f"nav age {age}d", "escalates": True}


def check_revisions(con, sid) -> dict:
    n = db.unresolved_revisions(con, sid)
    return {"metric": "data_integrity", "status": "breach" if n else "ok",
            "value": n, "threshold": 0, "escalates": True,
            "note": "vendor/NAV revisions detected — investigate before "
                    "trusting any other alarm" if n else "append-only clean"}


def check_return_cusum(con, sid, base) -> dict:
    r = _live_returns(con, sid)
    if len(r) < MIN_RET_DAYS:
        return {"metric": "return_cusum", "status": "insufficient",
                "value": len(r), "threshold": MIN_RET_DAYS,
                "note": f"n={len(r)} of {MIN_RET_DAYS} before escalation"}
    cal = base["cusum"]
    # standardize by the FROZEN baseline moments; recompute the statistic
    # from zero each run (cheap, and self-healing after data fixes) starting
    # from the last state-machine reset point (pinned reset-on-YELLOW rule)
    reset_i = int(db.kv_get(con, sid, "cusum_reset_i", 0))
    z = (r[reset_i:] - base["mu_daily"]) / base["std_daily"]
    s = 0.0
    for zi in z:
        s = max(0.0, s + (-zi) - cal["k"])
    db.kv_set(con, sid, "cusum_s", float(s))
    return {"metric": "return_cusum", "status": "breach" if s > cal["h"] else "ok",
            "value": round(float(s), 3), "threshold": cal["h"], "escalates": True,
            "half_threshold_ok": bool(s < cal["h"] / 2),
            "note": f"ARL {cal['target_arl']}d, k={cal['k']}, "
                    f"since reset idx {reset_i}"}


def check_dd(con, sid, base) -> dict:
    r = _live_returns(con, sid)
    if len(r) < MIN_DD_DAYS:
        return {"metric": "dd_percentile", "status": "insufficient",
                "value": len(r), "threshold": MIN_DD_DAYS,
                "note": f"n={len(r)} of {MIN_DD_DAYS}"}
    grid = base["dd_grid"]
    Ls = sorted(int(g) for g in grid if not g.startswith("_"))
    # CEILING match (referee: floor was anti-conservative between steps)
    L = min([l for l in Ls if l >= len(r)] or [Ls[-1]])
    # equity anchored at 1.0 (referee: unanchored cumprod made a first-day
    # crash invisible), and the escalation statistic is the CURRENT
    # underwater depth — recoverable, and the SAME statistic the certified
    # policy MC triggers on (referee bug 3 / F1: all-time worst was
    # permanent, so dd-REDs could never be re-promoted and the budget
    # certified a different machine than shipped)
    eq = np.concatenate([[1.0], np.cumprod(1 + r)])
    dd = eq / np.maximum.accumulate(eq) - 1.0
    cur, worst = float(dd[-1]), float(dd.min())
    g = grid[str(L)]
    status = "breach" if cur <= g["p95"] else "ok"
    return {"metric": "dd_percentile", "status": status,
            "value": round(cur, 4), "threshold": g["p95"], "escalates": True,
            "red": bool(cur <= g["p99"]), "all_time_worst": round(worst, 4),
            "note": f"current underwater vs length-matched grid L={L} "
                    f"(p99 {g['p99']:.3f}; all-time worst {worst:.3f} info-only)"}


def check_slippage(con, sid, base) -> dict:
    rows = con.execute(
        "SELECT slip_bps FROM edge_trades WHERE strategy_id=? AND slip_bps "
        "IS NOT NULL ORDER BY ts_utc", (sid,)).fetchall()
    slips = np.array([r[0] for r in rows], dtype=float)
    if len(slips) < MIN_SLIP_TRADES:
        return {"metric": "slip_cusum", "status": "insufficient",
                "value": len(slips), "threshold": MIN_SLIP_TRADES,
                "note": f"n={len(slips)} of {MIN_SLIP_TRADES}"}
    slip = base.get("slip")
    if not slip:
        # freeze slip norms from the FIRST MIN_SLIP_TRADES trades (declared)
        ref = slips[:MIN_SLIP_TRADES]
        slip = {"mean": float(ref.mean()), "sd": float(ref.std(ddof=1) or 1.0),
                "frozen_on_first_n": MIN_SLIP_TRADES}
        base["slip"] = slip
        db.kv_set(con, sid, "slip_norms", slip)
    z = (slips - slip["mean"]) / slip["sd"]
    # one-sided upward CUSUM (slippage worse = higher adverse bps).
    # h=3.5: referee-measured ARL0 ~= 200 trades at k=0.5 on Gaussian slips
    # (the first-shipped h=6.0 actually gave ARL0 ~2,447 — 12x the claim)
    s, h = 0.0, 3.5
    for zi in z[len(z) - min(len(z), 400):]:
        s = max(0.0, s + zi - SLIP_K_SIGMA)
    return {"metric": "slip_cusum", "status": "breach" if s > h else "ok",
            "value": round(s, 2), "threshold": h, "escalates": True,
            "note": f"norms {slip['mean']:.1f}±{slip['sd']:.1f}bps "
                    f"(frozen on first {MIN_SLIP_TRADES})"}


def check_vol_band(con, sid, base) -> dict:
    r = _live_returns(con, sid)
    if len(r) < 20:
        return {"metric": "vol_band", "status": "insufficient", "value": len(r),
                "threshold": 20, "note": "needs 20d"}
    ppy = base.get("periods_per_year", 252)
    v = float(np.std(r[-20:], ddof=1) * math.sqrt(ppy))
    band = base["dd_grid"]["_vol_band_ann"]
    out = not (band["p01"] <= v <= band["p99"])
    return {"metric": "vol_band", "status": "breach" if out else "ok",
            "value": round(v, 4), "escalates": False,   # regime flag only
            "note": f"backtest band [{band['p01']:.2f},{band['p99']:.2f}] — "
                    "informational, never sizes alone"}


def check_behavior(con, sid, base) -> dict:
    """Ops tripwire (informational): live trade RATE vs backtest trade rate.
    A strategy suddenly trading 3x more/less than its backtest changed
    upstream, whatever the P&L says."""
    n_tr = con.execute(
        "SELECT COUNT(*) FROM edge_trades WHERE strategy_id=?", (sid,)).fetchone()[0]
    n_days = con.execute(
        "SELECT COUNT(*) FROM edge_nav_daily WHERE strategy_id=?", (sid,)).fetchone()[0]
    exp = base.get("expected_trades_per_day") or \
        (base.get("source_fixture") or {}).get("expected_trades_per_day")
    if not exp or n_days < 30:
        return {"metric": "behavior_drift", "status": "insufficient",
                "value": n_tr, "note": "needs expected rate + 30 days"}
    rate = n_tr / n_days
    off = rate > 3 * exp or rate < exp / 3
    return {"metric": "behavior_drift", "status": "breach" if off else "ok",
            "value": round(rate, 3), "threshold": exp, "escalates": False,
            "note": "informational ops tripwire"}


def run_daily(con: sqlite3.Connection, sid: str, today: str | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc).date().isoformat()
    base = bl.load(con, sid)
    if base is None:
        return [{"metric": "baseline", "status": "blind",
                 "note": "no baseline registered — nothing to test against"}]
    slip_norms = db.kv_get(con, sid, "slip_norms")
    if slip_norms:
        base["slip"] = slip_norms
    checks = [check_freshness(con, sid, today), check_revisions(con, sid),
              check_return_cusum(con, sid, base), check_dd(con, sid, base),
              check_slippage(con, sid, base), check_vol_band(con, sid, base),
              check_behavior(con, sid, base)]
    for c in checks:
        con.execute(
            "INSERT INTO edge_checks VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(strategy_id,date,metric) DO UPDATE SET value=excluded.value, "
            "threshold=excluded.threshold, breach=excluded.breach, note=excluded.note",
            (sid, today, "L1", c["metric"], c.get("value"), c.get("threshold"),
             int(c["status"] == "breach"), f"{c['status']}: {c.get('note', '')}"))
    con.commit()
    return checks
