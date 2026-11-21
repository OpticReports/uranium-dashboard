"""Post hoc, after the map: (a) the mirror of P1 on the two states where the book earned MORE while the
state was on (S&P below its 200-day average; gold strong): the book at half size on the other days, full
size on those days, against a constant mix with the same average exposure, with the same shifted-state
placebo; (b) the book's log growth by calendar year and each engine's part of it. Writes out/leanin.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m1_run as m1  # noqa: E402

out = {"lean_in": {}, "by_year": {}}
rng = np.random.default_rng(61)
for sid in ("T1", "F_GOLD"):
    out["lean_in"][sid] = {}
    for which in ("verdict", "real", "shape"):
        ds, r, tb = m1.sample("BOOK", which)
        ii = np.array([m1.pos[d] for d in ds])
        s = np.nan_to_num(m1.S[sid][ii])
        ksh = rng.integers(63, len(ds) - 63, 1000)
        res = m1.p1(1 - s, r, tb, ksh)
        res["span"] = [ds[0], ds[-1], len(ds)]
        # the constant mix whose deepest fall equals the policy's, and what it grows at
        grid = np.linspace(0.3, 1.0, 141)
        dd = np.array([float(m1.maxdd(e * r + (1 - e) * tb)) for e in grid])
        e_eq = float(grid[int(np.argmin(np.abs(dd - res["maxdd"])))])
        res["same_fall_mix"] = {"exposure": e_eq, "growth": float(np.log1p(e_eq * r + (1 - e_eq) * tb).mean() * 252), "maxdd": float(m1.maxdd(e_eq * r + (1 - e_eq) * tb))}
        res["growth_full"] = float(np.log1p(r).mean() * 252)
        out["lean_in"][sid][which] = res
        print(sid, which, {k: round(v, 3) for k, v in res.items() if isinstance(v, float)}, res["same_fall_mix"])
W = {"HG": 0.341, "KMLM": 0.341, "SLEEVE": 0.318}
ds = sorted(m1.E["BOOK"])
for y in sorted({d[:4] for d in ds}):
    dd = [d for d in ds if d[:4] == y]
    row = {"book_log": float(np.log1p([m1.E["BOOK"][d] for d in dd]).sum())}
    for e, w in W.items():
        row[e] = float(sum(w * m1.E[e].get(d, m1.E["TBILL"][d]) for d in dd))       # weighted sum of daily returns: the engine's part
    out["by_year"][y] = row
tot = {k: sum(v[k] for y, v in out["by_year"].items() if y >= "2015") for k in ("book_log", "HG", "KMLM", "SLEEVE")}
print("2015 on", {k: round(v, 2) for k, v in tot.items()})
for y in ("2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"):
    print(y, {k: round(v, 2) for k, v in out["by_year"][y].items()})
json.dump(out, open(os.path.join(HERE, "out", "leanin.json"), "w"))
