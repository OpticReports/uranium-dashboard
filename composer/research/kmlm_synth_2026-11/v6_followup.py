"""Follow-ups required by the third review (post hoc, none a bar). Writes out/followup.json.
 switch   how concentrated the switch's edge on the rebuilt years is: without 2008 and 2020, against a static
          mix at the switch's own risk-on share, and on the real fund after the tree's own fitting stamp
 path     the live rule's unbroken daily path over the modelled and rebuilt years: depth, low, recovery
 ranks    do the window variants rank the same way on the rebuilt and the real years?"""
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
import q1_cells as q1  # noqa: E402
import sdata  # noqa: E402
import v3_long as v3  # noqa: E402

t_of = v3.t_of
out = {"switch": {}}
exposure = json.load(open(os.path.join(HERE, "out", "fidelity.json")))["exposure"]
PL = v3.long_panel("ts_synth", exposure)
PR = dict(kdata.panel_ab(q1.END), KMLM=sdata.fund_tr(q1.END))
tree, ftree = ks.approved(), ks.v_switch_flag(ks.approved())
STAMP = "2022-04-13"                                   # the tree's own description: "BT 4/13/22"
for k, P, lo, hi in (("R", PL, v3.R0, v3.R1), ("REAL", PR, q1.B_START, q1.END)):
    flag = q1.flag_rsi(P, 10)
    fd = [d for d in sorted(flag) if flag[d] is not None]
    base = ks.simulate(tree, P, lo, hi)
    days = base["days"]
    lb = np.log1p(np.array(base["ret"]))
    alt = {n: np.array(ks.simulate(ftree, P, lo, hi, flags=[f])["ret"]) for n, f in
           (("on", {d: True for d in fd}), ("off", {d: False for d in fd}), ("inv", {d: not flag[d] for d in fd}))}
    share = sum(flag[d] for d in days) / len(days)
    d_on, d_off, d_inv = (lb - np.log1p(alt[n]) for n in ("on", "off", "inv"))
    d_mix = lb - np.log1p(share * alt["on"] + (1 - share) * alt["off"])
    row = {"risk_on_share": share, "mirror_equals_sum_corr": float(np.corrcoef(d_inv, d_on + d_off)[0, 1]),
           "vs_static_mix": {"log_per_yr": float(d_mix.mean() * 252), "t": t_of(d_mix)},
           "mirror_by_year": {y: float(d_inv[[d[:4] == y for d in days]].sum()) for y in sorted({d[:4] for d in days})}}
    if k == "R":
        keep = np.array([d[:4] not in ("2008", "2020") for d in days])
        k08 = np.array([d[:4] != "2008" for d in days])
        mid = np.array(["2012" <= d[:4] <= "2019" for d in days])
        row.update({"mirror_all": {"log_per_yr": float(d_inv.mean() * 252), "t": t_of(d_inv)},
                    "mirror_without_2008_2020": {"log_per_yr": float(d_inv[keep].mean() * 252), "t": t_of(d_inv[keep])},
                    "share_of_mirror_from_2008_2020": float(d_inv[~keep].sum() / d_inv.sum()),
                    "risk_on_without_2008": {"log_per_yr": float(d_on[k08].mean() * 252), "t": t_of(d_on[k08])},
                    "risk_on_2012_2019": {"log_per_yr": float(d_on[mid].mean() * 252), "t": t_of(d_on[mid])}})
    else:
        after = np.array([d > STAMP for d in days])
        row.update({"mirror_all": {"log_per_yr": float(d_inv.mean() * 252), "t": t_of(d_inv)},
                    "mirror_after_stamp": {"log_per_yr": float(d_inv[after].mean() * 252), "t": t_of(d_inv[after]), "sessions": int(after.sum())}})
    out["switch"][k] = row
# ---- the unbroken path
lr = json.load(open(sdata.CACHE + "/cells_long.json"))
ds, r = lr["days"], np.array(lr["cells"]["base"]["ret"])
lvl = np.cumprod(1 + r)
pk = np.maximum.accumulate(lvl)
dd = 1 - lvl / pk
j = int(np.argmax(dd))
i = int(np.argmax(lvl[:j + 1]))
rec = next((ds[k] for k in range(j, len(ds)) if lvl[k] >= lvl[i]), None)
m_end = max(k for k, d in enumerate(ds) if d < v3.R0)
eps, a = [], 0
while a < len(dd):
    if dd[a] > 0:
        b = a
        while b < len(dd) and dd[b] > 0:
            b += 1
        c = a + int(np.argmax(dd[a:b]))
        eps.append({"depth": float(dd[c]), "peak": ds[a - 1] if a else ds[0], "trough": ds[c], "recovered": ds[b] if b < len(dd) else None})
        a = b
    else:
        a += 1
out["path"] = {"deepest": {"depth": float(dd[j]), "peak": ds[i], "trough": ds[j], "recovered": rec}, "depth_at_end_of_model_years": float(dd[m_end]),
               "falls_from_2008": sorted([e for e in eps if e["trough"] >= "2012-01-01"], key=lambda e: -e["depth"])[:4]}
# what the live rule held through its deepest fall after 2012 (which funds lost the money)
P = PL
sim = ks.simulate(tree, P, v3.R0, v3.R1)
f = out["path"]["falls_from_2008"][0]
loss = {}
for d0, d1 in zip(sim["days"][:-1], sim["days"][1:]):
    if f["peak"] <= d0 < f["trough"]:
        for t, w in sim["held"][d0].items():
            loss[t] = loss.get(t, 0.0) + w * (P[t][d1] / P[t][d0] - 1)
out["path"]["deepest_since_2012_by_fund"] = dict(sorted(loss.items(), key=lambda kv: kv[1])[:6])
# ---- do window variants rank alike?
L = json.load(open(os.path.join(HERE, "out", "long.json")))["cells"]
win = [c for c in L if c.startswith(("F1a.", "F1b.")) and not L[c]["is_live_rule"]]


def spearman(a, b):
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


x = {k: [L[c][k]["dlog_per_yr"] for c in win] for k in ("R", "REAL", "M")}
out["ranks"] = {"window_variants": len(win), "rebuilt_vs_real": spearman(x["R"], x["REAL"]), "modelled_vs_real": spearman(x["M"], x["REAL"]),
                "same_sign_rebuilt_real": int(sum((a > 0) == (b > 0) for a, b in zip(x["R"], x["REAL"])))}
json.dump(out, open(os.path.join(HERE, "out", "followup.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in out.items()}, indent=1)[:3800])
