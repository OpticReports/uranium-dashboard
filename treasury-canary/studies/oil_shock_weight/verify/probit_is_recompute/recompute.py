"""Fresh recompute of block probit_is from the spec + frozen panel.  Written WITHOUT reading run.py.
All transforms rebuilt from RAW panel columns (wti, gs10, tb3ms, fedfunds, usrec, energy_share_pct,
spread_cmt); the panel's derived columns are only used as an integrity cross-check.
"""
import json, sys, warnings
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
warnings.filterwarnings("ignore")

ROOT = "/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
P = pd.read_csv(f"{ROOT}/data/panel.csv", parse_dates=["date"]).set_index("date")
EV = json.load(open(f"{ROOT}/data/events.json"))
LAST_USREC = P.index[-1]                       # 2026-08
RESOLVED_END = pd.Timestamp("2025-08-01")       # spec: t + h <= 2025-08
out = {}

# ---------- transforms from raw ----------
P["oil12_raw"] = P["wti"].pct_change(12) * 100
P["oil12_w"] = P["oil12_raw"].clip(-100, 100)
P["spread"] = P["gs10"] - P["tb3ms"]
P["ff12_pp"] = P["fedfunds"].diff(12)          # pp of 12m change
# NOPI12 (Hamilton, 12m cumulative) from raw for the confirmatory rows
lp = np.log(P["wti"])
prior_max = lp.shift(1).rolling(36, min_periods=36).max()
P["nopi_m"] = (100 * (lp - prior_max)).clip(lower=0)
P["nopi12"] = P["nopi_m"].rolling(12, min_periods=12).sum()

# integrity vs panel-derived columns
integ = {}
for a, b in [("oil12_raw", "oil_12m_pct"), ("oil12_w", "oil_12m_pct_w"), ("spread", "spread_gs"), ("nopi12", "nopi36_sum12")]:
    d = (P[a] - P[b]).abs()
    integ[f"maxabs_{a}_vs_{b}"] = float(d.max())
d = (P["ff12_pp"] * 100 - P["ff_12m_chg_bps"]).abs()
integ["maxabs_ff12_bps"] = float(d.max())
out["integrity"] = integ

# ---------- labels ----------
usrec = P["usrec"].astype(int)
def label(h):
    # y_t = 1 if USREC=1 in any t+1..t+h
    fut = pd.concat([usrec.shift(-k) for k in range(1, h + 1)], axis=1)
    y = (fut.max(axis=1) == 1).astype(float)
    y[fut.isna().any(axis=1)] = np.nan
    return y

def sample(h, target, cols, start="1953-04-01", end=None):
    y = label(h)
    df = pd.DataFrame({"y": y})
    for c in cols:
        df[c] = P[c]
    df["usrec"] = usrec
    df = df.loc[start:]
    # resolved: t + h <= 2025-08
    tmax = RESOLVED_END - pd.DateOffset(months=h)
    df = df.loc[:tmax]
    if end is not None:
        df = df.loc[:end]
    if target == "B":
        df = df[df["usrec"] == 0]
    df = df.dropna(subset=["y"] + cols)
    return df

def fit(df, cols, h):
    X = sm.add_constant(df[cols], has_constant="add")
    m = sm.Probit(df["y"], X)
    r = m.fit(method="newton", maxiter=100, disp=0, cov_type="HAC", cov_kwds={"maxlags": h - 1})
    return r

def auc(p, y):
    from scipy.stats import rankdata
    y = np.asarray(y); p = np.asarray(p)
    r = rankdata(p)
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def mcfadden(r):
    return float(1 - r.llf / r.llnull)

