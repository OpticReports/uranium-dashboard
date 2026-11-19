"""Rebalance-phase sensitivity (post-result note N2, raised by the independent recompute).
The band rule makes each book's rebalance dates path-dependent, so an arm and the live book can rebalance on
different days and the difference between them picks up timing luck. Two phase-free re-statements per arm:
 (a) daily constant weights, no costs, for both arm and live;
 (b) both books rebalanced to target on the same fixed schedule (every month-end), costs charged.
Writes ../phase_check.json."""
import json, os, pickle
import numpy as np, pandas as pd
import lib2 as L, run2 as RUN
from lib2 import C, E, IX, LIVE

p = L.load(); tape = L.build(p, "T1"); cal = tape["cal"]; R = tape["R"].values; c = R[:, -1]; T = len(cal)
ix = lambda d: int(cal.searchsorted(pd.Timestamp(d))); i0, ic = ix(C.EXT0), ix(C.CONF0)
res = json.load(open(os.path.join(L.STUDY, "results2.json")))["T1"]["arms"]
ch1, _ = RUN.p1_changes(tape); b0 = tape["first"]["BTAL"]; eq = {l: -.10 * pr for l, pr in zip(L.EQ, L.EQP)}
ARMS = {"P1": L.path(cal, LIVE, ch1), "P3": L.path(cal, LIVE, [(b0, RUN.swap(TAIL=-.059, BTAL=.059))]), "S3b": L.path(cal, LIVE, [(b0, RUN.swap(TAIL=-.0295, BTAL=.0295))]),
        "P5": L.path(cal, RUN.swap(IEF=.10, **eq)), "P6": L.path(cal, RUN.swap(AVUV=-.08, AVLVc=.08)), "S6a": L.path(cal, RUN.swap(AVUV=-.08, QUAL=.08)),
        "S6b": L.path(cal, LIVE, [(tape["first"]["USMV"], RUN.swap(AVUV=-.08, USMV=.08))]),
        "E7": L.path(cal, LIVE, [(tape["first"]["UUP"], RUN.swap(TAIL=-.05, UUP=.05))]),
        "TAIL_to_bills_5pts": L.path(cal, RUN.swap(TAIL=-.05, BIL=.05))}
WL = L.path(cal, LIVE)
def cw(W):                                              # (a) daily constant weights: weights set at the prior close
    Wl = np.vstack([W[:1], W[:-1]]); return (Wl * R).sum(1)
def monthly(W):                                         # (b) engine with band 0: whole book back to target after every month-end
    return E.simulate(np.ascontiguousarray(R), np.ascontiguousarray(W), L.COST, tape["me"], 0.0, C.CAL_DAYS, 1e-9, False, np.zeros(L.N, bool), 0.0, 0, T)[0]
def d(ra, rl, a, b):
    return dict(d_sharpe=E.sharpe(ra[a:b] - c[a:b]) - E.sharpe(rl[a:b] - c[a:b]), d_sortino=L.sortino(ra[a:b] - c[a:b]) - L.sortino(rl[a:b] - c[a:b]),
                d_cagr=float(np.prod(1 + ra[a:b]) ** (252 / (b - a)) - np.prod(1 + rl[a:b]) ** (252 / (b - a))))
out = {}; lcw, lmo, lband = cw(WL), monthly(WL), L.sim(tape, WL)
for k, W in ARMS.items():
    if k in res:
        a, b = ix(res[k]["window"][0]), T; sp = ix(res[k]["split"])
    else:
        a, b, sp = i0, T, ic
    band = L.sim(tape, W)
    out[k] = dict(window=[str(cal[a].date()), str(cal[b - 1].date())],
                  band=dict(full=d(band, lband, a, b), h1=d(band, lband, a, sp), h2=d(band, lband, sp, b), conf=d(band, lband, ic, T)),
                  constant=dict(full=d(cw(W), lcw, a, b), h1=d(cw(W), lcw, a, sp), h2=d(cw(W), lcw, sp, b), conf=d(cw(W), lcw, ic, T)),
                  monthly=dict(full=d(monthly(W), lmo, a, b), h1=d(monthly(W), lmo, a, sp), h2=d(monthly(W), lmo, sp, b), conf=d(monthly(W), lmo, ic, T)))
json.dump(out, open(os.path.join(L.STUDY, "phase_check.json"), "w"), indent=1)
print("arm                 window      | Sharpe change: band / constant / monthly | Sortino change: band / constant / monthly | monthly h1 / h2 (Sharpe, Sortino) | CAGR monthly")
for k, o in out.items():
    f = lambda m, x: o[m]["full"][x]
    print(f"{k:19s} {o['window'][0]} | {f('band','d_sharpe'):+.3f} / {f('constant','d_sharpe'):+.3f} / {f('monthly','d_sharpe'):+.3f}            | {f('band','d_sortino'):+.3f} / {f('constant','d_sortino'):+.3f} / {f('monthly','d_sortino'):+.3f}            | {o['monthly']['h1']['d_sharpe']:+.3f},{o['monthly']['h1']['d_sortino']:+.3f} / {o['monthly']['h2']['d_sharpe']:+.3f},{o['monthly']['h2']['d_sortino']:+.3f} | {f('monthly','d_cagr')*100:+.2f}")
print("E7 vs TAIL->bills on 2017+: ", {k: {m: round(out[k][m]['conf']['d_sharpe'], 3) for m in ('band', 'constant', 'monthly')} for k in ('E7', 'TAIL_to_bills_5pts')})
