"""Repo operations: check out, let aider edit, gate, push, open a PR.

Deliberately NOT a coding agent. aider is a mature one that speaks
OpenRouter, understands git, and knows how to edit a repo it has mapped -
rebuilding that badly would be the expensive mistake here. This module is
the harness around it: it decides WHERE aider runs, WHAT it may touch, and
whether the result is allowed anywhere near the remote.

Every subprocess call is funnelled through _run so a test can substitute it
without a network, a clone, or an API key.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess

from .guard import (Refused, assert_paths_allowed, assert_pushable,
                    assert_tests_passed, branch_for, scan_diff_for_secrets)

logger = logging.getLogger(__name__)

# EACH SUITE RUNS FROM ITS OWN SERVICE DIRECTORY (2026-08-29, found live).
# Running them together from the repo root collected zero tests and errored
# with `No module named 'app'`: btc-executor's tests import `app.mirror`,
# which resolves only with that service as the root. A gate that cannot
# import the code it guards refuses everything - safe, and useless.
_PYTEST = ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]
TEST_SUITES = (("btc-executor", _PYTEST), ("code-agent", _PYTEST))
AIDER_TIMEOUT_S = 1800
TEST_TIMEOUT_S = 900

# Paths named in the task, handed to aider explicitly. Without this it falls
# back to its repo map, and this repo holds twelve projects - the first live
# run edited only .gitignore and never touched the file the task named.
_PATH_RE = re.compile(
    r"\b[\w.-]+(?:/[\w.-]+)+\.(?:py|md|ya?ml|txt|json|toml|cfg|ini|sh)\b")


def files_in(task: str, workdir: str) -> list[str]:
    """Repo paths mentioned in the task that actually exist."""
    seen, out = set(), []
    for m in _PATH_RE.findall(task or ""):
        if m not in seen and os.path.isfile(os.path.join(workdir, m)):
            seen.add(m)
            out.append(m)
    return out


def _run(cmd, cwd=None, timeout=300, env=None):
    """One choke point for every subprocess, so tests can replace it."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def ensure_repo(workdir: str, clone_url: str, run=_run) -> str:
    """A fresh checkout of origin/main, every task.

    Never reuses a dirty tree: a leftover edit from a previous task would be
    silently attributed to this one, and the diff is what the gates read."""
    if not os.path.isdir(os.path.join(workdir, ".git")):
        rc, out = run(["git", "clone", "--depth", "50", clone_url, workdir],
                      timeout=600)
        if rc != 0:
            raise Refused(f"clone failed: {out[-500:]}")
    for cmd in (["git", "fetch", "origin", "main"],
                ["git", "reset", "--hard", "origin/main"],
                ["git", "clean", "-fd"]):
        rc, out = run(cmd, cwd=workdir, timeout=300)
        if rc != 0:
            raise Refused(f"{' '.join(cmd)} failed: {out[-500:]}")
    return workdir


def stage_all(workdir: str, run=_run) -> None:
    """Stage everything - INCLUDING NEW FILES - before any gate reads a diff.

    `git diff HEAD` DOES NOT SEE UNTRACKED FILES (2026-08-31). So a task that
    edited one allowed file and also CREATED code-agent/app/x.py showed only
    the edit: the new file was never path-checked and never secret-scanned,
    and then `git add -A` inside commit_and_push swept it into the push. A
    file the gates never saw is the exact thing this harness exists to stop.

    Staging first makes creations, renames and deletions all visible to
    `git diff --cached`. Nothing is committed here - ensure_repo resets and
    cleans the tree at the start of every task, so a refused run leaves the
    index behind harmlessly."""
    rc, out = run(["git", "add", "-A"], cwd=workdir, timeout=120)
    if rc != 0:
        raise Refused(f"could not stage the edit: {out[-300:]}")


def changed_paths(workdir: str, run=_run) -> list[str]:
    rc, out = run(["git", "diff", "--cached", "--name-only"], cwd=workdir)
    if rc != 0:
        raise Refused(f"could not read the working diff: {out[-300:]}")
    return [l.strip() for l in out.splitlines() if l.strip()]


def working_diff(workdir: str, run=_run) -> str:
    rc, out = run(["git", "diff", "--cached"], cwd=workdir, timeout=120)
    if rc != 0:
        raise Refused(f"could not read the working diff: {out[-300:]}")
    return out


