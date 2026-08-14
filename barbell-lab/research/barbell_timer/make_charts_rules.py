#!/usr/bin/env python3
"""Phase 2-3 charts (PNG, light surface, validated reference palette).

Palette validated via dataviz validator (order-as-legend, ALL CHECKS PASS;
contrast WARN on aqua/magenta/yellow -> relief rule: every series is
direct-labeled). Color follows the ENTITY: 50/50 null keeps aqua from
figs 1-3; new rule entities take fresh slots (violet/magenta/yellow/red).
Holdings band on fig5 uses the sleeve entity colors from figs 1-3
(GDE blue / SPY orange / BOXX gray) at low alpha — labeled, not color-alone.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
C = {"static_5050": "#1baf7a", "relmom_cash": "#4a3aa7",
     "composite": "#e87ba4", "voltarget_15": "#eda100",
     "realrate_gate": "#e34948"}
LABEL = {"static_5050": "50/50 null", "relmom_cash": "R2 rel-mom + cash",
         "realrate_gate": "R3 real-rate gate", "composite": "R4 composite",
         "voltarget_15": "R5 vol-target 15%"}
ORDER = ["static_5050", "relmom_cash", "composite", "voltarget_15",
         "realrate_gate"]
HOLD = {"gde": "#2a78d6", "spy": "#eb6834", "boxx": "#b9b8b3"}

res = json.load(open(os.path.join(HERE, "rules_results.json")))
R = {}
for name in ORDER:
    s = pd.Series(res["monthly_returns"][name])
    s.index = pd.PeriodIndex(s.index, freq="M").to_timestamp(how="end")
    R[name] = s.sort_index()
states2 = pd.Series(res["states"]["rule2"])
states2.index = pd.PeriodIndex(states2.index, freq="M").to_timestamp(how="end")


def style(ax):
    ax.set_facecolor(SURF)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#d9d8d4")
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color="#e7e6e2", linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)


def fig_equity_oos():
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    style(ax)
    # B&H SPY reference (owner amendment A5, Q2) — muted dashed benchmark
    pm = json.load(open(os.path.join(HERE, "panel_monthly.json")))["panel"]
    spy = pd.Series({k: v["spx_tr"] for k, v in pm.items()})
    spy.index = pd.PeriodIndex(spy.index, freq="M").to_timestamp(how="end")
    spy = spy.sort_index().loc["1990-02":"2026-07"]
    eq_spy = (1 + spy).cumprod()
    ax.plot(eq_spy.index, eq_spy.values, color="#8a8984", lw=1.6, ls="--",
            label="B&H SPY (Q2 benchmark)")
    ax.annotate(f" B&H SPY  {eq_spy.iloc[-1]:,.0f}x",
                (eq_spy.index[-1], eq_spy.iloc[-1]), color=INK2, fontsize=9,
                va="top", xytext=(4, -8), textcoords="offset points")
    for name in ORDER:
        r = R[name].loc["1990-02":]
        eq = (1 + r).cumprod()
        ax.plot(eq.index, eq.values, color=C[name], lw=2, label=LABEL[name],
                solid_capstyle="round")
        ax.annotate(f" {LABEL[name]}  {eq.iloc[-1]:,.0f}x",
                    (eq.index[-1], eq.iloc[-1]), color=INK, fontsize=9,
                    va="center", xytext=(4, 0), textcoords="offset points")
    ax.set_yscale("log")
    ax.set_yticks([1, 2, 5, 10, 20, 50, 100, 200])
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.set_xlim(pd.Timestamp("1990-01-31"),
                pd.Timestamp("2026-07-31") + pd.Timedelta(days=365 * 9))
    ax.set_title("Rules, OOS window 1990-02 -> 2026-07: growth of $1 (log; net of"
                 " 5bp/switch) — walk-forward, GDE-synth is a MODEL", color=INK,
                 fontsize=11, loc="left", pad=12)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig4_rules_equity_oos.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


def fig_drawdowns():
    fig, (ax, axb) = plt.subplots(
        2, 1, figsize=(11, 6.4), dpi=150, sharex=True,
        gridspec_kw={"height_ratios": [5, 0.9], "hspace": 0.05})
    fig.patch.set_facecolor(SURF)
    style(ax)
    for name in ORDER:
        eq = (1 + R[name]).cumprod()
        dd = eq / eq.cummax() - 1
        ax.plot(dd.index, dd.values * 100, color=C[name], lw=1.6,
                label=LABEL[name])
    ax.axhline(0, color="#b9b8b3", lw=1)
    ax.set_ylabel("drawdown from peak (%)", color=INK2, fontsize=9)
    ax.set_title("Rule drawdowns, 1977-02 -> 2026-07 (month-end closes —"
                 " intramonth-blind, daily ~4pp deeper) + R2 holdings band",
                 color=INK, fontsize=11, loc="left", pad=12)
    ax.annotate("R3 held GDE into Oct-08,\nrotated to SPY for the 2nd leg: -57%",
                xy=(pd.Timestamp("2009-02-28"), -57),
                xytext=(pd.Timestamp("2011-06-30"), -44), color=INK2,
                fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.annotate("R2 worst: -33% (1980-82)",
                xy=(pd.Timestamp("1982-06-30"), -33),
                xytext=(pd.Timestamp("1985-06-30"), -44), color=INK2,
                fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK2,
              ncols=2)
    # holdings band: rule-2 state per month (switch dates = color changes)
    axb.set_facecolor(SURF)
    for sp in axb.spines.values():
        sp.set_visible(False)
    axb.tick_params(colors=INK2, labelsize=9, left=False, labelleft=False)
    s = states2.loc["1977-01":]
    for t, st in s.items():
        axb.axvspan(t - pd.offsets.MonthEnd(1), t, color=HOLD[st], alpha=0.75,
                    lw=0)
    axb.set_ylim(0, 1)
    axb.set_ylabel("R2 holds", color=INK2, fontsize=8, rotation=0, ha="right",
                   va="center")
    for lab, col, x in [("GDE", "gde", 0.35), ("SPY", "spy", 0.5),
                        ("BOXX", "boxx", 0.65)]:
        axb.annotate(lab, xy=(x, -0.55), xycoords="axes fraction",
                     color=INK2, fontsize=8, ha="left",
                     bbox=dict(boxstyle="square,pad=0.25", fc=HOLD[col],
                               alpha=0.75, lw=0))
    fig.savefig(os.path.join(FIGS, "fig5_rules_drawdowns.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


def fig_regimes():
    regs = ["1980-99", "2001-11", "2012-18", "2022->"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=150)
    fig.patch.set_facecolor(SURF)
    for ax, key, ttl, fmt in [
            (axes[0], "CAGR", "CAGR by regime block (%/yr)", "{:.0f}"),
            (axes[1], "MaxDD_m", "MaxDD by regime block (%, month-end)", "{:.0f}")]:
        style(ax)
        x = np.arange(len(regs))
        n = len(ORDER)
        w = 0.8 / n
        for i, name in enumerate(ORDER):
            v = [res["rules"][name]["regimes"][rg][key] * 100 for rg in regs]
            bars = ax.bar(x + (i - (n - 1) / 2) * w, v, width=w * 0.92,
                          color=C[name], label=LABEL[name])
            for b, vv in zip(bars, v):
                ax.annotate(fmt.format(vv), (b.get_x() + b.get_width() / 2, vv),
                            ha="center", fontsize=6.5, color=INK2,
                            va="bottom" if vv >= 0 else "top",
                            xytext=(0, 1 if vv >= 0 else -1),
                            textcoords="offset points")
        ax.axhline(0, color="#b9b8b3", lw=1)
        ax.set_xticks(x, regs)
        ax.set_title(ttl, color=INK, fontsize=10.5, loc="left", pad=10)
    axes[0].legend(loc="upper left", frameon=False, fontsize=8,
                   labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "fig6_rules_regimes.png"),
                facecolor=SURF, bbox_inches="tight")
    plt.close(fig)


fig_equity_oos()
fig_drawdowns()
fig_regimes()
print("wrote figs/:", sorted(os.listdir(FIGS)))
