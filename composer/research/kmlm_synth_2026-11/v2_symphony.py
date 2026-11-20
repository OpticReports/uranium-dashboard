"""Bars F4 and F5 (PREREG.md; DEVIATIONS.md 8): the whole KMLM symphony, and the 74 variants of addendum 57,
run with the synthetic in place of the fund on the overlap. Also the erratum check for addendum 57: its
cells re-run on the fund's corrected total return (Yahoo's adjusted close understates one distribution).
Writes out/symphony.json; the cell paths go to the scratch cache."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
K57 = os.path.join(HERE, "..", "kmlm_2026-11")
sys.path.insert(0, HERE)
sys.path.insert(0, K57)
import data as kdata  # noqa: E402
import ksim as ks  # noqa: E402
import ksynth as ky  # noqa: E402
import q1_cells as q1  # noqa: E402
import sdata  # noqa: E402

V1, MID = "2024-03-28", "2022-08-01"


def lg(r):
    return sum(math.log1p(x) for x in r)


def spearman(a, b):
    def rank(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for k, i in enumerate(o):
            r[i] = k
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma = (n - 1) / 2
    return sum((x - ma) * (y - ma) for x, y in zip(ra, rb)) / sum((x - ma) ** 2 for x in ra)


def cut(run, lo, hi):
    idx = [i for i, d in enumerate(run["days"]) if lo <= d <= hi]
    return {c: [v["ret"][i] for i in idx] for c, v in run["cells"].items()}


def main():
    exposure = json.load(open(os.path.join(HERE, "out", "fidelity.json")))["exposure"]
    fund = sdata.fund_tr(q1.END)
    yahoo = kdata.series("KMLM", q1.END)
    out = {}
    # ---- erratum: where does the switch differ between Yahoo's adjusted close and the corrected series?
    xlk = kdata.series("XLK", q1.END)
    ra = ks.rsi_series(xlk, 10)
    fy, fc = ks.rsi_series(yahoo, 10), ks.rsi_series(fund, 10)
    out["flag_differs"] = [d for d in sorted(fund) if fy.get(d) is not None and fc.get(d) is not None and (ra[d] > fy[d]) != (ra[d] > fc[d])]
    P = kdata.panel_ab(q1.END)
    Pc = dict(P, KMLM=fund)
    real = q1.run(Pc, q1.B_START, q1.END)
    json.dump(real, open(sdata.CACHE + "/cells_real_tr.json", "w"))
    old = json.load(open(os.path.join(K57, "out", "cells_ab.json")))
    ids = [c for c in real["cells"] if c != "base"]
    d_new = [lg(real["cells"][c]["ret"]) - lg(real["cells"]["base"]["ret"]) for c in ids]
    d_old = [lg(old["cells"][c]["ret"]) - lg(old["cells"]["base"]["ret"]) for c in ids]
    yrs = len(real["days"]) / 252
    out["erratum"] = {"base_log_growth": {"yahoo": lg(old["cells"]["base"]["ret"]), "corrected": lg(real["cells"]["base"]["ret"])},
                      "spearman_of_differences": spearman(d_new, d_old),
                      "max_abs_change_log_per_yr": max(abs(a - b) for a, b in zip(d_new, d_old)) / yrs,
                      "ahead_of_live": {"yahoo": sorted(c for c, v in zip(ids, d_old) if v > 1e-9), "corrected": sorted(c for c, v in zip(ids, d_new) if v > 1e-9)},
                      "best": {"yahoo": max(zip(d_old, ids)), "corrected": max(zip(d_new, ids))},
                      "sign_changes": sorted(c for c, a, b in zip(ids, d_new, d_old) if (a > 1e-9) != (b > 1e-9))}
    # ---- the synthetic in the fund's place, to the end of the futures data
    synth = ky.level(ky.build(exposure, start="2015-01-01"))
    first = min(fund)
    Ps = {t: {d: v for d, v in s.items() if d <= V1} for t, s in P.items()}
    Ps["KMLM"] = {d: v for d, v in synth.items() if first <= d <= V1}
    syn = q1.run(Ps, q1.B_START, V1)
    json.dump(syn, open(sdata.CACHE + "/cells_synth_overlap.json", "w"))
    tree = ks.approved()
    hr = ks.simulate(tree, {t: {d: v for d, v in s.items() if d <= V1} for t, s in Pc.items()}, q1.B_START, V1)
    hs = ks.simulate(tree, Ps, q1.B_START, V1)
    out["bars"] = {}
    for name, lo in (("whole", q1.B_START), ("second part", MID)):
        days = [d for d in hr["target"] if d >= lo]
        same = sum(set(hr["target"][d]) == set(hs["target"][d]) for d in days)
        close = sum(max(abs(hr["held"][d].get(k, 0) - hs["held"][d].get(k, 0)) for k in set(hr["held"][d]) | set(hs["held"][d])) <= 0.10 for d in days)
        cr, cs = cut(real, lo, V1), cut(syn, lo, V1)
        gr, gs_ = lg(cr["base"]), lg(cs["base"])
        dr = [lg(cr[c]) - gr for c in ids]
        ds = [lg(cs[c]) - gs_ for c in ids]
        distinct = [i for i, c in enumerate(ids) if c != "F2.vote8-10-12"]
        out["bars"][name] = {
            "sessions": len(days), "same_target": same / len(days), "held_within_corridor": close / len(days),
            "log_growth": {"real": gr, "synthetic": gs_, "ratio": gs_ / gr},
            "daily_corr_of_symphony_returns": ks.corr(cr["base"], cs["base"]),
            "spearman_74": spearman(dr, ds),
            "top10_overlap": len(set(sorted(ids, key=lambda c: -dr[ids.index(c)])[:10]) & set(sorted(ids, key=lambda c: -ds[ids.index(c)])[:10])),
            "same_sign_vs_live": sum((dr[i] > 0) == (ds[i] > 0) for i in distinct) / len(distinct),
            "F4_same_holdings>=0.95": same / len(days) >= 0.95, "F4_growth_within_10pct": abs(gs_ / gr - 1) <= 0.10,
            "F5_spearman>=0.80": spearman(dr, ds) >= 0.80,
            "cells": {c: [dr[i], ds[i]] for i, c in enumerate(ids)}}
    json.dump(out, open(os.path.join(HERE, "out", "symphony.json"), "w"), indent=1)
    print("flag differs on", out["flag_differs"])
    print("erratum", {k: v for k, v in out["erratum"].items()})
    for k, v in out["bars"].items():
        print(k, {a: b for a, b in v.items() if a != "cells"})


if __name__ == "__main__":
    main()
