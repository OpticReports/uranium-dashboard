"""ADS (Aruoba-Diebold-Scotti) comparator pipeline for the cycle-nowcast v2 study (SPEC v1 §5, F7).

Converts the Philadelphia Fed all-vintages workbook (one column per archived vintage,
``ADS_INDEX_MMDDYY``, daily rows ``YYYY:MM:DD`` from 1960-03-01) into the F7 derived panel:
per vintage the vintage date, the last date and last value, and for the last three calendar
months present in that vintage the monthly average, the number of days present and whether
the month is complete. The sha256 of the zip and of the xlsx are recorded with the panel.

Readings (§5): ADS_last(d) = the last daily value in the latest vintage dated <= d;
ADS_avg(M | d) = the mean of the daily values dated within target month M present in that
vintage. The vintage is the latest dated <= d, SAME-DAY vintages included (information parity
with the release that defines d); ``strict=True`` is the "< d" sensitivity.

Comparator reproduction gate (§5, DT-6): from the archive, the correlation of the real-time
last point (target 0.866) and of the previous-complete-month average (target 0.956) with the
2010-12-03 vintage, each within +/-0.01, over every vintage dated 2008-11..2010-10 (the spec's
wording). The Philadelphia Fed accuracy note (2011-01-19) that produced those two numbers
sampled the IP-release-day updates only (one per month, Dec-2008..Nov-2010 for the last
point; the previous month, Nov-2008..Oct-2010, for the average); that reading is computed
alongside and reported, never substituted. The "right line" figure (0.916) is quoted only.

No composite, nowcast or calibration is computed here. numpy + openpyxl (pinned production
dependencies) + standard library; no pandas.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import numpy as np

ADS_ZIP_URL = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/ads/ADS_All_Vintages-zip.zip"
ADS_ACCURACY_NOTE = ("Philadelphia Fed, 'Real-Time Accuracy of the ADS Index', January 19, 2011: "
                     "correlations 0.866 (last point) / 0.916 (right line) / 0.956 (average of the "
                     "previous month), IP-release-day updates, Nov-2008..Oct-2010, vs the 2010-12-03 update")
REF_VINTAGE = "2010-12-03"
GATE_WINDOW = ("2008-11-01", "2010-10-31")
GATE_TARGETS = {"last_point": 0.866, "prev_complete_month_avg": 0.956}
GATE_TOL = 0.01
RIGHT_LINE_QUOTED = 0.916
# ADS claims-only updates during the 2025 federal shutdown (tech doc, Oct-2025 revision: "special
# procedures" updating the index from initial claims alone, first such update 2025-10-16). The end
# of the claims-only window is NOT stated by the source; it is inferred from the component release
# calendar in the ALFRED vintage lists: the first post-shutdown PAYEMS vintage is 2025-11-20 and the
# last member to resume (CMRMTSPL) did so on 2025-12-23. Both bounds are recorded as flags.
CLAIMS_ONLY_START = "2025-10-16"
CLAIMS_ONLY_END_EXCL = "2025-11-20"     # first ADS update that could carry a monthly release
SHUTDOWN_PARTIAL_END_INCL = "2025-12-23"

_COL_RE = re.compile(r"^ADS_INDEX_(\d{2})(\d{2})(\d{2})$")
_DATE_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})$")

PANEL_FIELDS = ["vintage_date", "vintage_col", "col_index", "last_date", "last_value",
                "m0", "m0_avg", "m0_n", "m0_complete", "m1", "m1_avg", "m1_n", "m1_complete",
                "m2", "m2_avg", "m2_n", "m2_complete", "claims_only", "shutdown_partial"]


class AdsError(Exception):
    pass


# ----------------------------------------------------------------------------- helpers

def vintage_date_of(col: str) -> str:
    m = _COL_RE.match(col)
    if not m:
        raise AdsError(f"not a vintage column: {col!r}")
    mm, dd, yy = m.groups()
    return f"20{yy}-{mm}-{dd}"


def iso_of(ads_date: str) -> str:
    m = _DATE_RE.match(ads_date)
    if not m:
        raise AdsError(f"not an ADS date: {ads_date!r}")
    return "-".join(m.groups())


def days_in_month(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def prev_month(month: str, k: int = 1) -> str:
    t = int(month[:4]) * 12 + int(month[5:7]) - 1 - k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(x) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else repr(float(x))


# ----------------------------------------------------------------------------- conversion (F7)

def derive_panel(header: list, rows, ref_vintage: str = REF_VINTAGE):
    """Core of the conversion, independent of openpyxl: header = ['Date', 'ADS_INDEX_MMDDYY',
    ...]; rows = iterable of tuples (date 'YYYY:MM:DD', v1, v2, ...) with None for blanks.
    Returns (panel_rows, ref_daily, months, sums, counts, vintage_dates, n_rows)."""
    cols = list(header[1:])
    vdates = [vintage_date_of(c) for c in cols]
    n = len(cols)
    ref_j = vdates.index(ref_vintage) if ref_vintage in vdates else None
    months: list[str] = []
    midx: dict[str, int] = {}
    sums: list[np.ndarray] = []
    counts: list[np.ndarray] = []
    last_date = [None] * n
    last_value = np.full(n, np.nan)
    ref_daily: list[tuple[str, float]] = []
    n_rows = 0
    prev_date = None
    for r in rows:
        if r is None or r[0] is None:
            continue
        d = iso_of(str(r[0]))
        if prev_date is not None and d <= prev_date:
            raise AdsError(f"dates not increasing at {d}")
        prev_date = d
        n_rows += 1
        arr = np.array(r[1:1 + n], dtype=object)
        if len(arr) < n:
            arr = np.concatenate([arr, np.array([None] * (n - len(arr)), dtype=object)])
        mask = np.not_equal(arr, None)
        if not mask.any():
            continue
        vals = np.zeros(n)
        vals[mask] = arr[mask].astype(float)
        m = d[:7]
        if m not in midx:
            midx[m] = len(months)
            months.append(m)
            sums.append(np.zeros(n))
            counts.append(np.zeros(n, dtype=np.int32))
        k = midx[m]
        sums[k] += vals
        counts[k] += mask
        idx = np.flatnonzero(mask)
        for j in idx:
            last_date[j] = d
        last_value[idx] = vals[idx]
        if ref_j is not None and mask[ref_j]:
            ref_daily.append((d, float(vals[ref_j])))
    S = np.vstack(sums) if sums else np.zeros((0, n))
    C = np.vstack(counts) if counts else np.zeros((0, n), dtype=np.int32)
    panel = []
    for j in range(n):
        row = {"vintage_date": vdates[j], "vintage_col": cols[j], "col_index": j + 1,
               "last_date": last_date[j] or "", "last_value": _fmt(last_value[j]) if last_date[j] else ""}
        for k in range(3):
            key = f"m{k}"
            if last_date[j] is None:
                row.update({key: "", f"{key}_avg": "", f"{key}_n": "", f"{key}_complete": ""})
                continue
            mo = prev_month(last_date[j][:7], k)
            if mo in midx and C[midx[mo], j] > 0:
                nn = int(C[midx[mo], j])
                row.update({key: mo, f"{key}_avg": _fmt(S[midx[mo], j] / nn), f"{key}_n": nn,
                            f"{key}_complete": int(nn == days_in_month(mo))})
            else:
                row.update({key: mo, f"{key}_avg": "", f"{key}_n": 0, f"{key}_complete": 0})
        vd = vdates[j]
        row["claims_only"] = int(CLAIMS_ONLY_START <= vd < CLAIMS_ONLY_END_EXCL)
        row["shutdown_partial"] = int(CLAIMS_ONLY_END_EXCL <= vd <= SHUTDOWN_PARTIAL_END_INCL)
        panel.append(row)
    order = sorted(range(n), key=lambda j: (vdates[j], j))
    panel = [panel[j] for j in order]
    return panel, ref_daily, months, S, C, vdates, n_rows


def convert_workbook(xlsx_path: str, out_dir: str, zip_path: str | None = None,
                     matrix_path: str | None = None, log=print) -> dict:
    """Stream the workbook once (read-only openpyxl) and write the F7 files into out_dir:
    ads_vintage_panel.csv, ads_vintage_<REF>.csv (daily values of the reference vintage) and
    ads_hashes.json. matrix_path (optional, outside git) receives the monthly sum/count matrix."""
    import openpyxl
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = list(next(it))
    if header[0] != "Date":
        raise AdsError(f"unexpected header start {header[:2]}")
    panel, ref_daily, months, S, C, vdates, n_rows = derive_panel(header, it)
    wb.close()
    elapsed = time.time() - t0
    log(f"[ads] {n_rows} rows x {len(vdates)} vintages in {elapsed:.0f}s; "
        f"{vdates[0]}..{vdates[-1]}; months {months[0]}..{months[-1]}")
    panel_path = os.path.join(out_dir, "ads_vintage_panel.csv")
    with open(panel_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PANEL_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(panel)
    ref_path = os.path.join(out_dir, f"ads_vintage_{REF_VINTAGE}.csv")
    with open(ref_path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "value"])
        for d, v in ref_daily:
            w.writerow([d, repr(v)])
    rec = {"source_url": ADS_ZIP_URL, "xlsx": os.path.basename(xlsx_path),
           "xlsx_sha256": sha256_file(xlsx_path), "xlsx_bytes": os.path.getsize(xlsx_path),
           "zip": os.path.basename(zip_path) if zip_path else None,
           "zip_sha256": sha256_file(zip_path) if zip_path else None,
           "zip_bytes": os.path.getsize(zip_path) if zip_path else None,
           "n_rows": n_rows, "n_vintages": len(vdates), "first_vintage": min(vdates),
           "last_vintage": max(vdates), "first_month": months[0], "last_month": months[-1],
           "header_order_sorted": vdates == sorted(vdates),
           "ref_vintage": REF_VINTAGE, "ref_rows": len(ref_daily),
           "panel_file": os.path.basename(panel_path), "panel_sha256": sha256_file(panel_path),
           "ref_file": os.path.basename(ref_path), "ref_sha256": sha256_file(ref_path),
           "claims_only_window": [CLAIMS_ONLY_START, CLAIMS_ONLY_END_EXCL],
           "shutdown_partial_window": [CLAIMS_ONLY_END_EXCL, SHUTDOWN_PARTIAL_END_INCL],
           "n_claims_only": sum(r["claims_only"] for r in panel),
           "n_shutdown_partial": sum(r["shutdown_partial"] for r in panel),
           "conversion_seconds": round(elapsed, 1),
           "converted": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if matrix_path:
        os.makedirs(os.path.dirname(matrix_path), exist_ok=True)
        np.savez_compressed(matrix_path, months=np.array(months), vintage_dates=np.array(vdates),
                            sums=S, counts=C)
        rec["matrix_file"] = os.path.basename(matrix_path)   # kept in the session scratchpad, not in git
        rec["matrix_sha256"] = sha256_file(matrix_path)
    with open(os.path.join(out_dir, "ads_hashes.json"), "w") as f:
        json.dump(rec, f, indent=1, sort_keys=True)
        f.write("\n")
    return rec


# ----------------------------------------------------------------------------- panel access

def load_panel(path: str) -> list[dict]:
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            row = dict(r)
            row["last_value"] = float(r["last_value"]) if r["last_value"] else None
            for k in ("m0", "m1", "m2"):
                row[f"{k}_avg"] = float(r[f"{k}_avg"]) if r[f"{k}_avg"] else None
                row[f"{k}_n"] = int(r[f"{k}_n"]) if r[f"{k}_n"] else 0
                row[f"{k}_complete"] = bool(int(r[f"{k}_complete"])) if r[f"{k}_complete"] else False
            row["claims_only"] = bool(int(r["claims_only"]))
            row["shutdown_partial"] = bool(int(r["shutdown_partial"]))
            out.append(row)
    out.sort(key=lambda r: (r["vintage_date"], int(r["col_index"])))
    return out


def select_vintage(panel: list[dict], d: str, strict: bool = False) -> dict | None:
    """Latest vintage dated <= d (same-day included) or, strict=True, dated < d. When two
    vintages share a date the later column wins (the archive's order)."""
    best = None
    for r in panel:
        ok = r["vintage_date"] < d if strict else r["vintage_date"] <= d
        if ok and (best is None or (r["vintage_date"], int(r["col_index"])) >=
                   (best["vintage_date"], int(best["col_index"]))):
            best = r
    return best


def ads_last(panel: list[dict], d: str, strict: bool = False) -> dict | None:
    v = select_vintage(panel, d, strict)
    if v is None:
        return None
    return {"issue_date": d, "vintage_date": v["vintage_date"], "last_date": v["last_date"],
            "value": v["last_value"], "claims_only": v["claims_only"],
            "shutdown_partial": v["shutdown_partial"]}


def ads_avg(panel: list[dict], M: str, d: str, strict: bool = False) -> dict | None:
    """Mean of the daily values dated within month M present in the vintage selected at d.
    None when no vintage exists; a dict with value None and a reason when M is not among the
    three months the panel stores for that vintage (older months are not a §5 reading)."""
    v = select_vintage(panel, d, strict)
    if v is None:
        return None
    base = {"issue_date": d, "vintage_date": v["vintage_date"], "month": M,
            "claims_only": v["claims_only"], "shutdown_partial": v["shutdown_partial"]}
    for k in ("m0", "m1", "m2"):
        if v[k] == M:
            if v[f"{k}_n"] == 0:
                return {**base, "value": None, "n_days": 0, "complete": False,
                        "reason": "month after the vintage's last date"}
            return {**base, "value": v[f"{k}_avg"], "n_days": v[f"{k}_n"],
                    "complete": v[f"{k}_complete"]}
    if M > v["m0"]:
        return {**base, "value": None, "n_days": 0, "complete": False,
                "reason": f"month {M} not yet in vintage (last date {v['last_date']})"}
    return {**base, "value": None, "n_days": None, "complete": None,
            "reason": f"month {M} older than the stored window ({v['m2']}..{v['m0']})"}


def prev_complete_month(v: dict) -> tuple[str, float] | None:
    """The latest complete calendar month in the vintage and its average."""
    for k in ("m0", "m1", "m2"):
        if v[k] and v[f"{k}_complete"]:
            return v[k], v[f"{k}_avg"]
    return None


# ----------------------------------------------------------------------------- gate (§5)

def load_ref_daily(path: str) -> dict[str, float]:
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out[r["date"]] = float(r["value"])
    return out


def monthly_means(daily: dict[str, float]) -> dict[str, tuple[float, int]]:
    acc: dict[str, list[float]] = {}
    for d, v in daily.items():
        acc.setdefault(d[:7], []).append(v)
    return {m: (float(np.mean(vs)), len(vs)) for m, vs in acc.items()}


def _corr(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    a = np.array(pairs, dtype=float)
    return float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])


