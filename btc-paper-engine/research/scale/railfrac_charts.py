"""CANDIDATE B - the four charts. Run the three measurement scripts first."""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import numpy as np                                                    # noqa: E402
import matplotlib                                                    # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                      # noqa: E402
from matplotlib.ticker import FuncFormatter                          # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURF = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
RED = "#c0392b"

J = lambda n: json.load(open(os.path.join(HERE, n)))
SIM, PROP, ADV, SAN, HALT = (J("railfrac_sim.json"), J("railfrac_proposal.json"),
                             J("railfrac_adversarial.json"), J("railfrac_sanity.json"),
                             J("railfrac_halt.json"))
E0 = 100_055.0

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": GRID,
    "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.grid": True, "grid.linewidth": 0.7, "axes.spines.top": False,
    "axes.spines.right": False, "figure.dpi": 130})

usd = FuncFormatter(lambda v, _: (f"${v/1e6:.1f}m" if v >= 1e6 else
                                  f"${v/1e3:.0f}k" if v >= 1e3 else f"${v:.0f}"))
pct = FuncFormatter(lambda v, _: f"{v:.0%}")


def stamp(fig, txt):
    fig.text(0.005, 0.004, txt, fontsize=6.4, color=MUTED, ha="left", va="bottom")


# ============================================================= FIG 1  THE BREAK
eq = np.geomspace(80_000, 8_000_000, 400)
KM_T, LEV, BASE_T, MN_T = 0.20, 1.5, 50_000.0, 20_000.0
intent = 0.15 * eq                                        # 15% of equity, always
today_fixed = np.full_like(eq, KM_T * LEV * BASE_T)       # base constant
today_scaled = np.minimum(0.30 * eq, MN_T)                # base=equity, cap $20k
step1 = np.minimum(0.15 * eq, np.minimum(45_000.0, 0.20 * eq))
step2 = np.minimum(0.30 * eq, np.minimum(90_000.0, 0.40 * eq))

fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.4, 5.5))
for ax in (a1, a2):
    ax.set_xscale("log"); ax.xaxis.set_major_formatter(usd)
    ax.set_xlabel("account equity")
    ax.axvline(E0, color=INK, lw=1.0, ls=":", zorder=1)

a1.set_yscale("log"); a1.yaxis.set_major_formatter(usd)
a1.plot(eq, intent, color=MUTED, lw=1.4, ls="--", label="intent: 15% of equity")
a1.plot(eq, today_fixed, color=RED, lw=2.4,
        label="TODAY (base $50k fixed) — flat forever")
a1.plot(eq, today_scaled, color=ORANGE, lw=2.4,
        label="base=equity, cap left at $20k — clamps")
