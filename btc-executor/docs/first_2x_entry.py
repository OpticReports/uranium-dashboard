"""The first entry at the 2x size (docs/first_2x_entry.png).

Built from the account's own Hyperliquid records on 2026-09-18 — 15m
candleSnapshot, userFillsByTime, historicalOrders — plus the mirror's sizing
identity leg = kelly_m * lev * weight * SIZING_BASE_USD.
usage: python3 docs/first_2x_entry.py <candles.json> <out.png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

cpath, out = sys.argv[1], sys.argv[2]
c = json.load(open(cpath))

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

T0 = 1789689600          # 2026-09-18 00:00Z, the x origin
hrs = [(x["t"] / 1000 - T0) / 3600 for x in c]
px = [x["c"] for x in c]

KELLY, LEV, W_T, PX_E = 0.135, 1.5, 0.25, 80_757.0
old = KELLY * LEV * W_T * 25_000 / PX_E
new = KELLY * LEV * W_T * 50_000 / PX_E
ACTUAL = 0.03134

fig, (a, b) = plt.subplots(1, 2, figsize=(14.6, 5.6), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1.9, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: the day on the tape -------------------------------------------------
a.grid(color=GRID, lw=0.8)
a.plot(hrs, px, color=INK, lw=1.5, zorder=4)
a.axhline(79_849.79, color=ORANGE, ls="--", lw=1.2, zorder=3)
a.text(-0.4, 79_990, "S4 trail 79,849.79", color=ORANGE, fontsize=8.4)

evs = [(4.02, 77_345, "R re-open\nSELL 0.01671", AQUA, (0.4, 78_700)),
       (13.79, 79_899, "S4 TRAIL FIRES\nclose short 0.01671\nrealized -$42.68",
        RED, (7.4, 81_150)),
       (13.80, 79_811, "auto-drill x2  (0.00016 @13:47,\n0.00015 @14:47)"
        "  ->  ramp 12/14 -> 14/14", MUTED, (5.6, 76_300)),
       (14.80, 80_808, "", MUTED, (14.80, 80_808)),
       (16.01, 80_757, "FRESH LONG 0.03134 @ 80,757\n<- the 2x size",
        BLUE, (17.1, 78_100))]
for x, y, lab, col, xy in evs:
    a.plot([x], [y], "o", color=col, ms=8, zorder=6)
    a.annotate(lab, xy=(x, y), xytext=xy, color=col, fontsize=8.5,
               va="center", ha="left",
               arrowprops=dict(arrowstyle="->", color=col, lw=1.2))

a.axvspan(16.01, 16.96, color=RED, alpha=0.10, zorder=1)
a.text(16.5, 81_650, "UNPROTECTED\nno stop, no orders", color=RED,
       fontsize=8.6, ha="center", va="top", fontweight="bold")
a.set_xlim(-0.6, 20.8)
a.set_ylim(75_900, 82_100)
a.set_xticks([0, 4, 8, 12, 16, 20])
a.set_xticklabels(["00:00Z", "04:00", "08:00", "12:00", "16:00",
                   "20:00\n(next bar)"], fontsize=8.6, color=SEC)
a.set_ylabel("BTC", color=SEC, fontsize=9.5)
a.set_title("2026-09-18 on the tape", color=INK, fontsize=12,
            fontweight="bold", loc="left")

# --- B: the size, old base vs new ------------------------------------------
b.grid(axis="y", color=GRID, lw=0.8)
bars = [old, new, ACTUAL]
cols = [MUTED, AQUA, BLUE]
labs = ["at base\n25,000", "at base\n50,000", "ACTUAL\nfill"]
b.bar([0, 1, 2], bars, 0.55, color=cols, zorder=3)
for i, v in enumerate(bars):
    b.text(i, v + 0.0009, f"{v:.5f}", ha="center", color=INK, fontsize=9.5,
           fontweight="bold")
    b.text(i, v / 2, f"${v * PX_E:,.0f}", ha="center", color="white",
           fontsize=9.5, fontweight="bold")
b.set_xticks([0, 1, 2])
b.set_xticklabels(labs, fontsize=8.8, color=SEC)
b.set_ylabel("trend leg, BTC", color=SEC, fontsize=9.5)
b.set_ylim(0, 0.040)
b.text(1.5, 0.0375, "0.135 x 1.5 x 0.25 x 50,000 / 80,757\n= 0.031344  ->  "
       "filled 0.03134", color=AQUA, fontsize=8.5, ha="center", va="top")
b.set_title("SIZING_BASE_USD 50,000, confirmed live", color=INK, fontsize=12,
            fontweight="bold", loc="left")

fig.suptitle("btc-executor — first fresh entry at the 2x size, and the "
             "unprotected window that came with it",
             color=INK, fontsize=12.5, fontweight="bold", x=0.008, ha="left",
             y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
