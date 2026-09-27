#!/usr/bin/env python3
"""Runs SPEC (studies/yield-dynamics-forward-spx.md) once, end to end.

    python3 study.py            -> prints the report, writes results.json

numpy + pandas + scipy only. Deterministic (fixed bootstrap seed).
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
SPLIT = pd.Period("2009-01", "M")        # OOS halves: 1991-2008 | 2009-end
NBOOT = 2000
RNG = np.random.default_rng(20260927)
SMALL = ["S10_12", "C20_3", "L10_dev"]
KNN_FEATS = ["L10_dev", "S3_12", "S10_12", "C20_3", "dC20_3"]
K = 10
GAP = 12                                  # de-clustering, months

# ---------------------------------------------------------------- helpers


def block_indices(n: int, block: int, rng) -> np.ndarray:
    """Circular moving-block bootstrap: n indices from ceil(n/block) blocks."""
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, nb)
    idx = (starts[:, None] + np.arange(block)[None, :]) % n
    return idx.ravel()[:n]


def logit_fit(X: np.ndarray, y: np.ndarray, l2: float) -> np.ndarray:
    """Logistic regression with intercept; L2 on slopes only.
    Objective: sum logloss + (l2/2)*||w||^2  (l2 = 1/C, sklearn-equivalent)."""
    Xb = np.column_stack([np.ones(len(X)), X])

    def f(w):
        z = Xb @ w
        ll = np.logaddexp(0, z) - y * z
        pen = 0.5 * l2 * np.sum(w[1:] ** 2)
        g = Xb.T @ (1 / (1 + np.exp(-z)) - y)
        g[1:] += l2 * w[1:]
        return ll.sum() + pen, g

    w0 = np.zeros(Xb.shape[1])
    w0[0] = np.log((y.mean() + 1e-9) / (1 - y.mean() + 1e-9))
    return minimize(f, w0, jac=True, method="L-BFGS-B").x


def logit_pred(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-(w[0] + X @ w[1:])))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = pd.Series(np.concatenate([pos, neg])).rank().values
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                 / (len(pos) * len(neg)))


def declustered_knn(dist: pd.Series, k: int = K, gap: int = GAP) -> list:
    """Nearest months, at most one per `gap`-month neighbourhood."""
    chosen: list = []
    for per in dist.sort_values().index:
        if all(abs((per - c).n) >= gap for c in chosen):
            chosen.append(per)
            if len(chosen) == k:
                break
    return chosen


def summarize(r: pd.Series) -> dict:
    r = r.dropna()
    return {"n": int(len(r)), "p_up": float((r > 0).mean()),
            "median": float(r.median()), "p10": float(r.quantile(.10)),
            "p_dn10": float((r < -0.10).mean()),
            "p_dn20": float((r < -0.20).mean())}


def bh(pvals: dict, q: float = 0.10) -> dict:
    """Benjamini-Hochberg: {key: passes}."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, cut = len(items), 0
    for i, (_, pv) in enumerate(items, 1):
        if pv <= q * i / m:
            cut = i
    return {k: (i < cut) for i, (k, _) in enumerate(items)}


# ---------------------------------------------------------------- methods


def m0_base(df, h):
    return summarize(df[f"r{h}"])


def m1_terciles(df, h, feats):
    rows, pv = {}, {}
    for f in feats:
        d = df[[f, f"r{h}"]].dropna()
        lo, hi = d[f].quantile([1 / 3, 2 / 3])
        t = np.where(d[f] <= lo, 0, np.where(d[f] <= hi, 1, 2))
        up = (d[f"r{h}"] > 0).values
        cells = {name: summarize(d[f"r{h}"][t == i])
                 for i, name in enumerate(("low", "mid", "high"))}
        diff = up[t == 2].mean() - up[t == 0].mean()
        boots = []
        for _ in range(NBOOT):
            ix = block_indices(len(d), h, RNG)
            tb, ub = t[ix], up[ix]
            if (tb == 2).any() and (tb == 0).any():
                boots.append(ub[tb == 2].mean() - ub[tb == 0].mean())
        boots = np.array(boots)
        # CI of the top-minus-bottom difference; p by CI inversion
        p = 2 * min((boots <= 0).mean(), (boots >= 0).mean())
        rows[f] = {"cuts": [float(lo), float(hi)], "cells": cells,
                   "diff_up": float(diff),
                   "ci90": [float(np.quantile(boots, .05)),
                            float(np.quantile(boots, .95))],
                   "p": float(max(p, 1 / NBOOT))}
        pv[f] = rows[f]["p"]
    return rows, pv


