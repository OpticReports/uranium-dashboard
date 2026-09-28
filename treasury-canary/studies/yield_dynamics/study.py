#!/usr/bin/env python3
"""Runs SPEC v1 (studies/yield-dynamics-forward-spx.md) once, end to end.

    python3 study.py            -> prints the report, writes results.json

numpy + pandas + scipy only. Deterministic (fixed seeds).

The ONE confirmatory test (spec A1) is model SMALL at h = 12, via gate_small().
power.py calls the same gate_small() on synthetic outcomes, so the power
figure describes exactly the test that was run.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import panel as P

HERE = os.path.dirname(os.path.abspath(__file__))
H = (6, 12, 18)
OOS_START = pd.Period("1991-01", "M")
SPLIT = pd.Period("2009-01", "M")          # OOS halves: 1991-2008 | 2009-end
R1_SPLIT = pd.Period("2000-01", "M")       # sub-periods 1971-1999 | 2000-end
NBOOT = 2000
SEED = 20260927
SMALL = ["S10_12", "C20_3", "L10_dev"]
KNN_FEATS = ["L10_dev", "S3_12", "S10_12", "C20_3", "SB_12"]
K = 10
SHIFT_MIN = 36                              # circular-shift null, months

# ---------------------------------------------------------------- inference


def stationary_batch(n: int, mean_block: float, nboot: int, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap, vectorized: (nboot, n) indices.
    Blocks start at a uniform random position and run a geometric length
    with the given mean, wrapping circularly."""
    k = np.arange(n)
    new = rng.random((nboot, n)) < 1.0 / mean_block
    new[:, 0] = True
    begin = np.maximum.accumulate(np.where(new, k, 0), axis=1)
    starts = rng.integers(0, n, (nboot, n))
    s0 = np.take_along_axis(starts, begin, axis=1)
    return (s0 + (k - begin)) % n


def boot_ci(values_fn, n: int, mean_block: float, seed: int, nboot=NBOOT,
            q=(0.05, 0.95)):
    rng = np.random.default_rng(seed)
    b = np.array([values_fn(ix) for ix in stationary_batch(n, mean_block, nboot, rng)])
    b = b[np.isfinite(b)]
    return [float(np.quantile(b, q[0])), float(np.quantile(b, q[1]))], b


def episodes(idx, h: int) -> int:
    """Runs of qualifying origins; runs < h months apart merge (spec A3)."""
    idx = sorted(idx)
    return int(sum(1 for i, p in enumerate(idx)
                   if i == 0 or (p - idx[i - 1]).n > h))


# ---------------------------------------------------------------- models


