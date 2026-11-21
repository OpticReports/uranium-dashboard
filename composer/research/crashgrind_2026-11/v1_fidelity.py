"""Stage A fidelity (PREREG.md bars A1-A4): the funds rebuilt from the futures index against the real funds'
adjusted closes on every session both exist, and the existing regression model on the same bars.
Writes out/fidelity.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vdata as vd  # noqa: E402

md = vd.md
w = md.w
FEE = {"VIXY": 0.0085, "UVXY": 0.0095, "SVXY": 0.0095}
CUT = "2018-02-28"                      # first session at the new leverage
LEV = {"VIXY": (1.0, 1.0), "UVXY": (2.0, 1.5), "SVXY": (-1.0, -0.5)}


def synth(name, idx, tb, today=False):
    """{day: daily return} of the fund rebuilt from the index; today=True uses today's leverage throughout"""
    a, b = LEV[name]
    return {d: (b if (today or d >= CUT) else a) * r + tb.get(d, 0.0) - FEE[name] / 252 for d, r in idx.items()}


def real(name):
    px = w.kdata.series(name, md.END)
    ds = sorted(px)
    return {b: px[b] / px[a] - 1 for a, b in zip(ds, ds[1:])}


def model(name):
    """the existing regression model's own curve (not spliced onto the real fund)"""
    sys.path.insert(0, os.path.join(HERE, "..", "crash"))
    import hist_replay as hr
    cur, _ = hr.vix_etp(name)
    ds = sorted(cur)
    return {b: cur[b] / cur[a] - 1 for a, b in zip(ds, ds[1:])}


def bars(s, r):
    ds = sorted(set(s) & set(r))
    a, b = np.array([s[d] for d in ds]), np.array([r[d] for d in ds])
    yrs = sorted({d[:4] for d in ds})
    by = {y: float((np.log1p(a) - np.log1p(b))[[d[:4] == y for d in ds]].sum()) for y in yrs}
    full = {y: sum(d[:4] == y for d in ds) > 200 for y in yrs}
    top = np.argsort(-np.abs(b))[:20]
    ratio = a[top] / b[top]
    return {"from": ds[0], "to": ds[-1], "n": len(ds), "corr": float(np.corrcoef(a, b)[0, 1]), "log_gap_per_yr": float((np.log1p(a) - np.log1p(b)).mean() * 252),
            "worst_year_gap": max(((y, v) for y, v in by.items() if full[y]), key=lambda z: abs(z[1])), "by_year": by,
            "top20_within": int(((ratio >= 0.8) & (ratio <= 1.25)).sum()), "top20": [[ds[i], round(float(b[i]), 4), round(float(a[i]), 4)] for i in top],
            "beta": float(np.cov(b, a)[0, 1] / a.var(ddof=1))}


def main():
    idx, det = vd.index()
    E = md.engines()
    tb = E["TBILL"]
    out = {"index": {"from": min(idx), "to": max(idx), "n": len(idx)}, "synthetic": {}, "model": {}}
    for nm in ("VIXY", "UVXY", "SVXY"):
        r = real(nm)
        out["synthetic"][nm] = bars(synth(nm, idx, tb), r)
        try:
            out["model"][nm] = bars(model(nm), r)
        except Exception as e:                                                 # the old model has no curve for this fund
            out["model"][nm] = {"error": str(e)[:120]}
    v = out["synthetic"]
    out["bars"] = {"A1": v["VIXY"]["corr"] >= 0.98, "A2": abs(v["VIXY"]["log_gap_per_yr"]) <= 0.03 and abs(v["VIXY"]["worst_year_gap"][1]) <= 0.06,
                   "A3": all(v[n]["corr"] >= 0.97 and abs(v[n]["log_gap_per_yr"]) <= 0.08 for n in ("UVXY", "SVXY")), "A4": v["VIXY"]["top20_within"] >= 17}
    json.dump(out, open(os.path.join(HERE, "out", "fidelity.json"), "w"), indent=1)
    for k in ("synthetic", "model"):
        for nm, x in out[k].items():
            if "error" in x:
                print(k, nm, x)
                continue
            print(f"{k:9s} {nm} {x['from']}..{x['to']} n {x['n']} corr {x['corr']:.4f} beta {x['beta']:.3f} gap/yr {x['log_gap_per_yr']:+.4f} worst yr {x['worst_year_gap'][0]} {x['worst_year_gap'][1]:+.3f} top20 within {x['top20_within']}")
    print("bars", out["bars"])
    print("VIXY by year", {y: round(g, 3) for y, g in v["VIXY"]["by_year"].items()})
    print("VIXY top moves (date, real, synth)", v["VIXY"]["top20"][:8])


if __name__ == "__main__":
    main()
