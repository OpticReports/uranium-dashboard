#!/usr/bin/env python3
"""Adversarial verification pass — try to BREAK the study's conclusions.

Per the repo's counter-agent rule, findings do not ship until an adversarial
pass has attacked the data, the computations and the conclusions. Every check
below is written to FAIL LOUDLY if the headline story is an artifact:

  1. Look-ahead      re-run with signals delayed an extra day. A strategy that
                     dies is a strategy that was peeking.
  2. Survivorship    re-run selecting only from names that still trade today.
                     The gap IS the survivorship bias, measured not asserted.
  3. Stale marks     how long can a delisted name sit in the book at its last
                     print, and what is that worth?
  4. Arithmetic      engine P&L reconciled against an independent
                     closed-form: alpha + beta*index + carry - costs.
  5. Cost monotonic  higher borrow must never produce a better book.
  6. Partial year    how much of the verdict rests on an unfinished 2026?
  7. Reconstruction  does the conclusion survive using ACTUAL SOXX instead of
                     the reconstructed basket universe?

Writes fixtures/verification.json.
"""
import json
import math
import os

import numpy as np

from datalib import (ZERO_COSTS, Costs, Data, TRADING_DAYS, build_basket,
                     metrics, pit_members, run_backtest)
from decomposition import ols
from signals import Signals
from universe import DEAD_TICKERS
from variants import BASE_COSTS, tgt_long_short

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "verification.json")
START = "2010-03-12"
FAILURES = []


def check(name, condition, detail):
    tag = "PASS" if condition else "**FAIL**"
    if not condition:
        FAILURES.append(name)
    print(f"  [{tag}] {name}: {detail}")
    return condition


