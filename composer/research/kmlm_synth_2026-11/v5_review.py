"""Checks added after the two independent reviews (none is a bar; all post hoc). Writes out/review.json.
 alone       the rebuilt years read by themselves: best t and the max-statistic bar on REPLICATION alone
 resolution  on the overlap with the real fund, does the synthetic reproduce each variant's daily difference
             against the live rule? (review B S1, review A S3)
 switch      does the switch itself earn its keep: live rule minus always risk-on, always risk-off, the
             inverted flag, and 60 circularly shifted flags, per stretch (review B S4; edge rule)"""
import json
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
K57 = os.path.join(HERE, "..", "kmlm_2026-11")
sys.path.insert(0, HERE)
sys.path.insert(0, K57)
import data as kdata  # noqa: E402
import ksim as ks  # noqa: E402
import q1_cells as q1  # noqa: E402
import sdata  # noqa: E402
import v3_long as v3  # noqa: E402
from q2_stats import boot_idx  # noqa: E402

out = {}
t_of = v3.t_of
# ---- (a) each rebuilt stretch alone
lr = json.load(open(sdata.CACHE + "/cells_long.json"))
ids = [c for c in lr["cells"] if c != "base"]
rng = np.random.default_rng(20261124)
out["alone"] = {}
for k, lo, hi in (("R", v3.R0, v3.R1), ("M", v3.M0, "2008-01-31")):
    idx = [i for i, d in enumerate(lr["days"]) if lo <= d <= hi]
    b = np.log1p(np.array(lr["cells"]["base"]["ret"])[idx])
    D = np.array([np.log1p(np.array(lr["cells"][c]["ret"])[idx]) - b for c in ids]).T
    n = len(D)
    mean, se = D.mean(0), D.std(0, ddof=1) / math.sqrt(n)
    t = np.where(se > 0, mean / np.where(se > 0, se, 1), 0.0)
    mx = np.empty(2000)
    for j in range(2000):
        Db = D[boot_idx(n, rng)]
        sb = Db.std(0, ddof=1) / math.sqrt(n)
        ok = sb > 0
        mx[j] = np.max(np.where(ok, (Db.mean(0) - mean) / np.where(ok, sb, 1), -np.inf))
    live = [i for i in range(len(ids)) if se[i] == 0]
    best = int(np.argmax(t))
    out["alone"][k] = {"best": ids[best], "best_t": float(t[best]), "best_dlog_per_yr": float(mean[best] * 252), "critical_t_90": float(np.quantile(mx, 0.90)),
                       "best_p_fw": float((mx >= t[best]).mean()), "ahead": int((mean > 0).sum()), "challengers": len(ids) - len(live),
                       "worst": ids[int(np.argmin(t))], "worst_t": float(t.min()), "cells_below_minus_crit": [ids[i] for i in range(len(ids)) if t[i] < -np.quantile(mx, 0.90)]}
# ---- (b) resolution on the overlap
re_ = json.load(open(sdata.CACHE + "/cells_real_tr.json"))
so = json.load(open(sdata.CACHE + "/cells_synth_overlap.json"))
days = so["days"]
ri = [re_["days"].index(d) for d in days]
rb, sb_ = np.log1p(np.array(re_["cells"]["base"]["ret"])[ri]), np.log1p(np.array(so["cells"]["base"]["ret"]))
res = {}
for c in ids:
    a = np.log1p(np.array(re_["cells"][c]["ret"])[ri]) - rb
    s = np.log1p(np.array(so["cells"][c]["ret"])) - sb_
    if a.std() == 0 or s.std() == 0:
        continue
    res[c] = {"corr_of_daily_difference": float(np.corrcoef(a, s)[0, 1]), "real_total": float(a.sum()), "synthetic_total": float(s.sum())}
grp = {"windows 9-14": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (9, 11, 12, 14)], "windows 17-60": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (17, 20, 25, 30, 40, 60)],
       "windows 3-8": [f"{f}.rsi{n}" for f in ("F1a", "F1b") for n in (3, 5, 7, 8)], "moving averages and momentum": [c for c in ids if c.startswith(("F4.", "F5.", "F6."))]}
out["resolution"] = {"sessions": len(days), "cells": res, "groups": {}}
for g, cs in grp.items():
    cs = [c for c in cs if c in res]
    out["resolution"]["groups"][g] = {"cells": len(cs), "median_corr": float(np.median([res[c]["corr_of_daily_difference"] for c in cs])),
                                      "same_sign": int(sum((res[c]["real_total"] > 0) == (res[c]["synthetic_total"] > 0) for c in cs)),
                                      "rms_gap_log_per_yr": float(np.sqrt(np.mean([(res[c]["real_total"] - res[c]["synthetic_total"]) ** 2 for c in cs])) / (len(days) / 252))}
# ---- (c) the switch itself
exposure = json.load(open(os.path.join(HERE, "out", "fidelity.json")))["exposure"]
PL = v3.long_panel("ts_synth", exposure)
PR = dict(kdata.panel_ab(q1.END), KMLM=sdata.fund_tr(q1.END))
tree, ftree = ks.approved(), ks.v_switch_flag(ks.approved())
out["switch"] = {}
rnd = random.Random(20261124)
for k, P, lo, hi, shifts in (("M", PL, v3.M0, "2008-01-31", 0), ("R", PL, v3.R0, v3.R1, 60), ("REAL", PR, q1.B_START, q1.END, 60)):
    flag = q1.flag_rsi(P, 10)
    fd = [d for d in sorted(flag) if flag[d] is not None]
    base = ks.simulate(tree, P, lo, hi)
    lb = np.log1p(np.array(base["ret"]))
    chk = ks.simulate(ftree, P, lo, hi, flags=[flag])
    assert max(abs(x - y) for x, y in zip(base["ret"], chk["ret"])) < 1e-12
    row = {"sessions": len(lb), "risk_on_share": sum(flag[d] for d in base["days"]) / len(base["days"])}
    for name, f in (("always_risk_on", {d: True for d in fd}), ("always_risk_off", {d: False for d in fd}), ("inverted", {d: not flag[d] for d in fd})):
        r = ks.simulate(ftree, P, lo, hi, flags=[f])
        d = lb - np.log1p(np.array(r["ret"]))
        st = ks.stats(r["ret"])
        row[name] = {"live_minus_log_per_yr": float(d.mean() * 252), "t": t_of(d), "cagr": st["cagr"], "maxdd": st["maxdd"]}
    row["live"] = {x: ks.stats(base["ret"])[x] for x in ("cagr", "maxdd")}
    if shifts:
        inside = [d for d in fd if d >= base["days"][0] or True]
        vals = [flag[d] for d in inside]
        n_ge = 0
        gs = []
        for _ in range(shifts):
            s = rnd.randrange(60, len(vals) - 60)
            f = dict(zip(inside, vals[s:] + vals[:s]))
            r = ks.simulate(ftree, P, lo, hi, flags=[f])
            g = float(np.log1p(np.array(r["ret"])).sum())
            gs.append(g)
            n_ge += g >= lb.sum()
        row["placebo"] = {"shifts": shifts, "at_or_above_live": int(n_ge), "live_log_growth": float(lb.sum()), "median_shifted": float(np.median(gs)), "best_shifted": float(max(gs))}
    out["switch"][k] = row
    print(k, {a: ({x: round(y, 3) for x, y in b.items()} if isinstance(b, dict) else round(b, 3)) for a, b in row.items()}, flush=True)
json.dump(out, open(os.path.join(HERE, "out", "review.json"), "w"), indent=1)
print("alone", out["alone"])
print("resolution", out["resolution"]["groups"])
