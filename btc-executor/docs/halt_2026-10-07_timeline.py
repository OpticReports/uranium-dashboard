"""The 2026-10-07 LEDGER_DIVERGENCE halt: the two faults on one page.

Panel A - engine (Fault A): the 04:00Z bar the engine evaluated was the
snapshot it took while the bar was forming; the final bar's low was far
below the pending limit, so the venue filled the order and the engine
said "unfilled".
Panel B - executor (Fault B): the engine-exit close filled in full, but one
order-status read booked the whole leg as a residue nothing settled; the
ledger/venue mismatch escalated to a halt in three polls.
Panel C - the merge-blocking gates, pre-fix vs fixed.

Numbers: btc-executor/docs/HALT_2026-10-07.md section 1 (venue records and
Bitstamp minute candles). Render: python3 halt_2026-10-07_timeline.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

SURF, INK, INK2, MUTED, GRID, AXIS = ("#fcfcfb", "#0b0b0b", "#52514e",
                                      "#898781", "#e1e0d9", "#c3c2b7")
BLUE, ORANGE, GOOD, CRIT, WARN = "#2a78d6", "#eb6834", "#0ca30c", "#d03b3b", "#fab219"

plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": AXIS,
                     "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "text.color": INK,
                     "axes.titlecolor": INK, "axes.titleweight": "bold",
                     "axes.titlesize": 11, "axes.titlelocation": "left"})

fig = plt.figure(figsize=(12.5, 13.2), facecolor=SURF)
gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.0, 0.42], hspace=0.70,
                      top=0.925, bottom=0.03, left=0.07, right=0.97)
axA, axB, axC = (fig.add_subplot(gs[i]) for i in range(3))
for ax in (axA, axB, axC):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)

# ---------------------------------------------------------------- panel A
LIMIT = 84_121.28
O, H, L, C = 84_121.29, 84_348.23, 84_010.77, 84_119.73      # final 04:00Z bar
axA.set_title("A  engine: the 04:00Z bar was evaluated from its first-seconds snapshot")
axA.set_xlim(-0.35, 4.75)
axA.set_ylim(83_940, 84_430)
axA.set_xticks([0, 1, 2, 3, 4])
axA.set_xticklabels(["04:00Z", "05:00", "06:00", "07:00", "08:00Z"])
axA.set_ylabel("BTC-USD")
axA.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.0f}"))
# the final bar, as Bitstamp stores it: wick + hollow body across 04:00-08:00
axA.axvspan(0, 4, color=BLUE, alpha=0.05, lw=0)
axA.plot([2, 2], [L, H], color=BLUE, lw=2, solid_capstyle="round")
axA.add_patch(Rectangle((1.9, min(O, C) - 3), 0.2, abs(O - C) + 6,
                        facecolor=SURF, edgecolor=BLUE, lw=2, zorder=4))
axA.text(2.0, H + 8, "the final 04:00Z bar as Bitstamp stores it: open 84,121.29  high 84,348.23  "
         "low 84,010.77  close 84,119.73", ha="center", va="bottom", color=INK2, fontsize=8.5)
axA.annotate("low 84,010.77 printed at 04:43 — below the limit:\na FILL by the engine's own rule (bar.low < limit)",
             xy=(2, L), xytext=(2.2, 84_030), color=INK, fontsize=8.5,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8), va="center")
# the pending limit
axA.axhline(LIMIT, color=INK2, lw=1, ls=(0, (4, 3)))
axA.text(4.72, LIMIT + 6, "S3 pending limit 84,121.28", ha="right", va="bottom",
         color=INK2, fontsize=8.5)
# the snapshot the engine kept
axA.plot([0.01], [84_121.29], marker="o", ms=9, color=ORANGE, zorder=5)
axA.annotate("04:00:0x snapshot the engine kept until 08:00\nO=H=L=C 84,121.29 (its first seconds): low ≥ limit",
             xy=(0.01, 84_121.29), xytext=(0.22, 84_225), color=INK, fontsize=8.5,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
# the venue fill
axA.plot([0.13], [84_121.0], marker="v", ms=9, color=GOOD, zorder=6,
         markeredgecolor=SURF, markeredgewidth=1)
axA.annotate("04:00:24-31  the venue fills 0.93614 @84,121.00 maker (8 prints);\n"
             "minute-04:00 low 84,113.14 is already below the limit",
             xy=(0.13, 84_121.0), xytext=(0.35, 84_052), color=INK, fontsize=8.5,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
# 08:00 evaluation
axA.axvline(4.0, color=CRIT, lw=1.2)
axA.text(4.03, 84_395, "08:00:0x  OHLC fetch failed →\nstale snapshot evaluated →\n"
         "pending UNFILLED, S3 FLAT", color=CRIT, fontsize=8.5, va="top", weight="bold")
axA.text(4.03, 84_300, "08:00:09  executor: engine flat,\nledger holds → close (panel B)",
         color=INK2, fontsize=8.5, va="top")
axA.text(0, -0.17, "FIX A: a bar is FINAL only when fetched ≥ 30 s after its close. The 08:00 empty fetch "
         "DEFERS the bar (bar_not_final); the next poll's fetch fills the pending at the limit — gate (a).",
         color=GOOD, fontsize=9, va="top", transform=axA.transAxes)

# ---------------------------------------------------------------- panel B
axB.set_title("B  executor: a full close, one lagging status read, and three polls to a halt")
t = [0, 9, 9, 29, 49, 69, 78, 78, 90]
venue = [0.96748, 0.96748, 0.03134, 0.03134, 0.03134, 0.03134, 0.03134, 0.0, 0.0]
ledger = [0.96748, 0.96748, 0.96748, 0.96748, 0.96748, 0.96748, 0.96748, 0.0, 0.0]
fixed = [0.96748, 0.96748, 0.03134, 0.03134, 0.03134, 0.03134, 0.03134, 0.03134, 0.03134]
axB.plot(t, venue, color=ORANGE, lw=2.2, label="venue net position (truth)")
axB.plot(t, ledger, color=BLUE, lw=2.2, label="ledger sum, pre-fix (residue + trend leg)")
axB.plot(t, fixed, color=GOOD, lw=2.2, ls=(0, (5, 3)), label="ledger sum with the fix (booked from the send answer)")
axB.set_xlim(0, 92)
axB.set_ylim(-0.06, 1.12)
axB.set_xlabel("seconds after 08:00:00Z")
axB.set_ylabel("BTC")
axB.set_xticks([9, 29, 49, 69, 78])
axB.set_xticklabels(["08:00:09", ":29", ":49", "08:01:09", ":18"])
axB.legend(loc="upper left", bbox_to_anchor=(0.115, 0.58), frameon=False, fontsize=8.5)
for x, lbl in ((29, "netting_inconsistent 1/3"), (49, "2/3")):
    axB.plot([x], [0.03134], marker="o", ms=8, color=WARN, markeredgecolor=SURF, zorder=5)
    axB.text(x, 0.11, lbl, ha="center", color=INK2, fontsize=8.5)
axB.text(39, 0.19, "grace: the trend leg's stop read OPEN", ha="center", color=MUTED, fontsize=8)
axB.plot([69], [0.03134], marker="o", ms=9, color=CRIT, markeredgecolor=SURF, zorder=5)
axB.text(69, 0.30, "3/3 → LEDGER_DIVERGENCE\ncancel_all, flatten the NET", ha="center",
         color=CRIT, fontsize=8.5, weight="bold")
axB.annotate("08:01:18  halt flatten SELL 0.03134 @84,062:\nthe trend leg closed by the halt, not a signal",
             xy=(78, 0.0), xytext=(90, 0.60), color=INK, fontsize=8.5, ha="right",
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
axB.annotate("08:00:09  engine_exit close SELL 0.93614 IOC reduce-only: FILLED IN FULL\n"
             "(4 prints @84,113 in one ms). One order-status read ≈100 ms later → "
             "\"filled 0.0 of 0.93614\"\n→ the WHOLE leg booked as a residue (close_partial) and nothing settled it",
             xy=(9, 0.5), xytext=(12, 0.72), color=INK, fontsize=8.5,
             arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
axB.text(0, -0.30, "FIX B: the close is booked from the exchange's own order answer (filled totalSz / avgPx, "
         "which cannot lag). With no answer, settlement is poll- and age-gated and a residue never comes "
         "from one read — 17 gates.", color=GOOD, fontsize=9, va="top", transform=axB.transAxes)

# ---------------------------------------------------------------- panel C
axC.set_title("C  merge-blocking gates: pre-fix tree vs fixed tree")
axC.axis("off")
tiles = [
    ("executor  tests/test_close_settle_gates.py", "17 / 17 pass", "15 fail pre-fix (2 are design probes)"),
    ("engine  tests/test_bar_finality.py", "4 / 4 pass", "4 fail pre-fix"),
    ("full suites, fixed tree", "557 + 136 pass", "executor + engine, no skips"),
]
for i, (name, big, sub) in enumerate(tiles):
    x0 = 0.015 + i * 0.33
    axC.add_patch(FancyBboxPatch((x0, 0.08), 0.30, 0.84, boxstyle="round,pad=0.01,rounding_size=0.02",
                                 facecolor=SURF, edgecolor=GRID, lw=1.2, transform=axC.transAxes))
    axC.text(x0 + 0.02, 0.80, name, transform=axC.transAxes, color=INK2, fontsize=8.5, va="top")
    axC.text(x0 + 0.02, 0.50, big, transform=axC.transAxes, color=GOOD if i < 2 else INK,
             fontsize=20, weight="bold", va="center")
    axC.text(x0 + 0.02, 0.18, sub, transform=axC.transAxes, color=MUTED, fontsize=8.5, va="center")

fig.suptitle("LEDGER_DIVERGENCE 2026-10-07 08:01Z — two faults, one halt, 20 days flat",
             x=0.02, ha="left", fontsize=13, weight="bold", color=INK, y=0.985)
fig.text(0.02, 0.962, "from the venue's own fill/order records, Bitstamp minute candles and the code read "
         "(Render logs for 07:59–08:02Z unavailable); realized damage ≈ −$14.5 net of fees, the cost was the halt",
         color=INK2, fontsize=9)
out = __file__.replace(".py", ".png")
fig.savefig(out, dpi=150, facecolor=SURF, bbox_inches="tight")
print("wrote", out)