def dP(r, cols, shock_col, shock, spread, ci=True, extra=None):
    """dP = Phi(eta + b*shock) - Phi(eta) with other regressors at 0 except spread; delta-method 90%."""
    names = list(r.params.index)
    x0 = np.zeros(len(names)); x0[names.index("const")] = 1
    if "spread" in names: x0[names.index("spread")] = spread
    if extra:
        for k, v in extra.items(): x0[names.index(k)] = v
    x1 = x0.copy(); x1[names.index(shock_col)] += shock
    if extra and "shock_extra" in extra: pass
    b = r.params.values
    e0, e1 = x0 @ b, x1 @ b
    val = norm.cdf(e1) - norm.cdf(e0)
    g = norm.pdf(e1) * x1 - norm.pdf(e0) * x0
    se = float(np.sqrt(g @ r.cov_params().values @ g))
    return float(val), float(val - 1.645 * se), float(val + 1.645 * se)

# ---------- 1. in-sample fits ----------
fits = {}
for h in [6, 12, 18, 24]:
    for target in ["A", "B"]:
        for spec, cols in [("a", ["spread"]), ("b_w", ["spread", "oil12_w"]), ("b_n", ["spread", "nopi12"]),
                           ("c_w", ["oil12_w"]), ("c_n", ["nopi12"]), ("d", ["spread", "ff12_pp"]),
                           ("e_w", ["spread", "oil12_w", "ff12_pp"]), ("e_n", ["spread", "nopi12", "ff12_pp"])]:
            df = sample(h, target, cols)
            r = fit(df, cols, h)
            fits[(h, target, spec)] = (r, df)
            key = f"h{h}_{target}_{spec}"
            out[key] = {"n": int(len(df)), "n_pos": int(df.y.sum()), "start": str(df.index[0].date()), "end": str(df.index[-1].date()),
                        "coef": {k: float(v) for k, v in r.params.items()},
                        "z": {k: float(v) for k, v in r.tvalues.items()},
                        "auc": auc(r.predict(), df.y), "mcf": mcfadden(r), "converged": bool(r.mle_retvals.get("converged", True))}

rB = fits[(12, "B", "b_w")][0]; rA = fits[(12, "A", "b_w")][0]; rE = fits[(12, "B", "e_w")][0]
out["key"] = {
    "IS_b_oil_coef_TargetB_h12": float(rB.params["oil12_w"]), "IS_b_oil_hac_z_TargetB_h12": float(rB.tvalues["oil12_w"]),
    "IS_b_auc_TargetB_h12": out["h12_B_b_w"]["auc"], "IS_a_auc_TargetB_h12": out["h12_B_a"]["auc"],
    "IS_b_minus_a_auc_TargetB_h12": out["h12_B_b_w"]["auc"] - out["h12_B_a"]["auc"],
    "IS_b_oil_coef_TargetA_h12": float(rA.params["oil12_w"]), "IS_b_oil_hac_z_TargetA_h12": float(rA.tvalues["oil12_w"]),
    "IS_b_nopi_coef_TargetB_h12": float(fits[(12, "B", "b_n")][0].params["nopi12"]),
    "IS_b_nopi_hac_z_TargetB_h12": float(fits[(12, "B", "b_n")][0].tvalues["nopi12"]),
    "IS_b_nopi_hac_z_TargetA_h12": float(fits[(12, "A", "b_n")][0].tvalues["nopi12"]),
    "IS_e_oil_coef_TargetB_h12": float(rE.params["oil12_w"]), "IS_e_oil_hac_z_TargetB_h12": float(rE.tvalues["oil12_w"]),
    "IS_e_ff_coef_TargetB_h12": float(rE.params["ff12_pp"]), "IS_e_ff_hac_z_TargetB_h12": float(rE.tvalues["ff12_pp"]),
    "IS_e_ff_hac_z_TargetA_h12": float(fits[(12, "A", "e_w")][0].tvalues["ff12_pp"]),
    "IS_b_mcf_TargetB_h12": out["h12_B_b_w"]["mcf"], "IS_a_mcf_TargetB_h12": out["h12_B_a"]["mcf"],
    "study_a_TargetA_b0_h12": float(fits[(12, "A", "a")][0].params["const"]),
    "study_a_TargetA_b1_h12": float(fits[(12, "A", "a")][0].params["spread"]),
}
# oil z range over horizons, 12m spec (b), both targets
out["key"]["oil_z_range_b_w_all_h"] = [float(fits[(h, t, "b_w")][0].tvalues["oil12_w"]) for h in [6, 12, 18, 24] for t in ["A", "B"]]
out["key"]["nopi_z_B_h18_h24"] = [float(fits[(h, "B", "b_n")][0].tvalues["nopi12"]) for h in [18, 24]]

