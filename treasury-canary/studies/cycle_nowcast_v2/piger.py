"""Chauvet-Piger real-time release history for the cycle-nowcast v2 study (SPEC v1 §6).

Input: Piger's ``History_of_Real_Time_Recession_Probabilities.xlsx`` (one column per release,
header = release date, rows = observation months, values in DECIMAL units; x100 = percent, the
FRED/ALFRED RECPROUSM156N units). Known header quirk (research pass §1, R2 F5): the column for
the 2026-01-30 release is headed 2025-01-30; it is detected as a non-monotone header and
corrected by +1 year, and the correction is flagged on the row.

Outputs (``data/piger/``):
  realtime_path.csv   - the first-release path by RELEASE DATE: one row per release with the
                        latest month, its probability as released (percent), the ALFRED
                        RECPROUSM156N value vector chosen by the §6 rule (first ALFRED vintage
                        dated >= d_r whose latest observation month is m_r; fallback: Piger's
                        column), the cross-validation gap, the release lag and the rule states;
  realtime_events.json - the declarations of the published 3x80% / 3x20% rule with the
                        peak-dating step (peak = the month before the first >= 50% month of the
                        chain preceding the trigger; Chauvet-Piger 2008) and of the 1-month
                        >= 50% sensitivity rule, plus the checks on the known events.

Rules are applied release by release to that release's own vector (a real-time analyst sees
only the current release); months before ``scan_from`` (default 2001-12, the month after the
last NBER trough preceding the first release) are not scanned, so the historical recessions in
the back-history cannot trigger. Descriptive throughout; no composite or nowcast is computed.
Standard library only for the logic; openpyxl (pinned) reads the workbook.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import hashlib
import json
import os
import sys

HIST_URL = "https://jeremypiger.com/assets/files/History_of_Real_Time_Recession_Probabilities.xlsx"
ALFRED_SERIES = "RECPROUSM156N"
SCAN_FROM = "2001-12"           # month after the 2001-11 NBER trough (first release is 2006-08-01)
HI, LO, HALF = 0.80, 0.20, 0.50
SENS_TH = 0.50

PATH_FIELDS = ["release_date", "header_as_in_file", "header_corrected", "latest_month",
               "piger_latest_pct", "n_months", "release_lag_days", "value_source",
               "alfred_vintage_date", "alfred_vintage_sha256", "alfred_latest_month",
               "alfred_latest_pct", "alfred_vs_piger_max_abs_diff_pct", "alfred_n_common",
               "rule_3x80_state", "rule_3x80_event", "rule_1m50_fires",
               "max_pct_in_release_since_scan_from"]


class PigerError(Exception):
    pass


# ----------------------------------------------------------------------------- parsing

def _to_date(x) -> str | None:
    if isinstance(x, dt.datetime):
        return x.date().isoformat()
    if isinstance(x, dt.date):
        return x.isoformat()
    if isinstance(x, str) and len(x) >= 10 and x[4] == "-" and x[7] == "-":
        return x[:10]
    return None


def fix_headers(headers: list[str]) -> tuple[list[str], list[bool]]:
    """Release dates must increase strictly. A header <= its predecessor whose +1-year shift
    lands strictly between its neighbours is corrected and flagged (Piger's 2025-01-30 typo for
    the 2026-01-30 release). Any other disorder is an error, never silently reordered."""
    out, flags = [], []
    for i, h in enumerate(headers):
        fixed, flag = h, False
        if i and h <= out[-1]:
            cand = f"{int(h[:4]) + 1:04d}{h[4:]}"
            nxt = headers[i + 1] if i + 1 < len(headers) else None
            # a year typo is accepted only when the shifted date is sandwiched strictly between
            # both neighbours; a duplicate, a last-column disorder or anything else is an error
            if h != out[-1] and nxt is not None and out[-1] < cand < nxt:
                fixed, flag = cand, True
            else:
                raise PigerError(f"non-monotone release header {h} after {out[-1]} not fixable")
        out.append(fixed)
        flags.append(flag)
    return out, flags


def parse_rows(hdr: list, rows: list) -> list[dict]:
    """Core parser (openpyxl-free for tests): hdr[0] blank, hdr[1:] release dates; each row =
    (month, p_release1, p_release2, ...) in decimals. Returns releases sorted by release date."""
    raw = [_to_date(h) for h in hdr[1:]]
    if any(h is None for h in raw):
        bad = [i for i, h in enumerate(raw) if h is None]
        raise PigerError(f"non-date release headers at columns {bad[:5]}")
    fixed, flags = fix_headers(raw)
    months = []
    for r in rows:
        m = _to_date(r[0])
        if m is None:
            continue
        months.append((m[:7], r))
    releases = []
    for j, (d_raw, d_fix, flag) in enumerate(zip(raw, fixed, flags)):
        col = j + 1
        vec = []
        for m, r in months:
            v = r[col] if col < len(r) else None
            if v is None or v == "":
                continue
            v = float(v)
            if not (0.0 <= v <= 1.0):
                raise PigerError(f"value out of [0,1] at release {d_fix} month {m}: {v}")
            vec.append((m, v))
        if not vec:
            raise PigerError(f"empty release column {d_fix}")
        ms = [m for m, _ in vec]
        if ms != sorted(ms) or len(set(ms)) != len(ms):
            raise PigerError(f"months not increasing in release {d_fix}")
        releases.append({"release_date": d_fix, "header_as_in_file": d_raw,
                         "header_corrected": flag, "months": ms, "probs": [v for _, v in vec],
                         "latest_month": ms[-1], "latest_prob": vec[-1][1]})
    releases.sort(key=lambda r: r["release_date"])
    for a, b in zip(releases, releases[1:]):
        if b["latest_month"] < a["latest_month"]:
            raise PigerError(f"latest month goes backwards {a['release_date']}->{b['release_date']}")
    for r in releases:
        if r["latest_month"] + "-01" > r["release_date"]:
            raise PigerError(f"release {r['release_date']} dated before its latest month {r['latest_month']}")
    return releases


def load_history(xlsx_path: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    return parse_rows(list(rows[0]), rows[1:])


# ----------------------------------------------------------------------------- helpers

def month_end(m: str) -> dt.date:
    y, mo = int(m[:4]), int(m[5:7])
    return dt.date(y, mo, calendar.monthrange(y, mo)[1])


def add_months(m: str, k: int) -> str:
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def release_lag_days(r: dict) -> int:
    return (dt.date.fromisoformat(r["release_date"]) - month_end(r["latest_month"])).days


# ----------------------------------------------------------------------------- rules

def _run(probs, i, n, pred) -> bool:
    return i + n <= len(probs) and all(pred(p) for p in probs[i:i + n])


def _chain_back(months, probs, i, pred) -> str:
    """Earliest month of the maximal chain ending at i-1 (inclusive) whose values satisfy pred,
    i.e. the 'first >= 50% month preceding the trigger'. If month i-1 fails pred the chain is
    empty and the first such month is the trigger month i itself."""
    j = i
    while j - 1 >= 0 and pred(probs[j - 1]):
        j -= 1
    return months[j]


def rule_3x80(releases: list[dict], hi: float = HI, lo: float = LO, half: float = HALF,
              scan_from: str = SCAN_FROM, strict: bool = True) -> tuple[list[dict], list[str]]:
    """Published rule: three consecutive months > hi (>= hi if strict=False) = recession start,
    declared at the first release whose vector shows it; three consecutive months < lo after
    the start triple = expansion. Peak = month before the first >= half month of the chain
    preceding the start triple; trough (symmetric, this study's extension) = month before the
    first < half month of the chain preceding the end triple. Returns (events, state after each
    release)."""
    above = (lambda p: p > hi) if strict else (lambda p: p >= hi)
    below = (lambda p: p < lo) if strict else (lambda p: p <= lo)
    state, cursor = "expansion", scan_from
    events, states = [], []
    for r in releases:
        months, probs = r["months"], r["probs"]
        start_i = next((k for k, m in enumerate(months) if m >= cursor), len(months))
        if state == "expansion":
            for i in range(start_i, len(months) - 2):
                if _run(probs, i, 3, above):
                    first_half = _chain_back(months, probs, i, lambda p: p >= half)
                    j0 = months.index(first_half)
                    chain = {months[k]: round(100 * probs[k], 2) for k in range(max(0, j0 - 1), i + 1)}
                    events.append({"kind": "recession_start", "release_date": r["release_date"],
                                   "chain_pct": chain,
                                   "latest_month": r["latest_month"],
                                   "trigger_months": months[i:i + 3],
                                   "trigger_pct": [round(100 * p, 2) for p in probs[i:i + 3]],
                                   "first_half_month": first_half,
                                   "first_recession_month": first_half,
                                   "peak_month": add_months(first_half, -1),
                                   "months_after_peak": (int(r["release_date"][:4]) * 12 + int(r["release_date"][5:7])
                                                         - int(first_half[:4]) * 12 - int(first_half[5:7]) + 1)})
                    state, cursor = "recession", months[min(i + 3, len(months) - 1)]
                    break
        else:
            for i in range(start_i, len(months) - 2):
                if _run(probs, i, 3, below):
                    first_low = _chain_back(months, probs, i, lambda p: p < half)
                    events.append({"kind": "recession_end", "release_date": r["release_date"],
                                   "latest_month": r["latest_month"],
                                   "trigger_months": months[i:i + 3],
                                   "trigger_pct": [round(100 * p, 2) for p in probs[i:i + 3]],
                                   "first_below_half_month": first_low,
                                   "trough_month": add_months(first_low, -1)})
                    state, cursor = "expansion", months[min(i + 3, len(months) - 1)]
                    break
        states.append(state)
    return events, states


def rule_1m50(releases: list[dict], th: float = SENS_TH) -> list[dict]:
    """Sensitivity: the latest month of a release reads >= th. Returns one record per firing
    release, grouped into episodes (consecutive firing releases)."""
    out, ep = [], 0
    prev_fired = False
    for r in releases:
        fired = r["latest_prob"] >= th
        if fired:
            if not prev_fired:
                ep += 1
            out.append({"release_date": r["release_date"], "latest_month": r["latest_month"],
                        "latest_pct": round(100 * r["latest_prob"], 2), "episode": ep})
        prev_fired = fired
    return out


# ----------------------------------------------------------------------------- ALFRED value vectors (§6)

def alfred_vectors(releases: list[dict], cache_dir: str, lists_dir: str) -> dict[str, dict]:
    """For each release r (d_r, m_r): the first ALFRED RECPROUSM156N vintage dated >= d_r whose
    latest observation month is m_r. Uses the F6 cache via vintages.read_cached. Returns
    {release_date: {vintage_date, sha256, latest_month, vector{month: pct}, max_abs_diff_pct,
    n_common} | None}."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import vintages as V
    listed = V.load_vintage_list(lists_dir, ALFRED_SERIES)
    cache: dict[str, dict] = {}

    def rec(v):
        if v not in cache:
            p = V.cache_path(cache_dir, ALFRED_SERIES, v)
            cache[v] = V.read_cached(cache_dir, ALFRED_SERIES, v) if os.path.exists(p) else None
        return cache[v]

    out = {}
    for r in releases:
        chosen = None
        for v in listed:
            if v < r["release_date"]:
                continue
            x = rec(v)
            if x is None:
                continue                       # not cached (never substitutes another date)
            if x["last_obs_month"] == r["latest_month"]:
                chosen = x
                break
            if x["last_obs_month"] > r["latest_month"]:
                break                          # ALFRED already moved on: no vintage carries m_r
        if chosen is None:
            out[r["release_date"]] = None
            continue
        vec = {d[:7]: float(v) for d, v in chosen["obs"] if v is not None}
        pig = dict(zip(r["months"], r["probs"]))
        common = [m for m in vec if m in pig]
        diff = max((abs(vec[m] - 100 * pig[m]) for m in common), default=None)
        out[r["release_date"]] = {"vintage_date": chosen["vintage_date"], "sha256": chosen["sha256"],
                                  "latest_month": chosen["last_obs_month"], "vector": vec,
                                  "max_abs_diff_pct": diff, "n_common": len(common)}
    return out


# ----------------------------------------------------------------------------- assembly

def spec_vectors(releases: list[dict], alfred: dict[str, dict] | None) -> list[dict]:
    """§6 value vectors: the chosen ALFRED vintage's values (percent/100) where one exists,
    Piger's column otherwise; same release dates and latest months."""
    out = []
    for r in releases:
        a = (alfred or {}).get(r["release_date"])
        if a is None:
            out.append(dict(r, value_source="piger"))
            continue
        months = sorted(a["vector"])
        probs = [a["vector"][m] / 100.0 for m in months]
        out.append(dict(r, months=months, probs=probs, latest_month=months[-1],
                        latest_prob=probs[-1], value_source="alfred"))
    return out


def build_path(releases: list[dict], alfred: dict[str, dict] | None = None) -> tuple[list[dict], dict]:
    events, states = rule_3x80(releases)          # on Piger's own columns (complete history)
    sens = rule_1m50(releases)
    vecs = spec_vectors(releases, alfred)
    events_spec, states_spec = rule_3x80(vecs)    # on the §6 value vectors (ALFRED where chosen)
    sens_spec = rule_1m50(vecs)
    sens_dates = {s["release_date"] for s in sens}
    ev_by_date = {}
    for e in events:
        txt = (f"{e['kind']} peak={e['peak_month']}" if e["kind"] == "recession_start"
               else f"{e['kind']} trough={e['trough_month']}")
        ev_by_date.setdefault(e["release_date"], []).append(txt)
    rows = []
    for r, st in zip(releases, states):
        a = (alfred or {}).get(r["release_date"])
        since = [p for m, p in zip(r["months"], r["probs"]) if m >= SCAN_FROM]
        rows.append({"release_date": r["release_date"], "header_as_in_file": r["header_as_in_file"],
                     "header_corrected": int(r["header_corrected"]), "latest_month": r["latest_month"],
                     "piger_latest_pct": repr(round(100 * r["latest_prob"], 6)),
                     "n_months": len(r["months"]), "release_lag_days": release_lag_days(r),
                     "value_source": "alfred" if a else "piger",
                     "alfred_vintage_date": a["vintage_date"] if a else "",
                     "alfred_vintage_sha256": a["sha256"] if a else "",
                     "alfred_latest_month": a["latest_month"] if a else "",
                     "alfred_latest_pct": repr(a["vector"][a["latest_month"]]) if a else "",
                     "alfred_vs_piger_max_abs_diff_pct": repr(a["max_abs_diff_pct"]) if a and a["max_abs_diff_pct"] is not None else "",
                     "alfred_n_common": a["n_common"] if a else "",
                     "rule_3x80_state": st, "rule_3x80_event": " | ".join(ev_by_date.get(r["release_date"], [])),
                     "rule_1m50_fires": int(r["release_date"] in sens_dates),
                     "max_pct_in_release_since_scan_from": repr(round(100 * max(since), 4)) if since else ""})
    lags = sorted(release_lag_days(r) for r in releases)
    n = len(lags)
    median = lags[n // 2] if n % 2 else 0.5 * (lags[n // 2 - 1] + lags[n // 2])
    checks = known_event_checks(releases, events, sens)
    summary = {"n_releases": len(releases), "first_release": releases[0]["release_date"],
               "last_release": releases[-1]["release_date"],
               "last_latest_month": releases[-1]["latest_month"],
               "last_latest_pct": round(100 * releases[-1]["latest_prob"], 4),
               "header_corrections": [{"as_in_file": r["header_as_in_file"], "corrected": r["release_date"]}
                                      for r in releases if r["header_corrected"]],
               "release_lag_days": {"median": median, "min": lags[0], "max": lags[-1]},
               "rule_3x80": {"hi": HI, "lo": LO, "half": HALF, "strict_gt": True,
                             "scan_from": SCAN_FROM, "events": events,
                             "events_on_spec_vectors": events_spec,
                             "same_on_spec_vectors": events == events_spec and states == states_spec},
               "rule_1m50": {"threshold": SENS_TH, "firing_releases": sens,
                             "n_episodes": max((s["episode"] for s in sens), default=0),
                             "firing_releases_on_spec_vectors": sens_spec,
                             "same_on_spec_vectors": [(x["release_date"], x["latest_month"]) for x in sens]
                             == [(x["release_date"], x["latest_month"]) for x in sens_spec]},
               "alfred_anomalies_gt_1pp": [{"release_date": r["release_date"], "alfred_vintage_date": r["alfred_vintage_date"],
                                            "max_abs_diff_pct": r["alfred_vs_piger_max_abs_diff_pct"]}
                                           for r in rows if r["alfred_vs_piger_max_abs_diff_pct"]
                                           and float(r["alfred_vs_piger_max_abs_diff_pct"]) > 1.0],
               "alfred_coverage": ({"n_with_alfred": sum(1 for r in rows if r["value_source"] == "alfred"),
                                    "n_fallback": sum(1 for r in rows if r["value_source"] == "piger"),
                                    "first_alfred_release": next((r["release_date"] for r in rows if r["value_source"] == "alfred"), None),
                                    "max_abs_diff_pct_overall": max((float(r["alfred_vs_piger_max_abs_diff_pct"]) for r in rows if r["alfred_vs_piger_max_abs_diff_pct"]), default=None),
                                    "fallback_releases_after_first_alfred": [r["release_date"] for r in rows if r["value_source"] == "piger" and r["release_date"] >= "2012-09-04"]}
                                   if alfred is not None else None),
               "known_event_checks": checks,
               "all_known_events_pass": all(c["pass"] for c in checks.values())}
    return rows, summary


def known_event_checks(releases, events, sens) -> dict:
    starts = [e for e in events if e["kind"] == "recession_start"]
    s2008 = [e for e in starts if "2007-01" <= e["peak_month"] <= "2009-12"]
    s2020 = [e for e in starts if "2019-06" <= e["latest_month"] <= "2021-12"]
    r2021 = next((r for r in releases if r["release_date"] == "2021-10-29"), None)
    sens_2020 = [s for s in sens if "2020-01" <= s["latest_month"] <= "2020-12"]
    other = [e for e in starts if not ("2007-01" <= e["peak_month"] <= "2009-12")]
    return {
        "2008_declared_at_2009-01-01": {
            "expected": {"release_date": "2009-01-01", "n_declarations": 1},
            "computed": [{"release_date": e["release_date"], "trigger_months": e["trigger_months"],
                          "trigger_pct": e["trigger_pct"]} for e in s2008],
            "pass": len(s2008) == 1 and s2008[0]["release_date"] == "2009-01-01"},
        "2008_first_recession_month_2008-02_Hamilton": {
            "expected": {"first_recession_month": "2008-02",
                         "basis": "Hamilton (2011) w16162: 'would have announced on January 1, 2009 that a recession had started in February 2008'"},
            "computed": [{"first_recession_month": e["first_recession_month"], "chain_values_pct": e.get("chain_pct")} for e in s2008],
            "pass": len(s2008) == 1 and s2008[0]["first_recession_month"] == "2008-02"},
        "2008_peak_dated_2008-02_as_task_text": {
            "expected": {"peak_month": "2008-02", "basis": "SPEC v1 §1 row 7 / task text 'peak dated 2008-02'"},
            "computed": [{"peak_month": e["peak_month"], "first_half_month": e["first_half_month"],
                          "rule": "peak = month before the first >= 50% month of the chain preceding the trigger (§6)"}
                         for e in s2008],
            "pass": len(s2008) == 1 and s2008[0]["peak_month"] == "2008-02",
            "note": "reported as computed; a miss here means the spec text names the first recession month, "
                    "not the peak, under its own rule"},
        "2020_never_declared_by_3x80": {"expected": [], "computed": [e["release_date"] for e in s2020],
                                        "pass": not s2020},
        "no_other_3x80_declarations_2006-08..2026-09": {"expected": [], "computed": [e["release_date"] for e in other],
                                                       "pass": not other},
        "2021-10-29_release_Sep-2021_44.4pct_no_fire": {
            "expected": {"latest_month": "2021-09", "pct": 44.4, "fires_1m50": False},
            "computed": ({"latest_month": r2021["latest_month"], "pct": round(100 * r2021["latest_prob"], 2),
                          "fires_1m50": r2021["latest_prob"] >= SENS_TH} if r2021 else None),
            "pass": bool(r2021 and r2021["latest_month"] == "2021-09" and abs(100 * r2021["latest_prob"] - 44.4) < 0.05
                         and r2021["latest_prob"] < SENS_TH)},
        "1m50_sensitivity_catches_Mar-2020_at_2020-04-30": {
            "expected": {"release_date": "2020-04-30", "latest_month": "2020-03"},
            "computed": sens_2020[:1],
            "pass": bool(sens_2020 and sens_2020[0]["release_date"] == "2020-04-30" and sens_2020[0]["latest_month"] == "2020-03")},
    }


def write_outputs(rows, summary, out_dir: str, xlsx_path: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "realtime_path.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PATH_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    summary = dict(summary)
    summary.update({"source_url": HIST_URL, "source_file": os.path.basename(xlsx_path),
                    "source_sha256": hashlib.sha256(open(xlsx_path, "rb").read()).hexdigest(),
                    "source_bytes": os.path.getsize(xlsx_path), "units": "Piger file DECIMAL; x100 = percent (FRED/ALFRED units); all *_pct columns are percent",
                    "realtime_path_sha256": h,
                    "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    with open(os.path.join(out_dir, "realtime_events.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
        f.write("\n")
    return summary


def main(argv=None) -> int:
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--xlsx", default=os.path.join(here, "data", "piger", "History_of_Real_Time_Recession_Probabilities.xlsx"))
    p.add_argument("--out", default=os.path.join(here, "data", "piger"))
    p.add_argument("--cache", default=None, help="F6 vintage cache (for the ALFRED value-vector rule)")
    p.add_argument("--lists", default=os.path.join(here, "data", "vintage_lists"))
    a = p.parse_args(argv)
    releases = load_history(a.xlsx)
    alfred = alfred_vectors(releases, a.cache, a.lists) if a.cache else None
    rows, summary = build_path(releases, alfred)
    summary = write_outputs(rows, summary, a.out, a.xlsx)
    print(json.dumps({k: v for k, v in summary.items() if k != "rule_1m50"}, indent=1, sort_keys=True))
    print("1m50 firing releases:", [(s["release_date"], s["latest_month"], s["latest_pct"]) for s in summary["rule_1m50"]["firing_releases"]])
    return 0 if summary["all_known_events_pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
