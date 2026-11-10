"""SCALE LADDER: how much notional the S5 blend can carry, and what actually
binds it. Measured on the 10,002-bar 4h BTC fixture (2022-02 -> 2026-07).

Anchor convention (house standard, bench_blend.py): k = 1.0 IS the research S5
blend = 75/25 pullback/donchian at lev 1.5, i.e. gross exposure 1.5 x EQUITY.
KELLY.md's `m` is exactly this k. Validated against bench_blend.blend_curve
below to float precision.

Live today: leg_notional = KELLY_M * lev * weight * SIZING_BASE_USD
  = 0.20 * 1.5 * w * 50,000 -> gross $15,000 on $100,055 equity = 0.1499x
  => k_live = 0.1499 / 1.5 = 0.0999, NOT the 0.20 the config reads,
     because SIZING_BASE_USD (50,000) is half of equity (100,055).

Two sizing rules compared at every k:
  FIXED     - vol-blind, the live rule: expo_leg = k * 1.5 * weight
  VOLTARGET - expo_leg = k * R_leg / s_i, s_i = mult * ATR14_entry / entry,
              mult 2.5 pullback / 5.0 trail. R_leg set so that at k=1 the MEAN
              dollar risk per leg equals FIXED's - so the two rules are
              risk-matched BY CONSTRUCTION and differ only in vol-responsiveness.
              The 75/25 risk split between legs is PRESERVED.

Decision rule is KELLY.md's own: largest k with P(maxDD > 30%) <= 10%,
block bootstrap on the trade-return sequence.

Usage: python3 scale_ladder.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

from app.engine.core import Bar, BookCfg                          # noqa: E402
from app.engine.replay import run_replay                          # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE            # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")

W_TR, LEV = 0.25, 1.5
W_PB = 1.0 - W_TR
STOP_ATR_PB, TRAIL_ATR_TR = 2.5, 5.0
MULT = {"pullback": STOP_ATR_PB, "trend": TRAIL_ATR_TR}

# live executor config (btc-executor, Hyperliquid, 2026-09-28)
KELLY_M_LIVE = 0.20
KELLY_M_CAP = 0.20
SIZING_BASE_USD = 50_000.0
MAX_NOTIONAL_USD = 20_000.0
MAX_ACCOUNT_LEV = 2.0
MAX_EXPOSURE_FRAC = KELLY_M_CAP * LEV          # 0.30 of EQUITY, gross
EQUITY = 100_055.0
DD_HALT_PCT = 0.35

DD_BUDGET_LEVELS = (0.20, 0.30, 0.35)
BUDGET_P = 0.10
N_BOOT, BLOCK = 6000, 8
R: dict = {}


def trades() -> pd.DataFrame:
    df = pd.read_csv(BARS_CSV)
    bars = [Bar(ts=int(r.ts_open_unix), open=float(r.open), high=float(r.high),
                low=float(r.low), close=float(r.close), volume=float(r.volume))
            for r in df.itertuples()]
    books = [
        BookCfg(name="S3", sizing="fixed", strategy="pullback", leverage=1.0,
                long_mult=1.0, cap=1.0, start_equity=100_000.0, dd_halt=0.30),
        BookCfg(name="S4", sizing="fixed", strategy="donchian", trail_atr=5.0,
                leverage=1.0, long_mult=1.0, cap=1.0, start_equity=100_000.0,
                dd_halt=0.50),
    ]
    res = run_replay(bars, books, RESEARCH_SIGNAL, RESEARCH_TRADE, cash_apy=0.0)
    rows = []
    for leg, bk in (("pullback", "S3"), ("trend", "S4")):
        for t in res.books[bk].trades:
            rows.append(dict(
                leg=leg, exit_ts=t.exit_ts, entry_ts=t.entry_ts,
                r=t.pnl_pct / 100.0,
                s=MULT[leg] * t.atr_at_entry / t.entry_price,
                reason=t.exit_reason, side=t.side))
    ev = pd.concat([pd.DataFrame(rows)]).sort_values(
        ["exit_ts", "leg"]).reset_index(drop=True)
    ev["w"] = np.where(ev.leg == "pullback", W_PB, W_TR)
    return ev, res


def validate_against_bench(ev: pd.DataFrame, res) -> dict:
    """My construction at k=1 must equal bench_blend.blend_curve's S5 exactly."""
    # bench_blend reads sys.argv at import time; give it what it expects so we
    # import the REAL committed blend_curve rather than reimplementing it.
    saved = sys.argv
    sys.argv = ["bench_blend.py", BARS_CSV, HERE]
    try:
        from bench_blend import blend_curve
    finally:
        sys.argv = saved
    b3, b4 = res.books["S3"], res.books["S4"]
    ref = blend_curve(b3, b4, W_TR, LEV, 0, 2 ** 40)
    mine = curve(expo(ev, 1.0, "FIXED"), ev["r"].to_numpy())["eq"]
    ref_nav = np.array([c[1] for c in ref])
    n = min(len(ref_nav), len(mine))
    return {"n_ref": len(ref_nav), "n_mine": len(mine),
            "max_abs_nav_diff": float(np.max(np.abs(ref_nav[:n] - mine[:n]))),
            "final_ref": float(ref_nav[-1]), "final_mine": float(mine[-1])}