# ---------- 4. marginal effects (IS) ----------
for s, nm in [(0, "spread0"), (1, "spread1")]:
    out["key"][f"dP_oil_plus50_{nm}_IS"] = dP(rB, ["spread", "oil12_w"], "oil12_w", 50, s)
    out["key"][f"dP_ff_plus300bp_{nm}_IS"] = dP(rE, ["spread", "oil12_w", "ff12_pp"], "ff12_pp", 3, s)
    out["key"][f"dP_oil_plus50_{nm}_IS_e"] = dP(rE, ["spread", "oil12_w", "ff12_pp"], "oil12_w", 50, s)
out["key"]["baseP_spread0"] = float(norm.cdf(rB.params["const"])); out["key"]["baseP_spread1"] = float(norm.cdf(rB.params["const"] + rB.params["spread"]))

# ---------- 3. conditional cut + correlations ----------
dfB = sample(12, "B", ["spread", "oil12_raw"])
red = dfB[dfB["oil12_raw"] >= 50]
cut = {}
for nm, mask_red, mask_all in [("gt", red["spread"] > 0.25, dfB["spread"] > 0.25), ("le", red["spread"] <= 0.25, dfB["spread"] <= 0.25)]:
    rr = red[mask_red]; aa = dfB[mask_all]
    cut[nm] = {"n": int(len(rr)), "n_pos": int(rr.y.sum()), "P": float(rr.y.mean()), "base": float(aa.y.mean()),
               "months": [str(d.date())[:7] for d in rr.index]}
cut["all"] = {"n": int(len(red)), "P": float(red.y.mean()), "base": float(dfB.y.mean())}
out["cut"] = cut
# (b) refit on each half
for nm, mask in [("gt", dfB["spread"] > 0.25), ("le", dfB["spread"] <= 0.25)]:
    d2 = dfB[mask].copy(); d2["oil12_w"] = P["oil12_w"].reindex(d2.index)
    r = fit(d2, ["spread", "oil12_w"], 12)
    cut[f"refit_{nm}"] = {"oil": float(r.params["oil12_w"]), "z": float(r.tvalues["oil12_w"]), "dP0": dP(r, None, "oil12_w", 50, 0)[0],
                          "dP1": dP(r, None, "oil12_w", 50, 1)[0], "auc": auc(r.predict(), d2.y), "n": int(len(d2)), "n_pos": int(d2.y.sum())}
regs = {"R0": ("1953-04-01", "1985-12-01"), "R1": ("1986-01-01", "2008-12-01"), "R2": ("2009-01-01", "2019-12-01"), "R3": ("2020-01-01", "2026-08-01"), "full": ("1953-04-01", "2026-08-01")}
corr = {}
for k, (a, b) in regs.items():
    sub = P.loc[a:b, ["oil12_w", "oil12_raw", "nopi12", "spread"]].dropna()
    corr[k] = {"n": int(len(sub)), "w": float(sub["oil12_w"].corr(sub["spread"])), "raw": float(sub["oil12_raw"].corr(sub["spread"])), "nopi": float(sub["nopi12"].corr(sub["spread"]))}
out["corr"] = corr

# ---------- 5. Q3 regime blocks (Target B, h=12, (b) winsorised) ----------
def regions(y):
    idx = y.index[y == 1]
    regs_ = []
    if len(idx) == 0: return regs_
    start = prev = idx[0]
    for d in idx[1:]:
        if (d.year - prev.year) * 12 + d.month - prev.month != 1:
            regs_.append((str(start.date())[:7], str(prev.date())[:7])); start = d
        prev = d
    regs_.append((str(start.date())[:7], str(prev.date())[:7]))
    return regs_
