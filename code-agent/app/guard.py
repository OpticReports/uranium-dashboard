"""The gates. Everything the coding agent is NOT allowed to do lives here.

WHY THIS FILE EXISTS. The agent behind it is an LLM driven from Telegram,
so its input is attacker-reachable in the ordinary case: anything it reads -
an issue body, a CI log, a file in the repo, a message forwarded to the bot -
can try to steer it. The model is not the security boundary. These functions
are.

The repo it edits deploys a LIVE trading book: `main` auto-deploys, and
btc-executor holds a Hyperliquid key with signing authority over ~$50k. So
the threat model is not "the agent writes a bug" (review catches that), it is
"the agent ships to main", "the agent grants itself a credential", and "the
agent edits the rules that stop it". Each of those is a function below.

Every gate REFUSES by raising. None of them return a boolean the caller can
forget to check.
"""
from __future__ import annotations

import hashlib
import re


class Refused(Exception):
    """A gate said no. Never caught to 'try anyway' - it ends the run."""


# Branches the agent may create. Anything else - main above all - is refused.
BRANCH_PREFIX = "agent/"
PROTECTED_BRANCHES = ("main", "master", "HEAD")

# Paths the agent must never modify, and WHY each one:
#   render.yaml        - the deploy blueprint. An agent that can edit it can
#                        grant its own service any env var, including the
#                        trading keys it is specifically denied. Privilege
#                        escalation, not a code change.
#   code-agent/**      - its own guardrails. An agent that can edit this file
#                        can delete this list.
#   .github/workflows  - CI runs with its own credentials and can push.
#   *.env, .env*       - secrets by definition.
#   CLAUDE.md/AGENTS.md/.cursorrules - the conventions every tool loads. Not
#                        security-critical, but an agent quietly rewriting its
#                        own instructions is the same shape as the above.
# Entries ending in "/" deny a whole subtree; the rest are EXACT matches.
# Exactness matters: a bare startswith() also refuses render.yaml.example,
# and containment that blocks harmless work is containment that gets
# switched off.
DENIED_EXACT = ("render.yaml", "CLAUDE.md", "AGENTS.md", ".cursorrules")
DENIED_TREES = ("code-agent/", ".github/workflows/")
DENIED_SUFFIXES = (".env",)
DENIED_NAMES = (".env",)

# Patterns that must never appear in an ADDED line. Deliberately broad: a
# false refusal costs one retry, a miss commits a live credential to a public
# git history where rotating it is the only remedy.
SECRET_PATTERNS = (
    (re.compile(r"0x[0-9a-fA-F]{64}\b"), "a 32-byte hex key (wallet private key shape)"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a PEM private key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "an sk- API key"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "a Telegram bot token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "a GitHub token"),
    (re.compile(r"(?i)\b(secret|token|password|api[_-]?key|private[_-]?key)"
                r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"), "a hardcoded credential"),
)

# Env vars this service must never hold. Checked at boot against its OWN
# environment: the isolation is a deployment property, so verify it rather
# than trusting the blueprint to have stayed correct.
FORBIDDEN_ENV = (
    "HL_SECRET_KEY", "EXEC_TOKEN", "CB_API_KEY_NAME", "CB_API_PRIVATE_KEY",
    "IBKR_ACCOUNT", "COINBASE_API_SECRET",
)


def _norm(path) -> str:
    """Repo-relative, forward-slashed, no leading './'.

    NOT lstrip("./") - that strips a CHARACTER SET, so ".env" becomes "env"
    and ".github/..." becomes "github/...", quietly walking both past the
    deny list. Caught by this file's own tests before it shipped."""
    q = str(path).strip().replace("\\", "/")
    while q.startswith("./"):
        q = q[2:]
    return q.lstrip("/")


def branch_for(task: str, salt: str = "") -> str:
    """A deterministic, always-prefixed branch name.

    Derived rather than model-chosen: a branch name that comes back from the
    LLM is one more string an injected instruction can control, and the whole
    point of the prefix is that it cannot be talked out of."""
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:32].strip("-")
    h = hashlib.sha256((task + salt).encode()).hexdigest()[:8]
    return f"{BRANCH_PREFIX}{slug or 'task'}-{h}"


def assert_pushable(branch: str) -> None:
    """`main` auto-deploys into a live trading book. Nothing else matters as
    much as this one refusing correctly."""
    name = (branch or "").strip()
    if not name:
        raise Refused("no branch given")
    if name in PROTECTED_BRANCHES or name.lower() in PROTECTED_BRANCHES:
        raise Refused(
            f"refusing to push to {name!r}: it auto-deploys a live trading "
            f"book. The agent opens a PR; a human merges it.")
    if not name.startswith(BRANCH_PREFIX):
        raise Refused(
            f"refusing to push {name!r}: agent branches must start with "
            f"{BRANCH_PREFIX!r} so they are identifiable and cannot collide "
            f"with human work.")
    if ".." in name or name.startswith("-") or " " in name:
        raise Refused(f"unsafe branch name {name!r}")


def assert_paths_allowed(paths) -> None:
    """Refuse edits that would let the agent widen its own privileges."""
    bad = []
    for p in paths:
        q = _norm(p)
        if (q in DENIED_EXACT
                or any(q.startswith(d) for d in DENIED_TREES)
                or q.endswith(DENIED_SUFFIXES)
                or q.rsplit("/", 1)[-1] in DENIED_NAMES):
            bad.append(q)
    if bad:
        raise Refused(
            "refusing to modify " + ", ".join(sorted(set(bad))) +
            " - these control deployment, credentials, CI, or the agent's own "
            "guardrails. Ask a human to make that change.")


def scan_diff_for_secrets(diff: str) -> None:
    """Refuse a diff that ADDS anything credential-shaped.

    Added lines only: the repo's own docs quote key SHAPES (the agent-wallet
    notes in EXECUTOR.md, for one), and refusing to touch a file because an
    untouched line nearby looks like a key would make the agent useless
    exactly where the money is."""
    hits = []
    for line in (diff or "").splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for pat, what in SECRET_PATTERNS:
            if pat.search(line):
                hits.append(what)
                break
    if hits:
        raise Refused(
            "refusing to commit: the diff adds " + ", ".join(sorted(set(hits))) +
            ". Committed credentials are public the moment they are pushed and "
            "rotation is the only remedy.")


def assert_tests_passed(returncode: int, output: str = "") -> None:
    """The suite is the merge gate everywhere else in this repo; it is the
    push gate here. An agent that can push a red branch turns review into the
    only defence, and review is what gets skipped when things are urgent."""
    if returncode != 0:
        tail = "\n".join((output or "").strip().splitlines()[-15:])
        raise Refused(f"refusing to push: the test suite failed.\n{tail}")


def assert_environment_isolated(env) -> None:
    """Verify at boot that this service does not hold trading credentials.

    The blueprint is supposed to guarantee this, but a blueprint is a file
    someone can edit - and this repo has already had one env var silently
    flip on an unrelated sync. Check the property, do not assume it."""
    present = [k for k in FORBIDDEN_ENV if (env.get(k) or "").strip()]
    if present:
        raise Refused(
            "refusing to start: this service holds " + ", ".join(present) +
            " - a coding agent must never carry trading credentials. Remove "
            "them from the code-agent service in Render.")
