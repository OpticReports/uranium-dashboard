"""Total-deadline wrapper for the executor's two read-only feeds.

MF-A: `httpx.get(url, timeout=T)` sets PER-OPERATION timeouts (connect,
read, write, pool) — it is NOT a bound on the call. A server that emits one
chunk every T/2 seconds keeps every individual read comfortably inside T
while the whole fetch runs arbitrarily long. Measured against a local
4s-per-chunk trickle server with FEED_TIMEOUT at 8.0: `nino34_weekly()`
took 32.09s, and an in-flight kill->flatten took 31.57s. Only a SILENT
socket honours the per-operation cap (7.58s). The loop's cadence — and,
when a cycle is in flight, how long an operator waits for the emergency
stop — is set by these two calls, so the CALLER needs a bound the transport
does not give it.

`with_deadline` is that bound: the fetch runs on a daemon worker and the
caller waits at most `deadline_s` for it, whatever the socket does. The
per-operation timeout stays on the request underneath, so an abandoned
worker ends as soon as one read exceeds it. A server that trickles FOREVER
keeps one daemon thread alive per RE-TRY, which both feeds' negative caches
limit to one per FAIL_TTL — that residual is stated in README §6 rather
than pretended away. What is bounded is what matters: the loop, and the
emergency stop behind it, never wait longer than the deadline.
"""
from __future__ import annotations

import threading


class FeedDeadline(Exception):
    """The whole fetch did not finish inside its total deadline."""


def with_deadline(deadline_s: float, fn, *args, **kwargs):
    """Run `fn(*args, **kwargs)`, returning its result, and give the CALLER
    a hard bound of `deadline_s` seconds. Raises FeedDeadline if the
    deadline passes first (the worker is abandoned, never joined again);
    re-raises whatever `fn` raised otherwise."""
    box: dict = {}

    def _run() -> None:
        try:
            box["v"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            box["exc"] = exc

    t = threading.Thread(target=_run, daemon=True, name="feed-fetch")
    t.start()
    t.join(deadline_s)
    if t.is_alive():
        raise FeedDeadline(f"the fetch exceeded its {deadline_s}s TOTAL "
                           f"deadline (a per-operation timeout does not "
                           f"bound a trickling server)")
    if "exc" in box:
        raise box["exc"]
    return box["v"]
