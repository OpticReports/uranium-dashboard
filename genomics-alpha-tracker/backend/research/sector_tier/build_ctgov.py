"""Sector-tier measurements, stage 2: ClinicalTrials.gov, current and point in time.

Pre-registration: docs/DESIGN_SECTOR_TIER.md (rev 3 + amendments of
2026-10-05). Like stage 1 this only ASSEMBLES data.

Who is searched: every stage-1 population name whose daily FMP market cap
reached $300M on any day from 2025-08-01 (replay warm-up) to 2026-10-02, or
whose screener cap today is >= $300M. Below that floor a name can neither move
into the measured population nor enter Tier 1 or either funnel lane.

How: the SHIPPED funnel's query, `query.spons=<clean_company_name(screener
name)>`, but with no status and no date filter (a past day's view needs trials
that have since completed or been withdrawn), every page. One compact row per
study keeps the fields the rules read: phases, brief title, current PCD and
status, StudyFirstPostDate, LastUpdatePostDate, and - for the company's OWN
phase 2/3 trials (discovery.is_own_study) - collaborators and whether any
intervention is GENETIC.

Point-in-time record history (scripts/build_pit_catalysts.py's endpoints and
cache) is fetched for each study that could change a past day's answer:
  - phase 2/3, or a genomics keyword in its first 120 title characters (the
    only other way a study moves the funnel's catalyst lane: title tags);
  - first posted on or before 2026-09-30; and
  - last updated on or after 2025-08-01. A study last updated before then
    showed its CURRENT record for the whole replay, so history adds nothing.
Per study: the version list (dates, status per version), then the full record
for every "Study Status" version from the one in force on 2025-08-01 through
2026-09-30 (only that module carries the primary completion date). At most
MAX_PIT_PER_NAME studies per name (phase 3 first, then most recently updated);
every drop is counted in the output.

Only DECISION-RELEVANT names get history (measured 2026-10-06: 165 of 705,
1,810 of 3,040 studies): names with a genomics-labelled move (their baseline
visibility is measured) and every name that could be in Tier 1 under either
rule-(b) title mode (their catalysts rank the screen). Every other name's
queue status changes no metric, only the size chart; it keeps current
records. Versions are bisected: the version in force on 2025-08-01 and the
last one in the span are fetched (the last is the current record when no
later status version exists); intermediate versions only where the primary
completion date or phases differ between fetched neighbours. A date that
changed and changed back between two equal fetched versions is missed;
stated in the report.

CT.gov's API allows about 50 calls a minute: a global limiter spaces calls
1.25 s apart across workers.

Studies outside that set keep their current record. For the funnel's 50-row
page that is an approximation only for sponsors with more than 50 active
future-dated studies on a day (large pharma); it is stated in the report.

    cd genomics-alpha-tracker/backend && python -m research.sector_tier.build_ctgov
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
sys.path.insert(0, str(BACKEND))

from app.ingestion import discovery as D  # noqa: E402
from research.sector_tier import build_population as P  # noqa: E402
from scripts import build_pit_catalysts as B  # noqa: E402

OUT = HERE / "ctgov.json"
SEARCH_CACHE = P.CACHE / "ctgov" / "search"
SEARCH_FIELDS = ("NCTId|BriefTitle|Phase|StudyType|PrimaryCompletionDate|OverallStatus|"
                 "LeadSponsorName|CollaboratorName|InterventionType|StudyFirstPostDate|"
                 "LastUpdatePostDate")
PIT_FROM = "2025-08-01"     # replay warm-up start
PIT_TO = "2026-09-30"       # window end
MAX_PIT_PER_NAME = 60
WORKERS = 2
MIN_INTERVAL = 1.25
_lock = threading.Lock()
_rate_lock = threading.Lock()
_next_slot = [0.0]
_orig_get_json = B._get_json


def _limited_get_json(url, params=None):
    with _rate_lock:
        wait = _next_slot[0] - time.time()
        _next_slot[0] = max(time.time(), _next_slot[0]) + MIN_INTERVAL
    if wait > 0:
        time.sleep(wait)
    return _orig_get_json(url, params)


B._get_json = _limited_get_json
B.SLEEP_BETWEEN_CALLS = 0.0


def relevant_names(names: list[dict], census: dict) -> set[str]:
    """Names whose point-in-time trial record can change a metric (see docstring)."""
    from research.sector_tier import measure as M   # lazy: measure imports this module
    labels = json.loads((HERE / "labels.json").read_text())
    moves = json.loads(P.OUT_MOVES.read_text())
    g_movers = {m["symbol"] for m in moves if (labels.get(m["symbol"]) or {}).get("genomics")}
    core = M.Core({})
    partners = set().union(*(core.partners(t) for t, _ in core.hist))
    out = set()
    for p in names:
        s = p["symbol"]
        raw = (census.get(s) or {}).get("screener_name") or p["name"]
        q = D.clean_company_name(raw)
        rows = [compact(x, q) for x in search_name(q)]
        prof_path = P.CACHE / "fmp" / "profile" / f"{s}.json"
        prof = (json.loads(prof_path.read_text()) or [{}])[0] if prof_path.exists() else {}
        own = [r for r in rows if r.get("own_p23")]
        if (s in g_movers or D.genomics_tags_for([raw])
                or (census.get(s) or {}).get("screener_industry") == M.LAB_INDUSTRY
                or D.genomics_tags_for([(prof or {}).get("description") or ""])
                or any(r.get("genetic") for r in own) or D.genomics_tags_for([r["title"] for r in own])
                or D.genomics_partner_hits([x for r in own for x in r.get("partners") or []], partners, q)
                or D.genomics_tags_for([r["title"][:120] for r in rows])):
            out.add(s)
    return out


def eligible(pop: list[dict], census: dict[str, dict]) -> list[dict]:
    out = []
    for p in pop:
        path = P.CACHE / "fmp" / "mcap" / f"{p['symbol']}.json"
        caps = json.loads(path.read_text()) if path.exists() else []
        hist_max = max((float(x["marketCap"]) for x in caps or [] if x.get("marketCap")), default=0.0)
        now = (census.get(p["symbol"]) or {}).get("mcap_now") or 0.0
        if max(hist_max, now) >= P.MCAP_MIN:
            out.append(p)
    return out


def search_name(cleaned: str) -> list[dict]:
    path = SEARCH_CACHE / f"{B._slug(cleaned)[:120] or 'blank'}.json"
    if path.exists():
        return json.loads(path.read_text())["studies"]
    studies, token = [], None
    while True:
        params = {"query.spons": cleaned, "fields": SEARCH_FIELDS, "pageSize": 1000}
        if token:
            params["pageToken"] = token
        page = B._get_json(B.V2_SEARCH, params)
        studies += page.get("studies", []) or []
        token = page.get("nextPageToken")
        if not token:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"query": cleaned, "studies": studies}))
    return studies


def compact(study: dict, cleaned: str) -> dict:
    ps = study.get("protocolSection", {}) or {}
    ident = ps.get("identificationModule", {}) or {}
    st = ps.get("statusModule", {}) or {}
    design = ps.get("designModule", {}) or {}
    own = D.is_own_study(study, cleaned)
    row = {
        "nct": ident.get("nctId", ""),
        "title": ident.get("briefTitle") or "",
        "phases": design.get("phases") or [],
        "type": design.get("studyType"),
        "pcd": (st.get("primaryCompletionDateStruct") or {}).get("date"),
        "status": st.get("overallStatus"),
        "first_post": (st.get("studyFirstPostDateStruct") or {}).get("date"),
        "last_update": (st.get("lastUpdatePostDateStruct") or {}).get("date") or "",
        "own": own,
    }
    if own and D.is_interventional_p23(study):
        row["own_p23"] = True
        row["partners"] = D.trial_partner_names([study])
        row["genetic"] = D.has_genetic_intervention([study])
    return row


def is_p23(row: dict) -> bool:
    return any("PHASE2" in p or "PHASE3" in p for p in row["phases"])


def needs_pit(row: dict) -> bool:
    relevant = is_p23(row) or bool(D.genomics_tags_for([row["title"][:120]]))
    return (relevant and (row["first_post"] or "9999") <= PIT_TO
            and row["last_update"] >= PIT_FROM)


def _snap(nct: str, c: dict, counters: Counter, current: dict | None) -> dict | None:
    if current is not None:
        return {"from": c["date"], "version": c["version"], "status": c.get("status"),
                "pcd": current["pcd"], "phases": current["phases"], "from_current_record": True}
    try:
        snap = B.extract_snapshot(B.fetch_version(nct, c["version"]))
    except Exception as exc:  # noqa: BLE001
        with _lock:
            counters["version_failed"] += 1
        print(f"    {nct} v{c['version']}: version FAILED ({exc})", flush=True)
        return None
    with _lock:
        counters["versions_fetched"] += 1
    return {"from": c["date"], "version": c["version"], "status": snap["status"] or c.get("status"),
            "pcd": snap["pcd"], "phases": snap["phases"]}


def pit_history(nct: str, counters: Counter, current: dict | None = None) -> dict | None:
    """Version list -> [{from, status, pcd, phases}] over the needed span, plus
    the posting-lag probes (v0 date, last version date)."""
    try:
        changes = B.fetch_history(nct)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            counters["history_failed"] += 1
        print(f"    {nct}: history FAILED ({exc})", flush=True)
        return None
    if not changes:
        with _lock:
            counters["history_empty"] += 1
        return None
    changes = sorted(changes, key=lambda c: c["version"])
    status_versions = [c for c in changes if c["version"] == 0 or "Study Status" in (c.get("moduleLabels") or [])]
    before = [c for c in status_versions if (c.get("date") or "") <= PIT_FROM]
    span = ([before[-1]] if before else []) + [c for c in status_versions
                                               if PIT_FROM < (c.get("date") or "") <= PIT_TO]
    # Bisection over the span's status versions (see docstring). The last span
    # version IS the current record when no later status version exists.
    latest_status_version = status_versions[-1]["version"] if status_versions else None
    got: dict[int, dict | None] = {}

    def snap_at(k: int) -> dict | None:
        if k not in got:
            c = span[k]
            cur = current if (current is not None and c["version"] == latest_status_version) else None
            got[k] = _snap(nct, c, counters, cur)
        return got[k]

    def same(a: dict | None, b: dict | None) -> bool:
        return bool(a and b and a["pcd"] == b["pcd"] and list(a["phases"] or []) == list(b["phases"] or []))

    def bisect_span(lo: int, hi: int) -> None:
        if hi - lo <= 1 or same(snap_at(lo), snap_at(hi)):
            return
        mid = (lo + hi) // 2
        snap_at(mid)
        bisect_span(lo, mid)
        bisect_span(mid, hi)

    if span:
        snap_at(0)
        if len(span) > 1:
            snap_at(len(span) - 1)
            bisect_span(0, len(span) - 1)
    rows = [got[k] for k in sorted(got) if got[k] is not None]
    with _lock:
        counters["versions_skipped_by_bisection"] += max(0, len(span) - len(got))
    # The version list carries each version's overall status, so status needs
    # no extra fetch: every version from the one in force on PIT_FROM onward.
    in_force = [c for c in changes if (c.get("date") or "") <= PIT_FROM]
    statuses = [{"from": c["date"], "status": c.get("status")}
                for c in (in_force[-1:] + [c for c in changes if PIT_FROM < (c.get("date") or "") <= PIT_TO])]
    return {"versions": rows, "status_list": statuses, "v0_date": changes[0].get("date"),
            "last_version_date": changes[-1].get("date"), "n_versions": len(changes)}


def main() -> None:
    t0 = time.time()
    pop = json.loads(P.OUT_POP.read_text())
    census = {r["symbol"]: r for r in P.census_today()}
    delisted = {r["symbol"]: r for r in P.delisted_in_window()}
    names = eligible(pop, census)
    print(f"population {len(pop)}; eligible (cap >= $300M on some day) {len(names)}", flush=True)

    out_names: dict[str, dict] = {}
    want: dict[str, list[str]] = {}
    counters: Counter = Counter()
    for i, p in enumerate(names):
        sym = p["symbol"]
        raw_name = (census.get(sym) or {}).get("screener_name") or (delisted.get(sym) or {}).get("screener_name") or p["name"]
        cleaned = D.clean_company_name(raw_name)
        try:
            studies = search_name(cleaned)
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym}: SEARCH FAILED ({exc})", flush=True)
            out_names[sym] = {"query": cleaned, "error": str(exc)}
            counters["search_failed"] += 1
            continue
        rows = [compact(s, cleaned) for s in studies]
        rows = [r for r in rows if r["nct"]]
        pit = [r for r in rows if needs_pit(r)]
        pit.sort(key=lambda r: r["last_update"], reverse=True)
        pit.sort(key=lambda r: not any("PHASE3" in p for p in r["phases"]))
        kept, dropped = pit[:MAX_PIT_PER_NAME], pit[MAX_PIT_PER_NAME:]
        want[sym] = [r["nct"] for r in kept]
        out_names[sym] = {"query": cleaned, "screener_name": raw_name, "n_studies": len(rows),
                          "n_pit_wanted": len(pit), "n_pit_dropped_by_cap": len(dropped),
                          "studies": rows}
        if i % 100 == 0:
            print(f"  search {i}/{len(names)}: {sum(len(v) for v in want.values())} studies need history, "
                  f"{time.time() - t0:.0f}s", flush=True)

    relevant = relevant_names(names, census)
    print(f"decision-relevant names: {len(relevant)} of {len(want)}", flush=True)
    want = {s: v for s, v in want.items() if s in relevant}
    current = {r["nct"]: {"pcd": r["pcd"], "phases": r["phases"]}
               for e in out_names.values() for r in e.get("studies") or []}
    ncts = sorted({n for v in want.values() for n in v})
    print(f"searches done: {len(out_names)} names, {len(ncts)} distinct studies need history, "
          f"{sum(v.get('n_pit_dropped_by_cap', 0) for v in out_names.values())} dropped by the per-name cap; "
          f"{time.time() - t0:.0f}s", flush=True)

    pit_out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(pit_history, n, counters, current.get(n)): n for n in ncts}
        for k, f in enumerate(as_completed(futs)):
            res = f.result()
            if res is not None:
                pit_out[futs[f]] = res
            if k % 250 == 0:
                print(f"  history {k}/{len(ncts)}: {counters['versions_fetched']} versions, "
                      f"failures {counters['history_failed']}+{counters['version_failed']}, "
                      f"{time.time() - t0:.0f}s", flush=True)

    OUT.write_text(json.dumps({
        "built": date.today().isoformat(),
        "pit_span": [PIT_FROM, PIT_TO],
        "max_pit_per_name": MAX_PIT_PER_NAME,
        "pit_names": sorted(want),
        "counters": dict(counters),
        "names": out_names,
        "pit": pit_out,
    }))
    print(f"DONE in {time.time() - t0:.0f}s: {len(out_names)} names, {len(pit_out)}/{len(ncts)} histories, "
          f"counters {dict(counters)}", flush=True)


if __name__ == "__main__":
    main()
