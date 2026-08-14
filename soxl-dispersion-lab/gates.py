#!/usr/bin/env python3
"""Step 4 — regime gates, tested individually then in combination.

Two views for every gate:

  CONDITIONAL  the UNGATED book's returns partitioned by gate state. This
               isolates whether the gate carries information at all, with no
               interaction from rebalancing or costs.
  APPLIED      the full engine re-run with the gate scaling the book, so the
               reported numbers include the cost of trading in and out.

Both are split in-sample (<=2019) / out-of-sample (2020+). A gate that only
works in-sample is reported as failed, not quietly dropped.

Writes fixtures/gates.json.
"""
import json
import math
import os

import numpy as np

from datalib import Costs, Data, TRADING_DAYS, metrics, run_backtest
from signals import (Signals, gate_all, gate_dispersion, gate_macro,
                     gate_trend, gate_vix_ts, gate_vol)
from variants import BASE_COSTS, tgt_long_short

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "gates.json")
START, IS_END, OOS_START = "2010-03-12", "2019-12-31", "2020-01-01"


def ann(r):
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return float("nan"), float("nan")
    a = r.mean() * TRADING_DAYS
    s = (r.mean() / r.std(ddof=1) * math.sqrt(TRADING_DAYS)
         if r.std(ddof=1) > 0 else float("nan"))
    return a, s


