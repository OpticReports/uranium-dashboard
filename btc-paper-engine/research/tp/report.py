"""Reported (non-gating) items PREREG §5 promised: criterion A per calendar
year, DSR against the registry count, and the trade-level facts quoted in
RESEARCH_TP.md. Read-only use of the harness. Writes report.json.

usage: python3 report.py
"""
import dataclasses
import json
import math
import os
import statistics
from statistics import NormalDist

from harness import (BASE, LIVE_LEV, LIVE_W_TREND, S4_CFG, T_2013, T_2022,
                     T_IS_END, blend_exit_step, blend_mtm, load_asset, run_s3,
                     run_s4)
from variants import ROUND1, ROUND4

HERE = os.path.dirname(os.path.abspath(__file__))
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
REGISTRY_N = 2608                       # RESEARCH_PROTOCOL.md §1 after this study
BTC = load_asset("btc")
B3, M3 = run_s3(BTC, T_2022, T_IS_END)
byname = {v.name: v for v in ROUND1 + ROUND4}
picks = ["BASE", "F6_time120", "F6_time120_sa30", "F2_ptp3_f33", "F1_tp8"]


def yearly(curve):
    out, prev, cur = {}, curve[0][1], None
    import time as _t
    for ts, v in curve:
        y = _t.gmtime(ts).tm_year
        if y != cur:
            if cur is not None:
                out[cur] = last / prev - 1
                prev = last
            cur = y
        last = v
    out[cur] = last / prev - 1
    return out


rep = {"A_yearly": {}, "dsr": {}}
mtm_returns = {}
for nm in picks:
    v = BASE if nm == "BASE" else byname[nm]
    b4, m4 = run_s4(BTC, v, T_2022, T_IS_END)
    ce = blend_exit_step(B3, b4, LIVE_W_TREND, LIVE_LEV, T_2022, T_IS_END)
    cm = blend_mtm(M3, m4, LIVE_W_TREND, LIVE_LEV)
    rep["A_yearly"][nm] = {"exit": yearly(ce), "mtm": yearly(cm)}
    mtm_returns[nm] = [cm[k][1] / cm[k - 1][1] - 1 for k in range(1, len(cm))]

# DSR (Bailey & Lopez de Prado): hurdle from the spread of the study's own
# 62 trial Sharpes (A, MTM basis), N = the registry count.
rows = []
for r in ("r1", "r2", "r3", "r4"):
    rows += json.load(open(os.path.join(HERE, f"results_{r}.json")))["rows"]
sr_trials = [r["A"]["mtm"]["sharpe"] / math.sqrt(2190) for r in rows]
V = statistics.pvariance(sr_trials)
nd, g = NormalDist(), 0.5772156649
sr0 = math.sqrt(V) * ((1 - g) * nd.inv_cdf(1 - 1 / REGISTRY_N)
                      + g * nd.inv_cdf(1 - 1 / (REGISTRY_N * math.e)))
for nm, r in mtm_returns.items():
    T = len(r)
    mu = sum(r) / T
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (T - 1))
    sr = mu / sd
    sk = sum((x - mu) ** 3 for x in r) / T / sd ** 3
    ku = sum((x - mu) ** 4 for x in r) / T / sd ** 4
    den = math.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    z = (sr - sr0) * math.sqrt(T - 1) / den
    # Protocol §2 basis: independent zero-skill trials, Var(SR_hat) = 1/(T-1).
    sr0_i = math.sqrt(1 / (T - 1)) * ((1 - g) * nd.inv_cdf(1 - 1 / REGISTRY_N)
                                      + g * nd.inv_cdf(1 - 1 / (REGISTRY_N * math.e)))
    z_i = (sr - sr0_i) * math.sqrt(T - 1) / den
    rep["dsr"][nm] = dict(sr_ann=sr * math.sqrt(2190), sr0_ann=sr0 * math.sqrt(2190),
                          dsr=nd.cdf(z), sr0_indep_ann=sr0_i * math.sqrt(2190),
                          dsr_indep=nd.cdf(z_i))

# trade-level facts (S4 alone, kill switch off)
for lbl, t0 in (("2013_2026", T_2013), ("2022_2026", T_2022)):
    bk, _ = run_s4(BTC, BASE, t0, T_IS_END, cfg=NOHALT)
    tr = sorted(bk.trades, key=lambda t: -math.log(t.equity_after / t.equity_before))
    k = round(len(tr) * 0.10)
    top = tr[:k]
    keep = []
    for t in top:
        sgn = 1 if t.side == "L" else -1
        best = (t.mfe_px - t.entry_price) * sgn
        if best > 0:
            keep.append((t.exit_price - t.entry_price) * sgn / best)
    rep[f"top_{lbl}"] = dict(
        n=len(tr), k=k,
        log_top=sum(math.log(t.equity_after / t.equity_before) for t in top),
        log_rest=sum(math.log(t.equity_after / t.equity_before) for t in tr[k:]),
        top_held_120plus=sum(t.bars_held >= 120 for t in top),
        top_median_bars=statistics.median(t.bars_held for t in top),
        top_median_kept_of_peak=statistics.median(keep))
json.dump(rep, open(os.path.join(HERE, "report.json"), "w"), indent=1)
for nm in picks:
    ya = rep["A_yearly"][nm]["mtm"]
    d = rep["dsr"][nm]
    print(f"{nm:18s} A mtm by year {[f'{y}:{100 * v:+.0f}%' for y, v in ya.items()]} | "
          f"SR {d['sr_ann']:.2f} | protocol-basis hurdle {d['sr0_indep_ann']:.2f} -> DSR {d['dsr_indep']:.2f} "
          f"| study-spread hurdle {d['sr0_ann']:.2f} -> {d['dsr']:.2f}")
for lbl in ("2013_2026", "2022_2026"):
    print(lbl, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rep[f"top_{lbl}"].items()})
