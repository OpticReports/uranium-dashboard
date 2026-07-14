"""Post-mortems: WHY a closed call went right or wrong, from the data.

Every closed call gets an attribution record built from what actually printed:

  - path: max favorable / adverse excursion in R (did it ever work? did we
    round-trip a winner?)
  - attribution: the name's move split into sector beta (XBI over the same
    window) vs idiosyncratic alpha
  - signal: composite at call vs at exit (did the thesis decay before price?)
  - catalyst: exited before the binary as designed, or event passed mid-trade
  - hindsight stop verdict (filled ~10 bars AFTER exit): a stop that kept
    falling PROTECTED capital; one that snapped back above entry was a
    SHAKEOUT — the single most useful stat for retuning stop width.

The summary text is composed deterministically from these facts — no LLM, no
opinion, reproducible from the row. Post-mortems are attached to the immutable
call, never edited into it.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlmodel import Session, select

from ..models import CallPostmortem, Catalyst, PriceBar, ScoreSnapshot, TradeCall

logger = logging.getLogger(__name__)

BENCH = "XBI"
POST_EXIT_BARS = 10  # hindsight window for the stop verdict


def _bars(session: Session, symbol: str, start: date, end: date | None = None) -> list[PriceBar]:
    stmt = (
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= start)
        .order_by(PriceBar.date.asc())
    )
    if end is not None:
        stmt = stmt.where(PriceBar.date <= end)
    return session.exec(stmt).all()


def _close_on_or_before(session: Session, symbol: str, d: date) -> float | None:
    bar = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date <= d)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.desc())
        .limit(1)
    ).first()
    return bar.close if bar else None


def build_postmortem(session: Session, call: TradeCall) -> CallPostmortem | None:
    """Assemble the facts for one closed call. Returns None while call is open."""
    if call.status == "open" or call.exit_date is None or call.exit_price is None:
        return None
    risk = abs(call.entry_price - call.stop_price)
    if risk == 0:
        return None
    sign = -1.0 if call.direction == "short" else 1.0

    # --- path: excursions between entry and exit (bars AFTER the call date) ---
    trade_bars = [
        b for b in _bars(session, call.symbol, call.call_date, call.exit_date)
        if b.date > call.call_date and b.high is not None and b.low is not None
    ]
    mfe_r = mae_r = None
    if trade_bars:
        if call.direction == "short":
            best = min(b.low for b in trade_bars)
            worst = max(b.high for b in trade_bars)
        else:
            best = max(b.high for b in trade_bars)
            worst = min(b.low for b in trade_bars)
        mfe_r = max(0.0, sign * (best - call.entry_price) / risk)
        mae_r = max(0.0, -sign * (worst - call.entry_price) / risk)

    # --- attribution: name vs sector over the same window ---
    bench_entry = _close_on_or_before(session, BENCH, call.call_date)
    bench_exit = _close_on_or_before(session, BENCH, call.exit_date)
    bench_return = (
        (bench_exit - bench_entry) / bench_entry
        if bench_entry and bench_exit else None
    )
    name_return = call.return_pct
    alpha = (
        name_return - sign * bench_return
        if name_return is not None and bench_return is not None else None
    )

    # --- signal decay ---
    snap = session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.symbol == call.symbol)
        .order_by(ScoreSnapshot.asof.desc())
        .limit(1)
    ).first()
    composite_at_exit = snap.composite if snap else None
    decay = (
        composite_at_exit - call.composite_at_call
        if composite_at_exit is not None and call.composite_at_call is not None else None
    )

    # --- catalyst context ---
    nxt = session.exec(
        select(Catalyst)
        .where(Catalyst.symbol == call.symbol)
        .where(Catalyst.date > call.call_date)
        .order_by(Catalyst.date.asc())
        .limit(1)
    ).first()
    if nxt is None:
        catalyst_status = "no_catalyst"
    elif nxt.date > call.exit_date:
        catalyst_status = "exited_before_event"
    else:
        catalyst_status = "event_passed_during_trade"

    pm = CallPostmortem(
        call_id=call.id,
        mfe_r=mfe_r,
        mae_r=mae_r,
        name_return=name_return,
        bench_return=bench_return,
        alpha=alpha,
        composite_at_exit=composite_at_exit,
        signal_decay=decay,
        catalyst_status=catalyst_status,
    )
    pm.summary = compose_summary(call, pm)
    return pm


def finalize_hindsight(session: Session, pm: CallPostmortem, call: TradeCall) -> bool:
    """Fill the post-exit verdict once ~POST_EXIT_BARS bars have printed.

    stopped  -> did price keep going against us (stop PROTECTED capital) or
                snap back above entry (SHAKEOUT — stop too tight)?
    win/expiry -> did it keep running >=1R past our exit (EXITED_EARLY) or not
                (CLEAN_EXIT)?
    Returns True when the verdict was written.
    """
    after = [
        b for b in _bars(session, call.symbol, call.exit_date + timedelta(days=1))
        if b.close is not None
    ][:POST_EXIT_BARS]
    if len(after) < POST_EXIT_BARS:
        return False  # not enough hindsight yet — try again later
    risk = abs(call.entry_price - call.stop_price)
    sign = -1.0 if call.direction == "short" else 1.0
    closes = [b.close for b in after]

    if call.status == "stopped":
        kept_going = (min(closes) < call.stop_price) if sign > 0 else (max(closes) > call.stop_price)
        snapped_back = (max(closes) >= call.entry_price) if sign > 0 else (min(closes) <= call.entry_price)
        if kept_going and not snapped_back:
            pm.hindsight_verdict = "protected"
        elif snapped_back:
            pm.hindsight_verdict = "shakeout"
        else:
            pm.hindsight_verdict = "neutral"
    else:
        best_after = max(closes) if sign > 0 else min(closes)
        ran_on = sign * (best_after - call.exit_price) / risk >= 1.0 if risk else False
        pm.hindsight_verdict = "exited_early" if ran_on else "clean_exit"

    pm.hindsight_complete = True
    pm.summary = compose_summary(call, pm)
    return True


def compose_summary(call: TradeCall, pm: CallPostmortem) -> str:
    """Deterministic 'why it went right/wrong' prose from the facts."""
    parts: list[str] = []
    days = (call.exit_date - call.call_date).days if call.exit_date else None
    r = call.r_multiple

    outcome = {
        "target_hit": f"Target hit for {r:+.1f}R in {days}d.",
        "stopped": f"Stopped out for {r:+.1f}R after {days}d.",
        "expired": f"Time-stop exit at {r:+.1f}R after {days}d.",
        "closed_manual": f"Closed manually at {r:+.1f}R after {days}d.",
    }.get(call.status)
    if outcome and r is not None:
        parts.append(outcome)

    # Path: did it ever work / did we round-trip a winner?
    if pm.mfe_r is not None and r is not None:
        if call.status == "stopped" and pm.mfe_r >= 1.0:
            parts.append(
                f"It WAS working — peaked at {pm.mfe_r:+.1f}R before reversing; "
                "the give-back, not the entry, is what hurt."
            )
        elif call.status == "stopped" and pm.mfe_r < 0.3:
            parts.append(
                f"It never worked (max favorable move {pm.mfe_r:+.1f}R) — "
                "the entry premise looks wrong, not the exit."
            )
        elif call.status in ("target_hit",) and pm.mae_r is not None and pm.mae_r >= 0.8:
            parts.append(
                f"Won, but drew down {pm.mae_r:.1f}R along the way — "
                "the wide stop earned its keep."
            )

    # Attribution: sector beta vs the name.
    if pm.alpha is not None and pm.bench_return is not None:
        if abs(pm.bench_return) >= 0.05 and abs(pm.alpha) < abs(pm.name_return or 0) / 2:
            direction = "rallied" if pm.bench_return > 0 else "sold off"
            parts.append(
                f"Mostly a sector move: XBI {direction} {pm.bench_return:+.0%} over the "
                f"trade; idiosyncratic alpha was only {pm.alpha:+.0%}."
            )
        elif pm.alpha is not None and abs(pm.alpha) >= 0.05:
            parts.append(
                f"Name-specific move: {pm.alpha:+.0%} vs the sector "
                f"(XBI {pm.bench_return:+.0%})."
            )

    # Signal decay.
    if pm.signal_decay is not None and pm.signal_decay <= -15:
        parts.append(
            f"The signal decayed during the trade "
            f"(composite {call.composite_at_call:.0f}→{pm.composite_at_exit:.0f}) — "
            "the thesis faded before the exit did."
        )

    # Catalyst discipline.
    if pm.catalyst_status == "exited_before_event" and call.status == "expired":
        parts.append("Exited on the time-stop before the binary, as designed.")
    elif pm.catalyst_status == "event_passed_during_trade":
        parts.append("A catalyst passed mid-trade — outcome includes event risk.")

    # Hindsight verdict.
    if pm.hindsight_verdict == "protected":
        parts.append("Post-exit: price kept falling — the stop protected capital.")
    elif pm.hindsight_verdict == "shakeout":
        parts.append(
            "Post-exit: price recovered above entry within 10 bars — a SHAKEOUT; "
            "count these before blaming the signal (a pattern here means widen the stop)."
        )
    elif pm.hindsight_verdict == "exited_early":
        parts.append("Post-exit: it kept running ≥1R past our exit — left money on the table.")
    elif pm.hindsight_verdict == "clean_exit":
        parts.append("Post-exit: little further progress — a clean exit.")

    return " ".join(parts)


def update_postmortems(session: Session) -> int:
    """Create post-mortems for newly closed calls; finalize pending hindsight
    verdicts as post-exit bars accrue. Idempotent, runs on the calls job."""
    closed = session.exec(
        select(TradeCall).where(TradeCall.status != "open")
    ).all()
    existing = {p.call_id: p for p in session.exec(select(CallPostmortem)).all()}
    n = 0
    for call in closed:
        pm = existing.get(call.id)
        if pm is None:
            pm = build_postmortem(session, call)
            if pm is None:
                continue
            session.add(pm)
            n += 1
            existing[call.id] = pm
        if not pm.hindsight_complete:
            if finalize_hindsight(session, pm, call):
                session.add(pm)
                n += 1
    if n:
        session.commit()
        logger.info("Post-mortems created/updated: %d", n)
    return n
