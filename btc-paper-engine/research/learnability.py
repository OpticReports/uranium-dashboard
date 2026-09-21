"""What this book can and cannot learn, by sample rate (research/learnability.png).

Sample rates are measured or derived from the repo: fills and crossing booleans
from btc-executor's live record (2026-08-29..09-21), funding accruals from S3's
19.6% measured time-in-market, MTM trade-bars counted on the committed fixture,
closes from the live venue record. Detection horizons are two-sided t-tests at
alpha 0.05 against the book's ~8.2% annualized vol at full ramp, or the stated
trade counts for ratio statistics.
usage: python3 research/learnability.py research/learnability.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "research/learnability.png"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

# (label, samples/yr, years-to-a-decision-grade-answer, class)
PTS = [
    ("MTM trade-bars\n(already on disk)", 2000, 0.02, "cost"),
    ("funding accruals", 1700, 0.08, "cost"),
    ("daily marks", 365, 0.25, "cost"),
    ("fills / slippage", 185, 0.15, "cost"),
    ("MAE / MFE", 75, 0.5, "cost"),
    ("crossing rate\n(venue boolean)", 57, 0.3, "cost"),
    ("fee tier", 10, 0.04, "cost"),
    ("win rate", 75, 1.25, "edge"),
    ("Sharpe", 75, 2.5, "edge"),
    ("profit factor", 75, 4.5, "edge"),
    ("a 150 bps/yr execution\ngain, seen in P&L", 75, 114, "never"),
    ("the 30 bps/yr fee error\nalready found, in P&L", 75, 2847, "never"),
]
COL = {"cost": AQUA, "edge": ORANGE, "never": RED}

fig, ax = plt.subplots(figsize=(13.6, 7.4), facecolor=SURF)
ax.set_facecolor(SURF)
ax.set_xscale("log")
ax.set_yscale("log")
ax.grid(which="both", color=GRID, lw=0.7)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax.spines[s].set_color(AX)
ax.tick_params(colors=SEC, labelsize=9)

ax.axhspan(0.01, 1.0, color=AQUA, alpha=0.07, zorder=0)
ax.axhspan(1.0, 10.0, color=ORANGE, alpha=0.07, zorder=0)
ax.axhspan(10.0, 6000, color=RED, alpha=0.07, zorder=0)
ax.axhline(1.0, color=SEC, ls="--", lw=1.0, zorder=2)
ax.axhline(10.0, color=SEC, ls="--", lw=1.0, zorder=2)

ax.text(5.8, 0.28, "LEARNABLE\nweeks to months", color=AQUA, fontsize=10.5,
        fontweight="bold", va="center")
ax.text(5.8, 2.3, "LEARNABLE, SLOWLY\nyears — and the book\nmay not survive it",
        color=ORANGE, fontsize=10.5, fontweight="bold", va="center")
ax.text(5.8, 300, "NOT IN YOUR LIFETIME\nknowable only as arithmetic\non ledger rows, never from P&L",
        color=RED, fontsize=10.5, fontweight="bold", va="center")

OFF = {
    "fee tier": (0, 22), "crossing rate\n(venue boolean)": (0, -34),
    "fills / slippage": (0, 20), "MAE / MFE": (0, -34),
    "daily marks": (0, 20), "funding accruals": (20, 8),
    "MTM trade-bars\n(already on disk)": (-58, 30),
    "win rate": (16, 4), "Sharpe": (16, 4), "profit factor": (16, 4),
    "a 150 bps/yr execution\ngain, seen in P&L": (16, 0),
    "the 30 bps/yr fee error\nalready found, in P&L": (16, 0),
}
for lab, n, yrs, cls in PTS:
    ax.plot([n], [yrs], "o", ms=11, color=COL[cls], zorder=5,
            markeredgecolor="white", markeredgewidth=1.2)
    dx, dy = OFF.get(lab, (0, 18))
    ax.annotate(lab, xy=(n, yrs), xytext=(dx, dy), textcoords="offset points",
                fontsize=8.6, color=INK, ha="left" if dx > 0 else "center",
                va="center", zorder=6)

ax.set_xlabel("live samples per year  (log)", color=SEC, fontsize=10.5)
ax.set_ylabel("years to a decision-grade answer  (log)", color=SEC, fontsize=10.5)
ax.set_xlim(4, 6000)
ax.set_ylim(0.012, 6000)
ax.set_yticks([0.02, 0.1, 0.5, 1, 5, 20, 100, 1000])
ax.set_yticklabels(["1 week", "5 weeks", "6 months", "1 year", "5 years",
                    "20 years", "100 years", "1,000 years"], fontsize=8.8)


fig.suptitle("btc-paper-engine — what the live book can actually learn, and how fast",
             color=INK, fontsize=13.5, fontweight="bold", x=0.008, ha="left", y=0.98)
fig.text(0.008, 0.925, "The whole premise, in one picture: everything GREEN is a COST. Everything ORANGE or RED is the EDGE. Live trading buys you the green.",
         fontsize=10.5, color=INK, ha="left", va="top", fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.90))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
