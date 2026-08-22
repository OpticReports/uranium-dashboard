"""Gate tests for the keyless executor watchdog (app/watchdog.py).

Merge-blocking. The watchdog exists to page when the executor goes quiet or
stops mirroring, so the properties that matter are: it pages when it should,
it stays quiet when it shouldn't page, it never storms, it never places an
order, and it can never take the engine down with it.
"""
from __future__ import annotations

import time
import types

import pytest

from app import watchdog as wd_mod
from app.watchdog import Watchdog


class Cfg:
    watchdog_enabled = True
    watchdog_pulse_url = "http://executor.test/pulse"
    watchdog_period_s = 300
    watchdog_silence_s = 900
    watchdog_target_age_s = 900
    watchdog_divergence_s = 1800
    watchdog_cooldown_s = 3600


HEALTHY = {"ready": True, "dry_run": False, "halted": None,
           "red_events_24h": 0, "last_target_age_s": 10.0,
           "legs": {"pullback": {"in_position": False},
                    "trend": {"in_position": True}}}

BOOKS = {"S3": {"position": None}, "S4": {"position": {"side": "L"}}}


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(wd_mod, "_send", lambda m: out.append(m))
    return out


def mkwd(cfg=None, books=None):
    return Watchdog(cfg or Cfg(), lambda: books if books is not None else BOOKS)


def feed(wd, monkeypatch, pulse=None, exc=None):
    """Point the watchdog's HTTP call at a canned pulse (or an error)."""
    def _get(url, timeout=10):
        if exc is not None:
            raise exc
        return types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: pulse)
    monkeypatch.setattr(wd_mod.httpx, "get", _get)


# --- quiet when healthy ----------------------------------------------------
def test_gate_healthy_pulse_pages_nothing(sent, monkeypatch):
    wd = mkwd()
    feed(wd, monkeypatch, HEALTHY)
    wd.check()
    assert sent == [], sent


# --- dead-man's switch: the failure nothing else could report --------------
def test_gate_unreachable_executor_pages_after_silence(sent, monkeypatch):
    """The whole reason this module exists: a dead executor pages nobody,
    because every other alert path runs inside it."""
    wd = mkwd()
    feed(wd, monkeypatch, exc=RuntimeError("connection refused"))
    wd.started = time.monotonic() - 100          # inside grace
    wd.check()
    assert sent == [], "must not page on a blip inside the silence window"
    wd.started = time.monotonic() - 1000         # past watchdog_silence_s
    wd.check()
    assert any("executor_silent" in m for m in sent), sent
    assert "ACTION NEEDED" in sent[0]


def test_gate_silence_clears_and_says_so(sent, monkeypatch):
    wd = mkwd()
    feed(wd, monkeypatch, exc=RuntimeError("down"))
    wd.started = time.monotonic() - 1000
    wd.check()
    sent.clear()
    feed(wd, monkeypatch, HEALTHY)
    wd.check()
    assert any("RECOVERED" in m and "executor_silent" in m for m in sent), sent


def test_gate_non_dict_pulse_counts_as_silence(sent, monkeypatch):
    """A 200 carrying garbage is not a healthy executor."""
    wd = mkwd()
    feed(wd, monkeypatch, ["not", "a", "pulse"])
    wd.started = time.monotonic() - 1000
    wd.check()
    assert any("executor_silent" in m for m in sent), sent


# --- pulse-reported trouble ------------------------------------------------
def test_gate_halt_and_stale_and_reds_page(sent, monkeypatch):
    wd = mkwd()
    feed(wd, monkeypatch, {**HEALTHY, "halted": "DRAWDOWN",
                           "last_target_age_s": 5000, "red_events_24h": 3,
                           "ready": False})
    wd.check()
    keys = " ".join(sent)
    for k in ("halted", "stale_feed", "red_events", "not_ready"):
        assert k in keys, (k, sent)


def test_gate_conditions_clear_individually(sent, monkeypatch):
    wd = mkwd()
    feed(wd, monkeypatch, {**HEALTHY, "halted": "DRAWDOWN"})
    wd.check()
    sent.clear()
    feed(wd, monkeypatch, HEALTHY)
    wd.check()
    assert any("halted RECOVERED" in m for m in sent), sent


# --- no alert storms -------------------------------------------------------
def test_gate_open_condition_does_not_storm(sent, monkeypatch):
    """2026-08-17 produced 35 identical RED pages in ~12 minutes. An open
    condition re-pages on the cooldown, not on every poll."""
    wd = mkwd()
    feed(wd, monkeypatch, {**HEALTHY, "halted": "DRAWDOWN"})
    for _ in range(20):
        wd.check()
    assert len([m for m in sent if "halted" in m]) == 1, sent


