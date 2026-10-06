"""Analysis B: Casey's $18M post-exit plan vs two Dalio-balanced alternatives.

Run:  cd holygrail-engine && python results/casey-2026-10/post-exit/analysis.py
Parameters frozen in predeclared_params.json (declared before any result).
Everything goes through the holygrail public API; local helpers are marked LOCAL.
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from holygrail import report  # noqa: E402
from holygrail.allocate import quadrant_balance, risk_budget_weights  # noqa: E402
from holygrail.backtest import BacktestConfig, run_backtest  # noqa: E402
from holygrail.core import effective_bets, percent_risk_contributions, portfolio_vol  # noqa: E402
from holygrail.data import DataLoader, tbill_period_returns  # noqa: E402
from holygrail.environments import BOXES, CANONICAL_MAP, environment_balance, exposures_from_mapping  # noqa: E402
from holygrail.estimate import align_levels, estimate_cov, infer_periods_per_year, levels_to_returns  # noqa: E402
from holygrail.forward import SCENARIOS, SimConfig, replay_scenario, run_forward, stress_correlation  # noqa: E402
from holygrail.metrics import drawdown, max_drawdown, performance_metrics, calendar_year_returns  # noqa: E402
from holygrail.streams import ProxySpec  # noqa: E402

OUT = Path(__file__).resolve().parent
P = json.loads((OUT / "predeclared_params.json").read_text())
NAV = 18_000_000.0
RF = 0.0401
SPREAD_PREDECLARED = 0.0075   # predeclared_params.json; its label ('recalled, not opened', 'over rf') is wrong - see post_hoc
# IBKR Pro USD margin card, ibkr.com/en/trading/margin-rates.php fetched 2026-10-06 (scratchpad ibkr_margin.html):
# 0-100k 5.380% (BM+1.5%), 100k-1M 4.880% (BM+1%), 1M-50M 4.630% (BM+0.75%), 50M+ 4.380% (BM+0.5%); BM = 3.88%.
IBKR_TIERS = [(100_000.0, 0.0538), (1_000_000.0, 0.0488), (50_000_000.0, 0.0463), (math.inf, 0.0438)]


def ibkr_spread_over_rf(borrow_usd):
    """Tier-blended IBKR rate minus rf (DTB3) on a loan of ``borrow_usd`` (0 if nothing is borrowed)."""
    if borrow_usd <= 0:
        return 0.0
    out, lo = 0.0, 0.0
    for hi, rate in IBKR_TIERS:
        if borrow_usd <= lo:
            break
        out += (min(borrow_usd, hi) - lo) * rate
        lo = hi
    return out / borrow_usd - RF


def spread_for(w):
    """Spread over rf at the loan a constant mix ``w`` (fractions of NAV) carries today: max(sum w - 1, 0) x NAV."""
    return ibkr_spread_over_rf(max(float(np.sum(w)) - 1.0, 0.0) * NAV)


CAP = 3.0
S_BASE = 0.30
END = "2026-09-30"
MAIN0, ROB0, LONG0 = "2023-09-29", "2023-04-19", "2006-02-06"   # LEVEL start dates (first return = next session)
SER, INK, INK2, GRID, SURF = report.SERIES, report.INK, report.INK2, report.GRID, report.SURFACE
loader = DataLoader(offline=os.environ.get("HG_OFFLINE") == "1")  # HG_OFFLINE=1: cache only (reproducible re-runs)
prov: dict = {}
M: dict = {"params_file": "predeclared_params.json", "post_hoc": [{
    "item": "repair pass 2026-10-06: financing spread corrected from the predeclared 0.75% to the IBKR card, blended by tier at each "
            "book's own loan size (over DTB3 4.01%)",
    "why": "the predeclared label read 'IBKR Pro tier $1M-$50M BM+0.75%, recalled, not opened' and applied 0.75% over rf. The card was "
           "fetched in-session (ibkr_margin.html): 4.630% for $1M-50M = BM 3.88% + 0.75% = DTB3 + 0.62%; 5.380% / 4.880% for the "
           "first $100k / next $900k. A correction of a mis-sourced input, not tuning. Only books that borrow are affected "
           "(ALT-2 at ~2.1x: ~$19.6M loan, blend DTB3 + ~0.64%; ALT-1 scaled to 15%: small loan, blend ~DTB3 + 0.96%).",
    "predeclared_value": SPREAD_PREDECLARED}]}
CHARTS: list = []

COMP = ["c_hg", "c_kmlm", "c_crash", "c_vixhyg"]
COMP_W = np.array([0.29, 0.29, 0.27, 0.15])
BASKET = ["NVDA", "AVGO", "TSLA", "ISRG", "RKLB"]
BETA = ["SPY", "QQQ", "IEF", "TLT", "TIP", "GLD", "DBC"]
FACT = ["QQQ", "TLT", "GLD", "DBC"]
STREAMS = ["SPY", "QQQ", "BOXX", "IEF", "TIP", "TLT", "GLD", "DBC"] + BASKET + COMP
SLEEVE_OF = {"SPY": "SPY (US equity)", "QQQ": "SPCX sleeve", "BOXX": "Treasury bills", "IEF": "Duration (UST)",
             "TLT": "Duration (UST)", "TIP": "TIPS", "GLD": "Gold", "DBC": "Commodities",
             **{b: "SPCX sleeve" for b in BASKET}, **{c: "Composer sleeve" for c in COMP}}
SLEEVES = ["SPY (US equity)", "Composer sleeve", "SPCX sleeve", "Treasury bills", "Duration (UST)", "TIPS", "Gold",
           "Commodities"]
LABEL = {"c_hg": "Composer HG symphony (not Dalio)", "c_kmlm": "Composer KMLM switcher", "c_crash": "Composer Crash Convexity",
         "c_vixhyg": "Composer VIX Harvester"}
BOXMAP = {"SPY": CANONICAL_MAP["equity"], "QQQ": CANONICAL_MAP["equity"], **{b: CANONICAL_MAP["equity"] for b in BASKET},
          "c_hg": CANONICAL_MAP["equity"], "c_kmlm": CANONICAL_MAP["equity"], "c_crash": ("growth_down",),
          "c_vixhyg": ("growth_up",), "IEF": CANONICAL_MAP["nominal_bond"], "TLT": CANONICAL_MAP["nominal_bond"],
          "TIP": CANONICAL_MAP["ilb"], "GLD": CANONICAL_MAP["gold"], "DBC": CANONICAL_MAP["commodity"]}
CAND = ["PLAN", "ALT-1", "ALT-2"]
CAND_LABEL = {"PLAN": "PLAN (Casey as written)", "ALT-1": "ALT-1 (minimal change)", "ALT-2": "ALT-2 (Dalio-balanced @15%)"}
CCOL = {"PLAN": SER[1], "ALT-1": SER[3], "ALT-2": SER[0], "SPY": INK2}


# --------------------------------------------------------------------------- data
def yl(sym, proxies=()):
    ds = loader.market_levels(sym, [ProxySpec(*p) for p in proxies])
    prov[sym + ("+proxies" if proxies else "")] = ds.provenance.to_dict()
    return ds.values


def composer_levels(slug):
    """LOCAL: backtest returns up to the live start, live deposit-adjusted returns after (predeclared splice)."""
    d = ROOT / "data" / "casey"
    bt = pd.read_csv(d / f"composer_{slug}_backtest.csv", parse_dates=["date"]).set_index("date")["value"]
    lv = pd.read_csv(d / f"composer_{slug}_live.csv", parse_dates=["date"]).set_index("date")["deposit_adjusted_value"]
    rb, rl = bt.pct_change(), lv.pct_change()
    t0 = lv.index[0]
    r = pd.concat([rb[rb.index <= t0].iloc[1:], rl[rl.index > t0]])
    lev = pd.concat([pd.Series([1.0], index=[bt.index[0]]), (1 + r).cumprod()])
    prov[f"c_{slug}"] = {"source": "Composer backtest (IN-SAMPLE) spliced to live deposit-adjusted", "backtest": [str(bt.index[0].date()), str(bt.index[-1].date())],
                         "live_from": str(t0.date())}
    return lev, bt


lv_main = {s: yl(s) for s in STREAMS if not s.startswith("c_")}
comp_bt = {}
for c in COMP:
    lv_main[c], comp_bt[c] = composer_levels(c[2:])
L = pd.DataFrame(lv_main).sort_index().loc[:END]
R_all = levels_to_returns(align_levels(L, "D"))
dtb3 = loader.fred("DTB3")
prov["DTB3"] = dtb3.provenance.to_dict()


def window(R, start):
    return R.loc[R.index > pd.Timestamp(start)].dropna(how="any")


R = window(R_all, MAIN0)
R_rob = window(R_all, ROB0)
assert R.index[0] == pd.Timestamp("2023-10-02") and R.index[-1] == pd.Timestamp(END), (R.index[0], R.index[-1])
assert R_rob.index[0] == pd.Timestamp("2023-04-20"), R_rob.index[0]
PPY = infer_periods_per_year(R.index)
rf_d = tbill_period_returns(dtb3.values, R.index)
M["windows"] = {"main": [str(R.index[0].date()), str(R.index[-1].date()), len(R)],
                "robustness_longest_common": [str(R_rob.index[0].date()), str(R_rob.index[-1].date()), len(R_rob)],
                "periods_per_year_observed": PPY}


def cov_of(Rw):
    ppy = infer_periods_per_year(Rw.index)
    return estimate_cov(Rw, "sample", periods_per_year=ppy).annual


S = cov_of(R)
S_rob = cov_of(R_rob)
IX = {s: i for i, s in enumerate(STREAMS)}
N = len(STREAMS)
vol = np.sqrt(np.diag(S))


def vec(d):
    w = np.zeros(N)
    for k, v in d.items():
        w[IX[k]] += v
    return w


# --------------------------------------------------------------------------- candidates
def spcx_part(x, variant):
    return {b: x / len(BASKET) for b in BASKET} if variant == "i" else {"QQQ": x}


def comp_part(x):
    return dict(zip(COMP, x * COMP_W))


def sleeve_prc(w, Sm, sleeve):
    prc = percent_risk_contributions(w, Sm)
    return float(sum(prc[i] for i, s in enumerate(STREAMS) if SLEEVE_OF[s] == sleeve))


def build(variant):
    out = {}
    plan = {**comp_part(0.24), "SPY": 0.40, "BOXX": 0.16, **spcx_part(0.20, variant)}
    out["PLAN"] = vec(plan)

    def alt1(x):
        k = (1 - x) / 0.80
        return vec({**comp_part(0.24 * k), "SPY": 0.40 * k, "IEF": 0.08 * k, "TIP": 0.08 * k, **spcx_part(x, variant)})
    x = 0.20
    if sleeve_prc(alt1(0.20), S, "SPCX sleeve") > 0.20:
        lo, hi = 0.0, 0.20
        for _ in range(60):
            x = 0.5 * (lo + hi)
            lo, hi = (x, hi) if sleeve_prc(alt1(x), S, "SPCX sleeve") < 0.20 else (lo, x)
        x = 0.5 * (lo + hi)
    out["ALT-1"] = alt1(x)
    alt1_info = {"spcx_weight": x, "cap_binding": x < 0.20 - 1e-9}

    core = ["SPY", "TLT", "TIP", "GLD", "DBC"]
    ci = [IX[c] for c in core]
    Mc, unm = exposures_from_mapping(core, BOXMAP)
    assert not unm
    qb = quadrant_balance(S[np.ix_(ci, ci)], Mc, boxes=list(BOXES))
    B = np.zeros((N, 3))
    B[ci, 0] = qb.weights
    B[[IX[c] for c in COMP], 1] = COMP_W
    if variant == "i":
        B[[IX[b] for b in BASKET], 2] = 1 / len(BASKET)
    else:
        B[IX["QQQ"], 2] = 1.0
    S3 = B.T @ S @ B
    v = risk_budget_weights(S3, [0.70, 0.15, 0.15])
    w2 = B @ v
    Lg = min(0.15 / portfolio_vol(w2, S), CAP / w2.sum())
    out["ALT-2"] = Lg * w2
    alt2_info = {"core_weights": dict(zip(core, qb.weights.tolist())), "core_box_risk": dict(zip(BOXES, qb.box_shares.tolist())),
                 "sleeve_weights_unlevered": dict(zip(["beta core", "Composer", "SPCX"], v.tolist())),
                 "leverage": Lg, "cap_binding": bool(Lg * w2.sum() >= CAP - 1e-9),
                 "sleeve_vols": dict(zip(["beta core", "Composer", "SPCX"], np.sqrt(np.diag(S3)).tolist())),
                 "sleeve_corr": (S3 / np.outer(np.sqrt(np.diag(S3)), np.sqrt(np.diag(S3)))).tolist()}
    return out, {"ALT-1": alt1_info, "ALT-2": alt2_info}


W, INFO = {}, {}
for var in ("i", "ii"):
    W[var], INFO[var] = build(var)
M["weights"] = {var: {c: {s: float(W[var][c][IX[s]]) for s in STREAMS if abs(W[var][c][IX[s]]) > 1e-12} for c in CAND}
                for var in W}
M["construction"] = INFO


# --------------------------------------------------------------------------- priors (PRIOR-DRIVEN)
Xex = R.sub(rf_d, axis=0)
F = Xex[FACT].to_numpy()
Fd = np.column_stack([np.ones(len(F)), F])


def ols(y):
    coef, *_ = np.linalg.lstsq(Fd, y, rcond=None)
    res = y - Fd @ coef
    return coef, float(res.std(ddof=Fd.shape[1]) * math.sqrt(PPY)), 1 - res.var() / y.var()


def mu_vector(s=S_BASE, alpha_ir=0.0):
    mu = np.full(N, RF)
    for b in BETA:
        mu[IX[b]] = RF + s * vol[IX[b]]
    muF = np.array([mu[IX[f]] - RF for f in FACT])
    det = {}
    for a in BASKET + COMP:
        coef, rv, r2 = ols(Xex[a].to_numpy())
        mu[IX[a]] = RF + coef[1:] @ muF + alpha_ir * rv
        det[a] = {"betas": dict(zip(FACT, coef[1:].tolist())), "in_sample_alpha_annual": float(coef[0] * PPY),
                  "residual_vol": rv, "r2": float(r2)}
    return mu, det


MU, BETAS = mu_vector()
comp_insample = {}
for c in COMP:
    x = Xex[c]
    comp_insample[c] = {"in_sample_sharpe_3y_window": float(x.mean() / x.std() * math.sqrt(PPY)),
                        "prior_sharpe_zero_alpha": float((MU[IX[c]] - RF) / vol[IX[c]])}
xc = Xex[COMP] @ COMP_W
M["priors"] = {"basis": "PRIOR-DRIVEN (Dalio neutral prior for betas, zero-alpha beta-implied for alpha streams). NOT forecasts.",
               "mu_base": dict(zip(STREAMS, MU.tolist())), "vol_3y": dict(zip(STREAMS, vol.tolist())),
               "alpha_stream_regressions": BETAS, "composer_insample_vs_prior": comp_insample,
               "composer_sleeve_insample_sharpe": float(xc.mean() / xc.std() * math.sqrt(PPY))}


def prior_stats(w, mu, Sm, target=None):
    """PRIOR-DRIVEN mean/Sharpe of w, optionally scaled to ``target`` vol: non-BOXX streams x L; BOXX (if held)
    absorbs the remaining cash; any shortfall is borrowed at rf + spread."""
    nb = np.array([s != "BOXX" for s in STREAMS])
    Lx = 1.0 if target is None else target / portfolio_vol(w, Sm)
    wl = w.copy()
    wl[nb] = w[nb] * Lx
    rem = 1.0 - wl[nb].sum()
    wl[IX["BOXX"]] = max(rem, 0.0) if w[IX["BOXX"]] > 0 else 0.0
    cash = 1.0 - wl.sum()
    borrow = max(-cash, 0.0)
    sp = ibkr_spread_over_rf(borrow * NAV)
    m = float(wl @ mu + cash * RF - borrow * sp)
    s_ = portfolio_vol(wl, Sm)
    return {"vol": s_, "mean": m, "excess": m - RF, "sharpe": (m - RF) / s_, "leverage_applied": Lx,
            "gross": float(wl[nb].sum()), "borrow": borrow, "spread_over_rf": sp}


# --------------------------------------------------------------------------- risk structure
def plan_returns(Rw, w):
    return pd.Series(Rw.to_numpy() @ w, index=Rw.index)


EXPO, _ = exposures_from_mapping(STREAMS, BOXMAP)


def risk_block(w, Sm, Rw):
    eb = effective_bets(w, Sm, n_obs=len(Rw))
    prc = percent_risk_contributions(w, Sm)
    sl = {s: float(sum(prc[i] for i, st in enumerate(STREAMS) if SLEEVE_OF[st] == s)) for s in SLEEVES}
    dol = {s: float(sum(w[i] for i, st in enumerate(STREAMS) if SLEEVE_OF[st] == s)) for s in SLEEVES}
    # sleeve-level DR^2: each sleeve a composite stream
    used = [s for s in SLEEVES if dol[s] > 1e-12]
    B = np.zeros((N, len(used)))
    for j, s in enumerate(used):
        idx = [i for i, st in enumerate(STREAMS) if SLEEVE_OF[st] == s]
        B[idx, j] = w[idx] / w[idx].sum()
    v = np.array([dol[s] for s in used])
    ebs = effective_bets(v, B.T @ Sm @ B, n_obs=len(Rw))
    env = environment_balance(w, Sm, EXPO)
    pr = plan_returns(Rw, w)
    r2 = {f: float(np.corrcoef(pr, Rw[f])[0, 1] ** 2) for f in ("QQQ", "SPY")}
    eq_risk = float(env["risk_share"]["growth_up"] + env["risk_share"]["inflation_down"])  # equity streams split 50/50
    eq_stream_prc = float(sum(prc[i] for i, st in enumerate(STREAMS) if BOXMAP.get(st) == CANONICAL_MAP["equity"]))
    return {"vol": portfolio_vol(w, Sm), "gross": float(w.sum()), "neff": {r["measure"]: r["value"] for r in eb.rows()},
            "neff_flags": {r["measure"]: r["flag"] for r in eb.rows() if r["flag"]}, "n_streams": eb.n, "rho_bar": eb.rho_bar,
            "dr2_sleeve_level": ebs.dr2, "n_sleeves": ebs.n, "risk_share": sl, "dollar_share": dol,
            "env_risk_share": env["risk_share"], "env_unmapped": env["unmapped_risk_share"], "env_balance_score": env["balance_score"],
            "one_bet_r2": r2, "equity_stream_risk_share": eq_stream_prc,
            "stream_prc": {st: float(prc[i]) for i, st in enumerate(STREAMS) if abs(w[i]) > 1e-12}}


RB = {var: {c: risk_block(W[var][c], S, R) for c in CAND} for var in W}
RB_rob = {var: {c: risk_block(W[var][c], S_rob, R_rob) for c in CAND} for var in W}
PRIOR = {}
for var in W:
    PRIOR[var] = {}
    for c in CAND:
        d = {}
        for lab, (s_, a_) in {"base_s0.30": (0.30, 0.0), "s0.25": (0.25, 0.0), "s0.20": (0.20, 0.0),
                              "s0.30_alphaIR0.30": (0.30, 0.30)}.items():
            mu_, _ = mu_vector(s_, a_)
            d[lab] = {"native": prior_stats(W[var][c], mu_, S), "at_15pct_vol": prior_stats(W[var][c], mu_, S, 0.15)}
        PRIOR[var][c] = d
M["risk"] = RB
M["risk_robustness_longest_common_window"] = RB_rob
M["prior_driven_returns"] = PRIOR
M["post_hoc"][0]["spread_at_each_loan"] = {
    var: {c: {"native_borrow_usd": max(float(W[var][c].sum()) - 1.0, 0.0) * NAV, "native_spread_over_rf": spread_for(W[var][c]),
              "at_15_borrow_usd": PRIOR[var][c]["base_s0.30"]["at_15pct_vol"]["borrow"] * NAV,
              "at_15_spread_over_rf": PRIOR[var][c]["base_s0.30"]["at_15pct_vol"]["spread_over_rf"]} for c in CAND} for var in W}

# --------------------------------------------------------------------------- backtest A (real data, constant mix)
R_A = R_rob.copy()
rf_A = tbill_period_returns(dtb3.values, R_A.index)


def fixed(w):
    def f(S_):
        return w
    f.__name__ = "constant_mix_today_weights"
    return f


def bt(Rw, rfw, w, bench):
    cfg = BacktestConfig(allocator=fixed(w), window=2, min_periods=2, rebalance="M", cost_bps=5.0,
                         financing_spread=spread_for(w), max_leverage=CAP + 1e-9, periods_per_year=infer_periods_per_year(Rw.index))
    return run_backtest(Rw, cfg, rf=rfw, benchmark=bench)


BT_A = {}
for c in CAND:
    BT_A[c] = bt(R_A, rf_A, W["i"][c], R_A["SPY"])
BT_A["SPY"] = bt(R_A, rf_A, vec({"SPY": 1.0}), R_A["SPY"])
BT_Aii = {c: bt(R_A, rf_A, W["ii"][c], R_A["SPY"]) for c in CAND}


def mrow(b):
    m = b.metrics
    return {k: m[k] for k in ("start", "end", "cagr", "vol", "sharpe", "max_drawdown", "worst_year", "calmar", "total_return")}


M["backtest_A_real_constant_mix"] = {"basis": "CONSTANT-MIX of today's weights (hindsight), daily MTM, monthly rebalance, 5bp costs; "
                                              "Composer = IN-SAMPLE backtests (+live tail); basket = hindsight selection. IN-SAMPLE.",
                                     "proxy_i": {c: mrow(b) for c, b in BT_A.items()},
                                     "proxy_ii": {c: mrow(b) for c, b in BT_Aii.items()}}

# --------------------------------------------------------------------------- long history with proxies (B + replays)
LP = {"SPY": (), "QQQ": (), "IEF": (("VFITX", "2002-07-30", "Vanguard interm. Treasury fund"),),
      "TIP": (("VIPSX", "2003-12-05", "Vanguard Inflation-Protected fund"), ("VFITX", "2000-06-29", "interm. UST before VIPSX")),
      "TLT": (("VUSTX", "2002-07-30", "Vanguard long-term Treasury fund"),),
      "GLD": (("GC=F", "2004-11-18", "COMEX gold front-month, price only"),),
      "DBC": (("^SPGSCI", "2006-02-06", "S&P GSCI price index, no collateral yield"),)}
lv_long = {s: yl(s, p) for s, p in LP.items()}
for b in BASKET:
    lv_long[b] = lv_main[b]
lv_long["c_hg_actual"] = lv_main["c_hg"]
Llong = pd.DataFrame(lv_long).sort_index().loc[:END]
cal = Llong["SPY"].dropna().index
Rl = levels_to_returns(align_levels(Llong, "D", calendar=cal))
rf_l = tbill_period_returns(dtb3.values, Rl.index)
Rlex = Rl[FACT].sub(rf_l, axis=0)
fact_missing = {f: int(Rlex[f].loc["2000-03-10":].isna().sum()) for f in FACT}
Rlex0 = Rlex.fillna(0.0)   # LOCAL: missing factor (gold before 2000-08-30) = zero excess, flagged


def proxy_series(coefs):
    return rf_l + Rlex0.to_numpy() @ coefs


comp_coef, comp_rv, comp_r2 = ols(xc.to_numpy())
hg_coef, hg_rv, hg_r2 = ols(Xex["c_hg"].to_numpy())
Rl["c_proxy"] = proxy_series(comp_coef[1:])
Rl["c_hg_proxy"] = proxy_series(hg_coef[1:])
M["composer_beta_proxy"] = {"factors": FACT, "composite_betas": dict(zip(FACT, comp_coef[1:].tolist())),
                            "composite_r2": float(comp_r2), "composite_residual_vol": comp_rv,
                            "composite_insample_alpha_annual": float(comp_coef[0] * PPY),
                            "hg_betas": dict(zip(FACT, hg_coef[1:].tolist())), "hg_r2": float(hg_r2),
                            "missing_factor_days_from_2000_03_10_set_to_zero_excess": fact_missing}


def long_weights(w, variant_spcx="QQQ", available=None):
    """LOCAL: map a candidate's stream weights onto long-history streams: Composer -> c_proxy, BOXX -> cash,
    SPCX -> QQQ (or equal weight of the available basket names)."""
    d = {}
    for s, i in IX.items():
        x = w[i]
        if abs(x) < 1e-15 or s == "BOXX":
            continue
        if s in COMP:
            d["c_proxy"] = d.get("c_proxy", 0) + x
        elif s in BASKET or s == "QQQ":
            if variant_spcx == "QQQ":
                d["QQQ"] = d.get("QQQ", 0) + x
            else:
                for b in available:
                    d[b] = d.get(b, 0) + x / len(available)
        else:
            d[s] = d.get(s, 0) + x
    return d


RB_cols = ["SPY", "QQQ", "IEF", "TIP", "TLT", "GLD", "DBC", "c_proxy"]
R_B = Rl.loc[Rl.index > pd.Timestamp(LONG0), RB_cols].dropna(how="any").loc[:END]
rf_B = rf_l.reindex(R_B.index)
BT_B = {}
for c in CAND:
    d = long_weights(W["ii"][c])
    BT_B[c] = bt(R_B, rf_B, np.array([d.get(k, 0.0) for k in RB_cols]), R_B["SPY"])
BT_B["SPY"] = bt(R_B, rf_B, np.array([1.0 if k == "SPY" else 0.0 for k in RB_cols]), R_B["SPY"])
M["backtest_B_proxy_constant_mix"] = {
    "basis": "CONSTANT-MIX of today's weights (hindsight) 2006-2026, daily MTM, monthly rebalance; SPCX = QQQ; "
             "Composer = BETA PROXY (no switching logic, no residual) - NOT the symphonies. Treasury = T-bills. IN-SAMPLE.",
    "metrics": {c: mrow(b) for c, b in BT_B.items()},
    "calendar_years": {c: calendar_year_returns(b.returns, start_date=b.equity.index[0]).reset_index(names="year").to_dict(orient="records") for c, b in BT_B.items()}}

# --------------------------------------------------------------------------- stress replays
REPLAYS = {"tech_2000_02": ("2000-03-10", "2002-10-09"), "gfc_2008": SCENARIOS["gfc"][:2],
           "covid_2020": SCENARIOS["covid"][:2], "inflation_2022": SCENARIOS["inflation_2022"][:2]}
rp_rows = []
RP = {}
for key, (a, b) in REPLAYS.items():
    RP[key] = {}
    for c in CAND:
        for var in ("i", "ii"):
            if key in ("tech_2000_02", "gfc_2008") or var == "ii":
                d = long_weights(W[var][c], "QQQ")
                spx = "QQQ"
            else:
                avail = [x for x in BASKET if Rl[x].loc[pd.Timestamp(a):pd.Timestamp(b)].iloc[1:].notna().all()]
                d = long_weights(W[var][c], "basket", avail)
                spx = "EW " + "/".join(avail)
            res = replay_scenario(Rl, d, a, b, rebalance="none", rf_period=rf_l, missing="cash", label=f"{key} {c}")
            dc = {k: v for k, v in d.items() if k != "c_proxy"}
            res_cash = replay_scenario(Rl, dc, a, b, rebalance="none", rf_period=rf_l, missing="cash", label=f"{key} {c} composer-in-cash")
            row = {"scenario": key, "start": a, "end": b, "candidate": c, "spcx_proxy": var, "spcx_used": spx,
                   "cum_return": res["cum_return"], "max_drawdown": res["max_drawdown"], "loss_usd": res["cum_return"] * NAV,
                   "max_dd_usd": res["max_drawdown"] * NAV,
                   "cum_return_composer_in_tbills": res_cash["cum_return"], "max_dd_composer_in_tbills": res_cash["max_drawdown"],
                   "notes": "; ".join(res["notes"])}
            rp_rows.append(row)
            RP[key][f"{c}|{var}"] = {**row, "contributions": res["contributions"]}
    spy = replay_scenario(Rl, {"SPY": 1.0}, a, b, rf_period=rf_l, label=f"{key} SPY")
    rp_rows.append({"scenario": key, "start": a, "end": b, "candidate": "SPY 100%", "spcx_proxy": "-", "spcx_used": "-",
                    "cum_return": spy["cum_return"], "max_drawdown": spy["max_drawdown"], "loss_usd": spy["cum_return"] * NAV,
                    "max_dd_usd": spy["max_drawdown"] * NAV, "cum_return_composer_in_tbills": np.nan,
                    "max_dd_composer_in_tbills": np.nan, "notes": ""})
checks = []
for key in ("covid_2020", "inflation_2022"):
    a, b = REPLAYS[key]
    act = replay_scenario(Rl, {"c_hg_actual": 1.0}, a, b, label="hg actual")
    prx = replay_scenario(Rl, {"c_hg_proxy": 1.0}, a, b, rf_period=rf_l, label="hg proxy")
    checks.append({"scenario": key, "hg_actual_backtest_cum": act["cum_return"], "hg_actual_max_dd": act["max_drawdown"],
                   "hg_beta_proxy_cum": prx["cum_return"], "hg_beta_proxy_max_dd": prx["max_drawdown"]})
M["stress_replays"] = {"basis": "today's weights, buy-and-hold through the window, daily MTM; Composer = beta proxy; borrowing at rf (no spread)",
                       "rows": rp_rows, "composer_proxy_check": checks}

# --------------------------------------------------------------------------- forward bootstrap
H0 = R.to_numpy() - R.to_numpy().mean(axis=0)
H_base = H0 + MU / 252.0
Sig = np.cov(H0, rowvar=False)
S_st, st_info = stress_correlation(Sig, method="floor", rho=0.5, return_info=True)


def psd_root(A, inv=False):
    lam, V = np.linalg.eigh(A)
    lam = np.clip(lam, 1e-18, None)
    return (V * (lam ** (-0.5 if inv else 0.5))) @ V.T


H_st = H0 @ psd_root(Sig, inv=True) @ psd_root(S_st) + MU / 252.0
cfg = SimConfig(years=10, periods_per_year=252, n_paths=10_000, seed=20261006, method="bootstrap", mean_block=21)
FW = {}
for lab, H in (("base", H_base), ("corr_stress_rho0.5", H_st)):
    FW[lab] = {}
    for c in CAND:
        fr = run_forward(W["i"][c], cfg, history=H, rf=RF, spread=spread_for(W["i"][c]), chunk=250)
        st = {k: v for k, v in fr.stats.items() if not k.startswith("_")}
        FW[lab][c] = st
M["forward_bootstrap"] = {"basis": "IN-SAMPLE resampling of 2023-26 daily returns re-centred to PRIOR-DRIVEN means; not a forecast",
                          "stress_info": st_info, "results": FW}

# --------------------------------------------------------------------------- POST-HOC (labelled): ALT-2 without leverage
# Added after the first results showed ALT-2 needs ~2.1x gross; whether Casey accepts leverage is an open input.
w2u = W["i"]["ALT-2"] / W["i"]["ALT-2"].sum()
unlev = {"weights_sum": 1.0, "vol": portfolio_vol(w2u, S),
         "prior_base": prior_stats(w2u, MU, S), "prior_alphaIR0.30": prior_stats(w2u, mu_vector(0.30, 0.30)[0], S),
         "replays": {}}
for key, (a, b) in REPLAYS.items():
    if key in ("tech_2000_02", "gfc_2008"):
        d = long_weights(w2u, "QQQ")
    else:
        avail = [x for x in BASKET if Rl[x].loc[pd.Timestamp(a):pd.Timestamp(b)].iloc[1:].notna().all()]
        d = long_weights(w2u, "basket", avail)
    res = replay_scenario(Rl, d, a, b, rebalance="none", rf_period=rf_l, missing="cash", label=f"{key} ALT-2 unlevered")
    unlev["replays"][key] = {"cum_return": res["cum_return"], "max_drawdown": res["max_drawdown"]}
fr = run_forward(w2u, cfg, history=H_base, rf=RF, spread=spread_for(w2u), chunk=250)
unlev["forward_base"] = {k: v for k, v in fr.stats.items() if not k.startswith("_")}
M["post_hoc"].append({"item": "ALT-2 UNLEVERED (L = 1, same risk budgets): added after results, because ALT-2's 15% target needs "
                               "~2.1x gross and Casey's leverage tolerance is unknown", **unlev})

# worst realistic year table (computed from the predeclared outputs)
worst = []
for c in CAND:
    fb, fs = FW["base"][c], FW["corr_stress_rho0.5"][c]
    rps = [r for r in rp_rows if r["candidate"] == c and r["spcx_proxy"] == "i"]
    wr = min(rps, key=lambda r: r["max_drawdown"])
    cy = calendar_year_returns(BT_B[c].returns, start_date=BT_B[c].equity.index[0])
    cyf = cy[cy["complete"]]
    worst.append({"candidate": c, "boot_p05_year": fb["annual_return_quantiles"]["0.05"],
                  "boot_p05_year_usd": fb["annual_return_quantiles"]["0.05"] * NAV,
                  "boot_cvar05_year_usd": fb["cvar_0.05_annual"] * NAV,
                  "stress_p05_year": fs["annual_return_quantiles"]["0.05"], "stress_p05_year_usd": fs["annual_return_quantiles"]["0.05"] * NAV,
                  "worst_replay": wr["scenario"], "worst_replay_max_dd": wr["max_drawdown"], "worst_replay_max_dd_usd": wr["max_drawdown"] * NAV,
                  "worst_replay_composer_in_tbills_max_dd": wr["max_dd_composer_in_tbills"],
                  "backtestB_worst_calendar_year": float(cyf["return"].min()),
                  "backtestB_worst_calendar_year_label": int(cyf["return"].idxmin()),
                  "backtestB_worst_calendar_year_usd": float(cyf["return"].min()) * NAV})
M["worst_year_usd"] = worst

# --------------------------------------------------------------------------- SpaceX descriptive (post hoc, labelled)
try:
    sx = yl("SPCX")
    sxr = levels_to_returns(align_levels(pd.DataFrame({"SPCX": sx, "QQQ": lv_main["QQQ"]}).loc[:END], "D")).dropna()
    M["post_hoc"].append({"item": "SPCX ticker = Space Exploration Technologies Corp. (Nasdaq, first trade 2026-06-12); "
                                   "descriptive only, not used in any number",
                          "n_days": len(sxr), "ann_vol": float(sxr["SPCX"].std() * math.sqrt(252)),
                          "corr_QQQ": float(sxr.corr().iloc[0, 1]), "first": str(sxr.index[0].date()),
                          "cum_return": float((1 + sxr["SPCX"]).prod() - 1)})
except Exception as e:  # pragma: no cover
    M["post_hoc"].append({"item": "SPCX descriptive failed", "error": str(e)})

M["provenance"] = prov
report.write_json(M, OUT / "metrics.json")
print("metrics written")

# =========================================================================== charts
def fig_save(fig, name):
    fig.tight_layout()
    p = OUT / f"{name}.png"
    fig.savefig(p, dpi=150, facecolor=SURF)
    plt.close(fig)
    return str(p)


def rows_out(df, name):
    return report.write_rows(df, OUT / name)["csv"]


def chart(png, csv, caption):
    CHARTS.append({"png": png, "rows_csv": csv, "caption": caption})


# 1 risk vs dollars by sleeve
rows = []
for c in CAND:
    for s in SLEEVES:
        rows.append({"candidate": c, "sleeve": s, "dollar_share": RB["i"][c]["dollar_share"][s], "risk_share": RB["i"][c]["risk_share"][s],
                     "risk_share_spcx_qqq": RB["ii"][c]["risk_share"][s], "dollar_share_spcx_qqq": RB["ii"][c]["dollar_share"][s]})
df = pd.DataFrame(rows)
csv = rows_out(df, "c1_risk_vs_dollar_by_sleeve")
used = [s for s in SLEEVES if df.loc[df.sleeve == s, ["dollar_share", "risk_share"]].abs().to_numpy().max() > 1e-6]
fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), sharey=True)
for ax, c in zip(axes, CAND):
    d = df[df.candidate == c].set_index("sleeve").loc[used]
    y = np.arange(len(used))
    ax.barh(y + 0.2, d["dollar_share"] * 100, 0.38, color=GRID, label="dollars")
    ax.barh(y - 0.2, d["risk_share"] * 100, 0.38, color=CCOL[c], label="risk")
    for yi, v in zip(y, d["risk_share"]):
        ax.text(v * 100 + 1, yi - 0.2, f"{v:.0%}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y, used, fontsize=8)
    ax.invert_yaxis()
    report._style(ax, CAND_LABEL[c], "% of NAV (dollars, may exceed 100% if geared) / % of risk", "")
    ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="lower right")
chart(fig_save(fig, "c1_risk_vs_dollar_by_sleeve"), csv,
      "Risk share (Euler PRC) vs dollar share by sleeve, trailing-3y daily covariance, SPCX proxy (i) basket")

# 2 environment boxes
rows = []
for c in CAND:
    for var in ("i", "ii"):
        e = RB[var][c]
        rows.append({"candidate": c, "spcx_proxy": var, **{b: e["env_risk_share"][b] for b in BOXES}, "unmapped_cash": e["env_unmapped"],
                     "balance_score": e["env_balance_score"]})
df = pd.DataFrame(rows)
csv = rows_out(df, "c2_environment_box_risk")
fig, ax = plt.subplots(figsize=(8, 4))
d = df[df.spcx_proxy == "i"].set_index("candidate")
x = np.arange(len(BOXES))
for j, c in enumerate(CAND):
    ax.bar(x + (j - 1) * 0.27, d.loc[c, list(BOXES)] * 100, 0.25, color=CCOL[c], label=f"{CAND_LABEL[c]} (score {d.loc[c, 'balance_score']:.2f})")
ax.axhline(25, color=INK2, ls="--", lw=0.8)
ax.text(3.45, 26, "All Weather target 25%", fontsize=7, color=INK2, ha="right")
ax.set_xticks(x, ["growth up", "growth down", "inflation up", "inflation down"])
report._style(ax, "Share of risk by economic environment (All Weather boxes)", "", "% of risk")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2)
chart(fig_save(fig, "c2_environment_box_risk"), csv,
      "Environment-box risk shares (engine environment_balance; equity streams split 50/50 growth-up/inflation-down), SPCX proxy (i)")

# 3 effective bets
meas = [("dr2", "DR^2 (headline)"), ("equal_rho", "equal-rho"), ("pca_entropy", "PCA entropy"), ("prc_inverse_hhi", "1/sum PRC^2"),
        ("min_torsion", "min torsion")]
rows = []
for c in CAND:
    for var in ("i", "ii"):
        rows.append({"candidate": c, "spcx_proxy": var, **{m: RB[var][c]["neff"][m] for m, _ in meas},
                     "dr2_sleeve_level": RB[var][c]["dr2_sleeve_level"], "n_streams": RB[var][c]["n_streams"],
                     "dr2_longest_window": RB_rob[var][c]["neff"]["dr2"]})
df = pd.DataFrame(rows)
csv = rows_out(df, "c3_effective_bets")
fig, ax = plt.subplots(figsize=(8.5, 4))
d = df[df.spcx_proxy == "i"].set_index("candidate")
x = np.arange(len(meas) + 1)
for j, c in enumerate(CAND):
    vals = [d.loc[c, m] for m, _ in meas] + [d.loc[c, "dr2_sleeve_level"]]
    ax.bar(x + (j - 1) * 0.27, vals, 0.25, color=CCOL[c], label=CAND_LABEL[c])
    for xi, v in zip(x, vals):
        ax.text(xi + (j - 1) * 0.27, v + 0.1, f"{v:.1f}", ha="center", fontsize=6.5, color=INK2)
ax.set_xticks(x, [b for _, b in meas] + ["DR^2 sleeve-level"], fontsize=8)
report._style(ax, "Effective number of bets (Dalio's target: 15)", "", "N_eff")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2)
chart(fig_save(fig, "c3_effective_bets"), csv, "N_eff, five engine measures at stream level + DR^2 with sleeves as composite streams, trailing-3y daily")

# 4 one bet
rows = [{"candidate": c, "spcx_proxy": var, "r2_on_QQQ": RB[var][c]["one_bet_r2"]["QQQ"], "r2_on_SPY": RB[var][c]["one_bet_r2"]["SPY"],
         "equity_stream_risk_share": RB[var][c]["equity_stream_risk_share"]} for c in CAND for var in ("i", "ii")]
df = pd.DataFrame(rows)
csv = rows_out(df, "c4_one_bet")
fig, ax = plt.subplots(figsize=(7, 3.4))
d = df[df.spcx_proxy == "i"].set_index("candidate")
y = np.arange(3)
ax.barh(y + 0.18, d["r2_on_QQQ"] * 100, 0.34, color=[CCOL[c] for c in CAND])
ax.barh(y - 0.18, d["equity_stream_risk_share"] * 100, 0.34, color=GRID)
for yi, c in zip(y, CAND):
    ax.text(d.loc[c, "r2_on_QQQ"] * 100 + 1, yi + 0.18, f"{d.loc[c, 'r2_on_QQQ']:.0%} of variance = QQQ beta", va="center", fontsize=7, color=INK2)
    ax.text(d.loc[c, "equity_stream_risk_share"] * 100 + 1, yi - 0.18, f"{d.loc[c, 'equity_stream_risk_share']:.0%} of risk in equity streams",
            va="center", fontsize=7, color=INK2)
ax.set_yticks(y, [CAND_LABEL[c] for c in CAND], fontsize=8)
ax.invert_yaxis()
ax.set_xlim(0, 135)
report._style(ax, "How much of the plan is one bet (US/AI equity beta)?", "%", "")
chart(fig_save(fig, "c4_one_bet"), csv, "R^2 of each plan's daily returns on QQQ (one-factor) and the risk share of equity-mapped streams, trailing 3y")

# 5 equity curves A
rows = []
for c, b in BT_A.items():
    for dt, v in b.equity.items():
        rows.append({"date": dt.strftime("%Y-%m-%d"), "series": c, "equity": v, "drawdown": None})
df = pd.DataFrame(rows)
for c in BT_A:
    e = BT_A[c].equity
    df.loc[df.series == c, "drawdown"] = drawdown(e).to_numpy()
csv = rows_out(df, "c5_backtest_A_real_equity")
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.5, 5.6), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
for c in list(CAND) + ["SPY"]:
    e = BT_A[c].equity
    lab = CAND_LABEL.get(c, "SPY 100%") + f"  CAGR {BT_A[c].metrics['cagr']:.0%}, maxDD {BT_A[c].metrics['max_drawdown']:.0%}"
    a1.plot(e.index, e.to_numpy(), color=CCOL[c], lw=2 if c != "SPY" else 1.4, label=lab)
    a2.plot(e.index, drawdown(e).to_numpy() * 100, color=CCOL[c], lw=1.4)
a1.set_yscale("log")
report._style(a1, "Backtest A, real data, 2023-04..2026-09 (IN-SAMPLE, hindsight weights)", "", "growth of $1 (log)")
report._style(a2, "", "", "drawdown %")
a1.legend(frameon=False, fontsize=7, labelcolor=INK2)
chart(fig_save(fig, "c5_backtest_A_real_equity"), csv,
      "Constant-mix backtest A, real series for every sleeve (Composer IN-SAMPLE backtests, hindsight basket), daily MTM, with drawdowns")

# 6 equity curves B
rows = []
for c, b in BT_B.items():
    e = b.equity
    dd = drawdown(e)
    for dt, v, x_ in zip(e.index, e.to_numpy(), dd.to_numpy()):
        rows.append({"date": dt.strftime("%Y-%m-%d"), "series": c, "equity": v, "drawdown": x_})
df = pd.DataFrame(rows)
csv = rows_out(df, "c6_backtest_B_proxy_equity")
fig, (a1, a2) = plt.subplots(2, 1, figsize=(8.5, 5.8), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
for c in list(CAND) + ["SPY"]:
    e = BT_B[c].equity
    m = BT_B[c].metrics
    a1.plot(e.index, e.to_numpy(), color=CCOL[c], lw=2 if c != "SPY" else 1.4,
            label=CAND_LABEL.get(c, "SPY 100%") + f"  CAGR {m['cagr']:.1%}, maxDD {m['max_drawdown']:.0%}")
    a2.plot(e.index, drawdown(e).to_numpy() * 100, color=CCOL[c], lw=1.2)
a1.set_yscale("log")
report._style(a1, "Backtest B, 2006-2026 with PROXIES (Composer = beta proxy, SPCX = QQQ)", "", "growth of $1 (log)")
report._style(a2, "", "", "drawdown %")
a1.legend(frameon=False, fontsize=7, labelcolor=INK2)
chart(fig_save(fig, "c6_backtest_B_proxy_equity"), csv,
      "Constant-mix backtest B 2006-02..2026-09: Composer sleeve as a beta proxy (no switching), SPCX as QQQ, T-bills; IN-SAMPLE, log scale + drawdowns")

# 7 stress replays in $  (display: bar = peak-to-trough max drawdown, dot = end-of-window P&L)
df = pd.DataFrame(rp_rows)
csv = rows_out(df, "c7_stress_replays")
fig, ax = plt.subplots(figsize=(9, 4.4))
keys = list(REPLAYS)
x = np.arange(len(keys))
series = list(CAND) + ["SPY 100%"]
for j, c in enumerate(series):
    sub = df[(df.candidate == c) & (df.spcx_proxy.isin(["i", "-"]))].set_index("scenario").loc[keys]
    dd = sub["max_drawdown"] * NAV / 1e6
    end = sub["cum_return"] * NAV / 1e6
    xs = x + (j - 1.5) * 0.2
    ax.bar(xs, dd, 0.19, color=CCOL.get(c, INK2) if c != "SPY 100%" else GRID, label=CAND_LABEL.get(c, c))
    ax.plot(xs, end, "o", color=SURF, mec=INK, ms=4, zorder=3)
    for xi, v in zip(xs, dd):
        ax.text(xi, v - 0.4, f"{v:.1f}", ha="center", fontsize=6.5, color=INK2)
ax.plot([], [], "o", color=SURF, mec=INK, ms=4, label="end-of-window P&L")
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x, ["2000-02 tech bust", "2008 GFC", "2020 Covid", "2022 inflation"])
report._style(ax, "Stress replays on $18M: peak-to-trough loss (bar) and end-of-window P&L (dot)", "", "$M")
ax.legend(frameon=False, fontsize=7, labelcolor=INK2, loc="lower right")
chart(fig_save(fig, "c7_stress_replays"), csv,
      "Replays, today's weights buy-and-hold: 2000-02 and 2008 use QQQ for SPCX; Composer = beta proxy in every window; $ on $18M")

# 8 forward worst year
rows = []
for lab in FW:
    for c in CAND:
        st = FW[lab][c]
        q = st["annual_return_quantiles"]
        rows.append({"variant": lab, "candidate": c, "annual_p05": q["0.05"], "annual_p25": q["0.25"], "annual_p50": q["0.5"],
                     "annual_p75": q["0.75"], "annual_p95": q["0.95"], "p05_usd": q["0.05"] * NAV, "p_losing_year": st["p_losing_year"],
                     "cvar05_annual": st["cvar_0.05_annual"], "cagr10_p50": st["cagr_quantiles"]["0.5"], "cagr10_p05": st["cagr_quantiles"]["0.05"],
                     "maxdd10_p05": st["max_dd_quantiles"]["0.05"], "maxdd10_p50": st["max_dd_quantiles"]["0.5"]})
df = pd.DataFrame(rows)
csv = rows_out(df, "c8_forward_worst_year")
fig, ax = plt.subplots(figsize=(8.5, 4))
y = 0
ticks, tl = [], []
for c in CAND:
    for lab, a_ in (("base", 1.0), ("corr_stress_rho0.5", 0.55)):
        r_ = df[(df.variant == lab) & (df.candidate == c)].iloc[0]
        ax.plot([r_.annual_p05 * NAV / 1e6, r_.annual_p95 * NAV / 1e6], [y, y], color=CCOL[c], lw=2, alpha=a_)
        ax.plot([r_.annual_p25 * NAV / 1e6, r_.annual_p75 * NAV / 1e6], [y, y], color=CCOL[c], lw=7, alpha=a_, solid_capstyle="butt")
        ax.plot(r_.annual_p50 * NAV / 1e6, y, "o", color=SURF, mec=CCOL[c], ms=5)
        ax.text(r_.annual_p05 * NAV / 1e6, y + 0.28, f"p5 {r_.annual_p05 * NAV / 1e6:+.1f}M", fontsize=6.5, color=INK2, ha="center")
        ticks.append(y)
        tl.append(f"{c} {'base' if lab == 'base' else 'corr-stress'}")
        y += 1
    y += 0.5
ax.axvline(0, color=INK2, lw=0.8)
ax.set_yticks(ticks, tl, fontsize=8)
ax.invert_yaxis()
report._style(ax, "One-year P&L on $18M: bootstrap p5-p95 (thin), p25-p75 (thick), median (dot)", "$M", "")
chart(fig_save(fig, "c8_forward_worst_year"), csv,
      "Forward stationary bootstrap of 2023-26 daily returns re-centred to the PRIOR means (in-sample, not a forecast); corr-stress = every correlation floored at 0.5")

M["charts"] = CHARTS
report.write_json(M, OUT / "metrics.json")
print(json.dumps(CHARTS, indent=1))
