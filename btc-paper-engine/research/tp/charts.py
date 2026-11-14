"""Figures for RESEARCH_TP.md. usage: python3 charts.py  (needs matplotlib)"""
import dataclasses
import json
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from harness import (BASE, S4_CFG, T_2013, T_2022, T_IS_END, load_asset,  # noqa: E402
                     run_s4)
from variants import ROUND1  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
NOHALT = dataclasses.replace(S4_CFG, dd_halt=1.0)
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK})


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def title(fig, ax, head, sub):
    ax.set_title(head, loc="left", fontsize=12, fontweight="bold", pad=24)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2)


rows = []
for rnd in ("r1", "r2", "r3", "r4"):
    rows += [dict(r, rnd=rnd) for r in json.load(open(os.path.join(HERE, f"results_{rnd}.json")))["rows"]]
null = json.load(open(os.path.join(HERE, "null.json")))
null4 = json.load(open(os.path.join(HERE, "null4.json")))
q95 = null["q"]["40"]["q95"]                  # rounds 1-3 bar (0.587 at N=30)
q95_4 = null4["q"]["62"]["q95"]               # round 4 bar
singles = [d for rep in null["reps"] for d in rep]
singles_sa = [d for rep in null4["reps_extra"] for d in rep]

# ---------------------------------------------------------------- figure 1
fig, (ax, axh) = plt.subplots(2, 1, figsize=(10, 7.6), dpi=200, sharex=True,
                              gridspec_kw=dict(height_ratios=[2.4, 1]))
fig.patch.set_facecolor(SURF)
style(ax)
style(axh)
XMAX = 1.05
ys_all = [sum(r["judge"]["dD"].values()) / 4 for r in rows]
ylo, yhi = min(ys_all) - 0.04, max(0.14, max(ys_all) + 0.06)
ax.add_patch(plt.Rectangle((q95, 0), XMAX - q95, yhi, color=AQUA, alpha=0.08, zorder=0))
for a_ in (ax, axh):
    a_.axvline(q95, color=ORANGE, linewidth=1.5, linestyle=(0, (4, 3)), zorder=3)
    a_.axvline(q95_4, color=ORANGE, linewidth=1.0, linestyle=(0, (1, 2)), zorder=3)
    a_.axvline(0, color=INK2, linewidth=0.8, zorder=2)
ax.axhline(0, color=INK2, linewidth=0.8, zorder=2)
for rnd_set, col, lab in ((("r1", "r2", "r3"), BLUE, "rounds 1-3: take profit, re-enter on the next breakout (40)"),
                          (("r4",), ORANGE, "round 4: take profit, then stand aside 5 days (22)")):
    sel = [r for r in rows if r["rnd"] in rnd_set]
    ax.scatter([r["judge"]["dA_exit"] for r in sel],
               [sum(r["judge"]["dD"].values()) / 4 for r in sel],
               s=46, color=col, edgecolor=SURF, linewidth=1.5, zorder=4, label=lab)
ax.text(q95 + 0.012, yhi - 0.01, "pass zone: beats luck on\nBTC and better on the\nother coins (empty)",
        color=INK2, fontsize=8.5, va="top")
names = {"F6_time120": ("exit after 20 days", (6, 4)),
         "F6_time120_sa30": ("20 days, then stand aside", (-8, -14)),
         "F1_tp8": ("full TP at 8 ATR", (-30, 9)),
         "F1_tp3": ("full TP at 3 ATR", (6, 4)),
         "F2_ptp3_f33": ("take 1/3 at 3 ATR", (-6, 7)),
         "F5b_rsi20": ("RSI 20/80 exit", (6, 4))}
for r in rows:
    if r["name"] in names:
        lab, off = names[r["name"]]
        ax.annotate(lab, xy=(r["judge"]["dA_exit"], sum(r["judge"]["dD"].values()) / 4),
                    xytext=off, textcoords="offset points", fontsize=8.5, color=INK,
                    ha="right" if off[0] < 0 else "left")
ax.set_ylim(ylo, yhi)
ax.set_ylabel("Avg MAR change on ETH, LTC,\nXRP, BCH (never used to pick)")
ax.legend(loc="lower left", frameon=False, fontsize=8.5, labelcolor=INK2)
title(fig, ax, "0 of 62 take-profit rules cleared the bar",
      "Each dot is one rule. Right = better on BTC (live strategy mix 2022-26, MAR 1.39, in-sample); "
      "up = better on four other coins.")
bins = [x / 40 for x in range(-48, 46)]
axh.hist(singles, bins=bins, color=MUTED, alpha=0.6, zorder=3, label="random exits")
axh.hist(singles_sa, bins=bins, histtype="step", color=ORANGE, linewidth=1.4, zorder=4,
         label="random exits + 5-day stand-aside")
