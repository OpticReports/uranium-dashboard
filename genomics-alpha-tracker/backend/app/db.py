"""Database engine and session management.

SQLite by default with a clean upgrade path to Postgres: nothing in the app
uses SQLite-specific SQL, so switching DATABASE_URL to a postgres:// URL is the
only change required (plus `pip install psycopg2-binary`).
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    # Ensure the sqlite directory exists.
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


# Columns added to tables that may PRE-EXIST in a deployed DB. create_all
# creates missing tables but NEVER adds columns to existing ones — without
# this, adding a model field 500s every query on that table in production.
_LIGHT_MIGRATIONS: list[tuple[str, str, str]] = [
    ("trade_call", "confidence", "FLOAT"),
    ("security", "ctgov_names", "JSON"),
    # H11 shadow grader: fire-time ATR14 snapshot on calls (observe-only;
    # NULL on pre-feature rows until the shadow grader backfills it).
    ("trade_call", "atr_at_entry", "FLOAT"),
    # universe_candidate (discovery queue) is a NEW table: create_all makes it
    # whole on pre-existing DBs, so it needs no column entries here. Future
    # columns added to it after first deploy WILL need entries. Same for
    # shadow_grade and regime_log (H11/H8 shadow book).
]


def _light_migrate() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table, column, ddl_type in _LIGHT_MIGRATIONS:
        if table not in existing_tables:
            continue  # create_all will make it with the column included
        cols = {c["name"] for c in insp.get_columns(table)}
        if column not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def init_db() -> None:
    # Import models so SQLModel.metadata is populated before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _light_migrate()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
