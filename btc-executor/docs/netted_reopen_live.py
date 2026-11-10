"""First live netted_reopen (docs/netted_reopen_live.png).

Reconstructed from the account's own Hyperliquid records on 2026-09-18:
`userFillsByTime` and `historicalOrders`, 04:01:15Z-04:01:40Z.
usage: python3 docs/netted_reopen_live.py docs/netted_reopen_live.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "docs/netted_reopen_live.png"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
VIOLET = "#4a3aa7"

fig, (a, b) = plt.subplots(1, 2, figsize=(14.4, 5.4), facecolor=SURF,
                           gridspec_kw={"width_ratios": [1.45, 1]})
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: the venue net across the 25 seconds ---------------------------------
a.grid(axis="y", color=GRID, lw=0.8)
t = [0, 15, 15, 17, 17, 40]
net = [0.03342, 0.03342, 0.0, 0.0, -0.01671, -0.01671]
a.step(t, net, where="post", color=INK, lw=2.2, zorder=4)
a.axhline(0, color=AX, lw=1.0, zorder=2)
a.fill_between(t, net, 0, step="post", where=[v > 0 for v in net],
               color=BLUE, alpha=0.16, zorder=1)
a.fill_between(t, net, 0, step="post", where=[v < 0 for v in net],
               color=ORANGE, alpha=0.16, zorder=1)

evs = [(15, 0.03342, "X  SELL 0.03342 reduce-only\nclamped at the net -> FLAT",
        RED, (18.5, 0.0455)),
       (17, -0.01671, "R  SELL 0.01671 NOT reduce-only\nthe entry-class re-open",
        AQUA, (21.0, -0.0295)),
       (18, -0.01671, "stop placed -> CANCELLED", MUTED, (21.0, 0.0065)),
       (40, -0.01671, "stop re-placed, working\n0.01671 @ 79,850", VIOLET,
        (28.0, -0.0040))]
for x, y, lab, c, xy in evs:
    a.plot([x], [y], "o", color=c, ms=7, zorder=6)
    a.annotate(lab, xy=(x, y), xytext=xy, color=c, fontsize=8.6,
               va="center", arrowprops=dict(arrowstyle="->", color=c, lw=1.1))
a.text(0.4, 0.0355, "pullback long 0.05013 + trend short 0.01671\n"
       "= venue net +0.03342", color=SEC, fontsize=8.6, va="bottom")
a.set_xlabel("seconds after 2026-09-18 04:01:15Z", color=SEC, fontsize=9.5)
a.set_ylabel("venue net position, BTC", color=SEC, fontsize=9.5)
a.set_xlim(-1.5, 47)
a.set_ylim(-0.037, 0.050)
a.set_title("The R order, live for the first time", color=INK, fontsize=12,
            fontweight="bold", loc="left")

# --- B: what the ledger held vs what the venue could hold -------------------
b.grid(axis="y", color=GRID, lw=0.8)
lab = ["before\n04:01:15Z", "after\n04:01:40Z"]
pull = [0.05013, 0.0]
trend = [-0.01671, -0.01671]
x = [0, 1]
b.bar(x, pull, 0.5, color=BLUE, zorder=3, label="pullback leg (S3, long)")
b.bar(x, trend, 0.5, color=ORANGE, zorder=3, label="trend leg (S4, short)")
b.plot(x, [0.03342, -0.01671], "o--", color=INK, lw=1.8, ms=8, zorder=5,
       label="venue net (all the venue holds)")
b.axhline(0, color=AX, lw=1.0, zorder=2)
for i, (p, tr) in enumerate(zip(pull, trend)):
    if p:
        b.text(i, p + 0.003, f"{p:.5f}", ha="center", color=INK, fontsize=9)
    b.text(i, tr - 0.006, f"{tr:.5f}", ha="center", color=INK, fontsize=9)
b.text(1, 0.0075, "netted away ->\nowed as netted_qty ->\nre-opened by R",
       ha="center", color=AQUA, fontsize=8.4, va="bottom")
b.set_xticks(x)
b.set_xticklabels(lab, fontsize=9, color=SEC)
b.set_ylabel("BTC", color=SEC, fontsize=9.5)
b.set_ylim(-0.032, 0.062)
b.set_title("Two ledger legs, one net position", color=INK, fontsize=12,
            fontweight="bold", loc="left")
b.legend(frameon=False, fontsize=8.4, labelcolor=SEC, loc="upper right")

fig.suptitle("btc-executor netted_reopen — first live exercise, "
             "2026-09-18 04:01Z  (realized +$53.07 on the closed net)",
             color=INK, fontsize=12.5, fontweight="bold", x=0.008, ha="left",
             y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
