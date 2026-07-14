"""Pure functions for trade-call level construction and grading.

Deliberately ORM-free and side-effect-free (same philosophy as
scoring/components.py) so the call math is unit-testable with known
inputs/outputs. None always means "no data", never a silent zero.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass
class BarLike:
    date: date
    high: float | None
    low: float | None
    close: float | None
    open: float | None = None  # enables gap-aware exit fills when present


@dataclass
class CallLevels:
    entry: float
    stop: float
    target: float


@dataclass
class CallExit:
    status: str        # target_hit | stopped | expired
    exit_date: date
    exit_price: float


def atr(bars: Sequence[BarLike], window: int) -> float | None:
    """Average True Range over the trailing `window` bars (simple mean).

    Needs window+1 bars (the extra one supplies the previous close). Returns
    None when there is not enough clean data — callers fall back to a
    percentage stop rather than guessing.
    """
    clean = [b for b in bars if b.high is not None and b.low is not None and b.close is not None]
    if len(clean) < window + 1:
        return None
    clean = clean[-(window + 1):]
    trs: list[float] = []
    for prev, cur in zip(clean, clean[1:]):
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(tr)
    if not trs:
        return None
    return sum(trs) / len(trs)


def build_levels(
    entry: float,
    direction: str,
    atr_value: float | None,
    stop_atr_mult: float,
    fallback_stop_pct: float,
    reward_risk: float,
) -> CallLevels | None:
    """Exact entry/stop/target from a volatility-scaled risk unit.

    stop = entry -/+ stop_atr_mult * ATR (falls back to a % stop when ATR is
    unavailable); target = entry +/- reward_risk * risk. Returns None for a
    non-positive entry (bad data) — no call is better than a wrong call.
    """
    if entry is None or entry <= 0:
        return None
    risk = (stop_atr_mult * atr_value) if atr_value else (fallback_stop_pct * entry)
    if risk <= 0:
        return None
    # Cap the risk unit so a volatility blowout can't put the stop below zero.
    risk = min(risk, 0.5 * entry)
    if direction == "short":
        return CallLevels(entry=entry, stop=entry + risk, target=entry - reward_risk * risk)
    return CallLevels(entry=entry, stop=entry - risk, target=entry + reward_risk * risk)


def grade_call(
    direction: str,
    entry: float,
    stop: float,
    target: float,
    expires_on: date,
    bars: Sequence[BarLike],
) -> CallExit | None:
    """Walk daily bars chronologically and decide the call's exit, if any.

    - THE OPEN RESOLVES FIRST: the open is the one intrabar event whose order
      is KNOWN. A bar that opens beyond the target exits at the open as a win
      even if it later fades through the stop — grading biotech's classic
      gap-up-then-fade readout day as a stop-loss would systematically convert
      the strategy's best days into -1R.
    - Then stop and target are checked intrabar (low/high). When BOTH are
      touched and the open resolved neither, the order is unknowable from
      dailies, so the call grades STOPPED — the conservative reading.
    - GAP-AWARE FILLS: a stop gapped through fills at the open, not the level.
    - The time-stop exits at the close of the LAST bar at-or-before
      `expires_on` — never on a bar after it. A binary on a Monday (expiry
      Sunday) must exit at Friday's close, not ride through the event to
      Monday's post-readout print.
    Returns None while the call is still open.
    """
    prev: BarLike | None = None
    for b in sorted(bars, key=lambda b: b.date):
        if b.low is None or b.high is None or b.close is None:
            continue
        if b.date > expires_on:
            # Time-stop passed on a non-trading day: exit at the last bar
            # before it (prev is None only on a data gap straight past expiry).
            if prev is not None:
                return CallExit("expired", prev.date, prev.close)
            return CallExit("expired", b.date, b.open if b.open is not None else b.close)
        if direction == "short":
            if b.open is not None and b.open >= stop:
                return CallExit("stopped", b.date, b.open)
            if b.open is not None and b.open <= target:
                return CallExit("target_hit", b.date, b.open)
            if b.high >= stop:
                return CallExit("stopped", b.date, stop)
            if b.low <= target:
                return CallExit("target_hit", b.date, target)
        else:
            if b.open is not None and b.open <= stop:
                return CallExit("stopped", b.date, b.open)
            if b.open is not None and b.open >= target:
                return CallExit("target_hit", b.date, b.open)
            if b.low <= stop:
                return CallExit("stopped", b.date, stop)
            if b.high >= target:
                return CallExit("target_hit", b.date, target)
        if b.date == expires_on:
            return CallExit("expired", b.date, b.close)
        prev = b
    return None


def call_return(direction: str, entry: float, exit_price: float) -> float | None:
    """Direction-aware fractional return of a closed call."""
    if entry is None or entry <= 0 or exit_price is None:
        return None
    raw = (exit_price - entry) / entry
    return -raw if direction == "short" else raw


def addv(bars: Sequence[BarLike], volumes: Sequence[float | None], window: int) -> float | None:
    """MEDIAN daily dollar volume (close x volume) over the trailing window.

    Median, not mean: a single volume-blowout day would otherwise promote a
    thin name a full liquidity tier for a month. `bars` and `volumes` are
    parallel sequences. None when no clean observations exist in the window.
    """
    dollars = sorted(
        b.close * v
        for b, v in zip(bars[-window:], volumes[-window:])
        if b.close is not None and v is not None
    )
    if not dollars:
        return None
    mid = len(dollars) // 2
    if len(dollars) % 2:
        return dollars[mid]
    return (dollars[mid - 1] + dollars[mid]) / 2


def liquidity_tier(
    addv_value: float | None,
    tier_a_min: float,
    tier_b_min: float,
) -> str | None:
    """A (deep) / B (size with care) / C (thin — slippage at any size)."""
    if addv_value is None:
        return None
    if addv_value >= tier_a_min:
        return "A"
    if addv_value >= tier_b_min:
        return "B"
    return "C"


def call_r_multiple(
    direction: str, entry: float, stop: float, exit_price: float
) -> float | None:
    """Result expressed in R (multiples of the risk taken at entry)."""
    if exit_price is None:
        return None
    risk = (stop - entry) if direction == "short" else (entry - stop)
    if risk <= 0:
        return None
    pnl = (entry - exit_price) if direction == "short" else (exit_price - entry)
    return pnl / risk
