"""BLOCK probit_is — in-sample probits, conditional cut, oil–curve correlations,
Q3 PRIMARY effect-size-by-regime (spec v1 §4, oil-shock-recession-weight.md).

Re-runnable end to end from the frozen inputs (panel.csv, events.json) plus the
frozen copy of the live /recession-model JSON fetched 2026-09-15 (kept beside
this script; hard-coded fallback values if the file is absent). No network.
"""
import json, os, warnings
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm, rankdata
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = f"{ROOT}/blocks/probit_is"
os.makedirs(OUT, exist_ok=True)
warnings.filterwarnings("ignore")

P = pd.read_csv(f"{ROOT}/data/panel.csv", index_col="date", parse_dates=True)
EV = json.load(open(f"{ROOT}/data/events.json"))
LAST_USREC = P["usrec"].last_valid_index()                      # 2026-08
RESOLVED_BOUND = pd.Timestamp(EV["last_resolved_month_h12"] + "-01")   # 2025-08 = last USREC print − 12
SAMPLE_START = pd.Timestamp("1953-04-01")
HORIZONS = (6, 12, 18, 24)
OIL = {"w": "oil_12m_pct_w", "nopi": "nopi36_sum12"}
OIL_LABEL = {"w": "12m % chg winsorised ±100 (DECISION)", "nopi": "NOPI12 = nopi36_sum12 (confirmatory)"}
P["ff_pace"] = P["ff_12m_chg_bps"] / 100.0                       # pp
NUM = {}                                                         # numbers.json accumulator


def rec(key, value, definition):
    NUM[key] = {"value": value, "def": definition}
    return value


# ---------------------------------------------------------------- labels (§4)
u = P["usrec"].astype(float)
for h in HORIZONS:
    fut = pd.concat([u.shift(-k) for k in range(1, h + 1)], axis=1)
    P[f"yA_{h}"] = (fut.max(axis=1) >= 1).astype(float).where(fut.notna().all(axis=1))
    # Target A: usrec==1 in any of t+1..t+h.  Target B: same, but usrec_t==1 rows dropped.
    P[f"yB_{h}"] = P[f"yA_{h}"].where(u == 0)


def resolved_end(h):
    """t + h <= 2025-08  (spec §4 'Resolved', read literally)."""
    return RESOLVED_BOUND - pd.DateOffset(months=h)


def sample(h, target, oil_key=None, need_ff=False, start=SAMPLE_START, end=None):
    end = resolved_end(h) if end is None else min(end, resolved_end(h))
    cols = ["spread_gs", f"y{target}_{h}"]
    if oil_key:
        cols.append(OIL[oil_key])
    if need_ff:
        cols.append("ff_pace")
    d = P.loc[start:end, cols].dropna()
    return d


