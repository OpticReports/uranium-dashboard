"""Guards on the LIVE config/calls.yaml - the half of the invariants that
tests/conftest.py's pin deliberately stops the engine tests from proving.

TUNING.md lets a gated proposal edit calls.yaml and forbids editing tests, so
these assert SHAPE and the rules that must survive any tune - never which
flags happen to be triggers today (promotion and demotion must stay legal).
They read the YAML through app.config.load_yaml_config, which the pin does
not touch.
"""
from __future__ import annotations

import pytest

from app.config import flags_config, load_yaml_config
from tests.conftest import PINNED_KEYS

# Flags that are bearish by construction. The engine is long-only
# (manager.generate_calls hard-codes direction="long"), so these may be
# observed and graded but must never generate a long call.
NEVER_LONG_TRIGGERS = {"runway_cliff_approaching"}
ALLOWED_CONDITION_KEYS = {"direction"}
ALLOWED_DIRECTIONS = {"upward"}          # long-only engine; a short book would widen this


def live_calls() -> dict:
    cfg = load_yaml_config("calls.yaml").get("calls", {})
    assert cfg, "config/calls.yaml has no `calls:` root"
    return cfg


def test_live_trigger_list_is_a_well_formed_mapping():
    """A list, a null, or a bare key here makes generate_calls crash or go
    silent in production while the pinned engine tests stay green."""
    cfg = live_calls()
    triggers = cfg.get("triggers")
    assert isinstance(triggers, dict), "calls.triggers must be a mapping flag_type -> {conditions}"
    if cfg.get("enabled", True):
        assert triggers, "no call triggers configured while calls are enabled: say `enabled: false` instead"
    known = set(flags_config())
    for flag_type, cond in triggers.items():
        assert flag_type in known, f"{flag_type!r} is not a flag the engine emits: dead config"
        assert isinstance(cond, dict), f"{flag_type}: conditions must be a mapping (a bare key is YAML null)"
        assert set(cond) <= ALLOWED_CONDITION_KEYS, f"{flag_type}: unknown condition {set(cond) - ALLOWED_CONDITION_KEYS}"
        if "direction" in cond:
            assert cond["direction"] in ALLOWED_DIRECTIONS, f"{flag_type}: direction {cond['direction']!r}"


def test_live_triggers_are_long_side_only():
    triggers = live_calls()["triggers"]
    assert not (set(triggers) & NEVER_LONG_TRIGGERS), "a bearish flag is configured as a long trigger"
    if "analyst_revision_cluster" in triggers:
        assert triggers["analyst_revision_cluster"].get("direction") == "upward", (
            "analyst_revision_cluster must carry direction: upward - downward clusters never generate a long call"
        )


def test_live_risk_and_horizon_are_sane():
    cfg = live_calls()
    risk, horizon = cfg["risk"], cfg["horizon"]
    assert int(risk["atr_window"]) >= 5
    assert 0 < float(risk["stop_atr_mult"]) <= 10
    assert 0 < float(risk["fallback_stop_pct"]) < 0.5
    assert float(risk["reward_risk"]) >= 1.0
    assert 0 < int(horizon["min_days"]) <= int(horizon["default_days"]) <= int(horizon["max_days"])


def test_live_gates_that_back_invariants():
    cfg = live_calls()
    assert cfg["liquidity"]["exclude_tier_c_from_auto_calls"] is True, "Tier C never auto-calls"
    assert 0 <= float(cfg["min_composite"]) <= 100
    assert int(cfg["cooldown_days"]) >= 0
    assert int(cfg["max_open_calls"]) >= 1


def test_pinned_sets_have_the_live_shape():
    """The test-owned knobs must keep the same keys as the live file, so a
    key added to calls.yaml is not silently missing from every engine test."""
    cfg = live_calls()
    for key, pinned in PINNED_KEYS.items():
        if key == "triggers":
            continue
        assert set(pinned) == set(cfg[key]), f"calls.{key}: pinned keys {set(pinned)} vs live {set(cfg[key])}"


def test_engine_is_quiet_with_no_triggers(session, monkeypatch):
    """The one engine branch the pin makes unreachable: no triggers -> no calls."""
    from app.calls import manager
    from app.config import calls_config          # already the pinned function here

    base = calls_config()
    monkeypatch.setattr(manager, "calls_config", lambda: {**base, "triggers": {}})
    assert manager.generate_calls(session) == []


@pytest.mark.parametrize("key", ["triggers", "risk", "horizon"])
def test_engine_sees_the_pinned_knobs_not_the_file(key):
    """Proves the pin is active for the engine's own binding."""
    from app.calls import manager

    assert manager.calls_config()[key] == PINNED_KEYS[key]
