"""End-to-end gate: the REAL Robinhood-Chain payload for the tokenized Farmmi
token, pushed through discovery -> registry -> rollup -> ladder -> alert with
every network lane stubbed.

Three tape states over identical on-chain plumbing, which is the whole product
in miniature:

  * the snapshot AS CAPTURED (2026-09-02 ~18:00 UTC) — JINQIAN's last hour was
    running at 0.47x its own 24h rate, i.e. already cooling. The ladder must
    hold at PAIRED and stay silent. Alerting here would be alerting on a move
    that has been and gone.
  * the same pools while ACCELERATING, tape still flat — this is the trade, and
    the alert must fire.
  * accelerating pools, tape already up on 160x volume — suppressed, because by
    then the alert is an obituary.
"""
from __future__ import annotations

import copy

import pytest
from sqlmodel import Session, select

from app import scan
from app.db import engine as db_engine, init_db
from app.models import Candidate, EquityToken, MemeLaunch, ScanState, StageEvent
from tests.conftest import load

# The real FAMI tape on 2026-09-02, and the prior close the evening before.
QUOTE_MOVED = {"price": 0.1518, "prev_close": 0.1187, "change_pct": 27.89,
               "volume": 807_631_865, "high_52w": 2.05, "low_52w": 0.0919,
               "exchange": "NASDAQ", "market_status": "open"}
QUOTE_FLAT = {"price": 0.1187, "prev_close": 0.123, "change_pct": -3.5,
              "volume": 4_904_808, "high_52w": 2.05, "low_52w": 0.0919,
              "exchange": "NASDAQ", "market_status": "open"}


def _accelerating(pairs: list[dict]) -> list[dict]:
    """Counterfactual: the same pools an hour into the ramp instead of after
    it. Only the volume/price windows are touched — depth, trade counts and
    token identities stay exactly as captured."""
    out = copy.deepcopy(pairs)
    for p in out:
        vol = p.get("volume") or {}
        h24 = vol.get("h24") or 0.0
        if h24 <= 0:
            continue
        vol["h1"] = h24 / 3.0
        vol["m5"] = h24 / 12.0
        p.setdefault("priceChange", {})["h1"] = 40.0
    return out


@pytest.fixture
def wired(monkeypatch):
    """Stub every network lane; return a factory that sets the tape + pools."""
    init_db()
    with Session(db_engine) as s:
        # ScanState too: the universe cursor is deliberately persistent in
        # production, so leaving it set would leak between tests.
        for model in (StageEvent, Candidate, MemeLaunch, EquityToken, ScanState):
            for row in s.exec(select(model)).all():
                s.delete(row)
        s.commit()

    monkeypatch.setattr(scan.equity_lane, "sec_universe",
                        lambda *a, **k: scan.equity_lane.parse_sec_universe(
                            load("sec_company_tickers.json")))
    monkeypatch.setattr(scan.equity_lane, "history",
                        lambda *a, **k: scan.equity_lane.parse_history(
                            load("fami_history.json")))
    # The credentialed lane is stubbed off: tests never spend a real API call,
    # and the no-key degradation path is what gets exercised by default.
    monkeypatch.setattr(scan.fundamentals, "profile", lambda *a, **k: {})
    monkeypatch.setattr(scan.dexscreener, "meta_pairs", lambda *a, **k: [])
    monkeypatch.setattr(scan.dexscreener, "token_boosts_latest", lambda *a, **k: [])

    def wire(quote, pairs):
        monkeypatch.setattr(scan.equity_lane, "quote", lambda *a, **k: dict(quote))
        monkeypatch.setattr(scan.dexscreener, "search",
                            lambda q, **k: pairs if q.upper() == "FAMI" else [])
        monkeypatch.setattr(scan.dexscreener, "token_pairs", lambda *a, **k: pairs)
    return wire


def _run(wire, quote, pairs=None):
    wire(quote, pairs if pairs is not None else load("robinhood_fami_token_pairs.json"))
    with Session(db_engine) as s:
        scan.universe_sweep(s, slice_size=10_000)
        scan.registry_sweep(s)
        alerts = scan.rollup(s)
        cand = s.exec(select(Candidate).where(Candidate.ticker == "FAMI")).first()
        launches = s.exec(select(MemeLaunch).where(MemeLaunch.ticker == "FAMI")).all()
        return alerts, cand, launches


