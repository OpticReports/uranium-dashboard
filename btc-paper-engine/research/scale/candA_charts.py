"""CANDIDATE A charts. Palette pinned by the brief."""
import csv
import json
import os
import sys
from dataclasses import replace

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)
from app.engine.core import Bar, BookCfg                    # noqa: E402
from app.engine.replay import run_replay                    # noqa: E402
from app.indicators import atr as atr_pure                  # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURF = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK, "grid.color": GRID,
    "font.size": 10, "axes.titlesize": 11.5, "axes.titleweight": "bold",
    "axes.grid": True, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "figure.dpi": 130})

W = {"pullback": 0.75, "trend": 0.25}
SIZ = {"pullback": 2.5, "trend": 5.0}
BLEND_LEV, EQUITY = 1.5, 100_055.0
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY)
HOLDOUT = 1719792000
BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")

F = json.load(open(os.path.join(HERE, "candA_frontier.json")))
B = json.load(open(os.path.join(HERE, "candA_beta.json")))
C = json.load(open(os.path.join(HERE, "candA_counter.json")))
V = json.load(open(os.path.join(HERE, "candA_fwdvol.json")))


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def run_leg(bars, leg):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZ[leg])
    cfg = (BookCfg(name="P", sizing="fixed", strategy="pullback", leverage=1.0,
                   cap=1.0, dd_halt=0.30) if leg == "pullback" else
           BookCfg(name="T", sizing="fixed", strategy="donchian", trail_atr=5.0,
                   leverage=1.0, cap=1.0, dd_halt=0.50))
    bk = run_replay(bars, [cfg], RESEARCH_SIGNAL, tc, cash_apy=0.0).books[cfg.name]
    return [dict(exit_ts=t.exit_ts, s=tc.stop_atr * t.atr_at_entry / t.entry_price,
                 gross=(1.0 if t.side == "L" else -1.0) * (t.exit_price / t.entry_price - 1),
                 fee=t.fees_usd / t.notional) for t in bk.trades]


def build(rows, beta, cap, r0, sbar, t0=None):
    evs = []
    for leg, rr in rows.items():
        for r in rr:
            su = (r["s"] ** beta) * (sbar[leg] ** (1 - beta))
            nf = min(r0[leg] / su, cap)
            evs.append((r["exit_ts"], BLEND_LEV * W[leg] * nf * (r["gross"] - r["fee"]),
                        BLEND_LEV * W[leg] * nf))
    evs.sort(key=lambda x: x[0])
    evs = [e for e in evs if t0 is None or e[0] >= t0]
    return (np.array([e[0] for e in evs]), np.array([e[1] for e in evs]),
            np.array([e[2] for e in evs]))


bars = load_bars()
rows = {l: run_leg(bars, l) for l in ("pullback", "trend")}
sbar = {l: float(np.mean([r["s"] for r in rows[l]])) for l in rows}
r0 = dict(sbar)
usd = FuncFormatter(lambda v, _: f"${v/1000:,.0f}k" if abs(v) >= 1000 else f"${v:,.0f}")

# ===================== FIG 1: THE ANSWER ============================
fig, ax = plt.subplots(1, 3, figsize=(17.6, 5.4))
a = ax[0]
arms = [("FIXED\n(shipped)", "b0.0_c1.0", MUTED),
        ("VOL-TARGET\ncap 2.0x eq", "b1.0_c2.0", BLUE),
        ("VOL-TARGET\nuncapped", "b1.0_c99.0", ORANGE)]
x = np.arange(3)
mean_f = [B["sweep"]["full"][k]["mean_notional_at_k_max"] for _, k, _ in arms]
max_f = [B["sweep"]["full"][k]["max_notional_at_k_max"] for _, k, _ in arms]
a.bar(x - 0.19, mean_f, 0.36, color=[c for _, _, c in arms], label="MEAN notional/trade")
a.bar(x + 0.19, max_f, 0.36, color=[c for _, _, c in arms], alpha=0.42,
      hatch="///", edgecolor="white", label="MAX notional/trade")
