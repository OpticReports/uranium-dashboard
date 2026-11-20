"""Every pre-registered cell (PREREG.md), simulated once on the long panel (MODEL + REPLICATION years, one
continuous path) and once on fresh closes (REAL years). Writes the daily paths to the scratch cache
(windows/cells_<ENGINE>.json). No statistic is judged here."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wsim as w  # noqa: E402


def run(eng, cells_of, PL):
    base, cells = cells_of(PL)
    PR = w.real_panel(eng)
    sp = w.SPAN[eng]
    out = {"engine": eng, "span": sp, "cells": {}}
    ref = {}
    for cid, (fam, grid, tree, makers) in [("base", ("base", None, base, []))] + list(cells.items()):
        c = {"family": fam, "grid": grid}
        for key, P, lo, hi in (("long", PL, sp["M"][0], sp["R"][1]), ("real", PR, sp["A"][0], sp["A"][1])):
            r = w.simulate(tree, P, lo, hi, makers)
            if key in ref and r["days"] != ref[key]:
                raise RuntimeError(f"{cid}: not the base's sessions on {key}")
            ref.setdefault(key, r["days"])
            c[key] = {"ret": r["ret"], "to": r["turnover"]}
            if cid == "base":
                out[key + "_days"] = r["days"]
                c[key]["held"] = {d: {t: round(x, 4) for t, x in h.items()} for d, h in r["held"].items()}
        out["cells"][cid] = c
    return out


if __name__ == "__main__":
    os.makedirs(w.CACHE, exist_ok=True)
    PL = w.long_panel()
    for eng, f, n in (("HG", w.hg_cells, 89), ("SLEEVE", w.sleeve_cells, 45)):
        t0 = time.time()
        o = run(eng, f, PL)
        assert len(o["cells"]) - 1 == n, len(o["cells"])
        json.dump(o, open(f"{w.CACHE}/cells_{eng}.json", "w"))
        print(f"{eng}: {n} cells; long {len(o['long_days'])} sessions {o['long_days'][0]}..{o['long_days'][-1]}; real {len(o['real_days'])} "
              f"{o['real_days'][0]}..{o['real_days'][-1]}; {time.time() - t0:.0f}s", flush=True)
