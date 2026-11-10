"""Chart for the 2x size step (docs/size_2x_plan.png).

Inputs are the live reads quoted in the reply: Hyperliquid `portfolio`
accountValue and BTC mid at 2026-09-16, and the mirror's own sizing
identities (leg notional = kelly_m * lev * weight * SIZING_BASE_USD;
cap_notional = min(MAX_NOTIONAL_USD, MAX_ACCOUNT_LEV * base)).
usage: python3 docs/size_2x_chart.py docs/size_2x_plan.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "docs/size_2x_plan.png"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED, INK, SEC = "#e34948", "#0b0b0b", "#52514e"
VIOLET = "#4a3aa7"
MUTED, GRID, AX, SURF = "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

EQUITY = 99_892.61          # portfolio accountValue (spot-backed), 2026-09-16
PX = 75_769.5               # BTC mid
KELLY, LEV, W_T = 0.135, 1.5, 0.25

def legs(base):
    return KELLY * LEV * (1 - W_T) * base, KELLY * LEV * W_T * base

P0, T0 = legs(25_000)                     # live config
P1, T1 = legs(50_000)                     # proposed
CAP0, CAP1 = 10_000.0, 20_000.0           # min(MAX_NOTIONAL_USD, 2.0 * base)
T1_CLAMPED = max(0.0, CAP0 - P1)          # trend room if the cap is not raised

fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.3), facecolor=SURF)
for ax in axes:
    ax.set_facecolor(SURF)
    ax.grid(axis="y", color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AX)
    ax.tick_params(colors=SEC, labelsize=9)

# --- A: leg notional against the cap rail ----------------------------------
a = axes[0]
lab = ["now\n25k base / 10k cap", "2x, cap left at 10k\n(clamps)",
       "2x, cap 20k\n(proposed)"]
pull = [P0, P1, P1]
trend = [T0, T1_CLAMPED, T1]
x = range(3)
a.bar(x, pull, 0.55, color=BLUE, zorder=3, label="pullback leg (0.75w)")
a.bar(x, trend, 0.55, bottom=pull, color=ORANGE, zorder=3,
      label="trend leg (0.25w)")
a.axhline(CAP0, color=MUTED, ls="--", lw=1.3, zorder=4)
a.axhline(CAP1, color=AQUA, ls="--", lw=1.3, zorder=4)
a.text(-0.45, CAP0 + 350, "cap_notional 10,000", color=MUTED, fontsize=8.5,
       ha="left")
a.text(-0.45, CAP1 + 350, "cap_notional 20,000", color=AQUA, fontsize=8.5,
       ha="left")
for i, (p, t) in enumerate(zip(pull, trend)):
    a.text(i, p + t + 450, f"${p + t:,.0f}", ha="center", color=INK,
           fontsize=9.5, fontweight="bold")
a.annotate(f"trend clamped\n${T1:,.0f} → ${T1_CLAMPED:,.0f}\ncap_clamp RED"
           " every entry", xy=(1, P1 + T1_CLAMPED), xytext=(0.72, 15_600),
           color=RED, fontsize=8.5, ha="center",
           arrowprops=dict(arrowstyle="->", color=RED, lw=1.2))
a.set_xticks(list(x))
a.set_xticklabels(lab, fontsize=8.5, color=SEC)
a.set_ylabel("gross leg notional, USD", color=SEC, fontsize=9.5)
a.set_ylim(0, 25_000)
a.set_title("Gross deployed vs the cap rail", color=INK, fontsize=11.5,
            fontweight="bold", loc="left")
a.legend(frameon=False, fontsize=8.5, labelcolor=SEC,
         loc="upper center", ncol=2)

# --- B: exposure as % of the account ---------------------------------------
b = axes[1]
gross = [(P0 + T0) / EQUITY * 100, (P1 + T1) / EQUITY * 100]
net = [(P0 - T0) / EQUITY * 100, (P1 - T1) / EQUITY * 100]
xb = [0, 1]
b.bar([v - 0.16 for v in xb], gross, 0.3, color=BLUE, zorder=3, label="gross")
b.bar([v + 0.16 for v in xb], net, 0.3, color=VIOLET, zorder=3,
      label="net (legs opposed)")
for v, g, n in zip(xb, gross, net):
    b.text(v - 0.16, g + 0.5, f"{g:.1f}%", ha="center", color=INK,
           fontsize=9.5, fontweight="bold")
    b.text(v + 0.16, n + 0.5, f"{n:.1f}%", ha="center", color=INK,
           fontsize=9.5, fontweight="bold")
b.axhline(30, color=RED, ls="--", lw=1.3, zorder=4)
b.text(1.45, 27.4, "MAX_EXPOSURE_FRAC 30% — pages exposure_over_cap",
       color=RED, fontsize=8.5, ha="right")
b.set_xticks(xb)
b.set_xticklabels(["now", "2x"], fontsize=9.5, color=SEC)
b.set_ylabel(f"% of ${EQUITY:,.0f} account", color=SEC, fontsize=9.5)
b.set_ylim(0, 40)
b.set_title("Exposure vs the repo ceiling", color=INK, fontsize=11.5,
            fontweight="bold", loc="left")
b.legend(frameon=False, fontsize=8.5, labelcolor=SEC, loc="upper left")

# --- C: the halt rails move with the base ----------------------------------
c = axes[2]
dd = [0.35 * 25_000, 0.35 * 50_000]
dl = [0.06 * 25_000, 0.06 * 50_000]
c.bar([v - 0.16 for v in xb], dd, 0.3, color=RED, zorder=3,
      label="DRAWDOWN halt (35% of base)")
c.bar([v + 0.16 for v in xb], dl, 0.3, color=ORANGE, zorder=3,
      label="DAILY_LOSS halt (6% of base)")
for v, d, l in zip(xb, dd, dl):
    c.text(v - 0.16, d + 350, f"${d:,.0f}\n{d / EQUITY:.1%} of acct",
           ha="center", color=INK, fontsize=8.5, fontweight="bold")
    c.text(v + 0.16, l + 350, f"${l:,.0f}\n{l / EQUITY:.1%}", ha="center",
           color=INK, fontsize=8.5, fontweight="bold")
c.text(0.5, 22_000, "leave MAX_NOTIONAL_USD at 10,000 and the DD halt "
       "(17,500) exceeds the whole cap\n⇒ halt_config WARN every poll",
       color=RED, fontsize=8.5, ha="center", va="top")
c.set_xticks(xb)
c.set_xticklabels(["now", "2x"], fontsize=9.5, color=SEC)
c.set_ylabel("loss required to halt, USD", color=SEC, fontsize=9.5)
c.set_ylim(0, 27_000)
c.set_title("The halt rails double too (they are % of base)", color=INK,
            fontsize=11.5, fontweight="bold", loc="left")
c.legend(frameon=False, fontsize=8.5, labelcolor=SEC,
         loc="upper left", ncol=1)

fig.suptitle("btc-executor 2x size step — SIZING_BASE_USD 25,000 → 50,000"
             f"   (BTC {PX:,.0f}, account ${EQUITY:,.0f}, 2026-09-16)",
             color=INK, fontsize=12.5, fontweight="bold", x=0.008, ha="left",
             y=0.985)
fig.tight_layout(rect=(0, 0, 1, 0.945))
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)
