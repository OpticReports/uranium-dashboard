#!/usr/bin/env python3
"""Runs SPEC v1 of studies/rate-spike-recession.md once. numpy/pandas/scipy.

    python3 study.py        -> prints the report, writes results.json

The unit is the LIVE alert: WARN events from the 75/60 state machine on the
daily 60-observation change in the 30y yield (routes_rates / events.py).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
W = 60
FIRE, REARM = 75, 60                      # bp — routes_rates.RATE_THRESHOLDS + A6
SEAMS = ("2002-02-19", "2006-02-09")      # Treasury 30y fill seams (A5)
LAST_ORIGIN = pd.Period("2024-08", "M")   # last USREC month − 24 (A2)
SHIFT_MIN = 504                           # trading days (A3)
EP_MERGE_DAYS = 182                       # "same episode" (A6)
VOLCKER = ("1979-01-01", "1982-12-31")
SEED = 20260930
# NBER business-cycle PEAK announcement dates (A2) keyed by the onset month
# (first USREC=1 month = peak + 1).
ANNOUNCED = {"1980-02": "1980-06-03", "1981-08": "1982-01-06",
             "1990-08": "1991-04-25", "2001-04": "2001-11-26",
             "2008-01": "2008-12-01", "2020-03": "2020-06-08"}


def fred(sid: str) -> pd.Series:
    df = pd.read_csv(os.path.join(DATA, f"{sid}.csv"), na_values=[".", ""])
    df.columns = ["date", sid]
    return df.set_index(pd.to_datetime(df["date"]))[sid].dropna().astype(float)


# ------------------------------------------------------------------ series
def d60_series(corrected: bool = True) -> pd.Series:
    """60-observation change in the 30y, whole bp. corrected: chain daily
    changes, replacing the two fill-seam days with DGS20's change (A5)."""
    y30 = fred("DGS30")
    if corrected:
        y20 = fred("DGS20")
        dy = y30.diff()
        for s in SEAMS:
            t = pd.Timestamp(s)
            dy.loc[t] = y20.loc[t] - y20.loc[:t].iloc[-2]
        lvl = y30.iloc[0] + dy.fillna(0).cumsum()
    else:
        lvl = y30
    return ((lvl - lvl.shift(W)) * 100).round().dropna()


def warn_events(d60: pd.Series) -> list[pd.Timestamp]:
    armed, out = True, []
    for d, v in d60.items():
        if not armed and v < REARM:
            armed = True
        if armed and v >= FIRE:
            out.append(d)
            armed = False
    return out


def recessions():
    r = fred("USREC")
    r = pd.Series(r.values, index=r.index.to_period("M"))
    onsets = [m for m, p in zip(r.index[1:], r.values[:-1]) if r[m] == 1 and p == 0
              and m.year >= 1977]
    spans = []
    for o in onsets:
        e = o
        while e + 1 in r.index and r[e + 1] == 1:
            e += 1
        spans.append((o, e, pd.Timestamp(ANNOUNCED[str(o)])))
    return r, spans


def curve_series() -> pd.Series:
    y10, dtb3, cmt = fred("DGS10"), fred("DTB3"), fred("DGS3MO")
    bey = 365 * dtb3 / (360 - 0.91 * dtb3)
    short = pd.concat([bey[bey.index < "1981-09-01"], cmt[cmt.index >= "1981-09-01"]])
    both = pd.concat([y10.rename("y10"), short.rename("s")], axis=1, sort=True).ffill(limit=5)
    return (both["y10"] - both["s"]).dropna()


