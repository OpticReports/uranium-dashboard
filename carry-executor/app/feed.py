"""Decision feed: GET /carry/target from the paper engine. Read-only."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def get_carry_target(base_url: str, token: str = "", timeout: float = 20.0) -> dict | None:
    try:
        headers = {"X-Exec-Token": token} if token else {}
        r = httpx.get(f"{base_url.rstrip('/')}/carry/target", headers=headers,
                      timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("carry target fetch failed: %s", exc)
        return None
