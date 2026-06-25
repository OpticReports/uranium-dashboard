"""Tests for catalyst ingestion normalization + override-preserving upsert."""
from __future__ import annotations

from datetime import date, timedelta

from app.ingestion.catalysts import CatalystIngestion, _parse_loose_date
from sqlmodel import select

from app.models import Catalyst, Security


def _study(nct, title, phase, pcd):
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": title},
            "statusModule": {"primaryCompletionDateStruct": {"date": pcd}},
            "designModule": {"phases": [phase]},
        }
    }


def test_parse_loose_date_handles_year_month():
    assert _parse_loose_date("2026-09-15") == date(2026, 9, 15)
    assert _parse_loose_date("2026-09") == date(2026, 9, 15)  # mid-month estimate
    assert _parse_loose_date(None) is None
    assert _parse_loose_date("garbage") is None


def test_normalize_maps_phase_to_event_and_impact():
    ing = CatalystIngestion()
    future = (date.today() + timedelta(days=120)).isoformat()
    raw = {"trials": [_study("NCT1", "Pivotal study", "PHASE3", future)], "earnings": []}
    recs = ing.normalize("CRSP", raw)
    assert len(recs) == 1
    assert recs[0].event_type == "phase3_readout"
    assert recs[0].impact_weight >= 0.8  # phase 3 is heavily weighted


def test_normalize_skips_past_dates():
    ing = CatalystIngestion()
    past = (date.today() - timedelta(days=10)).isoformat()
    raw = {"trials": [_study("NCT2", "Old", "PHASE2", past)], "earnings": [past]}
    assert ing.normalize("CRSP", raw) == []


def test_normalize_includes_future_earnings():
    ing = CatalystIngestion()
    future = (date.today() + timedelta(days=20)).isoformat()
    raw = {"trials": [], "earnings": [future]}
    recs = ing.normalize("LLY", raw)
    assert len(recs) == 1 and recs[0].event_type == "earnings"


def test_upsert_preserves_manual_override(session):
    session.add(Security(symbol="CRSP", name="CRISPR", subsector=["gene-editing"]))
    session.commit()
    ing = CatalystIngestion()
    d = date.today() + timedelta(days=90)
    cat = Catalyst(symbol="CRSP", date=d, event_type="phase3_readout",
                   title="X", impact_weight=0.9)
    ing.upsert(session, [cat])

    # Operator sets a manual override.
    stored = session.exec(select(Catalyst).where(Catalyst.symbol == "CRSP")).first()
    stored.impact_override = 1.0
    session.add(stored)
    session.commit()

    # Re-ingesting the same catalyst must NOT clobber the override.
    cat2 = Catalyst(symbol="CRSP", date=d, event_type="phase3_readout",
                    title="X", impact_weight=0.85)
    ing.upsert(session, [cat2])
    again = session.exec(select(Catalyst).where(Catalyst.symbol == "CRSP")).first()
    assert again.impact_override == 1.0
    assert again.effective_impact == 1.0
