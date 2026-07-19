"""
Orchestrator: build synthetic series, run the watchdog, emit results + report.

WHAT THIS RUN DOES AND DOES NOT CLAIM
-------------------------------------
DOES  : prove the reconstruction ENGINE against the REAL ETF (synthetic TQQQ vs
        actual TQQQ daily returns, 2010+ overlap), and prove the WATCHDOG can
        both PASS a causal strategy and FAIL a leaky/over-fit one.
DOES NOT: validate "the crash-convexity sleeve". That needs (1) the real
        symphony definition (Step D, not yet run) and (2) real VIX-futures data
        for the vol sleeve. No sleeve-level performance number here is a finding.

v2 -- incorporates the adversarial audit (see AUDIT.md): real reconstruction
test replaces the tautological Sharpe check; deflated Sharpe degeneracy fixed;
look-ahead probe catches same-bar peeking and is wired into evaluate(); Sharpe
is risk-free-adjusted.
"""
from __future__ import annotations

import json
import os
import numpy as np
import pandas as pd

import data
import synth
import watchdog as wd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)


# --------------------------------------------------------------------------- #
# Example strategies -- to exercise the watchdog's discrimination, NOT the sleeve
# --------------------------------------------------------------------------- #
def causal_ma_gate(df: pd.DataFrame) -> pd.Series:
    """Risk-on when YESTERDAY's NDX closed above its trailing 200d avg (causal)."""
    lvl = df["ndx"]
    ma = lvl.rolling(200).mean().shift(1)
    return (lvl.shift(1) > ma).astype(float)


def same_bar_ma_gate(df: pd.DataFrame) -> pd.Series:
    """Uses TODAY's close to trade today -- unimplementable live (same-bar leak)."""
    lvl = df["ndx"]
    ma = lvl.rolling(200).mean()
    return (lvl > ma).astype(float)


def leaky_centered_gate(df: pd.DataFrame) -> pd.Series:
    """Centered average -> secretly uses FUTURE data (classic look-ahead)."""
    lvl = df["ndx"]
    ma = lvl.rolling(200, center=True).mean()
    return (lvl > ma).astype(float)


def strategy_returns(pos: pd.Series, idx_ret: pd.Series) -> pd.Series:
    """Realized daily return of holding `pos` (0/1) through each bar's index move."""
    return (pos.reindex(idx_ret.index) * idx_ret).dropna()


