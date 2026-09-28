"""CANDIDATE C figures. Palette per repo convention."""
from __future__ import annotations
import json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURF = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
J = lambda n: json.load(open(os.path.join(HERE, n)))
PORT, CRASH, MULTI = J("candC_portfolio.json"), J("candC_crash.json"), J("candC_multi.json")
NET, CTR, ORC = J("candC_net.json"), J("candC_counter.json"), J("candC_oracle.json")
FUND, WIN = J("candC_funding.json"), J("candC_window.json")
U = PORT["universe_liquidity_order"]

plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "text.color": INK, "xtick.color": INK, "ytick.color": INK,
                     "grid.color": GRID, "font.size": 9,
                     "axes.titlesize": 10.5, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False})


def style(ax, ylab=None, xlab=None, title=None):
    ax.grid(True, axis="y", lw=0.7, alpha=0.9, zorder=0)
    ax.set_axisbelow(True)
    if ylab: ax.set_ylabel(ylab)
    if xlab: ax.set_xlabel(xlab)
    if title: ax.set_title(title, loc="left")


# ============================ FIG 1 — THE ANSWER =========================
fig = plt.figure(figsize=(15.2, 9.4))
gs = fig.gridspec = fig.add_gridspec(2, 3, hspace=0.50, wspace=0.34,
                                     left=0.068, right=0.982, top=0.870, bottom=0.078)

ax = fig.add_subplot(gs[0, :2])
ns = sorted(int(k) for k in PORT["ladder"])
gross = [PORT["ladder"][str(n)]["gross_usd"] for n in ns]
# incremental labels: the full "BTC+ETH+SOL+XRP+LTC" strings collided at N>=5
labels = [PORT["ladder"]["1"]["coins"][0]] + \
         ["+" + PORT["ladder"][str(n)]["coins"][-1] for n in ns[1:]]
med = [PORT["subsets"][str(n)]["mult_median"] * PORT["baseline"]["btc_blend_today"]["k_at_DD30"] * PORT["equity"] for n in ns]
b = ax.bar([n - 0.19 for n in ns], gross, width=0.38, color=BLUE, zorder=3,
           label="nested liquidity ladder (pre-registered order)")
ax.bar([n + 0.19 for n in ns], med, width=0.38, color=MUTED, alpha=0.75, zorder=3,
       label="MEDIAN of all C(6,N) subsets — the un-lucky read")
for n, g in zip(ns, gross):
    ax.text(n - 0.19, g + 3200, f"${g/1000:.0f}k", ha="center", fontsize=8.5,
            fontweight="bold", color=BLUE)
ax.axhline(100_000, color=ORANGE, lw=1.6, ls="--", zorder=4)
ax.text(6.62, 116_000, "Casey\ntarget\n$100k", color=ORANGE, va="center",
        ha="left", fontsize=8.2, fontweight="bold")
ax.axhline(15_000, color=INK, lw=1.3, ls=":", zorder=4)
ax.text(6.62, 33_000, "live\ntoday\n$15k", color=INK, va="center", ha="left",
        fontsize=8.2)
ax.set_xticks(ns)
ax.set_xticklabels([f"N={n}\n{l}" for n, l in zip(ns, labels)], fontsize=8.2)
style(ax, "gross notional authorised, USD",
      title="A.  Gross notional at the SAME drawdown budget — P(maxDD>30%) ≤ 10% over a fixed 2.0y horizon")
ax.legend(frameon=False, fontsize=8.3, loc="upper left")
ax.set_ylim(0, 205_000)
ax.set_xlim(0.45, 7.25)
ax.yaxis.set_major_formatter(lambda x, p: f"${x/1000:.0f}k")

ax = fig.add_subplot(gs[0, 2])
names = ["full sample\n(headline)", "net of\nfunding", "fixture BTC\nbaseline",
         "liquidity-\nweighted", "SUSTAINED\nDRAWDOWN"]