def m2_regime(df, h):
    return {g: summarize(d[f"r{h}"]) | {"episodes": episodes(d.index)}
            for g, d in df.groupby("regime")}


def episodes(idx) -> int:
    """Count of runs of consecutive months — the honest n for a cell."""
    idx = sorted(idx)
    return int(sum(1 for i, p in enumerate(idx) if i == 0 or (p - idx[i - 1]).n > 1))


def m3_walkforward(df, h, feats):
    """Each OOS origin t trains only on origins s with s + h <= t."""
    y = df[f"up{h}"]
    oos = [t for t in df.index if t >= OOS_START and not pd.isna(y.get(t))]
    models = ["base"] + [f"uni:{f}" for f in feats] + ["small", "full", "knn"]
    pred = {m: [] for m in models}
    ys = []
    for t in oos:
        tr = df.loc[:t - h].dropna(subset=feats + [f"up{h}"])
        ytr = tr[f"up{h}"].astype(float).values
        x_now = df.loc[t, feats].astype(float)
        mu, sd = tr[feats].mean(), tr[feats].std(ddof=0)
        Z = ((tr[feats] - mu) / sd).values
        z_now = ((x_now - mu) / sd).values
        pred["base"].append(ytr.mean())
        for j, f in enumerate(feats):
            w = logit_fit(Z[:, [j]], ytr, 1e-6)
            pred[f"uni:{f}"].append(float(logit_pred(w, z_now[[j]][None, :])[0]))
        js = [feats.index(f) for f in SMALL]
        w = logit_fit(Z[:, js], ytr, 1e-6)
        pred["small"].append(float(logit_pred(w, z_now[js][None, :])[0]))
        w = logit_fit(Z, ytr, 1.0)
        pred["full"].append(float(logit_pred(w, z_now[None, :])[0]))
        jk = [feats.index(f) for f in KNN_FEATS]
        dist = pd.Series(np.sqrt(((Z[:, jk] - z_now[jk]) ** 2).sum(1)), index=tr.index)
        nb = declustered_knn(dist)
        pred["knn"].append(float(tr.loc[nb, f"up{h}"].astype(float).mean()))
        ys.append(float(y[t]))
    ys = np.array(ys)
    oos_idx = pd.PeriodIndex(oos)
    first = oos_idx < SPLIT
    out = {}
    base_se = (np.array(pred["base"]) - ys) ** 2
    for m in models:
        pm = np.array(pred[m])
        se = (pm - ys) ** 2
        bss = 1 - se.mean() / base_se.mean()
        boots = []
        for _ in range(NBOOT):
            ix = block_indices(len(ys), h, RNG)
            boots.append(1 - se[ix].mean() / base_se[ix].mean())
        halves = [1 - se[mask].mean() / base_se[mask].mean()
                  for mask in (first, ~first)]
        out[m] = {"brier": float(se.mean()), "bss": float(bss),
                  "bss_ci90": [float(np.quantile(boots, .05)),
                               float(np.quantile(boots, .95))],
                  "bss_halves": [float(x) for x in halves],
                  "auc": auc(pm, ys), "n_oos": int(len(ys))}
    return out, {m: np.array(v) for m, v in pred.items()}, ys, oos_idx


def today_models(df, h, feats, now):
    """Fit every M3 model on ALL closed origins and predict today."""
    tr = df.dropna(subset=feats + [f"up{h}"])
    ytr = tr[f"up{h}"].astype(float).values
    mu, sd = tr[feats].mean(), tr[feats].std(ddof=0)
    Z = ((tr[feats] - mu) / sd).values
    z = ((now[feats].astype(float) - mu) / sd).values
    out = {"base": float(ytr.mean())}
    for j, f in enumerate(feats):
        out[f"uni:{f}"] = float(logit_pred(logit_fit(Z[:, [j]], ytr, 1e-6), z[[j]][None, :])[0])
    js = [feats.index(f) for f in SMALL]
    out["small"] = float(logit_pred(logit_fit(Z[:, js], ytr, 1e-6), z[js][None, :])[0])
    out["full"] = float(logit_pred(logit_fit(Z, ytr, 1.0), z[None, :])[0])
    jk = [feats.index(f) for f in KNN_FEATS]
    dist = pd.Series(np.sqrt(((Z[:, jk] - z[jk]) ** 2).sum(1)), index=tr.index)
    out["knn"] = float(tr.loc[declustered_knn(dist), f"up{h}"].astype(float).mean())
    return out


