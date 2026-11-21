"""Sources for the forward-range study (PREREG.md): joint daily returns of HG, KMLM, SLEEVE and T-bills on
each scenario's sample, the one-close-late paths (cached; same construction as macro_2026-11/m6_robust.py),
and the S&P 500 for the beta scenario."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "macro_2026-11"))
import mdata as md  # noqa: E402

w = md.w
ks = w.ks
ENG = ("HG", "KMLM", "SLEEVE")
CACHE = w.kdata.SCRATCH + "/forward"
os.makedirs(CACHE, exist_ok=True)
SPAN = {"A": ("2021-06-02", "2026-11-19"), "B": ("2015-06-01", "2026-11-19"), "C": ("1994-06-02", "2026-11-19")}


def late_path(held, P, cached):
    """held[d] = weights after the trade at close d. One close late: held[d-1] earns d -> d+1; the day's
    cost is the study path's own (cached net less rebuilt gross)."""
    hd = sorted(held)
    late, gap = {}, []
    for i in range(len(hd) - 1):
        d, d1 = hd[i], hd[i + 1]
        h, hp = held[d], (held[hd[i - 1]] if i else held[d])
        same = sum(x * (P[t][d1] / P[t][d] - 1) for t, x in h.items())
        if d1 in cached:
            gap.append(abs(same - cached[d1]))
        if all(t in P and d in P[t] and d1 in P[t] for t in hp):
            late[d1] = sum(x * (P[t][d1] / P[t][d] - 1) for t, x in hp.items()) + ((cached[d1] - same) if d1 in cached else 0.0)
    return late, float(max(gap))


def late_engines():
    f = CACHE + "/late.json"
    if os.path.exists(f):
        return json.load(open(f))
    E = md.engines()
    PL = w.long_panel()
    out, gaps = {}, {}
    for eng in ("HG", "SLEEVE"):
        o = json.load(open(w.CACHE + f"/cells_{eng}.json"))
        b = o["cells"]["base"]
        out[eng] = {}
        for part, P, dl in (("long", PL, o["long_days"]), ("real", w.real_panel(eng), o["real_days"])):
            la, gaps[f"{eng}.{part}"] = late_path(b[part]["held"], P, dict(zip(dl, b[part]["ret"])))
            out[eng].update(la)
    import q1_cells as q1
    tree = ks.approved()
    Pab = dict(w.kdata.panel_ab(md.END), KMLM=w.sdata.fund_tr(md.END))
    out["KMLM"] = {}
    for part, P, a, b_ in (("long", PL, "1991-04-01", "2020-12-01"), ("real", Pab, q1.B_START, q1.END)):
        r = ks.simulate(tree, P, a, b_, flags=[q1.switch_flags(P)["F1a.rsi10"][0]])
        la, gaps[f"KMLM.{part}"] = late_path(r["held"], P, {d: E["KMLM"][d] for d in r["days"] if d in E["KMLM"]})
        out["KMLM"].update(la)
    out = {e: {d: v for d, v in out[e].items() if d in E[e]} for e in out}
    out["_max_gap_rebuilt_vs_cached"] = gaps
    json.dump(out, open(f, "w"))
    return out


def spy():
    PL, PRH = w.long_panel(), w.real_panel("HG")
    px = {**{d: v for d, v in PL["SPY"].items() if d <= "2015-08-31"}, **{d: v for d, v in PRH["SPY"].items() if d > "2015-08-31"}}
    ds = sorted(px)
    return {b: px[b] / px[a] - 1 for a, b in zip(ds, ds[1:])}


def source(span, late=False):
    """(days, R[n,3] engine returns, tb[n], spy[n]) on the sessions all series share"""
    E = md.engines()
    src = late_engines() if late else E
    sp = spy()
    lo, hi = span
    ds = [d for d in sorted(E["BOOK"]) if lo <= d <= hi and all(d in src[e] for e in ENG) and d in sp]
    return ds, np.array([[src[e][d] for e in ENG] for d in ds]), np.array([E["TBILL"][d] for d in ds]), np.array([sp[d] for d in ds])


if __name__ == "__main__":
    L = late_engines()
    print("late paths; rebuilt-vs-cached gaps", L["_max_gap_rebuilt_vs_cached"])
    for k, sp_ in SPAN.items():
        ds, R, tb, s = source(sp_)
        print(k, ds[0], ds[-1], len(ds), "growth/yr", [round(float(np.log1p(R[:, i]).mean() * 252), 3) for i in range(3)], "tb", round(float(tb.mean() * 252), 4), "spy", round(float(np.log1p(s).mean() * 252), 3))
    ds, R, tb, s = source(SPAN["B"], late=True)
    print("F", ds[0], ds[-1], len(ds), "growth/yr", [round(float(np.log1p(R[:, i]).mean() * 252), 3) for i in range(3)])