q3 = {}
for nm, a, b in [("R0R1", "1953-04-01", "2008-12-01"), ("R2R3", "2009-01-01", None)]:
    df = sample(12, "B", ["spread", "oil12_w"], start=a, end=b)
    r = fit(df, ["spread", "oil12_w"], 12)
    q3[nm] = {"n": int(len(df)), "n_pos": int(df.y.sum()), "start": str(df.index[0].date())[:7], "end": str(df.index[-1].date())[:7],
              "regions": regions(df.y), "curve": float(r.params["spread"]), "curve_z": float(r.tvalues["spread"]),
              "oil": float(r.params["oil12_w"]), "oil_z": float(r.tvalues["oil12_w"]),
              "dP0": dP(r, None, "oil12_w", 50, 0), "dP1": dP(r, None, "oil12_w", 50, 1), "auc": auc(r.predict(), df.y),
              "converged": bool(r.mle_retvals["converged"]), "maxabs": float(np.abs(r.params).max()), "prange": [float(r.predict().min()), float(r.predict().max())],
              "oil_on_pos": [float(df.loc[df.y == 1, "oil12_w"].min()), float(df.loc[df.y == 1, "oil12_w"].max())]}
q3["ratio"] = q3["R2R3"]["dP0"][0] / q3["R0R1"]["dP0"][0]
# interaction as written: curve + oil + oil*(share-mean), 1959+
df = sample(12, "B", ["spread", "oil12_w", "energy_share_pct"], start="1959-01-01")
mean_share = float(df["energy_share_pct"].mean())
df["oilxshare"] = df["oil12_w"] * (df["energy_share_pct"] - mean_share)
r = fit(df, ["spread", "oil12_w", "oilxshare"], 12)
q3["interaction"] = {"n": int(len(df)), "n_pos": int(df.y.sum()), "mean_share": mean_share, "curve": float(r.params["spread"]), "curve_z": float(r.tvalues["spread"]),
                     "oil": float(r.params["oil12_w"]), "oil_z": float(r.tvalues["oil12_w"]), "inter": float(r.params["oilxshare"]), "inter_z": float(r.tvalues["oilxshare"]), "auc": auc(r.predict(), df.y)}
# uncentred as a check (interaction coef must be invariant)
df["oilxshare_u"] = df["oil12_w"] * df["energy_share_pct"]
ru = fit(df, ["spread", "oil12_w", "oilxshare_u"], 12)
q3["interaction_uncentred"] = {"inter": float(ru.params["oilxshare_u"]), "inter_z": float(ru.tvalues["oilxshare_u"]), "oil": float(ru.params["oil12_w"])}
# implied dP at shares
def dP_share(share):
    b = r.params; C = r.cov_params().values; names = list(b.index)
    x0 = np.array([1, 0, 0, 0.0]); x1 = np.array([1, 0, 50, 50 * (share - mean_share)])
    e0, e1 = x0 @ b.values, x1 @ b.values
    v = norm.cdf(e1) - norm.cdf(e0); g = norm.pdf(e1) * x1 - norm.pdf(e0) * x0; se = np.sqrt(g @ C @ g)
    return [float(v), float(v - 1.645 * se), float(v + 1.645 * se)]
share_1980_06 = float(P.loc["1980-06-01", "energy_share_pct"]); share_latest = float(P["energy_share_pct"].dropna().iloc[-1]); latest_share_date = str(P["energy_share_pct"].dropna().index[-1].date())[:7]
q3["dP_at_share"] = {"1980-06": [share_1980_06, dP_share(share_1980_06)], "mean": [mean_share, dP_share(mean_share)], "latest": [latest_share_date, share_latest, dP_share(share_latest)]}
q3["share_gt7_months"] = [str(d.date())[:7] for d in P.index[P["energy_share_pct"] > 7]][:1] + ["..."] + [str(d.date())[:7] for d in P.index[P["energy_share_pct"] > 7]][-1:]
# + share main effect
df["share_c"] = df["energy_share_pct"] - mean_share
rm = fit(df, ["spread", "oil12_w", "share_c", "oilxshare"], 12)
q3["interaction_with_main"] = {"oil": float(rm.params["oil12_w"]), "oil_z": float(rm.tvalues["oil12_w"]), "share": float(rm.params["share_c"]), "share_z": float(rm.tvalues["share_c"]), "inter": float(rm.params["oilxshare"]), "inter_z": float(rm.tvalues["oilxshare"]), "curve": float(rm.params["spread"]), "auc": auc(rm.predict(), df.y)}
out["q3"] = q3