def test_registry_learns_the_unofficial_wrapper(wired):
    _, cand, _ = _run(wired, QUOTE_FLAT)
    with Session(db_engine) as s:
        tokens = s.exec(select(EquityToken).where(EquityToken.ticker == "FAMI")).all()
    assert len(tokens) == 1
    assert tokens[0].issuer_class == "UNOFFICIAL"
    assert tokens[0].company == "Farmmi, Inc."
    assert cand.issuer_class == "UNOFFICIAL"


def test_the_meme_cluster_is_reconstructed(wired):
    _, cand, launches = _run(wired, QUOTE_FLAT)
    symbols = {l.base_symbol for l in launches}
    assert {"JINQIAN", "MUSHROOMCOIN", "YUANBAO", "JINCHAN"} <= symbols
    assert cand.meme_count >= 4
    assert cand.top_meme_symbol
    assert cand.onchain_volume_h24 > 1_000_000


def test_wrapper_deployment_is_timestamped_before_the_memes(wired):
    """The earliest and most valuable rung: the tokenized FAMI pool was seeded
    the evening BEFORE the memes launched against it."""
    _, cand, _ = _run(wired, QUOTE_FLAT)
    assert cand.first_tokenized_at is not None
    assert cand.first_paired_at is not None
    assert cand.first_tokenized_at < cand.first_paired_at


def test_cooling_snapshot_does_not_alert(wired):
    """As captured, JINQIAN's last hour ran at 0.47x its own 24h rate. A screen
    that alerts on this is alerting on a move that already happened."""
    alerts, cand, _ = _run(wired, QUOTE_FLAT)
    assert cand.stage == "PAIRED"
    assert any("cooling" in r for r in cand.reasons)
    assert alerts == []


def test_alert_fires_while_accelerating_and_the_stock_is_still_flat(wired):
    """The trade: on-chain cascade in progress, tape has not reacted yet."""
    pairs = _accelerating(load("robinhood_fami_token_pairs.json"))
    alerts, cand, _ = _run(wired, QUOTE_FLAT, pairs)
    assert cand.stage == "CLUSTER"
    fami = [a for a in alerts if a["ticker"] == "FAMI"]
    assert fami, "expected a FAMI alert while the tape was still quiet"
    assert fami[0]["score"] > 45
    assert any("attention-only" in r for r in fami[0]["reasons"])


def test_alert_is_suppressed_once_the_stock_has_already_run(wired):
    """The obituary: same accelerating pools, but 807M shares have traded."""
    pairs = _accelerating(load("robinhood_fami_token_pairs.json"))
    alerts, cand, _ = _run(wired, QUOTE_MOVED, pairs)
    assert cand.stage == "EQUITY_MOVING"
    assert not [a for a in alerts if a["ticker"] == "FAMI"]


def test_ladder_transitions_are_recorded_for_lead_lag(wired):
    _run(wired, QUOTE_FLAT)
    with Session(db_engine) as s:
        events = s.exec(select(StageEvent).where(StageEvent.ticker == "FAMI")).all()
    assert events, "transitions must persist or lead time can never be measured"
    assert all(e.hours_since_tokenized is not None for e in events)


def test_rescanning_the_same_pairs_is_idempotent(wired):
    _, _, first = _run(wired, QUOTE_FLAT)
    _, _, again = _run(wired, QUOTE_FLAT)
    assert len(first) == len(again) > 0
    with Session(db_engine) as s:
        assert len(s.exec(select(Candidate).where(Candidate.ticker == "FAMI")).all()) == 1
        assert len(s.exec(select(EquityToken)).all()) == 1


def test_equity_lane_dark_does_not_crash_or_alert(wired):
    """A dark quote lane must degrade, never fabricate a call."""
    wired({}, load("robinhood_fami_token_pairs.json"))
    with Session(db_engine) as s:
        scan.universe_sweep(s, slice_size=10_000)
        scan.registry_sweep(s)
        alerts = scan.rollup(s)
        cand = s.exec(select(Candidate).where(Candidate.ticker == "FAMI")).first()
    assert cand.equity_dark is True
    assert cand.pumpability == 0.0
    assert alerts == []


