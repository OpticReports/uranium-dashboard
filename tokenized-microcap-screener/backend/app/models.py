"""SQLModel tables.

Design note: all scoring math lives in pure functions under engine/ — these
tables persist only what must survive a restart:

  * EquityToken — the on-chain tokenized-equity registry (the thing a meme
    gets paired AGAINST), with the timestamp we first saw it. Its
    `first_seen_at` is the EARLIEST rung of the ladder and therefore the
    single most valuable column in this service.
  * MemeLaunch  — one meme token paired against an EquityToken.
  * Candidate   — the per-ticker rollup the dashboard ranks and alerts on.
  * StageEvent  — append-only ladder transitions. This is the lead-lag
    recorder: it exists so the lead time can eventually be MEASURED across
    events instead of assumed. See README "Honesty box".
"""
from __future__ import annotations

from datetime import datetime as DateTime
from typing import Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

# Ladder rungs, earliest first. Held here (not in an Enum) so a stored row from
# an older build never fails to load.
STAGES = [
    "TOKENIZED",      # a tokenized equity token for this ticker exists on-chain
    "PAIRED",         # >=1 meme token has been paired against it
    "RAMPING",        # onchain volume/txn acceleration on a paired meme
    "CLUSTER",        # >=N distinct memes against the same ticker (cascade)
    "EQUITY_MOVING",  # the listed stock has broken out on volume — too late
    "FADED",          # onchain heat has decayed and the equity is not moving
]


class EquityToken(SQLModel, table=True):
    """A token on a DEX that represents a listed equity."""

    __table_args__ = (UniqueConstraint("chain_id", "address", name="uq_equity_token"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    address: str = Field(index=True)
    symbol: str
    token_name: str
    ticker: str = Field(index=True)          # resolved US listing
    company: str                              # SEC-registered company title
    # OFFICIAL_RH  — "<Company> • Robinhood Token": a real mint/redeem wrapper,
    #                so on-chain demand can transmit to the tape.
    # UNOFFICIAL   — name matches the SEC company title but carries no issuer
    #                marker: no redemption path, so the loop is pure attention.
    issuer_class: str = Field(index=True)
    first_seen_at: DateTime = Field(default_factory=DateTime.utcnow, index=True)
    # Earliest pairCreatedAt observed for this token — proxies deployment time.
    first_pair_at: Optional[DateTime] = Field(default=None, index=True)


class MemeLaunch(SQLModel, table=True):
    """A non-equity token paired against an EquityToken."""

    __table_args__ = (UniqueConstraint("chain_id", "pair_address", name="uq_meme_pair"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)
    pair_address: str = Field(index=True)
    dex_id: str = ""
    base_address: str = ""
    base_symbol: str = ""
    base_name: str = ""
    ticker: str = Field(index=True)           # the equity side's listing
    equity_token_address: str = ""
    pair_created_at: Optional[DateTime] = Field(default=None, index=True)
    first_seen_at: DateTime = Field(default_factory=DateTime.utcnow, index=True)
    last_seen_at: DateTime = Field(default_factory=DateTime.utcnow)

    liquidity_usd: float = 0.0
    volume_h24: float = 0.0
    volume_h1: float = 0.0
    volume_m5: float = 0.0
    fdv: float = 0.0
    price_change_h1: float = 0.0
    price_change_h24: float = 0.0
    buys_h1: int = 0
    sells_h1: int = 0
    credibility: float = 0.0
    heat: float = 0.0
    url: str = ""


class Candidate(SQLModel, table=True):
    """Per-ticker rollup: what the dashboard ranks and what alerts fire on."""

    __table_args__ = (UniqueConstraint("ticker", name="uq_candidate_ticker"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    company: str = ""
    stage: str = Field(default="TOKENIZED", index=True)
    issuer_class: str = ""
    chains: str = ""

    meme_count: int = 0
    top_meme_symbol: str = ""
    top_meme_url: str = ""
    onchain_liquidity_usd: float = 0.0
    onchain_volume_h24: float = 0.0
    onchain_volume_h1: float = 0.0

    credibility: float = 0.0      # is the setup real (liquid, two-sided)?
    heat: float = 0.0             # is attention accelerating right now?
    pumpability: float = 0.0      # would the listing actually move if bid?
    earliness: float = 0.0        # how much of the move is still ahead?
    alert_score: float = 0.0      # the ranked composite

    # Equity side (keyless lane; None when dark).
    equity_price: Optional[float] = None
    equity_prev_close: Optional[float] = None
    equity_change_pct: Optional[float] = None
    equity_volume: Optional[float] = None
    equity_avg_volume: Optional[float] = None
    equity_rvol: Optional[float] = None
    equity_market_status: str = ""
    equity_exchange: str = ""
    equity_dark: bool = False

    first_tokenized_at: Optional[DateTime] = Field(default=None)
    first_paired_at: Optional[DateTime] = Field(default=None)
    first_ramping_at: Optional[DateTime] = Field(default=None)
    first_cluster_at: Optional[DateTime] = Field(default=None)
    first_equity_move_at: Optional[DateTime] = Field(default=None)
    alerted_at: Optional[DateTime] = Field(default=None)

    reasons: list = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: DateTime = Field(default_factory=DateTime.utcnow, index=True)


class StageEvent(SQLModel, table=True):
    """Append-only ladder transition. The lead-lag measurement substrate."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    stage: str = Field(index=True)
    at: DateTime = Field(default_factory=DateTime.utcnow, index=True)
    # Hours since this ticker's first TOKENIZED rung, when known.
    hours_since_tokenized: Optional[float] = None
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))


class ScanState(SQLModel, table=True):
    """Tiny KV for scan bookkeeping (the rolling universe-sweep cursor)."""

    key: str = Field(primary_key=True)
    value: str = ""
    updated_at: DateTime = Field(default_factory=DateTime.utcnow)
