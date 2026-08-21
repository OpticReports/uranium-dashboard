"""API surface: health, manual catalysts (incl. direction lean), status page.

Offline: RUN_SCHEDULER=false (conftest env) so no jobs and no network at boot;
the app's own DB points at a temp file set in conftest before app import.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

client = TestClient(app)
init_db()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "catalyst-options-engine"
    assert body["paper_only"] is True and body["keyless"] is True


def test_post_manual_catalyst_with_lean():
    r = client.post("/catalysts", json={
        "symbol": "mrna", "date": "2026-09-10",
        "event_type": "interim_analysis",
        "title": "INTerpath-002 interim analysis (operator-entered)",
        "direction_lean": "bullish"})
    assert r.status_code == 201
    body = r.json()
    assert body["symbol"] == "MRNA"
    assert body["direction_lean"] == "bullish"
    assert body["source"] == "manual"
    assert body["impact_weight"] == 0.95  # engine.yaml interim_analysis weight


def test_post_manual_catalyst_rejects_bad_lean():
    r = client.post("/catalysts", json={
        "symbol": "MRNA", "date": "2026-09-10",
        "event_type": "interim_analysis", "title": "x",
        "direction_lean": "moon"})
    assert r.status_code == 422


def test_undated_manual_catalyst_becomes_watch():
    r = client.post("/catalysts", json={
        "symbol": "BNTX", "event_type": "interim_analysis",
        "title": "undated interim watch (operator)"})
    assert r.status_code == 201
    assert r.json()["watch"] is True
    assert r.json()["date"] is None


def test_setups_and_book_endpoints_empty_ok():
    assert client.get("/setups").status_code == 200
    book = client.get("/paper/book").json()
    assert book["summary"]["equity"] == 100000.0
    assert client.get("/paper/positions").status_code == 200


def test_status_page_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "Catalyst Options Engine" in r.text
    assert "PAPER ONLY" in r.text


def test_close_unknown_position_404():
    assert client.post("/paper/close/99999").status_code == 404
