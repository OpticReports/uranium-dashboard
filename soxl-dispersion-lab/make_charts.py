#!/usr/bin/env python3
"""Figures for the SOXL-dispersion study. Reads fixtures, writes figs/*.png.

Palette is the validated categorical default (blue/orange/aqua/yellow/red);
it clears the CVD and normal-vision floors on the adjacent pairlist. The two
low-contrast slots (aqua, yellow) are always direct-labelled, which is the
documented relief for the contrast WARN.
"""
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

from datalib import Costs, Data, TRADING_DAYS, build_basket, run_backtest
from variants import BASE_COSTS, tgt_long_short

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "figs")
os.makedirs(FIGS, exist_ok=True)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8880"
GRID = "#e5e4df"
C = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a",
     "yellow": "#eda100", "red": "#e34948", "violet": "#4a3aa7"}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.size": 10, "font.family": "DejaVu Sans",
    "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.7,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})
PCT = FuncFormatter(lambda v, _: f"{v*100:.0f}%")


def _style(ax, title, sub=None, ylabel=None):
    ax.set_title(title, color=INK, fontsize=12, fontweight="bold", loc="left",
                 pad=14 if sub else 8)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    ax.set_axisbelow(True)


def _dates(ds):
    return np.array([np.datetime64(x) for x in ds])


def fig_equity(d, runs):
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.4), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]})
    ax, ax2 = axes
    for (label, res, col) in runs:
        x = _dates(res["dates"])
        nav = res["nav"]
        ax.plot(x, nav, color=col, lw=2, label=label)
        ax.annotate(f"{label}  {nav[-1]:.1f}x", (x[-1], nav[-1]),
                    xytext=(6, 0), textcoords="offset points",
                    color=col, fontsize=9, fontweight="bold", va="center")
        dd = nav / np.maximum.accumulate(nav) - 1
        ax2.plot(x, dd, color=col, lw=1.6)
    ax.set_yscale("log")
    ax.set_yticks([0.5, 1, 2, 5, 10, 20, 50])
    ax.get_yaxis().set_major_formatter(
        FuncFormatter(lambda v, _: f"{v:g}x"))
    _style(ax, "Growth of $1, net of all modelled costs",
           "log scale — the seed strategy against the book it is built from")
    ax.legend(loc="upper left", fontsize=9)
    ax2.yaxis.set_major_formatter(PCT)
    _style(ax2, "Drawdown", ylabel=None)
    ax2.set_xlim(x[0], x[-1] + np.timedelta64(400, "D"))
    fig.tight_layout()
    fig.savefig(f"{FIGS}/equity.png", dpi=150)
    plt.close(fig)


def fig_cadence(d):
    """The central result: what the short leg pays depends on cadence."""
    from decomposition import _pair_trade
    lo, hi = d.slice_idx("2010-03-12", d.dates[-1])
    rl, rx = d.ret("SOXL")[lo:hi], d.ret("SOXX")[lo:hi]
    x = _dates(d.dates[lo:hi])
    fig, ax = plt.subplots(figsize=(11, 5.4))
    for (k, name, col) in [(1, "daily reset", C["blue"]),
                           (5, "weekly", C["aqua"]),
                           (21, "monthly", C["yellow"]),
                           (63, "quarterly", C["orange"]),
                           (10 ** 9, "never (static)", C["red"])]:
        nav = _pair_trade(rl, rx, k)
        nav = np.where(nav <= 0, np.nan, nav)
        ax.plot(x, nav, color=col, lw=2, label=name)
        last = np.where(np.isfinite(nav))[0]
        if len(last):
            j = last[-1]
            ax.annotate(name, (x[j], nav[j]), xytext=(6, 0),
                        textcoords="offset points", color=col, fontsize=9,
                        fontweight="bold", va="center")
    ax.set_yscale("log")
    ax.axhline(1.0, color=MUTED, lw=1, ls=":")
    ax.get_yaxis().set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    _style(ax, "Short 1x SOXL vs long 3x SOXX — the same trade at five cadences",
           "variance drag is only harvestable by letting the position ride; "
           "letting it ride is what destroys it")
    ax.set_xlim(x[0], x[-1] + np.timedelta64(500, "D"))
    fig.tight_layout()
    fig.savefig(f"{FIGS}/cadence.png", dpi=150)
    plt.close(fig)


