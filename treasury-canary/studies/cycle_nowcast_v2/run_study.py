"""Cycle nowcast v2 — the single-shot study runner (SPEC v1 §7.4, §11; task B3).

    python3 run_study.py --synthetic <bundle dir> [--freeze freeze.json] [--out results.json]
    python3 run_study.py --real --f5 <frozen F5 pull dir> --freeze freeze.json [--ads-matrix npz] [--out ...]

Order of operations (each step refuses with its own exit code; nothing is written on refusal):
  1. mode and output: results.json is written ONCE; an existing file refuses (3) unless
     --correction "<reason>" names a correction run, which writes results.correction-<k>.json
     and appends the reason to corrections.log, never touching the original. In --real the
     ONE scored run is per STUDY DIRECTORY, not per --out: any results*.json or corrections.log
     here refuses (3) whatever --out says, --out outside this directory is a usage error (9),
     and a correction run supersedes results.json here only;
  2. --real is accepted only through scoring.arm_real_run(): CNV2_SCORED_RUN=1 in the
     environment AND a freeze.json that validates as FROZEN with Casey's answers (2), the
     questions Q16 (comparator calibration store) and Q17 (target_first agreement
     reading) included — both RULED by the spec owner in SPEC v1.2 (2026-10-20); the harness
     still refuses a freeze that omits them. THIS STAGE NEVER PASSES
     --real; the synthetic dry run is the proof of the script;
  2b. --real also needs the committed state of v1 §7.4: `git status --porcelain` over the spec,
     every .py here, data/ and the freeze (when inside the repo) must be empty (10); HEAD is
     recorded in results.json; --f1 must be the gate's F1_PATH (9);
  3. freeze.json is read and validated (7); the template defaults are used for --synthetic
     only when no --freeze is given, and results.json says so;
  4. the committed hashes are verified BEFORE any scored input is read or the raw tarball is
     extracted: F6 (vintage table, issue dates, issue panels, raw tarball), F7 (ADS panel,
     reference vintage; the monthly matrix when --ads-matrix is given), F8 (vintage lists; the
     Piger history file); a mismatch or an unreadable manifest refuses (4). The F1 gate's
     fixtures (F1/F3/F4) are B1's committed fixtures, hashed into gates.fixtures;
  5. the F1 reproduction gate (gates.run_all) runs; any HARD gate row failing refuses (5),
     except the six rows SPEC v1.1 ruled DESCRIPTIVE (G04, S01_claims, S01_ens, S04, Q01, Q04);
     in --real mode the §5 comparator reproduction gate (note-literal sampling, v1.1) and the
     §6 Piger known-event checks (the 2008-02 peak label ruled) must pass too;
  5b. a correction run must have the SAME input hashes (F1, F5, F6/F7/F8, Piger, NBER, ADS
     matrix) and the same freeze as the file it supersedes — "a correction run that changes
     any hash is a new run" (v1 §7.3) — else usage (9); the comparison is recorded;
  5c. the v1 §4.1 run-day re-check of the unrevised series (T10Y3M, BAA10YM): in --real one
     listed 2026 vintage of each (the cache, else the F4 file at a listed date, header
     validated) is compared with F5 and recorded; none available refuses (8). The synthetic
     bundle has none and records that note (synthetic mode only);
  6. scoring.run_all_sections in SECTION_ORDER; a violation of the RMSE_A >= RMSE_B >= RMSE_C
     diagnostic halts the read-out: diagnostic_halt.json is written beside the output (never
     overwriting an earlier halt record), no results.json (6); a raw vintage whose bytes do not
     match the verified F6 table refuses (8);
  7. results.json: every number tagged DECISION / DESCRIPTIVE with basis, n, window; the three
     decisions with their consequence text; the sha256 of every input and of the study code;
     first/last vintage date per series; the freeze values. The non-deterministic fields are
     `generated` and, in a correction run, `correction.logged`.
Standard library + numpy + the study modules. No network; git is read only (rev-parse, status).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ads as A        # noqa: E402
import engine as E     # noqa: E402
import gates as G      # noqa: E402
import nber as NB      # noqa: E402
import piger as PG     # noqa: E402
import scoring as S    # noqa: E402
import vintages as V   # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))                # treasury-canary
SPEC_MD = os.path.join(REPO, "studies", "cycle-nowcast-v2.md")
DATA = os.path.join(HERE, "data")
DEFAULT_OUT_REAL = os.path.join(HERE, "results.json")
TEMPLATE = os.path.join(HERE, "freeze_template.json")
CODE_FILES = ("engine.py", "metrics.py", "scoring.py", "run_study.py", "synthetic.py", "gates.py",
              "vintages.py", "ads.py", "piger.py", "nber.py")
SERIES13 = tuple(G.DEPLOYED_SERIES)
# SPEC v1.1 rulings: these gate rows are DESCRIPTIVE (recorded, not blocking)
RULED_DESCRIPTIVE = {
    "G04": "v1.1: ENS_GRID_REPRO 50/50 count (361 vs 354 +/- 5) — hindsight-selector count with near-ties, gate-only quantity; DESCRIPTIVE pending Q5",
    "S01_claims": "v1.1: literal D2 scoring-mode delta row (CLAIMS rows t <= K) — recorded, the D1+D6 row stays the gate",
    "S01_ens": "v1.1: literal D2 scoring-mode delta row (ENS) — recorded, the D1+D6 row stays the gate",
    "S04": "v1.1: literal D2 scoring-mode delta row (exact counts) — recorded, the D1+D6 row stays the gate",
    "Q01": "v1.1: soft ENS_BC_S (-22.09% vs -24.2 +/- 1 pp) — QA harness not recoverable; Casey Q5",
    "Q04": "v1.1: soft ENS_BC_S onsets 4-2-1 vs 5-1-1 — QA harness not recoverable; Casey Q5",
}
PIGER_RULED_CHECKS = {"2008_peak_dated_2008-02_as_task_text": "v1.1: under the 3x80% rule as written the model dates the peak 2008-01; the text is corrected"}
EXIT = {"guard": 2, "exists": 3, "hash": 4, "gate": 5, "diagnostic": 6, "freeze": 7, "input": 8, "usage": 9, "uncommitted": 10}
# M3 / v1 §7.3: the input hashes a correction run must share with the file it supersedes (code may differ —
# that is what a correction is; spec_md is recorded, not required: the results section is written into the
# spec file after the run and must not turn a correction into a 'new run')
CORRECTION_INPUT_KEYS = ("F1", "F5", "F6_F7_F8_verified", "piger_history", "nber_turning_points", "ads_matrix")
UNREVISED_RUN_YEAR = "2026"                              # v1 §4.1: "re-checked on the run day against one 2026 vintage"


class Refusal(Exception):
    def __init__(self, kind: str, msg: str):
        super().__init__(msg)
        self.kind, self.code = kind, EXIT[kind]


def log(*a):
    print("[run_study]", *a, file=sys.stderr, flush=True)


def sha256(path: str) -> str:
    return S.sha256_file(path)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- freeze
def load_freeze(path: str | None, mode: str) -> dict:
    if mode == "real":
        if not path or not os.path.isfile(path):
            raise Refusal("guard", f"--real needs --freeze <freeze.json with Casey's answers>; {path!r} not found")
        with open(path) as f:
            fz = json.load(f)
        problems = S.validate_freeze(fz, require_frozen=True)
        src = {"source": "freeze.json", "path": os.path.relpath(path, REPO), "sha256": sha256(path)}
    else:
        if path:
            if not os.path.isfile(path):
                raise Refusal("freeze", f"--freeze {path!r} not found")
            with open(path) as f:
                fz = json.load(f)
            src = {"source": "freeze.json (synthetic dry run)", "path": os.path.abspath(path), "sha256": sha256(path)}
        else:
            with open(TEMPLATE) as f:
                fz = json.load(f)
            src = {"source": "freeze_template.json DEFAULTS — not Casey's answers (synthetic dry run only)",
                   "path": os.path.relpath(TEMPLATE, REPO), "sha256": sha256(TEMPLATE)}
        problems = S.validate_freeze(fz, require_frozen=False)
    if problems:
        raise Refusal("freeze", "freeze.json invalid: " + "; ".join(problems))
    values = {k: v for k, v in fz.items() if not k.startswith("_")}
    values["_source"] = src["source"]
    return {"values": values, **src}


# ----------------------------------------------------------------------------- hashes
def verify_hashes(expected: dict[str, str]) -> dict:
    """expected = {absolute path: sha256}. Refuses on any missing file or mismatch."""
    mism, missing, checked = [], [], 0
    for path, h in sorted(expected.items()):
        if not os.path.isfile(path):
            missing.append(path)
            continue
        got = sha256(path)
        checked += 1
        if got != h:
            mism.append({"path": path, "expected": h, "got": got})
    if missing or mism:
        raise Refusal("hash", f"frozen-input hash verification failed: {len(missing)} missing, {len(mism)} mismatched: "
                              + "; ".join(missing[:3] + [m["path"] for m in mism[:3]]))
    return {"checked": checked, "mismatches": 0, "missing": 0}


def expected_hashes_real(data: str, ads_matrix: str | None = None) -> dict[str, str]:
    """The frozen-input set F6/F7/F8 from the committed manifests (plus the F7 monthly matrix when
    --ads-matrix is given, M5). An unreadable or incomplete manifest refuses (4), never a traceback (D2)."""
    exp = {}
    try:
        with open(os.path.join(data, "vintages_panel", "build_summary.json")) as f:
            bs = json.load(f)
        for key, fn in (("vintage_table_sha256", "vintage_table.csv"), ("issue_dates_sha256", "issue_dates.csv"),
                        ("issue_panel_wide_sha256", "issue_panel_wide.csv"), ("issue_panel_long_sha256", "issue_panel_long.csv")):
            exp[os.path.join(data, "vintages_panel", fn)] = bs[key]
        if bs.get("raw_tarball"):
            exp[os.path.join(data, bs["raw_tarball"]["file"])] = bs["raw_tarball"]["sha256"]
        with open(os.path.join(data, "ads_panel", "ads_hashes.json")) as f:
            ah = json.load(f)
        exp[os.path.join(data, "ads_panel", ah["panel_file"])] = ah["panel_sha256"]
        exp[os.path.join(data, "ads_panel", ah["ref_file"])] = ah["ref_sha256"]
        if ads_matrix:
            if not ah.get("matrix_sha256"):
                raise KeyError("ads_hashes.json carries no matrix_sha256 for --ads-matrix")
            exp[os.path.abspath(ads_matrix)] = ah["matrix_sha256"]
        with open(os.path.join(data, "vintage_lists", "SHA256SUMS")) as f:
            for ln in f:
                h, fn = ln.split()
                exp[os.path.join(data, "vintage_lists", fn)] = h
        with open(os.path.join(data, "piger", "realtime_events.json")) as f:
            ev = json.load(f)
        exp[os.path.join(data, "piger", ev["source_file"])] = ev["source_sha256"]
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise Refusal("hash", f"frozen-input manifest unreadable or incomplete under {data}: {type(exc).__name__}: {exc}")
    return exp


def expected_hashes_synthetic(bundle: str) -> dict[str, str]:
    try:
        with open(os.path.join(bundle, "hashes.json")) as f:
            h = json.load(f)
        return {os.path.join(bundle, rel): v for rel, v in h.items()}
    except (OSError, ValueError, AttributeError) as exc:
        raise Refusal("hash", f"synthetic bundle hashes.json unreadable: {type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------------- gates
def f1_gate() -> dict:
    rep = G.run_all(write=False)
    hard = list(rep["summary"]["hard_fail_ids"])
    soft = list(rep["summary"]["soft_fail_ids"])
    blocking = [i for i in hard if i not in RULED_DESCRIPTIVE]
    ruled = {i: RULED_DESCRIPTIVE[i] for i in hard + soft if i in RULED_DESCRIPTIVE}
    rows = {r["id"]: {"status": r["status"], "computed": r["computed"], "target": r["target"], "tolerance": r["tolerance"]}
            for r in rep["rows"]}
    out = {"summary": {k: rep["summary"][k] for k in ("PASS", "FAIL", "INFO", "NOT_RUN", "n_rows", "deployed_module_imported")},
           "hard_fail_ids": hard, "soft_fail_ids": soft, "ruled_descriptive": ruled, "blocking": blocking,
           "fixtures": rep["fixtures"], "rows": rows, "scored": rep["scored"]}
    if blocking:
        raise Refusal("gate", f"F1 reproduction gate: HARD rows fail outside the v1.1 rulings: {blocking} — raised, never widened")
    return out


def ads_gate_real(data: str) -> dict:
    panel = A.load_panel(os.path.join(data, "ads_panel", "ads_vintage_panel.csv"))
    ref = A.load_ref_daily(os.path.join(data, "ads_panel", f"ads_vintage_{A.REF_VINTAGE}.csv"))
    with open(os.path.join(data, "ads_panel", "gate_ads.json")) as f:
        stored = json.load(f)
    ind = [{"vintage_date": r["g17_date"], "last_obs_month": A.prev_month(m)} for m, r in stored["note_literal"]["ip_days"].items() if r["g17_date"]]
    res = A.comparator_gate(panel, ref, ind)
    nl = res["note_literal"]
    ok = bool(nl["last_point"]["within_tol"] and nl["prev_month_avg"]["within_tol"])
    out = {"note_literal_pass": ok, "note_literal": {k: nl[k] for k in ("last_point", "prev_month_avg")},
           "every_vintage_descriptive": {k: {kk: res[k][kk] for kk in ("n", "corr", "target", "tol")} for k in ("last_point", "prev_complete_month_avg")},
           "right_line_quoted": res["right_line_quoted_not_gated"], "ruling": "v1.1: gate = the accuracy note's IP-release-day sampling; every-vintage correlations DESCRIPTIVE"}
    if not ok:
        raise Refusal("gate", "ADS comparator reproduction gate (note-literal sampling) fails")
    return out


def piger_gate(summary: dict) -> dict:
    checks = summary["known_event_checks"]
    failing = [k for k, c in checks.items() if not c["pass"] and k not in PIGER_RULED_CHECKS]
    out = {"checks": {k: c["pass"] for k, c in checks.items()}, "ruled": {k: v for k, v in PIGER_RULED_CHECKS.items() if k in checks and not checks[k]["pass"]},
           "blocking": failing}
    if failing:
        raise Refusal("gate", f"Piger known-event checks fail outside the ruling: {failing}")
    return out


# ----------------------------------------------------------------------------- inputs
def _daily_raw(f5_dir: str, sids=("T10Y3M", "BAA10YM", "GS10", "TB3MS")) -> dict:
    out = {}
    for sid in sids:
        p = os.path.join(f5_dir, sid + ".csv")
        if os.path.exists(p):
            _, rows = E.read_fred_csv(p, sid)
            out[sid] = [(d, v) for d, v in rows if v.strip() not in ("", ".") and d >= "1959-01-01"]
    return out


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _compare_unrevised(rec: dict, current_csv: str) -> dict:
    """vintages.unrevised_check's comparison on an already-parsed, header-validated vintage record."""
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
    return {"series": rec["series"], "vintage_date": rec["vintage_date"], "vintage_sha256": rec["sha256"],
            "current_file": os.path.basename(current_csv), "current_header": hdr, "n_vintage": len(vint), "n_current": len(cur),
            "n_common": len(common), "n_changed": len(changed),
            "max_abs_change": max((abs(a - b) for _, a, b in changed), default=0.0), "changed_examples": changed[:5],
            "unrevised": len(changed) == 0}


