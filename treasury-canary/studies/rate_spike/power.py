#!/usr/bin/env python3
"""Power of the "about 2x" gate (spec v1 A3), measured BEFORE the real run.

Keeps the REAL daily grid and the REAL WARN event dates; replaces history's
recessions with synthetic ones: a monthly onset hazard h0 (calibrated to ~6
onsets over the sample) multiplied by M in the 12 months after each real
event; durations and announcement lags resampled from the six real
recessions since 1977. Each draw runs the same gate as study.py (circular-
shift step 5 trading days here for cost; the real run uses step 1).

    python3 power.py [draws]       (default 1000 per multiplier)
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

import study as S

DUR = [6, 16, 8, 8, 18, 2]          # USREC months, 1980..2020
LAG = [4, 5, 8, 7, 11, 3]           # onset month -> NBER announcement month
MULTS = (1.0, 2.0, 3.0)
STEP = 5


def setup():
    d60 = S.d60_series(True)
    ev = S.warn_events(d60)
    f = S.daily_frame(d60)
    months = pd.period_range(f["month"].iloc[0], S.LAST_ORIGIN + 12, freq="M")
    mi = {m: i for i, m in enumerate(months)}
    day_m = np.array([mi[m] for m in f["month"]])
    day_dom = np.array([t.day for t in f.index])
    ev_pos = f.index.get_indexer([e for e in ev if e in f.index])
    ev_pos = ev_pos[ev_pos >= 0]
    boost = np.zeros(len(months), bool)
    for p in ev_pos:
        m0 = day_m[p]
        boost[m0 + 1:m0 + 13] = True
    vol = np.array([not (pd.Timestamp(S.VOLCKER[0]) <= t <= pd.Timestamp(S.VOLCKER[1]))
                    for t in f.index])
    return len(months), day_m, day_dom, ev_pos, boost, vol


def draw(rng, nm, boost, mult, h0):
    rec = np.zeros(nm, bool)
    onset_of = np.full(nm, -1)
    ann = np.full(nm, 10 ** 9)
    m = 0
    while m < nm:
        h = h0 * (mult if boost[m] else 1.0)
        if rng.random() < h:
            d = DUR[rng.integers(6)]
            lag = LAG[rng.integers(6)]
            e = min(nm, m + d)
            rec[m:e] = True
            onset_of[m:e] = m
            ann[m:e] = m + lag
            m = e + 1
        else:
            m += 1
    return rec, onset_of, ann


def gate(rng_seed, nm, day_m, day_dom, ev_pos, boost, vol, mult, h0):
    rng = np.random.default_rng(rng_seed)
    rec, onset_of, ann = draw(rng, nm, boost, mult, h0)
    cs = np.concatenate([[0], np.cumsum(rec)])
    lo, hi = day_m, np.minimum(day_m + 13, nm)
    y = ((cs[hi] - cs[lo]) > 0).astype(float)
    # excluded once the recession is "announced" (month granularity; day 15)
    excl = rec[day_m] & ((day_m > ann[day_m]) | ((day_m == ann[day_m]) & (day_dom >= 15)))
    elig = ~excl

    def one(mask):
        el = elig & mask
        base = y[el].mean() if el.any() else np.nan
        ep = np.array([p for p in ev_pos if el[p]], int)
        if not len(ep) or not base:
            return np.nan, np.nan, set()
        rate = y[ep].mean()
        N = len(y)
        sh = np.arange(S.SHIFT_MIN, N - S.SHIFT_MIN + 1, STEP)
        sp = (ep[None, :] + sh[:, None]) % N
        ok = el[sp]
        rs = (y[sp] * ok).sum(1) / np.maximum(ok.sum(1), 1)
        rs = rs[ok.sum(1) > 0]
        p = (1 + (rs >= rate - 1e-12).sum()) / (1 + len(rs))
        ons = set()
        for q in ep:
            if y[q]:
                m0 = day_m[q]
                w = np.flatnonzero(rec[m0:min(m0 + 13, nm)])
                ons.add(int(onset_of[m0 + w[0]]))
        return rate / base, p, ons
    R, p, ons = one(np.ones(len(y), bool))
    Rv, _, _ = one(vol)
    ok = (R >= 1.8) and (p < 0.10) and (len(ons) >= 3) and (Rv >= 1.5)
    return {"pass": bool(ok), "R": float(R), "p": float(p), "ons": len(ons),
            "Rv": float(Rv), "n_onsets": int(((np.diff(np.concatenate([[0], rec.astype(int)]))) == 1).sum())}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    nm, day_m, day_dom, ev_pos, boost, vol = setup()
    h0 = 6 / (nm * 0.9)
    out = {}
    for mult in MULTS:
        rows = [gate(S.SEED * 10 + int(mult * 1000) + i, nm, day_m, day_dom, ev_pos,
                     boost, vol, mult, h0) for i in range(n)]
        df = pd.DataFrame(rows)
        out[str(mult)] = {"power": float(df["pass"].mean()),
                          "R_median": float(df["R"].median()),
                          "p_lt_0.10": float((df["p"] < 0.10).mean()),
                          "ge3_onsets": float((df["ons"] >= 3).mean()),
                          "Rv_ge_1.5": float((df["Rv"] >= 1.5).mean()),
                          "onsets_median": float(df["n_onsets"].median())}
        print(mult, out[str(mult)], flush=True)
    json.dump({"draws": n, "h0": h0, "step": STEP, "results": out},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json"), "w"),
              indent=1)
