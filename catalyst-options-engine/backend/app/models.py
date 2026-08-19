"""SQLModel tables.

Design note: signal math lives in pure functions (engine/*.py) — these tables
only persist what must survive restarts: the catalyst calendar, the latest
scored setups, and the paper book (positions + daily equity snapshots).
Prices and option chains are fetched fresh through the lanes (file-cached),
never persisted row-by-row.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime as DateTime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Catalyst(SQLModel, table=True):
    """A dated (or watch-only undated) upcoming event for a radar name.

    watch=True rows are undated 'interim watch' entries (phase-3, active-not-
    recruiting, PCD far out — an interim analysis could drop any time). They
    NEVER carry a fabricated date.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    date: Optional[Date] = Field(default=None, index=True)  # None only when watch=True
    event_type: str
    title: str
    impact_weight: float = 0.5
    watch: bool = False
    # Operator-set manual lean ("bullish"/"bearish") — the ONLY path to a
    # CALL_ONLY / directional proposal; never inferred automatically.
    direction_lean: Optional[str] = None
    confirmed: bool = False
    source: str = "clinicaltrials"  # clinicaltrials | manual
    url: Optional[str] = None
    created_at: DateTime = Field(default_factory=DateTime.utcnow)


class Setup(SQLModel, table=True):
    """Latest scored radar snapshot per symbol (rewritten each scan)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    asof: Date = Field(index=True)
    score: Optional[float] = None            # None when no dated event in horizon
    days_to_event: Optional[int] = None
    event_date: Optional[Date] = None
    event_type: Optional[str] = None
    event_title: Optional[str] = None
    impact_weight: Optional[float] = None
    watch: bool = False                      # undated interim-watch flag
    drift_z10: Optional[float] = None
    rv20: Optional[float] = None             # 20d realized vol, annualized
    atm_iv: Optional[float] = None           # from chain, annualized
    iv_ratio: Optional[float] = None
    spot: Optional[float] = None
    chain_dark: bool = False                 # option-chain lane unavailable
    prices_dark: bool = False                # price lane unavailable
    flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: DateTime = Field(default_factory=DateTime.utcnow)


class PaperPosition(SQLModel, table=True):
    """One paper options position. Long premium only — max loss = premium paid."""

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    structure: str = "ATM_STRADDLE"          # ATM_STRADDLE | CALL_ONLY
    strike: float
    expiry: Date
    event_date: Optional[Date] = None
    contracts: int = 1
    entry_date: Date
    # unit premium = per-share structure price; cost = unit * 100 * contracts
    entry_unit_premium: float
    entry_cost: float
    pricing_basis: str                       # chain_ask | bs_scenario
    entry_iv: Optional[float] = None         # IV used/implied at entry (annualized)
    spot_at_entry: Optional[float] = None
    direction_lean: Optional[str] = None
    setup_score: Optional[float] = None
    status: str = "open"                     # open | closed
    mark_value: Optional[float] = None       # latest total mark (USD)
    mark_basis: Optional[str] = None         # chain_mid | bs_entry_iv
    marked_at: Optional[DateTime] = None
    close_date: Optional[Date] = None
    close_unit_value: Optional[float] = None
    close_proceeds: Optional[float] = None
    close_basis: Optional[str] = None        # chain_bid | intrinsic
    realized_pnl: Optional[float] = None
    notes: Optional[str] = None
    created_at: DateTime = Field(default_factory=DateTime.utcnow)


class EquityPoint(SQLModel, table=True):
    """Daily paper-book equity snapshot (cash + marked open positions)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: Date = Field(index=True)
    equity: float
    cash: float
    open_value: float
    open_positions: int
    created_at: DateTime = Field(default_factory=DateTime.utcnow)
