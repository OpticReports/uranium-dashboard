"""RESEARCH_SHARPE.md figure + the numbers it quotes. python3 figures.py
-> sharpe_answer.png, figures.json. Includes ONE diagnostic, unregistered
variant (H1 down-only, m capped at 1.0) that counter-agent A ran first; it is
labelled as such everywhere."""
import csv, json, os, sys, datetime as dt
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sharpe_lib as S, run as R                                    # noqa: E402

W = S.World()
FULL = ("2013-01-01", R.END)
out = {}

def curve(spec, a, b, m_hi=None):
    old = S.M_HI
    if m_hi is not None: S.M_HI = m_hi
    try: return R.account(W, spec, a, b)
    finally: S.M_HI = old

base = curve(set(), *FULL); h1 = curve({"vol"}, *FULL); h1d = curve({"vol"}, *FULL, m_hi=1.0)
h2 = curve({"gate"}, *FULL)
for n, x in {"baseline": base, "H1": h1, "H1 down-only (diag)": h1d, "H2": h2}.items():
    lo, hi = S.boot_delta(base["d"], x["d"]) if n != "baseline" else (0, 0)
    out[n] = dict(sharpe=x["sharpe"], per_yr=x["per_yr"], maxdd=x["maxdd"], boot90=(lo, hi))
# per-era, 2019+ for the down-only diagnostic
out["H1 down-only eras"] = {}
for en, (a, b) in list(R.ERAS.items())[:6]:
    y = curve(set(), a, b); z = curve({"vol"}, a, b, m_hi=1.0)
    out["H1 down-only eras"][en] = z["sharpe"] - y["sharpe"]
for st in ("2019-01-01",):
    y, z, z1 = curve(set(), st, R.END), curve({"vol"}, st, R.END, m_hi=1.0), curve({"vol"}, st, R.END)
    out[f"from {st[:4]}"] = dict(base=y["sharpe"], h1d=z["sharpe"], h1=z1["sharpe"],
                                base_dd=y["maxdd"], h1d_dd=z["maxdd"], base_yr=y["per_yr"], h1d_yr=z["per_yr"],
                                h1d_ci=S.boot_delta(y["d"], z["d"]))
# H2 delta $ by calendar year
yrs = sorted(set(dt.datetime.utcfromtimestamp(int(d) * 86400).year for d in base["days"]))
def by_year(x):
    yy = np.array([dt.datetime.utcfromtimestamp(int(d) * 86400).year for d in x["days"]])
    return {y: float(x["d"][yy == y].sum()) for y in yrs}
bb, b2 = by_year(base), by_year(h2)
out["H2 delta by year"] = {y: b2[y] - bb[y] for y in yrs}
# carry sleeve net $ by year vs T-bill on $30k
c = R.account(W, {"carry_s"}, "2016-06-01", R.END)
rows = [r for r in csv.reader(open(os.path.join(HERE, "data", "dtb3.csv")))][1:]
tb = {}
for d, v in rows:
    if v not in ("", "."): tb.setdefault(int(d[:4]), []).append(float(v))
cy = np.array([dt.datetime.utcfromtimestamp(int(d) * 86400).year for d in c["days"]])
car, cash = {}, {}
for y in range(2016, 2027):
    m = cy == y
    car[y] = float(c["d_car"][m].sum())
    cash[y] = float(np.mean(tb[y]) / 100 * 30_000 * m.sum() / 365)
out["carry by year"] = car; out["tbill on 30k by year"] = cash
json.dump(out, open(os.path.join(HERE, "figures.json"), "w"), indent=1, default=float)

