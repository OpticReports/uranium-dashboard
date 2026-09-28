"""The answer table: what notional this book supports, and what binds it.

Pulls the measured numbers from the three prior scripts and resolves them into
the one question Casey asked - how big can the trades be - plus the chart that
carries the divergence between the full sample and the single-touch holdout.

Usage: python3 scale_answer.py    (run after scale_ladder / lever_sweep /
                                   kelly_headroom)
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from scale_ladder import (EQUITY, LEV, MAX_ACCOUNT_LEV, MAX_NOTIONAL_USD,   # noqa: E402
                          SIZING_BASE_USD, KELLY_M_LIVE, DD_HALT_PCT,
                          MAX_EXPOSURE_FRAC, curve, expo, _gross, perf, trades)

LAD = json.load(open(os.path.join(HERE, "ladder_findings.json")))
LEVR = json.load(open(os.path.join(HERE, "lever_findings.json")))
KH = json.load(open(os.path.join(HERE, "kelly_headroom.json")))
SC = json.load(open(os.path.join(HERE, "scale_findings.json")))
A: dict = {}

K_LIVE = LAD["live_position_on_the_ladder"]["k_live_effective_kelly_multiple"]
KMAX_F = LEVR["lever1_voltarget"]["kmax_at_P_dd30_le_10pct"]["FIXED"]
KMAX_V = LEVR["lever1_voltarget"]["kmax_at_P_dd30_le_10pct"]["VOLTARGET"]
GROSS_PER_EQUITY_AT_DDBUDGET = KMAX_F * LEV     # gross notional per $1 equity


def main() -> None:
    ev, _ = trades()
    r = ev["r"].to_numpy()
    e1 = expo(ev, 1.0, "FIXED")
    R_LEG = {lg: float((e1 * ev["s"].to_numpy())[(ev.leg == lg).to_numpy()].mean())
             for lg in ("pullback", "trend")}

    # ---- the config arithmetic, stated exactly ---------------------------
    want_pb = KELLY_M_LIVE * LEV * 0.75 * SIZING_BASE_USD
    want_tr = KELLY_M_LIVE * LEV * 0.25 * SIZING_BASE_USD
    cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV * SIZING_BASE_USD)
    A["config_arithmetic"] = {
        "pullback_leg_usd": want_pb, "trend_leg_usd": want_tr,
        "gross_usd": want_pb + want_tr,
        "cap_notional_usd": cap_notional,
        "cap_binding_today": (want_pb + want_tr) > cap_notional,
        "gross_pct_of_equity": (want_pb + want_tr) / EQUITY * 100,
        "MAX_EXPOSURE_FRAC_design_gross_usd": MAX_EXPOSURE_FRAC * EQUITY,
        "shortfall_vs_design_point_usd": MAX_EXPOSURE_FRAC * EQUITY - (want_pb + want_tr),
        "dd_halt_dollars": DD_HALT_PCT * SIZING_BASE_USD,
        "dd_halt_as_pct_of_REAL_equity": DD_HALT_PCT * SIZING_BASE_USD / EQUITY * 100,
        "daily_halt_dollars": 0.06 * SIZING_BASE_USD,
        "note": "halts are struck off BASE, not equity. With base frozen at "
                "half of equity the 35% DD rail is 17.5% of the real account. "
                "Casey's proportionality holds - but only once base tracks equity.",
    }

    # ---- notional per dollar of equity, by governing basis ---------------
    bases = {}
    rec_full = KH["cases"]["full|FIXED|k_live_0.0999"]["kelly"]["recommended_m"]
    rec_2y = KH["cases"]["last_2y|FIXED|k_live_0.0999"]["kelly"]["recommended_m"]
    rec_full_v = KH["cases"]["full|VOLTARGET|k_live_0.0999"]["kelly"]["recommended_m"]
    rec_2y_v = KH["cases"]["last_2y|VOLTARGET|k_live_0.0999"]["kelly"]["recommended_m"]
    bases["A_holdout_2024_07_to_2026_07_kelly_p10"] = {
        "gross_usd_at_100k_equity": 15_000.0 * rec_2y,
        "gross_per_equity": 15_000.0 * rec_2y / EQUITY,
        "m_vs_live": rec_2y, "binding_criterion": "bootstrap p10 of m*",
        "voltarget_variant_gross": 15_000.0 * rec_2y_v}
    bases["B_live_today"] = {
        "gross_usd_at_100k_equity": 15_000.0,
        "gross_per_equity": 15_000.0 / EQUITY, "m_vs_live": 1.0,
        "binding_criterion": "SIZING_BASE_USD 50,000 (half of equity)"}
    bases["C_config_design_point_MAX_EXPOSURE_FRAC"] = {
        "gross_usd_at_100k_equity": MAX_EXPOSURE_FRAC * EQUITY,
        "gross_per_equity": MAX_EXPOSURE_FRAC,
        "m_vs_live": MAX_EXPOSURE_FRAC * EQUITY / 15_000.0,
        "binding_criterion": "MAX_NOTIONAL_USD 20,000 would clamp this"}
    bases["D_full_sample_kelly_recommended_m"] = {
        "gross_usd_at_100k_equity": 15_000.0 * rec_full,
        "gross_per_equity": 15_000.0 * rec_full / EQUITY,
        "m_vs_live": rec_full,
        "binding_criterion": "half-Kelly, and TRUNCATED by kelly.py M_CAP=4.0 "
                             "-> a floor, not a measurement",
        "voltarget_variant_gross": 15_000.0 * rec_full_v}
    bases["E_full_sample_DD30_budget_only"] = {
        "gross_usd_at_100k_equity": KMAX_F * LEV * EQUITY,
        "gross_per_equity": KMAX_F * LEV,
        "m_vs_live": KMAX_F / K_LIVE,
        "binding_criterion": "P(maxDD>30%)<=10%, ignoring the other three "
                             "Kelly criteria - the LOOSEST defensible basis"}
    A["notional_by_governing_basis"] = bases

    # ---- Casey's two targets --------------------------------------------
    tgt = {}
    for g in (100_000.0, 1_000_000.0):
        tgt[f"${g:,.0f}_gross"] = {
            "equity_needed_at_DD30_budget_basis": g / GROSS_PER_EQUITY_AT_DDBUDGET,
            "equity_needed_at_config_design_point_0.30": g / MAX_EXPOSURE_FRAC,
            "equity_needed_at_holdout_basis":
                g / (15_000.0 * rec_2y / EQUITY),
            "MAX_NOTIONAL_USD_needed_FIXED": g,
            "MAX_NOTIONAL_USD_needed_VOLTARGET_p99":
                g * (LEVR["lever1_voltarget"]["at_own_kmax"]["VOLTARGET"]
                     ["gross_usd"]["p99"]
                     / LEVR["lever1_voltarget"]["at_own_kmax"]["VOLTARGET"]
                     ["gross_usd"]["median"]),
            "measured_market_impact_bps_at_this_size":
                {100_000.0: 0.06, 1_000_000.0: 1.02}[g],
            "dollar_risk_at_median_stop_4.14pct": g * 0.0414026585423883,
        }
    A["caseys_targets"] = tgt

    # ---- the two levers, scored -----------------------------------------
    sw = LEVR["lever2_stop_width_sweep_S3_pullback"]
    A["levers_scored"] = {
        "lever1_vol_target": {
            "notional_uplift_at_same_dollar_risk": "median 1.03x, p99 2.62x, "
                                                   "max 3.16x of FIXED",
            "cagr_uplift_full_sample_at_matched_k": 1.203,
            "maxdd_ratio_full_sample": 0.971,
            "k_headroom_uplift": KMAX_V / KMAX_F,
            "holdout_verdict": f"recommended_m {rec_2y_v} vs FIXED {rec_2y} - "
                               f"WORSE on the holdout",
            "trade_set_changed": False,
            "MAX_NOTIONAL_USD_required_to_function": "p99 = 2.62x the median "
                "gross; at the live size that is $39,225 vs the $20,000 ceiling "
                "(24.8% of trades clamped)"},
        "lever2_tighter_stop": {
            "notional_uplift_2.5atr_to_1.0atr":
                sw["1.0"]["notional_at_1000_risk_median_usd"]
                / sw["2.5"]["notional_at_1000_risk_median_usd"],
            "win_rate_2.5_vs_1.0_pct": [sw["2.5"]["win_rate_pct"],
                                        sw["1.0"]["win_rate_pct"]],
            "stopouts_2.5_vs_1.0": [sw["2.5"]["exit_mix"].get("STOP"),
                                    sw["1.0"]["exit_mix"].get("STOP")],
            "expectancy_per_unit_risk_2.5_vs_1.0":
                [sw["2.5"]["expectancy_per_unit_RISK"],
                 sw["1.0"]["expectancy_per_unit_RISK"]],
            "realised_maxdd_at_CONSTANT_nominal_risk_2.5_vs_1.0":
                [sw["2.5"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"],
                 sw["1.0"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"]],
            "dd_inflation_factor":
                sw["1.0"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"]
                / sw["2.5"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"],
            "net_notional_per_unit_DD":
                (sw["1.0"]["notional_at_1000_risk_median_usd"]
                 / sw["2.5"]["notional_at_1000_risk_median_usd"])
                / (sw["1.0"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"]
                   / sw["2.5"]["equity_at_constant_0.397pct_risk"]["maxdd_pct"]),
            "verdict": "nominal stop risk UNDER-PRICES tight stops by ~1.9x. "
                       "Risk-equivalence does NOT imply outcome-equivalence."},
    }

    A["latent_defect_found"] = {
        "file": "btc-paper-engine/backend/app/engine/core.py",
        "lines": "208-212 (_size) called from 255 (donchian path)",
        "defect": "_size() computes stop_dist from tcfg.stop_atr (2.5) for "
                  "EVERY book, but the donchian book's real exit is "
                  "BookCfg.trail_atr (5.0). Any book configured "
                  "sizing='vol_target' with strategy='donchian' would size "
                  "the trend leg as if its stop were half as far away, i.e. "
                  "at ~2x the intended dollar risk.",
        "bites_today": False,
        "why_not": "RESEARCH_BOOKS sets S4 sizing='fixed', so the vol_target "
                   "branch is never taken for donchian in the shipped config.",
        "bites_if": "vol-targeting is adopted for the blend - which is exactly "
                    "lever 1. Fix before, not after.",
    }

    A["honesty"] = {
        "measurement_basis": "trade-close (exit-step) blended equity, research "
                             "basis, cash_apy 0, engine's 12bp round-trip taker "
                             "inside every return. MTM runs deeper than "
                             "trade-close (RESEARCH_CARRY.md honesty box).",
        "in_sample": "Every CAGR here is IN-SAMPLE on 2022-02..2026-07 and is "
                     "NOT a forecast. The 2024-07..2026-07 split is the "
                     "single-touch holdout per RESEARCH_TRAIL.md's window map.",
        "not_modelled": [
            "gap-through / slippage on stops: the sim fills STOP exits AT the "
            "stop price. Measured pullback loss/nominal-stop is 1.018-1.098 "
            "(n=66), i.e. fee only. Real gap risk is strictly worse.",
            "funding cost on the perp leg",
            "cash yield on idle USDC (cash_apy=0 throughout). RESEARCH_FEES "
            "measured this dimension moving S5's recommended m from 0.30 to "
            "0.79 - a 2.6x swing. THIS IS THE LARGEST UNQUANTIFIED INPUT HERE.",
            "the blend's own DD_HALT_PCT 35% never binds in this sample "
            "(deepest maxDD at k=0.30 is -7.1%), so halt-on and halt-off are "
            "identical at every size tested up to k=0.30",
            "order-book depth in stressed regimes (only the 2026-09-28 calm "
            "snapshot exists)",
            "correlation between ATR level and edge quality: vol-targeting "
            "assumes the edge per unit of risk is regime-independent. Not tested.",
        ],
        "harness_validation": LAD["harness_validation_vs_bench_blend"],
        "atr_parity_vs_engine": SC["atr_parity_max_abs_err_vs_engine"],
    }

    with open(os.path.join(HERE, "ANSWER.json"), "w") as fh:
        json.dump(A, fh, indent=2, default=float)

    print(json.dumps(A, indent=2, default=float))
    chart(ev, r, R_LEG)


def chart(ev, r, R_LEG) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    INK, MUT = "#1c1917", "#78716c"
    C_F, C_V, C_R, C_OK = "#b45309", "#0f766e", "#b91c1c", "#4d7c0f"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#d6d3d1",
                         "axes.labelcolor": INK, "text.color": INK,
                         "xtick.color": MUT, "ytick.color": MUT,
                         "axes.grid": True, "grid.color": "#e7e5e4",
                         "grid.linewidth": 0.6, "figure.facecolor": "white",
                         "axes.spines.top": False, "axes.spines.right": False})
    usd = FuncFormatter(lambda v, p: f"${v:,.0f}")

    fig = plt.figure(figsize=(13.5, 9.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.05], hspace=0.38, wspace=0.26)

    # -- A: the answer ladder ------------------------------------------
    ax = fig.add_subplot(gs[0, :])
    labs, vals, cols = [], [], []
    B = A["notional_by_governing_basis"]
    order = [("A_holdout_2024_07_to_2026_07_kelly_p10",
              "HOLDOUT Kelly (2024-07→2026-07)\nbootstrap p10 binds", C_R),
             ("B_live_today", "LIVE today\nbase 50k = half of equity", MUT),
             ("C_config_design_point_MAX_EXPOSURE_FRAC",
              "config design point\nMAX_EXPOSURE_FRAC 0.30 × equity", "#7c3aed"),
             ("D_full_sample_kelly_recommended_m",
              "full-sample Kelly rec m\n(M_CAP-truncated: a FLOOR)", C_OK),
             ("E_full_sample_DD30_budget_only",
              "DD-30% budget ALONE\n(loosest defensible)", C_V)]
    for key, lab, c in order:
        labs.append(lab)
        vals.append(B[key]["gross_usd_at_100k_equity"])
        cols.append(c)
    y = np.arange(len(labs))
    ax.barh(y, vals, color=cols, height=0.6)
    for i, v in enumerate(vals):
        ax.text(v * 1.04, i, f"${v:,.0f}   ({v/15000:.2f}x live)",
                va="center", fontsize=8.5, color=INK)
    ax.axvline(20_000, color=C_R, ls="--", lw=1.4)
    ax.annotate("MAX_NOTIONAL_USD $20,000", (20_000, len(labs) - 0.35),
                fontsize=8, color=C_R, rotation=90, va="top", ha="right")
    ax.axvline(100_000, color=INK, ls=":", lw=1.4)
    ax.annotate("Casey's $100k target", (100_000, 0.1), fontsize=8,
                color=INK, rotation=90, va="bottom", ha="right")
    ax.set_yticks(y, labs, fontsize=8.5)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(usd)
    ax.set_xlabel("gross notional supported at $100,055 equity (log scale)")
    ax.set_title("The whole answer: the range spans 12x, and the window you "
                 "trust picks the number", loc="left", fontsize=12, weight="bold")
    ax.invert_yaxis()

    # -- B: full vs holdout divergence --------------------------------
    ax = fig.add_subplot(gs[1, 0])
    t_end = ev["exit_ts"].iloc[-1]
    split = t_end - int(2 * 365.25 * 86400)
    x = pd.to_datetime(ev["exit_ts"], unit="s", utc=True).to_numpy()
    for rule, c in (("FIXED", C_F), ("VOLTARGET", C_V)):
        e = expo(ev, 0.30, rule, R_LEG)
        cc = curve(e, r)
        ax.plot(x, cc["eq"], color=c, lw=1.7, label=f"{rule} at k=0.30")
    ax.axvline(pd.Timestamp(split, unit="s", tz="UTC"), color=C_R, lw=1.5)
    ax.annotate("single-touch HOLDOUT →\n(RESEARCH_TRAIL window map)",
                (pd.Timestamp(split, unit="s", tz="UTC"), 1.52), fontsize=8,
                color=C_R, ha="right", va="top")
    ax.set_yscale("log")
    ax.set_ylabel("blend equity (×, log)")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("B. the edge that authorises size is mostly PRE-holdout",
                 loc="left", weight="bold")

    # -- C: the two levers side by side ------------------------------
    ax = fig.add_subplot(gs[1, 1])
    sw = json.load(open(os.path.join(HERE, "lever_findings.json")))[
        "lever2_stop_width_sweep_S3_pullback"]
    m = sorted(sw, key=float)
    nn = np.array([sw[k]["notional_at_1000_risk_median_usd"] for k in m])
    dd = np.array([abs(sw[k]["equity_at_constant_0.397pct_risk"]["maxdd_pct"])
                   for k in m])
    base_i = m.index("2.5")
    ax.plot([float(k) for k in m], nn / nn[base_i], "o-", color=C_V, lw=1.8,
            label="notional at fixed $1,000 nominal risk")
    ax.plot([float(k) for k in m], dd / dd[base_i], "s-", color=C_R, lw=1.8,
            label="REALISED maxDD at the same nominal risk")
    ax.axhline(1.0, color=MUT, lw=1.0)
    ax.axvline(2.5, color=INK, ls="--", lw=1.2)
    ax.annotate("shipped 2.5×ATR", (2.5, 4.4), fontsize=8, color=INK,
                rotation=90, va="top", ha="right")
    ax.set_xlabel("pullback stop multiple (× ATR14)")
    ax.set_ylabel("× relative to the shipped 2.5×ATR")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("C. lever 2: a tighter stop buys notional and buys DD with it",
                 loc="left", weight="bold")
    fig.savefig(os.path.join(HERE, "fig8_the_answer.png"), dpi=140,
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
