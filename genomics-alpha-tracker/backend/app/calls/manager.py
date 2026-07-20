"""Trade-call lifecycle: generate from fresh flags, grade against bars, aggregate.

Three entry points, all idempotent and safe to run on a schedule:
  generate_calls()  — turn fresh high-conviction flags into exact calls
  evaluate_calls()  — grade open calls against daily bars (stop/target/expiry)
  scorecard()       — aggregate the track record (hit rate, avg R) per signal
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ..config import calls_config
from ..models import Catalyst, FlagEvent, PriceBar, ScoreSnapshot, Security, TradeCall
from .rules import (
    BarLike,
    addv,
    atr,
    build_levels,
    call_r_multiple,
    call_return,
    grade_call,
    liquidity_tier,
)

logger = logging.getLogger(__name__)

# Catalyst impact at/above which a call must exit BEFORE the event (the desk
# rarely holds through binaries).
_BINARY_IMPACT = 0.7


def _recent_bars(session: Session, symbol: str, since: date) -> list[BarLike]:
    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= since)
        .order_by(PriceBar.date.asc())
    ).all()
    return [BarLike(b.date, b.high, b.low, b.close, b.open) for b in rows]


def _latest_close(session: Session, symbol: str) -> tuple[date, float] | None:
    bar = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.desc())
        .limit(1)
    ).first()
    if bar is None or bar.close is None:
        return None
    return bar.date, bar.close


def _latest_composite(session: Session, symbol: str) -> float | None:
    snap = session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.symbol == symbol)
        .order_by(ScoreSnapshot.asof.desc())
        .limit(1)
    ).first()
    return snap.composite if snap else None


def _expiry_for(session: Session, symbol: str, call_date: date, cfg: dict) -> date | None:
    """Time-stop for a new call: the day before the nearest binary catalyst
    (sell into the event), else the default horizon.

    Returns None — REFUSE the call — when the binary is so close that a
    sell-before-the-event exit can't respect the minimum horizon. Stretching
    the expiry past the event instead would force holding through the binary,
    the one thing the desk said it never does.
    """
    h = cfg.get("horizon", {})
    default_days = h.get("default_days", 30)
    min_days = h.get("min_days", 5)
    max_days = h.get("max_days", 45)

    expiry = call_date + timedelta(days=default_days)
    nearest = session.exec(
        select(Catalyst)
        .where(Catalyst.symbol == symbol)
        .where(Catalyst.date > call_date)
        .order_by(Catalyst.date.asc())
    ).all()
    for c in nearest:
        if c.effective_impact >= _BINARY_IMPACT:
            binary_exit = c.date - timedelta(days=1)
            if binary_exit < call_date + timedelta(days=min_days):
                return None  # too close to the event to establish and exit
            expiry = min(expiry, binary_exit)
            break
    hi = call_date + timedelta(days=max_days)
    return min(expiry, hi)


def symbol_liquidity(session: Session, symbol: str) -> dict:
    """ADDV + liquidity tier + a sizing warning for one name.

    Tier A = deep, B = size with care above the warn threshold, C = thin-float
    (slippage at any size). None tier = no volume data.
    """
    cfg = calls_config().get("liquidity", {})
    window = cfg.get("addv_window_days", 20)
    tier_a = cfg.get("tier_a_min_addv", 25_000_000)
    tier_b = cfg.get("tier_b_min_addv", 5_000_000)
    warn_usd = cfg.get("warn_position_usd", 50_000)

    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .order_by(PriceBar.date.desc())
        .limit(window * 2)
    ).all()
    rows.reverse()
    bars = [BarLike(b.date, b.high, b.low, b.close) for b in rows]
    volumes = [b.volume for b in rows]
    value = addv(bars, volumes, window)
    tier = liquidity_tier(value, tier_a, tier_b)
    warning = None
    if tier == "B":
        warning = f"size with care above ${warn_usd/1000:.0f}k — ${value/1e6:.1f}M/day traded"
    elif tier == "C":
        warning = f"thin float — only ${value/1e6:.2f}M/day traded; expect slippage"
    return {"addv": value, "tier": tier, "warning": warning}


def _confidence_for(session, symbol, flag_type, composite, fresh_flags):
    """Fire-time confidence: setup quality × graded-edge × corroboration."""
    from ..scoring.outcomes import flag_track_record
    from .confidence import compute_confidence

    rec = flag_track_record(session).get("by_flag_type", {}).get(flag_type, {})
    h1m = rec.get("horizons", {}).get("1m", {})
    n_distinct = len({f.flag_type for f in fresh_flags if f.symbol == symbol}) or 1
    return compute_confidence(
        composite,
        hit_rate_1m=h1m.get("hit_rate"),
        n_1m=h1m.get("n") or 0,
        n_distinct_flags=n_distinct,
    )


def _flag_triggers_call(flag: FlagEvent, trigger_cfg: dict) -> bool:
    cond = trigger_cfg.get(flag.flag_type)
    if cond is None:
        return False
    want_dir = cond.get("direction")
    if want_dir and (flag.evidence or {}).get("direction") != want_dir:
        return False
    return True


def generate_calls(session: Session, asof: date | None = None) -> list[TradeCall]:
    """Turn fresh high-conviction flags into exact, logged trade calls.

    Conservative by design (false positives are the main failure mode): a flag
    only becomes a call if the name's composite clears `min_composite`, there is
    no open or recent call on the symbol, and the open-call cap has room.
    """
    cfg = calls_config()
    if not cfg or not cfg.get("enabled", True):
        return []
    asof = asof or date.today()
    triggers = cfg.get("triggers", {})
    if not triggers:
        return []

    since = datetime.utcnow() - timedelta(hours=cfg.get("flag_lookback_hours", 24))
    fresh = session.exec(
        select(FlagEvent)
        .where(FlagEvent.asof >= since)
        .order_by(FlagEvent.asof.desc())
    ).all()

    open_calls = session.exec(select(TradeCall).where(TradeCall.status == "open")).all()
    open_symbols = {c.symbol for c in open_calls}
    n_open_auto = sum(1 for c in open_calls if c.source == "auto_flag")
    max_open = cfg.get("max_open_calls", 10)

    cooldown_since = asof - timedelta(days=cfg.get("cooldown_days", 14))
    recent_call_symbols = {
        c.symbol
        for c in session.exec(
            select(TradeCall).where(TradeCall.call_date >= cooldown_since)
        ).all()
    }

    risk = cfg.get("risk", {})
    made: list[TradeCall] = []
    seen_this_run: set[str] = set()

    for flag in fresh:
        sym = flag.symbol
        if sym in open_symbols or sym in recent_call_symbols or sym in seen_this_run:
            continue
        if not _flag_triggers_call(flag, triggers):
            continue
        if n_open_auto + len(made) >= max_open:
            logger.info("Call cap (%d open) reached; skipping %s", max_open, sym)
            break

        sec = session.get(Security, sym)
        if sec is None or not sec.active:
            continue

        composite = _latest_composite(session, sym)
        if composite is None or composite < cfg.get("min_composite", 55):
            continue

        latest = _latest_close(session, sym)
        if latest is None:
            continue
        bar_date, entry = latest

        liq = symbol_liquidity(session, sym)
        if (
            liq["tier"] in (None, "C")
            and cfg.get("liquidity", {}).get("exclude_tier_c_from_auto_calls", True)
        ):
            logger.info("Skipping %s: liquidity tier %s (thin-float)", sym, liq["tier"])
            continue

        atr_window = risk.get("atr_window", 14)
        bars = _recent_bars(session, sym, bar_date - timedelta(days=atr_window * 3))
        levels = build_levels(
            entry=entry,
            direction="long",
            atr_value=atr(bars, atr_window),
            stop_atr_mult=risk.get("stop_atr_mult", 2.0),
            fallback_stop_pct=risk.get("fallback_stop_pct", 0.08),
            reward_risk=risk.get("reward_risk", 2.0),
        )
        if levels is None:
            continue

        expires_on = _expiry_for(session, sym, bar_date, cfg)
        if expires_on is None:
            logger.info("Skipping %s: binary catalyst too close to trade into", sym)
            continue

        # Confidence, frozen at fire-time: setup quality bent by this flag
        # type's graded track record and corroborated by any other fresh flags
        # on the same name.
        confidence = _confidence_for(session, sym, flag.flag_type, composite, fresh)

        call = TradeCall(
            symbol=sym,
            call_date=bar_date,
            direction="long",
            source="auto_flag",
            flag_type=flag.flag_type,
            thesis=(
                f"{flag.message}. Composite {composite:.0f}. "
                f"Long {sym} at {levels.entry:.2f}, stop {levels.stop:.2f}, "
                f"target {levels.target:.2f}, time-stop {expires_on.isoformat()}."
            ),
            entry_price=round(levels.entry, 4),
            stop_price=round(levels.stop, 4),
            target_price=round(levels.target, 4),
            expires_on=expires_on,
            composite_at_call=composite,
            confidence=confidence,
            evidence={
                "flag_id": flag.id,
                "flag_type": flag.flag_type,
                "flag_message": flag.message,
                "flag_evidence": flag.evidence,
                # Stamped at fire-time so the scorecard can later be cut by
                # liquidity tier (thin names behave differently).
                "liquidity": {"tier": liq["tier"], "addv": liq["addv"]},
            },
        )
        session.add(call)
        made.append(call)
        seen_this_run.add(sym)

    if made:
        session.commit()
        for c in made:
            session.refresh(c)
        logger.info("Generated %d trade call(s): %s", len(made), [c.symbol for c in made])
    return made


def evaluate_calls(session: Session, asof: date | None = None) -> list[TradeCall]:
    """Grade every open call against daily bars AFTER the call date.

    Entry is assumed at the call-date close, so the call date's own bar never
    grades the call. Returns the calls that were closed this run.
    """
    asof = asof or date.today()
    open_calls = session.exec(select(TradeCall).where(TradeCall.status == "open")).all()
    closed: list[TradeCall] = []
    for call in open_calls:
        bars = [
            b
            for b in _recent_bars(session, call.symbol, call.call_date)
            if b.date > call.call_date
        ]
        exit_ = grade_call(
            call.direction, call.entry_price, call.stop_price,
            call.target_price, call.expires_on, bars,
        )
        if exit_ is None:
            # No bar has printed on/past expiry yet; a long data gap past the
            # time-stop should not leave the call open forever.
            if asof > call.expires_on + timedelta(days=7) and bars:
                last = bars[-1]
                exit_ = grade_call(
                    call.direction, call.entry_price, call.stop_price,
                    call.target_price, last.date, [last],
                )
            if exit_ is None:
                continue
        call.status = exit_.status
        call.exit_date = exit_.exit_date
        call.exit_price = round(exit_.exit_price, 4)
        call.closed_at = datetime.utcnow()
        call.return_pct = call_return(call.direction, call.entry_price, exit_.exit_price)
        call.r_multiple = call_r_multiple(
            call.direction, call.entry_price, call.stop_price, exit_.exit_price
        )
        session.add(call)
        closed.append(call)
    if closed:
        session.commit()
        for c in closed:
            session.refresh(c)
        logger.info(
            "Closed %d call(s): %s",
            len(closed), [(c.symbol, c.status) for c in closed],
        )
    return closed


def close_call_manual(
    session: Session, call: TradeCall, exit_price: float | None, note: str | None = None
) -> TradeCall:
    """Operator override: close a call now at `exit_price` (or the last close)."""
    if exit_price is None:
        latest = _latest_close(session, call.symbol)
        if latest is None:
            raise ValueError(f"no price data to close {call.symbol}")
        exit_date, exit_price = latest
    else:
        exit_date = date.today()
    call.status = "closed_manual"
    call.exit_date = exit_date
    call.exit_price = round(exit_price, 4)
    call.closed_at = datetime.utcnow()
    call.return_pct = call_return(call.direction, call.entry_price, exit_price)
    call.r_multiple = call_r_multiple(
        call.direction, call.entry_price, call.stop_price, exit_price
    )
    if note:
        call.thesis = f"{call.thesis}\n[closed manually] {note}".strip()
    session.add(call)
    session.commit()
    session.refresh(call)
    return call


_CLOSED = ("target_hit", "stopped", "expired", "closed_manual")


def scorecard(session: Session) -> dict:
    """The tracker's own track record, overall and per signal type.

    Groups auto calls by their triggering flag type and manual/chat calls by
    source, so "which signals actually pay" is answerable at a glance.
    """
    calls = session.exec(select(TradeCall)).all()

    def _bucket(rows: list[TradeCall]) -> dict:
        done = [c for c in rows if c.status in _CLOSED]
        wins = [c for c in done if (c.return_pct or 0) > 0]
        rets = [c.return_pct for c in done if c.return_pct is not None]
        rs = [c.r_multiple for c in done if c.r_multiple is not None]
        return {
            "calls": len(rows),
            "open": sum(1 for c in rows if c.status == "open"),
            "closed": len(done),
            "target_hit": sum(1 for c in done if c.status == "target_hit"),
            "stopped": sum(1 for c in done if c.status == "stopped"),
            "expired": sum(1 for c in done if c.status == "expired"),
            "win_rate": (len(wins) / len(done)) if done else None,
            "avg_return_pct": (sum(rets) / len(rets)) if rets else None,
            "avg_r": (sum(rs) / len(rs)) if rs else None,
            "total_r": sum(rs) if rs else None,
        }

    by_signal: dict[str, list[TradeCall]] = {}
    for c in calls:
        key = c.flag_type if (c.source == "auto_flag" and c.flag_type) else c.source
        by_signal.setdefault(key, []).append(c)

    return {
        "overall": _bucket(calls),
        "by_signal": {k: _bucket(v) for k, v in sorted(by_signal.items())},
    }
