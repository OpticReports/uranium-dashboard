"""Chart series for the macro report: what the book earned while a state was on and while it was off,
cumulated through time. Writes out/charts.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m1_run as m1  # noqa: E402

out = {}
ds = sorted(m1.E["BOOK"])
ii = np.array([m1.pos[d] for d in ds])
lr = np.log1p(np.array([m1.E["BOOK"][d] for d in ds]))
for sid in ("T1", "F_GOLD", "F_LIQUIDITY", "F_CREDIT", "F_DOLLAR"):
    s = np.nan_to_num(m1.S[sid][ii])
    on, off = np.cumsum(lr * s), np.cumsum(lr * (1 - s))
    out[sid] = {"on": [[d, round(float(v), 4)] for d, v in list(zip(ds, on))[::5]], "off": [[d, round(float(v), 4)] for d, v in list(zip(ds, off))[::5]],
                "share_on": float(s.mean())}
json.dump(out, open(os.path.join(HERE, "out", "charts.json"), "w"))
print({k: (round(v["on"][-1][1], 2), round(v["off"][-1][1], 2), round(v["share_on"], 2)) for k, v in out.items()})
