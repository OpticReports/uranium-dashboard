"""Where the ramp stands against step B (docs/rung_b_gate.png).

Staircase and advance criteria from EXECUTOR.md "Ramp schedule - v3";
P&L from the account's own userFillsByTime (closedPnl and fee, so the line
is NET of fees, which is the only version that can settle a gate).
usage: python3 docs/rung_b_gate.py <fills.json> <out.png>
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

fpath, out = sys.argv[1], sys.argv[2]
fills = sorted(json.load(open(fpath)), key=lambda f: f["t"])

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

EQUITY = 99_924.39
OPEN_UPNL = 28.14
LEV, W_T, BASE = 1.5, 0.25, 50_000

fig, (a, b) = plt.subplots(1, 2, figsize=(14.8, 5.6), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1, 1.25]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: the staircase, and what each rung deploys ---------------------------
a.grid(axis="y", color=GRID, lw=0.8)
rungs = [("token\n0.05", 0.05, MUTED), ("A\n0.10", 0.10, MUTED),
         ("live\n0.135", 0.135, BLUE), ("B (ceiling)\n0.20", 0.20, AQUA),
         ("C\n0.35", 0.35, RED), ("D\n0.56", 0.56, RED)]
xs = range(len(rungs))
gross = [k * LEV * BASE for _, k, _ in rungs]
cols = [c for _, _, c in rungs]
bars = a.bar(xs, gross, 0.6, color=cols, zorder=3)
for i, (lab, k, c) in enumerate(rungs):
    if k > 0.20:
        bars[i].set_alpha(0.30)
        bars[i].set_hatch("//")
a.axhline(0.30 * EQUITY, color=RED, ls="--", lw=1.3, zorder=4)
a.text(-0.45, 0.30 * EQUITY + 900, "MAX_EXPOSURE_FRAC 30% of equity "
       f"(${0.30*EQUITY:,.0f})", color=RED, fontsize=8.2, ha="left")
for i, g in enumerate(gross):
    a.text(i, g + 900, f"${g:,.0f}", ha="center", color=INK, fontsize=8.6,
           fontweight="bold")
a.text(4.35, 40_500, "RETIRED\noutside the\nKelly envelope", color=RED,
       fontsize=8.4, ha="right", va="top")
a.annotate("", xy=(3, 15_000), xytext=(2, 10_125),
           arrowprops=dict(arrowstyle="->", color=AQUA, lw=2.2))
a.text(2.5, 17_400, "the step\n1.48x", color=AQUA, fontsize=9,
       ha="center", fontweight="bold")
a.set_xticks(list(xs))
a.set_xticklabels([l for l, _, _ in rungs], fontsize=8.4, color=SEC)
a.set_ylabel("gross deployed, USD  (kelly x 1.5 x 50,000)", color=SEC,
             fontsize=9.2)
a.set_ylim(0, 46_000)
a.set_title("KELLY_M 0.20 is the ceiling, and the only step left",
            color=INK, fontsize=11.5, fontweight="bold", loc="left")

# --- B: the gate that is actually binding ----------------------------------
b.grid(color=GRID, lw=0.8)
cum, xs2, ys = 0.0, [], []
for i, f in enumerate(fills):
    cum += f["pnl"] - f["fee"]
    xs2.append(i)
    ys.append(cum)
b.plot(xs2, ys, color=INK, lw=1.9, zorder=5)
b.fill_between(xs2, ys, 0, where=[v < 0 for v in ys], color=RED, alpha=0.13,
               zorder=1)
b.fill_between(xs2, ys, 0, where=[v >= 0 for v in ys], color=AQUA, alpha=0.13,
               zorder=1)
b.axhline(0, color=RED, ls="--", lw=1.5, zorder=4)
b.text(0.3, 2.5, "THE GATE: cumulative ramp P&L >= 0", color=RED,
       fontsize=8.8, fontweight="bold")
end = len(fills) - 1
b.plot([end], [ys[-1]], "o", color=RED, ms=9, zorder=6)
b.annotate(f"now  {ys[-1]:+.2f}\nnet of ${sum(f['fee'] for f in fills):.2f} fees",
           xy=(end, ys[-1]), xytext=(end - 13, -46), color=RED, fontsize=8.8,
           arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
b.plot([end + 3], [ys[-1] + OPEN_UPNL], "o", color=AQUA, ms=9, zorder=6)
b.annotate(f"open leg at +${OPEN_UPNL:.2f}\nwould close the gate",
           xy=(end + 3, ys[-1] + OPEN_UPNL), xytext=(end - 11, 27),
           color=AQUA, fontsize=8.8,
           arrowprops=dict(arrowstyle="->", color=AQUA, lw=1.2))
b.plot([end, end + 3], [ys[-1], ys[-1] + OPEN_UPNL], ls=":", color=AQUA,
       lw=1.6, zorder=5)
b.annotate("09-10\nhalt #1", xy=(20, ys[20]), xytext=(15.5, -63),
           color=MUTED, fontsize=8, ha="center",
           arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
b.annotate("09-18 netting close\n+$53.07", xy=(28, ys[28]), xytext=(20.5, 18),
           color=MUTED, fontsize=8,
           arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.0))
b.set_xlabel("fill # (live history, 08-29 to 09-21)", color=SEC, fontsize=9.2)
b.set_ylabel("cumulative realized P&L, net of fees, USD", color=SEC,
             fontsize=9.2)
b.set_xlim(-1, len(fills) + 5)
b.set_ylim(-72, 42)
b.set_title("Trade count passes. P&L does not — yet.", color=INK,
            fontsize=11.5, fontweight="bold", loc="left")

fig.suptitle("btc-executor — the next size step is KELLY_M 0.135 -> 0.20, "
             "and one gate still says no  (2026-09-21)",
             color=INK, fontsize=12.5, fontweight="bold", x=0.008, ha="left",
             y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
