"""Signal feed: pulls /exec/target from the paper engine. Read-only."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class EngineFeed:
    def __init__(self, base_url: str, token: str = "", timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def get_target(self) -> dict | None:
        try:
            headers = {"X-Exec-Token": self.token} if self.token else {}
            r = httpx.get(f"{self.base_url}/exec/target", headers=headers,
                          timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("engine feed failed: %s", exc)
            return None
