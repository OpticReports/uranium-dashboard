"""Flag forward-return tracking — the uncensored learning loop.

Every FlagEvent gets graded against what price subsequently did (1w/1m/3m in
trading bars, raw and XBI-excess), regardless of whether it became a trade
call. This is what turns "equal weights until we see the data" into
evidence-based weights: /flags/track-record answers, per flag type, "when this
fires, what happens next — and does it beat just owning the sector?"
"""
from __future__ import annotations

import logging
from datetime import date

from sqlmodel import Session, select

from ..models import FlagEvent, FlagOutcome, PriceBar

logger = logging.getLogger(__name__)

BENCH = "XBI"
HORIZONS = {"1w": 5, "1m": 21, "3m": 63}  # trading bars


def _closes(session: Session, symbol: str) -> list[tuple[date, float]]:
    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.asc())
    ).all()
    return [(b.date, b.close) for b in rows]


def _fwd_return(closes: list[tuple[date, float]], fired_on: date, bars_fwd: int) -> float | None:
    """Return from the fire-date close to `bars_fwd` trading bars later.

    None until enough bars have printed — never extrapolated.
    """
    idx = next((i for i, (d, _) in enumerate(closes) if d >= fired_on), None)
    if idx is None:
        return None
    # Anchor on the bar at/just before the fire date's close.
    if closes[idx][0] > fired_on:
        if idx == 0:
            return None
        idx -= 1
    if idx + bars_fwd >= len(closes):
        return None
    base = closes[idx][1]
    if not base:
        return None
    return (closes[idx + bars_fwd][1] - base) / base


def evaluate_flag_outcomes(session: Session, batch: int = 500) -> int:
    """Create/refresh FlagOutcome rows for flags not yet fully graded.

    Idempotent and cheap: complete rows are never touched again; incomplete
    rows fill in horizon by horizon as bars accrue.
    """
    flags = session.exec(select(FlagEvent).order_by(FlagEvent.asof.asc())).all()
    existing = {o.flag_id: o for o in session.exec(select(FlagOutcome)).all()}

    closes_cache: dict[str, list[tuple[date, float]]] = {}

    def closes_for(symbol: str) -> list[tuple[date, float]]:
        if symbol not in closes_cache:
            closes_cache[symbol] = _closes(session, symbol)
        return closes_cache[symbol]

    bench_closes = closes_for(BENCH)

    n = 0
    for flag in flags:
        if flag.id is None:
            continue
        out = existing.get(flag.id)
        if out is not None and out.complete:
            continue
        fired_on = flag.asof.date()
        closes = closes_for(flag.symbol)
        if out is None:
            # Anchor bar = the fire date's close (or the last close before it —
            # the normal case for a flag fired intraday, before today's bar).
            base_idx = next((i for i, (d, _) in enumerate(closes) if d >= fired_on), None)
            if base_idx is None:
                base_idx = len(closes) - 1  # fired after the newest bar
            elif closes[base_idx][0] > fired_on:
                base_idx -= 1
            if base_idx < 0:
                continue  # no bar at/before fire date yet — grade later
            out = FlagOutcome(
                flag_id=flag.id, symbol=flag.symbol, flag_type=flag.flag_type,
                fired_on=closes[base_idx][0], price_at_fire=closes[base_idx][1],
            )
        changed = out.id is None
        for label, bars_fwd in HORIZONS.items():
            if getattr(out, f"fwd_{label}") is not None:
                continue
            fwd = _fwd_return(closes, out.fired_on, bars_fwd)
            if fwd is None:
                continue
            setattr(out, f"fwd_{label}", fwd)
            bench_fwd = _fwd_return(bench_closes, out.fired_on, bars_fwd)
            if bench_fwd is not None:
                setattr(out, f"excess_{label}", fwd - bench_fwd)
            changed = True
        out.complete = all(getattr(out, f"fwd_{h}") is not None for h in HORIZONS)
        if changed:
            session.add(out)
            n += 1
        if n >= batch:
            break
    if n:
        session.commit()
        logger.info("Graded/updated %d flag outcome(s)", n)
    return n


def flag_track_record(session: Session) -> dict:
    """Per-flag-type forward-return stats. Small n is stated, never hidden."""
    outcomes = session.exec(select(FlagOutcome)).all()
    by_type: dict[str, list[FlagOutcome]] = {}
    for o in outcomes:
        by_type.setdefault(o.flag_type, []).append(o)

    def _horizon_stats(rows: list[FlagOutcome], label: str) -> dict:
        raw = [getattr(o, f"fwd_{label}") for o in rows]
        raw = [r for r in raw if r is not None]
        exc = [getattr(o, f"excess_{label}") for o in rows]
        exc = [e for e in exc if e is not None]
        graded = exc if exc else raw  # prefer benchmark-relative when available
        return {
            "n": len(raw),
            "hit_rate": (sum(1 for g in graded if g > 0) / len(graded)) if graded else None,
            "avg_return": (sum(raw) / len(raw)) if raw else None,
            "avg_excess": (sum(exc) / len(exc)) if exc else None,
            "vs_benchmark": bool(exc),
        }

    return {
        "benchmark": BENCH,
        "note": (
            "Every flag is graded from its fire-time close — including flags "
            "that never became calls — so these hit rates are uncensored. "
            "Treat n < 10 as insufficient history, not signal."
        ),
        "by_flag_type": {
            ftype: {
                "fired": len(rows),
                "horizons": {h: _horizon_stats(rows, h) for h in HORIZONS},
            }
            for ftype, rows in sorted(by_type.items())
        },
    }