def unrevised_recheck(mode: str, paths: dict, run_year: str = UNREVISED_RUN_YEAR) -> list:
    """v1 §4.1: T10Y3M and BAA10YM are taken current, 're-checked on the run day against one 2026 vintage
    and recorded in results.json'. For each unrevised series the listed `run_year` vintage comes from (1) the
    raw cache (latest cached listed vintage) or (2) the F4 file data/alfred_shutdown/alf_<ID>_<date>.csv at
    a LISTED date, read explicitly and validated like a served vintage (header date == listed date). In
    --real a series with neither refuses (8): the run-day F8 re-pull must fetch one by list first (S2). The
    synthetic bundle carries no such vintage; that is recorded as a note in synthetic mode only."""
    cache, lists, f5_dir = paths["cache"], paths["lists"], paths["f5"]
    out = []
    for sid in V.UNREVISED_SERIES:
        cur = os.path.join(f5_dir, sid + ".csv")
        if not os.path.exists(cur):
            if mode == "real":
                raise Refusal("input", f"F5 pull lacks {sid}.csv: the §4.1 unrevised re-check cannot run")
            continue
        lp = os.path.join(lists, f"vd_{sid}.txt")
        listed = V.load_vintage_list(lists, sid) if os.path.exists(lp) else []
        wanted = [v for v in listed if v >= f"{run_year}-01-01"]
        rec, source = None, None
        if os.path.isdir(os.path.join(cache, sid)):
            cached = [v for v in wanted if os.path.exists(V.cache_path(cache, sid, v))]
            if cached:
                rec, source = V.read_cached(cache, sid, cached[-1]), "raw cache (listed vintage)"
        if rec is None and paths.get("f4_dir") and os.path.isdir(paths["f4_dir"]):
            for v in sorted(wanted, reverse=True):
                p = os.path.join(paths["f4_dir"], f"alf_{sid}_{v}.csv")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        body = f.read()
                    rec, source = V.parse_alfred_csv(body, sid, v), f"F4 file {os.path.relpath(p, HERE)} (listed date, header validated)"
                    break
        if rec is None:
            if mode == "real":
                raise Refusal("input", f"v1 §4.1 run-day re-check: no listed {run_year} vintage of {sid} is available (raw cache or F4 file); "
                                       f"the run-day F8 re-pull must fetch one by list ({len(listed)} dates listed, {len(wanted)} in {run_year}) before --real")
            continue
        out.append({**_compare_unrevised(rec, cur), "source": source,
                    "basis": f"v1 §4.1: one listed {run_year} vintage vs the F5 pull on common observation dates"})
    if not out and mode == "synthetic":
        out.append({"note": "no archived vintage of an unrevised series in the synthetic bundle: series current by construction (synthetic dry run only)"})
    return out


