"""Charts for the scale study. Reads the frozen JSONs; computes nothing new.

Run: python3 research/scale/charts.py
"""
from __future__ import annotations
import json, math, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = json.load(open(os.path.join(HERE, "envelope.json")))
LIQ = json.load(open(os.path.join(HERE, "liq.json")))
NSC = json.load(open(os.path.join(HERE, "nscale.json")))

# validated palette (dataviz reference instance, light mode; all checks PASS,
# aqua carries a contrast WARN -> every series is DIRECT-LABELLED, which is the
# required relief)
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8983"
BLUE, ORANGE, AQUA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"
GRID = "#dedcd3"

EQUITY = float(LIQ["equity"])
LEV = 1.5
MSTAR = float(NSC["stream"]["m_star"])
DD30 = float(NSC["stream"]["dd30_2y"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "grid.color": GRID, "grid.linewidth": 0.6,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2.0, "figure.dpi": 130,
})
usd = FuncFormatter(lambda v, _: (f"\\${v/1e6:.0f}m" if v >= 1e6 else
                                  f"\\${v/1e3:.0f}k" if v >= 1e3 else f"\\${v:.0f}"))

fig, AX = plt.subplots(2, 2, figsize=(14.5, 10.4))
fig.suptitle("Scaling the BTC book: what \\$100k and \\$1m of gross notional actually cost",
             fontsize=14, fontweight="bold", y=0.985, color=INK)
fig.text(0.5, 0.955, "Casey's premise holds - 2x the book on 2x the capital is the "
         "same risk. The constraint is CAPITAL, and it is not the 30% rail.",
         ha="center", fontsize=9.5, color=INK2)

# ---------------------------------------------------------------- A: the ladder
ax = AX[0][0]
eq = np.logspace(np.log10(3e4), np.log10(6e6), 300)
LINES = [("live config  0.15x equity", 0.15, MUTED, "--"),
         ("repo rail  0.30x  (= base <= equity)", 0.30, BLUE, "-"),
         ("Kelly envelope now  0.54x", REC := 0.54, ORANGE, "-"),
         ("Kelly ceiling, DD30 budget  1.32x", 1.32, AQUA, "-")]
for lbl, f, c, ls in LINES:
    ax.plot(eq, f * eq, color=c, ls=ls, label=lbl,
            lw=2.2 if ls == "-" else 1.6)
for tgt, nm in ((1e5, "\\$100k target"), (1e6, "\\$1m target")):
    ax.axhline(tgt, color=VIOLET, lw=1.2, ls=":")
    ax.text(3.15e4, tgt * 1.16, nm, color=VIOLET, fontsize=8.5, fontweight="bold")
ax.axvline(EQUITY, color=INK, lw=1.2, ls="-.")
ax.text(EQUITY * 1.10, 5.0e3, f"equity today  \\${EQUITY/1e3:.0f}k", color=INK,
        fontsize=8.5, fontweight="bold")
# where each ceiling reaches $1m
for lbl, f, c, ls in LINES:
    if ls != "-": continue
    ax.plot([1e6 / f], [1e6], "o", ms=7, color=c, mec=SURFACE, mew=1.6, zorder=5)
    ax.annotate(f"\\${1e6/f/1e6:.2f}m", (1e6 / f, 1e6), textcoords="offset points",
                xytext=(5, -14), color=c, fontsize=8.6, fontweight="bold")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlim(3e4, 6e6); ax.set_ylim(4e3, 9e6)
ax.xaxis.set_major_formatter(usd); ax.yaxis.set_major_formatter(usd)
ax.set_xlabel("account equity"); ax.set_ylabel("gross notional")
ax.set_title("A.  Gross notional is a fixed multiple of equity.\n"
             "     \\$1m needs \\$0.76m-\\$3.3m of capital, depending on the envelope.")
ax.grid(True, which="major", alpha=0.55); ax.grid(True, which="minor", alpha=0.18)
ax.legend(loc="lower right", frameon=False, fontsize=8.2, labelcolor=INK2)

# ------------------------------------------------- B: the drawdown price
ax = AX[0][1]
x = np.linspace(0.05, 8.5, 900)
c = x / (LEV * MSTAR)
e = 2.0 / c - 1.0
d = np.where(e > 0, 1.0 - np.exp(np.log(0.10) / np.maximum(e, 1e-9)), np.nan)
ax.plot(x, d * 100, color=ORANGE, lw=2.4, label="drawdown you must budget (Thorp, p=10%)")
ax.axhline(30, color=BLUE, lw=1.6, ls="--")
ax.text(9.25, 32.2, "the repo's 30% drawdown budget", color=BLUE,
        fontsize=8.5, fontweight="bold", ha="right")
PTS = [(0.150, "live today", MUTED), (0.300, "base=equity (the free 2x)", BLUE),
       (0.540, "Kelly envelope now", ORANGE),
       (1.000, "\\$100k on \\$100k equity", VIOLET),
       (1.320, "DD30 ceiling", AQUA)]
for xf, nm, col in PTS:
    cc = xf / (LEV * MSTAR); ee = 2.0 / cc - 1.0
    dd = (1.0 - math.exp(math.log(0.10) / ee)) * 100
    ax.plot([xf], [dd], "o", ms=8, color=col, mec=SURFACE, mew=1.8, zorder=6)
    ax.annotate(f"  {nm}  {dd:.0f}%", (xf, dd), textcoords="offset points",
                xytext=(9, -3), fontsize=8.3, color=col, fontweight="bold")
ax.axvline(8.65, color=INK, lw=1.4)
ax.text(8.5, 86, "c = 2x full Kelly:\ngrowth rate turns\nNEGATIVE", ha="right",
        fontsize=8.5, color=INK, fontweight="bold")
