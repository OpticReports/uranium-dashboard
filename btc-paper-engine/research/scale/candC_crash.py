"""CANDIDATE C, step 4: THE CASE THAT MATTERS. Crypto correlations go to 1 in
a crash. Test it on the data rather than asserting a number.

FOUR TESTS, in increasing severity:
 T1  MEASURED stress-conditional correlation. Split the sample into stress and
     calm bars (defined on BTC price alone, the market factor) and re-measure
     the cross-asset correlation of the STRATEGY streams in each. Also measure
     the underlying PRICE correlation in each, which is the claim being tested.
 T2  SIDE CONCENTRATION. For this strategy the real crash mechanism is not
     covariance, it is every leg ending up on the SAME side at once. Measured
     directly from the engine's own positions.
 T3  CRASH-ONLY BOOTSTRAP. Re-run the DD-budget sizing with block STARTS
     restricted to stress episodes -- i.e. price a future made only of
     crashes. This imposes no copula: blocks run forward through the real
     series, so cross-asset alignment and joint tail dependence inside the
     block are the ones that actually happened.
 T4  THREE HARD DEPENDENCE ANCHORS, all built from real data, no synthesis:
       rho -> 0 : circular block-shift each asset independently. Preserves
                  each asset's marginal AND its own autocorrelation EXACTLY;
                  destroys only cross-asset alignment.
       rho = measured : the real matrix.
       rho = 1  : replace every asset's stream with BTC's. Must return a
                  multiple of exactly 1.00 -- that is the machinery's own
                  sanity check, and it is the honest answer to "what if
                  everything becomes the same trade".

Run: python3 research/scale/candC_crash.py
"""
from __future__ import annotations
import json, os, time

import numpy as np
from candC_lib import (BARS_PER_YEAR, EQUITY, HERE, HORIZON, SEED, ann_stats,
                       dd_constrained, dd_prob)

Z = np.load(os.path.join(HERE, "candC_streams.npz"), allow_pickle=True)
UNIVERSE = [str(x) for x in Z["assets"]]
S = {(c, l): Z[f"{c}_{l}"] for c in UNIVERSE for l in ("S3", "S4")}
POS = {(c, l): Z[f"{c}_pos_{l}"] for c in UNIVERSE for l in ("S3", "S4")}
CLOSE = {c: Z[f"{c}_close"] for c in UNIVERSE}
NB = len(S[("BTC", "S3")])


def blend(coins, w=0.75):
    n = len(coins)
    return sum((w / n) * S[(c, "S3")] + ((1 - w) / n) * S[(c, "S4")] for c in coins)


