"""Shared test fixtures: an isolated in-memory SQLite DB per test."""
from __future__ import annotations

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


# --- the call-trigger list is a TUNING surface, not a test invariant -------------
#
# Every test that exercises the call engine fires `pre_catalyst_sentiment_ramp`
# as its example trigger. Until 2026-10-04 those tests read the live
# config/calls.yaml, so the first evidence-gated demotion of that trigger
# (TUNING.md) broke 17 tests that were asserting engine MECHANICS (sizing,
# cooldown, exits, shadow grading, blend intents), not the trigger list - and
# would have let liquidity/binary invariants pass VACUOUSLY (no trigger, no
# call, nothing to assert against). The engine's behaviour must be tested
# against a trigger set the tests own. Everything else in calls.yaml (risk,
# horizon, liquidity, cooldown, cap) is still read live, so a change there is
# still caught here.
TEST_CALL_TRIGGERS = {
    "pre_catalyst_sentiment_ramp": {},
    "analyst_revision_cluster": {"direction": "upward"},
    "unusual_options_social_spike": {},
}


@pytest.fixture(autouse=True)
def pinned_call_triggers(monkeypatch):
    """Pin the trigger list the call engine sees to TEST_CALL_TRIGGERS.

    Only `app.calls.manager.calls_config` is patched: it is the single reader
    of `triggers`. Direct readers of the YAML (the tuning evidence bundle, the
    config well-formedness tests) still see the live file."""
    from app import config as app_config
    from app.calls import manager

    def _pinned() -> dict:
        cfg = dict(app_config.calls_config())
        cfg["triggers"] = dict(TEST_CALL_TRIGGERS)
        return cfg

    monkeypatch.setattr(manager, "calls_config", _pinned)
