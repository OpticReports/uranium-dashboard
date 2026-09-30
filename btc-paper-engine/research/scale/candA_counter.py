"""CANDIDATE A - COUNTER-AGENT PASS. Attacks the candidate's own result set.

The candidate's claims under attack:
  C1 mean notional gain is only ~1.12x and that is a HARD BOUND = 1+CV^2(s).
  C2 k_max (the DD budget) does not move: 0.987x full, 0.885x holdout.
  C3 the holdout degradation is monotone in beta.
Attacks:
  A1 SEED. k_max ratios are 1-11% effects. Are they inside bootstrap noise?
     Paired multi-seed test: SAME resampled paths for both arms, 16 seeds.
  A2 WINDOW. One holdout date decided C2/C3. Sweep the split date and run
     every calendar year standalone.
  A3 SCALE-INVARIANCE of the 1+CV^2 bound. s = m*ATR/close, so CV(s) must be
     independent of the stop multiple m. Verified numerically over m, and over
     ATR lookback, to show what WOULD have to change to move the bound.
  A4 RISK-MATCH BASIS. The match r=mean(s) is a choice. Re-run with r set by
     median(s), by harmonic mean, and by matching TOTAL realised loss.
  A5 SHARPE significance. Paired stationary-bootstrap CI on the per-step
     Sharpe DIFFERENCE (same paths both arms) -- is the full-sample +5.1%
     distinguishable from zero, and is the holdout -6.7%?

Output: candA_counter.json
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
from app.indicators import atr as atr_pure                  # noqa: E402
from app.config import RESEARCH_SIGNAL, RESEARCH_TRADE      # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SIZING_STOP = {"pullback": 2.5, "trend": 5.0}
W = {"pullback": 0.75, "trend": 0.25}
BLEND_LEV, EQUITY = 1.5, 100_055.0
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY)
DD_LIMIT, P_LIMIT, DRAWS, MEAN_BLOCK, SEED = 0.30, 0.10, 2000, 10, 20260804


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def run_leg(bars, leg):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZING_STOP[leg])
    cfg = (BookCfg(name="P", sizing="fixed", strategy="pullback", leverage=1.0,
                   cap=1.0, dd_halt=0.30) if leg == "pullback" else
           BookCfg(name="T", sizing="fixed", strategy="donchian", trail_atr=5.0,
                   leverage=1.0, cap=1.0, dd_halt=0.50))
    bk = run_replay(bars, [cfg], RESEARCH_SIGNAL, tc, cash_apy=0.0).books[cfg.name]
    return [dict(exit_ts=t.exit_ts, entry_ts=t.entry_ts,
                 s=tc.stop_atr * t.atr_at_entry / t.entry_price,
                 atr_n=t.atr_at_entry / t.entry_price,
                 gross=(1.0 if t.side == "L" else -1.0) * (t.exit_price / t.entry_price - 1),
                 fee=t.fees_usd / t.notional) for t in bk.trades]


def boot_idx(n, draws, rng, mean_block=MEAN_BLOCK):
    p = 1.0 / mean_block
    idx = np.empty((draws, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, draws)
    restart = rng.random((draws, n)) < p
    jump = rng.integers(0, n, (draws, n))
    for i in range(1, n):
        idx[:, i] = np.where(restart[:, i], jump[:, i], (idx[:, i - 1] + 1) % n)
    return idx


def dd_prob_vec(steps, k, idx):
    x = 1.0 + k * steps[idx]
    ruin = (x <= 0).any(axis=1)
    nav = np.cumprod(np.where(x <= 0, 1e-12, x), axis=1)
    mdd = (nav / np.maximum.accumulate(nav, axis=1) - 1.0).min(axis=1)
    return float(((mdd < -DD_LIMIT) | ruin).mean())


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


def build(rows_by_leg, beta, cap, r_by_leg, sbar, t0=None, t1=None):
    evs = []
    for leg, rows in rows_by_leg.items():
        for r in rows:
            su = (r["s"] ** beta) * (sbar[leg] ** (1 - beta))
            nf = min(r_by_leg[leg] / su, cap)
            evs.append((r["exit_ts"],
                        BLEND_LEV * W[leg] * nf * (r["gross"] - r["fee"]),
                        BLEND_LEV * W[leg] * nf))
    evs.sort(key=lambda x: x[0])
    evs = [e for e in evs if (t0 is None or e[0] >= t0) and (t1 is None or e[0] < t1)]
    return np.array([e[1] for e in evs]), np.array([e[2] for e in evs])


def main():
    bars = load_bars()
    rows_by_leg = {leg: run_leg(bars, leg) for leg in ("pullback", "trend")}
    sbar = {leg: float(np.mean([r["s"] for r in rows_by_leg[leg]]))
            for leg in rows_by_leg}
    rmean = dict(sbar)
    out = {"meta": dict(draws=DRAWS, dd_limit=DD_LIMIT, p_limit=P_LIMIT,
                        blend_lev=BLEND_LEV, equity=EQUITY, k_live=K_LIVE)}

    # ============ A1 SEED: paired multi-seed k_max ======================
    a1 = {}
    for wname, t0 in (("full", None), ("holdout", 1719792000)):
        ref, _ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
        recs = []
        for sd in range(16):
            idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1 + sd * 7919))
            kf = k_max(build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)[0], idx)
            kv = k_max(build(rows_by_leg, 1.0, 99.0, rmean, sbar, t0)[0], idx)
            kv2 = k_max(build(rows_by_leg, 1.0, 2.0, rmean, sbar, t0)[0], idx)
            recs.append(dict(seed=SEED + 1 + sd * 7919, k_fixed=kf,
                             k_vt_unc=kv, k_vt_cap2=kv2,
                             ratio_unc=kv / kf, ratio_cap2=kv2 / kf))
        ru = np.array([r["ratio_unc"] for r in recs])
        r2 = np.array([r["ratio_cap2"] for r in recs])
        a1[wname] = dict(
            n_seeds=len(recs), records=recs,
            k_fixed=dict(mean=float(np.mean([r["k_fixed"] for r in recs])),
                         sd=float(np.std([r["k_fixed"] for r in recs])),
                         min=float(min(r["k_fixed"] for r in recs)),
                         max=float(max(r["k_fixed"] for r in recs))),
            ratio_uncapped=dict(mean=float(ru.mean()), sd=float(ru.std()),
                                min=float(ru.min()), max=float(ru.max()),
                                n_above_1=int((ru > 1).sum()),
                                t_vs_1=float((ru.mean() - 1) / (ru.std(ddof=1) / np.sqrt(len(ru))))),
            ratio_cap2=dict(mean=float(r2.mean()), sd=float(r2.std()),
                            min=float(r2.min()), max=float(r2.max()),
                            n_above_1=int((r2 > 1).sum()),
                            t_vs_1=float((r2.mean() - 1) / (r2.std(ddof=1) / np.sqrt(len(r2))))))
        u = a1[wname]["ratio_uncapped"]
        print(f"A1 {wname:8s}: k_max ratio VT/FIX over 16 seeds mean={u['mean']:.4f} "
              f"sd={u['sd']:.4f} range=[{u['min']:.4f},{u['max']:.4f}] "
              f"above1={u['n_above_1']}/16 t={u['t_vs_1']:+.2f}")
    out["A1_seed"] = a1

    # ============ A2 WINDOW: split sweep + per-year =====================
    a2 = {"split_sweep": [], "per_year": []}
    for yr, t0 in ((2023, 1672531200), (2024, 1704067200), (2025, 1735689600),
                   (2024.5, 1719792000), (2025.5, 1751328000)):
        ref, _ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
        if len(ref) < 40:
            continue
        idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1))
        sf, nf_ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
        sv, nv = build(rows_by_leg, 1.0, 99.0, rmean, sbar, t0)
        kf, kv = k_max(sf, idx), k_max(sv, idx)
        a2["split_sweep"].append(dict(
            from_year=yr, start_ts=t0, n=int(len(sf)),
            k_fixed=kf, k_vt=kv, k_ratio=kv / kf,
            sr_fixed=float(sf.mean() / sf.std()), sr_vt=float(sv.mean() / sv.std()),
            sr_ratio=float((sv.mean() / sv.std()) / (sf.mean() / sf.std())),
            mean_notional_ratio=float((nv * kv).mean() / (nf_ * kf).mean()),
            nav_ratio_at_k_live=float(np.cumprod(1 + K_LIVE * sv)[-1]
                                      / np.cumprod(1 + K_LIVE * sf)[-1])))
    for y, (t0, t1) in {2022: (1640995200, 1672531200), 2023: (1672531200, 1704067200),
                        2024: (1704067200, 1735689600), 2025: (1735689600, 1767225600),
                        2026: (1767225600, 1799000000)}.items():
        sf, nf_ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0, t1)
        sv, nv = build(rows_by_leg, 1.0, 99.0, rmean, sbar, t0, t1)
        if len(sf) < 15:
            continue
        a2["per_year"].append(dict(
            year=y, n=int(len(sf)),
            nav_fixed=float(np.cumprod(1 + K_LIVE * sf)[-1]),
            nav_vt=float(np.cumprod(1 + K_LIVE * sv)[-1]),
            sr_fixed=float(sf.mean() / sf.std()), sr_vt=float(sv.mean() / sv.std()),
            sr_ratio=float((sv.mean() / sv.std()) / (sf.mean() / sf.std()))
            if sf.mean() != 0 else None,
            mean_notional_ratio=float(nv.mean() / nf_.mean())))
    out["A2_window"] = a2
    print("A2 split sweep:", [(r["from_year"], round(r["k_ratio"], 3),
                               round(r["sr_ratio"], 3)) for r in a2["split_sweep"]])
    print("A2 per year SR ratio:", [(r["year"], round(r["sr_ratio"] or 0, 3),
                                     round(r["mean_notional_ratio"], 3))
                                    for r in a2["per_year"]])

    # ============ A3 SCALE-INVARIANCE of the 1+CV^2 bound ==============
    c = np.array([b.close for b in bars]); h = np.array([b.high for b in bars])
    lo = np.array([b.low for b in bars])
    a3 = {"stop_multiple_invariance": [], "atr_lookback": []}
    for m in (1.0, 2.0, 2.5, 3.5, 5.0):
        for leg in ("pullback", "trend"):
            s = np.array([r["atr_n"] for r in rows_by_leg[leg]]) * m
            a3["stop_multiple_invariance"].append(dict(
                leg=leg, stop_mult=m, cv=float(s.std() / s.mean()),
                bound=float(s.mean() * (1 / s).mean())))
    for n_atr in (5, 7, 14, 30, 60):
        a = np.array([x if x is not None else np.nan for x in
                      atr_pure(list(h), list(lo), list(c), n_atr)], float)
        an = (a / c)[210:]
        an = an[np.isfinite(an)]
        a3["atr_lookback"].append(dict(
            atr_n=n_atr, cv_bar_level=float(an.std() / an.mean()),
            bound_bar_level=float(an.mean() * (1 / an).mean())))
    out["A3_bound_invariance"] = a3
    print("A3 stop-mult invariance (cv should be identical per leg):",
          [(r["leg"][:4], r["stop_mult"], round(r["cv"], 4)) for r in a3["stop_multiple_invariance"]])
    print("A3 atr lookback bound:", [(r["atr_n"], round(r["bound_bar_level"], 4))
                                     for r in a3["atr_lookback"]])

    # ============ A4 RISK-MATCH BASIS ==================================
    a4 = {}
    bases = {}
    for leg in ("pullback", "trend"):
        s = np.array([r["s"] for r in rows_by_leg[leg]])
        bases[leg] = dict(mean=float(s.mean()), median=float(np.median(s)),
                          harmonic=float(1 / (1 / s).mean()))
    for bname in ("mean", "median", "harmonic"):
        rb = {leg: bases[leg][bname] for leg in bases}
        for wname, t0 in (("full", None), ("holdout", 1719792000)):
            ref, _ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
            idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1))
            sf, nf_ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
            sv, nv = build(rows_by_leg, 1.0, 99.0, rb, sbar, t0)
            kf, kv = k_max(sf, idx), k_max(sv, idx)
            a4[f"{bname}_{wname}"] = dict(
                risk_basis=rb, k_fixed=kf, k_vt=kv, k_ratio=kv / kf,
                mean_risk_frac_vt_over_fixed=float(
                    np.mean([rb[l] for l in ("pullback", "trend")])
                    / np.mean([bases[l]["mean"] for l in ("pullback", "trend")])),
                mean_notional_at_own_kmax_ratio=float(
                    (nv * kv).mean() / (nf_ * kf).mean()),
                max_notional_at_own_kmax_ratio=float(
                    (nv * kv).max() / (nf_ * kf).max()))
    out["A4_risk_match_basis"] = a4
    for k, v in a4.items():
        print(f"A4 {k:18s}: k_ratio={v['k_ratio']:.3f} "
              f"mean_notl_ratio={v['mean_notional_at_own_kmax_ratio']:.3f} "
              f"max_notl_ratio={v['max_notional_at_own_kmax_ratio']:.3f}")

    # ============ A5 paired Sharpe difference CI ========================
    a5 = {}
    for wname, t0 in (("full", None), ("holdout", 1719792000)):
        sf, _ = build(rows_by_leg, 0.0, 1.0, rmean, sbar, t0)
        sv, _ = build(rows_by_leg, 1.0, 99.0, rmean, sbar, t0)
        idx = boot_idx(len(sf), 4000, np.random.default_rng(SEED + 99))
        srf = sf[idx].mean(axis=1) / sf[idx].std(axis=1)
        srv = sv[idx].mean(axis=1) / sv[idx].std(axis=1)
        d = srv - srf
        a5[wname] = dict(
            n=int(len(sf)),
            sr_fixed_point=float(sf.mean() / sf.std()),
            sr_vt_point=float(sv.mean() / sv.std()),
            diff_point=float(sv.mean() / sv.std() - sf.mean() / sf.std()),
            diff_boot_mean=float(d.mean()), diff_boot_sd=float(d.std()),
            diff_ci5=float(np.percentile(d, 5)), diff_ci95=float(np.percentile(d, 95)),
            p_diff_gt_0=float((d > 0).mean()))
        v = a5[wname]
        print(f"A5 {wname:8s}: SR diff={v['diff_point']:+.5f} "
              f"90% CI [{v['diff_ci5']:+.5f},{v['diff_ci95']:+.5f}] "
              f"P(diff>0)={v['p_diff_gt_0']:.3f}")
    out["A5_sharpe_paired"] = a5

    p = os.path.join(HERE, "candA_counter.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
