"""Call-performance time series — the instrument that shows whether the
learning loop is actually learning.

Three views, all from closed calls (plus flag outcomes for early signal):

  equity_curve     cumulative R by exit date — the raw "strength of calls"
  rolling          trailing-20-call win rate and avg R, stepped per close —
                   smooth enough to see drift, honest about n
  monthly_cohorts  calls grouped by the month they were MADE (not closed):
                   if the system is improving, later cohorts should grade
                   better than earlier ones — this is the learning metric,
                   because it compares decisions made under different configs
  flag_cohorts     per fire-month flag hit rate vs XBI (1m horizon) — flags
                   accrue much faster than calls, so this line moves first

Numbers carry their n; the UI is expected to show "insufficient history"
rather than draw confident lines through three points.
"""
from __future__ import annotations

from collections import deque

from sqlmodel import Session, select

from ..models import FlagOutcome, TradeCall

ROLLING_WINDOW = 20


def calls_performance(session: Session) -> dict:
    closed = [
        c
        for c in session.exec(
            select(TradeCall)
            .where(TradeCall.status != "open")
            .order_by(TradeCall.exit_date.asc())
        ).all()
        if c.exit_date is not None and c.r_multiple is not None
    ]

    equity: list[dict] = []
    rolling: list[dict] = []
    cum = 0.0
    window: deque[float] = deque(maxlen=ROLLING_WINDOW)
    for c in closed:
        cum += c.r_multiple
        window.append(c.r_multiple)
        equity.append({
            "date": c.exit_date.isoformat(),
            "symbol": c.symbol,
            "r": round(c.r_multiple, 3),
            "cum_r": round(cum, 3),
        })
        rolling.append({
            "date": c.exit_date.isoformat(),
            "n": len(window),
            "win_rate": round(sum(1 for r in window if r > 0) / len(window), 3),
            "avg_r": round(sum(window) / len(window), 3),
        })

    # Entry-month cohorts: the honest "is it improving" comparison, because
    # each cohort's calls were generated under that month's config/signals.
    by_month: dict[str, list[float]] = {}
    for c in closed:
        by_month.setdefault(c.call_date.strftime("%Y-%m"), []).append(c.r_multiple)
    monthly = [
        {
            "month": m,
            "n": len(rs),
            "win_rate": round(sum(1 for r in rs if r > 0) / len(rs), 3),
            "avg_r": round(sum(rs) / len(rs), 3),
            "total_r": round(sum(rs), 3),
        }
        for m, rs in sorted(by_month.items())
    ]

    # Flag fire-month cohorts (1m excess vs XBI) — the fast-moving early line.
    flag_month: dict[str, list[float]] = {}
    for o in session.exec(select(FlagOutcome)).all():
        val = o.excess_1m if o.excess_1m is not None else o.fwd_1m
        if val is None:
            continue
        flag_month.setdefault(o.fired_on.strftime("%Y-%m"), []).append(val)
    flag_cohorts = [
        {
            "month": m,
            "n": len(vs),
            "hit_rate": round(sum(1 for v in vs if v > 0) / len(vs), 3),
            "avg_excess": round(sum(vs) / len(vs), 4),
        }
        for m, vs in sorted(flag_month.items())
    ]

    return {
        "closed_calls": len(closed),
        "cum_r": round(cum, 3) if closed else None,
        "equity_curve": equity,
        "rolling": rolling,
        "rolling_window": ROLLING_WINDOW,
        "monthly_cohorts": monthly,
        "flag_cohorts": flag_cohorts,
        "note": (
            "Cohorts group calls by the month they were MADE — if the loop is "
            "learning (weights/triggers retuned from evidence), later cohorts "
            "should outperform earlier ones. Treat any point with n < 10 as "
            "anecdote, not trend."
        ),
    }
