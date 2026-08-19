"""Light-migration tests: reproduce the production failure where a model
gained a column but the deployed table pre-existed without it (create_all
never ALTERs), then prove init_db heals it."""
from __future__ import annotations

import importlib

from sqlalchemy import text


def _fresh_db_module(tmp_path, monkeypatch):
    """Reload app.db against an isolated on-disk sqlite file."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/mig.db")
    import app.config as config
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "settings", config.get_settings(), raising=True)
    import app.db as db
    importlib.reload(db)
    return db


def test_init_db_adds_missing_column_to_preexisting_table(tmp_path, monkeypatch):
    db = _fresh_db_module(tmp_path, monkeypatch)

    # Simulate the OLD production schema: trade_call exists WITHOUT confidence.
    with db.engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE trade_call ("
            "id INTEGER PRIMARY KEY, symbol VARCHAR, created_at DATETIME,"
            "call_date DATE, direction VARCHAR, source VARCHAR, flag_type VARCHAR,"
            "thesis VARCHAR, entry_price FLOAT, stop_price FLOAT, target_price FLOAT,"
            "expires_on DATE, composite_at_call FLOAT, evidence JSON, status VARCHAR,"
            "closed_at DATETIME, exit_date DATE, exit_price FLOAT, return_pct FLOAT,"
            "r_multiple FLOAT)"
        ))
        conn.execute(text(
            "INSERT INTO trade_call (symbol, call_date, direction, source, entry_price,"
            " stop_price, target_price, expires_on, composite_at_call, status)"
            " VALUES ('CRSP', '2026-07-14', 'long', 'auto_flag', 100.0, 94.0, 118.0,"
            " '2026-08-28', 62.0, 'open')"
        ))

    # Old model query would 500 here with 'no such column'. init_db must heal it.
    db.init_db()

    from sqlmodel import Session, select
    from app.models import TradeCall

    with Session(db.engine) as s:
        calls = s.exec(select(TradeCall)).all()  # would raise before the fix
    assert len(calls) == 1
    assert calls[0].symbol == "CRSP"
    assert calls[0].confidence is None  # backfilled as NULL -> display falls back to composite

    from app.calls.confidence import display_confidence
    assert display_confidence(calls[0]) == 62.0  # old calls keep a sane conviction


def test_init_db_adds_ctgov_names_to_preexisting_security(tmp_path, monkeypatch):
    db = _fresh_db_module(tmp_path, monkeypatch)

    # Simulate the OLD production schema: security exists WITHOUT ctgov_names.
    with db.engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE security ("
            "symbol VARCHAR PRIMARY KEY, name VARCHAR, subsector JSON,"
            "active BOOLEAN, created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO security (symbol, name, subsector, active, created_at,"
            " updated_at) VALUES ('BNTX', 'BioNTech', '[\"mrna\"]', 1,"
            " '2026-01-01', '2026-01-01')"
        ))

    db.init_db()

    from sqlmodel import Session, select
    from app.models import Security

    with Session(db.engine) as s:
        secs = s.exec(select(Security)).all()  # would raise before the fix
    assert len(secs) == 1
    assert secs[0].symbol == "BNTX"
    # Backfilled as NULL; consumers read it as "no aliases" (fall back to name).
    assert (secs[0].ctgov_names or []) == []


def test_init_db_idempotent_on_current_schema(tmp_path, monkeypatch):
    db = _fresh_db_module(tmp_path, monkeypatch)
    db.init_db()
    db.init_db()  # second run: no duplicate-column error
    from sqlalchemy import inspect
    cols = {c["name"] for c in inspect(db.engine).get_columns("trade_call")}
    assert "confidence" in cols
    sec_cols = {c["name"] for c in inspect(db.engine).get_columns("security")}
    assert "ctgov_names" in sec_cols
