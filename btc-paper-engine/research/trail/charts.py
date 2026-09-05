"""Four-panel summary for the S4 trail robustness diagnostic.

    python3 research/trail/charts.py <artifact_dir> <out.png>
"""
import json
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = sys.argv[1] if len(sys.argv) > 1 else "/tmp/trail"
OUT = sys.argv[2] if len(sys.argv) > 2 else f"{D}/trail_summary.png"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC, MUTED = "#e34948", "#0b0b0b", "#52514e", "#898781"
GRID, AX, SURF, VIOLET = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#4a3aa7"

live = json.load(open(f"{D}/trail_sweep.json"))
off = json.load(open(f"{D}/trail_sweep_ddhalt1.json"))
nul = json.load(open(f"{D}/trail_sweep_null.json"))
plc = json.load(open(f"{D}/trail_sweep_placebo.json"))
seq = json.load(open(f"{D}/trail_sweep_nullseq.json"))
G = live["grid"]
X = np.array(G)


def mars(d, w):
    return np.array([d["windows"][w]["cells"][f"{m:.2f}"]["s6"]["mar"] for m in G])


fig, axs = plt.subplots(2, 2, figsize=(15, 10.4), facecolor=SURF)
for a in axs.ravel():
    a.set_facecolor(SURF)
    for s in ("top", "right"):
        a.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        a.spines[s].set_color(AX)
    a.tick_params(colors=SEC, labelsize=9)

# ---- A: the registered curve is a kill-switch curve
ax = axs[0, 0]
mL, mO = mars(live, "modern"), mars(off, "modern")
halted = [live["windows"]["modern"]["cells"][f"{m:.2f}"]["halted"] for m in G]
for m, h in zip(G, halted):
    if h:
        ax.axvspan(m - 0.125, m + 0.125, color=RED, alpha=0.09, zorder=0)
ax.plot(X, mL, "-o", color=ORANGE, ms=4.5, lw=2, zorder=3,
        label="live config (dd_halt −50%)")
ax.plot(X, mO, "-o", color=BLUE, ms=4.5, lw=2, zorder=3,
        label="kill switch OFF (post-hoc)")
ax.axvline(5.0, color=INK, lw=1.1, ls=":", zorder=2)
ax.annotate("live 5.0×ATR", (5.0, 1.60), color=INK, fontsize=9,
            ha="center", fontweight="bold")
ax.set_xlabel("S4 chandelier trail (× ATR14)", fontsize=10, color=SEC)
ax.set_ylabel("S6 blend MAR, 2022→ (exit-step)", fontsize=10, color=SEC)
ax.grid(color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=9, labelcolor=SEC, loc="lower right")
ax.set_title("13 of 21 settings trip S4's −50% book halt — the live one does not",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
ax.text(0, 1.05, "Red bands = the book halted and stopped trading. The registered\n"
        "dose curve is partly measuring which cells got killed, not the trail.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

# ---- B: plateau across windows (halt off)
ax = axs[0, 1]
for w, c, lb in (("modern", BLUE, "2022→ primary (~54% in-sample)"),
                 ("hl", AQUA, "2023-05→ bench window (nested in primary)"),
                 ("modern_A", MUTED, "2022→2024-06 = VALIDATE (selection window)"),
                 ("modern_B", VIOLET, "2024-07→ = the single-touch HOLDOUT")):
    ax.plot(X, mars(off, w), "-o", color=c, ms=3.5, lw=1.7, label=lb, zorder=3)
ax.axvspan(2.75, 7.0, color=AQUA, alpha=0.07, zorder=0)
ax.axhline(1.362, color=MUTED, lw=1, ls="--", zorder=1)
ax.axvline(5.0, color=INK, lw=1.1, ls=":", zorder=2)
ax.annotate("+12.8% clear of\nthe next best cell", (5.0, 1.537),
            xytext=(5.55, 1.95), fontsize=8.6, color=RED, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
ax.set_xlabel("S4 chandelier trail (× ATR14)", fontsize=10, color=SEC)
ax.set_ylabel("S6 blend MAR (kill switch off)", fontsize=10, color=SEC)
ax.grid(color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper left")
ax.set_title("Not a plateau — a band with one spike on the incumbent",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
ax.text(0, 1.05, "Above 2.75×ATR every cell sits in 1.02–1.36 except 5.00 at 1.54 (z = +3.26). The registered\n"
        "flatness test STILL FAILS here: 25.9% vs a 25% bar — and 77.1% on a sane 3.0–7.0 grid.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

# ---- C: bootstrap rank of the incumbent
ax = axs[1, 0]
rk = np.array(nul["base_rank"])
rs = np.array(seq["base_rank"])
bins = np.arange(0.5, 22.5, 1)
ax.hist(rs, bins=bins, color=BLUE, alpha=0.85, zorder=3,
        label="per-cell sequence blocks (vacuous — over-disperses 3×)")
ax.hist(rk, bins=bins, color=ORANGE, alpha=0.55, zorder=4,
        label="shared-draw 30-day blocks (the usable null)")
ax.axvline(float(np.median(rs)), color=BLUE, lw=2, zorder=5)
ax.axvline(float(np.median(rk)), color=ORANGE, lw=2, zorder=5)
ax.set_xlabel("rank of the live 5.0×ATR setting among the 21 cells",
              fontsize=10, color=SEC)
ax.set_ylabel("bootstrap resamples (n=2000 each)", fontsize=10, color=SEC)
ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=8.4, labelcolor=SEC, loc="upper right")
ax.set_title("The one flattering statistic is the unregistered one",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
ax.text(0, 1.05, f"Median rank {np.median(rk):.0f} of 21 under the usable null, {np.median(rs):.0f} under the "
        "per-cell version the prereg named.\nRank was never a registered statistic — reported here as post-hoc, "
        "and not leaned on.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

# ---- D: the sweep buys less than random thinning
ax = axs[1, 1]
L = np.array(plc["lifts"])
gm = np.array(nul["gap_max_med"])
ax.hist(gm, bins=40, color=MUTED, alpha=0.55, zorder=2,
        label="best-of-21 lift under the block bootstrap")
ax.hist(L, bins=40, color=AQUA, alpha=0.45, zorder=3,
        label="thinning placebo (STRUCK — 1.62× over-dispersed)")
ax.axvline(plc["obs_lift"], color=RED, lw=2.4, zorder=5)
ax.text(plc["obs_lift"] + 0.03, ax.get_ylim()[1] * 0.86,
        f"observed trail sweep\n{plc['obs_lift']:+.3f}", color=RED, fontsize=9.5,
        fontweight="bold")
ax.set_xlabel("MAR lift of the best cell over its own grid median",
              fontsize=10, color=SEC)
ax.set_ylabel("draws", fontsize=10, color=SEC)
ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper right")
ax.set_title("One usable null, and it finds the sweep unremarkable",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
p1 = float((gm >= plc["obs_lift"]).mean())
p2 = float((L >= plc["obs_lift"]).mean())
ax.text(0, 1.05, f"A random best-of-21 lift beats the observed one in {100*p1:.0f}% of shared-draw resamples "
        "(0.63–0.85 across block\nlengths). The thinning arm is STRUCK: 1.62× over-dispersed, and matched it gives 0.26, not 0.80.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

fig.suptitle("S4 chandelier trail: INDETERMINATE — no change  ·  "
             "Bitstamp 4h, blend 75% pullback / 25% donchian @2.0×, 6bp/side, exit-step  ·  2026-09-05",
             fontsize=10.5, color=SEC, y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.965))
fig.savefig(OUT, dpi=132, facecolor=SURF)
print(f"wrote {OUT}")
