"""Figures for RESEARCH_EXIT2.md. usage: python3 charts2.py (needs matplotlib)"""
import dataclasses
import json
import math
import os
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

from harness2 import BASE, S4_CFG, T_2013, T_IS_END, extend, load_asset, run_s4x  # noqa: E402
from variants2 import ALL  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e4e3df", "#fcfcfb"
COL = {"V1": "#2a78d6", "V2": "#eb6834", "V3": "#1baf7a", "V4": "#eda100", "V5": "#e87ba4"}
LAB = {"V1": "V1 scale down as volatility rises", "V2": "V2 scale with trend strength",
       "V3": "V3 trail width by market regime", "V4": "V4 trail tightens with time / profit, SAR",
       "V5": "V5 multivariate model exit"}
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def title(ax, head, sub):
    ax.set_title(head, loc="left", fontsize=12, fontweight="bold", pad=24, color=INK)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2)


R = json.load(open(os.path.join(HERE, "results_sel.json")))
base, rows = R["base"], R["rows"]
bar_a = 0.10 * base["A"]["exit"]["mar"]

# ------------------------------------------------------------- figure 1
fig, ax = plt.subplots(figsize=(10, 6.2), dpi=200)
fig.patch.set_facecolor(SURF)
style(ax)
xs = [r["judge"]["dA_exit"] for r in rows]
ys = [sum(r["judge"]["dD"].values()) / 4 for r in rows]
ax.add_patch(plt.Rectangle((bar_a, 0), 0.6, 0.6, color=COL["V3"], alpha=0.07, zorder=0))
ax.axvline(bar_a, color=INK2, linewidth=1.2, linestyle=(0, (4, 3)))
ax.axvline(0, color=INK2, linewidth=0.8)
ax.axhline(0, color=INK2, linewidth=0.8)
for fam in COL:
    sel = [(x, y) for r, x, y in zip(rows, xs, ys) if r["family"] == fam]
    ax.scatter([p[0] for p in sel], [p[1] for p in sel], s=48, color=COL[fam], edgecolor=SURF,
               linewidth=1.5, zorder=4, label=LAB[fam])
names = {"V4_acc_time_a0.5_min3.5": ("trail 5 to 3.5 ATR over ~3 weeks", (-10, 10)),
         "V3_regime_highvol_wide": ("wider trail when volatility is high", (6, 4)),
         "V1_volscale_rv_b25": ("cut size as volatility rises", (-8, -14)),
         "V5_logit_p70": ("multivariate model", (6, 4)),
         "V4_psar_max0.2": ("Parabolic SAR", (6, -12)),
         "V2_tscale_slow_d1": ("scale with slow trend strength", (6, 4))}
for r, x, y in zip(rows, xs, ys):
    if r["name"] in names:
        lab, off = names[r["name"]]
        ax.annotate(lab, xy=(x, y), xytext=off, textcoords="offset points", fontsize=8.5, color=INK,
                    ha="right" if off[0] < 0 else "left")
ax.text(bar_a + 0.01, max(ys) + 0.05, "selection zone: +10% on BTC\nand better on the other coins (empty)",
        color=INK2, fontsize=8.5, va="top")
ax.set_xlim(min(xs) - 0.08, max(0.5, max(xs) + 0.15))
ax.set_ylim(min(ys) - 0.06, max(ys) + 0.08)
ax.set_xlabel(f"Change in MAR on BTC, live strategy mix 2022-26 (baseline {base['A']['exit']['mar']:.2f}; dashed = +10% bar)")
ax.set_ylabel("Avg MAR change on ETH, LTC, XRP, BCH")
ax.legend(loc="lower right", frameon=False, fontsize=8, labelcolor=INK2)
title(ax, "0 of 28 adaptive exits made the cut",
      "Each dot is one registered exit rule. No rule was run on the 12 fresh holdout coins: "
      "none qualified.")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "exit2_fig1_map.png"), facecolor=SURF)

# ------------------------------------------------------------- figure 2
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
fig.patch.set_facecolor(SURF)
style(ax)
for fam in COL:
    sel = [r for r in rows if r["family"] == fam and r["B"]["kept"]["median"] is not None]
    ax.scatter([100 * r["B"]["kept"]["median"] for r in sel], [r["B"]["end_x"] for r in sel], s=48,
               color=COL[fam], edgecolor=SURF, linewidth=1.5, zorder=4, label=LAB[fam])
bk, bx = 100 * base["B"]["kept"]["median"], base["B"]["end_x"]
ax.scatter([bk], [bx], s=120, marker="D", color=INK, zorder=5, label="today's trail (5 ATR)")
ax.annotate(f"today: keeps {bk:.0f}% of the peak, x{bx:,.0f}", xy=(bk, bx), xytext=(8, 6),
            textcoords="offset points", fontsize=9, color=INK, fontweight="bold")
ax.set_yscale("log")
ax.set_xlabel("Median share of the peak move kept, on runs that went 10%+ in the trade's favor (%)")
ax.set_ylabel("Growth of $1, BTC trend leg 2013 to Jul 2026 (log)")
ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK2)
ax.annotate("regime-based trails: more growth on BTC 2013-26,\nbut worse on the other coins or the 2022-26 live mix",
            xy=(46.3, 4300), xytext=(30, 1.6e4), textcoords="data", fontsize=8.5, color=INK2,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_ylim(top=6e4)
title(ax, "Keeping more of each run: some exits won on BTC's history, none held up elsewhere",
      "Each dot is a rule (BTC trend leg alone, 2013 to Jul 2026, in-sample; the two Parabolic SAR rules "
      "went below zero and are not shown). None also held up on the other coins.")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "exit2_fig2_keep_vs_growth.png"), facecolor=SURF)

# ------------------------------------------------------------- figure 3
byname = {x.name: x for x in ALL}
pick = [("BASE", "today's trail (5 ATR)", "#2a78d6", BASE),
        ("V4_acc_time_a0.5_min3.5", "trail tightens 5 to 3.5 ATR over ~3 weeks", "#eda100",
         byname["V4_acc_time_a0.5_min3.5"])]
fig, axes = plt.subplots(1, 2, figsize=(11, 5), dpi=200)
fig.patch.set_facecolor(SURF)
for ax, sym, win in ((axes[0], "btc", (T_2013, T_IS_END)), (axes[1], "eth", (None, None))):
    style(ax)
    A = load_asset(sym)
    E = extend(A)
    for _, lab, c, x in pick:
        _, m = run_s4x(A, E, x, win[0], win[1], cfg=NOHALT)
        t = [datetime.fromtimestamp(p[0], timezone.utc) for p in m]
        e = [p[1] / m[0][1] for p in m]
        ax.plot(t, e, color=c, linewidth=1.8, label=lab)
        ax.annotate(f"x{e[-1]:,.1f}" if e[-1] < 100 else f"x{e[-1]:,.0f}", xy=(t[-1], e[-1]),
                    xytext=(3, -3), textcoords="offset points", fontsize=8.5, color=INK, fontweight="bold")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title(f"{sym.upper()} trend leg alone", loc="left", fontsize=10, color=INK)
axes[0].set_ylabel("Growth of $1 (log)")
axes[0].legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK2)
fig.suptitle("The closest call: a trail that tightens with time halved BTC growth and hurt ETH",
             x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "exit2_fig3_nearmiss.png"), facecolor=SURF)
print("wrote 3 figures")
