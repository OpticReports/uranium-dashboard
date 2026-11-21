"""FRED source — the backbone. Cached, backed off, and gracefully degrading.

No key -> returns empty and logs (the dashboard shows those metrics STALE rather
than crashing). Observations are (date, value|None); FRED's "." missing marker
maps to None so gaps never masquerade as zero.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _cache_path(series_id: str, start: str) -> str:
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, f"fred_{series_id}_{start}.json")


# FRED uses HTTP 400 BOTH for "series doesn't exist" AND for a bad/unregistered
# api_key. Conflating them once turned an invalid key on a fresh deploy into 33
# silently-STALE metrics while /health said fred_key_present=true. A detected
# key error is recorded here and surfaced by /health and /refresh.
_key_error: dict[str, str | None] = {"msg": None}


def fred_key_error() -> str | None:
    """The last detected FRED api_key error, or None once a call succeeds."""
    return _key_error["msg"]


# Series currently served from an old disk copy because their last FRED call failed
# (series id -> copy age in hours). Cleared per series on its next successful fetch;
# surfaced by /health and /refresh so a stale-but-plausible dashboard never looks live.
_stale_served: dict[str, float] = {}


def fred_stale_series() -> dict[str, float]:
    return dict(sorted(_stale_served.items()))


# Circuit breaker: after _BREAKER_FAILS consecutive network/server failures FRED is treated as
# down for _BREAKER_SECONDS and calls fail fast (served from the disk copy or empty). Without it
# a bundle rebuild during an outage waits out 4 tries x 30 s for each of ~89 series while every
# request holding the expired bundle waits on its lock. A 400 (bad key / no series) is not counted.
_BREAKER_FAILS = 5
_BREAKER_SECONDS = 600
_breaker: dict[str, float] = {"fails": 0, "open_until": 0.0}
_breaker_lock = threading.Lock()


def _get_with_backoff(params: dict, tries: int = 4) -> dict | None:
    if time.time() < _breaker["open_until"]:
        return None
    delay = 1.0
    for attempt in range(tries):
        try:
            r = httpx.get(_BASE, params=params, timeout=settings.http_timeout_seconds)
            if r.status_code == 400:
                body = r.text[:200]
                if "api_key" in body:
                    _key_error["msg"] = body
                    logger.error(
                        "FRED REJECTED THE API KEY (not a missing series) — every "
                        "FRED-based metric will be STALE until FRED_API_KEY is fixed: %s",
                        body)
                else:
                    logger.warning("FRED 400 for %s (series may not exist): %s",
                                   params.get("series_id"), body)
                return None
            r.raise_for_status()
            _key_error["msg"] = None  # a successful call proves the key works
            with _breaker_lock:
                _breaker["fails"] = 0
            return r.json()
        except Exception as exc:  # noqa: BLE001
            if attempt == tries - 1:
                logger.warning("FRED fetch failed for %s: %s", params.get("series_id"), exc)
                with _breaker_lock:
                    _breaker["fails"] += 1
                    if _breaker["fails"] >= _BREAKER_FAILS:
                        _breaker["open_until"] = time.time() + _BREAKER_SECONDS
                        logger.warning("FRED looks down (%d failures in a row): failing fast for %d s",
                                       _breaker["fails"], _BREAKER_SECONDS)
                return None
            time.sleep(delay)
            delay *= 2
    return None


def _splice_frozen(series_id: str, dates, values):
    """Prepend frozen pre-truncation history for the ICE series FRED cut in
    April 2026. No-op for every other series. See sources/ice_reference.py."""
    from .ice_reference import splice
    return splice(series_id, list(dates), list(values))


def fetch_series(
    series_id: str, start: str = "1976-01-01", use_cache: bool = True
) -> tuple[list[date], list[float | None]]:
    """Return (dates, values) for a FRED series. A failed call serves the last good disk
    copy if it is younger than fred_stale_max_age_hours (recorded in _stale_served);
    empty on a missing or rejected key, or when no usable copy exists."""
    if not settings.fred_api_key:
        logger.info("FRED_API_KEY not set — skipping %s (metric will show STALE)", series_id)
        return [], []

    cache = _cache_path(series_id, start)
    if use_cache and os.path.exists(cache):
        age = time.time() - os.path.getmtime(cache)
        if age < settings.cache_ttl_seconds:
            try:
                raw = json.load(open(cache))
                return _splice_frozen(series_id, *_parse(raw))
            except Exception:  # noqa: BLE001
                pass

    data = _get_with_backoff({
        "series_id": series_id, "api_key": settings.fred_api_key,
        "file_type": "json", "observation_start": start,
    })
    if data is not None and not data.get("observations"):
        logger.warning("FRED returned no observations for %s; keeping the disk copy", series_id)
        data = None                        # never overwrite a good copy with an empty reply
    if data is None:
        # A failed call (rate limit, outage) must not turn a series EMPTY while a recent
        # good copy sits on disk: the bundle below is memoized for hours, so one bad call
        # used to wipe the NBER bands and the fitted recession model until the next
        # restart (2026-11-21). But a rejected key is a configuration error: fail loudly
        # (every FRED metric STALE), never mask it with old copies; and past the age cap
        # an old copy goes empty too. What is served stale is listed (fred_stale_series).
        if _key_error["msg"]:
            return [], []
        stale = _read_cache(cache)
        if stale is not None:
            age_h = (time.time() - os.path.getmtime(cache)) / 3600
            if age_h <= settings.fred_stale_max_age_hours:
                _stale_served[series_id] = round(age_h, 1)
                logger.warning("FRED fetch failed for %s; serving the last good copy (%.1f h old)",
                               series_id, age_h)
                return _splice_frozen(series_id, *_parse(stale))
            logger.warning("FRED fetch failed for %s; the disk copy is %.0f h old (cap %d h), "
                           "so the series is left empty", series_id, age_h, settings.fred_stale_max_age_hours)
        return [], []
    _stale_served.pop(series_id, None)
    try:
        from .fred_csv import _write_atomic          # temp file + rename: a crash mid-write keeps the old copy
        _write_atomic(cache, json.dumps(data))
    except Exception:  # noqa: BLE001
        pass
    return _splice_frozen(series_id, *_parse(data))


def _read_cache(path: str) -> dict | None:
    """The cached FRED JSON at `path`, any age, or None (absent or unreadable)."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        return raw if isinstance(raw, dict) and raw.get("observations") else None
    except Exception:  # noqa: BLE001
        return None


