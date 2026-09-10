"""Stage 2 — the forward shadow.

WHY THIS EXISTS AND THE BACKTEST DOES NOT REPLACE IT. Neither model card
states an overall training cutoff, and whether crypto series are in their
pretraining corpora is "not specified". So no historical window can be
proven clean, and section 5 of the study doc makes the forward record the
primary evidence. This is that record.

APPEND-ONLY, AND THE FORECAST IS WRITTEN BEFORE THE OUTCOME EXISTS. Each
row is stamped with the bar it was made at and the bar it resolves at; the
outcome is filled in by a separate pass once that bar has actually closed.
A file where a forecast could be edited after the fact is not evidence, and
"we would have predicted that" is the easiest lie a study can tell itself.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

from . import data as D
from .metrics import LEVELS

SCHEMA = 1


def _row(model: str, ts_made: int, ts_resolve: int, q: np.ndarray,
         horizon: int) -> dict:
    return {"schema": SCHEMA, "model": model, "ts_made": int(ts_made),
            "ts_resolve": int(ts_resolve), "horizon": horizon,
            "levels": [float(x) for x in LEVELS],
            "q": [float(x) for x in q], "y": None,
            "written_at": int(time.time())}


def append_forecast(path: str, model: str, ts_made: int, q: np.ndarray,
                    horizon: int = D.HORIZON_BARS) -> dict:
    """Log one forecast. Refuses to overwrite: append only.

    ts_resolve is derived, not supplied - a caller that could choose when
    its own forecast resolves could choose the window that flattered it."""
    if len(q) != LEVELS.size:
        raise ValueError(f"expected {LEVELS.size} quantiles, got {len(q)}")
    if not np.all(np.diff(q) >= 0):
        raise ValueError("quantiles are not monotonic; the forecast is invalid")
    row = _row(model, ts_made, ts_made + horizon * D.BAR_SECONDS, q, horizon)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def resolve(path: str, bars: dict, now: int | None = None) -> int:
    """Fill in outcomes for rows whose window has fully closed.

    REFUSES TO RESOLVE EARLY. A row is only scored once the resolving bar
    exists in the data AND is in the past; scoring a partially observed
    window would systematically understate realized volatility, because a
    window that has not finished cannot yet contain its own worst move.
    Rewrites the file with outcomes filled; existing forecasts are never
    modified, only their `y`."""
    now = int(time.time()) if now is None else now
    rows = load(path)
    if not rows:
        return 0
    y_all = D.forward_realized_vol(bars["close"], D.HORIZON_BARS)
    by_ts = {int(t): i for i, t in enumerate(bars["ts"])}
    n = 0
    for r in rows:
        if r.get("y") is not None:
            continue
        if r["ts_resolve"] > now:
            continue
        i = by_ts.get(r["ts_made"])
        if i is None or not np.isfinite(y_all[i]):
            continue
        r["y"] = float(y_all[i])
        r["resolved_at"] = int(time.time())
        n += 1
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, path)
    return n


def score(path: str, model: str | None = None) -> dict:
    """Score resolved rows only. Unresolved rows are COUNTED and reported
    rather than dropped, so a model whose forecasts mostly never resolve
    cannot look good on the handful that did."""
    from . import metrics as M
    rows = [r for r in load(path) if model is None or r["model"] == model]
    done = [r for r in rows if r.get("y") is not None]
    if not done:
        return {"n": 0, "pending": len(rows) - len(done)}
    y = np.array([r["y"] for r in done])
    Q = np.array([r["q"] for r in done])
    out = M.summary(y, Q)
    out["pending"] = len(rows) - len(done)
    out["first"] = min(r["ts_made"] for r in done)
    out["last"] = max(r["ts_made"] for r in done)
    # Section 4 rule 5: eight consecutive weeks. Reported, never inferred
    # from a total count - 8 weeks of data is not 8 weeks of agreement.
    out["weeks_spanned"] = round((out["last"] - out["first"]) / 604800.0, 2)
    return out
