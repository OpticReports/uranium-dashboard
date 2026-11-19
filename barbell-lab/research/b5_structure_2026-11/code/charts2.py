"""Charts for the structure study, from results2.json + _cache/series2.pkl. Writes ../charts/02..06 *.png."""
import json, os, pickle
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import lib2 as L
r = json.load(open(os.path.join(L.STUDY, "results2.json"))); S = pickle.load(open(os.path.join(L.STUDY, "_cache", "series2.pkl"), "rb"))["T1"]
R = r["T1"]; A = R["arms"]; cal = S["cal"]; OUT = os.path.join(L.STUDY, "charts")
INK, INK2, MUT, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": AX, "axes.labelcolor": INK2, "xtick.color": MUT, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
KC = {"primary": C1, "translation": C1, "sign-only": C1, "secondary": C2, "exploratory": C3, "combo": C3, "control": MUT, "posthoc": MUT}
SHORT = {"P1": "1 Risk-balanced weights", "S1b": "1b ...no halfway shrink", "S1c": "1c ...on downside risk", "P2": "2 Idea 1 at 1.1x (loan +1.5%)", "P2lo": "2 Idea 1 at 1.1x (loan +0.5%)",
         "P2drift": "2 ...unmanaged loan", "S2b": "Live at 1.2x (loan +1.5%)", "S2blo": "Live at 1.2x (loan +0.5%)", "P3": "3 TAIL -> BTAL", "S3b": "3b half of TAIL -> BTAL",
         "P4": "4 Trend blend, same size", "S4b": "4b trend blend at 20%", "P5": "5 10% Treasuries", "S5b": "5b Treasuries + TIPS", "S5c": "5c Treasuries on a loan",
         "P6": "6 AVUV -> large value", "S6a": "6a AVUV -> QUAL", "S6b": "6b AVUV -> min-volatility", "E7": "5% long dollar from TAIL", "E9a": "Collar wrapper on QUAL",
         "E9b": "Put-protected wrapper on QUAL", "COMBO": "Combination picked on 2007-17",
         "C3": "control: TAIL -> T-bills (5.9%)", "C7": "control: 5 pts TAIL -> T-bills"}
order = ["P1", "S1b", "S1c", "P2", "P2lo", "S2b", "S2blo", "P3", "S3b", "C3", "P4", "S4b", "P5", "S5b", "S5c", "P6", "S6a", "S6b", "E7", "C7", "E9a", "E9b", "COMBO"]

# ---- 02 forest: change in Sharpe and Sortino vs the live book, each on its own window
fig, axs = plt.subplots(1, 2, figsize=(12.5, 7.4), sharey=True, gridspec_kw={"wspace": .06}); y = np.arange(len(order))[::-1]
for ax, key, bk, title, lim in ((axs[0], "d_sharpe", "boot_sharpe", "Sharpe change vs live book", (-.16, .2)), (axs[1], "d_sortino_avg", "boot_sortino", "Sortino change vs live book (monthly returns, grid-free estimate)", (-.3, .46))):
    for yy, k in zip(y, order):
        a = A[k]; c = KC[a["kind"]]; lo, hi = a[bk]["ci21"]
        ax.plot([lo, hi], [yy, yy], color=c, lw=2, alpha=.55, solid_capstyle="round"); ax.plot(a["full"][key], yy, "o", color=c, ms=7, mec=SURF, mew=1.5)
    ax.axvline(0, color=AX, lw=1.2); ax.set_xlim(*lim); ax.set_title(title, loc="left", color=INK, fontsize=11, fontweight="bold"); ax.yaxis.grid(False)
axs[0].set_yticks(y); axs[0].set_yticklabels([f"{SHORT[k]}  ({A[k]['window'][0][:4]}+)" for k in order], fontsize=9)
for lab, k in zip(axs[0].get_yticklabels(), order):
    lab.set_color(INK if A[k]["family"] else INK2); lab.set_fontweight("bold" if A[k]["family"] else "normal")
