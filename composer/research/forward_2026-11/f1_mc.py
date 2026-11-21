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
    exC = (RC - tC[:, None]).mean(0)
    # Z, H, I were added after the independent review (DEVIATIONS 4); they come last so A-G keep their draws
    S = {"A": (RA, tA, dsA), "B": (RB, tB, dsB), "C": (RC, tC, dsC), "D": (RB - 0.5 * ex[None, :], tB, dsB), "E": (RB - 0.73 * ex[None, :], tB, dsB), "F": (RF, tF, dsF), "G": (G, tB, dsB),
         "Z": (RB - ex[None, :], tB, dsB), "H": (RC - 0.5 * exC[None, :], tC, dsC), "I": (RC - 0.73 * exC[None, :], tC, dsC)}
    pre = np.array([d < "2015-06-01" for d in dsC])
    dec = np.array(["2000-01-01" <= d <= "2009-12-31" for d in dsC])
    w0 = np.array([0.341, 0.341, 0.318])
    cg = lambda x: float(np.prod(1 + x) ** (252 / len(x)) - 1)                  # noqa: E731
    xb = RB - tB[:, None]
    top = {}
    for i in range(3):
        o = np.sort(xb[:, i])[::-1]
        top[fd.ENG[i]] = float(o[:50].sum() / o.sum())
    bookB = RB @ w0
    keep50 = np.ones(len(bookB), bool)
    keep50[np.argsort(bookB)[::-1][:50]] = False
    y2020 = np.array([d[:4] == "2020" for d in dsB])
    side = {"beta_B": beta.tolist(), "beta_C": beta_of(RC, tC, sC).tolist(), "spx_growth_per_yr_B": float(spx_mean_daily * 252), "spx_growth_per_yr_C": float(np.log1p(sC).mean() * 252),
            "spx_growth_after_shift": float(np.log1p(sB - (spx_mean_daily - low_daily)).mean() * 252),
            "engine_mean_over_tbills_per_yr_B": (ex * 252).tolist(), "engine_mean_over_tbills_per_yr_C": ((RC - tC[:, None]).mean(0) * 252).tolist(),
            "edge_kept_one_close_late": ((RF - tF[:, None]).mean(0) / ex).tolist(), "edge_kept_before_2015": ((RC[pre] - tC[pre, None]).mean(0) / ex).tolist(),
            "book_cagr_2000_2009": cg(RC[dec] @ w0), "spx_cagr_2000_2009": cg(sC[dec]), "book_cagr_before_2015": cg(RC[pre] @ w0), "book_cagr_B": cg(bookB), "spx_cagr_B": cg(sB),
            "share_of_edge_from_best_50_sessions": top, "book_cagr_B_without_its_best_50_sessions": cg(bookB[keep50]), "book_cagr_B_without_2020": cg(bookB[~y2020]), "book_return_2020": float(np.prod(1 + bookB[y2020]) - 1),
            "spx_mean_over_tbills_per_yr_C": float((sC - tC).mean() * 252),
            "tbill_per_yr_B": float(tB.mean() * 252), "spx_mean_over_tbills_per_yr_B": float((sB - tB).mean() * 252), "g_shift_per_yr": (beta * (spx_mean_daily - low_daily) * 252).tolist()}
    return S, side


