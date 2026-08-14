"""Portfolio Register — the CIO layer.

The portfolio ("B.5 Enhanced") is a first-class, VERSIONED object:

* exactly one LIVE version at a time; changes arrive as CANDIDATE versions
  linked to their parent, carrying a rationale and an evaluation battery;
* promotion to LIVE is an explicit, confirmed action that retires the old
  version — the ledger is append-only, so "what did we change and did it
  work" is always answerable;
* every version's metrics snapshot (realized + Monte Carlo + constraint
  compliance) is computed from the same registered machinery as the CLI.

v1.0 is seeded from config/portfolio.yaml the first time the register is
touched, so the config file remains the platform's bootstrap but stops being
the live source of truth once versions exist.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import load
from ..backtest.engine import resolve_targets, simulate
from ..backtest.metrics import TRADING_DAYS, summary
from .combined import bot_return_series, combined_returns
from .simulate import bootstrap_paths, path_metrics

EXPLORATORY_PATHS = 5000
_METRICS_TTL_HOURS = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ CRUD
def ensure_seed(con: sqlite3.Connection) -> None:
    """Seed v1.0 LIVE from config targets if the register is empty."""
    n = con.execute("SELECT COUNT(*) FROM portfolio_versions").fetchone()[0]
    if n:
        return
    port = load("portfolio")
    weights = resolve_targets(port["tail_sleeve"]["current"])
    con.execute(
        "INSERT INTO portfolio_versions (name, label, status, weights, bot_frac, "
        "parent_id, rationale, created_at, adopted_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (port.get("name", "b5-enhanced"), "v1.0", "LIVE", json.dumps(weights),
         1.0 - float(port.get("sleeve_fraction", 0.8)), None,
         "Seeded from config/portfolio.yaml (initial B.5 Enhanced targets)",
         _now(), _now()),
    )
    con.commit()


def _row_to_dict(r) -> dict:
    return {"id": r[0], "name": r[1], "label": r[2], "status": r[3],
            "weights": json.loads(r[4]), "bot_frac": r[5], "parent_id": r[6],
            "rationale": r[7], "evidence": json.loads(r[8]) if r[8] else None,
            "created_at": r[9], "adopted_at": r[10], "retired_at": r[11]}


_COLS = ("id, name, label, status, weights, bot_frac, parent_id, rationale, "
         "evidence, created_at, adopted_at, retired_at")


def get_version(con: sqlite3.Connection, version_id: int) -> dict:
    r = con.execute(f"SELECT {_COLS} FROM portfolio_versions WHERE id=?",
                    (version_id,)).fetchone()
    if r is None:
        raise ValueError(f"no portfolio version {version_id}")
    return _row_to_dict(r)


def get_live(con: sqlite3.Connection) -> dict:
    ensure_seed(con)
    r = con.execute(f"SELECT {_COLS} FROM portfolio_versions WHERE status='LIVE' "
                    "ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        raise RuntimeError("register has versions but no LIVE one — promote a candidate")
    return _row_to_dict(r)


def list_versions(con: sqlite3.Connection) -> list[dict]:
    ensure_seed(con)
    rows = con.execute(f"SELECT {_COLS} FROM portfolio_versions ORDER BY id").fetchall()
    return [_row_to_dict(r) for r in rows]


def _next_label(con: sqlite3.Connection) -> str:
    labels = [r[0] for r in con.execute(
        "SELECT label FROM portfolio_versions").fetchall()]
    best = (1, 0)
    for lb in labels:
        try:
            a, b = lb.lstrip("v").split(".")
            best = max(best, (int(a), int(b)))
        except ValueError:
            continue
    return f"v{best[0]}.{best[1] + 1}"


# ------------------------------------------------------------------ series
def version_book(con: sqlite3.Connection, version: dict,
                 allow_bot_model: bool = True,
                 kill_switch: str = "perfect") -> pd.DataFrame:
    """Daily sleeve/bot/combined frame for a version's explicit weights."""
    from ..ingest.series import returns_matrix
    weights = version["weights"]
    mat = returns_matrix(con, list(weights.keys()), spliced=True).dropna()
    w = np.array([weights[t] for t in weights])
    sleeve = pd.Series(mat.values @ w, index=mat.index, name="sleeve")
    if version["bot_frac"] <= 0:
        df = sleeve.to_frame()
        df["combined"] = df["sleeve"]
        df.attrs["bot_provenance"] = "none"
        return df
    bot = bot_return_series(con, allow_model=allow_bot_model, kill_switch=kill_switch)
    joint = combined_returns(sleeve, bot, sleeve_frac=1.0 - version["bot_frac"])
    joint.attrs["bot_provenance"] = bot.attrs.get("provenance", "real")
    return joint


