#!/usr/bin/env python3
"""Figures for studies/labor-stress-board.md (and the rate-spike re-test).

    python3 charts.py [outdir]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study as S  # noqa: E402
from app.metrics import labor_stress as L  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "figs")
os.makedirs(OUT, exist_ok=True)
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
S1, S2, S3, BASE, CRIT = "#2a78d6", "#eb6834", "#1baf7a", "#8a8985", "#e34948"
REC = "#e9e8e4"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})


def style(ax):
    ax.set_facecolor(SURF)
    ax.grid(color=GRID, lw=0.8, axis="y")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def t(k):
    return dt.date(k[0], k[1], 15)


def shade(ax, lo=None, hi=None):
    for p, tr in S.PEAKS:
        ax.axvspan(t(L.ym_add(p, 1)), t(tr), color=REC, lw=0, zorder=0)


SER = {k: S.load(v) for k, v in S.SERIES.items()}
VALS, LIT = S.run(SER, sahm_from="unrate")
RES = json.load(open(os.path.join(HERE, "results.json")))


def fig_timeline():
    comp = S.composite(LIT)
    rows = [("A1", "Insured unemployment (SOS) — layoffs", S1),
            ("A2", "Job losers — layoffs", S1), ("A3", "Continuing claims — layoffs", S1),
            ("B1", "Prime-age employment drawdown — slack", S2),
            ("B2", "Participation-adjusted unemployment — slack", S2),
            ("C1", "Sahm rule — slack", S2)]
    fig, ax = plt.subplots(figsize=(12, 4.8))
    fig.patch.set_facecolor(SURF)
    style(ax)
    ax.grid(False)
    shade(ax)
    for i, (rid, lab, c) in enumerate(rows):
        y = len(rows) - i + 1
        ks = [k for k, v in LIT[rid].items() if v and k >= (1972, 1)]
        ax.scatter([t(k) for k in ks], [y] * len(ks), marker="|", s=90, color=c, lw=1.6)
        ax.text(dt.date(1971, 1, 1), y, lab, ha="right", va="center", fontsize=8, color=INK2)
    ks = [k for k, v in comp.items() if v and k >= (1972, 1)]
    ax.scatter([t(k) for k in ks], [0.6] * len(ks), marker="|", s=260, color=CRIT, lw=2.6)
    ax.text(dt.date(1971, 1, 1), 0.6, "BOARD ALERT (layoffs AND slack)", ha="right",
            va="center", fontsize=8.5, color=INK, weight="bold")
    ax.annotate("Aug 2024: lit with\nno recession", xy=(t((2024, 8)), 0.6),
                xytext=(t((2015, 1)), -0.9), fontsize=8, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.9))
    ax.set_ylim(-1.6, len(rows) + 2)
    ax.set_yticks([])
    ax.set_xlim(dt.date(1971, 6, 1), dt.date(2026, 12, 1))
    fig.suptitle("Labor Stress Board, 1972-2026 (in-sample): flagged 5 of 7 recessions, 3 months "
                 "before to 1 month after they began, a median 2 months before the Sahm rule.\n"
                 "No alert without a recession nearby 1972-2020 — then one in Aug 2024 with none. "
                 "Job losers alone did as well. Grey = NBER recessions.",
                 x=0.01, ha="left", fontsize=10.5, color=INK)
    fig.subplots_adjust(left=0.24, right=0.98, top=0.86, bottom=0.08)
    fig.savefig(os.path.join(OUT, "fig_board_timeline.png"), dpi=160, facecolor=SURF)


def fig_slack():
    g = {k: L.monthly(*S.load(v)) for k, v in
         {"un": "UNEMPLOY", "lf": "CLF16OV", "u6": "U6RATE", "wj": "NILFWJN"}.items()}
    u3 = {k: 100 * g["un"][k] / g["lf"][k] for k in g["un"] if k in g["lf"]}
    wj = {k: 100 * (g["un"][k] + g["wj"][k]) / (g["lf"][k] + g["wj"][k])
          for k in g["un"] if k in g["lf"] and k in g["wj"]}
    pa = VALS["_paur"]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    fig.patch.set_facecolor(SURF)
    style(ax)
    start = (2015, 1)
    for series, lab, c, lw in ((g["u6"], "U-6 (incl. involuntary part-time, marginally attached)", BASE, 1.6),
                               (wj, "unemployed + want a job", S3, 1.8),
                               (pa, "participation-adjusted (upper bound)", S2, 2.0),
                               (u3, "headline U-3", S1, 2.2)):
        ks = sorted(k for k in series if k >= start and not ((2020, 3) <= k <= (2020, 12)))
        # break the line across the omitted months instead of bridging them
        xs, ys = [], []
        for k in ks:
            if xs and k == (2021, 1):
                xs.append(t((2020, 7)))
                ys.append(np.nan)
            xs.append(t(k))
            ys.append(series[k])
        ax.plot(xs, ys, color=c, lw=lw, label=lab)
        ax.text(t(ks[-1]) + dt.timedelta(days=40), series[ks[-1]], f"{series[ks[-1]]:.1f}%",
                va="center", fontsize=8.5, color=INK, weight="bold")
    ax.set_ylabel("% (2020 pandemic months omitted)")
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.set_xlim(dt.date(2015, 1, 1), dt.date(2027, 3, 1))
    ax.set_title("Is 4.1% too good? Broader measures fell with the headline over the past year;\n"
                 "the participation-adjusted rate — an upper bound — runs ~0.5pp higher and flat",
                 loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_hidden_slack.png"), dpi=160, facecolor=SURF)


def fig_hire_fire():
    ue = L.monthly(*S.load("LNS17100000"))
    un = L.monthly(*S.load("UNEMPLOY"))
    jf = L.ma3({k: 100 * ue[k] / un[L.ym_add(k, -1)] for k in ue if L.ym_add(k, -1) in un})
    iur = L.monthly(*S.load("IURSA"))
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    fig.patch.set_facecolor(SURF)
    for ax, series, lab, c, off in ((axes[0], jf, "Job-finding rate: share of the unemployed hired each month (3-mo avg, %)", S1, (-14, -18)),
                                    (axes[1], iur, "Insured unemployment rate: people on jobless benefits, % of covered jobs", S2, (-14, 10))):
        style(ax)
        shade(ax)
        ks = sorted(k for k in series if k >= (1994, 1))
        ax.plot([t(k) for k in ks], [series[k] for k in ks], color=c, lw=1.6)
        ax.plot([t(ks[-1])], [series[ks[-1]]], "o", color=c, ms=6, mec=SURF, mew=1.5)
        ax.annotate(f"{series[ks[-1]]:.1f}", xy=(t(ks[-1]), series[ks[-1]]),
                    xytext=off, textcoords="offset points", fontsize=9, color=INK,
                    weight="bold")
        ax.set_title(lab, loc="left", fontsize=9, color=INK2)
        ax.set_xlim(dt.date(1994, 1, 1), dt.date(2027, 1, 1))
    fig.suptitle("Low-hire, low-fire: the job-finding rate is its lowest since 2016 (outside the "
                 "2020-21 pandemic), while benefit claims stay near record lows", x=0.01, ha="left",
                 fontsize=10.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(os.path.join(OUT, "fig_hire_fire.png"), dpi=160, facecolor=SURF)


def fig_spike():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rs", os.path.join(HERE, "..", "rate_spike", "study.py"))
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    d60 = rs.d60_series(True)
    res = json.load(open(os.path.join(HERE, "..", "rate_spike", "results.json")))
    fig, ax = plt.subplots(figsize=(12, 4.6))
    fig.patch.set_facecolor(SURF)
    style(ax)
    for p, tr in S.PEAKS[1:]:
        ax.axvspan(t(L.ym_add(p, 1)), t(tr), color=REC, lw=0, zorder=0)
    ax.plot(d60.index, d60.values, color=BASE, lw=0.8)
    ax.axhline(75, color=S2, lw=1.4, ls="--")
    ax.text(dt.date(1998, 1, 1), 86, "+75bp spike line", color=S2, fontsize=8.5, weight="bold")
    for e in res["T1"]["episode_list"]:
        d = dt.date.fromisoformat(e["first"])
        v = d60.loc[str(d)] if str(d) in d60.index else 75
        ax.plot([d], [float(np.atleast_1d(v)[0])], "o", ms=8,
                color=CRIT if e["hit"] else INK2, mec=SURF, mew=1.5, zorder=4)
    ax.plot([], [], "o", color=CRIT, label="recession began within 12 months")
    ax.plot([], [], "o", color=INK2, label="no recession within 12 months")
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)
    ax.set_ylabel("30y yield, change over 60 trading days (bp)")
    ax.set_ylim(-250, 350)
    ax.set_title("30-year yield spikes: a recession followed 3 of 20 spike episodes, all by 1990 — "
                 "none of the 13 since.\nToo few recessions to confirm or rule out a link; the "
                 "old '44% vs 21%' counted overlapping Volcker weeks. Grey = NBER recessions.",
                 loc="left", fontsize=10.5, color=INK)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_rate_spike_episodes.png"), dpi=160, facecolor=SURF)


if __name__ == "__main__":
    fig_timeline()
    fig_slack()
    fig_hire_fire()
    fig_spike()
    print("written to", OUT)
