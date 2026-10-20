"""ALFRED vintage pipeline for the cycle-nowcast v2 study (SPEC v1 §4.3-§4.4, F6/F8).

Fetch-by-vintage-list ONLY. For every series the full vintage-date list is taken from
``alfred.stlouisfed.org/series/downloaddata?seid=<ID>`` (an HTML page whose
``form_selected_vintage_dates`` select holds one <option> per archived vintage) and
frozen as F8 (``data/vintage_lists/vd_<ID>.txt`` + SHA256SUMS). Every CSV request is for
a LISTED date, never a snapped one, so the served vintage is the listed vintage and the
header-echo hazard (research pass §1 row 9) cannot arise.

Validation before caching (§4.4), in this order:
  1. HTTP 200 (5xx, timeouts, 429/403 and any other transport failure: retry with
     exponential backoff, then hard-fail; never cached, never read as "no vintage");
  2. first line exactly ``observation_date,<ID>_<YYYYMMDD>`` with YYYYMMDD == the listed
     date (a header mismatch is a hard failure, not a different vintage);
  3. at least one data row with a numeric value;
  4. the last observation month is recorded with the row.
  A 404 with an EMPTY body is accepted only for a date strictly before the list's first
  entry (cannot happen under fetch-by-list; kept because the rule is part of the contract).
Cache key = (series, listed vintage date): ``<cache>/<ID>/<ID>_<YYYY-MM-DD>.csv`` holding
the bytes exactly as served, plus a ``.meta.json`` sidecar. Concurrency <= 8.

Derived tables (F6):
  * vintage_table.csv  - series, vintage_date, sha256, bytes, n_rows, first_obs, last_obs,
                         last_obs_month, for every cached listed vintage;
  * issue_dates.csv    - issue date for (series, M) = the earliest listed vintage whose last
                         observation month is M (content-decided; revision-only vintages are
                         never issue dates; a month that was never a vintage's latest month
                         has NO issue date and is flagged);
  * issue_panel_wide.csv / issue_panel_long.csv - per issue date (union of the PAYEMS,
                         INDPRO and W875RX1 issue dates): P_c(d), M = P_PAYEMS(d), lags
                         L_c, K(d), the IS label of §2.3, the vintage used per series with
                         its hash, the latest month and its value, and the flags §2.4/§4.1
                         ask for (lag >= 3, dropped member, IS-C with L_CMRMTSPL = 2).
``as_of(d)`` returns each series exactly as known at d (latest listed vintage <= d, from
the cache) for the engine. Nothing here computes a composite or a nowcast.

Pure standard library + httpx (a pinned production dependency). No pandas.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ALFRED_LIST_URL = "https://alfred.stlouisfed.org/series/downloaddata?seid={sid}"
ALFRED_CSV_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&vintage_date={d}"
# ALFRED's edge blocks non-browser-looking agents on the HTML endpoints (a bespoke UA string
# got "server disconnected" / HTTP/2 INTERNAL_ERROR on 2026-10-20; a Mozilla-prefixed one
# and curl's default pass). The CSV endpoint is indifferent. Keep the prefix.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) treasury-canary-cycle-nowcast-v2-replay"

COIN_SERIES = ("PAYEMS", "INDPRO", "W875RX1", "CMRMTSPL")
REPLAY_SERIES = COIN_SERIES + ("ICSA",)
PIGER_SERIES = "RECPROUSM156N"
UNREVISED_SERIES = ("T10Y3M", "BAA10YM")
TRIGGERS = {"PAYEMS": "A", "INDPRO": "B", "W875RX1": "C"}
REPLAY_START = "2013-01-01"          # pull range (task sizing); regime (i) starts 2013-06-14
REGIME_I_START = "2013-06-14"        # first CMRMTSPL vintage
MAX_WORKERS = 8
DEFAULT_TRIES = 6
DEFAULT_BACKOFF_S = 1.0
HTTP_TIMEOUT_S = 60.0

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CACHE_FILE_RE = re.compile(r"^([A-Z0-9]+)_(\d{4}-\d{2}-\d{2})\.(csv|meta\.json)$")
# F6: the raw cache, frozen in git as one xz tarball (DT-4: a re-run elsewhere reads the
# frozen bytes through as_of(); it never re-pulls and hopes ALFRED serves identical bytes)
RAW_TARBALL_ROOT = "vintages_raw"
RAW_TARBALL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                           RAW_TARBALL_ROOT + ".tar.xz")
_SELECT_RE = re.compile(
    r'<select[^>]*id="form_selected_vintage_dates"[^>]*>(.*?)</select>', re.S | re.I)
_OPTION_RE = re.compile(r'<option\s+value="(\d{4}-\d{2}-\d{2})"', re.I)


# ----------------------------------------------------------------------------- errors

class VintageError(Exception):
    """Base: anything that must stop a pull or a build (never swallowed)."""


class HardFail(VintageError):
    """Transport/5xx/non-CSV after the retry budget. Nothing was cached."""

    def __init__(self, kind: str, sid: str, vdate: str | None, detail: str):
        super().__init__(f"{kind}: {sid} {vdate or ''} {detail}".strip())
        self.kind, self.sid, self.vdate, self.detail = kind, sid, vdate, detail


class ValidationFail(VintageError):
    """A 200 (or 404) whose content violates §4.4. Nothing was cached."""

    def __init__(self, kind: str, sid: str, vdate: str, detail: str):
        super().__init__(f"{kind}: {sid} {vdate} {detail}")
        self.kind, self.sid, self.vdate, self.detail = kind, sid, vdate, detail


class NotYetArchived(Exception):
    """Empty 404 strictly before the list's first entry (allowed, not cached)."""


# ----------------------------------------------------------------------------- helpers

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def month_of(date_str: str) -> str:
    return date_str[:7]


def month_diff(a: str, b: str) -> int:
    """Calendar months a - b for 'YYYY-MM' (or longer) strings."""
    return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])


def add_months(m: str, k: int) -> str:
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def cache_path(cache_dir: str, sid: str, vdate: str) -> str:
    return os.path.join(cache_dir, sid, f"{sid}_{vdate}.csv")


def _atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- transport

_client_lock = threading.Lock()
_client = None
_stats_lock = threading.Lock()      # pull statistics are incremented from up to 8 threads


def _bump(stats: dict | None, key: str, reason: str | None = None) -> None:
    """Thread-safe increment of a pull statistic (and of its retry_reasons bucket)."""
    if stats is None:
        return
    with _stats_lock:
        stats[key] = stats.get(key, 0) + 1
        if reason is not None:
            stats.setdefault("retry_reasons", {})
            stats["retry_reasons"][reason] = stats["retry_reasons"].get(reason, 0) + 1


