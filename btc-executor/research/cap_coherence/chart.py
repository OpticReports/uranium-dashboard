"""SIZING_BASE_USD moved 1,000 -> 25,000 on 2026-09-09. MAX_NOTIONAL_USD did
not. Everything below follows from those two numbers.

    python3 research/cap_coherence/chart.py [out_dir]
"""
import os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MAGENTA, VIOLET, RED = "#e87ba4", "#4a3aa7", "#e34948"
INK, SEC, MUTED, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.edgecolor": AX, "axes.labelcolor": SEC, "text.color": INK,
                     "xtick.color": SEC, "ytick.color": SEC, "grid.color": GRID,
                     "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold"})

CAP, LEV, K, PX = 2_000.0, 1.5, 0.135, 78_557.0
W = {"pullback": 0.75, "trend": 0.25}
fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.8))

# -- 1. what the legs wanted vs what the cap allowed -----------------------
ax = axes[0]
bases = [1_000, 25_000]
labels, want, got = [], [], []
for b in bases:
    other = 0.00064 if b == 25_000 else 0.0        # the open trend leg, old size
    w = K * LEV * W["pullback"] * b
    room = max(0.0, CAP - other * PX)
    labels.append(f"base {b:,}")
    want.append(w); got.append(min(w, room))
x = np.arange(len(bases)); wd = 0.34
ax.bar(x - wd/2, want, wd, label="pullback leg wanted", color=BLUE, zorder=3)
ax.bar(x + wd/2, got, wd, label="cap allowed", color=ORANGE, zorder=3)
ax.axhline(CAP, color=RED, lw=1.4, ls="--", zorder=4)
ax.text(-0.42, CAP * 1.06, "MAX_NOTIONAL_USD 2,000", color=RED, fontsize=8.4, ha="left")
for i, (a, b_) in enumerate(zip(want, got)):
    ax.text(i - wd/2, a * 1.03, f"{a:,.0f}", ha="center", fontsize=8.4, color=SEC)
    ax.text(i + wd/2, b_ * 1.03, f"{b_:,.0f}", ha="center", fontsize=8.4, color=SEC)
ax.set_xticks(x, labels); ax.set_ylabel("leg notional, USD")
ax.set_title("1. The cap, not the base, sets the trade")
ax.legend(frameon=False, fontsize=8.2, loc="upper left"); ax.grid(axis="y", lw=0.6, zorder=0)
ax.set_ylim(0, max(want) * 1.30)
ax.text(0.98, 0.97, "the 09-09 fill was 0.02481 BTC\n= 1,949 USD, i.e. 51% of intent",
        transform=ax.transAxes, fontsize=8.4, color=RED, ha="right", va="top")

# -- 2. halt lines vs the most the caps can lose ---------------------------
ax = axes[1]
rows = [("daily loss\n6% of base", 0.06), ("drawdown\n35% of base", 0.35)]
y = np.arange(len(rows)); h = 0.34
for j, (b, col, lab) in enumerate([(1_000, AQUA, "base 1,000 (before)"),
                                   (25_000, MAGENTA, "base 25,000 (now)")]):
    vals = [p * b for _, p in rows]
    ax.barh(y + (j - 0.5) * h, vals, h, color=col, label=lab, zorder=3)
    for i, v in enumerate(vals):
        ax.text(v * 1.05, y[i] + (j - 0.5) * h, f"${v:,.0f}", va="center",
                fontsize=8.2, color=SEC)
ax.axvline(CAP, color=RED, lw=1.5, ls="--", zorder=4)
ax.text(CAP * 1.15, 0.62, "most the caps can\never lose: $2,000",
        color=RED, fontsize=8.2, va="center")
ax.set_yticks(y, [r[0] for r in rows]); ax.set_xscale("log")
ax.set_xlim(40, 3.0e4)
ax.set_xlabel("loss needed to fire the breaker, USD (log)")
ax.set_title("2. Both halt lines moved; the cap did not")
ax.legend(frameon=False, fontsize=8.2, loc="lower right"); ax.grid(axis="x", lw=0.6, zorder=0)

# -- 3. how many maximum-size total losses it takes ------------------------
ax = axes[2]
names = ["daily loss", "drawdown"]
before = [0.06 * 1_000 / CAP, 0.35 * 1_000 / CAP]
after = [0.06 * 25_000 / CAP, 0.35 * 25_000 / CAP]
x = np.arange(2); wd = 0.34
ax.bar(x - wd/2, before, wd, color=AQUA, label="before", zorder=3)
ax.bar(x + wd/2, after, wd, color=MAGENTA, label="now", zorder=3)
ax.axhline(1.0, color=RED, lw=1.4, ls="--", zorder=4)
ax.text(1.45, 1.12, "1.0 = a total loss of the\nbiggest position allowed",
        color=RED, fontsize=8.2, ha="right")
for i, (a, b_) in enumerate(zip(before, after)):
    ax.text(i - wd/2, a + 0.12, f"{a:.2f}x", ha="center", fontsize=8.4, color=SEC)
    ax.text(i + wd/2, b_ + 0.12, f"{b_:.2f}x", ha="center", fontsize=8.4, color=SEC)
ax.set_xticks(x, names); ax.set_ylabel("total losses of a max position needed")
ax.set_title("3. Only the drawdown line is provably out of reach")
ax.legend(frameon=False, fontsize=8.2, loc="upper left"); ax.grid(axis="y", lw=0.6, zorder=0)
ax.text(0.02, 0.62, "drawdown accrues ACROSS trades, so\n4.4x does not mean it can never fire -\n"
                    "only that no single position reaches it.\nThe daily line still can, at 0.75x.",
        transform=ax.transAxes, fontsize=8.2, color=SEC)

fig.suptitle("btc-executor: SIZING_BASE_USD moved 1,000 → 25,000. MAX_NOTIONAL_USD stayed at 2,000.",
             fontsize=12, fontweight="bold", y=0.99)
fig.text(0.008, 0.015, "Cap inferred from the live fill, not from config: 2000/78,557 − 0.00064 = 0.024819 BTC "
                       "vs the actual 0.02481. Both vars are sync:false and set by hand in Render.",
         fontsize=7.8, color=MUTED)
fig.tight_layout(rect=(0, 0.045, 1, 0.945))
p = os.path.join(OUT, "cap_coherence.png"); fig.savefig(p, dpi=150)
print("wrote", p)