ax.annotate("\\$1m on \\$100k equity\nsits at 10.0x - off this chart,\n"
            "past the ruin boundary", xy=(8.62, 58), xytext=(3.4, 66),
            fontsize=8.6, color=VIOLET, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=VIOLET, lw=1.4))
ax.set_xlim(0, 9.4); ax.set_ylim(0, 100)
ax.set_xlabel("gross notional / equity"); ax.set_ylabel("max drawdown at 10% probability (%)")
ax.set_title("B.  Drawdown is set by notional/EQUITY, not by notional.\n"
             "     Doubling both leaves this chart unmoved - Casey is right.")
ax.grid(True, alpha=0.5)
ax.legend(loc="lower right", frameon=False, fontsize=8.2, labelcolor=INK2)

# ------------------------------------------------- C: does more data buy size?
ax = AX[1][0]
fix = [r for r in NSC["scan"] if r["dd_basis"] == "fixed2y"]
hor = [r for r in NSC["scan"] if r["dd_basis"] == "horizon_n"]
n = [r["n"] for r in fix]
ax.plot(n, [r["gross_over_equity"] for r in fix], "o-", color=ORANGE, ms=6,
        mec=SURFACE, mew=1.4, label="authorised gross/equity, 2-year DD budget")
ax.plot(n, [r["gross_over_equity"] for r in hor], "s--", color=AQUA, ms=5.5,
        mec=SURFACE, mew=1.4, label="same, if the DD budget spans the WHOLE history")
ax.axhline(1.32, color=AQUA, lw=1.2, ls=":")
ax.text(1500, 1.36, "DD30 ceiling 1.32x - data cannot pass this",
        ha="right", fontsize=8.4, color=AQUA, fontweight="bold")
ax.axhline(0.15, color=MUTED, lw=1.4, ls="-.")
ax.text(200, 0.19, "live today 0.15x", fontsize=8.4, color=MUTED, fontweight="bold")
ax.axvline(146, color=INK, lw=1.2, ls="-.")
ax.text(152, 0.30, "today: n=146\n(2 years)", fontsize=8.4, color=INK, fontweight="bold")
ax.annotate("saturates at n~300\n(~2 more years of trading)", xy=(300, 1.32),
            xytext=(430, 0.42), fontsize=8.6, color=ORANGE, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.4))
ax.set_xscale("log"); ax.set_xlim(130, 2300); ax.set_ylim(0, 1.92)
ax.set_xlabel("closed trades in the sample (n)")
ax.set_ylabel("authorised gross notional / equity")
ax.set_title("C.  More TRADES buy ~1.6x, then stop. More data cannot buy \\$1m.\n"
             "     Which DD horizon applies is a policy choice, and it flips the sign.")
ax.grid(True, which="major", alpha=0.5); ax.grid(True, which="minor", alpha=0.15)
ax.legend(loc="upper right", frameon=False, fontsize=8.2, labelcolor=INK2)

# ------------------------------------------------- D: liquidation vs the stop
ax = AX[1][1]
N = np.logspace(np.log10(5e4), np.log10(3e6), 400)
maint = float(LIQ["maint_ratio"])
liq = np.abs((maint * N - EQUITY) / (N * (1 - maint))) * 100
ax.plot(N, np.where(liq <= 100, liq, np.nan), color=BLUE, lw=2.4,
        label=f"distance to liquidation on \\${EQUITY/1e3:.0f}k equity (cross, maint {maint:.2%})")
TRAIL = LIQ["S4 chandelier trail (5.0 ATR)"]
for key, col, nm in (("median", AQUA, "5xATR14 stop, median"),
                     ("p90", ORANGE, "5xATR14 stop, p90"),
                     ("p99", VIOLET, "5xATR14 stop, p99")):
    v = float(TRAIL[key]) * 100
    ax.axhline(v, color=col, lw=1.6, ls="--")
    ax.text(5.4e4, v + 1.1, f"{nm}  {v:.1f}%", color=col, fontsize=8.3,
            fontweight="bold")
    xc = EQUITY / ((v / 100) * (1 - maint) + maint)
    if 5e4 < xc < 3e6:
        ax.plot([xc], [v], "o", ms=8, color=col, mec=SURFACE, mew=1.8, zorder=6)
        ax.annotate(f"\\${xc/1e3:.0f}k", (xc, v), textcoords="offset points",
                    xytext=(7, 5), fontsize=8.3, color=col, fontweight="bold")
ax.axvline(1e6, color=INK, lw=1.3, ls="-.")
ax.text(1.09e6, 40, "\\$1m: liq at 8.9%\nINSIDE the p90 stop\n- the stop cannot\nbe honoured",
        fontsize=8.5, color=INK, fontweight="bold")
ax.fill_between(N, 0, np.where(liq <= 100, liq, 100), where=(N > 5e5),
                color=ORANGE, alpha=0.06)
ax.set_xscale("log"); ax.set_xlim(5e4, 3e6); ax.set_ylim(0, 60)
ax.xaxis.set_major_formatter(usd)
ax.set_xlabel("gross notional"); ax.set_ylabel("adverse move to liquidation (%)")
ax.set_title("D.  Exchange margin is NOT the first wall - but above ~\\$0.5m\n"
             "     the position is liquidated before its own stop fires.")
ax.grid(True, which="major", alpha=0.5); ax.grid(True, which="minor", alpha=0.15)
ax.legend(loc="upper right", frameon=False, fontsize=8.2, labelcolor=INK2)

fig.tight_layout(rect=[0, 0.005, 1, 0.945])
out = os.path.join(HERE, "scale_study.png")
fig.savefig(out, bbox_inches="tight")
print(f"wrote {out}")