def _httpx_fetch(url: str) -> tuple[int, bytes]:
    """Default transport: (status, body). Raises on timeout / connection errors.
    Uses a shared client; honours HTTPS_PROXY and SSL_CERT_FILE from the environment."""
    global _client
    import httpx  # pinned production dependency
    with _client_lock:
        if _client is None:
            verify = os.environ.get("SSL_CERT_FILE") or True
            _client = httpx.Client(timeout=HTTP_TIMEOUT_S, verify=verify,
                                   follow_redirects=False,
                                   headers={"User-Agent": USER_AGENT})
    r = _client.get(url)
    return r.status_code, r.content


def fetch_with_retry(url: str, fetch_fn, *, sid: str, vdate: str | None,
                     tries: int = DEFAULT_TRIES, backoff_s: float = DEFAULT_BACKOFF_S,
                     sleep=time.sleep, accept_404: bool = True,
                     stats: dict | None = None) -> tuple[int, bytes]:
    """Fetch url; retry with exponential backoff on transport errors, 5xx, 429/403 and
    other non-200/404 statuses; hard-fail after the budget. 200 and (optionally) 404 are
    returned to the caller for content validation."""
    last = "no attempt"
    for attempt in range(tries):
        try:
            status, body = fetch_fn(url)
        except Exception as exc:  # timeout, connection reset, proxy failure
            last = f"{type(exc).__name__}: {exc}"
            kind = "timeout"
        else:
            if status == 200 or (status == 404 and accept_404):
                if attempt:
                    _bump(stats, "retried_ok")
                return status, body
            last = f"HTTP {status} ({len(body)} bytes)"
            kind = "server_error" if status >= 500 else "http_status"
        _bump(stats, "retries", kind)
        if attempt < tries - 1:
            sleep(backoff_s * (2 ** attempt))
    raise HardFail(kind, sid, vdate, f"after {tries} attempts: {last}")


# ----------------------------------------------------------------------------- vintage lists (F8)

def parse_vintage_list(html: str, sid: str) -> list[str]:
    """Extract the listed vintage dates from the ALFRED download page. Raises
    ValidationFail if the page does not carry the select (bot block / wrong series)."""
    m = _SELECT_RE.search(html)
    if not m:
        raise ValidationFail("no_vintage_select", sid, "list",
                             "page has no form_selected_vintage_dates select "
                             f"({len(html)} chars)")
    dates = _OPTION_RE.findall(m.group(1))
    if not dates:
        raise ValidationFail("empty_vintage_list", sid, "list", "select has no options")
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValidationFail("unsorted_vintage_list", sid, "list",
                             "options not strictly increasing")
    if f"seid={sid}" not in html and f'"{sid}"' not in html and sid not in html:
        raise ValidationFail("list_series_mismatch", sid, "list", "series id absent")
    return dates


def fetch_vintage_list(sid: str, fetch_fn=None, *, tries: int = DEFAULT_TRIES,
                       sleep=time.sleep, stats: dict | None = None) -> tuple[list[str], bytes]:
    fetch_fn = fetch_fn or _httpx_fetch
    url = ALFRED_LIST_URL.format(sid=sid)
    for attempt in range(tries):
        status, body = fetch_with_retry(url, fetch_fn, sid=sid, vdate="list", tries=tries,
                                        sleep=sleep, accept_404=False, stats=stats)
        try:
            return parse_vintage_list(body.decode("utf-8", "replace"), sid), body
        except ValidationFail as exc:
            if attempt == tries - 1:
                raise HardFail("non_list_body", sid, "list", exc.detail) from exc
            sleep(DEFAULT_BACKOFF_S * (2 ** attempt))
    raise HardFail("non_list_body", sid, "list", "unreachable")


def save_vintage_list(lists_dir: str, sid: str, dates: list[str], raw_html: bytes,
                      retrieved: str) -> dict:
    os.makedirs(lists_dir, exist_ok=True)
    txt = ("\n".join(dates) + "\n").encode()
    path = os.path.join(lists_dir, f"vd_{sid}.txt")
    _atomic_write(path, txt)
    rec = {"series": sid, "file": f"vd_{sid}.txt", "n": len(dates), "first": dates[0],
           "last": dates[-1], "sha256": sha256_bytes(txt), "bytes": len(txt),
           "page_sha256": sha256_bytes(raw_html), "page_bytes": len(raw_html),
           "retrieved": retrieved, "url": ALFRED_LIST_URL.format(sid=sid)}
    return rec


def load_vintage_list(lists_dir: str, sid: str) -> list[str]:
    path = os.path.join(lists_dir, f"vd_{sid}.txt")
    with open(path) as f:
        dates = [ln.strip() for ln in f if ln.strip()]
    bad = [d for d in dates if not _DATE_RE.match(d)]
    if bad:
        raise ValidationFail("bad_list_file", sid, "list", f"non-date lines {bad[:3]}")
    return dates


def write_lists_manifest(lists_dir: str, records: list[dict]) -> None:
    """Merge the run's list records into manifest.json / SHA256SUMS (one entry per series)."""
    mpath = os.path.join(lists_dir, "manifest.json")
    merged = {}
    if os.path.exists(mpath):
        with open(mpath) as f:
            for r in json.load(f):
                merged[r["series"]] = r
    for r in records:
        merged[r["series"]] = r
    records = sorted(merged.values(), key=lambda r: r["series"])
    with open(os.path.join(lists_dir, "SHA256SUMS"), "w") as f:
        for r in records:
            f.write(f"{r['sha256']}  {r['file']}\n")
    with open(os.path.join(lists_dir, "manifest.json"), "w") as f:
        json.dump(records, f, indent=1, sort_keys=True)
        f.write("\n")


# ----------------------------------------------------------------------------- CSV validation (§4.4)

