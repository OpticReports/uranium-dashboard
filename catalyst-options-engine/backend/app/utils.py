"""Tiny file-backed TTL cache + retry-with-backoff.

Trimmed copies of genomics-alpha-tracker/backend/app/utils/{cache,ratelimit}.py
so this service stays dependency-free of the tracker while keeping the same
politeness toward free public endpoints.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from .config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    root = Path(settings.cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{digest}.json"


def cache_get(key: str, ttl: int | None = None) -> Any | None:
    ttl = settings.cache_ttl_seconds if ttl is None else ttl
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - payload.get("_ts", 0) > ttl:
        return None
    return payload.get("value")


def cache_set(key: str, value: Any) -> None:
    try:
        _cache_path(key).write_text(json.dumps({"_ts": time.time(), "value": value}))
    except (TypeError, OSError):
        pass  # caching is best-effort; never let it break a lane


def cached(key: str, producer: Callable[[], Any], ttl: int | None = None) -> Any:
    hit = cache_get(key, ttl=ttl)
    if hit is not None:
        return hit
    value = producer()
    if value is not None:
        cache_set(key, value)
    return value


def with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_delay: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call fn(), retrying on `exceptions` with exponential backoff (2,4,8s)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except exceptions as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == retries:
                break
            delay = base_delay * (2**attempt)
            logger.warning("Call failed (attempt %d/%d): %s -- retrying in %.0fs",
                           attempt + 1, retries + 1, exc, delay)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