def expo(ev: pd.DataFrame, k: float, rule: str,
         r_leg: dict | None = None) -> np.ndarray:
    if rule == "FIXED":
        return (k * LEV * ev["w"]).to_numpy()
    return (k * ev["leg"].map(r_leg) / ev["s"]).to_numpy()


def curve(e: np.ndarray, r: np.ndarray, cap_frac: float | None = None,
          halt: float | None = None) -> dict:
    n_clamp = 0
    if cap_frac is not None:
        n_clamp = int((e > cap_frac).sum())
        e = np.minimum(e, cap_frac)
    step = 1.0 + e * r
    if halt is not None:                      # book stops trading at the halt
        eq_l, peak, halted = [], 1.0, False
        eqv = 1.0
        for s_ in step:
            if not halted:
                eqv *= s_
                peak = max(peak, eqv)
                if eqv / peak - 1.0 <= -halt:
                    halted = True
            eq_l.append(eqv)
        eq = np.array(eq_l)
    else:
        eq = np.cumprod(step)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    return dict(eq=eq, dd=dd, maxdd=float(dd.min()), final=float(eq[-1]),
                n_clamp=n_clamp,
                expo_med=float(np.median(e)), expo_p90=float(np.percentile(e, 90)),
                expo_p99=float(np.percentile(e, 99)), expo_max=float(e.max()))


def perf(c: dict, years: float) -> dict:
    cagr = c["final"] ** (1 / years) - 1
    return {"cagr_pct": cagr * 100, "maxdd_pct": c["maxdd"] * 100,
            "mar": cagr / abs(c["maxdd"]) if c["maxdd"] < -1e-6 else None,
            "total_pct": (c["final"] - 1) * 100}


def boot_idx(n: int, n_boot: int, block: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, nb))
    off = np.arange(block)
    idx = (starts[:, :, None] + off[None, None, :]).reshape(n_boot, -1) % n
    return idx[:, :n]


