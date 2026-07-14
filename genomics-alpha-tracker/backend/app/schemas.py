"""Pydantic request/response models for the REST API."""
from __future__ import annotations

from datetime import date as Date
from datetime import datetime as DateTime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Universe ---------------------------------------------------------------

class SecurityOut(BaseModel):
    symbol: str
    name: str
    subsector: list[str]
    active: bool
    updated_at: DateTime


class SecurityCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    name: Optional[str] = None  # auto-fetched from provider when omitted
    subsector: list[str] = Field(default_factory=list)
    active: bool = True
    backfill: bool = True       # kick an immediate backfill on insert


class SecurityUpdate(BaseModel):
    name: Optional[str] = None
    subsector: Optional[list[str]] = None
    active: Optional[bool] = None


# --- Catalysts --------------------------------------------------------------

class CatalystOut(BaseModel):
    id: int
    symbol: str
    date: Date
    event_type: str
    title: str
    impact_weight: float
    impact_override: Optional[float]
    effective_impact: float
    confirmed: bool
    status: str
    url: Optional[str]
    source: str


class CatalystCreate(BaseModel):
    symbol: str
    date: Date
    event_type: str = "other"
    title: str = ""
    impact_override: Optional[float] = None
    confirmed: bool = False
    url: Optional[str] = None
    source: str = "manual"


class CatalystUpdate(BaseModel):
    date: Optional[Date] = None
    event_type: Optional[str] = None
    title: Optional[str] = None
    impact_override: Optional[float] = None  # manual impact override
    confirmed: Optional[bool] = None
    status: Optional[str] = None


# --- Scores / flags ---------------------------------------------------------

class ScoreOut(BaseModel):
    symbol: str
    name: str
    subsector: list[str]
    asof: DateTime
    composite: Optional[float]
    components: dict[str, Any]
    missing: list[str]
    formula: dict[str, Any]


class FlagOut(BaseModel):
    id: int
    symbol: str
    asof: DateTime
    flag_type: str
    severity: str
    message: str
    evidence: dict[str, Any]


# --- Views ------------------------------------------------------------------

class HeatmapTile(BaseModel):
    subsector: str
    avg_composite: Optional[float]
    count: int
    symbols: list[str]


class MoverOut(BaseModel):
    symbol: str
    name: str
    mention_acceleration: Optional[float]
    composite: Optional[float]


# --- Trade calls (the tracker's own logged track record) ----------------------

class TradeCallOut(BaseModel):
    id: int
    symbol: str
    name: str = ""
    created_at: DateTime
    call_date: Date
    direction: str
    source: str
    flag_type: Optional[str]
    thesis: str
    entry_price: float
    stop_price: float
    target_price: float
    expires_on: Date
    composite_at_call: Optional[float]
    status: str
    exit_date: Optional[Date]
    exit_price: Optional[float]
    return_pct: Optional[float]
    r_multiple: Optional[float]
    # Live context for OPEN calls (from the latest bar; null once closed).
    last_price: Optional[float] = None
    unrealized_pct: Optional[float] = None
    unrealized_r: Optional[float] = None
    # WHY it went right/wrong (closed calls; hindsight fields fill ~10 bars
    # after exit).
    postmortem: Optional[dict] = None


class TradeCallCreate(BaseModel):
    """Log a manual call (an operator take, or an AI chat call transcribed)."""

    symbol: str = Field(..., min_length=1, max_length=12)
    direction: str = "long"                  # long | short
    entry_price: Optional[float] = None      # default: latest close
    stop_price: Optional[float] = None       # default: ATR-based, like auto calls
    target_price: Optional[float] = None
    horizon_days: int = Field(30, ge=1, le=365)
    thesis: str = ""
    source: str = "manual"                   # manual | chat


class TradeCallClose(BaseModel):
    exit_price: Optional[float] = None       # default: latest close
    note: Optional[str] = None


class CallBucketOut(BaseModel):
    calls: int
    open: int
    closed: int
    target_hit: int
    stopped: int
    expired: int
    win_rate: Optional[float]
    avg_return_pct: Optional[float]
    avg_r: Optional[float]
    total_r: Optional[float]


class CallsScorecardOut(BaseModel):
    overall: CallBucketOut
    by_signal: dict[str, CallBucketOut]