a1.plot(eq, step1, color=BLUE, lw=2.6, label="STEP 1 (fractional rails)")
a1.plot(eq, step2, color=AQUA, lw=2.0, ls="-.", label="STEP 2 (the free 2×)")
a1.axhline(1_000_000, color=INK, lw=0.9, ls=":")
a1.text(8.2e4, 1.08e6, "$1m of gross notional", fontsize=7.6, color=INK)
a1.scatter([E0], [15_000], color=RED, s=46, zorder=6)
a1.annotate("live today $15,000\n(STEP 1 ships the same)", (E0, 15_000), (1.9e5, 6_200),
            fontsize=7.6, color=RED, arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
a1.annotate("STEP 1 stops being proportional here\n($225k) — BY DESIGN: cap_clamp RED\n"
            "fires on every entry from here on",
            (225_000, 45_000), (2.9e5, 2.4e5), fontsize=7.4, color=BLUE,
            arrowprops=dict(arrowstyle="->", color=BLUE, lw=0.9))
a1.set_title("Gross notional the rails actually deliver")
a1.set_ylabel("gross notional deployed")
a1.legend(frameon=False, fontsize=7.6, loc="upper left",
          bbox_to_anchor=(0.005, 0.995))

a2.yaxis.set_major_formatter(pct); a2.set_ylim(0, 0.34)
a2.plot(eq, intent / eq, color=MUTED, lw=1.4, ls="--")
a2.plot(eq, today_fixed / eq, color=RED, lw=2.4)
a2.plot(eq, today_scaled / eq, color=ORANGE, lw=2.4)
a2.plot(eq, step1 / eq, color=BLUE, lw=2.6)
a2.plot(eq, step2 / eq, color=AQUA, lw=2.0, ls="-.")
a2.axhline(0.30, color=INK, lw=0.8, ls=":")
a2.text(1.45e6, 0.307, "MAX_EXPOSURE_FRAC 0.30", fontsize=7.4, color=INK)
a2.text(1.45e6, 0.157, "15% — today's risk, held", fontsize=7.4, color=BLUE)
a2.annotate("today's book stops betting\nas the account grows",
            (6.0e5, 0.025), (1.15e5, 0.058), fontsize=7.6, color=RED,
            arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
a2.set_title("The same thing as RISK: gross notional ÷ equity")
a2.set_ylabel("gross notional as a fraction of equity")

fig.suptitle("Casey's premise is right, and one fixed dollar number is what breaks it. "
             "MAX_NOTIONAL_USD does not scale.", fontsize=12.5, weight="bold", y=0.985)
stamp(fig, "btc-executor rails replayed over 318 real engine trades (S3+S4, 2022-02→2026-07). "
           "IN-SAMPLE. Trade-close basis. research/scale/railfrac_sim.py")
fig.tight_layout(rect=[0, 0.016, 1, 0.945])
fig.savefig(os.path.join(HERE, "railfrac_fig1_the_break.png"))
plt.close(fig)

# ================================================= FIG 2  INVARIANCE + BLAST RADIUS
M1C = SIM["M1c_matched_risk"]["rows"]
xe = [r["equity"] for r in M1C]
fd_dd = [-r["fixed_dollar"]["maxdd"] for r in M1C]
ff_dd = [-r["fixed_frac"]["maxdd"] for r in M1C]
fd_g = [r["fixed_dollar"]["gross"] for r in M1C]
ff_g = [r["fixed_frac"]["gross"] for r in M1C]

fig, (b1, b2, b3) = plt.subplots(1, 3, figsize=(15.6, 5.2))
b1.set_xscale("log"); b1.xaxis.set_major_formatter(usd)
b1.plot(xe, ff_dd, color=BLUE, lw=2.6, marker="o", ms=5,
        label="fixed FRACTION (STEP 1)")
b1.plot(xe, fd_dd, color=RED, lw=2.4, marker="s", ms=5,
        label="fixed DOLLAR (today)")
b1.axhline(2.42, color=BLUE, lw=0.8, ls=":")
b1.text(1.02e5, 2.20, "−2.42% at EVERY equity level", fontsize=7.8, color=BLUE)
b1.set_ylim(0, 3.4)
for x, g in zip(xe, ff_g):
    b1.annotate(f"${g/1e3:.0f}k" if g < 1e6 else f"${g/1e6:.2f}m",
                (x, 2.42), (x, 2.72), fontsize=7.0, color=BLUE, ha="center")
b1.set_title("Casey's premise, measured\nsame proportion → same drawdown")
b1.set_ylabel("in-sample max drawdown (%)"); b1.set_xlabel("account equity")
b1.legend(frameon=False, fontsize=7.8, loc="upper right")
b1.text(1.02e5, 0.18, "labels above the flat line = gross notional\n"
        "carried, at identical measured risk", fontsize=7.0, color=MUTED)

A1 = ADV["A1_blast_radius"]
b2.set_xscale("log"); b2.xaxis.set_major_formatter(usd); b2.yaxis.set_major_formatter(pct)
eqx = np.geomspace(80_000, 8_000_000, 300)
b2.plot(eqx, np.minimum(20_000.0, 2.0 * 50_000.0) / eqx, color=RED, lw=2.4,
        label="TODAY: $20k, constant in dollars")
b2.plot(eqx, np.minimum(45_000.0, 0.20 * eqx) / eqx, color=BLUE, lw=2.6,
        label="STEP 1: 20% of equity, then $45k")
b2.axhline(0.20, color=MUTED, lw=0.8, ls=":")
b2.text(8.4e4, 0.205, "20% of equity", fontsize=7.4, color=MUTED)
b2.set_ylim(0, 0.26)
b2.annotate("the fixed rail stops being a risk\ncontrol and becomes a throttle",
            (1.0e6, 0.020), (1.45e5, 0.055), fontsize=7.6, color=RED,
            arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
b2.set_title("Blast radius: worst single position\nif a latent bug loses 100% of it")
b2.set_ylabel("worst position ÷ equity"); b2.set_xlabel("account equity")
b2.legend(frameon=False, fontsize=7.8, loc="upper right")

rows = SAN["bad_read_rows"]
ex = [r["e"] for r in rows]
b3.set_xscale("log")
b3.plot(ex, [r["h1.5_x"] for r in rows], color=ORANGE, lw=2.2, marker="s", ms=4,
        label="ceiling h=1.5, no clamp")
b3.plot(ex, [r["h3_x"] for r in rows], color=RED, lw=2.2, marker="^", ms=4,
        label="ceiling h=3.0, no clamp")
b3.plot(ex, [r["h3_clamp_x"] for r in rows], color=BLUE, lw=2.8, marker="o", ms=5,
        label="h=3.0 + EQUITY_SANITY_MULT 1.25")
b3.axhline(20_000 / 15_000, color=MUTED, lw=1.0, ls="--")
b3.text(9.0, 1.365, "today's cap ratio 1.333×", fontsize=7.4, color=MUTED)
b3.set_ylim(0.82, 3.35)
b3.set_title("The NEW risk fractional rails create:\na bad equity read sizes the trade")
b3.set_ylabel("oversize shipped (× intended)")
b3.set_xlabel("equity read error (× true equity)")
b3.legend(frameon=False, fontsize=7.6, loc="upper left")
b3.text(2.6, 0.88, "the clamp is what makes STEP 1 SAFER\nthan today, not a trade-off",
        fontsize=7.2, color=BLUE)

fig.suptitle("What scaling buys, what it costs, and the one new failure mode "
             "fractional rails create", fontsize=12.5, weight="bold", y=0.985)
stamp(fig, "Left/middle: 318-trade replay, in-sample, trade-close. Right: arithmetic on "
           "mirror.py _base/_leg_qty. research/scale/railfrac_{sim,adversarial,sanity}.py")
fig.tight_layout(rect=[0, 0.016, 1, 0.94])
fig.savefig(os.path.join(HERE, "railfrac_fig2_invariance_and_price.png"))
plt.close(fig)

# ================================================== FIG 3  THE SAFETY / HALT PICTURE
G = HALT["false_fire_grid"]
lv = [float(x) for x in HALT["levels"]]
keys = list(G.keys())
M = np.array([[G[k]["p_fire"][str(l)] for l in lv] for k in keys], dtype=float)

fig, (c1, c2) = plt.subplots(1, 2, figsize=(13.6, 5.4),
                             gridspec_kw={"width_ratios": [1.25, 1]})
im = c1.imshow(M, cmap="RdYlGn_r", vmin=0, vmax=1, aspect="auto")
c1.set_xticks(range(len(lv))); c1.set_xticklabels([f"{l:.1%}" for l in lv], fontsize=7.6)
c1.set_yticks(range(len(keys)))
ROWLAB = {0: "live today", 1: "STEP 2 (free 2×)",
          2: "Kelly envelope", 3: "DD30 ceiling"}
c1.set_yticklabels([f"{ROWLAB[i]}\n{G[k]['gross_frac']:.0%} of equity"
                    for i, k in enumerate(keys)], fontsize=7.6)
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        c1.text(j, i, f"{M[i,j]:.0%}", ha="center", va="center", fontsize=7.0,
                color="white" if M[i, j] > 0.55 else INK)
c1.set_xlabel("DD_HALT_PCT (with base = equity, this IS the drawdown % that halts)")
c1.set_title("Breaker FALSE-FIRE rate: P(a clean 4.4y path\ntrips the halt), "
             "bootstrapped (kelly.dd_prob)")
c1.grid(False)
c1.add_patch(plt.Rectangle((lv.index(0.175) - .5, -.5), 1, M.shape[0],
                           fill=False, edgecolor=BLUE, lw=2.4))
c1.text(lv.index(0.175), -0.78, "proposed 0.175", fontsize=8.0,
        color=BLUE, ha="center", weight="bold")
plt.colorbar(im, ax=c1, fraction=0.035, pad=0.02).set_label("P(fire | no bug)",
                                                            fontsize=7.6)

bars = [("today\nbase $50k", 0.175, BLUE), ("base=equity,\nDD_HALT_PCT left\nat 0.35",
        0.35, RED), ("STEP 1\nre-cut to 0.175", 0.175, BLUE)]
c2.bar([b[0] for b in bars], [b[1] for b in bars],
       color=[b[2] for b in bars], width=0.6)
c2.axhline(0.30, color=INK, lw=1.6, ls="--")
c2.text(-0.46, 0.318, "Kelly drawdown BUDGET 30%", fontsize=8.2, color=INK, weight="bold")
c2.yaxis.set_major_formatter(pct); c2.set_ylim(0, 0.42)
for i, b in enumerate(bars):
    c2.text(i, b[1] + 0.012, f"{b[1]:.1%}", ha="center", fontsize=9, weight="bold",
            color=b[2])
c2.text(1, 0.175, "fires only AFTER\nthe budget is blown", ha="center", fontsize=8.0,
        color="white", weight="bold")
for i in (0, 2):
    c2.text(i, 0.072, "inside the budget:\nprotects it", ha="center", fontsize=8.0,
            color="white", weight="bold")
c2.set_title("Where the drawdown breaker actually sits,\nas a % of the REAL account")
c2.set_ylabel("drawdown that halts the book")

fig.suptitle("Flipping the base to equity silently DOUBLES the loss the breakers permit "
             "(17.5% → 35.0%). The re-cut is free.", fontsize=12.2, weight="bold", y=0.985)
stamp(fig, "Bootstrap: kelly.dd_prob, 2000 draws, seed 20260804, stationary block 10, "
           "318 exit-step returns. Trade-close — MTM runs 1-4pp deeper (KELLY.md). "
           "research/scale/railfrac_halt.py")
fig.tight_layout(rect=[0, 0.03, 1, 0.94])
fig.savefig(os.path.join(HERE, "railfrac_fig3_safety.png"))
plt.close(fig)

# ==================================================== FIG 4  THE HONEST ANSWER
fig, (d1, d2) = plt.subplots(1, 2, figsize=(13.4, 5.2),
                             gridspec_kw={"width_ratios": [1.15, 1]})
regs = [("repo rail 0.30× equity", 0.30, MUTED),
        ("STEP 1  0.15×", 0.15, BLUE),
        ("STEP 2  0.30×", 0.30, AQUA),
        ("Kelly envelope 0.54×", 0.54, ORANGE),
        ("DD30 ceiling 1.32×", 1.32, RED)]
labs = [r[0] for r in regs]
need_1m = [1_000_000.0 / r[1] for r in regs]
need_100k = [100_000.0 / r[1] for r in regs]
y = np.arange(len(regs))
d1.barh(y - 0.2, need_100k, 0.38, color=[r[2] for r in regs], alpha=0.48,
        label="$100k of gross notional")
d1.barh(y + 0.2, need_1m, 0.38, color=[r[2] for r in regs],
        label="$1m of gross notional")
d1.set_yticks(y); d1.set_yticklabels(labs, fontsize=8.2)
d1.set_xscale("log"); d1.xaxis.set_major_formatter(usd)
d1.axvline(E0, color=INK, lw=2.0)
d1.text(E0 * 0.60, -0.92, f"equity today\n${E0:,.0f}", fontsize=8.2,
        color=INK, weight="bold", ha="center")
for i, (v, w) in enumerate(zip(need_100k, need_1m)):
    d1.text(v * 1.08, i - 0.2, f"${v/1e3:.0f}k", fontsize=7.2, va="center", color=MUTED)
    d1.text(w * 1.08, i + 0.2, f"${w/1e6:.2f}m", fontsize=7.4, va="center", color=INK)
d1.set_xlabel("equity required")
d1.set_title("Equity required for Casey's targets.\nCandidate B moves NONE of these bars.")
d1.legend(frameon=False, fontsize=7.8, loc="center right")
d1.invert_yaxis()

what = [("gross notional the rails deliver at today's equity", "$15,000", "$30,017", AQUA),
        ("does notional follow equity?", "no — flat", "yes, to $225k", BLUE),
        ("blast radius as % of equity", "20% → 0.3% (decays)", "20% (constant)", BLUE),
        ("bad equity read → oversize", "1.00× (immune)", "1.25× (clamped)", ORANGE),
        ("worst configurable exposure", "UNBOUNDED", "0.40× equity", BLUE),
        ("equity needed for $1m gross", "$6.67m", "$3.33m", MUTED)]
d2.axis("off")
d2.text(0.02, 0.945, "TODAY", fontsize=9.4, weight="bold", color=RED, transform=d2.transAxes)
d2.text(0.58, 0.945, "AFTER STEP 1 + 2", fontsize=9.4, weight="bold", color=BLUE,
        transform=d2.transAxes)
d2.plot([0.01, 0.99], [0.925] * 2, color=INK, lw=1.0, transform=d2.transAxes,
        clip_on=False)
for i, (lab, a, b, col) in enumerate(what):
    top = 0.885 - i * 0.150
    d2.text(0.02, top, lab, fontsize=7.8, color=MUTED, transform=d2.transAxes)
    d2.text(0.02, top - 0.060, a, fontsize=9.0, color=INK, transform=d2.transAxes,
            linespacing=1.25)
    d2.text(0.58, top - 0.060, b, fontsize=9.0, color=col, weight="bold",
            transform=d2.transAxes, linespacing=1.25)
    d2.plot([0.01, 0.99], [top - 0.098] * 2, color=GRID, lw=0.8,
            transform=d2.transAxes, clip_on=False)
d2.set_title("The ledger of the change", fontsize=10.5, loc="left")

fig.suptitle("$1m of notional is a CAPITAL question, not a rails question. "
             "Candidate B makes the rails stop being the answer's blocker.",
             fontsize=12.2, weight="bold", y=0.985)
stamp(fig, "Multiples from research/scale/{fee_axis,envelope}.json (Phase 1) and "
           "railfrac_proposal.json. Kelly envelope is IN-SAMPLE on the selection "
           "window — an upper bound on honest size, not a forecast.")
fig.tight_layout(rect=[0, 0.035, 1, 0.93])
fig.savefig(os.path.join(HERE, "railfrac_fig4_the_answer.png"))
plt.close(fig)
print("wrote railfrac_fig1_the_break.png, fig2_invariance_and_price.png, "
      "fig3_safety.png, fig4_the_answer.png")
