import json, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

D = os.path.dirname(os.path.abspath(__file__))
r = json.load(open(f"{D}/results.json"))
s = pd.read_csv(f"{D}/daily_returns.csv", index_col=0, parse_dates=True)
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1f1f1e", "#6b6a64", "#e4e3de"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False})

cols = [("B v1.0", "v1.0", C1),
        ("B v1.2 stand-in (i) CAOS->BIL pre-inception", "v1.2 (BIL stand-in pre-CAOS)", C2),
        ("B v1.2 stand-in (ii) CAOS removed pro-rata pre-inception", "v1.2 (no-CAOS stand-in pre-CAOS)", C3)]
caos0 = pd.Timestamp(r["meta"]["caos_first_return"])

fig, axs = plt.subplots(2, 2, figsize=(13.33, 6.8), dpi=150, sharex="col",
                        gridspec_kw={"height_ratios": [2.2, 1], "width_ratios": [1, 1.35]})
# ---- LEFT: window A, real data for every holding (the comparison the verdict rests on)
A = r["A_common_window"]
colsA = [("A v1.0", "v1.0", A["v1.0"], C1, "-"), ("A v1.2", "v1.2", A["v1.2"], C2, "-"),
         ("A v1.2 no-CAOS pro-rata", "v1.2 weights, CAOS dropped pro-rata", A["v1.2 without CAOS, pro-rata"], "#7a5cc4", "--")]
c1, c2 = axs[0, 0], axs[1, 0]
ddA = []
for key, lab, st, c, ls in colsA:
    ret = s[key].dropna(); w = (1 + ret).cumprod()
    w = pd.concat([pd.Series([1.0], index=[ret.index[0] - pd.Timedelta(days=1)]), w])
    c1.plot(w.index, w.values, color=c, lw=2 if ls == "-" else 1.5, ls=ls,
            label=f"{lab}: CAGR {st['cagr']*100:.1f}%, vol {st['vol']*100:.1f}%, Sharpe {st['sharpe']:.2f}")
    dd = w / w.cummax() - 1
    c2.plot(dd.index, dd.values * 100, color=c, lw=1.6 if ls == "-" else 1.2, ls=ls)
    ddA.append(f"{lab}: {dd.min()*100:.1f}% ({dd.idxmin().date()})")
dA = A["v1.2_minus_v1.0"]
c1.set_yscale("log"); c1.set_yticks([1.0, 1.2, 1.4, 1.6, 1.8]); c1.set_ylim(0.92, 2.15)
c1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
c1.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
c1.legend(loc="upper left", frameon=False, fontsize=8)
c1.text(0.99, 0.03, f"v1.2 - v1.0: {dA['ann_mean_return_diff']*100:+.1f}%/yr, t = {dA['t_stat_mean_diff']:.2f}\n"
        f"Sharpe diff {dA['sharpe_diff_point']:+.2f}, 90% CI [{dA['sharpe_diff_block_bootstrap']['ci90'][0]:+.2f}, "
        f"{dA['sharpe_diff_block_bootstrap']['ci90'][1]:+.2f}] (block bootstrap)",
        transform=c1.transAxes, ha="right", va="bottom", fontsize=8, color=INK)
c1.set_ylabel("Growth of $1 (log)")
c1.set_title(f"A) Matched window, real CAOS ({A['v1.0']['start_first_return']} to {A['v1.0']['end']})",
             fontsize=10.5, color=INK, loc="left")
c2.set_ylabel("Drawdown (%)"); c2.set_ylim(-15.5, 0.5)
c2.text(0.01, 0.04, "Max DD:\n" + "\n".join(ddA), transform=c2.transAxes, fontsize=7.5, color=INK, va="bottom")
c2.xaxis.set_major_locator(mdates.YearLocator()); c2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
for ax in (c1, c2): ax.grid(axis="y", color=GRID, lw=0.8)
# ---- RIGHT: window B, with stand-ins before CAOS existed
a1, a2 = axs[0, 1], axs[1, 1]
x0 = None
ddtxt = []
for key, lab, c in cols:
    ret = s[key].dropna()
    w = (1 + ret).cumprod()
    w = pd.concat([pd.Series([1.0], index=[ret.index[0] - pd.Timedelta(days=1)]), w])
    x0 = w.index[0]
    a1.plot(w.index, w.values, color=c, lw=2, label=lab)
    st = r["B_full_history_real"][key.split("B ", 1)[1]]
    a1.annotate(f"{lab}\nCAGR {st['cagr']*100:.1f}%  Sharpe {st['sharpe']:.2f}", (w.index[-1], w.iloc[-1]),
                xytext=(6, {C1: 10, C2: -14, C3: 0}[c]), textcoords="offset points",
                fontsize=8, color=INK, va="center")
    dd = w / w.cummax() - 1
    a2.plot(dd.index, dd.values * 100, color=c, lw=1.6)
    ddtxt.append(f"{lab}: max DD {dd.min()*100:.1f}% ({dd.idxmin().date()})")
