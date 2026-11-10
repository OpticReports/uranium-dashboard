"""Write routes on a PUBLICLY REACHABLE app require a token, and fail CLOSED.

Until 2026-09-21 src/barbell/web/app.py contained no auth construct of any
kind. `grep -cE "Depends|HTTPBearer|Security|add_middleware|verify_token"`
returned 0 while POST /api/promote — whose own docstring says "this changes
the live book's targets" — answered the public internet, and its typed-label
confirmation was served unauthenticated by GET /api/versions. POST /api/chat
also reaches register_trial(..., sharpe=None, ...), and stats.trials
cumulative_count is COUNT(*), so an anonymous caller could inflate the
selection-bias hurdle every book in the monorepo is deflated against.
"""
import os

import pytest
from fastapi.testclient import TestClient

from barbell.web.app import WRITE_ROUTES, app

SECRET = "s3kr1t-for-tests"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BARBELL_TOKEN", SECRET)
    return TestClient(app)


def _post(c, route, **kw):
    return c.post(route, json={}, **kw)


def test_every_mutating_route_requires_a_token(client):
    """THE GATE THAT MATTERS: enumerate the LIVE app, not a hand-kept list.

    A new POST route added later without a dependency fails here rather than
    shipping open. btc-executor's _WRITE_ENDPOINTS list has the same job and
    the same instruction: this must grow whenever a write endpoint is added.
    """
    live = {r.path for r in app.routes
            if "POST" in getattr(r, "methods", set())}
    assert live == set(WRITE_ROUTES), (
        f"unlisted POST routes: {sorted(live - set(WRITE_ROUTES))}; "
        f"listed but absent: {sorted(set(WRITE_ROUTES) - live)}")
    for route in sorted(live):
        assert _post(client, route).status_code == 401, route


def test_a_wrong_token_is_refused(client):
    for route in WRITE_ROUTES:
        r = _post(client, route, headers={"X-Barbell-Token": "wrong"})
        assert r.status_code == 401, route
        r = client.post(route, json={}, params={"token": "wrong"})
        assert r.status_code == 401, route


def test_unconfigured_fails_CLOSED_not_open(monkeypatch):
    """The inversion of btc-executor's _auth, deliberately. There, an absent
    token opens up because a refusing executor leaves a live position
    unmanaged. Here nothing holds a position, so an absent token must mean
    the promote button is OFF, never that it is open to everyone."""
    monkeypatch.delenv("BARBELL_TOKEN", raising=False)
    c = TestClient(app)
    for route in WRITE_ROUTES:
        r = _post(c, route)
        assert r.status_code == 503, (route, r.status_code)
        assert "not configured" in r.text
    monkeypatch.setenv("BARBELL_TOKEN", "   ")      # whitespace is not a token
    for route in WRITE_ROUTES:
        assert _post(TestClient(app), route).status_code == 503, route


def test_a_correct_token_passes_the_gate(client):
    """Past auth the HANDLER runs — on a bare test DB it may 422 or even 500,
    and that is the point: 401/503 must not be what a valid caller sees.
    raise_server_exceptions=False so a handler blowing up on an empty
    database surfaces as 500 rather than propagating and masking the
    auth result this test is actually about."""
    c = TestClient(app, raise_server_exceptions=False)
    for route in WRITE_ROUTES:
        for kw in ({"headers": {"X-Barbell-Token": SECRET}},
                   {"params": {"token": SECRET}}):
            r = c.post(route, json={}, **kw)
            assert r.status_code not in (401, 503), (route, kw, r.status_code)


def test_reads_are_still_open_so_the_hub_keeps_working(client):
    """Scoped deliberately: this app is fronted by the optic.capital hub and
    the public GET surface is its whole purpose. Gating reads is a separate
    decision with a separate blast radius — recorded, not silently taken."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/versions").status_code == 200


def test_the_browser_shim_ships_on_every_page(client):
    """One monkey-patch on window.fetch covers every POST call site, so a
    page added later cannot forget the header."""
    body = client.get("/versions").text
    assert "X-Barbell-Token" in body
    assert "sessionStorage" in body
    assert "replaceState" in body      # the token leaves the address bar