for i, (m, mx) in enumerate(zip(mean_f, max_f)):
    a.annotate(f"${m/1000:,.0f}k\n{m/mean_f[0]:.2f}x", (i - 0.19, m), ha="center",
               va="bottom", fontsize=9, fontweight="bold", xytext=(0, 3),
               textcoords="offset points")
    a.annotate(f"${mx/1000:,.0f}k\n{mx/max_f[0]:.2f}x", (i + 0.19, mx), ha="center",
               va="bottom", fontsize=9, color=INK, xytext=(0, 3),
               textcoords="offset points")
a.set_xticks(x); a.set_xticklabels([n for n, _, _ in arms], fontsize=9)
a.yaxis.set_major_formatter(usd); a.set_ylim(0, max(max_f) * 1.30)
a.set_ylabel("gross notional per trade, at each arm's OWN k_max")
a.set_title("3.11x the CEILING buys 1.11x the SIZE\n"
            "full sample \u00b7 identical DD budget", loc="left")
a.legend(frameon=False, fontsize=8.5, loc="upper left")

a = ax[1]
mean_h = [B["sweep"]["holdout"][k]["mean_notional_at_k_max"] for _, k, _ in arms]
max_h = [B["sweep"]["holdout"][k]["max_notional_at_k_max"] for _, k, _ in arms]
a.bar(x - 0.19, mean_h, 0.36, color=[c for _, _, c in arms])
a.bar(x + 0.19, max_h, 0.36, color=[c for _, _, c in arms], alpha=0.42,
      hatch="///", edgecolor="white")
for i, (m, mx) in enumerate(zip(mean_h, max_h)):
    a.annotate(f"${m/1000:,.0f}k\n{m/mean_h[0]:.2f}x", (i - 0.19, m), ha="center",
               va="bottom", fontsize=9, fontweight="bold", xytext=(0, 3),
               textcoords="offset points")
    a.annotate(f"${mx/1000:,.0f}k\n{mx/max_h[0]:.2f}x", (i + 0.19, mx), ha="center",
               va="bottom", fontsize=9, xytext=(0, 3), textcoords="offset points")
a.set_xticks(x); a.set_xticklabels([n for n, _, _ in arms], fontsize=9)
a.yaxis.set_major_formatter(usd); a.set_ylim(0, max(max_h) * 1.30)
a.set_title("HOLDOUT: the mean gain is GONE\n"
            "1.00x deployed \u00b7 only the ceiling grows", loc="left")

a = ax[2]
for wname, col, off in (("full", BLUE, -0.16), ("holdout", ORANGE, 0.16)):
    recs = C["A1_seed"][wname]["records"]
    vals = np.array([q["ratio_unc"] for q in recs])
    a.scatter(np.full(len(vals), off) + np.random.default_rng(7).normal(0, 0.028, len(vals)),
              vals, s=34, color=col, alpha=0.85, zorder=3,
              label=f"{wname}  mean {vals.mean():.3f}")
    a.hlines(vals.mean(), off - 0.1, off + 0.1, color=INK, lw=2, zorder=4)
a.axhline(1.0, color=INK, lw=1.4, ls="--")
a.annotate("1.00 = no change in the drawdown-budget envelope", (0.0, 1.0),
           xytext=(0, 9), textcoords="offset points", fontsize=8.5, color=MUTED,
           va="bottom", ha="center")
a.set_xlim(-0.42, 0.42); a.set_xticks([])
a.set_ylabel("k_max(vol-target) / k_max(fixed)")
a.set_title("The envelope goes DOWN, not up\n"
            "16 paired bootstrap seeds", loc="left")
a.legend(frameon=False, fontsize=9, loc="lower left")
fig.tight_layout()
fig.subplots_adjust(wspace=0.30, top=0.83)
fig.savefig(os.path.join(HERE, "candA_fig1_the_answer.png"), bbox_inches="tight")
plt.close(fig)

