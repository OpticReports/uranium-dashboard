#!/usr/bin/env python3
"""Scores studies/labor-stress-board.md once. The RULES come from the
dashboard's own module (backend/app/metrics/labor_stress.py) so the backtest
scores exactly what ships.

    python3 study.py        -> prints the report, writes results.json
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from app.metrics import labor_stress as L  # noqa: E402

DATA = os.path.join(HERE, "data")
PEAKS = [(1973, 11), (1980, 1), (1981, 7), (1990, 7), (2001, 3), (2007, 12), (2020, 2)]
SCORE = ((1972, 1), (2020, 12))
HOLDOUT = ((2021, 1), (2026, 8))
HIT_WIN = (-6, 3)          # onset in [peak-6, peak+3]
FA_WIN = (-3, 12)          # an onset is justified if a peak is in [onset-3, onset+12]
QUIET = 6                  # an onset = first lit month after >= 6 unlit months
WINDOW = 1                 # composite co-occurrence window (months)

SERIES = {"iursa": "IURSA", "ccnsa": "CCNSA", "job_losers": "LNS13023621",
          "clf": "CLF16OV", "epop_prime": "LNS12300060", "lfpr_prime": "LNS11300060",
          "pop16": "LNU00000060", "unemploy": "UNEMPLOY", "sahm": "SAHMREALTIME"}


def load(sid: str):
    d, v = [], []
    for r in csv.reader(open(os.path.join(DATA, f"{sid}.csv"))):
        if r[0][:1].isdigit():
            d.append(dt.date.fromisoformat(r[0]))
            v.append(float(r[1]) if r[1] not in (".", "") else None)
    return d, v


def in_range(k, rng):
    return rng[0] <= k <= rng[1]


def onsets(flags: dict, rng) -> list:
    """First lit month after >= QUIET unlit months, inside rng. A month with
    no value counts as unlit (the rule could not fire)."""
    ks = sorted(flags)
    out, last_lit = [], None
    for k in ks:
        if not flags[k]:
            continue
        if last_lit is None or L.ym_diff(k, last_lit) > QUIET:
            if in_range(k, rng):
                out.append(k)
        last_lit = k
    return out


def score(flags: dict, available_from) -> dict:
    ons = onsets(flags, SCORE)
    hits, timing = [], []
    for p in PEAKS:
        if L.ym_diff(p, available_from) < -HIT_WIN[0]:
            hits.append({"peak": f"{p[0]}-{p[1]:02d}", "hit": None,
                         "note": "rule not available 6 months before this peak"})
            continue
        cand = [o for o in ons if HIT_WIN[0] <= L.ym_diff(o, p) <= HIT_WIN[1]]
        if cand:
            t = L.ym_diff(cand[0], p)
            hits.append({"peak": f"{p[0]}-{p[1]:02d}", "hit": True, "onset":
                         f"{cand[0][0]}-{cand[0][1]:02d}", "timing": t})
            timing.append(t)
        else:
            hits.append({"peak": f"{p[0]}-{p[1]:02d}", "hit": False})
    fa = [o for o in ons if not any(FA_WIN[0] <= L.ym_diff(p, o) <= FA_WIN[1]
                                    for p in PEAKS)]
    hold = onsets(flags, HOLDOUT)
    n_av = sum(1 for h in hits if h["hit"] is not None)
    timing_sorted = sorted(timing)
    med = (timing_sorted[len(timing) // 2] if len(timing) % 2 else
           (timing_sorted[len(timing) // 2 - 1] + timing_sorted[len(timing) // 2]) / 2
           ) if timing else None
    return {"available_from": f"{available_from[0]}-{available_from[1]:02d}",
            "hits": sum(1 for h in hits if h["hit"]), "peaks_available": n_av,
            "per_peak": hits, "median_timing": med,
            "timing_range": [min(timing), max(timing)] if timing else None,
            "false_alarms": [f"{k[0]}-{k[1]:02d}" for k in fa],
            "holdout_onsets": [f"{k[0]}-{k[1]:02d}" for k in hold]}


def main() -> dict:
    ser = {k: load(v) for k, v in SERIES.items()}
    vals = L.rule_values(ser)
    lit = L.lit(vals)
    res = {"rules": {}, "today": {}}
    for rid in L.RULES:
        f = lit[rid]
        res["rules"][rid] = score(f, min(f)) | {"label": L.RULES[rid]["label"],
                                                 "threshold": L.RULES[rid]["threshold"]}
        last = max(vals[rid])
        res["today"][rid] = {"month": f"{last[0]}-{last[1]:02d}", "value": vals[rid][last],
                             "lit": lit[rid][last]}
    b = L.board(lit, WINDOW)
    comp = {k: v == "ALERT" for k, v in b.items()}
    start = max(min(lit[r]) for r in ("A1", "A2", "A3"))    # the A-leg's full coverage
    res["composite"] = score({k: v for k, v in comp.items() if k >= min(lit["A1"])},
                             min(lit["A1"])) | {"window": WINDOW, "a_leg_full_from": str(start)}
    last = max(b)
    res["today"]["board"] = {"month": f"{last[0]}-{last[1]:02d}", "state": b[last]}
    s, c = res["rules"]["C1"], res["composite"]
    res["decision"] = {
        "hits>=6of7": c["hits"] >= 6,
        "fa<=sahm": len(c["false_alarms"]) <= len(s["false_alarms"]),
        "zero_holdout": len(c["holdout_onsets"]) == 0,
        "timing<=sahm+1": (c["median_timing"] is not None and s["median_timing"] is not None
                           and c["median_timing"] <= s["median_timing"] + 1),
    }
    res["decision"]["ship_red_alert"] = all(res["decision"].values())
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1)[:5000])
