"""SQLModel ORM tables.

Design notes:
- `Security` is the universe. Deactivating sets active=False but never deletes
  rows, so all historical data is retained.
- Numeric signal fields are Optional everywhere. A NULL means "no data" and is
  treated differently from 0.0 throughout the scoring engine — a zero in a
  signal component is a real value, not an absence of one.
"""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime as DateTime
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> DateTime:
    return DateTime.utcnow()


class Security(SQLModel, table=True):
    """A name in the coverage universe."""

    __tablename__ = "security"

    symbol: str = Field(primary_key=True)
    name: str = ""
    subsector: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    active: bool = True
    created_at: DateTime = Field(default_factory=_utcnow)
    updated_at: DateTime = Field(default_factory=_utcnow)


class PriceBar(SQLModel, table=True):
    __tablename__ = "price_bar"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_price_symbol_date"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    date: Date = Field(index=True)
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adj_close: Optional[float] = None
    volume: Optional[float] = None
    source: str = "yfinance"


class Fundamental(SQLModel, table=True):
    """Point-in-time fundamentals + positioning. Optional fields => may be NULL."""

    __tablename__ = "fundamental"
    __table_args__ = (UniqueConstraint("symbol", "asof", name="uq_fund_symbol_asof"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    asof: Date = Field(index=True)
    market_cap: Optional[float] = None
    cash: Optional[float] = None
    quarterly_burn: Optional[float] = None      # positive = cash outflow / quarter
    rd_spend: Optional[float] = None            # trailing R&D
    runway_quarters: Optional[float] = None     # cash / quarterly_burn
    short_interest_pct: Optional[float] = None  # short interest as % of float
    short_interest_percentile: Optional[float] = None  # 0-1 within universe
    iv: Optional[float] = None                  # at-the-money implied vol
    iv_skew: Optional[float] = None             # put-call skew
    source: str = "yfinance"


class AnalystRevision(SQLModel, table=True):
    __tablename__ = "analyst_revision"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    date: Date = Field(index=True)
    firm: Optional[str] = None
    metric: str = "eps"          # eps | revenue | price_target | rating
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    direction: int = 0           # +1 up, -1 down, 0 reiterate
    note: Optional[str] = None
    source: str = "fmp"


class Catalyst(SQLModel, table=True):
    """An upcoming (or recent) catalyst on the pipeline calendar."""

    __tablename__ = "catalyst"
    __table_args__ = (
        UniqueConstraint("symbol", "event_type", "date", "title", name="uq_catalyst"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    date: Date = Field(index=True)                 # estimated event date
    event_type: str = "other"                     # pdufa, adcom, phase3_readout, ...
    title: str = ""
    impact_weight: float = 0.2                    # auto-assigned (0-1)
    impact_override: Optional[float] = None       # manual override wins
    confirmed: bool = False                       # estimated vs confirmed date
    status: str = "upcoming"
    url: Optional[str] = None
    source: str = "clinicaltrials"
    created_at: DateTime = Field(default_factory=_utcnow)

    @property
    def effective_impact(self) -> float:
        return self.impact_override if self.impact_override is not None else self.impact_weight


class SciencePub(SQLModel, table=True):
    __tablename__ = "science_pub"
    __table_args__ = (UniqueConstraint("symbol", "kind", "ext_id", name="uq_science"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    date: Date = Field(index=True)
    kind: str = "pubmed"          # pubmed | biorxiv | medrxiv | patent
    ext_id: str = ""
    title: str = ""
    url: Optional[str] = None
    source: str = "pubmed"


class SocialMention(SQLModel, table=True):
    """Daily aggregated social mentions per platform."""

    __tablename__ = "social_mention"
    __table_args__ = (
        UniqueConstraint("symbol", "platform", "date", name="uq_social"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    date: Date = Field(index=True)
    platform: str = "stocktwits"      # x | reddit | stocktwits
    volume: int = 0                   # mention count
    sentiment: Optional[float] = None  # -1..+1 mean sentiment
    source: str = "stocktwits"


class ScoreSnapshot(SQLModel, table=True):
    """An auditable Alpha Signal computation for one name at one time."""

    __tablename__ = "score_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    asof: DateTime = Field(default_factory=_utcnow, index=True)
    composite: Optional[float] = None
    components: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    missing: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    formula: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class FlagEvent(SQLModel, table=True):
    """A named, evidence-linked flag emitted by the scoring engine."""

    __tablename__ = "flag_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    asof: DateTime = Field(default_factory=_utcnow, index=True)
    flag_type: str = ""
    message: str = ""
    severity: str = "info"        # info | warn | high
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class TradeCall(SQLModel, table=True):
    """An exact trade call (entry/stop/target/horizon) logged at fire-time.

    Calls are IMMUTABLE once made (levels never retro-edited) and are graded
    against subsequent daily bars, so the tracker builds an honest track record
    of its own signals — the feedback loop for improving what fires.
    """

    __tablename__ = "trade_call"

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, foreign_key="security.symbol")
    created_at: DateTime = Field(default_factory=_utcnow, index=True)
    call_date: Date = Field(index=True)            # trading date the call is made
    direction: str = "long"                        # long | short
    source: str = "auto_flag"                      # auto_flag | manual | chat
    flag_type: Optional[str] = None                # trigger flag for auto calls
    thesis: str = ""                               # why the call was made

    # The exact call — levels are frozen at fire-time.
    entry_price: float
    stop_price: float
    target_price: float
    expires_on: Date                               # time-stop (sell-before-binary aware)

    # Context snapshotted at fire-time for later attribution.
    composite_at_call: Optional[float] = None
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Outcome (filled by the evaluator; NULL while the call is open).
    status: str = Field(default="open", index=True)  # open | target_hit | stopped | expired | closed_manual
    closed_at: Optional[DateTime] = None
    exit_date: Optional[Date] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None             # fractional, direction-aware
    r_multiple: Optional[float] = None             # (exit-entry)/(entry-stop) for longs
