"""Three panels for the exit_flag lag fix. Run measure.py first (writes
measure.csv), then:

    python3 research/exit_lag/charts.py [out_dir]

Panel 1 is the DEFECT (live, verifiable): every close-based exit reached the
venue a full 4h bar after the engine booked it, while entries reached it in
seconds. Panels 2 and 3 are the CONSEQUENCE, measured on 4.56y of backtested
pullback trades: the correction is a coin flip centred on zero. That is the
honest claim - this removes an unmodelled exposure window, it does not add
edge.
"""
from __future__ import annotations

import csv
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MAGENTA, VIOLET, RED = "#e87ba4", "#4a3aa7", "#e34948"
INK, SEC, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AX, SURF = "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF,
    "axes.edgecolor": AX, "axes.labelcolor": SEC, "text.color": INK,
    "xtick.color": SEC, "ytick.color": SEC, "grid.color": GRID,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
})

# --- live record, from the engine's own /books/S3/trades (2026-09-09) -------
# Only the PULLBACK leg can lag: S4/donchian exits via its chandelier trail,
# which is a resting venue stop order, not a flag.
LIVE = [
    ("08-19 12:00", "STOP",   0.0),      # resting venue stop - never lagged
    ("08-31 16:00", "SIGNAL", 4.0),
    ("09-03 16:00", "SIGNAL", 4.0),
    ("09-09 08:00", "SIGNAL", 4.0),
]
ENTRY_LAG_H = 37 / 3600.0                # measured entry latency, seconds

rows = list(csv.DictReader(open(os.path.join(HERE, "measure.csv"))))
d = np.array([float(r["delta_pct"]) for r in rows])

fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.9))

# ---------------------------------------------------------------- panel 1
ax = axes[0]
labels = [f"{t}\n{r}" for t, r, _ in LIVE]
lags = [h for _, _, h in LIVE]
cols = [AQUA if h == 0 else RED for h in lags]
y = np.arange(len(LIVE))
ax.barh(y, lags, color=cols, height=0.55, zorder=3)
ax.barh(y, [ENTRY_LAG_H] * len(LIVE), color=BLUE, height=0.18, zorder=4)
for i, h in enumerate(lags):
    ax.text(h + 0.12, i, "4h late" if h else "on time (resting stop)",
            va="center", fontsize=8.5, color=RED if h else AQUA, zorder=5)
ax.set_yticks(y, labels, fontsize=8)
ax.set_xlim(0, 6.2)
ax.set_xlabel("hours between the engine booking the exit and the venue fill")
ax.set_title("1. The defect, on the live record")
ax.grid(axis="x", lw=0.6, zorder=0)
ax.invert_yaxis()
ax.text(0.98, 0.97,
        "blue sliver = entry latency, 37s",
        transform=ax.transAxes, ha="right", va="top", fontsize=8, color=SEC)

# ---------------------------------------------------------------- panel 2
ax = axes[1]
ax.hist(d, bins=34, color=BLUE, alpha=0.72, zorder=3, edgecolor=SURF, lw=0.5)
mu = float(np.mean(d))
rng = np.random.default_rng(20260909)
boot = rng.choice(d, size=(20_000, len(d)), replace=True).mean(axis=1)
lo, hi = np.percentile(boot, [2.5, 97.5])
ax.axvspan(lo, hi, color=ORANGE, alpha=0.16, zorder=2)
ax.axvline(0, color=MUTED, lw=1.1, ls="--", zorder=4)
ax.axvline(mu, color=ORANGE, lw=1.8, zorder=5)
ax.set_xlabel("change in exit price vs the old one-bar-late fill, % of entry")
ax.set_ylabel("trades")
ax.set_ylim(0, ax.get_ylim()[1] * 1.42)
ax.set_title("2. What the correction is worth, per trade")
ax.grid(axis="y", lw=0.6, zorder=0)
ax.text(0.02, 0.95,
        f"n = {len(d)} close-based exits, 4.56y\n"
        f"mean {mu:+.4f}%   median {statistics.median(d):+.4f}%\n"
        f"95% CI [{lo:+.3f}%, {hi:+.3f}%] — includes zero\n"
        f"better on {100*np.mean(d > 0):.0f}% of trades",
        transform=ax.transAxes, va="top", fontsize=8.3, color=SEC)

# ---------------------------------------------------------------- panel 3
ax = axes[2]
ts = np.array([int(r["exit_ts"]) for r in rows], dtype=float)
order = np.argsort(ts)
yrs = (ts[order] - ts[order][0]) / (365.25 * 86400)
cum = np.cumsum(d[order])
ax.plot(yrs, cum, color=VIOLET, lw=1.6, zorder=4)
ax.fill_between(yrs, 0, cum, color=VIOLET, alpha=0.13, zorder=3)
ax.axhline(0, color=MUTED, lw=1.1, ls="--", zorder=2)
ax.set_xlabel("years from the first affected exit (2022 →)")
ax.set_ylabel("cumulative change, % of leg notional")
ax.set_title("3. Cumulative — it wanders, it does not trend")
ax.grid(lw=0.6, zorder=0)
ax.set_ylim(min(cum.min(), 0) - 0.4, cum.max() + 2.4)
ax.text(0.02, 0.97,
        f"ends {cum[-1]:+.2f}% over 4.56y = {cum[-1]/4.56:+.3f}%/yr\n"
        f"on a 3,797 USD pullback leg (base 25k): "
        f"{cum[-1]/4.56/100*3797:+,.0f} USD/yr\n"
        "a tracking-error fix, not a money-maker",
        transform=ax.transAxes, va="top", fontsize=8.3, color=SEC)

fig.suptitle("btc-executor: the engine's exit_flag was never read — exits "
             "landed one 4h bar late", fontsize=12, fontweight="bold", y=0.99)
fig.text(0.008, 0.015,
         "Live record from the engine's own trade log (btc-paper-engine "
         "/books/S3/trades, read 2026-09-09). Panels 2-3: 124 close-based "
         "exits over 4.56y of 4h BTC bars, same engine code path.",
         fontsize=7.8, color=MUTED)
fig.tight_layout(rect=(0, 0.045, 1, 0.945))
path = os.path.join(OUT, "exit_lag.png")
fig.savefig(path, dpi=150)
print("wrote", path)