# ---------------------------------------------------------------- estimator
def auc_mw(p, y):
    p = np.asarray(p, float); y = np.asarray(y, int)
    r = rankdata(p)
    n1 = int(y.sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return None
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fit_probit(d, xcols, ycol, h):
    X = sm.add_constant(d[xcols], has_constant="add")
    y = d[ycol].astype(int)
    m = sm.Probit(y, X)
    r = m.fit(method="newton", maxiter=100, disp=0, cov_type="HAC", cov_kwds={"maxlags": max(h - 1, 0)})
    conv = bool(r.mle_retvals.get("converged", True))
    p = r.predict(X)
    out = {"params": {k: float(v) for k, v in r.params.items()},
           "hac_z": {k: float(v) for k, v in r.tvalues.items()},
           "hac_se": {k: float(v) for k, v in r.bse.items()},
           "auc": auc_mw(p, y), "pseudo_r2": float(1 - r.llf / r.llnull),
           "llf": float(r.llf), "n": int(len(y)), "n_pos": int(y.sum()),
           "converged": conv, "hac_maxlags": h - 1}
    return r, out


SPECS = {"a": ["spread_gs"], "b": ["spread_gs", "oil"], "c": ["oil"],
         "d": ["spread_gs", "ff_pace"], "e": ["spread_gs", "oil", "ff_pace"]}
SPEC_NAME = {"a": "curve", "b": "curve+oil", "c": "oil only", "d": "curve+FF", "e": "curve+oil+FF"}

fits = []          # list of dicts
fit_objs = {}      # (spec, oil_key, target, h) -> results
for h in HORIZONS:
    for target in ("A", "B"):
        for spec, cols in SPECS.items():
            for ok in (("w", "nopi") if "oil" in cols else (None,)):
                xcols = [OIL[ok] if c == "oil" else c for c in cols]
                d = sample(h, target, ok, need_ff="ff_pace" in cols)
                r, o = fit_probit(d, xcols, f"y{target}_{h}", h)
                o.update({"spec": spec, "spec_name": SPEC_NAME[spec], "oil": ok, "target": target, "h": h,
                          "sample": f"{d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}", "xcols": xcols})
                fits.append(o); fit_objs[(spec, ok, target, h)] = (r, d, xcols)
rec("fits_table", fits,
    "statsmodels Probit(method=newton,maxiter=100), cov_type=HAC maxlags=h-1 (Bartlett); "
    "Target A: y=1 if usrec==1 in t+1..t+h; Target B: same with usrec_t==1 rows excluded; "
    "sample 1953-04+ (1955-07+ when FF pace enters), resolved months only t+h<=2025-08; "
    "curve=spread_gs (GS10-TB3MS); oil = oil_12m_pct_w or nopi36_sum12; ff_pace = ff_12m_chg_bps/100 (pp); "
    "auc = Mann-Whitney on fitted p (in-sample); pseudo_r2 = 1-llf/llnull (McFadden)")


def get(spec, ok, target, h):
    return next(f for f in fits if f["spec"] == spec and f["oil"] == ok and f["target"] == target and f["h"] == h)


# ---------------------------------------------------------------- 3. deployed check (h=12, Target A)
live_path = f"{OUT}/live_recession_model_2026-09-15.json"
if os.path.exists(live_path):
    live = json.load(open(live_path))["horizons"]["12"]
else:  # frozen fallback (fetched 2026-09-15 from https://treasury-canary.onrender.com/recession-model)
    live = {"b0": -0.5595, "b1": -0.2665, "auc": 0.686, "n_obs": 528, "n_pos": 94}
rec("deployed_live_h12", {k: live[k] for k in ("b0", "b1", "auc", "n_obs", "n_pos")},
    "live /recession-model horizons[12] fetched 2026-09-15: naive-IRLS probit on monthly-mean DGS10-DGS3MO "
    "(daily, FRED DGS3MO starts 1981-09) with Target A labels for every month having h future USREC prints "
    "(no resolved-month rule; 540-month sample 1981-09..2026-08 => n_obs 528 at h=12)")

dep = {}
def naive_fit(d, xcol, ycol):
    X = sm.add_constant(d[[xcol]], has_constant="add")
    r = sm.Probit(d[ycol].astype(int), X).fit(method="newton", maxiter=100, disp=0)
    p = r.predict(X)
    return {"b0": float(r.params["const"]), "b1": float(r.params[xcol]), "auc": auc_mw(p, d[ycol].astype(int)),
            "n": int(len(d)), "n_pos": int(d[ycol].sum()), "sample": f"{d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}"}

# (i) this block's (a) Target A h=12 on spread_gs 1953-04+, resolved
a12 = get("a", None, "A", 12)
dep["study_spread_gs_1953_resolved"] = {"b0": a12["params"]["const"], "b1": a12["params"]["spread_gs"],
                                        "auc": a12["auc"], "n": a12["n"], "n_pos": a12["n_pos"], "sample": a12["sample"]}
# (ii) spread_gs restricted to 1982-01+, resolved (isolates the sample-window effect)
d = sample(12, "A", start=pd.Timestamp("1982-01-01"))
dep["spread_gs_1982_resolved"] = naive_fit(d, "spread_gs", "yA_12")
# (iii) spread_cmt (T10Y3M monthly mean = deployed basis) 1982-01+, resolved
d = P.loc["1982-01-01":resolved_end(12), ["spread_cmt", "yA_12"]].dropna()
dep["spread_cmt_1982_resolved"] = naive_fit(d, "spread_cmt", "yA_12")
# (iv) spread_cmt 1982-01+, deployed labelling (every month with 12 future USREC prints, t <= 2025-08)
d = P.loc["1982-01-01":LAST_USREC - pd.DateOffset(months=12), ["spread_cmt", "yA_12"]].dropna()
dep["spread_cmt_1982_deployed_labels"] = naive_fit(d, "spread_cmt", "yA_12")
dep["live"] = {"b0": live["b0"], "b1": live["b1"], "auc": live["auc"], "n": live["n_obs"], "n_pos": live["n_pos"],
               "sample": "1981-09..2025-08 (inferred from n_obs)"}
rec("deployed_reproduction_h12_targetA", dep,
    "ladder of naive probit fits P(usrec in t+1..t+12)=Phi(b0+b1*spread): study basis (spread_gs, 1953-04+, resolved) -> "
    "spread_gs 1982+ resolved -> spread_cmt (T10Y3M monthly mean) 1982+ resolved -> spread_cmt 1982+ with the deployed "
    "labelling (t+12 <= last USREC print) -> live values")

# ---------------------------------------------------------------- 4. conditional cut + correlations
cut = {}
dB = P.loc[SAMPLE_START:resolved_end(12), ["spread_gs", "oil_12m_pct", "yB_12", "usrec"]].dropna()
red = dB[dB["oil_12m_pct"] >= 50]
for name, mask in (("spread_gt_0.25", red["spread_gs"] > 0.25), ("spread_le_0.25", red["spread_gs"] <= 0.25)):
    s = red[mask]
    cut[name] = {"n_months": int(len(s)), "n_pos": int(s["yB_12"].sum()),
                 "p_onset_within_12": (float(s["yB_12"].mean()) if len(s) else None),
                 "months": [f"{i:%Y-%m}" for i in s.index]}
cut["all_D1_RED_targetB"] = {"n_months": int(len(red)), "n_pos": int(red["yB_12"].sum()),
                             "p_onset_within_12": float(red["yB_12"].mean()) if len(red) else None}
cut["base_rate_targetB_h12"] = {"n_months": int(len(dB)), "n_pos": int(dB["yB_12"].sum()), "p": float(dB["yB_12"].mean())}
cut["base_rate_by_spread"] = {"spread_gt_0.25": float(dB.loc[dB["spread_gs"] > 0.25, "yB_12"].mean()),
                              "spread_le_0.25": float(dB.loc[dB["spread_gs"] <= 0.25, "yB_12"].mean()),
                              "n_gt": int((dB["spread_gs"] > 0.25).sum()), "n_le": int((dB["spread_gs"] <= 0.25).sum())}
rec("conditional_cut_D1RED", cut,
    "Target B months (usrec_t=0), 1953-04..2024-08 (t+12<=2025-08), D1-RED ON = WTISPLC 12m % chg >= +50; "
    "P(onset within 12) = mean of yB_12 on those months, split by spread_gs > +0.25 vs <= +0.25")

# (b)'s marginal effect within each cut (spec §4 conditional cut): refit (b) Target B h=12 on each half
def dP_oil(params, spread, x0=0.0, shock=50.0, oilcol="oil_12m_pct_w", ff=None):
    eta0 = params["const"] + params["spread_gs"] * spread + params[oilcol] * x0 + (params.get("ff_pace", 0.0) * ff if ff is not None else 0.0)
    eta1 = eta0 + params[oilcol] * shock
    return float(norm.cdf(eta1) - norm.cdf(eta0))

cut_me = {}
for name, mask in (("spread_gt_0.25", dB["spread_gs"] > 0.25), ("spread_le_0.25", dB["spread_gs"] <= 0.25)):
    dd = P.loc[dB.index[mask], ["spread_gs", "oil_12m_pct_w", "yB_12"]].dropna()
    r, o = fit_probit(dd, ["spread_gs", "oil_12m_pct_w"], "yB_12", 12)
    cut_me[name] = {"oil_coef": o["params"]["oil_12m_pct_w"], "oil_hac_z": o["hac_z"]["oil_12m_pct_w"],
                    "dP_plus50_at_spread0": dP_oil(o["params"], 0.0), "dP_plus50_at_spread1": dP_oil(o["params"], 1.0),
                    "n": o["n"], "n_pos": o["n_pos"], "auc": o["auc"]}
rec("conditional_cut_b_marginal", cut_me,
    "(b) curve+oil_12m_pct_w, Target B h=12, refit separately on months with spread_gs > +0.25 and <= +0.25; "
    "dP = Phi(eta at oil=+50) - Phi(eta at oil=0) holding spread at the stated value")

REG = {"R0": ("1953-04-01", "1985-12-01"), "R1": ("1986-01-01", "2008-12-01"),
       "R2": ("2009-01-01", "2019-12-01"), "R3": ("2020-01-01", f"{LAST_USREC:%Y-%m-%d}"),
       "full": ("1953-04-01", f"{LAST_USREC:%Y-%m-%d}")}
corrs = {}
for k, (s, e) in REG.items():
    dd = P.loc[s:e, ["oil_12m_pct_w", "oil_12m_pct", "spread_gs", "nopi36_sum12"]].dropna()
    corrs[k] = {"window": f"{s[:7]}..{e[:7]}", "n": int(len(dd)),
                "corr_oil12w_spread": float(dd["oil_12m_pct_w"].corr(dd["spread_gs"])),
                "corr_oil12_unwinsorised_spread": float(dd["oil_12m_pct"].corr(dd["spread_gs"])),
                "corr_nopi12_spread": float(dd["nopi36_sum12"].corr(dd["spread_gs"]))}
rec("oil_curve_correlations", corrs,
    "Pearson corr(oil_12m_pct_w, spread_gs), corr(oil_12m_pct unwinsorised, spread_gs) and corr(nopi36_sum12, spread_gs) on all months in each regime block "
    "(signal-month regimes R0 1953-04..1985-12, R1 1986..2008, R2 2009..2019, R3 2020-01..2026-08; full = 1953-04..2026-08)")

# ---------------------------------------------------------------- 5. marginal effects (in-sample, descriptive)
def dme(res, xcols, fn):
    """delta-method SE of a scalar function of the params using the HAC covariance."""
    p0 = res.params.values.astype(float); names = list(res.params.index)
    f0 = fn(dict(zip(names, p0)))
    g = np.zeros(len(p0))
    for i in range(len(p0)):
        e = np.zeros(len(p0)); e[i] = 1e-5 * max(1.0, abs(p0[i]))
        g[i] = (fn(dict(zip(names, p0 + e))) - fn(dict(zip(names, p0 - e)))) / (2 * e[i])
    V = np.asarray(res.cov_params())
    se = float(np.sqrt(max(g @ V @ g, 0.0)))
    return {"dP": float(f0), "se": se, "ci90": [float(f0 - 1.645 * se), float(f0 + 1.645 * se)]}

me = {}
rb, _, _ = fit_objs[("b", "w", "B", 12)]
re_, _, _ = fit_objs[("e", "w", "B", 12)]
for sp in (0.0, 1.0):
    me[f"oil_plus50_spread{sp:g}_spec_b"] = dme(rb, None, lambda q: dP_oil(q, sp))
    me[f"oil_plus50_spread{sp:g}_spec_e_ff0"] = dme(re_, None, lambda q: dP_oil(q, sp, ff=0.0))
    me[f"ff_plus300bp_spread{sp:g}_spec_e_oil0"] = dme(re_, None, lambda q: float(
        norm.cdf(q["const"] + q["spread_gs"] * sp + q["ff_pace"] * 3.0) - norm.cdf(q["const"] + q["spread_gs"] * sp)))
    me[f"baseP_spread{sp:g}_oil0_spec_b"] = float(norm.cdf(rb.params["const"] + rb.params["spread_gs"] * sp))
rec("marginal_effects_insample_h12_targetB", me,
    "IN-SAMPLE, descriptive. dP(12m) for oil_12m_pct_w 0 -> +50 at spread_gs = 0 and +1pp from (b) and from (e) at ff_pace=0; "
    "dP for ff_pace 0 -> +3pp at oil=0 from (e); delta-method SE from the HAC covariance, 90% = ±1.645 se")

# ---------------------------------------------------------------- 6. Q3 PRIMARY effect-size-by-regime
q3 = {}
blocks = {"R0R1": (SAMPLE_START, pd.Timestamp("2008-12-01")), "R2R3": (pd.Timestamp("2009-01-01"), resolved_end(12))}
for k, (s, e) in blocks.items():
    dd = P.loc[s:e, ["spread_gs", "oil_12m_pct_w", "yB_12"]].dropna()
    y = dd["yB_12"]
    pos_months = [f"{i:%Y-%m}" for i in dd.index[y == 1]]
    # positive-label regions = contiguous runs of y==1
    runs = []
    for i, m in enumerate(dd.index):
        if y.iloc[i] == 1 and (i == 0 or y.iloc[i - 1] == 0):
            runs.append([f"{m:%Y-%m}", f"{m:%Y-%m}"])
        elif y.iloc[i] == 1:
            runs[-1][1] = f"{m:%Y-%m}"
    try:
        r, o = fit_probit(dd, ["spread_gs", "oil_12m_pct_w"], "yB_12", 12)
        # separation diagnostics
        p = r.predict(sm.add_constant(dd[["spread_gs", "oil_12m_pct_w"]], has_constant="add"))
        sep = {"converged": o["converged"], "max_abs_coef": float(np.max(np.abs(r.params.values))),
               "max_fitted_p": float(p.max()), "min_fitted_p": float(p.min()),
               "n_oil_nonzero": int((dd["oil_12m_pct_w"] != 0).sum()),
               "oil_range_on_positives": [float(dd.loc[y == 1, "oil_12m_pct_w"].min()), float(dd.loc[y == 1, "oil_12m_pct_w"].max())],
               "spread_range_on_positives": [float(dd.loc[y == 1, "spread_gs"].min()), float(dd.loc[y == 1, "spread_gs"].max())]}
        q3[k] = {"sample": f"{dd.index[0]:%Y-%m}..{dd.index[-1]:%Y-%m}", "n": o["n"], "n_pos": o["n_pos"],
                 "positive_regions": runs, "curve_coef": o["params"]["spread_gs"], "curve_hac_z": o["hac_z"]["spread_gs"],
                 "oil_coef": o["params"]["oil_12m_pct_w"], "oil_hac_z": o["hac_z"]["oil_12m_pct_w"],
                 "oil_hac_se": o["hac_se"]["oil_12m_pct_w"], "auc": o["auc"], "pseudo_r2": o["pseudo_r2"],
                 "dP_plus50_spread0": dme(r, None, lambda q: dP_oil(q, 0.0)),
                 "dP_plus50_spread1": dme(r, None, lambda q: dP_oil(q, 1.0)),
                 "separation_diagnostics": sep}
    except Exception as ex:  # noqa: BLE001
        q3[k] = {"sample": f"{s:%Y-%m}..{e:%Y-%m}", "n": int(len(dd)), "n_pos": int(y.sum()), "positive_regions": runs,
                 "error": repr(ex)}
# also the full-sample (b) for reference
fb = get("b", "w", "B", 12)
q3["full_1953_2024"] = {"sample": fb["sample"], "n": fb["n"], "n_pos": fb["n_pos"], "oil_coef": fb["params"]["oil_12m_pct_w"],
                        "oil_hac_z": fb["hac_z"]["oil_12m_pct_w"], "dP_plus50_spread0": me["oil_plus50_spread0_spec_b"]}
# identification verdict for R2+R3 (one positive region = one onset lead window; n_pos = 12 months from one event)
r23 = q3["R2R3"]
n_regions = len(r23["positive_regions"])
identified = ("error" not in r23) and r23["separation_diagnostics"]["converged"] and n_regions >= 2
r23["identification"] = {
    "n_positive_regions": n_regions,
    "verdict": "NOT IDENTIFIED as an oil effect" if not identified else "identified",
    "reason": ("all positive labels come from a single contiguous 12-month lead window before the 2020-03 onset (one event); "
               "the oil coefficient is fitted on one episode's oil path, so its sign and size are that episode's accident, not an effect size"
               if n_regions == 1 else "multiple independent positive regions")}
ratio = None
if "error" not in r23 and "error" not in q3["R0R1"] and q3["R0R1"]["dP_plus50_spread0"]["dP"] != 0:
    ratio = r23["dP_plus50_spread0"]["dP"] / q3["R0R1"]["dP_plus50_spread0"]["dP"]
q3["ratio_R2R3_over_R0R1_dP_spread0"] = ratio
q3["test_verdict"] = {
    "rule": "§4: R2+R3 marginal effect (dP for +50% oil at spread 0, Target B h=12) <= half of R0+R1 -> bigger-market argument cuts against oil",
    "R0R1_dP": q3["R0R1"].get("dP_plus50_spread0", {}).get("dP"),
    "R2R3_dP": r23.get("dP_plus50_spread0", {}).get("dP"),
    "ratio": ratio,
    "le_half": (ratio is not None and ratio <= 0.5),
    "R2R3_identified": identified,
    "verdict": ("R2+R3 point effect <= half of R0+R1 (ratio %.2f), BUT the R2+R3 fit is NOT identified (single 2020 lead window): "
                "report as 'unidentified / consistent with <= half', not as a measured shrinkage" % ratio)
               if (ratio is not None and ratio <= 0.5 and not identified) else
               ("R2+R3 point effect > half of R0+R1 (ratio %.2f) but NOT identified (single 2020 lead window): no verdict either way" % ratio)
               if (ratio is not None and not identified) else
               ("MET: ratio %.2f <= 0.5" % ratio if ratio is not None and ratio <= 0.5 else
                ("NOT met: ratio %.2f > 0.5" % ratio if ratio is not None else "R2+R3 fit failed"))}
rec("q3_effect_size_by_regime_PRIMARY", q3,
    "(b) curve+oil_12m_pct_w, Target B h=12, fitted separately on signal months 1953-04..2008-12 (R0+R1) and 2009-01..2024-08 "
    "(R2+R3; t+12<=2025-08). oil_coef per pct-point of winsorised 12m change; HAC z maxlags=11; dP = Phi(c+b_oil*50)-Phi(c) at "
    "spread_gs=0 (and +1pp), delta-method 90% CI from HAC cov. Identification = >=2 separate positive-label regions and convergence")

# interaction model 1959+ (energy share available)
di = P.loc["1959-01-01":resolved_end(12), ["spread_gs", "oil_12m_pct_w", "energy_share_pct", "yB_12"]].dropna()
es_mean = float(di["energy_share_pct"].mean())
di["oil_x_es"] = di["oil_12m_pct_w"] * (di["energy_share_pct"] - es_mean)
ri, oi = fit_probit(di, ["spread_gs", "oil_12m_pct_w", "oil_x_es"], "yB_12", 12)
# robustness: add the energy-share main effect (not in the spec formula; labelled)
di["es_c"] = di["energy_share_pct"] - es_mean
ri2, oi2 = fit_probit(di, ["spread_gs", "oil_12m_pct_w", "es_c", "oil_x_es"], "yB_12", 12)
def dP_at_share(q, share):
    b = q["oil_12m_pct_w"] + q["oil_x_es"] * (share - es_mean)
    c = q["const"] + q.get("es_c", 0.0) * (share - es_mean)
    return float(norm.cdf(c + b * 50) - norm.cdf(c))
es_now = float(P["energy_share_pct"].dropna().iloc[-1]); es_now_m = f"{P['energy_share_pct'].dropna().index[-1]:%Y-%m}"
es_1980 = float(P.loc["1980-06-01", "energy_share_pct"])
inter = {"sample": f"{di.index[0]:%Y-%m}..{di.index[-1]:%Y-%m}", "n": oi["n"], "n_pos": oi["n_pos"],
         "energy_share_sample_mean": es_mean,
         "spec_as_written": {"params": oi["params"], "hac_z": oi["hac_z"], "auc": oi["auc"], "pseudo_r2": oi["pseudo_r2"],
                             "interaction_hac_z": oi["hac_z"]["oil_x_es"],
                             "dP_plus50_spread0_at_share_1980_06": dme(ri, None, lambda q: dP_at_share(q, es_1980)),
                             "dP_plus50_spread0_at_share_mean": dme(ri, None, lambda q: dP_at_share(q, es_mean)),
                             "dP_plus50_spread0_at_share_latest": dme(ri, None, lambda q: dP_at_share(q, es_now))},
         "robustness_with_share_main_effect": {"params": oi2["params"], "hac_z": oi2["hac_z"], "auc": oi2["auc"],
                                               "interaction_hac_z": oi2["hac_z"]["oil_x_es"]},
         "share_1980_06": es_1980, "share_latest": es_now, "share_latest_month": es_now_m}
rec("q3_interaction_energy_share", inter,
    "Probit Target B h=12 on 1959-01..2024-08: curve + oil_12m_pct_w + oil_12m_pct_w*(energy_share_pct - sample mean); "
    "HAC z maxlags=11; dP for +50% oil at spread 0 evaluated at the 1980-06 share, the sample-mean share and the latest share. "
    "Robustness row adds the centred share main effect (not in the spec formula)")

# D1-RED episodes (§4 episode rule) and energy share at each start
on = ((P["oil_12m_pct"] >= 50) & (P["usrec"] == 0)).fillna(False)
on_in_rec = ((P["oil_12m_pct"] >= 50) & (P["usrec"] == 1)).fillna(False)
episodes = []
cur = None
last_on = None
for m in P.index[on]:
    gap = None if last_on is None else (m.year - last_on.year) * 12 + m.month - last_on.month - 1   # OFF months between
    if cur is None or gap > 6:
        if cur is not None:
            episodes.append(cur)
        cur = {"start": m, "end": m, "n_on": 1}
    else:
        cur["end"] = m; cur["n_on"] += 1
    last_on = m
if cur is not None:
    episodes.append(cur)
onsets = [pd.Timestamp(x + "-01") for x in EV["recession_onsets"]]
ep_rows = []
for e in episodes:
    s, en = e["start"], e["end"]
    nxt = [o for o in onsets if o > s]
    nxt = nxt[0] if nxt else None
    lead = None if nxt is None else (nxt.year - s.year) * 12 + nxt.month - s.month
    ep_rows.append({"start": f"{s:%Y-%m}", "end": f"{en:%Y-%m}", "n_on_months": e["n_on"],
                    "energy_share_pct_at_start": (float(P.loc[s, "energy_share_pct"]) if pd.notna(P.loc[s, "energy_share_pct"]) else None),
                    "oil_12m_pct_at_start": float(P.loc[s, "oil_12m_pct"]), "spread_gs_at_start": (float(P.loc[s, "spread_gs"]) if pd.notna(P.loc[s, "spread_gs"]) else None),
                    "next_onset": (f"{nxt:%Y-%m}" if nxt else None), "months_to_next_onset": lead,
                    "pending": bool(en > resolved_end(12))})
rec("d1_red_episode_starts_energy_share", ep_rows,
    "D1-RED episodes per §4: ON = WTISPLC 12m % chg >= +50 with usrec_t=0 (in-recession ON months excluded and counted as OFF "
    "for the gap rule); consecutive ON months <= 6 OFF months apart merge; start = first ON month. energy_share_pct = PCE energy / PCE (1959+). "
    "Outcome attachment is the Q1 block's job — months_to_next_onset here is descriptive only")
rec("d1_red_on_months_in_recession", [f"{m:%Y-%m}" for m in P.index[on_in_rec]],
    "D1-RED ON months with usrec_t=1 (listed, excluded from episodes)")

# ---------------------------------------------------------------- key numbers (PRIMARY for this block)
b12 = get("b", "w", "B", 12); b12A = get("b", "w", "A", 12); bn12 = get("b", "nopi", "B", 12)
e12 = get("e", "w", "B", 12); a12B = get("a", None, "B", 12)
KEY = {
    "IS_b_oil_coef_TargetB_h12": b12["params"]["oil_12m_pct_w"],
    "IS_b_oil_hac_z_TargetB_h12": b12["hac_z"]["oil_12m_pct_w"],
    "IS_b_auc_TargetB_h12": b12["auc"], "IS_a_auc_TargetB_h12": a12B["auc"],
    "IS_b_minus_a_auc_TargetB_h12": b12["auc"] - a12B["auc"],
    "IS_b_oil_coef_TargetA_h12": b12A["params"]["oil_12m_pct_w"], "IS_b_oil_hac_z_TargetA_h12": b12A["hac_z"]["oil_12m_pct_w"],
    "IS_b_nopi_coef_TargetB_h12": bn12["params"]["nopi36_sum12"], "IS_b_nopi_hac_z_TargetB_h12": bn12["hac_z"]["nopi36_sum12"],
    "IS_e_oil_coef_TargetB_h12": e12["params"]["oil_12m_pct_w"], "IS_e_oil_hac_z_TargetB_h12": e12["hac_z"]["oil_12m_pct_w"],
    "IS_e_ff_coef_TargetB_h12": e12["params"]["ff_pace"], "IS_e_ff_hac_z_TargetB_h12": e12["hac_z"]["ff_pace"],
    "dP_oil_plus50_spread0_IS": me["oil_plus50_spread0_spec_b"]["dP"], "dP_oil_plus50_spread1_IS": me["oil_plus50_spread1_spec_b"]["dP"],
    "dP_ff_plus300bp_spread0_IS": me["ff_plus300bp_spread0_spec_e_oil0"]["dP"], "dP_ff_plus300bp_spread1_IS": me["ff_plus300bp_spread1_spec_e_oil0"]["dP"],
    "Q3_R0R1_oil_coef": q3["R0R1"]["oil_coef"], "Q3_R0R1_oil_hac_z": q3["R0R1"]["oil_hac_z"], "Q3_R0R1_dP_plus50_spread0": q3["R0R1"]["dP_plus50_spread0"]["dP"],
    "Q3_R0R1_n": q3["R0R1"]["n"], "Q3_R0R1_n_pos": q3["R0R1"]["n_pos"],
    "Q3_R2R3_oil_coef": r23.get("oil_coef"), "Q3_R2R3_oil_hac_z": r23.get("oil_hac_z"), "Q3_R2R3_dP_plus50_spread0": r23.get("dP_plus50_spread0", {}).get("dP"),
    "Q3_R2R3_n": r23["n"], "Q3_R2R3_n_pos": r23["n_pos"], "Q3_R2R3_n_positive_regions": n_regions, "Q3_R2R3_identified": identified,
    "Q3_ratio_R2R3_over_R0R1": ratio, "Q3_verdict": q3["test_verdict"]["verdict"],
    "Q3_interaction_coef": oi["params"]["oil_x_es"], "Q3_interaction_hac_z": oi["hac_z"]["oil_x_es"],
    "corr_oil12w_spread_full": corrs["full"]["corr_oil12w_spread"],
    "corr_oil12w_spread_R0": corrs["R0"]["corr_oil12w_spread"], "corr_oil12w_spread_R1": corrs["R1"]["corr_oil12w_spread"],
    "corr_oil12w_spread_R2": corrs["R2"]["corr_oil12w_spread"], "corr_oil12w_spread_R3": corrs["R3"]["corr_oil12w_spread"],
    "cut_P_onset12_D1RED_spread_gt_0.25": cut["spread_gt_0.25"]["p_onset_within_12"], "cut_n_D1RED_spread_gt_0.25": cut["spread_gt_0.25"]["n_months"],
    "cut_P_onset12_D1RED_spread_le_0.25": cut["spread_le_0.25"]["p_onset_within_12"], "cut_n_D1RED_spread_le_0.25": cut["spread_le_0.25"]["n_months"],
    "deployed_live_b0_h12": live["b0"], "deployed_live_b1_h12": live["b1"],
    "study_a_TargetA_b0_h12": a12["params"]["const"], "study_a_TargetA_b1_h12": a12["params"]["spread_gs"],
    "repro_spread_cmt_1982_deployed_labels_b0": dep["spread_cmt_1982_deployed_labels"]["b0"],
    "repro_spread_cmt_1982_deployed_labels_b1": dep["spread_cmt_1982_deployed_labels"]["b1"],
}
NUM["KEY_NUMBERS"] = {"value": KEY, "def": "headline numbers; each is a copy of an entry above (see the matching key's def)"}
json.dump(NUM, open(f"{OUT}/numbers.json", "w"), indent=1, default=float)

# ---------------------------------------------------------------- figures
SURF, BAND, GRID, INK, INK2 = "#fcfcfb", "#e5e4e0", "#e6e5e1", "#0b0b0b", "#52514e"
C_BLUE, C_ORANGE, C_AQUA, C_YELLOW, C_VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"
plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "axes.facecolor": SURF, "figure.facecolor": SURF, "savefig.facecolor": SURF})
rec_spans = [(pd.Timestamp(s + "-01"), pd.Timestamp(e + "-01")) for s, e in zip(EV["recession_onsets"], EV["recession_ends"])]


