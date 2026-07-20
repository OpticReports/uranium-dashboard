"""Tuning-evidence export: everything the improvement loop reads, one URL.

GET /tuning/evidence returns the compact aggregate bundle the tuner agent (see
TUNING.md) is allowed to consume — track record, scorecard, performance
cohorts, per-conviction-band call stats, current config echo, and evidence
counts. Auth-gated like the rest of the app. Deliberately aggregate-only: the
tuner never needs (and must not read) raw bars or full tables.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..calls.manager import scorecard
from ..calls.performance import calls_performance
from ..config import calls_config, flags_config, scoring_config
from ..db import get_session
from ..models import FlagOutcome, TradeCall
from ..scoring.outcomes import flag_track_record

router = APIRouter(prefix="/tuning", tags=["tuning"])


def _conviction_bands(session: Session) -> list[dict]:
    """Closed-call results cut by composite-at-call band — the evidence for
    moving the min_composite conviction gate."""
    closed = [
        c for c in session.exec(select(TradeCall).where(TradeCall.status != "open")).all()
        if c.r_multiple is not None and c.composite_at_call is not None
    ]
    bands = [(0, 55), (55, 65), (65, 75), (75, 101)]
    out = []
    for lo, hi in bands:
        rs = [c.r_multiple for c in closed if lo <= c.composite_at_call < hi]
        out.append({
            "band": f"{lo}-{hi - 1}",
            "n": len(rs),
            "win_rate": (sum(1 for r in rs if r > 0) / len(rs)) if rs else None,
            "avg_r": (sum(rs) / len(rs)) if rs else None,
        })
    return out


@router.get("/evidence")
def tuning_evidence(session: Session = Depends(get_session)):
    graded_1m = len(session.exec(
        select(FlagOutcome).where(FlagOutcome.fwd_1m != None)  # noqa: E711
    ).all())
    closed_calls = len(session.exec(
        select(TradeCall).where(TradeCall.status != "open")
    ).all())
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "counts": {
            "flag_outcomes_graded_1m": graded_1m,
            "closed_calls": closed_calls,
        },
        "flag_track_record": flag_track_record(session),
        "calls_scorecard": scorecard(session),
        "calls_performance": calls_performance(session),
        "conviction_bands": _conviction_bands(session),
        "configs": {
            "scoring_weights": scoring_config().get("weights", {}),
            "calls": {k: calls_config().get(k) for k in
                      ("triggers", "min_composite", "risk", "horizon", "liquidity",
                       "cooldown_days", "max_open_calls")},
            "flags": flags_config(),
        },
        "law": "TUNING.md governs how this bundle may be used.",
    }
