"""Gate tests. These are the only tests in this service that matter: the
agent's usefulness degrades gracefully, its containment does not.
"""
from __future__ import annotations

import pytest

from app.guard import (BRANCH_PREFIX, Refused, assert_environment_isolated,
                       assert_paths_allowed, assert_pushable,
                       assert_tests_passed, branch_for, scan_diff_for_secrets)


# --------------------------------------------------------------- branches
@pytest.mark.parametrize("branch", ["main", "master", "HEAD", "Main", "MAIN"])
def test_gate_never_pushes_to_a_deploying_branch(branch):
    """main auto-deploys into a live book holding ~$50k. Casing included:
    git is case-sensitive but operators are not, and a refusal that misses
    'Main' is a refusal that misses."""
    with pytest.raises(Refused, match="live trading book"):
        assert_pushable(branch)


@pytest.mark.parametrize("branch", ["fix-the-thing", "feature/x", "hotfix",
                                    "agent", "agents/x", ""])
def test_gate_refuses_anything_outside_the_agent_prefix(branch):
    with pytest.raises(Refused):
        assert_pushable(branch)


def test_gate_allows_a_properly_prefixed_branch():
    assert_pushable(f"{BRANCH_PREFIX}fix-stop-rounding-a1b2c3d4")


@pytest.mark.parametrize("branch", ["agent/../main", "agent/a b", "-agent/x"])
def test_gate_refuses_branch_names_that_could_escape(branch):
    with pytest.raises(Refused):
        assert_pushable(branch)


def test_gate_branch_names_are_derived_not_model_chosen():
    """A model-supplied branch name is one more string an injected
    instruction can control; the prefix has to be un-talk-out-of-able."""
    b = branch_for("Fix the stop rounding on Hyperliquid")
    assert b.startswith(BRANCH_PREFIX)
    assert branch_for("x") != branch_for("y")
    assert branch_for("x") == branch_for("x"), "not deterministic"
    assert_pushable(b)


def test_gate_branch_name_survives_a_hostile_task_string():
    for task in ("../../main", "main", "  ", "!!!", "a" * 500):
        assert_pushable(branch_for(task))


# ------------------------------------------------------------------ paths
@pytest.mark.parametrize("path", [
    "render.yaml",                       # could grant itself trading keys
    "code-agent/app/guard.py",           # could delete these gates
    "code-agent/tests/test_guard.py",
    ".github/workflows/ci.yml",          # CI runs with its own credentials
    "btc-executor/.env",
    ".env",
    "CLAUDE.md", "AGENTS.md", ".cursorrules",
])
def test_gate_refuses_privilege_widening_paths(path):
    with pytest.raises(Refused):
        assert_paths_allowed([path])


@pytest.mark.parametrize("path", [
    "btc-executor/app/hl.py", "btc-executor/tests/test_hl_venue.py",
    "btc-paper-engine/backend/app/live.py", "barbell-lab/src/barbell/edge/db.py",
    "btc-executor/EXECUTOR.md",
])
def test_gate_allows_ordinary_work(path):
    """Containment that blocks the actual job gets switched off."""
    assert_paths_allowed([path])


def test_gate_path_check_is_not_fooled_by_prefixes():
    assert_paths_allowed(["render.yaml.example", "code-agentx/foo.py"])
    with pytest.raises(Refused):
        assert_paths_allowed(["./render.yaml"])


def test_gate_names_every_offending_path_not_just_the_first():
    with pytest.raises(Refused) as e:
        assert_paths_allowed(["render.yaml", "btc-executor/app/hl.py", ".env"])
    assert "render.yaml" in str(e.value) and ".env" in str(e.value)


# ---------------------------------------------------------------- secrets
@pytest.mark.parametrize("secret", [
    "+HL_SECRET_KEY = 0x" + "ab" * 32,
    "+-----BEGIN EC PRIVATE KEY-----",
    "+key = 'sk-or-v1-0123456789abcdef0123456789abcdef'",
    "+TOKEN = \"1234567890:AAHfSHFyeuiwyriuwe-YRIUEYRIUwEYRIUYRIx\"",
    "+aws = AKIAIOSFODNN7EXAMPLE",
    "+t = ghp_0123456789abcdefghijklmnopqrstuvwxyz",
    "+password = 'hunter2hunter2hunter2'",
])
def test_gate_refuses_a_diff_that_adds_a_credential(secret):
    with pytest.raises(Refused, match="refusing to commit"):
        scan_diff_for_secrets(f"--- a/x\n+++ b/x\n{secret}\n")


def test_gate_ignores_credentials_on_context_and_removed_lines():
    """Only ADDED lines. This repo's own docs quote key shapes - EXECUTOR.md
    discusses agent-wallet keys at length - and refusing to edit a file
    because an untouched neighbouring line looks like a key would make the
    agent useless precisely where the money is."""
    diff = ("--- a/x\n+++ b/x\n"
            " existing = '0x" + "ab" * 32 + "'\n"
            "-removed = 'sk-0123456789abcdefghij'\n"
            "+harmless = 1\n")
    scan_diff_for_secrets(diff)


def test_gate_does_not_trip_on_the_diff_header():
    scan_diff_for_secrets("+++ b/secrets.py\n+x = 1\n")


def test_gate_clean_diff_passes():
    scan_diff_for_secrets("--- a/x\n+++ b/x\n+def f():\n+    return 1\n")


# ------------------------------------------------------------------ tests
def test_gate_refuses_to_push_a_red_suite():
    with pytest.raises(Refused, match="test suite failed"):
        assert_tests_passed(1, "E   assert 1 == 2\n3 failed")


def test_gate_failure_message_carries_the_tail_so_it_is_actionable():
    with pytest.raises(Refused) as e:
        assert_tests_passed(1, "\n".join(f"line{i}" for i in range(40)))
    assert "line39" in str(e.value)


def test_gate_green_suite_passes():
    assert_tests_passed(0, "316 passed")


# -------------------------------------------------------------- isolation
@pytest.mark.parametrize("var", ["HL_SECRET_KEY", "EXEC_TOKEN",
                                 "CB_API_PRIVATE_KEY"])
def test_gate_refuses_to_boot_holding_trading_credentials(var):
    """The blueprint is supposed to guarantee this, but a blueprint is a file
    someone can edit - and this repo has already had an env var silently flip
    on an unrelated sync. Verify the property at boot."""
    with pytest.raises(Refused, match="never carry trading credentials"):
        assert_environment_isolated({var: "something"})


def test_gate_boots_clean_without_them():
    assert_environment_isolated({"GITHUB_TOKEN": "x", "OPENROUTER_API_KEY": "y"})


def test_gate_empty_value_is_not_holding_a_credential():
    assert_environment_isolated({"HL_SECRET_KEY": "", "EXEC_TOKEN": "   "})
