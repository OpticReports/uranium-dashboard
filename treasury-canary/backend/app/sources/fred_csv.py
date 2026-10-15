"""Keyless FRED CSV fetcher (fredgraph.csv) plus the shared cached-download
primitive the AI-debt flow sources ride on.

Why a second FRED path next to sources/fred.py: the API there needs
FRED_API_KEY, and the AI-debt tab is built on free, keyless sources only
(BUILD.md). https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES serves
the full history of any public series without a key; FRED's "." missing
marker maps to None so gaps never masquerade as zero.

Degradation contract (same as every ride-along source): a failed fetch
returns the last cached copy, however old, and the series is marked "stale";
no cache and no network -> ([], []) marked "error". Nothing here raises on a
network problem. A FRED 404 (unknown series) is an HTML page, never cached.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
from datetime import date, datetime
from typing import Callable, Iterable

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_TTL = 12 * 3600          # FRED data is daily at best; twice-daily refresh is plenty
_TRIES = 2                # a dead FRED must not block the warm job for 30 min (60 series x 3 x 30 s)
_FRED_TIMEOUT = 10.0      # per request, fredgraph.csv only; the big file downloads keep the settings timeout

# series_id -> "ok" | "stale" | "error" for the last fetch_csv call; the route
# layer reports these per block so a quietly-stale panel is never shown as ok.
_status: dict[str, str] = {}
_status_lock = threading.Lock()


def status(series_id: str) -> str | None:
    """Outcome of the last fetch_csv for this series ("ok"/"stale"/"error")."""
    return _status.get(series_id)


def _set_status(key: str, value: str) -> None:
    with _status_lock:
        _status[key] = value


def url(series_id: str, start: str | None = None) -> str:
    """The fredgraph.csv URL for a series (the citation the payload carries)."""
    u = f"{_BASE}?id={series_id}"
    return f"{u}&cosd={start}" if start else u


def _cache_path(name: str) -> str:
    os.makedirs(settings.cache_dir, exist_ok=True)
    return os.path.join(settings.cache_dir, name)


def _get_with_backoff(u: str, headers: dict | None = None,
                      timeout: float | None = None) -> httpx.Response | None:
    """GET with exponential backoff. None on exhaustion or a non-2xx status
    (FRED answers an unknown id with a 404 HTML page; that is a failure, not
    data, and must not be cached as if it were)."""
    delay = 1.0
    for attempt in range(_TRIES):
        try:
            r = httpx.get(u, headers=headers, timeout=timeout or settings.http_timeout_seconds,
                          follow_redirects=True)
            if r.status_code == 404:
                logger.warning("404 for %s (series/file may not exist)", u)
                return None
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            if attempt == _TRIES - 1:
                logger.warning("fetch failed for %s: %s", u, exc)
                return None
            time.sleep(delay)
            delay *= 2
    return None


# ---------------------------------------------------------------------------
# Shared cached download (bytes). Used by tic.py (CSLT zip), boj_mof.py (BoJ
# zip, MOF csv) and treasury_supply.py (MSPD json, ACM xls).
# ---------------------------------------------------------------------------
def _http_get_bytes(u: str, headers: dict | None = None) -> bytes | None:
    r = _get_with_backoff(u, headers)
    return r.content if r is not None else None


def _write_atomic(path: str, data: bytes | str) -> None:
    """Write via a private temp file + os.replace. The temp name is unique per
    writer (mkstemp), so two threads refreshing the same key never share a
    half-written file that one of them could os.replace into place."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=os.path.basename(path) + ".")
    try:
        if isinstance(data, str):
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
        else:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parses(fn: Callable[[bytes], object]) -> Callable[[bytes], bool]:
    """A download_cached `validate` built from a parser: the body is accepted
    only if `fn(body)` returns without raising and yields something truthy, so
    an HTML error/maintenance page (or a format drift) can never replace the
    last good cached copy — the stale-on-error contract stays recoverable."""
    def _ok(body: bytes) -> bool:
        try:
            return bool(fn(body))
        except Exception:  # noqa: BLE001
            return False
    return _ok