# ------------------------------------------------------------------ metrics
def version_metrics(con: sqlite3.Connection, version: dict,
                    n_paths: int = EXPLORATORY_PATHS,
                    force: bool = False) -> dict:
    """Realized + Monte Carlo + constraint-compliance snapshot (cached 24h)."""
    row = con.execute(
        "SELECT computed_at, metrics FROM portfolio_metrics WHERE version_id=? "
        "ORDER BY computed_at DESC LIMIT 1", (version["id"],)).fetchone()
    if row and not force:
        age_h = (datetime.now(timezone.utc)
                 - datetime.fromisoformat(row[0])).total_seconds() / 3600
        if age_h < _METRICS_TTL_HOURS:
            return json.loads(row[1])

    mc = load("backtest")["monte_carlo"]
    cons = load("portfolio")["constraints"]
    weights = version["weights"]

    # realized (cost-paying threshold simulation of the sleeve)
    from ..ingest.series import returns_matrix
    mat = returns_matrix(con, list(weights.keys()), spliced=True).dropna()
    sim = simulate(mat, weights, mode="threshold")
    s = summary(sim.returns)

    def _trailing(years: float) -> float | None:
        n = int(years * TRADING_DAYS)
        if len(sim.returns) < n:
            return None
        r = sim.returns.iloc[-n:]
        return float((1 + r).prod() ** (TRADING_DAYS / len(r)) - 1)

    # Monte Carlo on the combined book (bot at version's fraction, model ok)
    joint = version_book(con, version)
    cols = ["sleeve", "bot"] if version["bot_frac"] > 0 else ["sleeve"]
    w = (np.array([1 - version["bot_frac"], version["bot_frac"]])
         if version["bot_frac"] > 0 else np.array([1.0]))
    p1 = bootstrap_paths(joint[cols], w, n_paths, 1,
                         int(mc["block_len_days"]), seed=int(mc["seed"]))
    m1 = path_metrics(p1)
    p10 = bootstrap_paths(joint[cols], w, max(2000, n_paths // 2), 10,
                          int(mc["block_len_days"]), seed=int(mc["seed"]) + 1)
    m10 = path_metrics(p10)

    max_w = max(weights.values())
    metrics = {
        "as_of": f"{mat.index.max():%Y-%m-%d}",
        "history_start": f"{mat.index.min():%Y-%m-%d}",
        "cagr_realized": s["cagr"],
        "cagr_1y": _trailing(1), "cagr_3y": _trailing(3),
        "cagr_expected_10y": m10["cagr_median"],
        "sharpe": s["sharpe_annual"],
        "ann_vol": s["ann_vol"],
        "maxdd_realized": s["max_drawdown"],
        "maxdd_p5_mc": m1["maxdd_p5"],
        "cvar5_mc": m1["cvar5_annual"],
        "p5_1y": float(np.percentile(p1["annual_returns"], 5)),
        "bot_provenance": joint.attrs.get("bot_provenance", "none"),
        "n_paths": n_paths,
        "constraints": {
            "cvar5": {"value": m1["cvar5_annual"],
                      "floor": float(cons["cvar_5_annual_min"]),
                      "pass": m1["cvar5_annual"] >= float(cons["cvar_5_annual_min"])},
            "maxdd_p5": {"value": m1["maxdd_p5"],
                         "floor": float(cons["p5_max_drawdown_min"]),
                         "pass": m1["maxdd_p5"] >= float(cons["p5_max_drawdown_min"])},
            "max_position": {"value": max_w, "cap": float(cons["max_position"]),
                             "pass": max_w <= float(cons["max_position"]) + 1e-9},
        },
    }
    con.execute("INSERT OR REPLACE INTO portfolio_metrics (version_id, computed_at, metrics) "
                "VALUES (?,?,?)", (version["id"], _now(), json.dumps(metrics)))
    con.commit()
    return metrics


# ------------------------------------------------------------------ workflow
def propose_candidate(con: sqlite3.Connection, weights: dict[str, float] | None = None,
                      bot_frac: float | None = None, rationale: str = "",
                      n_paths: int = EXPLORATORY_PATHS) -> dict:
    """File a CANDIDATE version and run the evaluation battery vs LIVE.

    weights: full explicit dict (ticker -> weight, must sum to 1). Omitted
    fields inherit from LIVE. Every proposal registers trials."""
    from ..config import config_hash
    from ..stats.trials import register_trial

    live = get_live(con)
    new_w = dict(weights) if weights else dict(live["weights"])
    total = sum(new_w.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights sum to {total:.4f}, must sum to 1.0")
    if any(v < 0 for v in new_w.values()):
        raise ValueError("negative weights not allowed (long-only register)")
    cfg = load("data")["tickers"]
    unknown = [t for t in new_w if t not in cfg]
    if unknown:
        raise ValueError(f"tickers not in the data universe: {unknown}")
    bf = live["bot_frac"] if bot_frac is None else float(bot_frac)
    if not 0 <= bf < 1:
        raise ValueError("bot_frac must be in [0, 1)")

    label = _next_label(con)
    cur = con.execute(
        "INSERT INTO portfolio_versions (name, label, status, weights, bot_frac, "
        "parent_id, rationale, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (live["name"], label, "CANDIDATE", json.dumps(new_w), bf, live["id"],
         rationale or "(no rationale given)", _now()))
    con.commit()
    cand = get_version(con, cur.lastrowid)

    cm = version_metrics(con, cand, n_paths=n_paths, force=True)
    lm = version_metrics(con, live, n_paths=n_paths)
    h = config_hash({"candidate": new_w, "bot_frac": bf})
    register_trial(con, h, "portfolio",
                   f"candidate {label} vs live {live['label']}",
                   None, None, {"candidate": cm, "rationale": rationale})

    deltas = {k: cm[k] - lm[k] for k in
              ("cagr_realized", "cagr_expected_10y", "sharpe", "cvar5_mc",
               "maxdd_p5_mc", "p5_1y") if cm.get(k) is not None and lm.get(k) is not None}
    all_pass = all(c["pass"] for c in cm["constraints"].values())
    if not all_pass:
        verdict = "INCONCLUSIVE"
        basis = "Candidate violates hard constraints — not promotable as-is."
    elif deltas.get("cagr_expected_10y", 0) > 0.003 and deltas.get("cvar5_mc", 0) >= -0.002:
        verdict = "IMPROVED"
        basis = (f"Higher expected CAGR ({deltas['cagr_expected_10y']:+.2%}) with "
                 f"no material tail-risk cost (ΔCVaR5 {deltas['cvar5_mc']:+.2%}).")
    elif abs(deltas.get("cagr_expected_10y", 0)) <= 0.003:
        verdict = "NO_CHANGE"
        basis = "Expected CAGR within noise of live; no reason to switch."
    else:
        verdict = "INCONCLUSIVE"
        basis = "Trade-off is mixed — inspect the side-by-side before deciding."
    evidence = {"vs_live": live["label"], "deltas": deltas, "verdict": verdict,
                "basis": basis, "n_paths": n_paths,
                "note": "exploratory paths; promote only after reviewing the comparison"}
    con.execute("UPDATE portfolio_versions SET evidence=? WHERE id=?",
                (json.dumps(evidence), cand["id"]))
    con.commit()
    cand["evidence"] = evidence
    return cand


def compare(con: sqlite3.Connection, a_id: int, b_id: int) -> dict:
    a, b = get_version(con, a_id), get_version(con, b_id)
    return {"a": {"version": a["label"], "status": a["status"],
                  "weights": a["weights"], "bot_frac": a["bot_frac"],
                  "metrics": version_metrics(con, a)},
            "b": {"version": b["label"], "status": b["status"],
                  "weights": b["weights"], "bot_frac": b["bot_frac"],
                  "metrics": version_metrics(con, b)}}


def promote(con: sqlite3.Connection, version_id: int, confirm_label: str) -> dict:
    """Promote a CANDIDATE to LIVE. `confirm_label` must equal the candidate's
    label — typed confirmation, this changes the live book's targets."""
    cand = get_version(con, version_id)
    if cand["status"] != "CANDIDATE":
        raise ValueError(f"{cand['label']} is {cand['status']}, not a CANDIDATE")
    if confirm_label.strip() != cand["label"]:
        raise ValueError(f"confirmation mismatch: type the exact label "
                         f"'{cand['label']}' to promote")
    live = get_live(con)
    now = _now()
    con.execute("UPDATE portfolio_versions SET status='RETIRED', retired_at=? "
                "WHERE id=?", (now, live["id"]))
    con.execute("UPDATE portfolio_versions SET status='LIVE', adopted_at=? "
                "WHERE id=?", (now, cand["id"]))
    con.execute("INSERT INTO alerts (ts_utc, kind, message, details) VALUES (?,?,?,?)",
                (now, "portfolio",
                 f"PROMOTED {cand['label']} to LIVE (retired {live['label']})",
                 json.dumps({"weights": cand["weights"], "bot_frac": cand["bot_frac"]})))
    con.commit()
    return get_version(con, version_id)


def ledger(con: sqlite3.Connection) -> list[dict]:
    """Version timeline with deltas — the 'iterations and improvements' view."""
    out = []
    for v in list_versions(con):
        row = {"id": v["id"], "label": v["label"], "status": v["status"],
               "created_at": v["created_at"][:10],
               "adopted_at": (v["adopted_at"] or "")[:10] or None,
               "rationale": v["rationale"],
               "verdict": (v["evidence"] or {}).get("verdict"),
               "deltas": (v["evidence"] or {}).get("deltas")}
        out.append(row)
    return out