def _ads_matrix(path: str | None):
    if not path:
        return None
    z = np.load(path)
    months = [str(m) for m in z["months"]]
    return {"months": months, "vintage_dates": [str(v) for v in z["vintage_dates"]], "sums": z["sums"], "counts": z["counts"],
            "_midx": {m: i for i, m in enumerate(months)}}


def load_inputs(mode: str, paths: dict, freeze: dict, hashes: dict) -> tuple[S.StudyInputs, dict]:
    """Shared loader: paths = {f5, f1, cache, lists, panel, ads_panel, ads_matrix, piger_xlsx, nber_csv, usrec_csv}."""
    f5 = E.load_fred_csv_dir(paths["f5"], list(SERIES13))
    missing = [s for s in E.COIN_MEMBERS + ("ICSA", "T10Y3M", "USREC") if s not in f5]
    if missing:
        raise Refusal("input", f"F5 pull lacks {missing}")
    f1 = E.load_fixture_json(paths["f1"]) if paths.get("f1") and os.path.exists(paths["f1"]) else None
    cache, lists = paths["cache"], paths["lists"]
    issue_rows = _read_csv(os.path.join(paths["panel"], "issue_panel_wide.csv"))
    issue_dates_rows = _read_csv(os.path.join(paths["panel"], "issue_dates.csv"))
    vtable = _read_csv(os.path.join(paths["panel"], "vintage_table.csv"))
    vlists = {}
    for sid in ("PAYEMS", "INDPRO", "W875RX1", V.PI_SERIES):
        p = os.path.join(lists, f"vd_{sid}.txt")
        if os.path.exists(p):
            vlists[sid] = V.load_vintage_list(lists, sid)
    panel = A.load_panel(paths["ads_panel"]) if paths.get("ads_panel") and os.path.exists(paths["ads_panel"]) else []
    releases = PG.load_history(paths["piger_xlsx"]) if paths.get("piger_xlsx") and os.path.exists(paths["piger_xlsx"]) else []
    alfred = PG.alfred_vectors(releases, cache, lists) if releases and os.path.isdir(os.path.join(cache, PG.ALFRED_SERIES)) else None
    nb = NB.build(paths["nber_csv"], paths["usrec_csv"]) if paths.get("nber_csv") and os.path.exists(paths["nber_csv"]) else {}
    nb.pop("built", None)
    # unrevised re-check (v1 §4.1, S2): one listed 2026 vintage of each unrevised series vs the F5 pull; --real refuses without one
    unrev = unrevised_recheck(mode, paths)
    for r in unrev:
        if r.get("unrevised") is False:
            log(f"WARNING §4.1: {r['series']} changed {r['n_changed']} values between vintage {r['vintage_date']} and F5 (max {r['max_abs_change']}) — recorded")
    extra = {}
    if mode == "synthetic":
        with open(paths["manifest"]) as f:
            man = json.load(f)
        extra = {"manifest": man, "shutdown_windows": man["shutdown_windows"], "regime_i_start": man["regime_i_start"],
                 "regime_ii_window": man["regime_ii_window"]}
    inp = S.StudyInputs(mode, f5, freeze=freeze["values"], f5_daily=_daily_raw(paths["f5"]), f1=f1,
                        as_of=lambda d: V.as_of(d, cache, lists), issue_rows=issue_rows, issue_dates_rows=issue_dates_rows,
                        vintage_table=vtable, vintage_lists=vlists, ads_panel=panel, ads_matrix=_ads_matrix(paths.get("ads_matrix")),
                        piger_releases=releases, piger_alfred=alfred, nber=nb, unrevised=unrev, hashes=hashes,
                        labels={"f5": os.path.basename(os.path.normpath(paths["f5"]))}, **extra)
    spans = {"f5_series": {s: [min(d), max(d)] for s, d in f5.items() if d},
             "vintages": {sid: [min(r["vintage_date"] for r in vtable if r["series"] == sid), max(r["vintage_date"] for r in vtable if r["series"] == sid)]
                          for sid in sorted({r["series"] for r in vtable})},
             "issue_rows": [issue_rows[0]["issue_date"], issue_rows[-1]["issue_date"]] if issue_rows else None,
             "ads_vintages": [panel[0]["vintage_date"], panel[-1]["vintage_date"]] if panel else None,
             "piger_releases": [releases[0]["release_date"], releases[-1]["release_date"]] if releases else None,
             "vintage_lists": {k: [v[0], v[-1], len(v)] for k, v in vlists.items()}}
    return inp, spans


