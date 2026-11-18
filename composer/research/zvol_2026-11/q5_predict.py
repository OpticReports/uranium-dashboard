"""Q5: which variables known at the close predict the short mid-term-volatility return?
Target: the simulator's ZVOL series (real fund from 2023-04-19, calibrated -1x mid-term before), in excess
of T-bills, over the next 1, 5 and 21 sessions. Sample: 2008-01-02 (VIX6M's first day) .. 2026-11-17.
Usage: python3 q5_predict.py DATA_DIR"""
import json, math, sys
import numpy as np
import lib, sim

D = sys.argv[1]; C = D + "/cache"; P = sim.panel(D)
days = P["days"]
vix = lib.series("^VIX", C, "close"); v3 = lib.series("^VIX3M", C, "close"); v6 = lib.series("^VIX6M", C, "close")
vvix = lib.series("^VVIX", C, "close"); spy = lib.series("SPY", C, "adj"); hyg = lib.series("HYG", C, "adj")
sd = sorted(spy); sr = lib.rets(spy); hd = sorted(hyg)
mid = P["mid"]
X = {k: {} for k in ("roll_yield_mid", "vix3m_over_vix", "vix6m_over_vix3m", "vrp", "vvix", "vix_pctile_1y", "hyg_5d", "spy_rsi2")}
vd = sorted(vix)
for i, d in enumerate(days):
    m = mid.get(d)
    if m and all(m["F"]) and len(m["F"]) == 4:
        X["roll_yield_mid"][d] = (m["F"][3] - m["F"][0]) / (sum(m["F"]) / 4.0)          # 4th-7th month slope; > 0 = contango
    if d in v3 and d in vix:
        X["vix3m_over_vix"][d] = v3[d] / vix[d] - 1
    if d in v6 and d in v3:
        X["vix6m_over_vix3m"][d] = v6[d] / v3[d] - 1
    j = sd.index(d) if d in spy else None
    if j is not None and j >= 21 and d in vix:
        rv = sum(sr[sd[k]] ** 2 for k in range(j - 20, j + 1)) * 252 / 21 * 1e4          # annualised variance, % squared
        X["vrp"][d] = vix[d] ** 2 - rv
    if d in vvix:
        X["vvix"][d] = vvix[d]
    if d in vix:
        k = vd.index(d)
        if k >= 252:
            win = [vix[x] for x in vd[k - 252:k]]
            X["vix_pctile_1y"][d] = sum(1 for x in win if x <= vix[d]) / 252.0
    if d in hyg:
        k = hd.index(d)
        if k >= 5:
            X["hyg_5d"][d] = hyg[d] / hyg[hd[k - 5]] - 1
    if P["rsi"][2].get(d) is not None:
        X["spy_rsi2"][d] = P["rsi"][2][d]
ex = [P["ZVOL"][d] - P["BIL"][d] for d in days]
def fwd(i, h):
    return math.prod(1 + ex[k] for k in range(i + 1, i + 1 + h)) - 1 if i + h < len(days) else None
A = days.index(next(d for d in days if d >= "2008-01-02"))
tests = []; out = {"sample": [days[A], days[-1]], "predictors": {}}
for name, x in X.items():
    out["predictors"][name] = {}
    for h in (1, 5, 21):
        rows = [(x[days[i]], fwd(i, h)) for i in range(A, len(days)) if days[i] in x and fwd(i, h) is not None]
        xs = np.array([a for a, _ in rows]); ys = np.array([b for _, b in rows])
        z = (xs - xs.mean()) / xs.std()
        b, t, r2 = lib.nw_t(ys, z, lags=max(h - 1, 5))
        # quintiles on the full sample
        q = np.quantile(xs, [.2, .4, .6, .8]); g = np.digitize(xs, q)
        qm = [float(ys[g == k].mean()) for k in range(5)]
        # walk-forward out-of-sample R2 vs the expanding mean: refit every 21 sessions on data whose
        # forward window has closed, first third burn-in
        n = len(ys); start = n // 3; se_m = se_f = 0.0; cnt = 0
        beta = None
        for i in range(start, n):
            if (i - start) % 21 == 0:
                tr = slice(0, max(2, i - h))
                xt, yt = xs[tr], ys[tr]
                mu_x, sd_x = xt.mean(), xt.std() or 1.0
                bb = np.polyfit((xt - mu_x) / sd_x, yt, 1); beta = (bb, mu_x, sd_x, yt.mean())
            bb, mu_x, sd_x, ybar = beta
            f = bb[1] + bb[0] * (xs[i] - mu_x) / sd_x
            se_f += (ys[i] - f) ** 2; se_m += (ys[i] - ybar) ** 2; cnt += 1
        oos = 1 - se_f / se_m
        p = math.erfc(abs(t) / math.sqrt(2))
        out["predictors"][name][h] = {"n": n, "beta_per_sd": float(b), "t_nw": float(t), "p": p, "r2": float(r2), "oos_r2": float(oos),
                                     "quintile_means": qm, "q5_minus_q1": qm[4] - qm[0]}
        tests.append((p, name, h))
