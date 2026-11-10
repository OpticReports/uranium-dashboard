"""Figure for RESUME_PROTOCOL.md: where the executor's rails sit today
(K 0.75, high water 100,239) and after a DRAWDOWN halt followed by a
reanchored resume at K 0.30 (equity ~70,000, illustrative fill at the line).

Right panel: the exposure guard (mirror.MAX_EXPOSURE_FRAC = 1.125 of
max(equity, high_water), gross = K x lev x base) — why 0.75 is not a
post-halt option at base 100,000. Numbers as of 2026-10-27 12:25Z.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE, LEV = 100_000.0, 1.5
HW, EQ, DAY0 = 100_239.28, 100_087.62, 100_095.49
EQ_AFTER = 70_000.0                       # illustrative: fill at the line
BLUE, ORANGE, RED, YELLOW, VIOLET, AQUA = ("#2a78d6", "#eb6834", "#e34948",
                                           "#eda100", "#6250d6", "#1baf7a")
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

fig, (ax, bx) = plt.subplots(1, 2, figsize=(15, 7.2), facecolor="#fcfcfb",
                             gridspec_kw={"width_ratios": [1.35, 1]})
for a in (ax, bx):
    a.set_facecolor("#fcfcfb")
    for s in ("top", "right"):
        a.spines[s].set_visible(False)
    a.spines["left"].set_color(GRID); a.spines["bottom"].set_color(GRID)
    a.tick_params(colors=INK2, labelsize=10)
    a.yaxis.grid(True, color=GRID, lw=0.8); a.set_axisbelow(True)

# ---- left: the rails ladder -------------------------------------------
cols = {"today\nK 0.75, HW 100,239": 0.0,
        "after halt + /resume?reanchor=1\nK 0.30, equity ~70,000": 1.5}
rails_today = [
    ("high water", HW, INK2, "-"),
    ("T4 monitor page (90% HW)", 0.9 * HW, YELLOW, "--"),
    ("DAILY_LOSS 15% of base", DAY0 - 0.15 * BASE, ORANGE, "-"),
    ("DRAWDOWN halt  HW - 30,000", HW - 0.30 * BASE, RED, "-"),
]
rails_after = [
    ("new high water = equity", EQ_AFTER, INK2, "-"),
    ("T4 monitor page", 0.9 * EQ_AFTER, YELLOW, "--"),  # label va=top
    ("DAILY_LOSS 6% (after next 00:00Z)", EQ_AFTER - 0.06 * BASE, ORANGE, "-"),
    ("DAILY_LOSS 15% (first day, frozen)", EQ_AFTER - 0.15 * BASE, ORANGE, ":"),
    ("next DRAWDOWN halt = KILL", EQ_AFTER - 0.30 * BASE, RED, "-"),
]
W = 0.36
for (lab, x), rails, eq in zip(cols.items(), (rails_today, rails_after),
                                (EQ, EQ_AFTER)):
    for name, y, c, ls in rails:
        ax.hlines(y, x - W, x + W, color=c, lw=2.2, ls=ls)
        va = ("top" if name.startswith("T4 monitor page") and x > 0.5
              else "bottom" if name.startswith("DAILY_LOSS 6%") else "center")
        dy = -300 if va == "top" else 300 if va == "bottom" else 0
        ax.text(x + W + 0.03, y + dy, f"{name}\n${y:,.0f}", va=va,
                ha="left", fontsize=9, color=INK)
    ax.plot([x], [eq], "o", ms=9, color=BLUE, mec="#fcfcfb", mew=1.5)
    if x < 0.5:
        ax.text(x - W - 0.03, eq, f"equity\n${eq:,.0f}", va="center",
                ha="right", fontsize=9, color=INK)
ax.axhline(112_500 / (1.125 * 1.01), color=VIOLET, lw=1.6, ls="-.")
ax.text(1.5 + W + 0.03, 112_500 / (1.125 * 1.01) + 600,
        "0.75 allowed only above $99,010\n(exposure guard, base 100k)",
        fontsize=9, color=VIOLET, va="bottom")
ax.set_xlim(-0.75, 2.95); ax.set_ylim(33_000, 108_000)
ax.set_xticks(list(cols.values())); ax.set_xticklabels(list(cols.keys()),
                                                        fontsize=10, color=INK)
ax.set_ylabel("account equity, USD", color=INK2)
ax.set_title("Where the rails sit — before the halt, and after a reanchored "
             "resume at 0.30", loc="left", fontsize=12, color=INK)

# ---- right: the exposure guard ----------------------------------------
groups = [("today\nK 0.75", 0.75 * LEV * BASE, EQ, 1.125 * max(EQ, HW)),
          ("after\nK 0.30", 0.30 * LEV * BASE, EQ_AFTER, 1.125 * EQ_AFTER),
          ("after\nK 0.75 (pages)", 0.75 * LEV * BASE, EQ_AFTER,
           1.125 * EQ_AFTER)]
xs = range(len(groups))
for i, (lab, gross, eq, ceil) in zip(xs, groups):
    bx.bar(i - 0.19, eq, 0.34, color=BLUE, label="equity" if i == 0 else None)
    bx.bar(i + 0.19, gross, 0.34, color=ORANGE,
           label="configured gross = K × 1.5 × 100k" if i == 0 else None,
           hatch="//" if gross > ceil else None, edgecolor="#fcfcfb")
    bx.hlines(ceil, i - 0.42, i + 0.42, color=INK, lw=2.0,
              label="guard ceiling 1.125 × max(equity, HW)" if i == 0 else None)
    bx.text(i + 0.19, gross + 1500, f"${gross/1000:.1f}k", ha="center",
            fontsize=9, color=INK)
    bx.text(i - 0.19, eq + 1500, f"${eq/1000:.1f}k", ha="center",
            fontsize=9, color=INK)
bx.set_xticks(list(xs)); bx.set_xticklabels([g[0] for g in groups],
                                            fontsize=10, color=INK)
bx.set_ylim(0, 165_000); bx.set_ylabel("USD", color=INK2)
bx.legend(frameon=False, fontsize=9, loc="upper left")
bx.set_title("Why 0.30: the exposure guard pages 0.75 below ~$99k",
             loc="left", fontsize=12, color=INK)
fig.text(0.01, 0.01,
         "btc-executor rails: DRAWDOWN = high water − 30% × SIZING_BASE_USD "
         "100,000 (fixed, so $30,000 at any account size); DAILY_LOSS = "
         "6% × max(1, K/0.30) of base from 00:00Z equity, frozen per day. "
         "After-halt equity is illustrative (fill at the line). 2026-10-27.",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig("docs/resume_protocol_rails.png", dpi=150, facecolor=fig.get_facecolor())
print("wrote docs/resume_protocol_rails.png")