def _parse(data: dict) -> tuple[list[date], list[float | None]]:
    dates: list[date] = []
    vals: list[float | None] = []
    for obs in data.get("observations", []):
        try:
            d = datetime.strptime(obs["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        raw = obs.get("value", ".")
        try:
            v = None if raw in (".", "", None) else float(raw)
        except ValueError:
            v = None
        dates.append(d)
        vals.append(v)
    return dates, vals


# In-process cache of the assembled bundle. Every API endpoint calls fetch_bundle,
# and the browser fires several at once — without this, each request re-fetches ~25
# FRED series, a thundering herd that times out / OOMs a small (free-tier) instance.
# A lock serializes the cold fetch so concurrent callers share ONE network pass.
_BUNDLE_TTL_SECONDS = 6 * 3600  # data is EOD/daily; a few hours stale is fine
_DEGRADED_TTL_SECONDS = 15 * 60  # a bundle with a FRED series missing retries soon
_bundle_cache: dict[str, object] = {"ts": 0.0, "data": None, "degraded": False}
_bundle_lock = threading.Lock()


def fetch_bundle(start: str = "1976-01-01", force: bool = False
                 ) -> dict[str, tuple[list[date], list[float | None]]]:
    """Fetch the full FRED catalog into one logical-keyed bundle (memoized).

    Keys are provider-agnostic (tenor labels, "sofr", "hy_oas", ...). Missing or rejected
    key, or a failed series with no recent disk copy -> that entry is ([], []) and its
    metrics render STALE (a failed series with a recent copy is served from it and listed
    by fred_stale_series()). A good series is never replaced by an empty one.
    """
    cached = _bundle_cache["data"]
    if not force and cached is not None and _bundle_fresh():
        return cached  # type: ignore[return-value]
    with _bundle_lock:
        # double-check: another thread may have populated it while we waited
        cached = _bundle_cache["data"]
        if not force and cached is not None and _bundle_fresh():
            return cached  # type: ignore[return-value]
        bundle = _fetch_bundle_uncached(start)
        prev = cached or {}
        holes = [k for k in _fred_plan() if not (bundle.get(k) or ([], []))[0]]
        kept = [k for k in holes if (prev.get(k) or ([], []))[0]]   # type: ignore[union-attr]
        for k in kept:                     # never swap a good series for an empty one
            bundle[k] = prev[k]            # type: ignore[index]
        missing = [k for k in holes if k not in kept]
        if holes:
            logger.warning("FRED bundle: %d series failed (kept the previous copy of %s; "
                           "still missing %s)", len(holes), kept or "none", missing or "none")
        _bundle_cache["data"] = bundle
        _bundle_cache["ts"] = time.time()
        _bundle_cache["degraded"] = bool(missing)
        return bundle


def _bundle_fresh() -> bool:
    ttl = _DEGRADED_TTL_SECONDS if _bundle_cache.get("degraded") else _BUNDLE_TTL_SECONDS
    return time.time() - float(_bundle_cache["ts"]) < ttl  # type: ignore[arg-type]


def _fred_plan() -> dict[str, str]:
    """logical bundle key -> FRED series id (the series fetch_series supplies)."""
    from ..config import (
        FRED_BREAKEVENS, FRED_CREDIT, FRED_DISTRESS, FRED_FLOWS, FRED_FOREIGN,
        FRED_FUNDING, FRED_LABOR, FRED_LEADING, FRED_MACRO, FRED_PINS,
        FRED_REAL_YIELDS, FRED_SEVERITY, FRED_TENORS, FRED_VOL,
    )
    plan: dict[str, str] = dict(FRED_TENORS)
    for extra in (FRED_LABOR, FRED_FLOWS, FRED_LEADING, FRED_PINS, FRED_FOREIGN,
                  FRED_SEVERITY, FRED_DISTRESS):
        for k, sid in extra.items():
            plan[k] = sid
    plan["real_10y"] = FRED_REAL_YIELDS["10y"]
    plan["breakeven_5y5y"] = FRED_BREAKEVENS["5y5y"]
    for k in ("sofr", "effr", "iorb"):
        plan[k] = FRED_FUNDING[k]
    plan["vix"] = FRED_VOL["vix"]
    plan["hy_oas"] = FRED_CREDIT["hy_oas"]
    plan["ig_oas"] = FRED_CREDIT["ig_oas"]
    plan["sp500"] = FRED_MACRO["sp500"]
    plan["nfci"] = FRED_MACRO["nfci"]
    plan["acm_tp10"] = FRED_MACRO["acm_tp10"]
    plan["recession"] = FRED_MACRO["recession"]
    return plan


def _fetch_bundle_uncached(start: str) -> dict[str, tuple[list[date], list[float | None]]]:
    from concurrent.futures import ThreadPoolExecutor

    plan = _fred_plan()                    # logical key -> FRED series id

    # Fetch concurrently — ~25 sequential FRED calls would be slow on a cold
    # instance; the disk cache + this pool keep the cold path to a few seconds.
    def _one(item):
        key, sid = item
        return key, fetch_series(sid, start)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(_one, plan.items())
    bundle = {key: series for key, series in results}
    # Non-FRED series ride along in the same bundle (each gracefully []).
    from .cftc import fetch_lev_net_short
    from .finra_margin import fetch_margin_stats
    from .fmp import fetch_gold
    from .ofr import fetch_fsi
    bundle["gold"] = fetch_gold()
    bundle["ofr_fsi"] = fetch_fsi()
    bundle["cot_net_short"] = fetch_lev_net_short()
    bundle.update(fetch_margin_stats())
    from .household_debt import extend_household_debt
    before = bundle.get("hh_debt_gdp", ([], []))
    bundle["hh_debt_gdp"] = extend_household_debt(
        before, bundle.get("hh_debt_z1", ([], [])), bundle.get("gdp", ([], [])))
    if before[0] and bundle["hh_debt_gdp"][0][0] == before[0][0]:
        logger.warning("household debt/GDP: Z.1 back-extension unavailable (CMDEBT or GDP "
                       "missing) — severity ranks it against 2008+ only")
    return bundle


def recession_start_dates(dates: list[date], usrec: list[float | None]) -> list[date]:
    """First day of each USREC==1 run (NBER recession onsets) for chart annotation."""
    starts: list[date] = []
    prev = 0.0
    for d, v in zip(dates, usrec):
        cur = v or 0.0
        if cur == 1.0 and prev != 1.0:
            starts.append(d)
        prev = cur
    return starts