def boot_maxdd(e: np.ndarray, r: np.ndarray, idx: np.ndarray) -> np.ndarray:
    step = 1.0 + e[idx] * r[idx]
    step = np.maximum(step, 1e-9)          # a step <= 0 is a wipe-out
    eq = np.cumprod(step, axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    return (eq / peak - 1.0).min(axis=1)


def main() -> None:
    ev, res = trades()
    r = ev["r"].to_numpy()
    years = (ev["exit_ts"].iloc[-1] - ev["exit_ts"].iloc[0]) / (365.25 * 86400)
    R["harness_validation_vs_bench_blend"] = validate_against_bench(ev, res)
    R["sample"] = {"n_trades": int(len(ev)), "years": float(years),
                   "n_pullback": int((ev.leg == "pullback").sum()),
                   "n_trend": int((ev.leg == "trend").sum()),
                   "first_exit": str(pd.to_datetime(ev.exit_ts.iloc[0], unit="s")),
                   "last_exit": str(pd.to_datetime(ev.exit_ts.iloc[-1], unit="s"))}

    # risk-match VOLTARGET to FIXED at k=1, preserving the per-leg risk split
    e1 = expo(ev, 1.0, "FIXED")
    risk1 = e1 * ev["s"].to_numpy()
    R_LEG = {lg: float(risk1[(ev.leg == lg).to_numpy()].mean())
             for lg in ("pullback", "trend")}
    R["risk_match"] = {
        "per_leg_mean_dollar_risk_frac_of_equity_at_k1": R_LEG,
        "gross_mean_risk_pct_equity_at_k1": sum(R_LEG.values()) * 100,
        "note": "VOLTARGET holds each leg's dollar risk CONSTANT at these "
                "values; FIXED lets it float with ATR.",
    }
    e1v = expo(ev, 1.0, "VOLTARGET", R_LEG)
    assert abs((e1v * ev["s"].to_numpy())[(ev.leg == "pullback").to_numpy()].mean()
               - R_LEG["pullback"]) < 1e-12

    # ---- where the live book actually sits -------------------------------
    gross_live = KELLY_M_LIVE * LEV * SIZING_BASE_USD
    k_live = gross_live / (LEV * EQUITY)
    R["live_position_on_the_ladder"] = {
        "gross_notional_usd": gross_live,
        "gross_frac_of_equity": gross_live / EQUITY,
        "k_live_effective_kelly_multiple": k_live,
        "KELLY_M_env_reads": KELLY_M_LIVE,
        "gap_because_base_is_not_equity": {
            "SIZING_BASE_USD": SIZING_BASE_USD, "equity": EQUITY,
            "base_over_equity": SIZING_BASE_USD / EQUITY,
            "k_if_base_were_equity": KELLY_M_LIVE,
            "free_multiple_from_setting_base_to_equity": KELLY_M_LIVE / k_live,
            "gross_if_base_were_equity": KELLY_M_LIVE * LEV * EQUITY,
        },
        "MAX_EXPOSURE_FRAC_design_point_gross_usd": MAX_EXPOSURE_FRAC * EQUITY,
        "MAX_NOTIONAL_USD": MAX_NOTIONAL_USD,
        "cap_notional_today_usd": min(MAX_NOTIONAL_USD,
                                      MAX_ACCOUNT_LEV * SIZING_BASE_USD),
        "cap_notional_if_base_equity": min(MAX_NOTIONAL_USD,
                                           MAX_ACCOUNT_LEV * EQUITY),
    }

    # ---- the k ladder: DD budget under each rule -------------------------
    idx = boot_idx(len(r), N_BOOT, BLOCK, seed=20260928)
    ks = np.round(np.concatenate([np.arange(0.05, 1.01, 0.05),
                                  np.arange(1.10, 3.01, 0.10)]), 3)
    ladder = []
    for k in ks:
        row = {"k": float(k)}
        for rule in ("FIXED", "VOLTARGET"):
            e = expo(ev, k, rule, R_LEG)
            c = curve(e, r)
            b = boot_maxdd(e, r, idx)
            row[rule] = {
                **perf(c, years),
                "gross_notional_usd_at_100k_equity": {
                    "median": c["expo_med"] * EQUITY / max(ev["w"].min(), 1e-9) * 0
                              + float(np.median(_gross(ev, e))) * EQUITY,
                    "p90": float(np.percentile(_gross(ev, e), 90)) * EQUITY,
                    "p99": float(np.percentile(_gross(ev, e), 99)) * EQUITY,
                    "max": float(np.max(_gross(ev, e))) * EQUITY,
                },
                "boot_maxdd_median_pct": float(np.median(b) * 100),
                "boot_maxdd_p5_pct": float(np.percentile(b, 5) * 100),
                **{f"P_dd_gt_{int(l*100)}": float((b < -l).mean())
                   for l in DD_BUDGET_LEVELS},
            }
        ladder.append(row)
    R["ladder"] = ladder

    def kmax(rule: str, level: float) -> float | None:
        ok = [row["k"] for row in ladder if row[rule][f"P_dd_gt_{int(level*100)}"] <= BUDGET_P]
        return max(ok) if ok else None

    budget = {}
    for level in DD_BUDGET_LEVELS:
        kf, kv = kmax("FIXED", level), kmax("VOLTARGET", level)
        budget[f"dd_{int(level*100)}"] = {
            "k_max_FIXED": kf, "k_max_VOLTARGET": kv,
            "voltarget_k_uplift_x": (kv / kf) if (kf and kv) else None,
            "FIXED_gross_usd_at_kmax": (kf * LEV * EQUITY) if kf else None,
            "VOLTARGET_gross_median_usd_at_kmax":
                float(np.median(_gross(ev, expo(ev, kv, "VOLTARGET", R_LEG)))) * EQUITY
                if kv else None,
            "VOLTARGET_gross_p99_usd_at_kmax":
                float(np.percentile(_gross(ev, expo(ev, kv, "VOLTARGET", R_LEG)), 99)) * EQUITY
                if kv else None,
            "VOLTARGET_gross_max_usd_at_kmax":
                float(np.max(_gross(ev, expo(ev, kv, "VOLTARGET", R_LEG)))) * EQUITY
                if kv else None,
        }
    R["dd_budget_kmax"] = budget | {
        "budget_rule": f"largest k with P(maxDD > level) <= {BUDGET_P:.0%}, "
                       f"block bootstrap block={BLOCK} n={N_BOOT}",
        "k_live": k_live,
        "kelly_md_recommended_m_S5_fee_corrected_binding_cell": 0.30,
        "kelly_md_recommended_m_S5_full_window_cells": [0.83, 0.78],
    }

    # ---- what MAX_NOTIONAL_USD must be for each rule to not clamp --------
    caps = {}
    for k_lab, k in (("k_live_0.0999", k_live), ("k_0.20", 0.20),
                     ("k_0.30_S5_authorised", 0.30)):
        g_f = _gross(ev, expo(ev, k, "FIXED")) * EQUITY
        g_v = _gross(ev, expo(ev, k, "VOLTARGET", R_LEG)) * EQUITY
        caps[k_lab] = {
            "FIXED_gross_usd": float(g_f.max()),
            "VOLTARGET_gross_usd": {"median": float(np.median(g_v)),
                                    "p90": float(np.percentile(g_v, 90)),
                                    "p99": float(np.percentile(g_v, 99)),
                                    "max": float(g_v.max())},
            "MAX_NOTIONAL_USD_needed_for_no_clamp_p99": float(np.percentile(g_v, 99)),
            "pct_of_trades_clamped_at_20k": float((g_v > MAX_NOTIONAL_USD).mean() * 100),
        }
    R["max_notional_requirement"] = caps

    # ---- cost of clamping VOLTARGET at the live $20k ceiling ------------
    clamp_cost = {}
    for k_lab, k in (("k_0.20", 0.20), ("k_0.30", 0.30)):
        e = expo(ev, k, "VOLTARGET", R_LEG)
        gross_frac = _gross(ev, e)
        for cap_usd in (20_000, 30_000, 50_000, 100_000, 1_000_000):
            scale = np.minimum(1.0, (cap_usd / EQUITY) / np.maximum(gross_frac, 1e-12))
            cc = curve(e * scale, r)
            bb = boot_maxdd(e * scale, r, idx)
            clamp_cost[f"{k_lab}_cap{cap_usd}"] = {
                **perf(cc, years),
                "pct_trades_clamped": float((scale < 1.0).mean() * 100),
                "P_dd_gt_30": float((bb < -0.30).mean()),
            }
    R["clamp_cost"] = clamp_cost

    # ---- halt-on honesty variant at the live k and at k=0.30 ------------
    halt = {}
    for k_lab, k in (("k_live", k_live), ("k_0.20", 0.20), ("k_0.30", 0.30)):
        for rule in ("FIXED", "VOLTARGET"):
            e = expo(ev, k, rule, R_LEG)
            halt[f"{k_lab}_{rule}"] = {
                "halt_off": perf(curve(e, r), years),
                "halt_on_35pct": perf(curve(e, r, halt=DD_HALT_PCT), years)}
    R["dd_halt_sensitivity"] = halt

    make_charts(ev, r, R_LEG, ladder, idx, years, k_live)
    with open(os.path.join(HERE, "ladder_findings.json"), "w") as fh:
        json.dump(R, fh, indent=2, default=float)
    report(ev, ladder, k_live, R_LEG, r, years)


def _gross(ev: pd.DataFrame, e: np.ndarray) -> np.ndarray:
    """Gross exposure fraction of equity implied per trade. Legs are separate
    positions; gross at any instant is the sum, so scale each leg's exposure
    up by 1/weight to state the GROSS the pair implies at that trade's vol."""
    return e / ev["w"].to_numpy()


def report(ev, ladder, k_live, R_LEG, r, years) -> None:
    print("=" * 78)
    print("HARNESS VALIDATION vs bench_blend.blend_curve (S5, k=1):",
          json.dumps(R["harness_validation_vs_bench_blend"], indent=1))
    print("=" * 78)
    print("LIVE POSITION ON THE LADDER")
    print(json.dumps(R["live_position_on_the_ladder"], indent=1, default=float))
    print("=" * 78)
    print("DD BUDGET k_max")
    print(json.dumps(R["dd_budget_kmax"], indent=1, default=float))
    print("=" * 78)
    print("MAX_NOTIONAL REQUIREMENT")
    print(json.dumps(R["max_notional_requirement"], indent=1, default=float))
    print("=" * 78)
    print("CLAMP COST")
    print(json.dumps(R["clamp_cost"], indent=1, default=float))
    print("=" * 78)
    print("DD HALT SENSITIVITY")
    print(json.dumps(R["dd_halt_sensitivity"], indent=1, default=float))
    print("=" * 78)
    print(f"{'k':>6} | {'FIX cagr':>9} {'FIX dd':>8} {'FIX P30':>8} "
          f"| {'VT cagr':>9} {'VT dd':>8} {'VT P30':>8} | {'VT gross p99 $':>14}")
    for row in ladder:
        f_, v_ = row["FIXED"], row["VOLTARGET"]
        print(f"{row['k']:>6.2f} | {f_['cagr_pct']:>8.1f}% {f_['maxdd_pct']:>7.1f}% "
              f"{f_['P_dd_gt_30']:>8.3f} | {v_['cagr_pct']:>8.1f}% "
              f"{v_['maxdd_pct']:>7.1f}% {v_['P_dd_gt_30']:>8.3f} | "
              f"{v_['gross_notional_usd_at_100k_equity']['p99']:>14,.0f}")


def make_charts(ev, r, R_LEG, ladder, idx, years, k_live) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    INK, MUT = "#1c1917", "#78716c"
    C_F, C_V, C_R = "#b45309", "#0f766e", "#b91c1c"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#d6d3d1",
                         "axes.labelcolor": INK, "text.color": INK,
                         "xtick.color": MUT, "ytick.color": MUT,
                         "axes.grid": True, "grid.color": "#e7e5e4",
                         "grid.linewidth": 0.6, "figure.facecolor": "white",
                         "axes.spines.top": False, "axes.spines.right": False})
    usd = FuncFormatter(lambda v, p: f"${v:,.0f}")
    ks = np.array([row["k"] for row in ladder])

    # FIG 5: DD budget frontier + notional demanded
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.4))
    for rule, c in (("FIXED", C_F), ("VOLTARGET", C_V)):
        ax[0].plot(ks, [row[rule]["P_dd_gt_30"] for row in ladder], color=c,
                   lw=1.8, label=rule)
    ax[0].axhline(0.10, color=C_R, ls="--", lw=1.2, label="10% DD budget")
    ax[0].axvline(k_live, color=MUT, ls=":", lw=1.4)
    ax[0].annotate(f"live k={k_live:.3f}", (k_live, 0.55), rotation=90,
                   fontsize=8, color=MUT, va="center")
    ax[0].axvline(0.30, color="#7c3aed", ls=":", lw=1.4)
    ax[0].annotate("KELLY.md S5 m=0.30", (0.30, 0.55), rotation=90,
                   fontsize=8, color="#7c3aed", va="center")
    ax[0].set_xlabel("k  (Kelly multiple of research S5; gross = k x 1.5 x equity)")
    ax[0].set_ylabel("P(maxDD > 30%)")
    ax[0].set_title("A. the DD budget, not the market, sets k",
                    loc="left", weight="bold")
    ax[0].legend(frameon=False, fontsize=8)

    for rule, c in (("FIXED", C_F), ("VOLTARGET", C_V)):
        ax[1].plot(ks, [row[rule]["cagr_pct"] for row in ladder], color=c,
                   lw=1.8, label=f"{rule} (in-sample)")
    ax[1].axvline(k_live, color=MUT, ls=":", lw=1.4)
    ax[1].set_xlabel("k")
    ax[1].set_ylabel("in-sample CAGR (%)  NOT a forecast")
    ax[1].set_title("B. growth curve — over-betting turns down",
                    loc="left", weight="bold")
    ax[1].legend(frameon=False, fontsize=8)

    ax[2].plot(ks, [row["FIXED"]["gross_notional_usd_at_100k_equity"]["max"]
                    for row in ladder], color=C_F, lw=1.8, label="FIXED gross (constant)")
    ax[2].plot(ks, [row["VOLTARGET"]["gross_notional_usd_at_100k_equity"]["median"]
                    for row in ladder], color=C_V, lw=1.8, label="VOLTARGET median")
    ax[2].plot(ks, [row["VOLTARGET"]["gross_notional_usd_at_100k_equity"]["p99"]
                    for row in ladder], color=C_V, lw=1.2, ls="--", label="VOLTARGET p99")
    ax[2].axhline(20_000, color=C_R, ls="--", lw=1.2, label="MAX_NOTIONAL_USD $20k")
    ax[2].axhline(100_000, color=MUT, ls=":", lw=1.2, label="Casey's $100k target")
    ax[2].set_yscale("log")
    ax[2].yaxis.set_major_formatter(usd)
    ax[2].set_xlabel("k")
    ax[2].set_ylabel("gross notional @ $100k equity")
    ax[2].set_title("C. what the $20k ceiling blocks", loc="left", weight="bold")
    ax[2].legend(frameon=False, fontsize=7.5)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig5_dd_budget_frontier.png"), dpi=140)
    plt.close(fig)

    # FIG 6: equity curves at the authorised k=0.30 under both rules, halt on/off
    x = pd.to_datetime(ev["exit_ts"], unit="s", utc=True).to_numpy()
    fig, ax = plt.subplots(2, 1, figsize=(11, 7.6), sharex=True,
                           gridspec_kw={"height_ratios": [1.4, 1]})
    for k, ls in ((k_live, ":"), (0.30, "-")):
        for rule, c in (("FIXED", C_F), ("VOLTARGET", C_V)):
            e = expo(ev, k, rule, R_LEG)
            cc = curve(e, r)
            lab = f"{rule} k={k:.3f}  CAGR {perf(cc, years)['cagr_pct']:.1f}%  " \
                  f"DD {cc['maxdd']*100:.1f}%"
            ax[0].plot(x, cc["eq"], color=c, lw=1.6 if ls == "-" else 1.1,
                       ls=ls, label=lab)
            ax[1].plot(x, cc["dd"] * 100, color=c, lw=1.2, ls=ls)
    ax[0].set_yscale("log")
    ax[0].set_ylabel("blend equity (x, log)")
    ax[0].legend(loc="upper left", frameon=False, fontsize=8)
    ax[0].set_title("Live k=0.0999 (dotted) vs the already-authorised k=0.30 "
                    "(solid) — IN-SAMPLE, trade-close, halt OFF",
                    loc="left", fontsize=11, weight="bold")
    ax[1].axhline(-35, color=C_R, ls="--", lw=1.1, label="DD_HALT_PCT 35%")
    ax[1].set_ylabel("drawdown (%)")
    ax[1].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig6_live_vs_authorised.png"), dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
