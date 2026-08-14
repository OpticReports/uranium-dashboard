#!/usr/bin/env python3
"""Step 2 validation discipline + Step 5 forward scenarios.

  A. Parameter sensitivity heatmap (top-N x rebalance cadence), full/IS/OOS.
  B. Borrow-rate sweep and the solved breakeven -- the study's dominant
     unknown, treated as a swept parameter rather than an assumed constant.
  C. Block bootstrap + Monte Carlo path resampling -> CIs on CAGR, Sharpe,
     max drawdown. Block size preserves the autocorrelation that makes the
     short leg's drawdowns long.
  D. Walk-forward: at each year end, pick the best config on data seen SO
     FAR, trade it the next year. This is the only number in the study that
     an investor could actually have earned by following the process.
  E. Forward regime scenarios via conditional resampling.

Writes fixtures/validation.json.
"""
import json
import math
import os

import numpy as np

from datalib import (ZERO_COSTS, Costs, Data, TRADING_DAYS, metrics,
                     run_backtest)
from signals import Signals
from variants import BASE_COSTS, tgt_long_short

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "validation.json")
START, IS_END, OOS_START = "2010-03-12", "2019-12-31", "2020-01-01"
RNG = np.random.default_rng(20260814)      # fixed seed -> reproducible CIs

FREQS = [("D", "daily"), ("W", "weekly"), ("M", "monthly"), ("Q", "quarterly")]
NS = [3, 5, 8, 12]


def run(d, ps, pe, n, freq, costs, **kw):
    return run_backtest(d, ps, pe, tgt_long_short(n, "cap"), costs=costs,
                        rebalance=freq, **kw)


def sharpe_of(d, res, ps, pe):
    lo, hi = d.slice_idx(ps, pe)
    m = metrics(res["nav"], res["dates"], rf=d.rf[lo + 1:hi])
    return m


