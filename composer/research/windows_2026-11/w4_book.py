"""The book (PREREG.md "The book"): daily-fixed 34.1 / 34.1 / 31.8 of HG / KMLM / SLEEVE on the days all
three have a simulated return; each variant swapped into its engine; the sleeve's pay on the worst days of
the other two; the live engines' drawdowns per stretch. Writes out/book.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wsim as w  # noqa: E402
from q2_stats import boot_idx, stat  # noqa: E402

WT = {"HG": 0.341, "KMLM": 0.341, "SLEEVE": 0.318}
SPLIT = ("2021-06-01", "2023-02-01")            # book: rebuilt years (shape only) | KMLM and HG real, sleeve part rebuilt | all three real
KS = w.kdata.SCRATCH + "/kmlm_synth"


def by_day(o, c):
    out = dict(zip(o["long_days"], o["cells"][c]["long"]["ret"]))
    out.update(zip(o["real_days"], o["cells"][c]["real"]["ret"]))
    return out


def dd_info(ds, r):
    lvl = np.cumprod(1 + np.array(r))
    dd = 1 - lvl / np.maximum.accumulate(lvl)
    j = int(np.argmax(dd))
    i = int(np.argmax(lvl[:j + 1]))
    rec = next((ds[k] for k in range(j, len(ds)) if lvl[k] >= lvl[i]), None)
    return {"maxdd": float(dd[j]), "peak": ds[i], "trough": ds[j], "recovered": rec, "share_below_20pct": float((dd > 0.20).mean()),
            "path": [[d, round(float(-x), 4)] for d, x in list(zip(ds, dd))[::5]]}


def main():
    eng = {e: json.load(open(f"{w.CACHE}/cells_{e}.json")) for e in ("HG", "SLEEVE")}
    st = {e: json.load(open(os.path.join(HERE, "out", f"stats_{e}.json"))) for e in ("HG", "SLEEVE")}
    kl, kr = json.load(open(KS + "/cells_long.json")), json.load(open(KS + "/cells_real_tr.json"))
    kcell = lambda c: {**dict(zip(kl["days"], kl["cells"][c]["ret"])), **dict(zip(kr["days"], kr["cells"][c]["ret"]))}   # noqa: E731
    live = {"HG": by_day(eng["HG"], "base"), "SLEEVE": by_day(eng["SLEEVE"], "base"), "KMLM": kcell("base")}
    days = sorted(set(live["HG"]) & set(live["SLEEVE"]) & set(live["KMLM"]))
    part = lambda d: "M" if d < SPLIT[0] else "R" if d < SPLIT[1] else "A"   # noqa: E731
    idx = {k: np.array([i for i, d in enumerate(days) if part(d) == k]) for k in "MRA"}
    L = {e: np.array([live[e][d] for d in days]) for e in WT}
    book = sum(WT[e] * L[e] for e in WT)
    out = {"weights": WT, "days": [days[0], days[-1], len(days)], "spans": {k: [days[v[0]], days[v[-1]], len(v)] for k, v in idx.items()},
           "live": {k: stat(book[v]) for k, v in idx.items()}, "engines": {e: {k: stat(L[e][v]) for k, v in idx.items()} for e in WT},
           "corr": {k: {f"{a}-{b}": float(np.corrcoef(L[a][v], L[b][v])[0, 1]) for a, b in (("HG", "KMLM"), ("HG", "SLEEVE"), ("KMLM", "SLEEVE"))} for k, v in idx.items()},
           "swaps": {}, "sleeve_on_bad_days": {}}
    ver = np.concatenate([idx["R"], idx["A"]])
    rng = np.random.default_rng(20261123)

    def swap(e, r, ci=False):
        alt = book + WT[e] * (r - L[e])
        d = np.log1p(alt) - np.log1p(book)
        res = {k: {"d_return_per_yr": float(stat(alt[v])["cagr"] - stat(book[v])["cagr"]), "d_maxdd": float(stat(alt[v])["maxdd"] - stat(book[v])["maxdd"]),
                   "dlog_per_yr": float(d[v].mean() * 252)} for k, v in idx.items()}
        dj = d[ver]
        res["joined"] = {"dlog_per_yr": float(dj.mean() * 252), "t": float(dj.mean() / (dj.std(ddof=1) / math.sqrt(len(dj)))) if dj.std() > 0 else 0.0,
                         "d_maxdd_R": res["R"]["d_maxdd"], "d_maxdd_A": res["A"]["d_maxdd"]}
        if ci:
            bs = np.array([dj[boot_idx(len(dj), rng)].mean() * 252 for _ in range(2000)])
            res["joined"]["ci90"] = [float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))]
        return res
    for e in ("HG", "SLEEVE"):
        cells = [c for c in eng[e]["cells"] if c != "base" and not st[e]["cells"][c]["same_as_live"]]
        res = {c: swap(e, np.array([by_day(eng[e], c)[d] for d in days]), ci=(c == st[e]["best_by_t"])) for c in cells}
        fams = sorted({st[e]["cells"][c]["grid"] for c in cells})
        out["swaps"][e] = {"best_by_t": st[e]["best_by_t"], "cells": res,
                           "families": {g: {"n": len(cs), "mean_dlog_per_yr": float(np.mean([res[c]["joined"]["dlog_per_yr"] for c in cs])),
                                            "min": float(min(res[c]["joined"]["dlog_per_yr"] for c in cs)), "max": float(max(res[c]["joined"]["dlog_per_yr"] for c in cs)),
                                            "mean_d_maxdd_R": float(np.mean([res[c]["R"]["d_maxdd"] for c in cs])), "ahead": int(sum(res[c]["joined"]["dlog_per_yr"] > 0 for c in cs))}
                                        for g in fams for cs in [[c for c in cells if st[e]["cells"][c]["grid"] == g]]},
                           "best_book": max(cells, key=lambda c: res[c]["joined"]["t"])}
    kbest = "F1b.rsi12"
    out["swaps"]["KMLM"] = {"best_by_t": kbest, "cells": {kbest: swap("KMLM", np.array([kcell(kbest)[d] for d in days]), ci=True)}}
    # the sleeve as a hedge: its mean return on the worst 5% of days of HG and KMLM together (REPLICATION + REAL)
    other = (0.5 * L["HG"] + 0.5 * L["KMLM"])[ver]
    bad = other <= np.quantile(other, 0.05)
    sl = L["SLEEVE"][ver]
    out["sleeve_on_bad_days"] = {"days": int(bad.sum()), "others_mean": float(other[bad].mean()), "live_sleeve_mean": float(sl[bad].mean()), "live_sleeve_all_days_mean": float(sl.mean()),
                                 "live_sleeve_positive_share": float((sl[bad] > 0).mean()), "cells": {}}
    for c in out["swaps"]["SLEEVE"]["cells"]:
        r = np.array([by_day(eng["SLEEVE"], c)[d] for d in days])[ver]
        out["sleeve_on_bad_days"]["cells"][c] = float(r[bad].mean() - sl[bad].mean())
    # next 5 and 20 sessions after a bad day (add. 54.3: the sleeve pays in the sessions after)
    pos = np.flatnonzero(bad)
    for h in (5, 20):
        f = [np.prod(1 + sl[i + 1:i + 1 + h]) - 1 for i in pos if i + h < len(sl)]
        g = [np.prod(1 + other[i + 1:i + 1 + h]) - 1 for i in pos if i + h < len(sl)]
        out["sleeve_on_bad_days"][f"next_{h}_sessions"] = {"sleeve": float(np.mean(f)), "others": float(np.mean(g))}
    # live drawdowns per engine and stretch, on each engine's own stretches
    out["drawdowns"] = {}
    for e in ("HG", "SLEEVE"):
        s = st[e]["spans"]
        b = by_day(eng[e], "base")
        ds = sorted(b)
        out["drawdowns"][e] = {k: dd_info([d for d in ds if lo <= d <= hi], [b[d] for d in ds if lo <= d <= hi]) for k, (lo, hi, _) in s.items()}
        lv, pts = 1.0, []
        for i, d in enumerate(ds):
            lv *= 1 + b[d]
            if i % 5 == 0:
                pts.append([d, round(lv, 4)])
        out["drawdowns"][e]["growth"] = pts
    out["drawdowns"]["BOOK"] = {k: dd_info([days[i] for i in v], book[v]) for k, v in idx.items()}
    lv, pts = 1.0, []
    for i, d in enumerate(days):
        lv *= 1 + book[i]
        if i % 5 == 0:
            pts.append([d, round(lv, 4)])
    out["drawdowns"]["BOOK"]["growth"] = pts
    json.dump(out, open(os.path.join(HERE, "out", "book.json"), "w"))
    print("book days", out["days"], out["spans"])
    for k in "MRA":
        print(k, "book", {x: round(y, 3) for x, y in out["live"][k].items() if x in ("cagr", "maxdd", "sharpe")}, "| corr", {a: round(b, 2) for a, b in out["corr"][k].items()},
              "|", {e: (round(out["engines"][e][k]["cagr"], 3), round(out["engines"][e][k]["maxdd"], 3)) for e in WT})
    for e in ("HG", "SLEEVE", "KMLM"):
        s = out["swaps"][e]
        b = s["cells"][s["best_by_t"]]
        print(e, "best-by-t", s["best_by_t"], {k: (round(v, 4) if isinstance(v, float) else [round(x, 4) for x in v]) for k, v in b["joined"].items()},
              {k: (round(b[k]["d_return_per_yr"], 4), round(b[k]["d_maxdd"], 4)) for k in "MRA"})
        if "families" in s:
            print("   best at book level:", s["best_book"], {k: round(v, 4) for k, v in s["cells"][s["best_book"]]["joined"].items() if isinstance(v, float)})
            for g, v in s["families"].items():
                print("   ", g, {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
    sb = out["sleeve_on_bad_days"]
    print("sleeve on bad days", {k: v for k, v in sb.items() if k != "cells"})
    print("   variants better than live on bad days:", sorted(((round(v * 1e4, 1), c) for c, v in sb["cells"].items()), reverse=True)[:6])
    for e in ("HG", "SLEEVE", "BOOK"):
        print(e, {k: {x: (round(y, 3) if isinstance(y, float) else y) for x, y in v.items() if x != "path"} for k, v in out["drawdowns"][e].items() if k != "growth"})


if __name__ == "__main__":
    main()
