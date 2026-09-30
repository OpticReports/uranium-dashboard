#!/usr/bin/env python3
"""Scores SPEC v1 of studies/labor-stress-board.md once. The rules come from
the dashboard's own module (backend/app/metrics/labor_stress.py), so the
backtest scores exactly what ships.

    python3 study.py        -> prints the report, writes results.json
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
from app.metrics import labor_stress as L  # noqa: E402

DATA = os.path.join(HERE, "data")
PEAKS = [((1973, 11), (1975, 3)), ((1980, 1), (1980, 7)), ((1981, 7), (1982, 11)),
         ((1990, 7), (1991, 3)), ((2001, 3), (2001, 11)), ((2007, 12), (2009, 6)),
         ((2020, 2), (2020, 4))]
SCORE = ((1972, 1), (2020, 12))
FINAL = ((2021, 1), (2024, 9))
PROVISIONAL = ((2024, 10), (2025, 8))
PENDING_FROM = (2025, 9)
QUIET = 6
COVERAGE_AFFECTED = [(1973, 11), (1980, 1)]      # A3 (v1 A4)
GRID = {"A2": (0.27, 0.30, 0.35), "A3": (10.0, 15.0, 20.0),
        "B1": (0.40, 0.50, 0.60), "B2": (0.40, 0.50, 0.60)}

SERIES = {"iursa": "IURSA", "ccnsa": "CCNSA", "covemp": "COVEMP",
          "job_losers": "LNS13023621", "clf": "CLF16OV", "epop_prime": "LNS12300060",
          "lfpr_prime": "LNS11300060", "pop_prime": "LNU00000060",
          "unemploy": "UNEMPLOY", "unrate": "UNRATE", "sahm": "SAHMREALTIME"}


def load(sid):
    d, v = [], []
    for r in csv.reader(open(os.path.join(DATA, f"{sid}.csv"))):
        if r[0][:1].isdigit():
            d.append(dt.date.fromisoformat(r[0]))
            v.append(float(r[1]) if r[1] not in (".", "") else None)
    return d, v


def s(k):
    return f"{k[0]}-{k[1]:02d}"


# ------------------------------------------------------------ scoring (A3)
def onsets(flags: dict) -> list:
    """First lit month preceded by >= QUIET OBSERVED unlit months; a spell lit
    at the first computable month is left-censored (never an onset)."""
    out, unlit = [], 0
    for k in sorted(flags):
        if flags[k]:
            if unlit >= QUIET:
                out.append(k)
            unlit = 0
        else:
            unlit += 1
    return out


def classify(o) -> tuple[str, str | None]:
    for p, _ in PEAKS:
        if -6 <= L.ym_diff(o, p) <= 3:
            return "HIT", s(p)
    for p, t in PEAKS:
        if 4 <= L.ym_diff(o, p) and o <= t:
            return "LATE", s(p)
    for p, _ in PEAKS:
        if -12 <= L.ym_diff(o, p) <= -7:
            return "EARLY", s(p)
    return "FALSE", None


def score(flags: dict) -> dict:
    ons = [o for o in onsets(flags)]
    in_score = [o for o in ons if SCORE[0] <= o <= SCORE[1]]
    cls = {o: classify(o) for o in in_score}
    per_peak = []
    for p, t in PEAKS:
        hits = [o for o in in_score if cls[o] == ("HIT", s(p))]
        if hits:
            per_peak.append({"peak": s(p), "outcome": "HIT", "onset": s(hits[0]),
                             "timing": L.ym_diff(hits[0], p)})
            continue
        # lit-through: the rule is lit at p-6 in a spell begun before it
        k6 = L.ym_add(p, -6)
        if flags.get(k6):
            per_peak.append({"peak": s(p), "outcome": "LIT-THROUGH"})
            continue
        late = [o for o in in_score if cls[o] == ("LATE", s(p))]
        early = [o for o in in_score if cls[o] == ("EARLY", s(p))]
        per_peak.append({"peak": s(p), "outcome": "LATE" if late else
                         ("EARLY" if early else "MISS"),
                         "onset": s((late or early)[0]) if (late or early) else None})
    fa = [o for o in in_score if cls[o][0] == "FALSE"]
    tier = lambda a, b: [s(o) for o in ons if a <= o <= b]  # noqa: E731
    lit_months = [k for k in flags if SCORE[0] <= k <= SCORE[1]]
    return {"hits": sum(1 for x in per_peak if x["outcome"] == "HIT"),
            "hits_ex2020": sum(1 for x in per_peak
                               if x["outcome"] == "HIT" and x["peak"] != "2020-02"),
            "per_peak": per_peak,
            "false_alarms": [s(o) for o in fa],
            "onsets_classified": {s(o): cls[o][0] for o in in_score},
            "final_2021_2024": tier(*FINAL),
            "provisional_2024_2025": tier(*PROVISIONAL),
            "pending": [s(o) for o in ons if o >= PENDING_FROM],
            "duty_cycle": (round(sum(flags[k] for k in lit_months) / len(lit_months), 3)
                           if lit_months else None)}


def timing_of(sc):
    return {x["peak"]: x["timing"] for x in sc["per_peak"] if x["outcome"] == "HIT"}


def paired_timing(sc, base):
    a, b = timing_of(sc), timing_of(base)
    d = sorted(a[p] - b[p] for p in a if p in b)
    if not d:
        return None
    return d[len(d) // 2] if len(d) % 2 else (d[len(d) // 2 - 1] + d[len(d) // 2]) / 2


def or_flags(lit, ids):
    ks = set().union(*[set(lit[i]) for i in ids])
    return {k: any(lit[i].get(k, False) for i in ids) for k in ks}


def composite(lit, a_ids=("A1", "A2", "A3"), bc_ids=("B1", "B2", "C1")):
    """Same-month AND, on months where the slack leg is observed (the monthly
    CPS grid — A6)."""
    a, bc = or_flags(lit, a_ids), or_flags(lit, bc_ids)
    return {k: bool(a.get(k)) and bc[k] for k in bc}


def criteria(comp, sahm, bc) -> dict:
    c = score(comp)
    sh = score(sahm)
    b = score(bc)
    hits_bc = {x["peak"] for x in b["per_peak"] if x["outcome"] == "HIT"}
    hits_c = {x["peak"] for x in c["per_peak"] if x["outcome"] == "HIT"}
    removed = [f for f in b["false_alarms"] if f not in c["false_alarms"]]
    pt = paired_timing(c, sh)
    return {
        "c1_hits>=6": c["hits"] >= 6,
        "c2_fa<=sahm": len(c["false_alarms"]) <= len(sh["false_alarms"]),
        "c3_zero_final": len(c["final_2021_2024"]) == 0,
        "c4_paired_timing<=+1": pt is not None and pt <= 1,
        "c6_no_hit_lost": hits_bc <= hits_c,
        "c6_removes_bc_fa": len(c["false_alarms"]) < len(b["false_alarms"]),
        "_paired_timing": pt, "_bc_fa_removed_or_moved": removed,
        "_comp": c, "_sahm": sh, "_bc": b,
    }


def passes(cr) -> bool:
    return all(v for k, v in cr.items() if not k.startswith("_"))


def size_test(lit, bc_ids=("B1", "B2", "C1")) -> dict:
    """Rotate the A-leg lit series over the scoring period; statistic = hits,
    then fewest false alarms."""
    a = or_flags(lit, ("A1", "A2", "A3"))
    bc = or_flags(lit, bc_ids)
    months = [k for k in sorted(bc) if SCORE[0] <= k <= SCORE[1]]
    n = len(months)
    a_vec = [bool(a.get(k)) for k in months]
    obs = score({k: a_vec[i] and bc[k] for i, k in enumerate(months)})
    better, total = 0, 0
    for sh in range(24, n - 24 + 1):
        rot = a_vec[-sh:] + a_vec[:-sh]
        sc = score({k: rot[i] and bc[k] for i, k in enumerate(months)})
        total += 1
        if sc["hits"] > obs["hits"] or (sc["hits"] == obs["hits"]
                                        and len(sc["false_alarms"]) <= len(obs["false_alarms"])):
            better += 1
    return {"n_rotations": total, "at_least_as_good": better,
            "p": round((1 + better) / (1 + total), 4),
            "observed": {"hits": obs["hits"], "fa": len(obs["false_alarms"])}}


def run(ser, **kw) -> dict:
    vals = L.rule_values(ser, **kw)
    return vals, L.lit(vals)


def main() -> dict:
    ser = {k: load(v) for k, v in SERIES.items()}
    vals, lit = run(ser, sahm_from="unrate")
    res = {"rules": {}, "today": {}}
    for rid in L.RULES:
        res["rules"][rid] = score(lit[rid]) | {"label": L.RULES[rid]["label"],
                                               "threshold": L.RULES[rid]["threshold"],
                                               "first_month": s(min(lit[rid]))}
        last = max(vals[rid])
        res["today"][rid] = {"month": s(last), "value": vals[rid][last], "lit": lit[rid][last]}
    bc = or_flags(lit, ("B1", "B2", "C1"))
    comp = composite(lit)
    cr = criteria(comp, lit["C1"], bc)
    res["composite"] = cr["_comp"]
    res["slack_leg_alone"] = cr["_bc"]
    res["sahm_current_vintage"] = cr["_sahm"]
    res["paired_timing_vs_sahm"] = cr["_paired_timing"]
    res["bc_false_alarms_removed_or_moved"] = cr["_bc_fa_removed_or_moved"]
    res["criteria"] = {k: v for k, v in cr.items() if not k.startswith("_")}
    res["size"] = size_test(lit)
    res["criteria"]["c5_size_p<=0.10"] = res["size"]["p"] <= 0.10

    # robustness grid (A8): criteria 1-4 + 6 at each of 81 points
    grid = []
    for a2, a3, b1, b2 in itertools.product(GRID["A2"], GRID["A3"], GRID["B1"], GRID["B2"]):
        lt = L.lit(vals, {"A2": a2, "A3": a3, "B1": b1, "B2": b2})
        g_cr = criteria(composite(lt), lt["C1"], or_flags(lt, ("B1", "B2", "C1")))
        grid.append({"A2": a2, "A3": a3, "B1": b1, "B2": b2, "pass": passes(g_cr)})
    share = sum(g["pass"] for g in grid) / len(grid)
    res["grid"] = {"share_pass": round(share, 3), "n": len(grid),
                   "passing": [g for g in grid if g["pass"]][:20]}
    res["criteria"]["c7_grid>=2/3"] = share >= 2 / 3

    # population-control sensitivity (A7)
    v2, l2 = run(ser, sahm_from="unrate", pop_control_adjust=True)
    cr2 = criteria(composite(l2), l2["C1"], or_flags(l2, ("B1", "B2", "C1")))
    res["popcontrol_sensitivity"] = {"passes": passes(cr2),
                                     "hits": cr2["_comp"]["hits"],
                                     "fa": cr2["_comp"]["false_alarms"]}
    res["criteria"]["c8_popcontrol_same"] = passes(cr2) == passes(cr)

    # other sensitivities (reported, cannot rescue a failed gate)
    sens = {}
    v3, l3 = run(ser, sahm_from="series")
    sens["sahm_realtime"] = criteria(composite(l3), l3["C1"],
                                     or_flags(l3, ("B1", "B2", "C1")))["_comp"]
    v4, l4 = run(ser, sahm_from="unrate", a3_normalize=True)
    sens["a3_covemp_normalized"] = criteria(composite(l4), l4["C1"],
                                            or_flags(l4, ("B1", "B2", "C1")))["_comp"]
    l5 = {k: dict(v) for k, v in lit.items()}
    for p, t in PEAKS:
        if p in COVERAGE_AFFECTED:
            k = L.ym_add(p, -12)
            while k <= t:
                if k in l5["A3"]:
                    l5["A3"][k] = False
                k = L.ym_add(k, 1)
    sens["a3_masked_1973_1980"] = score(composite(l5))
    a_lit = or_flags(lit, ("A1", "A2", "A3"))
    sens["window3"] = score({k: any(a_lit.get(L.ym_add(k, -i), False) for i in range(3))
                             and any(bc.get(L.ym_add(k, -i), False) for i in range(3))
                             for k in bc})
    res["sensitivities"] = {k: {"hits": v["hits"], "false_alarms": v["false_alarms"],
                                "final_2021_2024": v["final_2021_2024"]}
                            for k, v in sens.items()}
    res["criteria"]["ship_red_alert"] = all(v for k, v in res["criteria"].items()
                                            if k != "ship_red_alert")
    last = max(k for k in comp)
    res["today"]["board"] = {"month": s(last), "alert": comp[last],
                             "watch": any(lit[r].get(last, False) for r in L.RULES)}
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("criteria", "size", "paired_timing_vs_sahm")},
                     indent=1, default=str))