def m4_analogs(df, now, pool_h=18):
    """Today's k nearest de-clustered months among origins whose 18m window
    has closed, standardized on that pool."""
    pool = df.dropna(subset=KNN_FEATS + [f"r{pool_h}"])
    mu, sd = pool[KNN_FEATS].mean(), pool[KNN_FEATS].std(ddof=0)
    Z = (pool[KNN_FEATS] - mu) / sd
    z = (now[KNN_FEATS].astype(float) - mu) / sd
    dist = np.sqrt(((Z - z) ** 2).sum(1))
    nb = declustered_knn(dist)
    rows = []
    for per in nb:
        r = df.loc[per]
        rows.append({"month": str(per), "dist": float(dist[per]),
                     **{f: float(r[f]) for f in KNN_FEATS + ["L10"]},
                     "regime": r["regime"],
                     **{f"r{h}": float(r[f"r{h}"]) for h in H}})
    return rows


# ---------------------------------------------------------------- main


def main() -> dict:
    p = P.build()
    o = P.outcomes(p, H)
    df = p.join(o).loc[P.START:]
    now_per = df.index[-1]
    now = df.loc[now_per]
    feats = P.FEATURES
    res = {"asof": str(now_per), "splice_offset": p.attrs["splice_offset"],
           "today": {f: float(now[f]) for f in feats} | {"regime": now["regime"]},
           "h": {}}
    pvals = {}
    for h in H:
        d = df.dropna(subset=[f"r{h}"])
        R = {"base": m0_base(d, h)}
        R["terciles"], pv = m1_terciles(d, h, feats)
        pvals |= {f"{f}@{h}": v for f, v in pv.items()}
        R["regime"] = m2_regime(d, h)
        R["wf"], preds, ys, oos_idx = m3_walkforward(d, h, feats)
        R["today_models"] = today_models(d, h, feats, now)
        # where today sits in each feature's terciles
        R["today_tercile"] = {f: ("low" if now[f] <= R["terciles"][f]["cuts"][0]
                                  else "mid" if now[f] <= R["terciles"][f]["cuts"][1]
                                  else "high") for f in feats}
        # robustness
        R["R1_subperiod"] = {}
        for lab, sub in (("1971-1999", d.loc[:"1999-12"]), ("2000-end", d.loc["2000-01":])):
            R["R1_subperiod"][lab] = {
                f: float((sub[f"r{h}"][sub[f] > R["terciles"][f]["cuts"][1]] > 0).mean()
                         - (sub[f"r{h}"][sub[f] <= R["terciles"][f]["cuts"][0]] > 0).mean())
                for f in feats}
        R["R2_ex_recession"] = m0_base(d[d["rec"] != 1], h)
        R["R3_ex_splice"], _ = m1_terciles(d[~d["splice20"]], h, ["S20_12", "C20_3", "dC20_3"])
        rel, _ = m1_terciles(d, h, ["S10_12_rel"])
        R["R5_rel_speed"] = rel
        res["h"][h] = R
        np.save(os.path.join(HERE, f"wf_preds_{h}.npy"),
                {"preds": preds, "ys": ys, "oos": [str(x) for x in oos_idx]},
                allow_pickle=True)
    res["fdr"] = bh(pvals, 0.10)
    res["pvals"] = pvals
    res["analogs"] = m4_analogs(df, now)
    # decision rule
    res["gate"] = {}
    for h in H:
        wf = res["h"][h]["wf"]
        passing = []
        for m, s in wf.items():
            if m == "base":
                continue
            ok = s["bss"] > 0 and s["bss_ci90"][0] > 0 and min(s["bss_halves"]) > 0
            if m.startswith("uni:"):
                ok = ok and res["fdr"].get(f"{m[4:]}@{h}", False)
            if ok:
                passing.append(m)
        res["gate"][h] = passing
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({"asof": r["asof"], "today": r["today"], "gate": r["gate"]},
                     indent=1, default=str))
