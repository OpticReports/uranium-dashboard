"""GDP watch study v1, disclosed sensitivity (not a switch): the trend window, 40 quarters (frozen) vs 20.

Both run on the common origins 2016-Q4+ (pandemic targets excluded) so the comparison uses the same quarters.
The frozen choice stays at 40: 20 cuts China's 4-quarter error sharply but raises the pooled error.

    python3 -I sensitivity_v1.py <backtest_v1.py> <snapshot.json.gz> <out_dir>
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sys

spec = importlib.util.spec_from_file_location("bt", sys.argv[1])
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
snap = json.load(gzip.open(sys.argv[2], "rt", encoding="utf-8"))
res = {"common_origins_from": "2016-Q4", "windows": {}}
for w, mn in ((40, 20), (20, 12)):
    bt.WINDOW, bt.MIN_WINDOW = w, mn
    rows = [r for r in bt.errors(snap, snap["countries"]) if r["t"] >= "2016-Q4"]
    res["windows"][str(w)] = {
        "pooled_mae_A": [bt.summary(rows, "A", h, True)["mae"] for h in bt.H],
        "n_per_horizon": bt.summary(rows, "A", 1, True)["n"],
        "by_country_mae_A_h4": {c: bt.summary([r for r in rows if r["c"] == c], "A", 4, True).get("mae") for c in snap["countries"]}}
json.dump(res, open(os.path.join(sys.argv[3], "sensitivity_v1.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
print({w: v["pooled_mae_A"] for w, v in res["windows"].items()})