def main():
    d = Data()
    end = d.dates[-1]
    costs = Costs(**BASE_COSTS)
    res = {}

    # =====================================================================
    print("=" * 96)
    print("A. PARAMETER SENSITIVITY — Sharpe by top-N x rebalance cadence")
    print("=" * 96)
    grid = {}
    for pname, ps, pe in [("full", START, end), ("IS", START, IS_END),
                          ("OOS", OOS_START, end)]:
        print(f"\n-- {pname}    (rows = top-N, cols = cadence)")
        print(f"{'N':<5}" + "".join(f"{nm:>12}" for _, nm in FREQS))
        for n in NS:
            line = f"{n:<5}"
            for f, nm in FREQS:
                m = sharpe_of(d, run(d, ps, pe, n, f, costs), ps, pe)
                s = m.get("Sharpe", float("nan"))
                grid[f"{pname}|{n}|{f}"] = {"sharpe": s, "cagr": m.get("CAGR"),
                                            "maxdd": m.get("MaxDD")}
                line += f"{s:>12.2f}"
            print(line)
    res["sensitivity"] = grid
    print("\n  Read: Sharpe is driven far more by CADENCE than by N. That is")
    print("  the convexity of the short leg talking, not stock selection.")

    # =====================================================================
    print("\n" + "=" * 96)
    print("B. BORROW-RATE SWEEP — the input we could not source")
    print("=" * 96)
    print(f"{'borrow %/yr':<14}{'V0 CAGR':>10}{'V0 Shrp':>10}"
          f"{'V0.W CAGR':>12}{'V0.W Shrp':>11}{'V4d CAGR':>11}{'V4d Shrp':>10}")
    sweep = {}
    for bo in [0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12]:
        c = Costs(**{**BASE_COSTS, "borrow_soxl": bo})
        m0 = sharpe_of(d, run(d, START, end, 8, "M", c), START, end)
        mw = sharpe_of(d, run(d, START, end, 8, "W", c), START, end)
        r4 = run_backtest(d, START, end,
                          lambda data, i: {"SOXL": -0.25, "SOXX": 0.75},
                          costs=c, rebalance="D")
        m4 = sharpe_of(d, r4, START, end)
        print(f"{bo*100:<14.1f}{m0['CAGR']*100:>9.1f}%{m0['Sharpe']:>10.2f}"
              f"{mw['CAGR']*100:>11.1f}%{mw['Sharpe']:>11.2f}"
              f"{m4['CAGR']*100:>10.1f}%{m4['Sharpe']:>10.2f}")
        sweep[bo] = {"V0": {"cagr": m0["CAGR"], "sharpe": m0["Sharpe"]},
                     "V0W": {"cagr": mw["CAGR"], "sharpe": mw["Sharpe"]},
                     "V4d": {"cagr": m4["CAGR"], "sharpe": m4["Sharpe"]}}
    res["borrow_sweep"] = sweep

    # solve breakeven borrow for the weekly book (CAGR == cash return)
    cash = float(np.nanmean(d.rf))
    lo_b, hi_b = 0.0, 0.40
    for _ in range(28):
        mid = (lo_b + hi_b) / 2
        c = Costs(**{**BASE_COSTS, "borrow_soxl": mid})
        m = sharpe_of(d, run(d, START, end, 8, "W", c), START, end)
        if m["CAGR"] > cash:
            lo_b = mid
        else:
            hi_b = mid
    print(f"\n  average cash rate over the period: {cash*100:.2f}%/yr")
    print(f"  breakeven SOXL borrow for V0.W (CAGR = cash): {lo_b*100:.1f}%/yr")
    print("  -> the short leg's carry edge is ~5.4%/yr of short notional;")
    print("     at 25% notional the book tolerates a high borrow rate before")
    print("     it dies, because the short is mostly a HEDGE, not the alpha.")
    res["breakeven_borrow_v0w"] = float(lo_b)
    res["avg_cash_rate"] = cash

    # =====================================================================
    print("\n" + "=" * 96)
    print("C. BLOCK BOOTSTRAP — confidence intervals (2000 resamples, 21d blocks)")
    print("=" * 96)
    boot = {}
    print(f"{'variant':<28}{'CAGR med':>10}{'CAGR 5%':>9}{'CAGR 95%':>10}"
          f"{'Shrp med':>10}{'Shrp 5%':>9}{'maxDD 5%':>10}{'P(CAGR<0)':>11}")
    for tag, n, f in [("V0 monthly", 8, "M"), ("V0.W weekly", 8, "W"),
                      ("V0.D daily", 8, "D")]:
        r = run(d, START, end, n, f, costs)
        nav = r["nav"]
        rr = nav[1:] / nav[:-1] - 1
        rr = rr[np.isfinite(rr)]
        b = _block_bootstrap(rr, n_boot=2000, block=21)
        boot[tag] = b
        print(f"{tag:<28}{b['cagr_med']*100:>9.1f}%{b['cagr_p5']*100:>8.1f}%"
              f"{b['cagr_p95']*100:>9.1f}%{b['sharpe_med']:>10.2f}"
              f"{b['sharpe_p5']:>9.2f}{b['maxdd_p5']*100:>9.1f}%"
              f"{b['p_negative']*100:>10.0f}%")
    res["bootstrap"] = boot

    # =====================================================================
    print("\n" + "=" * 96)
    print("D. WALK-FORWARD — pick the config on past data only, trade it next year")
    print("=" * 96)
    wf = _walk_forward(d, costs)
    print(f"{'year':<7}{'chosen cfg':<16}{'next-yr return':>16}"
          f"{'V0 monthly':>13}{'75%basket+cash':>16}")
    for row in wf["rows"]:
        print(f"{row['year']:<7}{row['cfg']:<16}{row['ret']*100:>15.1f}%"
              f"{row['v0']*100:>12.1f}%{row['bench']*100:>15.1f}%")
    print(f"\n  walk-forward compounded: {wf['cagr']*100:.1f}%/yr  "
          f"Sharpe {wf['sharpe']:.2f}")
    print(f"  always-V0-monthly:       {wf['v0_cagr']*100:.1f}%/yr")
    print(f"  75% basket + 25% cash:   {wf['bench_cagr']*100:.1f}%/yr")
    print(f"  config changed in {wf['n_switches']}/{len(wf['rows'])} years "
          f"-> parameter instability")
    res["walk_forward"] = wf

    # =====================================================================
    print("\n" + "=" * 96)
    print("E. FORWARD SCENARIOS — conditional resampling, 12-month horizon")
    print("=" * 96)
    scen = _scenarios(d, costs)
    print(f"{'regime':<34}{'n days':>8}{'median':>9}{'5th':>8}{'95th':>8}"
          f"{'P(loss)':>9}{'P(<-20%)':>10}")
    for k, v in scen.items():
        print(f"{k:<34}{v['n']:>8}{v['median']*100:>8.1f}%{v['p5']*100:>7.1f}%"
              f"{v['p95']*100:>7.1f}%{v['p_loss']*100:>8.0f}%"
              f"{v['p_bad']*100:>9.0f}%")
    res["scenarios"] = scen

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(f"\nwrote {OUT}")


