"""Decision feed: GET /carry/target from the paper engine. Read-only."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def btc_executor_ready(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    """The BTC executor must value spot tokens in equity BEFORE the sleeve
    swaps USDC into UETH, or it reads the swap as a -$30k day and halts the
    BTC book (review 2026-10-01 SERIOUS-3). Unknown = not ready."""
    try:
        r = httpx.get(f"{url.rstrip('/')}/pulse", timeout=timeout)
        r.raise_for_status()
        d = r.json()
    except Exception as exc:  # noqa: BLE001
        return False, f"btc-executor /pulse unreadable ({exc}) - not opening"
    if d.get("equity_counts_spot_tokens") is True:
        return True, "btc-executor values spot tokens"
    return False, (f"btc-executor build {d.get('build')} does not value spot "
                   f"tokens in equity - deploy it before opening")


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
