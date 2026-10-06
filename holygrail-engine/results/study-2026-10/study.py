"""Dalio Holy Grail study, 2026-10 (evidence section of Casey's report).

Run:  cd holygrail-engine && python results/study-2026-10/study.py
Parameters are frozen in predeclared_params.json (declared before any result).
Everything goes through the holygrail public API; the few local helpers are
marked FRICTION where the engine lacked a hook.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib
import matplotlib.dates
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from holygrail import report  # noqa: E402
from holygrail.allocate import erc, quadrant_balance, target_vol_gearing  # noqa: E402
from holygrail.backtest import BacktestConfig, run_backtest  # noqa: E402
from holygrail.core import dalio_table, effective_bets, mean_pairwise_correlation, cov_to_corr  # noqa: E402
from holygrail.data import DataLoader, tbill_period_returns  # noqa: E402
from holygrail.environments import BOXES, exposures_from_mapping, environment_balance  # noqa: E402
from holygrail.estimate import align_levels, levels_to_returns, sample_cov  # noqa: E402
from holygrail.forward import SimConfig, run_forward, stress_correlation  # noqa: E402
from holygrail.metrics import performance_metrics, max_drawdown  # noqa: E402
from holygrail.robustness import bootstrap_neff_sharpe, rolling_correlation, stress_mask  # noqa: E402

OUT = Path(__file__).resolve().parent
P = json.loads((OUT / "predeclared_params.json").read_text())
END = "2026-09-30"          # last complete month (FRICTION: no 'complete periods only' switch)
SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
UNIV = ["VFINX", "VGTSX", "VEIEX", "VUSTX", "VFITX", "VIPSX", "VWESX", "VWEHX", "VGSIX", "GLD", "PCRIX"]
LABEL = {"VFINX": "US eq", "VGTSX": "Intl eq", "VEIEX": "EM eq", "VUSTX": "Long UST", "VFITX": "Interm UST",
         "VIPSX": "TIPS", "VWESX": "IG credit", "VWEHX": "HY", "VGSIX": "REITs", "GLD": "Gold", "PCRIX": "Commod"}
COST, SPREAD, CAP, TV, WIN = 10.0, 0.005, 3.0, 0.10, 36
loader = DataLoader()
M = {"params": P, "sections": {}}
prov = {}


def monthly(tickers, start=None):
    lv = {}
    for t in tickers:
        ds = loader.yahoo(t)
        lv[t] = ds.values
        prov[t] = ds.provenance.to_dict()
    lv = pd.DataFrame(lv).sort_index().loc[:END]
    r = levels_to_returns(align_levels(lv, "M"))
    return r if start is None else r.loc[start:]


def rf_for(index):
    d = loader.fred("DTB3")
    prov["DTB3"] = d.provenance.to_dict()
    return tbill_period_returns(d.values, index)


def fig_save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=150, facecolor=SURF)
    plt.close(fig)
    return str(OUT / f"{name}.png")


def rows_out(df, name):
    return report.write_rows(df, OUT / name)["csv"]


CHARTS = []


def chart(png, csv, caption):
    CHARTS.append({"png": png, "rows_csv": csv, "caption": caption})


# =========================================================================== S1
s1 = {}
r = report.dalio_curve(OUT, n_max=30)
chart(r["png"], r["csv"], "S1 Dalio curve: portfolio vol vs N equal 18%-vol bets for rho in {0,.1,.2,.3,.4,.6} (closed form)")
r = report.neff_vs_rho(OUT, ns=(15,))
chart(r["png"], r["csv"], "S1 N_eff = N/(1+(N-1)rho) vs rho for N=15 (closed form)")
tab = dalio_table(0.18, 0.06, (1, 5, 10, 15), (0.0, 0.1, 0.2, 0.3, 0.4, 0.6))
pd.DataFrame(tab).to_csv(OUT / "s1_dalio_table.csv", index=False)
s1["table"] = tab
s1["dalio_check_rho0"] = {str(t["n"]): t["sigma_p"] for t in tab if t["rho"] == 0}
s1["exact_improvement_15"] = math.sqrt(15)
M["sections"]["S1"] = s1

# =========================================================================== data
R = monthly(UNIV).dropna(how="any")
assert R.index[0] == pd.Timestamp("2004-12-31") and R.index[-1] == pd.Timestamp(END), (R.index[0], R.index[-1])
rf = rf_for(R.index)
T = len(R)
M["common_window"] = {"first_return_month": str(R.index[0].date()), "last": str(R.index[-1].date()), "months": T}
EXPO, unm = exposures_from_mapping(UNIV, {k: tuple(v) for k, v in P["quadrant_mapping"].items() if k != "basis"})
assert not unm

# =========================================================================== S2
s2 = {}
S_full = sample_cov(R) * 12
C = R.corr()
cr = C.rename(index=LABEL, columns=LABEL)
long = cr.stack().reset_index()
long.columns = ["a", "b", "rho"]
csv = rows_out(long, "s2_corr_matrix")
fig, ax = plt.subplots(figsize=(7.2, 6))
im = ax.imshow(cr.to_numpy(), cmap=report.DIVERGING, vmin=-1, vmax=1)
ax.set_xticks(range(len(cr)), cr.columns, rotation=45, ha="right", fontsize=8, color=INK2)
ax.set_yticks(range(len(cr)), cr.index, fontsize=8, color=INK2)
for i in range(len(cr)):
    for j in range(len(cr)):
        v = cr.iat[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.5, color=INK if abs(v) < 0.7 else "#ffffff")
ax.set_title(f"Monthly return correlations, {R.index[0]:%Y-%m}..{R.index[-1]:%Y-%m} (n={T})", loc="left", fontsize=11, color=INK)
for s in ax.spines.values():
    s.set_visible(False)
fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02).ax.tick_params(labelsize=7, colors=INK2)
chart(fig_save(fig, "s2_corr_matrix"), csv, "S2 correlation matrix of the 11-asset universe, common window, monthly total returns")
s2["mean_pairwise_rho_full"] = mean_pairwise_correlation(C.to_numpy())

w_full = erc(S_full)
eb_full = effective_bets(w_full, S_full, n_obs=T)
# stress mask: VFINX month-end level > 10% below its running peak since 1980
vf = monthly(["VFINX"])
lvl = (1 + vf["VFINX"]).cumprod()
mask_all = stress_mask(lvl, dd_window=len(lvl), dd_threshold=0.10)
mask = mask_all.reindex(R.index).astype(bool)
s2["stress_rule"] = P["stress_rule"]
s2["n_stress_months"], s2["n_calm_months"] = int(mask.sum()), int((~mask).sum())
s2["stress_months"] = [str(d.date()) for d in R.index[mask.to_numpy()]]


def eb_row(label, w, S, n):
    eb = effective_bets(w, S, n_obs=n)
    return {"sample": label, "n_months": n, "rho_bar": eb.rho_bar, "dr2": eb.dr2, "equal_rho": eb.equal_rho,
            "pca_entropy": eb.pca_entropy, "prc_inverse_hhi": eb.prc_inverse_hhi, "min_torsion": eb.min_torsion,
            "dr": eb.dr, "vol": float(math.sqrt(w @ S @ w)), "pca_ambiguous": eb.pca_basis_ambiguous,
            "min_torsion_regularized": eb.min_torsion_regularized}


reg_rows = [eb_row("full sample (ERC on full S)", w_full, S_full, T)]
for lab, sel in (("calm", ~mask), ("stress", mask)):
    Sr = sample_cov(R[sel.to_numpy()]) * 12
    reg_rows.append(eb_row(f"{lab} (ERC re-solved on {lab} S)", erc(Sr), Sr, int(sel.sum())))
    reg_rows.append(eb_row(f"{lab} (full-sample ERC weights held)", w_full, Sr, int(sel.sum())))
rg = pd.DataFrame(reg_rows)
csv = rows_out(rg, "s2_neff_regimes")
s2["neff_regimes"] = reg_rows
s2["erc_weights_full"] = dict(zip(UNIV, w_full.tolist()))
boot = bootstrap_neff_sharpe(R, w_full, periods_per_year=12, n_boot=1000, mean_block=12, seed=20261006)
s2["neff_bootstrap_90ci"] = {k: boot[k] for k in ("dr2", "equal_rho", "pca_entropy", "prc_inverse_hhi", "min_torsion")}
pick = [0, 3, 4]  # full, stress re-solved, stress held
meas = [("dr2", "DR^2 (headline)"), ("equal_rho", "equal-rho (a)"), ("pca_entropy", "PCA entropy (c)"),
        ("prc_inverse_hhi", "1/sum PRC^2 (b)"), ("min_torsion", "min torsion (d)")]
fig, ax = plt.subplots(figsize=(8, 4.2))
x = np.arange(len(meas))
bw = 0.26
labs = ["full sample", "calm months", "stress months"]
for j, (ri, lab) in enumerate(zip([0, 1, 3], labs)):
    vals = [rg.iloc[ri][m] for m, _ in meas]
    ax.bar(x + (j - 1) * bw, vals, bw - 0.02, color=SER[j], label=lab + " (ERC re-solved)" if j else lab)
    for xi, v in zip(x, vals):
        ax.text(xi + (j - 1) * bw, v + 0.15, f"{v:.1f}", ha="center", fontsize=7, color=INK2)
ax.axhline(11, color=INK2, lw=0.8, ls="--")
ax.text(len(meas) - 0.5, 11.2, "N = 11 funds", fontsize=7, color=INK2, ha="right")
ax.set_xticks(x, [b for _, b in meas], fontsize=8)
report._style(ax, "Effective bets in the ERC portfolio: full vs calm vs stress months", "", "N_eff")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2)
chart(fig_save(fig, "s2_neff_regimes"), csv, "S2 N_eff (all five measures) of the ERC portfolio, full sample vs calm vs stress months (stress = US equity >10% below running peak)")

# rolling 36m, ERC re-solved each window (FRICTION: robustness.rolling_neff holds weights fixed)
roll = []
X = R.to_numpy()
for k in range(WIN, T + 1):
    S = sample_cov(X[k - WIN:k]) * 12
    w = erc(S)
    eb = effective_bets(w, S, n_obs=WIN)
    roll.append({"date": R.index[k - 1].strftime("%Y-%m-%d"), "dr2": eb.dr2, "equal_rho": eb.equal_rho,
                 "pca_entropy": eb.pca_entropy, "min_torsion": eb.min_torsion, "rho_bar": eb.rho_bar,
                 "erc_vol": float(math.sqrt(w @ S @ w)), "stress_month": bool(mask.iloc[k - 1])})
rl = pd.DataFrame(roll)
csv = rows_out(rl, "s2_rolling_neff")
d = pd.to_datetime(rl["date"])
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.5, 5.4), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
for i, (m, lab) in enumerate([("dr2", "DR^2 (headline)"), ("equal_rho", "equal-rho (a)"), ("pca_entropy", "PCA entropy (c)")]):
    a1.plot(d, rl[m], color=SER[i], lw=2 if i == 0 else 1.4, label=lab)
a2.plot(d, rl["rho_bar"], color=SER[3], lw=1.8, label="mean pairwise rho")
for a in (a1, a2):
    for s_, e_ in [("2007-11-01", "2009-03-31"), ("2020-02-01", "2020-04-30"), ("2022-01-01", "2022-10-31")]:
        a.axvspan(pd.Timestamp(s_), pd.Timestamp(e_), color=GRID, alpha=0.7, lw=0)
report._style(a1, "Rolling 36-month effective bets of the ERC portfolio (weights re-solved each window)", "", "N_eff")
report._style(a2, "", "window end (shaded: 2008, 2020, 2022 sell-offs)", "mean rho")
a1.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper left", ncol=3)
chart(fig_save(fig, "s2_rolling_neff"), csv, "S2 rolling 36m N_eff and mean pairwise correlation of the ERC portfolio, 2007-2026")
s2["rolling_summary"] = {
    "dr2_min": {"value": float(rl.dr2.min()), "date": rl.loc[rl.dr2.idxmin(), "date"]},
    "dr2_max": {"value": float(rl.dr2.max()), "date": rl.loc[rl.dr2.idxmax(), "date"]},
    "dr2_median": float(rl.dr2.median()),
    "at": {dt: rl.set_index("date").loc[dt, ["dr2", "rho_bar"]].to_dict()
           for dt in ["2008-12-31", "2009-02-27", "2020-03-31", "2020-12-31", "2022-09-30", "2022-12-30", "2026-09-30"]
           if dt in set(rl.date)},
}
M["sections"]["S2"] = s2

# =========================================================================== S3
iv = UNIV.index("VFINX")
onehot = np.zeros(len(UNIV)); onehot[iv] = 1.0
w6040 = np.zeros(len(UNIV)); w6040[iv] = 0.6; w6040[UNIV.index("VFITX")] = 0.4


def us_eq(S): return onehot
def sixty40(S): return w6040
def quad(S): return quadrant_balance(S, EXPO, BOXES).weights
def erc_eq_vol(S, win):
    w = erc(S)
    return w * math.sqrt(S[iv, iv]) / math.sqrt(w @ S @ w)


us_eq.__name__, sixty40.__name__, quad.__name__, erc_eq_vol.__name__ = "us_equity", "60_40", "quadrant", "erc_equity_vol"
STRATS = [
    ("1 US equity", dict(allocator=us_eq)),
    ("2 60/40", dict(allocator=sixty40)),
    ("3 Equal weight", dict(allocator="equal_weight")),
    ("4 ERC unlevered", dict(allocator="erc")),
    ("5 ERC @10% vol", dict(allocator="erc", target_vol=TV)),
    ("6 Quadrant @10% vol", dict(allocator=quad, target_vol=TV)),
    ("7 ERC @ equity vol", dict(allocator=erc_eq_vol)),
]


def bt(Rx, rfx, **kw):
    cfg = BacktestConfig(window=WIN, rebalance="M", cost_bps=COST, financing_spread=SPREAD, max_leverage=CAP,
                         periods_per_year=12, **kw)
    return run_backtest(Rx, cfg, rf=rfx)


res = {name: bt(R, rf, **kw) for name, kw in STRATS}
start = res["1 US equity"].equity.index[0]
for k, v in res.items():
    assert v.equity.index[0] == start
bench = res["1 US equity"].returns
mt = []
for name, b in res.items():
    m = b.metrics
    cmp = None
    if name != "1 US equity":
        from holygrail.metrics import benchmark_comparison
        cmp = benchmark_comparison(b.returns, bench, periods_per_year=12, rf=rf.loc[b.returns.index])
    tgt = b.targets
    gross_t = tgt.abs().sum(axis=1)
    mt.append({"strategy": name, "cagr": m["cagr"], "vol": m["vol"], "sharpe": m["sharpe"], "sortino": m["sortino"],
               "max_dd": m["max_drawdown"], "calmar": m["calmar"], "worst_year": m["worst_year"],
               "p_loss_year": m["p_loss_year"], "ulcer": m["ulcer_index"], "max_days_under_water": m["max_days_under_water"],
               "avg_gross": float(b.leverage.mean()), "max_gross": float(b.leverage.max()),
               "cap_binding_share": float((gross_t >= CAP - 1e-9).mean()),
               "turnover_per_year": float(b.turnover.iloc[1:].sum() / m["years"]),
               "cost_drag_per_year": float(b.costs.sum() / m["years"]),
               "beta_to_us_eq": cmp["beta"] if cmp else 1.0, "corr_to_us_eq": cmp["correlation"] if cmp else 1.0,
               "start": m["start"], "end": m["end"], "years": m["years"]})
mt_df = pd.DataFrame(mt)
mt_df.to_csv(OUT / "s3_metrics.csv", index=False)
curves = {n: b.equity for n, b in res.items()}
r = report.equity_curves(OUT, curves, name="s3_equity",
                         title=f"Walk-forward equity, {start:%Y-%m}..{R.index[-1]:%Y-%m} (log, month-end MTM, net of costs/financing)")
chart(r["png"], r["csv"], "S3 equity curves (log) of the seven walk-forward strategies")
r = report.drawdowns(OUT, {k: curves[k] for k in ["1 US equity", "2 60/40", "5 ERC @10% vol", "6 Quadrant @10% vol", "7 ERC @ equity vol"]},
                     name="s3_drawdown")
chart(r["png"], r["csv"], "S3 drawdowns from prior peak (month-end marks) for US equity, 60/40 and the geared strategies")

# worst windows
WINDOWS = {"GFC 2007-11..2009-02": ("2007-11-30", "2009-02-27"), "Covid 2020-01..2020-03": ("2020-01-31", "2020-03-31"),
           "2022 (Dec-21..Sep-22)": ("2021-12-31", "2022-09-30"), "Calendar 2022": ("2021-12-31", "2022-12-30")}
ww = []
for name, b in res.items():
    e = b.equity
    row = {"strategy": name}
    for wl, (s_, e_) in WINDOWS.items():
        row[wl] = float(e.asof(pd.Timestamp(e_)) / e.asof(pd.Timestamp(s_)) - 1)
    r12 = (1 + b.returns).rolling(12).apply(np.prod, raw=True) - 1
    row["worst_12m"] = float(r12.min()); row["worst_12m_end"] = str(r12.idxmin().date())
    ww.append(row)
ww_df = pd.DataFrame(ww)
csv = rows_out(ww_df, "s3_worst_windows")
fig, ax = plt.subplots(figsize=(8.5, 4.4))
wls = list(WINDOWS)[:1] + ["2022 (Dec-21..Sep-22)", "worst_12m"]
x = np.arange(len(res))
bw = 0.27
for j, wl in enumerate(wls):
    vals = 100 * ww_df[wl].to_numpy()
    ax.bar(x + (j - 1) * bw, vals, bw - 0.02, color=SER[j], label=wl.replace("worst_12m", "worst rolling 12m"))
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x, [n.split(" ", 1)[1] for n in res], fontsize=7.5, rotation=15)
report._style(ax, "Worst windows: cumulative return (%)", "", "return (%)")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3)
chart(fig_save(fig, "s3_worst_windows"), csv, "S3 worst windows: GFC, 2022 and worst rolling 12 months per strategy")

# leverage paths
lev = pd.DataFrame({n: res[n].leverage for n in ["5 ERC @10% vol", "6 Quadrant @10% vol", "7 ERC @ equity vol"]})
lev.index.name = "date"
csv = rows_out(lev.reset_index().assign(date=lambda z: z.date.dt.strftime("%Y-%m-%d")), "s3_leverage")
fig, ax = plt.subplots(figsize=(8, 3.6))
for i, c in enumerate(lev.columns):
    ax.plot(lev.index, lev[c], color=SER[4 + i], lw=1.8, label=c)
ax.axhline(CAP, color=INK2, lw=0.8, ls="--"); ax.text(lev.index[3], CAP + 0.05, "3x cap", fontsize=7, color=INK2)
ax.axhline(1, color=INK2, lw=0.8)
report._style(ax, "Gross exposure of the geared strategies (month-end, after drift)", "", "gross exposure (x NAV)")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="upper left")
chart(fig_save(fig, "s3_leverage"), csv, "S3 gross leverage over time of the geared strategies (5,6,7) vs the 3x cap")

# quadrant box risk shares (check the allocator delivered 25% per box at each date)
qt = res["6 Quadrant @10% vol"].targets
box_check = []
for dt in qt.index:
    win = R.loc[:dt].iloc[-WIN:]
    S = sample_cov(win) * 12
    eb = environment_balance(qt.loc[dt].to_numpy(), S, EXPO)
    box_check.append(max(abs(v - 0.25) for v in eb["risk_share_of_mapped"].values()))
s3 = {"metrics": mt, "worst_windows": ww, "first_trade": str(start.date()),
      "quadrant_max_box_deviation_from_25pct": float(max(box_check)),
      "realised_vs_target_vol": {n: res[n].metrics["vol"] for n in ["5 ERC @10% vol", "6 Quadrant @10% vol"]},
      "ex_ante_vol_7_mean": float(res["7 ERC @ equity vol"].ex_ante_vol.mean()),
      "latest_targets": {n: dict(zip(UNIV, res[n].targets.iloc[-1].round(4).tolist())) for n in ["4 ERC unlevered", "5 ERC @10% vol", "6 Quadrant @10% vol"]},
      "latest_target_date": str(res["5 ERC @10% vol"].targets.index[-1].date())}

# DIAGNOSTIC (not a strategy): split gearing into constant leverage vs vol timing.
# r_geared ~= rf + L_{t-1} (r_erc - rf) - max(L-1,0) spread; the counterfactual holds L at its
# realised MEAN (known only ex post: hindsight) to isolate what the 36m vol-timing cost.
diag = []
for gname, uname in (("5 ERC @10% vol", "4 ERC unlevered"), ("6 Quadrant @10% vol", None)):
    g = res[gname]
    if uname is None:   # unlevered quadrant = same allocator, no target
        u = bt(R, rf, allocator=quad)
    else:
        u = res[uname]
    Lt = g.targets.abs().sum(axis=1) / u.targets.abs().sum(axis=1)
    # leverage earning the return dated t = the target set at the previous label (verify/study fix:
    # the final date is never a rebalance, so a positional shift misfilled the last month)
    _ix = Lt.index.union(u.returns.index)
    Lp = Lt.reindex(_ix).ffill().shift(1).reindex(u.returns.index)
    rfr = rf.loc[u.returns.index]
    ex = u.returns - rfr
    Lbar = float(Lp.mean())
    cons = rfr + Lbar * ex - max(Lbar - 1, 0) * SPREAD / 12
    recon = rfr + Lp * ex - (Lp - 1).clip(lower=0) * SPREAD / 12
    for lab, ser in (("unlevered", u.returns), ("walk-forward geared (actual)", g.returns),
                     (f"constant {Lbar:.2f}x (hindsight)", cons)):
        pm = performance_metrics(ser, periods_per_year=12, rf=rfr)
        diag.append({"family": gname, "variant": lab, "cagr": pm["cagr"], "vol": pm["vol"], "sharpe": pm["sharpe"],
                     "max_dd": pm["max_drawdown"]})
    diag[-1]["recon_corr_actual"] = float(np.corrcoef(recon, g.returns)[0, 1])
    diag[-1]["corr_lev_vs_next_excess"] = float(np.corrcoef(Lp, ex)[0, 1])
pd.DataFrame(diag).to_csv(OUT / "s3_gearing_decomposition.csv", index=False)
# GOOD-stream screen + identity check over the trading window
tw = R.loc[res["1 US equity"].returns.index]
rft = rf.loc[tw.index]
good = []
for c in UNIV:
    pm = performance_metrics(tw[c], periods_per_year=12, rf=rft)
    good.append({"asset": c, "label": LABEL[c], "cagr": pm["cagr"], "vol": pm["vol"], "sharpe": pm["sharpe"],
                 "max_dd": pm["max_drawdown"], "sharpe_se": math.sqrt((1 + pm["sharpe"] ** 2 / 2) / pm["years"])})
gd = pd.DataFrame(good)
csv = rows_out(gd, "s3_good_streams")
fig, ax = plt.subplots(figsize=(8, 3.8))
o = gd.sort_values("sharpe")
ax.barh(o["label"], o["sharpe"], color=SER[0], height=0.6)
ax.errorbar(o["sharpe"], o["label"], xerr=1.96 * o["sharpe_se"], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2)
ax.axvline(0, color=INK2, lw=0.8)
report._style(ax, f"Stream Sharpe ratios, {tw.index[0]:%Y-%m}..{tw.index[-1]:%Y-%m} (excess of T-bills; bars = +/-1.96 SE)", "Sharpe", "")
chart(fig_save(fig, "s3_good_streams"), csv, "S3 'good stream' screen: realised Sharpe per asset over the walk-forward window with 95% sampling bands")
s3_good = {"streams": good, "mean_stream_sharpe": float(gd.sharpe.mean()),
           "erc_realised_sharpe": res["4 ERC unlevered"].metrics["sharpe"]}
s3["gearing_decomposition"], s3["good_streams"] = diag, s3_good
# long stocks/bonds run
RL_all = monthly(["VFINX", "VUSTX", "VFITX"])
rc = rolling_correlation(RL_all, 36, pairs=[("VFINX", "VUSTX"), ("VFINX", "VFITX")]).dropna(how="all")
rc.index.name = "date"
csv = rows_out(rc.reset_index().assign(date=lambda z: z.date.dt.strftime("%Y-%m-%d")), "s3_longrun_stock_bond_corr")
fig, ax = plt.subplots(figsize=(8.5, 3.8))
for i, c in enumerate(rc.columns):
    ax.plot(rc.index, rc[c], color=SER[i], lw=1.8, label=c.replace("|", " vs "))
ax.axhline(0, color=INK2, lw=0.8)
report._style(ax, "Rolling 36-month stock-bond correlation (monthly total returns)", "window end", "correlation")
ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower left")
chart(fig_save(fig, "s3_longrun_stock_bond_corr"), csv, "S3 long run: rolling 36m correlation of US equity vs long and intermediate Treasuries, 1989-2026")
RL = RL_all[["VFINX", "VFITX"]].dropna()
rfl = rf_for(RL.index)
lr_res = {"US equity": bt(RL, rfl, allocator=lambda S: np.array([1.0, 0.0])),
          "60/40": bt(RL, rfl, allocator=lambda S: np.array([0.6, 0.4])),
          "ERC stock/bond @10%": bt(RL, rfl, allocator="erc", target_vol=TV)}
r = report.equity_curves(OUT, {k: v.equity for k, v in lr_res.items()}, name="s3_longrun_equity",
                         title="Stocks/bonds only, walk-forward 1994-2026 (log, month-end)")
chart(r["png"], r["csv"], "S3 long run: US equity vs 60/40 vs ERC(US eq, interm UST) geared to 10%, 1994-2026")
SUB = {"1994-11..1999-12": ("1994-10-31", "1999-12-31"), "2000..2021": ("1999-12-31", "2021-12-31"),
       "2022..2026-09": ("2021-12-31", END)}
lr_rows = []
for n, b in lr_res.items():
    for sl, (s_, e_) in SUB.items():
        rr = b.returns.loc[pd.Timestamp(s_) + pd.Timedelta(days=1): e_]
        pm = performance_metrics(rr, periods_per_year=12, rf=rfl.loc[rr.index])
        lr_rows.append({"strategy": n, "period": sl, "cagr": pm["cagr"], "vol": pm["vol"], "sharpe": pm["sharpe"],
                        "max_dd": pm["max_drawdown"],
                        "stock_bond_corr": float(RL.loc[rr.index].corr().iloc[0, 1])})
    lr_rows.append({"strategy": n, "period": "full", "cagr": b.metrics["cagr"], "vol": b.metrics["vol"],
                    "sharpe": b.metrics["sharpe"], "max_dd": b.metrics["max_drawdown"],
                    "stock_bond_corr": float(RL.loc[b.returns.index].corr().iloc[0, 1])})
pd.DataFrame(lr_rows).to_csv(OUT / "s3_longrun_subperiods.csv", index=False)
s3["longrun"] = {"window": [str(RL.index[0].date()), str(RL.index[-1].date())],
                 "first_trade": str(lr_res["60/40"].equity.index[0].date()), "subperiods": lr_rows}
M["sections"]["S3"] = s3

# =========================================================================== S4
q6 = res["6 Quadrant @10% vol"].returns
s4 = {}
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
live_rows = []
for ax, (tk, st) in zip(axes, [("RPAR", "2020-01-01"), ("ALLW", "2025-04-01")]):
    lv = monthly([tk], start=st)[tk].dropna()
    idx = lv.index.intersection(q6.index)
    a, b_ = q6.loc[idx], lv.loc[idx]
    te = float((a - b_).std(ddof=1) * math.sqrt(12))
    s4[tk] = {"first_month": str(idx[0].date()), "last_month": str(idx[-1].date()), "months": len(idx),
              "cum_quadrant": float((1 + a).prod() - 1), "cum_live": float((1 + b_).prod() - 1),
              "vol_quadrant": float(a.std(ddof=1) * math.sqrt(12)), "vol_live": float(b_.std(ddof=1) * math.sqrt(12)),
              "corr": float(a.corr(b_)), "beta_live_on_quadrant": float(np.cov(b_, a)[0, 1] / a.var()),
              "tracking_error": te, "max_dd_quadrant": max_drawdown(pd.concat([pd.Series([1.0]), (1 + a).cumprod()]).reset_index(drop=True)),
              "max_dd_live": max_drawdown(pd.concat([pd.Series([1.0]), (1 + b_).cumprod()]).reset_index(drop=True))}
    ga, gb = (1 + a).cumprod(), (1 + b_).cumprod()
    base = pd.Timestamp(idx[0]) - pd.offsets.MonthEnd(1)
    ga = pd.concat([pd.Series([1.0], index=[base]), ga]); gb = pd.concat([pd.Series([1.0], index=[base]), gb])
    ax.plot(ga.index, ga, color=SER[0], lw=2, label="(6) quadrant @10% (backtest)")
    ax.plot(gb.index, gb, color=SER[1], lw=1.8, label=f"{tk} (live fund)")
    report._style(ax, f"{tk}: {idx[0]:%Y-%m}..{idx[-1]:%Y-%m}, corr {s4[tk]['corr']:.2f}", "", "growth of $1")
    ax.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="upper left")
    ax.xaxis.set_major_locator(matplotlib.dates.AutoDateLocator(maxticks=6))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y-%m"))
    for dt in ga.index:
        live_rows.append({"fund": tk, "date": dt.strftime("%Y-%m-%d"), "quadrant_6": float(ga.loc[dt]), "live": float(gb.loc[dt])})
csv = rows_out(pd.DataFrame(live_rows), "s4_live_tracking")
chart(fig_save(fig, "s4_live_tracking"), csv, "S4 live sanity: geared quadrant backtest (6) vs RPAR (2020-01+) and ALLW (2025-04+), monthly")
M["sections"]["S4"] = s4

# =========================================================================== S5
s5 = {}
H = R.copy()
H["CASH"] = rf.to_numpy()  # FRICTION: run_forward takes a constant rf; bootstrap rf jointly as a column
g5 = target_vol_gearing(erc(S_full), S_full, TV, max_leverage=CAP)
g6 = target_vol_gearing(quadrant_balance(S_full, EXPO, BOXES).weights, S_full, TV, max_leverage=CAP)
books = {"US equity": (onehot, 0.0), "5 ERC @10%": (g5.weights, g5.cash_weight), "6 Quadrant @10%": (g6.weights, g6.cash_weight)}
s5["weights"] = {k: {**dict(zip(UNIV, v[0].round(4).tolist())), "cash": round(v[1], 4)} for k, v in books.items()}
s5["leverage"] = {"5": g5.leverage, "6": g6.leverage, "cap_binding": [g5.cap_binding, g6.cap_binding]}

# correlation-stress history: re-colour to C_s = .5 C + .5 C_2022 (vols, means kept)
dl = pd.DataFrame({t: loader.yahoo(t).values for t in UNIV}).sort_index()
D22 = levels_to_returns(align_levels(dl, "D")).loc["2022-01-01":"2022-12-31"].dropna()
C22 = D22.corr().to_numpy()
Sm = sample_cov(R)
Ss = stress_correlation(Sm, method="blend", crisis_corr=C22, alpha=0.5)
mu = R.mean().to_numpy()
Lc, Ls = np.linalg.cholesky(Sm), np.linalg.cholesky(Ss)
Xs = mu + (R.to_numpy() - mu) @ np.linalg.inv(Lc).T @ Ls.T
Hs = pd.DataFrame(Xs, index=R.index, columns=UNIV); Hs["CASH"] = rf.to_numpy()
assert np.allclose(sample_cov(Hs[UNIV]), Ss)
s5["corr_stress"] = {"mean_rho_full": mean_pairwise_correlation(cov_to_corr(Sm)[1]),
                     "mean_rho_2022_daily": mean_pairwise_correlation(C22),
                     "mean_rho_stressed": mean_pairwise_correlation(cov_to_corr(Ss)[1]), "n_days_2022": len(D22),
                     "ex_ante_vol_stressed": {k: float(math.sqrt(v[0] @ (Ss * 12) @ v[0])) for k, v in books.items()}}
cfg = SimConfig(years=10, periods_per_year=12, n_paths=10_000, seed=20261006, method="bootstrap", mean_block=12)
fw_rows, dd_rows = [], []
# SUPPLEMENTARY, POST-HOC (added after the pre-declared daily-2022 stress came out near-null):
# blend toward the 2022 MONTHLY correlation (12 obs, noisy, PSD-singular; the 50% blend is PD)
C22m = R.loc["2022-01-01":"2022-12-31"].corr().to_numpy()
Ss2 = stress_correlation(Sm, method="blend", crisis_corr=C22m, alpha=0.5)
Xs2 = mu + (R.to_numpy() - mu) @ np.linalg.inv(Lc).T @ np.linalg.cholesky(Ss2).T
Hs2 = pd.DataFrame(Xs2, index=R.index, columns=UNIV); Hs2["CASH"] = rf.to_numpy()
s5["corr_stress_monthly_posthoc"] = {"mean_rho_2022_monthly": mean_pairwise_correlation(C22m),
    "mean_rho_stressed": mean_pairwise_correlation(cov_to_corr(Ss2)[1]),
    "stock_bond_rho": {"full": float(C.loc["VFINX", "VFITX"]), "2022_daily": float(C22[0, 4]), "2022_monthly": float(C22m[0, 4])},
    "ex_ante_vol_stressed": {k: float(math.sqrt(v[0] @ (Ss2 * 12) @ v[0])) for k, v in books.items()}}
for variant, hist in (("base", H), ("corr stress", Hs), ("stress monthly (post-hoc)", Hs2)):
    for name, (w, cash) in books.items():
        if variant != "base" and name == "US equity":
            continue
        wv = np.append(w, cash)
        fr = run_forward(wv, cfg, history=hist, rf=0.0, spread=SPREAD, cash_weight=0.0, spread_weight=max(-cash, 0.0))
        st = fr.stats
        key = f"{name} [{variant}]"
        s5[key] = {k: v for k, v in st.items() if not k.startswith("_")}
        fw_rows.append({"book": name, "variant": variant, **{f"cagr_q{k}": v for k, v in st["cagr_quantiles"].items()},
                        "mean_cagr": st["mean_cagr"], "p_loss_10y": st["p_loss_horizon"], "p_losing_year": st["p_losing_year"],
                        "cvar5_cagr": st["cvar_0.05_cagr"], "cvar5_annual": st["cvar_0.05_annual"],
                        **{f"maxdd_q{k}": v for k, v in st["max_dd_quantiles"].items()}})
        if name == "6 Quadrant @10%" and variant == "base":
            r = report.forward_fan(OUT, st["_wealth_bands"], 12, name="s5_fan_quadrant")
            chart(r["png"], r["csv"], "S5 forward: 10y stationary-bootstrap wealth bands, quadrant-balanced @10% vol (base)")
fw = pd.DataFrame(fw_rows)
csv = rows_out(fw, "s5_forward_distributions")
labels = [f"{b}\n[{v.replace(' (post-hoc)', '*')}]" for b, v in zip(fw.book, fw.variant)]
for metric, title, fname, ylab in (("cagr", "10-year CAGR distribution (5/25/50/75/95th pct)", "s5_cagr_dist", "CAGR (%)"),
                                   ("maxdd", "10-year max drawdown distribution (5/25/50/75/95th pct)", "s5_maxdd_dist", "max drawdown (%)")):
    fig, ax = plt.subplots(figsize=(8, 4))
    for i in range(len(fw)):
        q = [100 * fw.iloc[i][f"{metric}_q{k}"] for k in ("0.05", "0.25", "0.5", "0.75", "0.95")]
        col = SER[{"base": 0, "corr stress": 1}.get(fw.variant.iloc[i], 2)]
        ax.plot([i, i], [q[0], q[4]], color=col, lw=1.5)
        ax.plot([i, i], [q[1], q[3]], color=col, lw=7, solid_capstyle="butt", alpha=0.6)
        ax.plot(i, q[2], "o", color=col, ms=8, mec=SURF, mew=2)
        ax.text(i + 0.12, q[2], f"{q[2]:.1f}", fontsize=7.5, color=INK2, va="center")
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(range(len(fw)), labels, fontsize=7.5)
    report._style(ax, title, "", ylab)
    ax.plot([], [], color=SER[0], lw=4, label="base bootstrap"); ax.plot([], [], color=SER[1], lw=4, label="stress: 50% to 2022 daily corr (declared)"); ax.plot([], [], color=SER[2], lw=4, label="stress: 50% to 2022 monthly corr (post-hoc)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK2, loc="lower right" if metric == "maxdd" else "upper right")
    chart(fig_save(fig, fname), csv, f"S5 forward: {title}, base vs correlation-stress")
M["sections"]["S5"] = s5
M["provenance"] = prov
M["charts"] = CHARTS
report.write_json(M, OUT / "metrics.json")
print(json.dumps({"S3": mt_df.round(4).to_dict(orient="records")}, indent=0, default=str)[:200])
print("done", len(CHARTS), "charts")
