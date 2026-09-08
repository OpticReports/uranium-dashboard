"""DataForSEO lane gates: response parsing, no-key skip, daily cap, once-per-
day dedupe, breaker on 401/402/403, series replacement, router shape."""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.ingestion import trends as lane
from app.models import PriceBar, Security, TrendPoint
from app.trends import dataforseo as dfs


def _payload(n=60, start=date(2021, 1, 3)):
    data = [{"date_from": (start + timedelta(weeks=k)).isoformat(),
             "date_to": (start + timedelta(weeks=k, days=6)).isoformat(),
             "timestamp": 0, "missing_data": False, "values": [10 + (k % 7)]} for k in range(n)]
    return {"status_code": 20000, "status_message": "Ok.", "cost": 0.009,
            "tasks": [{"status_code": 20000, "status_message": "Ok.",
                       "result": [{"keywords": ["silver price"], "items": [
                           {"type": "google_trends_map", "data": []},
                           {"type": "google_trends_graph", "data": data}]}]}]}


def test_parse_graph_extracts_weekly_points():
    pts = dfs.parse_graph(_payload(5))
    assert [p["date"] for p in pts] == ["2021-01-03", "2021-01-10", "2021-01-17", "2021-01-24", "2021-01-31"]
    assert pts[0]["value"] == 10.0 and pts[0]["missing"] is False


def test_parse_graph_raises_on_api_error():
    with pytest.raises(dfs.TrendsError) as e:
        dfs.parse_graph({"status_code": 40200, "status_message": "Payment required"})
    assert e.value.status == 40200
    bad = _payload(3)
    bad["tasks"][0]["status_code"] = 40501
    with pytest.raises(dfs.TrendsError):
        dfs.parse_graph(bad)


def test_redact_scrubs_credentials():
    assert "hunter2" not in dfs.redact("password='hunter2' Authorization: Basic aGk6aHVudGVyMg==")
    assert "aGk6" not in dfs.redact("Authorization: Basic aGk6aHVudGVyMg==")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    lane._BUDGET.update({"day": None, "used": 0, "cost_usd": 0.0})
    lane._BREAKER.update({"until": 0.0, "reason": None})
    lane._FETCHED.update({"day": None, "keywords": set()})
    monkeypatch.setattr(lane, "ensure_proxy_prices", lambda *a, **k: 0)
    monkeypatch.setattr(lane, "keywords", lambda: [
        {"keyword": "silver price", "label": "Silver", "price_symbol": "SLV"},
        {"keyword": "bitcoin", "label": "Bitcoin", "price_symbol": "BTCUSD"}])
    yield


def test_no_credentials_skips(session, monkeypatch):
    monkeypatch.setattr(lane.settings, "dataforseo_login", None)
    monkeypatch.setattr(lane.settings, "dataforseo_password", None)
    assert lane.run_trends(session) == 0
    assert lane.status()["configured"] is False


def test_fetch_replaces_series_and_dedupes_per_day(session, monkeypatch):
    monkeypatch.setattr(lane.settings, "dataforseo_login", "u")
    monkeypatch.setattr(lane.settings, "dataforseo_password", "p")
    calls = {"n": 0}

    def fake(keyword, login, password, **kw):
        calls["n"] += 1
        return dfs.parse_graph(_payload(60)), 0.009
    monkeypatch.setattr(lane, "fetch_interest", fake)
    # a stale row from an older window must be gone after the refresh
    session.add(TrendPoint(keyword="silver price", date=date(2015, 1, 4), value=99, window="old"))
    session.commit()
    n = lane.run_trends(session)
    assert n == 120 and calls["n"] == 2
    rows = session.exec(select(TrendPoint).where(TrendPoint.keyword == "silver price")).all()
    assert len(rows) == 60 and all(r.window == "past_5_years" for r in rows)
    # second run the same UTC day: nothing spent
    assert lane.run_trends(session) == 0 and calls["n"] == 2
    st = lane.status()
    assert st["used_today"] == 2 and abs(st["cost_today_usd"] - 0.018) < 1e-9