# Holm across the 24 tests
tests.sort(); m = len(tests); run = 0.0
for k, (p, name, h) in enumerate(tests):
    adj = min(1.0, max(run, (m - k) * p)); run = adj
    out["predictors"][name][h]["p_holm"] = adj
    out["predictors"][name][h]["works"] = bool(adj < 0.05 and out["predictors"][name][h]["oos_r2"] > 0)
# on the harvester's ZVOL-entry days: does each predictor split good entries from bad? (episode fund return)
r = sim.run(P, cost_bps=0.0)
rd = r["days"]
ent = [i for i in range(1, len(rd)) if r["w"][i]["ZVOL"] > 1e-9 and r["w"][i - 1]["ZVOL"] <= 1e-9 and rd[i - 1] >= days[A]]
ep = []
for i in ent:
    j = i
    while j < len(rd) and r["w"][j]["ZVOL"] > 1e-9:
        j += 1
    ep.append((rd[i - 1], math.prod(1 + P["ZVOL"][rd[k]] for k in range(i, j)) - 1))
out["entries"] = {"n": len(ep)}
for name, x in X.items():
    rows = [(x[d], f) for d, f in ep if d in x]
    xs = np.array([a for a, _ in rows]); ys = np.array([b for _, b in rows])
    med = np.median(xs); lo = ys[xs <= med]; hi = ys[xs > med]
    tt = (hi.mean() - lo.mean()) / math.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    ter = np.quantile(xs, [1 / 3, 2 / 3]); g = np.digitize(xs, ter)
    out["entries"][name] = {"n": len(ys), "below_median_mean": float(lo.mean()), "above_median_mean": float(hi.mean()), "t_diff": float(tt),
                            "tercile_means": [float(ys[g == k].mean()) for k in range(3)], "tercile_worst": [float(ys[g == k].min()) for k in range(3)],
                            "corr": float(np.corrcoef(xs, ys)[0, 1])}
out["current"] = {name: (x.get(lib.END) if lib.END in x else x.get(max(x))) for name, x in X.items()}
json.dump(out, open("out/q5_predict.json", "w"), indent=1)
print("sample", out["sample"])
for name, v in out["predictors"].items():
    for h, s in v.items():
        print(f"{name:18s} h={h:2d} n={s['n']} beta/sd {s['beta_per_sd']*1e4:+7.1f} bps t {s['t_nw']:+.2f} p_holm {s['p_holm']:.3f} R2 {s['r2']:.4f} OOS R2 {s['oos_r2']:+.4f} Q1..Q5 {[round(x*1e4) for x in s['quintile_means']]} works={s['works']}")
print("entries n", out["entries"]["n"])
for name in X:
    e = out["entries"][name]; print(f"  {name:18s} below-median {e['below_median_mean']:+.2%} above {e['above_median_mean']:+.2%} t {e['t_diff']:+.2f} terciles {[f'{x:+.2%}' for x in e['tercile_means']]} worst {[f'{x:+.1%}' for x in e['tercile_worst']]}")
print("current:", {k: (round(v, 3) if v is not None else None) for k, v in out["current"].items()})
