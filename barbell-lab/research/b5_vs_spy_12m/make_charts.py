"""Chart for the B.5-vs-SPY trailing-12m study. usage: make_charts.py results.json out.png"""
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

SURF, INK, INK2, MUTED, GRID, BASE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
B5, SPY = "#2a78d6", "#eb6834"          # categorical slots 1-2 (validated, light)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": BASE,
                     "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.facecolor": SURF, "figure.facecolor": SURF, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
                     "axes.spines.top": False, "axes.spines.right": False})

res = json.load(open(sys.argv[1]))["primary"]
b5, spy = res["B5_v1.0_TAIL_bands"], res["SPY"]
rb = pd.Series(b5["daily_returns"]); rb.index = pd.to_datetime(rb.index)
rs = pd.Series(spy["daily_returns"]); rs.index = pd.to_datetime(rs.index)
t0 = pd.Timestamp(res["window"]["buy_close"])
wb = pd.concat([pd.Series([1.0], [t0]), (1 + rb).cumprod()]) * 100
ws = pd.concat([pd.Series([1.0], [t0]), (1 + rs).cumprod()]) * 100

fig = plt.figure(figsize=(15, 9.2))
gs = fig.add_gridspec(3, 2, width_ratios=[1.6, 1], height_ratios=[2.3, 1, 1], hspace=0.38, wspace=0.27)
ax1 = fig.add_subplot(gs[0, 0]); ax2 = fig.add_subplot(gs[1, 0], sharex=ax1); ax3 = fig.add_subplot(gs[2, 0], sharex=ax1)
ax4 = fig.add_subplot(gs[0:2, 1]); ax5 = fig.add_subplot(gs[2, 1])

# A — growth of $100
ax1.plot(wb.index, wb, color=B5, lw=1.8, label=f"B.5 Enhanced  {b5['total_return']:+.1%}", solid_capstyle="round")
ax1.plot(ws.index, ws, color=SPY, lw=1.8, label=f"SPY  {spy['total_return']:+.1%}", solid_capstyle="round")
for d in b5["rebalance_dates"]:
    d = pd.Timestamp(d)
    ax1.plot([d], [wb.loc[d]], "o", ms=6, color=B5, mec=SURF, mew=1.5, zorder=5)
    ax1.annotate(f"band rebalance ({d:%b %d})", (d, wb.loc[d]), xytext=(0, 14), textcoords="offset points",
                 ha="center", color=INK2, fontsize=8)
ax1.axhline(100, color=BASE, lw=0.8)
ax1.set_title("Growth of $100 — total return, daily closes", loc="left", color=INK, fontsize=11)
ax1.legend(loc="upper left", frameon=False, fontsize=10)
ax1.tick_params(labelbottom=False)

# B — cumulative lead (pp of starting capital)
lead = wb - ws
ax2.plot(lead.index, lead, color=INK2, lw=1.4)
ax2.fill_between(lead.index, 0, lead, where=lead >= 0, color=B5, alpha=0.14, lw=0, interpolate=True)
ax2.fill_between(lead.index, 0, lead, where=lead < 0, color=SPY, alpha=0.14, lw=0, interpolate=True)
ax2.axhline(0, color=BASE, lw=0.8)
pk = lead.idxmax()
ax2.annotate(f"B.5 lead peaks +{lead.max():.1f}pp ({pk:%b %d})", (pk, lead.max()), xytext=(-8, 0),
             textcoords="offset points", color=INK2, fontsize=8, va="center", ha="right")
ax2.annotate(f"{lead.iloc[-1]:+.1f}pp", (lead.index[-1], lead.iloc[-1]), xytext=(4, 0),
             textcoords="offset points", color=INK, fontsize=8, va="center")
ax2.set_title("B.5 minus SPY, cumulative (pp)  — blue wash = B.5 ahead, orange = SPY ahead",
              loc="left", color=INK, fontsize=10)
ax2.tick_params(labelbottom=False)

