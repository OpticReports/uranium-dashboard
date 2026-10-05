"""Recall fixes to the discovery funnel (2026-10-05, after the Vertex audit).

Vertex Pharmaceuticals ($128B, co-owner of Casgevy with CRISPR Therapeutics,
15 active phase-3 trials) scored 60 with ZERO genomics tags and never
surfaced: its Casgevy trials are titled "CTX001" and the keyword match read
only the company name and trial titles. Separately, genomics tools makers
(10x, PacBio, Bruker) were absent from the census because Nasdaq files them
under Industrials. And the daily movers snapshot drifted with every redeploy.

Each fix is pinned here with the shapes CT.gov and the Nasdaq screener
actually return, including the false positive the full-census simulation
caught: counting ANY universe name as a partner pulled in Bristol-Myers and
Incyte through their Eli Lilly collaborations.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.ingestion import discovery as disc
from app.models import Security, UniverseCandidate

TODAY = date(2026, 10, 5)


def _cfg(**over):
    cfg = dict(disc._DEFAULTS)
    cfg.update(over)
    return cfg


def _study(nct, title, phases, pcd, lead="X", collaborators=(), interventions=()):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": "RECRUITING",
                         "primaryCompletionDateStruct": {"date": pcd}},
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": lead},
            "collaborators": [{"name": c} for c in collaborators]},
        "armsInterventionsModule": {"interventions": [{"type": t} for t in interventions]},
        "designModule": {"phases": phases},
    }}


class _Sec:
    def __init__(self, name, subsector, ctgov_names=(), active=True):
        self.name, self.subsector, self.ctgov_names, self.active = name, list(subsector), list(ctgov_names), active


UNIVERSE = [
    _Sec("CRISPR Therapeutics", ["gene-editing"]),
    _Sec("Moderna", ["mrna", "vaccines"], ["ModernaTX"]),
    _Sec("Eli Lilly", ["pharma", "anchor"]),
    _Sec("Butterfly Network", ["devices", "imaging"]),
    _Sec("Old Edit Co", ["gene-editing"], active=False),
]
MODS = disc._DEFAULTS["partner_modalities"]


# --- pure helpers -------------------------------------------------------------------

def test_partner_names_cover_lead_and_collaborators():
    s = [_study("N1", "t", ["PHASE3"], "2026-11", lead="Vertex Pharmaceuticals Incorporated",
                collaborators=["CRISPR Therapeutics"]),
         _study("N2", "t", ["PHASE2"], "2027-01", lead="Vertex Pharmaceuticals Incorporated",
                collaborators=["Moderna, Inc"])]
    assert disc.trial_partner_names(s) == ["Vertex Pharmaceuticals Incorporated", "CRISPR Therapeutics",
                                           "Vertex Pharmaceuticals Incorporated", "Moderna, Inc"]
    assert disc.trial_partner_names([]) == []


def test_genetic_intervention_detects_ctgov_gene_transfer_label():
    assert disc.has_genetic_intervention([_study("N", "t", ["PHASE3"], "2027", interventions=["DRUG", "GENETIC"])])
    # CRISPR / Intellia label their editing products BIOLOGICAL - not GENETIC
    assert not disc.has_genetic_intervention([_study("N", "t", ["PHASE3"], "2027", interventions=["BIOLOGICAL"])])


def test_universe_partner_names_are_modality_restricted():
    names = disc.universe_partner_names(UNIVERSE, MODS)
    assert names == {"crispr therapeutics", "moderna", "modernatx"}
    # Eli Lilly (pharma), Butterfly (devices) and an INACTIVE gene-editing name never count
    assert "eli lilly" not in names and "butterfly network" not in names and "old edit co" not in names


def test_partner_hits_exclude_the_candidate_itself():
    names = {"crispr therapeutics", "moderna"}
    assert disc.genomics_partner_hits(["CRISPR Therapeutics", "Vertex"], names, "Vertex Pharmaceuticals") == \
        ["crispr therapeutics"]
    # a universe name is never its own partner
    assert disc.genomics_partner_hits(["CRISPR Therapeutics AG"], names, "CRISPR Therapeutics") == []


# --- the catalyst lane on the Vertex shape ------------------------------------------

def _vertex(monkeypatch, collaborators):
    near = (TODAY + timedelta(days=25)).isoformat()
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [
        _study("NCT05444257", "Long-term Safety and Efficacy of VX-121 Combination Therapy",
               ["PHASE3"], near, lead="Vertex Pharmaceuticals Incorporated"),
        _study("NCT05329649", "A Study of CTX001 in Pediatric Participants With Sickle Cell Disease",
               ["PHASE3"], "2027-06", lead="Vertex Pharmaceuticals Incorporated",
               collaborators=collaborators, interventions=["BIOLOGICAL"]),
    ] if cleaned == "Vertex Pharmaceuticals" else [])
    return [{"symbol": "VRTX", "name": "Vertex Pharmaceuticals Incorporated Common Stock",
             "last": 504.73, "pct_change": -0.4, "market_cap": 127.9e9}]


def test_vertex_is_tagged_through_its_crispr_partner_and_clears_auto_promote(monkeypatch, session):
    census = _vertex(monkeypatch, ["CRISPR Therapeutics"])
    partners = disc.universe_partner_names(UNIVERSE, MODS)
    out, checked = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY, partners)
    assert checked == 1
    c = out["VRTX"]
    assert c["genomics_tags"] == {"gene-editing", "genomics-partner"}
    assert c["evidence"]["genomics_partners"] == ["crispr therapeutics"]
    disc.upsert_candidates(session, out, _cfg(), TODAY)
    row = session.get(UniverseCandidate, "VRTX")
    assert row.score == pytest.approx(76.0)              # 25 mcap + 35 PCD<=60d + 16 two tags
    promoted = disc.auto_promote(session, _cfg(), TODAY)
    assert promoted == ["VRTX"]                          # standard path: score, $2B, PCD <= 90d
    assert session.get(Security, "VRTX") is not None


def test_without_the_partner_signal_vertex_stays_at_60(monkeypatch, session):
    """The pre-fix behaviour, kept as the control: same trials, no partners passed."""
    census = _vertex(monkeypatch, ["CRISPR Therapeutics"])
    out, _ = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY)  # partner_names omitted
    # the collaborator NAME still carries "crispr" -> one keyword tag, no partner tag
    assert out["VRTX"]["genomics_tags"] == {"gene-editing"}
    disc.upsert_candidates(session, out, _cfg(), TODAY)
    assert session.get(UniverseCandidate, "VRTX").score == pytest.approx(68.0)
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_a_big_pharma_partner_is_not_a_genomics_partner(monkeypatch):
    """The simulation's false positive: BMY/INCY partner with Eli Lilly. Lilly
    is in the universe but carries no genomics modality, so no tag."""
    census = _vertex(monkeypatch, ["Eli Lilly and Company"])
    partners = disc.universe_partner_names(UNIVERSE, MODS)
    out, _ = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY, partners)
    assert "genomics-partner" not in out["VRTX"]["genomics_tags"]
    assert "genomics_partners" not in out["VRTX"]["evidence"]


def test_genetic_intervention_alone_makes_a_phase2_name_a_candidate(monkeypatch):
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [
        _study("N9", "A Gene Transfer Study in DMD", ["PHASE2"], "2028-01", interventions=["GENETIC"])])
    census = [{"symbol": "SRPT", "name": "Sarepta Therapeutics, Inc. Common Stock",
               "last": 20.0, "pct_change": 0.1, "market_cap": 2.1e9}]
    out, _ = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY, set())
    assert out["SRPT"]["genomics_tags"] == {"gene-therapy"}


# --- census supplement ------------------------------------------------------------------

def _dl_row(sym, name, sector, industry, mcap="12,182,224,208.00", pct="1.0%"):
    return {"symbol": sym, "name": name, "sector": sector, "industry": industry,
            "lastsale": "$10.00", "pctchange": pct, "marketCap": mcap}


@pytest.fixture
def passthrough_cache(monkeypatch):
    keys: list[str] = []

    def fake_cached(key, producer, ttl=None):
        keys.append(key)
        return producer()

    monkeypatch.setattr("app.utils.cache.cached", fake_cached)
    return keys


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


def test_supplement_keeps_lab_instruments_and_genomics_names_only(monkeypatch, passthrough_cache):
    rows = [
        _dl_row("TXG", "10x Genomics, Inc. Class A Common Stock", "Industrials",
                "Biotechnology: Laboratory Analytical Instruments"),
        _dl_row("BRKR", "Bruker Corporation Common Stock", "Industrials",
                "Biotechnology: Laboratory Analytical Instruments", pct="-12.5%"),
        _dl_row("GENO", "Some Genomic Software Co", "Technology", "Computer Software: Prepackaged Software"),
        _dl_row("CAT", "Caterpillar, Inc. Common Stock", "Industrials", "Construction/Ag Equipment/Trucks"),
        _dl_row("LLY", "Eli Lilly and Company Common Stock", "Health Care",
                "Biotechnology: Pharmaceutical Preparations"),          # already in the HC census
    ]
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(params)
        return _Resp({"data": {"rows": rows}})

    monkeypatch.setattr(httpx, "get", fake_get)
    out = disc.fetch_census_supplement(_cfg())
    assert seen["download"] == "true" and "sector" not in seen
    assert passthrough_cache == ["discovery:census_supplement"]
    by = {r["symbol"]: r for r in out}
    assert set(by) == {"TXG", "BRKR", "GENO"}
    assert by["TXG"]["market_cap"] == pytest.approx(12182224208.0)
    assert by["BRKR"]["pct_change"] == pytest.approx(-12.5)


def test_supplement_off_and_failure_are_dark_not_fatal(monkeypatch, passthrough_cache, caplog):
    assert disc.fetch_census_supplement(_cfg(census_supplement=False)) == []
    monkeypatch.setattr(disc, "with_backoff", lambda fn, **kw: fn())

    def boom(*a, **kw):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(httpx, "get", boom)
    import logging
    with caplog.at_level(logging.WARNING):
        assert disc.fetch_census_supplement(_cfg()) == []
    assert "census supplement failed" in caplog.text


def test_run_discovery_merges_the_supplement_without_duplicates(session, monkeypatch):
    hc = [{"symbol": "AAA", "name": "A Bio", "last": 1.0, "pct_change": 0.0, "market_cap": 1e9}]
    supp = [{"symbol": "AAA", "name": "dup", "last": 1.0, "pct_change": 0.0, "market_cap": 1e9},
            {"symbol": "TXG", "name": "10x Genomics", "last": 1.0, "pct_change": 14.0, "market_cap": 1.2e10}]
    monkeypatch.setattr(disc, "fetch_census", lambda: hc)
    monkeypatch.setattr(disc, "fetch_census_supplement", lambda cfg: supp)
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [])
    monkeypatch.setattr("app.utils.cache.set", lambda key, value: None)
    summary = disc.run_discovery(session)
    assert summary["census"] == 2 and summary["census_supplement"] == 1
    assert summary["movers"] == 1                         # TXG's 14% day, found only via the supplement


def test_supplement_is_skipped_when_the_health_care_census_is_dark(session, monkeypatch):
    called = []
    monkeypatch.setattr(disc, "fetch_census", lambda: [])
    monkeypatch.setattr(disc, "fetch_census_supplement", lambda cfg: called.append(1) or [])
    monkeypatch.setattr("app.utils.cache.set", lambda key, value: None)
    assert disc.run_discovery(session)["census"] == 0
    assert called == []


# --- the sweep is anchored after the US close ----------------------------------------------

def test_discovery_trigger_parses_and_rejects_bad_values():
    from app.scheduler import discovery_trigger

    assert discovery_trigger({"at_utc": "21:45"}) == (21, 45)
    assert discovery_trigger({}) is None and discovery_trigger({"at_utc": ""}) is None
    with pytest.raises(ValueError):
        discovery_trigger({"at_utc": "25:00"})


def test_live_intervals_anchor_discovery_after_the_us_close():
    """21:45 UTC is after the 16:00 New York close in both EDT (20:00 UTC) and
    EST (21:00 UTC), so the movers lane always reads a close-to-close move."""
    from app.config import intervals_config
    from app.scheduler import discovery_trigger

    hour, minute = discovery_trigger(intervals_config()["discovery"])
    assert hour * 60 + minute > 21 * 60


def test_scheduler_registers_a_weekday_cron_for_discovery(monkeypatch):
    import app.scheduler as sch

    monkeypatch.setattr(sch, "_scheduler", None)
    monkeypatch.setattr(sch, "intervals_config", lambda: {
        **{n: {"enabled": False} for n in sch._JOB_FUNCS},
        "scoring": {"enabled": False}, "calls": {"enabled": False},
        "discovery": {"enabled": True, "at_utc": "21:45"}})
    sched = sch.start_scheduler()
    try:
        job = sched.get_job("discovery")
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["hour"] == "21" and fields["minute"] == "45" and fields["day_of_week"] == "mon-fri"
    finally:
        sched.shutdown(wait=False)
        monkeypatch.setattr(sch, "_scheduler", None)


def test_vertex_is_on_the_watchlist():
    from app.config import watchlist_config

    syms = {e["symbol"]: e for e in watchlist_config()["universe"]}
    assert "VRTX" in syms and syms["VRTX"]["active"] is True
    assert "gene-editing" in syms["VRTX"]["subsector"]
