#!/usr/bin/env python3
"""Calibration and power for studies/distress-bottoms.md SPEC v1 s.6 —
synthetic series only (no project failure data), scored with bottoms.score_p.

    python3 bottoms_power.py      # -> bottoms_power.json (fixes theta_A, the floor, reachability)

Generator (log level): AR(1) background + a raised-cosine rise/decline per
recession on the real NBER chronology (level peak at trough + N(mu, sigma)) +
iid irregular at the measured count noise (0.116 before 1914, 0.053 after).
Equity lows are the real Shiller dates (targets, not the signal).
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bottoms as BT  # noqa: E402
import bottoms_engine as B  # noqa: E402
import load as D  # noqa: E402
from engine import M  # noqa: E402

SEED = 20261012
REPS = int(os.environ.get("BOTTOMS_POWER_REPS", 400))
PERMS = int(os.environ.get("BOTTOMS_POWER_PERMS", 999))
T0, T1 = M(1890, 1), M(1965, 6)
NOISE_PRE, NOISE_POST, NOISE_MOORE = 0.116, 0.053, 0.134
CAL_THETAS = (0.10, 0.15, 0.20, 0.25)
CAL_FLOORS = (0.05, 0.075, 0.10)


def background(rng, n, sd=0.012, rho=0.98):
    e = rng.normal(0, sd, n)
    bg = np.zeros(n)
    for i in range(1, n):
        bg[i] = rho * bg[i - 1] + e[i]
    return bg


def bump(n, t0, tpk, R, Rd, a):
    t = np.arange(t0, t0 + n)
    out = np.zeros(n)
    up = (t >= tpk - R) & (t <= tpk)
    out[up] = a * (1 - np.cos(np.pi * (t[up] - (tpk - R)) / R)) / 2
    dn = (t > tpk) & (t <= tpk + Rd)
    out[dn] = a * (1 + np.cos(np.pi * (t[dn] - tpk) / Rd)) / 2
    return out


# ------------------------------------------------------------------ calibration
def no_recession_rate(theta, floor, sigma, bg_sd, reps, rng, months=600):
    rule = B.Rule(theta=theta, floor=floor)
    sigs, obs = 0, 0
    for _ in range(reps):
        x = background(rng, months, bg_sd) + rng.normal(0, sigma, months)
        vals = dict(enumerate(1000 * np.exp(x)))
        g = B.growth(vals, rule)
        sigs += len(B.signals(g, range(months), rule))
        obs += sum(1 for t in range(months) if B.trailing_high(g, t, rule.look) is not None)
    return sigs / (obs / 120)


def calibrate(rng) -> dict:
    table = {}
    choice = None
    for th in CAL_THETAS:
        for fl in CAL_FLOORS:
            r = no_recession_rate(th, fl, NOISE_PRE, 0.012, 200, rng)
            table[f"{th}/{fl}"] = {"pre1914_noise": round(r, 3)}
            if choice is None and r <= 1.0:
                choice = (th, fl)
    for th, fl in [(t, f) for t in CAL_THETAS for f in CAL_FLOORS]:
        row = table[f"{th}/{fl}"]
        row["post1914_noise"] = round(no_recession_rate(th, fl, NOISE_POST, 0.012, 100, rng), 3)
        for bg in (0.008, 0.016):
            row[f"pre1914_bg{bg}"] = round(no_recession_rate(th, fl, NOISE_PRE, bg, 100, rng), 3)
    return {"theta": choice[0], "floor": choice[1], "table": table,
            "rule": "smallest theta in {10,15,20,25%}, then smallest floor in {5,7.5,10pp}, with <= 1 "
                    "roll-over per decade at the pre-1914 count noise (bg sd 0.012)"}


# ------------------------------------------------------------------ synthetic P
def synth_segments(rng, scen, mu, sig, noise_pre=NOISE_PRE, noise_post=NOISE_POST):
    n = T1 - T0 + 1
    t = np.arange(T0, T1 + 1)
    x = background(rng, n) + rng.normal(0, 1, n) * np.where(t < M(1914, 1), noise_pre, noise_post)
    cyc = np.zeros(n)
    for p, tau in BT.CHRON:
        if p > T1:
            break
        R, Rd, a = int(rng.integers(12, 31)), int(rng.integers(12, 31)), rng.uniform(0.3, 0.8)
        if scen == "clock":
            tpk = p + int(rng.integers(-6, 4)) + R
        else:
            tpk = tau + int(round(rng.normal(mu, sig)))
        cyc += bump(n, T0, tpk, R, Rd, a)
    if scen == "shift":
        cyc = np.roll(cyc, int(rng.integers(60, n - 60)))
    level = dict(zip(t.tolist(), (1000 * np.exp(x + cyc)).tolist()))
    a_rng, b_rng, c_rng = (M(1894, 1), M(1938, 8)), (M(1934, 6), M(1939, 12)), (M(1939, 1), M(1965, 6))
    return [{m: v for m, v in level.items() if lo <= m <= hi} for lo, hi in (a_rng, b_rng, c_rng)]


def one_rep(args):
    scen, mu, sig, seed, theta, floor, eqt, noise = args
    rng = np.random.default_rng(seed)
    segs = synth_segments(rng, scen, mu, sig, *noise)
    rule = B.Rule(theta=theta, floor=floor)
    res = BT.score_p(segs, rule, 1, eqt, rng, PERMS)
    holm = BT.E.holm({s: res[s]["p_lagperm"] for s in BT.SHOTS})
    gr = BT.grade(res, holm)
    return {s: {"pass": gr[s]["pass"], "hits": res[s]["hits"], "early": res[s]["early"],
                "median_e": float(np.median([e["e"] for e in res[s]["episodes"] if e["e"] is not None]))
                if any(e["e"] is not None for e in res[s]["episodes"]) else None,
                "p": res[s]["p_lagperm"]} for s in BT.SHOTS}


def cell(scen, mu, sig, theta, floor, eqt, noise, seed0, reps=REPS):
    args = [(scen, mu, sig, seed0 + i, theta, floor, eqt, noise) for i in range(reps)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        out = list(ex.map(one_rep, args, chunksize=8))
    summ = {}
    for s in BT.SHOTS:
        rows = [o[s] for o in out]
        me = [r["median_e"] for r in rows if r["median_e"] is not None]
        summ[s] = {"p_grade": sum(r["pass"] for r in rows) / reps,
                   "p_lagperm_le_0.10": sum(r["p"] is not None and r["p"] <= 0.10 for r in rows) / reps,
                   "mean_hits": float(np.mean([r["hits"] for r in rows])),
                   "mean_early": float(np.mean([r["early"] for r in rows])),
                   "median_of_median_e": float(np.median(me)) if me else None}
    return summ


def mechanical_lag(theta, floor) -> dict:
    """Noise-free: release of the roll-over relative to the level peak, by rise length."""
    rule = B.Rule(theta=theta, floor=floor)
    out = {}
    for R in (12, 18, 24, 30):
        n = 200
        x = bump(n, 0, 100, R, 24, 0.5)
        vals = dict(enumerate(1000 * np.exp(x)))
        g = B.growth(vals, rule)
        sig = B.signals(g, range(n), rule)
        out[str(R)] = (sig[0]["t"] + 1 - 100) if sig else None
    return out


def main():
    rng = np.random.default_rng(SEED)
    cal = calibrate(rng)
    th, fl = cal["theta"], cal["floor"]
    P, _ = D.shiller_monthly()
    eqt = BT.equity_targets(P)
    cells = {}
    seed = SEED * 10
    for mu in (-6, -3, 0, 3):
        for sig in (2, 4, 8):
            seed += 1000
            cells[f"mu{mu}_sigma{sig}"] = cell("inf", mu, sig, th, fl, eqt, (NOISE_PRE, NOISE_POST), seed)
            print("cell", mu, sig, {s: v["p_grade"] for s, v in cells[f"mu{mu}_sigma{sig}"].items()}, flush=True)
    moore = {}
    for mu in (0, -3):
        seed += 1000
        moore[f"mu{mu}_sigma4"] = cell("inf", mu, 4, th, fl, eqt, (NOISE_MOORE, NOISE_MOORE), seed, reps=200)
    size = {}
    for scen in ("clock", "shift"):
        seed += 1000
        size[scen] = cell(scen, 0, 4, th, fl, eqt, (NOISE_PRE, NOISE_POST), seed)
    reach = {s: (cells["mu0_sigma4"][s]["p_grade"] >= 0.2 or cells["mu-3_sigma4"][s]["p_grade"] >= 0.2)
             for s in BT.SHOTS}
    out = {"seed": SEED, "reps": REPS, "perms": PERMS, "calibration": cal,
           "noise": {"pre1914": NOISE_PRE, "post1914": NOISE_POST, "moore_sensitivity": NOISE_MOORE},
           "mechanical_lag_months_after_level_peak": mechanical_lag(th, fl),
           "cells": cells, "moore_noise_cells": moore, "size": size,
           "reachability": {"rule": "reachable if P(grade) >= 0.2 at sigma 4 for mu = 0 or mu = -3",
                            "reachable": reach}}
    with open(os.path.join(HERE, "bottoms_power.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({"calibration": [th, fl], "reachable": reach}, indent=1))


if __name__ == "__main__":
    main()
