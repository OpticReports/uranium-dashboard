"""Build a POINT-IN-TIME catalyst store from ClinicalTrials.gov record history.

WHAT THIS UNLOCKS: the prior backtests' documented blocker — "no historical
catalyst calendar" — is gone. CT.gov serves every historical version of a
study record:

  GET /api/int/studies/{NCT}/history      -> version list with dates + which
                                             modules changed per version
  GET /api/int/studies/{NCT}/history/{N}  -> the FULL record as of version N

So for any past date d we can reconstruct what the registry SAID on d about a
trial's primary completion date (PCD), overall status and phases — i.e. the
catalyst calendar the dashboard WOULD have shown, at submission-lag
granularity (a sponsor's internal knowledge is invisible until they push an
update; that lag is real and it is exactly what the live pipeline sees too).

METHOD
  1. Universe = active names in config/watchlist.yaml, queried by their
     ctgov_names sponsor aliases when present (MRNA -> ModernaTX) else the
     display name — same alias logic as app/ingestion/catalysts.py.
  2. v2 search per alias with NO overallStatus filter (a 10y replay needs
     trials that completed/terminated years ago), union by NCT across aliases.
  3. Keep PHASE2/PHASE3 trials only; cap at MAX_TRIALS_PER_NAME per name
     (phase-3 first, then most-recently-updated; drops are logged).
  4. Per trial: fetch the version list, then the full record for version 0
     plus every version whose moduleLabels include "Study Status" (that module
     carries PCD + status; other-module-only versions can't change them).
  5. Compress consecutive versions with identical (pcd, status, phases) into
     half-open intervals [from_date, to_date) -> backend/data/pit_catalysts.json.

POLITENESS / ROBUSTNESS
  - NO custom User-Agent (CT.gov's WAF 403s browser UAs from non-browser
    clients; the plain httpx default works).
  - ~0.22s between calls, exponential backoff on 429/5xx.
  - EVERY response is cached under backend/data/pit_ctgov_cache/ (gitignored),
    so reruns are free and the build is resumable mid-flight.

Usage:  python -m scripts.build_pit_catalysts
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import watchlist_config  # noqa: E402

V2_SEARCH = "https://clinicaltrials.gov/api/v2/studies"
INT_HISTORY = "https://clinicaltrials.gov/api/int/studies/{nct}/history"
INT_VERSION = "https://clinicaltrials.gov/api/int/studies/{nct}/history/{v}"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "pit_ctgov_cache"
OUT_PATH = DATA_DIR / "pit_catalysts.json"

SEARCH_FIELDS = (
    "NCTId|BriefTitle|Phase|PrimaryCompletionDate|OverallStatus|LeadSponsorName"
    "|LastUpdatePostDate"  # needed only to order the per-name cap (most recent first)
)
KEEP_PHASES = {"PHASE2", "PHASE3"}
MAX_TRIALS_PER_NAME = 60
SLEEP_BETWEEN_CALLS = 0.22
MAX_RETRIES = 5
TIMEOUT = 30.0

_client = httpx.Client(timeout=TIMEOUT)  # default httpx UA on purpose (see docstring)


def _get_json(url: str, params: dict | None = None) -> dict:
    """GET with exponential backoff on 429/5xx; raises after MAX_RETRIES."""
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            r = _client.get(url, params=params)
            if r.status_code in (429,) or r.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"status {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            time.sleep(SLEEP_BETWEEN_CALLS)
            return r.json()
        except Exception:  # noqa: BLE001 (network + status + JSON errors all retry)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _cached_json(path: Path, producer) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    data = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")


# --- step 1-3: sponsor search, union, phase filter, cap ------------------------

def search_alias(alias: str) -> list[dict]:
    """All studies for one sponsor alias (paginated; NO status filter)."""
    def _producer():
        studies: list[dict] = []
        token: str | None = None
        while True:
            params = {"query.spons": alias, "fields": SEARCH_FIELDS, "pageSize": 100}
            if token:
                params["pageToken"] = token
            page = _get_json(V2_SEARCH, params)
            studies.extend(page.get("studies", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return {"studies": studies}

    return _cached_json(CACHE_DIR / f"search_{_slug(alias)}.json", _producer)["studies"]


def flatten_study(study: dict) -> dict:
    ps = study.get("protocolSection", {})
    status = ps.get("statusModule", {}) or {}
    return {
        "nct": (ps.get("identificationModule", {}) or {}).get("nctId", ""),
        "title": (ps.get("identificationModule", {}) or {}).get("briefTitle", ""),
        "phases": (ps.get("designModule", {}) or {}).get("phases", []) or [],
        "pcd": ((status.get("primaryCompletionDateStruct", {}) or {}).get("date")),
        "status": status.get("overallStatus"),
        "last_update": ((status.get("lastUpdatePostDateStruct", {}) or {}).get("date")) or "",
        "lead": ((ps.get("sponsorCollaboratorsModule", {}) or {})
                 .get("leadSponsor", {}) or {}).get("name"),
    }


def select_trials(symbol: str, aliases: list[str]) -> tuple[list[dict], int, list[str]]:
    by_nct: dict[str, dict] = {}
    for alias in aliases:
        for study in search_alias(alias):
            t = flatten_study(study)
            if t["nct"]:
                by_nct.setdefault(t["nct"], t)
    p23 = [t for t in by_nct.values() if KEEP_PHASES & set(t["phases"])]
    # Cap: phase-3 trials first, then most-recently-updated (stable two-pass).
    p23.sort(key=lambda t: t["last_update"], reverse=True)
    p23.sort(key=lambda t: "PHASE3" not in t["phases"])
    kept, dropped = p23[:MAX_TRIALS_PER_NAME], p23[MAX_TRIALS_PER_NAME:]
    if dropped:
        print(f"  {symbol}: cap {MAX_TRIALS_PER_NAME} — dropped {len(dropped)} "
              f"trials: {', '.join(t['nct'] for t in dropped[:10])}"
              f"{'…' if len(dropped) > 10 else ''}")
    return kept, len(by_nct), [t["nct"] for t in dropped]


# --- step 4-5: version history -> compressed PIT timeline ----------------------

def fetch_history(nct: str) -> list[dict]:
    data = _cached_json(CACHE_DIR / f"{nct}_history.json",
                        lambda: _get_json(INT_HISTORY.format(nct=nct)))
    return data.get("changes", []) or []


def fetch_version(nct: str, v: int) -> dict:
    return _cached_json(CACHE_DIR / f"{nct}_v{v}.json",
                        lambda: _get_json(INT_VERSION.format(nct=nct, v=v)))


def extract_snapshot(version_payload: dict) -> dict:
    ps = (version_payload.get("study", {}) or {}).get("protocolSection", {}) or {}
    status = ps.get("statusModule", {}) or {}
    return {
        "pcd": (status.get("primaryCompletionDateStruct", {}) or {}).get("date"),
        "status": status.get("overallStatus"),
        "phases": (ps.get("designModule", {}) or {}).get("phases", []) or [],
    }


def build_timeline(nct: str, counters: dict) -> list[dict] | None:
    """Fetch v0 + every Study-Status version; compress identical snapshots.

    Returns None when the trial's history could not be fetched at all.
    """
    try:
        changes = fetch_history(nct)
    except Exception as exc:  # noqa: BLE001
        print(f"    {nct}: history fetch FAILED ({exc}) — trial skipped")
        counters["trials_failed"] += 1
        return None
    wanted = sorted({c["version"] for c in changes
                     if c.get("version") == 0
                     or "Study Status" in (c.get("moduleLabels") or [])})
    date_by_version = {c["version"]: c.get("date") for c in changes}
    counters["versions_skipped"] += max(0, len(changes) - len(wanted))

    snaps: list[tuple[str, dict]] = []  # (version_date, snapshot)
    for v in wanted:
        vd = date_by_version.get(v)
        if not vd:
            continue
        try:
            snaps.append((vd, extract_snapshot(fetch_version(nct, v))))
            counters["versions_fetched"] += 1
        except Exception as exc:  # noqa: BLE001
            print(f"    {nct} v{v}: version fetch FAILED ({exc}) — version skipped")
            counters["versions_failed"] += 1
    if not snaps:
        counters["trials_failed"] += 1
        return None

    snaps.sort(key=lambda x: x[0])
    # Same-date re-submissions: the LAST version of a date is what stands.
    by_date: dict[str, dict] = {vd: s for vd, s in snaps}
    ordered = sorted(by_date.items())

    timeline: list[dict] = []
    for vd, s in ordered:
        key = (s["pcd"], s["status"], tuple(s["phases"]))
        if timeline and (timeline[-1]["pcd"], timeline[-1]["status"],
                         tuple(timeline[-1]["phases"])) == key:
            continue
        if timeline:
            timeline[-1]["to"] = vd
        timeline.append({"from": vd, "to": None, "pcd": s["pcd"],
                         "status": s["status"], "phases": s["phases"]})
    return timeline


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    universe = [e for e in watchlist_config().get("universe", []) if e.get("active")]
    print(f"PIT catalyst build: {len(universe)} active names -> {OUT_PATH}")

    symbols_out: dict[str, list[dict]] = {}
    summary: list[dict] = []
    for idx, entry in enumerate(universe, 1):
        sym = entry["symbol"]
        aliases = entry.get("ctgov_names") or [entry.get("name", sym)]
        t0 = time.time()
        counters = {"versions_fetched": 0, "versions_failed": 0,
                    "versions_skipped": 0, "trials_failed": 0}
        try:
            kept, total_ncts, dropped = select_trials(sym, aliases)
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx}/{len(universe)}] {sym}: SEARCH FAILED ({exc}) — name skipped")
            summary.append({"symbol": sym, "error": str(exc)})
            continue
        trials_out: list[dict] = []
        for t in kept:
            tl = build_timeline(t["nct"], counters)
            if tl:
                trials_out.append({"nct": t["nct"], "title": t["title"],
                                   "phases": t["phases"], "timeline": tl})
        symbols_out[sym] = trials_out
        row = {"symbol": sym, "aliases": aliases, "ncts_matched": total_ncts,
               "p23_kept": len(kept), "dropped_by_cap": len(dropped),
               "trials_with_timeline": len(trials_out), **counters,
               "secs": round(time.time() - t0, 1)}
        summary.append(row)
        print(f"[{idx}/{len(universe)}] {sym}: {total_ncts} NCTs matched, "
              f"{len(kept)} P2/P3 kept ({len(dropped)} capped), "
              f"{counters['versions_fetched']} versions fetched "
              f"({counters['versions_failed']} failed, "
              f"{counters['trials_failed']} trials failed) "
              f"in {row['secs']}s")
        # Checkpoint after every name so a crash loses nothing.
        OUT_PATH.write_text(json.dumps({
            "built": datetime.now(timezone.utc).isoformat(),
            "note": ("Point-in-time CT.gov record history: for each trial, "
                     "half-open intervals [from, to) of what the registry said "
                     "(pcd/status/phases). to=null means 'through today'."),
            "symbols": symbols_out,
        }))

    print("\n=== PIT build summary ===")
    print(f"{'sym':6} {'NCTs':>5} {'kept':>5} {'capped':>6} {'timelines':>9} "
          f"{'vers':>6} {'vfail':>5} {'tfail':>5}")
    for r in summary:
        if "error" in r:
            print(f"{r['symbol']:6} SEARCH FAILED: {r['error']}")
            continue
        print(f"{r['symbol']:6} {r['ncts_matched']:>5} {r['p23_kept']:>5} "
              f"{r['dropped_by_cap']:>6} {r['trials_with_timeline']:>9} "
              f"{r['versions_fetched']:>6} {r['versions_failed']:>5} "
              f"{r['trials_failed']:>5}")
    tot_v = sum(r.get("versions_fetched", 0) for r in summary)
    tot_t = sum(r.get("trials_with_timeline", 0) for r in summary)
    tot_vf = sum(r.get("versions_failed", 0) for r in summary)
    tot_tf = sum(r.get("trials_failed", 0) for r in summary)
    print(f"\nTOTAL: {tot_t} trials with timelines, {tot_v} versions fetched, "
          f"{tot_vf} version failures, {tot_tf} trial failures")
    print(f"Store written to {OUT_PATH}")


if __name__ == "__main__":
    main()
