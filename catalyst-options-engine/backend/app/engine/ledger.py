"""Paper book: open -> mark -> auto-close accounting.

Honesty rules (README bullets; test-pinned):
  * Entries pay the ASK, exits receive the BID whenever real quotes exist —
    the paper book eats the spread like a real fill would.
  * Daily marks: chain MID when the chain lane is live ("chain_mid"), else
    Black-Scholes at the ENTRY IV with the current spot ("bs_entry_iv") —
    mark_basis recorded on the position either way.
  * Auto-close at min(expiry, event_date + 3 trading days): the thesis is the
    event; after it resolves the position has no reason to exist.
  * Close pricing: chain BID per leg when live ("chain_bid"), else intrinsic
    at the current spot ("intrinsic").
  * Cash/equity are DERIVED from the position rows (start capital - premium
    paid + proceeds), never a mutable counter that can drift.

Pure helpers up top (unit-tested directly); thin SQLModel wrappers below.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from ..models import EquityPoint, PaperPosition
from .bs import bs_price
from .proposer import Proposal, _leg_kinds
from .signals import ChainRowView

logger = logging.getLogger(__name__)


# --- pure helpers -------------------------------------------------------------

def add_trading_days(d: date, n: int) -> date:
    """d + n trading days (weekends skipped; exchange holidays NOT modeled —
    a documented approximation)."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    cur = d
    while remaining > 0:
        cur += timedelta(days=step)
        if cur.weekday() < 5:
            remaining -= 1
    return cur


def auto_close_date(expiry: date, event_date: date | None,
                    hold_trading_days: int = 3) -> date:
    if event_date is None:
        return expiry
    return min(expiry, add_trading_days(event_date, hold_trading_days))


def _find_row(chain_rows: list[ChainRowView] | None, expiry: date,
              strike: float) -> ChainRowView | None:
    if not chain_rows:
        return None
    for r in chain_rows:
        if r.expiry == expiry and abs(r.strike - strike) < 1e-9:
            return r
    return None


def _legs(structure: str) -> list[str]:
    return _leg_kinds(structure)


def unit_mark(structure: str, strike: float, expiry: date, entry_iv: float | None,
              chain_row: ChainRowView | None, spot: float | None,
              asof: date) -> tuple[float, str] | None:
    """Per-share mark of the structure: chain mid, else BS at entry IV.
    Returns (unit_value, basis) or None when unmarkable (no chain, no spot)."""
    if chain_row is not None:
        total, ok = 0.0, True
        for kind in _legs(structure):
            bid = chain_row.c_bid if kind == "call" else chain_row.p_bid
            ask = chain_row.c_ask if kind == "call" else chain_row.p_ask
            if bid is None or ask is None or ask <= 0:
                ok = False
                break
            total += 0.5 * (bid + ask)
        if ok:
            return total, "chain_mid"
    if spot is not None and spot > 0 and entry_iv is not None:
        T = max((expiry - asof).days, 0) / 365.0
        total = sum(bs_price(spot, strike, T, entry_iv, kind=k)
                    for k in _legs(structure))
        return total, "bs_entry_iv"
    return None


def unit_close_value(structure: str, strike: float,
                     chain_row: ChainRowView | None,
                     spot: float | None) -> tuple[float, str] | None:
    """Per-share exit value: chain BID per leg when live, else intrinsic."""
    if chain_row is not None:
        total, ok = 0.0, True
        for kind in _legs(structure):
            bid = chain_row.c_bid if kind == "call" else chain_row.p_bid
            if bid is None or bid < 0:
                ok = False
                break
            total += bid
        if ok:
            return total, "chain_bid"
    if spot is not None and spot > 0:
        total = 0.0
        for kind in _legs(structure):
            total += max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
        return total, "intrinsic"
    return None


# --- book summary (pure over position rows) -----------------------------------

@dataclass
class BookSummary:
    starting_equity: float
    cash: float
    open_value: float
    equity: float
    realized_pnl: float
    open_positions: int
    closed_positions: int
    wins: int
    hit_rate: float | None  # None until at least one closed position


def summarize(positions: list[PaperPosition], starting_equity: float) -> BookSummary:
    cash = starting_equity
    open_value = realized = 0.0
    n_open = n_closed = wins = 0
    for p in positions:
        cash -= p.entry_cost
        if p.status == "closed":
            n_closed += 1
            cash += p.close_proceeds or 0.0
            pnl = p.realized_pnl or 0.0
            realized += pnl
            if pnl > 0:
                wins += 1
        else:
            n_open += 1
            open_value += p.mark_value if p.mark_value is not None else p.entry_cost
    return BookSummary(
        starting_equity=starting_equity, cash=round(cash, 2),
        open_value=round(open_value, 2), equity=round(cash + open_value, 2),
        realized_pnl=round(realized, 2), open_positions=n_open,
        closed_positions=n_closed, wins=wins,
        hit_rate=(wins / n_closed) if n_closed else None)


