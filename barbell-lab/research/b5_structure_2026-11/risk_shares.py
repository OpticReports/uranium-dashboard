"""Descriptive only: where the live B.5 book's risk sits, by leg (no arm is tested here).
Reads the overlay study's verified tape (b5_overlay_2026-11/_cache/series.pkl). Writes risk_shares.json + chart."""
import json, os, pickle
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
S = pickle.load(open(os.path.join(HERE, "..", "b5_overlay_2026-11", "_cache", "series.pkl"), "rb"))["T1"]; R = S["legs"]
legs = ["AVUV", "PHYS", "QUAL", "KMLM", "AVDV", "AVEM", "TAIL"]; w = np.array([.235, .235, .153, .141, .118, .059, .059])
out = {}
for nm, a in (("2017-04..2026-11", "2017-04-07"), ("2007-06..2026-11", "2007-06-01")):
    ex = R.loc[a:, legs].sub(R.loc[a:, "BIL"], axis=0); cov = ex.cov().values * 252; pv = np.sqrt(w @ cov @ w)
    port = ex.values @ w; q = np.quantile(port, .05); tail = port <= q
    trc = np.array([(w[i] * ex.values[tail, i]).sum() for i in range(7)]); trc /= trc.sum()
    out[nm] = dict(book_vol=float(pv), legs={l: dict(weight=float(w[i]), vol=float(ex[l].std() * np.sqrt(252)),
                   sharpe=float(ex[l].mean() / ex[l].std() * np.sqrt(252)),
                   sortino=float(ex[l].mean() * 252 / (np.sqrt((np.minimum(ex[l], 0) ** 2).mean()) * np.sqrt(252))),
                   risk_share=float(w[i] * (cov @ w)[i] / pv ** 2), worst5pct_share=float(trc[i]),
                   corr_to_book=float(np.corrcoef(ex[l], port)[0, 1])) for i, l in enumerate(legs)})
json.dump(out, open(os.path.join(HERE, "risk_shares.json"), "w"), indent=1)
INK, INK2, MUT, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
d = out["2017-04..2026-11"]["legs"]; order = sorted(legs, key=lambda l: -d[l]["risk_share"]); y = np.arange(len(order))[::-1]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": AX, "xtick.color": MUT, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False})
fig, ax = plt.subplots(figsize=(9.5, 5.2), facecolor=SURF); ax.set_facecolor(SURF); h = .26
for k, (key, lab, c) in enumerate((("weight", "Share of capital", "#2a78d6"), ("risk_share", "Share of volatility", "#eb6834"), ("worst5pct_share", "Share of losses on the worst 5% of days", "#1baf7a"))):
    v = [d[l][key] * 100 for l in order]; ax.barh(y + (1 - k) * (h + .02), v, h, color=c, label=lab)
    for yy, vv in zip(y + (1 - k) * (h + .02), v):
        ax.text(vv + (1 if vv >= 0 else -1), yy, f"{vv:.0f}%", va="center", ha="left" if vv >= 0 else "right", color=INK2, fontsize=8.5)
ax.axvline(0, color=AX, lw=1); ax.set_yticks(y); ax.set_yticklabels(order); ax.xaxis.grid(True, color=GRID, lw=.8); ax.set_axisbelow(True)
ax.set_xlim(-9, 50); ax.set_xticks([0, 10, 20, 30, 40]); ax.set_xticklabels(["0%", "10%", "20%", "30%", "40%"]); ax.tick_params(length=0)
ax.set_title("Where B.5's risk sits, 2017-04 to 2026-11 (real holdings)", loc="left", color=INK, fontsize=12, fontweight="bold", pad=26)
ax.text(0, 1.035, "The four equity legs are 56.5% of capital and 86% of volatility; KMLM is 14% of capital and 2% of volatility", transform=ax.transAxes, color=INK2, fontsize=9.5)
ax.legend(loc="lower right", frameon=False, labelcolor=INK2)
fig.savefig(os.path.join(HERE, "charts", "01_risk_shares.png"), dpi=170, facecolor=SURF, bbox_inches="tight"); print("ok")
