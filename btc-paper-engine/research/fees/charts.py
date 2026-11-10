"""Three panels for the fee study. Run run_grid.py and refit_kelly.py first.

    python3 research/fees/charts.py [out_dir]
"""
from __future__ import annotations
import json, os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MAGENTA, VIOLET, RED = "#e87ba4", "#4a3aa7", "#e34948"
INK, SEC, MUTED, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.edgecolor": AX, "axes.labelcolor": SEC, "text.color": INK,
                     "xtick.color": SEC, "ytick.color": SEC, "grid.color": GRID,
                     "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold"})

grid = json.load(open(os.path.join(HERE, "grid.json")))
kel = json.load(open(os.path.join(HERE, "kelly_refit.json")))

fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.9))

# ---- 1. the measurement: what the venue actually charged -----------------
ax = axes[0]
# the four INTENDED-MAKER pullback entries, from userFills 2026-09-10
entries = [("08-31 00:00", 151.36), ("09-01 16:01", 151.07),
           ("09-08 08:00", 151.24), ("09-09 16:00", 1949.00)]
y = np.arange(len(entries))
ax.barh(y, [4.32] * 4, color=RED, height=0.5, zorder=3)
ax.barh(y, [1.44] * 4, color=AQUA, height=0.5, zorder=4)

for i, (lab, ntl) in enumerate(entries):
    ax.text(4.45, i, f"${ntl:,.0f}", va="center", fontsize=8.2, color=SEC)
ax.set_yticks(y, [e[0] for e in entries], fontsize=8.4)
ax.set_xlim(-0.35, 6.6); ax.set_ylim(3.6, -1.75); 
ax.set_xlabel("entry fee actually charged, bps")
ax.set_title("1. The post-only entry has never rested")
ax.grid(axis="x", lw=0.6, zorder=0)
ax.text(0.72, -1.15, "modelled:\nmaker, 1.44 bps", color=AQUA, fontsize=8.2,
        ha="center", va="center", fontweight="bold")
ax.text(4.32, -1.15, "actually paid:\ntaker, 4.32 bps", color=RED, fontsize=8.2,
        ha="center", va="center", fontweight="bold")
ax.text(0.0, -0.315, "4 of 4 crossed. n=4, so the point estimate is 100% — which is "
                     "NOT the same as established.",
        transform=ax.transAxes, fontsize=8, color=RED, va="top")

# ---- 2. the dose curve ---------------------------------------------------
ax = axes[1]
for wname, col, mk in (("full", BLUE, "o"), ("hl_era", VIOLET, "s")):
    cells = [g for g in grid if g["window"] == wname and g["frac"] is not None]
    cells.sort(key=lambda g: g["frac"])
    ax.plot([c["frac"] * 100 for c in cells],
            [c["stats"]["S3"]["cagr_pct"] for c in cells],
            marker=mk, color=col, lw=1.8, ms=5, zorder=4,
            label=f"{wname} window")
base_full = [g for g in grid if g["arm"] == "baseline_6.0" and g["window"] == "full"][0]
ax.axhline(base_full["stats"]["S3"]["cagr_pct"], color=MUTED, ls="--", lw=1.1,
           zorder=2)
ax.text(2, base_full["stats"]["S3"]["cagr_pct"] - 0.10,
        f"as modelled today ({base_full['stats']['S3']['cagr_pct']}%) — which "
        f"is only ~8% crossing",
        fontsize=8, color=MUTED, va="top")
ax.axvline(8.33, color=AQUA, ls="-.", lw=1.3, zorder=3)
ax.text(10.5, 15.98, "the shipped model\nassumes ~8% cross", color=AQUA,
        fontsize=8, va="bottom")
ax.axvline(100, color=RED, ls=":", lw=1.4, zorder=3)
ax.text(103, 16.3, "live: 4 of 4", color=RED, fontsize=8.2, ha="left",
        va="bottom", rotation=90)
