#!/usr/bin/env python3
"""Figures for studies/yield-dynamics-forward-spx.md, driven off results.json.

    python3 charts.py [outdir]     -> fig1_rates.png, fig2_analogs.png,
                                      fig3_odds.png, fig4_power.png
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import panel as P  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
R = json.load(open(os.path.join(HERE, "results.json")))
PW = json.load(open(os.path.join(HERE, "power.json")))

# reference palette (dataviz skill), light mode
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
BASE = "#8a8985"
CRIT = "#e34948"                     # status: reserved for the downside rows

plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "font.family": "DejaVu Sans"})


def style(ax):
    ax.set_facecolor(SURF)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def pct(x, _=None):
    return f"{100 * x:.0f}%"


LABELS = {"L10": "10y level", "L10_dev": "10y vs its 5-yr avg",
          "R10": "real 10y (minus CPI)", "S3_12": "3y, 12m change",
          "S10_12": "10y, 12m change", "S20_12": "20y, 12m change",
          "S10_6": "10y, 6m change", "C10_3": "curve 10y−3y",
          "C20_3": "curve 20y−3y", "SB_12": "3m bill, 12m change"}


# ------------------------------------------------------------ fig 1
def fig1():
    h = "12"
    Rh = R["h"][h]
    base = Rh["base"]["p_up"]
    feats = list(LABELS)
    fig, ax = plt.subplots(figsize=(9.6, 6.4))
    fig.patch.set_facecolor(SURF)
    style(ax)
    ax.axvspan(*Rh["base"]["p_up_ci90"], color=BASE, alpha=0.12, lw=0)
    ax.axvline(base, color=BASE, lw=1.6)
    ax.text(base, -0.75, f" base rate {100*base:.0f}%", color=INK2, fontsize=8.5,
            va="center")
    off = {"low": -0.22, "mid": 0.0, "high": 0.22}
    col = {"low": S1, "mid": BASE, "high": S2}
    for i, f in enumerate(feats[::-1]):
        t = Rh["terciles"][f]
        today = Rh["today_tercile"][f]
        for name in ("low", "mid", "high"):
            c = t["cells"][name]
            y = i + off[name]
            ax.plot([c["p_up"]], [y], "o", ms=8 if name == today else 5.5,
                    color=col[name], mec=INK if name == today else SURF,
                    mew=1.6 if name == today else 1, zorder=3)
        ax.text(0.505, i, f"p={t['p_shift']:.2f}", va="center", fontsize=7.5,
                color=INK2)
    ax.set_yticks(range(len(feats)))
    ax.set_yticklabels([LABELS[f] for f in feats[::-1]])
    ax.set_xlim(0.50, 0.95)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(pct))
    ax.set_xlabel("share of months the S&P 500 was higher 12 months later")
    for name, lab in (("low", "lowest third of history"), ("mid", "middle third"),
                      ("high", "highest third")):
        ax.plot([], [], "o", color=col[name], label=lab)
    ax.plot([], [], "o", color=SURF, mec=INK, mew=1.6, ms=8, label="where TODAY sits")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    ax.set_ylim(-1.1, len(feats) - 0.5)
    ax.set_title("Rate level, speed and curve shape barely move the 12-month odds\n"
                 "every cell sits inside the base rate's own uncertainty · "
                 "0 of 30 tests significant", loc="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, "S&P 500 price index, month-end origins 1971-01..2025-08. "
             "Terciles fixed on the full sample. Shaded band: 90% CI on the base rate "
             "(stationary bootstrap).", fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(OUT, "fig1_rates.png"), dpi=160, facecolor=SURF)


# ------------------------------------------------------------ fig 2
def fig2():
    p = P.build()
    spx = p["spx"]
    origins = pd.PeriodIndex(p.loc[P.START:].index)
    paths = []
    for t in origins:
        seg = spx.loc[t:t + 18]
        if len(seg) == 19 and seg.notna().all() and t + 18 < origins[-1]:
            paths.append((seg / seg.iloc[0]).values)
    paths = np.array(paths)
    q = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    fig.patch.set_facecolor(SURF)
    style(ax)
    m = np.arange(19)
    ax.fill_between(m, q[0], q[2], color=BASE, alpha=0.16, lw=0,
                    label="all months since 1971: 10th-90th percentile")
    ax.plot(m, q[1], color=BASE, lw=2, label="all months since 1971: median")
    med = R["cape_median_1971"]
    for a in R["analogs"]:
        t = pd.Period(a["month"], "M")
        seg = spx.loc[t:t + 18]
        v = (seg / seg.iloc[0]).values
        hi = a["cape"] > med
        ax.plot(np.arange(len(v)), v, color=S2 if hi else S1, lw=1.3, alpha=0.9)
        ax.text(18.2, v[-1], a["month"][:4], fontsize=7, color=INK2, va="center")
        if a["cape"] >= 35:
            k = int(np.argmin(v))
            ax.annotate(f"{a['month'][:4]}: the only match at today's valuation\n"
                        f"(CAPE {a['cape']:.0f}) — the one that fell",
                        xy=(k, v[k]), xytext=(2.2, 0.84), fontsize=8,
                        color=INK, arrowprops=dict(arrowstyle="->", color=INK2, lw=0.9))
    ax.plot([], [], color=S2, label=f"analog, CAPE above {med:.0f} (median)")
    ax.plot([], [], color=S1, label="analog, CAPE below median")
    ax.axhline(1, color=INK2, lw=0.8)
    ax.axvline(10, color=INK, lw=1, ls=":")
    ax.text(10.1, ax.get_ylim()[1] * 0.98, "≈ July 2027\n(sale close)", fontsize=8,
            color=INK, va="top")
    ax.set_xlim(0, 20)
    ax.set_xticks([0, 6, 12, 18])
    ax.set_xticklabels(["today", "+6m", "+12m", "+18m"])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{100*(v-1):+.0f}%"))
    ax.set_ylabel("S&P 500 vs the starting month")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.set_title("The 10 closest historical matches to today's rate picture\n"
                 "9 of 10 higher a year later — but rate-matching did WORSE than the "
                 "base rate out of sample: stories, not odds",
                 loc="left", fontsize=11, color=INK)
    fig.text(0.01, 0.01, "Matched on 10y vs 5-yr avg, 12m change in 3y and 10y, "
             "20y−3y curve, 12m change in the 3m bill; at most one match per 18 months.",
             fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(OUT, "fig2_analogs.png"), dpi=160, facecolor=SURF)


# ------------------------------------------------------------ fig 3
def fig3():
    """The headline: base-rate odds by horizon, with 90% CIs, and the long
    (1928+) record as a check on how kind the post-1971 era was."""
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 4.4), sharey=True)
    fig.patch.set_facecolor(SURF)
    rows = ["higher (price)", "higher (1928+ record)", "trailed 3-month bills\n(incl. dividends)",
            "fell ≥20% below start\nat some point", "ended ≥20% lower"]
    for ax, h in zip(axes, ("6", "12", "18")):
        style(ax)
        R_ = R["h"][h]
        b = R_["base"]
        vals = [(b["p_up"], b["p_up_ci90"]), (R_["base_1928"]["p_up"], None),
                (b["tr_p_below_cash"], b["tr_p_below_cash_ci90"]),
                (b["p_dd20"], None), (b["p_dn20"], None)]
        cols = [S1, BASE, S2, CRIT, CRIT]
        ys = np.arange(len(rows))[::-1]
        for y, (v, ci), c in zip(ys, vals, cols):
            ax.barh(y, v, height=0.56, color=c, alpha=0.9)
            if ci:
                ax.plot(ci, [y, y], color=INK, lw=1.2)
                ax.plot([ci[0], ci[0]], [y - 0.12, y + 0.12], color=INK, lw=1.2)
                ax.plot([ci[1], ci[1]], [y - 0.12, y + 0.12], color=INK, lw=1.2)
            ax.text((ci[1] if ci else v) + 0.02, y, pct(v), va="center", fontsize=8.5,
                    color=INK, weight="bold" if y == ys[0] else None)
        ax.set_xlim(0, 1.0)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(pct))
        ax.set_title(f"{h} months out", fontsize=10, color=INK, loc="left")
    axes[0].set_yticks(np.arange(len(rows))[::-1])
    axes[0].set_yticklabels(rows, fontsize=8.5)
    fig.suptitle("The answer: the S&P's historical odds — rates don't measurably move them\n"
                 "1971+ month-end origins; bars = 90% CI (stationary bootstrap). The 1928+ "
                 "record, Depression included, runs ~5-7pp lower.",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(os.path.join(OUT, "fig3_odds.png"), dpi=160, facecolor=SURF)


# ------------------------------------------------------------ fig 5
def fig5():
    """Valuation, shown with the SAME test the rates got — and its episode
    count, which is the honest n."""
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.6))
    fig.patch.set_facecolor(SURF)
    labels = ["all months", "CAPE above\nmedian (22)\npre-registered", "CAPE ≥ 25",
              "CAPE ≥ 30", "CAPE ≥ 35", "CAPE ≥ 40"]
    for ax, (key, title) in zip(axes, (("up", "higher 18 months later"),
                                       ("fell20", "fell ≥20% below start within 18 months"))):
        style(ax)
        V = R["h"]["18"]["valuation"]
        cells = [None, V["median_split_prereg"]] + [V[f"cape_ge_{c}"] for c in (25, 30, 35, 40)]
        xs = np.arange(len(labels))
        for x, c in zip(xs, cells):
            if c is None:
                v = R["h"]["18"]["base"]["p_up" if key == "up" else "p_dd20"]
                ax.bar(x, v, color=BASE, width=0.62)
                ax.text(x, v + 0.02, pct(v), ha="center", fontsize=8, color=INK)
                continue
            cc = c if "p_event" in c else c[key]
            if key == "fell20" and "p_event" in c:          # median split row: up only
                ax.text(x, 0.03, "n/a", ha="center", fontsize=7.5, color=INK2)
                continue
            v, (lo, hi) = cc["p_event"], cc["ci90"]
            ax.bar(x, v, color=S2 if x > 1 else S1, width=0.62)
            ax.plot([x, x], [max(0, cc["p_base"] + lo), min(1, cc["p_base"] + hi)], color=INK, lw=1.1)
            n_eras = len(c["eras"]) if "eras" in c else None
            ax.text(x, v + 0.02, pct(v), ha="center", fontsize=8, color=INK)
            k_ = n_eras or cc["episodes"]
            ax.text(x, -0.1, f"{k_} era{'s' if k_ != 1 else ''}", ha="center",
                    fontsize=7.5, color=INK2)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=7.5)
        ax.set_ylim(-0.14, 1.0)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: "" if v < 0 else pct(v)))
        ax.set_title(title, fontsize=10, color=INK, loc="left")
    fig.suptitle(f"Valuation: a risk to plan around, not a validated signal (today CAPE "
                 f"{R['today']['cape']:.0f})\nThe pre-registered split shows nothing; "
                 "the cutoffs were chosen after seeing the data and rest on 1-3 eras; "
                 "every CI crosses the base rate",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(os.path.join(OUT, "fig5_valuation.png"), dpi=160, facecolor=SURF)


# ------------------------------------------------------------ fig 4
def fig4():
    s = pd.DataFrame(PW["summary"])
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    fig.patch.set_facecolor(SURF)
    style(ax)
    ax.plot(100 * s["r2"], s["power"], "o-", color=S1, lw=2, ms=6)
    fp = float(s.loc[s["r2"] == 0, "power"].iloc[0])
    ax.axhline(fp, color=BASE, lw=1, ls="--")
    ax.text(29, fp + 0.01, "false-positive rate", ha="right", fontsize=8, color=INK2)
    ax.axvspan(2, 10, color=S3, alpha=0.12, lw=0)
    ax.text(6, 0.13, "realistic size\nfor rate effects", ha="center", fontsize=8,
            color=INK2)
    for _, r in s.iterrows():
        ax.text(100 * r["r2"], r["power"] + 0.008, f"{100*r['power']:.1f}%",
                ha="center", fontsize=7.5, color=INK)
    ax.set_ylim(0, 0.2)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{100*v:.0f}%"))
    ax.set_yticks([0, 0.05, 0.10, 0.15, 0.20])
    ax.set_xlabel("share of 12-month S&P variance a rate signal would explain (%)")
    ax.set_ylabel("chance the test detects it")
    ax.set_title("Why 'no signal found' ≠ 'rates don't matter'\n55 years can't confirm "
                 "a rate effect even one moving 12m odds ~60%→82% per SD (10% here): "
                 "caught ≤3% of the time", loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_power.png"), dpi=160, facecolor=SURF)


if __name__ == "__main__":
    fig1(); fig2(); fig3(); fig4(); fig5()
    print("written to", OUT)
