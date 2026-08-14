"""Import the short-vol bot's actual P&L from its own SQLite.

The bot project owns its schema; config/data.yaml maps its table/columns to
the canonical ``bot_pnl(date, realized, unrealized)``. Anything missing or
malformed raises — the combined-book simulator must never quietly run on a
parameterized model when real history was requested (model fallback is an
explicit CLI flag, see portfolio/combined.py).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from ..config import load
from ..ingest.base import ProviderError


def import_bot_pnl(con: sqlite3.Connection, bot_db_path: str | None = None) -> int:
    cfg = load("data")["bot"]
    path = Path(bot_db_path or cfg["sqlite_path"]).expanduser()
    if not path.exists():
        raise ProviderError(
            f"bot SQLite not found at {path} — set bot.sqlite_path in config/data.yaml "
            "or pass --bot-db. Refusing to fabricate bot P&L."
        )
    cols = cfg["columns"]
    q = (f"SELECT {cols['date']} AS date, {cols['realized']} AS realized, "
         f"{cols['unrealized']} AS unrealized FROM {cfg['table']}")
    with sqlite3.connect(path) as src:
        df = pd.read_sql_query(q, src)
    if df.empty:
        raise ProviderError(f"bot table {cfg['table']} is empty in {path}")
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.groupby("date", as_index=False).sum(numeric_only=True)
    con.executemany(
        "INSERT INTO bot_pnl (date, realized, unrealized) VALUES (?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET realized=excluded.realized, "
        "unrealized=excluded.unrealized",
        df[["date", "realized", "unrealized"]].values.tolist(),
    )
    con.commit()
    return len(df)


def read_bot_pnl(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT date, realized, unrealized FROM bot_pnl ORDER BY date",
                           con, parse_dates=["date"])
    return df.set_index("date")
