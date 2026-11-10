"""Independent recomputation of the walk block's h=12 decision test from panel.csv.
Written from the spec, not from run.py: own labels, own announcement-lag mask, own probit loop,
own AUC/Brier, own bootstrap.  Compares to blocks/walk/oos_forecasts.csv and numbers.json.
Also runs (i) the LITERAL spec rule 't + h + L <= T' for label-1 rows and (ii) alternative
bootstrap seeds / block lengths to see whether the interval statements are seed-fragile."""
import json, math, warnings
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy.stats import norm, rankdata

ROOT = "/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil"
OUTD = f"{ROOT}/verify/walk_audit"
P = pd.read_csv(f"{ROOT}/data/panel.csv", index_col="date", parse_dates=True)
N = json.load(open(f"{ROOT}/blocks/walk/numbers.json"))
F = pd.read_csv(f"{ROOT}/blocks/walk/oos_forecasts.csv", parse_dates=["date"])
H = 12
mi = lambda ts: ts.year * 12 + ts.month - 1
P["mi"] = [mi(t) for t in P.index]
u = P["usrec"].values.astype(int)
n = len(P)

# ---- labels, independently
yA = np.full(n, np.nan)
for i in range(n):
    if i + H < n:
        yA[i] = 1.0 if u[i + 1:i + 1 + H].max() == 1 else 0.0
yB = np.where(u == 0, yA, np.nan)

# ---- announcement month of the peak of the recession containing the first usrec=1 month in the window
onsets = [i for i in range(1, n) if u[i] == 1 and u[i - 1] == 0]
onset_mi = np.array([P["mi"].iloc[i] for i in onsets])
ANN_ACT = {"1980-02": "1980-06", "1981-08": "1982-01", "1990-08": "1991-04", "2001-04": "2001-11", "2008-01": "2008-12", "2020-03": "2020-06"}
ann_of_onset = {}
for i in onsets:
    k = P.index[i].strftime("%Y-%m")
    ann_of_onset[P["mi"].iloc[i]] = mi(pd.Timestamp(ANN_ACT[k] + "-01")) if k in ANN_ACT else P["mi"].iloc[i] - 1 + 12  # peak + 12
peak_of_onset = {o: o - 1 for o in ann_of_onset}
ann_row = np.full(n, np.nan); lag_row = np.full(n, np.nan)   # lag_row = L of that peak (announcement - peak), for the literal rule
for i in range(n):
    if yA[i] == 1:
        j = i + 1 + int(np.argmax(u[i + 1:i + 1 + H] == 1))
        o = onset_mi[onset_mi <= P["mi"].iloc[j]].max()
        ann_row[i] = ann_of_onset[o]; lag_row[i] = ann_of_onset[o] - peak_of_onset[o]

def auc(p, y):
    r = rankdata(p); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

def fit(X, y):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = sm.Probit(y, X).fit(method="newton", maxiter=100, disp=0)
    return np.asarray(r.params), bool(r.mle_retvals.get("converged", True))

