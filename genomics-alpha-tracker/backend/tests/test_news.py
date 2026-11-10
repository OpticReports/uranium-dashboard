"""News lane gates: ingestion budget/dedupe, velocity math, no-key skip."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.ingestion import news_tiingo as nt
from app.models import NewsArticle


def _mem():
    eng = create_engine("sqlite://",
                        connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


def test_no_key_skips(monkeypatch):
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    with Session(_mem()) as s:
        assert nt.run_news(s, ["crsp"]) == 0


def test_ingest_dedupe_and_budget(monkeypatch):
    monkeypatch.setenv("TIINGO_API_KEY", "k")
    monkeypatch.setenv("TIINGO_DAILY_CAP", "1")
    nt._BUDGET.update({"day": None, "used": 0})
    calls = {"n": 0}

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return [{"id": 7, "publishedDate": "2026-08-15T10:00:00Z",
                     "title": "CRISPR readout", "source": "x", "url": "u",
                     "tickers": ["crsp"], "description": "d"}]

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return R()
    monkeypatch.setattr(nt.httpx, "get", fake_get)
    with Session(_mem()) as s:
        assert nt.run_news(s, ["crsp"]) == 1
        assert nt.run_news(s, ["crsp"]) == 0          # cap=1: second run skips
        assert calls["n"] == 1
        nt._BUDGET.update({"day": None, "used": 0})
        assert nt.run_news(s, ["crsp"]) == 0          # dedupe by article id
        assert s.get(NewsArticle, 7).title == "CRISPR readout"


def test_pulse_velocity(monkeypatch):
    from app import db as adb
    from sqlmodel import SQLModel as SM, delete
    SM.metadata.create_all(adb.engine)
    now = datetime.now(timezone.utc)
    with Session(adb.engine) as s:
        s.exec(delete(NewsArticle))
        for i in range(6):                             # baseline: 1/day for 6d
            s.add(NewsArticle(id=100 + i, title="t", source="s", url="u",
                              tickers="crsp",
                              published=(now - timedelta(days=i + 1, hours=1)).isoformat()))
        for i in range(4):                             # burst today
            s.add(NewsArticle(id=200 + i, title="burst", source="s", url="u",
                              tickers="crsp",
                              published=(now - timedelta(hours=i + 1)).isoformat()))
        s.commit()
    from app.main import app
    c = TestClient(app)
    p = c.get("/news/pulse").json()
    d = p["tickers"]["CRSP"]
    assert d["n_24h"] == 4 and d["n_7d"] == 10
    assert d["velocity_x"] == 4.0
    assert "CRSP" in p["movers"]
    assert "DESCRIPTIVE" in p["note"]
    t = c.get("/news/CRSP").json()
    assert len(t["items"]) == 10
    with Session(adb.engine) as s:
        s.exec(delete(NewsArticle))
        s.commit()
