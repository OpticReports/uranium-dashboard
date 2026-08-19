"""Per-name pre-catalyst signals. Pure, ORM-free, unit-testable.

Every function returns None to mean "no data" — never a silent 0.0 substitute
(genomics scoring/components.py convention).

Signals per radar name:
  * days_to_event — calendar days to the nearest DATED catalyst with
    impact_weight >= min_impact inside horizon_days. Undated phase-3
    interim-watch names carry watch=True and NO fabricated date.
  * drift_z10 — 10d return / (20d realized vol scaled to 10d): "has the stock
    already moved?" ~0 = quiet tape into the event = the asymmetric case.
  * iv_ratio — ATM implied vol (chain expiry just after the event) / 20d
    realized vol: "is the gamble already priced?" None when the chain lane is
    dark or the event is undated.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date

from .bs import implied_vol

TRADING_DAYS_PER_YEAR = 252


@dataclass
class EventView:
    """Minimal catalyst view the signal layer needs (ORM-free)."""

    date: date | None
    event_type: str
    impact_weight: float
    title: str = ""
    watch: bool = False
    direction_lean: str | None = None


@dataclass
class ChainRowView:
    """One strike row of an option chain (ORM-free)."""

    expiry: date
    strike: float
    c_bid: float | None = None
    c_ask: float | None = None
    c_last: float | None = None
    p_bid: float | None = None
    p_ask: float | None = None
    p_last: float | None = None


# --- catalyst timing ---------------------------------------------------------

def nearest_event(events: list[EventView], asof: date, horizon_days: int = 60,
                  min_impact: float = 0.85) -> EventView | None:
    """Nearest DATED catalyst with impact >= min_impact within the horizon."""
    dated = [e for e in events
             if e.date is not None and e.impact_weight >= min_impact
             and 0 <= (e.date - asof).days <= horizon_days]
    if not dated:
        return None
    return min(dated, key=lambda e: e.date)  # type: ignore[arg-type,return-value]


def days_to_event(events: list[EventView], asof: date, horizon_days: int = 60,
                  min_impact: float = 0.85) -> int | None:
    ev = nearest_event(events, asof, horizon_days, min_impact)
    return None if ev is None or ev.date is None else (ev.date - asof).days


def has_interim_watch(events: list[EventView]) -> bool:
    return any(e.watch for e in events)


def detect_interim_watch(overall_status: str, pcd: date | None, asof: date,
                         phases: list[str] | None,
                         min_months_out: int = 12) -> bool:
    """Undated phase-3 'interim watch': trial is ACTIVE_NOT_RECRUITING with a
    primary completion date more than `min_months_out` months out — an interim
    analysis could surprise at any time (the MRNA/V940 2026-08-19 pattern).
    Carries NO fabricated date."""
    if overall_status != "ACTIVE_NOT_RECRUITING":
        return False
    if not phases or "PHASE3" not in phases:
        return False
    if pcd is None:
        return False
    return (pcd - asof).days > min_months_out * 30.44


# --- price-drift -------------------------------------------------------------

def realized_vol_20d(adj_closes: list[float], annualize: bool = True) -> float | None:
    """Std-dev of the last 20 daily log returns (needs >= 21 closes, oldest
    first). Annualized with sqrt(252) unless annualize=False (daily)."""
    if adj_closes is None or len(adj_closes) < 21:
        return None
    tail = adj_closes[-21:]
    if any(c is None or c <= 0 for c in tail):
        return None
    rets = [math.log(tail[i + 1] / tail[i]) for i in range(20)]
    sd = statistics.stdev(rets)
    if sd == 0:
        return None
    return sd * math.sqrt(TRADING_DAYS_PER_YEAR) if annualize else sd


def drift_z10(adj_closes: list[float]) -> float | None:
    """10d return / (20d realized daily vol scaled to 10d).

    adj_closes oldest-first. Needs >= 21 closes (10d return needs 11, the
    20d vol needs 21). None on insufficient/degenerate data."""
    if adj_closes is None or len(adj_closes) < 21:
        return None
    daily_vol = realized_vol_20d(adj_closes, annualize=False)
    if daily_vol is None:
        return None
    c_now, c_then = adj_closes[-1], adj_closes[-11]
    if c_then is None or c_then <= 0 or c_now is None:
        return None
    ret10 = c_now / c_then - 1.0
    vol10 = daily_vol * math.sqrt(10)
    if vol10 == 0:
        return None
    return ret10 / vol10


# --- implied-vol richness ----------------------------------------------------

def _mid(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid < 0 or ask <= 0 or ask < bid:
        return None
    return 0.5 * (bid + ask)


def expiry_after(rows: list[ChainRowView], event_date: date) -> date | None:
    """The chain expiry just AFTER (>=) the event date — the contract that
    still holds the event's gamma."""
    cands = sorted({r.expiry for r in rows if r.expiry >= event_date})
    return cands[0] if cands else None


def atm_row(rows: list[ChainRowView], spot: float) -> ChainRowView | None:
    if not rows or spot is None or spot <= 0:
        return None
    return min(rows, key=lambda r: abs(r.strike - spot))


def atm_iv(rows: list[ChainRowView], spot: float | None, event_date: date | None,
           asof: date) -> float | None:
    """ATM implied vol at the expiry just after the event: mid of bid/ask per
    leg, IV solved per leg, call+put IVs averaged. None whenever any required
    piece is missing — never fabricated."""
    if not rows or spot is None or spot <= 0 or event_date is None:
        return None
    exp = expiry_after(rows, event_date)
    if exp is None:
        return None
    at_exp = [r for r in rows if r.expiry == exp]
    row = atm_row(at_exp, spot)
    if row is None:
        return None
    T = (exp - asof).days / 365.0
    if T <= 0:
        return None
    ivs: list[float] = []
    call_mid = _mid(row.c_bid, row.c_ask)
    if call_mid is not None:
        iv = implied_vol(call_mid, spot, row.strike, T, kind="call")
        if iv is not None:
            ivs.append(iv)
    put_mid = _mid(row.p_bid, row.p_ask)
    if put_mid is not None:
        iv = implied_vol(put_mid, spot, row.strike, T, kind="put")
        if iv is not None:
            ivs.append(iv)
    return sum(ivs) / len(ivs) if ivs else None


def iv_ratio(atm_iv_annual: float | None, rv20_annual: float | None) -> float | None:
    """ATM IV / 20d realized vol (both annualized). >1 = event premium already
    priced; ~1 = cheap gamble. None when either side is unknown."""
    if atm_iv_annual is None or rv20_annual is None or rv20_annual <= 0:
        return None
    return atm_iv_annual / rv20_annual
