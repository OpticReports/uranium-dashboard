"""Tests for universe management: upsert is history-safe, deactivate retains data."""
from __future__ import annotations

from datetime import date

from sqlmodel import select

from app.models import PriceBar, Security
from app.universe import manager


def test_upsert_insert_then_update_preserves_history(session):
    manager.upsert_security(session, "CRSP", "CRISPR Therapeutics", ["gene-editing"], True)
    # Add a historical price row.
    session.add(PriceBar(symbol="CRSP", date=date(2026, 1, 2), close=50.0))
    session.commit()

    # Update tags + deactivate; history must remain.
    sec = manager.set_active(session, "CRSP", False)
    assert sec.active is False
    bars = session.exec(select(PriceBar).where(PriceBar.symbol == "CRSP")).all()
    assert len(bars) == 1  # history retained on deactivate


def test_upsert_updates_fields_without_duplicating(session):
    manager.upsert_security(session, "BEAM", "Beam", ["gene-editing"], True)
    manager.upsert_security(session, "BEAM", "Beam Therapeutics", ["gene-editing", "base-edit"], True)
    secs = manager.list_securities(session)
    beams = [s for s in secs if s.symbol == "BEAM"]
    assert len(beams) == 1
    assert beams[0].name == "Beam Therapeutics"
    assert "base-edit" in beams[0].subsector


def test_symbol_is_uppercased(session):
    manager.upsert_security(session, "ntla", "Intellia")
    assert manager.get_security(session, "NTLA") is not None
    assert manager.get_security(session, "ntla") is not None  # lookup also uppercases


def test_delete_removes_security(session):
    manager.upsert_security(session, "TWST", "Twist")
    assert manager.delete_security(session, "TWST") is True
    assert manager.get_security(session, "TWST") is None
    assert manager.delete_security(session, "NOPE") is False


def test_all_subsectors_are_deduped_and_sorted(session):
    manager.upsert_security(session, "A", "A", ["x", "y"])
    manager.upsert_security(session, "B", "B", ["y", "z"])
    assert manager.all_subsectors(session) == ["x", "y", "z"]


def test_list_can_exclude_inactive(session):
    manager.upsert_security(session, "ACT", "Active", active=True)
    manager.upsert_security(session, "INACT", "Inactive", active=False)
    active_only = manager.list_securities(session, include_inactive=False)
    symbols = {s.symbol for s in active_only}
    assert "ACT" in symbols and "INACT" not in symbols
