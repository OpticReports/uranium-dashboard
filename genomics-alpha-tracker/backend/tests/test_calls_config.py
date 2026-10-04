"""Guards on the LIVE config/calls.yaml - the half of the invariants that
tests/conftest.py's pin deliberately stops the engine tests from proving.

TUNING.md lets a gated proposal edit calls.yaml and forbids editing tests, so
these assert SHAPE and the rules that must survive any tune - never which
flags happen to be triggers today (promotion and demotion must stay legal,
down to an empty trigger list, which simply leaves the engine quiet). They
read the YAML through app.config.load_yaml_config, which the pin does not
touch.
"""
from __future__ import annotations

import pytest

from app.config import flags_config, load_yaml_config
from tests.conftest import PINNED_KEYS

# Flags that are bearish by construction. The engine is long-only
# (manager.generate_calls hard-codes direction="long"), so these may be
# observed and graded but must never generate a long call.
NEVER_LONG_TRIGGERS = {"runway_cliff_approaching"}
# Only these flags write evidence["direction"] (app/scoring/flags.py), so a
# direction condition on any other flag can never match: a dead trigger.
DIRECTIONAL_FLAGS = {"analyst_revision_cluster"}
ALLOWED_CONDITION_KEYS = {"direction"}
ALLOWED_DIRECTIONS = {"upward"}          # long-only engine; a short book would widen this


def live_calls() -> dict:
    cfg = load_yaml_config("calls.yaml").get("calls", {})
    assert cfg, "config/calls.yaml has no `calls:` root"
    return cfg


def test_live_trigger_list_is_a_well_formed_mapping():
    """A list, a null, or a bare key here makes generate_calls crash or go
    silent in production while the pinned engine tests stay green. An EMPTY
    mapping is legal: it is what demoting the last trigger writes."""
    triggers = live_calls().get("triggers")
    assert isinstance(triggers, dict), "calls.triggers must be a mapping flag_type -> {conditions}"
    known = set(flags_config())
    for flag_type, cond in triggers.items():
        assert flag_type in known, f"{flag_type!r} is not a flag the engine emits: dead config"
        assert isinstance(cond, dict), f"{flag_type}: conditions must be a mapping (a bare key is YAML null)"
        assert set(cond) <= ALLOWED_CONDITION_KEYS, f"{flag_type}: unknown condition {set(cond) - ALLOWED_CONDITION_KEYS}"
        if "direction" in cond:
            assert flag_type in DIRECTIONAL_FLAGS, f"{flag_type} never carries a direction: this trigger can never fire"
            assert cond["direction"] in ALLOWED_DIRECTIONS, f"{flag_type}: direction {cond['direction']!r}"


def test_live_triggers_are_long_side_only():
    triggers = live_calls()["triggers"]
    assert not (set(triggers) & NEVER_LONG_TRIGGERS), "a bearish flag is configured as a long trigger"
    if "analyst_revision_cluster" in triggers:
        assert triggers["analyst_revision_cluster"].get("direction") == "upward", (
            "analyst_revision_cluster must carry direction: upward - downward clusters never generate a long call"
        )


def test_live_risk_and_horizon_are_sane():
    """The time-stop gate's single `horizon_days` maps to BOTH default_days
    and max_days (the engine clips the default at the max), so a tune of one
    without the other is a no-op and is rejected here."""
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
    """The test-owned knob blocks must keep the same keys as the live file,
    so a key added to calls.yaml is not silently missing from every engine
    test. (Adding a key is an engineering change, not a tuning lane.)"""
    cfg = live_calls()
    for key, pinned in PINNED_KEYS.items():
        if key == "triggers" or not isinstance(pinned, dict):
            continue
        assert set(pinned) == set(cfg[key]), f"calls.{key}: pinned keys {set(pinned)} vs live {set(cfg[key])}"


def test_tuning_evidence_echoes_the_live_file_not_the_pin():
    """The tuner acts on GET /tuning/evidence; it must see reality even when
    this suite's pin differs from the file (true whenever a tune has moved
    a pinned knob). Imported here, after the pin, to prove the binding is
    independent of import order."""
    from app.routers import tuning

    live = live_calls()
    echoed = tuning.calls_config()
    for key in PINNED_KEYS:
        assert echoed[key] == live[key], f"/tuning/evidence would echo the pinned {key}, not the file"


def test_engine_is_quiet_with_no_triggers(session, monkeypatch):
    """The one engine branch the pin makes unreachable: no triggers -> no calls.
    Non-vacuous: the same seeded flag DOES produce a call under the pin."""
    from app.calls import manager
    from tests.test_calls import _fire_flag, _seed_name

    _seed_name(session)
    _fire_flag(session)
    pinned = manager.calls_config
    monkeypatch.setattr(manager, "calls_config", lambda: {**pinned(), "triggers": {}})
    assert manager.generate_calls(session) == []
    monkeypatch.setattr(manager, "calls_config", pinned)
    assert len(manager.generate_calls(session)) == 1


@pytest.mark.parametrize("key", sorted(PINNED_KEYS))
def test_engine_sees_the_pinned_knobs_not_the_file(key):
    """Proves the pin is active for the engine's own binding."""
    from app.calls import manager

    assert manager.calls_config()[key] == PINNED_KEYS[key]
