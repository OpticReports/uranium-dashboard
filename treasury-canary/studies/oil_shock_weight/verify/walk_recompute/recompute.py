"""Independent recomputation of the walk block's primary numbers from the spec + frozen panel.
Written WITHOUT reading run.py. Readings follow the spec text; where the block logged a reading
(results.md s7) the same reading is taken so the comparison is like-for-like, and the literal
alternative (t+h+L <= T) is run as a sensitivity."""
import json, sys, time, warnings
import numpy as np, pandas as pd
from scipy.stats import norm
import statsmodels.api as sm
warnings.filterwarnings("ignore")

D = "/tmp/claude-0/-home-user-uranium-dashboard/2a5ba7c6-de7e-5470-a27d-d0386eb4bbf1/scratchpad/oil/"
OUT = D + "verify/walk_recompute/"
panel = pd.read_csv(D + "data/panel.csv", parse_dates=["date"])
panel = panel[panel.date >= "1953-04-01"].reset_index(drop=True)
panel["ym"] = panel.date.dt.year * 12 + panel.date.dt.month - 1   # month index
usrec = panel.usrec.values.astype(int)
ym = panel.ym.values
n_all = len(panel)

def ymi(s):  # 'YYYY-MM' -> month index
    y, m = s.split("-"); return int(y) * 12 + int(m) - 1
def ymstr(i): return f"{i//12:04d}-{i%12+1:02d}"

# recession onsets from usrec (first 1 after a 0) and announcement months (spec s4)
onsets = [ym[i] for i in range(1, n_all) if usrec[i] == 1 and usrec[i-1] == 0]
if usrec[0] == 1: onsets = [ym[0]] + onsets  # 1953-04 is not in recession, fine
ann_actual = {"1980-02": "1980-06", "1981-08": "1982-01", "1990-08": "1991-04",
              "2001-04": "2001-11", "2008-01": "2008-12", "2020-03": "2020-06"}
ann = {}
for o in onsets:
    s = ymstr(o)
    ann[o] = ymi(ann_actual[s]) if s in ann_actual else (o - 1) + 12  # peak + 12 pre-1979
# recession id per month (which onset it belongs to)
rec_onset = np.full(n_all, -1)
cur = -1
for i in range(n_all):
    if usrec[i] == 1:
        if i == 0 or usrec[i-1] == 0: cur = ym[i]
        rec_onset[i] = cur
print("onsets:", [ymstr(o) for o in onsets]); print("ann:", {ymstr(k): ymstr(v) for k, v in ann.items()})

def build_labels(h):
    y = np.full(n_all, np.nan); known_block = np.full(n_all, 10**9); known_lit = np.full(n_all, 10**9); known_noL = np.full(n_all, 10**9)
    for i in range(n_all):
        if i + h >= n_all: continue
        win = usrec[i+1:i+h+1]
        if win.max() == 1:
            y[i] = 1
            j = i + 1 + int(np.argmax(win))            # first usrec=1 month in window
            o = rec_onset[j]; a = ann[o]; L = a - (o - 1)
            known_block[i] = max(ym[i] + h, a)          # block reading: t+h<=T and T>=announcement
            known_lit[i] = ym[i] + h + L                # literal: t+h+L<=T
        else:
            y[i] = 0
            known_block[i] = ym[i] + h + 12; known_lit[i] = ym[i] + h + 12
        known_noL[i] = ym[i] + h
    return y, known_block, known_lit, known_noL

def fit_probit(X, y):
    try:
        r = sm.Probit(y, X).fit(method="newton", maxiter=100, disp=0)
        if not r.mle_retvals.get("converged", True): return np.asarray(r.params), False
        return np.asarray(r.params), True
    except Exception as e:
        return None, False

def auc(p, y):
    from scipy.stats import rankdata
    y = np.asarray(y); p = np.asarray(p); n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0: return np.nan
    r = rankdata(p); return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
def brier(p, y): return np.mean((np.asarray(p) - np.asarray(y)) ** 2)