def walk(target, rule, oil="oil_12m_pct_w"):
    y = yA if target == "A" else yB
    S = P.loc["1953-04-01":].copy(); S["y"] = y[P.index.get_indexer(S.index)]
    S["ann"] = ann_row[P.index.get_indexer(S.index)]; S["lag"] = lag_row[P.index.get_indexer(S.index)]
    pool = S.dropna(subset=["y"])
    t_mi = pool["mi"].values; yv = pool["y"].values.astype(int); annv = pool["ann"].values; lagv = pool["lag"].values
    xs = pool["spread_gs"].values; xo = pool[oil].values
    out = []; nconv = 0
    for T in pd.date_range("1970-01-01", "2024-08-01", freq="MS"):
        Tm = mi(T)
        if rule == "L":          # block's reading: known once window closed and peak announced
            m = ((yv == 1) & (t_mi + H <= Tm) & (annv <= Tm)) | ((yv == 0) & (t_mi + H + 12 <= Tm))
        elif rule == "literal":  # spec text: t + h + L <= T, L = announcement - peak for label-1, 12 for label-0
            m = ((yv == 1) & (t_mi + H + lagv <= Tm)) | ((yv == 0) & (t_mi + H + 12 <= Tm))
        else:                    # noL
            m = t_mi + H <= Tm
        ytr = yv[m]
        pa, ca = fit(np.column_stack([np.ones(m.sum()), xs[m]]), ytr)
        pb, cb = fit(np.column_stack([np.ones(m.sum()), xs[m], xo[m]]), ytr)
        nconv += (not ca) + (not cb)
        sT = float(P.at[T, "spread_gs"]); oT = float(P.at[T, oil])
        out.append({"date": T, "n_train": int(m.sum()), "n_train_pos": int(ytr.sum()), "y": y[P.index.get_loc(T)],
                    "p_a": norm.cdf(pa[0] + pa[1] * sT), "p_b": norm.cdf(pb[0] + pb[1] * sT + pb[2] * oT), "beta_oil": pb[2],
                    "nz": int((xo[m] != 0).sum())})
    d = pd.DataFrame(out).set_index("date"); d.attrs["nconv_fail"] = nconv
    return d

def score(d):
    s = d.dropna(subset=["y"]); y = s["y"].values.astype(int); pa = s["p_a"].values; pb = s["p_b"].values
    return {"n": len(y), "n_pos": int(y.sum()), "auc_a": auc(pa, y), "auc_b": auc(pb, y), "dauc": auc(pb, y) - auc(pa, y),
            "brier_a": np.mean((pa - y) ** 2), "brier_b": np.mean((pb - y) ** 2), "dbrier": np.mean((pb - y) ** 2) - np.mean((pa - y) ** 2)}

def block_boot(d, block=36, ndraw=1000, seed=20260915):
    s = d.dropna(subset=["y"]); y = s["y"].values.astype(int); pa = s["p_a"].values; pb = s["p_b"].values
    rng = np.random.default_rng(seed); nn = len(y); nb = math.ceil(nn / block); da = []; db = []
    for _ in range(ndraw):
        st = rng.integers(0, nn - block + 1, size=nb); idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:nn]
        yy = y[idx]
        if yy.sum() in (0, nn): continue
        da.append(auc(pb[idx], yy) - auc(pa[idx], yy)); db.append(np.mean((pb[idx] - yy) ** 2) - np.mean((pa[idx] - yy) ** 2))
    return np.percentile(da, [5, 95]).tolist(), np.percentile(db, [5, 95]).tolist()

def stationary_boot(d, mean_block=36, ndraw=1000, seed=1):
    """Politis-Romano stationary bootstrap, geometric block lengths (mean 36) -- a different resampling scheme."""
    s = d.dropna(subset=["y"]); y = s["y"].values.astype(int); pa = s["p_a"].values; pb = s["p_b"].values
    rng = np.random.default_rng(seed); nn = len(y); da = []; db = []
    for _ in range(ndraw):
        idx = [];
        while len(idx) < nn:
            st = rng.integers(0, nn); ln = rng.geometric(1 / mean_block); idx.extend(((st + np.arange(ln)) % nn).tolist())
        idx = np.array(idx[:nn]); yy = y[idx]
        if yy.sum() in (0, nn): continue
        da.append(auc(pb[idx], yy) - auc(pa[idx], yy)); db.append(np.mean((pb[idx] - yy) ** 2) - np.mean((pa[idx] - yy) ** 2))
    return np.percentile(da, [5, 95]).tolist(), np.percentile(db, [5, 95]).tolist()