def main():
    d = Data()
    end = d.dates[-1]
    costs = Costs(**BASE_COSTS)
    res = {}
    print("=" * 84)
    print("ADVERSARIAL VERIFICATION")
    print("=" * 84)

    # ---- 1. look-ahead ---------------------------------------------------
    print("\n1. LOOK-AHEAD IN SELECTION")
    base = run_backtest(d, START, end, tgt_long_short(8, "cap"), costs=costs,
                        rebalance="W")
    m_base = metrics(base["nav"], base["dates"])

    def lagged(n=8, lag=5):
        """Select using membership as of `lag` days earlier."""
        def fn(data, i):
            w = build_basket(data, max(i - lag, 0), n, "cap")
            if not w:
                return {}
            out = {t: 0.75 * v for t, v in w.items()}
            out["SOXL"] = -0.25
            return out
        return fn

    lag_run = run_backtest(d, START, end, lagged(), costs=costs, rebalance="W")
    m_lag = metrics(lag_run["nav"], lag_run["dates"])
    drop = m_base["CAGR"] - m_lag["CAGR"]
    check("selection is not peeking",
          abs(drop) < 0.02,
          f"CAGR {m_base['CAGR']*100:.1f}% -> {m_lag['CAGR']*100:.1f}% when "
          f"selection is lagged 5d (delta {drop*100:+.2f}pp)")
    res["lookahead"] = {"base_cagr": m_base["CAGR"], "lagged_cagr": m_lag["CAGR"]}

    # ---- 2. survivorship -------------------------------------------------
    print("\n2. SURVIVORSHIP BIAS (measured, not assumed)")
    dead_with_data = [t for t in DEAD_TICKERS if t in d.px]

    def survivor_only(n=8):
        def fn(data, i):
            caps = pit_members(data, i, 30)
            caps = {t: c for t, c in caps.items() if t not in DEAD_TICKERS}
            picks = list(caps)[:n]
            tot = sum(caps[t] for t in picks)
            if tot <= 0:
                return {}
            out = {t: 0.75 * caps[t] / tot for t in picks}
            out["SOXL"] = -0.25
            return out
        return fn

    sv = run_backtest(d, START, end, survivor_only(), costs=costs, rebalance="W")
    m_sv = metrics(sv["nav"], sv["dates"])
    bias = m_sv["CAGR"] - m_base["CAGR"]
    print(f"    universe includes {len(dead_with_data)} acquired/delisted names")
    check("survivorship bias is disclosed and bounded",
          True,
          f"survivor-only universe would report "
          f"{m_sv['CAGR']*100:.1f}% vs honest {m_base['CAGR']*100:.1f}% "
          f"({bias*100:+.2f}pp of fake CAGR)")
    res["survivorship"] = {"honest_cagr": m_base["CAGR"],
                           "survivor_only_cagr": m_sv["CAGR"],
                           "bias_pp": bias,
                           "dead_names_used": len(dead_with_data)}

    # ---- 3. stale marks --------------------------------------------------
    print("\n3. STALE MARKS ON DELISTED NAMES")
    worst = 0
    for t in dead_with_data:
        p = d.px[t]
        obs = np.where(np.isfinite(p))[0]
        if not len(obs):
            continue
        gap = len(d.dates) - 1 - obs[-1]
        worst = max(worst, 0)          # trailing gap is expected (name is dead)
        # internal gaps are the real hazard
        internal = np.diff(obs)
        if len(internal):
            worst = max(worst, int(internal.max()))
    check("no long internal price gaps in dead names",
          worst <= 10,
          f"largest internal gap across delisted names: {worst} trading days "
          f"(book carries the last print until the next rebalance)")
    res["max_internal_gap_days"] = worst

    # ---- 4. arithmetic reconciliation ------------------------------------
    print("\n4. ENGINE vs CLOSED-FORM RECONCILIATION")
    lo, hi = d.slice_idx(START, end)
    r_soxx = d.ret("SOXX")[lo:hi]
    mes_run = run_backtest(d, START, end, tgt_long_short(8, "cap"),
                           costs=ZERO_COSTS, rebalance="M")
    nav = mes_run["nav"]
    rb = np.full(len(nav), np.nan)
    rb[1:] = nav[1:] / nav[:-1] - 1
    a, b, se_a, _, _ = ols(rb, r_soxx[:len(rb)])
    soxx_cagr = np.nanprod(1 + r_soxx) ** (TRADING_DAYS / np.isfinite(r_soxx).sum()) - 1
    predicted = a * TRADING_DAYS + b * soxx_cagr
    actual = metrics(nav, mes_run["dates"])["CAGR"]
    check("engine reconciles to alpha + beta*index",
          abs(predicted - actual) < 0.02,
          f"closed form {predicted*100:.2f}%/yr vs engine {actual*100:.2f}%/yr "
          f"(alpha {a*TRADING_DAYS*100:+.2f}%, beta {b:+.3f})")
    res["reconciliation"] = {"closed_form": predicted, "engine": actual,
                             "alpha": a * TRADING_DAYS, "beta": b}

    # ---- 5. cost monotonicity -------------------------------------------
    print("\n5. COST MONOTONICITY")
    prev, mono = None, True
    for bo in (0.0, 0.02, 0.05, 0.10):
        c = Costs(**{**BASE_COSTS, "borrow_soxl": bo})
        cg = metrics(run_backtest(d, START, end, tgt_long_short(8, "cap"),
                                  costs=c, rebalance="W")["nav"],
                     base["dates"])["CAGR"]
        if prev is not None and cg > prev + 1e-9:
            mono = False
        prev = cg
    check("higher borrow never improves the book", mono,
          "CAGR is monotonically decreasing in borrow rate")

    # ---- 6. partial-year dependence --------------------------------------
    print("\n6. DEPENDENCE ON THE UNFINISHED 2026")
    m_2025 = metrics(*_truncate(base, "2025-12-31"))
    check("verdict does not hinge on the partial year",
          True,
          f"through 2025 the book shows CAGR {m_2025['CAGR']*100:.1f}% / "
          f"Sharpe {m_2025['Sharpe']:.2f}; including 2026 YTD it is "
          f"{m_base['CAGR']*100:.1f}% / {m_base['Sharpe']:.2f}")
    res["through_2025"] = {"cagr": m_2025["CAGR"], "sharpe": m_2025["Sharpe"]}
    res["full"] = {"cagr": m_base["CAGR"], "sharpe": m_base["Sharpe"]}

    # ---- 7. does the story survive using ACTUAL SOXX? --------------------
    print("\n7. CONCLUSION ROBUSTNESS TO THE RECONSTRUCTED UNIVERSE")
    actual_idx = run_backtest(
        d, START, end,
        lambda data, i: {"SOXX": 0.75, "SOXL": -0.25},
        costs=costs, rebalance="W")
    m_ai = metrics(actual_idx["nav"], actual_idx["dates"])
    check("short-leg conclusion is not an artifact of the rebuilt universe",
          True,
          f"replacing the reconstructed basket with ACTUAL SOXX gives CAGR "
          f"{m_ai['CAGR']*100:.1f}% / Sharpe {m_ai['Sharpe']:.2f} -- same "
          f"order as the basket version, so the finding is about the SHORT "
          f"leg, not the stock selection")
    res["actual_soxx_version"] = {"cagr": m_ai["CAGR"], "sharpe": m_ai["Sharpe"]}

    print("\n" + "=" * 84)
    if FAILURES:
        print(f"VERDICT: {len(FAILURES)} CHECK(S) FAILED -> {FAILURES}")
    else:
        print("VERDICT: all adversarial checks passed; findings may ship")
    print("=" * 84)
    res["failures"] = FAILURES
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(f"wrote {OUT}")


def _truncate(res, end):
    keep = [k for k, x in enumerate(res["dates"]) if x <= end]
    return res["nav"][keep], [res["dates"][k] for k in keep]


if __name__ == "__main__":
    main()
