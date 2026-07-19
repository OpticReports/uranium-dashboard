"""
Orchestrator: build synthetic series, run the watchdog, emit results + report.

WHAT THIS RUN DOES AND DOES NOT CLAIM
-------------------------------------
DOES  : prove the reconstruction ENGINE and the WATCHDOG work, on real
        data (NDX 1986+) and on a transparent example strategy.
DOES  : show the look-ahead probe distinguishing a causal gate from a leaky one.
DOES NOT: validate "the crash-convexity sleeve". That needs (1) the real
        symphony definition (Step D, not yet run) and (2) real VIX-futures data
        for the vol sleeve. Until both exist, no sleeve-level performance number
        here should be treated as a finding. The report says so, loudly.
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
# Example strategies (ONLY to exercise the look-ahead probe -- not the sleeve)
# --------------------------------------------------------------------------- #
def causal_ma_gate(df: pd.DataFrame) -> pd.Series:
    """Risk-on when yesterday's NDX closed above its trailing 200d avg (causal)."""
    lvl = df["ndx"]
    ma = lvl.rolling(200).mean().shift(1)
    return (lvl.shift(1) > ma).astype(float)


def leaky_ma_gate(df: pd.DataFrame) -> pd.Series:
    """Same idea but with a CENTERED average -> secretly uses future data."""
    lvl = df["ndx"]
    ma = lvl.rolling(200, center=True).mean()
    return (lvl > ma).astype(float)


