"""Catalyst lane: alias union + dedup, phase mapping, interim-watch rows,
manual events with direction lean. Offline — httpx mocked with the real
CT.gov fixture (captured live 2026-08-19, query.spons=ModernaTX)."""
from __future__ import annotations

from datetime import date

import pytest

from app.lanes import catalysts
from tests.conftest import FakeResponse, load_fixture

ASOF = date(2026, 8, 19)


@pytest.fixture()
def fixture():
    return load_fixture("ctgov_modernatx.json")


@pytest.fixture()
def mock_ctgov(monkeypatch, fixture):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["query.spons"])
        # both aliases return the same study set -> dedup must collapse them
        return FakeResponse(fixture)

    monkeypatch.setattr(catalysts.httpx, "get", fake_get)
    monkeypatch.setattr(catalysts, "cached",
                        lambda key, producer, ttl=None: producer())
    return calls


def test_union_queries_every_alias_and_dedups(mock_ctgov):
    studies = catalysts.union_studies(["ModernaTX", "Moderna"])
    assert sorted(set(mock_ctgov)) == ["Moderna", "ModernaTX"]
    ncts = [s["protocolSection"]["identificationModule"]["nctId"]
            for s in studies]
    assert len(ncts) == len(set(ncts))  # no duplicates despite 2 aliases
    assert "NCT05933577" in ncts  # the V940 melanoma trial (Merck-led)


def test_normalize_interim_watch_no_fabricated_date(fixture):
    recs = catalysts.normalize("MRNA", fixture["studies"], ASOF)
    watches = [r for r in recs if r.watch]
    # NCT05933577: ANR PHASE3, PCD 2029-10-26 (>12mo out) -> interim watch.
    # NCT06592794: ANR PHASE3, PCD 2027-02-15 is only ~6mo out -> a normal
    # DATED phase3_readout, not a watch.
    assert len(watches) == 1
    w = watches[0]
    assert w.date is None                # NEVER a fabricated date
    assert w.event_type == "interim_watch"
    assert w.impact_weight == pytest.approx(0.85)
    assert "NCT05933577" in w.title
    dated_p3 = [r for r in recs if r.event_type == "phase3_readout"]
    assert any("NCT06592794" in r.title and r.date == date(2027, 2, 15)
               for r in dated_p3)


def test_normalize_dated_events_phase_mapping(fixture):
    recs = catalysts.normalize("MRNA", fixture["studies"], ASOF)
    dated = {r.title.split("(")[-1].rstrip(")"): r for r in recs if not r.watch}
    # NCT05164094: PHASE1|PHASE2, PCD 2026-10-05 -> phase2_readout (first
    # mapped phase in list order wins per genomics convention)
    assert "NCT05164094" in dated
    ev = dated["NCT05164094"]
    assert ev.date == date(2026, 10, 5)
    assert ev.event_type in ("phase1_readout", "phase2_readout")
    assert ev.impact_weight > 0
    # NCT06067230: PCD 2026-07-30 is in the past -> excluded
    assert "NCT06067230" not in dated


def test_scan_symbol_end_to_end(mock_ctgov):
    recs = catalysts.scan_symbol("MRNA", ["ModernaTX", "Moderna"], ASOF)
    assert any(r.watch for r in recs)
    assert any(not r.watch and r.date is not None for r in recs)
    assert all(r.symbol == "MRNA" for r in recs)


def test_upsert_idempotent(session, mock_ctgov):
    recs = catalysts.scan_symbol("MRNA", ["ModernaTX"], ASOF)
    n1 = catalysts.upsert(session, recs)
    assert n1 == len(recs)
    n2 = catalysts.upsert(session,
                          catalysts.scan_symbol("MRNA", ["ModernaTX"], ASOF))
    assert n2 == 0  # re-scan inserts nothing new


def test_lane_dark_returns_empty_with_warning(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("ct.gov down")

    monkeypatch.setattr(catalysts.httpx, "get", boom)
    monkeypatch.setattr(catalysts, "cached",
                        lambda key, producer, ttl=None: producer())
    monkeypatch.setattr(catalysts, "with_backoff", lambda fn, **k: fn())
    with caplog.at_level("WARNING"):
        assert catalysts.fetch_studies("ModernaTX") == []
    assert any("DARK" in r.message for r in caplog.records)


def test_loose_date_parsing():
    assert catalysts._parse_loose_date("2026-10-05") == date(2026, 10, 5)
    assert catalysts._parse_loose_date("2029-08") == date(2029, 8, 15)  # mid-month
    assert catalysts._parse_loose_date(None) is None
    assert catalysts._parse_loose_date("garbage") is None
