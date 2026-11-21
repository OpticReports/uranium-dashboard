"""Statistics of the windows study (PREREG.md "Verdict rule"), per engine, from the cell paths of
w2_cells.py. Writes out/stats_<ENGINE>.json. The verdict sample is REPLICATION + REAL joined; each stretch
alone, the stretch-standardised t, the MODEL years, the power and the group averages are beside it.
Usage: python3 w3_stats.py [SLEEVE_R_START]   (the sleeve's replication start; default as registered)"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wsim as w  # noqa: E402
from q2_stats import boot_idx, stat  # noqa: E402

from statistics import NormalDist  # noqa: E402

DRAWS, SEED = 5000, 20261122
MIN_DIFF = 75                      # days a variant must differ from the live rule to enter the restricted bar (DEVIATIONS.md 5)
COST = w.ks.COST


def t_of(x):
    s = x.std(ddof=1)
    return float(x.mean() / (s / math.sqrt(len(x)))) if s > 0 else 0.0


def maxstat(D, draws, rng):
    n = len(D)
    mean, se = D.mean(0), D.std(0, ddof=1) / math.sqrt(n)
    t = np.where(se > 0, mean / np.where(se > 0, se, 1), 0.0)
    mx = np.empty(draws)
    for b in range(draws):
        Db = D[boot_idx(n, rng)]
        sb = Db.std(0, ddof=1) / math.sqrt(n)
        ok = sb > 0
        mx[b] = np.max(np.where(ok, (Db.mean(0) - mean) / np.where(ok, sb, 1), -np.inf))
    return t, mx, se


def run(eng, r_start=None):
    o = json.load(open(f"{w.CACHE}/cells_{eng}.json"))
    sp = {k: list(v) for k, v in o["span"].items()}
    if r_start:
        sp["M"][1], sp["R"][0] = "moved", r_start
    ld, rd = o["long_days"], o["real_days"]
    iM = [i for i, d in enumerate(ld) if d < sp["R"][0]]
    iR = [i for i, d in enumerate(ld) if d >= sp["R"][0]]
    ids = [c for c in o["cells"] if c != "base"]

    def arr(c, key, f, idx=None, extra=0.0):
        x = np.array(o["cells"][c][key]["ret"]) - extra * np.array(o["cells"][c][key]["to"])
        return x if idx is None else x[idx]

    R = {"M": {c: arr(c, "long", 0, iM) for c in o["cells"]}, "R": {c: arr(c, "long", 0, iR) for c in o["cells"]}, "A": {c: arr(c, "real", 0) for c in o["cells"]}}
    R2 = {"R": {c: arr(c, "long", 0, iR, COST) for c in o["cells"]}, "A": {c: arr(c, "real", 0, None, COST) for c in o["cells"]}}
    D = {k: np.array([np.log1p(R[k][c]) - np.log1p(R[k]["base"]) for c in ids]).T for k in R}
    J = np.vstack([D["R"], D["A"]])
    J2 = np.vstack([np.array([np.log1p(R2[k][c]) - np.log1p(R2[k]["base"]) for c in ids]).T for k in ("R", "A")])
    Js = np.vstack([D[k] / np.where(D[k].std(0, ddof=1) > 0, D[k].std(0, ddof=1), 1) for k in ("R", "A")])   # each stretch at unit variance
    rng = np.random.default_rng(SEED)
    t, mx, se = maxstat(J, DRAWS, rng)
    mean = J.mean(0)
    crit = float(np.quantile(mx, 0.90))
    ndiff = (J != 0).sum(0)
    wide = np.flatnonzero(ndiff >= MIN_DIFF)
    _, mxw, _ = maxstat(J[:, wide], 2000, rng)
    nd = NormalDist()
    bonf = nd.inv_cdf(1 - 0.10 / len(ids))
    ts, mxs, _ = maxstat(Js, 2000, rng)
    alone = {}
    for k in ("R", "A", "M"):
        tk, mk, _ = maxstat(D[k], 2000, rng)
        alone[k] = {"t": tk, "crit90": float(np.quantile(mk, 0.90)), "p": [(float((mk >= x).mean())) for x in tk]}
    base = {k: stat(R[k]["base"]) for k in R}
    pos = {c: i for i, c in enumerate(ids)}
    beats = lambda c: c in w.LIVE or mean[pos[c]] > 0                        # noqa: E731
    yrs = {k: len(R[k]["base"]) / 252 for k in R}
    out = {"engine": eng, "spans": {"M": [ld[iM[0]], ld[iM[-1]], len(iM)] if iM else None, "R": [ld[iR[0]], ld[iR[-1]], len(iR)], "A": [rd[0], rd[-1], len(rd)]},
           "base": base, "critical_t_90": crit, "critical_t_95": float(np.quantile(mx, 0.95)), "critical_t_90_standardised": float(np.quantile(mxs, 0.90)),
           "critical_t_90_bonferroni": bonf, "critical_t_90_restricted": float(np.quantile(mxw, 0.90)), "restricted_cells": int(len(wide)),
           "critical_alone": {k: v["crit90"] for k, v in alone.items()}, "cells": {}}
    for i, c in enumerate(ids):
        grid = w.GRIDS[o["cells"][c]["grid"]]
        k_ = grid.index(c)
        nb = [grid[j] for j in (k_ - 1, k_ + 1) if 0 <= j < len(grid)]
        st = {k: stat(R[k][c]) for k in R}
        p = float((mx >= t[i]).mean()) if se[i] > 0 else 1.0
        same = bool(all(np.all(D[k][:, i] == 0) for k in ("R", "A")))
        cond = {"1_fw_p<0.10": bool(mean[i] > 0 and p < 0.10), "2_ahead_in_R_and_REAL": bool(D["R"][:, i].mean() > 0 and D["A"][:, i].mean() > 0),
                "3_neighbours_ahead": all(beats(x) for x in nb),
                "4_maxdd_within_5pts": bool(st["R"]["maxdd"] <= base["R"]["maxdd"] + 0.05 and st["A"]["maxdd"] <= base["A"]["maxdd"] + 0.05),
                "5_ahead_at_2x_cost": bool(J2[:, i].mean() > 0)}
        p_bonf = min(1.0, len(ids) * (1 - nd.cdf(float(t[i]))))
        top = {}
        for k in ("R", "A"):
            tot = float(D[k][:, i].sum())
            top[k] = float(np.sort(D[k][:, i])[-10:].sum() / tot) if tot > 0 else None
        out["cells"][c] = {
            "family": o["cells"][c]["family"], "grid": o["cells"][c]["grid"], "same_as_live": same, "neighbours": nb,
            "days_differing": int(ndiff[i]), "share_of_gain_from_best_10_days": top,
            "joined": {"dlog_per_yr": float(mean[i] * 252), "t": float(t[i]), "p_fw": p, "mde50": float(crit * se[i] * 252),
                       "p_bonferroni": p_bonf, "mde50_bonferroni": float(bonf * se[i] * 252),
                       "passes_with_bonferroni": bool(not same and mean[i] > 0 and p_bonf < 0.10 and all(v for k_, v in cond.items() if not k_.startswith("1_"))),
                       "t_standardised": float(ts[i]), "p_fw_standardised": float((mxs >= ts[i]).mean())},
            **{n: {"dlog_per_yr": float(D[k][:, i].mean() * 252), "t": float(alone[k]["t"][i]), "p_fw_alone": alone[k]["p"][i], **st[k],
                   "turnover_per_yr": float(np.array(o["cells"][c]["long" if k != "A" else "real"]["to"])[(iM if k == "M" else iR) if k != "A" else slice(None)].sum() / yrs[k])}
               for k, n in (("M", "M"), ("R", "R"), ("A", "REAL"))},
            "conditions": None if same else cond, "passes": None if same else bool(all(cond.values()))}
    ch = [c for c in ids if not out["cells"][c]["same_as_live"]]
    out["n_cells"], out["n_distinct"] = len(ids), len(ch)
    out["passing"] = [c for c in ch if out["cells"][c]["passes"]]
    out["ahead_joined"] = sorted(c for c in ch if out["cells"][c]["joined"]["dlog_per_yr"] > 0)
    out["ahead_all_three"] = sorted(c for c in ch if all(out["cells"][c][k]["dlog_per_yr"] > 0 for k in ("R", "REAL", "M")))
    out["ahead_R_and_REAL"] = sorted(c for c in ch if all(out["cells"][c][k]["dlog_per_yr"] > 0 for k in ("R", "REAL")))
    out["best_by_t"] = max(ch, key=lambda c: out["cells"][c]["joined"]["t"])
    out["best_alone"] = {n: max(ch, key=lambda c: out["cells"][c][n]["t"]) for n in ("R", "REAL", "M")}
    m = sorted(out["cells"][c]["joined"]["mde50"] for c in ch)
    out["median_mde50"] = m[len(m) // 2]
    m = sorted(out["cells"][c]["joined"]["mde50_bonferroni"] for c in ch)
    out["median_mde50_bonferroni"] = m[len(m) // 2]
    out["passing_with_bonferroni"] = [c for c in ch if out["cells"][c]["joined"]["passes_with_bonferroni"]]
    out["worse_family_wise"] = sorted((c for c in ch if out["cells"][c]["joined"]["t"] <= -bonf), key=lambda c: out["cells"][c]["joined"]["t"])
    out["ahead_by_stretch"] = {n: int(sum(out["cells"][c][n]["dlog_per_yr"] > 0 for c in ch)) for n in ("M", "R", "REAL")}
    # group averages per grid: cells before the live position (shorter / faster) and after (longer / slower)
    out["groups"] = {}

    def grp(cs):
        cs = [pos[c] for c in cs if c in pos]
        if not cs:
            return None
        g = {k: {"dlog_per_yr": float(D[k][:, cs].mean(1).mean() * 252), "t": t_of(D[k][:, cs].mean(1)), "ahead": int((D[k][:, cs].mean(0) > 0).sum())} for k in ("M", "R", "A")}
        gj = np.concatenate([D["R"][:, cs].mean(1), D["A"][:, cs].mean(1)])
        g["joined"] = {"dlog_per_yr": float(gj.mean() * 252), "t": t_of(gj), "ahead": int((J[:, cs].mean(0) > 0).sum())}
        g["cells"] = len(cs)
        return g
    for gname, grid in w.GRIDS.items():
        if not any(c in pos for c in grid):
            continue
        live = next((j for j, c in enumerate(grid) if c in w.LIVE), None)
        if live is None:                                     # an EMA grid: no live position; split at the live windows' place
            sm = w.GRIDS[gname[:-1] + "s"]
            live_at = next(j for j, c in enumerate(sm) if c in w.LIVE)
            out["groups"][gname] = {"shorter": grp(grid[:live_at]), "at_live_window": grp(grid[live_at:live_at + 1]), "longer": grp(grid[live_at + 1:]), "all": grp(grid)}
        else:
            out["groups"][gname] = {"shorter": grp(grid[:live]), "longer": grp(grid[live + 1:]), "all": grp([c for c in grid if c not in w.LIVE])}
    # EMA minus SMA at the same windows (pairs where both exist; the live SMA counts as zero)
    out["ema_minus_sma"] = {}
    for fam in ("HA", "HB", "HC", "HD"):
        if fam + "s" not in out["groups"] and fam + "e" not in out["groups"]:
            continue
        pairs = [(e, s) for e, s in zip(w.GRIDS[fam + "e"], w.GRIDS[fam + "s"]) if e in pos]
        col = lambda k, c: D[k][:, pos[c]] if c in pos else np.zeros(len(D[k]))   # noqa: E731
        dd = {k: np.mean([col(k, e) - col(k, s) for e, s in pairs], axis=0) for k in ("M", "R", "A")}
        out["ema_minus_sma"][fam] = {k: {"dlog_per_yr": float(v.mean() * 252), "t": t_of(v)} for k, v in dd.items()}
        out["ema_minus_sma"][fam]["pairs_ema_ahead_joined"] = int(sum(np.concatenate([col("R", e) - col("R", s), col("A", e) - col("A", s)]).mean() > 0 for e, s in pairs))
        out["ema_minus_sma"][fam]["pairs"] = len(pairs)
    json.dump(out, open(os.path.join(HERE, "out", f"stats_{eng}.json"), "w"), indent=1)
    print(f"\n===== {eng}  spans {out['spans']}")
    for k in ("M", "R", "A"):
        b = base[k]
        print(f"LIVE {k}: {b['cagr']:+.1%}/yr DD {b['maxdd']:.1%} Sharpe {b['sharpe']:.2f}")
    print(f"Bonferroni bar {bonf:.2f}; restricted bar {out['critical_t_90_restricted']:.2f} over {len(wide)} cells; passing with Bonferroni {out['passing_with_bonferroni'] or 'none'}; "
          f"family-wise worse {out['worse_family_wise']}; ahead by stretch {out['ahead_by_stretch']}; median MDE (Bonferroni) {out['median_mde50_bonferroni']:.3f}")
    print(f"critical t 90% {crit:.2f} (standardised {out['critical_t_90_standardised']:.2f}; alone {out['critical_alone']}); passing {out['passing'] or 'none'}; "
          f"ahead joined {len(out['ahead_joined'])}/{len(ch)}; ahead in R and REAL {out['ahead_R_and_REAL']}; in all three {out['ahead_all_three']}; median MDE50 {out['median_mde50']:.3f}")
    print(f"{'cell':16s} {'joined':>7s} {'t':>6s} {'p_fw':>5s} {'t_std':>6s} {'MDE':>5s} | {'R':>7s} {'t':>5s} {'DD':>4s} | {'REAL':>7s} {'t':>5s} {'DD':>4s} | {'MODEL':>7s} {'t':>5s} | 1 2 3 4 5")
    for c in ids:
        v = out["cells"][c]
        f = lambda x: "Y" if x else "n"  # noqa: E731
        print(f"{c:16s} {v['joined']['dlog_per_yr']:+7.3f} {v['joined']['t']:+6.2f} {v['joined']['p_fw']:5.2f} {v['joined']['t_standardised']:+6.2f} {v['joined']['mde50']:5.2f} | "
              f"{v['R']['dlog_per_yr']:+7.3f} {v['R']['t']:+5.1f} {v['R']['maxdd']:4.0%} | {v['REAL']['dlog_per_yr']:+7.3f} {v['REAL']['t']:+5.1f} {v['REAL']['maxdd']:4.0%} | "
              f"{v['M']['dlog_per_yr']:+7.3f} {v['M']['t']:+5.1f} | " + ("same as live" if v["same_as_live"] else " ".join(f(x) for x in v["conditions"].values())) + ("  <== PASSES" if v["passes"] else ""))
    for g, v in out["groups"].items():
        print(g, {k: ({s: (round(x[s]["dlog_per_yr"], 3), round(x[s]["t"], 1), f"{x[s]['ahead']}/{x['cells']}") for s in ("M", "R", "A", "joined")} if x else None) for k, x in v.items()})
    print("EMA minus SMA", {f: {k: (round(x["dlog_per_yr"], 3), round(x["t"], 1)) if isinstance(x, dict) else x for k, x in v.items()} for f, v in out["ema_minus_sma"].items()})
    return out


if __name__ == "__main__":
    run("HG")
    run("SLEEVE", sys.argv[1] if len(sys.argv) > 1 else None)
