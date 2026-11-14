"""Run the registered study (PREREG.md). Writes results_<round>.json / null.json.

usage: python3 run.py null            # placebo best-of-N, R=200, N up to 40
       python3 run.py r1|r2|r3        # a round (r2/r3 only if PREREG escalates)
"""
import dataclasses
import json
import os
import statistics
import sys
import time

from harness import (BASE, LIVE_LEV, LIVE_W_TREND, S4_CFG, T_2013, T_2022,
                     T_FWD, T_IS_END, blend_exit_step, blend_mtm,
                     curve_stats, load_asset, run_s3, run_s4, trade_stats)
from variants import ROUND1, ROUND3, ROUND4, family, placebos, placebos_sa, round2

HERE = os.path.dirname(os.path.abspath(__file__))
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
W, LEV = LIVE_W_TREND, LIVE_LEV
BTC = load_asset("btc")
ALTS = {s: load_asset(s) for s in ("eth", "ltc", "xrp", "bch")}
B3, M3 = run_s3(BTC, T_2022, T_IS_END)


def crit_a(v, exit_only=False):
    b4, m4 = run_s4(BTC, v, T_2022, T_IS_END)            # deployed config
    ce = blend_exit_step(B3, b4, W, LEV, T_2022, T_IS_END)
    if ce[-1][0] < T_IS_END:
        ce.append((T_IS_END, ce[-1][1]))
    se = curve_stats(ce)
    if exit_only:
        return se
    sm = curve_stats(blend_mtm(M3, m4, W, LEV), bar_returns=True)
    return dict(exit=se, mtm=sm, s4_trades=trade_stats(b4), halted=b4.halted)


def crit_b(v):
    b, m = run_s4(BTC, v, T_2013, T_IS_END, cfg=NOHALT)
    yearly, prev = {}, m[0][1]
    for t_, e in m:
        y = time.gmtime(t_).tm_year
        if y not in yearly:
            yearly[y] = [prev, e]
        yearly[y][1] = e
        prev = e
    return dict(mtm=curve_stats(m, bar_returns=True), trades=trade_stats(b),
                yearly={y: b_[1] / b_[0] - 1 for y, b_ in yearly.items()})


def crit_d(v):
    out = {}
    for s, A in ALTS.items():
        b, m = run_s4(A, v, None, None, cfg=NOHALT)
        out[s] = dict(mtm=curve_stats(m, bar_returns=True), trades=trade_stats(b))
    return out


def fwd(v):
    b, m = run_s4(BTC, v, T_FWD, None)
    return dict(mtm=curve_stats(m, bar_returns=True), n=len(b.trades),
                open=b.position is not None,
                pnl=[(t.exit_reason, round(t.pnl_usd, 2)) for t in b.trades])


def evaluate(v):
    return dict(name=v.name, family=family(v), spec=dataclasses.asdict(v),
                A=crit_a(v), B=crit_b(v), D=crit_d(v), F=fwd(v))


def mar(x):
    return x["mar"] if x["mar"] is not None else 0.0


def judge(r, base, q95):
    da_e = mar(r["A"]["exit"]) - mar(base["A"]["exit"])
    da_m = mar(r["A"]["mtm"]) - mar(base["A"]["mtm"])
    a = (da_e >= 0.10 * abs(mar(base["A"]["exit"]))
         and da_m >= 0.10 * abs(mar(base["A"]["mtm"])))
    b = mar(r["B"]["mtm"]) >= mar(base["B"]["mtm"])
    c = q95 is not None and da_e > q95
    dd = [mar(r["D"][s]["mtm"]) - mar(base["D"][s]["mtm"]) for s in ALTS]
    d = sum(x > 0 for x in dd) >= 3 and statistics.mean(dd) > 0
    return dict(dA_exit=da_e, dA_mtm=da_m, dB=mar(r["B"]["mtm"]) - mar(base["B"]["mtm"]),
                dD=dict(zip(ALTS, dd)), A=a, B=b, C=c, D=d, eligible=a and b and c and d)


def main():
    what = sys.argv[1]
    t0 = time.time()
    if what == "null4":                       # AMENDMENT 1: extend to N = 62
        nj = json.load(open(os.path.join(HERE, "null.json")))
        base_e = nj["base_exit_mar"]
        reps = []
        for rep, ds in enumerate(nj["reps"]):
            extra = [mar(crit_a(v, exit_only=True)) - base_e for v in placebos_sa(22, rep)]
            reps.append(ds + extra)
        best = sorted(max(ds) for ds in reps)
        q = dict(q95=best[int(0.95 * len(best)) - 1], median=best[len(best) // 2])
        json.dump(dict(base_exit_mar=base_e, q={"62": q}, reps_extra=[r[40:] for r in reps]),
                  open(os.path.join(HERE, "null4.json"), "w"))
        print("null4", json.dumps(q), f"{time.time() - t0:.0f}s")
        return
    if what == "null":
        base_e = mar(crit_a(BASE, exit_only=True))
        reps = []
        for rep in range(200):
            ds = [mar(crit_a(v, exit_only=True)) - base_e for v in placebos(40, rep)]
            reps.append(ds)
        q = {}
        for n in (30, 34, 40):
            best = sorted(max(ds[:n]) for ds in reps)
            q[n] = dict(q95=best[int(0.95 * len(best)) - 1], median=best[len(best) // 2])
        json.dump(dict(base_exit_mar=base_e, q=q, reps=reps),
                  open(os.path.join(HERE, "null.json"), "w"))
        print("null", json.dumps(q), f"{time.time() - t0:.0f}s")
        return
    base = evaluate(BASE)
    nullq = json.load(open(os.path.join(HERE, "null.json")))["q"]
    if what == "r4":
        nullq.update(json.load(open(os.path.join(HERE, "null4.json")))["q"])
    if what == "r1":
        vs, n = ROUND1, "30"
    elif what == "r2":
        r1 = json.load(open(os.path.join(HERE, "results_r1.json")))
        best = {}
        for r in sorted(r1["rows"], key=lambda r: -r["judge"]["dA_exit"]):
            best.setdefault(r["family"], r)
        top = sorted(best.values(), key=lambda r: -r["judge"]["dA_exit"])[:3]
        by_name = {v.name: v for v in ROUND1}
        vs, n = round2([by_name[r["name"]] for r in top]), "34"
    elif what == "r3":
        vs, n = ROUND3, "40"
    elif what == "r4":
        vs, n = ROUND4, "62"
    else:
        raise SystemExit(f"unknown round {what!r}")
    q95 = nullq[n]["q95"]
    rows = []
    for v in vs:
        r = evaluate(v)
        r["judge"] = judge(r, base, q95)
        rows.append(r)
        j = r["judge"]
        print(f"{v.name:22s} dA_exit {j['dA_exit']:+.3f} dA_mtm {j['dA_mtm']:+.3f} "
              f"dB {j['dB']:+.3f} alts+ {sum(x > 0 for x in j['dD'].values())}/4 "
              f"A{int(j['A'])} B{int(j['B'])} C{int(j['C'])} D{int(j['D'])}"
              f"{'  ELIGIBLE' if j['eligible'] else ''}")
    json.dump(dict(base=base, q95=q95, n_trials=int(n), rows=rows),
              open(os.path.join(HERE, f"results_{what}.json"), "w"), default=float)
    print(f"base A exit MAR {mar(base['A']['exit']):.3f} mtm {mar(base['A']['mtm']):.3f} "
          f"B {mar(base['B']['mtm']):.3f} | q95(best-of-{n}) {q95:+.3f} | "
          f"{sum(r['judge']['eligible'] for r in rows)} eligible | {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
