"""Tests for catalyst ingestion normalization + override-preserving upsert,
sponsor-alias union fetch, radar-gap warning, and partnered-trial visibility."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from app.ingestion.catalysts import CatalystIngestion, _parse_loose_date
from sqlmodel import select

from app.models import Catalyst, Security


def _study(nct, title, phase, pcd, lead=None):
    ps = {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"primaryCompletionDateStruct": {"date": pcd}},
        "designModule": {"phases": [phase]},
    }
    if lead is not None:
        ps["sponsorCollaboratorsModule"] = {"leadSponsor": {"name": lead}}
    return {"protocolSection": ps}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _mock_ctgov(monkeypatch, responses_by_sponsor, cache_keys=None):
    """Offline CT.gov: httpx.get keyed by query.spons; cache passes through."""

    def fake_cached(key, producer, ttl=None):
        if cache_keys is not None:
            cache_keys.append(key)
        return producer()

    monkeypatch.setattr("app.utils.cache.cached", fake_cached)

    def fake_get(url, params=None, timeout=None):
        return _FakeResp({"studies": responses_by_sponsor.get(params["query.spons"], [])})

    monkeypatch.setattr(httpx, "get", fake_get)


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


def test_fetch_trials_unions_aliases_and_dedupes_by_nct(monkeypatch):
    future = (date.today() + timedelta(days=120)).isoformat()
    keys: list[str] = []
    _mock_ctgov(monkeypatch, {
        "Moderna": [_study("NCT1", "Solo trial", "PHASE2", future)],
        "ModernaTX": [
            _study("NCT1", "Solo trial", "PHASE2", future),  # overlap -> dedupe
            _study("NCT2", "Melanoma trial", "PHASE3", future),
        ],
    }, cache_keys=keys)
    ing = CatalystIngestion(name_map={"MRNA": "Moderna"},
                            alias_map={"MRNA": ["Moderna", "ModernaTX"]})
    trials = ing._fetch_trials(ing._aliases("MRNA"))
    ncts = sorted(
        t["protocolSection"]["identificationModule"]["nctId"] for t in trials
    )
    assert ncts == ["NCT1", "NCT2"]  # union, deduped by NCT id
    assert keys == ["ctgov:Moderna", "ctgov:ModernaTX"]  # per-alias cache keys


def test_alias_map_falls_back_to_display_name(monkeypatch):
    keys: list[str] = []
    _mock_ctgov(monkeypatch, {}, cache_keys=keys)
    ing = CatalystIngestion(name_map={"CRSP": "CRISPR Therapeutics"})
    ing._fetch_trials(ing._aliases("CRSP"))
    assert keys == ["ctgov:CRISPR Therapeutics"]


def test_radar_gap_warning_on_zero_studies(monkeypatch, caplog):
    _mock_ctgov(monkeypatch, {})  # every sponsor query returns 0 studies
    monkeypatch.setattr(CatalystIngestion, "_fetch_earnings", lambda self, s: [])
    ing = CatalystIngestion(name_map={"MRNA": "Moderna"},
                            alias_map={"MRNA": ["Moderna", "ModernaTX"]})
    with caplog.at_level(logging.WARNING):
        raw = ing.fetch("MRNA")
    assert raw["trials"] == []
    assert "ctgov radar gap" in caplog.text
    assert "Moderna" in caplog.text and "ModernaTX" in caplog.text


def test_no_radar_gap_warning_when_studies_found(monkeypatch, caplog):
    future = (date.today() + timedelta(days=120)).isoformat()
    _mock_ctgov(monkeypatch, {"ModernaTX": [_study("NCT2", "T", "PHASE3", future)]})
    monkeypatch.setattr(CatalystIngestion, "_fetch_earnings", lambda self, s: [])
    ing = CatalystIngestion(alias_map={"MRNA": ["ModernaTX"]})
    with caplog.at_level(logging.WARNING):
        ing.fetch("MRNA")
    assert "ctgov radar gap" not in caplog.text


def test_partnered_trial_gets_lead_sponsor_suffix():
    ing = CatalystIngestion(name_map={"MRNA": "Moderna"},
                            alias_map={"MRNA": ["ModernaTX"]})
    future = (date.today() + timedelta(days=120)).isoformat()
    raw = {"trials": [
        # Lead matches an alias (substring either way) -> no suffix.
        _study("NCT10", "Own trial", "PHASE3", future, lead="ModernaTX, Inc."),
        # Lead is the partner -> suffix names who actually runs it.
        _study("NCT11", "Partner trial", "PHASE3", future,
               lead="Merck Sharp & Dohme LLC"),
    ], "earnings": []}
    recs = ing.normalize("MRNA", raw)
    by_nct = {r.url.rsplit("/", 1)[-1]: r for r in recs}
    assert "partnered" not in by_nct["NCT10"].title
    assert by_nct["NCT11"].title.endswith(
        " — partnered, lead: Merck Sharp & Dohme LLC")


def test_partnered_suffix_respects_title_truncation():
    ing = CatalystIngestion(alias_map={"MRNA": ["ModernaTX"]})
    future = (date.today() + timedelta(days=120)).isoformat()
    raw = {"trials": [_study("NCT12", "X" * 300, "PHASE3", future,
                             lead="Merck Sharp & Dohme LLC")], "earnings": []}
    recs = ing.normalize("MRNA", raw)
    assert len(recs) == 1 and len(recs[0].title) == 200


def test_interim_analysis_is_a_recognized_event_type():
    from app.scoring.components import CatalystLike, catalyst_score_raw
    from app.utils.labels import event_label

    ing = CatalystIngestion()
    assert ing._impact["interim_analysis"] == 0.95
    # The scoring engine resolves the weight for manual interim catalysts.
    d = date.today() + timedelta(days=10)
    interim = catalyst_score_raw([CatalystLike(d, "interim_analysis")],
                                 date.today(), 180, 45, ing._impact)
    other = catalyst_score_raw([CatalystLike(d, "other")],
                               date.today(), 180, 45, ing._impact)
    assert interim > other
    assert "_" not in event_label("interim_analysis")  # never a raw code


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
