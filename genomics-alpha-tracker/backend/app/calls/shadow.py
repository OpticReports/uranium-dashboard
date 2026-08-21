"""OBSERVE-ONLY shadow grading of live calls under the R2-A exit engine (H11/H8).

The round-2 variant campaign (docs/BACKTEST_VARIANTS_R2.md) found R2-A —
a 200dma prior-close XBI regime gate plus 3.0xATR trailing exits with a 90
calendar-day time stop — beat the production fixed-3:1 engine in replay.
Per the house promotion law that is a HYPOTHESIS, not a config change: it
must earn a LIVE track record first. This module builds that record:

  - every live auto-call is ALSO graded under the trailing exit engine
    (ShadowGrade rows), independently of the live grade — either book may
    close a call first;
  - the XBI regime-gate state is logged daily (RegimeLog rows) on the
    PRIOR-CLOSE convention (the counter-agent-corrected form).

NOTHING here touches the live book: call generation, live grading, the
paper account, and every level on every call are bit-identical with this
module present. The trailing parameters are the R2-A REGISTERED values and
deliberately not config-tunable — re-parameterizing a pre-registered
variant after the fact would void the campaign's evidence.

Pure functions first (ORM-free, unit-testable — same philosophy as
rules.py), then the Session-taking wiring (same split as manager.py).
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, timedelta

from sqlmodel import Session, select

from ..config import calls_config
from ..models import PriceBar, RegimeLog, ShadowGrade, TradeCall
from .rules import BarLike, CallExit, atr, call_r_multiple

logger = logging.getLogger(__name__)

# R2-A registered exit parameters (docs/VARIANTS_PREREGISTRATION_R2.md).
ENGINE_TRAILING = "trailing_3atr"
TRAIL_MULT = 3.0
TIME_STOP_DAYS = 90  # CALENDAR days, matching the campaign contract

# Regime-gate MA windows: 200dma is the R2-A gate; the 50dma is logged
# alongside it for H12 (gate-speed comparison), never used to gate anything.
REGIME_WINDOWS = (50, 200)

_CLOSED = ("target_hit", "stopped", "expired", "closed_manual")


# --- pure functions -----------------------------------------------------------

def grade_trailing(
    bars: Sequence[BarLike],
    entry: float,
    entry_date: date,
    atr_at_entry: float | None,
    trail_mult: float = TRAIL_MULT,
    time_stop_days: int = TIME_STOP_DAYS,
    atr_window: int = 14,
) -> CallExit | None:
    """Grade a LONG call under the R2-A trailing-stop exit engine.

    Conventions (campaign contract, counter-agent-verified):
    - trail = (max close since entry through the PRIOR bar)
              - trail_mult * ATR14 recomputed daily THROUGH THE PRIOR BAR —
      no same-bar information ever sets the level that grades the bar.
      `bars` should therefore include pre-entry history so the daily ATR is
      computable; where it is not, `atr_at_entry` seeds the trail. The trail
      RATCHETS UP ONLY — an ATR blowout never lowers a level already earned.
    - Open-first gap-aware fills, exactly grade_call's philosophy: a bar that
      opens through the trail fills at the OPEN, not the level.
    - Time stop: exit at the close of the LAST bar at-or-before
      entry_date + time_stop_days CALENDAR days — never on a bar after it.
    - Entry is the entry-date close; the entry-date bar never grades the call.
    Returns None while the shadow position is still open (insufficient bars
    included — no data is never an exit).
    """
    if entry is None or entry <= 0:
        return None
    deadline = entry_date + timedelta(days=time_stop_days)
    clean = sorted(
        (b for b in bars if b.high is not None and b.low is not None and b.close is not None),
        key=lambda b: b.date,
    )
    history: list[BarLike] = []   # every clean bar STRICTLY BEFORE the bar being graded
    peak = entry                  # max close since entry through the prior bar
    trail: float | None = None    # ratchets up only
    prev: BarLike | None = None   # last post-entry bar processed
    for b in clean:
        if b.date <= entry_date:
            history.append(b)
            continue
        if b.date > deadline:
            # Time-stop passed on a non-trading day: exit at the last bar
            # before it (prev is None only on a data gap straight past it).
            if prev is not None:
                return CallExit("expired", prev.date, prev.close)
            return CallExit("expired", b.date, b.open if b.open is not None else b.close)
        atr_prior = atr(history, atr_window)
        if atr_prior is None or atr_prior <= 0:
            atr_prior = atr_at_entry
        if atr_prior is not None and atr_prior > 0:
            level = peak - trail_mult * atr_prior
            trail = level if trail is None else max(trail, level)
        if trail is not None:
            if b.open is not None and b.open <= trail:
                return CallExit("stopped", b.date, b.open)
            if b.low <= trail:
                return CallExit("stopped", b.date, trail)
        if b.date == deadline:
            return CallExit("expired", b.date, b.close)
        history.append(b)
        peak = max(peak, b.close)
        prev = b
    return None


def regime_state(
    xbi_closes: Sequence[float | None],
    windows: Sequence[int] = REGIME_WINDOWS,
) -> dict:
    """XBI regime-gate state on the PRIOR-CLOSE convention.

    `xbi_closes` are benchmark closes ordered oldest→newest THROUGH the as-of
    day. The state actionable at the as-of day's open is the PRIOR trading
    day's close vs the SMA ending at that prior day (the counter-agent
    correction: the gate flips the day AFTER a cross, never the day of).
    An SMA with insufficient history is None — an undefined gate never binds.
    """
    closes = [c for c in xbi_closes if c is not None]
    out: dict = {"prior_close": None}
    for w in windows:
        out[f"sma_{w}"] = None
        out[f"above_{w}dma"] = None
    if len(closes) < 2:
        return out
    prior = closes[:-1]
    out["prior_close"] = prior[-1]
    for w in windows:
        if len(prior) >= w:
            sma = sum(prior[-w:]) / w
            out[f"sma_{w}"] = sma
            out[f"above_{w}dma"] = prior[-1] > sma
    return out


# --- DB wiring (Session-taking, same shape as manager.py) ---------------------

def _bars_for(session: Session, symbol: str, since: date) -> list[BarLike]:
    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= since)
        .order_by(PriceBar.date.asc())
    ).all()
    return [BarLike(b.date, b.high, b.low, b.close, b.open) for b in rows]


def _backfill_atr_at_entry(
    session: Session, call: TradeCall, atr_window: int, stop_atr_mult: float
) -> float | None:
    """ATR14 as of the call date for a pre-feature call missing the snapshot.

    Recomputed from the same bars generate_calls saw; when even that is
    unavailable, the stored build_levels risk implies it (risk / stop mult —
    the R2-A convention of trusting the frozen fire-time risk unit).
    """
    bars = [
        b
        for b in _bars_for(session, call.symbol, call.call_date - timedelta(days=atr_window * 3))
        if b.date <= call.call_date
    ]
    value = atr(bars, atr_window)
    if value is None:
        risk = call.entry_price - call.stop_price
        value = (risk / stop_atr_mult) if risk > 0 else None
    return value


def evaluate_shadow_calls(session: Session, asof: date | None = None) -> list[ShadowGrade]:
    """Grade every not-yet-shadow-graded auto-call under the trailing engine.

    Runs in the same scheduler cycle as evaluate_calls but is fully
    independent of it: a live call may close while its shadow stays open and
    vice versa. A ShadowGrade row is written only when the shadow engine
    exits; r_multiple uses the LIVE call's risk unit (entry - stop) so R is
    comparable across engines on the same call. Idempotent — a graded call
    is never re-graded. Returns the grades recorded this run.
    """
    asof = asof or date.today()
    risk_cfg = calls_config().get("risk", {})
    atr_window = risk_cfg.get("atr_window", 14)
    stop_atr_mult = risk_cfg.get("stop_atr_mult", 3.0)

    graded_ids = {
        g.call_id
        for g in session.exec(
            select(ShadowGrade).where(ShadowGrade.engine == ENGINE_TRAILING)
        ).all()
    }
    calls = session.exec(select(TradeCall).where(TradeCall.source == "auto_flag")).all()

    made: list[ShadowGrade] = []
    dirty = False
    for call in calls:
        if call.id in graded_ids or call.direction != "long":
            continue
        if call.atr_at_entry is None:
            value = _backfill_atr_at_entry(session, call, atr_window, stop_atr_mult)
            if value is not None:
                call.atr_at_entry = round(value, 6)
                session.add(call)
                dirty = True
        bars = _bars_for(session, call.symbol, call.call_date - timedelta(days=atr_window * 3))
        exit_ = grade_trailing(
            bars, call.entry_price, call.call_date, call.atr_at_entry,
            TRAIL_MULT, TIME_STOP_DAYS, atr_window,
        )
        if exit_ is None:
            # Same data-gap failsafe as evaluate_calls: a long gap past the
            # time-stop must not leave the shadow position open forever.
            deadline = call.call_date + timedelta(days=TIME_STOP_DAYS)
            post = [b for b in bars if b.date > call.call_date and b.close is not None]
            if asof > deadline + timedelta(days=7) and post:
                exit_ = CallExit("expired", post[-1].date, post[-1].close)
            if exit_ is None:
                continue
        made.append(ShadowGrade(
            call_id=call.id,
            engine=ENGINE_TRAILING,
            status=exit_.status,
            exit_date=exit_.exit_date,
            exit_price=round(exit_.exit_price, 4),
            r_multiple=call_r_multiple(
                call.direction, call.entry_price, call.stop_price, exit_.exit_price
            ),
        ))
        session.add(made[-1])
    if made or dirty:
        session.commit()
        for g in made:
            session.refresh(g)
    if made:
        logger.info(
            "Shadow-graded %d call(s) under %s: %s",
            len(made), ENGINE_TRAILING, [(g.call_id, g.status) for g in made],
        )
    return made


def log_regime(session: Session) -> RegimeLog | None:
    """Log today's (latest XBI bar's) regime-gate state — one row per XBI
    trading day, idempotent, never rewritten. None when XBI has <2 bars."""
    from ..scoring.outcomes import BENCH

    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == BENCH)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.desc())
        .limit(max(REGIME_WINDOWS) + 1)
    ).all()
    rows.reverse()
    if len(rows) < 2:
        return None
    latest = rows[-1]
    existing = session.get(RegimeLog, latest.date)
    if existing is not None:
        return existing
    state = regime_state([r.close for r in rows])
    row = RegimeLog(
        date=latest.date,
        xbi_close=latest.close,
        above_50dma=state["above_50dma"],
        above_200dma=state["above_200dma"],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def shadow_track_record(session: Session) -> dict:
    """Per-engine comparison on the SAME calls — the H11 live evidence.

    Only CLOSED PAIRS (live call closed AND shadow graded) enter the
    comparison, so both engines are always measured on identical trades.
    Hit = R > 0 on both sides (same basis both engines). Pending buckets
    make the independence visible; regime carries H8's gate log summary.
    """
    calls = session.exec(select(TradeCall).where(TradeCall.source == "auto_flag")).all()
    grades = {
        g.call_id: g
        for g in session.exec(
            select(ShadowGrade).where(ShadowGrade.engine == ENGINE_TRAILING)
        ).all()
    }
    pairs = [(c, grades[c.id]) for c in calls if c.status in _CLOSED and c.id in grades]

    def _side(rs: list[float | None], statuses: list[str]) -> dict:
        done = [r for r in rs if r is not None]
        counts: dict[str, int] = {}
        for s in statuses:
            counts[s] = counts.get(s, 0) + 1
        return {
            "hit_rate": (sum(1 for r in done if r > 0) / len(done)) if done else None,
            "avg_r": (sum(done) / len(done)) if done else None,
            "total_r": sum(done) if done else None,
            "by_status": counts,
        }

    regime_rows = session.exec(select(RegimeLog)).all()
    latest_regime = max(regime_rows, key=lambda r: r.date) if regime_rows else None
    return {
        "engine": ENGINE_TRAILING,
        "params": {"trail_mult": TRAIL_MULT, "time_stop_days": TIME_STOP_DAYS},
        "closed_pairs": {
            "n": len(pairs),
            "production": _side(
                [c.r_multiple for c, _ in pairs], [c.status for c, _ in pairs]
            ),
            ENGINE_TRAILING: _side(
                [g.r_multiple for _, g in pairs], [g.status for _, g in pairs]
            ),
        },
        "pending": {
            "live_open_shadow_closed": sum(
                1 for c in calls if c.status == "open" and c.id in grades
            ),
            "live_closed_shadow_open": sum(
                1 for c in calls if c.status in _CLOSED and c.id not in grades
            ),
            "both_open": sum(
                1 for c in calls if c.status == "open" and c.id not in grades
            ),
        },
        "regime": {
            "date": latest_regime.date if latest_regime else None,
            "xbi_close": latest_regime.xbi_close if latest_regime else None,
            "above_50dma": latest_regime.above_50dma if latest_regime else None,
            "above_200dma": latest_regime.above_200dma if latest_regime else None,
            "days_logged": len(regime_rows),
            # H8's gate is the 200dma: days the book WOULD have refused entries.
            "days_gated_off_200dma": sum(
                1 for r in regime_rows if r.above_200dma is False
            ),
        },
        "note": (
            "observe-only shadow book (H11/H8) — live calls, levels, and the "
            "paper account are unaffected"
        ),
    }