def main():
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe": UNIVERSE, "n_bars": NB}

    # ---- define stress on BTC price alone (the market factor) -------------
    # ALIGNMENT: run_replay skips warmup_bars=210, so the MTM series has
    # len(close)-210 entries and the return stream has one fewer again. The
    # return at stream index j is the move INTO close index 211+j. Getting
    # this wrong silently shifts every regime label, so it is asserted.
    W = len(CLOSE["BTC"]) - NB               # = 211
    px = CLOSE["BTC"][W:]
    assert len(px) == NB, (len(px), NB, W)
    # rolling 120-bar (20-day) peak: a local drawdown measure, not a 2-year one
    k = 120
    roll = np.array([px[max(0, i - k):i + 1].max() for i in range(NB)])
    dd_local = px / roll - 1.0
    lr = np.diff(np.log(CLOSE["BTC"]))[W - 1:]
    assert len(lr) == NB, (len(lr), NB)
    rv = np.array([lr[max(0, i - 30):i + 1].std(ddof=1) if i >= 2 else np.nan
                   for i in range(NB)])
    rv = np.nan_to_num(rv, nan=np.nanmedian(rv))

    DEFS = {
        "drawdown >=15% off 20-day peak": dd_local <= -0.15,
        "drawdown >=10% off 20-day peak": dd_local <= -0.10,
        "top-decile 30-bar realised vol": rv >= np.quantile(rv, 0.90),
        "top-quartile 30-bar realised vol": rv >= np.quantile(rv, 0.75),
        "worst 10% of BTC 4h returns": lr <= np.quantile(lr, 0.10),
    }
    print("=" * 100)
    print("STRESS DEFINITIONS (on BTC price only — the market factor)")
    print("=" * 100)
    for lbl, m in DEFS.items():
        print(f"  {lbl:<38} {m.sum():>5} bars ({m.mean()*100:>5.1f}%)  "
              f"BTC mean 4h ret {lr[m].mean()*1e4:>+7.1f} bp vs "
              f"{lr[~m].mean()*1e4:>+6.1f} bp calm")
    OUT["stress_defs"] = {lbl: {"n_bars": int(m.sum()), "frac": float(m.mean())}
                          for lbl, m in DEFS.items()}

    # ---- T1: stress-conditional correlation ------------------------------
    print()
    print("=" * 100)
    print("T1 — DOES CORRELATION GO TO 1 IN A CRASH?  measured, strategy vs price")
    print("=" * 100)
    B = {c: 0.75 * S[(c, "S3")] + 0.25 * S[(c, "S4")] for c in UNIVERSE}
    PR = {c: np.diff(np.log(CLOSE[c]))[W - 1:] for c in UNIVERSE}
    for c in UNIVERSE:
        assert len(PR[c]) == NB
    iu = np.triu_indices(len(UNIVERSE), 1)

    def offdiag(mat_src, mask):
        M = np.stack([mat_src[c][mask] for c in UNIVERSE])
        return np.corrcoef(M)[iu]

    print(f"  {'regime':<38} {'PRICE rho':>22}   {'STRATEGY rho':>22}")
    print(f"  {'':<38} {'mean':>7}{'min':>7}{'max':>8}   {'mean':>7}{'min':>7}{'max':>8}")
    T1 = {}
    for lbl, m in [("FULL SAMPLE", np.ones(NB, bool))] + list(DEFS.items()):
        op, os_ = offdiag(PR, m), offdiag(B, m)
        T1[lbl] = {"n_bars": int(m.sum()),
                   "price": {"mean": float(op.mean()), "min": float(op.min()),
                             "max": float(op.max())},
                   "strategy": {"mean": float(os_.mean()), "min": float(os_.min()),
                                "max": float(os_.max())}}
        print(f"  {lbl:<38} {op.mean():>+7.3f}{op.min():>+7.3f}{op.max():>+8.3f}   "
              f"{os_.mean():>+7.3f}{os_.min():>+7.3f}{os_.max():>+8.3f}")
    OUT["T1_conditional_correlation"] = T1
    fs, dd15 = T1["FULL SAMPLE"], T1["drawdown >=15% off 20-day peak"]
    print(f"\n  PRICE correlation in a >=15% drawdown: {fs['price']['mean']:+.3f} -> "
          f"{dd15['price']['mean']:+.3f}  ({dd15['price']['mean']/fs['price']['mean']:.2f}x)")
    print(f"  STRATEGY correlation, same bars:       {fs['strategy']['mean']:+.3f} -> "
          f"{dd15['strategy']['mean']:+.3f}  "
          f"({dd15['strategy']['mean']/fs['strategy']['mean']:.2f}x)")

    # ---- T2: side concentration ------------------------------------------
    print()
    print("=" * 100)
    print("T2 — SIDE CONCENTRATION. For THIS strategy the crash mechanism is every")
    print("     leg ending up on the same side, not covariance drift.")
    print("=" * 100)
    # reconstruct per-bar signed exposure from the engine's own positions:
    # sign of the leg's return vs the asset's return tells us the side.
    side = {}
    for c in UNIVERSE:
        for l in ("S3", "S4"):
            r, p = S[(c, l)], POS[(c, l)]
            pr = PR[c]
            sg = np.zeros(NB)
            live = p & (np.abs(r) > 1e-12) & (np.abs(pr) > 1e-12)
            sg[live] = np.sign(r[live] * pr[live])
            side[(c, l)] = sg
    net = np.stack([side[(c, "S3")] * 0.75 + side[(c, "S4")] * 0.25 for c in UNIVERSE])
    live_ct = (np.abs(net) > 1e-9).sum(axis=0)
    gross_w = np.abs(net).sum(axis=0)
    net_w = np.abs(net.sum(axis=0))
    conc = np.divide(net_w, gross_w, out=np.zeros(NB), where=gross_w > 1e-9)
    has = gross_w > 1e-9
    print(f"  bars with at least one leg live: {has.sum()} ({has.mean()*100:.1f}%)")
    print(f"  mean |net|/gross directional concentration (1.00 = every live leg")
    print(f"    on the SAME side, 0.00 = perfectly offsetting):")
    print(f"    full sample      {conc[has].mean():.3f}")
    T2 = {"full_sample": float(conc[has].mean()), "regimes": {}}
    for lbl, m in DEFS.items():
        mm = m & has
        T2["regimes"][lbl] = {"conc": float(conc[mm].mean()),
                              "mean_legs_live": float(live_ct[mm].mean()),
                              "n_bars": int(mm.sum())}
        print(f"    {lbl:<32} {conc[mm].mean():.3f}   "
              f"({live_ct[mm].mean():.2f} legs live)")
    frac_all_same = float((conc[has] > 0.99).mean())
    T2["frac_bars_all_same_side"] = frac_all_same
    print(f"  fraction of live bars with EVERY live leg on the same side: "
          f"{frac_all_same*100:.1f}%")
    OUT["T2_side_concentration"] = T2

    # ---- T3: crash-only bootstrap ----------------------------------------
    print()
    print("=" * 100)
    print("T3 — CRASH-ONLY FUTURE. DD-budget sizing with block starts restricted")
    print("     to stress bars. No copula: blocks run forward through the REAL")
    print("     series, so the joint tails are the ones that happened.")
    print("=" * 100)
    b1, b6 = blend(["BTC"]), blend(UNIVERSE)
    k1_full, k6_full = dd_constrained(b1), dd_constrained(b6)
    print(f"  {'bootstrap pool':<38} {'k(BTC)':>8} {'k(6 asset)':>11} {'MULTIPLE':>9} "
          f"{'gross $ at 6':>13}")
    print(f"  {'full sample (the headline)':<38} {k1_full:>8.3f} {k6_full:>11.3f} "
          f"{k6_full/k1_full:>8.2f}x ${k6_full*EQUITY:>12,.0f}")
    T3 = {"full_sample": {"k_btc": k1_full, "k_6": k6_full,
                          "mult": k6_full / k1_full,
                          "gross_6": k6_full * EQUITY}}
    for lbl, m in DEFS.items():
        pool = np.flatnonzero(m)
        if len(pool) < 60:
            continue
        k1 = dd_constrained(b1, pool=pool)
        k6 = dd_constrained(b6, pool=pool)
        T3[lbl] = {"k_btc": k1, "k_6": k6, "pool_bars": int(len(pool)),
                   "mult": (k6 / k1) if k1 > 0 else None,
                   "gross_6": k6 * EQUITY}
        print(f"  {lbl:<38} {k1:>8.3f} {k6:>11.3f} "
              f"{(k6/k1) if k1>0 else float('nan'):>8.2f}x ${k6*EQUITY:>12,.0f}")
    OUT["T3_crash_only_bootstrap"] = T3

    # ---- T4: three hard dependence anchors -------------------------------
    print()
    print("=" * 100)
    print("T4 — DEPENDENCE ANCHORS, all built from real streams")
    print("=" * 100)
    rng = np.random.default_rng(SEED)
    # rho -> 0 : independent circular shifts (marginals + own autocorr exact)
    shift_mults, shift_rhos = [], []
    for t in range(12):
        sh = {}
        for c in UNIVERSE:
            o = int(rng.integers(0, NB))
            sh[c] = 0.75 * np.roll(S[(c, "S3")], o) + 0.25 * np.roll(S[(c, "S4")], o)
        s6 = sum(sh[c] / len(UNIVERSE) for c in UNIVERSE)
        M = np.stack([sh[c] for c in UNIVERSE])
        shift_rhos.append(float(np.corrcoef(M)[iu].mean()))
        shift_mults.append(dd_constrained(s6) / k1_full)
    sm = np.array(shift_mults)
    print(f"  rho -> 0   (12 independent circular block-shifts)")
    print(f"             realised mean off-diag rho {np.mean(shift_rhos):+.4f}")
    print(f"             multiple vs BTC: mean {sm.mean():.2f}x  sd {sm.std(ddof=1):.3f}  "
          f"range {sm.min():.2f}-{sm.max():.2f}x")
    # rho = measured
    print(f"  rho = measured ({T1['FULL SAMPLE']['strategy']['mean']:+.3f})")
    print(f"             multiple vs BTC: {k6_full/k1_full:.2f}x   <- THE HEADLINE")
    # rho = 1
    s_one = sum(blend(["BTC"]) / len(UNIVERSE) for _ in UNIVERSE)
    k_one = dd_constrained(s_one)
    print(f"  rho = 1    (every asset replaced by BTC's own stream)")
    print(f"             multiple vs BTC: {k_one/k1_full:.2f}x   "
          f"(must be 1.00 — machinery sanity check)")
    OUT["T4_anchors"] = {
        "rho_zero": {"realised_rho": float(np.mean(shift_rhos)),
                     "mult_mean": float(sm.mean()), "mult_sd": float(sm.std(ddof=1)),
                     "mult_min": float(sm.min()), "mult_max": float(sm.max()),
                     "all": sm.tolist()},
        "rho_measured": {"rho": T1["FULL SAMPLE"]["strategy"]["mean"],
                         "mult": k6_full / k1_full},
        "rho_one": {"mult": k_one / k1_full, "k": k_one}}

    # analytic vol-only law through the same anchors, for the shape
    print()
    print("  Analytic vol-only law sqrt(N/(1+(N-1)rho)) for the SHAPE (it prices")
    print("  variance only, so it OVER-promises against the DD-budget numbers):")
    rho_m = T1["FULL SAMPLE"]["strategy"]["mean"]
    print(f"  {'rho':>8} " + " ".join(f"{'N='+str(n):>7}" for n in (1, 2, 3, 4, 6, 8, 12)))
    LAW = {}
    for rho, tag in ((0.0, "independent"), (rho_m, "MEASURED"),
                     (dd15["strategy"]["mean"], "in >=15% BTC drawdown"),
                     (0.25, ""), (0.50, ""), (1.0, "everything one trade")):
        row, line = {}, f"  {rho:>+8.3f} "
        for N in (1, 2, 3, 4, 6, 8, 12):
            d = 1 + (N - 1) * rho
            f = float(np.sqrt(N / d)) if d > 1e-9 else float("inf")
            row[N] = f
            line += f"{f:>7.2f} " if np.isfinite(f) else f"{'inf':>7} "
        LAW[f"{rho:+.4f}"] = row
        print(line + ("  <- " + tag if tag else ""))
    OUT["analytic_law"] = LAW

    # ---- realised worst windows ------------------------------------------
    print()
    print("=" * 100)
    print("REALISED (not bootstrapped) WORST WINDOWS at each portfolio's OWN k")
    print("=" * 100)
    def realised(s, k, lbl):
        eq = np.cumprod(1 + k * s)
        pk = np.maximum.accumulate(eq)
        dd = eq / pk - 1
        w = 2 * BARS_PER_YEAR
        worst2y = min((eq[i:i+w] / np.maximum.accumulate(eq[i:i+w]) - 1).min()
                      for i in range(0, max(1, len(eq) - w), 60))
        yrs = len(s) / BARS_PER_YEAR
        return {"label": lbl, "k": k, "total_return_pct": float(100*(eq[-1]-1)),
                "in_sample_cagr_pct": float(100*(eq[-1]**(1/yrs) - 1)),
                "max_dd_pct": float(100*dd.min()),
                "worst_rolling_2y_dd_pct": float(100*worst2y),
                "worst_bar_pct": float(100*(k*s).min())}
    rs = [realised(b1, k1_full, "BTC only, at its own k"),
          realised(b6, k6_full, "6 assets, at its own k"),
          realised(b6, k1_full, "6 assets, at BTC's k (same gross)")]
    for r in rs:
        print(f"  {r['label']:<36} k {r['k']:>6.3f}  maxDD {r['max_dd_pct']:>7.2f}%  "
              f"worst 2y DD {r['worst_rolling_2y_dd_pct']:>7.2f}%  "
              f"worst bar {r['worst_bar_pct']:>6.2f}%  in-sample CAGR "
              f"{r['in_sample_cagr_pct']:>6.1f}%")
    print("  IN-SAMPLE. Not a forecast. The CAGR column is there only to show the")
    print("  DD column was not bought by giving up return.")
    OUT["realised"] = rs

    json.dump(OUT, open(os.path.join(HERE, "candC_crash.json"), "w"), indent=1,
              default=str)
    print("\nfrozen -> candC_crash.json")


if __name__ == "__main__":
    main()
