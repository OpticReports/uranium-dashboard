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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """A test that forgets to stub a fetcher must fail, not query Nasdaq."""
    def _blocked(*a, **k):
        raise AssertionError("network call in a unit test")
    monkeypatch.setattr(httpx, "get", _blocked)


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
    # diagnostics/tools modalities are vendors on a trial, not partners
    assert "sequencing" not in MODS and "liquid-biopsy" not in MODS
    # Eli Lilly (pharma), Butterfly (devices) and an INACTIVE gene-editing name never count
    assert "eli lilly" not in names and "butterfly network" not in names and "old edit co" not in names


def test_discovery_promoted_names_never_seed_partners():
    class _S(_Sec):
        def __init__(self, sym, *a, **k):
            super().__init__(*a, **k)
            self.symbol = sym
    secs = [_S("CRSP", "CRISPR Therapeutics", ["gene-editing"]), _S("PROM", "Promoted Bio", ["gene-editing"])]
    assert disc.universe_partner_names(secs, MODS, {"PROM"}) == {"crispr therapeutics"}


def test_partner_match_is_whole_word():
    assert disc.genomics_partner_hits(["Illumination Health LLC"], {"illumina"}, "X") == []
    assert disc.genomics_partner_hits(["Illumina, Inc."], {"illumina"}, "X") == ["illumina"]


def test_only_the_candidates_own_phase23_studies_qualify():
    """CT.gov's sponsor search is fuzzy: 'Merck' returns a study run by The
    John Merck Fund with Illumina collaborating. It must not tag Merck."""
    fund = _study("NF", "Newborn genome sequencing", ["PHASE2"], "2027", lead="The John Merck Fund",
                  collaborators=["Illumina"])
    own = _study("NO", "Pembrolizumab study", ["PHASE3"], "2027", lead="Merck Sharp & Dohme LLC")
    registry = _study("NR", "Carrier screening", [], "2027", lead="Merck Sharp & Dohme LLC", interventions=["GENETIC"])
    assert disc.qualifying_studies([fund, own, registry], "Merck") == [own]
    assert disc.is_own_study(own, "Merck") and not disc.is_own_study(fund, "Merck")


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


def test_tags_from_studies_the_candidate_is_not_on_are_ignored(monkeypatch):
    """The Merck / NHC / J&J false positives: the study is returned by the
    fuzzy sponsor search but the candidate is neither lead nor collaborator."""
    near = (TODAY + timedelta(days=23)).isoformat()
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [
        _study("N1", "Pembrolizumab in NSCLC", ["PHASE3"], near, lead="Merck Sharp & Dohme LLC"),
        _study("N2", "Newborn Genomic Sequencing", ["PHASE2"], "2027-01", lead="The John Merck Fund",
               collaborators=["Illumina", "Moderna, Inc"], interventions=["GENETIC"]),
    ])
    census = [{"symbol": "MRK", "name": "Merck & Company, Inc. Common Stock",
               "last": 100.0, "pct_change": 0.1, "market_cap": 356e9}]
    partners = disc.universe_partner_names(UNIVERSE, MODS)
    out, _ = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY, partners)
    # title keywords on returned studies still count (pre-existing behaviour,
    # kept for recall), but nothing from the John Merck Fund study's sponsors,
    # collaborators or interventions
    assert "genomics-partner" not in out["MRK"]["genomics_tags"]
    assert "gene-therapy" not in out["MRK"]["genomics_tags"]


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
        _study("N9", "A Study in DMD", ["PHASE2"], "2028-01", lead="Sarepta Therapeutics, Inc.",
               interventions=["GENETIC"])])
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
    monkeypatch.setattr(disc, "fetch_census_with_asof", lambda: (hc, None))
    monkeypatch.setattr(disc, "fetch_census_supplement", lambda cfg: supp)
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [])
    monkeypatch.setattr("app.utils.cache.set", lambda key, value: None)
    summary = disc.run_discovery(session)
    assert summary["census"] == 2 and summary["census_supplement"] == 1
    assert summary["movers"] == 1                         # TXG's 14% day, found only via the supplement


def test_supplement_is_skipped_when_the_health_care_census_is_dark(session, monkeypatch):
    called = []
    monkeypatch.setattr(disc, "fetch_census_with_asof", lambda: ([], None))
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


def test_vertex_is_on_the_watchlist_but_does_not_seed_partners():
    from app.config import watchlist_config

    syms = {e["symbol"]: e for e in watchlist_config()["universe"]}
    assert "VRTX" in syms and syms["VRTX"]["active"] is True
    # genetic-medicines, not gene-editing: a modality tag would make every Vertex
    # collaborator a "genomics partner" (Zai Lab via povetacicept)
    assert not (set(syms["VRTX"]["subsector"]) & set(disc._DEFAULTS["partner_modalities"]))


# --- the three serious findings of counter-agent round 1 -------------------------------

def test_a_supplement_name_never_takes_the_fast_path_on_a_move_alone(session, monkeypatch):
    """Waters ($42B lab instruments) passed the drug-trial check through a CT.gov
    sponsor named 'John Waters'. A supplement name needs a genomics tag."""
    monkeypatch.setattr(disc, "_has_drug_trial", lambda name: True)
    ev = {"move_pct": -12.0, "date": TODAY.isoformat(), "census_source": "supplement"}
    session.add(UniverseCandidate(symbol="WAT", name="Waters Corporation Common Stock", status="new",
                                  score=41.0, market_cap=41.8e9, genomics_tags=[], sources=["mover"],
                                  evidence=ev, first_seen=TODAY, last_seen=TODAY))
    session.commit()
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    assert session.get(Security, "WAT") is None


