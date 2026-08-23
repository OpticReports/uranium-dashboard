"""Two-way Telegram triage for the live BTC stack — ask it what a page means.

A 3am RED alert tells you something broke; it doesn't tell you whether it's
the known drift false-positive, a real mirror divergence, or a halt you have
to act on. This answers that question from LIVE state, on a provider that
bills separately from any one AI subscription — so triage survives a usage
window lapsing on the primary.

Flow: Telegram webhook -> owner chat-id check -> snapshot (this engine's
books + the executor's PUBLIC /pulse + watchdog conditions) -> OpenRouter
chat completion -> reply.

WHAT IT IS NOT (deliberate, and enforced by gate tests):
- Not in any alert path. The watchdog pages by itself, deterministically,
  with no model involved. This module only EXPLAINS after the fact; if it
  is down, broken, or unfunded, every page still fires.
- Not in any trade path. It lives on the keyless engine, reads a public
  endpoint, and has no order surface at all. It cannot halt, resume, size,
  enter or exit anything. Its entire output is text sent to one chat id.
- Not authoritative. It reads the same snapshot you can read; it can be
  wrong. Numbers it quotes are only as good as the snapshot, and the rules
  below force it to say when a datum isn't there.

SEPARATE BOT REQUIRED: Telegram allows exactly ONE webhook per bot. The
alert bot's token (TELEGRAM_BOT_TOKEN) is already used for one-way pages and
another service in this monorepo may own its webhook — registering this one
on the same token would silently steal it. So triage takes its own bot
(TRIAGE_BOT_TOKEN from BotFather) and refuses to start on the alert token.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import deque

import httpx

logger = logging.getLogger(__name__)

_OR_URL = "https://openrouter.ai/api/v1/chat/completions"
_HISTORY: deque = deque(maxlen=12)     # alternating user/assistant turns

SYSTEM_PROMPT = """\
You are the triage analyst for a live BTC trading stack. The owner is asking \
about its CURRENT state, supplied below as a snapshot.

THE STACK (fixed facts, use them):
- btc-paper-engine: keyless strategy brain. Books S3 (pullback) and S4 \
(Donchian trend) run at 1x; S5 is the live blend, 75% S3 / 25% S4 at 1.5x.
- btc-executor: the only service holding venue credentials. It MIRRORS the \
engine's book state onto Coinbase dated futures. Protective stops are REAL \
resting venue orders, so they survive the executor being down.
- The mirror confirms a position only AFTER the engine closes its 4h bar, so \
engine and executor legitimately disagree for a short handoff window. A \
disagreement that persists past that is a real problem.
- Coverage/ramp: KELLY_M advances only when the RAMP v4 event matrix is \
complete; counts require live-mode provenance.

RULES:
- Ground every number in the snapshot. If it isn't there, say "not in my \
current snapshot" rather than guessing.
- Be succinct and direct; Telegram-length answers. No preamble.
- When asked about an alert, say plainly: is this benign, worth watching, or \
action-needed — and what the owner should actually look at.
- You are analysis, not advice, and you are NOT the safety system: the \
watchdog and the executor's own rails page independently of you. Never imply \
a page can be dismissed because you think it looks fine.
- You cannot take any action. If asked to halt, resume, trade or change \
config, say so and point at the executor's own token-gated endpoints.
"""


def _tok() -> str:
    """The triage bot's OWN token — never the alerting bot's."""
    return (os.environ.get("TRIAGE_BOT_TOKEN") or "").strip()


def _owner() -> str:
    return (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()


def enabled() -> bool:
    alert_tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    tok = _tok()
    if not tok or not _owner():
        return False
    if alert_tok and tok == alert_tok:
        # one webhook per bot: registering here would steal the alert bot's
        # webhook from whichever service owns it
        logger.error("triage disabled: TRIAGE_BOT_TOKEN must be a SEPARATE "
                     "bot from TELEGRAM_BOT_TOKEN (Telegram allows one "
                     "webhook per bot)")
        return False
    return True


def webhook_secret() -> str:
    """Deterministic secret derived from the bot token — Telegram echoes it in
    X-Telegram-Bot-Api-Secret-Token so update authenticity is verifiable
    without another env var. Salt differs per service so two services can
    never validate each other's updates."""
    return hashlib.sha256(f"btc-triage-webhook:{_tok()}".encode()).hexdigest()[:40]


def register_webhook() -> bool:
    """Called at boot: point Telegram at this service's /triage/webhook."""
    base = (os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not (enabled() and base):
        return False
    try:
        r = httpx.post(f"https://api.telegram.org/bot{_tok()}/setWebhook",
                       json={"url": f"{base}/triage/webhook",
                             "secret_token": webhook_secret(),
                             "allowed_updates": ["message"]}, timeout=15)
        ok = bool(r.json().get("ok"))
        logger.info("triage webhook registration ok=%s", ok)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage webhook registration failed: %s", exc)
        return False


def _reply(text: str) -> None:
    """Answer on the TRIAGE bot, not the alert bot — so a chatty triage
    thread can never crowd or impersonate an alert."""
    tok = _tok()
    if not tok or not _owner():
        return
    try:
        httpx.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                   json={"chat_id": _owner(), "text": text[:4000]}, timeout=15)
    except Exception as exc:  # noqa: BLE001
        logger.warning("triage reply failed: %s", exc)


