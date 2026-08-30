"""code-agent: a Telegram-driven coding agent for this repo.

Deliberately NOT deployed alongside anything that holds money. It carries a
GitHub token and an OpenRouter key and nothing else - `guard.assert_environment_isolated`
refuses to boot if a trading credential is present, because the isolation is
a deployment property and this repo has already had an env var flip silently
on an unrelated blueprint sync.

What it does: owner-only Telegram message -> aider edits a fresh checkout of
origin/main -> path/secret/test gates -> push an `agent/*` branch. It never
pushes to main and never merges. You review the branch and merge it, which
is the step that actually deploys.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request

from .guard import Refused, assert_environment_isolated
from .runner import do_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKDIR = os.environ.get("WORKDIR", "/app/data/repo")
MODEL = os.environ.get("CODE_MODEL", "openrouter/moonshotai/kimi-k3")
BUSY = threading.Lock()          # one task at a time: two aiders in one
                                 # checkout would interleave edits


def _tok() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def webhook_secret() -> str:
    """Derived from the bot token, like treasury-canary's - no extra env."""
    return hashlib.sha256(("code-agent" + _tok()).encode()).hexdigest()[:32]


def send(text: str) -> None:
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (_tok() and chat):
        logger.warning("telegram not configured; dropping: %s", text[:200])
        return
    try:
        httpx.post(f"https://api.telegram.org/bot{_tok()}/sendMessage",
                   json={"chat_id": chat, "text": text[:4000]}, timeout=20)
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram send failed: %s", exc)


def clone_url() -> str:
    """HTTPS with the token inlined. Never logged, never echoed to Telegram."""
    tok = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "OpticReports/uranium-dashboard")
    if not tok:
        raise Refused("GITHUB_TOKEN is not set")
    return f"https://x-access-token:{tok}@github.com/{repo}.git"


def _work(task: str) -> None:
    if not BUSY.acquire(blocking=False):
        send("busy with another task - try again when it finishes")
        return
    try:
        send(f"working: {task[:200]}")
        r = do_task(task, WORKDIR, clone_url(), MODEL)
        if not r.get("ok"):
            send(f"no change made: {r.get('reason')}")
            return
        repo = os.environ.get("GITHUB_REPO", "OpticReports/uranium-dashboard")
        send(f"pushed {r['branch']}\nfiles: {', '.join(r['files'][:10])}\n"
             f"tests: {r['tests']}\n"
             f"https://github.com/{repo}/compare/{r['branch']}?expand=1")
    except Refused as exc:
        send(f"refused: {exc}")            # a gate said no; that is the answer
    except Exception as exc:  # noqa: BLE001
        logger.exception("task failed")
        send(f"failed: {type(exc).__name__}: {exc}")
    finally:
        BUSY.release()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot-time isolation check. Raising here fails the deploy, which is the
    # correct outcome: a coding agent holding a trading key must not run.
    assert_environment_isolated(os.environ)
    # The webhook path, so setup does not require deriving a sha256 by hand.
    # Safe to log: it is a HASH of the bot token, not the token, and Render
    # logs are account-private. It only keeps the endpoint from being found
    # by scanning - the owner chat-id check behind it is the real gate.
    if _tok():
        base = os.environ.get("RENDER_EXTERNAL_URL", "https://<service>.onrender.com")
        logger.info("webhook: register this URL with Telegram ->\n"
                    "  %s/telegram/%s", base.rstrip("/"), webhook_secret())
    else:
        logger.warning("TELEGRAM_BOT_TOKEN unset: the bot cannot be reached "
                       "and no webhook path exists yet")
    yield


app = FastAPI(title="code-agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "code-agent", "model": MODEL,
            "busy": BUSY.locked()}


@app.post("/telegram/{secret}")
async def telegram(secret: str, request: Request):
    if secret != webhook_secret():
        raise HTTPException(status_code=404, detail="not found")
    update = await request.json()
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    owner = os.environ.get("TELEGRAM_CHAT_ID", "")
    # Owner-only, and silent for everyone else: an error reply confirms the
    # endpoint exists to whoever found it.
    if not text or not owner or chat_id != str(owner):
        return {"ok": True}
    if text.lower() in ("/start", "/help"):
        send("Send me a coding task. I edit a fresh checkout of main, run the "
             "test suite, and push an agent/* branch for you to review. I "
             "never push to main and never merge.")
        return {"ok": True}
    threading.Thread(target=_work, args=(text,), daemon=True).start()
    return {"ok": True}
