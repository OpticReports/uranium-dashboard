"""Q2: the pre-registered verdict on every cell (PREREG.md "What counts as a superior time frame").
Reads out/cells_ab.json (and cells_c.json when present); writes out/stats.json and prints the table.
Nothing is selected here: every one of the 74 declared cells is judged by the same five conditions."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "barbell-lab", "src"))
from barbell.stats import dsr as bdsr  # noqa: E402
from barbell.stats import pbo as bpbo  # noqa: E402

DRAWS, BLOCK, SEED = 5000, 10, 20261120
TRIALS = 101                       # 74 declared + the 27 scouting cells seen before the pre-registration
GRIDS = {                          # each cell's neighbours live on its own grid, in this order
    "F1a": [f"F1a.rsi{n}" for n in (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)],
    "F1b": [f"F1b.rsi{n}" for n in (3, 5, 7, 8, 9, 10, 11, 12, 14, 17, 20, 25, 30, 40, 60)],
    "F3a": [f"F3a.pops{n}" for n in (5, 7, 14, 20)], "F3b": [f"F3b.dips{n}" for n in (5, 7, 14, 20)],
    "F3c": [f"F3c.both{n}" for n in (5, 7, 14, 20)],
    "F4": [f"F4.mom{n}" for n in (5, 10, 20, 40, 60, 120)],
    "F5s": [f"F5.sma{n}" for n in (10, 20, 50, 100, 200)], "F5e": [f"F5.ema{n}" for n in (10, 20, 50, 100, 200)],
    "F6s": [f"F6.sma{a}x{b}" for a, b in ((5, 20), (10, 20), (10, 50), (20, 50), (50, 200))],
    "F6e": [f"F6.ema{a}x{b}" for a, b in ((5, 20), (10, 20), (10, 50), (20, 50), (50, 200))],
}
LIVE = {"F1a.rsi10", "F1b.rsi10"}  # these two declared cells ARE the live rule


def stat(r):
    r = np.asarray(r)
    lvl = np.cumprod(1 + r)
    dd = float(np.max(1 - lvl / np.maximum.accumulate(lvl)))
    sd = r.std(ddof=1)
    return {"cagr": float(lvl[-1] ** (252 / len(r)) - 1), "maxdd": dd,
            "sharpe": float(r.mean() / sd * math.sqrt(252)) if sd else 0.0, "n": int(len(r))}


def boot_idx(n, rng):
    """stationary bootstrap index path (Politis-Romano), mean block BLOCK"""
    idx = np.empty(n, dtype=np.int64)
    i = rng.integers(n)
    jump = rng.random(n) < 1.0 / BLOCK
    starts = rng.integers(n, size=n)
    for t in range(n):
        idx[t] = i
        i = starts[t] if jump[t] else (i + 1) % n
    return idx


def main():
    ab = json.load(open(os.path.join(HERE, "out", "cells_ab.json")))
    days = ab["days"]
    ids = [c for c in ab["cells"] if c != "base"]
    assert len(ids) == 74, len(ids)
    a_mask = np.array([d > ab["a_start"] for d in days])
    R = np.array([ab["cells"][c]["ret"] for c in ids]).T                    # T x 74
    TO = np.array([ab["cells"][c]["to"] for c in ids]).T
    rb, tob = np.array(ab["cells"]["base"]["ret"]), np.array(ab["cells"]["base"]["to"])
    D = np.log1p(R) - np.log1p(rb)[:, None]                                  # daily log-return difference
    n = len(days)
    mean, se = D.mean(0), D.std(0, ddof=1) / math.sqrt(n)
    tstat = np.where(se > 0, mean / np.where(se > 0, se, 1), 0.0)
    # ---- condition 1: max-statistic stationary bootstrap over all 74 cells (studentised, centred)
    rng = np.random.default_rng(SEED)
    mx = np.empty(DRAWS)
    for b in range(DRAWS):
        Db = D[boot_idx(n, rng)]
        sb = Db.std(0, ddof=1) / math.sqrt(n)
        ok = sb > 0
        mx[b] = np.max(np.where(ok, (Db.mean(0) - mean) / np.where(ok, sb, 1), -np.inf))
    p_fw = np.array([(mx >= t).mean() if s > 0 else 1.0 for t, s in zip(tstat, se)])
    # ---- conditions 2-5
    mA, mB = D[a_mask].mean(0), D[~a_mask].mean(0)
    base_all = stat(rb)
    R2 = R - ab["cost"] * TO                                                # a second cost on every trade
    D2 = np.log1p(R2) - np.log1p(rb - ab["cost"] * tob)[:, None]
    pos = {c: i for i, c in enumerate(ids)}
    beats = lambda c: c in LIVE or mean[pos[c]] > 0                          # noqa: E731
    out = {"n_sessions": n, "tier_b": [days[0], ab["a_start"]], "tier_a": [ab["a_start"], days[-1]],
           "base": {"all": base_all, "A": stat(rb[a_mask]), "B": stat(rb[~a_mask]),
                    "turnover": float(tob.sum()), "trades": ab["cells"]["base"]["trades"],
                    "flips": ab["cells"]["base"].get("flips"), "knife_share": ab["cells"]["base"].get("knife_share")},
           "cells": {}}
    for i, c in enumerate(ids):
        fam = ab["cells"][c]["family"]
        grid = next((g for g in GRIDS.values() if c in g), None)
        if fam == "F2":
            mem = [f"F1a.rsi{m}" for m in c.split("vote")[-1].split("split")[-1].split("-")]
            med = float(np.median([0.0 if m in LIVE else mean[pos[m]] for m in mem]))
            c3, c3_note = bool(mean[i] > med), f"vs member median {med * 252:+.3f}/yr"
        else:
            k = grid.index(c)
            nb = [grid[j] for j in (k - 1, k + 1) if 0 <= j < len(grid)]
            c3, c3_note = all(beats(x) for x in nb), "neighbours " + ", ".join(f"{x.split('.')[-1]}{'+' if beats(x) else '-'}" for x in nb)
        s_all, s_a, s_b = stat(R[:, i]), stat(R[a_mask, i]), stat(R[~a_mask, i])
        cond = {"1_fw_p<0.10": bool(mean[i] > 0 and p_fw[i] < 0.10), "2_beats_in_A_and_B": bool(mA[i] > 0 and mB[i] > 0),
                "3_plateau": c3, "4_maxdd_within_5pts": bool(s_all["maxdd"] <= base_all["maxdd"] + 0.05),
                "5_positive_at_2x_cost": bool(D2[:, i].mean() > 0)}
        if c in LIVE:
            cond = {k_: None for k_ in cond}
        out["cells"][c] = {"family": fam, "all": s_all, "A": s_a, "B": s_b,
                           "dlog_per_yr": float(mean[i] * 252), "dlog_A": float(mA[i] * 252), "dlog_B": float(mB[i] * 252),
                           "t": float(tstat[i]), "p_fw": float(p_fw[i]), "conditions": cond, "plateau_note": c3_note,
                           "passes": bool(all(v for v in cond.values())) if c not in LIVE else None,
                           "turnover": float(TO[:, i].sum()), "trades": ab["cells"][c]["trades"],
                           "flips": ab["cells"][c].get("flips"), "knife_share": ab["cells"][c].get("knife_share")}
    # ---- beside the verdict: overfitting probability, deflated Sharpe, fragility of the live window
    pbo = bpbo.cscv_pbo(np.column_stack([rb, R]), n_blocks=10)
    best = int(np.argmax(tstat))
    sr_d = D.mean(0) / np.where(D.std(0, ddof=1) > 0, D.std(0, ddof=1), np.nan)
    mom = bdsr.moments(D[:, best])
    dsr = bdsr.deflated_sharpe(float(sr_d[best]), n, TRIALS, float(np.nanvar(sr_d, ddof=1)), skew=mom["skew"], kurt=mom["kurt"])
    f1a = [c for c in GRIDS["F1a"] if c not in LIVE]
    far = [c for c in f1a if abs(out["cells"][c]["A"]["cagr"] - out["base"]["A"]["cagr"]) > 0.50]
    out["beside"] = {"pbo": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in pbo.items()
                             if not isinstance(v, (list, np.ndarray))},
                     "best_by_t": ids[best], "deflated_sharpe_of_best_difference": dsr,
                     "fragile": {"f1a_cells_more_than_50pts_from_live_on_A": far, "share": len(far) / len(f1a),
                                 "supported": len(far) / len(f1a) > 1 / 3},
                     "max_stat_95": float(np.quantile(mx, 0.95)), "max_stat_90": float(np.quantile(mx, 0.90))}
    out["passing"] = [c for c in ids if out["cells"][c]["passes"]]
    cpath = os.path.join(HERE, "out", "cells_c.json")
    if os.path.exists(cpath):
        cc = json.load(open(cpath))
        cb = np.array(cc["cells"]["base"]["ret"])
        out["tier_c"] = {"span": [cc["days"][0], cc["days"][-1]], "base": stat(cb), "cells": {}}
        for c, v in cc["cells"].items():
            if c == "base":
                continue
            r = np.array(v["ret"])
            out["tier_c"]["cells"][c] = dict(stat(r), dlog_per_yr=float((np.log1p(r) - np.log1p(cb)).mean() * 252))
    json.dump(out, open(os.path.join(HERE, "out", "stats.json"), "w"), indent=1)
    b = out["base"]
    print(f"sessions {n}: B {days[0]}..{ab['a_start']}, A ..{days[-1]}")
    print(f"LIVE  all {b['all']['cagr']:+7.1%} DD {b['all']['maxdd']:5.1%} Sh {b['all']['sharpe']:.2f} | A {b['A']['cagr']:+7.1%} "
          f"DD {b['A']['maxdd']:5.1%} | B {b['B']['cagr']:+7.1%} DD {b['B']['maxdd']:5.1%} | flips {b['flips']} knife {b['knife_share']:.1%}")
    print(f"{'cell':22s} {'all CAGR':>9s} {'DD':>6s} {'Sh':>5s} | {'A':>8s} {'B':>8s} | {'dlog/yr':>8s} {'t':>6s} {'p_fw':>5s} | 1 2 3 4 5 | C dlog")
    for c in ids:
        v = out["cells"][c]
        k = v["conditions"]
        f = lambda x: "." if x is None else ("Y" if x else "n")              # noqa: E731
        tc = out.get("tier_c", {}).get("cells", {}).get(c)
        print(f"{c:22s} {v['all']['cagr']:+9.1%} {v['all']['maxdd']:6.1%} {v['all']['sharpe']:5.2f} | {v['A']['cagr']:+8.1%} "
              f"{v['B']['cagr']:+8.1%} | {v['dlog_per_yr']:+8.3f} {v['t']:+6.2f} {v['p_fw']:5.2f} | "
              + " ".join(f(x) for x in k.values()) + (f" | {tc['dlog_per_yr']:+.3f}" if tc else " |") + ("  <== PASSES" if v["passes"] else ""))
    bs = out["beside"]
    print(f"passing: {out['passing'] or 'none'}")
    print(f"max-stat critical t: 90% {bs['max_stat_90']:.2f}, 95% {bs['max_stat_95']:.2f}; best by t: {bs['best_by_t']}")
    print(f"PBO {bs['pbo']}")
    print(f"deflated Sharpe of the best difference ({TRIALS} trials): {bs['deflated_sharpe_of_best_difference']}")
    print(f"fragile: {bs['fragile']}")


if __name__ == "__main__":
    main()
