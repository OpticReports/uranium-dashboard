"""Runner tests. The point is ORDER: each gate must fire before the step it
protects, and nothing may reach the remote past a refusal.

No network, no clone, no API key - every subprocess goes through the
injected `run`, so these assert on the command sequence itself.
"""
from __future__ import annotations

import pytest

from app import runner
from app.guard import Refused


class FakeRun:
    """Records commands and replays scripted results."""

    def __init__(self, diff="", names="btc-executor/app/hl.py",
                 test_rc=0, test_out="316 passed", aider_rc=0):
        self.calls = []
        self.diff, self.names = diff, names
        self.test_rc, self.test_out, self.aider_rc = test_rc, test_out, aider_rc

    def __call__(self, cmd, cwd=None, timeout=300, env=None):
        self.calls.append(list(cmd))
        if cmd[0] == "aider":
            return self.aider_rc, "edited 1 file"
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return 0, self.names
        if cmd[:2] == ["git", "diff"]:
            return 0, self.diff
        if cmd[0] == "python3":
            return self.test_rc, self.test_out
        return 0, ""

    def ran(self, *prefix):
        return any(c[:len(prefix)] == list(prefix) for c in self.calls)

    @property
    def pushed(self):
        return any(c[:2] == ["git", "push"] for c in self.calls)


def _do(fake, task="fix the stop rounding"):
    return runner.do_task(task, "/tmp/x", "https://example/repo.git",
                          "openrouter/m", run=fake)


def test_gate_happy_path_pushes_a_prefixed_branch(monkeypatch, tmp_path):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="--- a/x\n+++ b/x\n+ok = 1\n")
    r = _do(f)
    assert r["ok"] and r["branch"].startswith("agent/")
    assert f.pushed


def test_gate_nothing_reaches_the_remote_when_a_denied_path_is_touched(monkeypatch):
    """render.yaml is how an agent would grant itself the trading keys."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(names="render.yaml\nbtc-executor/app/hl.py")
    with pytest.raises(Refused, match="refusing to modify"):
        _do(f)
    assert not f.pushed


def test_gate_nothing_reaches_the_remote_when_the_diff_adds_a_secret(monkeypatch):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="--- a/x\n+++ b/x\n+K = '0x" + "ab" * 32 + "'\n")
    with pytest.raises(Refused, match="refusing to commit"):
        _do(f)
    assert not f.pushed


def test_gate_nothing_reaches_the_remote_when_tests_fail(monkeypatch):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n", test_rc=1, test_out="3 failed")
    with pytest.raises(Refused, match="test suite failed"):
        _do(f)
    assert not f.pushed


def test_gate_tests_run_before_the_push_not_after(monkeypatch):
    """A suite that runs after the push is a report, not a gate."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    order = [c[0] for c in f.calls]
    assert order.index("python3") < [i for i, c in enumerate(f.calls)
                                     if c[:2] == ["git", "push"]][0]


def test_gate_aider_is_not_allowed_to_commit(monkeypatch):
    """--no-auto-commits keeps the change in the working tree so the gates
    still see a diff they can refuse. An agent that commits before it is
    checked has already done the thing we are preventing."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    aider = [c for c in f.calls if c[0] == "aider"][0]
    assert "--no-auto-commits" in aider


def test_gate_every_task_starts_from_a_clean_origin_main(monkeypatch):
    """A leftover edit from a previous task would be attributed to this one,
    and the diff is what every gate reads."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    assert f.ran("git", "reset", "--hard", "origin/main")
    assert f.ran("git", "clean", "-fd")


def test_gate_an_empty_edit_is_reported_not_pushed(monkeypatch):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(names="")
    r = _do(f)
    assert r["ok"] is False and not f.pushed


def test_gate_a_failed_editor_never_reaches_the_gates(monkeypatch):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(aider_rc=1)
    with pytest.raises(Refused, match="editor failed"):
        _do(f)
    assert not f.pushed


def test_gate_the_test_command_covers_the_repo_not_one_service():
    """A change in btc-executor that breaks code-agent's own gates must fail
    the run that made it."""
    assert any("btc-executor/tests" in a for a in runner.TEST_CMD)
    assert any("code-agent/tests" in a for a in runner.TEST_CMD)
