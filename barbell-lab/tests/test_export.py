"""Merge-blocking gates on the Tier-0 lab export (/api/export/*).

The lab Mac mini pulls research data through these routes. The properties
below are the ONLY thing standing between "a keyless training box" and "a
box that quietly exfiltrates conversation history", so they are tested
rather than trusted:

  * default-closed  — no LAB_READ_TOKEN means the routes do not exist
  * constant-time   — a wrong token is 401, never a partial match
  * allow-list      — only tables listed in EXPORTABLE can leave, and the
                      chat_* tables can never be added by accident
  * schema-honest   — every exported column still exists in the table, so a
                      rename breaks CI here instead of the nightly pull
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from barbell import db
from barbell.web.export import EXPORTABLE, NEVER_EXPORTABLE

TOKEN = "lab-tok-test-42"


@pytest.fixture
def con(tmp_path, monkeypatch):
    """Point the whole app at a throwaway DB with a couple of seeded rows."""
    path = tmp_path / "barbell.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    c = db.connect(path)
    c.executemany(
        "INSERT INTO prices (ticker, date, close_adj, close_raw, volume, source) "
        "VALUES (?,?,?,?,?,?)",
        [("SPY", "2026-01-02", 500.0, 500.0, 1e6, "fmp"),
         ("SPY", "2026-06-01", 550.0, 550.0, 2e6, "fmp")])
    # Real conversation content, so the allow-list gate proves unreachability
    # rather than merely emptiness.
    c.execute("INSERT INTO chat_conversations (title, created_at, updated_at) "
              "VALUES (?,?,?)",
              ("position sizing thoughts", "2026-01-01T00:00:00Z",
               "2026-01-01T00:00:00Z"))
    c.execute("INSERT INTO chat_messages (conversation_id, role, content, created_at) "
              "VALUES (?,?,?,?)",
              (1, "user", "SECRET-CONVERSATION-CONTENT", "2026-01-01T00:00:00Z"))
    c.commit()
    return c


@pytest.fixture
def client(con, monkeypatch):
    from barbell.web.app import app
    monkeypatch.setenv("LAB_READ_TOKEN", TOKEN)
    return TestClient(app)


def _client_no_token(con, monkeypatch):
    from barbell.web.app import app
    monkeypatch.delenv("LAB_READ_TOKEN", raising=False)
    return TestClient(app)


# --------------------------------------------------------------- closed by default

def test_routes_are_404_until_token_is_set(con, monkeypatch):
    c = _client_no_token(con, monkeypatch)
    assert c.get("/api/export/manifest").status_code == 404
    assert c.get("/api/export/table/prices").status_code == 404


def test_wrong_token_is_401_and_returns_no_data(client):
    r = client.get("/api/export/table/prices", headers={"X-Lab-Token": "nope"})
    assert r.status_code == 401
    assert "SPY" not in r.text


def test_missing_header_is_401_when_token_configured(client):
    assert client.get("/api/export/manifest").status_code == 401


# --------------------------------------------------------------- allow-list

def test_chat_tables_are_never_exportable(client):
    """THE gate. Conversation content must not be reachable, ever."""
    for name in NEVER_EXPORTABLE:
        assert name not in EXPORTABLE, (
            f"{name} was added to EXPORTABLE — conversation content must never "
            f"leave this service, even to the lab box")
        r = client.get(f"/api/export/table/{name}",
                       headers={"X-Lab-Token": TOKEN})
        assert r.status_code == 404
        assert "SECRET-CONVERSATION-CONTENT" not in r.text


def test_unknown_table_is_404_even_with_valid_token(client):
    r = client.get("/api/export/table/sqlite_master",
                   headers={"X-Lab-Token": TOKEN})
    assert r.status_code == 404


def test_manifest_reports_only_allowlisted_datasets(client):
    r = client.get("/api/export/manifest", headers={"X-Lab-Token": TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert set(body["datasets"]) == set(EXPORTABLE)
    assert body["datasets"]["prices"]["rows"] == 2
    assert body["datasets"]["prices"]["latest"] == "2026-06-01"


# --------------------------------------------------------------- payload

def test_table_streams_ndjson(client):
    r = client.get("/api/export/table/prices", headers={"X-Lab-Token": TOKEN})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    rows = [json.loads(line) for line in r.text.strip().splitlines()]
    assert len(rows) == 2
    assert rows[0]["ticker"] == "SPY"
    assert rows[0]["date"] == "2026-01-02"      # ordered by time column


def test_since_filters_to_incremental_slice(client):
    r = client.get("/api/export/table/prices?since=2026-03-01",
                   headers={"X-Lab-Token": TOKEN})
    rows = [json.loads(line) for line in r.text.strip().splitlines()]
    assert [row["date"] for row in rows] == ["2026-06-01"]


# --------------------------------------------------------------- schema drift

def test_exported_columns_all_exist(con):
    """A column rename must fail here, not silently empty the nightly pull."""
    for name, (cols, tcol) in EXPORTABLE.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({name})")}
        assert have, f"{name} is in EXPORTABLE but not in the schema"
        missing = set(cols) - have
        assert not missing, f"{name}: exported columns missing from schema: {missing}"
        if tcol:
            assert tcol in have, f"{name}: time column {tcol} missing from schema"