# ------------------------------------------------------------------ outcomes
def daily_frame(d60: pd.Series) -> pd.DataFrame:
    rec, spans = recessions()
    f = pd.DataFrame({"d60": d60})
    f["month"] = f.index.to_period("M")
    f = f[f["month"] <= LAST_ORIGIN]
    in_rec, excl, rt12, onset12, any12, tag = [], [], [], [], [], []
    for t, m in zip(f.index, f["month"]):
        span = next((s for s in spans if s[0] <= m <= s[1]), None)
        in_rec.append(span is not None)
        excl.append(bool(span is not None and t >= span[2]))
        win = rec.loc[m:m + 12]
        hit = bool((win == 1).any())
        new_onset = any(m < s[0] <= m + 12 for s in spans)
        rt12.append(float(hit))
        onset12.append(float(new_onset))
        any12.append(float(hit))
        tag.append("LEAD" if new_onset else ("LATE" if span is not None else ""))
    f["in_rec"], f["excluded"] = in_rec, excl
    f["rt12"], f["onset12"], f["any12"], f["tag"] = rt12, onset12, any12, tag
    f["onset_hit"] = [
        next((str(s[0]) for s in spans if m < s[0] <= m + 12), None) or
        next((str(s[0]) for s in spans if s[0] <= m <= s[1]), None)
        for m in f["month"]]
    return f


# ------------------------------------------------------------------ T1
def wilson(k: int, n: int, z: float = 1.645) -> list[float]:
    if n == 0:
        return [float("nan")] * 2
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [float(c - h), float(c + h)]


def t1(f: pd.DataFrame, events: list, ycol: str = "rt12",
       mask: pd.Series | None = None, step: int = 1) -> dict:
    g = f if mask is None else f[mask]
    elig = ~g["excluded"].values
    y = g[ycol].values
    base = float(y[elig].mean())
    pos_all = g.index.get_indexer([e for e in events if e in g.index])
    ev_pos = np.array([p for p in pos_all if p >= 0 and elig[p]], dtype=int)
    k, n = int(y[ev_pos].sum()), len(ev_pos)
    rate = k / n if n else float("nan")
    N = len(y)
    shifts = np.arange(SHIFT_MIN, N - SHIFT_MIN + 1, step)
    sp = (ev_pos[None, :] + shifts[:, None]) % N
    ok = elig[sp]
    rates = np.where(ok.sum(1) > 0, (y[sp] * ok).sum(1) / np.maximum(ok.sum(1), 1), np.nan)
    rates = rates[np.isfinite(rates)]
    p_up = float((1 + (rates >= rate - 1e-12).sum()) / (1 + len(rates)))
    p_two = float((1 + (np.abs(rates - base) >= abs(rate - base) - 1e-12).sum())
                  / (1 + len(rates)))
    dates = g.index[ev_pos]
    # episodes: events < 26 weeks apart merge; hit = first event's hit
    eps = [i for i, d in enumerate(dates)
           if i == 0 or (d - dates[i - 1]).days >= EP_MERGE_DAYS]
    ke = int(sum(y[ev_pos[i]] for i in eps))
    onsets_hit = sorted({g["onset_hit"].iloc[p] for p in ev_pos
                         if y[p] == 1 and g["onset_hit"].iloc[p]})
    return {"base": base, "k": k, "n": n, "rate": rate,
            "R": rate / base if base else None,
            "wilson90_events": wilson(k, n), "episodes_n": len(eps), "episodes_k": ke,
            "wilson90_episodes": wilson(ke, len(eps)),
            "p_shift_one_sided": p_up, "p_shift_two_sided": p_two,
            "distinct_onsets_hit": onsets_hit,
            "events": [{"date": str(d.date()), "hit": int(y[p]), "tag": g["tag"].iloc[p],
                        "onset": (g["onset_hit"].iloc[p]
                                  if isinstance(g["onset_hit"].iloc[p], str) else None)}
                       for d, p in zip(dates, ev_pos)],
            "episode_list": [{"first": str(dates[i].date()), "hit": int(y[ev_pos[i]]),
                              "tag": g["tag"].iloc[ev_pos[i]]} for i in eps]}


def gate_2x(main: dict, exv: dict) -> dict:
    c = {"R>=1.8": (main["R"] or 0) >= 1.8, "p<0.10": main["p_shift_one_sided"] < 0.10,
         ">=3 onsets": len(main["distinct_onsets_hit"]) >= 3,
         "ex-Volcker R>=1.5": (exv["R"] or 0) >= 1.5}
    return {"pass": all(c.values()), **c}


