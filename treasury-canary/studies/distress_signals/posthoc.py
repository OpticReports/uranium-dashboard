#!/usr/bin/env python3
"""POST-HOC, descriptive - not part of the pre-registered run (SPEC v1.1).

Checks the verifiers ran outside the pre-registered run, reproduced here from
the study's own code so the numbers quoted in distress-signals.md can be rerun.
The claims verifier found that Panel A's 1981-2000 state effect comes almost
entirely from 1981-90:

  1. each Panel A test fitted on 1981-90 and on 1991-2000 (the split-panel
     jackknife halves), with the primary inference (division wild-cluster
     bootstrap, seed 20261012, 9,999 draws);
  2. the pre-registered claims-control robustness window (1988-2000) WITHOUT
     the claims control (same cells), to separate the window effect from the
     control;
  3. Panel B's power against effects the size of the 1991-2000 estimates;
  4. Panel A without Vermont (its 1989 business/consumer split looks odd; the
     honesty box's data note).

    python3 posthoc.py      # -> posthoc.json

Nothing here feeds a grade or the dashboard's role labels.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

import study as S

HERE = os.path.dirname(os.path.abspath(__file__))


def claims_cells(pa, cache) -> np.ndarray:
    """The cells of the pre-registered claims robustness (study.q_r): usable,
    claims growth available, 1988-2000."""
    clw = cache.setdefault("claims_w", S.D.state_claims_weekly())
    cla = {s: S.claims_annual(v) for s, v in clw.items()}
    Cm = np.full(pa.g.shape, np.nan)
    for i, s in enumerate(pa.units):
        for j, y in enumerate(pa.years):
            if y in cla.get(s, {}) and y - 1 in cla.get(s, {}):
                Cm[i, j] = math.log(cla[s][y] / cla[s][y - 1])
    return pa.usable() & ~np.isnan(Cm) & (np.array(pa.years)[None, :] >= 1988)


def main():
    cache: dict = {}
    out: dict = {"note": "post-hoc decomposition, not pre-registered; see module docstring",
                 "seed": S.SEED, "draws": S.DRAWS, "panel_A": {}, "power_panelB_vs_1991_2000_beta": {}}
    for signal in ("S1", "S2"):
        for target in ("a", "b"):
            pa = S.build_panel_a(signal, target, cache)
            yrs = np.array(pa.years)[None, :]
            ok = pa.usable()
            divs = S.div_ids(pa.units)
            row = {}
            no_vt = ok & (np.array(pa.units) != "VT")[:, None]
            for name, cells in (("1981_1990", ok & (yrs <= 1990)), ("1991_2000", ok & (yrs >= 1991)),
                                ("claims_cells_1988_2000_no_claims_control", claims_cells(pa, cache)),
                                ("all_years_without_VT", no_vt)):
                m, u, _ = pa.fit(cells=cells)
                w = S.P.wild_cluster_bootstrap(m, divs[u], S.DRAWS, S.rng())
                row[name] = {"beta": m.beta, "p": w["p"], "n_obs": int(cells.sum())}
            out["panel_A"][f"{signal}/{target}"] = row
    for signal in ("S1", "S2"):
        for target in ("a", "b"):
            pb = S.build_panel_b(signal, target, cache)
            b = out["panel_A"][f"{signal}/{target}"]["1991_2000"]["beta"]
            out["power_panelB_vs_1991_2000_beta"][f"{signal}/{target}"] = {"beta_alt": b,
                                                                          "power": S.qr_power(pb, b)}
    with open(os.path.join(HERE, "posthoc.json"), "w") as f:
        json.dump(out, f, indent=1)
    for k, v in out["panel_A"].items():
        print(k, {n: (round(r["beta"], 4), r["p"]) for n, r in v.items()},
              "power vs 1990s:", out["power_panelB_vs_1991_2000_beta"][k]["power"])


if __name__ == "__main__":
    main()