def _wrapper_only(pairs: list[dict]) -> list[dict]:
    """The state the world was in on the evening of 2026-09-01: the tokenized
    FAMI pool exists, no meme has been pooled against it yet."""
    return [p for p in pairs
            if {p["baseToken"]["symbol"], p["quoteToken"]["symbol"]} <= {"FAMI", "USDG", "ETH"}]


def test_cold_tokenization_alert_fires_the_night_before(wired):
    """The highest-lead rung: a $5.7M nanocap has been wrapped on-chain and
    nothing has been built on it. In the real timeline this state preceded the
    equity move by ~15.8 hours."""
    pairs = _wrapper_only(load("robinhood_fami_token_pairs.json"))
    alerts, cand, launches = _run(wired, QUOTE_FLAT, pairs)
    assert launches == [], "fixture should contain no meme launches"
    assert cand.stage == "TOKENIZED"
    fami = [a for a in alerts if a["ticker"] == "FAMI"]
    assert fami, "expected a cold-tokenization alert"
    assert "nanocap" in fami[0]["why"]


def test_cold_tokenization_does_not_alert_on_a_large_cap(wired, monkeypatch):
    """Same shape, but the underlying is a $1T name — routine, not a signal."""
    pairs = _wrapper_only(load("robinhood_fami_token_pairs.json"))
    monkeypatch.setattr(scan.fundamentals, "profile",
                        lambda *a, **k: {"market_cap": 1_200_000_000_000})
    alerts, cand, _ = _run(wired, {**QUOTE_FLAT, "price": 224.0}, pairs)
    assert cand.stage == "TOKENIZED"
    assert alerts == []


def test_alert_payload_carries_the_pools_and_their_links(wired):
    """Casey's test: the alert has to show what is actually trading, not just
    name a ticker."""
    pairs = _accelerating(load("robinhood_fami_token_pairs.json"))
    alerts, _, _ = _run(wired, QUOTE_FLAT, pairs)
    fami = [a for a in alerts if a["ticker"] == "FAMI"][0]
    pools = fami["pools"]
    assert pools, "alert must carry the pools"
    assert pools[0]["symbol"] == "JINQIAN", "deepest pool should lead"
    assert pools[0]["url"].startswith("https://dexscreener.com/")
    assert pools[0]["liquidity_usd"] > pools[-1]["liquidity_usd"]
    for p in pools:
        assert {"symbol", "url", "liquidity_usd", "volume_h24", "chain"} <= set(p)


def test_pool_snapshots_are_recorded_for_the_trend_read(wired):
    """Liquidity trajectory needs history; one reading is not a trajectory."""
    from app.models import PoolSnapshot
    _run(wired, QUOTE_FLAT)
    with Session(db_engine) as s:
        snaps = s.exec(select(PoolSnapshot).where(PoolSnapshot.ticker == "FAMI")).all()
    assert snaps, "expected pool snapshots"
    assert all(x.at is not None for x in snaps)
    # A single reading must not fabricate a trend.
    with Session(db_engine) as s:
        launches = s.exec(select(MemeLaunch).where(MemeLaunch.ticker == "FAMI")).all()
    assert all(l.liquidity_trend_pct is None for l in launches)


def test_telegram_push_is_attempted_for_a_fired_alert(wired, monkeypatch):
    sent = []
    monkeypatch.setattr(scan.alerts, "push", lambda a: sent.append(a) or True)
    pairs = _accelerating(load("robinhood_fami_token_pairs.json"))
    _run(wired, QUOTE_FLAT, pairs)
    assert sent and sent[0]["ticker"] == "FAMI"


def test_no_push_when_nothing_fires(wired, monkeypatch):
    sent = []
    monkeypatch.setattr(scan.alerts, "push", lambda a: sent.append(a) or True)
    _run(wired, QUOTE_MOVED)          # equity already moving -> suppressed
    assert sent == []
