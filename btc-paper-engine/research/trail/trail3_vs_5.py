"""3.0x vs the incumbent 5.0x chandelier trail (trail3_vs_5.png).

Re-runs the PRE-REGISTERED grid from research/trail/PREREG.md (21 cells,
2.00..7.00) through the committed sweep harness, on the repo fixture
backend/tests/fixtures/bars_4h_btcusd.csv. NOTE the 2026-09-05 study used a
DIFFERENT bar set (13,666 Bitstamp bars vs this fixture's 10,002), so levels
differ from RESEARCH_TRAIL.md; the argmax structure and the transfer finding
both reproduce.
usage: python3 research/trail/trail3_vs_5.py <summary.json> <out.png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

spath, out = sys.argv[1], sys.argv[2]
d = json.load(open(spath))
g = [float(x) for x in d["grid"]]
A, B = d["A"], d["B"]

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"
i3, i5 = g.index(3.0), g.index(5.0)

fig, (a, b) = plt.subplots(1, 2, figsize=(15.0, 6.2), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1.5, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_axisbelow(True)
    ax.grid(color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: the dose curve, in-sample vs holdout --------------------------------
a.plot(g, A, "-o", color=MUTED, lw=1.8, ms=4, zorder=4,
       label="IN-SAMPLE 2022-01..2024-06 (the window 5.0 was picked on)")
a.plot(g, B, "-o", color=VIOLET, lw=2.4, ms=5, zorder=5,
       label="HOLDOUT 2024-07..2026-07 (genuinely out of sample)")
for i, col, lab in ((i5, AQUA, "5.0 incumbent"), (i3, RED, "3.0 proposed")):
    a.axvline(g[i], color=col, ls="--", lw=1.5, zorder=3)
    a.text(g[i] + 0.06, 2.22, lab, color=col, fontsize=9, fontweight="bold",
           rotation=90, va="top")
    a.plot([g[i]], [B[i]], "o", color=col, ms=11, zorder=7,
           markeredgecolor="white", markeredgewidth=1.4)
a.annotate(f"holdout MAR {B[i3]:.3f}", xy=(g[i3], B[i3]),
           xytext=(g[i3] - 0.75, B[i3] + 0.62), color=RED, fontsize=9,
           fontweight="bold", arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
a.annotate(f"holdout MAR {B[i5]:.3f}\nbest of 21, by 0.35 sd", xy=(g[i5], B[i5]),
           xytext=(g[i5] + 0.35, B[i5] + 0.72), color=AQUA, fontsize=9,
           fontweight="bold", arrowprops=dict(arrowstyle="->", color=AQUA, lw=1.2))
a.set_xlabel("trail_atr  (chandelier multiple)", color=SEC, fontsize=10)
a.set_ylabel("S6 blend MAR", color=SEC, fontsize=10)
a.set_ylim(-0.15, 2.45)
a.set_title(f"The two curves barely relate: rho = {d['rho']:+.3f}  (p = 0.94)",
            color=INK, fontsize=12, fontweight="bold", loc="left")
a.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper left")

# --- B: the ONLY window that is out of sample ------------------------------
order = sorted(range(len(g)), key=lambda i: -B[i])
xs = list(range(len(g)))
cols = [AQUA if g[i] == 5.0 else (RED if g[i] == 3.0 else MUTED) for i in order]
b.bar(xs, [B[i] for i in order], 0.72, color=cols, zorder=3)
b.axhline(0, color=AX, lw=1.1, zorder=4)
for pos, i in enumerate(order[:2]):
    b.text(pos, B[i] + 0.022, f"{g[i]:.2f}\n{B[i]:.3f}", ha="center",
           color=INK, fontsize=9.2, fontweight="bold")
b.set_xticks(xs)
b.set_xticklabels([f"{g[i]:.2f}" for i in order], fontsize=6.4, color=SEC,
                  rotation=90)
b.set_ylabel("S6 blend MAR, HOLDOUT only", color=SEC, fontsize=10)
b.set_ylim(-0.08, 0.99)
b.set_title("On the holdout they are 1st and 2nd, 0.35 sd apart",
            color=INK, fontsize=12, fontweight="bold", loc="left")
b.text(4.6, 0.86, "21 cells ranked on the HOLDOUT\n"
       f"gap {d['gap']:+.3f} MAR = {d['gap_sd']:.2f} grid sd\n"
       "a shared-draw bootstrap puts\nP(3.0 >= 5.0) at 0.35",
       color=SEC, fontsize=9, va="top")
b.text(11.2, 0.60, "IN-SAMPLE the order inverts:\n"
       f"5.0 ranks {d['rkA5']}/21, 3.0 ranks {d['rkA3']}/21.\n"
       "The big gaps live in the window\n5.0 was fitted on.",
       color=ORANGE, fontsize=9, va="top", fontweight="bold")

fig.suptitle("S4 chandelier trail, 3.0x vs 5.0x — INDETERMINATE, as the "
             "registered study already concluded", color=INK, fontsize=13,
             fontweight="bold", x=0.008, ha="left", y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