ax.set_xlim(-5, 113); ax.set_ylim(15.85, 18.45)
ax.set_xlabel("share of entries that CROSS (pay taker), %")
ax.set_ylabel("S3 CAGR, % (in-sample)")
ax.set_title("2. What the true fee costs S3")
ax.legend(frameon=False, fontsize=8.2, loc="upper right"); ax.grid(lw=0.6, zorder=0)

# ---- 3. the decision -----------------------------------------------------
# Four cells: {2y, full} x {cash_apy 0.04, 0.00}. All four are declared in
# PREREG AMENDMENT 2; the first cut reported only one of them and got the
# headline backwards. See A2.4/A2.5.
ax = axes[2]
CELLS = [("2y_cash0.04", "2y\ncash 4%"), ("2y_cash0.00", "2y\ncash 0%"),
         ("full_cash0.04", "full\ncash 4%"), ("full_cash0.00", "full\ncash 0%")]
base = [kel[c]["baseline_6.0"]["S6"]["recommended_m"] for c, _ in CELLS]
corr = [kel[c]["live_8.64"]["S6"]["recommended_m"] for c, _ in CELLS]
x = np.arange(len(CELLS)); w = 0.34
ax.bar(x - w/2, base, w, color=AQUA, zorder=3, label="as modelled (6.00 bps)")
ax.bar(x + w/2, corr, w, color=MAGENTA, zorder=3, label="fee-corrected (8.64 bps)")
for i, (a, b) in enumerate(zip(base, corr)):
    ax.text(i - w/2, a + 0.018, f"{a:.2f}", ha="center", fontsize=7.9, color=SEC)
    ax.text(i + w/2, b + 0.085, f"{b:.2f}", ha="center", fontsize=7.9,
            color=RED if b < 0.35 else SEC,
            fontweight="bold" if b < 0.35 else "normal")

for rung, style in ((0.135, "-"), (0.20, "--"), (0.35, ":")):
    ax.axhline(rung, color=ORANGE, ls=style, lw=1.5, zorder=5)

# the cell that fails the top rung is the one that governs (A2.5)
binding = corr[1]
ax.axvspan(0.5, 1.5, color=RED, alpha=0.055, zorder=1)
ax.annotate(f"0.35 rung\nnot cleared\nbinding size {binding:.2f}",
            xy=(0.98, 0.42), xytext=(0.42, 1.24),
            color=RED, fontsize=8.4, fontweight="bold", ha="center", va="top",
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))

ax.set_xticks(x, [lab for _, lab in CELLS], fontsize=8.4)
ax.set_xlim(-0.6, 3.72); ax.set_ylim(0, 1.30)
ax.set_ylabel("S6 recommended m (KELLY.md envelope)")
ax.set_title("3. The 0.35 rung does not clear", pad=7)
ax.legend(frameon=False, fontsize=8, loc="upper right"); ax.grid(axis="y", lw=0.6, zorder=0)
for rung, lab in ((0.135, "0.135"), (0.20, "0.20"), (0.35, "0.35")):
    ax.text(3.70, rung + 0.012, lab, color=ORANGE, fontsize=7.8,
            ha="right", va="bottom", fontweight="bold")

fig.suptitle("S3 fee model: the backtest gives the entry away free, the venue never has",
             fontsize=12, fontweight="bold", y=0.99)
fig.text(0.008, 0.015, "Pre-registered 2026-09-10 (commit dbab333) before any run; window and cash_apy "
                       "declared retroactively in AMENDMENT 2. In-sample on a fixture already used for "
                       "~2,491 prior trials \u2014 read as an UPPER bound. Panel 3 n = 146 (2y) / 318 (full) blend steps.",
         fontsize=7.8, color=MUTED)
fig.tight_layout(rect=(0, 0.075, 1, 0.945))
p = os.path.join(OUT, "fee_study.png"); fig.savefig(p, dpi=150)
print("wrote", p)
