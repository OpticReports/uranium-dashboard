"""Telegram analyst gates: webhook auth, owner filter, degradation. Offline —
the LLM and Telegram sends are monkeypatched."""
from fastapi.testclient import TestClient

from app import telegram_chat
from app.main import app


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


def test_gate_context_builds_offline():
    ctx = telegram_chat.build_context()
    assert isinstance(ctx, str) and len(ctx) > 0
    assert len(ctx) <= 14_000