def test_short_series_keeps_previous(session, monkeypatch):
    monkeypatch.setattr(lane.settings, "dataforseo_login", "u")
    monkeypatch.setattr(lane.settings, "dataforseo_password", "p")
    monkeypatch.setattr(lane, "fetch_interest", lambda *a, **k: (dfs.parse_graph(_payload(10)), 0.009))
    session.add(TrendPoint(keyword="silver price", date=date(2015, 1, 4), value=99))
    session.commit()
    assert lane.run_trends(session) == 0
    assert session.exec(select(TrendPoint)).first().value == 99


def test_daily_cap(session, monkeypatch):
    monkeypatch.setattr(lane.settings, "dataforseo_login", "u")
    monkeypatch.setattr(lane.settings, "dataforseo_password", "p")
    monkeypatch.setenv("TRENDS_DAILY_CAP", "1")
    monkeypatch.setattr(lane, "fetch_interest", lambda *a, **k: (dfs.parse_graph(_payload(60)), 0.009))
    assert lane.run_trends(session) == 60


@pytest.mark.parametrize("status", [401, 402, 403])
def test_breaker_trips_on_auth_or_billing(session, monkeypatch, status):
    monkeypatch.setattr(lane.settings, "dataforseo_login", "u")
    monkeypatch.setattr(lane.settings, "dataforseo_password", "p")

    def boom(*a, **k):
        raise dfs.TrendsError("nope", status=status)
    monkeypatch.setattr(lane, "fetch_interest", boom)
    assert lane.run_trends(session) == 0
    assert lane._BREAKER["until"] > time.time() + 23 * 3600
    assert lane.status()["breaker_until"] is not None
    # while tripped, nothing is spent
    monkeypatch.setattr(lane, "fetch_interest", lambda *a, **k: (dfs.parse_graph(_payload(60)), 0.009))
    assert lane.run_trends(session) == 0


def test_router_pairs_price_and_reports_state(session, monkeypatch):
    # test_migrations.py reloads app.db, so take the router's own bound
    # get_session (same pattern as test_shadow.py).
    from app.main import app
    from app.routers.trends import get_session
    # seed: a flat interest series with one parabolic record spike at the end,
    # and a rising price - the detector must call CLIMAX on the last week.
    start = date(2020, 1, 5)
    session.add(Security(symbol="SLV", name="SLV (trends proxy)", subsector=["trends_proxy"], active=False))
    n = 120
    for k in range(n):
        v = 20.0 if k < n - 2 else (45.0 if k == n - 2 else 60.0)
        session.add(TrendPoint(keyword="silver price", date=start + timedelta(weeks=k), value=v))
        for d in range(5):
            session.add(PriceBar(symbol="SLV", date=start + timedelta(weeks=k, days=1 + d),
                                 close=20.0 + k * 0.5))
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    try:
        c = TestClient(app)
        r = c.get("/trends")
        assert r.status_code == 200
        body = r.json()
        assert body["note"].startswith("OBSERVE-ONLY")
        silver = next(i for i in body["items"] if i["keyword"] == "silver price")
        assert silver["summary"]["state"] == "CLIMAX"
        assert silver["points"][-1]["close"] == pytest.approx(20.0 + (n - 1) * 0.5)
        assert silver["points"][-1]["stage"] == 1
        one = c.get("/trends/silver%20price").json()
        assert one["summary"]["last_climax"] == silver["summary"]["last_climax"]
        assert c.get("/trends/nope").status_code == 404
        st = c.get("/trends/study").json()
        assert st["pooled"]["recall"]["price_peaks"] == 11
        assert c.get("/health").json()["optional_keys"]["dataforseo"] is False
    finally:
        app.dependency_overrides.clear()