def aider_cmd(task: str, workdir: str, model: str) -> list[str]:
    """The exact argv, built separately so a failed run can REPORT it.

    Two runs were diagnosed by guessing at which flags had been applied,
    and the second guess was wrong - the context grew when the change was
    supposed to shrink it. The command is the cheapest possible evidence
    and it was the one thing not in the result."""
    cmd = ["aider", "--model", model, "--yes", "--no-auto-commits",
           "--no-analytics", "--no-check-update",
           # The model kept spending turns proposing commands to run instead
           # of emitting an edit. It has no shell here; offering one is a
           # detour with no destination.
           "--no-suggest-shell-commands"]
    fmt = os.environ.get("AIDER_EDIT_FORMAT", "").strip()
    if fmt:
        # An env knob, not a constant: which format a model can actually
        # produce is an empirical property of that model, and finding out
        # costs one live task. Changing it must not cost a redeploy.
        cmd += ["--edit-format", fmt]
    files = files_in(task, workdir)
    for f in files:
        cmd += ["--file", f]          # explicit beats hoping the map finds it
    if files:
        # NO REPO MAP once the files are named (2026-08-31). The run that
        # changed nothing sent 37k tokens: the map spans twelve projects, so
        # the model spent the task reasoning about which OTHER files it
        # wanted rather than editing the one it was given, and signed off
        # with prose claiming an edit it never emitted.
        cmd += ["--map-tokens", "0"]
    cmd += ["--message", task]
    return cmd


def run_aider(workdir: str, task: str, model: str, run=_run) -> str:
    """Let aider make the edit. It commits nothing - --no-auto-commits keeps
    the change in the working tree so the gates below see a diff they can
    still refuse. An agent that commits before it is checked has already
    written the thing you wanted to prevent."""
    cmd = aider_cmd(task, workdir, model)
    rc, out = run(cmd, cwd=workdir, timeout=AIDER_TIMEOUT_S)
    if rc != 0:
        raise Refused(f"the editor failed: {out[-800:]}")
    return out


def run_tests(workdir: str, run=_run) -> tuple[int, str]:
    """Every suite must pass. Stops at the first failure - the caller only
    needs to know that the gate said no, and which suite said it."""
    outs = []
    for sub, cmd in TEST_SUITES:
        rc, out = run(cmd, cwd=os.path.join(workdir, sub),
                      timeout=TEST_TIMEOUT_S)
        outs.append(f"--- {sub} ---\n{out.strip()}")
        if rc != 0:
            return rc, "\n".join(outs)
    return 0, "\n".join(outs)


# GitHub says "authentication failed" for an expired token exactly as it does
# for a wrong one, and a fine-grained PAT expires on a date nobody remembers -
# months after it was set, mid-task. Name the likely cause in the message so
# the failure is one glance instead of an evening.
_AUTH_HINTS = ("authentication failed", "could not read username",
               "invalid username or password", "403", "permission denied",
               "repository not found")


def _explain(out: str) -> str:
    tail = (out or "")[-500:]
    if any(h in (out or "").lower() for h in _AUTH_HINTS):
        return (tail + "\n\nLIKELY CAUSE: the GITHUB_TOKEN has expired, been "
                "revoked, or lacks Contents:write on this repo. Fine-grained "
                "tokens expire on a fixed date and GitHub does not warn the "
                "service - reissue it and update the code-agent env var.")
    return tail


def commit_and_push(workdir: str, branch: str, task: str, run=_run) -> None:
    assert_pushable(branch)                      # again, at the last moment
    for cmd in (["git", "checkout", "-b", branch],
                ["git", "add", "-A"],
                ["git", "commit", "-m", f"agent: {task[:70]}"],
                ["git", "push", "-u", "origin", branch]):
        rc, out = run(cmd, cwd=workdir, timeout=300)
        if rc != 0:
            raise Refused(f"{cmd[1]} failed: {_explain(out)}")


def do_task(task: str, workdir: str, clone_url: str, model: str,
            run=_run) -> dict:
    """The whole loop, in the order the gates have to happen.

    ORDER IS THE DESIGN. Paths are checked before the diff is read, the diff
    before the tests, the tests before anything reaches the remote - and the
    branch is re-checked at the push itself. Each gate assumes the previous
    ones may have been wrong."""
    ensure_repo(workdir, clone_url, run=run)
    out = run_aider(workdir, task, model, run=run)

    stage_all(workdir, run=run)          # so NEW files reach the gates below
    paths = changed_paths(workdir, run=run)
    if not paths:
        # NAME THE LIKELY CAUSE. This came back as a bare "changed nothing"
        # after a 30-minute run, and the log had to be read line by line to
        # find that the model had written PROSE describing the edit instead
        # of an edit block. That is a model-format problem with a one-line
        # remedy, and it looked like a harness bug.
        return {"ok": False,
                "reason": "the editor changed nothing - the model most "
                          "likely described the edit in prose instead of "
                          "emitting an edit block. Try AIDER_EDIT_FORMAT="
                          "whole, or a different CODE_MODEL.",
                "aider_cmd": " ".join(aider_cmd(task, workdir, model)),
                "log": out[-1500:]}
    assert_paths_allowed(paths)
    scan_diff_for_secrets(working_diff(workdir, run=run))

    rc, tout = run_tests(workdir, run=run)
    assert_tests_passed(rc, tout)

    branch = branch_for(task)
    commit_and_push(workdir, branch, task, run=run)
    return {"ok": True, "branch": branch, "files": paths,
            "tests": tout.strip().splitlines()[-1] if tout.strip() else ""}
