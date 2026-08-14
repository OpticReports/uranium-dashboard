"""Baseline registration: freeze the null hypothesis a strategy's live data
is tested against, and calibrate the WHOLE policy jointly (referee F2 —
per-detector ARL addition is wrong; detectors interact through the state
machine, so false-RED and null return-drag come from one policy MC).
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np

from . import cusum, db, psr

DECLARED_PENALTY_TRIALS = 20     # strategies without a full trials registry
CONFIDENCE = 0.95
TARGET_ARL = 500.0
DD_GRID_STEP = 21
POLICY_PATHS = 200               # joint policy MC (registration-time only)


def _dd_grid(returns: np.ndarray, max_len: int, n_mc: int = 1500,
             block: int = 20, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    n = len(returns)
    nblk = int(np.ceil(max_len / block))
    starts = rng.integers(0, n, size=(n_mc, nblk))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n
           ).reshape(n_mc, -1)[:, :max_len]
    eq = np.cumprod(1 + returns[idx], axis=1)
    dd = eq / np.maximum.accumulate(eq, axis=1) - 1.0
    grid = {}
    for L in range(DD_GRID_STEP, max_len + 1, DD_GRID_STEP):
        m = dd[:, :L].min(axis=1)
        grid[str(L)] = {"p95": float(np.percentile(m, 5)),
                        "p99": float(np.percentile(m, 1))}
    # 20d realized-vol band (annualized) for the regime flag
    w = 20
    k = (eq[:, w:] / eq[:, :-w])
    vols = np.array([returns[idx][i][j:j + w].std(ddof=1) * math.sqrt(252)
                     for i in range(0, n_mc, 25) for j in range(0, max_len - w, 63)])
    grid["_vol_band_ann"] = {"p01": float(np.percentile(vols, 1)),
                             "p99": float(np.percentile(vols, 99))}
    return grid


def _policy_mc(returns: np.ndarray, k: float, h: float, grid: dict,
               n_paths: int = POLICY_PATHS, horizon: int = 1260,
               seed: int = 13) -> dict:
    """Joint state-machine MC under the null: false-RED rate, YELLOW share,
    and null return drag — the policy's real budget numbers."""
    rng = np.random.default_rng(seed)
    mu, sd = returns.mean(), returns.std(ddof=1)
    n = len(returns)
    reds = yell_days = 0
    lw_m, lw_r = [], []
    for _ in range(n_paths):
        # block-bootstrap a null path from the backtest itself
        nblk = int(np.ceil(horizon / 20))
        st_ = rng.integers(0, n, size=nblk)
        r = returns[((st_[:, None] + np.arange(20)[None, :]) % n
                     ).reshape(-1)[:horizon]]
        w_m = w_r = eqty = peak = 1.0
        s = 0.0
        state, clean, size = "GREEN", 0, 1.0
        last_c = last_d = -10_000
        red = False
        for t in range(horizon):
            w_r *= 1 + r[t]
            w_m *= 1 + size * r[t]
            eqty *= 1 + r[t]
            peak = max(peak, eqty)
            dd = eqty / peak - 1.0
            z = (r[t] - mu) / sd
            s = max(0.0, s + (-z) - k)
            L = str(min(max(DD_GRID_STEP, (t + 1) // DD_GRID_STEP * DD_GRID_STEP),
                        max(int(g) for g in grid if not g.startswith("_"))))
            c_al, d95 = s > h, dd <= grid[L]["p95"]
            d99 = dd <= grid[L]["p99"]
            if c_al:
                last_c = t
            if d95:
                last_d = t
            if state != "RED":
                if d99 or (last_c > -10_000 and last_d > -10_000
                           and abs(last_c - last_d) <= 30
                           and max(last_c, last_d) == t):
                    state, size, red = "RED", 0.0, True
                elif state == "GREEN" and (c_al or d95):
                    state, size, clean, s = "YELLOW", 0.5, 0, 0.0
                elif state == "YELLOW":
                    yell_days += 1
                    if s < h / 2 and not d95:
                        clean += 1
                        if clean >= 20:
                            state, size = "GREEN", 1.0
                    else:
                        clean = 0
        reds += red
        lw_m.append(math.log(w_m))
        lw_r.append(math.log(w_r))
    yrs = horizon / 252.0
    return {"false_red_per_5y": reds / n_paths,
            "yellow_day_share": yell_days / (n_paths * horizon),
            "null_drag_pp_terminal_red": round(
                (math.exp(np.mean(lw_m) / yrs) - math.exp(np.mean(lw_r) / yrs)) * 100, 2),
            "note": "terminal-RED framing: true drag with the re-promotion "
                    "lane is ~4x smaller (REFEREE.md round 2)"}


def register(con: sqlite3.Connection, strategy_id: str, fixture: dict,
             n_trials: int | None = None,
             sr_std_across_trials: float = 0.02) -> str:
    """Freeze the null from a backtest-returns fixture (edge_baseline_s5.py
    output shape). Idempotent per content: baseline_id = hash of inputs."""
    db.ensure_schema(con)
    r = np.asarray(fixture["returns"], dtype=float)
    s = psr.sharpe_stats(r)
    trials = n_trials if n_trials is not None else DECLARED_PENALTY_TRIALS
    cal = cusum.calibrate_h(r, target_arl=TARGET_ARL,
                            k=(s.sr / 2.0) if s.sr > 0 else 0.02,
                            n_sims=800, seed=5)
    grid = _dd_grid(r, max_len=1260)
    policy = _policy_mc(r, cal["k"], cal["h"], grid)
    mintrl = psr.min_trl(s.sr, 0.0, s.skew, s.kurt, CONFIDENCE)
    payload = {
        "strategy_id": strategy_id,
        "source_provenance": fixture.get("provenance"),
        "n_backtest_days": s.n,
        "sr_daily": s.sr, "sr_annual": s.sr * math.sqrt(252),
        "mu_daily": float(r.mean()), "std_daily": float(r.std(ddof=1)),
        "skew": s.skew, "kurt": s.kurt,
        "n_trials": trials,
        "trials_basis": ("registry" if n_trials is not None
                         else f"UNKNOWN -> declared penalty n={trials}"),
        "dsr": psr.dsr(r, trials, sr_std_across_trials),
        "pbo": "undefined:no_trial_matrix",
        "mintrl_days": None if math.isinf(mintrl) else round(mintrl),
        "cusum": cal,
        "dd_grid": grid,
        "policy_mc": policy,
        "slip": None,           # set after >=10 live trades (layers.py)
    }
    bid = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str)
                         .encode()).hexdigest()[:16]
    payload["baseline_id"] = bid
    con.execute("INSERT OR IGNORE INTO edge_baselines VALUES (?,?,?,?)",
                (bid, strategy_id, datetime.now(timezone.utc).isoformat(),
                 json.dumps(payload)))
    con.execute("UPDATE edge_strategies SET baseline_id=? WHERE strategy_id=?",
                (bid, strategy_id))
    con.commit()
    return bid


def load(con: sqlite3.Connection, strategy_id: str) -> dict | None:
    row = con.execute(
        "SELECT b.json FROM edge_baselines b JOIN edge_strategies s "
        "ON s.baseline_id = b.baseline_id WHERE s.strategy_id=?",
        (strategy_id,)).fetchone()
    return json.loads(row[0]) if row else None
