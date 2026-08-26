"""Telegram alerts — fire-and-forget, never blocks or breaks the engine.

Same Canary Optics bot as btc-executor (setup steps documented in
btc-executor/app/alerts.py). Render env: add the same TELEGRAM_BOT_TOKEN +
TELEGRAM_CHAT_ID to the btc-paper-engine service. Unset env -> silent no-op
(the engine and monitor run fine without alerting).
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)


def send(text: str) -> None:
    """Send asynchronously; drop on any failure (alerting must never be able
    to take down or delay the engine)."""
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
