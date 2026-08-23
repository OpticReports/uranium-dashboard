"""Gate tests for the read-only Telegram triage bot (app/triage_chat.py).

Merge-blocking. Triage is a convenience that sits next to a live-money
system, so the properties that matter are mostly about what it CANNOT do:
it cannot trade, it cannot be driven by a stranger, it cannot steal the
alert bot's webhook, and it cannot make alerting depend on a model.
"""
from __future__ import annotations

import ast
import time
import json
import types

import pytest

from app import triage_chat as tc


BOOKS = {"S3": {"state": "FLAT", "equity": 154678.09, "trades": 88,
                "position": None},
         "S4": {"state": "L", "equity": 98640.19, "trades": 60,
                "position": {"side": "L", "entry_price": 64139.89,
                             "qty": 1.5, "stop_price": 62000.0}}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("TRIAGE_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "OPENROUTER_API_KEY", "TRIAGE_CHAT_MODEL", "RENDER_EXTERNAL_URL"):
        monkeypatch.delenv(k, raising=False)
    tc._HISTORY.clear()


def _owner_env(monkeypatch, triage_tok="triage-tok", alert_tok="alert-tok"):
    monkeypatch.setenv("TRIAGE_BOT_TOKEN", triage_tok)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", alert_tok)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99")


def _update(text, chat_id="99"):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


# --- it must never become part of the alert path ---------------------------
def test_gate_triage_has_no_order_or_control_surface():
    """The engine is keyless and triage is read-only: no venue, no order, no
    halt/resume, no token. Scanned via AST so prose can't satisfy the gate."""
    tree = ast.parse(open(tc.__file__).read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.add(getattr(node, "module", "") or "")
            names.update(a.name for a in node.names)
    blob = " ".join(n.lower() for n in names if n)
    for forbidden in ("place", "cancel", "venue", "kill", "resume",
                      "exec_token", "private_key", "reset_books"):
        assert forbidden not in blob, f"triage must not reference {forbidden}"


def test_gate_disabled_without_its_own_bot(monkeypatch):
    assert tc.enabled() is False
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99")
    assert tc.enabled() is False, "no triage bot token -> stays off"


def test_gate_refuses_to_share_the_alert_bot(monkeypatch):
    """Telegram allows ONE webhook per bot. Registering triage on the alert
    bot's token would silently steal the webhook from whichever service owns
    it — so the same token must disable triage, loudly."""
    _owner_env(monkeypatch, triage_tok="same", alert_tok="same")
    assert tc.enabled() is False
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://engine.test")
    assert tc.register_webhook() is False


def test_gate_webhook_secret_is_service_scoped(monkeypatch):
    """Two services deriving a secret from the same token must not produce
    the same value, or either could validate the other's updates."""
    _owner_env(monkeypatch)
    engine_secret = tc.webhook_secret()
    import hashlib
    canary_style = hashlib.sha256(
        b"canary-webhook:triage-tok").hexdigest()[:40]
    assert engine_secret != canary_style
    assert len(engine_secret) == 40


# --- only the owner may drive it -------------------------------------------
def test_gate_non_owner_is_ignored(monkeypatch):
    _owner_env(monkeypatch)
    sent = []
    monkeypatch.setattr(tc, "_reply", lambda m: sent.append(m))
    monkeypatch.setattr(tc, "_llm_reply", lambda q, c: "should never run")
    tc.handle_update(_update("what's the state?", chat_id="1234"),
                     lambda: BOOKS, "http://x/pulse", None)
    assert sent == [], "stranger traffic must be dropped silently"


def test_gate_owner_gets_a_grounded_reply(monkeypatch):
    _owner_env(monkeypatch)
    sent, seen = [], {}
    monkeypatch.setattr(tc, "_reply", lambda m: sent.append(m))
    monkeypatch.setattr(tc, "_llm_reply",
                        lambda q, c: seen.update(q=q, c=c) or "answer")
    monkeypatch.setattr(tc.httpx, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"halted": None}))
    tc.handle_update(_update("is S4 long?"), lambda: BOOKS, "http://x/pulse")
    assert sent == ["answer"]
    assert "S4" in seen["c"] and "EXECUTOR PULSE" in seen["c"]


def test_gate_help_does_not_call_the_model(monkeypatch):
    _owner_env(monkeypatch)
    sent = []
    monkeypatch.setattr(tc, "_reply", lambda m: sent.append(m))
    monkeypatch.setattr(tc, "_llm_reply", lambda q, c: pytest.fail("no LLM"))
    tc.handle_update(_update("/help"), lambda: BOOKS, "http://x/pulse")
    assert sent and "cannot trade" in sent[0]


