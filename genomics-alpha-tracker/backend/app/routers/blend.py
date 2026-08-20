"""blend3070 intents API — the tracker half of the H13 30/70 execution path.

GET /blend3070/intents publishes, once per trading day, everything the
KEYLESS tracker knows that the ibkr-executor's Blend3070Manager needs:
fresh gate-on auto-call fires (entry candidates), the R2-A trailing-stop
level for every position the tracker's shadow machinery still tracks as
open (for the executor's daily GTC cancel/replace), and trail/time-stop
exit signals.

Separation of powers (CLAUDE.md law): this endpoint holds no credentials,
places no orders, and NEVER learns the executor's positions or account
equity. It therefore publishes CANDIDATES and LEVELS keyed by call_id; the
executor reconciles them against its own book and does all dollar sizing.
The `contract` field in the response states this machine-readably.

All gate and trailing math is IMPORTED from calls/shadow.py (the H11
reference implementation) — nothing is re-derived here. The one helper,
`current_trail_level`, obtains the live trail by driving grade_trailing
itself with a synthetic probe bar, so the published level is by
construction the exact level shadow grading would stop at tomorrow.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..calls.rules import BarLike
from ..calls.shadow import (
    ENGINE_TRAILING,
    TIME_STOP_DAYS,
    TRAIL_MULT,
    _backfill_atr_at_entry,
    _bars_for,
    grade_trailing,
    regime_state,
)
from ..db import get_session
from ..models import PriceBar, RegimeLog, ShadowGrade, TradeCall

router = APIRouter(prefix="/blend3070", tags=["blend"])

# H13 registered construction (docs/BACKTEST_VARIANTS_R2.md R2-A + the 30/70
# H13 entry): 30% R2-A sleeve / 70% SPY, 5pp rebalance band, BIL on idle
# sleeve cash, <=10 open, 1% of sleeve equity risked per call.
BOOK_PARAMS = {
    "max_open": 10,
    "risk_frac": 0.01,
    "band": 0.05,
    "cash_vehicle": "BIL",
    "core": "SPY",
}

# Exit signals stay visible this many days after the shadow engine graded
# them, so an executor that polls after the scheduler's shadow pass still
# sees the exit (its resting GTC stop and own 90d clock are the backstops).
_EXIT_ECHO_DAYS = 7

_ATR_WINDOW = 14

CONTRACT = (
    "The tracker knows fires, bars, the XBI gate, and per-call R2-A trail "
    "levels; it does NOT know the executor's positions or account equity. "
    "entries are CANDIDATE fires (risk_frac of SLEEVE equity each, sized in "
    "dollars executor-side); stops/exits carry levels for every call the "
    "tracker's shadow book still tracks as open — the executor acts only on "
    "call_ids it actually holds and ignores the rest. rebalance.needed is "
    "null because sleeve weights live executor-side: the executor computes "
    "drift against target and rebalances beyond the band. Exit rows are "
    "advisory same-day signals (echoed %d days); the executor's resting GTC "
    "stops and its own %d-calendar-day clock are the real backstops."
    % (_EXIT_ECHO_DAYS, TIME_STOP_DAYS)
)


# --- pure helpers -------------------------------------------------------------

def current_trail_level(
    bars: Sequence[BarLike],
    entry: float,
    entry_date: date,
    atr_at_entry: float | None,
) -> float | None:
    """The trailing-stop level actionable at the NEXT open, per shadow.py.

    Computed by grade_trailing ITSELF, not a re-derivation: a synthetic probe
    bar (open far above any trail, low far below) is appended one day after
    the last real bar; grade_trailing then stops "at the trail", and that
    fill price IS the ratcheted level with peak/ATR taken through the last
    real bar — exactly the prior-bar convention. Only call this when the
    position is still open on the real bars (grade_trailing(real) is None).
    None when the trail is not yet computable (no ATR, no seed).
    """
    clean = [
        b for b in bars
        if b.high is not None and b.low is not None and b.close is not None
    ]
    last = max((b.date for b in clean), default=entry_date)
    probe = BarLike(last + timedelta(days=1),
                    high=1e12, low=-1e12, close=1e12, open=1e12)
    ex = grade_trailing(list(clean) + [probe], entry, entry_date, atr_at_entry)
    if ex is not None and ex.status == "stopped" and ex.exit_date == probe.date:
        return round(ex.exit_price, 4)
    return None  # expired-at-probe is handled by the caller's exit pass


# --- DB wiring ----------------------------------------------------------------

# ATR seeds derive from frozen fire-time data (call_date bars), so a computed
# backfill never changes — memoized per process instead of recomputed on every
# executor poll (counter-agent perf finding). Keyed on the immutable identity
# fields; only non-None results are cached (bars may arrive later). Bounded.
_ATR_SEED_CACHE: dict[tuple, float] = {}


def _atr_seed(session: Session, c: TradeCall) -> float | None:
    """The call's frozen ATR seed: the stored snapshot, else the same
    backfill (and same config read) as evaluate_shadow_calls, memoized."""
    if c.atr_at_entry is not None:
        return c.atr_at_entry
    key = (c.id, c.symbol, c.call_date.isoformat(), c.entry_price)
    if key in _ATR_SEED_CACHE:
        return _ATR_SEED_CACHE[key]
    from ..config import calls_config

    risk_cfg = calls_config().get("risk", {})
    value = _backfill_atr_at_entry(
        session, c,
        risk_cfg.get("atr_window", _ATR_WINDOW),
        risk_cfg.get("stop_atr_mult", TRAIL_MULT),
    )
    if value is not None:
        if len(_ATR_SEED_CACHE) > 512:
            _ATR_SEED_CACHE.clear()
        _ATR_SEED_CACHE[key] = value
    return value

def _latest_xbi_date(session: Session) -> date | None:
    from ..scoring.outcomes import BENCH

    bar = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == BENCH)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.desc())
        .limit(1)
    ).first()
    return bar.date if bar else None


def _gate(session: Session) -> dict:
    """Current 200dma prior-close gate state + how long it has held.

    State comes from regime_state on the raw XBI closes (never stale even if
    the daily RegimeLog pass has not run yet); `since` comes from the logged
    RegimeLog run and is null when the log disagrees or is empty.
    """
    from ..scoring.outcomes import BENCH

    rows = session.exec(
        select(PriceBar)
        .where(PriceBar.symbol == BENCH)
        .where(PriceBar.close != None)  # noqa: E711
        .order_by(PriceBar.date.desc())
        .limit(201)
    ).all()
    rows.reverse()
    state = regime_state([r.close for r in rows])
    above = state.get("above_200dma")

    since = None
    logs = session.exec(
        select(RegimeLog).order_by(RegimeLog.date.desc()).limit(400)
    ).all()
    if logs and logs[0].above_200dma == above and above is not None:
        for log in logs:
            if log.above_200dma != above:
                break
            since = log.date
    return {"xbi_above_200dma_prior": above, "since": since}


def _open_shadow_calls(session: Session) -> tuple[list[TradeCall], dict[int, ShadowGrade]]:
    """Auto calls the tracker's shadow (R2-A) book tracks, split open/graded.

    Filtered to the R2-A trailing engine: rows a hypothetical second shadow
    engine might write must never mark a call closed for THIS book."""
    grades = {
        g.call_id: g
        for g in session.exec(
            select(ShadowGrade).where(ShadowGrade.engine == ENGINE_TRAILING)
        ).all()
    }
    calls = session.exec(
        select(TradeCall)
        .where(TradeCall.source == "auto_flag")
        .where(TradeCall.direction == "long")
    ).all()
    open_ = [c for c in calls if c.id not in grades]
    return open_, grades


@router.get("/intents")
def get_intents(session: Session = Depends(get_session)):
    """Today's blend3070 intent set (entries / exits / stops) for the executor.

    Read-only and offline-safe: pure DB, no network, mutates nothing (the
    shadow grader keeps its own schedule; ungraded calls are simply treated
    as open here).
    """
    as_of = _latest_xbi_date(session) or date.today()
    gate = _gate(session)
    open_calls, grades = _open_shadow_calls(session)

    # Entries: fresh auto-call fires from the last trading day, published
    # only while the gate is ON (an undefined gate never binds — R2-A law).
    entries: list[dict] = []
    if gate["xbi_above_200dma_prior"] is not False:
        for c in open_calls:
            if c.call_date != as_of:
                continue
            entries.append({
                "symbol": c.symbol,
                "call_id": c.id,
                "fire_date": c.call_date,
                "flag_type": c.flag_type,
                "risk_frac": BOOK_PARAMS["risk_frac"],
                # Sizing reference: the fire-day close the call's levels were
                # built from (the R2-A entry convention).
                "entry_ref": c.entry_price,
                "note": c.thesis,
            })

    # Stops + exits for every position the tracker's book tracks as open.
    exits: list[dict] = []
    stops: list[dict] = []
    for c in open_calls:
        atr_seed = _atr_seed(session, c)
        bars = _bars_for(session, c.symbol, c.call_date - timedelta(days=_ATR_WINDOW * 3))
        ex = grade_trailing(bars, c.entry_price, c.call_date, atr_seed)
        if ex is not None:
            exits.append({
                "symbol": c.symbol,
                "call_id": c.id,
                "reason": "trail" if ex.status == "stopped" else "time_stop",
                "trail_level": round(ex.exit_price, 4) if ex.status == "stopped" else None,
            })
            continue
        deadline = c.call_date + timedelta(days=TIME_STOP_DAYS)
        if date.today() > deadline:
            # Data gap straight past the time stop: still an exit signal.
            exits.append({"symbol": c.symbol, "call_id": c.id,
                          "reason": "time_stop", "trail_level": None})
            continue
        level = current_trail_level(bars, c.entry_price, c.call_date, atr_seed)
        # Guard: a bar-poor name whose 3xATR seed exceeds its price yields a
        # non-positive trail — never publishable (the venue would reject a
        # STP at <= 0; the executor guards its side too).
        if level is not None and level > 0:
            stops.append({"symbol": c.symbol, "call_id": c.id, "trail_level": level})

    # Echo recently shadow-graded exits so an executor polling after the
    # scheduler's shadow pass still sees them.
    echo_since = as_of - timedelta(days=_EXIT_ECHO_DAYS)
    listed = {e["call_id"] for e in exits}
    for call_id, g in grades.items():
        if g.exit_date >= echo_since and call_id not in listed:
            call = session.get(TradeCall, call_id)
            if call is None:
                # The TradeCall row is gone: a symbol-less exit is
                # unverifiable executor-side (its call_id/symbol cross-check
                # would refuse it anyway) — never publish it.
                continue
            exits.append({
                "symbol": call.symbol,
                "call_id": call_id,
                "reason": "trail" if g.status == "stopped" else "time_stop",
                "trail_level": g.exit_price if g.status == "stopped" else None,
            })

    return {
        "as_of": as_of,
        "gate": gate,
        "entries": entries,
        "exits": exits,
        "stops": stops,
        # Sleeve weights are executor-side state (the tracker never learns
        # account equity): needed stays null, the executor decides.
        "rebalance": {"needed": None, "current_sleeve_weight": None,
                      "target": 0.30},
        "book_params": dict(BOOK_PARAMS),
        "contract": CONTRACT,
    }