# ===================== FIG 2: MECHANISM =============================
fig, ax = plt.subplots(1, 3, figsize=(17.6, 5.2))
a = ax[0]
bk = V["T1_vol_mean_reversion"]["H41"]["buckets"]
vals = [b["ratio_median"] for b in bk]
cols = [AQUA if v < 1 else ORANGE for v in vals]
a.bar(range(1, 6), vals, 0.62, color=cols)
a.axhline(1.0, color=INK, lw=1.5, ls="--")
for i, b in enumerate(bk):
    a.annotate(f"{b['ratio_median']:.2f}", (i + 1, b["ratio_median"]), ha="center",
               va="bottom", fontsize=9.5, fontweight="bold", xytext=(0, 2),
               textcoords="offset points")
a.set_xticks(range(1, 6))
a.set_xticklabels(["Q1\ncalmest", "Q2", "Q3", "Q4", "Q5\nwildest"], fontsize=9)
a.set_ylim(0, 1.45)
a.set_ylabel("realised vol over the next 41 bars / trailing ATR14")
a.set_title("WHY it fails: vol mean-reverts\n"
            "calm regimes run 17% HOTTER than ATR says", loc="left")
a.annotate("sizes UP here\n-> into understated risk", (0.62, 1.245),
           fontsize=8.5, color=ORANGE, ha="left")
a.annotate("sizes DOWN here\n-> out of overstated risk", (5.42, 1.16),
           fontsize=8.5, color=AQUA, ha="right")

a = ax[1]
s = np.array([r["s"] for r in rows["pullback"]]) * 100
a.hist(s, bins=34, color=BLUE, alpha=0.78, edgecolor="white", lw=0.5)
m = s.mean(); hm = 1 / (1 / s).mean()
a.axvline(m, color=ORANGE, lw=2, label=f"arithmetic mean {m:.2f}%")
a.axvline(hm, color=AQUA, lw=2, label=f"harmonic mean {hm:.2f}%")
a.set_xlabel("stop distance s = 2.5 x ATR14 / entry  (% of price)")
a.set_ylabel("trades")
mech = B["mechanism_mean_notional_bound"]["pullback"]
a.set_title("The bonus is a CV² gap, not a multiple\n"
            f"mean(s)·mean(1/s) = {mech['arith_over_harmonic']:.4f} = "
            f"1+CV² (CV={mech['cv_s']:.2f})", loc="left")
a.legend(frameon=False, fontsize=8.5)
a.annotate(f"mean notional gain IS this ratio: {mech['arith_over_harmonic']:.3f}x\n"
           "INVARIANT to stop width (A3: CV identical\n"
           "at 1.0 / 2.0 / 2.5 / 3.5 / 5.0 x ATR)",
           xy=(0.975, 0.97), xycoords="axes fraction", fontsize=8.5,
           color=INK, ha="right", va="top",
           bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=GRID))

a = ax[2]
lk = C["A3_bound_invariance"]["atr_lookback"]
a.plot([r["atr_n"] for r in lk], [r["bound_bar_level"] for r in lk], "o-",
       color=BLUE, lw=2, ms=7)
a.axhline(1.0, color=INK, lw=1.2, ls="--")
for r in lk:
    a.annotate(f"{r['bound_bar_level']:.3f}", (r["atr_n"], r["bound_bar_level"]),
               fontsize=8.5, xytext=(4, 4), textcoords="offset points")
a.axvline(14, color=ORANGE, lw=1.4, ls=":")
a.annotate("ATR14 = the registered\nstop geometry", (15.5, 1.245),
           fontsize=8.5, color=ORANGE)
a.set_xlabel("ATR lookback used for sizing (bars)")
a.set_ylabel("max mean-notional bonus = mean(s)·mean(1/s)")
a.set_ylim(1.0, 1.32)
a.set_title("The ceiling on the bonus, at any lookback\n"
            "even ATR5 gives 1.25x - never a multiple", loc="left")
fig.tight_layout()
fig.subplots_adjust(wspace=0.30, top=0.83)
fig.savefig(os.path.join(HERE, "candA_fig2_mechanism.png"), bbox_inches="tight")
plt.close(fig)

# ===================== FIG 3: BETA SWEEP ============================
fig, ax = plt.subplots(1, 3, figsize=(17.6, 5.2))
betas = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
a = ax[0]
for wname, col in (("full", BLUE), ("holdout", ORANGE)):
    y = [B["sweep"][wname][f"b{b}_c99.0"]["vs_FIXED"]["k_max_ratio"] for b in betas]
    a.plot(betas, y, "o-", color=col, lw=2.2, ms=6, label=wname)