# ------------------------------------------------------------------ T2
def probit_fit(X, y):
    Xb = np.column_stack([np.ones(len(X)), X])

    def nll(b):
        z = Xb @ b
        p = np.clip(norm.cdf(z), 1e-9, 1 - 1e-9)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()
    return minimize(nll, np.zeros(Xb.shape[1]), method="BFGS").x


def t2(f: pd.DataFrame, events: list) -> dict:
    cv = curve_series()
    g = f[~f["excluded"]].join(cv.rename("curve"), how="left")
    g["curve"] = g["curve"].ffill(limit=5)
    g = g.dropna(subset=["curve"])
    spike = (g["d60"] >= FIRE).values.astype(float)
    y = g["rt12"].values
    X = np.column_stack([g["curve"].values, spike])
    b = probit_fit(X, y)
    N = len(y)
    null = []
    for k in range(SHIFT_MIN, N - SHIFT_MIN + 1, 21):       # monthly step: cost
        null.append(probit_fit(np.column_stack([X[:, 0], np.roll(spike, k)]), y)[2])
    null = np.array(null)
    p = float((1 + (np.abs(null) >= abs(b[2]) - 1e-12).sum()) / (1 + len(null)))
    bc = probit_fit(X[:, :1], y)
    g["p_curve"] = norm.cdf(bc[0] + bc[1] * g["curve"].values)
    base = float(y.mean())
    ev = [e for e in events if e in g.index]
    strata = {}
    for lab, sel in (("curve_prob_ge_30", lambda q: q >= 0.30),
                     ("curve_prob_lt_30", lambda q: q < 0.30)):
        es = [e for e in ev if sel(g.at[e, "p_curve"])]
        k = int(sum(g.at[e, "rt12"] for e in es))
        strata[lab] = {"n": len(es), "k": k, "rate": k / len(es) if es else None,
                       "ratio": (k / len(es)) / base if es else None,
                       "events": [str(e.date()) for e in es]}
    words = ("adds" if (p < 0.10 and (strata["curve_prob_lt_30"]["ratio"] or 0) >= 1.5)
             else "overlaps" if (strata["curve_prob_lt_30"]["n"] >= 5
                                 and strata["curve_prob_lt_30"]["k"] == 0)
             else "inseparable")
    return {"n": N, "coef_curve": float(b[1]), "coef_spike": float(b[2]),
            "p_shift_spike": p, "base": base, "strata": strata, "words": words,
            "curve_model": {"b0": float(bc[0]), "b1": float(bc[1])}}


# ------------------------------------------------------------------ main
def main() -> dict:
    d60 = d60_series(True)
    ev = warn_events(d60)
    f = daily_frame(d60)
    res = {"asof_data": str(d60.index[-1].date()), "live_d60": float(d60.iloc[-1]),
           "events_all": [str(e.date()) for e in ev], "n_events_all": len(ev)}
    main_ = t1(f, ev)
    vol = (f.index < VOLCKER[0]) | (f.index > VOLCKER[1])
    exv = t1(f, ev, mask=pd.Series(vol, index=f.index))
    res["T1"] = main_
    res["T1_ex_volcker"] = exv
    res["gate_2x"] = gate_2x(main_, exv)
    ex20 = ~((f["month"] >= pd.Period("2019-03", "M")) & (f["month"] <= pd.Period("2020-04", "M")))
    res["T1_ex_2020"] = t1(f, ev, mask=ex20)
    res["T1_onset12_strict"] = t1(f.assign(excluded=f["in_rec"]), ev, ycol="onset12")
    res["T1_any12"] = t1(f.assign(excluded=False), ev, ycol="any12")
    raw = d60_series(False)
    fr = daily_frame(raw)
    res["T1_raw_d60"] = t1(fr, warn_events(raw))
    res["T2"] = t2(f, ev)
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1,
              default=str, allow_nan=False)
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: v for k, v in r.items() if k not in ("events_all",)},
                     indent=1, default=str)[:6000])