def walk(h, target, variant, oilcol, first_pred="1970-01", last_pred=None, knowledge="block"):
    y, kb, kl, kn = build_labels(h)
    known = {"block": kb, "lit": kl}[knowledge] if variant == "L" else kn
    spread = panel.spread_gs.values; oil = panel[oilcol].values
    T0 = ymi(first_pred); T1 = ymi(last_pred) if last_pred else ymi("2025-08") - h
    rows = []
    prev = {}
    for T in range(T0, T1 + 1):
        iT = T - ym[0]
        tr = (known <= T) & ~np.isnan(y) & ~np.isnan(spread)
        if target == "B": tr &= (usrec == 0)
        trb = tr & ~np.isnan(oil)
        Xa = sm.add_constant(spread[tr]); ya = y[tr]
        pa_par, ok_a = fit_probit(Xa, ya)
        if pa_par is None: pa_par = prev.get("a"); ok_a = False
        prev["a"] = pa_par
        Xb = np.column_stack([np.ones(trb.sum()), spread[trb], oil[trb]]); yb = y[trb]
        n_nonzero = int((oil[trb] != 0).sum())
        pb_par, ok_b = fit_probit(Xb, yb)
        if pb_par is None: pb_par = prev.get("b"); ok_b = False
        prev["b"] = pb_par
        nonid = n_nonzero < 24
        p_a = norm.cdf(pa_par[0] + pa_par[1] * spread[iT])
        p_b_raw = norm.cdf(pb_par[0] + pb_par[1] * spread[iT] + pb_par[2] * oil[iT])
        p_b = p_a if nonid else p_b_raw
        scored = (target == "A") or (usrec[iT] == 0)
        rows.append(dict(T=ymstr(T), h=h, target=target, variant=variant, oil=oilcol, n_train=int(tr.sum()), n_pos=int(ya.sum()),
                         train_last=ymstr(ym[tr].max()), y=y[iT], usrec_T=usrec[iT], scored=scored, spread_T=spread[iT], oil_T=oil[iT],
                         const_a=pa_par[0], beta_spread_a=pa_par[1], p_a=p_a, const_b=pb_par[0], beta_spread_b=pb_par[1], beta_oil=pb_par[2],
                         n_oil_nonzero=n_nonzero, nonid=nonid, p_b=p_b, p_b_raw=p_b_raw, ok_a=ok_a, ok_b=ok_b))
    return pd.DataFrame(rows)

def block_boot(pa, pb, y, B=1000, blk=36, seed=20260915):
    rng = np.random.default_rng(seed); n = len(y); k = int(np.ceil(n / blk))
    da, db = [], []
    for _ in range(B):
        st = rng.integers(0, n - blk + 1, size=k)
        idx = np.concatenate([np.arange(s, s + blk) for s in st])[:n]
        da.append(auc(pb[idx], y[idx]) - auc(pa[idx], y[idx])); db.append(brier(pb[idx], y[idx]) - brier(pa[idx], y[idx]))
    da = np.array(da); db = np.array(db)
    return np.nanpercentile(da, [5, 95]), np.nanpercentile(db, [5, 95]), da, db

def cycle_boot(df, B=1000, seed=20260915):
    cuts = [ymi(s) for s in ["1973-12", "1980-02", "1981-08", "1990-08", "2001-04", "2008-01", "2020-03"]]
    Tidx = df["T"].map(ymi).values
    seg = np.searchsorted(cuts, Tidx, side="right")
    segs = [np.where(seg == s)[0] for s in range(8)]
    rng = np.random.default_rng(seed); da, db = [], []
    pa, pb, y = df.p_a.values, df.p_b.values, df.y.values
    for _ in range(B):
        pick = rng.integers(0, 8, size=8)
        idx = np.concatenate([segs[i] for i in pick])
        da.append(auc(pb[idx], y[idx]) - auc(pa[idx], y[idx])); db.append(brier(pb[idx], y[idx]) - brier(pa[idx], y[idx]))
    return np.nanpercentile(np.array(da, float), [5, 95]), np.nanpercentile(np.array(db, float), [5, 95])

def score(df, first="1970-01"):
    s = df[df.scored & (df["T"] >= first)]
    pa, pb, y = s.p_a.values, s.p_b.values, s.y.values
    out = dict(n=len(s), n_pos=int(y.sum()), auc_a=auc(pa, y), auc_b=auc(pb, y), brier_a=brier(pa, y), brier_b=brier(pb, y))
    out["delta_auc"] = out["auc_b"] - out["auc_a"]; out["delta_brier"] = out["brier_b"] - out["brier_a"]
    (a5, a95), (b5, b95), _, _ = block_boot(pa, pb, y)
    out.update(ci5=a5, ci95=a95, brier_ci5=b5, brier_ci95=b95)
    if first == "1970-01":
        (c5, c95), (cb5, cb95) = cycle_boot(s); out.update(cycle_ci5=c5, cycle_ci95=c95, cycle_brier_ci5=cb5, cycle_brier_ci95=cb95)
    sg = df[(df["T"] >= "1986-01") & ~df.nonid]
    out["sign_frac_1986"] = float((sg.beta_oil > 0).mean()); out["n_sign"] = len(sg); out["final_beta"] = float(df.beta_oil.iloc[-1])
    out["n_nonid"] = int(df.nonid.sum()); out["n_fail_a"] = int((~df.ok_a).sum()); out["n_fail_b"] = int((~df.ok_b).sum())
    met = (out["delta_auc"] >= 0.02 and a5 > 0 and out["delta_brier"] < 0 and b95 < 0 and out["sign_frac_1986"] >= 0.9 and out["final_beta"] > 0)
    sugg = (not met) and out["delta_auc"] >= 0.02 and (a5 <= 0 <= a95 or b5 <= 0 <= b95)
    out["verdict"] = "MET" if met else ("SUGGESTIVE" if sugg else "NOT MET")
    return out

