"""Monte Carlo of the book by sleeve weight under the seven scenarios of PREREG.md, and the three
side methods (deflated Sharpe, beta split, live record). Writes out/forward.json."""
import datetime as dt
import json
import math
import os
import sys
from statistics import NormalDist

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fdata as fd  # noqa: E402

N, T, BLOCK, SEED, COST = 10000, 2520, 21, 20261121, 5.856e-4
HOR = {"1y": 252, "5y": 1260, "10y": 2520}
WEIGHTS = (0.0, 0.10, 0.20, 0.318, 0.40, 0.50)
QS = (5, 25, 50, 75, 95)
SPX_LOW = 0.02                     # the low-return decade: S&P 500 at +2% a year nominal


def beta_of(R, tb, sp):
    x = sp - tb
    return np.array([float(np.cov(R[:, i] - tb, x)[0, 1] / x.var(ddof=1)) for i in range(3)])


def scenarios():
    dsA, RA, tA, sA = fd.source(fd.SPAN["A"])
    dsB, RB, tB, sB = fd.source(fd.SPAN["B"])
    dsC, RC, tC, sC = fd.source(fd.SPAN["C"])
    dsF, RF, tF, sF = fd.source(fd.SPAN["B"], late=True)
    ex = (RB - tB[:, None]).mean(0)
    beta = beta_of(RB, tB, sB)
    # growth to growth: the S&P's own daily log growth in B less the daily log growth of +2% a year, so the
    # shifted S&P compounds at about 2% (an arithmetic mean less a compound rate would over-shift by var/2)
    spx_mean_daily = float(np.log1p(sB).mean())
    low_daily = math.log(1 + SPX_LOW) / 252
    G = RB - beta[None, :] * (spx_mean_daily - low_daily)
    S = {"A": (RA, tA, dsA), "B": (RB, tB, dsB), "C": (RC, tC, dsC), "D": (RB - 0.5 * ex[None, :], tB, dsB), "E": (RB - 0.73 * ex[None, :], tB, dsB), "F": (RF, tF, dsF), "G": (G, tB, dsB)}
    side = {"beta_B": beta.tolist(), "beta_C": beta_of(RC, tC, sC).tolist(), "spx_growth_per_yr_B": float(spx_mean_daily * 252), "spx_growth_per_yr_C": float(np.log1p(sC).mean() * 252),
            "spx_growth_after_shift": float(np.log1p(sB - (spx_mean_daily - low_daily)).mean() * 252),
            "engine_mean_over_tbills_per_yr_B": (ex * 252).tolist(), "engine_mean_over_tbills_per_yr_C": ((RC - tC[:, None]).mean(0) * 252).tolist(),
            "tbill_per_yr_B": float(tB.mean() * 252), "g_shift_per_yr": (beta * (spx_mean_daily - low_daily) * 252).tolist()}
    return S, side


