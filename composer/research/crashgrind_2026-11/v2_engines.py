"""Stage A bar A5 and Stage B (PREREG.md): the sleeve and Holy Grail re-simulated on the long panel with
UVXY, SVXY and VIXY rebuilt from the futures index. Writes out/engines.json and caches the new daily paths
(same close and one close late) in the session scratchpad."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for p in ("forward_2026-11", "sleeve_weight_2026-11"):
    sys.path.insert(0, os.path.join(HERE, "..", p))
import v1_fidelity as v1  # noqa: E402
import fdata as fd  # noqa: E402

vd, md = v1.vd, v1.md
w = md.w
CACHE = w.kdata.SCRATCH + "/crashgrind"
os.makedirs(CACHE, exist_ok=True)
B0 = "2006-01-03"                       # the rebuilt stretch starts here
LAUNCH = {"VIXY": "2011-01-04", "UVXY": "2011-10-04", "SVXY": "2011-10-04"}


def swap(px, synth, lo, hi):
    """the price series with its daily returns replaced by `synth` on (lo, hi]; anchored at its last price"""
    ds = sorted(px)
    r = {b: px[b] / px[a] - 1 for a, b in zip(ds, ds[1:])}
    for d in ds[1:]:
        if lo < d <= hi and d in synth:
            r[d] = synth[d]
    out, lvl = {ds[-1]: px[ds[-1]]}, px[ds[-1]]
    for a, b in zip(ds[-2::-1], ds[:0:-1]):
        lvl = lvl / (1 + r[b])
        out[a] = lvl
    return out


def panels():
    idx, _ = vd.index()
    tb = md.engines()["TBILL"]
    PL = w.long_panel()
    S = {nm: v1.synth(nm, idx, tb) for nm in LAUNCH}
    P_b = dict(PL)                       # Stage B: rebuilt from 2006-01 to launch
    for nm, la in LAUNCH.items():
        P_b[nm] = swap(PL[nm], S[nm], B0, la)
    P_a = dict(PL)                       # bar A5: rebuilt in place of the real funds on the overlap
    for nm in ("UVXY", "SVXY"):
        P_a[nm] = swap(PL[nm], S[nm], "2011-10-31", "2020-11-30")
    return PL, P_a, P_b


def run(tree, P, lo, hi):
    r = w.simulate(tree, P, lo, hi)
    return dict(zip(r["days"], r["ret"])), r["held"]


def same_holdings(h1, h2, ds):
    f = lambda h: tuple(sorted(t for t, v in h.items() if v > 1e-9))          # noqa: E731
    return float(np.mean([f(h1[d]) == f(h2[d]) for d in ds if d in h1 and d in h2]))


def main():
    PL, P_a, P_b = panels()
    out = {}
    sl, hg = w.approved("SLEEVE"), w.approved("HG")
    # ---- A5
    lo, hi = "2011-11-01", "2020-11-30"
    r0, h0 = run(sl, PL, lo, hi)
    r1, h1 = run(sl, P_a, lo, hi)
    ds = sorted(set(r0) & set(r1))
    g0, g1 = float(np.log1p([r0[d] for d in ds]).sum()), float(np.log1p([r1[d] for d in ds]).sum())
    out["A5"] = {"from": ds[0], "to": ds[-1], "n": len(ds), "same_holdings": same_holdings(h0, h1, ds), "log_growth_real_funds": g0, "log_growth_rebuilt_funds": g1, "ratio": g1 / g0,
                 "daily_corr": float(np.corrcoef([r0[d] for d in ds], [r1[d] for d in ds])[0, 1]),
                 "by_year": {y: [float(np.log1p([r0[d] for d in ds if d[:4] == y]).sum()), float(np.log1p([r1[d] for d in ds if d[:4] == y]).sum())] for y in sorted({d[:4] for d in ds})}}
    out["A5"]["pass"] = out["A5"]["same_holdings"] >= 0.95 and 0.9 <= out["A5"]["ratio"] <= 1.1
    print("A5", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out["A5"].items() if k != "by_year"})
    print("A5 by year (real, rebuilt)", {y: [round(a, 2), round(b, 2)] for y, (a, b) in out["A5"]["by_year"].items()})
    # ---- Stage B
    new, held = {}, {}
    for eng, tree, lo, hi in (("SLEEVE", sl, w.SPAN["SLEEVE"]["M"][0], "2023-01-31"), ("HG", hg, w.SPAN["HG"]["M"][0], w.SPAN["HG"]["R"][1])):
        r, h = run(tree, P_b, lo, hi)
        old = md.engines()[eng]
        dd = [d for d in sorted(r) if d in old]
        new[eng], held[eng] = r, h
        late, gap = fd.late_path(h, P_b, r)
        new[eng + ".late"] = late
        diff = [d for d in dd if abs(r[d] - old[d]) > 1e-9]
        yr = {}
        for y in range(2005, 2013):
            m = [d for d in dd if d[:4] == str(y)]
            if m:
                yr[str(y)] = [float(np.log1p([old[d] for d in m]).sum()), float(np.log1p([r[d] for d in m]).sum())]
        out[eng] = {"sessions": len(dd), "sessions_changed": len(diff), "first_changed": diff[0] if diff else None, "last_changed": diff[-1] if diff else None, "log_growth_by_year_old_new": yr,
                    "late_rebuild_gap": gap}
        print(eng, "changed", len(diff), diff[:1], diff[-1:], "by year old/new", {y: [round(a, 2), round(b, 2)] for y, (a, b) in yr.items()})
    # the ladder half alone on the rebuilt stretch
    import s1_sleeve as s1
    for half in ("FrontrunBonds", "InverseHold"):
        t = s1.half(sl, half)
        r, _ = run(t, P_b, B0, "2011-10-31")
        ro, _ = run(t, PL, B0, "2011-10-31")
        out[half] = {"log_growth_2006_2011_old": float(np.log1p(list(ro.values())).sum()), "log_growth_2006_2011_new": float(np.log1p(list(r.values())).sum()),
                     "by_year_new": {y: float(np.log1p([v for d, v in r.items() if d[:4] == y]).sum()) for y in sorted({d[:4] for d in r})}}
        print(half, {k: (round(v, 3) if isinstance(v, float) else {a: round(b, 2) for a, b in v.items()}) for k, v in out[half].items()})
    json.dump({k: v for k, v in new.items()}, open(CACHE + "/engines_new.json", "w"))
    json.dump(out, open(os.path.join(HERE, "out", "engines.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