def paths_synthetic(bundle: str, ads_matrix: str | None) -> dict:
    b = os.path.abspath(bundle)
    return {"f5": os.path.join(b, "f5"), "f1": os.path.join(b, "f1", "fixtures_cycle_fred.json"),
            "cache": os.path.join(b, "vintages", "cache"), "lists": os.path.join(b, "vintages", "lists"),
            "panel": os.path.join(b, "vintages", "panel"), "ads_panel": os.path.join(b, "ads", "ads_vintage_panel.csv"),
            "ads_matrix": ads_matrix if ads_matrix is not None else os.path.join(b, "ads", "ads_monthly_matrix.npz"),
            "piger_xlsx": os.path.join(b, "piger", "History_of_Real_Time_Recession_Probabilities.xlsx"),
            "nber_csv": os.path.join(b, "nber", "nber_turning_points_announcements.csv"),
            "usrec_csv": os.path.join(b, "f5", "USREC.csv"), "manifest": os.path.join(b, "manifest.json"), "f4_dir": None}


def paths_real(f5: str, f1: str, data: str, cache: str | None, ads_matrix: str | None) -> dict:
    """Called only AFTER verify_hashes (N5/D4): the raw tarball under --data is extracted here, so its bytes
    were verified before extraction; a --cache directory is verified vintage by vintage in scoring (M4)."""
    tar = os.path.join(data, os.path.basename(V.RAW_TARBALL))
    return {"f5": os.path.abspath(f5), "f1": f1, "cache": V.resolve_cache(cache, tar_path=tar, log=log), "lists": os.path.join(data, "vintage_lists"),
            "panel": os.path.join(data, "vintages_panel"), "ads_panel": os.path.join(data, "ads_panel", "ads_vintage_panel.csv"),
            "ads_matrix": ads_matrix, "piger_xlsx": os.path.join(data, "piger", "History_of_Real_Time_Recession_Probabilities.xlsx"),
            "nber_csv": os.path.join(data, "nber", "nber_turning_points_announcements.csv"),
            "usrec_csv": os.path.join(os.path.abspath(f5), "USREC.csv"), "f4_dir": os.path.join(data, "alfred_shutdown")}