def main():
    results = {"tiers": {}, "engine_validation": {}, "watchdog_discrimination": {},
               "assumption_sensitivity": {}, "notes": []}

    panel = data.load_panel()
    ndx = panel["NASDAQ100"].dropna()
    vix = panel["VIXCLS"].dropna()
    rate = panel["DGS3MO"]              # risk-free, %/yr -> used for excess Sharpe + financing
    ndx_ret = synth.index_returns(ndx)

    # ---- TIER 1: TQQQ = 3x NDX, reconstructed 1986+ (DATA-GROUNDED) ---------- #
    tqqq = synth.reconstruct_leveraged_etf(
        ndx_ret, leverage=3.0, expense_ratio=0.0086,
        financing_rate=rate, borrow_spread=0.004, div_yield=0.006,
    )
    results["tiers"]["tier1_tqqq_3x_ndx"] = {
        "trust": "DATA-GROUNDED (reconstructed from real NDX index, 1986+)",
        "span": [str(tqqq.index.min().date()), str(tqqq.index.max().date())],
        "underlying_ndx_buy_hold": wd.perf_stats(ndx_ret, rf_annual=rate),
        "synthetic_tqqq_buy_hold": wd.perf_stats(tqqq, rf_annual=rate),
    }

    # ---- ENGINE VALIDATION: synthetic TQQQ vs REAL TQQQ (2010+ overlap) ------ #
    # Replaces the old tautological "3x Sharpe <= 1x Sharpe" check with a real
    # tracking test that would catch sign flips / scale errors / mis-specification.
    real_tqqq_ret = data.fetch_yahoo_adjclose("TQQQ").pct_change().dropna()
    track = wd.reconstruction_tracking(tqqq, real_tqqq_ret)
    results["engine_validation"]["synthetic_vs_real_tqqq"] = track
    # Negative control: a sign-flipped engine MUST fail the tracking test.
    flipped = synth.reconstruct_leveraged_etf(
        ndx_ret, leverage=-3.0, expense_ratio=0.0086, financing_rate=rate, borrow_spread=0.004)
    results["engine_validation"]["negative_control_sign_flipped"] = {
        "expect": "FAIL (corr<0)", **wd.reconstruction_tracking(flipped, real_tqqq_ret)}

    # ---- TIER 2: modelled short-vol futures ETF (ILLUSTRATIVE ONLY) ---------- #
    stvix = synth.modelled_short_vol_futures(vix)
    uvxy_lev = synth.apply_leverage_schedule(stvix, synth.UVXY_LEVERAGE_SCHEDULE)
    uvxy_like = (uvxy_lev * stvix - 0.0095 / 252).rename("modelled_uvxy_like").dropna()
    results["tiers"]["tier2_uvxy_like_from_vix_spot"] = {
        "trust": "MODELLED / ILLUSTRATIVE -- built from VIX SPOT, not futures. "
                 "NOT valid for performance claims. Replace with real SPVXSTR/futures.",
        "span": [str(uvxy_like.index.min().date()), str(uvxy_like.index.max().date())],
        "stats_do_not_quote": wd.perf_stats(uvxy_like, rf_annual=rate),
    }

    # ---- WATCHDOG DISCRIMINATION: pass the causal strat, fail the leaky ones -- #
    inputs = pd.DataFrame({"ndx": ndx})
    for name, fn in [("causal_gate", causal_ma_gate),
                     ("same_bar_leak", same_bar_ma_gate),
                     ("centered_future_leak", leaky_centered_gate)]:
        ret = strategy_returns(fn(inputs), ndx_ret)
        rep = wd.evaluate(ret, label=name, n_trials=1, rf_annual=rate,
                          strategy_fn=fn, strategy_inputs=inputs)
        results["watchdog_discrimination"][name] = rep.to_dict()

    # ---- ASSUMPTION SENSITIVITY on the Tier-1 reconstruction ----------------- #
    def build(params):
        return synth.reconstruct_leveraged_etf(
            ndx_ret, leverage=3.0, expense_ratio=params["expense_ratio"],
            financing_rate=rate, borrow_spread=params["borrow_spread"],
            div_yield=params["div_yield"])
    results["assumption_sensitivity"]["tqqq"] = wd.assumption_sensitivity(build, grid={
        "expense_ratio": [0.0070, 0.0086, 0.0110],
        "borrow_spread": [0.002, 0.004, 0.008],
        "div_yield": [0.004, 0.006, 0.008]})

    results["notes"] = [
        "Sharpe/PSR/DSR are RISK-FREE-ADJUSTED (excess over 3M T-bill).",
        "Engine validated against REAL TQQQ on 2010+ overlap; sign-flipped negative "
        "control fails as it must.",
        "Tier-2 vol sleeve is MODELLED from VIX spot -- illustrative only, never quoted.",
        "KNOWN UNMODELLED BIASES: NDX survivorship/quarterly reconstitution is inside the "
        "Tier-1 index; no transaction-cost/turnover/slippage on traded strategies; "
        "walk_forward here measures early-vs-late regime stability, not refit-per-fold.",
        "No result validates the actual crash-convexity SLEEVE: needs the real symphony "
        "definition (Step D) and real VIX-futures/SPVXSTR data.",
    ]

    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Wrote", os.path.join(OUT, "results.json"))

    # Console summary
    t1 = results["tiers"]["tier1_tqqq_3x_ndx"]
    print("\n=== ENGINE VALIDATION: synthetic vs REAL TQQQ (2010+ overlap) ===")
    print(" ", track)
    print("  negative control (sign-flipped) passed?:",
          results["engine_validation"]["negative_control_sign_flipped"]["passed"])
    print("\n=== TIER 1  NDX -> synthetic TQQQ (excess-Sharpe, 1986+) ===")
    print("  NDX  buy&hold:", t1["underlying_ndx_buy_hold"])
    print("  TQQQ buy&hold:", t1["synthetic_tqqq_buy_hold"])
    print("\n=== WATCHDOG DISCRIMINATION (must fail the leaks) ===")
    for name in ["causal_gate", "same_bar_leak", "centered_future_leak"]:
        r = results["watchdog_discrimination"][name]
        print(f"  {name:22s} causal={r['lookahead'].get('causal')}"
              f" violations={r['lookahead'].get('lookahead_violations')}"
              f" flags={len(r['flags'])}")
        for fl in r["flags"]:
            print("       -", fl)
    s = results["assumption_sensitivity"]["tqqq"]
    print("\n=== ASSUMPTION SENSITIVITY  sharpe_range:", s["sharpe_range"], "spread:", s["sharpe_spread"])
    return results


if __name__ == "__main__":
    main()
