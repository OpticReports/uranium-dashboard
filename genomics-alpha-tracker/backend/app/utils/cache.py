"""Tiny file-backed response cache with TTL.

Per-API caching to respect free-tier limits. Keyed by a caller-supplied string;
values are JSON-serializable. Not concurrency-hardened (single-process scheduler
+ API is the target), but safe enough for that.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..config import settings


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    root = Path(settings.cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{digest}.json"


def get(key: str, ttl: int | None = None) -> Any | None:
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


def set(key: str, value: Any) -> None:
    path = _cache_path(key)
    try:
        path.write_text(json.dumps({"_ts": time.time(), "value": value}))
    except (TypeError, OSError):
        # Caching is best-effort; never let it break ingestion.
        pass


def cached(key: str, producer, ttl: int | None = None) -> Any:
    """Return cached value for key or call producer() and cache the result."""
    hit = get(key, ttl=ttl)
    if hit is not None:
        return hit
    value = producer()
    if value is not None:
        set(key, value)
    return value