a.axhline(1.0, color=INK, lw=1.3, ls="--")
a.fill_between([0, 1], 0.86, 1.0, color=ORANGE, alpha=0.06)
a.set_xlabel("beta   (0 = shipped fixed sizing,  1 = full vol-targeting)")
a.set_ylabel("k_max ratio vs fixed sizing")
a.set_title("Partial vol-targeting does not rescue it\n"
            "holdout degrades MONOTONICALLY in beta", loc="left", pad=14)
a.legend(frameon=False, fontsize=9)
a.annotate("best full-sample gain anywhere: +1.7%", (0.375, 1.017),
           fontsize=8.5, color=BLUE, xytext=(0.30, 0.955), textcoords="data",
           ha="left", arrowprops=dict(arrowstyle="->", color=BLUE, lw=1),
           bbox=dict(boxstyle="round,pad=0.35", fc=SURF, ec=GRID))
a.annotate("-11.5% at beta=1", (0.83, 0.887), fontsize=8.5, color=ORANGE, ha="right")

a = ax[1]
for wname, col in (("full", BLUE), ("holdout", ORANGE)):
    y = [B["sweep"][wname][f"b{b}_c99.0"]["vs_FIXED"]["sharpe_ratio"] for b in betas]
    a.plot(betas, y, "o-", color=col, lw=2.2, ms=6, label=wname)
a.axhline(1.0, color=INK, lw=1.3, ls="--")
a5 = C["A5_sharpe_paired"]
a.set_xlabel("beta")
a.set_ylabel("per-step Sharpe ratio vs fixed sizing")
a.set_title("...and the Sharpe change is not real\n"
            f"paired 90% CI at beta=1 (full): "
            f"[{a5['full']['diff_ci5']:+.3f}, {a5['full']['diff_ci95']:+.3f}]",
            loc="left")
a.legend(frameon=False, fontsize=9)

a = ax[2]
mean_r = [B["sweep"]["full"][f"b{b}_c99.0"]["vs_FIXED"]["mean_notional_ratio"] for b in betas]
max_r = [B["sweep"]["full"][f"b{b}_c99.0"]["vs_FIXED"]["max_notional_ratio"] for b in betas]
a.plot(betas, max_r, "o-", color=ORANGE, lw=2.2, ms=6, label="MAX notional (the rail demand)")
a.plot(betas, mean_r, "o-", color=BLUE, lw=2.2, ms=6, label="MEAN notional (what you deploy)")
a.axhline(1.0, color=INK, lw=1.3, ls="--")
a.fill_between(betas, mean_r, max_r, color=MUTED, alpha=0.13)
a.annotate("pure rail cost:\nraise the ceiling 3.1x\nto deploy 1.11x",
           (0.06, 2.45), fontsize=9, color=INK,
           bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=GRID))
a.set_xlabel("beta"); a.set_ylabel("ratio vs fixed sizing, full sample")
a.set_title("Rail demand vs delivery\n"
            "the wedge IS the problem", loc="left")
a.legend(frameon=False, fontsize=8.5, loc="upper left")
fig.tight_layout()
fig.subplots_adjust(wspace=0.30, top=0.83)
fig.savefig(os.path.join(HERE, "candA_fig3_beta.png"), bbox_inches="tight")
plt.close(fig)

# ============== FIG 4: EQUITY / DD / WHAT IT DOES BUY ================
fig, ax = plt.subplots(1, 3, figsize=(17.6, 5.2))
tsF, stF, ntF = build(rows, 0.0, 1.0, r0, sbar)
tsV, stV, ntV = build(rows, 1.0, 99.0, r0, sbar)
kmF = B["sweep"]["full"]["b0.0_c1.0"]["k_max"]
kmV = B["sweep"]["full"]["b1.0_c99.0"]["k_max"]
dtF = np.array(tsF, dtype="datetime64[s]")
a = ax[0]
for st, k, col, lab in ((stF, kmF, MUTED, f"FIXED at its k_max {kmF:.3f}"),
                        (stV, kmV, ORANGE, f"VOL-TARGET at its k_max {kmV:.3f}")):
    nav = np.cumprod(1 + k * st)
    a.plot(dtF, nav, color=col, lw=2.0, label=lab)