vals = [PORT["ladder"]["6"]["mult_vs_btc"], NET["multiple_net"],
        CTR["A4_data_basis"]["mult_fixture"],
        PORT["weighting"]["liquidity weight (24h vlm)"]["mult_vs_btc"],
        CRASH["T3_crash_only_bootstrap"]["drawdown >=15% off 20-day peak"]["mult"]]
cols = [BLUE, BLUE, MUTED, MUTED, ORANGE]
bb = ax.barh(range(len(names)), vals, color=cols, zorder=3, height=0.66)
ax.axvline(1.0, color=INK, lw=1.5, zorder=4)
for i, v in enumerate(vals):
    ax.text(v + 0.03, i, f"{v:.2f}x", va="center", fontsize=9, fontweight="bold",
            color=cols[i])
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names, fontsize=7.8)
ax.invert_yaxis()
ax.tick_params(axis="y", pad=1)
ax.grid(True, axis="x", lw=0.7, alpha=0.9, zorder=0); ax.set_axisbelow(True)
ax.set_xlabel("× gross notional vs BTC alone")
ax.set_title("B.  The multiple, under every basis I could test", loc="left")
ax.set_xlim(0, 2.0)
ax.text(1.03, 4.46, "no gain", color=INK, fontsize=7.2, va="center")

ax = fig.add_subplot(gs[1, 0])
eq = [PORT["ladder"][str(n)]["equity_for_1m"] for n in ns]
ax.plot(ns, eq, "o-", color=BLUE, lw=2.2, ms=7, zorder=3)
ax.axhline(PORT["equity"], color=ORANGE, lw=1.6, ls="--", zorder=4)
ax.text(1.05, PORT["equity"] * 1.35, "Casey's equity today $100k", color=ORANGE,
        fontsize=8.2, fontweight="bold")
for n, e in zip(ns, eq):
    ax.annotate(f"${e/1e3:.0f}k", (n, e), textcoords="offset points",
                xytext=(0, 9), ha="center", fontsize=7.8, color=BLUE)
ax.set_yscale("log")
ax.set_xticks(ns)
style(ax, "equity required (log)", "number of assets",
      title="C.  Equity needed to carry $1,000,000 of gross")
ax.yaxis.set_major_formatter(lambda x, p: f"${x/1000:.0f}k")
ax.set_ylim(4e5, 1.6e6)
ax.text(3.2, 4.6e5, "6 assets cut it 40%\nbut the floor is still ~6× today's equity",
        fontsize=8, color=INK, style="italic")

ax = fig.add_subplot(gs[1, 1])
sh = [MULTI["assets"][c]["blend"]["ann_SR"] for c in U]
cl = [AQUA if MULTI["assets"][c]["blend"]["prob_neg_edge"] <= 0.25 else MUTED for c in U]
ax.bar(range(len(U)), sh, color=cl, zorder=3)
for i, (c, v) in enumerate(zip(U, sh)):
    pn = MULTI["assets"][c]["blend"]["prob_neg_edge"]
    ax.text(i, v + (0.05 if v >= 0 else -0.12), f"{v:.2f}", ha="center",
            fontsize=8, fontweight="bold")
    ax.text(i, -0.30, f"P(neg)\n{pn:.0%}", ha="center", fontsize=7,
            color=INK if pn <= 0.25 else ORANGE)
ax.axhline(0, color=INK, lw=1.2)
ax.set_xticks(range(len(U))); ax.set_xticklabels(U, fontsize=8.5)
style(ax, "annualised Sharpe, S5 blend",
      title="D.  Per-asset edge — only ETH clears the repo's own kill rule")
ax.set_ylim(-0.45, 1.45)
ax.legend(handles=[Patch(color=AQUA, label="passes kill rule (P(neg) ≤ 25%)"),
                   Patch(color=MUTED, label="KILLED by the repo's own rule")],
          frameon=False, fontsize=7.8, loc="upper right")

