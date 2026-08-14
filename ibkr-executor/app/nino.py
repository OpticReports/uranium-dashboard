"""Weekly Nino3.4 anomaly from NOAA CPC (keyless). The ladder's arm/kill
signal. Cached 6h; None-degrading (a dead feed blocks ENTRIES, never exits —
the manager treats None as 'cannot arm')."""
from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)
_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
_CACHE: dict = {}


def nino34_weekly() -> float | None:
    hit = _CACHE.get("v")
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    try:
        txt = httpx.get(_URL, timeout=30).text
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
        return last
    except Exception as exc:  # noqa: BLE001
        logger.warning("nino fetch failed: %s", exc)
        return _CACHE.get("v", (0, None))[1]
