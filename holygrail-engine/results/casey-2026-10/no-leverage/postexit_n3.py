"""No-leverage follow-up, N3: the $18M post-exit book with no borrowing, three candidates (PLAN with the crash-contingent
SpaceX rule, ALT-2 UNLEVERED refreshed, CASEY ROUTE), each pre- and post-trigger where the SpaceX rule applies.

Run: cd holygrail-engine && HG_OFFLINE=1 python results/casey-2026-10/no-leverage/postexit_n3.py
Parameters: predeclared_params.json (this folder). Estimation, priors, replays and bootstrap follow
results/casey-2026-10/post-exit/analysis.py (daily, trailing 3y, sample covariance). LOCAL helpers are marked.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from holygrail import report  # noqa: E402
from holygrail.allocate import quadrant_balance, risk_budget_weights  # noqa: E402
from holygrail.core import effective_bets, percent_risk_contributions, portfolio_vol  # noqa: E402
from holygrail.data import DataLoader, tbill_period_returns  # noqa: E402
from holygrail.environments import BOXES, CANONICAL_MAP, environment_balance, exposures_from_mapping  # noqa: E402
from holygrail.estimate import align_levels, estimate_cov, infer_periods_per_year, levels_to_returns  # noqa: E402
from holygrail.forward import SCENARIOS, SimConfig, replay_scenario, run_forward  # noqa: E402
from holygrail.streams import ProxySpec  # noqa: E402

PP = json.loads((HERE / "predeclared_params.json").read_text())["N3"]
NAV = 18_000_000.0
RF = 0.0401
END = "2026-09-30"
MAIN0 = "2023-09-29"
SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
loader = DataLoader(offline=os.environ.get("HG_OFFLINE") == "1")
prov: dict = {}
M: dict = {"params_file": "predeclared_params.json (N3)", "post_hoc": [], "rf": RF, "nav_usd": NAV}
CHARTS: list = []

COMP = ["c_hg", "c_kmlm", "c_crash", "c_vixhyg"]
COMP_W = np.array([0.29, 0.29, 0.27, 0.15])
BASKET = ["NVDA", "AVGO", "TSLA", "ISRG", "RKLB"]
BETA = ["SPY", "QQQ", "TLT", "TIP", "GLD", "DBC"]
FACT = ["QQQ", "TLT", "GLD", "DBC"]
EMP = ["SPY", "QQQ", "BOXX", "TLT", "TIP", "GLD", "DBC", "HYG", "IWM"] + BASKET + COMP
PARAM = ["FILM", "VENT", "SPCX"]
STREAMS = EMP + PARAM
IX = {s: i for i, s in enumerate(STREAMS)}
N = len(STREAMS)
SLEEVE_OF = {"SPY": "SPY / equity beta", "QQQ": "QQQ", "BOXX": "T-bills / BOXX", "TLT": "long Treasuries", "TIP": "TIPS", "GLD": "gold",
             "DBC": "commodities", "HYG": "HYG (factor only)", "IWM": "IWM (factor only)", **{b: "SPCX basket (5 names)" for b in BASKET},
             **{c: "Composer" for c in COMP}, "FILM": "film / private lending", "VENT": "venture deals", "SPCX": "SpaceX (SPCX)"}
SLEEVES = ["SPY / equity beta", "long Treasuries", "TIPS", "gold", "commodities", "Composer", "SPCX basket (5 names)", "SpaceX (SPCX)",
           "film / private lending", "venture deals", "T-bills / BOXX"]
EQ = CANONICAL_MAP["equity"]
BOXMAP = {"SPY": EQ, "QQQ": EQ, **{b: EQ for b in BASKET}, "c_hg": EQ, "c_kmlm": EQ, "c_crash": ("growth_down",), "c_vixhyg": ("growth_up",),
          "TLT": CANONICAL_MAP["nominal_bond"], "TIP": CANONICAL_MAP["ilb"], "GLD": CANONICAL_MAP["gold"], "DBC": CANONICAL_MAP["commodity"],
          "FILM": CANONICAL_MAP["credit"], "VENT": EQ, "SPCX": EQ}


# --------------------------------------------------------------------------- data (as post-exit/analysis.py)
def yl(sym, proxies=()):
    ds = loader.market_levels(sym, [ProxySpec(*p) for p in proxies])
    prov[sym + ("+proxies" if proxies else "")] = ds.provenance.to_dict()
    return ds.values


def composer_levels(slug):
    d = ROOT / "data" / "casey"
    bt = pd.read_csv(d / f"composer_{slug}_backtest.csv", parse_dates=["date"]).set_index("date")["value"]
    lv = pd.read_csv(d / f"composer_{slug}_live.csv", parse_dates=["date"]).set_index("date")["deposit_adjusted_value"]
    rb, rl = bt.pct_change(), lv.pct_change()
    t0 = lv.index[0]
    r = pd.concat([rb[rb.index <= t0].iloc[1:], rl[rl.index > t0]])
    return pd.concat([pd.Series([1.0], index=[bt.index[0]]), (1 + r).cumprod()])


lv_main = {s: yl(s) for s in EMP if not s.startswith("c_")}
for c in COMP:
    lv_main[c] = composer_levels(c[2:])
L = pd.DataFrame(lv_main).sort_index().loc[:END]
R_all = levels_to_returns(align_levels(L, "D"))
dtb3 = loader.fred("DTB3")
R = R_all.loc[R_all.index > pd.Timestamp(MAIN0)].dropna(how="any")
assert R.index[0] == pd.Timestamp("2023-10-02") and R.index[-1] == pd.Timestamp(END), (R.index[0], R.index[-1])
PPY = infer_periods_per_year(R.index)
rf_d = tbill_period_returns(dtb3.values, R.index)
S_emp = estimate_cov(R[EMP], "sample", periods_per_year=PPY).annual
vol_emp = np.sqrt(np.diag(S_emp))
EI = {s: i for i, s in enumerate(EMP)}

# --------------------------------------------------------------------------- parametric streams (predeclared)
VENT_VOL = 0.90 * math.sqrt(0.30 + 0.70 / 17.5)
sx_lv = yl("SPCX")
sx = levels_to_returns(align_levels(pd.DataFrame({"SPCX": sx_lv, "QQQ": lv_main["QQQ"]}).loc[:END], "D")).dropna()
sx_cov = np.cov(sx.to_numpy(), rowvar=False) * 252
SX_BETA = float(sx_cov[0, 1] / sx_cov[1, 1])
SX_TOTAL_VOL = float(math.sqrt(sx_cov[0, 0]))
sx_res = sx["SPCX"] - SX_BETA * sx["QQQ"]
SX_IDIO = float(sx_res.std(ddof=2) * math.sqrt(252))
PAR = {"FILM": {"factor": "HYG", "rho": 0.30, "vol": 0.22},
       "VENT": {"factor": "IWM", "rho": 0.40, "vol": VENT_VOL}}
for k, d in PAR.items():
    f = d["factor"]
    d["beta"] = d["rho"] * d["vol"] / vol_emp[EI[f]]
    d["idio"] = math.sqrt(max(d["vol"] ** 2 - (d["beta"] * vol_emp[EI[f]]) ** 2, 0.0))
PAR["SPCX"] = {"factor": "QQQ", "beta": SX_BETA, "idio": SX_IDIO}
PAR["SPCX"]["vol"] = math.sqrt(SX_BETA ** 2 * S_emp[EI["QQQ"], EI["QQQ"]] + SX_IDIO ** 2)
M["parametric"] = {k: {kk: (float(vv) if not isinstance(vv, str) else vv) for kk, vv in d.items()} for k, d in PAR.items()}
M["parametric"]["SPCX"].update({"listed_window": [str(sx.index[0].date()), str(sx.index[-1].date()), len(sx)],
                                "measured_total_vol_listed_window": SX_TOTAL_VOL,
                                "corr_qqq_listed_window": float(sx.corr().iloc[0, 1])})
M["parametric"]["VENT"]["vol_formula"] = "0.90 x sqrt(0.30 + 0.70/17.5)"

S = np.zeros((N, N))
S[:len(EMP), :len(EMP)] = S_emp
for k, d in PAR.items():
    i, fi = IX[k], EI[d["factor"]]
    S[i, :len(EMP)] = d["beta"] * S_emp[fi]
    S[:len(EMP), i] = S[i, :len(EMP)]
for a in PARAM:
    for b in PARAM:
        S[IX[a], IX[b]] = PAR[a]["beta"] * PAR[b]["beta"] * S_emp[EI[PAR[a]["factor"]], EI[PAR[b]["factor"]]]
    S[IX[a], IX[a]] = PAR[a]["vol"] ** 2
assert np.all(np.linalg.eigvalsh(S) > -1e-10)
vol = np.sqrt(np.diag(S))


def vec(d):
    w = np.zeros(N)
    for k, v in d.items():
        w[IX[k]] += v
    return w


# --------------------------------------------------------------------------- candidates (predeclared)
comp = lambda x: dict(zip(COMP, x * COMP_W))  # noqa: E731
core = ["SPY", "TLT", "TIP", "GLD", "DBC"]
ci = [IX[c] for c in core]
Mc, _ = exposures_from_mapping(core, BOXMAP)
qb = quadrant_balance(S[np.ix_(ci, ci)], Mc, boxes=list(BOXES))
CORE_W = dict(zip(core, qb.weights.tolist()))
# ALT-2 unlevered (refresh of post-exit post_hoc)
B = np.zeros((N, 3))
B[ci, 0] = qb.weights
B[[IX[c] for c in COMP], 1] = COMP_W
B[[IX[b] for b in BASKET], 2] = 1 / len(BASKET)
v3 = risk_budget_weights(B.T @ S @ B, [0.70, 0.15, 0.15])
w_alt2 = B @ v3
w_alt2 = w_alt2 / w_alt2.sum()
spx = 750_000.0 / NAV
cr = PP["CASEY_ROUTE_pre_trigger"]
core_usd = NAV - cr["film_private_lending_usd"] - cr["venture_new_usd"] - cr["composer_usd"] - cr["spacex_reserve_usd"]
assert abs(core_usd - 8_530_000) < 1
casey_pre = {**{c: core_usd / NAV * CORE_W[c] for c in core}, "FILM": cr["film_private_lending_usd"] / NAV,
             "VENT": cr["venture_new_usd"] / NAV, **comp(cr["composer_usd"] / NAV), "BOXX": cr["spacex_reserve_usd"] / NAV}
casey_post = {**casey_pre, "SPCX": spx, "BOXX": cr["spacex_reserve_usd"] / NAV - spx}
W = {"PLAN pre-trigger": vec({**comp(0.24), "SPY": 0.40, "BOXX": 0.36}),
     "PLAN post-trigger": vec({**comp(0.24), "SPY": 0.40, "SPCX": spx, "BOXX": 0.36 - spx}),
     "ALT-2 UNLEVERED": w_alt2,
     "CASEY ROUTE pre-trigger": vec(casey_pre),
     "CASEY ROUTE post-trigger": vec(casey_post)}
for k, w in W.items():
    assert abs(w.sum() - 1) < 1e-9 and w.min() >= -1e-12, (k, w.sum())
CAND = list(W)
M["weights"] = {c: {s: float(W[c][IX[s]]) for s in STREAMS if abs(W[c][IX[s]]) > 1e-12} for c in CAND}
M["construction"] = {"core_weights": CORE_W, "core_box_risk": dict(zip(BOXES, qb.box_shares.tolist())),
                     "alt2_sleeve_weights": dict(zip(["beta core", "Composer", "SPCX basket"], (v3 / v3.sum()).tolist())),
                     "casey_route_usd": {"core": core_usd, **{k: v for k, v in cr.items() if k.endswith("_usd")}}}

# --------------------------------------------------------------------------- priors (PRIOR-DRIVEN)
Xex = R.sub(rf_d, axis=0)
Fd = np.column_stack([np.ones(len(R)), Xex[FACT].to_numpy()])


def mu_vector(film_rate):
    mu = np.full(N, RF)
    for b in BETA:
        mu[IX[b]] = RF + 0.30 * vol[IX[b]]
    muF = np.array([mu[IX[f]] - RF for f in FACT])
    for a in BASKET + COMP:
        coef, *_ = np.linalg.lstsq(Fd, Xex[a].to_numpy(), rcond=None)
        mu[IX[a]] = RF + coef[1:] @ muF
    mu[IX["FILM"]] = film_rate
    mu[IX["VENT"]] = RF + 0.30 * VENT_VOL
    mu[IX["SPCX"]] = RF + SX_BETA * (mu[IX["QQQ"]] - RF)
    return mu


FILM_HEADLINE = 0.20
FILM_ADJ = (1 - 0.08) * 0.20 - 0.08 * 0.50
MU = {"film_20pct_headline": mu_vector(FILM_HEADLINE), "film_14.4pct_default_adjusted": mu_vector(FILM_ADJ)}
M["priors"] = {"basis": "PRIOR-DRIVEN, NOT forecasts: betas rf + 0.30 x vol; Composer/basket zero-alpha beta-implied; film 20% headline "
                        "or 14.4% = (1-0.08) x 20% - 0.08 x 50%; venture rf + 0.30 x 52.5%; SPCX zero-alpha rf + beta x (mu_QQQ - rf)",
               **{k: dict(zip(STREAMS, v.tolist())) for k, v in MU.items()}}


# --------------------------------------------------------------------------- risk structure
EXPO, _ = exposures_from_mapping(STREAMS, BOXMAP)


def risk_block(w):
    eb = effective_bets(w, S, n_obs=len(R))
    prc = percent_risk_contributions(w, S)
    sl = {s: float(sum(prc[i] for i, st in enumerate(STREAMS) if SLEEVE_OF[st] == s)) for s in SLEEVES}
    dol = {s: float(sum(w[i] for i, st in enumerate(STREAMS) if SLEEVE_OF[st] == s)) for s in SLEEVES}
    env = environment_balance(w, S, EXPO)
    mu20, mu14 = MU["film_20pct_headline"], MU["film_14.4pct_default_adjusted"]
    v_ = portfolio_vol(w, S)
    return {"vol": v_, "gross": float(w[[IX[s] for s in STREAMS if s != "BOXX"]].sum()),
            "neff": {r["measure"]: r["value"] for r in eb.rows()}, "rho_bar": eb.rho_bar, "risk_share": sl, "dollar_share": dol,
            "env_risk_share": env["risk_share"], "env_unmapped": env["unmapped_risk_share"], "env_balance_score": env["balance_score"],
            "exp_return_prior_film20": float(w @ mu20), "exp_return_prior_film14": float(w @ mu14),
            "sharpe_prior_film20": float((w @ mu20 - RF) / v_), "sharpe_prior_film14": float((w @ mu14 - RF) / v_),
            "film_contrib_to_return_film20": float(w[IX["FILM"]] * mu20[IX["FILM"]]),
            "private_risk_share": sl["film / private lending"] + sl["venture deals"]}


RB = {c: risk_block(W[c]) for c in CAND}
M["risk"] = RB
for c in CAND:
    r_ = RB[c]
    print(c, {k: round(r_[k], 4) for k in ("vol", "exp_return_prior_film20", "exp_return_prior_film14", "env_balance_score")},
          "DR2", round(r_["neff"]["dr2"], 2), {k: round(v, 3) for k, v in r_["risk_share"].items() if abs(v) > 1e-4})

# --------------------------------------------------------------------------- replays (long history with proxies)
LP = {"SPY": (), "QQQ": (), "IEF": (("VFITX", "2002-07-30", "Vanguard interm. Treasury fund"),),
      "TIP": (("VIPSX", "2003-12-05", "Vanguard Inflation-Protected fund"), ("VFITX", "2000-06-29", "interm. UST before VIPSX")),
      "TLT": (("VUSTX", "2002-07-30", "Vanguard long-term Treasury fund"),),
      "GLD": (("GC=F", "2004-11-18", "COMEX gold front-month, price only"),),
      "DBC": (("^SPGSCI", "2006-02-06", "S&P GSCI price index, no collateral yield"),),
      "HYG": (("VWEHX", "2007-04-11", "Vanguard High-Yield Corporate fund"),), "IWM": ()}
lv_long = {s: yl(s, p) for s, p in LP.items()}
for b in BASKET:
    lv_long[b] = lv_main[b]
Llong = pd.DataFrame(lv_long).sort_index().loc[:END]
cal = Llong["SPY"].dropna().index
Rl = levels_to_returns(align_levels(Llong, "D", calendar=cal))
rf_l = tbill_period_returns(dtb3.values, Rl.index)
Rlex = Rl[FACT].sub(rf_l, axis=0).fillna(0.0)    # LOCAL: missing factor = zero excess (gold before 2000-08-30), flagged
xc = Xex[COMP] @ COMP_W
cc, *_ = np.linalg.lstsq(Fd, xc.to_numpy(), rcond=None)
Rl["c_proxy"] = rf_l + Rlex.to_numpy() @ cc[1:]
for k, d in PAR.items():
    Rl[k] = rf_l + d["beta"] * (Rl[d["factor"]] - rf_l)     # no idio in replays (stated)
REPLAYS = {"tech_2000_02": ("2000-03-10", "2002-10-09"), "gfc_2008": SCENARIOS["gfc"][:2], "covid_2020": SCENARIOS["covid"][:2],
           "inflation_2022": SCENARIOS["inflation_2022"][:2]}


def long_weights(w, a, b, key):
    d = {}
    # as post-exit/analysis.py: the basket is QQQ in tech_2000_02 and gfc_2008, listed names (EW) in covid/2022
    avail = [] if key in ("tech_2000_02", "gfc_2008") else [x for x in BASKET if Rl[x].loc[pd.Timestamp(a):pd.Timestamp(b)].iloc[1:].notna().all()]
    for s, i in IX.items():
        x = w[i]
        if abs(x) < 1e-15 or s == "BOXX":
            continue
        if s in COMP:
            d["c_proxy"] = d.get("c_proxy", 0) + x
        elif s in BASKET:
            if avail:
                for n in avail:
                    d[n] = d.get(n, 0) + x / len(avail)
            else:
                d["QQQ"] = d.get("QQQ", 0) + x
        else:
            d[s] = d.get(s, 0) + x
    return d, ("EW " + "/".join(avail)) if avail else "QQQ"


rp = []
for key, (a, b) in REPLAYS.items():
    for c in CAND:
        d, bas = long_weights(W[c], a, b, key)
        res = replay_scenario(Rl, d, a, b, rebalance="none", rf_period=rf_l, missing="cash", label=f"{key} {c}")
        rp.append({"scenario": key, "start": a, "end": b, "candidate": c, "basket_used": bas, "cum_return": res["cum_return"],
                   "max_drawdown": res["max_drawdown"], "loss_usd": res["cum_return"] * NAV, "max_dd_usd": res["max_drawdown"] * NAV,
                   "notes": "; ".join(res["notes"])})
    spy = replay_scenario(Rl, {"SPY": 1.0}, a, b, rf_period=rf_l, label=f"{key} SPY")
    rp.append({"scenario": key, "start": a, "end": b, "candidate": "SPY 100%", "basket_used": "-", "cum_return": spy["cum_return"],
               "max_drawdown": spy["max_drawdown"], "loss_usd": spy["cum_return"] * NAV, "max_dd_usd": spy["max_drawdown"] * NAV, "notes": ""})
M["stress_replays"] = {"basis": "today's weights buy-and-hold, daily MTM; Composer = beta proxy; film = rf + beta x (HYG - rf) "
                                "(VWEHX before 2007-04-11); venture = rf + beta x (IWM - rf); SPCX = rf + beta x (QQQ - rf); no idiosyncratic "
                                "risk in replays (understates single-name / single-loan losses)", "rows": rp}

# --------------------------------------------------------------------------- forward bootstrap
rng = np.random.default_rng(20261006)
H0 = np.zeros((len(R), N))
H0[:, :len(EMP)] = R[EMP].to_numpy() - R[EMP].to_numpy().mean(axis=0)
for k, d in PAR.items():
    f = H0[:, EI[d["factor"]]]
    e = rng.normal(0.0, d["idio"] / math.sqrt(252), len(R))
    H0[:, IX[k]] = d["beta"] * f + (e - e.mean())   # demeaned: the synthetic draw must not carry a sample-mean drift
cfg = SimConfig(years=10, periods_per_year=252, n_paths=10_000, seed=20261006, method="bootstrap", mean_block=21)
FW = {}
for lab, mu in MU.items():
    H = H0 + mu / 252.0
    FW[lab] = {}
    for c in CAND:
        fr = run_forward(W[c], cfg, history=H, rf=RF, spread=0.0, chunk=250)
        FW[lab][c] = {k: v for k, v in fr.stats.items() if not k.startswith("_")}
M["post_hoc"].append({"item": "bootstrap: synthetic private/SPCX idiosyncratic draws demeaned (bug fix after the first run)",
                      "why": "a finite Gaussian sample carries a sample-mean drift (venture idio ~50%/yr over 750 days: SE ~29%/yr), which "
                             "pushed bootstrap medians above the prior means; demeaning restores the declared 're-centred on prior means'"})
M["forward_bootstrap"] = {"basis": "IN-SAMPLE resampling of 2023-26 daily returns (private/SPCX synthesised: beta x factor + Gaussian idio), "
                                   "re-centred to PRIOR-DRIVEN means; not a forecast; no default jumps", "results": FW}

worst = []
for c in CAND:
    rr = [r for r in rp if r["candidate"] == c]
    wr = min(rr, key=lambda r: r["max_drawdown"])
    q14 = FW["film_14.4pct_default_adjusted"][c]["annual_return_quantiles"]
    q20 = FW["film_20pct_headline"][c]["annual_return_quantiles"]
    worst.append({"candidate": c, "vol": RB[c]["vol"], "dr2": RB[c]["neff"]["dr2"], "balance_score": RB[c]["env_balance_score"],
                  "exp_return_prior_film20": RB[c]["exp_return_prior_film20"], "exp_return_prior_film14": RB[c]["exp_return_prior_film14"],
                  "exp_usd_per_year_film14": RB[c]["exp_return_prior_film14"] * NAV,
                  "worst_replay": wr["scenario"], "worst_replay_max_dd": wr["max_drawdown"], "worst_replay_max_dd_usd": wr["max_dd_usd"],
                  "boot_p05_year_film14": q14["0.05"], "boot_p05_year_usd_film14": q14["0.05"] * NAV,
                  "boot_p05_year_film20": q20["0.05"], "boot_p05_year_usd_film20": q20["0.05"] * NAV,
                  "boot_median_cagr10_film14": FW["film_14.4pct_default_adjusted"][c]["cagr_quantiles"]["0.5"],
                  "p_losing_year_film14": FW["film_14.4pct_default_adjusted"][c]["p_losing_year"]})
M["summary"] = worst
WT = pd.DataFrame(worst)
report.write_rows(WT, HERE / "n3_summary")
print(WT.round(4).to_string())


# --------------------------------------------------------------------------- charts
def save(fig, name):
    fig.tight_layout(); p = HERE / f"{name}.png"; fig.savefig(p, dpi=150, facecolor=SURF); plt.close(fig); return str(p)


rows = [{"candidate": c, "sleeve": s, "dollar_share": RB[c]["dollar_share"][s], "risk_share": RB[c]["risk_share"][s]} for c in CAND for s in SLEEVES]
df = pd.DataFrame(rows)
csv = report.write_rows(df, HERE / "n3_risk_vs_dollar_by_sleeve")["csv"]
used = [s for s in SLEEVES if df.loc[df.sleeve == s, ["dollar_share", "risk_share"]].abs().to_numpy().max() > 1e-6]
fig, axs = plt.subplots(1, 5, figsize=(18, 4.8), sharey=True)
y = np.arange(len(used))
for ax, c, col in zip(axs, CAND, (SER[1], SER[1], SER[0], SER[2], SER[2])):
    d = df[df.candidate == c].set_index("sleeve").loc[used]
    ax.barh(y + 0.2, d.dollar_share * 100, 0.38, color=GRID, label="dollars")
    ax.barh(y - 0.2, d.risk_share * 100, 0.38, color=col, label="risk")
    for yi, x_ in zip(y, d.risk_share):
        if abs(x_) > 0.004:
            ax.text(x_ * 100 + 1, yi - 0.2, f"{x_:.0%}", va="center", fontsize=6.5, color=INK2)
    report._style(ax, f"{c}\nvol {RB[c]['vol']:.1%}, DR^2 {RB[c]['neff']['dr2']:.1f}", "% of $18M / % of risk", "")
    ax.legend(frameon=False, fontsize=6.5, labelcolor=INK2, loc="lower right")
axs[0].set_yticks(y, used, fontsize=8); axs[0].invert_yaxis()
CHARTS.append({"png": save(fig, "n3_risk_vs_dollar"), "rows_csv": csv,
               "caption": "N3: $18M, no leverage. Dollar vs Euler risk share by sleeve, trailing-3y daily covariance; private streams = book assumptions"})

rows = [{"candidate": c, **{b: RB[c]["env_risk_share"][b] for b in BOXES}, "unmapped": RB[c]["env_unmapped"], "balance_score": RB[c]["env_balance_score"]} for c in CAND]
de = pd.DataFrame(rows)
csv = report.write_rows(de, HERE / "n3_environment_boxes")["csv"]
fig, ax = plt.subplots(figsize=(9.5, 4))
x = np.arange(len(BOXES))
for j, c in enumerate(CAND):
    vals = [de.loc[j, b] * 100 for b in BOXES]
    ax.bar(x + (j - 2) * 0.16, vals, 0.15, color=SER[j], label=f"{c} (balance {de.loc[j, 'balance_score']:.2f})")
ax.axhline(25, color=INK2, lw=0.8, ls="--")
ax.set_xticks(x, ["growth up", "growth down", "inflation up", "inflation down"])
report._style(ax, "Share of risk by All Weather box (target 25%)", "", "% of risk")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2)
CHARTS.append({"png": save(fig, "n3_environment_boxes"), "rows_csv": csv, "caption": "N3 environment-box risk shares (film = credit -> growth-up; venture/SPCX = equity)"})

dfr = pd.DataFrame(rp)
csv = report.write_rows(dfr, HERE / "n3_stress_replays")["csv"]
fig, ax = plt.subplots(figsize=(10, 4.4))
keys = list(REPLAYS)
xs = np.arange(len(keys))
ser = CAND + ["SPY 100%"]
for j, c in enumerate(ser):
    sub = dfr[dfr.candidate == c].set_index("scenario").loc[keys]
    dd = sub.max_drawdown * NAV / 1e6
    xj = xs + (j - 2.5) * 0.14
    ax.bar(xj, dd, 0.13, color=SER[j] if c != "SPY 100%" else GRID, label=c)
    for xi, v_ in zip(xj, dd):
        ax.text(xi, v_ - 0.35, f"{v_:.1f}", ha="center", fontsize=5.8, color=INK2)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(xs, ["2000-02 tech bust", "2008 GFC", "2020 Covid", "2022 inflation"])
report._style(ax, "Stress replays on $18M: peak-to-trough loss, today's weights buy-and-hold", "", "$M")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="lower right")
CHARTS.append({"png": save(fig, "n3_stress_replays"), "rows_csv": csv,
               "caption": "N3 replays: Composer = beta proxy, private streams = factor betas only (no idio), SPCX = beta x QQQ; $M on $18M"})

rows = []
for lab in FW:
    for c in CAND:
        q = FW[lab][c]["annual_return_quantiles"]
        rows.append({"film_rate": lab, "candidate": c, **{f"p{int(float(k) * 100):02d}": v for k, v in q.items()},
                     "p05_usd": q["0.05"] * NAV, "p_losing_year": FW[lab][c]["p_losing_year"]})
dq = pd.DataFrame(rows)
csv = report.write_rows(dq, HERE / "n3_bootstrap_one_year")["csv"]
fig, ax = plt.subplots(figsize=(9, 4.2))
yv = 0
tk, tl = [], []
for j, c in enumerate(CAND):
    r_ = dq[(dq.film_rate == "film_14.4pct_default_adjusted") & (dq.candidate == c)].iloc[0]
    ax.plot([r_.p05 * NAV / 1e6, r_.p95 * NAV / 1e6], [yv, yv], color=SER[j], lw=2)
    ax.plot([r_.p25 * NAV / 1e6, r_.p75 * NAV / 1e6], [yv, yv], color=SER[j], lw=7, solid_capstyle="butt")
    ax.plot(r_.p50 * NAV / 1e6, yv, "o", color=SURF, mec=SER[j], ms=6, mew=2)
    ax.text(r_.p05 * NAV / 1e6, yv + 0.32, f"p5 {r_.p05 * NAV / 1e6:+.2f}M", fontsize=7, color=INK2, ha="center")
    tk.append(yv); tl.append(c); yv += 1
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks(tk, tl, fontsize=8); ax.invert_yaxis()
report._style(ax, "One-year P&L on $18M, bootstrap (film at 14.4% adjusted): p5-p95 / p25-p75 / median", "$M", "")
CHARTS.append({"png": save(fig, "n3_bootstrap_one_year"), "rows_csv": csv,
               "caption": "N3 forward bootstrap of 2023-26 daily returns re-centred on PRIOR means (in-sample shape, not a forecast); film 14.4% (20% rows in CSV)"})

M["charts"] = CHARTS
M["provenance"] = prov
report.write_json(M, HERE / "metrics_postexit.json")
print("done")
