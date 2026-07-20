"""twitterapi.io circuit breaker: a 402 (or auth error) pauses the whole X
source for the cycle instead of hammering the dead endpoint per symbol."""
from __future__ import annotations

import httpx
import pytest

from app.ingestion import social


class _Resp:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture(autouse=True)
def _reset_breaker(monkeypatch):
    social._x_breaker["until"] = 0.0
    social._x_fetch_day.clear()
    monkeypatch.setattr(social.settings, "twitterapi_io_key", "k", raising=False)
    monkeypatch.setattr(social.settings, "x_bearer_token", None, raising=False)
    yield
    social._x_breaker["until"] = 0.0


def test_402_trips_breaker_and_pauses_all_symbols(monkeypatch):
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return _Resp(402)

    monkeypatch.setattr(social.httpx, "get", fake_get)
    src = social.SocialIngestion()

    # First symbol hits the 402 -> trips the breaker (one HTTP call).
    assert src._twitterapi_io("BFLY") == []
    assert calls["n"] == 1
    assert social._x_breaker_open()

    # Every subsequent symbol this cycle short-circuits with NO HTTP call.
    for sym in ("CRSP", "NTLA", "TEM", "GH"):
        assert src._twitterapi_io(sym) == []
    assert calls["n"] == 1  # still just the one call — no per-symbol hammering


def test_auth_error_also_trips_breaker(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(social.httpx, "get",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1) or _Resp(401)))
    src = social.SocialIngestion()
    assert src._twitterapi_io("BFLY") == []
    assert src._twitterapi_io("CRSP") == []
    assert calls["n"] == 1
    assert social._x_breaker_open()


def test_402_cooldown_longer_than_auth():
    social._x_breaker["until"] = 0.0
    social._trip_x_breaker(401)
    auth_until = social._x_breaker["until"]
    social._x_breaker["until"] = 0.0
    social._trip_x_breaker(402)
    credits_until = social._x_breaker["until"]
    assert credits_until > auth_until  # 402 backs off ~24h vs ~1h for auth


def test_healthy_response_does_not_trip(monkeypatch):
    monkeypatch.setattr(social.httpx, "get", lambda *a, **k: _Resp(
        200, {"tweets": [], "has_next_page": False, "next_cursor": None}))
    src = social.SocialIngestion()
    assert src._twitterapi_io("BFLY") == []
    assert not social._x_breaker_open()  # no error -> breaker stays closed
