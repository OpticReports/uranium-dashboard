#!/usr/bin/env python3
"""Phase 1 charts (PNG, light surface, validated reference palette).

Palette: dataviz reference categorical order (adjacent-validated):
slot1 blue #2a78d6 (GDE-synth), slot2 orange #eb6834 (SPY),
slot3 aqua #1baf7a (50/50), slot4 yellow #eda100 (bills; low contrast on
light surface -> relief rule: direct-labeled). Color follows the ENTITY on
every figure. Grid/axes recessive; 2px lines; no dual axes.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
C = {"gde": "#2a78d6", "spy": "#eb6834", "s5050": "#1baf7a", "bills": "#eda100"}

res = json.load(open(os.path.join(HERE, "baselines_results.json")))
P = {}
for name in ["B&H GDE-synth", "B&H SPY", "50/50 GDE/SPY (M)", "Bills (TB3MS)"]:
    s = pd.Series(res["portfolio_returns"][name])
    s.index = pd.PeriodIndex(s.index, freq="M").to_timestamp(how="end")
    P[name] = s.sort_index()


def style(ax):
    ax.set_facecolor(SURF)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#d9d8d4")
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color="#e7e6e2", linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def fig_equity():
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    style(ax)
    series = [("B&H GDE-synth", C["gde"]), ("B&H SPY", C["spy"]),
              ("50/50 GDE/SPY (M)", C["s5050"]), ("Bills (TB3MS)", C["bills"])]
    for name, c in series:
        eq = (1 + P[name]).cumprod()
        ax.plot(eq.index, eq.values, color=c, lw=2, label=name,
                solid_capstyle="round")
        ax.annotate(f" {name.replace(' (M)','').replace(' (TB3MS)','')}"
                    f"  {eq.iloc[-1]:,.0f}x",
                    (eq.index[-1], eq.iloc[-1]), color=INK, fontsize=9,
                    va="center", xytext=(4, 0), textcoords="offset points")
    ax.set_yscale("log")
    ax.set_yticks([1, 3, 10, 30, 100, 300, 1000])
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.set_xlim(P["B&H SPY"].index[0], P["B&H SPY"].index[-1] + pd.Timedelta(days=365 * 8))
    ax.set_title("Growth of $1, monthly, 1975-2026 (log scale) — GDE-synth is a"
                 " MODEL, carry-model band ±1%/yr pre-2007", color=INK,
                 fontsize=11, loc="left", pad=12)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig1_equity_curves.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


def fig_drawdown():
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    style(ax)
    for name, c in [("B&H GDE-synth", C["gde"]), ("B&H SPY", C["spy"]),
                    ("50/50 GDE/SPY (M)", C["s5050"])]:
        eq = (1 + P[name]).cumprod()
        dd = eq / eq.cummax() - 1
        ax.plot(dd.index, dd.values * 100, color=c, lw=1.6, label=name)
    ax.axhline(0, color="#b9b8b3", lw=1)
    ax.set_ylabel("drawdown from peak (%)", color=INK2, fontsize=9)
    ax.set_title("Drawdown profiles (month-end closes — intramonth-blind; daily"
                 " estimates ~4-6pp deeper)", color=INK, fontsize=11,
                 loc="left", pad=12)
    ax.annotate("1980-82 gold bust:\nGDE-synth -61%", xy=(pd.Timestamp("1982-06-30"), -61),
                xytext=(pd.Timestamp("1986-06-30"), -52), color=INK2, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.annotate("GFC: 50/50 -45%", xy=(pd.Timestamp("2009-02-27"), -45),
                xytext=(pd.Timestamp("2012-06-30"), -56), color=INK2, fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig2_drawdowns.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


def fig_rolling():
    def r10(r):
        c = (1 + r).rolling(120).apply(np.prod, raw=True)
        return (c ** (12 / 120) - 1).dropna()

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.2), dpi=150, sharex=True)
    fig.patch.set_facecolor(SURF)
    a, b = axes
    for ax in axes:
        style(ax)
        ax.axhline(0, color="#b9b8b3", lw=1)
    ga, sa, ma = (r10(P["B&H GDE-synth"]), r10(P["B&H SPY"]),
                  r10(P["50/50 GDE/SPY (M)"]))
    a.plot(ga.index, (ga - sa).values * 100, color=C["gde"], lw=2,
           label="GDE-synth minus SPY")
    a.plot(ma.index, (ma - sa).values * 100, color=C["s5050"], lw=2,
           label="50/50 minus SPY")
    a.set_title("Rolling 10-year annualized return spreads (monthly, %/yr) —"
                " regime-dominated, exactly as the priors said", color=INK,
                fontsize=11, loc="left", pad=12)
    a.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK2)
    b.plot(ga.index, (ga - ma).values * 100, color=C["gde"], lw=2,
           label="GDE-synth minus 50/50 (the null)")
    b.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK2)
    b.set_ylabel("spread (%/yr)", color=INK2, fontsize=9)
    a.set_ylabel("spread (%/yr)", color=INK2, fontsize=9)
    for ax in axes:  # regime blocks from the frozen brief
        for x0, x1 in [("1980-01", "1999-12"), ("2001-01", "2011-12"),
                       ("2012-01", "2018-12"), ("2022-01", "2026-07")]:
            ax.axvspan(pd.Timestamp(x0), pd.Timestamp(x1) + pd.offsets.MonthEnd(),
                       color="#52514e", alpha=0.045, lw=0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig3_rolling10y_spreads.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


fig_equity()
fig_drawdown()
fig_rolling()
print("wrote figs/:", sorted(os.listdir(FIGS)))