def fig_convexity(d, res_v0, res_vw):
    """Monthly book return vs monthly SOXX return — the short-gamma smile."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    for ax, (label, res, col) in zip(
            axes, [("V0 monthly rebalance", res_v0, C["blue"]),
                   ("V0.W weekly rebalance", res_vw, C["aqua"])]):
        mb, ms = _monthly_pairs(d, res)
        ax.axhline(0, color=MUTED, lw=1)
        ax.axvline(0, color=MUTED, lw=1)
        ax.scatter(ms, mb, s=26, color=col, alpha=0.75, edgecolor=SURFACE,
                   linewidth=1.2, zorder=3)
        z = np.polyfit(ms, mb, 2)
        xs = np.linspace(min(ms), max(ms), 100)
        ax.plot(xs, np.polyval(z, xs), color=C["red"], lw=2, zorder=4)
        ax.xaxis.set_major_formatter(PCT)
        ax.yaxis.set_major_formatter(PCT)
        ax.set_xlabel("SOXX monthly return", fontsize=9)
        _style(ax, label, f"quadratic term {z[0]:+.2f}")
    axes[0].set_ylabel("book monthly return", fontsize=9)
    fig.suptitle("Payoff shape vs the semiconductor index",
                 color=INK, fontsize=12, fontweight="bold", x=0.008, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(f"{FIGS}/convexity.png", dpi=150)
    plt.close(fig)


def _monthly_pairs(d, res):
    nav, ds = res["nav"], res["dates"]
    soxx = d.px["SOXX"]
    mb, ms, start, si, cur = [], [], nav[0], d.di[ds[0]], ds[0][:7]
    for k in range(1, len(ds)):
        if ds[k][:7] != cur:
            mb.append(nav[k - 1] / start - 1)
            ms.append(soxx[d.di[ds[k - 1]]] / soxx[si] - 1)
            start, si, cur = nav[k - 1], d.di[ds[k - 1]], ds[k][:7]
    return np.array(mb), np.array(ms)


def fig_yearly(d, res_v0):
    nav, ds = res_v0["nav"], res_v0["dates"]
    years, rets = [], []
    for y in sorted({x[:4] for x in ds}):
        idx = [k for k, x in enumerate(ds) if x[:4] == y]
        if len(idx) < 20:
            continue
        years.append(y)
        rets.append(nav[idx[-1]] / nav[idx[0]] - 1)
    fig, ax = plt.subplots(figsize=(11, 4.4))
    cols = [C["aqua"] if r >= 0 else C["red"] for r in rets]
    bars = ax.bar(years, rets, color=cols, width=0.68)
    ax.axhline(0, color=INK2, lw=1)
    for b, r in zip(bars, rets):
        ax.annotate(f"{r*100:+.0f}%", (b.get_x() + b.get_width() / 2, r),
                    xytext=(0, 4 if r >= 0 else -13), textcoords="offset points",
                    ha="center", fontsize=8, color=INK2)
    ax.yaxis.set_major_formatter(PCT)
    _style(ax, "V0 calendar-year net return",
           "eight losing years, one +66% year (2024), one -31% year (2026 YTD)")
    fig.tight_layout()
    fig.savefig(f"{FIGS}/yearly.png", dpi=150)
    plt.close(fig)


def fig_heatmap():
    with open(os.path.join(HERE, "fixtures", "validation.json")) as f:
        v = json.load(f)
    grid = v["sensitivity"]
    NS, FS = [3, 5, 8, 12], ["D", "W", "M", "Q"]
    names = {"D": "daily", "W": "weekly", "M": "monthly", "Q": "quarterly"}
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.9))
    for ax, per in zip(axes, ["IS", "OOS", "full"]):
        M = np.array([[grid[f"{per}|{n}|{f}"]["sharpe"] for f in FS]
                      for n in NS])
        im = ax.imshow(M, cmap="RdYlBu", vmin=-0.4, vmax=1.2, aspect="auto")
        for i in range(len(NS)):
            for j in range(len(FS)):
                ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center",
                        fontsize=9, color=INK)
        ax.set_xticks(range(len(FS)), [names[f] for f in FS], fontsize=8)
        ax.set_yticks(range(len(NS)), [f"top-{n}" for n in NS], fontsize=8)
        ax.grid(False)
        lbl = {"IS": "in-sample <=2019", "OOS": "out-of-sample 2020+",
               "full": "full period"}[per]
        _style(ax, lbl)
    fig.suptitle("Sharpe by basket size x rebalance cadence — cadence dominates",
                 color=INK, fontsize=12, fontweight="bold", x=0.006, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    fig.savefig(f"{FIGS}/heatmap.png", dpi=150)
    plt.close(fig)


def fig_attribution(d):
    """Cumulative P&L by leg for V0 — where the money actually came from."""
    lo, hi = d.slice_idx("2010-03-12", d.dates[-1])
    costs = Costs(**BASE_COSTS)
    legs = {
        "long top-8 basket (75%)": run_backtest(
            d, "2010-03-12", d.dates[-1],
            lambda data, i: {t: 0.75 * v for t, v in
                             build_basket(data, i, 8, "cap").items()},
            costs=costs, rebalance="M"),
        "short SOXL (25%)": run_backtest(
            d, "2010-03-12", d.dates[-1],
            lambda data, i: {"SOXL": -0.25}, costs=costs, rebalance="M"),
        "combined book (V0)": run_backtest(
            d, "2010-03-12", d.dates[-1], tgt_long_short(8, "cap"),
            costs=costs, rebalance="M"),
    }
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for (label, col) in [("long top-8 basket (75%)", C["blue"]),
                         ("short SOXL (25%)", C["orange"]),
                         ("combined book (V0)", C["violet"])]:
        r = legs[label]
        x = _dates(r["dates"])
        ax.plot(x, r["nav"] - 1, color=col, lw=2)
        ax.annotate(label, (x[-1], r["nav"][-1] - 1), xytext=(6, 0),
                    textcoords="offset points", color=col, fontsize=9,
                    fontweight="bold", va="center")
    ax.axhline(0, color=MUTED, lw=1)
    ax.yaxis.set_major_formatter(PCT)
    _style(ax, "Cumulative P&L by leg, on the book's own capital",
           "the short leg is a persistent cost that buys beta neutrality")
    ax.set_xlim(_dates(legs["combined book (V0)"]["dates"])[0],
                _dates(legs["combined book (V0)"]["dates"])[-1]
                + np.timedelta64(900, "D"))
    fig.tight_layout()
    fig.savefig(f"{FIGS}/attribution.png", dpi=150)
    plt.close(fig)


def main():
    d = Data()
    costs = Costs(**BASE_COSTS)
    end = d.dates[-1]
    v0 = run_backtest(d, "2010-03-12", end, tgt_long_short(8, "cap"),
                      costs=costs, rebalance="M")
    vw = run_backtest(d, "2010-03-12", end, tgt_long_short(8, "cap"),
                      costs=costs, rebalance="W")
    bench = run_backtest(d, "2010-03-12", end,
                         lambda data, i: {t: 0.75 * v for t, v in
                                          build_basket(data, i, 8, "cap").items()},
                         costs=costs, rebalance="M")
    soxx = run_backtest(d, "2010-03-12", end, lambda data, i: {"SOXX": 1.0},
                        costs=costs, rebalance="M")
    fig_equity(d, [("SOXX long-only", soxx, C["yellow"]),
                   ("75% basket + cash", bench, C["orange"]),
                   ("V0.W weekly", vw, C["aqua"]),
                   ("V0 monthly (seed)", v0, C["blue"])])
    print("equity.png")
    fig_cadence(d)
    print("cadence.png")
    fig_convexity(d, v0, vw)
    print("convexity.png")
    fig_yearly(d, v0)
    print("yearly.png")
    fig_attribution(d)
    print("attribution.png")
    try:
        fig_heatmap()
        print("heatmap.png")
    except FileNotFoundError:
        print("heatmap.png SKIPPED (run validation.py first)")


if __name__ == "__main__":
    main()
