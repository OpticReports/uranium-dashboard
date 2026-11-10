"""The one thing in our own data that does what Casey asked.

Not a new study - a re-reading of numbers already computed, on the same
trade-close basis. Adding the donchian leg to the pullback book raised return
above BOTH legs while cutting drawdown below BOTH legs. That is "more profit,
no more drawdown", and no cost or yield tweak comes close to it.

    python3 research/frontier/breadth.py [out_dir]
"""
from __future__ import annotations
import json, os, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
MAGENTA, VIOLET, RED = "#e87ba4", "#4a3aa7", "#e34948"
INK, SEC, MUTED, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.edgecolor": AX, "axes.labelcolor": SEC, "text.color": INK,
                     "xtick.color": SEC, "ytick.color": SEC, "grid.color": GRID,
                     "font.size": 9.5, "axes.titlesize": 11.5, "axes.titleweight": "bold"})

d = json.load(open(os.path.join(HERE, "frontier.json")))
s = d["single"]["live_fee"]
blend = d["rays"]["live_fee"][d["levs"].index(1.0)]

PTS = [("S3 pullback\nalone", abs(s["S3"]["max_dd_pct"]), s["S3"]["cagr_pct"], VIOLET),
       ("S4 donchian\nalone", abs(s["S4"]["max_dd_pct"]), s["S4"]["cagr_pct"], ORANGE),
       ("75/25 blend\n(both legs)", abs(blend["dd"]), blend["cagr"], AQUA)]

fig, ax = plt.subplots(figsize=(8.6, 6.0))

# the quadrant the blend occupies relative to BOTH legs
bx, by = PTS[2][1], PTS[2][2]
ax.axvspan(8, bx, color=AQUA, alpha=0.055, zorder=1)
ax.axhspan(by, 24, color=AQUA, alpha=0.055, zorder=1)

OFF = {"S3": (0, -46, "center"), "S4": (0, 24, "center"),
       "75": (14, 20, "left")}
for lab, dd, cagr, col in PTS:
    ax.scatter([dd], [cagr], s=210, color=col, zorder=6, edgecolor=SURF, lw=1.5)
    dx, dy, ha = OFF[lab[:2]]
    ax.annotate(f"{lab}\n{cagr:.1f}% / -{dd:.1f}%  (MAR {cagr/dd:.2f})",
                xy=(dd, cagr), xytext=(dx, dy), textcoords="offset points",
                ha=ha, fontsize=9.2, color=col, fontweight="bold")

for lab, dd, cagr, col in PTS[:2]:
    ax.annotate("", xy=(bx, by), xytext=(dd, cagr),
                arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.5,
                                ls="--", alpha=0.8))

ax.text(31, 12.3, "the blend beats BOTH legs\non return AND on drawdown\n"
                  "— up and to the LEFT of each",
        color=AQUA, fontsize=10, fontweight="bold", ha="center", va="center")
ax.text(31, 9.2, "S4 alone is the WORSE book (MAR 0.42).\n"
                 "Adding it still improved the whole.\n"
                 "That is diversification, not selection.",
        color=SEC, fontsize=8.8, ha="center", va="center")

ax.set_xlabel("max drawdown, % (trade-close basis)")
ax.set_ylabel("CAGR, % (in-sample)")
ax.set_title("The only free lunch in our own data: an uncorrelated second leg")
ax.set_xlim(8, 52); ax.set_ylim(8, 24)
ax.grid(lw=0.6, zorder=0)
fig.text(0.01, 0.015,
         "Full window 2022-01-01 ->, both legs at 1x so leverage is not doing the work. Pullback charged the "
         "corrected 8.64 bps;\ndonchian still charged 12.0 (core.py sets it explicitly) — which makes S4 look "
         "WORSE than it is, so this comparison is\nCONSERVATIVE. In-sample on a fixture carrying ~2,515 prior "
         "trials. Correlation S3/S4 = -0.15 (config.py).",
         fontsize=7.6, color=MUTED)
fig.tight_layout(rect=(0, 0.085, 1, 1))
p = os.path.join(OUT, "breadth.png"); fig.savefig(p, dpi=150)
print("wrote", p)
for lab, dd, cagr, _ in PTS:
    print(f"  {lab.replace(chr(10),' '):<26} CAGR {cagr:6.2f}%  DD -{dd:5.2f}%  MAR {cagr/dd:.2f}")
