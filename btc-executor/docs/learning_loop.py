"""What actually adapts, and what does not (docs/learning_loop.png).

Sources: btc-paper-engine/backend/app/engine/kelly.py (its own docstring:
"the engine never resizes anything by itself"), main.py's /kelly/compare
(reads REPLAY bars, not live fills), engine/core.py's static dataclass
defaults, btc-executor/app/mirror.py (no feedback path), and the research
docs named on the right-hand panel.
usage: python3 docs/learning_loop.py docs/learning_loop.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch   # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "docs/learning_loop.png"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

fig, (a, b) = plt.subplots(1, 2, figsize=(15.0, 6.4), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1, 1.12]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

def box(ax, x, y, w, h, text, fc, ec, fs=8.6, tc=INK, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.14",
                                fc=fc, ec=ec, lw=1.5, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, zorder=4,
            fontweight="bold" if bold else "normal")

def arrow(ax, p1, p2, c=SEC, ls="-", lw=1.7):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=15,
                                 color=c, lw=lw, ls=ls, zorder=2,
                                 shrinkA=2, shrinkB=2))

# --- A: the loop as it actually runs ---------------------------------------
a.text(0.1, 9.65, "The loop as it actually runs", fontsize=12,
       fontweight="bold", color=INK)
a.text(0.1, 9.15, "Nothing in the grey ring changes a parameter.",
       fontsize=9, color=SEC, style="italic")

box(a, 0.4, 7.2, 4.0, 1.25, "btc-paper-engine\nfixed params: rsi 45/55,\n"
    "stop 2.5 ATR, trail 5 ATR", "#eef4fb", BLUE)
box(a, 5.6, 7.2, 4.0, 1.25, "/exec/target\n{w_trend 0.25, lev 1.5}",
    "#eef4fb", BLUE)
box(a, 5.6, 4.9, 4.0, 1.25, "btc-executor\nmirrors it to the venue\n"
    "(no strategy opinion)", "#eef4fb", BLUE)
box(a, 0.4, 4.9, 4.0, 1.25, "Hyperliquid fills\nslip_bps, closedPnl\nrecorded",
    "#eef4fb", BLUE)
arrow(a, (4.4, 7.82), (5.6, 7.82), MUTED)
arrow(a, (7.6, 7.2), (7.6, 6.15), MUTED)
arrow(a, (5.6, 5.52), (4.4, 5.52), MUTED)
a.add_patch(FancyArrowPatch((2.4, 4.9), (2.4, 3.95), arrowstyle="-|>",
                            mutation_scale=15, color=ORANGE, lw=2.2,
                            zorder=2))
a.text(2.7, 4.4, "evidence only", fontsize=8.4, color=ORANGE, va="center")

box(a, 0.4, 2.55, 5.4, 1.35, "RESEARCH PASS  (a person + agents)\n"
    "pre-registered, counter-agent reviewed", "#fdf1ea", ORANGE, bold=True)
box(a, 0.4, 0.55, 5.4, 1.25, "Casey edits a dashboard env var\n"
    "KELLY_M, SIZING_BASE_USD, ...", "#fdf1ea", ORANGE, bold=True)
arrow(a, (3.1, 2.55), (3.1, 1.8), ORANGE, lw=2.2)
a.add_patch(FancyArrowPatch((5.9, 1.8), (7.0, 4.9), arrowstyle="-|>",
                            mutation_scale=15, color=ORANGE, lw=2.2,
                            connectionstyle="arc3,rad=-0.28", zorder=2))
a.text(6.15, 3.45, "the ONLY path\nback into sizing", fontsize=8.6,
       color=ORANGE, ha="left", fontweight="bold")

box(a, 6.2, 0.45, 3.5, 1.6, "/kelly/compare\nreads REPLAY bars, not live fills\n\n"
    '"the engine never resizes\nanything by itself"', "#f4f2fb", VIOLET,
    fs=8.0, tc=VIOLET)

# --- B: what live evidence HAS changed -------------------------------------
b.text(0.1, 9.65, "What the live record has actually changed", fontsize=12,
       fontweight="bold", color=INK)
b.text(0.1, 9.15, "All of it execution and risk. None of it the edge.",
       fontsize=9, color=SEC, style="italic")

rows = [
    ("09-10", "Fees: 4 of 4 maker entries crossed and paid\n"
     "taker. 8.64 bps, not 6.00. Kelly re-fit ->\n"
     "rungs C/D/ceiling RETIRED, cap 0.20.", AQUA, "made it SMALLER"),
    ("09-16", "Two halts reconstructed order-by-order ->\n"
     "net-mirror rewrite, 72 new gate tests.", AQUA, "fixed a real bug"),
    ("08-10", "cb.py discarded average_filled_price, so the\n"
     "slippage gate had sample size ZERO.", AQUA, "made it measurable"),
    ("08-06", "False DRAWDOWN halt on one bad balance read\n"
     "-> breach debounce. stop_vanished paged\n"
     "4,320x/day -> per-kind throttle.", AQUA, "stopped false alarms"),
    ("—", "S3/S4 strategy parameters:\nUNCHANGED since backtest.", MUTED,
     "11 closes cannot move them"),
]
y = 8.0
for date, text, col, tag in rows:
    b.add_patch(FancyBboxPatch((0.5, y - 1.1), 9.0, 1.15,
                               boxstyle="round,pad=0.10",
                               fc="#f2faf6" if col == AQUA else "#f4f4f2",
                               ec=col, lw=1.4, zorder=3))
    b.text(0.95, y - 0.52, date, fontsize=8.6, color=col, va="center",
           fontweight="bold")
    b.text(1.95, y - 0.52, text, fontsize=8.0, color=INK, va="center")
    b.text(9.25, y - 0.52, tag, fontsize=7.6, color=col, va="center",
           ha="right", style="italic")
    y -= 1.42

b.add_patch(FancyBboxPatch((0.5, 0.10), 9.0, 0.95,
                           boxstyle="round,pad=0.10", fc="#fdeeee", ec=RED,
                           lw=1.5, zorder=3))
b.text(5.0, 0.575, "Deflated Sharpe on the backtests: 0.12 / 0.31 / 0.33 — "
       "not yet\ndistinguishable from selection bias. The live record is the "
       "adjudicator,\nand at 11 closes it has not said anything yet.",
       fontsize=8.2, color=RED, ha="center", va="center", fontweight="bold")

fig.suptitle("btc-executor — is it self-learning?  No. The loop has a human "
             "in it, on purpose.", color=INK, fontsize=13,
             fontweight="bold", x=0.008, ha="left", y=0.98)
fig.tight_layout(rect=(0, 0, 1, 0.945))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
