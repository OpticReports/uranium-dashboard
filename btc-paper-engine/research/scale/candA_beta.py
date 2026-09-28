"""CANDIDATE A - mechanism decomposition + the BETA variant.

WHY the mean notional gain is small, analytically: vol-targeting sets
nf_i = r / s_i with r = mean(s). Its mean notional is therefore
    mean(nf) = mean(s) * mean(1/s) = 1 + CV^2(s) + O(skew)
i.e. the arithmetic/harmonic-mean gap. NOT a multiple -- a CV^2 bonus.
Measured here directly.

THE VARIANT. T1 measured strong vol mean-reversion (fwd/trailing 1.18x in the
calmest ATR quintile, 0.81x in the wildest). Pure trailing-ATR targeting
therefore upsizes into vol that then EXPANDS. Partial targeting:
    s_used(beta) = s_i^beta * s_bar^(1-beta),   nf = min(risk / s_used, cap)
beta=0 reduces EXACTLY to the shipped fixed sizing; beta=1 is pure
vol-targeting. If the mean-reversion matters, the best beta is < 1.
Swept EXACTLY without re-running the engine: ret_eq = nf * (gross - fee) and
nf is a deterministic function of s_i (validated against the engine below).

Output: candA_beta.json
"""
import csv
import json
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, BACKEND)

from app.engine.core import Bar, BookCfg                    # noqa: E402
from app.engine.replay import run_replay                    # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SIZING_STOP = {"pullback": 2.5, "trend": 5.0}
W = {"pullback": 0.75, "trend": 0.25}
BLEND_LEV, EQUITY = 1.5, 100_055.0
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY)
HOLDOUT_START = 1719792000
DD_LIMIT, P_LIMIT, DRAWS, MEAN_BLOCK, SEED = 0.30, 0.10, 2000, 10, 20260804


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def run_leg(bars, leg, sizing, risk=0.0, cap=1.0):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZING_STOP[leg])
    cfg = (BookCfg(name="P", sizing=sizing, strategy="pullback", leverage=1.0,
                   risk=risk, cap=cap, dd_halt=0.30) if leg == "pullback" else
           BookCfg(name="T", sizing=sizing, strategy="donchian", trail_atr=5.0,
                   leverage=1.0, risk=risk, cap=cap, dd_halt=0.50))
    bk = run_replay(bars, [cfg], RESEARCH_SIGNAL, tc, cash_apy=0.0).books[cfg.name]
    rows = []
    for t in bk.trades:
        sgn = 1.0 if t.side == "L" else -1.0
        rows.append(dict(exit_ts=t.exit_ts, s=tc.stop_atr * t.atr_at_entry / t.entry_price,
                         gross=sgn * (t.exit_price / t.entry_price - 1),
                         fee=t.fees_usd / t.notional,
                         nf_engine=t.notional / t.equity_before,
                         ret_eq_engine=t.pnl_usd / t.equity_before))
    return bk, rows