def parse_alfred_csv(body: bytes, sid: str, vdate: str) -> dict:
    """Validate and parse one served vintage. Returns the parsed record or raises
    ValidationFail. ``obs`` keeps the value strings exactly as served ('.' -> None)."""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFail("non_csv", sid, vdate, f"not utf-8: {exc}") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if not lines or not lines[0]:
        raise ValidationFail("non_csv", sid, vdate, "empty body")
    if not text.endswith("\n"):
        # every served ALFRED body ends with a newline (1,585 of 1,585 cached vintages); a
        # transfer cut mid-row does not — refused as non_csv (retried), never parsed, because
        # a cut last row could silently shift last_obs_month and with it the lag pattern
        raise ValidationFail("non_csv", sid, vdate, "body does not end with a newline (cut transfer?)")
    expected = f"observation_date,{sid}_{vdate.replace('-', '')}"
    if lines[0].strip() != expected:
        head = lines[0][:80]
        kind = "non_csv" if "<" in head or "," not in head else "header_mismatch"
        raise ValidationFail(kind, sid, vdate, f"first line {head!r} != {expected!r}")
    obs: list[tuple[str, str | None]] = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        parts = ln.split(",")
        if len(parts) != 2 or not _DATE_RE.match(parts[0]):
            raise ValidationFail("non_csv", sid, vdate, f"bad row {ln[:60]!r}")
        v = parts[1].strip()
        if v in ("", "."):
            # both are ALFRED missing-value forms: '.' in monthly series, an EMPTY field in
            # the daily-rate vintages (T10Y3M 2014-01-27: 348 empty rows, 0 dots; 2026-01-02:
            # 478) and in two ICSA vintages (2018-11-21, 2019-07-03). Truncation is caught by
            # the trailing-newline rule above, not by the field.
            obs.append((parts[0], None))
        else:
            try:
                x = float(v)
            except ValueError as exc:
                raise ValidationFail("non_csv", sid, vdate, f"bad value {ln[:60]!r}") from exc
            if not math.isfinite(x):
                raise ValidationFail("non_csv", sid, vdate, f"non-finite value {ln[:60]!r}")
            obs.append((parts[0], v))
    numeric = [(d, v) for d, v in obs if v is not None]
    if not numeric:
        raise ValidationFail("no_rows", sid, vdate, "no data row with a numeric value")
    dates = [d for d, _ in obs]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValidationFail("non_csv", sid, vdate, "observation dates not strictly increasing")
    return {"series": sid, "vintage_date": vdate, "header": lines[0].strip(),
            "n_rows": len(obs), "n_numeric": len(numeric),
            "first_obs": numeric[0][0], "last_obs": numeric[-1][0],
            "last_obs_month": month_of(numeric[-1][0]),
            "sha256": sha256_bytes(body), "bytes": len(body), "obs": obs}


def validate_response(status: int, body: bytes, sid: str, vdate: str,
                      first_listed: str) -> dict:
    """§4.4 decision on a (status, body) pair. Raises NotYetArchived for the one allowed
    404; ValidationFail otherwise."""
    if status == 404:
        if body.strip() == b"" and vdate < first_listed:
            raise NotYetArchived(f"{sid} {vdate} < first listed {first_listed}")
        raise ValidationFail("not_found", sid, vdate,
                             f"404 ({len(body)} bytes) at a listed date >= {first_listed}")
    if status != 200:
        raise ValidationFail("http_status", sid, vdate, f"HTTP {status}")
    return parse_alfred_csv(body, sid, vdate)


# ----------------------------------------------------------------------------- pull

def _meta_path(path: str) -> str:
    return path[:-4] + ".meta.json"


