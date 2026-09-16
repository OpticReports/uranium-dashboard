"""BLOCK walk — Q2 DECISION TEST: walk-forward probits (a) curve-only vs (b) curve+oil,
uncertainty (block + cycle bootstrap), decision rule, decision-relevant marginal effects,
Figures 2 and 3.  Spec: treasury-canary/studies/oil-shock-recession-weight.md v1 §3-§5.

Re-runnable end to end from the frozen inputs (panel.csv, events.json). No network.
Every reported number is written to numbers.json with its definition string.
"""
import json, os, math, warnings, time
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm, rankdata
from statsmodels.tools.sm_exceptions import ConvergenceWarning, HessianInversionWarning
try:
    from statsmodels.tools.sm_exceptions import PerfectSeparationWarning
except ImportError:                                   # older statsmodels
    class PerfectSeparationWarning(Warning): pass
try:
    from statsmodels.tools.sm_exceptions import PerfectSeparationError
except ImportError:
    class PerfectSeparationError(Exception): pass
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = f"{ROOT}/blocks/walk"
os.makedirs(OUT, exist_ok=True)
T0 = time.time()

P = pd.read_csv(f"{ROOT}/data/panel.csv", index_col="date", parse_dates=True)
EV = json.load(open(f"{ROOT}/data/events.json"))
RESOLVED = pd.Timestamp(EV["last_resolved_month_h12"] + "-01")          # 2025-08 = last USREC print - 12
SAMPLE_START = pd.Timestamp("1953-04-01")                                # spread_gs starts
HORIZONS = (12, 6, 18, 24)                                               # 12 = decision; others descriptive
OILS = {"w": "oil_12m_pct_w", "nopi": "nopi36_sum12"}
OIL_LABEL = {"w": "12m % chg winsorised ±100 (DECISION spec)", "nopi": "NOPI12 = nopi36_sum12 (confirmatory)"}
FIRST_PRED = {"primary": pd.Timestamp("1970-01-01"), "secondary": pd.Timestamp("1986-01-01")}
SIGN_FROM = pd.Timestamp("1986-01-01")
SEED, BLOCK, NDRAW = 20260915, 36, 1000
CYCLE_BOUNDS = ["1973-12", "1980-02", "1981-08", "1990-08", "2001-04", "2008-01", "2020-03"]
OOS_ONSETS = CYCLE_BOUNDS                                                # the 7 walk-forward positives
P["ff_pace"] = P["ff_12m_chg_bps"] / 100.0                               # pp, 1955-07+
NUM = {}


def rec(key, value, definition):
    NUM[key] = {"value": value, "def": definition}
    return value


def mi(ts):
    """month integer"""
    ts = pd.Timestamp(ts)
    return ts.year * 12 + ts.month - 1


