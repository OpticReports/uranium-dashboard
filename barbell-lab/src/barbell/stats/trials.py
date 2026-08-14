"""Trial registry — the multiple-testing denominator. NON-NEGOTIABLE.

Every strategy/weights variant that gets EVALUATED (not just reported) is
appended here with its config hash. Significance statements always use the
CUMULATIVE count: deleting rows would silently un-correct every past result,
so there is no delete API.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .corrections import holm_bonferroni
from .dsr import deflated_sharpe


def register_trial(con: sqlite3.Connection, config_hash: str, module: str,
                   description: str, sharpe: float | None, n_obs: int | None,
                   metrics: dict | None = None) -> int:
    cur = con.execute(
        "INSERT INTO trials (ts_utc, config_hash, module, description, sharpe, n_obs, metrics) "
        "VALUES (?,?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), config_hash, module, description,
         sharpe, n_obs, json.dumps(metrics or {})),
    )
    con.commit()
    return int(cur.lastrowid)


def cumulative_count(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM trials").fetchone()[0])


def all_sharpes(con: sqlite3.Connection) -> np.ndarray:
    rows = con.execute("SELECT sharpe FROM trials WHERE sharpe IS NOT NULL").fetchall()
    return np.array([r[0] for r in rows], dtype=float)


def significance_block(con: sqlite3.Connection, sr_hat: float, n_obs: int,
                       skew: float, kurt: float) -> dict:
    """The mandatory numbers for every backtest report: cumulative trial
    count, DSR against that count, and the Holm-corrected p-value of THIS
    trial among all registered trials' p-values."""
    n_trials = max(cumulative_count(con), 1)
    srs = all_sharpes(con)
    var_sr = float(np.var(srs, ddof=1)) if srs.size >= 2 else 0.0
    d = deflated_sharpe(sr_hat, n_obs, n_trials, var_sr, skew=skew, kurt=kurt)
    # Holm across all trials: approximate each registered trial's p-value from
    # its stored per-period Sharpe and n_obs (PSR vs 0), then correct.
    df = pd.read_sql_query(
        "SELECT trial_id, sharpe, n_obs FROM trials WHERE sharpe IS NOT NULL AND n_obs IS NOT NULL",
        con)
    corrected_p = None
    if not df.empty:
        from .dsr import psr
        pvals = [1.0 - psr(row.sharpe, int(row.n_obs)) for row in df.itertuples()]
        # this trial's raw p enters the family too
        pvals.append(d["p_value"])
        adj = holm_bonferroni(pvals)
        corrected_p = float(adj[-1])
    return {
        "trial_count": n_trials,
        "sr0": d["sr0"],
        "dsr": d["dsr"],
        "p_raw": d["p_value"],
        "p_holm": corrected_p if corrected_p is not None else d["p_value"],
        "var_sr_across_trials": var_sr,
    }


def trial_summary(con: sqlite3.Connection) -> str:
    n = cumulative_count(con)
    df = pd.read_sql_query(
        "SELECT trial_id, ts_utc, module, description, sharpe FROM trials "
        "ORDER BY trial_id DESC LIMIT 15", con)
    lines = [f"cumulative trials to date: {n}", ""]
    if not df.empty:
        lines.append(df.to_string(index=False))
    return "\n".join(lines)
