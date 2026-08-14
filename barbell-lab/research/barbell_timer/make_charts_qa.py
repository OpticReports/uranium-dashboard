#!/usr/bin/env python3
"""Phase 4 referee figures (independent recompute, qa_phase4 engine).

fig7_qa_lag_stress.png  — the kill chart: relmom_cash executed on time vs one
                          month late, OOS, log scale, vs the 50/50 null.
fig8_qa_robustness.png  — start-date / drop-year / signal-noise robustness of
                          the relmom_cash Calmar edge over the null.
"""
import importlib.util
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("qa", os.path.join(HERE, "qa_phase4.py"))
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)

C_MAIN, C_LAG, C_NULL, C_SPY = "#2a78d6", "#eb6834", "#52514e", "#b0afa8"
INK, MUT = "#0b0b0b", "#52514e"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#d8d7d0",
                     "axes.labelcolor": MUT, "xtick.color": MUT,
                     "ytick.color": MUT, "figure.facecolor": "white",
                     "axes.facecolor": "white"})

panel = qa.load_panel()
rf = panel["bills"]
A = pd.DataFrame({"gde": panel["gde_synth"], "spy": panel["spx_tr"],
                  "boxx": panel["bills"] - qa.BOXX_DRAG / 12})
st2 = qa.rule2_states(panel)
OOS = qa.OOS
r2 = qa.win(qa.bt(st2, A), OOS)
r2l = qa.win(qa.bt(st2, A, lag=2), OOS)
null = qa.win(qa.bt(pd.Series("5050", index=panel.index), A), OOS)
spy = qa.win(panel["spx_tr"], OOS)
Q = json.load(open(os.path.join(HERE, "qa_results.json")))


def despine(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#eceae4", lw=0.7)
    ax.set_axisbelow(True)


# ------------------------------------------------------ fig 7: lag stress ---
fig, ax = plt.subplots(figsize=(9, 4.6), dpi=160)
x = r2.index.to_timestamp()
for r, c, lw in ((null, C_NULL, 1.4), (spy, C_SPY, 1.4),
                 (r2l, C_LAG, 1.8), (r2, C_MAIN, 1.8)):
    ax.plot(x, (1 + r).cumprod(), color=c, lw=lw)
ax.set_yscale("log")
ax.set_yticks([1, 2, 5, 10, 20, 50, 100, 200])
ax.get_yaxis().set_major_formatter(mtick.ScalarFormatter())
despine(ax)
oct08 = pd.Period("2008-10", "M")
eqL = (1 + r2l).cumprod()
ax.text(pd.Period("2009-04", "M").to_timestamp(), 1.55,
        "Oct-2008: lagged exit eats a -31.6% GDE month\n"
        "(the on-time rule exited at the Oct-1 open)", fontsize=8, color=INK)
ax.annotate("", xy=(oct08.to_timestamp(), eqL.loc[oct08] * 1.05),
            xytext=(oct08.to_timestamp(), eqL.loc[oct08] * 2.6),
            arrowprops=dict(arrowstyle="->", color=C_LAG, lw=1.2))
lab = [("relmom_cash, executed on time  (15.2%/yr, maxDD -23%)", C_MAIN, r2),
       ("relmom_cash, ONE MONTH LATE  (12.9%/yr, maxDD -49%)", C_LAG, r2l),
       ("static 50/50 null  (12.8%/yr, -45%)", C_NULL, null),
       ("B&H SPY  (11.0%/yr, -51%)", C_SPY, spy)]
for i, (t, c, r) in enumerate(lab):
    ax.text(0.01, 0.97 - 0.062 * i, t, transform=ax.transAxes, color=c,
            fontsize=8.5, fontweight="bold" if c in (C_MAIN, C_LAG) else "normal",
            va="top")
ax.set_title("Phase-4 kill test: the drawdown edge requires on-time execution\n"
             "growth of $1, 1990-02 -> 2026-07 (month-end, log scale) — referee recompute",
             loc="left", fontsize=10, color=INK)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "figs", "fig7_qa_lag_stress.png"))
plt.close(fig)