ax = fig.add_subplot(gs[1, 2])
mx = np.array([CTR["A1_multiple_testing"]["null_max_median"],
               CTR["A1_multiple_testing"]["null_max_p95"]])
ax.axvspan(0, CTR["A1_multiple_testing"]["null_max_p95"], color=MUTED, alpha=0.22,
           zorder=1, label="null: best of 12 legs, 5–95%")
ax.axvline(CTR["A1_multiple_testing"]["null_max_median"], color=MUTED, lw=2, zorder=3)
ax.text(CTR["A1_multiple_testing"]["null_max_median"] - 0.06, 0.88,
        "null median\nof the MAX", color=INK, fontsize=7.6, va="top", ha="right")
obs = CTR["A1_multiple_testing"]["best_ann_SR"]
ax.axvline(obs, color=ORANGE, lw=2.6, zorder=4)
ax.text(obs + 0.04, 0.42, f" ETH/S3\n observed\n {obs:.2f}", color=ORANGE,
        fontsize=8.4, fontweight="bold", va="center")
ax.set_xlim(0, 2.6); ax.set_ylim(0, 1)
ax.set_yticks([])
ax.set_xlabel("annualised Sharpe")
ax.set_title("E.  The edge does NOT survive multiple testing", loc="left")
ax.text(0.06, 0.13, f"family-wise p = {CTR['A1_multiple_testing']['p_familywise']:.3f}\n"
        f"(single-test p = {CTR['A1_multiple_testing']['p_single']:.3f})",
        fontsize=8.6, fontweight="bold", color=ORANGE)
ax.grid(False)

fig.suptitle("CANDIDATE C  ·  more notional via diversification across Hyperliquid perps",
             fontsize=13.5, fontweight="bold", x=0.068, ha="left", y=0.972)
fig.text(0.068, 0.945, "The risk-side mechanism is real and robust. The edge is NOT established.",
         fontsize=10, color=ORANGE, fontweight="bold", ha="left")
fig.text(0.068, 0.914,
         f"6 assets · shipped engine UNCHANGED, zero per-asset fitting · {PORT['n_bars']} common 4h bars, "
         f"{PORT['years']:.2f}y (2024-06→2026-09) · Hyperliquid data · 8.64 bp round trip (measured) · IN-SAMPLE, not a forecast",
         fontsize=8.4, color=MUTED, ha="left")
p1 = os.path.join(HERE, "candC_fig1_the_answer.png")
fig.savefig(p1, dpi=125); plt.close(fig)

# ======================= FIG 2 — THE MECHANISM ===========================
fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.0))
fig.subplots_adjust(left=0.055, right=0.975, top=0.80, bottom=0.30, wspace=0.30)
for ax, key, ttl in ((axes[0], "price_correlation", "A.  UNDERLYING 4h price returns"),
                     (axes[1], "correlation", "B.  STRATEGY streams (S5 blend, per-bar MTM)")):
    M = np.array(MULTI[key]["matrix"])
    im = ax.imshow(M, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(U))); ax.set_xticklabels(U, fontsize=8, rotation=45)
    ax.set_yticks(range(len(U))); ax.set_yticklabels(U, fontsize=8)
    for i in range(len(U)):
        for j in range(len(U)):
            ax.text(j, i, f"{M[i,j]:.2f}", ha="center", va="center", fontsize=7.6,
                    color="white" if abs(M[i, j]) > 0.55 else INK)
    ax.set_title(f"{ttl}\nmean off-diagonal ρ = {MULTI[key]['offdiag_mean']:+.3f}",
                 loc="left", fontsize=9.8)
    ax.grid(False)
fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.03)

ax = axes[2]
ax.barh([1, 0], [MULTI["price_correlation"]["offdiag_mean"],
                 MULTI["correlation"]["offdiag_mean"]],
        color=[ORANGE, AQUA], height=0.42, zorder=3)
