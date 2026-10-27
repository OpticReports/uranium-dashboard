"""Telegram analyst gates: webhook auth, owner filter, degradation, and the
snapshot's truthfulness. Offline — the LLM, Telegram sends, the bundle and
the store are monkeypatched."""
from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import telegram_chat
from app.main import app
from app.metrics.base import MetricResult, Status
from app.scoring.composite import compute_composite
from app.store.models import Base, EventLog, MetricSnapshot


def _store(tmp_path, monkeypatch):
    """A throwaway SQLite store behind app.store.db.session_scope."""
    eng = create_engine(f"sqlite:///{tmp_path / 'canary.db'}",
                        connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    SL = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    @contextmanager
    def scope():
        s = SL()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    monkeypatch.setattr("app.store.db.session_scope", scope)
    return SL


def _offline(monkeypatch, metrics=None):
    """No network: an empty bundle, no auctions, no rate ensemble. With
    `metrics`, compute_all returns exactly those (the live board)."""
    monkeypatch.setattr("app.sources.fred.fetch_bundle", lambda: {})
    monkeypatch.setattr("app.jobs.refresh._fetch_auctions", lambda: [])

    def no_ensemble():
        raise RuntimeError("offline")
    monkeypatch.setattr("app.sources.rate_markets.ensemble", no_ensemble)
    if metrics is not None:
        monkeypatch.setattr(
            "app.jobs.refresh.compute_all",
            lambda bundle, auctions=None: (metrics, {}, compute_composite(metrics), []))


def _m(mid, value, status, asof, category="J"):
    return MetricResult(metric_id=mid, category=category, label=mid, value=value,
                        status=status, asof=asof)


def _line(ctx, mid):
    return next(ln.strip() for ln in ctx.splitlines() if ln.strip().startswith(f"{mid}:"))


def test_gate_webhook_rejects_bad_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    with TestClient(app) as c:
        r = c.post("/telegram/webhook", json={"message": {}})
        assert r.status_code == 403
        r = c.post("/telegram/webhook", json={"message": {}},
                   headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        assert r.status_code == 403
        r = c.post("/telegram/webhook", json={"message": {}},
                   headers={"X-Telegram-Bot-Api-Secret-Token":
                            telegram_chat.webhook_secret()})
        assert r.status_code == 200


def test_gate_owner_filter(monkeypatch):
    sent = []
    monkeypatch.setattr("app.alerts.send", lambda t: sent.append(t))
    monkeypatch.setattr(telegram_chat, "_llm_reply", lambda q: f"answer:{q}")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    # stranger: silently ignored
    telegram_chat.handle_update(
        {"message": {"chat": {"id": 999}, "text": "hello"}})
    assert sent == []
    # owner: answered
    telegram_chat.handle_update(
        {"message": {"chat": {"id": 111}, "text": "why is composite 24?"}})
    assert sent == ["answer:why is composite 24?"]
    # /start gets the intro, not the LLM
    telegram_chat.handle_update(
        {"message": {"chat": {"id": 111}, "text": "/start"}})
    assert "analyst" in sent[-1]


def test_gate_no_key_degrades(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = telegram_chat._llm_reply("test")
    assert "OPENROUTER_API_KEY" in out


def test_gate_context_builds_offline(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    _offline(monkeypatch)               # the REAL compute_all on an empty bundle
    ctx = telegram_chat.build_context()
    assert isinstance(ctx, str) and len(ctx) > 0
    assert len(ctx) <= 14_000
    assert "COMPOSITE STRESS: n/a/100 band=NO_DATA" in ctx
    assert _line(ctx, "curve.3m10y").startswith("curve.3m10y: n/a STALE")


def test_gate_context_reads_the_live_board_not_a_shadowing_stale_row(tmp_path, monkeypatch):
    """2026-10-19: a failed fetch on 2026-09-17 had persisted STALE rows dated
    that day, AFTER the labor block's real rows (2026-09-01 / 2026-08-01). The
    bot read the latest row per metric and called the block stale while the
    dashboard showed the prints. It must read the board GET /metrics renders."""
    SL = _store(tmp_path, monkeypatch)
    with SL() as s:
        for asof, val, st in ((date(2026, 8, 1), 4.3, "GREEN"),
                              (date(2026, 9, 1), 4.2, "GREEN"),
                              (date(2026, 9, 17), None, "STALE")):
            s.add(MetricSnapshot(metric_id="labor.unrate", category="J",
                                 asof=asof, value=val, status=st))
        s.commit()
    _offline(monkeypatch, [_m("labor.unrate", 4.2, Status.GREEN, date(2026, 9, 1)),
                           _m("vol.move", 912.7735510823914, Status.RED,
                              date(2026, 10, 23), category="B")])
    ctx = telegram_chat.build_context()
    assert _line(ctx, "labor.unrate") == "labor.unrate: 4.2 GREEN asof=2026-09-01 n/a n/a n/a"
    assert _line(ctx, "vol.move") == "vol.move: 912.774 RED asof=2026-10-23 n/a n/a n/a"
    # the model is told that an old asof is usually release lag, and to call
    # a series lagging only when sure of its cadence (counter-agent: the
    # lines carry no frequency, so a weekly or quarterly series is easy to
    # misread as lagging)
    assert "the normal release lag, not staleness" in telegram_chat.SYSTEM_PROMPT
    assert "Call a series lagging only when you are sure" in telegram_chat.SYSTEM_PROMPT


def test_gate_context_reports_a_live_stale_metric_as_stale(tmp_path, monkeypatch):
    """Truthful both ways: a metric the board shows STALE right now is STALE in
    the snapshot, however good its last stored row was."""
    SL = _store(tmp_path, monkeypatch)
    with SL() as s:
        s.add(MetricSnapshot(metric_id="foreign.custody_26w", category="F",
                             asof=date(2026, 10, 21), value=-5.7, status="RED"))
        s.commit()
    _offline(monkeypatch, [_m("foreign.custody_26w", None, Status.STALE, None, category="F"),
                           _m("labor.unrate", 4.2, Status.GREEN, date(2026, 9, 1))])
    ctx = telegram_chat.build_context()
    assert _line(ctx, "foreign.custody_26w") == "foreign.custody_26w: n/a STALE asof=n/a n/a n/a n/a"
    assert "COMPOSITE STRESS: 0.0/100 band=LOW coverage=" in ctx


def test_gate_context_keeps_the_squeeze_state_and_recent_events(tmp_path, monkeypatch):
    """The store still supplies what only it holds: the squeeze radar's state
    at the last refresh (a STALE state there IS the current state) and the
    event log."""
    SL = _store(tmp_path, monkeypatch)
    with SL() as s:
        s.add(MetricSnapshot(metric_id="squeeze.t1", category="S",
                             asof=date(2026, 10, 25), value=None, status="NOT_MET"))
        s.add(MetricSnapshot(metric_id="squeeze.t1", category="S",
                             asof=date(2026, 10, 26), value=None, status="STALE"))
        s.add(MetricSnapshot(metric_id="squeeze.f2", category="S",
                             asof=date(2026, 10, 26), value=12.5, status="MET"))
        s.add(EventLog(event_type="metric_red:vol.move", severity="RED",
                       asof=date(2026, 10, 26), dedup_key="vol.move:2026-10-26",
                       rationale="MOVE (proxy) -> RED"))
        s.commit()
    _offline(monkeypatch, [])
    ctx = telegram_chat.build_context()
    assert _line(ctx, "squeeze.t1") == "squeeze.t1: n/a STALE asof=2026-10-26"
    assert _line(ctx, "squeeze.f2") == "squeeze.f2: 12.5 MET asof=2026-10-26"
    assert "[RED] 2026-10-26 metric_red:vol.move: MOVE (proxy) -> RED" in ctx
