"""SQLite persistence — bars, trades, book state, equity snapshots, events.

Book state (equity/halted/open position/pending order) is persisted as one
JSON row per book so restart-resume rebuilds exactly; closed trades are
first-class rows (spec §3). New columns on shipped tables require an entry in
_LIGHT_MIGRATIONS (create_all never ALTERs — lesson from the genomics app).
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Float, Integer, String, Text, create_engine, text,
)
from sqlalchemy.orm import Session, declarative_base

from ..config import settings

Base = declarative_base()


class BarRow(Base):
    __tablename__ = "bars_4h"
    ts_open = Column(Integer, primary_key=True)      # unix UTC
    open = Column(Float); high = Column(Float); low = Column(Float)
    close = Column(Float); volume = Column(Float)


class TradeRow(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    book = Column(String, index=True)
    side = Column(String)
    signal_ts = Column(Integer)
    entry_ts = Column(Integer, index=True)
    entry_price = Column(Float)
    qty = Column(Float); notional = Column(Float)
    stop_price = Column(Float); atr_at_entry = Column(Float)
    exit_ts = Column(Integer); exit_price = Column(Float)
    exit_reason = Column(String)
    bars_held = Column(Integer)
    fees_usd = Column(Float); pnl_usd = Column(Float); pnl_pct = Column(Float)
    equity_before = Column(Float); equity_after = Column(Float)


class SignalRow(Base):
    __tablename__ = "signals"
    ts_bar = Column(Integer, primary_key=True)
    direction = Column(String)
    close = Column(Float); rsi = Column(Float)
    depth_atr = Column(Float); vol_ratio = Column(Float)


class BookStateRow(Base):
    __tablename__ = "book_state"
    book = Column(String, primary_key=True)
    state_json = Column(Text)                        # equity/peak/halted/position/pending
    last_processed_bar = Column(Integer)


class EquitySnapRow(Base):
    __tablename__ = "equity_snapshots"
    ts = Column(Integer, primary_key=True)
    book = Column(String, primary_key=True)
    equity = Column(Float); unrealized = Column(Float)
    peak_equity = Column(Float); drawdown = Column(Float)


class EventRow(Base):
    __tablename__ = "engine_events"
    id = Column(Integer, primary_key=True)
    ts = Column(Integer, index=True)
    level = Column(String); book = Column(String)
    event = Column(String); detail = Column(Text)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = settings.database_url
        if url.startswith("sqlite:///"):
            os.makedirs(os.path.dirname(url.replace("sqlite:///", "")) or ".", exist_ok=True)
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    return _engine


_LIGHT_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, sqltype) — appended when shipped tables grow columns
]


def init_db() -> None:
    eng = get_engine()
    Base.metadata.create_all(eng)
    with eng.connect() as c:
        for table, col, sqltype in _LIGHT_MIGRATIONS:
            cols = [r[1] for r in c.execute(text(f"PRAGMA table_info({table})"))]
            if col not in cols:
                c.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sqltype}"))
        c.commit()


@contextmanager
def session_scope():
    s = Session(get_engine())
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def log_event(s: Session, level: str, event: str, detail: str = "", book: str = "") -> None:
    s.add(EventRow(ts=int(datetime.now(timezone.utc).timestamp()),
                   level=level, book=book, event=event, detail=detail))


def dump_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))
