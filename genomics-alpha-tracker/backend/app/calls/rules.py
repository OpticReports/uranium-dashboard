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

    - Stop and target are checked intrabar (low/high). When BOTH are touched
      in the same bar the order is unknowable from dailies, so the call is
      graded as STOPPED — the conservative reading.
    - A bar on/after `expires_on` closes the call at that bar's close
      (time-stop / sell-before-binary).
    Returns None while the call is still open.
    """
    for b in sorted(bars, key=lambda b: b.date):
        if b.low is None or b.high is None or b.close is None:
            continue
        if direction == "short":
            if b.high >= stop:
                return CallExit("stopped", b.date, stop)
            if b.low <= target:
                return CallExit("target_hit", b.date, target)
        else:
            if b.low <= stop:
                return CallExit("stopped", b.date, stop)
            if b.high >= target:
                return CallExit("target_hit", b.date, target)
        if b.date >= expires_on:
            return CallExit("expired", b.date, b.close)
    return None


def call_return(direction: str, entry: float, exit_price: float) -> float | None:
    """Direction-aware fractional return of a closed call."""
    if entry is None or entry <= 0 or exit_price is None:
        return None
    raw = (exit_price - entry) / entry
    return -raw if direction == "short" else raw


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