# ---------- context snapshot (read-only) ----------

def build_context(book_state=None, pulse_url: str | None = None,
                  watchdog=None) -> str:
    """Compact snapshot for grounding: our books, the executor's public
    pulse, and the watchdog's open conditions. Every section degrades
    independently — a dead section says so instead of sinking the reply."""
    parts: list[str] = []
    try:
        books = (book_state() if book_state else {}) or {}
        parts.append("ENGINE BOOKS:")
        for name in ("S3", "S4", "S5"):
            b = books.get(name)
            if not isinstance(b, dict):
                continue
            pos = b.get("position")
            parts.append(
                f"  {name}: state={b.get('state')} equity={b.get('equity')} "
                f"trades={b.get('trades')} win_rate={b.get('win_rate')} "
                f"PF={b.get('profit_factor')} maxDD={b.get('max_dd_pct')} "
                f"unrealized={b.get('unrealized')}")
            if pos:
                parts.append(f"    position: side={pos.get('side')} "
                             f"entry={pos.get('entry_price')} "
                             f"qty={pos.get('qty')} stop={pos.get('stop_price')}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(engine books unavailable: {exc})")

    try:
        r = httpx.get(pulse_url, timeout=10)
        r.raise_for_status()
        parts.append("EXECUTOR PULSE (public): " + json.dumps(r.json())[:2000])
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(executor pulse unreachable: {exc} — if the watchdog "
                     "has also paged executor_silent, the executor is likely "
                     "down; venue stops still protect open positions)")

    try:
        if watchdog is not None:
            openk = sorted(getattr(watchdog, "open", {}))
            parts.append("WATCHDOG open conditions: "
                         + (", ".join(openk) if openk else "none"))
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(watchdog state unavailable: {exc})")

    try:
        from sqlalchemy import select
        from .store.db import EventRow, session_scope
        with session_scope() as s:
            evs = s.execute(select(EventRow).order_by(
                EventRow.ts.desc()).limit(15)).scalars().all()
            if evs:
                parts.append("RECENT ENGINE EVENTS:")
                for e in evs:
                    parts.append(f"  [{e.level}] {e.ts} {e.book} {e.event}: "
                                 f"{(e.detail or '')[:180]}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(engine event log unavailable: {exc})")

    return "\n".join(parts)[:14_000]


# ---------- LLM ----------

def _llm_reply(question: str, context: str) -> str:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip().strip('"')
    if not key:
        return ("OPENROUTER_API_KEY isn't set on btc-paper-engine — add it in "
                "Render to enable triage replies. (Alerting is unaffected: "
                "the watchdog pages without any model.)")
    model = (os.environ.get("TRIAGE_CHAT_MODEL") or "").strip()
    if not model:
        return ("TRIAGE_CHAT_MODEL isn't set on btc-paper-engine — set it to "
                "the OpenRouter model slug you want triage answered by.")
    messages = [{"role": "system",
                 "content": SYSTEM_PROMPT + "\n\nCURRENT SNAPSHOT:\n" + context}]
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
        logger.warning("triage backend failed: %s", exc)
        return (f"triage backend error: {exc}\n\n(Alerting is unaffected — "
                "the watchdog and the executor's rails page without a model.)")
    _HISTORY.append({"role": "user", "content": question})
    _HISTORY.append({"role": "assistant", "content": reply[:4000]})
    return reply


# ---------- webhook handling ----------

HELP = ("BTC triage. Ask about live state — book positions, what a RED page "
        "means, whether engine and executor agree, ramp coverage. I read the "
        "engine's books, the executor's public pulse and the watchdog's open "
        "conditions.\n\nI cannot trade, halt or resume anything, and I am not "
        "the safety system: pages fire without me.")


def handle_update(update: dict, book_state=None, pulse_url: str | None = None,
                  watchdog=None) -> None:
    """One Telegram update: owner's text in -> grounded reply out.

    Non-owner traffic is dropped silently. Anything a stranger could get in
    here is untrusted text, and it reaches only a model whose sole output is
    a message back to the owner's own chat — there is no tool, order or
    config surface behind it.
    """
    msg = update.get("message") or {}
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    if not text or not _owner() or chat_id != _owner():
        return
    if text.lower() in ("/start", "/help"):
        _reply(HELP)
        return
    ctx = build_context(book_state, pulse_url, watchdog)
    _reply(_llm_reply(text, ctx))


def start_triage(cfg, book_state, watchdog=None) -> bool:
    """Register the webhook off-thread at boot. Returns False when disabled."""
    if not enabled():
        return False

    def _go():
        try:
            register_webhook()
        except Exception as exc:  # noqa: BLE001
            logger.warning("triage start failed: %s", exc)

    threading.Thread(target=_go, daemon=True).start()
    return True
