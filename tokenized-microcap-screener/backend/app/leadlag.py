"""Lead-lag measurement.

The whole premise of this service is that the on-chain rungs happen BEFORE the
equity moves. That is a claim about a distribution, and right now the sample
that motivated it is n=1 (Farmmi, 2026-09-02). So this module measures the lag
rather than assuming it, and every consumer reports the sample size next to the
number. Until n is large enough to mean anything, the honest reading of these
figures is "here is what we have logged", not "here is the lead you will get".
"""
from __future__ import annotations

import statistics
from datetime import datetime

from sqlmodel import Session, select

from .models import Candidate

# (from_field, to_field, label)
_LEGS = [
    ("first_tokenized_at", "first_paired_at", "tokenized->paired"),
    ("first_tokenized_at", "first_equity_move_at", "tokenized->equity_move"),
    ("first_paired_at", "first_ramping_at", "paired->ramping"),
    ("first_ramping_at", "first_equity_move_at", "ramping->equity_move"),
    ("first_cluster_at", "first_equity_move_at", "cluster->equity_move"),
    ("alerted_at", "first_equity_move_at", "alert->equity_move"),
]


def _hours(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds() / 3600.0


def measure(session: Session) -> dict:
    rows = session.exec(select(Candidate)).all()
    legs: dict[str, dict] = {}
    for src, dst, label in _LEGS:
        vals = [h for h in (_hours(getattr(r, src, None), getattr(r, dst, None))
                            for r in rows) if h is not None]
        legs[label] = {
            "n": len(vals),
            "median_hours": round(statistics.median(vals), 2) if vals else None,
            "min_hours": round(min(vals), 2) if vals else None,
            "max_hours": round(max(vals), 2) if vals else None,
            # A leg with n < 5 is an anecdote; say so in the payload itself so
            # a consumer cannot read it as an estimate by accident.
            "interpretable": len(vals) >= 5,
        }
    completed = [r.ticker for r in rows if r.first_equity_move_at is not None]
    alerted_then_moved = [
        r.ticker for r in rows
        if r.alerted_at is not None and r.first_equity_move_at is not None
        and r.first_equity_move_at > r.alerted_at]
    alerted = [r.ticker for r in rows if r.alerted_at is not None]
    return {
        "legs": legs,
        "tickers_tracked": len(rows),
        "equity_moves_observed": len(completed),
        "alerts_fired": len(alerts_count := alerted),
        "alerts_followed_by_move": len(alerted_then_moved),
        "hit_rate": (round(len(alerted_then_moved) / len(alerts_count), 3)
                     if alerts_count else None),
        "caveat": ("Observational and unadjusted. Hit rate counts an alert as a "
                   "hit if the equity later cleared the move gate; it says "
                   "nothing about whether the trade was profitable after "
                   "slippage, halts, or the reversal that followed FAMI."),
    }