def style(ax):
    ax.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def shade(ax):
    for s, e in rec_spans:
        ax.axvspan(s, e, color=BAND, alpha=0.6, lw=0)


# fig_is_coefs.png — 4 panels: (transform × target); series (b) orange, (e) violet; x = horizon
fig, axes = plt.subplots(4, 1, figsize=(11, 20))
panels = [("w", "A"), ("w", "B"), ("nopi", "A"), ("nopi", "B")]
for ax, (ok, tg) in zip(axes, panels):
    style(ax); ax.axhline(0, color=INK2, lw=1)
    for spec, col, off, mk in (("b", C_ORANGE, -0.35, "o"), ("e", C_VIOLET, 0.35, "s")):
        xs, ys, lo, hi = [], [], [], []
        for h in HORIZONS:
            f = get(spec, ok, tg, h); c = f["params"][OIL[ok]]; se = f["hac_se"][OIL[ok]]
            xs.append(h + off); ys.append(c); lo.append(c - 1.645 * se); hi.append(c + 1.645 * se)
        ax.errorbar(xs, ys, yerr=[np.array(ys) - np.array(lo), np.array(hi) - np.array(ys)], fmt=mk, color=col, ms=9,
                    lw=2, capsize=5, label=f"({spec}) {SPEC_NAME[spec]}")
        for x, y_, h in zip(xs, ys, HORIZONS):
            f = get(spec, ok, tg, h)
            ax.annotate(f"z={f['hac_z'][OIL[ok]]:.1f}", (x, y_), textcoords="offset points", xytext=(-14, 0) if spec == "b" else (14, 0),
                        ha="right" if spec == "b" else "left", va="center", fontsize=8, color=INK2)
    ax.set_xticks(list(HORIZONS)); ax.set_xlabel("horizon h (months)")
    ax.set_ylabel("oil coefficient (probit index per unit)")
    ax.set_title(f"Oil coefficient by horizon — {OIL_LABEL[ok]}, Target {tg}"
                 + (" (deployed label)" if tg == "A" else " (onset-lead label)"), loc="left", color=INK, fontsize=11)
    lo_, hi_ = ax.get_ylim(); ax.set_ylim(lo_, hi_ + 0.28 * (hi_ - lo_))
    ax.legend(loc="upper left", ncol=2, frameon=False)
