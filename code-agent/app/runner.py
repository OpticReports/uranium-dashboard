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
import subprocess

from .guard import (Refused, assert_paths_allowed, assert_pushable,
                    assert_tests_passed, branch_for, scan_diff_for_secrets)

logger = logging.getLogger(__name__)

# The gate the whole repo already merges on. Run from the repo root so a
# change anywhere is covered, not just the service the task mentioned.
TEST_CMD = ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "btc-executor/tests", "code-agent/tests"]
AIDER_TIMEOUT_S = 1800
TEST_TIMEOUT_S = 900


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


def changed_paths(workdir: str, run=_run) -> list[str]:
    rc, out = run(["git", "diff", "--name-only", "HEAD"], cwd=workdir)
    if rc != 0:
        raise Refused(f"could not read the working diff: {out[-300:]}")
    return [l.strip() for l in out.splitlines() if l.strip()]


def working_diff(workdir: str, run=_run) -> str:
    rc, out = run(["git", "diff", "HEAD"], cwd=workdir, timeout=120)
    if rc != 0:
        raise Refused(f"could not read the working diff: {out[-300:]}")
    return out


def run_aider(workdir: str, task: str, model: str, run=_run) -> str:
    """Let aider make the edit. It commits nothing - --no-auto-commits keeps
    the change in the working tree so the gates below see a diff they can
    still refuse. An agent that commits before it is checked has already
    written the thing you wanted to prevent."""
    cmd = ["aider", "--model", model, "--yes", "--no-auto-commits",
           "--no-analytics", "--no-check-update", "--message", task]
    rc, out = run(cmd, cwd=workdir, timeout=AIDER_TIMEOUT_S)
    if rc != 0:
        raise Refused(f"the editor failed: {out[-800:]}")
    return out


def run_tests(workdir: str, run=_run) -> tuple[int, str]:
    return run(TEST_CMD, cwd=workdir, timeout=TEST_TIMEOUT_S)


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

    paths = changed_paths(workdir, run=run)
    if not paths:
        return {"ok": False, "reason": "the editor changed nothing",
                "log": out[-1500:]}
    assert_paths_allowed(paths)
    scan_diff_for_secrets(working_diff(workdir, run=run))

    rc, tout = run_tests(workdir, run=run)
    assert_tests_passed(rc, tout)

    branch = branch_for(task)
    commit_and_push(workdir, branch, task, run=run)
    return {"ok": True, "branch": branch, "files": paths,
            "tests": tout.strip().splitlines()[-1] if tout.strip() else ""}