def main():
    results = {"tiers": {}, "engine_demo": {}, "lookahead_demo": {}, "notes": []}

    panel = data.load_panel()
    ndx = panel["NASDAQ100"].dropna()
    vix = panel["VIXCLS"].dropna()
    rate = panel["DGS3MO"]
    ndx_ret = synth.index_returns(ndx)

    # ---- TIER 1: TQQQ = 3x NDX, reconstructed 1986+ (DATA-GROUNDED) ---------- #
    tqqq = synth.reconstruct_leveraged_etf(
        ndx_ret, leverage=3.0, expense_ratio=0.0086,
        financing_rate=rate, borrow_spread=0.004, div_yield=0.006,
    )
    ndx_stats = wd.perf_stats(ndx_ret)
    tqqq_stats = wd.perf_stats(tqqq)
    results["tiers"]["tier1_tqqq_3x_ndx"] = {
        "trust": "DATA-GROUNDED (reconstructed from real NDX index, 1986+)",
        "span": [str(tqqq.index.min().date()), str(tqqq.index.max().date())],
        "underlying_ndx_buy_hold": ndx_stats,
        "synthetic_tqqq_buy_hold": tqqq_stats,
        "volatility_drag_check": {
            "note": "3x buy-hold Sharpe should be <= 1x Sharpe due to daily-reset drag; "
                    "if synthetic 3x shows HIGHER Sharpe than 1x, the engine is wrong.",
            "ndx_sharpe": ndx_stats["sharpe"],
            "tqqq_sharpe": tqqq_stats["sharpe"],
            "engine_sane": tqqq_stats["sharpe"] <= ndx_stats["sharpe"] + 1e-9,
        },
    }

    # ---- TIER 2: modelled short-vol futures ETF (ILLUSTRATIVE ONLY) ---------- #
    stvix = synth.modelled_short_vol_futures(vix)
    uvxy_lev = synth.apply_leverage_schedule(stvix, synth.UVXY_LEVERAGE_SCHEDULE)
    uvxy_like = (uvxy_lev * stvix - 0.0095 / 252).rename("modelled_uvxy_like").dropna()
    results["tiers"]["tier2_uvxy_like_from_vix_spot"] = {
        "trust": "MODELLED / ILLUSTRATIVE -- built from VIX SPOT, not futures. "
                 "NOT valid for performance claims. Replace with real SPVXSTR/futures.",
        "span": [str(uvxy_like.index.min().date()), str(uvxy_like.index.max().date())],
        "stats_do_not_quote": wd.perf_stats(uvxy_like),
    }

    # ---- ENGINE + WATCHDOG demonstration on the real Tier-1 series ----------- #
    # We run the skeptic battery on synthetic TQQQ buy-and-hold. This validates
    # the machinery on a series we understand; it is NOT a strategy endorsement.
    rep = wd.evaluate(tqqq, label="synthetic_TQQQ_buy_and_hold", n_trials=1)
    results["engine_demo"]["watchdog_on_tqqq_buy_hold"] = rep.to_dict()

    # Assumption sensitivity: does the reconstruction's Sharpe depend on the soft
    # financing / fee / dividend inputs we had to assume?
    def build(params):
        return synth.reconstruct_leveraged_etf(
            ndx_ret, leverage=3.0,
            expense_ratio=params["expense_ratio"],
            financing_rate=rate,
            borrow_spread=params["borrow_spread"],
            div_yield=params["div_yield"],
        )
    sens = wd.assumption_sensitivity(build, grid={
        "expense_ratio": [0.0070, 0.0086, 0.0110],
        "borrow_spread": [0.002, 0.004, 0.008],
        "div_yield": [0.004, 0.006, 0.008],
    })
    results["engine_demo"]["assumption_sensitivity_tqqq"] = sens

    # ---- LOOK-AHEAD PROBE demonstration: causal vs leaky ---------------------- #
    inputs = pd.DataFrame({"ndx": ndx})
    causal = wd.lookahead_probe(causal_ma_gate, inputs)
    leaky = wd.lookahead_probe(leaky_ma_gate, inputs)
    results["lookahead_demo"] = {
        "causal_200d_gate": causal,
        "leaky_centered_gate": leaky,
        "probe_works": (causal["causal"] is True) and (leaky["causal"] is False),
        "interpretation": "The probe must PASS the causal gate and FAIL the leaky one. "
                          "If probe_works is true, the look-ahead detector is functioning.",
    }

    results["notes"] = [
        "Tier-1 (NDX->TQQQ) is data-grounded to 1986 and is the trustworthy engine demo.",
        "Tier-2 (vol sleeve) is MODELLED from VIX spot -- illustrative only, do not quote.",
        "No result here validates the actual crash-convexity SLEEVE: the real symphony "
        "definition (Step D) and real VIX-futures/SPVXSTR data are both still required.",
        "The watchdog raised the flags listed under engine_demo.watchdog_on_tqqq_buy_hold.flags.",
    ]

    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("Wrote", os.path.join(OUT, "results.json"))

    # Console summary
    print("\n=== TIER 1  NDX -> synthetic TQQQ (data-grounded, 1986+) ===")
    print("  NDX  buy&hold:", ndx_stats)
    print("  TQQQ buy&hold:", tqqq_stats)
    print("  engine sane (3x Sharpe <= 1x Sharpe):",
          results["tiers"]["tier1_tqqq_3x_ndx"]["volatility_drag_check"]["engine_sane"])
    print("\n=== WATCHDOG on synthetic TQQQ buy&hold ===")
    print("  PSR:", rep.probabilistic_sharpe, " DSR:", rep.deflated_sharpe)
    print("  bootstrap:", rep.bootstrap)
    print("  walk-forward:", rep.walk_forward)
    print("  flags:", rep.flags or "none")
    print("\n=== LOOK-AHEAD PROBE (must catch the leaky one) ===")
    print("  causal gate causal? ", causal["causal"], "violations:", causal["lookahead_violations"])
    print("  leaky  gate causal? ", leaky["causal"], "violations:", leaky["lookahead_violations"])
    print("  probe_works:", results["lookahead_demo"]["probe_works"])
    print("\n=== ASSUMPTION SENSITIVITY (Sharpe spread across soft inputs) ===")
    print("  sharpe_range:", sens["sharpe_range"], " spread:", sens["sharpe_spread"])
    return results


if __name__ == "__main__":
    main()
