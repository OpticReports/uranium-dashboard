"""Shared test fixtures: an isolated in-memory SQLite DB per test, and the
call engine's TUNING KNOBS pinned to a test-owned set (see below)."""
from __future__ import annotations

import copy

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def session():
    # Import models so metadata is populated.
    from app import models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- the tuning knobs in calls.yaml are a TUNING surface, not test invariants ----
#
# TUNING.md lets an evidence-gated proposal change the call-trigger list, the
# exit parameters (stop multiple, reward:risk, time-stop) and the conviction
# gate in config/calls.yaml, and forbids editing tests. Until 2026-10-04 the
# engine tests read that live file: every test fired
# `pre_catalyst_sentiment_ramp` as its example trigger and hard-coded levels
# derived from 3xATR / 3:1 (stop 94, target 118 on a 100 close with ATR 2).
# The first gated demotion of that trigger therefore broke 17 tests that
# assert engine MECHANICS (sizing, cooldown, exits, shadow grading, blend
# intents) - and would have let the five liquidity/binary invariant tests
# pass VACUOUSLY (no trigger, no call, nothing to assert against). An
# exit-parameter proposal (stop 2.5x or RR 2:1) breaks five more the same way.
#
# So the mechanics tests run against trigger / risk / horizon sets the tests
# OWN, pinned below. What the suite then no longer proves about the LIVE file
# - that its triggers are real flag types, long-side only, that Tier C never
# auto-calls, that risk/horizon are sane - is asserted directly on the YAML
# in tests/test_calls_config.py, which bypasses this pin on purpose.
TEST_CALL_TRIGGERS = {
    "pre_catalyst_sentiment_ramp": {},
    "analyst_revision_cluster": {"direction": "upward"},
    "unusual_options_social_spike": {},
}
TEST_CALL_RISK = {
    "atr_window": 14,
    "stop_atr_mult": 3.0,
    "fallback_stop_pct": 0.08,
    "reward_risk": 3.0,
}
TEST_CALL_HORIZON = {"default_days": 45, "min_days": 5, "max_days": 45}
PINNED_KEYS = {"triggers": TEST_CALL_TRIGGERS, "risk": TEST_CALL_RISK, "horizon": TEST_CALL_HORIZON}

# Every module that binds `calls_config` at import time and feeds the engine,
# its grading, or its routes. app.routers.tuning is deliberately ABSENT: the
# tuning evidence bundle must echo the LIVE trigger list the tuner acts on,
# so never assert engine behaviour against that echo.
_ENGINE_READERS = (
    "app.calls.manager",
    "app.calls.shadow",
    "app.calls.paper",
    "app.calls.confidence",
    "app.routers.calls",
    "app.routers.today",
)


@pytest.fixture(autouse=True)
def pinned_call_tuning(monkeypatch):
    """Pin triggers / risk / horizon for the engine and its readers.

    Patches app.config.calls_config itself (so lazy `from ..config import
    calls_config` inside a function, as app.routers.blend does, is covered)
    plus the import-time bindings in _ENGINE_READERS. Everything else in
    calls.yaml - min_composite, liquidity, cooldown, cap, paper, confidence -
    stays live. A missing calls.yaml still yields {} so the engine goes quiet
    and the mechanics tests fail loudly rather than run on injected knobs."""
    import importlib

    from app import config as app_config

    live = app_config.calls_config          # the unpatched function

    def _pinned() -> dict:
        cfg = copy.deepcopy(live())
        if not cfg:
            return cfg
        for key, value in PINNED_KEYS.items():
            cfg[key] = copy.deepcopy(value)
        return cfg

    monkeypatch.setattr(app_config, "calls_config", _pinned)
    for mod_name in _ENGINE_READERS:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "calls_config"):
            monkeypatch.setattr(mod, "calls_config", _pinned)