fig.suptitle("In-sample probit oil coefficients with Newey–West HAC 90% bars (maxlags = h−1)\n"
             "curve = GS10−TB3MS; sample 1953-04+ (1955-07+ with Fed-funds pace), resolved months t+h ≤ 2025-08", x=0.01, ha="left", color=INK2, fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.965)); fig.savefig(f"{OUT}/fig_is_coefs.png", dpi=150); plt.close(fig)

# fig_energy_share.png — energy share 1959+ with NBER bands and D1-RED episode starts
fig, ax = plt.subplots(figsize=(11, 5)); style(ax); shade(ax)
es = P["energy_share_pct"].dropna()
ax.plot(es.index, es.values, color=C_YELLOW, lw=2, label="energy share of PCE (%)")
first = True
k_lab = 0
for e in ep_rows:
    s = pd.Timestamp(e["start"] + "-01")
    if s < es.index[0]:
        continue
    v = e["energy_share_pct_at_start"]
    ax.plot([s], [v], marker="^", ms=10, color=C_ORANGE, mec=INK, mew=0.6, ls="none", label="D1-RED episode start" if first else None)
    up = (k_lab % 2 == 0); k_lab += 1
    ax.annotate(f"{e['start']}\n{v:.1f}%", (s, v), textcoords="offset points", xytext=(0, 12 if up else -26), ha="center", fontsize=8, color=INK)
    first = False