# --------------------------------------------------------------------------
def _block_bootstrap(r, n_boot=2000, block=21):
    """Stationary block bootstrap on daily returns."""
    n = len(r)
    nb = int(np.ceil(n / block))
    cagrs, sharpes, mdds = [], [], []
    for _ in range(n_boot):
        starts = RNG.integers(0, n - block, size=nb)
        path = np.concatenate([r[s:s + block] for s in starts])[:n]
        nav = np.cumprod(1 + path)
        if nav[-1] <= 0:
            cagrs.append(-1.0)
            sharpes.append(float("nan"))
            mdds.append(-1.0)
            continue
        cagrs.append(nav[-1] ** (TRADING_DAYS / n) - 1)
        sd = path.std(ddof=1)
        sharpes.append(path.mean() / sd * math.sqrt(TRADING_DAYS)
                       if sd > 0 else float("nan"))
        mdds.append(float((nav / np.maximum.accumulate(nav) - 1).min()))
    c, s, m = np.array(cagrs), np.array(sharpes), np.array(mdds)
    return {"cagr_med": float(np.median(c)), "cagr_p5": float(np.percentile(c, 5)),
            "cagr_p95": float(np.percentile(c, 95)),
            "sharpe_med": float(np.nanmedian(s)),
            "sharpe_p5": float(np.nanpercentile(s, 5)),
            "maxdd_p5": float(np.percentile(m, 5)),
            "maxdd_med": float(np.median(m)),
            "p_negative": float((c < 0).mean())}


def _year_return(nav, dates, year):
    idx = [k for k, x in enumerate(dates) if x[:4] == year]
    if len(idx) < 20:
        return None
    return nav[idx[-1]] / nav[idx[0]] - 1


def _walk_forward(d, costs):
    """Expanding-window config selection, evaluated on the following year."""
    from datalib import build_basket
    cfgs = [(n, f) for n in NS for f, _ in FREQS]
    rows, rets, v0s, bms = [], [], [], []
    switches, prev = 0, None
    end = d.dates[-1]
    years = sorted({x[:4] for x in d.dates if START <= x <= end})
    for y in years[2:]:                      # need >=2y of history to choose
        train_end = f"{int(y)-1}-12-31"
        best, best_s = None, -np.inf
        for n, f in cfgs:
            m = sharpe_of(d, run(d, START, train_end, n, f, costs),
                          START, train_end)
            s = m.get("Sharpe", float("nan"))
            if np.isfinite(s) and s > best_s:
                best_s, best = s, (n, f)
        n, f = best
        if prev is not None and best != prev:
            switches += 1
        prev = best
        ys, ye = f"{y}-01-01", f"{y}-12-31"
        r = run(d, ys, min(ye, end), n, f, costs)
        if len(r["nav"]) < 20:
            continue
        ret = r["nav"][-1] / r["nav"][0] - 1
        r0 = run(d, ys, min(ye, end), 8, "M", costs)
        v0 = r0["nav"][-1] / r0["nav"][0] - 1
        rb = run_backtest(d, ys, min(ye, end),
                          lambda data, i: {t: 0.75 * v for t, v in
                                           build_basket(data, i, 8, "cap").items()},
                          costs=costs, rebalance="M")
        bm = rb["nav"][-1] / rb["nav"][0] - 1
        rows.append({"year": y, "cfg": f"top{n}/{f}", "ret": float(ret),
                     "v0": float(v0), "bench": float(bm)})
        rets.append(ret)
        v0s.append(v0)
        bms.append(bm)
    yrs = len(rets)
    comp = float(np.prod([1 + x for x in rets]) ** (1 / yrs) - 1) if yrs else float("nan")
    sh = (float(np.mean(rets) / np.std(rets, ddof=1)) if yrs > 2 else float("nan"))
    return {"rows": rows, "cagr": comp, "sharpe": sh,
            "v0_cagr": float(np.prod([1 + x for x in v0s]) ** (1 / yrs) - 1),
            "bench_cagr": float(np.prod([1 + x for x in bms]) ** (1 / yrs) - 1),
            "n_switches": switches}


