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
for w, c, lb in (("modern", BLUE, "2022→ (primary)"),
                 ("hl", AQUA, "2023-05→ (S6 bench window)"),
                 ("modern_A", MUTED, "2022→2024-06 (partly in-sample)"),
                 ("modern_B", VIOLET, "2024-07→ (out-of-sample)")):
    ax.plot(X, mars(off, w), "-o", color=c, ms=3.5, lw=1.7, label=lb, zorder=3)
ax.axvspan(2.75, 7.0, color=AQUA, alpha=0.07, zorder=0)
ax.axvline(5.0, color=INK, lw=1.1, ls=":", zorder=2)
ax.set_xlabel("S4 chandelier trail (× ATR14)", fontsize=10, color=SEC)
ax.set_ylabel("S6 blend MAR (kill switch off)", fontsize=10, color=SEC)
ax.grid(color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper left")
ax.set_title("Above ~2.75×ATR it is a plateau, not a peak",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
ax.text(0, 1.05, "The cliff is at the tight end: a 2.0×ATR trail turns the trend leg into noise.\n"
        "Between 2.75 and 7.0 the argmax wanders by window — 4.50, 5.00, 7.00.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

# ---- C: bootstrap rank of the incumbent
ax = axs[1, 0]
rk = np.array(nul["base_rank"])
bins = np.arange(0.5, 22.5, 1)
ax.hist(rk, bins=bins, color=BLUE, alpha=0.85, zorder=3)
ax.axvline(float(np.median(rk)), color=ORANGE, lw=2, zorder=4)
ax.text(float(np.median(rk)) + 0.4, ax.get_ylim()[1] * 0.92,
        f"median rank {np.median(rk):.0f} of 21", color=ORANGE, fontsize=9.5,
        fontweight="bold")
ax.set_xlabel("rank of the live 5.0×ATR setting among the 21 cells",
              fontsize=10, color=SEC)
ax.set_ylabel("bootstrap resamples (30-day blocks, n=2000)",
              fontsize=10, color=SEC)
ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
ax.set_axisbelow(True)
ax.set_title("5.0 is a reliable plateau member, not a demonstrable optimum",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
top5 = float((rk <= 5).mean())
bot = float((rk > 10.5).mean())
ax.text(0, 1.05, f"Top-5 in {100*top5:.0f}% of resamples, bottom half in {100*bot:.0f}%. "
        f"It is the argmax in {100*nul['argmax_counts']['5.00']/nul['n_eff']:.0f}%\n"
        "of draws (uniform would be 4.8%) — good, but it shares that title with 7.00 and 4.25.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

# ---- D: the sweep buys less than random thinning
ax = axs[1, 1]
L = np.array(plc["lifts"])
gm = np.array(nul["gap_max_med"])
ax.hist(gm, bins=40, color=MUTED, alpha=0.55, zorder=2,
        label="best-of-21 lift under the block bootstrap")
ax.hist(L, bins=40, color=AQUA, alpha=0.6, zorder=3,
        label="best-of-21 lift from RANDOM trade thinning")
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
ax.set_title("Searching 21 trails buys LESS than thinning trades at random",
             fontsize=12.5, color=INK, fontweight="bold", loc="left", pad=36)
p1 = float((gm >= plc["obs_lift"]).mean())
p2 = float((L >= plc["obs_lift"]).mean())
ax.text(0, 1.05, f"A random best-of-21 beats the whole trail grid's lift {100*p1:.0f}% of the time "
        f"(bootstrap) and {100*p2:.0f}% (thinning).\nRandom thinning's best-of-21 MAR beats the grid's "
        "MAX in 100% of reps. The parameter is not a lever.",
        transform=ax.transAxes, fontsize=8.6, color=MUTED, va="bottom")

fig.suptitle("S4 chandelier trail: robustness diagnostic, not a re-tune  ·  "
             "Bitstamp 4h, blend 75% pullback / 25% donchian @2.0×, 6bp/side, exit-step  ·  2026-09-05",
             fontsize=10.5, color=SEC, y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.965))
fig.savefig(OUT, dpi=132, facecolor=SURF)
print(f"wrote {OUT}")
