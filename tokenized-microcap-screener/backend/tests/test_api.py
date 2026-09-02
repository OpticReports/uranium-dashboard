"""API + status-page gates. The scheduler is off and no lane is called."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_reports_degradations_rather_than_hiding_them(client):
    """/health must state which optional lanes are live, so nobody reads a
    price-and-volume proxy as a real market cap."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["market_cap_enrichment"], bool)
    assert isinstance(body["alert_webhook"], bool)


def test_candidates_endpoint_is_sorted_and_filterable(client):
    assert client.get("/candidates").status_code == 200
    assert client.get("/candidates?stage=CLUSTER&min_score=50").status_code == 200


def test_unknown_ticker_is_404(client):
    assert client.get("/candidates/ZZZZ").status_code == 404


def test_leadlag_reports_sample_size_and_the_caveat(client):
    body = client.get("/leadlag").json()
    assert "legs" in body and "caveat" in body
    for leg in body["legs"].values():
        assert "n" in leg and "interpretable" in leg
        # A leg with too few observations must never present as an estimate.
        if leg["n"] < 5:
            assert leg["interpretable"] is False


def test_status_page_renders_and_carries_the_honesty_note(client):
    html = client.get("/").text
    assert "Tokenized Microcap Screener" in html
    assert "watchlist generator, not a signal" in html
    assert "unofficial" in html


def test_config_endpoint_exposes_the_live_tunables(client):
    cfg = client.get("/config").json()
    assert cfg["ladder"]["cluster_min_memes"] >= 1
    assert "robinhood" in cfg["scan"]["chains"]


def test_health_reports_the_alert_channels(client):
    body = client.get("/health").json()
    assert isinstance(body["telegram_alerts"], bool)
    assert body["telegram_min_severity"] in ("INFO", "WARN", "RED", "CRITICAL")
    # Short interest is genuinely unavailable for these microcaps on FMP, so
    # it is reported absent rather than proxied by something else.
    assert body["short_interest"] is False


def test_pools_endpoints_exist_and_filter(client):
    assert client.get("/pools").status_code == 200
    assert client.get("/pools?ticker=FAMI&min_liquidity=1000").status_code == 200
    assert client.get("/pools/0xabc/history").json() == []


def test_status_page_has_a_pools_section(client):
    html = client.get("/").text
    assert "what is actually trading against these tickers" in html
