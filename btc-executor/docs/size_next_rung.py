"""Where trade size can still go: the RAMP v3 ladder against the two Kelly
envelopes from RESEARCH_FEES.md. Answers "what is the next rung" — there
isn't one; 0.20 is the terminal step. Regenerate: python3 size_next_rung.py"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

BASE = 50_000                      # SIZING_BASE_USD, live
PULLBACK_W = 0.75                  # 1 - w_trend
LEV = 1.5                          # REFERENCE_LEV, the blend /exec/target ships

# RAMP v3 ladder. live=True is where the book is now.
RUNGS = [
    ("token", 0.05, "done"),
    ("A",     0.10, "done"),
    ("B",     0.20, "live"),
    ("C",     0.35, "retired"),
    ("D",     0.56, "retired"),
    ("ceil",  0.80, "retired"),
]
S6_ENV, S5_ENV = 0.22, 0.30        # binding recommended m, fee-corrected

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.4, 5.4),
                             gridspec_kw={"width_ratios": [1.35, 1]})
fig.patch.set_facecolor(SURF)

# ---- left: the ladder, in pullback-entry dollars
xs = range(len(RUNGS))
for x, (name, m, st) in zip(xs, RUNGS):
    usd = m * LEV * PULLBACK_W * BASE
    col = {"done": MUTED, "live": BLUE, "retired": AX}[st]
    a1.bar(x, usd, width=0.62, color=col,
           edgecolor=RED if st == "retired" else "none",
           linewidth=1.4, linestyle=(0, (3, 2)) if st == "retired" else "-",
           zorder=3)
    lbl = f"${usd:,.0f}"
    a1.text(x, usd + 900, lbl, ha="center", va="bottom", fontsize=9.5,
            color=INK if st == "live" else SEC,
            fontweight="bold" if st == "live" else "normal", zorder=4)
    if st == "retired":
        a1.text(x, usd / 2, "RETIRED", ha="center", va="center", fontsize=8.5,
                color=RED, rotation=90, fontweight="bold", zorder=5)

# envelope lines, converted to the same pullback-dollar axis
for env, col, tag in ((S6_ENV, ORANGE, "S6 envelope  m 0.22"),
                      (S5_ENV, AQUA,   "S5 envelope  m 0.30")):
    y = env * LEV * PULLBACK_W * BASE
    a1.axhline(y, color=col, lw=1.8, ls="--", zorder=2)
    a1.text(-0.42, y + 600, tag, ha="left", va="bottom",
            fontsize=9, color=col, fontweight="bold")

a1.set_xticks(list(xs))
a1.set_xticklabels([f"{n}\nKELLY_M {m}" for n, m, _ in RUNGS], fontsize=9,
                   color=SEC)
a1.set_ylabel("pullback entry, USD notional", fontsize=10, color=SEC)
a1.set_title("RAMP v3 ladder vs the Kelly envelopes\n"
             "at SIZING_BASE_USD 50,000 · lev 1.5 · weight 0.75",
             fontsize=11.5, color=INK, loc="left", pad=12)
a1.set_ylim(0, 52_000)
a1.yaxis.grid(True, color=GRID, lw=0.9, zorder=0)
a1.set_axisbelow(True)
for s in ("top", "right"):
    a1.spines[s].set_visible(False)
for s in ("left", "bottom"):
    a1.spines[s].set_color(AX)
a1.tick_params(colors=SEC, labelsize=9)
a1.legend(loc="upper left", handles=[Patch(facecolor=BLUE, label="live — step B, 0.20"),
                   Patch(facecolor=MUTED, label="completed steps"),
                   Patch(facecolor=AX, edgecolor=RED, ls="--",
                         label="outside the envelope")],
          fontsize=9, frameon=False)

# ---- right: gross exposure as a fraction of equity
EQUITY = 100_000.0
cur_gross = 0.20 * LEV * BASE                    # 15,000
scen = [
    ("live now\nbase 50k", cur_gross / EQUITY, BLUE),
    ("KELLY_M 0.22\n(S6 envelope)", 0.22 * LEV * BASE / EQUITY, ORANGE),
    ("base 100k\nKELLY_M 0.20", 0.20 * LEV * 100_000 / EQUITY, AQUA),
]
for i, (lbl, frac, col) in enumerate(scen):
    a2.barh(i, frac, height=0.55, color=col, zorder=3)
    a2.text(frac + 0.006, i, f"{frac:.0%}", va="center", fontsize=10,
            color=INK, fontweight="bold")
a2.axvline(0.30, color=RED, lw=2.0, zorder=4)
a2.text(0.293, -0.42, "MAX_EXPOSURE_FRAC 30%\nexposure_over_cap pages above",
        fontsize=9, color=RED, va="center", ha="right", fontweight="bold")
a2.set_yticks(range(len(scen)))
a2.set_yticklabels([s[0] for s in scen], fontsize=9, color=SEC)
a2.invert_yaxis()
a2.set_xlim(0, 0.40)
a2.set_xlabel("configured gross exposure / equity", fontsize=10, color=SEC)
a2.set_title("What each lever does to exposure", fontsize=11.5, color=INK,
             loc="left", pad=12)
a2.xaxis.grid(True, color=GRID, lw=0.9, zorder=0)
a2.set_axisbelow(True)
for s in ("top", "right"):
    a2.spines[s].set_visible(False)
for s in ("left", "bottom"):
    a2.spines[s].set_color(AX)
a2.tick_params(colors=SEC, labelsize=9)

fig.text(0.008, 0.015,
         "Step B is the terminal rung: C/D/ceiling were retired on the "
         "fee-corrected Kelly re-fit (RESEARCH_FEES.md §5), not deferred. "
         "Doctrine is that the smaller defensible envelope governs → 0.22.",
         fontsize=8.5, color=MUTED)
fig.tight_layout(rect=(0, 0.035, 1, 1))
fig.savefig("/home/user/uranium-dashboard/btc-executor/docs/size_next_rung.png",
            dpi=155, facecolor=SURF)
print("wrote size_next_rung.png")