def download_cached(name: str, u: str, ttl_seconds: int, headers: dict | None = None,
                    validate: Callable[[bytes], bool] | None = None,
                    use_cache: bool = True) -> tuple[bytes | None, str]:
    """(bytes, status) for a keyless download kept under settings.cache_dir.

    Fresh cache (younger than ttl) -> ("ok"). Otherwise fetch; a body that
    fails `validate` (e.g. an HTML error page where a CSV was expected) counts
    as a failed fetch and is NOT written over the cache. On failure the old
    cache, any age, is returned as "stale"; with nothing cached -> (None, "error")."""
    path = _cache_path(name)
    if use_cache and os.path.exists(path):
        if time.time() - os.path.getmtime(path) < ttl_seconds:
            try:
                return open(path, "rb").read(), "ok"
            except Exception:  # noqa: BLE001
                pass
    body = _http_get_bytes(u, headers)
    if body is not None and validate is not None and not validate(body):
        logger.warning("%s: body failed validation (%d bytes); not cached", name, len(body))
        body = None
    if body is not None:
        try:
            _write_atomic(path, body)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not cache %s: %s", name, exc)
        return body, "ok"
    if os.path.exists(path):
        try:
            logger.warning("%s: fetch failed — serving stale cache from %s", name,
                           datetime.fromtimestamp(os.path.getmtime(path)).date())
            return open(path, "rb").read(), "stale"
        except Exception:  # noqa: BLE001
            pass
    return None, "error"


# ---------------------------------------------------------------------------
# FRED CSV
# ---------------------------------------------------------------------------
_HEADER_RE = re.compile(r"^(observation_date|DATE),", re.IGNORECASE)


def _looks_like_fred_csv(body: bytes) -> bool:
    return bool(_HEADER_RE.match(body[:64].decode("utf-8", errors="replace")))


def _fetch_text(series_id: str, start: str | None) -> str | None:
    """The single network call for a series (tests monkeypatch this). Short
    per-request timeout: a FRED outage must degrade to stale quickly, not hold
    the scheduler for 60 series x 30 s."""
    r = _get_with_backoff(url(series_id, start), timeout=min(settings.http_timeout_seconds, _FRED_TIMEOUT))
    body = r.content if r is not None else None
    if body is None or not _looks_like_fred_csv(body):
        return None
    return body.decode("utf-8", errors="replace")


def parse_csv(text: str, start: str | None = None) -> tuple[list[date], list[float | None]]:
    """fredgraph.csv text -> (dates, values); "." -> None; rows before start dropped."""
    dates: list[date] = []
    vals: list[float | None] = []
    lo = datetime.strptime(start, "%Y-%m-%d").date() if start else None
    for line in text.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        try:
            d = datetime.strptime(parts[0], "%Y-%m-%d").date()
        except ValueError:
            continue  # header or junk
        if lo and d < lo:
            continue
        raw = parts[1].strip()
        try:
            v = None if raw in (".", "", "NA", "n.a.") else float(raw)
        except ValueError:
            v = None
        dates.append(d)
        vals.append(v)
    return dates, vals


def fetch_csv(series_id: str, start: str | None = None, use_cache: bool = True
              ) -> tuple[list[date], list[float | None]]:
    """(dates, values) for a FRED series via the keyless CSV endpoint.

    Disk cache under settings.cache_dir (TTL 12h); on a failed fetch the last
    cached copy is served and status(series_id) == "stale"; nothing cached ->
    ([], []) and "error". Values are floats, missing observations None."""
    key = f"fred_csv_{series_id}_{start or 'all'}.csv"
    path = _cache_path(key)
    if use_cache and os.path.exists(path) and time.time() - os.path.getmtime(path) < _TTL:
        try:
            out = parse_csv(open(path, encoding="utf-8").read(), start)
            _set_status(series_id, "ok")
            return out
        except Exception:  # noqa: BLE001
            pass
    text = _fetch_text(series_id, start)
    if text is not None:
        try:
            _write_atomic(path, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not cache %s: %s", key, exc)
        _set_status(series_id, "ok")
        return parse_csv(text, start)
    if os.path.exists(path):
        try:
            out = parse_csv(open(path, encoding="utf-8").read(), start)
            logger.warning("FRED CSV %s: fetch failed — serving stale cache", series_id)
            _set_status(series_id, "stale")
            return out
        except Exception:  # noqa: BLE001
            pass
    _set_status(series_id, "error")
    return [], []


def fetch_many(series_ids: Iterable[str], start: str | None = None, workers: int = 6
               ) -> dict[str, tuple[list[date], list[float | None]]]:
    """fetch_csv over a list, concurrently (the Z.1 holder panel is ~40 series)."""
    from concurrent.futures import ThreadPoolExecutor

    ids = list(dict.fromkeys(series_ids))

    def _one(sid: str):
        return sid, fetch_csv(sid, start)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(_one, ids))


def worst_status(series_ids: Iterable[str]) -> str:
    """"error" if any series errored, else "stale" if any is stale, else "ok"."""
    seen = {status(s) for s in series_ids}
    if "error" in seen or None in seen:
        return "error"
    return "stale" if "stale" in seen else "ok"


def latest(dates: list[date], values: list[float | None]) -> tuple[date, float] | None:
    """(date, value) of the last non-missing observation, or None."""
    for d, v in zip(reversed(dates), reversed(values)):
        if v is not None:
            return d, v
    return None