def ip_release_days(indpro_vt_rows: list[dict], months: list[str]) -> dict[str, dict]:
    """For each calendar month m: the earliest INDPRO vintage dated in m whose last observation
    month is m-1 (the G.17 day). indpro_vt_rows carry vintage_date and last_obs_month."""
    out = {}
    for m in months:
        cands = sorted(r["vintage_date"] for r in indpro_vt_rows
                       if r["vintage_date"][:7] == m and r["last_obs_month"] == prev_month(m))
        out[m] = {"g17_date": cands[0] if cands else None,
                  "indpro_vintages_in_month": sorted(r["vintage_date"] for r in indpro_vt_rows
                                                     if r["vintage_date"][:7] == m)}
    return out


def comparator_gate(panel: list[dict], ref_daily: dict[str, float],
                    indpro_vt_rows: list[dict] | None = None) -> dict:
    ref_m = monthly_means(ref_daily)
    lo, hi = GATE_WINDOW
    win = [r for r in panel if lo <= r["vintage_date"] <= hi and r["last_date"]]
    # (1) spec-literal: every vintage dated in the window
    lp, pm, lp_rows, pm_rows, lp_miss, pm_miss = [], [], [], [], [], []
    for r in win:
        if r["last_date"] in ref_daily:
            lp.append((r["last_value"], ref_daily[r["last_date"]]))
            lp_rows.append({"vintage_date": r["vintage_date"], "last_date": r["last_date"],
                            "rt": r["last_value"], "ref": ref_daily[r["last_date"]]})
        else:
            lp_miss.append(r["vintage_date"])
        pcm = prev_complete_month(r)
        if pcm and pcm[0] in ref_m:
            pm.append((pcm[1], ref_m[pcm[0]][0]))
            pm_rows.append({"vintage_date": r["vintage_date"], "month": pcm[0],
                            "rt": pcm[1], "ref": ref_m[pcm[0]][0]})
        else:
            pm_miss.append(r["vintage_date"])
    res = {"definition": "SPEC v1 §5 / DT-6: every archived vintage dated "
                         f"{lo}..{hi} vs the {REF_VINTAGE} vintage at the same date / same month",
           "reference_vintage": REF_VINTAGE, "window": list(GATE_WINDOW),
           "n_vintages_in_window": len(win),
           "first_vintage_in_window": win[0]["vintage_date"] if win else None,
           "last_vintage_in_window": win[-1]["vintage_date"] if win else None,
           "last_point": {"n": len(lp), "corr": _corr(lp), "target": GATE_TARGETS["last_point"],
                          "tol": GATE_TOL, "missing_ref_dates": lp_miss},
           "prev_complete_month_avg": {"n": len(pm), "corr": _corr(pm),
                                       "target": GATE_TARGETS["prev_complete_month_avg"],
                                       "tol": GATE_TOL, "missing": pm_miss},
           "rows_last_point": lp_rows, "rows_prev_month": pm_rows}
    for key in ("last_point", "prev_complete_month_avg"):
        c = res[key]["corr"]
        res[key]["pass"] = bool(c is not None and abs(c - res[key]["target"]) <= GATE_TOL)
        res[key]["delta"] = None if c is None else round(c - res[key]["target"], 4)
    res["pass"] = bool(res["last_point"]["pass"] and res["prev_complete_month_avg"]["pass"])
    # (2) note-literal: IP-release-day updates, one per month
    note = {"definition": ADS_ACCURACY_NOTE + "; here: first ADS vintage dated >= the G.17 day "
                          "of each month (G.17 day = earliest INDPRO vintage in that month whose "
                          "last observation month is the previous month)"}
    if indpro_vt_rows:
        months = []
        m = "2008-12"
        while m <= "2010-11":
            months.append(m)
            m = prev_month(m, -1)
        ipd = ip_release_days(indpro_vt_rows, months)
        nlp, npm, rows = [], [], []
        for m in months:
            g = ipd[m]["g17_date"]
            if g is None:
                rows.append({"month": m, "g17_date": None, "ads_vintage": None})
                continue
            cand = [r for r in panel if r["vintage_date"] >= g and r["vintage_date"][:7] == m
                    and r["last_date"]]
            if not cand:
                rows.append({"month": m, "g17_date": g, "ads_vintage": None})
                continue
            v = cand[0]
            row = {"month": m, "g17_date": g, "ads_vintage": v["vintage_date"],
                   "last_date": v["last_date"], "rt_last": v["last_value"],
                   "ref_last": ref_daily.get(v["last_date"])}
            if row["ref_last"] is not None:
                nlp.append((row["rt_last"], row["ref_last"]))
            pmo = prev_month(m)
            for k in ("m0", "m1", "m2"):
                if v[k] == pmo and v[f"{k}_n"]:
                    row.update({"avg_month": pmo, "rt_avg": v[f"{k}_avg"],
                                "avg_complete": v[f"{k}_complete"],
                                "ref_avg": ref_m.get(pmo, (None, 0))[0]})
                    if row["ref_avg"] is not None:
                        npm.append((row["rt_avg"], row["ref_avg"]))
            rows.append(row)
        note.update({"ip_days": ipd, "rows": rows,
                     "last_point": {"n": len(nlp), "corr": _corr(nlp), "target": GATE_TARGETS["last_point"]},
                     "prev_month_avg": {"n": len(npm), "corr": _corr(npm),
                                        "target": GATE_TARGETS["prev_complete_month_avg"]}})
        for key in ("last_point", "prev_month_avg"):
            c = note[key]["corr"]
            note[key]["within_tol"] = bool(c is not None and abs(c - note[key]["target"]) <= GATE_TOL)
    else:
        note["skipped"] = "INDPRO 2008-12..2010-11 vintages not available"
    res["note_literal"] = note
    res["right_line_quoted_not_gated"] = RIGHT_LINE_QUOTED
    res["computed"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return res


# ----------------------------------------------------------------------------- CLI

def _here():
    return os.path.dirname(os.path.abspath(__file__))


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--xlsx", required=True)
    c.add_argument("--zip", default=None)
    c.add_argument("--out", default=os.path.join(_here(), "data", "ads_panel"))
    c.add_argument("--matrix", default=None, help="npz path for the monthly sum/count matrix (outside git)")
    g = sub.add_parser("gate")
    g.add_argument("--panel-dir", default=os.path.join(_here(), "data", "ads_panel"))
    g.add_argument("--indpro-cache", default=None, help="vintage cache dir holding INDPRO/ (for the note-literal check)")
    a = p.parse_args(argv)
    if a.cmd == "convert":
        rec = convert_workbook(a.xlsx, a.out, a.zip, a.matrix)
        print(json.dumps(rec, indent=1, sort_keys=True))
        return 0
    if a.cmd == "gate":
        panel = load_panel(os.path.join(a.panel_dir, "ads_vintage_panel.csv"))
        ref = load_ref_daily(os.path.join(a.panel_dir, f"ads_vintage_{REF_VINTAGE}.csv"))
        ind = None
        if a.indpro_cache:
            sys.path.insert(0, _here())
            import vintages as V
            d = os.path.join(a.indpro_cache, "INDPRO")
            ind = []
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".csv") and "2008-11-01" <= fn[7:17] <= "2010-11-30":
                    r = V.read_cached(a.indpro_cache, "INDPRO", fn[7:17])
                    ind.append({"vintage_date": r["vintage_date"], "last_obs_month": r["last_obs_month"],
                                "sha256": r["sha256"]})
        res = comparator_gate(panel, ref, ind)
        with open(os.path.join(a.panel_dir, "gate_ads.json"), "w") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
        short = {k: v for k, v in res.items() if k not in ("rows_last_point", "rows_prev_month", "note_literal")}
        short["note_literal"] = {k: v for k, v in res["note_literal"].items() if k not in ("rows", "ip_days")}
        print(json.dumps(short, indent=1, sort_keys=True))
        return 0 if res["pass"] else 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
