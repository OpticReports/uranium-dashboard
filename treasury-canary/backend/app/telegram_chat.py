"""Two-way Telegram: ask the canary questions, answered by an LLM grounded in
the dashboard's live data.

Flow: Telegram webhook -> chat-id check (only the owner) -> context snapshot
(composite, metric matrix, recent events, rate-path ensemble) -> OpenRouter
chat completion (default moonshotai/kimi-k3, override CHAT_MODEL) -> reply
via the same bot.

Grounding rule mirrors the genomics analyst: the model answers FROM the
supplied snapshot and says so when a datum isn't in it — no invented numbers.

Setup: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (already set for alerts) plus
OPENROUTER_API_KEY. The webhook self-registers on boot using Render's
RENDER_EXTERNAL_URL; the webhook secret is derived from the bot token, so no
extra env is needed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import deque

import httpx

logger = logging.getLogger(__name__)

_OR_URL = "https://openrouter.ai/api/v1/chat/completions"
_HISTORY: deque = deque(maxlen=12)     # alternating user/assistant turns

SYSTEM_PROMPT = """\
You are the Treasury Canary analyst — a fixed-income stress-surveillance \
dashboard's resident quant. The user is the dashboard's owner asking about \
its CURRENT data, which is provided below as a snapshot.

RULES:
- Ground every number in the snapshot. If it isn't there, say "not in my \
current snapshot" rather than guessing.
- Be succinct and direct; Telegram-length answers (a few short paragraphs \
max). No preamble.
- Relational questions are the point: connect metrics, explain WHY a reading \
matters, what historically follows, what would change the picture.
- You are analysis, not advice; skip disclaimers unless genuinely warranted.
"""


def _tok() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def webhook_secret() -> str:
    """Deterministic secret derived from the bot token — Telegram echoes it
    in X-Telegram-Bot-Api-Secret-Token so we can verify update authenticity
    without another env var."""
    return hashlib.sha256(f"canary-webhook:{_tok()}".encode()).hexdigest()[:40]


def register_webhook() -> bool:
    """Called at boot: point Telegram at this service's /telegram/webhook."""
    base = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not (_tok() and base):
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{_tok()}/setWebhook",
                       json={"url": f"{base}/telegram/webhook",
                             "secret_token": webhook_secret(),
                             "allowed_updates": ["message"]}, timeout=15)
        ok = bool(r.json().get("ok"))
        logger.info("telegram webhook registration: %s", r.text[:200])
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram webhook registration failed: %s", exc)
        return False


# ---------- context snapshot ----------

def build_context() -> str:
    """Compact text snapshot of the canary's current state for grounding."""
    parts: list[str] = []
    try:
        from .store.db import session_scope
        from .store.models import EventLog, MetricSnapshot
        from sqlalchemy import select
        with session_scope() as s:
            rows = s.execute(select(MetricSnapshot).order_by(
                MetricSnapshot.asof.desc(), MetricSnapshot.metric_id)).scalars().all()
            seen: dict[str, object] = {}
            for r in rows:
                if r.metric_id not in seen:
                    seen[r.metric_id] = r
            comp = seen.pop("composite", None)
            if comp is not None:
                parts.append(f"COMPOSITE STRESS: {comp.value:.0f}/100 "
                             f"band={comp.status} asof={comp.asof}")
            parts.append("METRICS (id value status d1d d5d d20d):")
            for mid, r in sorted(seen.items()):
                parts.append(f"  {mid}: {r.value} {r.status} "
                             f"{r.delta_1d} {r.delta_5d} {r.delta_20d}")
            evs = s.execute(select(EventLog).order_by(
                EventLog.created_at.desc()).limit(12)).scalars().all()
            if evs:
                parts.append("RECENT EVENTS:")
                for e in evs:
                    parts.append(f"  [{e.severity}] {e.asof} {e.event_type}: "
                                 f"{e.rationale[:200]}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(metric store unavailable: {exc})")
    try:
        from .sources.rate_markets import ensemble
        ens = ensemble()
        parts.append("RATE-PATH ODDS (accuracy-weighted Polymarket+Kalshi):")
        for m in ens.get("meetings", [])[:4]:
            b = m.get("blend") or {}
            parts.append(f"  {m['date']}: " + " ".join(
                f"{k}={v:.0%}" for k, v in b.items()))
        w = ens.get("weights", {})
        parts.append("  source weights: " + ", ".join(
            f"{k} {v['weight']:.0%} (brier {v['brier']}, n={v['n']})"
            for k, v in w.items()))
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(rate ensemble unavailable: {exc})")
    return "\n".join(parts)[:14_000]


# ---------- LLM ----------

def _llm_reply(question: str) -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip().strip('"')
    if not key:
        return ("OPENROUTER_API_KEY isn't set on the canary service — add it "
                "in Render to enable analyst replies.")
    model = os.environ.get("CHAT_MODEL", "moonshotai/kimi-k3")
    messages = [{"role": "system",
                 "content": SYSTEM_PROMPT + "\n\nCURRENT SNAPSHOT:\n" + build_context()}]
    messages += list(_HISTORY)
    messages.append({"role": "user", "content": question})
    try:
        r = httpx.post(_OR_URL, timeout=120,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "messages": messages,
                             "max_tokens": 1200})
        r.raise_for_status()
        reply = r.json()["choices"][0]["message"]["content"] or "(empty reply)"
    except Exception as exc:  # noqa: BLE001
        logger.warning("openrouter chat failed: %s", exc)
        return f"analyst backend error: {exc}"
    _HISTORY.append({"role": "user", "content": question})
    _HISTORY.append({"role": "assistant", "content": reply[:4000]})
    return reply


# ---------- webhook handling ----------

def handle_update(update: dict) -> None:
    """Process one Telegram update: owner's text in -> analyst reply out."""
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    owner = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not text or not owner or chat_id != str(owner):
        return                      # silently ignore non-owner traffic
    from .alerts import send
    if text.lower() in ("/start", "/help"):
        send("I'm the canary analyst. Ask me about the dashboard's current "
             "data — composite stress, any metric, recent events, rate-path "
             "odds — and I'll answer from the live snapshot.")
        return
    send(_llm_reply(text))
