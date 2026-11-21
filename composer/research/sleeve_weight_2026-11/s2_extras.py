"""Post hoc checks on the sleeve study (none is a pre-registered test): how concentrated each half's return
is, by era; E4 without its crisis months; the cost of InverseHold as an offset to Holy Grail. Writes
out/extras.json."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s1_sleeve as s1  # noqa: E402

w = s1.w
PL, PR = w.long_panel(), w.real_panel("SLEEVE")
tree = w.approved("SLEEVE")
paths = {"sleeve": s1.path(tree, PL, PR), "InverseHold": s1.path(s1.half(tree, "InverseHold"), PL, PR), "FrontrunBonds": s1.path(s1.half(tree, "FrontrunBonds"), PL, PR)}
out = {"concentration": {}, "E4_without": {}, "top_days": {}}
for nm, (r, held) in paths.items():
    out["concentration"][nm] = {}
    for e, lo, hi in s1.ERAS:
        ds = [d for d in sorted(r) if lo <= d <= hi]
        x = np.log1p(np.array([r[d] for d in ds]))
        tot = float(x.sum())
        o = np.argsort(x)
        act = np.array([any(t not in ("BOXX", "BIL") and v > 1e-9 for t, v in held[d].items()) for d in ds[:-1]] + [False])
        nxt = np.array([r[d] for d in ds])
        out["concentration"][nm][e] = {"total_log": tot, "best_10_days_log": float(x[o[-10:]].sum()), "worst_10_days_log": float(x[o[:10]].sum()),
                                       "without_best_10_per_yr": float((tot - x[o[-10:]].sum()) / (len(ds) / 252)), "positive_years": int(sum(sum(x[i] for i, d in enumerate(ds) if d[:4] == y) > 0 for y in sorted({d[:4] for d in ds}))),
                                       "years": len({d[:4] for d in ds})}
        if nm == "FrontrunBonds" and e in ("E4", "E5", "E6"):
            out["top_days"][e] = [[ds[i], round(float(np.expm1(x[i])), 3), {t: round(v, 2) for t, v in held[ds[i - 1]].items()}] for i in o[-6:][::-1]]
    ds = [d for d in sorted(r) if s1.ERAS[3][1] <= d <= s1.ERAS[3][2]]
    for label, drop in (("all of E4", ()), ("without 2018-02", ("2018-02",)), ("without 2020-02..04", ("2020-02", "2020-03", "2020-04")), ("without both", ("2018-02", "2020-02", "2020-03", "2020-04"))):
        x = np.array([r[d] for d in ds if d[:7] not in drop])
        st = s1.stat(x)
        out["E4_without"].setdefault(nm, {})[label] = {"cagr": st["cagr"], "maxdd": st["maxdd"], "sharpe": st["sharpe"], "sessions": len(x)}
out["growth"] = {}
for nm, (r, _) in paths.items():
    for label, lo in (("all", "1994-06-01"), ("from_2015", "2015-06-01")):
        lv, pts = 1.0, []
        for i, d in enumerate(d for d in sorted(r) if d >= lo):
            lv *= 1 + r[d]
            if i % 5 == 0:
                pts.append([d, round(lv, 4)])
        out["growth"].setdefault(label, {})[nm] = pts
json.dump(out, open(os.path.join(HERE, "out", "extras.json"), "w"), indent=1)
for nm, v in out["concentration"].items():
    for e, c in v.items():
        print(f"{nm:13s} {e} total log {c['total_log']:+.2f} best10 {c['best_10_days_log']:+.2f} worst10 {c['worst_10_days_log']:+.2f} without best 10: {c['without_best_10_per_yr']:+.2f}/yr; positive years {c['positive_years']}/{c['years']}")
for nm, v in out["E4_without"].items():
    print(nm, {k: (round(x["cagr"], 2), round(x["maxdd"], 2)) for k, x in v.items()})
for e, v in out["top_days"].items():
    print("FrontrunBonds best days", e, v)