ci = CTR["A3_rho_ci"]
ax.plot([ci["ci5"], ci["ci95"]], [0, 0], color=INK, lw=2.4, zorder=5)
ax.text(MULTI["price_correlation"]["offdiag_mean"] + 0.02, 1,
        f"{MULTI['price_correlation']['offdiag_mean']:+.3f}", va="center",
        fontsize=11, fontweight="bold", color=ORANGE)
ax.text(MULTI["correlation"]["offdiag_mean"] + 0.03, 0.30,
        f"{MULTI['correlation']['offdiag_mean']:+.3f}\n90% CI [{ci['ci5']:.3f}, {ci['ci95']:.3f}]",
        va="center", fontsize=9.6, fontweight="bold", color=AQUA)
ax.set_yticks([1, 0]); ax.set_yticklabels(["PRICES\nmove together", "STRATEGIES\ndo not"],
                                          fontsize=9)
ax.set_xlim(0, 0.9); ax.set_xlabel("mean pairwise correlation")
ax.grid(True, axis="x", lw=0.7, alpha=0.9, zorder=0); ax.set_axisbelow(True)
ax.set_title("C.  THE MECHANISM, in one number", loc="left")
fig.text(0.695, 0.135,
         f"The signal is in market only {100*MULTI['assets']['BTC']['S3']['in_market_frac']:.0f}% of bars per leg and picks its own side,\n"
         f"so on average {MULTI['simultaneity']['mean_assets_in_market']:.2f} of 6 assets carry a position at once. That\n"
         f"timing gap — not any hedge — is what decorrelates\n"
         f"{MULTI['price_correlation']['offdiag_mean']:.2f} into {MULTI['correlation']['offdiag_mean']:.2f}. It is also why it is FRAGILE: in a\n"
         f"sustained drawdown the legs line up and it reverts.",
         fontsize=8.3, color=INK, va="top", ha="left")
fig.suptitle("THE MECHANISM  ·  6 crypto perps whose PRICES are 0.72 correlated run STRATEGIES that are only 0.15 correlated",
             fontsize=12.5, fontweight="bold", x=0.055, ha="left", y=0.955)
p2 = os.path.join(HERE, "candC_fig2_mechanism.png")
fig.savefig(p2, dpi=125); plt.close(fig)

# ======================= FIG 3 — THE CRASH CASE ==========================
fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.2))
fig.subplots_adjust(left=0.062, right=0.982, top=0.775, bottom=0.235, wspace=0.235)

ax = axes[0]
regs = ["FULL SAMPLE", "top-quartile 30-bar realised vol",
        "top-decile 30-bar realised vol", "worst 10% of BTC 4h returns",
        "drawdown >=10% off 20-day peak", "drawdown >=15% off 20-day peak"]
short = ["full\nsample", "vol\nQ4", "vol\nD10", "worst 10%\nof bars",
         "DD\n≥10%", "DD\n≥15%"]
pr = [CRASH["T1_conditional_correlation"][r]["price"]["mean"] for r in regs]
st = [CRASH["T1_conditional_correlation"][r]["strategy"]["mean"] for r in regs]
x = np.arange(len(regs))
ax.bar(x - 0.2, pr, 0.4, color=ORANGE, zorder=3, label="PRICE ρ")
ax.bar(x + 0.2, st, 0.4, color=AQUA, zorder=3, label="STRATEGY ρ")
for i, (a, bv) in enumerate(zip(pr, st)):
    ax.text(i - 0.2, a + 0.015, f"{a:.2f}", ha="center", fontsize=7.4, color=ORANGE)
    ax.text(i + 0.2, bv + 0.015, f"{bv:.2f}", ha="center", fontsize=7.4,
            fontweight="bold", color=AQUA)
ax.set_xticks(x); ax.set_xticklabels(short, fontsize=7.6)
style(ax, "mean pairwise correlation",
      title="A.  Correlation by regime")
ax.legend(frameon=False, fontsize=8.2, loc="upper left")
ax.set_ylim(0, 1.0)

