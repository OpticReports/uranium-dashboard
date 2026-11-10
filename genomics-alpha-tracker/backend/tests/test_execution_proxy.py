"""Execution-feed reverse proxy: GET /api/execution/feed sits behind the
dashboard's Basic gate, injects the executor's READ_TOKEN server-side (the
browser never sees it), and passes upstream status through (404 until the
env vars are set)."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings as cfg
from app.main import app


class FakeResponse:
    def __init__(self, status_code=200, content=b'{"mode": "OFFLINE"}',
                 content_type="application/json"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


class FakeAsyncClient:
    """Captures the proxied request; returns a canned upstream response."""
    calls: list[dict] = []
    response = FakeResponse()

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        FakeAsyncClient.calls.append({"url": url, "headers": dict(headers or {})})
        return FakeAsyncClient.response


@pytest.fixture
def upstream(monkeypatch):
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse()
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(cfg, "blend_upstream", "https://ibkr-executor.example")
    monkeypatch.setattr(cfg, "blend_read_token", "read-tok-42")
    return FakeAsyncClient


def test_feed_behind_dashboard_auth_and_injects_read_token(upstream, monkeypatch):
    monkeypatch.setattr(cfg, "dashboard_user", "casey")
    monkeypatch.setattr(cfg, "dashboard_password", "pw")
    c = TestClient(app)
    # no login -> 401 from the Basic gate, upstream NEVER contacted
    assert c.get("/api/execution/feed").status_code == 401
    assert upstream.calls == []
    # logged in -> proxied with the token injected server-side
    r = c.get("/api/execution/feed", auth=("casey", "pw"))
    assert r.status_code == 200
    assert r.json() == {"mode": "OFFLINE"}
    (call,) = upstream.calls
    assert call["url"] == "https://ibkr-executor.example/blend/feed"
    assert call["headers"]["X-Read-Token"] == "read-tok-42"
    # the token never leaks to the browser (body or headers)
    assert "read-tok-42" not in r.text
    assert "read-tok-42" not in str(r.headers)


def test_feed_upstream_404_passes_through(upstream):
    upstream.response = FakeResponse(status_code=404,
                                     content=b'{"detail": "not found"}')
    c = TestClient(app)
    r = c.get("/api/execution/feed")
    assert r.status_code == 404


def test_feed_not_configured_is_404_without_upstream_call(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(cfg, "blend_upstream", "")
    c = TestClient(app)
    r = c.get("/api/execution/feed")
    assert r.status_code == 404
    assert "not configured" in r.json()["detail"]
    assert FakeAsyncClient.calls == []


def test_feed_upstream_unreachable_is_502(monkeypatch):
    class BoomClient(FakeAsyncClient):
        async def get(self, url, headers=None):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", BoomClient)
    monkeypatch.setattr(cfg, "blend_upstream", "https://ibkr-executor.example")
    c = TestClient(app)
    r = c.get("/api/execution/feed")
    assert r.status_code == 502
