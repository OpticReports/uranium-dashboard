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


def test_gate_auth_failure_names_the_expired_token(monkeypatch):
    """GitHub reports an EXPIRED token identically to a wrong one, and a
    fine-grained PAT expires on a date set months earlier. Without this the
    failure is a generic 'push failed' in the middle of a task."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)

    class Failing(FakeRun):
        def __call__(self, cmd, cwd=None, timeout=300, env=None):
            if cmd[:2] == ["git", "push"]:
                self.calls.append(list(cmd))
                return 128, "remote: Invalid username or password\nfatal: Authentication failed"
            return super().__call__(cmd, cwd, timeout, env)

    with pytest.raises(Refused, match="expired"):
        _do(Failing(diff="+ok = 1\n"))


def test_gate_a_normal_failure_is_not_blamed_on_the_token(monkeypatch):
    """Guessing 'expired token' at every failure trains the operator to
    ignore the hint."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)

    class Failing(FakeRun):
        def __call__(self, cmd, cwd=None, timeout=300, env=None):
            if cmd[:2] == ["git", "push"]:
                self.calls.append(list(cmd))
                return 1, "error: failed to push some refs (non-fast-forward)"
            return super().__call__(cmd, cwd, timeout, env)

    with pytest.raises(Refused) as e:
        _do(Failing(diff="+ok = 1\n"))
    assert "expired" not in str(e.value)


def test_gate_webhook_secret_is_derived_and_stable(monkeypatch):
    """Setup needs this value; deriving a sha256 by hand is how setup gets
    skipped. It must also not BE the bot token - it is logged."""
    from app import main
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:abcdefg")
    a = main.webhook_secret()
    assert a == main.webhook_secret(), "not stable across calls"
    assert "12345:abcdefg" not in a, "the log line would leak the bot token"
    assert len(a) == 32
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "99999:zzzzzzz")
    assert main.webhook_secret() != a, "same path for a different bot"


def test_gate_health_reports_the_build_and_readiness_but_no_secret(monkeypatch):
    """A health endpoint that cannot say which build it is running turns
    'the log line is missing' and 'the deploy has not landed' into the same
    observation - which is how this got diagnosed by guesswork once already.
    It must NOT leak the webhook path: that is what stops the endpoint being
    found by scanning."""
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234567890")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:abcdefg")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    body = TestClient(main.app).get("/health").json()
    assert body["build"] == "abc1234"
    assert body["telegram_ready"] is True and body["github_ready"] is True
    blob = str(body)
    assert main.webhook_secret() not in blob, "health leaked the webhook path"
    assert "12345:abcdefg" not in blob, "health leaked the bot token"
    assert "ghp_x" not in blob, "health leaked the github token"


def test_gate_health_shows_what_is_still_unset(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GITHUB_TOKEN",
              "RENDER_GIT_COMMIT", "GIT_COMMIT"):
        monkeypatch.delenv(k, raising=False)
    body = TestClient(main.app).get("/health").json()
    assert body["telegram_ready"] is False and body["github_ready"] is False
    assert body["build"] is None, "guessed a build id it does not have"


def test_gate_webhook_log_is_one_line_and_self_findable(monkeypatch, caplog):
    """Logs are retrieved through a substring filter. A two-line message
    puts the URL on a continuation line that does not contain the search
    term, so the only half that matters is the half that gets hidden -
    which is exactly what happened in production."""
    import logging
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:abcdefg")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://code-agent-96w7.onrender.com")
    with caplog.at_level(logging.INFO):
        with TestClient(main.app):
            pass
    hits = [r.getMessage() for r in caplog.records if "webhook" in r.getMessage()]
    assert hits, "nothing logged the webhook at boot"
    line = hits[-1]
    assert "\n" not in line, "multi-line: the URL half is invisible to a filter"
    assert main.webhook_secret() in line, "the secret is not on the found line"
    assert "code-agent-96w7.onrender.com/telegram/" in line