ax = axes[1]
cc = [CRASH["T2_side_concentration"]["full_sample"]] + \
     [CRASH["T2_side_concentration"]["regimes"][r]["conc"] for r in regs[1:]]
ax.bar(x, cc, color=[MUTED] + [ORANGE] * 5, zorder=3)
for i, v in enumerate(cc):
    ax.text(i, v + 0.008, f"{v:.3f}", ha="center", fontsize=7.8, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(short, fontsize=7.6)
ax.set_ylim(0.70, 0.95)
style(ax, "|net| / gross directional exposure",
      title="B.  Side concentration")
ax.text(-0.42, 0.706,
        f"{CRASH['T2_side_concentration']['frac_bars_all_same_side']*100:.0f}% of live bars have EVERY live leg on the\n"
        "SAME side. 1.00 = one trade in six wrappers.",
        fontsize=8.0, color=INK, style="italic", va="bottom")

ax = axes[2]
km = [CRASH["T3_crash_only_bootstrap"]["full_sample"]["mult"]] + \
     [CRASH["T3_crash_only_bootstrap"][r]["mult"] for r in regs[1:]]
cols = [BLUE] + [BLUE if v >= 1.0 else ORANGE for v in km[1:]]
ax.bar(x, km, color=cols, zorder=3)
ax.axhline(1.0, color=INK, lw=1.6, zorder=4)
for i, v in enumerate(km):
    ax.text(i, v + 0.03, f"{v:.2f}x", ha="center", fontsize=8.2, fontweight="bold",
            color=cols[i])
ax.set_xticks(x); ax.set_xticklabels(short, fontsize=7.6)
ax.set_ylim(0, 2.70)
style(ax, "× gross notional vs BTC alone",
      title="C.  A crash-only future")
ax.text(-0.45, 2.62, "Block STARTS restricted to stress bars. A one-bar\n"
        "crash is survivable (1.63x). A SUSTAINED drawdown\n"
        "regime is not: 0.89x — worse than BTC alone.",
        fontsize=8.0, color=ORANGE, fontweight="bold", va="top")
fig.suptitle("THE CASE THAT MATTERS  ·  'crypto correlations go to 1 in a crash' — measured, not assumed",
             fontsize=12.5, fontweight="bold", x=0.062, ha="left", y=0.945)
fig.text(0.062, 0.095, "DEPENDENCE ANCHORS, all built from real streams — no copula:",
         fontsize=8.6, color=INK, fontweight="bold", ha="left")
fig.text(0.062, 0.045,
         f"ρ→0, via independent circular block-shifts = {CRASH['T4_anchors']['rho_zero']['mult_mean']:.2f}x      ·      "
         f"ρ as measured ({CRASH['T4_anchors']['rho_measured']['rho']:+.3f}) = {CRASH['T4_anchors']['rho_measured']['mult']:.2f}x      ·      "
         f"ρ=1, every asset replaced by BTC's own stream = {CRASH['T4_anchors']['rho_one']['mult']:.2f}x  (the machinery's own sanity check)",
         fontsize=8.5, color=INK, ha="left")
p3 = os.path.join(HERE, "candC_fig3_crash.png")
fig.savefig(p3, dpi=125); plt.close(fig)

# ======================= FIG 4 — ROBUSTNESS ==============================
fig, axes = plt.subplots(2, 3, figsize=(15.2, 8.3))
fig.subplots_adjust(left=0.058, right=0.962, top=0.855, bottom=0.075,
                    wspace=0.36, hspace=0.50)

ax = axes[0, 0]
g = CTR["A2_budget_sensitivity"]["grid"]
ks = sorted(g, key=lambda s: (float(s.split("_")[0][2:]), float(s.split("_")[1][1:])))
ax.bar(range(len(ks)), [g[k]["mult"] for k in ks], color=BLUE, zorder=3)
ax.axhline(1.0, color=INK, lw=1.3)
ax.set_xticks(range(len(ks)))
ax.set_xticklabels([f"{float(k.split('_')[0][2:]):.0%}\n{float(k.split('_')[1][1:]):.0%}"
                    for k in ks], fontsize=6.6)
ax.set_ylim(0, 2.0)
style(ax, "multiple", "drawdown limit / probability limit",
      title=f"A.  DD budget: {CTR['A2_budget_sensitivity']['mult_min']:.2f}–{CTR['A2_budget_sensitivity']['mult_max']:.2f}x over 12 budgets")

ax = axes[0, 1]
sd = PORT["seed_stability"]
ax.plot(range(len(sd["ratio"])), sd["ratio"], "o-", color=BLUE, lw=2, ms=6, zorder=3)
ax.axhline(sd["ratio_mean"], color=ORANGE, lw=1.5, ls="--", zorder=4)
ax.text(0.1, sd["ratio_mean"] + 0.012, f"mean {sd['ratio_mean']:.2f}x", color=ORANGE,
        fontsize=8.4, fontweight="bold")
ax.set_ylim(1.4, 1.85)
ax.set_xticks(range(len(sd["ratio"])))
ax.set_xticklabels([str(s)[-2:] for s in sd["seeds"]], fontsize=7.5)
style(ax, "multiple", "bootstrap seed (last 2 digits)",
      title=f"B.  Seed stability: {sd['ratio_min']:.2f}–{sd['ratio_max']:.2f}x (sd {sd['ratio_sd']:.3f})")

ax = axes[0, 2]
bs = PORT["block_sensitivity"]
mb = sorted(int(k) for k in bs)
xp = np.arange(len(mb))
ax.plot(xp, [bs[str(m)]["ratio"] for m in mb], "o-", color=BLUE, lw=2.2, ms=7,
        zorder=3, label="RATIO (the claim)")
ax2 = ax.twinx()
ax2.plot(xp, [bs[str(m)]["k_btc"] for m in mb], "s--", color=MUTED, lw=1.5, ms=5,
         label="k(BTC) level")
ax2.plot(xp, [bs[str(m)]["k_6asset"] for m in mb], "^--", color="#c9c6bc", lw=1.5,
         ms=5, label="k(6) level")
ax2.set_ylabel("k level", color=MUTED); ax2.tick_params(colors=MUTED)
ax2.spines["right"].set_visible(True); ax2.spines["right"].set_color(MUTED)
ax2.grid(False)
# LINEAR x on evenly-spaced positions: a log axis drew minor ticks (3x10^1,
# 4x10^1 ...) straight through the category labels in the first render.
ax.set_xscale("linear")
ax.set_ylim(1.3, 1.95)
style(ax, "multiple", "bootstrap mean block (bars)",
      title="C.  Block length moves the LEVEL, not the RATIO")
# AFTER twinx: sharing the x-axis resets the locator, so the first render
# showed 0.0-3.0 instead of the block lengths.
ax.set_xticks(xp); ax.set_xticklabels([str(m) for m in mb])
ax.set_xlim(-0.35, 3.35)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7.2, loc="upper left", ncol=1)

