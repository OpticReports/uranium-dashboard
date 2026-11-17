import sys, json, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
D = sys.argv[1]; cur = pd.read_pickle(D + "/curves.pkl"); res = json.load(open(D + "/results.json"))
INK, MUT, GRID = "#0b0b0b", "#52514e", "#e4e3df"
COL = {"1 daily": "#2a78d6", "3 month-end": "#eb6834", "4 quarter-end": "#1baf7a", "5 annual calendar": "#eda100", "6 buy&hold": "#e87ba4"}
plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUT, "axes.labelcolor": MUT, "xtick.color": MUT, "ytick.color": MUT, "axes.spines.top": False, "axes.spines.right": False})
labs = list(cur)[:2]
fig, axes = plt.subplots(3, 2, figsize=(14, 9), gridspec_kw={"height_ratios": [3, 1.1, 1.2]}, sharex="col")
for j, L in enumerate(labs):
    curves, dates, tab = cur[L]; ax, axr, axd = axes[0, j], axes[1, j], axes[2, j]
    for i, (k, col) in enumerate(COL.items()):
        v = pd.Series(curves[k], index=dates)
        ax.plot(v.index, v.values, color=col, lw=1.6)
        t = tab[k]
        rd = pd.to_datetime(t["rebalance_dates"]); axr.scatter(rd, [i] * len(rd), marker="|", s=90, color=col, lw=2)
        axd.plot(v.index, v / v.cummax() - 1, color=col, lw=1.1)
    ends = sorted(((curves[k][-1], k) for k in COL), reverse=True); ys = []
    for e, k in ends:
        y = np.log(e) if not ys else min(np.log(e), ys[-1] - 0.035); ys.append(y)
        ax.annotate(f"{k}  {tab[k]['cagr']:.2%}", (dates[-1], np.exp(y)), xytext=(6, 0), textcoords="offset points", color=INK, fontsize=8, va="center")
    ax.set_yscale("log"); ax.grid(axis="y", color=GRID); ax.set_ylabel("growth of $1 (log)")
    S = res["studies"][L]; ax.set_title(f"{L}\n{S['start']} to {S['end']}  (net of costs, trade next close)", fontsize=10, color=INK, loc="left")
    if "proxy" in L:
        for a in (ax, axr, axd): a.axvspan(pd.Timestamp(S["start"]), pd.Timestamp("2020-12-02"), color="#d9d8d3", alpha=.35, lw=0)
        ax.text(pd.Timestamp(S["start"]), ax.get_ylim()[1] * .97, " proxied stretch: AVUV/AVDV/AVEM to 2019-10, KMLM (ASFYX) to 2020-12", fontsize=8, color=MUT, va="top")
    axr.set_yticks(range(len(COL))); axr.set_yticklabels([k.split(" ", 1)[1] for k in COL], fontsize=7.5); axr.set_ylim(-.7, len(COL) - .3); axr.invert_yaxis(); axr.set_title("rebalance trade dates", fontsize=8, color=MUT, loc="left")
    axd.set_ylabel("drawdown"); axd.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, 0)); axd.grid(axis="y", color=GRID)
    ax.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=int(len(dates) / 252 * 75)))
fig.suptitle("B.5 v1.0: band-check cadence barely changes the path (±20% relative bands)", x=.01, ha="left", fontsize=12, color=INK)
fig.tight_layout(); fig.savefig(D + "/cadence_equity.png", dpi=150); plt.close(fig)

arms = ["1 daily", "2 weekly(Fri)", "4 quarter-end", "5 annual calendar", "6 buy&hold", "7 daily band10 (expl)", "8 daily band30 (expl)", "9 daily partial"]
allarms = arms[:2] + ["3 month-end"] + arms[2:]
SC = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a"}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6.6), gridspec_kw={"width_ratios": [1.6, 1]})
keys = list(res["studies"]); y = np.arange(len(arms))
for s_i, L in enumerate(keys):
    S = res["studies"][L]; tag = L[0]; off = (s_i - 1) * .26
    for i, k in enumerate(arms):
        b = S["bootstrap"][k]; hist = (S["table"][k]["cagr"] - S["table"]["3 month-end"]["cagr"]) * 1e4
        a1.plot(b["ci95_bps"], [i + off] * 2, color=SC[tag], lw=2, solid_capstyle="round")
        a1.plot(hist, i + off, "o", ms=6, color=SC[tag], mec="white", mew=1.2)
    a1.plot([], [], "o-", color=SC[tag], label=f"{tag}: {L[2:].split('(')[0].strip()} - dot = actual history, bar = bootstrap 95% CI")
a1.axvline(0, color=INK, lw=1); a1.set_yticks(y); a1.set_yticklabels(arms); a1.invert_yaxis(); a1.grid(axis="x", color=GRID)
a1.set_xlabel("CAGR minus month-end arm (bps/yr), net of costs"); a1.set_xlim(-130, 380)
a1.legend(loc="upper center", bbox_to_anchor=(.5, -.12), fontsize=7.5, frameon=False); a1.set_title("Every CI straddles zero: no cadence beats month-end beyond noise", loc="left", fontsize=10, color=INK)
y2 = np.arange(len(allarms))
for s_i, L in enumerate(keys[:2]):
    S = res["studies"][L]; tag = L[0]; vals = [S["table"][k]["reb_per_yr"] for k in allarms]
    a2.barh(y2 + (s_i - .5) * .38, vals, height=.36, color=SC[tag], label=f"{tag}: {L[2:].split('(')[0].strip()}")
    for yy, v in zip(y2 + (s_i - .5) * .38, vals): a2.text(v + .05, yy, f"{v:.1f}", va="center", fontsize=7, color=MUT)
a2.set_yticks(y2); a2.set_yticklabels(allarms); a2.invert_yaxis(); a2.set_xlabel("rebalances per year"); a2.grid(axis="x", color=GRID)
a2.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(.5, -.12), ncol=2); a2.set_title("Trade frequency", loc="left", fontsize=10, color=INK)
fig.tight_layout(); fig.savefig(D + "/cadence_bars.png", dpi=150)
