"""GET /track-record — the dashboard's own prediction log, scored in arrears.

Each refresh logs the day's headline predictions (composite, 12m recession
probabilities raw+adjusted, curve state, pins, Sahm). Rows older than 12 months
resolve against USREC (did a recession actually start within 12m?) and get a
Brier contribution; unresolved rows are shown as pending. The point: the system
earns (or loses) empirical trust in public, over time.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..sources.fred import fetch_bundle, recession_start_dates
from ..store.db import get_session
from ..store.models import PredictionLog

router = APIRouter(tags=["track-record"])


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


@router.get("/track-record")
def track_record(session: Session = Depends(get_session)):
    rows = session.execute(
        select(PredictionLog).order_by(PredictionLog.asof.desc()).limit(730)
    ).scalars().all()

    rec_d, rec_v = fetch_bundle().get("recession", ([], []))
    onsets = recession_start_dates(rec_d, rec_v)
    last_known = rec_d[-1] if rec_d else None

    out = []
    briers: list[float] = []
    for r in rows:
        outcome = None  # None = unresolved
        # resolvable only if USREC coverage extends >= 12 months past asof
        if last_known is not None and _months_between(r.asof, last_known) >= 12:
            outcome = 1 if any(0 < _months_between(r.asof, o) <= 12 for o in onsets) else 0
            if r.rec_prob_12m is not None:
                briers.append((r.rec_prob_12m / 100.0 - outcome) ** 2)
        out.append({
            "asof": r.asof.isoformat(), "composite_score": r.composite_score,
            "composite_band": r.composite_band, "coverage": r.coverage,
            "rec_prob_12m": r.rec_prob_12m, "rec_prob_adj_12m": r.rec_prob_adj_12m,
            "curve_state": r.curve_state, "pins_overall": r.pins_overall,
            "sahm": r.sahm, "outcome_recession_12m": outcome,
        })

    return {
        "rows": out,
        "n_total": len(out),
        "n_resolved": sum(1 for r in out if r["outcome_recession_12m"] is not None),
        "brier": round(sum(briers) / len(briers), 4) if briers else None,
        "brier_note": "Mean squared error of the 12m recession probability vs outcome "
                      "(0=perfect, 0.25=coin-flip-at-50%). Needs >=12mo of log to resolve.",
        "caveat": "On free-tier hosting the log resets on redeploys; upgrade to a "
                  "persistent disk to accumulate an unbroken record.",
    }