def test_a_health_care_mega_cap_mover_still_takes_the_fast_path(session, monkeypatch):
    """The MRNA fix must survive: same shape, health-care census, promoted."""
    monkeypatch.setattr(disc, "_has_drug_trial", lambda name: True)
    ev = {"move_pct": 11.6, "date": TODAY.isoformat()}
    session.add(UniverseCandidate(symbol="MRNA", name="Moderna, Inc. Common Stock", status="new",
                                  score=41.0, market_cap=23.8e9, genomics_tags=[], sources=["mover"],
                                  evidence=ev, first_seen=TODAY, last_seen=TODAY))
    session.commit()
    assert disc.auto_promote(session, _cfg(), TODAY) == ["MRNA"]


def test_census_ttl_is_shorter_than_a_day():
    """The cache stamps when a fetch FINISHES; against a daily 21:45 run a 24h
    TTL re-served yesterday's snapshot every other day."""
    assert disc.CENSUS_TTL < 23 * 3600


def test_supplement_drops_preferreds_and_other_instruments(monkeypatch, passthrough_cache):
    rows = [_dl_row("BRKRP", "Bruker Corporation 6.375% Mandatory Convertible Preferred Stock, Series A",
                    "Industrials", "Biotechnology: Laboratory Analytical Instruments", mcap="71,000,000,000"),
            _dl_row("BRKR", "Bruker Corporation Common Stock", "Industrials",
                    "Biotechnology: Laboratory Analytical Instruments")]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({"data": {"rows": rows}}))
    out = disc.fetch_census_supplement(_cfg())
    assert [r["symbol"] for r in out] == ["BRKR"] and out[0]["census_source"] == "supplement"


def test_unquoted_at_utc_is_accepted():
    from app.scheduler import discovery_trigger

    assert discovery_trigger({"at_utc": 21 * 60 + 45}) == (21, 45)   # YAML 1.1 sexagesimal


def test_catchup_after_a_missed_anchor():
    from datetime import datetime

    from app.scheduler import discovery_catchup_due
    mon_2200 = datetime(2026, 10, 5, 22, 0)
    assert discovery_catchup_due(mon_2200, (21, 45), None)
    assert discovery_catchup_due(mon_2200, (21, 45), datetime(2026, 10, 2, 21, 46))   # last ran Friday
    assert not discovery_catchup_due(mon_2200, (21, 45), datetime(2026, 10, 5, 21, 46))
    assert not discovery_catchup_due(datetime(2026, 10, 5, 20, 0), (21, 45), None)    # before the anchor
    assert not discovery_catchup_due(datetime(2026, 10, 4, 22, 0), (21, 45), None)    # Sunday


# --- counter-agent round 2: the screener's own as-of date ------------------------------

def test_parse_asof():
    assert disc.parse_asof("Last price as of Oct 2, 2026") == date(2026, 10, 2)
    assert disc.parse_asof("Last price as of September 30, 2026") == date(2026, 9, 30)
    assert disc.parse_asof(None) is None and disc.parse_asof("garbage") is None


def test_adrs_are_companies_not_instruments():
    """'depositary' must never be an instrument marker: BioNTech, argenx and
    Legend list as ADRs (the first draft of the filter dropped 29 of them)."""
    assert not disc.is_instrument_row("BioNTech SE American Depositary Share")
    assert not disc.is_instrument_row("RLX Technology Inc. American Depositary Shares each representing the right to receive")
    assert disc.is_instrument_row("Revolution Medicines Inc. Warrant")
    assert disc.is_instrument_row("Fortress Biotech Inc. 9.375% Series A Cumulative Redeemable Perpetual Preferred")


def test_health_care_census_drops_units_and_warrants(monkeypatch, passthrough_cache):
    page = {"data": {"totalrecords": 2, "asof": "Last price as of Oct 2, 2026", "table": {"rows": [
        {"symbol": "BTSGU", "name": "BrightSpring Health Services, Inc. Tangible Equity Unit",
         "lastsale": "$80", "pctchange": "1%", "marketCap": "39,000,000,000"},
        {"symbol": "LLY", "name": "Eli Lilly and Company Common Stock",
         "lastsale": "$1,142.85", "pctchange": "-0.609%", "marketCap": "1,000,000,000,000"}]}}}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(page))
    rows, asof = disc.fetch_census_with_asof()
    assert [r["symbol"] for r in rows] == ["LLY"] and asof == date(2026, 10, 2)


def _run_with(session, monkeypatch, asof, rows):
    monkeypatch.setattr(disc, "fetch_census_with_asof", lambda: (rows, asof))
    monkeypatch.setattr(disc, "fetch_census_supplement", lambda cfg: [])
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [])
    return disc.run_discovery(session)


def test_moves_are_dated_by_the_snapshot_and_never_re_read(session, monkeypatch, tmp_path):
    """At 22:50 UTC on a Monday the screener still showed Friday's close. The
    move must be dated Friday, and Tuesday's run reading the SAME snapshot must
    not re-record it as a new session's move."""
    store = {}
    monkeypatch.setattr("app.utils.cache.set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr("app.utils.cache.get", lambda k, ttl=None: store.get(k))
    rows = [{"symbol": "MOVR", "name": "Mover Bio", "last": 10.0, "pct_change": 14.0, "market_cap": 1e9}]
    fri = date(2026, 10, 2)
    s1 = _run_with(session, monkeypatch, fri, rows)
    assert s1["movers"] == 1 and s1["asof"] == "2026-10-02"
    assert session.get(UniverseCandidate, "MOVR").evidence["date"] == "2026-10-02"
    s2 = _run_with(session, monkeypatch, fri, rows)                 # same snapshot again
    assert s2["movers"] == 0 and "already read" in s2["movers_note"]
    s3 = _run_with(session, monkeypatch, date(2026, 10, 5), rows)   # a new session
    assert s3["movers"] == 1
