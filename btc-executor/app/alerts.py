"""Telegram alerts — fire-and-forget, never blocks or breaks the trade loop.

Setup (one-time, user side):
  1. In Telegram, message @BotFather -> /newbot -> name it -> copy the token.
  2. Message your new bot anything (opens the chat).
  3. GET https://api.telegram.org/bot<TOKEN>/getUpdates -> read chat.id.
  4. Render env: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID on btc-executor.
Unset env -> module is a silent no-op.
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)


def send(text: str) -> None:
    """Send asynchronously; drop on any failure (alerting must never be able
    to take down or delay the executor)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return

    def _post():
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": chat, "text": text[:4000]}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram send failed: %s", exc)

    threading.Thread(target=_post, daemon=True).start()