# ---------------------------------------------------------------- figure
BLUE, ORANGE, AQUA, RED, INK, SEC, MUTED, GRID, AX, SURF = ("#2a78d6", "#eb6834", "#1baf7a", "#e34948",
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb")
fig, ax = plt.subplots(2, 2, figsize=(16, 10)); fig.patch.set_facecolor(SURF)
def style(a):
    a.set_facecolor(SURF); [a.spines[s].set_visible(False) for s in ("top", "right")]
    [a.spines[s].set_color(AX) for s in ("left", "bottom")]; a.tick_params(colors=SEC, labelsize=9)
    a.yaxis.grid(True, color=GRID, zorder=0)
dd = lambda x: [dt.datetime.utcfromtimestamp(int(d) * 86400) for d in x["days"]]
# A cumulative $
a = ax[0, 0]
for x, col, lw, lab in [(base, MUTED, 1.6, f"live engine today  (Sharpe {base['sharpe']:.2f})"),
                        (h1, BLUE, 1.4, f"H1 vol-target, registered  ({h1['sharpe']:.2f}; breaches \\$60k rail)"),
                        (h1d, AQUA, 2.2, f"H1 down-only, diagnostic  ({h1d['sharpe']:.2f}; fits every rail)")]:
    a.plot(dd(x), np.cumsum(x["d"]) / 1000, color=col, lw=lw, label=lab)
a.set_ylabel(r"cumulative \$k on the \$100k (fixed base, KELLY_M 0.30)", fontsize=9, color=SEC)
a.set_title("A. Vol-targeting: same money, smoother path", loc="left", fontsize=11, color=INK)
a.legend(frameon=False, fontsize=8.5, loc="upper left"); style(a)
# B drawdown $
a = ax[0, 1]
for x, col, lw, lab in [(base, MUTED, 1.4, "live engine today"), (h1d, AQUA, 2.0, "H1 down-only (diagnostic)")]:
    cum = np.cumsum(x["d"]); a.fill_between(dd(x), (cum - np.maximum.accumulate(np.maximum(cum, 0))) / 1000, 0,
                                            color=col, alpha=.35 if col == MUTED else .55, lw=0, label=lab)
a.axhline(-30, color=RED, lw=1, ls="--"); a.text(dd(base)[60], -29, r"Casey's -30% budget (\$30k)", fontsize=8, color=RED)
a.set_ylabel(r"drawdown, \$k", fontsize=9, color=SEC); a.set_ylim(-37, 1)
a.set_title(f"B. Drawdown: worst \\${-base['maxdd']/1000:.0f}k today vs \\${-h1d['maxdd']/1000:.0f}k vol-targeted (down-only)", loc="left", fontsize=11, color=INK)
a.legend(frameon=False, fontsize=8.5, loc="lower right"); style(a)
# C H2 by year
a = ax[1, 0]; v = [out["H2 delta by year"][y] / 1000 for y in yrs]
a.bar(yrs, v, color=[BLUE if y < 2019 else ORANGE for y in yrs], width=0.7, zorder=3)
a.axhline(0, color=AX, lw=1); a.axvline(2018.5, color=SEC, lw=1, ls=":")
a.text(2015.5, max(v) * .92, "years I knew the pullback\nlost money BEFORE registering", ha="center", fontsize=8.5, color=SEC)
a.text(2022.5, max(v) * .92, "since 2019: no gain\n(dSharpe +0.01, CI -0.23..+0.21)", ha="center", fontsize=8.5, color=SEC)
a.set_ylabel(r"200-day gate minus live, \$k per year", fontsize=9, color=SEC)
a.set_title("C. H2 200-day gate: all of its gain is hindsight — REJECTED", loc="left", fontsize=11, color=INK); style(a)
# D carry vs cash
a = ax[1, 1]; ys = list(range(2016, 2027)); w = 0.38
a.bar(np.array(ys) - w / 2, [car[y] / 1000 for y in ys], w, color=BLUE, label=r"carry sleeve on \$30k (BitMEX funding, net of fees)", zorder=3)
a.bar(np.array(ys) + w / 2, [cash[y] / 1000 for y in ys], w, color=MUTED, label=r"same \$30k in 3-mo T-bills", zorder=3)
a.axhline(0, color=AX, lw=1); a.legend(frameon=False, fontsize=8.5, loc="upper right")
a.set_ylabel(r"\$k per year", fontsize=9, color=SEC)
a.set_title("D. Carry sleeve: big in 2016-17, roughly cash since — PARKED", loc="left", fontsize=11, color=INK); style(a)
fig.suptitle("Better Sharpe for the $100k: one real lever — size down when BTC volatility is high", x=0.01, ha="left", fontsize=14, color=INK, fontweight="bold")
fig.text(0.01, 0.005, "Backtest 2013-01..2026-07, fixed $100k base (how live sizes), KELLY_M 0.30, 70/30, 4.32bp/side, Bitstamp 4h, MTM, daily Sharpe x sqrt(365), rf 0. "
         "In-sample; DSR ~0.01 vs ~2,546 trials. Not a forecast.", fontsize=8, color=MUTED)
fig.tight_layout(rect=(0, 0.02, 1, 0.95)); fig.savefig(os.path.join(HERE, "sharpe_answer.png"), dpi=130, facecolor=SURF)
print(json.dumps({k: v for k, v in out.items() if "year" not in k}, indent=1, default=float))
