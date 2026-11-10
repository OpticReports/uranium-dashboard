#!/usr/bin/env python3
"""RESEARCH_SCALE.md synthesis figure.

Three panels, all frozen numbers - nothing is recomputed here. Every value is
quoted from the named phase-1 / phase-2 artifact in research/scale/ and is
reproducible from it. This script only draws, then prints the arithmetic
behind each panel so the figure can be checked against the text.

  A  authorised gross notional at today's equity, by ceiling
  B  equity required to carry $1,000,000 of gross, by the same ceilings
  C  every candidate's notional multiple, as published vs after adversarial
     verification

Palette: dataviz reference instance, light surface. Static repo artifact, so
light mode only - stated rather than implied.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.lines import Line2D
import numpy as np

EQUITY = 100_055.0          # phase 1 risk/edge lanes; capital lane read $100,020.91
LEV = 1.5                   # REFERENCE_LEV, what /exec/target ships as the S5 blend

# ---------------------------------------------------------------- palette
SURF = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#dedcd6"
S1 = "#2a78d6"   # blue    - verified / survives
S2 = "#eb6834"   # orange  - the live book, and the repo's own rail
S3 = "#1baf7a"   # aqua    - drawdown budget
S4 = "#eda100"   # yellow  - the fee axis
S8 = "#e34948"   # red     - as published / refuted

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": GRID,
    "xtick.color": INK2, "ytick.color": INK2,
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
})

D = r"\$"   # matplotlib parses a bare $ as mathtext


def usd(x, _=None):
    if x >= 1e6:
        return f"{D}{x/1e6:.1f}m"
    if x >= 1e3:
        return f"{D}{x/1e3:.0f}k"
    return f"{D}{x:.0f}"


# ------------------------------------------------- panel A/B: the ceilings
# (label, gross/equity multiple, colour, source artifact)
CEILINGS = [
    (f"engine default fee 12.00bp\nm 0.07",             0.07 * LEV,  S4, "fee_axis.json"),
    ( "repo rail MAX_EXPOSURE_FRAC\n0.30 of equity",    0.30,        S2, "mirror.py:86"),
    ( "RESEARCH_FEES frozen\nS5 m 0.30",                0.30 * LEV,  S4, "RESEARCH_FEES.md 5"),
    ( "measured fee 8.64bp\nm 0.36",                    0.36 * LEV,  S4, "fee_axis.json"),
    ( "+30% staking discount\nm~0.56   [DERIVED]",      0.56 * LEV,  S4, "fee_axis + userFees"),
    ( "DD-30% budget, data we have\nk_max 0.6775",      0.6775 * LEV, S3, "ladder_findings.json"),
    ( "DD-30% budget, unlimited data\nm 0.88 asymptote", 0.88 * LEV, S3, "nscale.json"),
]
LIVE_A = 30_000.0   # render.yaml 76dfb08 record, 2026-09-28
LIVE_B = 15_000.0   # the config stated in the task brief

fig = plt.figure(figsize=(16.6, 6.9))
gs = fig.add_gridspec(1, 3, width_ratios=[1.10, 1.0, 1.06], wspace=0.40,
                      left=0.130, right=0.975, top=0.755, bottom=0.115)

y = np.arange(len(CEILINGS))
labels = [c[0] for c in CEILINGS]
cols = [c[2] for c in CEILINGS]

# ---- A -------------------------------------------------------------------
axA = fig.add_subplot(gs[0, 0])
vals = [c[1] * EQUITY for c in CEILINGS]
axA.barh(y, vals, height=0.60, color=cols, zorder=3)
for yi, v in zip(y, vals):
    axA.text(v * 1.07, yi, usd(v), va="center", ha="left", fontsize=8.6,
             color=INK, fontweight="bold")
axA.set_yticks(y)
axA.set_yticklabels(labels, fontsize=7.6)
axA.set_xscale("log")
axA.set_xlim(6.5e3, 9e5)
axA.set_ylim(-1.15, len(CEILINGS) - 0.35)
axA.xaxis.set_major_formatter(FuncFormatter(usd))
axA.grid(axis="x", color=GRID, lw=0.7, zorder=0)
axA.set_axisbelow(True)
axA.axvline(LIVE_B, color=S2, lw=1.1, ls=":", zorder=4)
axA.axvline(LIVE_A, color=S2, lw=1.9, zorder=4)
axA.axvline(100_000, color=INK, lw=1.5, ls="--", zorder=4)
axA.text(LIVE_A, len(CEILINGS) - 0.28, f"live {D}30k", color=S2, fontsize=8.4,
         fontweight="bold", ha="center", va="bottom")
axA.text(LIVE_B * 0.93, len(CEILINGS) - 0.62, f"brief {D}15k", color=S2,
         fontsize=7.6, ha="right", va="center")
axA.text(100_000, len(CEILINGS) - 0.28, f"TARGET {D}100k", color=INK,
         fontsize=8.4, fontweight="bold", ha="center", va="bottom")
axA.text(6.9e3, -0.95, f"the {D}1m target is 10x off the right of this axis",
         fontsize=8.2, color=S8, fontweight="bold", va="center")
axA.set_xlabel(f"authorised gross notional at equity {D}100,055   (log)", fontsize=8.6)
axA.set_title("A.  What the book is allowed to carry today", fontsize=11,
              fontweight="bold", loc="left", color=INK, pad=22)

# ---- B -------------------------------------------------------------------
axB = fig.add_subplot(gs[0, 1])
eq_req = [1_000_000.0 / c[1] for c in CEILINGS]
axB.barh(y, eq_req, height=0.60, color=cols, zorder=3)
for yi, v in zip(y, eq_req):
    axB.text(v * 1.07, yi, usd(v), va="center", ha="left", fontsize=8.6,
             color=INK, fontweight="bold")
axB.set_yticks(y)
axB.set_yticklabels([])
axB.set_xscale("log")
axB.set_xlim(4.5e5, 4.2e7)
axB.set_ylim(-1.15, len(CEILINGS) - 0.35)
axB.xaxis.set_major_formatter(FuncFormatter(usd))
axB.grid(axis="x", color=GRID, lw=0.7, zorder=0)
axB.set_axisbelow(True)
axB.axvline(757_576, color=INK, lw=1.5, ls="--", zorder=4)
axB.text(757_576, len(CEILINGS) - 0.28, f"floor {D}758k", color=INK,
         fontsize=8.4, fontweight="bold", ha="center", va="bottom")
axB.text(4.9e5, -0.98, f"equity today is {D}100,055  -  7.6x short of the floor, at best",
         fontsize=8.2, color=S8, fontweight="bold", va="center")
axB.set_xlabel(f"equity required to carry {D}1,000,000 of gross   (log)", fontsize=8.6)
axB.set_title(f"B.  The {D}1m answer is a deposit, not a config", fontsize=11,
              fontweight="bold", loc="left", color=INK, pad=22)

# ---- C -------------------------------------------------------------------
axC = fig.add_subplot(gs[0, 2])
LEVERS = [
    ("raise blend leverage 2.0 -> 4.0", 2.000, 1.000),
    ("diversify, 6 HL perps",           1.661, 0.964),
    ("maker-entry fix (cand D)",        1.396, 1.065),
    ("diversify, BTC+ETH only",         1.274, 1.159),
    ("vol-targeted sizing, best arm",   0.987, 1.088),
]
yc = np.arange(len(LEVERS))[::-1]
for yi, (lab, pub, ver) in zip(yc, LEVERS):
    axC.plot([pub, ver], [yi, yi], color=GRID, lw=2.6, zorder=2,
             solid_capstyle="round")
    axC.plot(pub, yi, "o", ms=9.5, color=S8, zorder=4, mec=SURF, mew=1.8)
    axC.plot(ver, yi, "o", ms=9.5, color=S1, zorder=4, mec=SURF, mew=1.8)
    pad = 0.035
    if ver <= pub:   # verified on the left, published on the right
        axC.text(ver - pad, yi, f"{ver:.2f}x", color=S1, fontsize=8.3,
                 fontweight="bold", ha="right", va="center")
        axC.text(pub + pad, yi, f"{pub:.2f}x", color=S8, fontsize=8.3,
                 fontweight="bold", ha="left", va="center")
    else:            # published on the left, verified on the right
        axC.text(pub - pad, yi, f"{pub:.2f}x", color=S8, fontsize=8.3,
                 fontweight="bold", ha="right", va="center")
        axC.text(ver + pad, yi, f"{ver:.2f}x", color=S1, fontsize=8.3,
                 fontweight="bold", ha="left", va="center")
axC.axvline(1.0, color=INK, lw=1.4, ls="--", zorder=1)
axC.text(1.0, len(LEVERS) - 0.62, "parity - buys nothing", color=INK,
         fontsize=8.2, ha="center", va="bottom")
axC.set_yticks(yc)
axC.set_yticklabels([l[0] for l in LEVERS], fontsize=8.2)
axC.set_xlim(0.78, 2.26)
axC.set_ylim(-1.15, len(LEVERS) - 0.35)
axC.grid(axis="x", color=GRID, lw=0.7, zorder=0)
axC.set_axisbelow(True)
axC.text(0.80, -0.95, "2 of 2 adversarial passes\nrefuted all four candidates",
         fontsize=8.2, color=S8, fontweight="bold", va="center")
axC.set_xlabel("x authorised gross notional at the same drawdown budget", fontsize=8.6)
axC.set_title("C.  Every mechanism shrank under verification", fontsize=11,
              fontweight="bold", loc="left", color=INK, pad=22)
axC.legend(handles=[Line2D([], [], marker="o", ls="", ms=8.5, color=S8,
                           label="as published"),
                    Line2D([], [], marker="o", ls="", ms=8.5, color=S1,
                           label="after verification")],
           loc="lower right", frameon=False, fontsize=8.4,
           bbox_to_anchor=(1.0, 0.075))

fig.text(0.008, 0.955,
         f"Can this book trade {D}100k, and then {D}1m, without more drawdown?",
         fontsize=13.5, fontweight="bold", ha="left", color=INK)
fig.text(0.008, 0.905,
         f"{D}100k  YES - it is inside the drawdown budget at today's equity, and outside every other control the repo has."
         f"        {D}1m  NO - it needs {D}0.76m to {D}1.0m of equity.",
         fontsize=10.6, fontweight="bold", ha="left", color=S8)
fig.text(0.008, 0.862,
         "All values frozen from research/scale/*.json.  Trade-close basis, IN-SAMPLE on a fixture carrying ~2,515 prior "
         "trials, no Deflated-Sharpe haircut;  every authorised size is an UPPER bound on honest size, not a forecast.",
         fontsize=8.3, color=INK2, ha="left")

out = "/home/user/uranium-dashboard/btc-paper-engine/research/scale/scale_answer.png"
fig.savefig(out, dpi=150, facecolor=SURF)
print("wrote", out)

# ------------------------------------------------------- printed arithmetic
print("\n=== PANEL A/B TABLE (equity %.2f, lev %.1f) ===" % (EQUITY, LEV))
print(f"{'ceiling':50s} {'g/eq':>7s} {'gross@today':>12s} {'eq for $100k':>13s} {'eq for $1m':>12s}")
for lab, m, _c, src in CEILINGS:
    print(f"{lab.replace(chr(10),' '):50s} {m:7.4f} {m*EQUITY:12,.0f} "
          f"{100_000/m:13,.0f} {1_000_000/m:12,.0f}   [{src}]")
print(f"\nlive A (render.yaml 76dfb08): ${LIVE_A:,.0f} = {LIVE_A/EQUITY:.4f} x equity, "
      f"k_eff = {LIVE_A/(LEV*EQUITY):.4f}")
print(f"live B (task brief):          ${LIVE_B:,.0f} = {LIVE_B/EQUITY:.4f} x equity, "
      f"k_eff = {LIVE_B/(LEV*EQUITY):.4f}")
for tgt in (100_000, 1_000_000):
    print(f"  ${tgt:,} = {tgt/EQUITY:.2f}x equity | {tgt/LIVE_A:.2f}x live-A | {tgt/LIVE_B:.2f}x live-B")

print("\n=== HALT REACHABILITY (DD_HALT_PCT 0.35 of base, KELLY_M 0.20, lev 1.5) ===")
print("  base = gross / 0.30 ;  halt threshold = 0.35 * base = 1.16667 * gross")
for g in (15_000, 30_000, 45_000, 68_609, 85_761, 100_000, 1_000_000):
    base = g / 0.30
    halt = 0.35 * base
    print(f"  gross ${g:>9,.0f} -> base ${base:>11,.0f} -> DD halt ${halt:>11,.0f} "
          f"= {halt/EQUITY:7.1%} of equity | MAX_ACCOUNT_LEV 2.0*base = "
          f"${2*base:>12,.0f} = {2*base/EQUITY:5.1f}x equity")
print(f"  guard-1 WARN (0.35*base > 0.80*equity) above gross = ${0.80*EQUITY/1.16667:,.0f}")
print(f"  breaker UNREACHABLE (0.35*base > equity) above gross = ${EQUITY/1.16667:,.0f}")

print("\n=== DD COST OF SCALING k (bootstrap median maxDD, ladder_findings.json) ===")
LAD = [(0.05, 1.59), (0.10, 3.16), (0.15, 4.71), (0.20, 6.24), (0.30, 9.27), (0.65, 19.38)]
prev = None
for k, dd in LAD:
    g = k * LEV * EQUITY
    line = f"  k {k:5.2f} -> gross ${g:>9,.0f}  median maxDD {dd:5.2f}%"
    if prev:
        dg, ddd = g - prev[0], dd - prev[1]
        line += f"   (+${dg:>8,.0f} for +{ddd:4.2f}pp = ${dg/ddd:>7,.0f} per pp)"
    print(line)
    prev = (g, dd)
