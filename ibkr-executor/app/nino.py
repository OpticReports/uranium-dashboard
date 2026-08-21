"""Weekly Nino3.4 anomaly from NOAA CPC (keyless). The ladder's arm/kill
signal. Cached 6h; None-degrading (a dead feed blocks ENTRIES, never exits —
the manager treats None as 'cannot arm').

MF-1: this is the FIRST call of every service-loop iteration. It used to be
a 30s timeout whose FAILURES were never cached, so an unreachable NOAA cost
the loop 30s EVERY cycle — and, before the flatten was moved to the top of
the iteration, an emergency /kill flatten waited behind it. The timeout is
now a few seconds and a failure is negative-cached: a dead feed is re-tried
on a schedule, not once per cycle. The stale (or None) value returned on
failure is unchanged.
"""
from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)
_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
FEED_TIMEOUT = 8.0       # MF-1: the loop's cadence (and, in flight, its
                         # emergency stop) may not hang on a weather feed
FAIL_TTL = 900           # MF-1: negative cache — a failing fetch is re-tried
                         # every 15 min at most, never once per cycle. The
                         # datum itself is WEEKLY, so this delays nothing.
_CACHE: dict = {}


def nino34_weekly() -> float | None:
    hit = _CACHE.get("v")
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    failed_at = _CACHE.get("fail")
    if failed_at and time.time() - failed_at < FAIL_TTL:
        # The feed is known-dead and the retry is not due: degrade to the
        # same value the failure path would return, without paying the
        # timeout again (MF-1).
        return hit[1] if hit else None
    try:
        txt = httpx.get(_URL, timeout=FEED_TIMEOUT).text
        last = None
        for ln in txt.splitlines():
            p = ln.split()
            if len(p) == 9:
                try:
                    last = float(p[6])       # Nino3.4 SSTA column
                except ValueError:
                    continue
        if last is not None:
            _CACHE["v"] = (time.time(), last)
            _CACHE.pop("fail", None)
        return last
    except Exception as exc:  # noqa: BLE001
        _CACHE["fail"] = time.time()
        logger.warning("nino fetch failed: %s (retrying in <= %ss)",
                       exc, FAIL_TTL)
        return _CACHE.get("v", (0, None))[1]
