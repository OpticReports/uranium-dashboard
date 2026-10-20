"""NBER turning points and announcement dates for the cycle-nowcast v2 study (SPEC v1 §6).

Reads ``data/nber/nber_turning_points_announcements.csv`` (research pass, 2026-10-20: peaks and
troughs since 1980 from the BCDC spreadsheet, announcement dates from the committee's
announcements page; nothing earlier is announced on that page) and the USREC CSV of the
2026-10-20 FRED pull for the full monthly recession indicator (USREC = 1 from the month after
the peak through the trough month, verified on all six cycles since 1980 by R2/verify_R2).

Provides: turning points, announcement dates and lags, recession spans, the recession ONSET
months the August study scores (the first USREC = 1 month of each spell, 1960+), and a monthly
label function. Writes ``data/nber/nber_events.json``. Standard library only.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import sys

ANNOUNCE_FIELDS = ["turning_point", "type", "month", "announcement_date", "announcement_lag_months"]


class NberError(Exception):
    pass


def load_turning_points(path: str) -> list[dict]:
    out = []
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        missing = [c for c in ANNOUNCE_FIELDS if c not in (rd.fieldnames or [])]
        if missing:
            raise NberError(f"{os.path.basename(path)} lacks columns {missing}")
        for r in rd:
            if r["type"] not in ("peak", "trough"):
                raise NberError(f"bad type {r}")
            if r["month"] != r["turning_point"]:
                raise NberError(f"turning_point/month mismatch {r}")
            if not r["announcement_date"] or dt.date.fromisoformat(r["announcement_date"]) <= \
                    dt.date(int(r["month"][:4]), int(r["month"][5:7]), 1):
                raise NberError(f"announcement not after the turning point {r}")
            out.append({"month": r["month"], "type": r["type"],
                        "announcement_date": r["announcement_date"],
                        "announcement_lag_months": int(r["announcement_lag_months"]),
                        "announcement_url": r.get("announcement_url", "")})
    out.sort(key=lambda r: r["month"])
    kinds = [r["type"] for r in out]
    if any(a == b for a, b in zip(kinds, kinds[1:])):
        raise NberError("peaks and troughs do not alternate")
    for r in out:
        lag = (int(r["announcement_date"][:4]) - int(r["month"][:4])) * 12 + \
              int(r["announcement_date"][5:7]) - int(r["month"][5:7])
        if lag != r["announcement_lag_months"]:
            raise NberError(f"announcement lag {lag} != recorded {r['announcement_lag_months']} for {r['month']}")
    return out


def load_usrec(path: str) -> dict[str, int]:
    out = {}
    with open(path, newline="") as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            if len(row) >= 2 and row[1] not in ("", "."):
                out[row[0][:7]] = int(float(row[1]))
    return out


def recession_spans(usrec: dict[str, int], start: str = "1960-01") -> list[dict]:
    """Spells of USREC = 1: onset = first 1 month, end = last 1 month (= NBER trough month),
    peak = month before onset."""
    months = sorted(m for m in usrec if m >= start)
    spans, on = [], None
    prev = None
    for m in months:
        v = usrec[m]
        if v == 1 and on is None:
            on = m
        if v == 0 and on is not None:
            spans.append({"onset": on, "end": prev, "peak": _add(on, -1)})
            on = None
        prev = m
    if on is not None:
        spans.append({"onset": on, "end": prev, "peak": _add(on, -1), "open": True})
    return spans


def _add(m: str, k: int) -> str:
    t = int(m[:4]) * 12 + int(m[5:7]) - 1 + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def cross_check(tps: list[dict], spans: list[dict]) -> list[dict]:
    """USREC convention vs the announced turning points: first 1 = peak + 1; last 1 = trough."""
    out = []
    peaks = {r["month"]: r for r in tps if r["type"] == "peak"}
    troughs = {r["month"]: r for r in tps if r["type"] == "trough"}
    for s in spans:
        if s["peak"] in peaks or s["end"] in troughs:
            out.append({"onset": s["onset"], "peak_from_usrec": s["peak"], "peak_announced": s["peak"] in peaks,
                        "trough_from_usrec": s["end"], "trough_announced": s["end"] in troughs,
                        "peak_announcement_date": peaks.get(s["peak"], {}).get("announcement_date"),
                        "trough_announcement_date": troughs.get(s["end"], {}).get("announcement_date")})
    return out


def label(usrec: dict[str, int], month: str) -> int | None:
    return usrec.get(month)


def build(nber_csv: str, usrec_csv: str) -> dict:
    tps = load_turning_points(nber_csv)
    usrec = load_usrec(usrec_csv)
    spans = recession_spans(usrec)
    xc = cross_check(tps, spans)
    bad = [c for c in xc if not (c["peak_announced"] and c["trough_announced"]) and c["onset"] >= "1980-01"
           and not any(s.get("open") for s in spans if s["onset"] == c["onset"])]
    return {"turning_points": tps,
            "recession_spans_usrec_1960plus": spans,
            "onsets_1960plus": [s["onset"] for s in spans],
            "onsets_scored_in_august_study": [s["onset"] for s in spans if s["onset"] >= "1972-01"],
            "usrec_vs_announced_cross_check": xc,
            "cross_check_pass": not bad,
            "sources": {"turning_points_file": os.path.basename(nber_csv),
                        "turning_points_sha256": hashlib.sha256(open(nber_csv, "rb").read()).hexdigest(),
                        "usrec_file": os.path.basename(usrec_csv),
                        "usrec_sha256": hashlib.sha256(open(usrec_csv, "rb").read()).hexdigest(),
                        "usrec_last_month": max(usrec), "usrec_last_value": usrec[max(usrec)]},
            "note": "announcement dates exist only from the 1980-01 peak; earlier onsets carry none",
            "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def main(argv=None) -> int:
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--nber", default=os.path.join(here, "data", "nber", "nber_turning_points_announcements.csv"))
    p.add_argument("--usrec", default=os.path.join(here, "data", "fred_2026-10-20", "USREC.csv"))
    p.add_argument("--out", default=os.path.join(here, "data", "nber", "nber_events.json"))
    a = p.parse_args(argv)
    res = build(a.nber, a.usrec)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps({k: v for k, v in res.items() if k != "turning_points"}, indent=1, sort_keys=True))
    return 0 if res["cross_check_pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