def input_hashes(mode: str, paths: dict, expected: dict) -> dict:
    """sha256 of every input file: F1, F5 (per file), F6/F7/F8 (the verified set), Piger, NBER."""
    h = {"F1": {os.path.basename(paths["f1"]): sha256(paths["f1"])} if paths.get("f1") and os.path.exists(paths["f1"]) else None,
         "F5": {fn: sha256(os.path.join(paths["f5"], fn)) for fn in sorted(os.listdir(paths["f5"])) if fn.endswith(".csv")},
         "F6_F7_F8_verified": {os.path.relpath(p, HERE if mode == "real" else os.path.dirname(paths["manifest"]) if mode == "synthetic" else HERE): v
                               for p, v in sorted(expected.items())},
         "piger_history": sha256(paths["piger_xlsx"]) if os.path.exists(paths["piger_xlsx"]) else None,
         "nber_turning_points": sha256(paths["nber_csv"]) if os.path.exists(paths["nber_csv"]) else None,
         "ads_matrix": sha256(paths["ads_matrix"]) if paths.get("ads_matrix") and os.path.exists(paths["ads_matrix"]) else None,
         "spec_md": sha256(SPEC_MD) if os.path.exists(SPEC_MD) else None,
         "code": {fn: sha256(os.path.join(HERE, fn)) for fn in CODE_FILES if os.path.exists(os.path.join(HERE, fn))}}
    return h


