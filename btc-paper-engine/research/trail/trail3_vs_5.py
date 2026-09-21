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
A, B, M, S4, N = d["A"], d["B"], d["mod"], d["s4_mod"], d["n_mod"]

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
a.annotate(f"holdout MAR {B[i5]:.3f}\nstill the best cell", xy=(g[i5], B[i5]),
           xytext=(g[i5] + 0.35, B[i5] + 0.72), color=AQUA, fontsize=9,
           fontweight="bold", arrowprops=dict(arrowstyle="->", color=AQUA, lw=1.2))
a.set_xlabel("trail_atr  (chandelier multiple)", color=SEC, fontsize=10)
a.set_ylabel("S6 blend MAR", color=SEC, fontsize=10)
a.set_ylim(-0.15, 2.45)
a.set_title(f"The two curves barely relate: Spearman rho = {d['rho']:+.3f}",
            color=INK, fontsize=12, fontweight="bold", loc="left")
a.legend(frameon=False, fontsize=8.6, labelcolor=SEC, loc="upper left")

# --- B: what tightening actually buys ---------------------------------------
lab = ["S6 MAR\nin-sample", "S6 MAR\nholdout", "S6 MAR\nfull 2022+",
       "S4 leg MAR\nfull 2022+"]
v3 = [A[i3], B[i3], M[i3], S4[i3]]
v5 = [A[i5], B[i5], M[i5], S4[i5]]
x = range(len(lab))
b.bar([i - 0.19 for i in x], v3, 0.36, color=RED, zorder=3, label="3.0x")
b.bar([i + 0.19 for i in x], v5, 0.36, color=AQUA, zorder=3, label="5.0x")
b.axhline(0, color=AX, lw=1.2, zorder=4)
for i in x:
    for off, v in ((-0.19, v3[i]), (0.19, v5[i])):
        b.text(i + off, v + (0.05 if v >= 0 else -0.14), f"{v:.2f}",
               ha="center", color=INK, fontsize=8.8, fontweight="bold")
b.set_xticks(list(x))
b.set_xticklabels(lab, fontsize=8.2, color=SEC)
b.set_ylabel("MAR", color=SEC, fontsize=10)
b.set_ylim(-0.35, 2.05)
b.set_title("3.0 loses on every window tested", color=INK, fontsize=12,
            fontweight="bold", loc="left")
b.legend(frameon=False, fontsize=9, labelcolor=SEC, loc="upper right")
b.text(1.5, 1.62, f"and it trades {N[i3]} times vs {N[i5]}\non 2022+ — "
       f"{N[i3]/N[i5]:.1f}x the fee drag\nfor a worse result",
       color=ORANGE, fontsize=9, ha="center", fontweight="bold")

fig.suptitle("S4 chandelier trail — tightening 5.0x to 3.0x, on the "
             "pre-registered 21-cell grid", color=INK, fontsize=13,
             fontweight="bold", x=0.008, ha="left", y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
