"""code-agent: a token-gated coding API for this repo.

NOT a chat bot. Slav is the assistant; this is a tool Slav calls. That
split is forced by Telegram - a bot gets exactly one delivery mechanism,
webhook or polling, so two services wanting the same bot silently steal it
from each other - but it is also the better shape: one assistant that
answers questions AND writes code, rather than a bot per capability.

Deliberately NOT deployed alongside anything that holds money. It carries a
GitHub token and an OpenRouter key and nothing else; `assert_environment_isolated`
refuses to boot if a trading credential is present, because the isolation is
a deployment property and this repo has already had an env var flip silently
on an unrelated blueprint sync.

Flow: POST /task -> aider edits a fresh checkout of origin/main -> path,
secret and test gates -> push an `agent/*` branch. It never pushes to main
and never merges. A human reviews the branch and merges it, and that merge
is the deploy.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .guard import Refused, assert_environment_isolated
from .jobs import Jobs
from .runner import do_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKDIR = os.environ.get("WORKDIR", "/app/data/repo")
MODEL = os.environ.get("CODE_MODEL", "openrouter/moonshotai/kimi-k3")
REPO = os.environ.get("GITHUB_REPO", "OpticReports/uranium-dashboard")
JOBS = Jobs()
BUSY = threading.Lock()      # one task at a time: two aiders in one checkout
                             # would interleave edits into one diff


def _auth(token: str | None) -> None:
    """Shared-secret gate, compared in constant time.

    == on a secret leaks its prefix through timing. Cheap to avoid, and this
    endpoint can write to a repo that deploys a live trading book."""
    want = os.environ.get("AGENT_TOKEN", "")
    if not want:
        raise HTTPException(status_code=503,
                            detail="AGENT_TOKEN is not set; refusing to serve "
                                   "an unauthenticated coding endpoint")
    if not token or not hmac.compare_digest(token, want):
        raise HTTPException(status_code=401, detail="bad agent token")


def clone_url() -> str:
    """HTTPS with the token inlined. Never logged, never returned."""
    tok = os.environ.get("GITHUB_TOKEN", "")
    if not tok:
        raise Refused("GITHUB_TOKEN is not set")
    return f"https://x-access-token:{tok}@github.com/{REPO}.git"


def _touched() -> list:
    """Best-effort list of files the editor changed, for a refusal message."""
    try:
        from .runner import changed_paths
        return changed_paths(WORKDIR)
    except Exception:  # noqa: BLE001
        return []


def _work(jid: str, task: str) -> None:
    try:
        r = do_task(task, WORKDIR, clone_url(), MODEL)
        if r.get("ok"):
            r["compare"] = f"https://github.com/{REPO}/compare/{r['branch']}?expand=1"
        JOBS.finish(jid, result=r)
    except Refused as exc:
        # A gate said no. That is an ANSWER, not a crash - reported as a
        # normal outcome so the caller relays the reason rather than
        # retrying into the same refusal.
        #
        # WITH THE FILE LIST: the first live refusal said the suite failed
        # but not what had been edited, so it was impossible to tell whether
        # the editor had touched the intended file at all. A refusal that
        # cannot be attributed to a change is hard to act on.
        JOBS.finish(jid, error=f"refused: {exc}", files=_touched())
    except Exception as exc:  # noqa: BLE001
        logger.exception("task failed")
        JOBS.finish(jid, error=f"{type(exc).__name__}: {exc}")
    finally:
        BUSY.release()


def build_sha() -> str | None:
    sha = (os.environ.get("RENDER_GIT_COMMIT")
           or os.environ.get("GIT_COMMIT") or "").strip()
    return sha[:7] or None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Raising here fails the deploy, which is the correct outcome: a coding
    # agent holding a trading key must not run.
    assert_environment_isolated(os.environ)
    # THE TEST GATE MUST BE ABLE TO RUN (2026-08-29, found on the first real
    # task: the image had no pytest, so every task refused at the test gate
    # forever - safe, and completely useless). A gate that cannot run is not
    # a gate, and this failed at first USE rather than at deploy, which is
    # the wrong end. Fail the deploy instead.
    import importlib.util
    if importlib.util.find_spec("pytest") is None:
        raise Refused(
            "refusing to start: pytest is not installed, so the test gate "
            "cannot run and every task would refuse. Rebuild the image.")
    if not os.environ.get("AGENT_TOKEN"):
        logger.warning("AGENT_TOKEN unset: /task will refuse every call")
    yield


app = FastAPI(title="code-agent", lifespan=lifespan)


class TaskIn(BaseModel):
    task: str


@app.get("/health")
def health():
    """Public. Says what is running and whether setup is complete - never a
    secret, and never the AGENT_TOKEN."""
    return {"status": "ok", "service": "code-agent", "model": MODEL,
            "build": build_sha(), "busy": BUSY.locked(), "repo": REPO,
            # Which edit format is in force decides whether the editor can
            # produce an edit at all, and it was invisible from outside:
            # two rounds were spent guessing whether an env change had
            # taken. "default" means unset - aider picks per model.
            "edit_format": os.environ.get("AIDER_EDIT_FORMAT", "").strip()
                           or "default",
            "auth_ready": bool(os.environ.get("AGENT_TOKEN")),
            "github_ready": bool(os.environ.get("GITHUB_TOKEN"))}


@app.post("/task")
def create_task(body: TaskIn, x_agent_token: str | None = Header(default=None)):
    """Start a coding task. Returns immediately with a job id.

    Async because a task takes MINUTES - a caller holding the connection
    would time out mid-run and lose the outcome of work that is still
    happening."""
    _auth(x_agent_token)
    task = (body.task or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="empty task")
    if not BUSY.acquire(blocking=False):
        raise HTTPException(status_code=409,
                            detail="busy with another task")
    jid = JOBS.create(task)
    threading.Thread(target=_work, args=(jid, task), daemon=True).start()
    return {"id": jid, "state": "running", "task": task[:200]}


@app.get("/task/{jid}")
def get_task(jid: str, x_agent_token: str | None = Header(default=None)):
    _auth(x_agent_token)
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(status_code=404, detail="unknown job")
    return j


@app.get("/tasks")
def list_tasks(x_agent_token: str | None = Header(default=None)):
    _auth(x_agent_token)
    return {"jobs": JOBS.recent()}
