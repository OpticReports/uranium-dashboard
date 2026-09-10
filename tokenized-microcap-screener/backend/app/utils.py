"""Small shared helpers: file cache + retry, matching the sibling services."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")


def utcnow_ms() -> int:
    return int(time.time() * 1000)


def with_backoff(fn: Callable[[], T], attempts: int = 3, base: float = 0.6) -> T:
    """Retry with exponential backoff. Re-raises the last error."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1:
                time.sleep(base * (2 ** i))
    raise last  # type: ignore[misc]


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return Path(settings.cache_dir) / f"{digest}.json"


def cached(key: str, producer: Callable[[], Any], ttl: int) -> Any:
    """Read-through file cache. A stale entry is served if the producer fails,
    so a lane that goes dark degrades to last-known rather than to nothing."""
    path = _cache_path(key)
    now = time.time()
    stale: Any = None
    if path.exists():
        try:
            blob = json.loads(path.read_text())
            if now - blob["at"] < ttl:
                return blob["value"]
            stale = blob["value"]
        except Exception:  # noqa: BLE001
            stale = None
    try:
        value = producer()
    except Exception:  # noqa: BLE001
        if stale is not None:
            logger.warning("cache MISS + producer failed for %s; serving stale", key)
            return stale
        raise
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": now, "value": value}))
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache write failed for %s: %s", key, exc)
    return value


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))