# C — drawdown
for w, c, s in ((wb, B5, b5), (ws, SPY, spy)):
    dd = (w / w.cummax() - 1) * 100
    ax3.plot(dd.index, dd, color=c, lw=1.4)
    ax3.fill_between(dd.index, 0, dd, color=c, alpha=0.08, lw=0)
    tr = dd.idxmin()
    ax3.annotate(f"{dd.min():.1f}%", (tr, dd.min()), xytext=(4 if c == SPY else -4, -2), textcoords="offset points",
                 ha="left" if c == SPY else "right", va="top", color=INK, fontsize=8)
ax3.set_title("Drawdown from running peak (%)", loc="left", color=INK, fontsize=10)
ax3.xaxis.set_major_locator(mdates.MonthLocator())
ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b\n'%y"))
ax3.set_ylim(top=0.5)

# D — contribution by holding (pre-cost Carino, sums to the zero-cost total)
att = b5["attribution_pp_zero_cost"]; tg = b5["targets"]; tr = res["per_ticker_total_return"]
order = sorted(att, key=att.get)
y = np.arange(len(order))
ax4.barh(y, [att[t] for t in order], height=0.55, color=B5)
for i, t in enumerate(order):
    v = att[t]
    ax4.annotate(f"{v:+.2f}", (v, i), xytext=(4 if v >= 0 else -4, 0), textcoords="offset points",
                 ha="left" if v >= 0 else "right", va="center", color=INK, fontsize=9)
ax4.set_yticks(y, [f"{t} {tg[t]:.0%}\n12m {tr[t]:+.1%}" for t in order], color=INK2, fontsize=8.5)
ax4.axvline(0, color=BASE, lw=0.8)
ax4.grid(axis="y", visible=False)
tot = sum(att.values())
ax4.set_title(f"What drove B.5 — contribution by holding (pp)\n"
              f"Σ {tot:+.2f}pp pre-cost, costs {(b5['total_return']*100 - tot):+.2f}pp → net {b5['total_return']:+.2%}  (SPY {spy['total_return']:+.2%})",
              loc="left", color=INK, fontsize=10)
lo, hi = min(att.values()), max(att.values())
ax4.set_xlim(lo - 1.2, hi + 1.2)

# E — monthly returns
mb, ms = b5["monthly"], spy["monthly"]
months = list(ms)
x = np.arange(len(months)); bw = 0.38
ax5.bar(x - bw/2 - 0.01, [mb[m]*100 for m in months], width=bw, color=B5, label="B.5")
ax5.bar(x + bw/2 + 0.01, [ms[m]*100 for m in months], width=bw, color=SPY, label="SPY")
ax5.axhline(0, color=BASE, lw=0.8)
lab = [pd.Period(m).strftime("%b\n'%y") + ("*" if i in (0, len(months)-1) else "") for i, m in enumerate(months)]
ax5.set_xticks(x, lab, fontsize=8)
ax5.grid(axis="x", visible=False)
ax5.legend(loc="upper right", frameon=False, ncol=2, fontsize=8)
ax5.set_title(f"Monthly return (%) — B.5 beat SPY in {b5['months_beating_spy']} months  (*partial month)",
              loc="left", color=INK, fontsize=10)

fig.suptitle("B.5 Enhanced sleeve vs SPY — trailing 12 months  (buy 2025-10-09 close → mark 2026-10-09 close)",
             x=0.06, y=0.985, ha="left", color=INK, fontsize=13, fontweight="bold")
fig.text(0.06, 0.012,
         f"Simulated from v1.0 target weights (register LIVE since 2026-07-17; earlier months are hypothetical) via the platform's simulate(): "
         f"±20% relative bands checked month-end, platform cost model (incl. entry). Total return (Yahoo adjclose; FMP cross-check within 6.2bp/ticker). "
         f"NOT the live account's fills/timing; bot sleeve not included.  Vol {b5['ann_vol']:.1%} vs {spy['ann_vol']:.1%} · "
         f"beta {b5['beta_to_spy_daily']:.2f} daily / 0.58 weekly · corr {b5['corr_to_spy_daily']:.2f}.",
         color=MUTED, fontsize=7.5, wrap=True)
fig.subplots_adjust(left=0.06, right=0.97, top=0.92, bottom=0.09)
fig.savefig(sys.argv[2], dpi=150, facecolor=SURF)
print("wrote", sys.argv[2])