def ts_of(m):
    return pd.Timestamp(m // 12, m % 12 + 1, 1)


# ---------------------------------------------------------------- NBER announcement lag L (§4)
# keyed by ONSET month (first USREC=1 month = peak + 1).  Actual announcement months for the six
# post-1979 peaks; earlier peaks: announcement = peak + 12 months = onset + 11 months.
ANN = {"1980-02": "1980-06", "1981-08": "1982-01", "1990-08": "1991-04",
       "2001-04": "2001-11", "2008-01": "2008-12", "2020-03": "2020-06"}
ONSETS = [pd.Timestamp(o + "-01") for o in EV["recession_onsets"]]
ANN_MI = {}
for o in ONSETS:
    k = o.strftime("%Y-%m")
    ANN_MI[mi(o)] = mi(pd.Timestamp(ANN[k] + "-01")) if k in ANN else mi(o) + 11
rec("announcement_months_by_onset",
    {ts_of(k).strftime("%Y-%m"): ts_of(v).strftime("%Y-%m") for k, v in ANN_MI.items()},
    "onset (first USREC=1 month = NBER peak + 1) -> month in which the peak became knowable: actual NBER "
    "announcement month for 1980-01/1981-07/1990-07/2001-03/2007-12/2020-02 peaks; peak + 12 months before 1979")

# ---------------------------------------------------------------- labels (§4)
u = P["usrec"].astype(float)
usrec_arr = P["usrec"].values
onset_mi = np.array(sorted(ANN_MI.keys()))
for h in HORIZONS:
    fut = pd.concat([u.shift(-k) for k in range(1, h + 1)], axis=1)
    yA = (fut.max(axis=1) >= 1).astype(float).where(fut.notna().all(axis=1))
    P[f"yA_{h}"] = yA                                   # Target A: usrec==1 in any of t+1..t+h
    P[f"yB_{h}"] = yA.where(u == 0)                     # Target B: usrec_t==1 rows excluded (fit AND score)
    # announcement month of the label for label-1 rows: first usrec==1 month in t+1..t+h -> its onset -> ANN
    ann = np.full(len(P), np.nan)
    idx_mi = np.array([mi(t) for t in P.index])
    for i in range(len(P)):
        if yA.iloc[i] == 1:
            win = usrec_arr[i + 1:i + 1 + h]
            j = int(np.argmax(win == 1))
            m_first = idx_mi[i] + 1 + j
            o = onset_mi[onset_mi <= m_first].max()
            ann[i] = ANN_MI[o]
    P[f"ann_{h}"] = ann
P["mi"] = [mi(t) for t in P.index]


def last_scored(h):
    return RESOLVED - pd.DateOffset(months=h)           # T + h <= 2025-08


# ---------------------------------------------------------------- estimator
def auc_mw(p, y):
    p = np.asarray(p, float); y = np.asarray(y, int)
    n1 = int(y.sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return np.nan
    r = rankdata(p)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fit_probit(X, y):
    """statsmodels Probit, Newton, maxiter 100, disp 0.  Returns (params or None, failure reason or None)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            r = sm.Probit(y, X).fit(method="newton", maxiter=100, disp=0)
        except (PerfectSeparationError, np.linalg.LinAlgError) as e:
            return None, f"exception:{type(e).__name__}"
        bad = [x.category.__name__ for x in w if issubclass(x.category, (ConvergenceWarning, PerfectSeparationWarning))]
        hess = [x for x in w if issubclass(x.category, HessianInversionWarning)]
    params = np.asarray(r.params, float)
    conv = bool(r.mle_retvals.get("converged", True))
    if bad or (not conv) or (not np.all(np.isfinite(params))):
        reason = ",".join(sorted(set(bad))) or ("not_converged" if not conv else "nan_params")
        return params, reason
    return params, ("hessian_inversion_warning" if hess else None)


def walk(h, target, variant):
    """Expanding-window walk-forward for one (horizon, target, label-knowledge variant).
    Refit every month T from 1970-01 to the last scored month; (a) curve-only and (b) curve+oil for
    BOTH oil regressors on identical training rows.  Returns a DataFrame indexed by T."""
    ycol, acol = f"y{target}_{h}", f"ann_{h}"
    base = P.loc[SAMPLE_START:, ["spread_gs", OILS["w"], OILS["nopi"], "usrec", "mi", ycol, acol]].copy()
    fitpool = base.dropna(subset=["spread_gs", OILS["w"], OILS["nopi"], ycol])      # Target B already drops usrec_t==1
    t_mi = fitpool["mi"].values; yv = fitpool[ycol].values; annv = fitpool[acol].values
    Xs = fitpool["spread_gs"].values; Xo = {k: fitpool[c].values for k, c in OILS.items()}
    months = pd.date_range(FIRST_PRED["primary"], last_scored(h), freq="MS")
    prev = {}                                  # spec -> last good params (inherited on failure)
    rows = []
    for T in months:
        Tm = mi(T)
        if variant == "L":
            mask = ((yv == 1) & (t_mi + h <= Tm) & (annv <= Tm)) | ((yv == 0) & (t_mi + h + 12 <= Tm))
        else:                                  # no-L: BACKTEST.md §B design, row usable when t + h <= T
            mask = t_mi + h <= Tm
        n_tr = int(mask.sum()); n_pos = int(yv[mask].sum())
        row = {"date": T, "n_train": n_tr, "n_train_pos": n_pos, "train_last": ts_of(int(t_mi[mask].max())) if n_tr else pd.NaT,
               "usrec_T": int(P.at[T, "usrec"]), "y": P.at[T, ycol],
               "scored": bool(pd.notna(P.at[T, ycol])), "spread_T": float(P.at[T, "spread_gs"])}
        ytr = yv[mask].astype(int)
        # (a) curve only
        Xa = np.column_stack([np.ones(n_tr), Xs[mask]])
        pa, fa = fit_probit(Xa, ytr)
        fail_a = fa is not None and fa != "hessian_inversion_warning"
        if fail_a or pa is None:
            if "a" in prev:
                pa = prev["a"]
            elif pa is None or not np.all(np.isfinite(pa)):
                raise RuntimeError(f"first refit failed at {T:%Y-%m} for (a)")
        prev["a"] = pa
        row.update({"const_a": pa[0], "beta_spread_a": pa[1], "fail_a": fail_a, "fail_a_reason": fa,
                    "p_a": float(norm.cdf(pa[0] + pa[1] * row["spread_T"]))})
        # (b) curve + oil, each regressor
        for k, c in OILS.items():
            xo = Xo[k][mask]
            nz = int((xo != 0).sum())
            nonid = nz < 24
            Xb = np.column_stack([np.ones(n_tr), Xs[mask], xo])
            pb, fb = fit_probit(Xb, ytr)
            fail_b = fb is not None and fb != "hessian_inversion_warning"
            if fail_b or pb is None:
                if f"b_{k}" in prev:
                    pb = prev[f"b_{k}"]
                elif pb is None or not np.all(np.isfinite(pb)):
                    raise RuntimeError(f"first refit failed at {T:%Y-%m} for (b,{k})")
            prev[f"b_{k}"] = pb
            xT = float(P.at[T, c])
            p_b = float(norm.cdf(pb[0] + pb[1] * row["spread_T"] + pb[2] * xT))
            row.update({f"const_b_{k}": pb[0], f"beta_spread_b_{k}": pb[1], f"beta_oil_{k}": pb[2],
                        f"fail_b_{k}": fail_b, f"fail_b_{k}_reason": fb, f"n_oil_nonzero_{k}": nz,
                        f"nonid_{k}": nonid, f"oil_T_{k}": xT,
                        f"p_b_{k}": row["p_a"] if nonid else p_b,        # NON-IDENTIFIED -> (a)'s forecast
                        f"p_b_{k}_raw": p_b})
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    df.attrs["final_train_mask_index"] = fitpool.index[mask]              # training rows of the LAST refit
    return df


RUNS = {}
for h in HORIZONS:
    for target in ("A", "B"):
        for variant in ("L", "noL"):
            t1 = time.time()
            RUNS[(h, target, variant)] = walk(h, target, variant)
            d = RUNS[(h, target, variant)]
            print(f"walk h={h} target={target} {variant}: {len(d)} refits, scored {int(d['scored'].sum())}, "
                  f"fail_a {int(d['fail_a'].sum())} fail_b_w {int(d['fail_b_w'].sum())} fail_b_nopi {int(d['fail_b_nopi'].sum())} "
                  f"nonid_w {int(d['nonid_w'].sum())} nonid_nopi {int(d['nonid_nopi'].sum())}  [{time.time()-t1:.0f}s]", flush=True)

# ================================================================ scoring, uncertainty, decision
CLIP = (0.01, 0.99)


def score_set(y, pa, pb):
    y = np.asarray(y, int); pa = np.asarray(pa, float); pb = np.asarray(pb, float)
    pac, pbc = np.clip(pa, *CLIP), np.clip(pb, *CLIP)
    ls = lambda p: float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    o = {"n": int(len(y)), "n_pos": int(y.sum()), "base_rate": float(y.mean()),
         "auc_a": auc_mw(pa, y), "auc_b": auc_mw(pb, y),
         "brier_a": float(np.mean((pa - y) ** 2)), "brier_b": float(np.mean((pb - y) ** 2)),
         "logscore_a": ls(pac), "logscore_b": ls(pbc),
         "auc_a_clipped": auc_mw(pac, y), "auc_b_clipped": auc_mw(pbc, y),
         "brier_a_clipped": float(np.mean((pac - y) ** 2)), "brier_b_clipped": float(np.mean((pbc - y) ** 2))}
    o["delta_auc"] = o["auc_b"] - o["auc_a"]; o["delta_brier"] = o["brier_b"] - o["brier_a"]
    o["delta_logscore"] = o["logscore_b"] - o["logscore_a"]
    o["delta_auc_clipped"] = o["auc_b_clipped"] - o["auc_a_clipped"]
    o["delta_brier_clipped"] = o["brier_b_clipped"] - o["brier_a_clipped"]
    return o


def _pct(v):
    v = np.asarray(v, float)
    return [float(x) for x in np.percentile(v, [5, 50, 95])] if len(v) else [np.nan] * 3


def block_boot(y, pa, pb, block=BLOCK, ndraw=NDRAW, seed=SEED):
    """moving-block bootstrap of the paired triples (p_a, p_b, y): overlapping blocks of `block` months,
    ceil(n/block) blocks per draw, truncated to n; numpy Generator seeded `seed` (fresh per call)."""
    rng = np.random.default_rng(seed); n = len(y); nb = math.ceil(n / block)
    da, db = [], []; skipped = 0
    for _ in range(ndraw):
        starts = rng.integers(0, n - block + 1, size=nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        yy = y[idx]
        if yy.sum() == 0 or yy.sum() == n:
            skipped += 1; continue
        da.append(auc_mw(pb[idx], yy) - auc_mw(pa[idx], yy))
        db.append(float(np.mean((pb[idx] - yy) ** 2) - np.mean((pa[idx] - yy) ** 2)))
    a5, a50, a95 = _pct(da); b5, b50, b95 = _pct(db)
    return {"auc_p5": a5, "auc_p50": a50, "auc_p95": a95, "brier_p5": b5, "brier_p50": b50, "brier_p95": b95,
            "n_draws_valid": len(da), "n_draws_skipped": skipped, "block_len": block, "n_blocks_per_draw": nb,
            "seed": seed, "draws_auc": da, "draws_brier": db}


def cycle_segments(dates):
    b = np.array([mi(pd.Timestamp(x + "-01")) for x in CYCLE_BOUNDS])
    dm = np.array([mi(d) for d in dates])
    sid = np.searchsorted(b, dm, side="right")
    segs = [np.where(sid == s)[0] for s in range(len(b) + 1)]
    segs = [s for s in segs if len(s)]
    names = [f"{dates[s[0]]:%Y-%m}..{dates[s[-1]]:%Y-%m}" for s in segs]
    return segs, names


def cycle_boot(dates, y, pa, pb, ndraw=NDRAW, seed=SEED):
    """resample whole peak-to-peak cycles (cut at the NBER onset months) with replacement."""
    segs, names = cycle_segments(dates)
    k = len(segs); rng = np.random.default_rng(seed)
    da, db = [], []; skipped = 0
    for _ in range(ndraw):
        pick = rng.integers(0, k, size=k)
        idx = np.concatenate([segs[i] for i in pick])
        yy = y[idx]
        if yy.sum() == 0 or yy.sum() == len(yy):
            skipped += 1; continue
        da.append(auc_mw(pb[idx], yy) - auc_mw(pa[idx], yy))
        db.append(float(np.mean((pb[idx] - yy) ** 2) - np.mean((pa[idx] - yy) ** 2)))
    a5, a50, a95 = _pct(da); b5, b50, b95 = _pct(db)
    return {"auc_p5": a5, "auc_p50": a50, "auc_p95": a95, "brier_p5": b5, "brier_p50": b50, "brier_p95": b95,
            "n_draws_valid": len(da), "n_draws_skipped": skipped, "n_cycles": k, "cycle_names": names, "seed": seed,
            "draws_auc": da, "draws_brier": db}


def sign_stats(df, k):
    beta = df[f"beta_oil_{k}"]; ident = ~df[f"nonid_{k}"].astype(bool)
    post = beta[(df.index >= SIGN_FROM) & ident]
    neg = post[post <= 0]
    return {"sign_frac_1986": float((post > 0).mean()), "n_refits_1986": int(len(post)), "n_pos_1986": int((post > 0).sum()),
            "final_beta_oil": float(beta.iloc[-1]), "final_sign_positive": bool(beta.iloc[-1] > 0),
            "final_refit_month": df.index[-1].strftime("%Y-%m"), "first_refit_month": df.index[0].strftime("%Y-%m"),
            "sign_frac_all_refits": float((beta[ident] > 0).mean()), "n_refits_all": int(ident.sum()),
            "beta_min_1986": float(post.min()), "beta_max_1986": float(post.max()),
            "nonpositive_months_1986": [t.strftime("%Y-%m") for t in neg.index]}


def decide(sc, bb, ss):
    crit = [("delta_auc >= +0.02", sc["delta_auc"] >= 0.02),
            ("block-bootstrap 5th pct of delta_auc > 0", bb["auc_p5"] > 0),
            ("delta_brier < 0", sc["delta_brier"] < 0),
            ("block-bootstrap 95th pct of delta_brier < 0", bb["brier_p95"] < 0),
            ("beta_oil > 0 in >= 90% of refits from 1986-01", ss["sign_frac_1986"] >= 0.90),
            ("beta_oil > 0 in the final refit", ss["final_sign_positive"])]
    met = all(v for _, v in crit)
    if met:
        v = "MET"
    elif sc["delta_auc"] >= 0.02 and (bb["auc_p5"] <= 0 or bb["brier_p95"] >= 0):
        v = "SUGGESTIVE"
    else:
        v = "NOT MET"
    return {"verdict": v, "criteria": {k: bool(x) for k, x in crit}, "n_criteria_passed": int(sum(bool(x) for _, x in crit)),
            "failed": [k for k, x in crit if not x]}


def panel(h, target, variant, window, k):
    df = RUNS[(h, target, variant)]
    d = df[df["scored"] & (df.index >= FIRST_PRED[window])]
    y = d["y"].values.astype(int); pa = d["p_a"].values; pb = d[f"p_b_{k}"].values
    sc = score_set(y, pa, pb); bb = block_boot(y, pa, pb); cb = cycle_boot(d.index, y, pa, pb); ss = sign_stats(df, k)
    dec = decide(sc, bb, ss)
    fb = df[f"fail_b_{k}"].astype(bool); fa = df["fail_a"].astype(bool); ni = df[f"nonid_{k}"].astype(bool)
    return {"h": h, "target": target, "variant": variant, "window": window, "oil": k, "oil_col": OILS[k],
            "oos_first": d.index[0].strftime("%Y-%m"), "oos_last": d.index[-1].strftime("%Y-%m"),
            "scores": sc, "block_boot": {a: b for a, b in bb.items() if not a.startswith("draws")},
            "cycle_boot": {a: b for a, b in cb.items() if not a.startswith("draws")},
            "sign": ss, "decision": dec,
            "n_nonidentified": int(ni.sum()), "nonidentified_months": [t.strftime("%Y-%m") for t in df.index[ni]],
            "n_fail_a": int(fa.sum()), "fail_a_months": [t.strftime("%Y-%m") for t in df.index[fa]],
            "n_fail_b": int(fb.sum()), "fail_b_months": [t.strftime("%Y-%m") for t in df.index[fb]],
            "can_decide": bool(h == 12 and variant == "L" and window == "primary" and k == "w"),
            "_draws": {"block_auc": bb["draws_auc"], "block_brier": bb["draws_brier"],
                       "cycle_auc": cb["draws_auc"], "cycle_brier": cb["draws_brier"]}}


PANELS = {}
for h in HORIZONS:
    for target in ("A", "B"):
        for variant in ("L", "noL"):
            for window in ("primary", "secondary"):
                for k in OILS:
                    PANELS[(h, target, variant, window, k)] = panel(h, target, variant, window, k)
print(f"panels done [{time.time()-T0:.0f}s]", flush=True)

PANEL_DEF = ("walk-forward OOS scores on identical months T (first prediction 1970-01 primary / 1986-01 secondary; "
             "last scored T <= 2025-08 - h); (a) curve-only vs (b) curve+oil; expanding window from 1953-04, refit every month; "
             "L variant: label-1 row t usable at T iff t+h<=T and T>=announcement month of its recession's peak; label-0 row iff "
             "t+h+12<=T; noL variant: t+h<=T (BACKTEST.md §B). Target A: y=1 if USREC=1 in t+1..t+h; Target B: usrec_t=1 rows "
             "excluded from fitting and scoring, (a) refit on the same restricted rows. AUC = Mann-Whitney; Brier = mean (p-y)^2; "
             "logscore = mean[y ln p + (1-y) ln(1-p)] on p clipped to [0.01,0.99] (AUC/Brier on unclipped p, '_clipped' twins "
             "beside). delta = (b) - (a). block_boot: moving-block bootstrap of (p_a,p_b,y), block 36, 1000 draws, Generator seed "
             "20260915, percentiles 5/50/95; cycle_boot: whole peak-to-peak cycles cut at NBER onsets 1973-12/1980-02/1981-08/"
             "1990-08/2001-04/2008-01/2020-03 resampled with replacement, 1000 draws, same seed. sign: share of refits from 1986-01 "
             "with beta_oil>0 (non-identified refits excluded) and the final refit's sign. decision: MET iff delta_auc>=0.02 AND "
             "block 5th pct delta_auc>0 AND delta_brier<0 AND block 95th pct delta_brier<0 AND sign_frac_1986>=0.90 AND final "
             "beta_oil>0; SUGGESTIVE = delta_auc>=0.02 with a block interval including 0; else NOT MET. Only h=12 / L / primary / "
             "oil_12m_pct_w can decide; every other row is descriptive or confirmatory.")
rec("panels", {"|".join(map(str, key)): {a: b for a, b in v.items() if a != "_draws"} for key, v in PANELS.items()}, PANEL_DEF)

# ---------------------------------------------------------------- the DECISION (h=12, L, primary, oil_12m_pct_w)
RANK = {"NOT MET": 0, "SUGGESTIVE": 1, "MET": 2}
DEC = {t: PANELS[(12, t, "L", "primary", "w")] for t in ("A", "B")}
vA, vB = DEC["A"]["decision"]["verdict"], DEC["B"]["decision"]["verdict"]
overall = min((vA, vB), key=lambda v: RANK[v])
met_A_only = bool(vA == "MET" and vB != "MET")
DECISION = {"target_A": vA, "target_B": vB, "overall": overall,
            "met_on_target_A_only_coincident_information_only": met_A_only,
            "section5_row": ({"MET": "Q2 decision rule MET (both targets) -> oil-augmented probit variant beside the dials (never blended)",
                              "SUGGESTIVE": "Q2 SUGGESTIVE -> record; no deploy; re-test after the next NBER onset",
                              "NOT MET": "Q2 NOT met -> recession odds stay curve-only; non-result recorded in the oil channel's certainty text"}[overall]
                             if not met_A_only else "MET only on Target A -> descriptive note ('coincident information only'); no deploy"),
            "inputs": {t: {"delta_auc": DEC[t]["scores"]["delta_auc"], "ci5": DEC[t]["block_boot"]["auc_p5"], "ci95": DEC[t]["block_boot"]["auc_p95"],
                           "delta_brier": DEC[t]["scores"]["delta_brier"], "brier_ci5": DEC[t]["block_boot"]["brier_p5"], "brier_ci95": DEC[t]["block_boot"]["brier_p95"],
                           "sign_frac_1986": DEC[t]["sign"]["sign_frac_1986"], "final_sign": DEC[t]["sign"]["final_beta_oil"],
                           "auc_a": DEC[t]["scores"]["auc_a"], "auc_b": DEC[t]["scores"]["auc_b"],
                           "brier_a": DEC[t]["scores"]["brier_a"], "brier_b": DEC[t]["scores"]["brier_b"],
                           "n_oos": DEC[t]["scores"]["n"], "n_pos": DEC[t]["scores"]["n_pos"],
                           "cycle_ci5": DEC[t]["cycle_boot"]["auc_p5"], "cycle_ci95": DEC[t]["cycle_boot"]["auc_p95"],
                           "cycle_brier_ci5": DEC[t]["cycle_boot"]["brier_p5"], "cycle_brier_ci95": DEC[t]["cycle_boot"]["brier_p95"],
                           "verdict": DEC[t]["decision"]["verdict"], "criteria": DEC[t]["decision"]["criteria"]} for t in ("A", "B")}}
rec("decision_h12_L_primary_oil12m", DECISION,
    "§4 decision rule applied literally at h=12, oil_12m_pct_w, primary window 1970-01..2024-08, L variant, on Target A and Target B; "
    "overall = the weaker of the two verdicts (rule must be MET on both); 'met on Target A only' = coincident information only, no weight")

LEAK = {}
for t in ("A", "B"):
    L_, N_ = PANELS[(12, t, "L", "primary", "w")], PANELS[(12, t, "noL", "primary", "w")]
    LEAK[t] = {"delta_auc_L": L_["scores"]["delta_auc"], "delta_auc_noL": N_["scores"]["delta_auc"],
               "leak_in_delta_auc(noL-L)": N_["scores"]["delta_auc"] - L_["scores"]["delta_auc"],
               "auc_a_L": L_["scores"]["auc_a"], "auc_a_noL": N_["scores"]["auc_a"],
               "auc_b_L": L_["scores"]["auc_b"], "auc_b_noL": N_["scores"]["auc_b"],
               "delta_brier_L": L_["scores"]["delta_brier"], "delta_brier_noL": N_["scores"]["delta_brier"],
               "verdict_L": L_["decision"]["verdict"], "verdict_noL(descriptive)": N_["decision"]["verdict"]}
rec("label_leak_h12_primary", LEAK, "size of the NBER-announcement-lag leak: the same OOS months scored with (L) and without (noL) the lag rule")

# ---------------------------------------------------------------- marginal effects from the LAST refit (Target B, h=12, L)
dfB = RUNS[(12, "B", "L")]; last = dfB.iloc[-1]
b_par = {"const": float(last["const_b_w"]), "spread": float(last["beta_spread_b_w"]), "oil": float(last["beta_oil_w"])}
a_par = {"const": float(last["const_a"]), "spread": float(last["beta_spread_a"])}
train_idx = dfB.attrs["final_train_mask_index"]
te = P.loc[train_idx, ["spread_gs", "oil_12m_pct_w", "ff_pace", "yB_12"]].dropna()
Xe = sm.add_constant(te[["spread_gs", "oil_12m_pct_w", "ff_pace"]], has_constant="add")
re = sm.Probit(te["yB_12"].astype(int), Xe).fit(method="newton", maxiter=100, disp=0, cov_type="HAC", cov_kwds={"maxlags": 11})
e_par = {k: float(v) for k, v in re.params.items()}; e_z = {k: float(v) for k, v in re.tvalues.items()}


def Phi(*a):
    return float(norm.cdf(sum(a)))


ME = {"basis": f"last walk-forward refit at T={dfB.index[-1]:%Y-%m}, Target B, h=12, L variant; training rows {train_idx[0]:%Y-%m}..{train_idx[-1]:%Y-%m} "
               f"(n={len(train_idx)}, usrec_t=0 only); (e) fitted on the same rows with ff_pace available ({te.index[0]:%Y-%m}.., n={len(te)})",
      "b_params": b_par, "a_params": a_par, "e_params": e_par, "e_hac_z_lag11": e_z, "rows": []}
for s in (0.0, 1.0):
    base_a = Phi(a_par["const"], a_par["spread"] * s)
    base_b = Phi(b_par["const"], b_par["spread"] * s)
    dP_oil_b = Phi(b_par["const"], b_par["spread"] * s, b_par["oil"] * 50) - base_b
    base_e = Phi(e_par["const"], e_par["spread_gs"] * s)
    dP_oil_e = Phi(e_par["const"], e_par["spread_gs"] * s, e_par["oil_12m_pct_w"] * 50) - base_e
    dP_ff_e = Phi(e_par["const"], e_par["spread_gs"] * s, e_par["ff_pace"] * 3.0) - base_e
    ME["rows"].append({"spread_pp": s, "P_a_curve_only": base_a, "P_b_at_oil0": base_b, "dP_plus50_oil_from_b": dP_oil_b,
                       "P_e_at_oil0_ff0": base_e, "dP_plus50_oil_from_e": dP_oil_e, "dP_plus300bp_ff_from_e": dP_ff_e})
rec("marginal_effects_last_refit_targetB_h12_L", ME,
    "dP = Phi(x'beta with oil=+50 (winsorised 12m %, from 0)) - Phi(x'beta with oil=0) at spread_gs = 0 and +1pp, from the (b) "
    "coefficients of the LAST walk-forward refit (Target B, h=12, L); (e) = curve + oil_12m_pct_w + ff_pace (FEDFUNDS 12m change, pp) "
    "fitted once on that refit's training rows (HAC z, maxlags 11, reported for reference); dP for +300bp = ff_pace 0 -> +3 at oil=0")

# ---------------------------------------------------------------- named-episode tables (h=12, L, primary)
def onset_table(k="w"):
    rows = []
    for o in OOS_ONSETS:
        e = pd.Timestamp(o + "-01")
        for t in ("A", "B"):
            d = RUNS[(12, t, "L")]
            w = d.loc[e - pd.DateOffset(months=12): e - pd.DateOffset(months=1)]
            w = w[w["scored"]]
            if not len(w):
                continue
            rows.append({"onset": o, "target": t, "window": f"{w.index[0]:%Y-%m}..{w.index[-1]:%Y-%m}", "n_scored": int(len(w)),
                         "p_a_first": float(w["p_a"].iloc[0]), "p_b_first": float(w[f"p_b_{k}"].iloc[0]),
                         "p_a_max": float(w["p_a"].max()), "p_a_max_month": w["p_a"].idxmax().strftime("%Y-%m"),
                         "p_b_max": float(w[f"p_b_{k}"].max()), "p_b_max_month": w[f"p_b_{k}"].idxmax().strftime("%Y-%m"),
                         "mean_dp": float((w[f"p_b_{k}"] - w["p_a"]).mean()),
                         "oil_at_last": float(w[f"oil_T_{k}"].iloc[-1]), "spread_at_last": float(w["spread_T"].iloc[-1]),
                         "beta_oil_at_last": float(w[f"beta_oil_{k}"].iloc[-1])})
    return rows


ONSET_TAB = {k: onset_table(k) for k in OILS}
rec("oos_onset_table_h12_L", ONSET_TAB,
    "for each of the 7 OOS onsets: OOS forecasts in the 12 months before the onset [e-12, e-1] (Target B drops usrec_t=1 months, so the "
    "1981-08 window is 1980-08..1981-07); p_*_first = forecast at e-12; max and its month; mean_dp = mean(p_b - p_a); oil/spread/beta at e-1")


def cycle_table(t, k="w"):
    d = RUNS[(12, t, "L")]; d = d[d["scored"] & (d.index >= FIRST_PRED["primary"])]
    segs, names = cycle_segments(d.index)
    y = d["y"].values.astype(int); pa = d["p_a"].values; pb = d[f"p_b_{k}"].values
    rows = []
    for s, nm in zip(segs, names):
        yy = y[s]
        rows.append({"cycle": nm, "n": int(len(s)), "n_pos": int(yy.sum()),
                     "auc_a": auc_mw(pa[s], yy), "auc_b": auc_mw(pb[s], yy),
                     "brier_a": float(np.mean((pa[s] - yy) ** 2)), "brier_b": float(np.mean((pb[s] - yy) ** 2))})
    return rows


CYCLE_TAB = {f"{t}_{k}": cycle_table(t, k) for t in ("A", "B") for k in OILS}
rec("cycle_table_h12_L_primary", CYCLE_TAB, "per peak-to-peak cycle (cut at the OOS onset months) OOS AUC/Brier of (a) and (b); AUC is NaN when a cycle has no positives or no negatives")


def dp_stretches(t="A", k="w", thr=0.05):
    d = RUNS[(12, t, "L")]; d = d[d["scored"]]
    dp = (d[f"p_b_{k}"] - d["p_a"])
    flag = dp.abs() >= thr
    rows, cur = [], None
    for i, (T, f) in enumerate(flag.items()):
        sgn = int(np.sign(dp[T])) if f else 0
        if f and cur is not None and sgn == cur["sgn"] and (mi(T) - mi(cur["last"]) == 1):
            cur["last"] = T; cur["vals"].append(dp[T]); cur["ys"].append(int(d.at[T, "y"]))
        else:
            if cur is not None:
                rows.append(cur)
            cur = {"first": T, "last": T, "sgn": sgn, "vals": [dp[T]], "ys": [int(d.at[T, "y"])]} if f else None
    if cur is not None:
        rows.append(cur)
    out = []
    for r in rows:
        out.append({"stretch": f"{r['first']:%Y-%m}..{r['last']:%Y-%m}", "n": len(r["vals"]), "direction": "oil raises p" if r["sgn"] > 0 else "oil lowers p",
                    "mean_dp": float(np.mean(r["vals"])), "max_abs_dp": float(np.max(np.abs(r["vals"]))),
                    "share_y1": float(np.mean(r["ys"])), "in_recession_at_start": int(P.at[r["first"], "usrec"])})
    return out


STRETCH = {t: dp_stretches(t) for t in ("A", "B")}
rec("dp_stretches_h12_L_oil12m", STRETCH, "consecutive OOS months where |p_b - p_a| >= 0.05 with the same sign (oil_12m_pct_w spec, L variant); share_y1 = share of those months whose label was 1")


def decade_table(t, k="w"):
    d = RUNS[(12, t, "L")]; d = d[d["scored"] & (d.index >= FIRST_PRED["primary"])]
    y = d["y"].values; se = (d[f"p_b_{k}"].values - y) ** 2 - (d["p_a"].values - y) ** 2
    g = pd.Series(se, index=d.index).groupby(d.index.year // 10 * 10); tot = float(se.sum())
    return [{"decade": f"{int(dec)}s", "n": int(len(v)), "sum_dSE": float(v.sum()), "share_of_total": (float(v.sum() / tot) if tot else None)} for dec, v in g]


DECADE = {t: decade_table(t) for t in ("A", "B")}
rec("brier_decomposition_by_decade_h12_L_primary", DECADE,
    "sum over OOS months of [(p_b - y)^2 - (p_a - y)^2] by calendar decade (oil_12m_pct_w, L, primary window); total/n = delta_brier; share = decade sum / total")
import sys, scipy, statsmodels
rec("environment", {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
                    "statsmodels": statsmodels.__version__, "matplotlib": matplotlib.__version__}, "library versions the numbers were produced with")


def rolling_auc(d, col, win=120):
    out = pd.Series(np.nan, index=d.index)
    dm = np.array([mi(x) for x in d.index]); y = d["y"].values.astype(int); p = d[col].values
    for i, T in enumerate(d.index):
        m = (dm > dm[i] - win) & (dm <= dm[i])
        if y[m].sum() > 0 and y[m].sum() < m.sum():
            out.iloc[i] = auc_mw(p[m], y[m])
    return out


ROLL = {}
for t in ("A", "B"):
    d = RUNS[(12, t, "L")]; d = d[d["scored"] & (d.index >= FIRST_PRED["primary"])]
    ROLL[t] = pd.DataFrame({"a": rolling_auc(d, "p_a"), "b_w": rolling_auc(d, "p_b_w"), "b_nopi": rolling_auc(d, "p_b_nopi")})

# ---------------------------------------------------------------- dump the OOS forecasts for audit
frames = []
for (h, t, v), d in RUNS.items():
    x = d.copy(); x.attrs = {}; x.insert(0, "variant", v); x.insert(0, "target", t); x.insert(0, "h", h); frames.append(x.reset_index())
pd.concat(frames).to_csv(f"{OUT}/oos_forecasts.csv", index=False)
print(f"tables done [{time.time()-T0:.0f}s]", flush=True)

# ================================================================ figures (chart rules: one y-axis per panel, fixed identity colours)
INK, INK2, SURF, GRID, BAND = "#0b0b0b", "#52514e", "#fcfcfb", "#e6e5e1", "#e5e4e0"
C_A, C_B, C_NOPI, C_D3, C_V, C_M = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7", "#e87ba4"
PEND = "#8a8985"
REC_SPANS = [(pd.Timestamp(s + "-01"), pd.Timestamp(e + "-01")) for s, e in zip(EV["recession_onsets"], EV["recession_ends"])]
plt.rcParams.update({"font.size": 10, "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "legend.fontsize": 9})


import textwrap


def style(ax, title, sub, width=150):
    ax.set_facecolor(SURF); ax.grid(color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_color(GRID)
    sub = textwrap.fill(sub, width); nl = sub.count("\n") + 1
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=14 + 12 * nl)
    ax.text(0, 1.012, sub, transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom", linespacing=1.25)


def shade(ax, x0=None):
    for s, e in REC_SPANS:
        if x0 is None or e >= x0:
            ax.axvspan(s, e, color=BAND, alpha=0.6, lw=0, zorder=0)


X0, X1 = pd.Timestamp("1969-06-01"), pd.Timestamp("2025-06-01")
dA = RUNS[(12, "A", "L")]; dAs = dA[dA["scored"]]
dB = RUNS[(12, "B", "L")]; dBs = dB[dB["scored"]]
pA, pB = DEC["A"], DEC["B"]

# --- Figure 2: OOS probabilities / rolling AUC / beta_oil
fig, axes = plt.subplots(3, 1, figsize=(11, 16)); fig.patch.set_facecolor(SURF)
ax = axes[0]
style(ax, "Walk-forward recession probability: curve-only vs curve + oil (Target A, 12-month horizon)",
      "P(NBER recession within 12 months), expanding-window probit refit every month with NBER-announcement-lagged labels (L variant); "
      "out-of-sample 1970-01..2024-08; curve = GS10−TB3MS, oil = WTISPLC 12m % change winsorised ±100; NBER recessions shaded")
shade(ax, pd.Timestamp("1969-01-01"))
ax.plot(dAs.index, dAs["p_a"], color=C_A, lw=2, label="(a) curve-only")
ax.plot(dAs.index, dAs["p_b_w"], color=C_B, lw=2, label="(b) curve + oil (12m % chg)")
ax.set_ylim(0, 1); ax.set_xlim(X0, X1); ax.set_ylabel("probability of recession within 12m")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), frameon=False, ncol=2)
ax = axes[1]
style(ax, "120-month rolling out-of-sample AUC: does adding oil help the ranking?",
      "AUC (Mann–Whitney) on the trailing 120 calendar months of OOS forecasts ending at each month, h = 12, L variant, 1970-01..2024-08; "
      "solid = Target A (deployed labels), dashed = Target B (recession months excluded); blank where a window has one class only")
shade(ax, pd.Timestamp("1969-01-01"))
ax.plot(ROLL["A"].index, ROLL["A"]["a"], color=C_A, lw=2, label="(a) curve-only, Target A")
ax.plot(ROLL["A"].index, ROLL["A"]["b_w"], color=C_B, lw=2, label="(b) curve + oil, Target A")
ax.plot(ROLL["B"].index, ROLL["B"]["a"], color=C_A, lw=2, ls="--", label="(a) curve-only, Target B")
ax.plot(ROLL["B"].index, ROLL["B"]["b_w"], color=C_B, lw=2, ls="--", label="(b) curve + oil, Target B")
ax.axhline(0.5, color=INK2, lw=1, ls=":")
ax.set_ylim(-0.02, 1.02); ax.set_xlim(X0, X1); ax.set_ylabel("rolling OOS AUC (120m)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), frameon=False, ncol=4)
ax.text(0.01, 0.03,
        f"full-sample ΔAUC (b)−(a), block-bootstrap 90% [5th, 95th]:\n"
        f"Target A  {pA['scores']['delta_auc']:+.3f}  [{pA['block_boot']['auc_p5']:+.3f}, {pA['block_boot']['auc_p95']:+.3f}]   "
        f"cycle [{pA['cycle_boot']['auc_p5']:+.3f}, {pA['cycle_boot']['auc_p95']:+.3f}]\n"
        f"Target B  {pB['scores']['delta_auc']:+.3f}  [{pB['block_boot']['auc_p5']:+.3f}, {pB['block_boot']['auc_p95']:+.3f}]   "
        f"cycle [{pB['cycle_boot']['auc_p5']:+.3f}, {pB['cycle_boot']['auc_p95']:+.3f}]",
        transform=ax.transAxes, ha="left", va="bottom", fontsize=8.5, color=INK,
        bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=GRID))
ax = axes[2]
style(ax, "Oil coefficient across the walk-forward refits (sign criterion counts refits from 1986-01)",
      "β on the winsorised 12m oil change in specification (b), one expanding-window refit per month 1970-01..2024-08, L variant; "
      "solid = Target A, dashed = Target B; dotted horizontal = 0; grey ✕ = refit that inherited the previous month's coefficients (none if absent)")
shade(ax, pd.Timestamp("1969-01-01"))
ax.plot(dA.index, dA["beta_oil_w"], color=C_B, lw=2, label="β_oil, (b) curve + oil, Target A")
ax.plot(dB.index, dB["beta_oil_w"], color=C_B, lw=2, ls="--", label="β_oil, (b) curve + oil, Target B")
for d_, mk in ((dA, "x"), (dB, "x")):
    bad = d_[d_["fail_b_w"].astype(bool)]
    if len(bad):
        ax.plot(bad.index, bad["beta_oil_w"], ls="none", marker=mk, ms=9, color=PEND, label="inherited coefficients")
ax.axhline(0, color=INK2, lw=1, ls=":")
ax.axvline(SIGN_FROM, color=INK2, lw=1.2, ls="--")
ax.text(SIGN_FROM + pd.DateOffset(months=3), 0.105, "1986-01: sign criterion starts", color=INK2, fontsize=8.5, va="bottom")
ax.set_xlim(X0, X1); ax.set_ylabel("β_oil (probit index per 1 pct-pt of 12m oil change)")
ax.legend(loc="upper right", frameon=False)
ax.text(0.99, 0.5,
        f"share of refits 1986-01..{pA['sign']['final_refit_month']} with β_oil > 0:  Target A {pA['sign']['sign_frac_1986']:.3f}, Target B {pB['sign']['sign_frac_1986']:.3f}\n"
        f"final refit β_oil:  Target A {pA['sign']['final_beta_oil']:+.4f}, Target B {pB['sign']['final_beta_oil']:+.4f}",
        transform=ax.transAxes, ha="right", va="center", fontsize=8.5, color=INK, bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=GRID))
fig.subplots_adjust(left=0.07, right=0.985, top=0.955, bottom=0.05, hspace=0.5)
fig.savefig(f"{OUT}/fig2_walk_auc.png", dpi=150, facecolor=SURF); plt.close(fig)

# --- Figure 2b: bootstrap distributions of the decision deltas (4 stacked panels, one y-axis each)
fig, axes = plt.subplots(4, 1, figsize=(11, 21)); fig.patch.set_facecolor(SURF)
for i, (q, lab) in enumerate((("auc", "ΔAUC (b) − (a)"), ("brier", "ΔBrier (b) − (a)"))):
    for j, t in enumerate(("A", "B")):
        pnl = DEC[t]; ax = axes[i * 2 + j]
        blk = np.asarray(pnl["_draws"][f"block_{q}"]); cyc = np.asarray(pnl["_draws"][f"cycle_{q}"])
        style(ax, f"Bootstrap distribution of {lab}, Target {t}: does the 90% interval exclude 0?",
              f"h = 12, oil = 12m % chg winsorised, L variant, OOS 1970-01..2024-08 (n = {pnl['scores']['n']}); "
              f"moving-block bootstrap (36-month blocks, 1,000 draws) vs whole-cycle resampling ({pnl['cycle_boot']['n_cycles']} peak-to-peak cycles, 1,000 draws); "
              "numpy Generator seed 20260915; dotted = 0, solid = point estimate")
        lo, hi = min(blk.min(), cyc.min()), max(blk.max(), cyc.max())
        bins = np.linspace(lo, hi, 45)
        ax.hist(blk, bins=bins, color=C_V, alpha=0.6, label="moving-block bootstrap", zorder=2)
        ax.hist(cyc, bins=bins, color=C_M, alpha=0.6, label="cycle bootstrap", zorder=2)
        ax.axvline(0, color=INK, lw=1.5, ls=":")
        pt = pnl["scores"][f"delta_{q}"]
        ax.axvline(pt, color=INK2, lw=2)
        ax.text(pt, ax.get_ylim()[1] * 0.55, f" point {pt:+.4f}", color=INK, fontsize=8.5, va="center")
        b5, b95 = pnl["block_boot"][f"{q}_p5"], pnl["block_boot"][f"{q}_p95"]
        c5, c95 = pnl["cycle_boot"][f"{q}_p5"], pnl["cycle_boot"][f"{q}_p95"]
        ax.text(0.01, 0.97, f"block 90%: [{b5:+.4f}, {b95:+.4f}]\ncycle 90%: [{c5:+.4f}, {c95:+.4f}]", transform=ax.transAxes,
                fontsize=8.5, color=INK, va="top", bbox=dict(boxstyle="round,pad=0.3", fc=SURF, ec=GRID))
        ax.set_xlabel(lab); ax.set_ylabel("draws"); ax.legend(loc="upper right", frameon=False)
fig.subplots_adjust(left=0.07, right=0.985, top=0.965, bottom=0.03, hspace=0.55)
fig.savefig(f"{OUT}/fig2b_bootstrap.png", dpi=150, facecolor=SURF); plt.close(fig)

# --- Figure 3: reliability diagram (a) vs (b), h = 12
EDGES = [0.1, 0.2, 0.3, 0.5]; BNAMES = ["0–10%", "10–20%", "20–30%", "30–50%", "50–100%"]
REL = {}
fig, axes = plt.subplots(2, 1, figsize=(11, 11.5)); fig.patch.set_facecolor(SURF)
for i, t in enumerate(("A", "B")):
    d = RUNS[(12, t, "L")]; d = d[d["scored"] & (d.index >= FIRST_PRED["primary"])]
    y = d["y"].values.astype(int)
    ax = axes[i]
    style(ax, f"Reliability of the walk-forward forecasts: curve-only vs curve + oil (Target {t}, 12-month horizon)",
          f"OOS 1970-01..2024-08, L variant, n = {len(y)}, positives = {int(y.sum())}; buckets of predicted probability 0–10 / 10–20 / 20–30 / 30–50 / 50–100%; "
          "x = mean predicted, y = realised recession-within-12m frequency; dotted diagonal = perfect calibration; n printed per bucket")
    ax.plot([0, 1], [0, 1], color=INK2, lw=1, ls=":")
    REL[t] = {}
    for col, lab, colr, mk, off, ha_ in (("p_a", "(a) curve-only", C_A, "o", (-14, 10), "right"), ("p_b_w", "(b) curve + oil", C_B, "s", (14, -10), "left")):
        p = d[col].values; b = np.digitize(p, EDGES)
        xs, ys, ns = [], [], []
        for k in range(5):
            m = b == k
            if m.sum():
                xs.append(float(p[m].mean())); ys.append(float(y[m].mean())); ns.append(int(m.sum()))
            REL[t][f"{col}|{BNAMES[k]}"] = {"n": int(m.sum()), "mean_pred": float(p[m].mean()) if m.sum() else None,
                                            "realised": float(y[m].mean()) if m.sum() else None}
        ax.plot(xs, ys, color=colr, lw=2, marker=mk, ms=9, label=lab, zorder=3)
        for x_, y_, n_ in zip(xs, ys, ns):
            ax.annotate(f"n={n_}", (x_, y_), xytext=off, textcoords="offset points", color=INK2, fontsize=8.5, ha=ha_, va="center")
    ax.set_xlim(0, 1); ax.set_ylim(-0.05, 1.05); ax.set_xlabel("mean predicted probability in bucket"); ax.set_ylabel("realised frequency")
    sc = DEC[t]["scores"]
    ax.text(0.99, 0.03, f"Brier (a) {sc['brier_a']:.4f}   (b) {sc['brier_b']:.4f}   Δ {sc['delta_brier']:+.4f}\n"
                        f"AUC (a) {sc['auc_a']:.3f}   (b) {sc['auc_b']:.3f}   Δ {sc['delta_auc']:+.3f}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color=INK, bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=GRID))
    ax.legend(loc="upper left", frameon=False)
fig.subplots_adjust(left=0.07, right=0.985, top=0.92, bottom=0.05, hspace=0.45)
fig.savefig(f"{OUT}/fig3_reliability.png", dpi=150, facecolor=SURF); plt.close(fig)
rec("reliability_h12_L_primary", REL, "reliability buckets on unclipped OOS p (h=12, L, primary window): n, mean predicted, realised frequency, per model and target")
print(f"figures done [{time.time()-T0:.0f}s]", flush=True)

# ================================================================ results.md
def f3(x, sign=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.3f}" if sign else f"{x:.3f}"


def f4(x, sign=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.4f}" if sign else f"{x:.4f}"


L = []
L.append("# walk — Q2 decision test: walk-forward (a) curve-only vs (b) curve + oil, uncertainty, marginal effects\n")
L.append("Inputs: panel.csv / events.json (frozen). Sample 1953-04+ on `spread_gs` (GS10−TB3MS). Expanding window, refit every month, "
         "first prediction 1970-01 (primary) / 1986-01 (secondary, same refits, scored from 1986-01), last scored month T ≤ 2025-08 − h. "
         "Estimator: statsmodels Probit, Newton, maxiter 100. Oil regressor: `oil_12m_pct_w` (decision) and `nopi36_sum12` (confirmatory). "
         "Labels: Target A y=1 if USREC=1 in t+1..t+h; Target B drops usrec_t=1 rows from fitting AND scoring, (a) refit on the same rows. "
         "L variant (decision): label-1 row usable at origin T iff t+h ≤ T and T ≥ NBER announcement month of its peak; label-0 row iff t+h+12 ≤ T. "
         "noL: t+h ≤ T (BACKTEST.md §B). AUC/Brier on unclipped p; log-score on p clipped to [0.01, 0.99]. Δ = (b) − (a). "
         "Block bootstrap: moving blocks of 36 months, 1,000 draws, seed 20260915. Cycle bootstrap: whole peak-to-peak cycles cut at "
         "1973-12/1980-02/1981-08/1990-08/2001-04/2008-01/2020-03, resampled with replacement, 1,000 draws. All numbers in numbers.json; every OOS forecast in oos_forecasts.csv.\n")

L.append("## 1. DECISION — h = 12, oil = 12m % change winsorised, primary window 1970-01..2024-08, L variant\n")
L.append("| target | n OOS | n pos | AUC (a) | AUC (b) | ΔAUC | block 90% | cycle 90% | Brier (a) | Brier (b) | ΔBrier | block 90% | cycle 90% | Δlog-score | β_oil>0 share 1986+ | final β_oil | verdict |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for t in ("A", "B"):
    p = DEC[t]; s = p["scores"]; b = p["block_boot"]; c = p["cycle_boot"]; g = p["sign"]
    L.append(f"| {t} | {s['n']} | {s['n_pos']} | {f3(s['auc_a'])} | {f3(s['auc_b'])} | **{f3(s['delta_auc'], True)}** | [{f3(b['auc_p5'], True)}, {f3(b['auc_p95'], True)}] | "
             f"[{f3(c['auc_p5'], True)}, {f3(c['auc_p95'], True)}] | {f4(s['brier_a'], False)} | {f4(s['brier_b'], False)} | **{f4(s['delta_brier'])}** | "
             f"[{f4(b['brier_p5'])}, {f4(b['brier_p95'])}] | [{f4(c['brier_p5'])}, {f4(c['brier_p95'])}] | {f4(s['delta_logscore'])} | "
             f"{g['sign_frac_1986']:.3f} ({g['n_pos_1986']}/{g['n_refits_1986']}) | {g['final_beta_oil']:+.4f} | **{p['decision']['verdict']}** |")
L.append("")
L.append("| criterion (§4, all must hold) | Target A | Target B |")
L.append("|---|---|---|")
for k in DEC["A"]["decision"]["criteria"]:
    L.append(f"| {k} | {'PASS' if DEC['A']['decision']['criteria'][k] else 'FAIL'} | {'PASS' if DEC['B']['decision']['criteria'][k] else 'FAIL'} |")
L.append("")
L.append(f"**Verdict — Target A: {vA}; Target B: {vB}; overall (must be MET on both): {overall}.** "
         f"MET on Target A only (coincident information only)? **{'YES' if met_A_only else 'NO'}**. §5 row: {DECISION['section5_row']}.\n")
L.append("Non-identified (b) refits (oil regressor < 24 non-zero training rows → (b) forecast = (a)): "
         + "; ".join(f"Target {t}: {DEC[t]['n_nonidentified']} ({', '.join(DEC[t]['nonidentified_months']) or 'none'})" for t in ("A", "B"))
         + ". Refits that inherited the previous month's coefficients: "
         + "; ".join(f"Target {t}: (a) {DEC[t]['n_fail_a']} ({', '.join(DEC[t]['fail_a_months']) or 'none'}), (b) {DEC[t]['n_fail_b']} ({', '.join(DEC[t]['fail_b_months']) or 'none'})" for t in ("A", "B")) + ".\n")

L.append("Where the Brier deterioration comes from (sum of per-month squared-error differences (b) − (a), by decade; a positive number = oil hurt):\n")
L.append("| decade | Target A n | Target A Σ ΔSE | share | Target B n | Target B Σ ΔSE | share |")
L.append("|---|---|---|---|---|---|---|")
for ra, rb in zip(DECADE["A"], DECADE["B"]):
    L.append(f"| {ra['decade']} | {ra['n']} | {ra['sum_dSE']:+.2f} | {ra['share_of_total']*100:+.0f}% | {rb['n']} | {rb['sum_dSE']:+.2f} | {rb['share_of_total']*100:+.0f}% |")
L.append("")
L.append("## 2. Size of the label leak — same months with (L) and without (noL) the NBER announcement lag\n")
L.append("| target | AUC (a) L | AUC (a) noL | AUC (b) L | AUC (b) noL | ΔAUC L | ΔAUC noL | leak in ΔAUC (noL−L) | ΔBrier L | ΔBrier noL | verdict L | verdict noL (descriptive) |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for t in ("A", "B"):
    q = LEAK[t]
    L.append(f"| {t} | {f3(q['auc_a_L'])} | {f3(q['auc_a_noL'])} | {f3(q['auc_b_L'])} | {f3(q['auc_b_noL'])} | {f3(q['delta_auc_L'], True)} | {f3(q['delta_auc_noL'], True)} | "
             f"{f3(q['leak_in_delta_auc(noL-L)'], True)} | {f4(q['delta_brier_L'])} | {f4(q['delta_brier_noL'])} | {q['verdict_L']} | {q['verdict_noL(descriptive)']} |")
L.append("")

L.append("## 3. Confirmatory (NOPI12) and descriptive rows — the same panel; NONE of these can pass the rule (h ≠ 12, noL, 1986+ window and NOPI12 are reported beside)\n")
L.append("NOPI12 passing while the 12m % spec fails would trigger only the channel-trigger row (§5), never the odds row. h ≠ 12 passing alone = descriptive note.\n")
L.append("| h | oil | labels | window | target | OOS | n | n pos | AUC (a) | AUC (b) | ΔAUC | block 90% | cycle 90% | ΔBrier | block 90% | cycle 90% | Δlog-score | β_oil>0 1986+ | final β_oil | non-id | rule outcome | can decide? |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
order = sorted(PANELS.keys(), key=lambda k: (k[0] != 12, k[0], k[4] != "w", k[2] != "L", k[3] != "primary", k[1]))
for key in order:
    p = PANELS[key]; s = p["scores"]; b = p["block_boot"]; c = p["cycle_boot"]; g = p["sign"]
    L.append(f"| {p['h']} | {'12m%w' if p['oil']=='w' else 'NOPI12'} | {p['variant']} | {p['window']} | {p['target']} | {p['oos_first']}..{p['oos_last']} | {s['n']} | {s['n_pos']} | "
             f"{f3(s['auc_a'])} | {f3(s['auc_b'])} | {f3(s['delta_auc'], True)} | [{f3(b['auc_p5'], True)}, {f3(b['auc_p95'], True)}] | [{f3(c['auc_p5'], True)}, {f3(c['auc_p95'], True)}] | "
             f"{f4(s['delta_brier'])} | [{f4(b['brier_p5'])}, {f4(b['brier_p95'])}] | [{f4(c['brier_p5'])}, {f4(c['brier_p95'])}] | {f4(s['delta_logscore'])} | "
             f"{g['sign_frac_1986']:.3f} | {g['final_beta_oil']:+.4f} | {p['n_nonidentified']} | {p['decision']['verdict']} | {'**DECIDES**' if p['can_decide'] else 'no'} |")
L.append("")

L.append("## 4. Marginal effects from the LAST walk-forward refit (Target B, h = 12, L variant) — reported regardless of the decision\n")
L.append(ME["basis"] + ".\n")
L.append(f"(a) params: const {a_par['const']:+.4f}, spread {a_par['spread']:+.4f}. (b) params: const {b_par['const']:+.4f}, spread {b_par['spread']:+.4f}, oil {b_par['oil']:+.5f}. "
         f"(e) params: const {e_par['const']:+.4f}, spread {e_par['spread_gs']:+.4f} (HAC z {e_z['spread_gs']:+.2f}), oil {e_par['oil_12m_pct_w']:+.5f} (z {e_z['oil_12m_pct_w']:+.2f}), "
         f"FF pace {e_par['ff_pace']:+.4f} per pp (z {e_z['ff_pace']:+.2f}).\n")
L.append("| spread_gs | P (a) curve-only | P (b), oil = 0 | ΔP +50% oil, from (b) | P (e), oil 0 / FF 0 | ΔP +50% oil, from (e) | ΔP +300bp FF pace, from (e) |")
L.append("|---|---|---|---|---|---|---|")
for r in ME["rows"]:
    L.append(f"| {r['spread_pp']:+.0f}pp | {r['P_a_curve_only']:.3f} | {r['P_b_at_oil0']:.3f} | **{r['dP_plus50_oil_from_b']:+.3f}** | {r['P_e_at_oil0_ff0']:.3f} | {r['dP_plus50_oil_from_e']:+.3f} | **{r['dP_plus300bp_ff_from_e']:+.3f}** |")
L.append("")
L.append("If the decision rule is NOT met these effects are never applied to today's spread (§4 Q5 rule).\n")

L.append("## 5. Named episodes (h = 12, L variant, primary window)\n")
L.append("### 5a. The 7 OOS onsets — forecasts in the 12 months before each onset (oil = 12m % w)\n")
L.append("| onset | target | scored window | n | p(a) at e−12 | p(b) at e−12 | max p(a) (month) | max p(b) (month) | mean p(b)−p(a) | oil at e−1 | spread at e−1 | β_oil at e−1 |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in ONSET_TAB["w"]:
    L.append(f"| {r['onset']} | {r['target']} | {r['window']} | {r['n_scored']} | {r['p_a_first']:.3f} | {r['p_b_first']:.3f} | {r['p_a_max']:.3f} ({r['p_a_max_month']}) | "
             f"{r['p_b_max']:.3f} ({r['p_b_max_month']}) | {r['mean_dp']:+.3f} | {r['oil_at_last']:+.1f}% | {r['spread_at_last']:+.2f} | {r['beta_oil_at_last']:+.4f} |")
L.append("")
L.append("### 5b. Per-cycle OOS scores (cycles cut at the onset months)\n")
L.append("| cycle | target | n | n pos | AUC (a) | AUC (b) | ΔAUC | Brier (a) | Brier (b) | ΔBrier |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
for t in ("A", "B"):
    for r in CYCLE_TAB[f"{t}_w"]:
        da_ = (r["auc_b"] - r["auc_a"]) if (r["auc_a"] == r["auc_a"] and r["auc_b"] == r["auc_b"]) else float("nan")
        L.append(f"| {r['cycle']} | {t} | {r['n']} | {r['n_pos']} | {f3(r['auc_a'])} | {f3(r['auc_b'])} | {f3(da_, True)} | {r['brier_a']:.4f} | {r['brier_b']:.4f} | {r['brier_b']-r['brier_a']:+.4f} |")
L.append("")
L.append("### 5c. Stretches where oil moved the forecast by ≥ 5pp (Target A; share of those months that were followed by recession within 12m)\n")
L.append("| stretch | n | direction | mean Δp | max |Δp| | share y = 1 | in recession at start |")
L.append("|---|---|---|---|---|---|---|")
for r in STRETCH["A"]:
    L.append(f"| {r['stretch']} | {r['n']} | {r['direction']} | {r['mean_dp']:+.3f} | {r['max_abs_dp']:.3f} | {r['share_y1']:.2f} | {'yes' if r['in_recession_at_start'] else 'no'} |")
L.append("")

L.append("## 6. Figures\n")
L.append("- `fig2_walk_auc.png` — top: OOS P(recession within 12m) from (a) and (b), Target A, 1970-01..2024-08, NBER shaded; middle: 120-month rolling OOS AUC, both targets; bottom: β_oil across all refits with the 1986-01 sign-criterion line.")
L.append("- `fig2b_bootstrap.png` — moving-block (36m) vs cycle bootstrap distributions of ΔAUC and ΔBrier, Target A and B, with the point estimate and 90% bounds.")
L.append("- `fig3_reliability.png` — reliability diagram (a) vs (b), h = 12, buckets 0–10/10–20/20–30/30–50/50–100%, counts printed, Target A (top) and Target B (bottom).\n")

L.append("## 7. Spec readings (no ambiguity resolved by threshold search)\n")
CHOICES = [
    "1986-01 secondary window: same expanding window from 1953-04 and the same monthly refits; only the first SCORED month differs (spec: 'first prediction 1986-01').",
    "Clipping to [0.01, 0.99] is applied to the log-score only (spec: 'clipped … for the log-score'); AUC and Brier use unclipped p, clipped twins are in numbers.json.",
    "Label-1 knowledge date = announcement month of the peak of the recession containing the FIRST usrec=1 month in t+1..t+h; an announcement dated inside month T counts as known at origin T (T ≥ announcement month).",
    "Label-0 rows: usable iff t+h+12 ≤ T (as instructed); no separate trough-announcement rule beyond that.",
    "SUGGESTIVE = point ΔAUC ≥ 0.02 with the block-bootstrap ΔAUC or ΔBrier 90% interval including 0; a row failing only the sign or ΔBrier-point criteria is NOT MET.",
    "Overall verdict = the weaker of the two target verdicts; 'MET on Target A only' flagged separately.",
    "Non-identified refits (< 24 non-zero oil training rows) keep their fitted β for the record but are excluded from the sign fraction; their (b) forecast is (a)'s.",
    "Target B refits run in recession months too (unscored), so the β_oil series is monthly for both targets.",
    "(e) is fitted once on the last refit's training rows restricted to FF availability (1955-07+); it is not walked forward.",
    "The cycle bootstrap uses the 7 onset months as cut points, giving 8 segments on the primary window (the pre-1973-12 stub and the post-2020-03 tail are segments too).",
]
for c in CHOICES:
    L.append(f"- {c}")
open(f"{OUT}/results.md", "w").write("\n".join(L) + "\n")
rec("spec_readings", CHOICES, "readings of the spec taken by this block where the text allowed more than one implementation")

# ================================================================ numbers.json
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m")
    return o


KEY = {}
for t in ("A", "B"):
    for k, v in DECISION["inputs"][t].items():
        if k != "criteria":
            KEY[f"{t}_{k}"] = v
    KEY[f"{t}_noL_delta_auc"] = LEAK[t]["delta_auc_noL"]; KEY[f"{t}_noL_delta_brier"] = LEAK[t]["delta_brier_noL"]
    KEY[f"{t}_noL_ci5"] = PANELS[(12, t, "noL", "primary", "w")]["block_boot"]["auc_p5"]
    KEY[f"{t}_noL_ci95"] = PANELS[(12, t, "noL", "primary", "w")]["block_boot"]["auc_p95"]
    KEY[f"{t}_noL_brier_ci5"] = PANELS[(12, t, "noL", "primary", "w")]["block_boot"]["brier_p5"]
    KEY[f"{t}_noL_brier_ci95"] = PANELS[(12, t, "noL", "primary", "w")]["block_boot"]["brier_p95"]
    KEY[f"{t}_nopi_delta_auc"] = PANELS[(12, t, "L", "primary", "nopi")]["scores"]["delta_auc"]
    KEY[f"{t}_nopi_verdict_confirmatory"] = PANELS[(12, t, "L", "primary", "nopi")]["decision"]["verdict"]
KEY["overall_verdict"] = overall; KEY["met_on_target_A_only"] = met_A_only
KEY["dP_plus50_oil_spread0_b"] = ME["rows"][0]["dP_plus50_oil_from_b"]; KEY["dP_plus50_oil_spread1_b"] = ME["rows"][1]["dP_plus50_oil_from_b"]
KEY["dP_plus300bp_ff_spread0_e"] = ME["rows"][0]["dP_plus300bp_ff_from_e"]; KEY["dP_plus300bp_ff_spread1_e"] = ME["rows"][1]["dP_plus300bp_ff_from_e"]
rec("key_numbers", KEY, "flat copy of the decision-rule inputs (h=12, oil_12m_pct_w, primary window): L variant = decision; noL and cycle-bootstrap counterparts beside; NOPI12 confirmatory")
json.dump(_clean(NUM), open(f"{OUT}/numbers.json", "w"), indent=1)
print(json.dumps(_clean(KEY), indent=1))
print(f"DONE [{time.time()-T0:.0f}s]")
