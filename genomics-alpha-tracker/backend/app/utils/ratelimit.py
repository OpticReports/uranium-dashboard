"""Rate limiting + retry with exponential backoff for HTTP calls."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimiter:
    """Simple sliding-window limiter: at most `max_calls` per `period` seconds."""

    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            sleep_for = self.period - (now - self._calls[0])
            if sleep_for > 0:
                logger.debug("Rate limit hit, sleeping %.2fs", sleep_for)
                time.sleep(sleep_for)
        self._calls.append(time.monotonic())


def with_backoff(
    fn: Callable[[], T],
    *,
    retries: int = 4,
    base_delay: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Call fn(), retrying on `exceptions` with exponential backoff (2,4,8,16s)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except exceptions as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == retries:
                break
            delay = base_delay * (2**attempt)
            logger.warning(
                "Call failed (attempt %d/%d): %s -- retrying in %.0fs",
                attempt + 1,
                retries + 1,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
