"""Database engine + session management (SQLite; Postgres upgrade path)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

logger = logging.getLogger(__name__)

_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    from . import models  # noqa: F401  (populate SQLModel.metadata)

    SQLModel.metadata.create_all(engine)
    migrate()


def migrate() -> None:
    """Add columns that exist in the models but not yet in the database.

    `create_all()` creates MISSING TABLES and never alters an existing one, and
    the Render disk deliberately persists screener.db across deploys — so every
    column added after the first deploy was simply absent in production. The
    failure was quiet in the worst way: /health selects only `id` and kept
    returning 200 with a healthy-looking registry count, while every endpoint
    that selects a full model 500'd on `no such column: candidate.equity_price`.

    Deliberately minimal and additive: it only ever ADDs columns. It does not
    drop, rename or retype anything, so it cannot destroy data if a model and a
    database disagree in some other way — that case needs a human.
    """
    from . import models  # noqa: F401  (populate SQLModel.metadata)

    inspector = inspect(engine)
    added: list[str] = []
    for table in SQLModel.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" ' \
                  f'{col.type.compile(engine.dialect)}'
            # SQLite refuses a NOT NULL column without a default on an existing
            # table, so a non-nullable addition has to carry one.
            literal = _default_literal(col)
            if not col.nullable and literal is not None:
                ddl += f" NOT NULL DEFAULT {literal}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
            except Exception as exc:  # noqa: BLE001
                logger.error("migration FAILED for %s.%s: %s",
                             table.name, col.name, exc)
    if added:
        logger.warning("migrated %d new column(s): %s", len(added), ", ".join(added))


def _default_literal(col) -> str | None:
    """A SQL literal for the column's Python-side default, or None when there
    isn't a usable one (callable defaults like default_factory=list)."""
    default = getattr(col, "default", None)
    value = None
    if default is not None and not getattr(default, "is_callable", False):
        value = getattr(default, "arg", None)
    if value is None:
        # Fall back by type so a NOT NULL column can still be added.
        name = col.type.__class__.__name__.upper()
        if "CHAR" in name or "TEXT" in name or "STRING" in name:
            value = ""
        elif "INT" in name:
            value = 0
        elif "FLOAT" in name or "NUMERIC" in name or "REAL" in name:
            value = 0.0
        elif "BOOL" in name:
            value = False
        else:
            return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def schema_drift() -> list[str]:
    """Columns the models declare that the database does not have.

    /health selected only `id` and stayed green through a production outage
    where every full-model query 500'd. A health check that cannot see the
    most likely way this service breaks is not a health check.

    The models import is NOT redundant: SQLModel.metadata is populated as a
    side effect of importing them, and without it this returns an empty list
    and reports a healthy schema for any database at all — the same silent
    green it exists to prevent.
    """
    from . import models  # noqa: F401  (populate SQLModel.metadata)

    inspector = inspect(engine)
    missing: list[str] = []
    for table in SQLModel.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            missing.append(f"{table.name} (table absent)")
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{c.name}" for c in table.columns
                       if c.name not in existing)
    return missing