# ----------------------------------------------------------------------------- output
def resolve_output(out: str, correction: str | None) -> tuple[str, dict | None]:
    if not os.path.exists(out):
        if correction:
            raise Refusal("usage", f"--correction given but {out} does not exist: a correction run needs an original results.json")
        return out, None
    if not correction:
        raise Refusal("exists", f"{out} exists: results.json is written once; a correction run needs --correction \"<reason>\"")
    base, ext = os.path.splitext(out)
    k = 1
    while os.path.exists(f"{base}.correction-{k}{ext}"):
        k += 1
    rec = {"k": k, "reason": correction, "supersedes": os.path.basename(out), "supersedes_sha256": sha256(out), "logged": utc_now()}
    return f"{base}.correction-{k}{ext}", rec


def real_output_guard(out: str, correction: str | None, here: str = HERE) -> str:
    """M2: in --real the ONE scored run is per study directory. --out must lie in `here` (9); any
    results*.json or corrections.log already in `here` refuses a non-correction run (3) whatever --out
    says; a correction run supersedes `here`/results.json only (9). Returns the absolute --out."""
    out_abs = os.path.abspath(out)
    if os.path.dirname(out_abs) != os.path.abspath(here):
        raise Refusal("usage", f"--real writes only inside the study directory {here}; got {out_abs}")
    existing = sorted(fn for fn in os.listdir(here) if (fn.startswith("results") and fn.endswith(".json")) or fn == "corrections.log")
    if existing and not correction:
        raise Refusal("exists", f"a scored run already exists in {here} ({existing}): real data are scored ONCE; a correction run needs --correction \"<reason>\"")
    if correction and out_abs != os.path.join(os.path.abspath(here), "results.json"):
        raise Refusal("usage", f"a --real correction run supersedes {os.path.join(here, 'results.json')} only; got {out_abs}")
    return out_abs


def check_correction_inputs(correction: dict, original_path: str, hashes: dict, freeze: dict) -> dict:
    """M3 / v1 §7.3 'a correction run that changes any hash is a new run': the superseded results.json must
    carry the same input hashes (CORRECTION_INPUT_KEYS) and the same freeze.sha256; otherwise usage (9).
    The comparison (and whether spec_md / code changed) is recorded in the correction record."""
    try:
        with open(original_path) as f:
            orig = json.load(f)
    except (OSError, ValueError) as exc:
        raise Refusal("usage", f"correction run: cannot read the superseded {original_path}: {exc}")
    oh = (orig.get("inputs") or {}).get("hashes") or {}
    diffs = [k for k in CORRECTION_INPUT_KEYS if oh.get(k) != hashes.get(k)]
    fz_same = (orig.get("freeze") or {}).get("sha256") == freeze.get("sha256")
    if diffs or not fz_same:
        raise Refusal("usage", f"correction run refused: inputs differ from {os.path.basename(original_path)} in "
                               f"{diffs + ([] if fz_same else ['freeze.sha256'])}: a run that changes any input hash is a NEW run (v1 §7.3), not a correction")
    correction.update({"inputs_identical": True, "compared": list(CORRECTION_INPUT_KEYS) + ["freeze.sha256"],
                       "superseded_run_id": orig.get("run_id"), "spec_md_identical": oh.get("spec_md") == hashes.get("spec_md"),
                       "code_identical": oh.get("code") == hashes.get("code")})
    return correction