ax.set_ylabel("% of personal consumption expenditure"); ax.set_ylim(es.min() - 0.5, es.max() + 1.2)
fig.suptitle("Energy's share of consumer spending has roughly halved since 1980 — D1-RED oil episodes marked at their start month", x=0.01, ha="left", color=INK, fontsize=12)
ax.set_title("FRED DNRGRC1M027SBEA / PCE, monthly, 1959-01..%s; NBER recessions shaded; D1-RED = WTISPLC 12m %% change ≥ +50, usrec=0, §4 episode rule" % es_now_m,
             loc="left", fontsize=9, color=INK2)
ax.legend(loc="upper right", frameon=False)
fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(f"{OUT}/fig_energy_share.png", dpi=150); plt.close(fig)

# fig_regime_effect.png — ΔP for +50% oil at spread 0 by regime block (Q3 primary), with identification status
fig, ax = plt.subplots(figsize=(11, 5)); style(ax); ax.axhline(0, color=INK2, lw=1)
labels = ["R0+R1\n1953-04..2008-12", "R2+R3\n2009-01..2024-08", "full\n1953-04..2024-08"]
vals = [q3["R0R1"]["dP_plus50_spread0"], r23.get("dP_plus50_spread0"), me["oil_plus50_spread0_spec_b"]]
for i, (lab, v) in enumerate(zip(labels, vals)):
    if v is None:
        continue
    ok_id = (i != 1) or identified
    col = C_ORANGE if ok_id else "#8a8985"; mk = "o" if ok_id else "X"
    ax.errorbar([i], [v["dP"] * 100], yerr=[[(v["dP"] - v["ci90"][0]) * 100], [(v["ci90"][1] - v["dP"]) * 100]], fmt=mk, ms=11, color=col, lw=2, capsize=6)
    ax.annotate(f"ΔP = {v['dP']*100:+.1f}pp" + ("" if ok_id else "\nNOT IDENTIFIED\n(one event: 2020-03 window)"), (i, v["dP"] * 100),
                textcoords="offset points", xytext=(18, 0), ha="left", va="center", fontsize=9, color=INK)