def fetch_vintage(sid: str, vdate: str, first_listed: str, cache_dir: str, fetch_fn=None,
                  *, tries: int = DEFAULT_TRIES, sleep=time.sleep,
                  stats: dict | None = None) -> dict:
    """Fetch, validate and cache one listed vintage. Returns the meta record. On any
    failure nothing is written. A cached file is returned without a request."""
    path = cache_path(cache_dir, sid, vdate)
    if os.path.exists(path) and os.path.exists(_meta_path(path)):
        with open(_meta_path(path)) as f:
            meta = json.load(f)
        meta["from_cache"] = True
        return meta
    fetch_fn = fetch_fn or _httpx_fetch
    url = ALFRED_CSV_URL.format(sid=sid, d=vdate)
    t0 = time.time()
    for attempt in range(tries):
        status, body = fetch_with_retry(url, fetch_fn, sid=sid, vdate=vdate, tries=tries,
                                        sleep=sleep, stats=stats)
        try:
            rec = validate_response(status, body, sid, vdate, first_listed)   # may raise
            break
        except ValidationFail as exc:
            # a non-CSV body on a 200 (HTML interstitial, truncated transfer) is transient by
            # the §4.4 rule: retry with backoff, then hard-fail. Header/row failures are
            # deterministic content defects and fail at once. Nothing is cached either way.
            if exc.kind != "non_csv":
                raise
            _bump(stats, "retries", "non_csv")
            if attempt == tries - 1:
                raise HardFail("non_csv", sid, vdate, f"after {tries} attempts: {exc.detail}") from exc
            sleep(DEFAULT_BACKOFF_S * (2 ** attempt))
    meta = {k: v for k, v in rec.items() if k != "obs"}
    meta.update({"url": url, "http_status": status, "elapsed_s": round(time.time() - t0, 3),
                 "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "from_cache": False})
    _atomic_write(path, body)
    _atomic_write(_meta_path(path), (json.dumps(meta, sort_keys=True) + "\n").encode())
    return meta


def pull(series: dict[str, str], cache_dir: str, lists_dir: str, *, fetch_fn=None,
         max_workers: int = MAX_WORKERS, tries: int = DEFAULT_TRIES, sleep=time.sleep,
         log=print, extra_dates: dict[str, list[str]] | None = None) -> dict:
    """series = {ID: start_date}: fetch the vintage list of each ID (saved as F8) and every
    listed vintage >= start_date (plus extra_dates[ID], which must be listed dates).
    Returns pull statistics after finishing the batch: valid responses stay cached and
    every per-vintage HardFail/ValidationFail is listed in stats['failures'] (the CLI
    exits 2 when that list is non-empty); only a list fetch or an unlisted extra date
    raises before the batch starts."""
    fetch_fn = fetch_fn or _httpx_fetch
    max_workers = min(MAX_WORKERS, max(1, max_workers))
    t_start = time.time()
    retrieved = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats: dict = {"started": retrieved, "max_workers": max_workers, "series": {},
                   "retries": 0, "retry_reasons": {}, "retried_ok": 0, "failures": []}
    list_records = []
    tasks: list[tuple[str, str, str]] = []
    for sid, start in series.items():
        t0 = time.time()
        dates, raw = fetch_vintage_list(sid, fetch_fn, tries=tries, sleep=sleep, stats=stats)
        rec = save_vintage_list(lists_dir, sid, dates, raw, retrieved)
        rec["elapsed_s"] = round(time.time() - t0, 3)
        list_records.append(rec)
        wanted = [d for d in dates if d >= start]
        for d in (extra_dates or {}).get(sid, []):
            if d not in dates:
                raise ValidationFail("unlisted_date", sid, d, "extra date not in the list")
            if d not in wanted:
                wanted.append(d)
        wanted = sorted(set(wanted))
        cached = sum(1 for d in wanted if os.path.exists(cache_path(cache_dir, sid, d)))
        stats["series"][sid] = {"listed": len(dates), "first_listed": dates[0],
                                "last_listed": dates[-1], "wanted": len(wanted),
                                "cached_before": cached, "requested": 0, "ok": 0,
                                "failed": 0, "bytes": 0}
        tasks += [(sid, d, dates[0]) for d in wanted]
        log(f"[list] {sid}: {len(dates)} listed ({dates[0]}..{dates[-1]}), "
            f"{len(wanted)} wanted >= {start}, {cached} cached")
    write_lists_manifest(lists_dir, list_records)
    stats["lists"] = list_records
    lock = threading.Lock()

    def work(task):
        sid, d, first = task
        try:
            meta = fetch_vintage(sid, d, first, cache_dir, fetch_fn, tries=tries,
                                 sleep=sleep, stats=stats)
            return sid, d, meta, None
        except (HardFail, ValidationFail, NotYetArchived) as exc:
            return sid, d, None, exc

    t_req = time.time()
    n_req = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            sid, d, meta, exc = fut.result()
            with lock:
                s = stats["series"][sid]
                if meta is not None:
                    if not meta.get("from_cache"):
                        s["requested"] += 1
                        n_req += 1
                    s["ok"] += 1
                    s["bytes"] += meta["bytes"]
                else:
                    s["failed"] += 1
                    kind = getattr(exc, "kind", type(exc).__name__)
                    stats["failures"].append({"series": sid, "vintage_date": d,
                                              "kind": kind, "detail": str(exc)})
            if i % 100 == 0 or i == len(tasks):
                log(f"[pull] {i}/{len(tasks)} done, {n_req} requests, "
                    f"{time.time() - t_req:.0f}s, failures {len(stats['failures'])}")
    stats["requests"] = n_req
    stats["elapsed_requests_s"] = round(time.time() - t_req, 1)
    stats["elapsed_total_s"] = round(time.time() - t_start, 1)
    stats["finished"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if n_req:
        stats["s_per_request_effective"] = round(stats["elapsed_requests_s"] / n_req, 3)
    return stats


# ----------------------------------------------------------------------------- F6 raw-cache archive

def tarball_record(tar_path: str = RAW_TARBALL) -> dict | None:
    """{file, sha256, bytes} of the committed raw-cache archive, or None if absent."""
    if not os.path.exists(tar_path):
        return None
    return {"file": os.path.basename(tar_path), "sha256": sha256_file(tar_path),
            "bytes": os.path.getsize(tar_path)}


def cache_from_tarball(tar_path: str = RAW_TARBALL, dest: str | None = None) -> str:
    """Extract the committed raw-vintage archive into `dest` (a fresh temp dir by default)
    and return the cache directory inside it. The archive is data, never executed: only
    regular members named <root>/<ID>/<ID>_<YYYY-MM-DD>.csv|.meta.json are accepted,
    extracted with the stdlib 'data' filter (no absolute paths, links or parent refs)."""
    dest = dest or tempfile.mkdtemp(prefix="cnv2_" + RAW_TARBALL_ROOT + "_")
    with tarfile.open(tar_path, "r:xz") as tf:
        for m in tf:
            if m.isdir():
                continue
            parts = m.name.split("/")
            ok = (m.isreg() and len(parts) == 3 and parts[0] == RAW_TARBALL_ROOT
                  and (mm := _CACHE_FILE_RE.match(parts[2])) is not None and mm.group(1) == parts[1])
            if not ok:
                raise VintageError(f"refused archive member {m.name!r}")
            tf.extract(m, dest, filter="data")
    return os.path.join(dest, RAW_TARBALL_ROOT)


_tar_caches: dict[str, str] = {}


def resolve_cache(cache: str | None, tar_path: str = RAW_TARBALL, log=print) -> str:
    """The raw cache to READ: `cache` when given and present on disk; otherwise the
    committed archive, extracted once per process to a temp dir. A pull needs a real,
    writable cache directory and never goes through here."""
    if cache and os.path.isdir(cache):
        return cache
    if os.path.exists(tar_path):
        if tar_path not in _tar_caches:
            _tar_caches[tar_path] = cache_from_tarball(tar_path)
            log(f"[cache] {os.path.basename(tar_path)} -> {_tar_caches[tar_path]}")
        return _tar_caches[tar_path]
    raise VintageError(f"no raw cache: {cache!r} is not a directory and {tar_path} is absent")


# ----------------------------------------------------------------------------- F6 tables

VT_FIELDS = ["series", "vintage_date", "sha256", "bytes", "n_rows", "first_obs", "last_obs",
             "last_obs_month"]


def read_cached(cache_dir: str, sid: str, vdate: str) -> dict:
    """Re-parse a cached vintage with full validation (hash recomputed from the file)."""
    path = cache_path(cache_dir, sid, vdate)
    with open(path, "rb") as f:
        body = f.read()
    return parse_alfred_csv(body, sid, vdate)


def vintage_table(cache_dir: str, series: list[str], lists_dir: str | None = None,
                  start: str | None = None) -> list[dict]:
    """One row per cached listed vintage (re-hashed from disk). If lists_dir is given,
    files not on the list are refused and listed dates >= start that are missing from the
    cache are reported in a '_missing' attribute on the returned list."""
    rows: list[dict] = []
    missing: list[tuple[str, str]] = []
    for sid in series:
        d = os.path.join(cache_dir, sid)
        listed = set(load_vintage_list(lists_dir, sid)) if lists_dir else None
        present = set()
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not fn.endswith(".csv") or not fn.startswith(sid + "_"):
                continue
            vdate = fn[len(sid) + 1:-4]
            if listed is not None and vdate not in listed:
                raise ValidationFail("unlisted_cache_file", sid, vdate, fn)
            rec = read_cached(cache_dir, sid, vdate)
            rows.append({k: rec[k] for k in VT_FIELDS})
            present.add(vdate)
        if listed is not None and start is not None:
            missing += [(sid, v) for v in sorted(listed) if v >= start and v not in present]
    rows.sort(key=lambda r: (r["series"], r["vintage_date"]))
    out = _Rows(rows)
    out.missing = missing
    return out


class _Rows(list):
    missing: list = []


ID_FIELDS = ["series", "month", "issue_date", "issue_sha256", "first_vintage_containing",
             "status"]


def issue_dates(vtable: list[dict]) -> list[dict]:
    """Issue date for (series, M) = the earliest listed vintage whose last observation month
    is M. status: 'issue' | 'never_latest' (M first appeared inside a multi-month vintage
    whose latest month is later) | 'left_censored' (M was already the latest month of the
    first cached vintage, so an earlier uncached vintage may be its true issue date)."""
    out = []
    by = {}
    for r in vtable:
        by.setdefault(r["series"], []).append(r)
    for sid, rows in sorted(by.items()):
        rows.sort(key=lambda r: r["vintage_date"])
        if not rows:
            continue
        first_latest = rows[0]["last_obs_month"]
        seen_latest: dict[str, dict] = {}       # month -> earliest row with that latest month
        first_containing: dict[str, dict] = {}  # month -> earliest row with latest >= month
        prev_max = None
        for r in rows:
            m = r["last_obs_month"]
            if m not in seen_latest:
                seen_latest[m] = r
            if prev_max is None:
                first_containing[m] = r
            elif m > prev_max:
                mm = add_months(prev_max, 1)
                while mm <= m:
                    first_containing.setdefault(mm, r)
                    mm = add_months(mm, 1)
            prev_max = m if prev_max is None or m > prev_max else prev_max
        for m in sorted(first_containing):
            fc = first_containing[m]
            if m in seen_latest:
                r = seen_latest[m]
                status = "left_censored" if m <= first_latest else "issue"
                out.append({"series": sid, "month": m, "issue_date": r["vintage_date"],
                            "issue_sha256": r["sha256"],
                            "first_vintage_containing": fc["vintage_date"], "status": status})
            else:
                out.append({"series": sid, "month": m, "issue_date": "", "issue_sha256": "",
                            "first_vintage_containing": fc["vintage_date"],
                            "status": "never_latest"})
    out.sort(key=lambda r: (r["series"], r["month"]))
    return out


def latest_vintage_leq(vtable_rows: list[dict], d: str) -> dict | None:
    """Latest listed (cached) vintage of one series dated <= d, or None."""
    best = None
    for r in vtable_rows:
        if r["vintage_date"] <= d and (best is None or r["vintage_date"] > best["vintage_date"]):
            best = r
    return best


def is_label(P: dict[str, str]) -> dict:
    """§2.3: P = {member: latest month in hand}. M = P_PAYEMS; L_c = M - P_c; K = min P_c.
    IS = A if P_INDPRO < M; B if P_INDPRO == M and P_W875RX1 < M; C if P_W875RX1 == M.
    CMRMTSPL is carried as a lag, never in the label. Pure, deterministic."""
    M = P["PAYEMS"]
    lags = {c: month_diff(M, P[c]) for c in COIN_SERIES if c in P and P[c]}
    present = [c for c in COIN_SERIES if c in P and P[c]]
    K = min(P[c] for c in present)
    if P.get("INDPRO") is None or P["INDPRO"] < M:
        label = "A"
    elif P.get("W875RX1") is None or P["W875RX1"] < M:
        label = "B"
    else:
        label = "C"
    if P.get("W875RX1") is not None and P["W875RX1"] > M:
        label = "C"   # cannot happen with PAYEMS leading; kept explicit
    return {"IS": label, "M": M, "lags": lags, "K": K,
            "dropped": [c for c, L in lags.items() if L >= 4],
            "lag_ge3": [c for c, L in lags.items() if L >= 3],
            # a member whose latest month lies beyond M (outside §2.3; the engine floors the
            # lag at 0 and keeps M as the target) — flagged, never silently negative
            "members_ahead": [c for c, L in lags.items() if L < 0],
            "is_c_cmrmtspl_lag2": bool(label == "C" and lags.get("CMRMTSPL") == 2),
            # the §2.3 identity gate (completed COIN(M-1) == realized) holds ONLY on IS-C rows
            # with CMRMTSPL at lag 1; lag 2 is the spec-named flag, lag 3 is neither
            "is_c_identity": bool(label == "C" and lags.get("CMRMTSPL") == 1),
            "canonical": {"A": {"PAYEMS": 0, "INDPRO": 1, "W875RX1": 1, "CMRMTSPL": 2},
                          "B": {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 1, "CMRMTSPL": 2},
                          "C": {"PAYEMS": 0, "INDPRO": 0, "W875RX1": 0, "CMRMTSPL": 1}}[label] == lags}


PANEL_SERIES = COIN_SERIES + ("ICSA",)
WIDE_FIELDS = (["issue_date", "trigger", "trigger_month", "row_kind", "IS", "M", "K", "canonical",
                "lag_ge3", "dropped", "members_ahead", "is_c_cmrmtspl_lag2", "is_c_identity",
                "trigger_month_ne_M"]
               + [f"{c}_{k}" for c in PANEL_SERIES for k in ("vintage", "latest", "lag")])
LONG_FIELDS = ["issue_date", "trigger", "row_kind", "IS", "series", "vintage_date", "sha256",
               "month", "value", "lag"]


def row_kind(trigger_month: str, M: str) -> str:
    """§4.3 'exactly one target per (issue date, IS)': a trigger whose month is M scores
    the nowcast for M ('nowcast'); a trigger whose month is M-1 (W875RX1 printing for the
    month before the latest PAYEMS month, 10 rows 2013-2026) completes COIN(trigger month)
    and belongs in the COIN_HH(M-1) completion table ('completion'), never as a second
    nowcast row for M; a trigger month beyond M is 'trigger_ahead' (outside §2.3)."""
    if trigger_month == M:
        return "nowcast"
    return "completion" if trigger_month < M else "trigger_ahead"


def issue_panel(vtable: list[dict], idates: list[dict], cache_dir: str,
                start: str = REGIME_I_START, end: str | None = None,
                triggers: dict[str, str] = TRIGGERS) -> tuple[list[dict], list[dict]]:
    """Per issue date (union of the trigger series' issue dates in [start, end]): the lag
    pattern in hand and the latest value of every series. Reads the cache for values."""
    by = {}
    for r in vtable:
        by.setdefault(r["series"], []).append(r)
    issue = {}
    for r in idates:
        if r["series"] in triggers and r["status"] == "issue" and r["issue_date"] >= start \
                and (end is None or r["issue_date"] <= end):
            issue.setdefault((r["issue_date"], r["series"]), r["month"])
    wide, long_ = [], []
    cache: dict[tuple[str, str], dict] = {}

    def rec(sid, vd):
        if (sid, vd) not in cache:
            cache[(sid, vd)] = read_cached(cache_dir, sid, vd)
        return cache[(sid, vd)]

    for (d, trig), tmonth in sorted(issue.items()):
        P, used = {}, {}
        for sid in PANEL_SERIES:
            v = latest_vintage_leq(by.get(sid, []), d)
            used[sid] = v
            if v is not None and sid in COIN_SERIES:
                P[sid] = v["last_obs_month"]
        if "PAYEMS" not in P:
            continue
        lab = is_label(P)
        kind = row_kind(tmonth, lab["M"])
        row = {"issue_date": d, "trigger": trig, "trigger_month": tmonth, "row_kind": kind,
               "IS": lab["IS"], "M": lab["M"], "K": lab["K"], "canonical": int(lab["canonical"]),
               "lag_ge3": "|".join(lab["lag_ge3"]), "dropped": "|".join(lab["dropped"]),
               "members_ahead": "|".join(lab["members_ahead"]),
               "is_c_cmrmtspl_lag2": int(lab["is_c_cmrmtspl_lag2"]),
               "is_c_identity": int(lab["is_c_identity"]),
               "trigger_month_ne_M": int(tmonth != lab["M"])}
        for sid in PANEL_SERIES:
            v = used[sid]
            if v is None:
                row[f"{sid}_vintage"] = row[f"{sid}_latest"] = row[f"{sid}_lag"] = ""
                continue
            r = rec(sid, v["vintage_date"])
            last_date, last_val = next((o for o in reversed(r["obs"]) if o[1] is not None))
            row[f"{sid}_vintage"] = v["vintage_date"]
            row[f"{sid}_latest"] = last_date if sid == "ICSA" else r["last_obs_month"]
            row[f"{sid}_lag"] = (month_diff(lab["M"], r["last_obs_month"])
                                 if sid in COIN_SERIES else "")
            long_.append({"issue_date": d, "trigger": trig, "row_kind": kind, "IS": lab["IS"],
                          "series": sid, "vintage_date": v["vintage_date"], "sha256": v["sha256"],
                          "month": last_date if sid == "ICSA" else r["last_obs_month"],
                          "value": last_val, "lag": row[f"{sid}_lag"]})
        wide.append(row)
    return wide, long_


def write_csv(path: str, rows: list[dict], fields: list[str]) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    return sha256_file(path)


# ----------------------------------------------------------------------------- as_of for the engine

def as_of(d: str, cache_dir: str | None = None, lists_dir: str | None = None,
          series=REPLAY_SERIES) -> dict:
    """The series exactly as known at calendar date d: for each series the latest LISTED
    vintage dated <= d, read from the cache (cache_dir, or the committed F6 archive
    data/vintages_raw.tar.xz when cache_dir is None / absent; lists_dir defaults to the
    committed F8 lists). Returns
    {series: {'vintage_date', 'sha256', 'last_obs', 'last_obs_month', 'obs': [(date, value_str|None)]}}
    Raises VintageError if that listed vintage is not cached (never substitutes a later or
    earlier vintage); a series with no listed vintage <= d maps to None."""
    cache_dir = resolve_cache(cache_dir, log=lambda *_: None)
    lists_dir = lists_dir or _default_paths()["lists"]
    out = {}
    for sid in series:
        listed = load_vintage_list(lists_dir, sid)
        cand = [v for v in listed if v <= d]
        if not cand:
            out[sid] = None
            continue
        v = cand[-1]
        path = cache_path(cache_dir, sid, v)
        if not os.path.exists(path):
            raise VintageError(f"as_of({d}): {sid} listed vintage {v} not in cache {cache_dir}")
        rec = read_cached(cache_dir, sid, v)
        out[sid] = {k: rec[k] for k in ("vintage_date", "sha256", "last_obs", "last_obs_month", "obs")}
    return out


def monthly(obs, how: str) -> dict[str, float]:
    """Collapse (date, value) observations to {YYYY-MM: value}; how = 'mean' (ICSA weeks by
    their week-ending Saturday, daily rates) or 'last'. Mirrors the deployed _monthly()."""
    acc: dict[str, list[float]] = {}
    for d, v in obs:
        if v is None:
            continue
        acc.setdefault(d[:7], []).append(float(v))
    return {m: (sum(v) / len(v) if how == "mean" else v[-1]) for m, v in acc.items()}


# ----------------------------------------------------------------------------- unrevised check (§4.1)

def unrevised_check(sid: str, vdate: str, cache_dir: str, current_csv: str) -> dict:
    """Compare one cached ALFRED vintage with the current FRED CSV on common dates."""
    rec = read_cached(cache_dir, sid, vdate)
    vint = {d: float(v) for d, v in rec["obs"] if v is not None}
    cur = {}
    with open(current_csv) as f:
        rd = csv.reader(f)
        hdr = next(rd)
        for row in rd:
            if len(row) >= 2 and row[1] not in ("", "."):
                cur[row[0]] = float(row[1])
    common = sorted(set(vint) & set(cur))
    changed = [(d, vint[d], cur[d]) for d in common if abs(vint[d] - cur[d]) > 1e-9]
    return {"series": sid, "vintage_date": vdate, "vintage_sha256": rec["sha256"],
            "current_file": os.path.basename(current_csv), "current_header": hdr,
            "n_vintage": len(vint), "n_current": len(cur), "n_common": len(common),
            "n_changed": len(changed), "max_abs_change": max((abs(a - b) for _, a, b in changed), default=0.0),
            "changed_examples": changed[:5], "unrevised": len(changed) == 0}


# ----------------------------------------------------------------------------- 2026 calendar check (DT-17)

def calendar_check(vtable: list[dict], ref_rows: list[dict], year: str = "2026") -> dict:
    """Compare content-decided issue dates against data/alfred_first_vintage_2026.csv. A ref row
    with NOT_YET_BY_<date> must have no issue date <= that date (and no vintage whose latest
    month is the ref month at all in the table)."""
    idt = issue_dates(_Rows([r for r in vtable if r["vintage_date"] >= f"{int(year) - 1}-12-01"]))
    by = {(r["series"], r["month"]): r for r in idt}
    rows, ok = [], True
    for ref in ref_rows:
        key = (ref["series"], ref["ref_month"])
        if ref["series"] not in {r["series"] for r in vtable}:
            rows.append({**key_dict(key), "expected": ref["first_vintage_date"], "computed": None,
                         "status": "not_pulled", "pass": None})
            continue
        got = by.get(key)
        exp = ref["first_vintage_date"]
        if exp.startswith("NOT_YET_BY_"):
            cut = exp[len("NOT_YET_BY_"):]
            computed = got["issue_date"] if got and got["issue_date"] else None
            p = computed is None or computed > cut
            rows.append({**key_dict(key), "expected": exp, "computed": computed,
                         "status": got["status"] if got else "no_row", "pass": p})
        else:
            computed = got["issue_date"] if got else None
            p = (computed == exp) and got["status"] == "issue"
            rows.append({**key_dict(key), "expected": exp, "computed": computed,
                         "status": got["status"] if got else "no_row", "pass": p})
        ok = ok and (rows[-1]["pass"] is not False)
    return {"pass": ok, "n": len(rows), "n_checked": sum(1 for r in rows if r["pass"] is not None),
            "n_pass": sum(1 for r in rows if r["pass"]), "rows": rows,
            "ref_file": "alfred_first_vintage_2026.csv"}


def key_dict(key):
    return {"series": key[0], "month": key[1]}


# ----------------------------------------------------------------------------- regime (ii) issue points from LISTS ONLY (v1 §4.2; task B3)

PI_SERIES = "PI"                      # BEA Personal Income: the IS-C (PI&O day) proxy before W875RX1's 2010-05-28
# Earliest calendar day of M+1 on which the release that first carries month M can be listed.
# A content-free rule over the listed vintage dates (values are never fetched for this): the
# earliest listed vintage dated >= that day of M+1 and before the first day of M+3. PAYEMS:
# the first Friday of M+1 is always the first PAYEMS vintage of M+1; INDPRO: the G.17 lands
# on the 14th-18th of M+1 (annual revisions are listed in late March / Nov-Dec, outside the
# window); PI: the PI&O release lands in the last ~8 days of M+1 (or slips into M+2), the
# annual revision shares its release date. Labelled "list-only proxy" wherever it is used.
LIST_PROXY_MIN_DAY = {"PAYEMS": 1, "INDPRO": 14, PI_SERIES: 20, "W875RX1": 20}


def fetch_pi_vintage_list(lists_dir: str, fetch_fn=None, *, tries: int = DEFAULT_TRIES,
                          sleep=time.sleep) -> dict:
    """Fetch-by-list for BEA Personal Income (ALFRED id PI): the vintage DATE list only, saved
    as data/vintage_lists/vd_PI.txt with its hash in manifest.json / SHA256SUMS (F8). No PI
    vintage CSV is ever requested: regime (ii) needs the PI&O release dates, not the values."""
    retrieved = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dates, raw = fetch_vintage_list(PI_SERIES, fetch_fn, tries=tries, sleep=sleep)
    rec = save_vintage_list(lists_dir, PI_SERIES, dates, raw, retrieved)
    write_lists_manifest(lists_dir, [rec])
    return rec


def list_proxy_issue_dates(dates: list[str], months: list[str], series: str,
                           min_day: int | None = None) -> dict[str, str | None]:
    """Regime (ii) issue point for each month M from a vintage-date LIST alone: the earliest
    listed date d with '<M+1>-<min_day>' <= d <= '<M+3>-01' (None when no such date). The
    upper bound is INCLUSIVE (fix pass M1): a release slipping to exactly the 1st of M+3 is a
    real issue date (W875RX1 2018-12 was released 2019-03-01 after the shutdown). Content is
    not consulted (the lists carry no observation months); every consumer labels the result
    'list-only proxy' and scoring.section_regime_ii records the agreement table against the
    content-decided F6 issue dates. Deterministic."""
    if min_day is None:
        min_day = LIST_PROXY_MIN_DAY[series]
    ds = sorted(dates)
    out: dict[str, str | None] = {}
    for M in months:
        lo = f"{add_months(M, 1)}-{min_day:02d}"
        hi = f"{add_months(M, 3)}-01"
        out[M] = next((d for d in ds if lo <= d <= hi), None)
    return out


# ----------------------------------------------------------------------------- CLI

def _default_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    data = os.path.join(here, "data")
    return {"lists": os.path.join(data, "vintage_lists"),
            "panel": os.path.join(data, "vintages_panel"),
            "fred": os.path.join(data, "fred_2026-10-20")}


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("pi-list", help="fetch the BEA PI vintage DATE list only (regime (ii) IS-C proxy, F8)")
    pl.add_argument("--lists", default=_default_paths()["lists"])
    for name in ("pull", "build", "check", "calendar"):
        q = sub.add_parser(name)
        q.add_argument("--cache", default=None,
                       help="raw vintage cache directory (required for pull/check; build and "
                            "calendar read the committed data/vintages_raw.tar.xz when absent)")
        q.add_argument("--lists", default=_default_paths()["lists"])
        q.add_argument("--out", default=_default_paths()["panel"])
        q.add_argument("--start", default=REPLAY_START)
        q.add_argument("--workers", type=int, default=MAX_WORKERS)
        q.add_argument("--series", default=",".join(REPLAY_SERIES + (PIGER_SERIES,)))
        q.add_argument("--extra", action="append", default=[],
                       help="SID:YYYY-MM-DD listed date to fetch outside --start (repeatable)")
        q.add_argument("--fred", default=_default_paths()["fred"])
        q.add_argument("--allow-missing", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "pi-list":
        rec = fetch_pi_vintage_list(a.lists)
        print(json.dumps(rec, indent=1, sort_keys=True))
        return 0
    series = [s for s in a.series.split(",") if s]
    os.makedirs(a.out, exist_ok=True)
    if a.cmd in ("pull", "check") and not a.cache:
        print(f"{a.cmd}: --cache (a writable raw cache directory) is required", file=sys.stderr)
        return 2
    if a.cmd in ("build", "calendar"):
        a.cache = resolve_cache(a.cache)
    if a.cmd == "pull":
        extra: dict[str, list[str]] = {}
        for e in a.extra:
            sid, d = e.split(":", 1)
            extra.setdefault(sid, []).append(d)
        spec = {sid: a.start for sid in series}
        if PIGER_SERIES in spec:            # §6 needs the earliest ALFRED vintages (from 2012-09-04)
            spec[PIGER_SERIES] = min(a.start, "2012-09-04")
        stats = pull(spec, a.cache, a.lists, max_workers=a.workers, extra_dates=extra)
        with open(os.path.join(a.out, "pull_stats.json"), "w") as f:
            json.dump(stats, f, indent=1, sort_keys=True)
            f.write("\n")
        print(json.dumps({k: v for k, v in stats.items() if k not in ("lists", "series")}, indent=1))
        for sid, s in stats["series"].items():
            print(sid, s)
        if stats["failures"]:
            print(f"HARD FAIL: {len(stats['failures'])} listed vintages not cached", file=sys.stderr)
            return 2
        return 0
    if a.cmd == "build":
        vt = vintage_table(a.cache, series, a.lists, a.start)
        if vt.missing:
            print(f"missing listed vintages >= {a.start}: {vt.missing[:10]} (+{max(0, len(vt.missing) - 10)})",
                  file=sys.stderr)
            if not a.allow_missing:
                return 2
        h1 = write_csv(os.path.join(a.out, "vintage_table.csv"), vt, VT_FIELDS)
        # the issue-date derivation needs a CONTIGUOUS run of cached listed vintages: restrict
        # it to the pull range (cached extras before --start, e.g. the INDPRO 2008-10 G.17
        # vintages fetched for the ADS gate, stay in vintage_table.csv but not in the derivation)
        def _start(sid):  # §6: RECPROUSM156N is pulled from its first listed vintage (2012-09-04)
            return min(a.start, "2012-09-04") if sid == PIGER_SERIES else a.start
        in_range = _Rows([r for r in vt if r["vintage_date"] >= _start(r["series"])])
        idt = issue_dates(in_range)
        h2 = write_csv(os.path.join(a.out, "issue_dates.csv"), idt, ID_FIELDS)
        wide, long_ = issue_panel(in_range, idt, a.cache)
        h3 = write_csv(os.path.join(a.out, "issue_panel_wide.csv"), wide, WIDE_FIELDS)
        h4 = write_csv(os.path.join(a.out, "issue_panel_long.csv"), long_, LONG_FIELDS)
        summary = {"vintage_table_sha256": h1, "issue_dates_sha256": h2,
                   "issue_panel_wide_sha256": h3, "issue_panel_long_sha256": h4,
                   "n_vintages": len(vt), "n_vintages_in_range": len(in_range),
                   "n_vintages_before_start": len(vt) - len(in_range),
                   "n_issue_rows": len(idt), "n_issue_dates": len(wide),
                   "missing": vt.missing, "start": a.start,
                   "cache": os.path.basename(os.path.normpath(a.cache)),
                   # F6: the raw cache frozen in git; every vintage_table row's sha256 is
                   # re-hashed from the extracted files on each build
                   "raw_tarball": tarball_record(),
                   "n_rows_nowcast": sum(1 for w in wide if w["row_kind"] == "nowcast"),
                   "n_rows_completion": sum(1 for w in wide if w["row_kind"] == "completion"),
                   "is_counts_nowcast_rows": {k: sum(1 for w in wide if w["IS"] == k and w["row_kind"] == "nowcast")
                                              for k in "ABC"},
                   "per_series": {sid: {"n": sum(1 for r in vt if r["series"] == sid),
                                        "first": min((r["vintage_date"] for r in vt if r["series"] == sid), default=None),
                                        "last": max((r["vintage_date"] for r in vt if r["series"] == sid), default=None),
                                        "bytes": sum(r["bytes"] for r in vt if r["series"] == sid)}
                                  for sid in series},
                   "is_counts": {k: sum(1 for w in wide if w["IS"] == k) for k in "ABC"},
                   "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        with open(os.path.join(a.out, "build_summary.json"), "w") as f:
            json.dump(summary, f, indent=1, sort_keys=True)
            f.write("\n")
        print(json.dumps(summary, indent=1, sort_keys=True))
        return 0
    if a.cmd == "calendar":
        # the 2026 calendar check of alfred_first_vintage_2026.csv (DT-17): content-decided issue
        # dates from the cache for every series in that file that was pulled, AWHMAN included
        # (its 2026 vintages were fetched for this check only; they enter no scored number)
        ref = []
        with open(os.path.join(os.path.dirname(a.fred), "alfred_first_vintage_2026.csv"), newline="") as f:
            for r in csv.DictReader(f):
                ref.append(r)
        sids = sorted({r["series"] for r in ref} & set(os.listdir(a.cache)))
        vt = vintage_table(a.cache, sids, a.lists, None)
        aux = _Rows([r for r in vt if r["series"] == "AWHMAN"])
        write_csv(os.path.join(a.out, "calendar_check_vintages.csv"), aux, VT_FIELDS)
        res = calendar_check(vt, ref)
        with open(os.path.join(a.out, "calendar_check_2026.json"), "w") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, sort_keys=True))
        for r in res["rows"]:
            print(r)
        return 0 if res["pass"] else 3
    if a.cmd == "check":
        # §4.1 'taken current' basis: the current FRED CSV is compared with (1) the EARLIEST
        # listed ALFRED vintage overall, (2) the earliest listed 2026 vintage and (3) the
        # latest cached 2026 vintage. (1) and (2) span the whole archive, so a revision
        # anywhere since the first vintage shows up; (3) alone could only catch a same-month
        # revision. Vintages not yet cached are fetched by their listed date (§4.4).
        out = []
        for sid in UNREVISED_SERIES:
            listed = load_vintage_list(a.lists, sid)
            l26 = [v for v in listed if v >= "2026-01-01"]
            cached26 = [v for v in l26 if os.path.exists(cache_path(a.cache, sid, v))]
            which = {"earliest_listed": listed[0], "earliest_2026": l26[0] if l26 else None,
                     "latest_2026_cached": cached26[-1] if cached26 else None}
            comps = []
            for tag, v in which.items():
                if v is None:
                    comps.append({"which": tag, "error": "no such vintage"})
                    continue
                fetch_vintage(sid, v, listed[0], a.cache)          # cached -> no request
                comps.append({"which": tag, **unrevised_check(sid, v, a.cache, os.path.join(a.fred, f"{sid}.csv"))})
            out.append({"series": sid, "comparisons": comps,
                        "n_changed_total": sum(c.get("n_changed", 0) for c in comps),
                        "unrevised": all(c.get("unrevised") is True for c in comps)})
        with open(os.path.join(a.out, "unrevised_check.json"), "w") as f:
            json.dump(out, f, indent=1, sort_keys=True, default=str)
            f.write("\n")
        print(json.dumps(out, indent=1, default=str))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
