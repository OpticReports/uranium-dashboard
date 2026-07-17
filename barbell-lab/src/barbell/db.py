"""SQLite store: canonical schema + tiny helpers.

Tables
------
prices(ticker, date, close_adj, close_raw, volume, source)
    One row per (ticker, date, source). ``source`` is the provider name
    ("yahoo", "fmp", ...). Proxy history lives under the PROXY's own ticker;
    splicing happens at read time in ``ingest.series`` and is never persisted,
    so raw data and derived series can't be confused.
fred(series_id, date, value)
bot_pnl(date, realized, unrealized)
trials(...)         -- append-only trial registry (see stats.trials)
regime_log(...)     -- daily regime dashboard snapshots
alerts(...)         -- monitor alert log (alerting mode "log")
validation_log(...) -- every ingest validation outcome, pass or fail
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import DATA_DIR

DB_PATH = Path(DATA_DIR) / "barbell.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,
    close_adj REAL NOT NULL,
    close_raw REAL,
    volume    REAL,
    source    TEXT NOT NULL,
    PRIMARY KEY (ticker, date, source)
);
CREATE TABLE IF NOT EXISTS fred (
    series_id TEXT NOT NULL,
    date      TEXT NOT NULL,
    value     REAL,
    PRIMARY KEY (series_id, date)
);
CREATE TABLE IF NOT EXISTS bot_pnl (
    date       TEXT PRIMARY KEY,
    realized   REAL NOT NULL,
    unrealized REAL
);
CREATE TABLE IF NOT EXISTS trials (
    trial_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc      TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    module      TEXT NOT NULL,
    description TEXT NOT NULL,
    sharpe      REAL,
    n_obs       INTEGER,
    metrics     TEXT
);
CREATE TABLE IF NOT EXISTS regime_log (
    date      TEXT PRIMARY KEY,
    labor_z   REAL, inflation_z REAL, credit_z REAL, dollar_z REAL,
    quadrant  TEXT,
    details   TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_versions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    label      TEXT NOT NULL,
    status     TEXT NOT NULL CHECK(status IN ('LIVE','CANDIDATE','RETIRED')),
    weights    TEXT NOT NULL,           -- json {ticker: weight}, tail resolved
    bot_frac   REAL NOT NULL DEFAULT 0.20,
    parent_id  INTEGER,
    rationale  TEXT,
    evidence   TEXT,                    -- json: evaluation battery vs parent/live
    created_at TEXT NOT NULL,
    adopted_at TEXT,
    retired_at TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_metrics (
    version_id  INTEGER NOT NULL,
    computed_at TEXT NOT NULL,
    metrics     TEXT NOT NULL,          -- json snapshot (realized + MC + constraints)
    PRIMARY KEY (version_id, computed_at)
);
CREATE TABLE IF NOT EXISTS validation_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc  TEXT NOT NULL,
    check_name TEXT NOT NULL,
    ticker  TEXT,
    passed  INTEGER NOT NULL,
    detail  TEXT
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.executescript(_SCHEMA)
    return con


def upsert_prices(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Upsert a canonical prices frame (columns exactly as schema)."""
    rows = df[["ticker", "date", "close_adj", "close_raw", "volume", "source"]].values.tolist()
    con.executemany(
        "INSERT INTO prices (ticker, date, close_adj, close_raw, volume, source) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(ticker, date, source) DO UPDATE SET "
        "close_adj=excluded.close_adj, close_raw=excluded.close_raw, volume=excluded.volume",
        rows,
    )
    con.commit()
    return len(rows)


def upsert_fred(con: sqlite3.Connection, series_id: str, s: pd.Series) -> int:
    rows = [(series_id, d.strftime("%Y-%m-%d"), None if pd.isna(v) else float(v))
            for d, v in s.items()]
    con.executemany(
        "INSERT INTO fred (series_id, date, value) VALUES (?,?,?) "
        "ON CONFLICT(series_id, date) DO UPDATE SET value=excluded.value",
        rows,
    )
    con.commit()
    return len(rows)


def read_prices(con: sqlite3.Connection, ticker: str, source: str | None = None) -> pd.DataFrame:
    q = "SELECT date, close_adj, close_raw, volume, source FROM prices WHERE ticker=?"
    args: list = [ticker]
    if source:
        q += " AND source=?"
        args.append(source)
    q += " ORDER BY date"
    df = pd.read_sql_query(q, con, params=args, parse_dates=["date"])
    return df.set_index("date")


def read_fred(con: sqlite3.Connection, series_id: str) -> pd.Series:
    df = pd.read_sql_query(
        "SELECT date, value FROM fred WHERE series_id=? ORDER BY date",
        con, params=[series_id], parse_dates=["date"],
    )
    return df.set_index("date")["value"].rename(series_id)
