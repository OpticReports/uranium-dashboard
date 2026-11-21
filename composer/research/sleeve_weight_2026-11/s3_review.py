"""Checks required by the independent review (post hoc): 2015-2020 without its crisis months against the
real years' interval; each half as the third leg; the ladder alone against the live sleeve; the test at
other weights; single days that carry a stretch; how often the ladder's rarest tests have ever been true.
Writes out/review.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s1_sleeve as s1  # noqa: E402

w, stat, boot_idx = s1.w, s1.stat, s1.boot_idx
rng = np.random.default_rng(20261126)
PL, PR = w.long_panel(), w.real_panel("SLEEVE")
tree = w.approved("SLEEVE")
P_ = {"sleeve": s1.path(tree, PL, PR)[0], "ladder": s1.path(s1.half(tree, "FrontrunBonds"), PL, PR)[0], "inverse": s1.path(s1.half(tree, "InverseHold"), PL, PR)[0]}
hg = json.load(open(w.CACHE + "/cells_HG.json"))
HG = {**dict(zip(hg["long_days"], hg["cells"]["base"]["long"]["ret"])), **dict(zip(hg["real_days"], hg["cells"]["base"]["real"]["ret"]))}
kl, kr = json.load(open(s1.KS + "/cells_long.json")), json.load(open(s1.KS + "/cells_real_tr.json"))
KM = {**dict(zip(kl["days"], kl["cells"]["base"]["ret"])), **dict(zip(kr["days"], kr["cells"]["base"]["ret"]))}
bil = {}
for P, lo, hi in ((PL, "0", "2023-01-31"), (PR, "2023-02-01", "9")):
    b = P.get("BIL") or w.kdata.series("BIL", w.END)
    bd = sorted(b)
    bil.update({d1: b[d1] / b[d0] - 1 for d0, d1 in zip(bd, bd[1:]) if lo <= d1 <= hi})
common = sorted(set(P_["sleeve"]) & set(HG) & set(KM) & set(bil))
out = {}


def ci(x):
    lx = np.log1p(np.array(x))
    bs = [lx[boot_idx(len(lx), rng)].mean() * 252 for _ in range(2000)]
    return [float(lx.mean() * 252), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))]


r = P_["sleeve"]
e4 = [d for d in sorted(r) if "2015-06-01" <= d <= "2020-12-01"]
out["e4_log_per_yr"] = {"all": ci([r[d] for d in e4]), "without_2020_02_to_04": ci([r[d] for d in e4 if d[:7] not in ("2020-02", "2020-03", "2020-04")]),
                        "real_years_from_2020_12": ci([r[d] for d in sorted(r) if d >= "2020-12-02"])}
out["single_days"] = {}
for label, lo, hi, drop in (("2023-02 on without 2024-08-05", "2023-02-01", "9", "2024-08-05"), ("2011-11 to 2015-05 without 2011-11-01", "2011-11-01", "2015-05-31", "2011-11-01")):
    for nm in ("sleeve", "ladder"):
        ds = [d for d in sorted(P_[nm]) if lo <= d <= hi]
        out["single_days"].setdefault(label, {})[nm] = {"with": stat(np.array([P_[nm][d] for d in ds]))["cagr"], "without": stat(np.array([P_[nm][d] for d in ds if d != drop]))["cagr"], "that_day": P_[nm].get(drop)}
dd = lambda x: float(np.max(1 - np.cumprod(1 + x) / np.maximum.accumulate(np.cumprod(1 + x))))   # noqa: E731


def versus(a, b):
    d = np.log1p(a) - np.log1p(b)
    g = [d[boot_idx(len(d), rng)].mean() * 252 for _ in range(2000)]
    return {"dlog_per_yr": float(d.mean() * 252), "ci90": [float(np.quantile(g, 0.05)), float(np.quantile(g, 0.95))], "d_maxdd": dd(a) - dd(b)}


out["third_leg"] = {}
for e, lo, hi in (("2011-11 to 2015-05", "2011-11-01", "2015-05-31"), ("2015-06 to 2020-12", "2015-06-01", "2020-12-01"), ("2021-06 to 2026-11", "2021-06-02", "2026-11-19")):
    ds = [d for d in common if lo <= d <= hi]
    H, K, C = (np.array([x[d] for d in ds]) for x in (HG, KM, bil))
    L = {nm: np.array([P_[nm][d] for d in ds]) for nm in P_}
    book = lambda third, wt=0.318: (1 - wt) / 2 * (H + K) + wt * third   # noqa: E731
    row = {nm + "_vs_tbills": versus(book(L[nm]), book(C)) for nm in P_}
    row["ladder_alone_vs_live_sleeve"] = versus(book(L["ladder"]), book(L["sleeve"]))
    row["sleeve_vs_tbills_at_10pct"] = versus(book(L["sleeve"], 0.10), book(C, 0.10))
    row["sleeve_vs_tbills_at_50pct"] = versus(book(L["sleeve"], 0.50), book(C, 0.50))
    row["book_stats"] = {nm: {k: stat(book(L[nm]))[k] for k in ("cagr", "maxdd", "sharpe")} for nm in P_}
    row["book_stats"]["tbills"] = {k: stat(book(C))[k] for k in ("cagr", "maxdd", "sharpe")}
    out["third_leg"][e] = row
# how often the ladder's rarest one-day tests have ever been true (real TLT from 2002-07; the proxy before)
tlt = {**{d: v for d, v in PL["TLT"].items() if d <= "2023-01-31"}, **{d: v for d, v in PR["TLT"].items() if d > "2023-01-31"}}
td = sorted(tlt)
tr = {b: tlt[b] / tlt[a] - 1 for a, b in zip(td, td[1:]) if b >= "1994-06-01"}
out["rare_tests"] = {"TLT_1d_above_6pct": sorted(d for d, v in tr.items() if v > 0.06), "TLT_1d_below_minus_3.5pct": sorted(d for d, v in tr.items() if v < -0.035), "sessions": len(tr)}
json.dump(out, open(os.path.join(HERE, "out", "review.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "third_leg"}, indent=0)[:1500])
for e, v in out["third_leg"].items():
    print(e, {k: (round(x["dlog_per_yr"], 3), [round(c, 3) for c in x["ci90"]], round(x["d_maxdd"] * 100, 1)) for k, x in v.items() if k != "book_stats"})
    print("   books", {k: (round(x["cagr"], 2), round(x["maxdd"], 3), round(x["sharpe"], 2)) for k, x in v["book_stats"].items()})