# --- snapshot degrades, never explodes -------------------------------------
def test_gate_context_survives_dead_executor(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(tc.httpx, "get", _boom)
    ctx = tc.build_context(lambda: BOOKS, "http://x/pulse", None)
    assert "executor pulse unreachable" in ctx
    assert "S4" in ctx, "a dead executor must not sink the whole snapshot"
    assert "venue stops still protect" in ctx


def test_gate_context_survives_dead_books(monkeypatch):
    monkeypatch.setattr(tc.httpx, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"ready": True}))
    def _boom():
        raise RuntimeError("db gone")
    ctx = tc.build_context(_boom, "http://x/pulse", None)
    assert "engine books unavailable" in ctx
    assert "EXECUTOR PULSE" in ctx


def test_gate_context_includes_watchdog_conditions(monkeypatch):
    monkeypatch.setattr(tc.httpx, "get", lambda *a, **k: types.SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {}))
    wd = types.SimpleNamespace(open={"executor_silent": 1.0})
    ctx = tc.build_context(lambda: BOOKS, "http://x/pulse", wd)
    assert "executor_silent" in ctx


# --- unfunded/misconfigured backend must say so, not fail silently ---------
def test_gate_missing_key_explains_and_reassures(monkeypatch):
    _owner_env(monkeypatch)
    out = tc._llm_reply("anything", "ctx")
    assert "OPENROUTER_API_KEY" in out
    assert "watchdog pages without any model" in out


def test_gate_missing_model_is_explicit(monkeypatch):
    _owner_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    out = tc._llm_reply("anything", "ctx")
    assert "TRIAGE_CHAT_MODEL" in out


def test_gate_backend_error_says_alerting_is_unaffected(monkeypatch):
    _owner_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("TRIAGE_CHAT_MODEL", "some/model")
    def _boom(*a, **k):
        raise RuntimeError("router down")
    monkeypatch.setattr(tc.httpx, "post", _boom)
    out = tc._llm_reply("anything", "ctx")
    assert "triage backend error" in out
    assert "Alerting is unaffected" in out


def test_gate_no_model_id_hardcoded_in_source():
    """Model choice is configuration, not code: a slug baked into the module
    would drift from what Render actually runs."""
    src = open(tc.__file__).read()
    assert "TRIAGE_CHAT_MODEL" in src
    assert "/" not in src.split("TRIAGE_CHAT_MODEL")[1][:40], \
        "no model slug default in code — set it in render.yaml"


# --- webhook endpoint ------------------------------------------------------
def test_gate_webhook_rejects_bad_secret(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("RUN_ENGINE", "false")
    _owner_env(monkeypatch)
    called = []
    monkeypatch.setattr(tc, "handle_update",
                        lambda *a, **k: called.append(1))
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/triage/webhook", json=_update("hi"),
                   headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        r = c.post("/triage/webhook", json=_update("hi"))   # no header at all
        assert r.status_code == 200
    assert called == [], "a bad secret must never reach the handler"


def test_gate_webhook_accepts_the_real_secret(monkeypatch):
    """The rejection path is the easy half. A webhook that drops EVERYTHING
    would pass the test above and be silently useless."""
    from fastapi.testclient import TestClient
    monkeypatch.setenv("RUN_ENGINE", "false")
    _owner_env(monkeypatch)
    called = []
    monkeypatch.setattr(tc, "handle_update", lambda *a, **k: called.append(a))
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/triage/webhook", json=_update("hi"),
                   headers={"X-Telegram-Bot-Api-Secret-Token":
                            tc.webhook_secret()})
        assert r.status_code == 200
    for _ in range(200):                     # handler runs off-thread
        if called:
            break
        time.sleep(0.01)
    assert called, "a correctly-signed update must reach the handler"


def test_gate_webhook_is_inert_when_triage_disabled(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("RUN_ENGINE", "false")
    called = []
    monkeypatch.setattr(tc, "handle_update", lambda *a, **k: called.append(a))
    from app.main import app
    with TestClient(app) as c:                # no TRIAGE_BOT_TOKEN at all
        r = c.post("/triage/webhook", json=_update("hi"),
                   headers={"X-Telegram-Bot-Api-Secret-Token": "anything"})
        assert r.status_code == 200
    assert called == []
