import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SC = "/tmp/claude-0/-home-user-uranium-dashboard/a7353454-bea3-5b09-b047-d951ff3605bc/scratchpad/r9"
BLUE, ORANGE, AQUA, RED, MUTED, INK, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#6b7280", "#1f2430", "#e5e7eb"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "font.size": 10, "text.color": INK,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False})

# ── fig 1: the 108-arm distribution ─────────────────────────────────────────
res = pd.read_csv(f"{SC}/stage2_results.csv")
arms = res[res.arm != "baseline"].dropna(subset=["ann_excess_vs_base"])
fig, ax = plt.subplots(figsize=(10.5, 4.6))
ax.hist(arms["ann_excess_vs_base"], bins=30, color=BLUE, edgecolor="white")
ax.axvline(0, color=INK, lw=1.2)
ax.set_xlabel("annualized excess vs the size-blind baseline (pp, XBI-excess book)")
ax.set_ylabel("arms")
ax.set_title("108 size-conditional weight schemes vs size-blind equal weights: zero survivors",
             fontsize=12, loc="left", color=INK, pad=10)
best = arms.loc[arms["p_raw"].idxmin()]
ax.annotate(f"best raw p = {best['p_raw']:.3f} ({best['arm']})\n"
            f"→ Westfall-Young p = {best['p_wy']:.2f}",
            xy=(best["ann_excess_vs_base"], 1), xytext=(0.62, 0.82),
            textcoords="axes fraction", fontsize=9.5, color=INK,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax.text(0.02, 0.92, f"baseline IR {res[res.arm=='baseline']['IR'].iloc[0]:.2f} · "
        f"2016-2026 · 33 names · counter-agent reproduced exactly",
        transform=ax.transAxes, fontsize=9.5, color=MUTED)
fig.tight_layout()
fig.savefig(f"{SC}/fig1_arms.png", dpi=160)
plt.close(fig)

# ── fig 2: the one diagnostic — catalyst flags by size bucket ───────────────
fl = pd.read_csv(f"{SC}/stage1_flags.csv")
order = ["binary_event_within_n_days", "quiet_before_catalyst",
         "pullback_into_catalyst", "pullback_price_half",
         "rel_strength_60d", "volume_anomaly"]
labels = ["binary event\n≤21d", "quiet before\ncatalyst", "pullback into\ncatalyst",
          "pullback\n(price only)", "rel strength\n60d", "volume\nanomaly"]
means = fl.groupby(["flag", "bucket"])["r"].mean().unstack().reindex(order)
ns = fl.groupby(["flag", "bucket"])["r"].size().unstack().reindex(order)
x = np.arange(len(order))
w = 0.27
fig, ax = plt.subplots(figsize=(11.5, 5.0))
for i, (bk, col, lab) in enumerate([("S", ORANGE, "small <$1B"),
                                    ("M", BLUE, "mid $1-10B"),
                                    ("L", AQUA, "large ≥$10B")]):
    v = means[bk].values
    ax.bar(x + (i - 1) * w, v, w, color=col, label=lab)
    for xi, vi in zip(x, v):
        ax.text(xi + (i - 1) * w, vi + (0.008 if vi >= 0 else -0.022),
                f"{vi:+.2f}", ha="center", fontsize=8, color=INK)
ax.axhline(0, color=INK, lw=1.0)
ax.axvspan(-0.5, 2.5, color="#fcefe6", zorder=0)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylim(-0.38, 0.30)
ax.set_ylabel("mean R-multiple per fire (net, production grader)")
ax.legend(frameon=False, fontsize=9, ncol=3, loc="lower right")
ax.set_title("DIAGNOSTIC: catalyst-proximity long entries hurt only in small names — and only there",
             fontsize=12, loc="left", color=INK, pad=10)
ax.text(0.01, 0.022,
        "shaded = catalyst-conditioned flags, largely the SAME trades (union 50 symbol-months; 3 small-cap symbols:\n"
        "ARCT/CERS/CMPS — sign consistent in each; only binary-event survives Holm). Fire counts: S 45-58, M 45-97,\n"
        "L 63-194 for catalyst flags; 235-1,411 for price-only flags. Diagnostic grade — not a basis for a weight change.",
        transform=ax.transAxes, fontsize=8.2, color=MUTED, va="bottom")
fig.tight_layout()
fig.savefig(f"{SC}/fig2_flags.png", dpi=160)
print("figs done")