# --- coherence: the check neither service can make alone -------------------
def test_gate_divergence_needs_to_persist(sent, monkeypatch):
    """The executor confirms a position only after the engine closes the
    bar, so a fresh disagreement is a legitimate handoff, not a bug."""
    diverged = {**HEALTHY,
                "legs": {"pullback": {"in_position": True},
                         "trend": {"in_position": True}}}
    wd = mkwd()
    feed(wd, monkeypatch, diverged)          # engine S3 flat, executor in pos
    wd.check()
    assert sent == [], "must tolerate the bar-close handoff window"
    wd.since["divergence_pullback"] = time.monotonic() - 3600   # persisted
    wd.check()
    assert any("divergence_pullback" in m for m in sent), sent
    assert "S3" in sent[0]


def test_gate_divergence_clears_when_they_agree_again(sent, monkeypatch):
    diverged = {**HEALTHY,
                "legs": {"pullback": {"in_position": True},
                         "trend": {"in_position": True}}}
    wd = mkwd()
    feed(wd, monkeypatch, diverged)
    wd.since["divergence_pullback"] = time.monotonic() - 3600
    wd.check()
    sent.clear()
    feed(wd, monkeypatch, HEALTHY)
    wd.check()
    assert any("divergence_pullback RECOVERED" in m for m in sent), sent
    assert "divergence_pullback" not in wd.since, "stale timer must reset"


def test_gate_both_legs_checked_independently(sent, monkeypatch):
    wd = mkwd(books={"S3": {"position": {"side": "S"}}, "S4": {"position": None}})
    feed(wd, monkeypatch, HEALTHY)           # exactly inverted vs the books
    wd.since["divergence_pullback"] = time.monotonic() - 3600
    wd.since["divergence_trend"] = time.monotonic() - 3600
    wd.check()
    assert any("divergence_pullback" in m for m in sent), sent
    assert any("divergence_trend" in m for m in sent), sent


def test_gate_own_book_failure_never_pages(sent, monkeypatch):
    """If OUR book read throws, that is the engine's fault, not the
    executor's — blaming the executor for it would be a false alarm."""
    def _boom():
        raise RuntimeError("db down")
    wd = Watchdog(Cfg(), _boom)
    feed(wd, monkeypatch, HEALTHY)
    wd.check()
    assert not any("divergence" in m for m in sent), sent


def test_gate_missing_book_or_leg_is_not_a_divergence(sent, monkeypatch):
    wd = mkwd(books={})                      # engine has no books yet (boot)
    feed(wd, monkeypatch, HEALTHY)
    wd.since["divergence_pullback"] = time.monotonic() - 3600
    wd.check()
    assert not any("divergence" in m for m in sent), sent


# --- it must never be able to hurt the engine or the venue -----------------
def test_gate_watchdog_is_read_only():
    """Separation of powers: the engine is keyless. The watchdog may read
    and page; it must hold no credential and no order path.

    Scans identifiers via the AST rather than raw text, so prose about what
    the module must never do can't satisfy — or trip — the gate.
    """
    import ast
    tree = ast.parse(open(wd_mod.__file__).read())
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
    for forbidden in ("place", "cancel", "order", "venue", "api_key",
                      "exec_token", "private_key", "secret"):
        assert forbidden not in blob, \
            f"watchdog code must not reference {forbidden}: {sorted(names)}"
    # and the only env it may read is the alerting pair
    env_reads = set()
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get"):
            continue
        base = n.func.value
        if isinstance(base, ast.Attribute) and base.attr == "environ" and n.args:
            arg = n.args[0]
            env_reads.add(arg.value if isinstance(arg, ast.Constant) else "?")
    assert env_reads <= {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}, \
        f"watchdog may only read alerting env: {env_reads}"


def test_gate_disabled_by_default():
    from app.config import Settings
    s = Settings()
    assert s.watchdog_enabled is False, "a pager must be opted into"
    assert wd_mod.start_watchdog(s, lambda: {}) is None


def test_gate_missing_url_does_not_start():
    cfg = Cfg()
    cfg.watchdog_pulse_url = ""
    assert wd_mod.start_watchdog(cfg, lambda: {}) is None


def test_gate_enabled_config_actually_arms(monkeypatch):
    """The disabled paths are the easy ones to get right. A pager that
    silently fails to arm is the failure this whole module exists to
    prevent, so pin the positive case too."""
    cfg = Cfg()
    cfg.watchdog_period_s = 3600             # one pass, then sleeps
    monkeypatch.setattr(wd_mod.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("no executor in tests")))
    wd = wd_mod.start_watchdog(cfg, lambda: BOOKS)
    assert isinstance(wd, Watchdog)
    for _ in range(50):                      # let the thread take its pass
        if wd.last_ok is not None or wd.started:
            break
        time.sleep(0.01)
    assert wd.cfg is cfg


def test_gate_loop_survives_a_failing_pass(monkeypatch, sent):
    """A watchdog exception must never escape into the engine process."""
    wd = mkwd()
    def _boom(*a, **k):
        raise RuntimeError("transport exploded")
    monkeypatch.setattr(wd_mod.httpx, "get", _boom)
    wd.check()                               # must not raise
    wd.started = time.monotonic() - 1000
    wd.check()
    assert any("executor_silent" in m for m in sent), sent


def test_gate_send_is_noop_without_env(monkeypatch):
    """Unset Telegram env must be silent, not an exception in the loop."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    wd_mod._send("anything")                 # must not raise