ax = axes[1, 0]
wm = NET["within_mix_net"]
wps = sorted((float(k) for k in wm), reverse=True)
ax.plot([w * 100 for w in wps], [wm[f"{w:.2f}"]["k_gross"] for w in wps], "o-",
        color=MUTED, lw=1.6, ms=5, label="gross of funding")
ax.plot([w * 100 for w in wps], [wm[f"{w:.2f}"]["k_net"] for w in wps], "o-",
        color=BLUE, lw=2.2, ms=6, label="NET of funding")
ax.axvline(75, color=ORANGE, lw=1.5, ls="--")
ax.text(76, 1.18, "shipped\nS5 mix", color=ORANGE, fontsize=8, fontweight="bold")
style(ax, "k = gross / equity", "pullback share of each asset's book, %",
      title="D.  Within-asset mix — 75/25 is at the optimum")
ax.legend(frameon=False, fontsize=8)

ax = axes[1, 1]
rows = [("BTC only, own k", CRASH["realised"][0]),
        ("6 assets, own k", CRASH["realised"][1]),
        ("6 assets, BTC's k", CRASH["realised"][2])]
xs = np.arange(3)
ax.bar(xs - 0.2, [-r[1]["max_dd_pct"] for r in rows], 0.4, color=ORANGE, zorder=3,
       label="realised maxDD, %")
