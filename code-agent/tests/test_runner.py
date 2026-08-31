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
        self.test_cwds = []

    def __call__(self, cmd, cwd=None, timeout=300, env=None):
        self.calls.append(list(cmd))
        if cmd[0] == "aider":
            return self.aider_rc, "edited 1 file"
        if cmd[:2] == ["git", "diff"] and "--name-only" in cmd:
            return 0, self.names
        if cmd[:2] == ["git", "diff"]:
            return 0, self.diff
        if cmd[0] == "python3":
            self.test_cwds.append(cwd)
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
    subs = [sub for sub, _ in runner.TEST_SUITES]
    assert "btc-executor" in subs and "code-agent" in subs


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

def test_gate_each_suite_runs_from_its_own_service_directory(monkeypatch):
    """Running them together from the repo root collected ZERO tests and
    errored with `No module named app` - btc-executor's tests import
    `app.mirror`, which resolves only with that service as the root. A gate
    that cannot import the code it guards refuses everything: safe, useless,
    and it looked like a real failure."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    assert any(str(c).endswith("btc-executor") for c in f.test_cwds), \
        f"btc-executor suite not run from its own directory: {f.test_cwds}"
    assert any(str(c).endswith("code-agent") for c in f.test_cwds)


def test_gate_a_failing_suite_stops_the_run_at_that_suite(monkeypatch):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n", test_rc=1, test_out="1 failed")
    with pytest.raises(Refused, match="test suite failed"):
        _do(f)
    assert len(f.test_cwds) == 1, "kept running suites after one failed"
    assert not f.pushed


def test_gate_paths_named_in_the_task_are_handed_to_aider(monkeypatch, tmp_path):
    """The first live run edited ONLY .gitignore and never touched the file
    the task named: with --message alone aider falls back to its repo map,
    and this repo holds twelve projects."""
    (tmp_path / "btc-executor" / "app").mkdir(parents=True)
    (tmp_path / "btc-executor" / "app" / "hl.py").write_text("x = 1\n")
    got = runner.files_in("please fix quantize in btc-executor/app/hl.py",
                          str(tmp_path))
    assert got == ["btc-executor/app/hl.py"]


def test_gate_a_path_that_does_not_exist_is_not_passed_to_aider(tmp_path):
    """aider errors out on a --file that is not there, which would turn a
    typo in the task into an opaque 'the editor failed'."""
    assert runner.files_in("edit btc-executor/app/nope.py", str(tmp_path)) == []


def test_gate_the_repo_map_is_off_once_the_files_are_named(monkeypatch):
    """The run that changed nothing sent 37k tokens: the map spans twelve
    projects, so the model spent the task choosing files instead of editing
    the one it was handed."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(runner, "files_in", lambda t, w: ["btc-executor/app/hl.py"])
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    aider = [c for c in f.calls if c[0] == "aider"][0]
    assert aider[aider.index("--map-tokens") + 1] == "0"


def test_gate_the_repo_map_stays_on_when_no_file_was_named(monkeypatch):
    """With nothing named, the map is the ONLY way aider finds the file.
    Disabling it unconditionally would blind the editor completely."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(runner, "files_in", lambda t, w: [])
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    aider = [c for c in f.calls if c[0] == "aider"][0]
    assert "--map-tokens" not in aider


def test_gate_the_edit_format_is_settable_without_a_redeploy(monkeypatch):
    """Which format a model can actually produce is empirical, and finding
    out costs one live task."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.setenv("AIDER_EDIT_FORMAT", "whole")
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    aider = [c for c in f.calls if c[0] == "aider"][0]
    assert aider[aider.index("--edit-format") + 1] == "whole"


def test_gate_no_edit_format_is_forced_when_the_env_is_unset(monkeypatch):
    """Unset must mean 'let aider choose', not an empty flag value that
    aider rejects."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.delenv("AIDER_EDIT_FORMAT", raising=False)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    assert "--edit-format" not in [c for c in f.calls if c[0] == "aider"][0]


def test_gate_an_empty_edit_names_the_likely_cause(monkeypatch):
    """A bare 'changed nothing' after a 30-minute run sent us reading the
    log line by line to discover a one-line remedy."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    r = _do(FakeRun(names=""))
    assert r["ok"] is False
    assert "prose" in r["reason"] and "AIDER_EDIT_FORMAT" in r["reason"]


