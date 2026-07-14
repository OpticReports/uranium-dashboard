"""The "Today" landing payload: what is this, what's actionable right now, why.

Built for the desk's routine — EST, trading the NYSE open. One request returns:
  - the market regime strip (XBI/ARKG/NBI trend),
  - actionable setups (recent flags packaged as tradeable cards: why it fired,
    catalyst, suggested levels, liquidity tier, binary-event framing),
  - open trade calls at a glance,
  - this week's catalysts,
  - a pre-market digest (movers since the prior close, signal movers).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..calls import manager as call_mgr
from ..calls.rules import BarLike, atr, build_levels
from ..utils.labels import event_label as _event_label
from ..config import calls_config, scoring_config
from ..db import get_session
from ..models import (
    Catalyst,
    FlagEvent,
    Fundamental,
    PriceBar,
    ScoreSnapshot,
    Security,
    SocialMention,
    TradeCall,
)

router = APIRouter(prefix="/views", tags=["views"])

NY = ZoneInfo("America/New_York")
BINARY_IMPACT = 0.7


def _ny_today() -> date:
    """The desk trades NYSE from EST — 'today' means New York, not UTC.
    (At 8pm ET, UTC has already rolled over; days-until math would be off by one.)"""
    return datetime.now(NY).date()
PURPOSE = (
    "This dashboard hunts forward-looking alpha in the genomics universe: it "
    "scores every name on catalysts, analyst revisions, social hype, positioning "
    "and cash runway, flags actionable setups, and logs exact trade calls that "
    "it grades against what price actually did."
)


# --- price / benchmark helpers -------------------------------------------------

def _closes(session: Session, symbol: str, days: int) -> list[tuple[date, float]]:
    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= _ny_today() - timedelta(days=days))
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.asc())
    ).all()
    return [(b.date, b.close) for b in rows]


def _trailing_return(closes: list[tuple[date, float]], bars_back: int) -> float | None:
    """Return over the last `bars_back` TRADING bars (not calendar days)."""
    if len(closes) < bars_back + 1:
        return None
    then, now = closes[-bars_back - 1][1], closes[-1][1]
    if not then:
        return None
    return (now - then) / then


def _above_ma(closes: list[tuple[date, float]], window: int) -> bool | None:
    if len(closes) < window:
        return None
    vals = [c for _, c in closes[-window:]]
    return closes[-1][1] > sum(vals) / len(vals)


def regime_payload(session: Session) -> dict:
    """Benchmark trend strip. XBI is the primary sector barometer."""
    benches = [str(s).upper() for s in scoring_config().get("benchmarks", [])]
    out = []
    label = None
    for sym in benches:
        closes = _closes(session, sym, 160)
        r20 = _trailing_return(closes, 20)
        r60 = _trailing_return(closes, 60)
        above50 = _above_ma(closes, 50)
        out.append({
            "symbol": sym,
            "last_close": closes[-1][1] if closes else None,
            "return_20d": r20,
            "return_60d": r60,
            "above_50dma": above50,
        })
        if sym == "XBI" and r20 is not None and above50 is not None:
            if r20 > 0.03 and above50:
                label = "risk-on"
            elif r20 < -0.03 and not above50:
                label = "risk-off"
            else:
                label = "neutral"
    return {
        "label": label,   # null until XBI history has been ingested
        "benchmarks": out,
        "note": "XBI 20-day trend + 50-day MA define the sector regime label.",
    }


def relative_strength(
    session: Session,
    symbol: str,
    bench: str = "XBI",
    bench_closes: list[tuple[date, float]] | None = None,
) -> dict[str, float | None]:
    """Name return minus benchmark return over 20/60 trading bars (unadjusted
    excess return — not beta-adjusted). Pass `bench_closes` to avoid
    re-fetching the benchmark series per name."""
    sym_closes = _closes(session, symbol, 160)
    ben_closes = bench_closes if bench_closes is not None else _closes(session, bench, 160)
    out: dict[str, float | None] = {}
    for label, n in (("rs_20d", 20), ("rs_60d", 60)):
        rs_sym = _trailing_return(sym_closes, n)
        rs_ben = _trailing_return(ben_closes, n)
        out[label] = None if (rs_sym is None or rs_ben is None) else rs_sym - rs_ben
    return out


def implied_move(iv: float | None, days_until: int | None) -> float | None:
    """Expected |move| through the event date: ~0.8 * IV * sqrt(t).

    (0.8 ≈ 2/√2π converts vol to expected absolute move, straddle-style.)
    This is the DIFFUSIVE move through the period, not the event-day jump —
    it understates binary risk, which is why the framing text says so.
    """
    if iv is None or days_until is None or days_until <= 0:
        return None
    return 0.8 * iv * math.sqrt(days_until / 365.0)


# --- endpoint -------------------------------------------------------------------

@router.get("/regime")
def regime(session: Session = Depends(get_session)):
    return regime_payload(session)


@router.get("/today")
def today_view(session: Session = Depends(get_session)):
    from ..scoring.outcomes import flag_track_record, outcome_key

    today = _ny_today()
    now = datetime.utcnow()
    secs = {s.symbol: s for s in session.exec(select(Security)).all()}
    active = {sym: s for sym, s in secs.items() if s.active}

    # Data freshness: the most recent bar anywhere in the universe. Everything
    # on this page is computed off daily closes — say so, loudly.
    latest_bar = session.exec(
        select(PriceBar.date).order_by(PriceBar.date.desc()).limit(1)
    ).first()
    track = flag_track_record(session).get("by_flag_type", {})

    # One benchmark fetch serves every card's relative-strength calc.
    bench_closes = _closes(session, "XBI", 160)

    def _hit_rate_for(flag: FlagEvent) -> dict | None:
        t = track.get(outcome_key(flag.flag_type, flag.evidence))
        if not t:
            return None
        h1m = t.get("horizons", {}).get("1m", {})
        # n matches the hit-rate's declared basis (excess vs raw) — never a
        # benchmark-relative rate paired with a raw count.
        return {
            "fired": t.get("fired"),
            "n_graded_1m": h1m.get("n"),
            "hit_rate_1m": h1m.get("hit_rate"),
            "avg_excess_1m": h1m.get("avg_excess"),
            "vs_benchmark": h1m.get("vs_benchmark", False),
            "sufficient": (h1m.get("n") or 0) >= 10,
        }

    # Latest composite per name — recency-bounded (hourly scoring would
    # otherwise make this a full-history table scan on every page load).
    latest_score: dict[str, ScoreSnapshot] = {}
    for snap in session.exec(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.asof >= now - timedelta(days=14))
        .order_by(ScoreSnapshot.asof.asc())
    ).all():
        latest_score[snap.symbol] = snap

    # --- actionable: fresh flags (48h), deduped to newest per (symbol, type) ---
    since = now - timedelta(hours=48)
    fresh: dict[str, dict[str, FlagEvent]] = {}
    for f in session.exec(
        select(FlagEvent).where(FlagEvent.asof >= since).order_by(FlagEvent.asof.asc())
    ).all():
        if f.symbol in active:
            fresh.setdefault(f.symbol, {})[f.flag_type] = f

    risk_cfg = calls_config().get("risk", {})
    atr_window = risk_cfg.get("atr_window", 14)

    cards = []
    for sym, flags in fresh.items():
        sec = active[sym]
        snap = latest_score.get(sym)
        closes = _closes(session, sym, 40)
        last_close = closes[-1][1] if closes else None
        chg_1d = _trailing_return(closes, 1)

        # Reference levels — same ATR math the calls engine uses, anchored on
        # the LAST CLOSE and labeled as such: these are NOT a logged call, and
        # they are stale the moment price gaps (flag hit-rates + the Calls Log
        # are the graded record; this is orientation).
        suggested = None
        if last_close and closes:
            bars = call_mgr._recent_bars(session, sym, today - timedelta(days=atr_window * 3))
            lv = build_levels(
                entry=last_close, direction="long",
                atr_value=atr(bars, atr_window),
                stop_atr_mult=risk_cfg.get("stop_atr_mult", 3.0),
                fallback_stop_pct=risk_cfg.get("fallback_stop_pct", 0.08),
                reward_risk=risk_cfg.get("reward_risk", 2.0),
            )
            if lv:
                suggested = {
                    "entry": round(lv.entry, 2), "stop": round(lv.stop, 2),
                    "target": round(lv.target, 2),
                    "anchored_on_close_of": closes[-1][0].isoformat(),
                    "note": "reference levels off the last close — recompute if price has gapped",
                }

        # Next catalyst + binary framing.
        nxt = session.exec(
            select(Catalyst).where(Catalyst.symbol == sym)
            .where(Catalyst.date >= today).order_by(Catalyst.date.asc()).limit(1)
        ).first()
        binary = None
        if nxt is not None and nxt.effective_impact >= BINARY_IMPACT:
            fund = session.exec(
                select(Fundamental).where(Fundamental.symbol == sym)
                .order_by(Fundamental.asof.desc()).limit(1)
            ).first()
            days_until = (nxt.date - today).days
            im = implied_move(fund.iv if fund else None, days_until)
            binary = {
                "event_type": nxt.event_type,
                "date": nxt.date.isoformat(),
                "days_until": days_until,
                "impact": nxt.effective_impact,
                "implied_move_pct": im,
                "framing": (
                    f"Binary event risk: {_event_label(nxt.event_type)} in {days_until} days — "
                    "desk default is to exit before it. "
                    + (f"Options pricing implies a ±{im:.0%} move by the event date."
                       if im is not None else
                       "No options data to size the expected move — treat gap risk as unbounded.")
                ),
            }

        # 7d social sentiment.
        mentions = session.exec(
            select(SocialMention).where(SocialMention.symbol == sym)
            .where(SocialMention.date >= today - timedelta(days=7))
        ).all()
        sentis = [m.sentiment for m in mentions if m.sentiment is not None]
        sentiment_7d = (sum(sentis) / len(sentis)) if sentis else None

        cards.append({
            "symbol": sym,
            "name": sec.name,
            "composite": snap.composite if snap else None,
            "score_missing": snap.missing if snap else None,
            "flags": [
                {"type": f.flag_type, "severity": f.severity,
                 "message": f.message, "asof": f.asof.isoformat(),
                 "track_record": _hit_rate_for(f)}
                for f in sorted(flags.values(), key=lambda f: f.asof, reverse=True)
            ],
            "last_price": last_close,
            "price_change_1d": chg_1d,
            "suggested_levels": suggested,
            "liquidity": call_mgr.symbol_liquidity(session, sym),
            "relative_strength": relative_strength(session, sym, bench_closes=bench_closes),
            "next_catalyst": None if nxt is None else {
                "event_type": nxt.event_type, "title": nxt.title,
                "date": nxt.date.isoformat(),
                "days_until": (nxt.date - today).days,
                "impact": nxt.effective_impact,
            },
            "binary_event": binary,
            "sentiment_7d": sentiment_7d,
        })
    cards.sort(key=lambda c: (c["composite"] is None, -(c["composite"] or 0)))

    # --- open calls at a glance (with a signal-decay early exit hint) ---
    open_calls = []
    for c in session.exec(
        select(TradeCall).where(TradeCall.status == "open")
        .order_by(TradeCall.created_at.desc())
    ).all():
        latest = call_mgr._latest_close(session, c.symbol)
        last = latest[1] if latest else None
        comp_now = latest_score[c.symbol].composite if c.symbol in latest_score else None
        decay = (
            comp_now - c.composite_at_call
            if comp_now is not None and c.composite_at_call is not None else None
        )
        open_calls.append({
            "id": c.id, "symbol": c.symbol, "direction": c.direction,
            "entry": c.entry_price, "stop": c.stop_price, "target": c.target_price,
            "last_price": last,
            "unrealized_pct": (None if last is None else
                               (last - c.entry_price) / c.entry_price
                               * (-1 if c.direction == "short" else 1)),
            "expires_on": c.expires_on.isoformat(),
            "flag_type": c.flag_type, "source": c.source,
            "composite_at_call": c.composite_at_call,
            "composite_now": comp_now,
            "signal_decay": decay,   # strongly negative = thesis eroding; consider exiting early
        })

    # --- catalysts this week ---
    week = []
    for c in session.exec(
        select(Catalyst).where(Catalyst.date >= today)
        .where(Catalyst.date <= today + timedelta(days=7))
        .order_by(Catalyst.date.asc())
    ).all():
        if c.symbol in active:
            week.append({
                "symbol": c.symbol, "date": c.date.isoformat(),
                "days_until": (c.date - today).days,
                "event_type": c.event_type, "title": c.title,
                "impact": c.effective_impact, "confirmed": c.confirmed,
            })

    # --- digest: price moves since the prior close + biggest signal movers ---
    movers = []
    for sym, sec in active.items():
        closes = _closes(session, sym, 10)
        chg = _trailing_return(closes, 1)
        if chg is not None:
            movers.append({"symbol": sym, "name": sec.name, "change": chg,
                           "last_price": closes[-1][1],
                           "composite": (latest_score[sym].composite
                                         if sym in latest_score else None)})
    movers.sort(key=lambda m: m["change"])
    digest = {
        "as_of_note": "Latest bar vs the prior close — pre-market digest for the EST open.",
        "biggest_down": movers[:5],
        "biggest_up": list(reversed(movers[-5:])),
        "new_flags_24h": sum(
            1 for flags in fresh.values() for f in flags.values()
            if f.asof >= now - timedelta(hours=24)
        ),
    }

    return {
        "asof": now.isoformat(),
        "ny_date": today.isoformat(),
        "data_asof": latest_bar.isoformat() if latest_bar else None,
        "data_note": (
            "All numbers are computed from DAILY bars — the latest close on "
            "record, not live quotes. Recheck levels if price has moved since."
        ),
        "purpose": PURPOSE,
        "regime": regime_payload(session),
        "actionable": cards,
        "open_calls": open_calls,
        "catalysts_7d": week,
        "digest": digest,
    }