def draw(n, rng, block=BLOCK):
    """stationary bootstrap indices, N paths x T sessions"""
    idx = np.empty((N, T), np.int32)
    start = rng.integers(0, n, (N, T), dtype=np.int32)
    jump = rng.random((N, T)) < 1.0 / block
    idx[:, 0] = start[:, 0]
    for t in range(1, T):
        idx[:, t] = np.where(jump[:, t], start[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def run(R, tb, idx, wt, daily=False, rule="own"):
    """book paths for third-leg weight wt. Weights drift; all three are reset to target when an engine passes
    its cap. rule="own": each engine's cap is its OWN target + 10 points (at today's 31.8% book that is
    44.1 / 44.1 / 41.8, in effect POLICY's 44%); rule="largest": one cap for all, the largest target + 10
    points (PREREG's literal reading, which at a 40-50% sleeve lets HG or KMLM run from 25-30% to 50-60%).
    daily=True resets every session (the earlier studies' convention)."""
    tgt = np.array([(1 - wt) / 2, (1 - wt) / 2, wt])
    cap = (tgt + 0.10) if rule == "own" else np.full(3, tgt.max() + 0.10)
    cap = np.where(tgt > 0, cap, 2.0)
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
            hit = ((V / tot[:, None]) > cap[None, :]).any(1)
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
    """Each symphony live against the simulation on the same closes. Composer's deposit-adjusted series starts
    at the deposit, so the first day's move is taken out (the simulation starts at the first close). Also from
    the first close at which the symphony held at least $10,000, and the three as held in dollars."""
    f = os.path.join(HERE, "..", "zvol_2026-11", "data", "live.json")
    o = json.load(open(f))
    E = fd.md.engines()
    out, A, V = {}, {}, {}
    for e in fd.ENG:
        ds = [dt.datetime.utcfromtimestamp(x / 1000).strftime("%Y-%m-%d") for x in o[e]["epoch_ms"]]
        a = list(o[e]["deposit_adjusted_series"])
        first_day = o[e]["series"][0] / a[0] - 1                                  # the deposit day's own move
        adj = [a[0] * (1 + first_day)] + a[1:]                                    # level at each close
        A[e], V[e] = dict(zip(ds, adj)), dict(zip(ds, o[e]["series"]))
        simr = lambda lo, hi: float(np.prod(1 + np.array([E[e][d] for d in sorted(E[e]) if lo < d <= hi])) - 1)   # noqa: E731
        k = next(i for i, v in enumerate(o[e]["series"]) if v >= 10000)
        v = np.array(adj)
        out[e] = {"from": ds[0], "to": ds[-1], "sessions": len(ds) - 1, "live_return": adj[-1] / adj[0] - 1, "simulated_return_same_dates": simr(ds[0], ds[-1]),
                  "funded_from": ds[k], "funded_sessions": len(ds) - 1 - k, "live_return_funded": adj[-1] / adj[k] - 1, "simulated_return_funded": simr(ds[k], ds[-1]),
                  "live_deepest_fall": float(np.max(1 - v / np.maximum.accumulate(v)))}
    ds = sorted(set(A["HG"]) & set(A["KMLM"]) & set(A["SLEEVE"]))
    lv = sm = 1.0
    for a, b in zip(ds, ds[1:]):
        tot = sum(V[e][a] for e in fd.ENG)
        lv *= 1 + sum(V[e][a] / tot * (A[e][b] / A[e][a] - 1) for e in fd.ENG)
        sm *= 1 + sum(V[e][a] / tot * E[e][b] for e in fd.ENG if b in E[e])
    out["three_as_held"] = {"from": ds[0], "to": ds[-1], "sessions": len(ds) - 1, "live_return": lv - 1, "simulated_return_same_weights": sm - 1}
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
                                             "sharpe_over_tbills": float((x - tb).mean() / (x - tb).std(ddof=1) * math.sqrt(252)),
                                             "vol": float(x.std(ddof=1) * math.sqrt(252)), "n": len(x)}
        out["mc"][sid]["0.318.daily_reset"], _ = run(R, tb, idx, 0.318, daily=True)
        if sid in ("B", "D"):
            for wt in WEIGHTS:
                out["mc"][sid][f"{wt:.3f}.largest_cap"], _ = run(R, tb, idx, wt, rule="largest")
        v = out["mc"][sid]["0.318"]
        print(sid, len(ds), "31.8%:", {h: (round(v[h]["per_yr"]["5"], 2), round(v[h]["per_yr"]["50"], 2), round(v[h]["per_yr"]["95"], 2), "P<1", round(v[h]["p_below_start"], 3), "dd", round(v[h]["maxdd_median"], 2), round(v[h]["maxdd_p95"], 2)) for h in HOR},
              "| daily reset 10y dd", round(out["mc"][sid]["0.318.daily_reset"]["10y"]["maxdd_median"], 2), "resets/yr", round(v["10y"]["resets_per_yr"], 2), flush=True)
    # block-length sensitivity (review: one-year numbers and the loss odds move with it); its own generator
    rs = np.random.default_rng(SEED + 1)
    out["block_sensitivity"] = {}
    for sid in ("D", "E"):
        R, tb, ds = S[sid]
        out["block_sensitivity"][sid] = {str(b): run(R, tb, draw(len(ds), rs, b), 0.318)[0] for b in (5, 21, 63)}
    out["deflated"] = {sid: {wt: {str(n): deflated(h["sharpe"], h["n"], n) for n in (10, 100, 1000)} | {"sharpe": h["sharpe"]} for wt, h in out["hist"][sid].items() if wt in ("0.000", "0.318", "0.500")} for sid in ("A", "B", "C")}
    out["live"] = live_record()
    json.dump(out, open(os.path.join(HERE, "out", "forward.json"), "w"), indent=1)
    print("side", {k: ([round(z, 3) for z in v] if isinstance(v, list) else round(v, 4)) for k, v in side.items()})
    print("deflated B 31.8%", out["deflated"]["B"]["0.318"])
    print("live", out["live"])
    for sid in out["mc"]:
        print(sid, "10y median per yr / P(fall>30%) by weight:", {wt: (round(v["10y"]["per_yr"]["50"], 2), round(v["10y"]["p_fall_deeper"]["30"], 2)) for wt, v in out["mc"][sid].items() if "daily" not in wt and "largest" not in wt})
    print("block sensitivity", {sid: {b: (round(v["1y"]["per_yr"]["50"], 3), round(v["1y"]["p_below_start"], 3), round(v["10y"]["p_below_start"], 3), round(v["10y"]["maxdd_median"], 3)) for b, v in x.items()} for sid, x in out["block_sensitivity"].items()})


if __name__ == "__main__":
    main()
