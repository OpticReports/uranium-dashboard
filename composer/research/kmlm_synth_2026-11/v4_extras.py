"""Diagnostics and chart series for the report (all computed AFTER the bars were scored; none is a bar):
why F1 misses on the whole overlap, the live rule's drawdowns on each stretch, how the old stand-in's
switch compares with the synthetic's, the test's power. Writes out/extras.json."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K57 = os.path.join(HERE, "..", "kmlm_2026-11")
sys.path.insert(0, HERE)
sys.path.insert(0, K57)
import data as kdata  # noqa: E402
import ksim as ks  # noqa: E402
import ksynth as ky  # noqa: E402
import sdata  # noqa: E402

V0, V1 = "2021-03-01", "2024-03-28"
out = {}
exposure = json.load(open(os.path.join(HERE, "out", "fidelity.json")))["exposure"]
syn = ky.build(exposure, start="2000-01-01")
fund = sdata.fund_tr(V1)
fr = kdata.rets(fund)
days = [d for d in sorted(fr) if V0 <= d <= V1 and d in syn]
a, b = np.array([syn[d] for d in days]), np.array([fr[d] for d in days])
c = lambda x, y: float(np.corrcoef(x, y)[0, 1])  # noqa: E731


def kday(x, k):
    lx = np.log1p(x)
    return np.array([lx[i:i + k].sum() for i in range(0, len(lx) - k + 1, k)])


out["f1_diagnostics"] = {
    "by_year": {y: {"n": int(sum(d[:4] == y for d in days)), "corr": c(a[[d[:4] == y for d in days]], b[[d[:4] == y for d in days]])} for y in ("2021", "2022", "2023", "2024")},
    "from_2022-04-01": c(a[[d >= "2022-04-01" for d in days]], b[[d >= "2022-04-01" for d in days]]),
    "before_2022-04-01": c(a[[d < "2022-04-01" for d in days]], b[[d < "2022-04-01" for d in days]]),
    "two_session_returns": c(kday(a, 2), kday(b, 2)), "five_session_returns": c(kday(a, 5), kday(b, 5)),
    "synthetic_one_day_late": c(a[:-1], b[1:]), "synthetic_one_day_early": c(a[1:], b[:-1])}
# chart series: fund, synthetic, old stand-in on the overlap; index vs synthetic before the fund
rym = kdata.rets(kdata.series("RYMFX", V1))
lv = {"fund": 1.0, "synthetic": 1.0, "rymfx": 1.0}
pts = {k: [] for k in lv}
for i, d in enumerate(days):
    lv["fund"] *= 1 + fr[d]
    lv["synthetic"] *= 1 + syn[d]
    lv["rymfx"] *= 1 + rym.get(d, 0.0)
    if i % 3 == 0 or i == len(days) - 1:
        for k in lv:
            pts[k].append([d, round(lv[k], 4)])
out["overlap_levels"] = pts
ix = sdata.index_monthly()
sm = ky.monthly({d: r + ky.COSTS / 252 for d, r in syn.items()})
li = ls = 1.0
out["index_levels"] = {"index": [], "synthetic": []}
for m in sorted(sm):
    if "2008-03" <= m <= "2020-11" and m in ix:
        li *= 1 + ix[m]
        ls *= 1 + sm[m]
        out["index_levels"]["index"].append([m + "-28", round(li, 4)])
        out["index_levels"]["synthetic"].append([m + "-28", round(ls, 4)])
# the live rule's drawdowns per stretch
lr = json.load(open(sdata.CACHE + "/cells_long.json"))
re_ = json.load(open(sdata.CACHE + "/cells_real_tr.json"))


def dd_info(ds, r):
    lvl = np.cumprod(1 + np.array(r))
    pk = np.maximum.accumulate(lvl)
    dd = 1 - lvl / pk
    j = int(np.argmax(dd))
    i = int(np.argmax(lvl[:j + 1]))
    rec = next((ds[k] for k in range(j, len(ds)) if lvl[k] >= lvl[i]), None)
    return {"maxdd": float(dd[j]), "peak": ds[i], "trough": ds[j], "recovered": rec,
            "sessions_below_30pct": int((dd > 0.30).sum()), "share_below_30pct": float((dd > 0.30).mean()),
            "path": [[d, round(float(-x), 4)] for d, x in list(zip(ds, dd))[::5]]}


idx = {k: [i for i, d in enumerate(lr["days"]) if lo <= d <= hi] for k, (lo, hi) in {"M": ("0", "2008-01-31"), "R": ("2008-02-01", "9")}.items()}
out["live_drawdown"] = {k: dd_info([lr["days"][i] for i in v], [lr["cells"]["base"]["ret"][i] for i in v]) for k, v in idx.items()}
out["live_drawdown"]["A"] = dd_info(re_["days"], re_["cells"]["base"]["ret"])
worst = sorted(zip(lr["cells"]["base"]["ret"], lr["days"]))[:8]
out["live_worst_days_long"] = [[d, r] for r, d in worst]
# the old stand-in's switch against the synthetic's, before the fund
sys.path.insert(0, os.path.join(HERE, "..", "longrun"))
import long_panel as lp  # noqa: E402
P, _ = lp.build_long_prices()
old = P["KMLM"]
ky.set_calendar([d for d in P["SPY"] if d <= V1])
synl = ky.level(ky.build(exposure, start="1986-01-01"))
ra = ks.rsi_series(P["XLK"], 10)
ro, rs = ks.rsi_series(old, 10), ks.rsi_series(synl, 10)
out["old_standin_flag_agreement"] = {}
for name, lo, hi in (("2007-09..2020-12 (RYMFX)", "2007-09-04", "2020-12-01"), ("1991-04..2007-08 (trend proxy)", "1991-04-01", "2007-08-31")):
    dd = [d for d in sorted(synl) if lo <= d <= hi and all(x.get(d) is not None for x in (ra, ro, rs))]
    out["old_standin_flag_agreement"][name] = {"sessions": len(dd), "agreement": sum((ra[d] > ro[d]) == (ra[d] > rs[d]) for d in dd) / len(dd),
                                               "risk_on_share_synthetic": sum(ra[d] > rs[d] for d in dd) / len(dd)}
g, info = ky.build(exposure, start="1991-01-01", detail=True)
out["markets_by_year"] = {y: next(v for d, v in sorted(info.items()) if d[:4] == y) for y in ("1991", "1995", "2000", "2002", "2004", "2007", "2008", "2009")}
# power
L = json.load(open(os.path.join(HERE, "out", "long.json")))
old_rb = json.load(open(os.path.join(K57, "out", "robust.json")))
live = [k for k, v in L["cells"].items() if v["is_live_rule"]]
m_new = sorted(v["joined"]["mde50"] for k, v in L["cells"].items() if not v["is_live_rule"])
m_old = sorted(old_rb["power"][k]["mde50"] for k in L["cells"] if k in old_rb["power"] and k not in live)
out["power"] = {"median_mde50": {"real_only_addendum_57": m_old[len(m_old) // 2], "long": m_new[len(m_new) // 2]},
                "cells": {k: {"real_only": old_rb["power"][k]["mde50"], "long": L["cells"][k]["joined"]["mde50"]} for k in ("F1a.rsi11", "F1b.rsi12", "F1a.rsi14", "F1a.rsi20", "F5.ema50")},
                "critical_t": {"real_only": old_rb["critical_t_90"], "long": L["critical_t_90"]}}
st57 = json.load(open(os.path.join(K57, "out", "stats.json")))
out["addendum_57_standin_live"] = st57["tier_c"]["base"]
json.dump(out, open(os.path.join(HERE, "out", "extras.json"), "w"), indent=1)
show = {k: v for k, v in out.items() if k not in ("overlap_levels", "index_levels")}
for k in ("M", "R", "A"):
    show["live_drawdown"][k] = {x: y for x, y in show["live_drawdown"][k].items() if x != "path"}
print(json.dumps(show, indent=1))