a.plot(dtF, np.cumprod(1 + K_LIVE * stF), color=BLUE, lw=1.6, ls="--",
       label=f"FIXED at TODAY's live k {K_LIVE:.4f}")
a.axvline(np.datetime64(HOLDOUT, "s"), color=INK, lw=1.2, ls=":")
a.annotate("holdout starts", (np.datetime64(HOLDOUT, "s"), 1.06), fontsize=8.5,
           color=INK, rotation=90, va="bottom")
a.set_yscale("log"); a.set_ylabel("blend NAV (x), log scale")
a.set_title("At its OWN drawdown budget: +20% CAGR\n"
            "22.2% -> 26.6% IN SAMPLE; holdout gives it back", loc="left")
a.legend(frameon=False, fontsize=8.5, loc="upper left")
a.tick_params(axis="x", labelsize=8.5, rotation=30)

a = ax[1]
for st, k, col, lab in ((stF, kmF, MUTED, "FIXED at k_max"),
                        (stV, kmV, ORANGE, "VOL-TARGET at k_max")):
    nav = np.cumprod(1 + k * st)
    dd = 100 * (nav / np.maximum.accumulate(nav) - 1)
    a.fill_between(dtF, dd, 0, color=col, alpha=0.40, label=f"{lab}  min {dd.min():.1f}%")
a.axhline(-30, color=ORANGE, lw=1.3, ls="--")
a.annotate("30% DD budget both arms were sized to", (dtF[3], -29.4),
           fontsize=8.5, color=ORANGE, va="bottom")
a.set_ylabel("drawdown, % (trade-close basis)")
a.set_ylim(-33, 1)
a.set_title("Drawdown is matched by construction\n"
            "the budget IS the constraint", loc="left")
a.legend(frameon=False, fontsize=8.5, loc="center left")
a.tick_params(axis="x", labelsize=8.5, rotation=30)

a = ax[2]
t2 = V["T2_risk_equalisation"]["pullback"]
lf = t2["realised_loss_frac_losers"]["FIXED"]
lv = t2["realised_loss_frac_losers"]["VT_uncapped"]
labels = ["mean", "p90", "p95", "max"]
fv = [lf["mean"] * 100, lf["p90"] * 100, lf["p95"] * 100, lf["max"] * 100]
vv = [lv["mean"] * 100, lv["p90"] * 100, lv["p95"] * 100, lv["max"] * 100]
xx = np.arange(4)
a.bar(xx - 0.19, fv, 0.36, color=MUTED, label="FIXED")
a.bar(xx + 0.19, vv, 0.36, color=AQUA, label="VOL-TARGET")
for i, (p, q) in enumerate(zip(fv, vv)):
    a.annotate(f"{p:.2f}", (i - 0.19, p), ha="center", va="bottom", fontsize=8.5,
               xytext=(0, 2), textcoords="offset points")
    a.annotate(f"{q:.2f}", (i + 0.19, q), ha="center", va="bottom", fontsize=8.5,
               color=INK, fontweight="bold", xytext=(0, 2), textcoords="offset points")
a.set_xticks(xx); a.set_xticklabels(labels)
a.set_ylabel("realised loss on a losing trade, % of equity")
a.set_ylim(0, max(fv + vv) * 1.22)
a.set_title("The ONE thing it buys: loss CONSISTENCY\n"
            f"CV {t2['cv_of_realised_loss']['FIXED']:.2f} -> "
            f"{t2['cv_of_realised_loss']['VT_uncapped']:.2f}  \u00b7  p95 "
            f"x{t2['p95_loss_ratio_vt_over_fixed']['VT_uncapped']:.2f}", loc="left")
a.legend(frameon=False, fontsize=9)
fig.tight_layout()
fig.subplots_adjust(wspace=0.30, top=0.83)
fig.savefig(os.path.join(HERE, "candA_fig4_what_it_buys.png"), bbox_inches="tight")
plt.close(fig)
print("wrote 4 figures")