def test_gate_an_empty_edit_reports_the_command_that_was_run(monkeypatch):
    """Two failures in a row were diagnosed by GUESSING which flags had
    applied, and the second guess was wrong. The argv is the cheapest
    evidence there is and it was the one thing missing from the result."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(runner, "files_in", lambda t, w: ["btc-executor/app/hl.py"])
    r = _do(FakeRun(names=""))
    assert "--map-tokens 0" in r["aider_cmd"]
    assert "--file btc-executor/app/hl.py" in r["aider_cmd"]


class StagingAwareRun(FakeRun):
    """Models the ONE git behaviour this pair of tests is about: a file the
    editor CREATED is invisible to `git diff` until it has been staged."""

    def __init__(self, new_file, **kw):
        super().__init__(names="", **kw)
        self.new_file, self.staged = new_file, False

    def __call__(self, cmd, cwd=None, timeout=300, env=None):
        if cmd[:3] == ["git", "add", "-A"]:
            self.calls.append(list(cmd))
            self.staged = True
            return 0, ""
        if cmd[:2] == ["git", "diff"]:
            self.calls.append(list(cmd))
            visible = self.staged and "--cached" in cmd
            if "--name-only" in cmd:
                return 0, (self.new_file if visible else "")
            return 0, (f"--- /dev/null\n+++ b/{self.new_file}\n+x = 1\n"
                       if visible else "")
        return super().__call__(cmd, cwd, timeout, env)


def test_gate_a_file_the_editor_CREATED_is_still_path_checked(monkeypatch):
    """`git diff HEAD` does not list untracked files. Before staging was
    added, a task that created code-agent/app/x.py showed NO changed paths,
    so the deny list never saw it - and `git add -A` at commit time would
    then sweep it into the push. A new file is the easiest way to add code,
    so this is the gap that mattered most."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = StagingAwareRun("code-agent/app/backdoor.py")
    with pytest.raises(Refused, match="refusing to modify"):
        _do(f)
    assert not f.pushed


def test_gate_a_created_file_is_secret_scanned(monkeypatch):
    """Same blind spot, second gate: an untracked file contributes nothing to
    `git diff HEAD`, so a key inside a brand-new file scanned clean."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)

    class WithKey(StagingAwareRun):
        def __call__(self, cmd, cwd=None, timeout=300, env=None):
            rc, out = super().__call__(cmd, cwd, timeout, env)
            if cmd[:2] == ["git", "diff"] and "--name-only" not in cmd and out:
                return rc, "--- /dev/null\n+++ b/x\n+K = '0x" + "ab" * 32 + "'\n"
            return rc, out

    f = WithKey("btc-executor/app/new_helper.py")
    with pytest.raises(Refused, match="refusing to commit"):
        _do(f)
    assert not f.pushed


def test_gate_staging_happens_before_the_gates_read_anything(monkeypatch):
    """Order, not presence: staging after the gates would leave them reading
    the same blind worktree diff."""
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    f = FakeRun(diff="+ok = 1\n")
    _do(f)
    add = [i for i, c in enumerate(f.calls) if c[:3] == ["git", "add", "-A"]][0]
    first_read = [i for i, c in enumerate(f.calls) if c[:2] == ["git", "diff"]][0]
    assert add < first_read, f"gates read the diff before staging: {f.calls}"


def test_gate_aider_receives_the_file_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(runner.os.path, "isdir", lambda p: True)
    monkeypatch.setattr(runner, "files_in", lambda t, w: ["code-agent/app/guard.py"])
    f = FakeRun(diff="+ok = 1\n")
    _do(f, task="add a docstring to _norm in code-agent/app/guard.py")
    aider = [c for c in f.calls if c[0] == "aider"][0]
    assert "--file" in aider and "code-agent/app/guard.py" in aider