def draw(n, rng):
    """stationary bootstrap indices, N paths x T sessions"""
    idx = np.empty((N, T), np.int32)
    start = rng.integers(0, n, (N, T), dtype=np.int32)
    jump = rng.random((N, T)) < 1.0 / BLOCK
    idx[:, 0] = start[:, 0]
    for t in range(1, T):
        idx[:, t] = np.where(jump[:, t], start[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def run(R, tb, idx, wt, daily=False):
    """book paths for third-leg weight wt. Drift with a reset to target when any engine exceeds the largest
    target + 10 points (POLICY operation 5); daily=True resets every session (the earlier studies' convention)."""
    tgt = np.array([(1 - wt) / 2, (1 - wt) / 2, wt])
    cap = tgt.max() + 0.10
    V = np.tile(tgt, (N, 1)).astype(np.float64)
    peak = np.ones(N)
    mdd = np.zeros(N)
    resets = np.zeros(N)
    out, fan = {}, []
    for t in range(T):
        V *= 1 + R[idx[:, t]]
        tot = V.sum(1)
        if daily:
            V = tot[:, None] * tgt[None, :]
        else:
            hit = (V / tot[:, None]).max(1) > cap
            if hit.any():
                turn = np.abs(V[hit] / tot[hit, None] - tgt[None, :]).sum(1)
                tot[hit] *= 1 - COST * turn
                V[hit] = tot[hit, None] * tgt[None, :]
                resets[hit] += 1
        peak = np.maximum(peak, tot)
        mdd = np.maximum(mdd, 1 - tot / peak)
        if (t + 1) % 21 == 0:
            fan.append([t + 1] + [float(q) for q in np.percentile(tot, QS)])
        for h, n in HOR.items():
            if t + 1 == n:
                yrs = n / 252
                out[h] = {"multiple": {str(q): float(v) for q, v in zip(QS, np.percentile(tot, QS))},
                          "per_yr": {str(q): float(v ** (1 / yrs) - 1) for q, v in zip(QS, np.percentile(tot, QS))},
                          "p_below_start": float((tot < 1).mean()), "maxdd_median": float(np.median(mdd)), "maxdd_p95": float(np.percentile(mdd, 95)),
                          "p_fall_deeper": {str(x): float((mdd > x / 100).mean()) for x in (20, 30, 40, 50)}, "resets_per_yr": float(resets.mean() / yrs)}
    return out, fan


def deflated(sr_annual, n_obs, trials):
    """Bailey and Lopez de Prado: the Sharpe the best of `trials` unskilled tries is expected to show on n_obs
    daily observations (annualised), and the probability the observed one beats it (normal returns assumed)."""
    nd = NormalDist()
    g = 0.5772156649
    emax = ((1 - g) * nd.inv_cdf(1 - 1 / trials) + g * nd.inv_cdf(1 - 1 / (trials * math.e))) * math.sqrt(252 / n_obs)
    sr_d, e_d = sr_annual / math.sqrt(252), emax / math.sqrt(252)
    z = (sr_d - e_d) * math.sqrt(n_obs - 1) / math.sqrt(1 + 0.5 * sr_d ** 2)
    return {"expected_best_of_unskilled": emax, "prob_observed_beats_it": nd.cdf(z)}


def live_record():
    f = os.path.join(HERE, "..", "zvol_2026-11", "data", "live.json")
    o = json.load(open(f))
    E = fd.md.engines()
    out = {}
    for e in fd.ENG:
        ds = [dt.datetime.utcfromtimestamp(x / 1000).strftime("%Y-%m-%d") for x in o[e]["epoch_ms"]]
        a = o[e]["deposit_adjusted_series"]
        sim = [d for d in sorted(E[e]) if ds[0] < d <= ds[-1]]
        v = np.array(a)
        out[e] = {"from": ds[0], "to": ds[-1], "sessions": len(ds) - 1, "live_return": a[-1] / a[0] - 1, "simulated_return_same_dates": float(np.prod(1 + np.array([E[e][d] for d in sim])) - 1),
                  "live_deepest_fall": float(np.max(1 - v / np.maximum.accumulate(v)))}
    return out


def main():
    rng = np.random.default_rng(SEED)
    S, side = scenarios()
    out = {"meta": {"paths": N, "sessions": T, "block": BLOCK, "seed": SEED, "weights": WEIGHTS, "spans": {k: [v[2][0], v[2][-1], len(v[2])] for k, v in S.items()}}, "side": side, "mc": {}, "fan": {}, "hist": {}}
    for sid, (R, tb, ds) in S.items():
        idx = draw(len(ds), rng)
        out["mc"][sid], out["hist"][sid] = {}, {}
        for wt in WEIGHTS:
            res, fan = run(R, tb, idx, wt)
            out["mc"][sid][f"{wt:.3f}"] = res
            if abs(wt - 0.318) < 1e-9 or wt == 0.0:
                out["fan"][f"{sid}.{wt:.3f}"] = fan
            x = R @ np.array([(1 - wt) / 2, (1 - wt) / 2, wt])                 # the source's own daily-reset book: what the draws are made from
            lvl = np.cumprod(1 + x)
            out["hist"][sid][f"{wt:.3f}"] = {"cagr": float(lvl[-1] ** (252 / len(x)) - 1), "maxdd": float(np.max(1 - lvl / np.maximum.accumulate(lvl))), "sharpe": float(x.mean() / x.std(ddof=1) * math.sqrt(252)),
                                             "vol": float(x.std(ddof=1) * math.sqrt(252)), "n": len(x)}
        out["mc"][sid]["0.318.daily_reset"], _ = run(R, tb, idx, 0.318, daily=True)
        v = out["mc"][sid]["0.318"]
        print(sid, len(ds), "31.8%:", {h: (round(v[h]["per_yr"]["5"], 2), round(v[h]["per_yr"]["50"], 2), round(v[h]["per_yr"]["95"], 2), "P<1", round(v[h]["p_below_start"], 3), "dd", round(v[h]["maxdd_median"], 2), round(v[h]["maxdd_p95"], 2)) for h in HOR},
              "| daily reset 10y dd", round(out["mc"][sid]["0.318.daily_reset"]["10y"]["maxdd_median"], 2), "resets/yr", round(v["10y"]["resets_per_yr"], 2), flush=True)
    out["deflated"] = {sid: {wt: {str(n): deflated(h["sharpe"], h["n"], n) for n in (10, 100, 1000)} | {"sharpe": h["sharpe"]} for wt, h in out["hist"][sid].items() if wt in ("0.000", "0.318", "0.500")} for sid in ("A", "B", "C")}
    out["live"] = live_record()
    json.dump(out, open(os.path.join(HERE, "out", "forward.json"), "w"), indent=1)
    print("side", {k: ([round(z, 3) for z in v] if isinstance(v, list) else round(v, 4)) for k, v in side.items()})
    print("deflated B 31.8%", out["deflated"]["B"]["0.318"])
    print("live", out["live"])
    for sid in out["mc"]:
        print(sid, "10y median per yr / P(fall>30%) by weight:", {wt: (round(v["10y"]["per_yr"]["50"], 2), round(v["10y"]["p_fall_deeper"]["30"], 2)) for wt, v in out["mc"][sid].items() if "daily" not in wt})


if __name__ == "__main__":
    main()
