"""Figure for the modern-window re-judgement. python3 modern_chart.py -> modern_answer.png"""
import json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["text.parse_math"] = False
BLUE,ORANGE,AQUA,RED,INK,SEC,MUTED,GRID,AX,SURF="#2a78d6","#eb6834","#1baf7a","#e34948","#0b0b0b","#52514e","#898781","#e1e0d9","#c3c2b7","#fcfcfb"
d = json.load(open("modern.json"))
names = ["live engine","H1 down-only","H1 vol-target (registered)","H2 200d gate","H3a carry static","H1 down-only + H3a"]
lab = ["live engine","vol-target\n(down-only)","vol-target\n(registered)","200-day gate","carry sleeve\n(static)","vol-target +\ncarry"]
fig, ax = plt.subplots(1, 2, figsize=(16, 5.8)); fig.patch.set_facecolor(SURF)
def st(a):
    a.set_facecolor(SURF); [a.spines[s].set_visible(False) for s in ("top","right")]
    [a.spines[s].set_color(AX) for s in ("left","bottom")]; a.tick_params(colors=SEC,labelsize=9); a.yaxis.grid(True,color=GRID,zorder=0)
a = ax[0]; x = np.arange(len(names)); w = 0.38
for j,(s,col) in enumerate([("2019-01-01",BLUE),("2020-01-01",AQUA)]):
    v = [d[s][n]["sharpe"] for n in names]; base = d[s]["live engine"]["sharpe"]
    lo = [base + d[s][n]["ci90"][0] for n in names]; hi = [base + d[s][n]["ci90"][1] for n in names]
    xx = x + (j - .5) * w
    a.bar(xx, v, w, color=col, label=f"since {s[:4]}", zorder=3)
    a.errorbar(xx[1:], v[1:], yerr=[np.array(v[1:]) - np.array(lo[1:]), np.array(hi[1:]) - np.array(v[1:])],
               fmt="none", ecolor=INK, elinewidth=1, capsize=3, zorder=4)
    for i, t in enumerate(v): a.text(xx[i], 0.05, f"{t:.2f}", ha="center", fontsize=8.5, color="white", zorder=5)
a.set_xticks(x); a.set_xticklabels(lab, fontsize=8.5); a.set_ylim(0, 1.8)
a.set_ylabel("Sharpe (daily, account level)", fontsize=9, color=SEC)
a.set_title("A. Fair comparison (2019+ / 2020+): whiskers = 90% CI of the gain", loc="left", fontsize=11, color=INK)
a.text(4, 1.50, "can't run on\nHL as set up", ha="center", fontsize=8, color=RED)
a.text(3, 1.32, "rejected", ha="center", fontsize=8, color=RED)
a.legend(frameon=False, fontsize=8.5, loc="upper left"); st(a)
a = ax[1]
rows = [("today\nKELLY_M 0.30", d["sizing"]["2019+ live engine"]["0.30 (today)"], MUTED),
        ("live engine\nat -30% (k 0.73)", d["k_safe"]["2019+ live engine"], BLUE),
        ("vol-target down-only\nat -30% (k 0.94)", d["k_safe"]["2019+ H1 down-only"], AQUA)]
for i, (l, v, c) in enumerate(rows):
    a.bar(i, v["per_yr"] / 1000, 0.6, color=c, zorder=3)
    a.text(i, v["per_yr"] / 1000 + 0.8, f"${v['per_yr']/1000:.0f}k/yr\nworst DD ${-v['maxdd']/1000:.0f}k\n"
           f"days >$6k loss: {v['daily_loss_halts']}\npeak gross ${v['peak_gross']/1000:.0f}k", ha="center", fontsize=8.5, color=SEC)
a.set_xticks(range(3)); a.set_xticklabels([r[0] for r in rows], fontsize=9); a.set_ylim(0, 50)
a.set_ylabel("$k per year on the $100k (2019-01 → 2026-07)", fontsize=9, color=SEC)
a.set_title("B. Without the early years, the -30% budget allows ~2.5-3x today's size", loc="left", fontsize=11, color=INK)
st(a)
fig.suptitle("Modern regime only: engine Sharpe ~1.1; vol-targeting ~1.2; the real money is in size the early years were blocking",
             x=0.01, ha="left", fontsize=13, color=INK, fontweight="bold")
fig.text(0.01, 0.01, "Backtest, fixed $100k base, 70/30, 4.32bp/side, MTM. Size = bootstrap-safe k (P(DD>30% over 2y) <= 10%), in-sample on one bear (2022). "
         "Days >$6k loss = today's daily-loss halt; above KELLY_M 0.30 each needs a manual resume. Not a forecast.", fontsize=8, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 0.93)); fig.savefig("modern_answer.png", dpi=130, facecolor=SURF)
