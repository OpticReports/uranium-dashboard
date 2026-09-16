"""Two panels: what leverage buys you, and what the other two levers buy you.

    python3 research/frontier/chart.py [out_dir]
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

d = json.load(open(os.path.join(HERE, "frontier.json")))
LEVS = d["levs"]
ARMS = [("live_fee",       "as we trade today",         RED,     "o", "-"),
        ("resting_fee",    "+ post-only actually rests", ORANGE, "s", "--"),
        ("live_fee_cash4", "+ 4% on idle cash",          BLUE,   "^", "-."),
        ("both_levers",    "+ BOTH",                     AQUA,   "D", "-")]

fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.4))

# ---- 1. the frontier -------------------------------------------------------
ax = axes[0]
for key, lab, col, mk, ls in ARMS:
    r = [s for s in d["rays"][key] if not s["ruined"]]
    ax.plot([abs(s["dd"]) for s in r], [s["cagr"] for s in r],
            marker=mk, color=col, lw=1.7, ms=4.5, ls=ls, label=lab, zorder=4)

base = d["rays"]["live_fee"][LEVS.index(1.5)]
both = d["rays"]["both_levers"][LEVS.index(1.5)]
for s, col, name in ((base, RED, "S5 today"), (both, AQUA, "S5 + both levers")):
    ax.scatter([abs(s["dd"])], [s["cagr"]], s=110, facecolor="none",
               edgecolor=col, lw=2.0, zorder=6)
ax.annotate("", xy=(abs(both["dd"]), both["cagr"]),
            xytext=(abs(base["dd"]), base["cagr"]),
            arrowprops=dict(arrowstyle="->", color=AQUA, lw=2.2))
ax.annotate(f"same drawdown,\n+{both['cagr']-base['cagr']:.1f}pp CAGR\n"
            f"({both['dd']-base['dd']:+.1f}pp DD)",
            xy=(abs(base["dd"]) - 0.3, (base["cagr"] + both["cagr"]) / 2),
            xytext=(11.5, 56), color=AQUA, fontsize=9.2, fontweight="bold",
            ha="center", va="center",
            arrowprops=dict(arrowstyle="->", color=AQUA, lw=1.3))

# where leverage alone would have to go for the same return
ray = d["rays"]["live_fee"]
xs = [abs(s["dd"]) for s in ray]; ys = [s["cagr"] for s in ray]
dd_equiv = float(np.interp(both["cagr"], ys, xs))
ax.plot([abs(base["dd"]), dd_equiv], [both["cagr"]] * 2, color=MUTED,
        ls=":", lw=1.4, zorder=3)
ax.scatter([dd_equiv], [both["cagr"]], s=55, color=MUTED, zorder=5)
ax.annotate(f"leverage alone needs {dd_equiv:.0f}% DD\nto reach the same return",
            xy=(dd_equiv, both["cagr"]), xytext=(38.5, 26),
            color=SEC, fontsize=8.6, ha="center", va="center",
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1))

for L in (1.5, 2.0):
    s = ray[LEVS.index(L)]
    ax.text(abs(s["dd"]) + 1.4, s["cagr"] - 3.2,
            {1.5: "S5 1.5x", 2.0: "S6 2.0x"}[L],
            color=RED, fontsize=8.2, ha="left", fontweight="bold")
ax.set_xlabel("max drawdown, % (trade-close basis — MTM runs ~1pp deeper)")
ax.set_ylabel("CAGR, % (in-sample)")
ax.set_title("1. Leverage moves you ALONG the line. The other two levers move it UP.")
ax.set_xlim(4, 62); ax.set_ylim(5, 90)
ax.legend(frameon=False, fontsize=8.4, loc="upper left"); ax.grid(lw=0.6, zorder=0)

# ---- 2. MAR vs leverage ----------------------------------------------------
ax = axes[1]
for key, lab, col, mk, ls in ARMS:
    r = d["rays"][key]
    ax.plot(LEVS, [s["mar"] for s in r], marker=mk, color=col, lw=1.7,
            ms=4.5, ls=ls, label=lab, zorder=4)
ax.axvspan(2.0, 4.15, color=RED, alpha=0.05, zorder=1)
ax.text(2.9, 1.06, "over-betting:\nMAR falls away", color=RED, fontsize=8.6,
        ha="center", fontweight="bold")
for L, name in ((1.5, "S5"), (2.0, "S6")):
    ax.axvline(L, color=MUTED, ls=":", lw=1.0, zorder=2)
    ax.text(L, 1.755, name, color=SEC, fontsize=8.2, ha="center",
            fontweight="bold")
ax.set_xlabel("blend leverage")
ax.set_ylabel("MAR (CAGR / max drawdown)")
ax.set_title("2. Leverage does not buy return per unit of drawdown")
ax.set_xlim(0.3, 4.2); ax.set_ylim(1.0, 1.80)
ax.legend(frameon=False, fontsize=8.4, loc="lower left"); ax.grid(lw=0.6, zorder=0)

fig.suptitle("\"More profit, no more drawdown\": leverage cannot do it — cost and idle cash can",
             fontsize=12.5, fontweight="bold", y=0.985)
fig.text(0.008, 0.015, "75/25 pullback/donchian blend, research basis, full window 2022-01-01 ->. "
                       "Fee 8.64 bps = the round trip we actually pay. In-sample on a fixture "
                       "carrying ~2,515 prior trials — read the COMPARISONS, not the levels.",
         fontsize=7.8, color=MUTED)
fig.tight_layout(rect=(0, 0.055, 1, 0.945))
p = os.path.join(OUT, "frontier.png"); fig.savefig(p, dpi=150)
print("wrote", p)