# ---------- 2. deployed check ----------
def targetA_fit(spread_col, start, tmax):
    y = label(12); df = pd.DataFrame({"y": y, "spread": P[spread_col]}).loc[start:tmax].dropna()
    r = sm.Probit(df.y, sm.add_constant(df[["spread"]])).fit(method="newton", maxiter=100, disp=0)
    return {"b0": float(r.params["const"]), "b1": float(r.params["spread"]), "auc": auc(r.predict(), df.y), "n": int(len(df)), "n_pos": int(df.y.sum()), "start": str(df.index[0].date())[:7], "end": str(df.index[-1].date())[:7]}
dep = {}
dep["a_gs_1982_resolved"] = targetA_fit("spread", "1982-01-01", "2024-08-01")
dep["a_cmt_1982_resolved"] = targetA_fit("spread_cmt", "1982-01-01", "2024-08-01")
dep["a_cmt_1982_deployed_labels"] = targetA_fit("spread_cmt", "1982-01-01", "2025-08-01")   # t+12 <= last USREC print 2026-08
dep["a_cmt_all_deployed_labels"] = targetA_fit("spread_cmt", "1900-01-01", "2025-08-01")
dep["spread_cmt_first"] = str(P["spread_cmt"].dropna().index[0].date())
out["deployed"] = dep

# ---------- episodes: D1-RED, usrec_t=0, gap <= 6 OFF months ----------
on = (P["oil12_raw"] >= 50)
on_nr = on & (usrec == 0)
in_rec_on = [str(d.date())[:7] for d in P.index[on & (usrec == 1)]]
months = list(P.index[on_nr])
eps = []
cur = [months[0]]
for d in months[1:]:
    gap = (d.year - cur[-1].year) * 12 + d.month - cur[-1].month - 1   # number of OFF months between
    if gap <= 6: cur.append(d)
    else: eps.append(cur); cur = [d]
eps.append(cur)
onsets = [pd.Timestamp(o + "-01") for o in EV["recession_onsets"]]
ep_rows = []
for e in eps:
    s, l = e[0], e[-1]
    nxt = [o for o in onsets if o > s]
    # pending: last ON + 12 beyond resolved end
    pending = (l + pd.DateOffset(months=12)) > RESOLVED_END
    row = {"start": str(s.date())[:7], "last": str(l.date())[:7], "n_on": len(e), "oil12": float(P.loc[s, "oil12_raw"]),
           "spread": None if pd.isna(P.loc[s, "spread"]) else float(P.loc[s, "spread"]),
           "share": None if pd.isna(P.loc[s, "energy_share_pct"]) else float(P.loc[s, "energy_share_pct"]),
           "next_onset": str(nxt[0].date())[:7] if nxt else None,
           "months_to": ((nxt[0].year - s.year) * 12 + nxt[0].month - s.month) if nxt else None, "pending": bool(pending)}
    ep_rows.append(row)
out["episodes"] = ep_rows; out["in_rec_on"] = in_rec_on

json.dump(out, open(f"{ROOT}/verify/probit_is_recompute/recompute.json", "w"), indent=1, default=str)
print(json.dumps(out["key"], indent=1)); print(json.dumps(out["q3"], indent=1)); print(json.dumps(out["cut"], indent=1)); print(json.dumps(out["corr"], indent=1)); print(json.dumps(out["deployed"], indent=1)); print(json.dumps(out["integrity"], indent=1))
for r_ in ep_rows: print(r_)
print("in-rec ON:", in_rec_on)
