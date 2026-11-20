"""Q4 (PREREG.md "The collective"): the three-engine book at 34.1 / 34.1 / 31.8 with KMLM as the live
rule, as each of the three window ensembles (vote and split forms), and - as a labelled illustration,
DEVIATIONS.md 2 - as the cell with the highest t in q2 although it does not pass. HG and SLEEVE are
Composer's own backtests (research/zvol_2026-11/data, to 2026-11-17), unchanged. Two book rules: weights
reset daily, and weights drifting with a reset to target when one engine passes 44% (POLICY operation 5).
Differences from the live book carry a 90% paired stationary-bootstrap interval. Writes out/book.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "zvol_2026-11"))
import data  # noqa: E402
import lib  # noqa: E402
from q2_stats import boot_idx  # noqa: E402

W = np.array([29.0, 29.0, 27.0]) / 85.0          # HG, KMLM, SLEEVE
CAP, DRAWS, SEED = 0.44, 2000, 20261120


def book(R, drift):
    """R: T x 3 daily returns (HG, KMLM, SLEEVE) -> the book's daily returns"""
    if not drift:
        return R @ W
    out, w = np.empty(len(R)), W.copy()
    for t in range(len(R)):
        g = w * (1 + R[t])
        out[t] = g.sum() - 1
        w = g / g.sum()
        if w.max() > CAP:
            w = W.copy()
    return out


def metrics(r, rf):
    lvl = np.cumprod(1 + r)
    ex = r - rf
    k = max(1, int(round(0.05 * len(r))))
    m = np.add.reduceat(np.log1p(r), np.arange(0, len(r), 21))
    return np.array([lvl[-1] ** (252 / len(r)) - 1, r.std(ddof=1) * math.sqrt(252),
                     ex.mean() / ex.std(ddof=1) * math.sqrt(252), np.max(1 - lvl / np.maximum.accumulate(lvl)),
                     np.sort(r)[:k].mean(), np.expm1(m.min())])


NAMES = ("cagr", "vol", "sharpe", "maxdd", "cvar5", "worst_21d")


def main():
    ab = json.load(open(os.path.join(HERE, "out", "cells_ab.json")))
    st = json.load(open(os.path.join(HERE, "out", "stats.json")))
    Z = os.path.join(HERE, "..", "zvol_2026-11", "data")
    hg, sl = lib.load_bt(f"{Z}/bt_HG.json")["ret"], lib.load_bt(f"{Z}/bt_SLEEVE.json")["ret"]
    bil = data.rets(data.series("BIL"))
    days = [d for d in ab["days"] if d > ab["a_start"] and d in hg and d in sl]
    ix = {d: i for i, d in enumerate(ab["days"])}
    col = lambda c: np.array([ab["cells"][c]["ret"][ix[d]] for d in days])          # noqa: E731
    H, S, rf = np.array([hg[d] for d in days]), np.array([sl[d] for d in days]), np.array([bil.get(d, 0.0) for d in days])
    cells = ["base"] + [c for c in ab["cells"] if c.startswith("F2.")] + [st["beside"]["best_by_t"]]
    out = {"span": [days[0], days[-1]], "n": len(days), "weights": dict(zip(("HG", "KMLM", "SLEEVE"), W.round(4).tolist())),
           "illustration_only": st["beside"]["best_by_t"], "books": {}}
    rng = np.random.default_rng(SEED)
    paths = [boot_idx(len(days), rng) for _ in range(DRAWS)]
    for drift in (False, True):
        key = "drift_cap44" if drift else "daily_fixed"
        R0 = np.column_stack([H, col("base"), S])
        b0 = book(R0, drift)
        out["books"][key] = {}
        for c in cells:
            Rc = np.column_stack([H, col(c), S])
            bc = book(Rc, drift)
            m = metrics(bc, rf)
            row = {"metrics": dict(zip(NAMES, m.tolist())), "kmlm_alone": dict(zip(NAMES, metrics(col(c), rf).tolist()))}
            if c != "base":
                d = np.array([metrics(book(Rc[p], drift), rf[p]) - metrics(book(R0[p], drift), rf[p]) for p in paths])
                row["diff_vs_live"] = {n: {"point": float(m[i] - metrics(b0, rf)[i]), "lo": float(np.quantile(d[:, i], 0.05)),
                                           "hi": float(np.quantile(d[:, i], 0.95))} for i, n in enumerate(NAMES)}
            out["books"][key][c] = row
    json.dump(out, open(os.path.join(HERE, "out", "book.json"), "w"), indent=1)
    print("span", out["span"], "n", out["n"])
    for key, b in out["books"].items():
        print(key)
        for c, row in b.items():
            m, k = row["metrics"], row["kmlm_alone"]
            s = f"  {c:24s} book CAGR {m['cagr']:+7.1%} vol {m['vol']:5.1%} Sh {m['sharpe']:.2f} DD {m['maxdd']:5.1%} | KMLM alone {k['cagr']:+7.1%} DD {k['maxdd']:5.1%}"
            if "diff_vs_live" in row:
                d = row["diff_vs_live"]
                s += (f" | dCAGR {d['cagr']['point']*100:+.1f} [{d['cagr']['lo']*100:+.1f},{d['cagr']['hi']*100:+.1f}] "
                      f"dDD {d['maxdd']['point']*100:+.1f} [{d['maxdd']['lo']*100:+.1f},{d['maxdd']['hi']*100:+.1f}] "
                      f"dSh {d['sharpe']['point']:+.2f} [{d['sharpe']['lo']:+.2f},{d['sharpe']['hi']:+.2f}]")
            print(s)


if __name__ == "__main__":
    main()
