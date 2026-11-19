"""Chart: B.5 live book vs SPY vs risk-matched SPY+bills. Writes ../charts/13_vs_spy.png."""
import json, os, pickle
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import common as C, engine as E
exec(open(os.path.join(C.HERE, "spy_compare.py")).read().split("# ---- risk-matched")[0].split("out = {}")[0])
J = json.load(open(os.path.join(C.STUDY, "spy_compare.json")))
INK, INK2, MUT, GRID, AX, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
B5C, SPC, MXC = "#2a78d6", "#eb6834", "#52514e"
def mixser(w, a):
    i = cal >= pd.Timestamp(a); R = np.column_stack([spy[i].values, cash[i].values]); me = np.zeros(i.sum(), bool)
    ym = cal[i].year * 12 + cal[i].month; me[:-1] = ym[1:] != ym[:-1]
    return pd.Series(E.simulate(np.ascontiguousarray(R), np.repeat(np.array([[w, 1 - w]]), i.sum(), 0), np.array([1e-4, 1e-4]), me, 0.0, 10 ** 9, 1e-9, False,
                                np.zeros(2, bool), 0.0, 0, i.sum())[0], index=cal[i])
a = "2007-06-01"; W0 = J["2007-06..2026-11"]["spy_risk_matched"]["spy_weight"]
ser = {"B.5 live book": (live.loc[a:], B5C), "SPY": (spy.loc[a:], SPC), f"SPY {W0*100:.0f}% / T-bills {100-W0*100:.0f}% (same volatility as B.5)": (mixser(W0, a), MXC)}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.edgecolor": AX, "axes.labelcolor": INK2, "xtick.color": MUT, "ytick.color": MUT,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": .8, "axes.axisbelow": True})
fig = plt.figure(figsize=(11, 11.5), facecolor=SURF); gs = fig.add_gridspec(3, 1, height_ratios=[1.35, .8, 1], hspace=.42)
ax = fig.add_subplot(gs[0]); ax.set_facecolor(SURF)
for n, (r, c) in ser.items():
    nav = (1 + r).cumprod(); ax.plot(nav.index, nav.values, color=c, lw=2 if "SPY " not in n else 1.6, label=n, ls="-" if "T-bills" not in n else (0, (4, 2)))
    ax.annotate(f"${nav.iloc[-1]:.2f}", (nav.index[-1], nav.iloc[-1]), xytext=(6, 0), textcoords="offset points", va="center", color=INK2, fontsize=9)
ax.set_yscale("log"); ax.set_yticks([.5, 1, 2, 3, 4, 6]); ax.set_yticklabels(["$0.50", "$1", "$2", "$3", "$4", "$6"]); ax.minorticks_off()
ax.set_title("Growth of $1, log scale, 2007-06 to 2026-11 (total return, costs included)", loc="left", color=INK, fontsize=11.5, fontweight="bold")
ax.legend(loc="upper left", frameon=False, labelcolor=INK2)
ax.set_xlim(nav.index[0], nav.index[-1] + pd.Timedelta(days=500))
ax2 = fig.add_subplot(gs[1]); ax2.set_facecolor(SURF)
for n, (r, c) in ser.items():
    nav = (1 + r).cumprod(); dd = (nav / nav.cummax() - 1) * 100
    ax2.plot(dd.index, dd.values, color=c, lw=1.4 if "T-bills" not in n else 1.2, ls="-" if "T-bills" not in n else (0, (4, 2)))
    lab = "B.5" if c == B5C else ("SPY" if c == SPC else "SPY/bills")
    off = {B5C: (40, 10), SPC: (14, -4), MXC: (40, -8)}[c]
    ax2.annotate(f"{lab} {dd.min():.0f}%", (dd.idxmin(), dd.min()), xytext=off, textcoords="offset points", color=INK2, fontsize=9,
                 arrowprops=dict(arrowstyle="-", color=AX, lw=.8))
ax2.set_title("Drawdown from prior peak (%)", loc="left", color=INK, fontsize=11.5, fontweight="bold"); ax2.set_xlim(ax.get_xlim())
ax3 = fig.add_subplot(gs[2]); ax3.set_facecolor(SURF)
cy = J["calendar_years"]; ys = list(cy); x = np.arange(len(ys)); bw = .38
b = [cy[y]["b5"] * 100 for y in ys]; s = [cy[y]["spy"] * 100 for y in ys]
ax3.bar(x - bw / 2 - .01, b, bw, color=B5C, label="B.5 live book"); ax3.bar(x + bw / 2 + .01, s, bw, color=SPC, label="SPY")
ax3.axhline(0, color=AX, lw=1); ax3.set_xticks(x); ax3.set_xticklabels([y[2:] if int(y) % 2 else y for y in ys], fontsize=8.5)
ax3.set_title("Calendar-year return (%) — B.5 ahead in 6 of 19 years: 2008, 2009, 2010, 2020, 2022, 2025 (2026 = YTD)", loc="left", color=INK, fontsize=11.5, fontweight="bold")
ax3.legend(loc="upper left", frameon=False, labelcolor=INK2, ncol=2)
fig.text(.01, .005, "Before 2017 TAIL earns T-bills, KMLM is a managed-futures mutual fund, QUAL is SPY; before 2019 the Avantis legs are DFA funds. SPY from Yahoo adjusted closes (matches the S&P 500 TR index within 0.1 pt/yr).",
         color=MUT, fontsize=8.3)
fig.savefig(os.path.join(C.STUDY, "charts", "13_vs_spy.png"), dpi=170, facecolor=SURF, bbox_inches="tight")
print("ok")
