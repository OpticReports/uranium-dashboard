"""CANDIDATE A - the decision number: at an IDENTICAL drawdown budget, how
much gross notional does vol-targeting deploy vs the shipped fixed sizing?

Frame (same as phase 1 so the numbers compose):
    gross_notional_frac(leg) = k * BLEND_LEV * w_leg * nf_leg
    nf_leg = notional/equity the engine actually sized = 1.0 (FIXED) or
             min(risk/s_i, cap) (VOL_TARGET)
    live today: k = 15,000 / (1.5 * 100,055) = 0.0999
Per-step blend return at multiplier k = k * BLEND_LEV * w_leg * ret_eq_leg,
exact because ret_eq is equity-path independent (verified V0 in candA_fwdvol).

k_max = largest k with P(maxDD > 30%) <= 10% over stationary-bootstrap paths
of the observed length -- KELLY.md's own drawdown criterion.

Then: notional distribution AT each arm's own k_max. That is the honest
"how much larger a trade" answer: same drawdown budget, different notional.

Output: candA_frontier.json
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
from app.engine import kelly as K                           # noqa: E402

BARS_CSV = os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv")
SIZING_STOP = {"pullback": 2.5, "trend": 5.0}
W = {"pullback": 0.75, "trend": 0.25}
BLEND_LEV = 1.5
EQUITY = 100_055.0
K_LIVE = 15_000.0 / (BLEND_LEV * EQUITY)
HOLDOUT_START = 1719792000
DD_LIMIT, P_LIMIT = 0.30, 0.10
DRAWS, MEAN_BLOCK, SEED = 2000, 10, 20260804


def load_bars():
    return [Bar(ts=int(r["ts_open_unix"]), open=float(r["open"]),
                high=float(r["high"]), low=float(r["low"]),
                close=float(r["close"]), volume=float(r["volume"]))
            for r in csv.DictReader(open(BARS_CSV))]


def leg_cfg(leg, sizing, risk=0.0, cap=1.0):
    if leg == "pullback":
        return BookCfg(name="P", sizing=sizing, strategy="pullback",
                       leverage=1.0, risk=risk, cap=cap, dd_halt=0.30)
    return BookCfg(name="T", sizing=sizing, strategy="donchian", trail_atr=5.0,
                   leverage=1.0, risk=risk, cap=cap, dd_halt=0.50)


def run_leg(bars, leg, sizing, risk=0.0, cap=1.0):
    tc = replace(RESEARCH_TRADE, stop_atr=SIZING_STOP[leg])
    res = run_replay(bars, [leg_cfg(leg, sizing, risk, cap)],
                     RESEARCH_SIGNAL, tc, cash_apy=0.0)
    bk = res.books["P" if leg == "pullback" else "T"]
    rows = [dict(exit_ts=t.exit_ts, entry_ts=t.entry_ts,
                 s=tc.stop_atr * t.atr_at_entry / t.entry_price,
                 nf=t.notional / t.equity_before,
                 ret_eq=t.pnl_usd / t.equity_before,
                 reason=t.exit_reason) for t in bk.trades]
    return bk, rows


def blend_stream(rows_p, rows_t, t0=None):
    """(steps_at_k1, notional_frac_at_k1) in exit order. steps are
    BLEND_LEV*w*ret_eq; notional is BLEND_LEV*w*nf (the gross this leg's
    trade carried, as a fraction of equity, at k=1)."""
    evs = sorted([(r["exit_ts"], "pullback", r) for r in rows_p]
                 + [(r["exit_ts"], "trend", r) for r in rows_t])
    st, nt, tss = [], [], []
    for ts, leg, r in evs:
        if t0 is not None and ts < t0:
            continue
        st.append(BLEND_LEV * W[leg] * r["ret_eq"])
        nt.append(BLEND_LEV * W[leg] * r["nf"])
        tss.append(ts)
    return np.array(st), np.array(nt), np.array(tss)


def boot_idx(n, draws, rng, mean_block=MEAN_BLOCK):
    """Vectorised Politis-Romano stationary bootstrap: (draws, n) indices."""
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
    x = np.where(x <= 0, 1e-12, x)
    nav = np.cumprod(x, axis=1)
    peak = np.maximum.accumulate(nav, axis=1)
    mdd = (nav / peak - 1.0).min(axis=1)
    return float(((mdd < -dd_limit) | ruin).mean())


def k_max(steps, idx, dd_limit=DD_LIMIT, p_limit=P_LIMIT, hi=6.0):
    lo = 0.0
    if dd_prob_vec(steps, hi, idx, dd_limit) <= p_limit:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if dd_prob_vec(steps, mid, idx, dd_limit) <= p_limit:
            lo = mid
        else:
            hi = mid
    return lo


def curve(steps, k):
    nav = np.cumprod(1.0 + k * steps)
    peak = np.maximum.accumulate(nav)
    return nav, float((nav / peak - 1).min())


def dist(a):
    a = np.asarray(a, float)
    return dict(n=int(len(a)), mean=float(a.mean()), median=float(np.median(a)),
                p10=float(np.percentile(a, 10)), p90=float(np.percentile(a, 90)),
                p99=float(np.percentile(a, 99)), max=float(a.max()),
                min=float(a.min()))


def main():
    bars = load_bars()
    out = {"meta": dict(k_live=K_LIVE, equity=EQUITY, blend_lev=BLEND_LEV,
                        dd_limit=DD_LIMIT, p_limit=P_LIMIT, draws=DRAWS,
                        mean_block=MEAN_BLOCK, seed=SEED,
                        fee_rt_bps=2 * RESEARCH_TRADE.taker_fee_bps,
                        sizing_stop=SIZING_STOP, holdout_start=HOLDOUT_START)}

    # risk-match targets from the FIXED arm
    fx, risk_match = {}, {}
    for leg in ("pullback", "trend"):
        bk, rows = run_leg(bars, leg, "fixed", cap=1.0)
        fx[leg] = rows
        risk_match[leg] = float(np.mean([r["nf"] * r["s"] for r in rows]))
    out["risk_match"] = risk_match

    CAPS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 99.0]
    arms = {"FIXED": fx}
    for cap in CAPS:
        a = {}
        for leg in ("pullback", "trend"):
            _, rows = run_leg(bars, leg, "vol_target", risk_match[leg], cap)
            a[leg] = rows
        arms[f"VT_cap{cap}"] = a

    rng_master = np.random.default_rng(SEED + 1)
    res = {}
    for wname, t0 in (("full", None), ("holdout", HOLDOUT_START)):
        # ONE index matrix per window length, shared across arms so the
        # comparison is paired (identical resampled paths).
        ref, _, _ = blend_stream(arms["FIXED"]["pullback"], arms["FIXED"]["trend"], t0)
        idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1))
        res[wname] = {}
        for tag, a in arms.items():
            st, nt, tss = blend_stream(a["pullback"], a["trend"], t0)
            assert len(st) == len(ref), (tag, len(st), len(ref))
            km = k_max(st, idx)
            nav_km, dd_km = curve(st, km)
            nav_live, dd_live = curve(st, K_LIVE)
            yrs = (tss[-1] - tss[0]) / (365.25 * 86400)
            # gross notional per TRADE at k (fraction of equity), and the
            # GROSS BOOK notional (both legs) = sum of concurrent legs; the
            # exit-step frame gives per-trade, which is what a rail clamps.
            res[wname][tag] = dict(
                n_steps=int(len(st)), years=float(yrs),
                k_max=float(km),
                p_dd30_at_k_max=dd_prob_vec(st, km, idx),
                p_dd30_at_k_live=dd_prob_vec(st, K_LIVE, idx),
                # in-sample realised
                cagr_at_k_max_pct=100 * float(nav_km[-1] ** (1 / yrs) - 1),
                maxdd_at_k_max_pct=100 * dd_km,
                cagr_at_k_live_pct=100 * float(nav_live[-1] ** (1 / yrs) - 1),
                maxdd_at_k_live_pct=100 * dd_live,
                # notional: per-trade gross as fraction of equity, at k=1
                notional_frac_k1=dist(nt),
                notional_usd_at_k_max=dist(nt * km * EQUITY),
                notional_usd_at_k_live=dist(nt * K_LIVE * EQUITY),
                gross_sum_at_k_live=float(
                    (nt * K_LIVE * EQUITY).sum() / len(nt)))
        # ratios vs FIXED
        f = res[wname]["FIXED"]
        for tag, v in res[wname].items():
            v["vs_FIXED"] = dict(
                k_max_ratio=v["k_max"] / f["k_max"],
                mean_notional_at_own_kmax=(v["notional_usd_at_k_max"]["mean"]
                                           / f["notional_usd_at_k_max"]["mean"]),
                max_notional_at_own_kmax=(v["notional_usd_at_k_max"]["max"]
                                          / f["notional_usd_at_k_max"]["max"]),
                mean_notional_at_k_live=(v["notional_usd_at_k_live"]["mean"]
                                         / f["notional_usd_at_k_live"]["mean"]),
                max_notional_at_k_live=(v["notional_usd_at_k_live"]["max"]
                                        / f["notional_usd_at_k_live"]["max"]),
                cagr_ratio_at_k_live=(v["cagr_at_k_live_pct"]
                                      / f["cagr_at_k_live_pct"]),
                dd_ratio_at_k_live=(v["maxdd_at_k_live_pct"]
                                    / f["maxdd_at_k_live_pct"]))
    out["frontier"] = res

    # ---- validation: my dd_prob vs the shipped kelly.dd_prob -----------
    st, _, _ = blend_stream(arms["FIXED"]["pullback"], arms["FIXED"]["trend"])
    idxv = boot_idx(len(st), 800, np.random.default_rng(SEED + 1))
    val = {}
    for kk in (0.5, 1.0, 1.5):
        val[f"k{kk}"] = dict(
            mine=dd_prob_vec(st, kk, idxv),
            shipped=K.dd_prob(st, kk, DD_LIMIT, draws=800, seed=SEED))
    out["validation_dd_prob"] = val
    out["validation_blend_final_vs_bench"] = dict(
        mine=float(np.cumprod(1.0 + st)[-1]),
        note="scripts/bench_blend.py blend_curve at lev 1.5 full sample = "
             "2.9628742 on the committed artifact; candA_fwdvol printed 2.9629")

    # ---- k ladder for the chart ----------------------------------------
    ladder = {}
    for wname, t0 in (("full", None), ("holdout", HOLDOUT_START)):
        ref, _, _ = blend_stream(arms["FIXED"]["pullback"], arms["FIXED"]["trend"], t0)
        idx = boot_idx(len(ref), DRAWS, np.random.default_rng(SEED + 1))
        ladder[wname] = {}
        for tag in ("FIXED", "VT_cap2.0", "VT_cap99.0"):
            st, nt, _ = blend_stream(arms[tag]["pullback"], arms[tag]["trend"], t0)
            ks = [round(x, 3) for x in np.arange(0.05, 1.55, 0.05)]
            ladder[wname][tag] = [dict(
                k=float(k), p_dd30=dd_prob_vec(st, k, idx),
                mean_notional_usd=float((nt * k * EQUITY).mean()),
                max_notional_usd=float((nt * k * EQUITY).max()),
                realised_dd_pct=100 * curve(st, k)[1]) for k in ks]
    out["ladder"] = ladder

    for wname in ("full", "holdout"):
        print(f"\n== {wname} ==")
        for tag, v in out["frontier"][wname].items():
            print(f"{tag:12s} k_max={v['k_max']:.4f} "
                  f"({v['vs_FIXED']['k_max_ratio']:.3f}x) "
                  f"notional@own_kmax mean=${v['notional_usd_at_k_max']['mean']:>9,.0f} "
                  f"max=${v['notional_usd_at_k_max']['max']:>10,.0f} "
                  f"({v['vs_FIXED']['mean_notional_at_own_kmax']:.3f}x mean, "
                  f"{v['vs_FIXED']['max_notional_at_own_kmax']:.3f}x max) "
                  f"cagr@kmax={v['cagr_at_k_max_pct']:.1f}% "
                  f"dd@kmax={v['maxdd_at_k_max_pct']:.1f}%")
    print("\nvalidation dd_prob:", json.dumps(out["validation_dd_prob"]))
    p = os.path.join(HERE, "candA_frontier.json")
    json.dump(out, open(p, "w"), default=float)
    print("wrote", p)


if __name__ == "__main__":
    main()