if __name__ == "__main__":
    t0 = time.time(); res = {}; frames = {}
    hs = [12] if len(sys.argv) < 2 else [int(x) for x in sys.argv[1].split(",")]
    for h in hs:
        for target in ["A", "B"]:
            for variant in ["L", "noL"]:
                for oilcol in ["oil_12m_pct_w", "nopi36_sum12"]:
                    if h != 12 and (variant != "L"): continue
                    df = walk(h, target, variant, oilcol); frames[(h, target, variant, oilcol)] = df
                    for win, first in [("primary", "1970-01"), ("secondary", "1986-01")]:
                        res[f"{h}|{target}|{variant}|{win}|{oilcol}"] = score(df, first)
                    print(f"h={h} {target} {variant} {oilcol} done [{time.time()-t0:.0f}s]", flush=True)
        if h == 12:
            # literal-reading sensitivity (t+h+L <= T) for label-1 rows, decision spec only
            for target in ["A", "B"]:
                df = walk(12, target, "L", "oil_12m_pct_w", knowledge="lit"); frames[(12, target, "Llit", "oil_12m_pct_w")] = df
                res[f"12|{target}|L_literal|primary|oil_12m_pct_w"] = score(df, "1970-01")
    for k, v in res.items(): print(k, {kk: (round(vv, 5) if isinstance(vv, float) else vv) for kk, vv in v.items()})
    json.dump(res, open(OUT + "recompute_numbers_h%s.json" % "_".join(map(str, hs)), "w"), indent=1, default=float)
    for k, df in frames.items(): df.to_csv(OUT + "walk_%s.csv" % "_".join(map(str, k)), index=False)

    if 12 not in hs: print(f"DONE [{time.time()-t0:.0f}s]"); sys.exit(0)
    # marginal effects from the last refit, Target B h=12 L, decision spec
    dfB = frames[(12, "B", "L", "oil_12m_pct_w")]; last = dfB.iloc[-1]
    y, kb, _, _ = build_labels(12); T = ymi("2024-08")
    tr = (kb <= T) & ~np.isnan(y) & ~np.isnan(panel.spread_gs.values) & (usrec == 0)
    b = np.array([last.const_b, last.beta_spread_b, last.beta_oil]); a = np.array([last.const_a, last.beta_spread_a])
    me = {}
    for s in [0.0, 1.0]:
        me[f"dP_plus50_oil_spread{int(s)}_b"] = norm.cdf(b[0] + b[1] * s + b[2] * 50) - norm.cdf(b[0] + b[1] * s)
    ff = panel.ff_12m_chg_bps.values / 100.0
    tre = tr & ~np.isnan(ff)
    Xe = np.column_stack([np.ones(tre.sum()), panel.spread_gs.values[tre], panel.oil_12m_pct_w.values[tre], ff[tre]])
    re = sm.Probit(y[tre], Xe).fit(method="newton", maxiter=100, disp=0)
    re_hac = sm.Probit(y[tre], Xe).fit(method="newton", maxiter=100, disp=0, cov_type="HAC", cov_kwds={"maxlags": 11})
    e = re.params
    for s in [0.0, 1.0]:
        me[f"dP_plus300bp_ff_spread{int(s)}_e"] = norm.cdf(e[0] + e[1] * s + e[3] * 3) - norm.cdf(e[0] + e[1] * s)
    me["e_params"] = list(e); me["e_hac_z"] = list(re_hac.tvalues); me["n_train_last"] = int(tr.sum()); me["n_train_e"] = int(tre.sum())
    me["train_last_month"] = ymstr(ym[tr].max())
    print("marginal:", me); json.dump(me, open(OUT + "marginal.json", "w"), indent=1, default=float)

    # named-episode table 5a: h=12, L, primary
    ep = []
    for target in ["A", "B"]:
        df = frames[(12, target, "L", "oil_12m_pct_w")].set_index("T")
        for o in ["1973-12", "1980-02", "1981-08", "1990-08", "2001-04", "2008-01", "2020-03"]:
            oi = ymi(o); w = [ymstr(i) for i in range(oi - 12, oi)]
            s = df.loc[w]
            ep.append(dict(onset=o, target=target, n=len(s), p_a_e12=s.p_a.iloc[0], p_b_e12=s.p_b.iloc[0], max_pa=s.p_a.max(), max_pa_m=s.p_a.idxmax(),
                           max_pb=s.p_b.max(), max_pb_m=s.p_b.idxmax(), mean_dp=(s.p_b - s.p_a).mean(), oil_e1=s.oil_T.iloc[-1], spread_e1=s.spread_T.iloc[-1], beta_e1=s.beta_oil.iloc[-1]))
    ep = pd.DataFrame(ep); print(ep.round(4).to_string()); ep.to_csv(OUT + "episodes_5a.csv", index=False)
    # Brier decomposition by decade (Target A, and B)
    for target in ["A", "B"]:
        df = frames[(12, target, "L", "oil_12m_pct_w")]; s = df[df.scored].copy()
        s["dse"] = (s.p_b - s.y) ** 2 - (s.p_a - s.y) ** 2; s["dec"] = s["T"].str[:3] + "0s"
        g = s.groupby("dec").dse.agg(["count", "sum"]); g["share"] = g["sum"] / g["sum"].sum(); print(target, g.round(3))
    print(f"DONE [{time.time()-t0:.0f}s]")