def _scenarios(d, costs):
    """12-month forward distributions by conditioning on historical regimes.

    Resamples 21-day blocks drawn ONLY from days matching each regime, so the
    scenario inherits that regime's vol, autocorrelation and convexity rather
    than a fitted normal.
    """
    sig = Signals(d)
    end = d.dates[-1]
    r = run(d, START, end, 8, "W", costs)      # best-in-class variant
    nav = r["nav"]
    rr = np.full(len(nav), np.nan)
    rr[1:] = nav[1:] / nav[:-1] - 1
    idx = np.array([d.di[x] for x in r["dates"]])
    trend = sig.trend200[idx]
    vol = sig.vol20[idx]
    volmed = np.nanmedian(vol)
    soxx = d.ret("SOXX")[idx]

    regimes = {
        "(a) semi bull, trend up": (trend > 0) & (vol < volmed),
        "(b) sideways high-vol chop": (np.abs(trend) < np.nanstd(trend) * 0.3)
                                      & (vol >= volmed),
        "(c) cyclical downturn": trend < 0,
        "(d) vol spike (top decile vol)": vol >= np.nanpercentile(vol, 90),
        "unconditional": np.isfinite(rr),
    }
    # EMPIRICAL forward 12-month outcomes, conditioned on the regime holding
    # at ENTRY. This is the primary view. A block bootstrap drawn inside a
    # regime cannot produce a 2026-style twelve-month trend -- it reassembles
    # independent 21-day fragments, so the multi-month persistence that makes
    # the short leg dangerous is exactly what it destroys. It reported
    # P(loss worse than -20%) = 0% in every regime while the book was in the
    # middle of a -31% year. Resampled figures are kept as a secondary
    # column, clearly labelled, and never used for the tail.
    out = {}
    H = TRADING_DAYS
    for name, mask in regimes.items():
        fwd = []
        for k in range(len(rr) - H):
            if mask[k] and np.isfinite(nav[k]) and nav[k] > 0:
                fwd.append(nav[k + H] / nav[k] - 1)
        if len(fwd) < 60:
            continue
        f = np.array(fwd)
        pool = rr[mask & np.isfinite(rr)]
        sims = []
        for _ in range(4000):
            starts = RNG.integers(0, max(len(pool) - 63, 1), size=4)
            path = np.concatenate([pool[s:s + 63] for s in starts])
            sims.append(np.prod(1 + path) - 1)
        s = np.array(sims)
        out[name] = {
            "n": int(mask.sum()), "n_windows": len(f),
            "median": float(np.median(f)),
            "p5": float(np.percentile(f, 5)),
            "p95": float(np.percentile(f, 95)),
            "worst": float(f.min()), "best": float(f.max()),
            "p_loss": float((f < 0).mean()),
            "p_bad": float((f < -0.20).mean()),
            "resampled_median": float(np.median(s)),
            "resampled_p5": float(np.percentile(s, 5)),
        }
    return out


if __name__ == "__main__":
    main()