def boot_idx(n, draws, rng, mean_block=MEAN_BLOCK):
    p = 1.0 / mean_block
    idx = np.empty((draws, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, draws)
    restart = rng.random((draws, n)) < p
    jump = rng.integers(0, n, (draws, n))
    for i in range(1, n):
        idx[:, i] = np.where(restart[:, i], jump[:, i], (idx[:, i - 1] + 1) % n)
    return idx


def dd_prob_vec(steps, k, idx, dd_limit=DD_LIMIT):
    x = 1.0 + k * steps[idx]
    ruin = (x <= 0).any(axis=1)
    nav = np.cumprod(np.where(x <= 0, 1e-12, x), axis=1)
    mdd = (nav / np.maximum.accumulate(nav, axis=1) - 1.0).min(axis=1)
    return float(((mdd < -dd_limit) | ruin).mean())


def k_max(steps, idx, hi=6.0):
    lo = 0.0
    if dd_prob_vec(steps, hi, idx) <= P_LIMIT:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if dd_prob_vec(steps, mid, idx) <= P_LIMIT:
            lo = mid
        else:
            hi = mid
    return lo


def build(rows_by_leg, beta, cap, risk_by_leg, sbar_by_leg, t0=None):
    """(steps_at_k1, notional_frac_at_k1, n) for a (beta, cap) sizer."""
    evs = []
    for leg, rows in rows_by_leg.items():
        r0, sb = risk_by_leg[leg], sbar_by_leg[leg]
        for r in rows:
            s_used = (r["s"] ** beta) * (sb ** (1.0 - beta))
            nf = min(r0 / s_used, cap)
            evs.append((r["exit_ts"], BLEND_LEV * W[leg] * nf * (r["gross"] - r["fee"]),
                        BLEND_LEV * W[leg] * nf))
    evs.sort(key=lambda x: x[0])
    evs = [e for e in evs if t0 is None or e[0] >= t0]
    return (np.array([e[1] for e in evs]), np.array([e[2] for e in evs]))


def main():
    bars = load_bars()
    rows_by_leg, risk_by_leg, sbar_by_leg, eng = {}, {}, {}, {}
    for leg in ("pullback", "trend"):
        bk, rows = run_leg(bars, leg, "fixed", cap=1.0)
        rows_by_leg[leg] = rows
        s = np.array([r["s"] for r in rows])
        # r0 chosen so that at beta=1 mean intended risk fraction == FIXED's.
        # Under FIXED nf=1 so risk_i = s_i; mean = mean(s).
        risk_by_leg[leg] = float(s.mean())
        sbar_by_leg[leg] = float(s.mean())
        eng[leg] = dict(equity=float(bk.equity), start=bk.cfg.start_equity)
    out = {"meta": dict(equity=EQUITY, k_live=K_LIVE, blend_lev=BLEND_LEV,
                        dd_limit=DD_LIMIT, p_limit=P_LIMIT, draws=DRAWS,
                        seed=SEED, fee_rt_bps=2 * RESEARCH_TRADE.taker_fee_bps,
                        sizing_stop=SIZING_STOP, holdout_start=HOLDOUT_START),
           "risk_by_leg": risk_by_leg, "sbar_by_leg": sbar_by_leg}

    # ---- mechanism: mean(s)*mean(1/s) = 1 + CV^2 -----------------------
    mech = {}
    for leg, rows in rows_by_leg.items():
        s = np.array([r["s"] for r in rows])
        cv = s.std(ddof=0) / s.mean()
        mech[leg] = dict(
            n=len(s), mean_s=float(s.mean()), harmonic_mean_s=float(1 / (1 / s).mean()),
            arith_over_harmonic=float(s.mean() * (1 / s).mean()),
            cv_s=float(cv), one_plus_cv2=float(1 + cv ** 2),
            predicted_vs_measured_gap_pct=float(
                100 * (s.mean() * (1 / s).mean() - (1 + cv ** 2))),
            s_p10=float(np.percentile(s, 10)), s_p90=float(np.percentile(s, 90)),
            max_notional_mult_uncapped=float(s.mean() / s.min()))
    out["mechanism_mean_notional_bound"] = mech
    for leg, m in mech.items():
        print(f"MECH {leg:9s}: mean(s)*mean(1/s)={m['arith_over_harmonic']:.4f} "
              f"1+CV^2={m['one_plus_cv2']:.4f} (CV={m['cv_s']:.3f}) "
              f"max notional mult={m['max_notional_mult_uncapped']:.2f}x")

    # ---- V1: analytic path reproduces the engine EXACTLY ---------------
    v1 = {}
    for leg in ("pullback", "trend"):
        rows = rows_by_leg[leg]
        for tag, beta, cap in (("FIXED", 0.0, 1.0), ("VT_cap2", 1.0, 2.0),
                               ("VT_uncapped", 1.0, 99.0)):
            if tag == "FIXED":
                bk2, _ = run_leg(bars, leg, "fixed", cap=1.0)
            else:
                bk2, _ = run_leg(bars, leg, "vol_target", risk_by_leg[leg], cap)
            eq = 1.0
            for r in rows:
                s_used = (r["s"] ** beta) * (sbar_by_leg[leg] ** (1 - beta))
                nf = min(risk_by_leg[leg] / s_used, cap)
                eq *= 1 + nf * (r["gross"] - r["fee"])
            v1[f"{leg}_{tag}"] = dict(
                analytic=float(bk2.cfg.start_equity * eq),
                engine=float(bk2.equity),
                rel_err=float(abs(bk2.cfg.start_equity * eq - bk2.equity) / bk2.equity))
    out["V1_analytic_vs_engine"] = v1
    print("V1 max rel err:", max(v["rel_err"] for v in v1.values()))

    # ---- BETA x CAP sweep ----------------------------------------------
    BETAS = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]
    CAPS = [1.0, 1.5, 2.0, 3.0, 99.0]
    sweep = {}
    for wname, t0 in (("full", None), ("holdout", HOLDOUT_START)):
        ref_steps, _ = build(rows_by_leg, 0.0, 1.0, risk_by_leg, sbar_by_leg, t0)
        idx = boot_idx(len(ref_steps), DRAWS, np.random.default_rng(SEED + 1))
        sweep[wname] = {}
        for cap in CAPS:
            for beta in BETAS:
                st, nt = build(rows_by_leg, beta, cap, risk_by_leg, sbar_by_leg, t0)
                km = k_max(st, idx)
                nav = np.cumprod(1 + km * st)
                navl = np.cumprod(1 + K_LIVE * st)
                yrs = None
                sweep[wname][f"b{beta}_c{cap}"] = dict(
                    beta=beta, cap=cap, n=int(len(st)), k_max=float(km),
                    mean_step_pct=100 * float(st.mean()),
                    sd_step_pct=100 * float(st.std()),
                    sharpe_per_step=float(st.mean() / st.std()),
                    nav_at_k_max=float(nav[-1]),
                    dd_at_k_max_pct=100 * float(
                        (nav / np.maximum.accumulate(nav) - 1).min()),
                    nav_at_k_live=float(navl[-1]),
                    dd_at_k_live_pct=100 * float(
                        (navl / np.maximum.accumulate(navl) - 1).min()),
                    mean_notional_at_k_max=float((nt * km * EQUITY).mean()),
                    max_notional_at_k_max=float((nt * km * EQUITY).max()),
                    p99_notional_at_k_max=float(np.percentile(nt * km * EQUITY, 99)),
                    mean_notional_at_k_live=float((nt * K_LIVE * EQUITY).mean()),
                    max_notional_at_k_live=float((nt * K_LIVE * EQUITY).max()))
        b = sweep[wname]["b0.0_c1.0"]
        for v in sweep[wname].values():
            v["vs_FIXED"] = dict(
                k_max_ratio=v["k_max"] / b["k_max"],
                sharpe_ratio=v["sharpe_per_step"] / b["sharpe_per_step"],
                mean_notional_ratio=v["mean_notional_at_k_max"] / b["mean_notional_at_k_max"],
                max_notional_ratio=v["max_notional_at_k_max"] / b["max_notional_at_k_max"],
                nav_ratio_at_k_live=v["nav_at_k_live"] / b["nav_at_k_live"])
    out["sweep"] = sweep

    for wname in ("full", "holdout"):
        print(f"\n== {wname}: beta sweep at cap=99 (uncapped) ==")
        for beta in BETAS:
            v = sweep[wname][f"b{beta}_c99.0"]
            print(f" beta={beta:5.3f} k_max={v['k_max']:.4f} "
                  f"({v['vs_FIXED']['k_max_ratio']:.3f}x) SR/step={v['sharpe_per_step']:.4f} "
                  f"({v['vs_FIXED']['sharpe_ratio']:.3f}x) "
                  f"mean_notl=${v['mean_notional_at_k_max']:>8,.0f} "
                  f"({v['vs_FIXED']['mean_notional_ratio']:.3f}x) "
                  f"max_notl=${v['max_notional_at_k_max']:>9,.0f} "
                  f"({v['vs_FIXED']['max_notional_ratio']:.3f}x) "
                  f"dd@kmax={v['dd_at_k_max_pct']:.1f}%")
        print(f"-- cap sweep at beta=1.0 --")
        for cap in CAPS:
            v = sweep[wname][f"b1.0_c{cap}"]
            print(f" cap={cap:5.1f} k_max={v['k_max']:.4f} "
                  f"mean_notl=${v['mean_notional_at_k_max']:>8,.0f} "
                  f"({v['vs_FIXED']['mean_notional_ratio']:.3f}x) "
                  f"max_notl=${v['max_notional_at_k_max']:>9,.0f} "
                  f"({v['vs_FIXED']['max_notional_ratio']:.3f}x)")
    p = os.path.join(HERE, "candA_beta.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
