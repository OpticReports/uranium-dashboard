"""Telegram alerts for canary events — fire-and-forget, never blocks refresh.

Same bot as the executor's (one bot, one chat, two services): set
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID on this service too. Unset = no-op.
TELEGRAM_MIN_SEVERITY (default WARN) filters which events reach the phone:
WARN covers rate-path probability shifts; RED/CRITICAL covers metric flips,
band crossings and re-steepening alarms.
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)

_RANK = {"INFO": 0, "WARN": 1, "RED": 2, "CRITICAL": 3}
_ICON = {"WARN": "🟡", "RED": "🔴", "CRITICAL": "🚨"}


def min_severity() -> str:
    return os.environ.get("TELEGRAM_MIN_SEVERITY", "WARN").upper()


def should_send(severity: str) -> bool:
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and
            os.environ.get("TELEGRAM_CHAT_ID")):
        return False
    return _RANK.get(severity.upper(), 0) >= _RANK.get(min_severity(), 1)


def send(text: str) -> None:
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


def format_event(event_type: str, severity: str, rationale: str) -> str:
    icon = _ICON.get(severity.upper(), "ℹ️")
    return f"{icon} canary {event_type} [{severity}]\n{rationale}"