def logit_fit(X, y, l2, w=None):
    """Weighted logistic, intercept unpenalized.
    Objective: sum_i w_i*logloss_i + (l2/2)*||beta||^2."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    Xb = np.column_stack([np.ones(len(X)), X])

    def f(b):
        z = Xb @ b
        ll = w * (np.logaddexp(0, z) - y * z)
        g = Xb.T @ (w * (1 / (1 + np.exp(-z)) - y))
        g[1:] += l2 * b[1:]
        return ll.sum() + 0.5 * l2 * np.sum(b[1:] ** 2), g

    b0 = np.zeros(Xb.shape[1])
    m = np.average(y, weights=w)
    b0[0] = np.log((m + 1e-9) / (1 - m + 1e-9))
    return minimize(f, b0, jac=True, method="L-BFGS-B").x


def logit_pred(b, X):
    return 1 / (1 + np.exp(-(b[0] + np.asarray(X, float) @ b[1:])))


def auc(p, y):
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = pd.Series(np.concatenate([pos, neg])).rank().values
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def declustered_knn(dist: pd.Series, k: int, gap: int) -> list:
    chosen: list = []
    for per in dist.sort_values().index:
        if all(abs((per - c).n) >= gap for c in chosen):
            chosen.append(per)
            if len(chosen) == k:
                break
    return chosen


def knn_prob(tr, ycol, z_tr, z_now, h, base):
    dist = pd.Series(np.sqrt(((z_tr - z_now) ** 2).sum(1)), index=tr.index)
    nb = declustered_knn(dist, K, max(h, 12))
    ups = tr.loc[nb, ycol].astype(float).sum()
    return float((ups + 2 * base) / (len(nb) + 2))          # spec A6 shrink


# ---------------------------------------------------------------- summaries


def summarize(d: pd.DataFrame, h: int) -> dict:
    r = d[f"r{h}"]
    ok = r.notna()
    d, r = d[ok], r[ok]
    return {"n": int(len(r)), "episodes": episodes(d.index, h),
            "p_up": float((r > 0).mean()), "median": float(r.median()),
            "p10": float(r.quantile(.10)),
            "p_dn10": float((r <= -0.10).mean()),
            "p_dn20": float((r <= -0.20).mean()),
            "p_dd20": float((d[f"dd{h}"] <= -0.20).mean()),
            "p_below_cash": float((d[f"r{h}"] < d[f"carry{h}"]).mean()),
            "tr_p_up": float((d[f"tr{h}"] > 0).mean()),
            "tr_p_below_cash": float((d[f"tr{h}"] < d[f"carry{h}"]).mean())}


def base_with_ci(d: pd.DataFrame, h: int, seed: int) -> dict:
    s = summarize(d, h)
    up = (d[f"r{h}"] > 0).values.astype(float)
    ci, _ = boot_ci(lambda ix: up[ix].mean(), len(up), max(h, 24), seed)
    s["p_up_ci90"] = ci
    below = (d[f"r{h}"] < d[f"carry{h}"]).values.astype(float)
    s["p_below_cash_ci90"], _ = boot_ci(lambda ix: below[ix].mean(), len(below),
                                        max(h, 24), seed + 1)
    return s


# ---------------------------------------------------------------- M1 / M2


def m1_terciles(d: pd.DataFrame, h: int, feats: list) -> tuple[dict, dict]:
    rows, pv = {}, {}
    for f in feats:
        dd = d.dropna(subset=[f, f"r{h}"])
        lo, hi = dd[f].quantile([1 / 3, 2 / 3])
        x = dd[f].values
        up = (dd[f"r{h}"] > 0).values.astype(float)
        t = np.where(x <= lo, 0, np.where(x <= hi, 1, 2))
        cells = {name: summarize(dd[t == i], h)
                 for i, name in enumerate(("low", "mid", "high"))}
        diff = up[t == 2].mean() - up[t == 0].mean()
        # circular-shift null: rotate the feature (terciles move with it)
        n = len(x)
        null = np.array([up[np.roll(t, s) == 2].mean() - up[np.roll(t, s) == 0].mean()
                         for s in range(SHIFT_MIN, n - SHIFT_MIN + 1)])
        p = float((np.abs(null) >= abs(diff) - 1e-12).mean())

        def stat(ix):
            tb, ub = t[ix], up[ix]
            if not (tb == 2).any() or not (tb == 0).any():
                return np.nan
            return ub[tb == 2].mean() - ub[tb == 0].mean()
        ci, _ = boot_ci(stat, n, max(h, 24), SEED + 7 * feats.index(f) + h)
        rows[f] = {"cuts": [float(lo), float(hi)], "cells": cells,
                   "diff_up": float(diff), "ci90": ci, "p_shift": p}
        pv[f] = p
    return rows, pv


def m2_regime(d: pd.DataFrame, h: int) -> dict:
    return {g: summarize(x, h) for g, x in d.groupby("regime")}


def bh(pvals: dict, q: float = 0.10) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, cut = len(items), 0
    for i, (_, pv) in enumerate(items, 1):
        if pv <= q * i / m:
            cut = i
    return {k: (i < cut) for i, (k, _) in enumerate(items)}


# ---------------------------------------------------------------- M3


def walkforward(d: pd.DataFrame, h: int, feats: list, models: list,
                ycol: str | None = None) -> tuple[dict, np.ndarray, pd.PeriodIndex]:
    """At each OOS origin t, fit ONLY on origins s with s + h <= t."""
    ycol = ycol or f"up{h}"
    d = d.dropna(subset=feats + [ycol])
    oos = [t for t in d.index if t >= OOS_START]
    pred = {m: [] for m in models}
    ys = []
    for t in oos:
        tr = d.loc[:t - h]
        ytr = tr[ycol].astype(float).values
        mu, sd = tr[feats].mean(), tr[feats].std(ddof=0)
        Z = ((tr[feats] - mu) / sd).values
        z = ((d.loc[t, feats].astype(float) - mu) / sd).values
        base = ytr.mean()
        for m in models:
            if m == "base":
                pred[m].append(base)
            elif m.startswith("uni:"):
                j = feats.index(m[4:])
                b = logit_fit(Z[:, [j]], ytr, 1e-6)
                pred[m].append(float(logit_pred(b, z[[j]][None, :])[0]))
            elif m == "small":
                js = [feats.index(f) for f in SMALL]
                b = logit_fit(Z[:, js], ytr, 1e-6)
                pred[m].append(float(logit_pred(b, z[js][None, :])[0]))
            elif m == "full":
                b = logit_fit(Z, ytr, 1.0, np.full(len(ytr), 1.0 / h))   # A6
                pred[m].append(float(logit_pred(b, z[None, :])[0]))
            elif m == "knn":
                jk = [feats.index(f) for f in KNN_FEATS]
                pred[m].append(knn_prob(tr, ycol, Z[:, jk], z[jk], h, base))
        ys.append(float(d.at[t, ycol]))
    return {m: np.array(v) for m, v in pred.items()}, np.array(ys), pd.PeriodIndex(oos)


def score(pred: dict, ys: np.ndarray, oos: pd.PeriodIndex, h: int, seed: int) -> dict:
    first = oos < SPLIT
    base_se = (pred["base"] - ys) ** 2
    out = {}
    for m, pm in pred.items():
        se = (pm - ys) ** 2
        ci, _ = boot_ci(lambda ix: 1 - se[ix].mean() / base_se[ix].mean(),
                        len(ys), 2 * h, seed)
        out[m] = {"brier": float(se.mean()),
                  "bss": float(1 - se.mean() / base_se.mean()),
                  "bss_ci90": ci,
                  "bss_halves": [float(1 - se[k].mean() / base_se[k].mean())
                                 for k in (first, ~first)],
                  "auc": auc(pm, ys), "n_oos": int(len(ys))}
    return out


def small_coefs(d: pd.DataFrame, ycol: str) -> np.ndarray:
    dd = d.dropna(subset=SMALL + [ycol])
    Z = ((dd[SMALL] - dd[SMALL].mean()) / dd[SMALL].std(ddof=0)).values
    return logit_fit(Z, dd[ycol].astype(float).values, 1e-6)[1:]


def gate_small(d: pd.DataFrame, h: int = 12, ycol: str | None = None,
               seed: int = SEED) -> dict:
    """THE confirmatory test (spec A1). Pass iff:
    1. OOS BSS > 0 and its 90% CI lower bound > 0;
    2. BSS > 0 in both OOS halves;
    R1: every SMALL coefficient has the same sign fit on 1971-1999 and on
        2000-end;
    R3: every SMALL coefficient keeps its full-sample sign with the 20y-splice
        origins removed."""
    ycol = ycol or f"up{h}"
    pred, ys, oos = walkforward(d, h, P.FEATURES, ["base", "small"], ycol)
    s = score(pred, ys, oos, h, seed)["small"]
    c_full = small_coefs(d, ycol)
    c_a = small_coefs(d.loc[:R1_SPLIT - 1], ycol)
    c_b = small_coefs(d.loc[R1_SPLIT:], ycol)
    c_ns = small_coefs(d[~d["splice20"].astype(bool)], ycol)
    r1 = bool(np.all(np.sign(c_a) == np.sign(c_b)))
    r3 = bool(np.all(np.sign(c_ns) == np.sign(c_full)))
    c1 = s["bss"] > 0 and s["bss_ci90"][0] > 0
    c2 = min(s["bss_halves"]) > 0
    return {"pass": bool(c1 and c2 and r1 and r3), "c1": bool(c1), "c2": bool(c2),
            "r1": r1, "r3": r3, **s,
            "coef_full": c_full.tolist(), "coef_1971_1999": c_a.tolist(),
            "coef_2000_end": c_b.tolist(), "coef_ex_splice": c_ns.tolist()}


# ---------------------------------------------------------------- today


def fit_today(d: pd.DataFrame, h: int, now: pd.Series) -> dict:
    feats = P.FEATURES
    tr = d.dropna(subset=feats + [f"up{h}"])
    ytr = tr[f"up{h}"].astype(float).values
    mu, sd = tr[feats].mean(), tr[feats].std(ddof=0)
    Z = ((tr[feats] - mu) / sd).values
    z = ((now[feats].astype(float) - mu) / sd).values
    base = float(ytr.mean())
    out = {"base": base}
    for j, f in enumerate(feats):
        out[f"uni:{f}"] = float(logit_pred(logit_fit(Z[:, [j]], ytr, 1e-6), z[[j]][None, :])[0])
    js = [feats.index(f) for f in SMALL]
    out["small"] = float(logit_pred(logit_fit(Z[:, js], ytr, 1e-6), z[js][None, :])[0])
    out["full"] = float(logit_pred(logit_fit(Z, ytr, 1.0, np.full(len(ytr), 1 / h)),
                                   z[None, :])[0])
    jk = [feats.index(f) for f in KNN_FEATS]
    out["knn"] = knn_prob(tr, f"up{h}", Z[:, jk], z[jk], h, base)
    return out


def analogs(df: pd.DataFrame, now: pd.Series, k: int = K) -> list:
    """Today's nearest de-clustered months among origins whose 18m window has
    closed; >= 18 months apart so no two analog windows overlap."""
    pool = df.dropna(subset=KNN_FEATS + ["r18"])
    mu, sd = pool[KNN_FEATS].mean(), pool[KNN_FEATS].std(ddof=0)
    Z = (pool[KNN_FEATS] - mu) / sd
    z = (now[KNN_FEATS].astype(float) - mu) / sd
    dist = np.sqrt(((Z - z) ** 2).sum(1))
    rows = []
    for per in declustered_knn(dist, k, 18):
        r = df.loc[per]
        rows.append({"month": str(per), "dist": float(dist[per]),
                     **{f: float(r[f]) for f in KNN_FEATS + ["L10", "cape"]},
                     "regime": r["regime"],
                     **{f"r{h}": float(r[f"r{h}"]) for h in H},
                     **{f"dd{h}": float(r[f"dd{h}"]) for h in H},
                     **{f"carry{h}": float(r[f"carry{h}"]) for h in H}})
    return rows


def spx_long_outcomes(h: int) -> pd.Series:
    """h-month S&P price return from every month-end since the series starts
    (1927-12), with the same partial-month endpoint rule as panel.outcomes."""
    daily = P.gspc_daily()
    me = P.month_end(daily)
    last = daily.index[-1]
    if last < last + pd.offsets.BMonthEnd(0):
        me = me.iloc[:-1]
    return (me.shift(-h) / me - 1)


# ---------------------------------------------------------------- main


def main() -> dict:
    p = P.build()
    o = P.outcomes(p, H)
    full = p.join(o)
    df = full.loc[P.START:]
    now_per = df.index[-1]
    now = df.loc[now_per]
    feats = P.FEATURES
    res = {"asof": str(now_per), "splice_offset": p.attrs["splice_offset"],
           "today": {f: float(now[f]) for f in feats + ["L10", "bill", "cape", "spx"]}
           | {"regime": now["regime"]},
           "h": {}}
    pvals = {}
    for h in H:
        d = df[df[f"r{h}"].notna()]
        R = {"base": base_with_ci(d, h, SEED + h)}
        # Long-history sensitivity from the S&P alone. NOT from `full`: the
        # panel starts in 1962 (yield history), so a "1928+" slice of it was
        # silently 1962+ — caught by counter-agent A (reported 75.4% at 12m;
        # the true 1928+ figure is ~69%, the Depression is in the long sample).
        long = spx_long_outcomes(h)
        for lab, start in (("1928", "1928-01"), ("1962", "1962-01")):
            x = long.loc[start:].dropna()
            R[f"base_{lab}"] = {"n": int(len(x)), "p_up": float((x > 0).mean()),
                                "first": str(x.index[0])}
        R["terciles"], pv = m1_terciles(d, h, feats)
        pvals |= {f"{f}@{h}": v for f, v in pv.items()}
        R["today_tercile"] = {f: ("low" if now[f] <= R["terciles"][f]["cuts"][0]
                                  else "mid" if now[f] <= R["terciles"][f]["cuts"][1]
                                  else "high") for f in feats}
        R["regime"] = m2_regime(d, h)
        # exploratory walk-forward: every model, never the headline
        models = ["base"] + [f"uni:{f}" for f in feats] + ["small", "full", "knn"]
        pred, ys, oos = walkforward(d, h, feats, models)
        R["wf_exploratory"] = score(pred, ys, oos, h, SEED + 100 + h)
        R["today_models"] = fit_today(d, h, now)
        R["R1_subperiod"] = {
            lab: {f: float((sub[f"r{h}"][sub[f] > R["terciles"][f]["cuts"][1]] > 0).mean()
                           - (sub[f"r{h}"][sub[f] <= R["terciles"][f]["cuts"][0]] > 0).mean())
                  for f in feats}
            for lab, sub in (("1971-1999", d.loc[:"1999-12"]), ("2000-end", d.loc["2000-01":]))}
        R["R2_ex_recession_hindsight"] = summarize(d[d["rec"] != 1], h)
        R["R3_ex_splice"], _ = m1_terciles(d[~d["splice20"].astype(bool)], h,
                                           ["S20_12", "C20_3"])
        R["R5_rel_speed"], _ = m1_terciles(d, h, ["S10_12_rel"])
        res["h"][h] = R
    res["fdr_exploratory"] = bh(pvals, 0.10)
    res["pvals_shift"] = pvals

    d12 = df[df["r12"].notna()]
    res["gate"] = gate_small(d12, 12)
    # R6: does SMALL survive valuation? (full-sample, descriptive)
    dd = d12.dropna(subset=SMALL + ["cape"])
    cols = SMALL + ["cape"]
    Z = ((dd[cols] - dd[cols].mean()) / dd[cols].std(ddof=0)).values
    res["R6_small_plus_cape"] = {
        "coef_small_only": small_coefs(d12, "up12").tolist(),
        "coef_with_cape": logit_fit(Z, dd["up12"].astype(float).values, 1e-6)[1:].tolist(),
        "order": cols}
    res["analogs"] = analogs(df, now)
    med_cape = float(df["cape"].median())
    res["cape_median_1971"] = med_cape
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({"asof": r["asof"], "today": r["today"],
                      "gate": {k: r["gate"][k] for k in
                               ("pass", "c1", "c2", "r1", "r3", "bss", "bss_ci90",
                                "bss_halves")}},
                     indent=1, default=str))
