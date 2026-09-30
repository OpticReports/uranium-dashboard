"""The two levers on NOTIONAL, measured. Follow-on to scale_ladder.py.

risk_$ = notional x stop_frac,  stop_frac = mult * ATR14 / price

So there are exactly two ways to carry more notional at a fixed dollar risk:
  LEVER 1 - make sizing vol-AWARE (notional up when ATR is low). Does not
            touch the trade set at all: same entries, same exits, same win
            rate, same expectancy per $ of notional. Pure sizing change.
  LEVER 2 - make the STOP TIGHTER (smaller mult). Multiplies notional 1:1 but
            CHANGES THE TRADE SET - more stop-outs, lower win rate. This is
            where risk-equivalence stops implying outcome-equivalence, and it
            is measured here rather than assumed.

Also: refined k_max (0.01 grid) so the vol-target uplift is measured rather
than quantised away; FIXED-vs-VOLTARGET clamp cost apples-to-apples; and an
independent re-derivation of KELLY.md's binding 2y cell.

Usage: python3 lever_sweep.py
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

from scale_ladder import (EQUITY, LEV, MAX_NOTIONAL_USD, W_PB, W_TR,   # noqa: E402
                          MULT, boot_idx, boot_maxdd, curve, expo, perf,
                          _gross, trades, BARS_CSV)
from app.engine.core import Bar, BookCfg, TradeCfg                     # noqa: E402
from app.engine.replay import run_replay                               # noqa: E402
from app.config import RESEARCH_SIGNAL                                 # noqa: E402

N_BOOT, BLOCK, BUDGET_P = 6000, 8, 0.10
OUT: dict = {}


def kmax_interp(ks, ps, budget=BUDGET_P):
    """Largest k whose bootstrap P(maxDD>level) <= budget, linearly
    interpolated between grid points so a 0.01 grid is not the resolution."""
    ks, ps = np.asarray(ks, float), np.asarray(ps, float)
    over = np.where(ps > budget)[0]
    if over.size == 0:
        return float(ks[-1]), True          # budget never breached on the grid
    i = over[0]
    if i == 0:
        return float(ks[0]), False
    k0, k1, p0, p1 = ks[i - 1], ks[i], ps[i - 1], ps[i]
    return float(k0 + (budget - p0) * (k1 - k0) / (p1 - p0)), False


# ===================================================== LEVER 1, refined ======
def lever1(ev, r, years) -> None:
    e1 = expo(ev, 1.0, "FIXED")
    risk1 = e1 * ev["s"].to_numpy()
    R_LEG = {lg: float(risk1[(ev.leg == lg).to_numpy()].mean())
             for lg in ("pullback", "trend")}
    idx = boot_idx(len(r), N_BOOT, BLOCK, seed=20260928)
    ks = np.round(np.arange(0.30, 1.21, 0.01), 3)
    P = {"FIXED": [], "VOLTARGET": []}
    for k in ks:
        for rule in P:
            P[rule].append(float((boot_maxdd(expo(ev, k, rule, R_LEG), r, idx)
                                  < -0.30).mean()))
    kf, _ = kmax_interp(ks, P["FIXED"])
    kv, _ = kmax_interp(ks, P["VOLTARGET"])

    def at(k, rule):
        e = expo(ev, k, rule, R_LEG)
        c = curve(e, r)
        g = _gross(ev, e) * EQUITY
        return {**perf(c, years),
                "gross_usd": {"median": float(np.median(g)),
                              "p90": float(np.percentile(g, 90)),
                              "p99": float(np.percentile(g, 99)),
                              "max": float(g.max())}}

    OUT["lever1_voltarget"] = {
        "risk_match_per_leg_frac_equity_at_k1": R_LEG,
        "kmax_at_P_dd30_le_10pct": {"FIXED": kf, "VOLTARGET": kv,
                                    "k_uplift_x": kv / kf},
        "at_own_kmax": {"FIXED": at(kf, "FIXED"),
                        "VOLTARGET": at(kv, "VOLTARGET")},
        "at_MATCHED_k": {k: {"FIXED": at(k, "FIXED"),
                            "VOLTARGET": at(k, "VOLTARGET"),
                            "cagr_uplift_x": at(k, "VOLTARGET")["cagr_pct"]
                                             / at(k, "FIXED")["cagr_pct"],
                            "maxdd_ratio": at(k, "VOLTARGET")["maxdd_pct"]
                                           / at(k, "FIXED")["maxdd_pct"]}
                        for k in (0.0999, 0.20, 0.30, 0.65)},
        "trade_set_identical": True,
        "note": "same entries/exits/win-rate in both columns: only notional moves",
    }

    # apples-to-apples clamp cost of MAX_NOTIONAL_USD, BOTH rules
    clamp = {}
    for k in (0.20, 0.30):
        for rule in ("FIXED", "VOLTARGET"):
            e = expo(ev, k, rule, R_LEG)
            gf = _gross(ev, e)
            row = {}
            for cap in (20_000, 30_000, 50_000, 100_000, 200_000, 10 ** 9):
                sc = np.minimum(1.0, (cap / EQUITY) / np.maximum(gf, 1e-12))
                cc = curve(e * sc, r)
                row[cap] = {**perf(cc, years),
                            "pct_trades_clamped": float((sc < 1 - 1e-12).mean() * 100)}
            clamp[f"k{k}_{rule}"] = row
    OUT["lever1_clamp_cost_both_rules"] = clamp

    # KELLY.md's binding cell is a 2y window: re-derive it independently
    t_end = ev["exit_ts"].iloc[-1]
    m2 = (ev["exit_ts"] >= t_end - int(2 * 365.25 * 86400)).to_numpy()
    ev2, r2 = ev[m2].reset_index(drop=True), r[m2]
    idx2 = boot_idx(len(r2), N_BOOT, BLOCK, seed=7)
    ks2 = np.round(np.arange(0.10, 1.21, 0.01), 3)
    P2 = {rule: [float((boot_maxdd(expo(ev2, k, rule, R_LEG), r2, idx2) < -0.30).mean())
                 for k in ks2] for rule in ("FIXED", "VOLTARGET")}
    OUT["window_crosscheck_vs_KELLY_md"] = {
        "full_window_kmax_dd30": {"FIXED": kf, "VOLTARGET": kv},
        "last_2y_window_kmax_dd30": {
            "FIXED": kmax_interp(ks2, P2["FIXED"])[0],
            "VOLTARGET": kmax_interp(ks2, P2["VOLTARGET"])[0]},
        "n_trades_2y": int(len(ev2)),
        "KELLY_md_S5_fee_corrected": {"2y_cash0_BINDING": 0.30, "2y_cash4": 0.79,
                                      "full_cash0": 0.78, "full_cash4": 0.83},
        "note": "my fee is the engine's 12bp round trip (MORE conservative than "
                "the 8.64bp RESEARCH_FEES measured) and cash_apy is 0.",
    }
    return R_LEG


# ===================================================== LEVER 2: stop width ===
def lever2() -> None:
    df = pd.read_csv(BARS_CSV)
    bars = [Bar(ts=int(x.ts_open_unix), open=float(x.open), high=float(x.high),
                low=float(x.low), close=float(x.close), volume=float(x.volume))
            for x in df.itertuples()]
    rows = {}
    for mult in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        tcfg = TradeCfg(stop_atr=mult)
        books = [BookCfg(name="S3", sizing="fixed", strategy="pullback",
                         leverage=1.0, long_mult=1.0, cap=1.0,
                         start_equity=100_000.0, dd_halt=0.30)]
        res = run_replay(bars, books, RESEARCH_SIGNAL, tcfg, cash_apy=0.0)
        tr = res.books["S3"].trades
        r = np.array([t.pnl_pct / 100.0 for t in tr])
        s = np.array([mult * t.atr_at_entry / t.entry_price for t in tr])
        reasons = pd.Series([t.exit_reason for t in tr]).value_counts().to_dict()
        yrs = (tr[-1].exit_ts - tr[0].entry_ts) / (365.25 * 86400)
        # notional carryable per trade at a fixed $1,000 risk on $100k equity
        n_at_1k = 1_000.0 / s
        # equity curve at CONSTANT dollar risk (0.40% of equity per trade -
        # the risk-matched pullback budget measured at k=1 in lever 1)
        RISK = 0.00397
        e_vt = RISK / s
        c = curve(e_vt, r)
        rows[mult] = {
            "n_trades": int(len(tr)),
            "win_rate_pct": float((r > 0).mean() * 100),
            "exit_mix": {k: int(v) for k, v in reasons.items()},
            "stop_frac_median_pct": float(np.median(s) * 100),
            "mean_r_bps_per_dollar_notional": float(r.mean() * 10_000),
            "median_r_bps": float(np.median(r) * 10_000),
            "expectancy_per_unit_RISK": float((r / s).mean()),
            "mean_win_bps": float(r[r > 0].mean() * 10_000) if (r > 0).any() else None,
            "mean_loss_bps": float(r[r < 0].mean() * 10_000) if (r < 0).any() else None,
            "notional_at_1000_risk_median_usd": float(np.median(n_at_1k)),
            "notional_at_1000_risk_p90_usd": float(np.percentile(n_at_1k, 90)),
            "equity_at_constant_0.397pct_risk": {
                **perf(c, yrs),
                "gross_usd_median": float(np.median(e_vt) * EQUITY),
                "gross_usd_p99": float(np.percentile(e_vt, 99) * EQUITY),
            },
            "years": float(yrs),
        }
    OUT["lever2_stop_width_sweep_S3_pullback"] = rows
    OUT["lever2_caveats"] = [
        "IN-SAMPLE over the whole fixture, NOT pre-registered. RESEARCH_TRAIL.md "
        "is the cautionary precedent: a sweep like this on the selection window "
        "returned rho = -0.064 transfer to holdout. Treat as a MEASUREMENT of "
        "the trade-off shape, not as a parameter recommendation.",
        "stop_atr=2.5 is the shipped value and IS the registered objective "
        "(TradeCfg comment): moving it restates every published MAR in the repo.",
        "The sim fills STOP exits AT the stop price. No gap-through, no "
        "slippage. Tighter stops are therefore flattered here - they are hit "
        "more often and each hit is the one most exposed to real gap risk.",
    ]


def main() -> None:
    ev, _ = trades()
    r = ev["r"].to_numpy()
    years = (ev["exit_ts"].iloc[-1] - ev["exit_ts"].iloc[0]) / (365.25 * 86400)
    lever1(ev, r, years)
    lever2()
    charts()
    with open(os.path.join(HERE, "lever_findings.json"), "w") as fh:
        json.dump(OUT, fh, indent=2, default=float)
    print(json.dumps(OUT, indent=2, default=float))


def charts() -> None:
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
    sw = OUT["lever2_stop_width_sweep_S3_pullback"]
    m = sorted(sw)
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.3))
    ax[0].plot(m, [sw[k]["win_rate_pct"] for k in m], "o-", color=C_V, lw=1.8)
    ax[0].axvline(2.5, color=C_R, ls="--", lw=1.2)
    ax[0].annotate("shipped 2.5", (2.5, min(sw[k]["win_rate_pct"] for k in m)),
                   fontsize=8, color=C_R, rotation=90, va="bottom")
    ax[0].set_xlabel("stop multiple (x ATR14)")
    ax[0].set_ylabel("win rate (%)")
    ax[0].set_title("A. tighter stop -> lower win rate", loc="left", weight="bold")

    a1 = ax[1]
    a1.plot(m, [sw[k]["notional_at_1000_risk_median_usd"] for k in m], "o-",
            color=C_V, lw=1.8, label="notional at $1,000 risk (median)")
    a1.set_ylabel("notional carryable")
    a1.yaxis.set_major_formatter(usd)
    a1.axvline(2.5, color=C_R, ls="--", lw=1.2)
    a2 = a1.twinx()
    a2.plot(m, [sw[k]["mean_r_bps_per_dollar_notional"] for k in m], "s--",
            color=C_F, lw=1.6, label="mean return per $1 notional (bps)")
    a2.set_ylabel("bps per $1 notional", color=C_F)
    a2.grid(False)
    a1.set_xlabel("stop multiple (x ATR14)")
    a1.set_title("B. the trade: more notional, thinner edge per $",
                 loc="left", weight="bold")
    h1, l1 = a1.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    a1.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper center")

    ax[2].plot(m, [sw[k]["equity_at_constant_0.397pct_risk"]["cagr_pct"] for k in m],
               "o-", color=C_V, lw=1.8, label="CAGR at CONSTANT 0.397% $ risk")
    ax[2].axvline(2.5, color=C_R, ls="--", lw=1.2)
    ax[2].set_xlabel("stop multiple (x ATR14)")
    ax[2].set_ylabel("in-sample CAGR (%)  NOT a forecast")
    ax[2].set_title("C. net of everything: does it pay?", loc="left", weight="bold")
    ax[2].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fig7_stop_width_lever.png"), dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