# --------------------------------------------------- fig 8: robustness grid --
fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), dpi=160)

# (a) start-date sensitivity: Calmar by start year
sd = Q["start_date"]
yrs = sorted(int(y) for y in sd)
ax = axes[0]
ax.plot(yrs, [sd[str(y)]["relmom_cash"]["Calmar"] for y in yrs], color=C_MAIN,
        lw=1.8, marker="o", ms=3)
ax.plot(yrs, [sd[str(y)]["static_5050"]["Calmar"] for y in yrs], color=C_NULL,
        lw=1.4, marker="o", ms=3)
despine(ax)
ax.set_title("Calmar by start year (start -> 2026-07)", loc="left", fontsize=9, color=INK)
ax.text(1991, 0.95, "relmom_cash", color=C_MAIN, fontsize=8.5, fontweight="bold")
ax.text(1994, 0.34, "50/50 null", color=C_NULL, fontsize=8.5)
ax.text(0.30, 0.02, "edge positive at all 26 starts (min +0.33)",
        transform=ax.transAxes, fontsize=7.5, color=MUT)

# (b) drop-single-year: maxDD with year Y removed
dy = Q["drop_year"]
yrs2 = sorted(int(y) for y in dy)
ax = axes[1]
ax.plot(yrs2, [dy[str(y)]["relmom_cash"]["MaxDD"] * 100 for y in yrs2],
        color=C_MAIN, lw=1.8, marker="o", ms=3)
ax.plot(yrs2, [dy[str(y)]["static_5050"]["MaxDD"] * 100 for y in yrs2],
        color=C_NULL, lw=1.4, marker="o", ms=3)
despine(ax)
ax.set_title("OOS maxDD with year Y deleted (%)", loc="left", fontsize=9, color=INK)
ax.set_xlabel("year removed")
ax.text(2007, -20.5, "relmom_cash", color=C_MAIN, fontsize=8.5, fontweight="bold")
ax.text(2011, -43.2, "50/50 null", color=C_NULL, fontsize=8.5)
ax.text(0.05, 0.45, "gap survives removing\n2001, 2008, 2020 or 2022",
        transform=ax.transAxes, fontsize=7.5, color=MUT)

# (c) signal-noise decay: Calmar vs flip probability (median, p10)
ns = Q["signal_noise"]["relmom_cash"]
ax = axes[2]
ps = [0, 15, 30]
med = [Q["headline_recompute"]["relmom_cash"]["oos"]["Calmar"],
       ns["p15"]["median_Calmar"], ns["p30"]["median_Calmar"]]
p10 = [med[0], ns["p15"]["p10_Calmar"], ns["p30"]["p10_Calmar"]]
ax.plot(ps, med, color=C_MAIN, lw=1.8, marker="o", ms=4)
ax.plot(ps, p10, color=C_MAIN, lw=1.2, ls=":", marker="o", ms=3)
nullC = Q["headline_recompute"]["static_5050"]["oos"]["Calmar"]
ax.axhline(nullC, color=C_NULL, lw=1.2)
despine(ax)
ax.set_title("Calmar under random state flips (2000 trials)", loc="left",
             fontsize=9, color=INK)
ax.set_xlabel("% of monthly decisions flipped")
ax.set_xticks(ps)
ax.text(2.0, med[0] + 0.005, "median", color=C_MAIN, fontsize=8, va="bottom")
ax.text(6.5, 0.47, "10th pct", color=C_MAIN, fontsize=8, va="top")
ax.text(0.5, nullC - 0.012, "50/50 null (0.28)", color=C_NULL, fontsize=8, va="top")
ax.text(0.35, 0.02, "P(Calmar>null): 95% at 15%, 78% at 30%",
        transform=ax.transAxes, fontsize=7.5, color=MUT)

fig.suptitle("relmom_cash robustness battery — referee recompute (OOS 1990-02 -> 2026-07)",
             x=0.005, ha="left", fontsize=10, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(os.path.join(HERE, "figs", "fig8_qa_robustness.png"))
print("wrote figs/fig7_qa_lag_stress.png, figs/fig8_qa_robustness.png")
