"""GDP watch study v1, edge checks (CLAUDE.md "edge is the point"): two candidate edges the review raised, both
point in time, both null. Logged so the memo's numbers reproduce.

1. Bias correction. The rule ran high for China in 31 of 32 backtests. Would shifting every economy's line by the
   median of its own past misses (only misses whose target had printed by the origin, at least 8 of them) have
   cut the error? Mirror: the same shift with its sign flipped. Placebo: each economy shifted by another economy's
   past median miss (the economies rotated by one, alphabetically).
2. Trend gap. Does the gap between the 5-year and the 10-year trend at the origin predict the rule's miss four
   quarters on (Pearson correlation; a useful gap would let a reader lean against the line)?

Pandemic targets out, as in the scores.
    python3 -I edge_checks_v1.py <backtest_v1.py> <snapshot.json.gz> <out_dir>
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import os
import statistics
import sys

spec = importlib.util.spec_from_file_location("bt", sys.argv[1])
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
snap = json.load(gzip.open(sys.argv[2], "rt", encoding="utf-8"))
MIN_PAST = 8
codes = list(snap["countries"])
rows = [r for r in bt.errors(snap, codes) if not r["pandemic"]]


def corrected(rows: list[dict], h: int, source: dict[str, str], sign: float = 1.0) -> tuple[list[float], list[float], dict]:
    """|error| before and after shifting each line by the source economy's past median miss at horizon h."""
    by = {c: sorted((r for r in rows if r["c"] == c and r["h"] == h), key=lambda r: bt.qi(r["t"])) for c in codes}
    before, after, per = [], [], {}
    for c in codes:
        b_c, a_c = [], []
        for r in by[c]:
            t = bt.qi(r["t"])
            past = [p["A"] for p in by[source[c]] if bt.qi(p["target"]) <= t]
            if len(past) < MIN_PAST:
                continue
            shift = sign * statistics.median(past)            # error = actual - line, so line + shift has error - shift
            b_c.append(abs(r["A"]))
            a_c.append(abs(r["A"] - shift))
        before += b_c
        after += a_c
        if b_c:
            per[c] = {"n": len(b_c), "change_pct": round(100 * (sum(a_c) / sum(b_c) - 1), 1)}
    return before, after, per


out: dict = {"min_past_misses": MIN_PAST, "bias_correction": {}}
own = {c: c for c in codes}
rot = {c: sorted(codes)[(sorted(codes).index(c) + 1) % len(codes)] for c in codes}
for h in bt.H:
    res = {}
    for name, src, sign in (("own", own, 1.0), ("mirror", own, -1.0), ("placebo", rot, 1.0)):
        b, a, per = corrected(rows, h, src, sign)
        res[name] = {"n": len(b), "mae_before": round(statistics.fmean(b), 3), "mae_after": round(statistics.fmean(a), 3),
                     "change_pct": round(100 * (sum(a) / sum(b) - 1), 1)}
        if name == "own":
            res["own_by_country"] = per
            res["own_helped_in"] = sorted(c for c, v in per.items() if v["change_pct"] < 0)
    out["bias_correction"][str(h)] = res

# 2. trend gap at the origin vs the miss four quarters on
gaps = {}
for w, mn in ((40, 20), (20, 12)):
    bt.WINDOW, bt.MIN_WINDOW = w, mn
    for c in codes:
        q = snap["qoq"].get(c) or {}
        for r in (r for r in rows if r["c"] == c and r["h"] == 4):
            gaps.setdefault((c, r["t"]), {})[w] = bt.trend_phi(q, bt.qi(r["t"]))[0]
bt.WINDOW, bt.MIN_WINDOW = 40, 20
pairs = [(4 * (g[20] - g[40]), r["A"]) for r in rows if r["h"] == 4
         for g in [gaps.get((r["c"], r["t"]), {})] if g.get(20) is not None and g.get(40) is not None]
xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
out["trend_gap"] = {"n": len(pairs), "corr_gap_vs_miss_h4": round(statistics.correlation(xs, ys), 3),
                    "gap": "4 x (20-quarter median q/q - 40-quarter median q/q), points a year"}
json.dump(out, open(os.path.join(sys.argv[3], "edge_checks_v1.json"), "w", encoding="utf-8"), indent=1, sort_keys=True)
print({h: {k: v["change_pct"] for k, v in r.items() if isinstance(v, dict) and "change_pct" in v}
       for h, r in out["bias_correction"].items()}, out["trend_gap"])
print("own helped in (h4):", out["bias_correction"]["4"]["own_helped_in"], out["bias_correction"]["4"]["own_by_country"].get("CHN"))
