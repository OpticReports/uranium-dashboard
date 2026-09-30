#!/usr/bin/env python3
"""Runs studies/rate-spike-recession.md once. numpy + pandas + scipy only.

    python3 study.py        -> prints the report, writes results.json
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SPIKE = 0.75            # pp, 60-observation change in DGS30 (RATE_SHOCK's line)
W = 60                  # observations, = routes_rates.RATE_THRESHOLDS window_bdays
H_MONTHS = 12
EP_MERGE_WEEKS = 26
SHIFT_MIN = 104         # weeks, circular-shift null
NBOOT = 2000
SEED = 20260930
WF_START = pd.Timestamp("1990-01-01")


def fred(sid: str) -> pd.Series:
    df = pd.read_csv(os.path.join(DATA, f"{sid}.csv"), na_values=".")
    df.columns = ["date", sid]
    return df.set_index(pd.to_datetime(df["date"]))[sid].dropna().astype(float)


# ------------------------------------------------------------------ panel
def build() -> pd.DataFrame:
    y30 = fred("DGS30")
    d60 = (y30 - y30.shift(W)).rename("d60")
    y10, bill = fred("DGS10"), fred("DTB3")
    daily = pd.concat([y30.rename("y30"), d60, y10.rename("y10"), bill.rename("bill")],
                      axis=1, sort=True)
    daily = daily[daily["y30"].notna()]
    daily[["y10", "bill"]] = daily[["y10", "bill"]].ffill(limit=5)
    daily["curve"] = daily["y10"] - daily["bill"]
    t = fred("T10Y3M").rename("t10y3m")
    daily = daily.join(t, how="left")
    wk = daily.groupby(daily.index.to_period("W-FRI")).tail(1).copy()
    wk = wk[wk["d60"].notna()]
    wk["spike"] = wk["d60"] >= SPIKE - 1e-9
    wk["month"] = wk.index.to_period("M")
    return wk


def recession_months() -> pd.Series:
    r = fred("USREC")
    return pd.Series(r.values, index=r.index.to_period("M"))


def outcomes(wk: pd.DataFrame) -> pd.DataFrame:
    rec = recession_months()
    onsets = [m for m, prev in zip(rec.index[1:], rec.values[:-1])
              if rec[m] == 1 and prev == 0]
    last_known = rec.index[-1]
    out = pd.DataFrame(index=wk.index)
    in_rec, onset12, any12 = [], [], []
    for m in wk["month"]:
        end = m + H_MONTHS
        known = end <= last_known
        in_rec.append(bool(rec.get(m, np.nan) == 1))
        onset12.append(float(any(m < o <= end for o in onsets)) if known else np.nan)
        win = rec.loc[m + 1:end] if known else None
        any12.append(float((rec.get(m, 0) == 1) or (win is not None and (win == 1).any()))
                     if known else np.nan)
    out["in_rec"] = in_rec
    out["onset12"] = onset12
    out["any12"] = any12
    out.attrs["onsets"] = [str(o) for o in onsets]
    return out


# ------------------------------------------------------------------ inference
def stationary_batch(n, mean_block, nboot, rng):
    k = np.arange(n)
    new = rng.random((nboot, n)) < 1.0 / mean_block
    new[:, 0] = True
    begin = np.maximum.accumulate(np.where(new, k, 0), axis=1)
    starts = rng.integers(0, n, (nboot, n))
    return (np.take_along_axis(starts, begin, axis=1) + (k - begin)) % n


def episodes(idx_bool: np.ndarray, merge: int) -> list[tuple[int, int]]:
    """Runs of True, runs < `merge` apart merged; (first, last) positions."""
    pos = np.flatnonzero(idx_bool)
    if not len(pos):
        return []
    out, s, prev = [], pos[0], pos[0]
    for p in pos[1:]:
        if p - prev > merge:
            out.append((s, prev))
            s = p
        prev = p
    out.append((s, prev))
    return out


def logit_fit(X, y, l2=1e-6):
    Xb = np.column_stack([np.ones(len(X)), X])

    def f(b):
        z = Xb @ b
        g = Xb.T @ (1 / (1 + np.exp(-z)) - y)
        g[1:] += l2 * b[1:]
        return (np.logaddexp(0, z) - y * z).sum() + 0.5 * l2 * (b[1:] ** 2).sum(), g
    b0 = np.zeros(Xb.shape[1])
    m = y.mean()
    b0[0] = np.log((m + 1e-9) / (1 - m + 1e-9))
    return minimize(f, b0, jac=True, method="L-BFGS-B").x


def logit_pred(b, X):
    return 1 / (1 + np.exp(-(b[0] + np.asarray(X) @ b[1:])))


# ------------------------------------------------------------------ tests
def t1(d: pd.DataFrame, ycol: str, merge: int, seed: int) -> dict:
    d = d.dropna(subset=[ycol])
    y = d[ycol].values
    s = d["spike"].values.astype(bool)
    eps = episodes(s, merge)
    hits = [float(y[a]) for a, _ in eps]
    base = float(y.mean())
    ep_rate = float(np.mean(hits)) if hits else float("nan")
    wk_rate = float(y[s].mean()) if s.any() else float("nan")
    n = len(y)
    null = np.array([y[np.roll(s, k)].mean() - base
                     for k in range(SHIFT_MIN, n - SHIFT_MIN + 1)])
    obs = wk_rate - base
    p = float((1 + (np.abs(null) >= abs(obs) - 1e-12).sum()) / (1 + len(null)))
    rng = np.random.default_rng(seed)
    bs = []
    for ix in stationary_batch(n, 52, NBOOT, rng):
        sb, yb = s[ix], y[ix]
        if sb.any():
            bs.append(yb[sb].mean() - yb.mean())
    ci = [float(np.quantile(bs, .05)), float(np.quantile(bs, .95))]
    return {"n_weeks": int(n), "spike_weeks": int(s.sum()), "episodes": len(eps),
            "episode_first_weeks": [str(d.index[a].date()) for a, _ in eps],
            "episode_hits": hits, "episode_hit_rate": ep_rate,
            "week_rate_spike": wk_rate, "base_rate": base,
            "ratio_episode": ep_rate / base if base else None,
            "ratio_week": wk_rate / base if base else None,
            "diff_week": obs, "diff_ci90": ci, "p_shift": p}


def t2(d: pd.DataFrame, ycol: str, curve_col: str, seed: int) -> dict:
    d = d.dropna(subset=[ycol, curve_col])
    X = np.column_stack([d[curve_col].values, d["spike"].values.astype(float)])
    y = d[ycol].values
    mu, sd = X[:, 0].mean(), X[:, 0].std()
    Xs = X.copy()
    Xs[:, 0] = (X[:, 0] - mu) / sd
    b = logit_fit(Xs, y)
    rng = np.random.default_rng(seed)
    coefs = []
    for ix in stationary_batch(len(y), 104, 500, rng):
        if y[ix].min() == y[ix].max():
            continue
        coefs.append(logit_fit(Xs[ix], y[ix])[2])
    # walk-forward: at origin t train only on origins whose 12m outcome closed
    idx = d.index
    pc, pcs, ys = [], [], []
    for i, t in enumerate(idx):
        if t < WF_START:
            continue
        cutoff = (t.to_period("M") - H_MONTHS).to_timestamp(how="end")
        tr = idx <= cutoff
        if tr.sum() < 200 or y[tr].min() == y[tr].max():
            continue
        m_, s_ = X[tr, 0].mean(), X[tr, 0].std()
        Ztr = np.column_stack([(X[tr, 0] - m_) / s_, X[tr, 1]])
        zt = np.array([(X[i, 0] - m_) / s_, X[i, 1]])
        bc = logit_fit(Ztr[:, :1], y[tr])
        bcs = logit_fit(Ztr, y[tr])
        pc.append(float(logit_pred(bc, zt[:1][None, :])[0]))
        pcs.append(float(logit_pred(bcs, zt[None, :])[0]))
        ys.append(y[i])
    pc, pcs, ys = map(np.array, (pc, pcs, ys))
    se_c, se_cs = (pc - ys) ** 2, (pcs - ys) ** 2
    bss = 1 - se_cs.mean() / se_c.mean()
    bb = []
    for ix in stationary_batch(len(ys), 104, NBOOT, np.random.default_rng(seed + 1)):
        bb.append(1 - se_cs[ix].mean() / se_c[ix].mean())
    return {"n": int(len(y)), "coef_curve_std": float(b[1]), "coef_spike": float(b[2]),
            "coef_spike_ci90": [float(np.quantile(coefs, .05)), float(np.quantile(coefs, .95))],
            "wf_n": int(len(ys)), "wf_onsets": int(ys.sum()),
            "wf_bss_curve_plus_spike_vs_curve": float(bss),
            "wf_bss_ci90": [float(np.quantile(bb, .05)), float(np.quantile(bb, .95))]}


def main() -> dict:
    wk = build()
    o = outcomes(wk)
    d = wk.join(o)
    res = {"asof": str(d.index[-1].date()), "onsets": o.attrs["onsets"],
           "live": {"d60_pp": float(wk["d60"].iloc[-1]), "y30": float(wk["y30"].iloc[-1])}}
    nr = d[~d["in_rec"]]
    res["T1_onset12"] = t1(nr, "onset12", EP_MERGE_WEEKS, SEED)
    res["T1_onset12_merge5w"] = t1(nr, "onset12", 5, SEED + 1)
    res["T1_any12_replication"] = t1(d, "any12", 5, SEED + 2)
    res["T2_dtb3_curve"] = t2(nr, "onset12", "curve", SEED + 3)
    res["T3_ex_volcker"] = t1(nr[(nr.index < "1979-01-01") | (nr.index >= "1983-01-01")],
                              "onset12", EP_MERGE_WEEKS, SEED + 4)
    res["T3_t10y3m_1982"] = t2(nr[nr.index >= "1982-01-01"], "onset12", "t10y3m", SEED + 5)
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
