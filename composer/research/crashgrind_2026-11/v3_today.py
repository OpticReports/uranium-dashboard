"""The sleeve on UVXY and SVXY at TODAY's leverage (1.5 x and -0.5 x) all the way back to 2006, rebuilt
from the futures index up to the leverage change of 2018-02-28 (PREREG: reported beside the main run for
the episodes). Caches the path in the session scratchpad and writes out/today.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v2_engines as v2  # noqa: E402

v1, vd, md, w = v2.v1, v2.vd, v2.md, v2.w


def main():
    idx, _ = vd.index()
    tb = md.engines()["TBILL"]
    PL = w.long_panel()
    P = dict(PL)
    for nm in ("UVXY", "SVXY"):
        P[nm] = v2.swap(PL[nm], v1.synth(nm, idx, tb, today=True), v2.B0, "2018-02-27")
    r, _ = v2.run(w.approved("SLEEVE"), P, w.SPAN["SLEEVE"]["M"][0], "2023-01-31")
    json.dump(r, open(v2.CACHE + "/sleeve_today.json", "w"))
    yr = {y: float(np.log1p([v for d, v in r.items() if d[:4] == y]).sum()) for y in sorted({d[:4] for d in r}) if "2006" <= y <= "2020"}
    json.dump({"log_growth_by_year": yr}, open(os.path.join(HERE, "out", "today.json"), "w"), indent=1)
    print({y: round(v, 2) for y, v in yr.items()})


if __name__ == "__main__":
    main()