# --- DB-layer operations -------------------------------------------------------

def open_position(session: Session, prop: Proposal, asof: date) -> PaperPosition:
    pos = PaperPosition(
        symbol=prop.symbol, structure=prop.structure, strike=prop.strike,
        expiry=prop.expiry, event_date=prop.event_date, contracts=prop.contracts,
        entry_date=asof, entry_unit_premium=prop.unit_premium,
        entry_cost=prop.cost, pricing_basis=prop.pricing_basis,
        entry_iv=prop.entry_iv, spot_at_entry=prop.spot,
        direction_lean=prop.direction_lean, setup_score=prop.score,
        status="open", mark_value=prop.cost, mark_basis="entry",
        notes="; ".join(prop.flags) or None)
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return pos


def has_open_position(session: Session, symbol: str,
                      event_date: date | None) -> bool:
    q = select(PaperPosition).where(PaperPosition.symbol == symbol,
                                    PaperPosition.status == "open")
    for p in session.exec(q).all():
        if event_date is None or p.event_date == event_date:
            return True
    return False


def mark_position(session: Session, pos: PaperPosition,
                  chain_rows: list[ChainRowView] | None, spot: float | None,
                  asof: date) -> None:
    row = _find_row(chain_rows, pos.expiry, pos.strike)
    # entry_iv may be None on chain_ask entries; fall back to a mark at the
    # entry premium (flat) rather than inventing a vol.
    res = unit_mark(pos.structure, pos.strike, pos.expiry, pos.entry_iv,
                    row, spot, asof)
    if res is None:
        logger.warning("unmarkable position %s #%s (chain dark + no spot); "
                       "holding last mark", pos.symbol, pos.id)
        return
    unit, basis = res
    pos.mark_value = round(unit * 100.0 * pos.contracts, 2)
    pos.mark_basis = basis
    pos.marked_at = datetime.utcnow()
    session.add(pos)
    session.commit()


def close_position(session: Session, pos: PaperPosition,
                   chain_rows: list[ChainRowView] | None, spot: float | None,
                   asof: date, reason: str = "auto") -> PaperPosition | None:
    row = _find_row(chain_rows, pos.expiry, pos.strike)
    res = unit_close_value(pos.structure, pos.strike, row, spot)
    if res is None:
        logger.warning("cannot close %s #%s today (chain dark + no spot); "
                       "will retry next run", pos.symbol, pos.id)
        return None
    unit, basis = res
    proceeds = round(unit * 100.0 * pos.contracts, 2)
    pos.status = "closed"
    pos.close_date = asof
    pos.close_unit_value = round(unit, 4)
    pos.close_proceeds = proceeds
    pos.close_basis = basis
    pos.realized_pnl = round(proceeds - pos.entry_cost, 2)
    pos.mark_value = proceeds
    pos.mark_basis = basis
    pos.notes = ((pos.notes + "; ") if pos.notes else "") + f"closed: {reason}"
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return pos


def auto_close_due(session: Session, chain_lookup, price_lookup, asof: date,
                   hold_trading_days: int = 3) -> list[PaperPosition]:
    """Close every open position whose auto-close date has arrived.
    chain_lookup(symbol) -> list[ChainRowView] | None; price_lookup(symbol)
    -> float | None."""
    closed: list[PaperPosition] = []
    for pos in session.exec(select(PaperPosition)
                            .where(PaperPosition.status == "open")).all():
        due = auto_close_date(pos.expiry, pos.event_date, hold_trading_days)
        if asof >= due:
            out = close_position(session, pos, chain_lookup(pos.symbol),
                                 price_lookup(pos.symbol), asof,
                                 reason=f"auto (due {due.isoformat()})")
            if out is not None:
                closed.append(out)
    return closed


def snapshot_equity(session: Session, starting_equity: float,
                    asof: date) -> EquityPoint:
    positions = session.exec(select(PaperPosition)).all()
    s = summarize(list(positions), starting_equity)
    existing = session.exec(select(EquityPoint)
                            .where(EquityPoint.date == asof)).first()
    if existing:
        existing.equity, existing.cash = s.equity, s.cash
        existing.open_value, existing.open_positions = s.open_value, s.open_positions
        point = existing
    else:
        point = EquityPoint(date=asof, equity=s.equity, cash=s.cash,
                            open_value=s.open_value,
                            open_positions=s.open_positions)
    session.add(point)
    session.commit()
    return point
