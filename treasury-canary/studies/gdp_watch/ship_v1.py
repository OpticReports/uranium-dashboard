"""Ship the frozen study record to the backend: backend/app/sources/gdp_backtest_v1.json (the panel's bands, record
and caveat numbers) and backend/app/sources/gdp_snapshot.json.gz (the cold-start fallback). A gate test re-derives
the record from the study outputs and asserts equality.

    python3 -I ship_v1.py <study out dir> <snapshot.json.gz> <backend sources dir>
"""
from __future__ import annotations

import json
import os
import shutil
import sys

KEYS = ("as_of", "snapshot", "chosen", "first_origin", "window", "pandemic_targets_excluded", "pooled_ex_pandemic",
        "pooled_all", "by_country_ex_pandemic", "bands", "bands_pooled")


def record(out: str) -> dict:
    bt = json.load(open(os.path.join(out, "backtest_v1.json"), encoding="utf-8"))
    val = json.load(open(os.path.join(out, "validation_v1.json"), encoding="utf-8"))
    sens = json.load(open(os.path.join(out, "sensitivity_v1.json"), encoding="utf-8"))
    return {**{k: bt[k] for k in KEYS}, "coverage": val["coverage"], "coverage_split": val["split"],
            "recent_bias_h4_since_2023": val["recent_bias_h4_since_2023"], "sensitivity": sens}


if __name__ == "__main__":
    out, snap, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(os.path.join(dst, "gdp_backtest_v1.json"), "w", encoding="utf-8") as fh:
        json.dump(record(out), fh, indent=1, sort_keys=True)
    shutil.copyfile(snap, os.path.join(dst, "gdp_snapshot.json.gz"))
    print("shipped", os.path.join(dst, "gdp_backtest_v1.json"), os.path.join(dst, "gdp_snapshot.json.gz"))