ax.bar(xs + 0.2, [r[1]["in_sample_cagr_pct"] for r in rows], 0.4, color=AQUA,
       zorder=3, label="in-sample CAGR, %")
for i, r in enumerate(rows):
    ax.text(i - 0.2, -r[1]["max_dd_pct"] + 0.35, f"{-r[1]['max_dd_pct']:.1f}",
            ha="center", fontsize=8, color=ORANGE, fontweight="bold")
    ax.text(i + 0.2, r[1]["in_sample_cagr_pct"] + 0.35,
            f"{r[1]['in_sample_cagr_pct']:.1f}", ha="center", fontsize=8,
            color=AQUA, fontweight="bold")
ax.set_xticks(xs); ax.set_xticklabels([r[0] for r in rows], fontsize=8)
style(ax, "percent", title="E.  Realised, in-sample — at MATCHED gross, strictly better")
ax.legend(frameon=False, fontsize=8, loc="upper left")
ax.set_ylim(0, 22)

ax = axes[1, 2]
ax.axis("off")
ax.set_title("F.  Survives / fails", loc="left")
txt = [
    ("HOLDS", AQUA, f"ρ mechanism: strategy 0.15 vs price 0.72,\nCI [{ci['ci5']:.3f}, {ci['ci95']:.3f}]"),
    ("HOLDS", AQUA, f"multiple stable {CTR['A2_budget_sensitivity']['mult_min']:.2f}–{CTR['A2_budget_sensitivity']['mult_max']:.2f}x over 12 DD budgets"),
    ("HOLDS", AQUA, f"seed-stable {sd['ratio_min']:.2f}–{sd['ratio_max']:.2f}x; ρ=1 anchor\nreturns exactly 1.00x"),
    ("HOLDS", AQUA, f"funding is only {abs(FUND['portfolio']['delta_pct_yr']):.2f}%/yr of notional:\n1.66x → {NET['multiple_net']:.2f}x net"),
    ("HOLDS", AQUA, f"oracle leg-picking adds only {ORC['oracle_over_headline']:.2f}x —\nno cherry-pick is available"),
    ("FAILS", ORANGE, f"edge: family-wise p = {CTR['A1_multiple_testing']['p_familywise']:.3f}.\nETH is best-of-12."),
    ("FAILS", ORANGE, f"crash: {CRASH['T3_crash_only_bootstrap']['drawdown >=15% off 20-day peak']['mult']:.2f}x in a sustained ≥15% drawdown"),
    ("FAILS", ORANGE, f"data basis: {CTR['A4_data_basis']['mult_fixture']:.2f}x on the repo's fixture BTC"),
    ("FAILS", ORANGE, "$1m on $100k: needs ~$600k equity.\nCut 40%, not removed."),
]
yy = 1.00
for tag, col, body in txt:
    nl = body.count("\n") + 1
    ax.text(0.0, yy, tag, fontsize=7.4, fontweight="bold", color=col,
            transform=ax.transAxes, va="top")
    ax.text(0.17, yy, body, fontsize=7.5, color=INK, transform=ax.transAxes,
            va="top", linespacing=1.30)
    yy -= 0.062 * nl + 0.028

fig.suptitle("ROBUSTNESS  ·  what moves the answer and what does not",
             fontsize=12.5, fontweight="bold", x=0.062, ha="left", y=0.955)
p4 = os.path.join(HERE, "candC_fig4_robustness.png")
fig.savefig(p4, dpi=125); plt.close(fig)
print("wrote:"); [print(" ", p) for p in (p1, p2, p3, p4)]