ax.set_xticks(range(3)); ax.set_xticklabels(labels); ax.set_xlim(-0.5, 2.9)
ax.set_ylabel("ΔP(recession within 12m), percentage points")
fig.suptitle("Q3 primary: change in 12-month recession odds from a +50% oil move at a flat-zero curve, by regime block", x=0.01, ha="left", color=INK, fontsize=12)
ax.set_title("(b) curve + winsorised 12m oil change, Target B, in-sample, delta-method 90% bars from HAC cov (lags 11); grey X = fit not identified",
             loc="left", fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(f"{OUT}/fig_regime_effect.png", dpi=150); plt.close(fig)

# ---------------------------------------------------------------- results.md
L = []
L.append("# probit_is — in-sample probits, conditional cut, oil–curve correlation, Q3 effect-size-by-regime\n")
L.append(f"Inputs: panel.csv (frozen), events.json; sample 1953-04+ (1955-07+ when FF pace enters); resolved months t+h ≤ {RESOLVED_BOUND:%Y-%m}; "
         "curve = spread_gs (GS10−TB3MS). Estimator: statsmodels Probit, Newton, maxiter 100; z = Newey–West HAC, maxlags h−1 (naive z never shown). "
         "AUC = Mann–Whitney on fitted p (in-sample). All numbers in numbers.json.\n")
L.append("## 1. Fits per horizon\n")
for h in HORIZONS:
    L.append(f"### h = {h}  (sample end {resolved_end(h):%Y-%m}; HAC maxlags {h-1})\n")
    L.append("| target | spec | oil transform | curve coef (z) | oil coef (z) | FF pace coef (z) | AUC | McFadden R² | n | n_pos |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for tg in ("A", "B"):
        for f in [x for x in fits if x["h"] == h and x["target"] == tg]:
            def cz(name):
                return f"{f['params'][name]:+.4f} ({f['hac_z'][name]:+.2f})" if name in f["params"] else "—"
            oilc = OIL.get(f["oil"]) if f["oil"] else None
            L.append(f"| {tg} | ({f['spec']}) {f['spec_name']} | {OIL_LABEL[f['oil']].split(' (')[0] if f['oil'] else '—'} | {cz('spread_gs')} | "
                     f"{cz(oilc) if oilc else '—'} | {cz('ff_pace')} | {f['auc']:.3f} | {f['pseudo_r2']:.3f} | {f['n']} | {f['n_pos']} |")
    L.append("")
L.append("Oil coefficient units: per percentage point of 12m change (winsorised) or per log-pct of NOPI12; FF pace per pp of 12m change in the funds rate.\n")

L.append("## 2. Deployed-model check (h = 12, Target A)\n")
L.append("| fit | spread basis | sample | labels | b0 | b1 | AUC | n | n_pos |")
L.append("|---|---|---|---|---|---|---|---|---|")
rows = [("this block (a)", "GS10−TB3MS", dep["study_spread_gs_1953_resolved"], "resolved"),
        ("(a) 1982+", "GS10−TB3MS", dep["spread_gs_1982_resolved"], "resolved"),
        ("(a) 1982+", "T10Y3M monthly mean (deployed basis)", dep["spread_cmt_1982_resolved"], "resolved"),
        ("(a) 1982+, deployed labels", "T10Y3M monthly mean", dep["spread_cmt_1982_deployed_labels"], "t+12 ≤ last USREC print"),
        ("LIVE /recession-model", "DGS10−DGS3MO daily → monthly mean", dep["live"], "t+12 ≤ last USREC print")]
for nm, basis, r_, lab in rows:
    L.append(f"| {nm} | {basis} | {r_['sample']} | {lab} | {r_['b0']:+.4f} | {r_['b1']:+.4f} | {r_['auc']:.3f} | {r_['n']} | {r_['n_pos']} |")
L.append("")
dl = dep['spread_cmt_1982_deployed_labels']
L.append(f"Reading: the live fit (b0 {live['b0']:+.4f}, b1 {live['b1']:+.4f}) is reproduced to within |Δb1| = {abs(dl['b1']-live['b1']):.4f} and |Δb0| = {abs(dl['b0']-live['b0']):.4f} "
         f"by the T10Y3M-basis fit on 1982+ with the deployed labelling (b0 {dl['b0']:+.4f}, b1 {dl['b1']:+.4f}); the residual is the 4 months "
         "1981-09..1981-12 (n 524 vs 528, n_pos 90 vs 94: those four months lie inside the 1981-08..1982-11 recession, so under Target A they carry positive labels) that FRED's daily DGS3MO has and the panel's T10Y3M does not, "
         "plus daily-mean vs monthly-print rounding. The study's own (a) on GS10−TB3MS from 1953-04 gives a steeper slope "
         f"(b1 {a12['params']['spread_gs']:+.4f}): the 1950s–70s add six recessions preceded by shallow inversions on the discount-basis bill series, "
         "and the discount basis sits 20–40bp below bond-equivalent, both of which push the slope down. Differences are expected; no agreement is forced.\n")

L.append("## 3. Conditional cut (descriptive) and oil–curve correlation\n")
L.append(f"Target B months 1953-04..{resolved_end(12):%Y-%m}, D1-RED ON = WTISPLC 12m % change ≥ +50 with usrec_t = 0.\n")
L.append("| cut | n ON months | n with onset within 12 | P(onset within 12) | base rate on same cut (all months) | ON months |")
L.append("|---|---|---|---|---|---|")
for k, lab in (("spread_gt_0.25", "spread_gs > +0.25 (curve not flat)"), ("spread_le_0.25", "spread_gs ≤ +0.25 (flat/inverted)")):
    c = cut[k]; br = cut["base_rate_by_spread"]["spread_gt_0.25" if "gt" in k else "spread_le_0.25"]
    L.append(f"| {lab} | {c['n_months']} | {c['n_pos']} | {c['p_onset_within_12']*100 if c['p_onset_within_12'] is not None else float('nan'):.1f}% | {br*100:.1f}% | {', '.join(c['months'])} |")
L.append(f"| all D1-RED | {cut['all_D1_RED_targetB']['n_months']} | {cut['all_D1_RED_targetB']['n_pos']} | {cut['all_D1_RED_targetB']['p_onset_within_12']*100:.1f}% | {cut['base_rate_targetB_h12']['p']*100:.1f}% | |")
L.append("")
L.append("(b) refit on each half (Target B, h = 12):\n")
L.append("| cut | oil coef (HAC z) | ΔP +50% oil @ spread 0 | @ +1pp | AUC | n | n_pos |")
L.append("|---|---|---|---|---|---|---|")
for k, lab in (("spread_gt_0.25", "spread_gs > +0.25"), ("spread_le_0.25", "spread_gs ≤ +0.25")):
    c = cut_me[k]
    L.append(f"| {lab} | {c['oil_coef']:+.4f} ({c['oil_hac_z']:+.2f}) | {c['dP_plus50_at_spread0']*100:+.1f}pp | {c['dP_plus50_at_spread1']*100:+.1f}pp | {c['auc']:.3f} | {c['n']} | {c['n_pos']} |")
L.append("")
L.append("| regime (signal months) | window | n | corr(oil 12m % w, spread_gs) | corr(oil 12m % unwinsorised, spread_gs) | corr(NOPI12, spread_gs) |")
L.append("|---|---|---|---|---|---|")
for k in ("R0", "R1", "R2", "R3", "full"):
    c = corrs[k]; L.append(f"| {k} | {c['window']} | {c['n']} | {c['corr_oil12w_spread']:+.3f} | {c['corr_oil12_unwinsorised_spread']:+.3f} | {c['corr_nopi12_spread']:+.3f} |")
L.append("")
L.append("Notes: the ≤ +0.25 cut's six D1-RED months are ONE episode (1979-08..1980-01, all inside the 1980-02 lead window) — 100% is one event, not six. "
         "The negative oil–curve correlation is concentrated in R0 (1974, 1979–80: oil up while the curve inverted); in R3 it flips to +0.63 "
         "(2021–22 oil rose while the curve was still steep, then oil fell as it inverted), which is why the 2022 episode cannot borrow the 1970s' curve confounding. "
         "The spec's quoted full-sample −0.13 is on a different window/transform; the frozen panel gives −0.10 winsorised on 1953-04..2026-08.\n")

L.append("## 4. Marginal effects — IN-SAMPLE, descriptive (decision-relevant version comes from the walk-forward block)\n")
L.append("Target B, h = 12, decision transform. ΔP = Φ(η + β·shock) − Φ(η); delta-method 90% CI from the HAC covariance.\n")
L.append("| shock | spec | at spread 0 | at spread +1pp |")
L.append("|---|---|---|---|")
def fmt(v): return f"{v['dP']*100:+.1f}pp [{v['ci90'][0]*100:+.1f}, {v['ci90'][1]*100:+.1f}]"
L.append(f"| oil 12m % 0 → +50 | (b) curve+oil | {fmt(me['oil_plus50_spread0_spec_b'])} | {fmt(me['oil_plus50_spread1_spec_b'])} |")
L.append(f"| oil 12m % 0 → +50 | (e) curve+oil+FF (FF pace 0) | {fmt(me['oil_plus50_spread0_spec_e_ff0'])} | {fmt(me['oil_plus50_spread1_spec_e_ff0'])} |")
L.append(f"| FF pace 0 → +300bp | (e) (oil 0) | {fmt(me['ff_plus300bp_spread0_spec_e_oil0'])} | {fmt(me['ff_plus300bp_spread1_spec_e_oil0'])} |")
L.append(f"\nBase P at oil 0 from (b): spread 0 → {me['baseP_spread0_oil0_spec_b']*100:.1f}%, spread +1pp → {me['baseP_spread1_oil0_spec_b']*100:.1f}%.\n")

L.append("## 5. Q3 PRIMARY — effect size by regime (Target B, h = 12, (b) curve + winsorised 12m oil)\n")
L.append("| block | sample | n | n_pos | positive-label regions | curve coef (z) | oil coef (HAC z) | ΔP +50% oil @ spread 0 [90%] | @ +1pp | AUC |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
for k in ("R0R1", "R2R3"):
    q = q3[k]
    if "error" in q:
        L.append(f"| {k} | {q['sample']} | {q['n']} | {q['n_pos']} | {len(q['positive_regions'])} | fit failed: {q['error']} | | | | |"); continue
    regs = "; ".join(f"{a}..{b}" for a, b in q["positive_regions"])
    L.append(f"| {k} | {q['sample']} | {q['n']} | {q['n_pos']} | {len(q['positive_regions'])}: {regs} | {q['curve_coef']:+.4f} ({q['curve_hac_z']:+.2f}) | "
             f"{q['oil_coef']:+.4f} ({q['oil_hac_z']:+.2f}) | {fmt(q['dP_plus50_spread0'])} | {fmt(q['dP_plus50_spread1'])} | {q['auc']:.3f} |")
L.append(f"| full | {q3['full_1953_2024']['sample']} | {q3['full_1953_2024']['n']} | {q3['full_1953_2024']['n_pos']} | | | "
         f"{q3['full_1953_2024']['oil_coef']:+.4f} ({q3['full_1953_2024']['oil_hac_z']:+.2f}) | {fmt(me['oil_plus50_spread0_spec_b'])} | {fmt(me['oil_plus50_spread1_spec_b'])} | {fb['auc']:.3f} |")
L.append("")
sd = r23.get("separation_diagnostics", {})
L.append("Sample columns show the first/last non-recession month in each block (Target B drops usrec_t = 1 rows: 2008-01..2009-06 are in recession, so R0+R1 ends 2007-12 and R2+R3 starts 2009-07). "
         "R0+R1's first region 1953-04..1953-07 is the 1953-08 onset's lead window truncated by the curve's start.\n")
L.append(f"**Is the R2+R3 fit identified?** {r23['identification']['verdict']}. n_pos = {r23['n_pos']} months, all in {len(r23['positive_regions'])} contiguous region "
         f"({'; '.join(a+'..'+b for a, b in r23['positive_regions'])}) = the 12-month lead window of the single 2020-03 onset. Converged: {sd.get('converged')}; "
         f"max |coef| {sd.get('max_abs_coef', float('nan')):.3f}; fitted p range [{sd.get('min_fitted_p', float('nan')):.3f}, {sd.get('max_fitted_p', float('nan')):.3f}]; "
         f"oil_12m_pct_w on the positive months ranged {sd.get('oil_range_on_positives', ['?','?'])[0]:+.1f}..{sd.get('oil_range_on_positives', ['?','?'])[1]:+.1f}; "
         f"non-zero oil months {sd.get('n_oil_nonzero')}. {r23['identification']['reason']}.\n")
L.append(f"**§4 test verdict:** {q3['test_verdict']['verdict']}. Ratio R2+R3 / R0+R1 of ΔP(+50% oil, spread 0) = "
         f"{('%.2f' % ratio) if ratio is not None else 'n/a'}.\n")
L.append("### Interaction: oil × (energy share − mean), 1959+\n")
L.append(f"Sample {inter['sample']}, n {inter['n']}, n_pos {inter['n_pos']}, energy-share sample mean {es_mean:.2f}%.\n")
L.append("| model | curve (z) | oil (z) | share main (z) | oil×share (HAC z) | AUC |")
L.append("|---|---|---|---|---|---|")
sw = inter["spec_as_written"]; rb_ = inter["robustness_with_share_main_effect"]
L.append(f"| as written (spec §4) | {sw['params']['spread_gs']:+.4f} ({sw['hac_z']['spread_gs']:+.2f}) | {sw['params']['oil_12m_pct_w']:+.4f} ({sw['hac_z']['oil_12m_pct_w']:+.2f}) | — | "
         f"{sw['params']['oil_x_es']:+.4f} ({sw['hac_z']['oil_x_es']:+.2f}) | {sw['auc']:.3f} |")
L.append(f"| + share main effect (robustness, not in spec) | {rb_['params']['spread_gs']:+.4f} ({rb_['hac_z']['spread_gs']:+.2f}) | {rb_['params']['oil_12m_pct_w']:+.4f} ({rb_['hac_z']['oil_12m_pct_w']:+.2f}) | "
         f"{rb_['params']['es_c']:+.4f} ({rb_['hac_z']['es_c']:+.2f}) | {rb_['params']['oil_x_es']:+.4f} ({rb_['hac_z']['oil_x_es']:+.2f}) | {rb_['auc']:.3f} |")
L.append("")
L.append(f"Implied ΔP for +50% oil at spread 0 (as-written model): at the 1980-06 share ({es_1980:.2f}%) {fmt(sw['dP_plus50_spread0_at_share_1980_06'])}; "
         f"at the sample-mean share ({es_mean:.2f}%) {fmt(sw['dP_plus50_spread0_at_share_mean'])}; at the latest share ({es_now:.2f}%, {es_now_m}) {fmt(sw['dP_plus50_spread0_at_share_latest'])}.\n")
L.append("Caveat on the interaction: the energy share is above 7% only in 1973–85, so oil×share is identified mainly by the 1974 and 1979–80 episodes — the same episodes "
         "that carry the R0 oil effect. A positive interaction therefore says 'oil mattered when the share was high (the 1970s)', not that the share is the causal channel; "
         "the point estimate at today's share (−3pp) is an extrapolation below the share of every scored onset except 2020-03. Consumption share, not GDP share (§7 P2 #3 open).\n")
L.append("### Energy share at each D1-RED episode start (plot-ready)\n")
L.append("| episode start | last ON | ON months | oil 12m % at start | spread_gs at start | energy share % at start | next onset | months to it | pending |")
L.append("|---|---|---|---|---|---|---|---|---|")
for e in ep_rows:
    L.append(f"| {e['start']} | {e['end']} | {e['n_on_months']} | {e['oil_12m_pct_at_start']:+.1f} | "
             f"{(('%+.2f' % e['spread_gs_at_start']) if e['spread_gs_at_start'] is not None else 'n/a')} | "
             f"{(('%.2f' % e['energy_share_pct_at_start']) if e['energy_share_pct_at_start'] is not None else 'n/a (pre-1959)')} | "
             f"{e['next_onset'] or '—'} | {e['months_to_next_onset'] if e['months_to_next_onset'] is not None else '—'} | {'yes' if e['pending'] else ''} |")
L.append(f"\nD1-RED ON months inside recessions (excluded from episodes): {', '.join(NUM['d1_red_on_months_in_recession']['value'])}.\n")

L.append("## Figures\n")
L.append("- `fig_is_coefs.png` — oil coefficient with HAC 90% bars by horizon, (b) vs (e), four panels (transform × target): the oil coefficient is positive and "
         "its HAC z is shown next to each point; compare Target A vs B to see how much is coincident (in-recession) information.")
L.append("- `fig_energy_share.png` — energy share of PCE 1959+ with NBER bands; D1-RED episode starts marked with the share at that month.")
L.append("- `fig_regime_effect.png` — ΔP for +50% oil at spread 0 by regime block; the R2+R3 point is drawn as a grey X because it rests on one event.")
open(f"{OUT}/results.md", "w").write("\n".join(L) + "\n")
print("done"); print(json.dumps(KEY, indent=1, default=float))
