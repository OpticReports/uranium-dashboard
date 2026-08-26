import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from replicate import load_panel, build_weights, metrics
from diagnose import signals, perf

SC = os.path.dirname(os.path.abspath(__file__))
BLUE, ORANGE, AQUA, RED, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#4a3aa7"
INK, MUTED, GRID = "#1f2430", "#6b7280", "#e5e7eb"
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "font.size": 10,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})

P = load_panel("prices_div", "adjClose")
R = P.pct_change(fill_method=None)
R = R.where(R.abs() < 1.0)

# ── curves: bug vs honest vs benchmark ──────────────────────────────────────
value_rank = (1.0 / P).rank(axis=1, pct=True)
pos = (R > 0).astype(float).where(R.notna())
up_inc = pos.rolling(63, min_periods=63).mean()
mom = +(P / P.shift(10) - 1.0)
mom_z = mom.sub(mom.mean(axis=1), axis=0).div(mom.std(axis=1), axis=0)
bug_edge = (0.7 * value_rank + 0.3 * mom_z).where(up_inc > 0.55)
bug = perf(build_weights(bug_edge), "same_day")            # D4 fingerprint

edge_v, _ = signals(0.60, False, False)
verb = perf(build_weights(edge_v), "honest")               # L0 verbatim

# L2 honest: true-price signal, t+1 fill, 3.5bp
P_raw = load_panel("prices_raw", "adjClose")
vr = (1.0 / P_raw).rank(axis=1, pct=True)
rev = -(P_raw / P_raw.shift(10) - 1.0)
rz = rev.sub(rev.mean(axis=1), axis=0).div(rev.std(axis=1), axis=0)
e2 = (0.7 * vr + 0.3 * rz).where(pos.shift(1).rolling(63, min_periods=63).mean() > 0.60)
w2 = build_weights(e2).shift(1)
g2 = (w2 * R.shift(-1)).sum(axis=1).shift(1)
t2 = (w2 - w2.shift(1)).abs().sum(axis=1)
l2 = (g2 - t2.shift(1).fillna(0.0) * 0.00035).dropna()
l2 = l2[l2.index >= "2006-01-03"]

bench = R.mean(axis=1).dropna()
bench = bench[bench.index >= "2006-01-03"]

fig, (a1, a2) = plt.subplots(2, 1, figsize=(10.5, 7.2), sharex=True,
                             gridspec_kw={"height_ratios": [1.6, 1]})
for ser, col, lab, dy in [(bug, RED, "the look-ahead bug (D4): 'Sharpe 12'", 8),
                          (bench, MUTED, "S&P 500 equal-weight", 10),
                          (verb, BLUE, "paper's spec, implemented honestly (L0)", 16),
                          (l2, AQUA, "honest execution + real costs (L2)", -18)]:
    c = (1 + ser).cumprod()
    a1.plot(c.index, c.values, color=col, lw=1.6)
    a1.annotate(lab, xy=(c.index[-1], c.iloc[-1]),
                xytext=(-240 if col != MUTED else -150, dy),
                textcoords="offset points", fontsize=9, color=col)
a1.set_yscale("log")
a1.set_ylabel("growth of $1 (log)")
a1.set_title("arXiv 2511.12490 replicated: the 13-Sharpe exists only inside a one-line look-ahead",
             fontsize=12, loc="left", color=INK, pad=10)
py = l2.groupby(l2.index.year).apply(lambda r: r.mean() / r.std() * np.sqrt(252))
colors = [AQUA if v > 0 else RED for v in py.values]
a2.bar([pd.Timestamp(f"{y}-07-01") for y in py.index], py.values,
       width=250, color=colors)
a2.axhline(0, color=MUTED, lw=0.8)
a2.set_ylabel("honest-rung Sharpe, per year")
a2.text(pd.Timestamp("2006-06-01"), 1.45,
        "honest implementation by calendar year: no year above 2, mean ≈ 0 — "
        "consistent with reversal-after-costs literature", fontsize=9, color=INK)
a2.xaxis.set_major_locator(mdates.YearLocator(2))
a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(f"{SC}/fig1_curves.png", dpi=160)
plt.close(fig)

# ── the ladder waterfall ────────────────────────────────────────────────────
rows = [("Paper's claim (OOS)", 13.19, RED),
        ("Bug reproduction: sign flip + same-day earn (D4)", 11.99, ORANGE),
        ("Their spec, faithfully implemented (L0)", 0.16, BLUE),
        ("+ honest t+1 fill (L1)", 0.14, BLUE),
        ("+ realistic 3.5bp costs (L2)", -0.29, BLUE),
        ("open-to-open marks (L2o)", -1.98, BLUE)]
fig, ax = plt.subplots(figsize=(10.5, 4.4))
ys = range(len(rows))[::-1]
ax.barh(list(ys), [r[1] for r in rows], color=[r[2] for r in rows], height=0.55)
for y, (lab, v, c) in zip(ys, rows):
    ax.text(v + (0.25 if v >= 0 else -0.25), y, f"{v:+.2f}",
            va="center", ha="left" if v >= 0 else "right", fontsize=10, color=INK)
ax.set_yticks(list(ys))
ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
ax.axvline(0, color=MUTED, lw=0.8)
ax.set_xlabel("full-period Sharpe, 2006–2024 (rf=0), current-constituent universe")
ax.set_xlim(-3.2, 15)
ax.set_title("The sin ladder: honest steps remove the manufactured alpha",
             fontsize=12, loc="left", color=INK, pad=10)
fig.tight_layout()
fig.savefig(f"{SC}/fig2_ladder.png", dpi=160)
print("figs done; bug sharpe check:",
      round(bug.mean() / bug.std() * np.sqrt(252), 2))
