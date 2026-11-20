"""The 62 switch-type variants of addendum 57 on the long history (DEVIATIONS.md 9-12): MODEL years
1991-04..2008-01, REPLICATION years 2008-02..2020-12 (both on the long panel with the synthetic KMLM) and
the REAL years 2021-06..2026-11 (corrected fund; from v2_symphony.py's cache). Writes out/long.json and
out/long_paths.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K57 = os.path.join(HERE, "..", "kmlm_2026-11")
sys.path.insert(0, HERE)
sys.path.insert(0, K57)
import data as kdata  # noqa: E402
import ksim as ks  # noqa: E402
import ksynth as ky  # noqa: E402
import q1_cells as q1  # noqa: E402
import sdata  # noqa: E402
from q2_stats import GRIDS, LIVE, boot_idx, stat  # noqa: E402

M0, R0, R1 = "1991-04-01", "2008-02-01", "2020-12-01"
DRAWS, SEED = 5000, 20261121


def long_panel(mode, exposure):
    sys.path.insert(0, os.path.join(HERE, "..", "longrun"))
    import long_panel as lp
    P, _ = lp.build_long_prices(vix_mode=mode)
    ky.set_calendar([d for d in P["SPY"] if d <= "2024-03-28"])
    syn = ky.build(exposure, start="1986-01-01")
    v1 = json.load(open(sdata.CACHE + "/synth_v1.json"))["ret"]
    worst = max(abs(syn[d] - v1[d]) for d in v1 if d >= "1995-01-01" and d in syn)
    if worst > 1e-9 or any(d not in syn for d in v1 if d >= "1995-01-01"):
        raise RuntimeError(f"the long-calendar synthetic is not the fidelity run's series (max gap {worst})")
    P = dict(P)
    P["KMLM"] = ky.level(syn)
    return P


def t_of(x):
    s = x.std(ddof=1)
    return float(x.mean() / (s / math.sqrt(len(x)))) if s > 0 else 0.0


def part(run, lo, hi):
    idx = [i for i, d in enumerate(run["days"]) if lo <= d <= hi]
    days = [run["days"][i] for i in idx]
    return days, {c: (np.array(v["ret"])[idx], np.array(v["to"])[idx]) for c, v in run["cells"].items()}


def main():
    exposure = json.load(open(os.path.join(HERE, "out", "fidelity.json")))["exposure"]
    runs = {}
    for mode in ("ts_synth", "plain", "level"):
        P = long_panel(mode, exposure)
        runs[mode] = q1.run(P, M0, R1 if mode == "ts_synth" else "2008-01-31", tier_c=True)
        print(mode, len(runs[mode]["days"]), runs[mode]["days"][0], runs[mode]["days"][-1], flush=True)
    json.dump(runs["ts_synth"], open(sdata.CACHE + "/cells_long.json", "w"))
    real = json.load(open(sdata.CACHE + "/cells_real_tr.json"))
    ids = [c for c in runs["ts_synth"]["cells"] if c != "base"]
    assert len(ids) == 62, len(ids)
    dM, cM = part(runs["ts_synth"], M0, "2008-01-31")
    dR, cR = part(runs["ts_synth"], R0, R1)
    dA, cA = part(real, "0", "9")
    cost = ks.COST

    def diff(cells, c, extra=0.0):
        return np.log1p(cells[c][0] - extra * cells[c][1]) - np.log1p(cells["base"][0] - extra * cells["base"][1])

    D = {k: np.array([diff(cc, c) for c in ids]).T for k, cc in (("M", cM), ("R", cR), ("A", cA))}
    J = np.vstack([D["R"], D["A"]])                                          # the verdict sample
    n = len(J)
    mean, se = J.mean(0), J.std(0, ddof=1) / math.sqrt(n)
    t = np.where(se > 0, mean / np.where(se > 0, se, 1), 0.0)
    rng = np.random.default_rng(SEED)
    mx = np.empty(DRAWS)
    for b in range(DRAWS):
        Jb = J[boot_idx(n, rng)]
        sb = Jb.std(0, ddof=1) / math.sqrt(n)
        ok = sb > 0
        mx[b] = np.max(np.where(ok, (Jb.mean(0) - mean) / np.where(ok, sb, 1), -np.inf))
    crit = float(np.quantile(mx, 0.90))
    J2 = np.vstack([np.array([diff(cR, c, cost) for c in ids]).T, np.array([diff(cA, c, cost) for c in ids]).T])
    pos = {c: i for i, c in enumerate(ids)}
    beats = lambda c: c in LIVE or mean[pos[c]] > 0                          # noqa: E731
    base = {k: stat(cc["base"][0]) for k, cc in (("M", cM), ("R", cR), ("A", cA))}
    out = {"spans": {"M": [dM[0], dM[-1], len(dM)], "R": [dR[0], dR[-1], len(dR)], "A": [dA[0], dA[-1], len(dA)]},
           "exposure": exposure, "base": base, "critical_t_90": crit, "critical_t_95": float(np.quantile(mx, 0.95)), "cells": {}}
    for i, c in enumerate(ids):
        fam = runs["ts_synth"]["cells"][c]["family"]
        grid = next((g for g in GRIDS.values() if c in g), None)
        if fam == "F2":
            mem = [f"F1a.rsi{m}" for m in c.split("vote")[-1].split("split")[-1].split("-")]
            med = float(np.median([0.0 if m in LIVE else mean[pos[m]] for m in mem]))
            c3 = bool(mean[i] > med)
        else:
            k = grid.index(c)
            c3 = all(beats(x) for x in (grid[j] for j in (k - 1, k + 1) if 0 <= j < len(grid)))
        sR, sA, sM = stat(cR[c][0]), stat(cA[c][0]), stat(cM[c][0])
        p = float((mx >= t[i]).mean()) if se[i] > 0 else 1.0
        cond = {"1_fw_p<0.10": bool(mean[i] > 0 and p < 0.10),
                "2_ahead_in_R_and_REAL": bool(D["R"][:, i].mean() > 0 and D["A"][:, i].mean() > 0),
                "3_plateau": c3,
                "4_maxdd_within_5pts": bool(sR["maxdd"] <= base["R"]["maxdd"] + 0.05 and sA["maxdd"] <= base["A"]["maxdd"] + 0.05),
                "5_positive_at_2x_cost": bool(J2[:, i].mean() > 0)}
        live = c in LIVE or bool(np.all(D["R"][:, i] == 0) and np.all(D["A"][:, i] == 0))
        out["cells"][c] = {
            "family": fam, "is_live_rule": live,
            "joined": {"dlog_per_yr": float(mean[i] * 252), "t": float(t[i]), "p_fw": p, "se_per_yr": float(se[i] * 252),
                       "mde50": float(crit * se[i] * 252)},
            "R": {"dlog_per_yr": float(D["R"][:, i].mean() * 252), "t": t_of(D["R"][:, i]), **sR},
            "REAL": {"dlog_per_yr": float(D["A"][:, i].mean() * 252), "t": t_of(D["A"][:, i]), **sA},
            "M": {"dlog_per_yr": float(D["M"][:, i].mean() * 252), "t": t_of(D["M"][:, i]), **sM,
                  "other_vix_models": {m: float((np.log1p(np.array(runs[m]["cells"][c]["ret"])) - np.log1p(np.array(runs[m]["cells"]["base"]["ret"]))).mean() * 252)
                                       for m in ("plain", "level")}},
            "flips_per_yr": runs["ts_synth"]["cells"][c].get("flips", 0) / (len(runs["ts_synth"]["days"]) / 252),
            "conditions": None if live else cond, "passes": None if live else bool(all(cond.values()))}
    out["passing"] = [c for c in ids if out["cells"][c]["passes"]]
    out["ahead_joined"] = sorted(c for c in ids if not out["cells"][c]["is_live_rule"] and out["cells"][c]["joined"]["dlog_per_yr"] > 0)
    out["ahead_all_three"] = sorted(c for c in ids if not out["cells"][c]["is_live_rule"] and all(out["cells"][c][k]["dlog_per_yr"] > 0 for k in ("R", "REAL", "M")))
    best = int(np.argmax(t))
    out["best_by_t"] = ids[best]
    groups = {"long_14_60": (14, 17, 20, 25, 30, 40, 60), "short_3_8": (3, 5, 7, 8), "near_9_12": (9, 11, 12)}
    out["groups"] = {}
    for g, ns in groups.items():
        cs = [pos[f"{f}.rsi{k}"] for f in ("F1a", "F1b") for k in ns]
        out["groups"][g] = {k: {"dlog_per_yr": float(D[k][:, cs].mean(1).mean() * 252), "t": t_of(D[k][:, cs].mean(1)),
                                "cells_ahead": int((D[k][:, cs].mean(0) > 0).sum()), "cells": len(cs)} for k in ("M", "R", "A")}
        gj = np.concatenate([D["R"][:, cs].mean(1), D["A"][:, cs].mean(1)])
        out["groups"][g]["joined"] = {"dlog_per_yr": float(gj.mean() * 252), "t": t_of(gj)}
    for fam, pick in (("ma_price", [c for c in ids if c.startswith("F5.")]), ("ma_cross", [c for c in ids if c.startswith("F6.")]),
                      ("momentum", [c for c in ids if c.startswith("F4.")])):
        cs = [pos[c] for c in pick]
        out["groups"][fam] = {k: {"dlog_per_yr": float(D[k][:, cs].mean(1).mean() * 252), "t": t_of(D[k][:, cs].mean(1)),
                                  "cells_ahead": int((D[k][:, cs].mean(0) > 0).sum()), "cells": len(cs)} for k in ("M", "R", "A")}
    # by calendar year in R: the live rule and the best cell's difference
    yrs = sorted({d[:4] for d in dM + dR + dA})
    alld, allD, allb = dM + dR + dA, np.vstack([D["M"], D["R"], D["A"]]), np.concatenate([cM["base"][0], cR["base"][0], cA["base"][0]])
    out["by_year"] = {y: {"live": float(np.prod(1 + allb[[i for i, d in enumerate(alld) if d[:4] == y]]) - 1),
                          "long_minus_live": float(allD[[i for i, d in enumerate(alld) if d[:4] == y]][:, [pos[f"{f}.rsi{k}"] for f in ("F1a", "F1b") for k in groups["long_14_60"]]].mean(1).sum()),
                          "best_minus_live": float(allD[[i for i, d in enumerate(alld) if d[:4] == y], best].sum())} for y in yrs}
    json.dump(out, open(os.path.join(HERE, "out", "long.json"), "w"), indent=1)
    step = 5
    show = ["F1a.rsi14", "F1a.rsi20", "F1a.rsi30", "F1a.rsi5", "F5.sma50", "F5.ema200", "F4.mom20", ids[best]]
    paths = {"days": alld[::step], "live_log": np.cumsum(np.log1p(allb))[::step].round(4).tolist(),
             "cells": {c: np.cumsum(allD[:, pos[c]])[::step].round(4).tolist() for c in dict.fromkeys(show)},
             "long_group": np.cumsum(allD[:, [pos[f"{f}.rsi{k}"] for f in ("F1a", "F1b") for k in groups["long_14_60"]]].mean(1))[::step].round(4).tolist(),
             "breaks": [dR[0], dA[0]]}
    json.dump(paths, open(os.path.join(HERE, "out", "long_paths.json"), "w"))
    print("spans", out["spans"])
    for k in ("M", "R", "A"):
        b = base[k]
        print(f"LIVE {k}: {b['cagr']:+.1%}/yr DD {b['maxdd']:.1%} Sharpe {b['sharpe']:.2f}")
    print(f"critical t 90% {crit:.2f}; passing {out['passing'] or 'none'}; ahead joined {len(out['ahead_joined'])}/61; ahead in all three {out['ahead_all_three']}")
    print(f"{'cell':18s} {'joined':>8s} {'t':>6s} {'p_fw':>5s} {'MDE50':>6s} | {'R':>7s} {'t':>5s} | {'REAL':>7s} {'t':>5s} | {'MODEL':>7s} {'t':>5s} (plain, level) | 1 2 3 4 5")
    for c in ids:
        v = out["cells"][c]
        f = lambda x: "Y" if x else "n"  # noqa: E731
        print(f"{c:18s} {v['joined']['dlog_per_yr']:+8.3f} {v['joined']['t']:+6.2f} {v['joined']['p_fw']:5.2f} {v['joined']['mde50']:6.2f} | {v['R']['dlog_per_yr']:+7.3f} {v['R']['t']:+5.1f} | "
              f"{v['REAL']['dlog_per_yr']:+7.3f} {v['REAL']['t']:+5.1f} | {v['M']['dlog_per_yr']:+7.3f} {v['M']['t']:+5.1f} ({v['M']['other_vix_models']['plain']:+.2f}, {v['M']['other_vix_models']['level']:+.2f}) | "
              + ("live rule" if v["is_live_rule"] else " ".join(f(x) for x in v["conditions"].values())) + ("  <== PASSES" if v["passes"] else ""))
    for g, v in out["groups"].items():
        print(g, {k: (round(x["dlog_per_yr"], 3), round(x["t"], 2)) + ((f"{x['cells_ahead']}/{x['cells']}",) if "cells" in x else ()) for k, x in v.items()})


if __name__ == "__main__":
    main()
