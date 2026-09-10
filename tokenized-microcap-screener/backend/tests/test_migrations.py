"""Gate tests for additive schema migration.

This exists because of a real production failure on 2026-09-03. Render's disk
persists screener.db across deploys, and `SQLModel.metadata.create_all()`
creates missing TABLES but never alters an existing one — so every column added
after the first deploy was absent in the live database.

The failure mode was the dangerous kind: /health selects only `id`, so it kept
returning 200 with a healthy-looking registry count of 253 wrappers, while
every endpoint that selects a full model returned 500 with
`no such column: candidate.equity_price`. A green health check over a broken
service is worse than an obviously dead one.
"""
from __future__ import annotations

import sqlite3

import pytest
from sqlmodel import Session, create_engine, select

# The candidate table as the FIRST deploy created it: no equity_*, no
# pump_factors, no dilution or ladder-timestamp columns.
_OLD_SCHEMA = """CREATE TABLE candidate (
  id INTEGER PRIMARY KEY, ticker VARCHAR NOT NULL, company VARCHAR NOT NULL,
  stage VARCHAR NOT NULL, issuer_class VARCHAR NOT NULL, chains VARCHAR NOT NULL,
  meme_count INTEGER NOT NULL, top_meme_symbol VARCHAR NOT NULL,
  top_meme_url VARCHAR NOT NULL, onchain_liquidity_usd FLOAT NOT NULL,
  onchain_volume_h24 FLOAT NOT NULL, onchain_volume_h1 FLOAT NOT NULL,
  credibility FLOAT NOT NULL, heat FLOAT NOT NULL, pumpability FLOAT NOT NULL,
  earliness FLOAT NOT NULL, alert_score FLOAT NOT NULL, equity_dark BOOLEAN NOT NULL,
  equity_market_status VARCHAR NOT NULL, equity_exchange VARCHAR NOT NULL,
  reasons JSON, updated_at DATETIME NOT NULL)"""

_INSERT = """INSERT INTO candidate (id,ticker,company,stage,issuer_class,chains,
  meme_count,top_meme_symbol,top_meme_url,onchain_liquidity_usd,onchain_volume_h24,
  onchain_volume_h1,credibility,heat,pumpability,earliness,alert_score,equity_dark,
  equity_market_status,equity_exchange,reasons,updated_at)
  VALUES (1,'FAMI','Farmmi, Inc.','PAIRED','UNOFFICIAL','robinhood',3,'JINQIAN','',
          1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,0,'open','NASDAQ','[]','2026-09-03')"""


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """A database created by an older build, as production's disk holds."""
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute(_OLD_SCHEMA)
    con.execute(_INSERT)
    con.commit()
    con.close()

    from app import db as db_module
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


def test_legacy_database_is_migrated_in_place(legacy_db, monkeypatch):
    from app import db as db_module
    from app.models import Candidate

    # Before: selecting the full model is exactly the production 500.
    with Session(legacy_db) as s:
        with pytest.raises(Exception) as err:
            s.exec(select(Candidate)).all()
        assert "no such column" in str(err.value)

    db_module.migrate()

    with Session(legacy_db) as s:
        rows = s.exec(select(Candidate)).all()
    assert len(rows) == 1
    assert rows[0].ticker == "FAMI"
    # Pre-existing data must survive untouched.
    assert rows[0].company == "Farmmi, Inc."
    assert rows[0].heat == 5.0
    # New columns arrive with usable values, not nulls where NOT NULL applies.
    assert rows[0].dilution_flag == ""
    assert rows[0].equity_price is None


def test_migration_is_idempotent(legacy_db):
    from app import db as db_module
    from app.models import Candidate

    db_module.migrate()
    db_module.migrate()          # a second boot must be a no-op, not an error
    with Session(legacy_db) as s:
        assert len(s.exec(select(Candidate)).all()) == 1


def test_migration_only_adds_never_drops(legacy_db):
    """It must not be able to destroy data when a model and a database
    disagree in some way it does not understand."""
    from sqlalchemy import inspect

    from app import db as db_module

    before = {c["name"] for c in inspect(legacy_db).get_columns("candidate")}
    db_module.migrate()
    after = {c["name"] for c in inspect(legacy_db).get_columns("candidate")}
    assert before < after, "migration should only ever widen the table"


def test_health_style_query_would_not_have_caught_it(legacy_db):
    """The reason this shipped: /health selects only `id`, so it stayed green
    while the rest of the service was broken."""
    from app.models import Candidate

    with Session(legacy_db) as s:
        assert len(s.exec(select(Candidate.id)).all()) == 1


def test_health_reports_schema_drift(legacy_db):
    """After the outage: /health must SEE this, not sail past it."""
    from app import db as db_module

    drift = db_module.schema_drift()
    assert any("candidate.equity_price" in d for d in drift)
    # init_db() is what boot actually runs: create_all() for absent TABLES,
    # then migrate() for absent COLUMNS. migrate() alone never creates a table.
    db_module.init_db()
    assert db_module.schema_drift() == []


def test_drift_check_populates_metadata_itself(legacy_db, monkeypatch):
    """SQLModel.metadata is filled as a side effect of importing the models.
    Without that import schema_drift() returns [] for ANY database and reports
    a healthy schema — the same silent green it exists to prevent."""
    import sys

    from app import db as db_module

    monkeypatch.delitem(sys.modules, "app.models", raising=False)
    assert any("candidate.equity_price" in d for d in db_module.schema_drift())


def test_migrate_alone_does_not_create_tables(legacy_db):
    """Division of labour: create_all() makes absent tables, migrate() makes
    absent columns. Blurring them would let migrate() mask a broken deploy."""
    from app import db as db_module

    db_module.migrate()
    still_missing = [d for d in db_module.schema_drift() if "table absent" in d]
    assert still_missing, "migrate() must not be creating tables"
    db_module.init_db()
    assert db_module.schema_drift() == []
