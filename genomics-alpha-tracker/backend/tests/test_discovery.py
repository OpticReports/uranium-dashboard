"""Dynamic universe discovery tests — all OFFLINE (mocked httpx + cache).

Fixture shapes are trimmed from real captures (2026-08-19):
  * Nasdaq screener: data.table.rows string fields incl. '--', '', 'NA', '$',
    commas; data.totalrecords drives pagination.
  * ClinicalTrials.gov v2: protocolSection modules, 'YYYY-MM' loose dates.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ingestion import discovery as disc
from app.models import Security, UniverseCandidate
from sqlmodel import select


TODAY = date.today()


def _cfg(**over):
    cfg = dict(disc._DEFAULTS)
    cfg.update(over)
    return cfg


# --- Fixtures: realistic screener / CT.gov shapes -------------------------------

def _row(symbol, name, lastsale, pctchange, market_cap):
    # Real shape: {"symbol": "LLY", "name": "Eli Lilly and Company Common
    # Stock", "lastsale": "$1,268.815", "netchange": "43.085", "pctchange":
    # "3.515%", "marketCap": "1,194,407,964,428", "url": "/market-activity/..."}
    return {"symbol": symbol, "name": name, "lastsale": lastsale,
            "netchange": "0.0", "pctchange": pctchange, "marketCap": market_cap,
            "url": f"/market-activity/stocks/{symbol.lower()}"}


def _screener_payload(rows, total):
    return {"data": {"filters": None,
                     "table": {"asOf": None, "rows": rows},
                     "totalrecords": total},
            "message": None, "status": {"rCode": 200}}


def _study(nct, title, phases, pcd):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": "RECRUITING",
                         "primaryCompletionDateStruct": {"date": pcd}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "X"}},
        "designModule": {"phases": phases},
    }}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def passthrough_cache(monkeypatch):
    keys: list[str] = []

    def fake_cached(key, producer, ttl=None):
        keys.append(key)
        return producer()

    monkeypatch.setattr("app.utils.cache.cached", fake_cached)
    monkeypatch.setattr("app.utils.cache.set", lambda key, value: None)
    return keys


# --- Pure parsers ----------------------------------------------------------------

def test_parse_money_handles_screener_strings():
    assert disc.parse_money("$1,268.815") == pytest.approx(1268.815)
    assert disc.parse_money("10,588,934,649") == pytest.approx(10588934649.0)
    assert disc.parse_money("-6.025") == pytest.approx(-6.025)
    # No data is None — NEVER a silent zero.
    for bad in ("", "--", "NA", "N/A", None, "garbage"):
        assert disc.parse_money(bad) is None


def test_parse_pct_handles_sign_and_missing():
    assert disc.parse_pct("2.547%") == pytest.approx(2.547)
    assert disc.parse_pct("-1.529%") == pytest.approx(-1.529)
    assert disc.parse_pct("10.483%") == pytest.approx(10.483)
    assert disc.parse_pct("--") is None
    assert disc.parse_pct("") is None
    assert disc.parse_pct(None) is None


def test_clean_company_name_strips_listing_boilerplate():
    assert disc.clean_company_name("Moderna, Inc. Common Stock") == "Moderna"
    assert disc.clean_company_name("Eli Lilly and Company Common Stock") == "Eli Lilly"
    assert disc.clean_company_name("BioNTech SE American Depositary Shares") == "BioNTech SE"
    assert disc.clean_company_name("Twist Bioscience Corporation") == "Twist Bioscience"
    assert disc.clean_company_name("Guardant Health, Inc.") == "Guardant Health"
    # Degenerate input never returns empty.
    assert disc.clean_company_name("Inc.") == "Inc."


# --- Census fetch ------------------------------------------------------------------

def test_fetch_census_paginates_and_parses(monkeypatch, passthrough_cache):
    pages = {
        0: [_row("LLY", "Eli Lilly and Company Common Stock", "$1,268.815",
                 "3.515%", "1,194,407,964,428"),
            _row("MRK", "Merck & Company, Inc. Common Stock (new)", "$149.34",
                 "10.483%", "368,447,412,419")],
        100: [_row("ODD1", "Oddball Diagnostics Inc.", "$4.10", "--", ""),
              _row("ODD2", "NA-Cap Bio plc", "", "-12.4%", "NA"),
              {"symbol": "", "name": "row without symbol is skipped"}],
        200: [_row("TAIL", "Tail End Therapeutics Inc.", "$9.00", "0.5%",
                   "450,000,000")],
    }
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(int(params["offset"]))
        assert "Mozilla/5.0" in headers["User-Agent"]  # Nasdaq rejects default UAs
        return _FakeResp(_screener_payload(pages[int(params["offset"])], 250))

    monkeypatch.setattr(httpx, "get", fake_get)
    rows = disc.fetch_census()
    assert calls == [0, 100, 200]  # paginate until offset >= totalrecords
    assert passthrough_cache == ["discovery:census"]
    by_sym = {r["symbol"]: r for r in rows}
    assert len(rows) == 5  # symbol-less row dropped
    assert by_sym["LLY"]["last"] == pytest.approx(1268.815)
    assert by_sym["LLY"]["market_cap"] == pytest.approx(1194407964428.0)
    assert by_sym["MRK"]["pct_change"] == pytest.approx(10.483)
    assert by_sym["ODD1"]["pct_change"] is None    # '--'
    assert by_sym["ODD1"]["market_cap"] is None    # ''
    assert by_sym["ODD2"]["last"] is None          # ''
    assert by_sym["ODD2"]["market_cap"] is None    # 'NA'


def test_fetch_census_failure_goes_dark_never_raises(monkeypatch, passthrough_cache, caplog):
    monkeypatch.setattr(disc, "with_backoff", lambda fn, **kw: fn())

    def boom(*a, **kw):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(httpx, "get", boom)
    import logging
    with caplog.at_level(logging.WARNING):
        assert disc.fetch_census() == []
    assert "census fetch failed" in caplog.text


# --- Movers lane (the miss-detector) -----------------------------------------------

def _census():
    return [
        # In-universe mover: must be excluded (we already cover it).
        {"symbol": "MRNA", "name": "Moderna, Inc. Common Stock",
         "last": 300.0, "pct_change": 130.0, "market_cap": 120e9},
        # The miss: big mover, big cap, not covered -> candidate.
        {"symbol": "MRK", "name": "Merck & Company, Inc. Common Stock",
         "last": 149.34, "pct_change": 10.483, "market_cap": 368e9},
        # Negative movers count too (|pct|).
        {"symbol": "DOWN", "name": "Downbeat Genomics Inc.",
         "last": 12.0, "pct_change": -14.0, "market_cap": 900e6},
        # Too small.
        {"symbol": "TINY", "name": "Tiny Bio Inc.",
         "last": 2.0, "pct_change": 40.0, "market_cap": 50e6},
        # Not enough of a move.
        {"symbol": "FLAT", "name": "Flatline Therapeutics Inc.",
         "last": 30.0, "pct_change": 2.0, "market_cap": 5e9},
        # No-data fields are None -> skipped, never treated as 0.
        {"symbol": "NOPCT", "name": "No Print Inc.",
         "last": None, "pct_change": None, "market_cap": 5e9},
        {"symbol": "NOCAP", "name": "No Cap Inc.",
         "last": 5.0, "pct_change": 25.0, "market_cap": None},
    ]


def test_movers_lane_detects_misses_and_dedupes_universe():
    out = disc.movers_lane(_census(), {"MRNA"}, _cfg(), TODAY)
    assert set(out) == {"MRK", "DOWN"}
    ev = out["MRK"]["evidence"]
    assert ev["move_pct"] == pytest.approx(10.483)
    assert ev["date"] == TODAY.isoformat()
    assert ev["market_cap"] == pytest.approx(368e9)
    assert out["MRK"]["sources"] == {"mover"}
    assert out["DOWN"]["genomics_tags"] == {"sequencing"}  # "Genomics" in name


def test_movers_lane_excludes_inactive_universe_names_too():
    # "Any active state": an inactive Security was parked on purpose, not missed.
    out = disc.movers_lane(_census(), {"MRNA", "MRK", "DOWN"}, _cfg(), TODAY)
    assert set(out) == set()


# --- Rotation ----------------------------------------------------------------------

def test_rotation_is_deterministic_and_partitions():
    symbols = [f"SYM{i}" for i in range(200)]
    buckets = {s: disc.rotation_bucket(s, 10) for s in symbols}
    # Deterministic: same symbol, same bucket, every call.
    for s in symbols:
        assert disc.rotation_bucket(s, 10) == buckets[s]
        assert 0 <= buckets[s] < 10
    # Partition: across a full rotation each symbol is selected exactly once.
    seen: list[str] = []
    for day_bucket in range(10):
        seen += [s for s in symbols if buckets[s] == day_bucket]
    assert sorted(seen) == sorted(symbols)
    # Case-insensitive (screener symbols are upper, but be safe).
    assert disc.rotation_bucket("abc", 10) == disc.rotation_bucket("ABC", 10)


# --- Catalyst-census lane ------------------------------------------------------------

def _mock_trials(monkeypatch, by_name):
    monkeypatch.setattr(disc, "_fetch_ctgov_trials",
                        lambda cleaned: by_name.get(cleaned, []))


def test_catalyst_lane_near_phase3_is_sufficient(monkeypatch):
    near = (TODAY + timedelta(days=90)).isoformat()
    # clean_company_name("Merck & Company, Inc. Common Stock") == "Merck"
    _mock_trials(monkeypatch, {"Merck": [
        _study("NCT1", "Pivotal oncology study", ["PHASE3"], near)]})
    census = [{"symbol": "MRK", "name": "Merck & Company, Inc. Common Stock",
               "last": 149.0, "pct_change": 1.0, "market_cap": 368e9}]
    out, checked = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY)
    assert checked == 1
    ev = out["MRK"]["evidence"]
    assert ev["nearest_pcd"] == near
    assert ev["trials"][0]["nct"] == "NCT1"
    assert out["MRK"]["sources"] == {"catalyst"}


def test_catalyst_lane_phase2_needs_genomics_keyword(monkeypatch):
    # No near phase-3; PHASE2 only -> candidate ONLY with a genomics match.
    _mock_trials(monkeypatch, {
        "Plain Pharma": [_study("NCT2", "A statin study", ["PHASE2"], "2027-06")],
        "Edit Bio": [_study("NCT3", "CRISPR gene editing in TTR amyloidosis",
                            ["PHASE2"], "2027-06")],
    })
    census = [
        {"symbol": "PLN", "name": "Plain Pharma Inc.", "last": 10.0,
         "pct_change": 0.0, "market_cap": 2e9},
        {"symbol": "EDT", "name": "Edit Bio Inc.", "last": 10.0,
         "pct_change": 0.0, "market_cap": 2e9},
    ]
    out, checked = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY)
    assert checked == 2
    assert set(out) == {"EDT"}
    assert out["EDT"]["genomics_tags"] == {"gene-editing"}
    # Far-out PHASE2 has no phase-3 PCD -> nearest_pcd None (no data, not 0).
    assert out["EDT"]["evidence"]["nearest_pcd"] is None


def test_catalyst_lane_zero_trials_is_a_valid_outcome(monkeypatch):
    _mock_trials(monkeypatch, {})  # imperfect name matching -> 0 results is fine
    census = [{"symbol": "GHOST", "name": "Ghost Biotech Inc.", "last": 5.0,
               "pct_change": 0.0, "market_cap": 1e9}]
    out, checked = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY)
    assert checked == 1 and out == {}


def test_catalyst_lane_respects_rotation_bucket(monkeypatch):
    calls = []

    def spy(cleaned):
        calls.append(cleaned)
        return []

    monkeypatch.setattr(disc, "_fetch_ctgov_trials", spy)
    census = [{"symbol": f"SYM{i}", "name": f"Name {i} Inc.", "last": 1.0,
               "pct_change": 0.0, "market_cap": 1e9} for i in range(50)]
    cfg = _cfg(rotation_days=10)
    _, checked = disc.catalyst_lane(census, set(), cfg, TODAY)
    expected = [r["symbol"] for r in census
                if disc.rotation_bucket(r["symbol"], 10) == TODAY.toordinal() % 10]
    assert checked == len(expected) == len(calls)  # only today's bucket queried


def test_trial_evidence_capped_at_five_and_titles_truncated(monkeypatch):
    near = (TODAY + timedelta(days=30)).isoformat()
    studies = [_study(f"NCT{i}", "X" * 300, ["PHASE3"],
                      (TODAY + timedelta(days=30 + i)).isoformat())
               for i in range(8)]
    _mock_trials(monkeypatch, {"Busy Bio": studies})
    census = [{"symbol": "BUSY", "name": "Busy Bio Inc.", "last": 1.0,
               "pct_change": 0.0, "market_cap": 1e9}]
    out, _ = disc.catalyst_lane(census, set(), _cfg(rotation_days=1), TODAY)
    trials = out["BUSY"]["evidence"]["trials"]
    assert len(trials) == 5
    assert all(len(t["title"]) <= 120 for t in trials)
    assert trials[0]["pcd"] == near  # sorted nearest-first
    assert out["BUSY"]["evidence"]["nearest_pcd"] == near


# --- Tagging -----------------------------------------------------------------------

def test_genomics_tagging_matches_and_dedupes():
    tags = disc.genomics_tags_for([
        "Acme Genomics Inc.",
        "A CRISPR base editing study",
        "siRNA knockdown of PCSK9",
    ])
    assert tags == ["gene-editing", "rna", "sequencing"]  # deduped, sorted
    assert disc.genomics_tags_for(["Plain Industrials Corp"]) == []  # no match is fine
    assert disc.genomics_tags_for(["CAR-T CELL THERAPY"]) == ["cell-therapy"]  # case-insensitive


# --- Scoring -----------------------------------------------------------------------

@pytest.mark.parametrize("mcap,pcd,tags,mv,age,expected", [
    (None, None, 0, None, None, 0.0),            # no data anywhere -> 0
    (12e9, None, 0, None, None, 25.0),           # mcap >= 10B
    (5e9, None, 0, None, None, 20.0),            # mcap >= 2B
    (1.5e9, None, 0, None, None, 15.0),          # mcap >= 1B
    (500e6, None, 0, None, None, 10.0),          # mcap >= 300M
    (100e6, None, 0, None, None, 0.0),           # below floor
    (None, 45, 0, None, None, 35.0),             # phase-3 PCD <= 60d
    (None, 100, 0, None, None, 25.0),            # <= 120d
    (None, 200, 0, None, None, 15.0),            # <= 240d
    (None, 300, 0, None, None, 0.0),             # beyond horizon
    (None, -5, 0, None, None, 0.0),              # past PCD scores nothing
    (None, None, 2, None, None, 16.0),           # 2 tags * 8
    (None, None, 7, None, None, 24.0),           # tag term capped at 3
    (None, None, 0, 16.0, 3, 16.0),              # big move within 7d
    (None, None, 0, -16.0, 3, 16.0),             # abs move counts
    (None, None, 0, 16.0, 20, 8.0),              # within 30d
    (None, None, 0, 16.0, 45, 0.0),              # stale move
    (None, None, 0, 5.0, 1, 0.0),                # sub-threshold move
    (12e9, 45, 3, 16.0, 3, 100.0),               # 25+35+24+16 = 100, clamp holds
])
def test_score_candidate_table(mcap, pcd, tags, mv, age, expected):
    assert disc.score_candidate(mcap, pcd, tags, mv, age) == pytest.approx(expected)


def test_score_candidate_clamped_0_100():
    assert 0.0 <= disc.score_candidate(12e9, 1, 9, 99.0, 0) <= 100.0
    assert disc.score_candidate(-1e9, None, -5, None, None) == 0.0


# --- Upsert ------------------------------------------------------------------------

def _mover_cand(symbol="MRK", pct=10.5, mcap=368e9, day=None):
    day = day or TODAY
    return {symbol: {
        "name": f"{symbol} Pharma Inc.", "market_cap": mcap, "last_price": 100.0,
        "sources": {"mover"}, "genomics_tags": set(),
        "evidence": {"move_pct": pct, "date": day.isoformat(), "market_cap": mcap},
    }}


def test_upsert_inserts_new_candidate(session):
    n_new, n_upd = disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    assert (n_new, n_upd) == (1, 0)
    cand = session.get(UniverseCandidate, "MRK")
    assert cand.status == "new"
    assert cand.sources == ["mover"]
    assert cand.first_seen == cand.last_seen == TODAY
    assert cand.score == pytest.approx(25 + 16)  # $368B cap + fresh mover


def test_upsert_skips_names_already_in_universe_even_inactive(session):
    session.add(Security(symbol="MRK", name="Merck", active=False))
    session.commit()
    n_new, n_upd = disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    assert (n_new, n_upd) == (0, 0)
    assert session.get(UniverseCandidate, "MRK") is None


def test_upsert_updates_unions_sources_and_keeps_status(session):
    yesterday = TODAY - timedelta(days=1)
    disc.upsert_candidates(session, _mover_cand(day=yesterday), _cfg(), yesterday)
    cand = session.get(UniverseCandidate, "MRK")
    cand.status = "watch"  # the desk parked it in watch
    session.add(cand)
    session.commit()

    near = (TODAY + timedelta(days=50)).isoformat()
    catalyst = {"MRK": {
        "name": "MRK Pharma Inc.", "market_cap": 368e9, "last_price": 101.0,
        "sources": {"catalyst"}, "genomics_tags": {"mrna"},
        "evidence": {"trials": [{"nct": "NCT9", "phase": "PHASE3",
                                 "pcd": near, "title": "t"}],
                     "nearest_pcd": near},
    }}
    n_new, n_upd = disc.upsert_candidates(session, catalyst, _cfg(), TODAY)
    assert (n_new, n_upd) == (0, 1)
    cand = session.get(UniverseCandidate, "MRK")
    assert cand.status == "watch"                       # desk status kept
    assert cand.sources == ["catalyst", "mover"]        # union
    assert cand.genomics_tags == ["mrna"]
    assert cand.first_seen == yesterday and cand.last_seen == TODAY
    # Evidence union: retained mover print + new catalyst trials.
    assert cand.evidence["move_pct"] == pytest.approx(10.5)
    assert cand.evidence["nearest_pcd"] == near
    # Re-score sees ALL merged evidence: 25 (cap) + 35 (PCD 50d) + 8 (1 tag)
    # + 16 (mover 1 day old).
    assert cand.score == pytest.approx(25 + 35 + 8 + 16)


def test_dismissed_candidate_suppressed_within_window(session):
    disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    cand = session.get(UniverseCandidate, "MRK")
    cand.status = "dismissed"
    cand.status_reason = "not genomics-relevant"
    cand.status_changed_at = datetime.utcnow() - timedelta(days=10)
    session.add(cand)
    session.commit()

    n_new, n_upd = disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    assert (n_new, n_upd) == (0, 0)
    cand = session.get(UniverseCandidate, "MRK")
    assert cand.status == "dismissed"                    # window holds
    assert cand.status_reason == "not genomics-relevant"


def test_dismissed_candidate_resurfaces_after_window(session):
    disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    cand = session.get(UniverseCandidate, "MRK")
    cand.status = "dismissed"
    cand.status_reason = "old judgment"
    cand.status_changed_at = datetime.utcnow() - timedelta(days=120)
    session.add(cand)
    session.commit()

    n_new, n_upd = disc.upsert_candidates(session, _mover_cand(), _cfg(), TODAY)
    assert (n_new, n_upd) == (0, 1)
    cand = session.get(UniverseCandidate, "MRK")
    assert cand.status == "new"            # fresh signal resurfaces it
    assert cand.status_reason is None      # stale dismissal reason cleared


# --- Auto-promote --------------------------------------------------------------------

def _queued(session, symbol, score=80.0, mcap=5e9, evidence=None, tags=None,
            status="new", changed_days_ago=None):
    cand = UniverseCandidate(
        symbol=symbol, name=f"{symbol} Bio Inc.", market_cap=mcap, score=score,
        status=status, sources=["mover"], genomics_tags=tags or ["mrna"],
        evidence=evidence if evidence is not None else
        {"move_pct": 16.0, "date": TODAY.isoformat()},
    )
    if changed_days_ago is not None:
        cand.status_changed_at = datetime.utcnow() - timedelta(days=changed_days_ago)
    session.add(cand)
    session.commit()
    return cand


def test_auto_promote_happy_path_creates_security(session):
    _queued(session, "BIGM")
    promoted = disc.auto_promote(session, _cfg(), TODAY)
    assert promoted == ["BIGM"]
    sec = session.get(Security, "BIGM")
    assert sec is not None and sec.active
    assert sec.subsector == ["mrna"]                     # tags become subsector
    assert sec.name == "BIGM Bio"                        # cleaned name
    cand = session.get(UniverseCandidate, "BIGM")
    assert cand.status == "promoted"
    assert cand.status_reason.startswith("auto: ")
    assert "move +16.0%" in cand.status_reason           # gates summarized


def test_auto_promote_gate_score(session):
    _queued(session, "LOWS", score=69.0)
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    assert session.get(Security, "LOWS") is None


def test_auto_promote_gate_mcap(session):
    _queued(session, "SMLC", mcap=1.9e9)                 # score fine, cap not
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_auto_promote_gate_needs_near_pcd_or_big_move(session):
    # 12% move (>=10 makes it a candidate, <15 fails the promote gate) and a
    # phase-3 PCD at 120d (>90d): high score + big cap alone must NOT promote.
    _queued(session, "MEHH", evidence={
        "move_pct": 12.0, "date": TODAY.isoformat(),
        "nearest_pcd": (TODAY + timedelta(days=120)).isoformat(),
    })
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    # Near phase-3 PCD alone (no mover print at all) satisfies the OR.
    _queued(session, "NEAR", evidence={
        "nearest_pcd": (TODAY + timedelta(days=60)).isoformat()})
    assert disc.auto_promote(session, _cfg(), TODAY) == ["NEAR"]
    assert "phase-3 PCD in 60d" in session.get(UniverseCandidate, "NEAR").status_reason


def test_auto_promote_weekly_cap_counts_auto_and_manual(session):
    # 3 promotions already this week (however they happened) -> cap exhausted.
    for i, sym in enumerate(["W1", "W2", "W3"]):
        _queued(session, sym, status="promoted", changed_days_ago=i + 1)
    _queued(session, "PERF")
    assert disc.auto_promote(session, _cfg(), TODAY) == []

    # A promotion OUTSIDE the rolling 7 days frees a slot.
    old = session.get(UniverseCandidate, "W3")
    old.status_changed_at = datetime.utcnow() - timedelta(days=8)
    session.add(old)
    session.commit()
    assert disc.auto_promote(session, _cfg(), TODAY) == ["PERF"]


def test_auto_promote_partial_slots_take_highest_scores(session):
    for i, sym in enumerate(["P1", "P2"]):
        _queued(session, sym, status="promoted", changed_days_ago=i + 1)
    _queued(session, "GOOD", score=75.0)
    _queued(session, "BEST", score=95.0)
    promoted = disc.auto_promote(session, _cfg(), TODAY)  # 1 slot left of 3
    assert promoted == ["BEST"]
    assert session.get(UniverseCandidate, "GOOD").status == "new"


def test_auto_promote_config_off_is_propose_only(session):
    _queued(session, "BIGM")
    assert disc.auto_promote(session, _cfg(auto_promote=False), TODAY) == []
    assert session.get(UniverseCandidate, "BIGM").status == "new"
    assert session.get(Security, "BIGM") is None


def test_run_discovery_summary_shape(session, monkeypatch, passthrough_cache):
    monkeypatch.setattr(disc, "fetch_census", lambda: _census())
    monkeypatch.setattr(disc, "_fetch_ctgov_trials", lambda cleaned: [])
    session.add(Security(symbol="MRNA", name="Moderna", active=True))
    session.commit()
    summary = disc.run_discovery(session)
    assert summary["census"] == 7
    assert summary["movers"] == 2                       # MRK + DOWN
    assert summary["candidates_new"] == 2
    assert summary["candidates_updated"] == 0
    assert isinstance(summary["auto_promoted"], list)
    assert summary["catalyst_checked"] >= 0


# --- API ---------------------------------------------------------------------------

@pytest.fixture
def client(session):
    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_api_list_and_filter(session, client):
    _queued(session, "AAA", score=90.0)
    _queued(session, "BBB", score=50.0, status="dismissed")
    rows = client.get("/discovery/candidates").json()
    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]  # score-desc
    rows = client.get("/discovery/candidates?status=dismissed").json()
    assert [r["symbol"] for r in rows] == ["BBB"]
    assert client.get("/discovery/candidates?status=bogus").status_code == 422


def test_api_promote_creates_security(session, client):
    _queued(session, "AAA")
    out = client.post("/discovery/candidates/AAA/promote")
    assert out.status_code == 200
    body = out.json()
    assert body["status"] == "promoted" and body["status_reason"] == "manual"
    assert session.get(Security, "AAA") is not None      # actually in the universe
    # Re-promoting is a 409, and unknown symbols 404.
    assert client.post("/discovery/candidates/AAA/promote").status_code == 409
    assert client.post("/discovery/candidates/ZZZ/promote").status_code == 404


def test_api_dismiss_sets_reason(session, client):
    _queued(session, "AAA")
    out = client.post("/discovery/candidates/AAA/dismiss",
                      json={"reason": "medical devices, not genomics"})
    assert out.status_code == 200
    cand = session.get(UniverseCandidate, "AAA")
    assert cand.status == "dismissed"
    assert cand.status_reason == "medical devices, not genomics"
    # Empty reason is rejected — dismissals must be auditable.
    _queued(session, "CCC")
    assert client.post("/discovery/candidates/CCC/dismiss",
                       json={"reason": ""}).status_code == 422


def test_api_summary_counts_and_week_window(session, client, monkeypatch):
    monkeypatch.setattr("app.utils.cache.get", lambda key, ttl=None: {"census": 7})
    _queued(session, "AAA")
    _queued(session, "BBB", status="promoted", changed_days_ago=2)
    _queued(session, "CCC", status="promoted", changed_days_ago=9)  # outside window
    _queued(session, "DDD", status="dismissed")
    body = client.get("/discovery/summary").json()
    assert body["counts"] == {"new": 1, "watch": 0, "promoted": 2, "dismissed": 1}
    assert body["promoted_this_week"] == ["BBB"]
    assert body["auto_promote"] is True and body["auto_promote_per_week"] == 3
    assert body["last_run"] == {"census": 7}


def test_api_manual_run_returns_summary(session, client, monkeypatch):
    fake = {"census": 0, "movers": 0, "catalyst_checked": 0,
            "candidates_new": 0, "candidates_updated": 0, "auto_promoted": []}
    monkeypatch.setattr("app.routers.discovery.run_discovery", lambda s: fake)
    assert client.post("/discovery/run").json() == fake


# --- Auto-promote: mega-cap mover fast-path -------------------------------------
# The MRNA-in-June replay (verified live 2026-08-19): the cleaned screener name
# "Moderna" returns one partnered CF trial on CT.gov, so the candidate scores
# ~41 and the +11.6% day misses the 15% standard mover gate. Only the fast-path
# would have added it — that exact case is pinned here.

def _mrna_june(session, **over):
    kw = dict(score=41.0, mcap=23.8e9, tags=[],
              evidence={"move_pct": 11.6, "date": TODAY.isoformat()})
    kw.update(over)
    symbol = kw.pop("symbol", "MRNA")
    return _queued(session, symbol, **kw)


@pytest.fixture
def drug_trial_yes(monkeypatch):
    monkeypatch.setattr(disc, "_has_drug_trial", lambda name: True)


def test_fastpath_promotes_the_mrna_june_case(session, drug_trial_yes):
    _mrna_june(session)
    assert disc.auto_promote(session, _cfg(), TODAY) == ["MRNA"]
    cand = session.get(UniverseCandidate, "MRNA")
    assert "fast-path" in cand.status_reason
    assert cand.evidence["drug_trial_check"]["result"] is True
    sec = session.get(Security, "MRNA")
    assert sec is not None and sec.active


def test_fastpath_needs_mega_cap(session, drug_trial_yes):
    _mrna_june(session, mcap=9.9e9)                      # move fine, cap not
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_fastpath_needs_double_digit_move(session, drug_trial_yes):
    _mrna_june(session, evidence={"move_pct": 9.9, "date": TODAY.isoformat()})
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_fastpath_needs_recent_move(session, drug_trial_yes):
    stale = (TODAY - timedelta(days=8)).isoformat()
    _mrna_june(session, evidence={"move_pct": 11.6, "date": stale})
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_fastpath_respects_weekly_cap(session, drug_trial_yes):
    for i, sym in enumerate(["W1", "W2", "W3"]):
        _queued(session, sym, status="promoted", changed_days_ago=i + 1)
    _mrna_june(session)
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    assert session.get(UniverseCandidate, "MRNA").status == "new"


def test_fastpath_blocked_without_drug_trial(session, monkeypatch):
    # The UNH/HCA case: mega-cap mover with no drug/biologic trial must NOT
    # auto-add to a genomics universe.
    monkeypatch.setattr(disc, "_has_drug_trial", lambda name: False)
    _mrna_june(session, symbol="UNH")
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    cand = session.get(UniverseCandidate, "UNH")
    assert cand.status == "new"
    assert cand.evidence["drug_trial_check"]["result"] is False
    assert session.get(Security, "UNH") is None


def test_fastpath_fails_closed_when_ctgov_dark(session, monkeypatch):
    monkeypatch.setattr(disc, "_has_drug_trial", lambda name: None)
    _mrna_june(session)
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    assert session.get(UniverseCandidate, "MRNA").status == "new"


def test_fastpath_considered_before_higher_scored_standard(session, drug_trial_yes):
    # One slot left; a 95-score standard candidate must not starve the
    # low-scoring (by construction) fast-path candidate.
    for i, sym in enumerate(["P1", "P2"]):
        _queued(session, sym, status="promoted", changed_days_ago=i + 1)
    _queued(session, "BEST", score=95.0)
    _mrna_june(session)
    assert disc.auto_promote(session, _cfg(), TODAY) == ["MRNA"]
    assert session.get(UniverseCandidate, "BEST").status == "new"


def test_standard_gate_rejects_stale_mover(session):
    # High score + big cap + 16% move, but the print is 20 days old — the
    # standard mover gate requires freshness.
    stale = (TODAY - timedelta(days=20)).isoformat()
    _queued(session, "STAL", evidence={"move_pct": 16.0, "date": stale})
    assert disc.auto_promote(session, _cfg(), TODAY) == []


def test_auto_promote_never_overrides_watch(session, drug_trial_yes):
    _mrna_june(session)
    cand = session.get(UniverseCandidate, "MRNA")
    cand.status = "watch"
    session.add(cand)
    session.commit()
    assert disc.auto_promote(session, _cfg(), TODAY) == []
    assert session.get(UniverseCandidate, "MRNA").status == "watch"