hs = [plt.Line2D([], [], marker="o", ls="", color=c, ms=7, label=l) for c, l in ((C1, "Approved ideas (bold = in the tested family)"), (C2, "Variants"), (C3, "Exploratory / combination"), (MUT, "Control: just hold less TAIL"))]
fig.legend(handles=hs, loc="lower center", ncol=4, frameon=False, labelcolor=INK2, bbox_to_anchor=(.55, -.005))
fig.suptitle("No structural change clears zero: dot = measured change, bar = 95% bootstrap interval", x=.01, ha="left", color=INK, fontsize=12.5, fontweight="bold")
fig.savefig(os.path.join(OUT, "02_changes_vs_live.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

# ---- 03 Sharpe vs Sortino, everything on 2017-04+ (real TAIL), the one window every arm has
i17 = int(cal.searchsorted(L.CONF0)); c = S["cash"]
def ss(x):
    ex = x[i17:] - c[i17:]; return L.E.sharpe(ex), L.sortino_avg(ex)
fig, ax = plt.subplots(figsize=(9.5, 6.6))
pts = {k: ss(S["arms"][k]) for k in order}; lv = ss(S["live"]); kspy = S["live"][i17:].std() / S["spy"][i17:].std(); sm = ss(kspy * S["spy"] + (1 - kspy) * c); sp = ss(S["spy"])
for k, (a, b) in pts.items():
    ax.plot(a, b, "o", color=KC[A[k]["kind"]], ms=8, mec=SURF, mew=1.5)
lab = {"P3": (8, -4), "COMBO": (-8, 8), "S6b": (8, 4), "P5": (-2, -15), "S2b": (10, -12), "E9a": (8, 4), "P1": (-8, 4), "E7": (8, -10), "S1b": (-8, 6), "C3": (8, -4)}
for k, (dx, dy) in lab.items():
    ax.annotate(SHORT[k], pts[k], xytext=(dx, dy), textcoords="offset points", color=INK2, fontsize=8.5, ha="right" if dx < 0 else "left")
ax.plot(*lv, "s", color=INK, ms=9, mec=SURF, mew=1.5); ax.annotate("Live book", lv, xytext=(-8, -13), textcoords="offset points", color=INK, fontsize=9, fontweight="bold", ha="right")
ax.plot(*sm, "D", color=MUT, ms=8, mec=SURF, mew=1.5); ax.annotate("SPY + T-bills\nat live volatility", sm, xytext=(-6, 8), textcoords="offset points", color=INK2, fontsize=8.5, ha="center")
ax.set_xlabel("Sharpe (over T-bills)"); ax.set_ylabel("Sortino (monthly returns, averaged over grid starts)")
ax.set_title("Sharpe vs Sortino, 2017-04 to 2026-11 (real holdings)", loc="left", color=INK, fontsize=12, fontweight="bold")
ax.legend(handles=hs[:4] + [plt.Line2D([], [], marker="s", ls="", color=INK, ms=8, label="Live book"), plt.Line2D([], [], marker="D", ls="", color=MUT, ms=7, label="SPY + T-bills")],
          loc="lower right", frameon=False, labelcolor=INK2, fontsize=8.5)
fig.savefig(os.path.join(OUT, "03_sharpe_vs_sortino.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

# ---- 04 equity (log) and wealth relative to the live book
i0 = int(cal.searchsorted(L.EXT0)); d = cal[i0:]
nav = lambda x, i=i0: np.cumprod(1 + x[i:])
fig, axs = plt.subplots(2, 1, figsize=(11, 9), gridspec_kw={"hspace": .32, "height_ratios": [1.15, 1]})
ax = axs[0]
for x, col, nm, lw in ((S["spy"], C4, "SPY", 1.6), (S["arms"]["P5"], C3, "5 With 10% Treasuries", 1.6), (S["arms"]["P1"], C2, "1 Risk-balanced weights", 1.6), (S["live"], C1, "Live book", 2.2)):
    n_ = nav(x); ax.plot(d, n_, color=col, lw=lw, label=nm)
    ax.annotate(f"${n_[-1]:.2f}", (d[-1], n_[-1]), xytext=(6, {"SPY": 0, "Live book": 4, "1 Risk-balanced weights": -14, "5 With 10% Treasuries": -5}[nm]), textcoords="offset points", va="center", color=INK2, fontsize=8.5)
ax.set_yscale("log"); ax.set_yticks([.5, 1, 2, 4, 6]); ax.set_yticklabels(["$0.50", "$1", "$2", "$4", "$6"]); ax.minorticks_off()
ax.legend(loc="upper left", frameon=False, labelcolor=INK2); ax.set_xlim(d[0], d[-1] + pd.Timedelta(days=420))
ax.set_title("Growth of $1, log scale, 2007-06 to 2026-11", loc="left", color=INK, fontsize=11.5, fontweight="bold")
ax = axs[1]; base = nav(S["live"])
for k, col in (("P1", C2), ("P5", C3), ("P6", C4), ("P3", C1)):
    rel = nav(S["arms"][k]) / base * 100 - 100; ax.plot(d, rel, color=col, lw=1.8, label=SHORT[k])
    ax.annotate(f"{rel[-1]:+.1f}%", (d[-1], rel[-1]), xytext=(6, {"P1": -7, "P5": 6}.get(k, 0)), textcoords="offset points", va="center", color=INK2, fontsize=8.5)
ax.axhline(0, color=AX, lw=1.2); ax.legend(loc="lower left", frameon=False, labelcolor=INK2, ncol=2); ax.set_xlim(d[0], d[-1] + pd.Timedelta(days=420))
ax.set_title("Cumulative wealth relative to the live book (%): where each change gained or lost", loc="left", color=INK, fontsize=11.5, fontweight="bold")
fig.text(.01, .03, "Stand-in data before 2017 (TAIL), 2020-12 (KMLM) and 2019-10 (Avantis legs). The BTAL arm equals the live book before 2011-09.", color=MUT, fontsize=8.3)
fig.savefig(os.path.join(OUT, "04_equity_and_relative.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

# ---- 05 drawdowns
fig, ax = plt.subplots(figsize=(11, 4.4))
for x, col, nm, lw in ((S["arms"]["S2b"], C4, "Live at 1.2x", 1.3), (S["arms"]["P5"], C3, "5 With 10% Treasuries", 1.3), (S["arms"]["P1"], C2, "1 Risk-balanced weights", 1.3), (S["live"], C1, "Live book", 1.8)):
    n_ = nav(x); dd = (n_ / np.maximum.accumulate(n_) - 1) * 100; ax.plot(d, dd, color=col, lw=lw, label=f"{nm} (worst {dd.min():.0f}%)")
ax.legend(loc="lower right", frameon=False, labelcolor=INK2); ax.set_title("Drawdown from prior peak (%)", loc="left", color=INK, fontsize=11.5, fontweight="bold")
fig.savefig(os.path.join(OUT, "05_drawdowns.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

# ---- 06 what the risk-balanced arm held
W = S["W"]["P1"][i0:]; legs = ["AVUV", "AVDV", "AVEM", "QUAL", "PHYS", "KMLM", "TAIL"]; cols = ["#184f95", "#3987e5", "#86b6ef", "#b7d3f6", C4, C3, MUT]
fig, ax = plt.subplots(figsize=(11, 4.6)); ax.stackplot(d, [W[:, L.IX[l]] * 100 for l in legs], colors=cols, labels=legs, edgecolor=SURF, linewidth=.6)
ax.set_ylim(0, 100); ax.set_ylabel("% of book"); ax.legend(loc="center left", bbox_to_anchor=(1.0, .5), frameon=False, labelcolor=INK2, reverse=True)
ax.set_title("What the risk-balanced arm held: target weights by year (live weights until 2009)", loc="left", color=INK, fontsize=11.5, fontweight="bold")
lw_ = R["p1_weights"]["2026"]; ax.text(.01, -.16, "2026 targets: " + ", ".join(f"{k} {v * 100:.1f}" for k, v in lw_.items()) + ", TAIL 5.9   (live: AVUV 23.5, PHYS 23.5, QUAL 15.3, KMLM 14.1, AVDV 11.8, AVEM 5.9)",
                                       transform=ax.transAxes, color=MUT, fontsize=8.5)
fig.savefig(os.path.join(OUT, "06_risk_balanced_weights.png"), dpi=170, bbox_inches="tight"); plt.close(fig); print("ok")