def git_state(paths: list[str]) -> dict:
    """HEAD and `git status --porcelain` over `paths` (read-only git commands; M6 / v1 §7.4)."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
        por = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--"] + list(paths),
                             cwd=HERE, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"head": None, "clean": None, "dirty": None, "error": str(exc)}
    dirty = [ln.rstrip("\n") for ln in por.splitlines() if ln.strip()]
    return {"head": head, "clean": not dirty, "dirty": dirty, "paths_checked": [os.path.relpath(p, REPO) for p in paths]}


def committed_state_paths(freeze_path: str | None) -> list[str]:
    paths = [SPEC_MD] + sorted(glob.glob(os.path.join(HERE, "*.py"))) + [DATA]
    if freeze_path and os.path.abspath(freeze_path).startswith(os.path.abspath(os.path.join(HERE, "..", "..", "..")) + os.sep):
        paths.append(os.path.abspath(freeze_path))
    return paths


def require_committed_state(freeze_path: str | None) -> dict:
    """M6 / v1 §7.4: --real refuses (10) unless the spec, every study .py, data/ and the freeze (when inside
    the repo) are committed; HEAD is recorded in results.json."""
    st = git_state(committed_state_paths(freeze_path))
    if st.get("head") is None:
        raise Refusal("uncommitted", f"--real needs a git checkout to verify the committed state (v1 §7.4): {st.get('error')}")
    if not st["clean"]:
        raise Refusal("uncommitted", f"--real refused: uncommitted changes in the spec / study code / data / freeze (v1 §7.4): "
                                     f"{st['dirty'][:6]}{' ...' if len(st['dirty']) > 6 else ''}")
    return st


def write_once(path: str, payload: dict) -> None:
    body = json.dumps(S._py(payload), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    with open(path, "x", encoding="utf-8") as f:      # 'x': never overwrites
        f.write(body)


def write_halt(dirname: str, halt: dict) -> str:
    """N2: the halt record never overwrites an earlier one ('x'; a timestamped name when one exists)."""
    hp = os.path.join(dirname, "diagnostic_halt.json")
    try:
        with open(hp, "x") as f:
            json.dump(S._py(halt), f, indent=1, sort_keys=True)
    except FileExistsError:
        hp = os.path.join(dirname, "diagnostic_halt." + halt["generated"].replace("-", "").replace(":", "") + ".json")
        with open(hp, "x") as f:
            json.dump(S._py(halt), f, indent=1, sort_keys=True)
    return hp


def run_id(hashes: dict, freeze: dict, mode: str) -> str:
    """Deterministic identity of a run: code + verified inputs + F5 + F1 + freeze values + mode."""
    import hashlib
    key = {"code": hashes["code"], "inputs": hashes["F6_F7_F8_verified"], "F5": hashes["F5"], "F1": hashes["F1"],
           "freeze": freeze["values"], "mode": mode}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def tag_audit(results: dict) -> dict:
    """Every numeric leaf under `results` must sit inside a tagged record (v1 §8)."""
    untagged, n_tagged = [], 0

    def walk(o, path, inside):
        nonlocal n_tagged
        if isinstance(o, dict):
            if "tag" in o and "value" in o:
                n_tagged += 1
                inside = True
            for k, v in o.items():
                walk(v, path + [str(k)], inside)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + [str(i)], inside)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            if not inside:
                untagged.append("/".join(path))
    walk(results, [], False)
    return {"tagged_records": n_tagged, "untagged_numeric_leaves": untagged[:50], "n_untagged": len(untagged)}


# ----------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--synthetic", metavar="BUNDLE_DIR", help="score the synthetic bundle (the dry run)")
    g.add_argument("--real", action="store_true", help=f"the ONE scored run: needs {S.ENV_FLAG}=1 and a FROZEN freeze.json")
    p.add_argument("--freeze", default=None, help="freeze.json with Casey's answers (required with --real)")
    p.add_argument("--f5", default=None, help="frozen F5 pull directory of FRED CSVs (required with --real)")
    p.add_argument("--f1", default=G.F1_PATH, help="F1 fixture (default backend/tests/fixtures_cycle_fred.json)")
    p.add_argument("--data", default=DATA, help="committed data directory (F6/F7/F8)")
    p.add_argument("--cache", default=None, help="raw ALFRED cache dir (default: the committed tarball)")
    p.add_argument("--ads-matrix", default=None, help="F7 monthly sum/count matrix npz (smoothed-fit sensitivity)")
    p.add_argument("--out", default=None, help="results path (default: results.json here for --real; <bundle>/results.json for --synthetic)")
    p.add_argument("--correction", default=None, metavar="REASON", help="a labelled correction run (writes results.correction-<k>.json)")
    p.add_argument("--skip-f1-gate", action="store_true", help="synthetic only: skip the (real) F1 reproduction gate")
    return p


def run(argv=None) -> int:
    a = build_parser().parse_args(argv)
    mode = "real" if a.real else "synthetic"
    out = a.out or (DEFAULT_OUT_REAL if mode == "real" else os.path.join(os.path.abspath(a.synthetic), "results.json"))
    git = None
    try:
        if mode == "real":
            if a.skip_f1_gate:
                raise Refusal("usage", "--skip-f1-gate is refused with --real")
            if not a.f5 or not os.path.isdir(a.f5):
                raise Refusal("usage", "--real needs --f5 <frozen F5 pull directory>")
            S.arm_real_run(a.freeze)                                  # the guard (RealDataGuard -> refusal 2)
            out = real_output_guard(out, a.correction)                # M2: one scored run per study directory
            git = require_committed_state(a.freeze)                   # M6: v1 §7.4 committed state
            if os.path.abspath(a.f1) != os.path.abspath(G.F1_PATH):   # M5: the honesty ENS_HH-on-F1 runs on the gate's F1
                raise Refusal("usage", f"--real pins --f1 to the gate's F1_PATH {G.F1_PATH}; got {a.f1}")
        out_path, correction = resolve_output(out, a.correction)
        freeze = load_freeze(a.freeze, mode)
        # N5/D4: hashes are verified BEFORE any scored input is read or the raw tarball is extracted
        expected = expected_hashes_synthetic(a.synthetic) if mode == "synthetic" else expected_hashes_real(a.data, a.ads_matrix)
        log("verifying frozen-input hashes")
        hv = verify_hashes(expected)
        paths = paths_synthetic(a.synthetic, a.ads_matrix) if mode == "synthetic" else paths_real(a.f5, a.f1, a.data, a.cache, a.ads_matrix)
        gates = {}
        if a.skip_f1_gate:
            gates["F1_reproduction"] = {"skipped": True, "reason": "--skip-f1-gate (synthetic dry run only)"}
        else:
            log("F1 reproduction gate")
            gates["F1_reproduction"] = f1_gate()
        if mode == "real":
            log("ADS comparator reproduction gate")
            gates["ADS_comparator"] = ads_gate_real(a.data)
        else:
            gates["ADS_comparator"] = {"not_applicable": "synthetic archive: the §5 targets (0.866 / 0.956 vs the 2010-12-03 vintage) are properties of the real archive; run in --real only"}
        hashes = input_hashes(mode, paths, expected)
        if correction:                                                # M3: same inputs and freeze as the superseded file
            correction = check_correction_inputs(correction, out, hashes, freeze)
        log("loading inputs")
        inp, spans = load_inputs(mode, paths, freeze, hashes)
        if inp.piger_releases:
            _, psum = PG.build_path(inp.piger_releases, inp.piger_alfred)
            gates["piger_known_events"] = piger_gate(psum) if mode == "real" else {"not_gated_synthetic": {k: c["pass"] for k, c in psum["known_event_checks"].items()}}
        log("scoring sections:", ", ".join(S.SECTION_ORDER))
        res = S.run_all_sections(inp, log=lambda s: log("  section", s))
        if not res["diagnostic_holds"]:
            halt = {"halted": True, "reason": "v1 §3 diagnostic RMSE_A >= RMSE_B >= RMSE_C violated: read-out halted, bug hunt before any result is quoted",
                    "diagnostic": res["diagnostic"], "generated": utc_now(), "mode": mode}
            hp = write_halt(os.path.dirname(out_path), halt)
            raise Refusal("diagnostic", f"diagnostic violated; see {hp}; no results written")
        R = res["results"]
        payload = {
            "study": "cycle nowcast v2 — " + ("SCORED RUN (real data)" if mode == "real" else "SYNTHETIC DRY RUN (no real number scored)"),
            "spec": {"file": os.path.relpath(SPEC_MD, REPO), "version": "SPEC v1 (2026-10-20) + v1.1 amendments", "sha256": hashes["spec_md"]},
            "generated": utc_now(),
            "mode": mode, "scored_real_data": mode == "real",
            "run_id": run_id(hashes, freeze, mode),
            "freeze": freeze,
            "inputs": {"paths": {k: (os.path.relpath(v, REPO) if isinstance(v, str) and v.startswith(REPO) else (os.path.basename(v) if isinstance(v, str) else v)) for k, v in paths.items()},
                       "hash_verification": hv, "hashes": hashes, "spans": spans,
                       "synthetic_manifest": {k: v for k, v in (inp.manifest or {}).items() if k not in ("structure", "params")} if mode == "synthetic" else None},
            "gates": gates,
            "git": git,
            "section_order": list(S.SECTION_ORDER),
            "decisions": {"D1_primary": R["decision_D1"]["outcome"]["value"], "D2_completed_vs_partial": R["decision_D2"]["outcome"]["value"],
                          "D3_comparator": R["decision_D3"]["outcome"]["value"],
                          "consequences": {"D1": R["decision_D1"]["consequence"]["value"], "D2": R["decision_D2"]["consequence"]["value"],
                                           "D3": R["decision_D3"]["consequence"]["value"]}},
            "results": R,
            "board_bands": res["private"]["board_bands"],
            "correction": correction,
            "statement": ("Every number under 'results' is a tagged record {tag: DECISION | DESCRIPTIVE, value, basis, n, window, spec}; "
                          "no descriptive number is a pass or fail. gates.F1_reproduction is the pre-registered v1 §7.1 / §7.2 gate "
                          "(gates.run_all) on the committed REAL fixtures F1 / F3 / F4 — the same rows as gate_report_F1.json, no study metric. "
                          + ("Real data were scored exactly once by this invocation." if mode == "real"
                             else "Synthetic inputs only: every number under 'results' is synthetic; no real panel was scored. ")
                          + ("The non-deterministic fields are `generated` and `correction.logged`." if correction else "The only non-deterministic field is `generated`.")),
        }
        payload["tag_audit"] = tag_audit(R)
        write_once(out_path, payload)
        if correction:
            with open(os.path.join(os.path.dirname(out_path), "corrections.log"), "a") as f:
                f.write(json.dumps({**correction, "file": os.path.basename(out_path)}, sort_keys=True) + "\n")
        log("written:", out_path, "| decisions:", payload["decisions"]["D1_primary"], payload["decisions"]["D2_completed_vs_partial"], payload["decisions"]["D3_comparator"])
        return 0
    except Refusal as r:
        log(f"REFUSED ({r.kind}, exit {r.code}): {r}")
        return r.code
    except S.RealDataGuard as g:
        log(f"REFUSED (guard, exit {EXIT['guard']}): {g}")
        return EXIT["guard"]
    except S.InputIntegrityError as e:
        log(f"REFUSED (input, exit {EXIT['input']}): {e}")
        return EXIT["input"]
    finally:
        S.disarm()


if __name__ == "__main__":
    sys.exit(run())