for ax in (a1, a2):
    ax.axvspan(x0, caos0, color="#ecebe6", zorder=0)
    ax.grid(axis="y", color=GRID, lw=0.8)
a1.set_yscale("log")
a1.set_yticks([1.0, 1.25, 1.5, 1.75, 2.0])
a1.text(x0 + (caos0 - x0) / 2, 1.95, "CAOS stand-in\n(pre 2023-03-07; v1.2 lines are\nbracketing assumptions, not CAOS data)",
        ha="center", va="top", fontsize=8, color=MUTED)
a1.text(caos0 + pd.Timedelta(days=20), 1.95, "real CAOS", fontsize=8, color=MUTED, va="top")
a2.text(pd.Timestamp("2023-04-01"), -14.5, "\n".join(ddtxt), fontsize=7.5, color=INK, va="bottom")
a1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
a1.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
a1.set_title(f"B) Real-ETF history ({r['B_full_history_real']['v1.0']['start_first_return']} to {r['B_full_history_real']['v1.0']['end']})",
             fontsize=10.5, color=INK, loc="left")
a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
a1.set_xlim(x0, s.index[-1] + pd.Timedelta(days=560))
fig.suptitle("B.5 v1.0 vs v1.2, net of costs, month-end 20% band + 12m fallback, completed closes only",
             fontsize=11, color=INK, x=0.01, ha="left")
fig.tight_layout()
fig.savefig(f"{D}/b5_fair.png", dpi=150)

# window chart
f2, (b1, b2) = plt.subplots(1, 2, figsize=(9.33, 4.2), dpi=150)
items = [(f"v1.0\nreal {r['B_full_history_real']['v1.0']['start_first_return'][:7]}+", r["B_full_history_real"]["v1.0"], C1, None),
         (f"v1.0\nproxy {r['B2_proxy_extended']['v1.0']['start_first_return'][:7]}+", r["B2_proxy_extended"]["v1.0"], C1, "//"),
         ("v1.0\n2023-03+", r["A_common_window"]["v1.0"], "#86b6ef", None),
         ("v1.2\n2023-03+", r["A_common_window"]["v1.2"], C2, None)]
xs = np.arange(len(items))
for ax, k, t, fmt in [(b1, "sharpe", "Sharpe (excess of 3m bills)", "{:.2f}"), (b2, "max_dd", "Max drawdown", "{:.1%}")]:
    vals = [it[1][k] for it in items]
    bars = ax.bar(xs, vals, color=[it[2] for it in items], width=0.62, edgecolor="white", linewidth=2)
    for b_, it in zip(bars, items):
        if it[3]: b_.set_hatch(it[3])
    for xx, v in zip(xs, vals):
        ax.annotate(fmt.format(v), (xx, v), xytext=(0, 4 if v >= 0 else -13), textcoords="offset points",
                    ha="center", fontsize=9, color=INK)
    if min(vals) < 0: ax.set_ylim(min(vals) * 1.15, 0)
    ax.set_xticks(xs, [it[0] for it in items], fontsize=8)
    ax.set_title(t, fontsize=10.5, color=INK, loc="left")
    ax.axhline(0, color=MUTED, lw=0.8); ax.grid(axis="y", color=GRID, lw=0.8)
b2.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
f2.suptitle(f"Window effect: v1.0 full history vs 2023-03+ (to {r['A_common_window']['v1.0']['end']}), v1.2 over the same 2023-03+ window", fontsize=11, color=INK, x=0.01, ha="left")
f2.tight_layout()
f2.savefig(f"{D}/b5_window.png", dpi=150)

# fold no-fallback sensitivity into results.json
try:
    nf = json.load(open(f"{D}/nofb/results.json"))
    r["sensitivity_no_calendar_fallback"] = {sec: {k: {m: v[m] for m in ("cagr", "sharpe", "max_dd")} for k, v in nf[sec].items() if isinstance(v, dict) and "cagr" in v}
                                             for sec in ("A_common_window", "B_full_history_real", "B2_proxy_extended")}
    json.dump(r, open(f"{D}/results.json", "w"), indent=2)
except FileNotFoundError:
    pass
print("charts ok")