share = sum(d > 0 for d in singles) / len(singles)
share_sa = sum(d > 0 for d in singles_sa) / len(singles_sa)
axh.text(-1.18, axh.get_ylim()[1] * 0.92, f"rules that exit at random moments make the strategy\n"
         f"worse {1 - share:.0%} of the time ({1 - share_sa:.0%} with a stand-aside)",
         color=INK, fontsize=8.5, va="top")
axh.text(q95 + 0.012, axh.get_ylim()[1] * 0.92, "luck bars: best of\n40 / 62 random rules,\n95th pct",
         color=INK, fontsize=8.5, va="top")
axh.legend(loc="center left", frameon=False, fontsize=8, labelcolor=INK2)
axh.set_ylabel("Random rules")
axh.set_xlabel("Change in MAR (return / max drawdown) on BTC, live strategy mix 2022-26")
axh.set_xlim(-1.2, XMAX)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig1_rules_vs_luck.png"), facecolor=SURF)

# ---------------------------------------------------------------- figure 2
A = load_asset("btc")
bk, _ = run_s4(A, BASE, T_2022, T_IS_END, cfg=NOHALT)
g = sorted([100 * (t.equity_after / t.equity_before - 1) for t in bk.trades], reverse=True)
lg = sorted([math.log(t.equity_after / t.equity_before) for t in bk.trades], reverse=True)
k = round(len(g) * 0.10)
fig, ax = plt.subplots(figsize=(10, 5.2), dpi=200)
fig.patch.set_facecolor(SURF)
style(ax)
ax.grid(axis="x", visible=False)
xs2 = list(range(1, len(g) + 1))
ax.bar(xs2[:k], g[:k], color=BLUE, width=0.75, zorder=3)
ax.bar(xs2[k:], g[k:], color=MUTED, width=0.75, zorder=3)
ax.axhline(0, color=INK2, linewidth=0.8)
ax.annotate(f"the best {k} trades: x{math.exp(sum(lg[:k])):.0f} growth\n(+{g[k - 1]:.0f}% to +{g[0]:.0f}% each)",
            xy=(k / 2, g[0] * 0.55), xytext=(28, 18), textcoords="offset points", fontsize=9,
            color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.text(len(g) * 0.55, 8, f"the other {len(g) - k} trades together: x{math.exp(sum(lg[k:])):.2f}\n"
        "(many small stop-outs, a few modest wins)", fontsize=9, color=INK)
ax.set_xlabel("130 trend trades, 2022 to Jul 2026, sorted best to worst")
ax.set_ylabel("Trade result, % of the strategy's equity")
ax.set_xlim(0, len(g) + 1)
title(fig, ax, "Where the trend strategy's money comes from: a few long runs",
      f"Net x{math.exp(sum(lg)):.1f}. 12 of the 13 blue trades ran 20+ days; the trailing stop kept a "
      "median 72% of their peak move. 2013-26: 34 of 340 trades carry it all.")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig2_where_money_comes_from.png"), facecolor=SURF)

# ---------------------------------------------------------------- figure 3
pick = [("F1_tp8", "full take-profit at 8 ATR", ORANGE),
        ("F2_ptp3_f33", "take 1/3 at 3 ATR, trail the rest", AQUA),
        ("F6_time120", "exit after 20 days", YELLOW)]
byname = {v.name: v for v in ROUND1}
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 7), dpi=200, sharex=True,
                              gridspec_kw=dict(height_ratios=[2.2, 1]))
fig.patch.set_facecolor(SURF)
for a_ in (ax, ax2):
    style(a_)
series = [("BASE", "trailing stop only (today)", BLUE, BASE)] + \
         [(n, lab, c, byname[n]) for n, lab, c in pick]
for n, lab, c, v in series:
    _, m = run_s4(A, v, T_2013, T_IS_END, cfg=NOHALT)
    t = [datetime.fromtimestamp(x[0], timezone.utc) for x in m]
    e = [x[1] / m[0][1] for x in m]
    ax.plot(t, e, color=c, linewidth=2 if n == "BASE" else 1.6, label=lab, zorder=4 if n == "BASE" else 3)
    pk, dd = 0, []
    for x in e:
        pk = max(pk, x)
        dd.append(100 * (x / pk - 1))
    ax2.plot(t, dd, color=c, linewidth=1.2 if n != "BASE" else 1.6, zorder=4 if n == "BASE" else 3)
    ax.annotate(f"x{e[-1]:,.0f}", xy=(t[-1], e[-1]), xytext=(4, -3), textcoords="offset points",
                fontsize=8.5, color=INK, fontweight="bold")
ax.set_yscale("log")
ax.set_ylabel("Growth of $1 (log scale)")
ax2.set_ylabel("Drawdown %")
ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK2)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
title(fig, ax, "BTC trend strategy alone, 2013 to Jul 2026: what different exits did",
      "Same entry rule, 6 bps/side, kill switch off; in-sample. The 20-day exit beat the trail here, "
      "but helped only 2 of 4 other coins and is within luck.")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "fig3_equity.png"), facecolor=SURF)
print("wrote fig1..fig3")
