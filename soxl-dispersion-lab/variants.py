#!/usr/bin/env python3
"""Step 3 — the variant comparison table, gross and net of every cost.

Run: python3 variants.py            (full period)
     python3 variants.py --split    (adds in-sample / out-of-sample split)

Writes fixtures/variants.json.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

from datalib import (ZERO_COSTS, Costs, Data, TRADING_DAYS, build_basket,
                     margin_requirement, metrics, month_ends, run_backtest)
from signals import Signals, gate_all, gate_trend, gate_vol

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "variants.json")

START = "2010-03-12"
IS_END = "2019-12-31"
OOS_START = "2020-01-01"

# Baseline cost assumptions. borrow_soxl is the study's dominant UNKNOWN --
# no vendor borrow history was obtainable, so 1.0%/yr is a placeholder that
# every headline number is stress-tested against in sensitivity.py, and the
# breakeven is solved explicitly. It is never presented as a measured input.
BASE_COSTS = dict(commission_bps=0.5, slip_etf_bps=2.0, slip_stock_bps=3.0,
                  borrow_soxl=0.010, borrow_soxs=0.030,
                  credit_spread=0.005, debit_spread=0.015)


# --------------------------------------------------------------------------
# target builders
# --------------------------------------------------------------------------
def tgt_long_short(n_names=8, scheme="cap", w_long=0.75, w_short=0.25):
    def fn(data, i):
        w = build_basket(data, i, n_names, scheme)
        if not w:
            return {}
        out = {t: w_long * v for t, v in w.items()}
        out["SOXL"] = -w_short
        return out
    return fn


def tgt_beta_neutral(n_names=8, scheme="cap", w_long=0.75, lookback=126):
    """Short leg sized so trailing net beta to SOXX is ~0."""
    def fn(data, i):
        w = build_basket(data, i, n_names, scheme)
        if not w:
            return {}
        bb = _basket_beta(data, i, w, lookback)
        bl = _beta(data, "SOXL", i, lookback)
        if not (np.isfinite(bb) and np.isfinite(bl)) or abs(bl) < 0.5:
            bb, bl = 0.9, 2.96              # long-run fallback, documented
        w_short = min(max(w_long * bb / bl, 0.0), 0.60)
        out = {t: w_long * v for t, v in w.items()}
        out["SOXL"] = -w_short
        return out
    return fn


def tgt_decay_pure(w_short=0.25):
    """V4: short SOXL, long 3x that notional in SOXX. No stock selection."""
    def fn(data, i):
        return {"SOXL": -w_short, "SOXX": 3.0 * w_short}
    return fn


def tgt_double_decay(n_names=8, w_long=0.50, w_short=0.25):
    """V5: short SOXL AND SOXS (beta cancels), plus a long basket overlay."""
    def fn(data, i):
        w = build_basket(data, i, n_names, "cap")
        if not w:
            return {}
        out = {t: w_long * v for t, v in w.items()}
        out["SOXL"] = -w_short
        out["SOXS"] = -w_short
        return out
    return fn


def _beta(data, ticker, i, lookback):
    r = data.ret(ticker)[i - lookback:i]
    b = data.ret("SOXX")[i - lookback:i]
    ok = np.isfinite(r) & np.isfinite(b)
    if ok.sum() < lookback // 2 or b[ok].std() == 0:
        return np.nan
    return np.cov(r[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)


def _basket_beta(data, i, w, lookback):
    br = np.zeros(lookback)
    tot = 0.0
    for t, wt in w.items():
        p = data.px[t][i - lookback:i + 1]
        if np.isnan(p).any():
            continue
        br += wt * (p[1:] / p[:-1] - 1.0)
        tot += wt
    if tot < 0.5:
        return np.nan
    br /= tot
    b = data.ret("SOXX")[i - lookback + 1:i + 1]
    ok = np.isfinite(br) & np.isfinite(b)
    if ok.sum() < lookback // 2 or b[ok].std() == 0:
        return np.nan
    return np.cov(br[ok], b[ok])[0, 1] / np.var(b[ok], ddof=1)


# --------------------------------------------------------------------------
def summarize(res, data, start, end, label, note="", res_gross=None):
    """Metrics for one variant.

    `res_gross` is the SAME variant re-run with every friction set to zero
    (commissions, slippage, borrow, financing spreads). Running it as a
    separate backtest -- rather than shadowing a second book inside the
    engine -- keeps the gross path exact and stops 'gross' from silently
    also meaning 'earns no interest on its cash', which made gross look
    WORSE than net for the credit-balance variants.
    """
    lo, hi = data.slice_idx(start, end)
    r_soxx = data.ret("SOXX")[lo + 1:hi]
    r_spy = data.ret("SPY")[lo + 1:hi]
    rf = data.rf[lo + 1:hi]
    m = metrics(res["nav"], res["dates"], bench_ret=r_soxx, rf=rf)
    mg = metrics(res_gross["nav"], res_gross["dates"], rf=rf) if res_gross else {}
    if not m:
        return None
    yrs = m["Years"]
    # beta vs SPY
    r = res["nav"][1:] / res["nav"][:-1] - 1
    b2 = np.asarray(r_spy)[:len(r)]
    ok = np.isfinite(r) & np.isfinite(b2)
    beta_spy = (float(np.cov(r[ok], b2[ok])[0, 1] / np.var(b2[ok], ddof=1))
                if ok.sum() > 30 else float("nan"))
    c = res["costs"]
    out = {
        "label": label, "note": note,
        "CAGR": m["CAGR"], "CAGR_gross": mg.get("CAGR", float("nan")),
        "Vol": m["Vol"], "Sharpe": m["Sharpe"],
        "Sharpe_gross": mg.get("Sharpe", float("nan")),
        "Sortino": m["Sortino"], "MaxDD": m["MaxDD"], "Calmar": m["Calmar"],
        "WinRate": m["WinRate"], "WorstMonth": m.get("WorstMonth"),
        "WorstRoll12m": m.get("WorstRoll12m"),
        "BetaSOXX": m.get("Beta"), "BetaSPY": beta_spy,
        "Years": yrs,
        "TradesPerYear": c["n_trades"] / yrs,
        "TurnoverPerYear": res["turnover"] / yrs,
        "RebalPerYear": res["n_rebals"] / yrs,
        "AvgHoldDays": TRADING_DAYS / max(res["n_rebals"] / yrs, 1e-9),
        "BorrowDrag": c["borrow"] / yrs,
        "FinancingDrag": c["financing"] / yrs,
        "TradingDrag": c["commission_slippage"] / yrs,
        "MarginPM_mean": float(np.nanmean(res["margin_pm"])),
        "MarginPM_max": float(np.nanmax(res["margin_pm"])),
        "MarginRegT_max": float(np.nanmax(res["margin_regt"])),
        "GrossExp_mean": float(np.nanmean(res["gross_exposure"])),
        "NetExp_mean": float(np.nanmean(res["net_exposure"])),
        "MarginCalls": res["n_margin_calls"],
        "BlownUp": res["blown_up"],
    }
    return out


def build_variants(d, sig):
    """(key, label, kwargs) for every variant in Step 3."""
    V = []
    V.append(("V0", "25/75 baseline, top-8 cap, monthly",
              dict(target_fn=tgt_long_short(8, "cap"), rebalance="M")))
    V.append(("V1", "beta-neutral hedge ratio",
              dict(target_fn=tgt_beta_neutral(8, "cap"), rebalance="M")))
    V.append(("V2", "vol-targeted 15%",
              dict(target_fn=tgt_long_short(8, "cap"), rebalance="M",
                   vol_target=0.15)))
    for n in (3, 5, 8, 12):
        V.append((f"V3.cap{n}", f"top-{n} cap-weighted",
                  dict(target_fn=tgt_long_short(n, "cap"), rebalance="M")))
    for sch, nm in (("ew", "equal-weight"), ("mom", "6mo momentum")):
        V.append((f"V3.{sch}8", f"top-8 {nm}",
                  dict(target_fn=tgt_long_short(8, sch), rebalance="M")))
    V.append(("V4", "decay-pure: short SOXL + 3x long SOXX",
              dict(target_fn=tgt_decay_pure(0.25), rebalance="M")))
    V.append(("V4.d", "decay-pure, DAILY reset",
              dict(target_fn=tgt_decay_pure(0.25), rebalance="D")))
    V.append(("V5", "double decay: short SOXL+SOXS + basket",
              dict(target_fn=tgt_double_decay(), rebalance="M")))
    V.append(("V7", "V0 gated: SOXX<200dma AND vol>median",
              dict(target_fn=tgt_long_short(8, "cap"), rebalance="M",
                   gate_fn=gate_all(gate_trend(sig, 200, invert=True),
                                    gate_vol(sig, 0.5)))))
    V.append(("V7.t", "V0 gated: SOXX<200dma only",
              dict(target_fn=tgt_long_short(8, "cap"), rebalance="M",
                   gate_fn=gate_trend(sig, 200, invert=True))))
    V.append(("V8", "V0 drift-band +/-5%, weekly check",
              dict(target_fn=tgt_long_short(8, "cap"), rebalance="Q",
                   drift_band=0.05)))
    for freq, nm in (("D", "daily"), ("W", "weekly"), ("Q", "quarterly")):
        V.append((f"V0.{freq}", f"baseline, {nm} rebalance",
                  dict(target_fn=tgt_long_short(8, "cap"), rebalance=freq)))
    return V


def benchmarks(d, start, end):
    """Reference points every variant must be judged against."""
    out = {}
    for tag, fn in [("SOXX long-only", lambda data, i: {"SOXX": 1.0}),
                    ("SPY long-only", lambda data, i: {"SPY": 1.0}),
                    ("top-8 basket long-only",
                     lambda data, i: build_basket(data, i, 8, "cap")),
                    ("75% basket + 25% cash",
                     lambda data, i: {t: 0.75 * v for t, v in
                                      build_basket(data, i, 8, "cap").items()})]:
        r = run_backtest(d, start, end, fn, costs=Costs(**BASE_COSTS),
                         rebalance="M", label=tag)
        rg = run_backtest(d, start, end, fn, costs=ZERO_COSTS,
                          rebalance="M", label=tag)
        out[tag] = summarize(r, d, start, end, tag, res_gross=rg)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", action="store_true")
    args = ap.parse_args()

    d = Data()
    sig = Signals(d)
    end = d.dates[-1]
    costs = Costs(**BASE_COSTS)
    results = {"assumptions": BASE_COSTS, "period": [START, end], "rows": {}}

    periods = [("full", START, end)]
    if args.split:
        periods += [("IS", START, IS_END), ("OOS", OOS_START, end)]

    for pname, ps, pe in periods:
        print("\n" + "=" * 118)
        print(f"PERIOD {pname}: {ps} -> {pe}   (costs: borrow SOXL "
              f"{BASE_COSTS['borrow_soxl']*100:.1f}%/yr, SOXS "
              f"{BASE_COSTS['borrow_soxs']*100:.1f}%/yr)")
        print("=" * 118)
        hdr = (f"{'variant':<38}{'CAGRn':>7}{'CAGRg':>7}{'vol':>7}{'Shrp':>6}"
               f"{'Sort':>6}{'maxDD':>8}{'Calm':>6}{'bSOXX':>7}{'bSPY':>6}"
               f"{'trd/y':>7}{'turn':>6}{'wrst12m':>9}{'PMmax':>7}")
        print(hdr)
        print("-" * 118)
        rows = {}
        for key, label, kw in build_variants(d, sig):
            res = run_backtest(d, ps, pe, costs=costs, label=label, **kw)
            res_g = run_backtest(d, ps, pe, costs=ZERO_COSTS, label=label, **kw)
            s = summarize(res, d, ps, pe, label, res_gross=res_g)
            if not s:
                print(f"{key+' '+label:<38}{'no result':>7}")
                continue
            rows[key] = s
            flag = ""
            if s["BlownUp"]:
                flag = "  <-- WIPED OUT"
            elif s["MarginCalls"]:
                flag = f"  <-- {s['MarginCalls']} margin calls"
            print(f"{key+' '+label:<38}"
                  f"{s['CAGR']*100:>6.1f}%{s['CAGR_gross']*100:>6.1f}%"
                  f"{s['Vol']*100:>6.1f}%{s['Sharpe']:>6.2f}{s['Sortino']:>6.2f}"
                  f"{s['MaxDD']*100:>7.1f}%{s['Calmar']:>6.2f}"
                  f"{s['BetaSOXX']:>7.2f}{s['BetaSPY']:>6.2f}"
                  f"{s['TradesPerYear']:>7.0f}{s['TurnoverPerYear']:>6.2f}"
                  f"{(s['WorstRoll12m'] or 0)*100:>8.1f}%"
                  f"{s['MarginPM_max']*100:>6.0f}%{flag}")
        print("-" * 118)
        for tag, s in benchmarks(d, ps, pe).items():
            if s:
                rows["BM." + tag] = s
                print(f"{'BM ' + tag:<38}"
                      f"{s['CAGR']*100:>6.1f}%{s['CAGR_gross']*100:>6.1f}%"
                      f"{s['Vol']*100:>6.1f}%{s['Sharpe']:>6.2f}"
                      f"{s['Sortino']:>6.2f}{s['MaxDD']*100:>7.1f}%"
                      f"{s['Calmar']:>6.2f}{s['BetaSOXX']:>7.2f}"
                      f"{s['BetaSPY']:>6.2f}{s['TradesPerYear']:>7.0f}"
                      f"{s['TurnoverPerYear']:>6.2f}"
                      f"{(s['WorstRoll12m'] or 0)*100:>8.1f}%"
                      f"{s['MarginPM_max']*100:>6.0f}%")
        results["rows"][pname] = rows

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