RES = {}
for target in ("A", "B"):
    for rule in ("L", "noL", "literal"):
        d = walk(target, rule); RES[(target, rule)] = d
        sc = score(d)
        line = f"{target} {rule:8s} n={sc['n']} pos={sc['n_pos']} AUC a/b {sc['auc_a']:.4f}/{sc['auc_b']:.4f} dAUC {sc['dauc']:+.4f} Brier a/b {sc['brier_a']:.4f}/{sc['brier_b']:.4f} dBrier {sc['dbrier']:+.4f} conv_fail={d.attrs['nconv_fail']} min_nz={d['nz'].min()}"
        if rule in ("L", "noL"):
            blk = F[(F.h == 12) & (F.target == target) & (F.variant == rule)].set_index("date")
            j = d.join(blk[["p_a", "p_b_w", "n_train", "n_train_pos", "beta_oil_w"]], rsuffix="_blk")
            line += (f" | vs block: max|dp_a| {np.abs(j.p_a - j.p_a_blk).max():.2e} max|dp_b| {np.abs(j.p_b - j.p_b_w).max():.2e} "
                     f"n_train diff max {np.abs(j.n_train - j.n_train_blk).max()} n_pos diff max {np.abs(j.n_train_pos - j.n_train_pos_blk).max()} "
                     f"beta diff max {np.abs(j.beta_oil - j.beta_oil_w).max():.2e}")
            bb = block_boot(d); line += f" | block90 dAUC [{bb[0][0]:+.4f},{bb[0][1]:+.4f}] dBrier [{bb[1][0]:+.4f},{bb[1][1]:+.4f}]"
        else:
            bb = block_boot(d); line += f" | block90 dAUC [{bb[0][0]:+.4f},{bb[0][1]:+.4f}] dBrier [{bb[1][0]:+.4f},{bb[1][1]:+.4f}]"
            sign86 = (d.loc["1986-01-01":, "beta_oil"] > 0).mean(); line += f" sign86={sign86:.3f} final_beta={d['beta_oil'].iloc[-1]:+.4f}"
        print(line, flush=True)

print("\n--- bootstrap robustness on the block's own L forecasts (decision rows) ---")
for target in ("A", "B"):
    d = RES[(target, "L")]
    for seed in (20260915, 1, 2, 3):
        for block in (24, 36, 48):
            bb = block_boot(d, block=block, seed=seed)
            print(f"{target} seed={seed} block={block}: dAUC90 [{bb[0][0]:+.4f},{bb[0][1]:+.4f}] dBrier90 [{bb[1][0]:+.4f},{bb[1][1]:+.4f}]")
    sb = stationary_boot(d); print(f"{target} stationary(mean 36): dAUC90 [{sb[0][0]:+.4f},{sb[0][1]:+.4f}] dBrier90 [{sb[1][0]:+.4f},{sb[1][1]:+.4f}]")

print("\n--- literal-rule vs block-rule training-set differences (Target A): months where n_train differs ---")
dl, db_ = RES[("A", "literal")], RES[("A", "L")]
diff = (db_["n_train"] - dl["n_train"]); print("max extra rows under block rule:", diff.max(), "at", diff.idxmax().strftime("%Y-%m"), "; months with any difference:", int((diff != 0).sum()))

# NOPI confirmatory quick check (L rule)
for target in ("A", "B"):
    d = walk(target, "L", oil="nopi36_sum12"); sc = score(d)
    blk = F[(F.h == 12) & (F.target == target) & (F.variant == "L")].set_index("date")
    j = d.join(blk[["p_b_nopi", "nonid_nopi"]])
    j.loc[j.nonid_nopi.astype(bool), "p_b"] = j.loc[j.nonid_nopi.astype(bool), "p_a"]   # apply the fallback the same way
    sc = score(j.rename(columns={"p_b": "p_b"}))
    print(f"NOPI {target} L: dAUC {sc['dauc']:+.4f} dBrier {sc['dbrier']:+.4f} | block says {N['key_numbers']['value'][target + '_nopi_delta_auc']:+.4f}; max|dp_b| vs block {np.abs(j.p_b - j.p_b_nopi).max():.2e}")

pd.concat({k: v for k, v in RES.items()}, names=["target", "rule"]).to_csv(f"{OUTD}/recompute_forecasts.csv")