def main():
    d = Data()
    sig = Signals(d)
    end = d.dates[-1]
    costs = Costs(**BASE_COSTS)
    res = {}

    # ---- ungated reference book, daily returns ---------------------------
    base = run_backtest(d, START, end, tgt_long_short(8, "cap"), costs=costs,
                        rebalance="M", label="V0")
    nav = base["nav"]
    r = np.full(len(nav), np.nan)
    r[1:] = nav[1:] / nav[:-1] - 1
    bdates = base["dates"]
    di = {x: k for k, x in enumerate(bdates)}
    is_mask = np.array([x <= IS_END for x in bdates])

    GATES = {
        "trend: SOXX < 200dma": gate_trend(sig, 200, invert=True),
        "trend: SOXX < 100dma": gate_trend(sig, 100, invert=True),
        "trend: SOXX > 200dma (inverse)": gate_trend(sig, 200, invert=False),
        "vol: 20d rvol > 1y median": gate_vol(sig, 0.50),
        "vol: 20d rvol > 1y 75th pct": gate_vol(sig, 0.75),
        "VIX term structure inverted": gate_vix_ts(sig, 1.0),
        "VIX/VIX3M > 0.95": gate_vix_ts(sig, 0.95),
        "dispersion > 1y median": gate_dispersion(sig, 0.50),
        "dispersion > 1y 75th pct": gate_dispersion(sig, 0.75),
        "macro: SOX/SPX 6mo mom < 0": gate_macro(sig, 0.0),
        "COMBO: <200dma AND rvol>med": gate_all(gate_trend(sig, 200, True),
                                                gate_vol(sig, 0.50)),
        "COMBO: <200dma AND disp>med": gate_all(gate_trend(sig, 200, True),
                                                gate_dispersion(sig, 0.50)),
        "COMBO: <200dma AND SOX/SPX<0": gate_all(gate_trend(sig, 200, True),
                                                 gate_macro(sig, 0.0)),
    }

    # =====================================================================
    print("=" * 116)
    print("GATE ANALYSIS — conditional performance of the UNGATED V0 book")
    print("=" * 116)
    print(f"{'gate':<34}{'%on':>6}{'ON ann':>9}{'ON Shrp':>9}"
          f"{'OFF ann':>9}{'OFF Shrp':>9}{'IS ON ann':>11}{'OOS ON ann':>12}"
          f"{'survives':>10}")
    print("-" * 116)
    for name, g in GATES.items():
        state = np.array([g(d, d.di[x]) for x in bdates]) > 0
        on, off = state & np.isfinite(r), (~state) & np.isfinite(r)
        a_on, s_on = ann(r[on])
        a_off, s_off = ann(r[off])
        a_is, _ = ann(r[on & is_mask])
        a_oos, _ = ann(r[on & ~is_mask])
        surv = "yes" if (np.isfinite(a_is) and np.isfinite(a_oos)
                         and a_is > 0 and a_oos > 0) else "NO"
        print(f"{name:<34}{state.mean()*100:>5.0f}%{a_on*100:>8.1f}%"
              f"{s_on:>9.2f}{a_off*100:>8.1f}%{s_off:>9.2f}"
              f"{a_is*100:>10.1f}%{a_oos*100:>11.1f}%{surv:>10}")
        res.setdefault("conditional", {})[name] = {
            "pct_on": float(state.mean()), "on_ann": a_on, "on_sharpe": s_on,
            "off_ann": a_off, "off_sharpe": s_off, "is_on_ann": a_is,
            "oos_on_ann": a_oos, "survives_oos": surv == "yes"}

    # =====================================================================
    print("\n" + "=" * 116)
    print("GATE ANALYSIS — gate APPLIED to the book (engine, net of costs)")
    print("=" * 116)
    for pname, ps, pe in [("full", START, end), ("IS", START, IS_END),
                          ("OOS", OOS_START, end)]:
        print(f"\n-- {pname} ({ps} -> {pe})")
        print(f"{'gate':<34}{'CAGR':>8}{'vol':>7}{'Sharpe':>8}{'maxDD':>8}"
              f"{'Calmar':>8}{'trd/y':>7}")
        rows = {}
        ub = run_backtest(d, ps, pe, tgt_long_short(8, "cap"), costs=costs,
                          rebalance="M")
        lo, hi = d.slice_idx(ps, pe)
        m = metrics(ub["nav"], ub["dates"], rf=d.rf[lo + 1:hi])
        print(f"{'(ungated V0)':<34}{m['CAGR']*100:>7.1f}%{m['Vol']*100:>6.1f}%"
              f"{m['Sharpe']:>8.2f}{m['MaxDD']*100:>7.1f}%{m['Calmar']:>8.2f}"
              f"{ub['costs']['n_trades']/m['Years']:>7.0f}")
        rows["(ungated V0)"] = {k: m[k] for k in
                                ("CAGR", "Vol", "Sharpe", "MaxDD", "Calmar")}
        for name, g in GATES.items():
            b = run_backtest(d, ps, pe, tgt_long_short(8, "cap"), costs=costs,
                             rebalance="M", gate_fn=g)
            mm = metrics(b["nav"], b["dates"], rf=d.rf[lo + 1:hi])
            if not mm:
                continue
            print(f"{name:<34}{mm['CAGR']*100:>7.1f}%{mm['Vol']*100:>6.1f}%"
                  f"{mm['Sharpe']:>8.2f}{mm['MaxDD']*100:>7.1f}%"
                  f"{mm['Calmar']:>8.2f}"
                  f"{b['costs']['n_trades']/mm['Years']:>7.0f}")
            rows[name] = {k: mm[k] for k in
                          ("CAGR", "Vol", "Sharpe", "MaxDD", "Calmar")}
        res.setdefault("applied", {})[pname] = rows

    # ---- overfit flag: Sharpe collapse IS -> OOS ------------------------
    print("\n" + "=" * 116)
    print("OVERFIT SCREEN — Sharpe collapse from in-sample to out-of-sample")
    print("=" * 116)
    print(f"{'gate':<34}{'IS Sharpe':>11}{'OOS Sharpe':>12}{'collapse':>11}"
          f"{'verdict':>12}")
    flags = {}
    for name in res["applied"]["IS"]:
        si = res["applied"]["IS"][name]["Sharpe"]
        so = res["applied"]["OOS"].get(name, {}).get("Sharpe", float("nan"))
        if not (np.isfinite(si) and np.isfinite(so)):
            continue
        coll = (si - so) / abs(si) if si != 0 else float("nan")
        # A negative in-sample Sharpe means there was never an in-sample edge
        # to survive: reporting that as "ok" (as a bare collapse>40% test
        # does) would dress a decade of losses up as a passing grade.
        if si <= 0:
            verdict = "NO IS EDGE"
        elif coll > 0.40:
            verdict = "OVERFIT"
        else:
            verdict = "ok"
        print(f"{name:<34}{si:>11.2f}{so:>12.2f}{coll*100:>10.0f}%"
              f"{verdict:>12}")
        flags[name] = {"is_sharpe": si, "oos_sharpe": so, "collapse": coll,
                       "verdict": verdict}
    res["overfit_screen"] = flags

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
