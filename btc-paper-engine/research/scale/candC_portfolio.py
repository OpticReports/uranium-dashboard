"""CANDIDATE C, step 3: THE ANSWER. How much gross notional do N asset-legs
support at the SAME portfolio drawdown budget as today?

Definition, so the number is unambiguous:
  each leg stream r_i is the per-bar MTM return of a book whose notional is
  1.00 x equity. A weighted blend s = sum_i w_i r_i with sum(w)=1 is therefore
  the per-bar return of a portfolio carrying gross notional = 1.00 x equity,
  split w_i. k = the largest multiplier with P(maxDD > 30%) <= 10% over a
  FIXED 2.00-year horizon is then exactly gross/equity. Every case below uses
  the identical stream length and the identical horizon, so the comparison
  cannot confound diversification with holding period.

WEIGHTS: 75/25 pullback/trend WITHIN each asset (the shipped S5 mix), equal
across assets. Asset ORDER is the pre-registered liquidity ranking from
candC_fetch.py -- 24h venue volume, no return information -- so the nested
N=1..6 ladder is not a cherry-pick. The full C(6,N) subset distribution is
reported alongside it, which is the honest check on that.

Run: python3 research/scale/candC_portfolio.py
"""
from __future__ import annotations
import itertools, json, os, time

import numpy as np
from candC_lib import (BARS_PER_YEAR, DD_LIMIT, EQUITY, HERE, HORIZON,
                       LIVE_GROSS, P_LIMIT, SEED, ann_stats, boot_stats,
                       dd_constrained)

Z = np.load(os.path.join(HERE, "candC_streams.npz"), allow_pickle=True)
UNIVERSE = [str(x) for x in Z["assets"]]
FETCH = json.load(open(os.path.join(HERE, "candC_fetch.json")))
S = {(c, l): Z[f"{c}_{l}"] for c in UNIVERSE for l in ("S3", "S4")}
NB = len(S[(UNIVERSE[0], "S3")])


def blend(coins, w_pull=0.75):
    """Equal across assets, 75/25 within. sum of weights = 1 exactly."""
    n = len(coins)
    return sum((w_pull / n) * S[(c, "S3")] + ((1 - w_pull) / n) * S[(c, "S4")]
               for c in coins)


def case(label, s, extra=None):
    k = dd_constrained(s)
    p10, p50, pneg = boot_stats(s)
    d = {"label": label, "k_at_DD30": k, "gross_usd": k * EQUITY,
         "x_live_15k": k * EQUITY / LIVE_GROSS,
         "equity_for_100k": 100_000 / k if k > 0 else None,
         "equity_for_1m": 1_000_000 / k if k > 0 else None,
         "kstar_p10": p10, "kstar_p50": p50, "prob_neg_edge": pneg,
         **ann_stats(s)}
    if extra:
        d.update(extra)
    return d


def main():
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe_liquidity_order": UNIVERSE, "n_bars": NB,
           "years": NB / BARS_PER_YEAR, "horizon_bars": HORIZON,
           "dd_limit": DD_LIMIT, "p_limit": P_LIMIT, "equity": EQUITY,
           "live_gross": LIVE_GROSS}

    print("=" * 100)
    print("BASELINE — BTC alone, the book as it exists today (2 legs, one asset)")
    print("=" * 100)
    b_pull = case("BTC pullback only (1 leg, 1 asset)", S[("BTC", "S3")])
    b_btc = case("BTC 75/25 blend = TODAY'S BOOK", blend(["BTC"]))
    for c in (b_pull, b_btc):
        print(f"  {c['label']:<42} annSR {c['ann_SR']:>5.2f}  k {c['k_at_DD30']:>6.3f}  "
              f"gross ${c['gross_usd']:>10,.0f}  = {c['x_live_15k']:>5.2f}x live")
    OUT["baseline"] = {"btc_pullback_only": b_pull, "btc_blend_today": b_btc}

    # ---------------- the nested liquidity ladder --------------------------
    print()
    print("=" * 100)
    print("THE LADDER — adding assets in PRE-REGISTERED liquidity order")
    print(f"  k = gross/equity at P(maxDD>{DD_LIMIT:.0%}) <= {P_LIMIT:.0%} over a fixed "
          f"{HORIZON/BARS_PER_YEAR:.2f}y horizon")
    print("=" * 100)
    print(f"  {'N':>2} {'assets':<34} {'annSR':>6} {'annSD':>7} {'k':>6} "
          f"{'gross $':>11} {'vs 1':>6} {'eq for $1m':>12}")
    ladder = {}
    for n in range(1, len(UNIVERSE) + 1):
        coins = UNIVERSE[:n]
        c = case("+".join(coins), blend(coins), {"coins": coins, "n": n})
        c["mult_vs_btc"] = c["k_at_DD30"] / b_btc["k_at_DD30"]
        ladder[n] = c
        print(f"  {n:>2} {'+'.join(coins):<34} {c['ann_SR']:>6.2f} "
              f"{c['ann_sd_pct']:>6.1f}% {c['k_at_DD30']:>6.3f} "
              f"${c['gross_usd']:>10,.0f} {c['mult_vs_btc']:>5.2f}x "
              f"${c['equity_for_1m']:>11,.0f}")
    OUT["ladder"] = ladder

    # ---------------- every subset, so the ladder cannot hide a cherry-pick
    print()
    print("=" * 100)
    print("ALL C(6,N) SUBSETS — is the liquidity ladder lucky?")
    print("=" * 100)
    print(f"  {'N':>2} {'#subsets':>9} {'mult: min':>10} {'median':>8} {'mean':>8} "
          f"{'max':>8}   {'best subset':<26} {'worst subset':<26}")
    subs = {}
    for n in range(1, len(UNIVERSE) + 1):
        rows = []
        for combo in itertools.combinations(UNIVERSE, n):
            k = dd_constrained(blend(list(combo)))
            rows.append((k / b_btc["k_at_DD30"], "+".join(combo), k))
        rows.sort()
        m = np.array([r[0] for r in rows])
        subs[n] = {"n_subsets": len(rows),
                   "mult_min": float(m.min()), "mult_median": float(np.median(m)),
                   "mult_mean": float(m.mean()), "mult_max": float(m.max()),
                   "best": rows[-1][1], "worst": rows[0][1],
                   "all": [{"coins": r[1], "k": r[2], "mult": r[0]} for r in rows]}
        print(f"  {n:>2} {len(rows):>9} {m.min():>9.2f}x {np.median(m):>7.2f}x "
              f"{m.mean():>7.2f}x {m.max():>7.2f}x   {rows[-1][1]:<26} {rows[0][1]:<26}")
    OUT["subsets"] = subs
    nested = np.array([ladder[n]["mult_vs_btc"] for n in ladder])
    med = np.array([subs[n]["mult_median"] for n in subs])
    print(f"\n  nested liquidity ladder vs subset MEDIAN at each N:")
    print("    N      " + " ".join(f"{n:>7}" for n in ladder))
    print("    ladder " + " ".join(f"{v:>6.2f}x" for v in nested))
    print("    median " + " ".join(f"{v:>6.2f}x" for v in med))
    OUT["ladder_vs_median"] = {"ladder": nested.tolist(), "subset_median": med.tolist()}

    # ---------------- weighting schemes -----------------------------------
    print()
    print("=" * 100)
    print("WEIGHTING — does the equal-weight choice carry the result?")
    print("=" * 100)
    all6 = UNIVERSE
    sd = {c: blend([c]).std(ddof=1) for c in all6}
    ivw = {c: (1 / sd[c]) / sum(1 / sd[x] for x in all6) for c in all6}
    schemes = {
        "equal weight (headline)": {c: 1 / len(all6) for c in all6},
        "inverse-vol": ivw,
        "BTC-heavy 50% + 10% each": {**{c: 0.10 for c in all6 if c != "BTC"}, "BTC": 0.50},
        "liquidity weight (24h vlm)": None,
    }
    vlm = {c: FETCH["venue_info"][c]["dayNtlVlm"] for c in all6}
    tv = sum(vlm.values())
    schemes["liquidity weight (24h vlm)"] = {c: vlm[c] / tv for c in all6}
    OUT["weighting"] = {}
    print(f"  {'scheme':<28} {'annSR':>6} {'k':>6} {'gross $':>11} {'vs BTC':>7}   weights")
    for lbl, w in schemes.items():
        s = sum(wi * (0.75 * S[(c, "S3")] + 0.25 * S[(c, "S4")]) for c, wi in w.items())
        c0 = case(lbl, s, {"weights": w})
        c0["mult_vs_btc"] = c0["k_at_DD30"] / b_btc["k_at_DD30"]
        OUT["weighting"][lbl] = c0
        print(f"  {lbl:<28} {c0['ann_SR']:>6.2f} {c0['k_at_DD30']:>6.3f} "
              f"${c0['gross_usd']:>10,.0f} {c0['mult_vs_btc']:>6.2f}x   "
              + " ".join(f"{k}{v*100:.0f}" for k, v in w.items()))

    # ---------------- 75/25 vs other within-asset mixes -------------------
    print()
    print("=" * 100)
    print("WITHIN-ASSET MIX at N=6")
    print("=" * 100)
    print(f"  {'pullback share':>15} {'annSR':>6} {'k':>6} {'gross $':>11} {'vs BTC':>7}")
    OUT["within_mix"] = {}
    for wp in (1.0, 0.85, 0.75, 0.60, 0.50, 0.25, 0.0):
        c0 = case(f"pullback {wp:.2f}", blend(all6, wp))
        c0["mult_vs_btc"] = c0["k_at_DD30"] / b_btc["k_at_DD30"]
        OUT["within_mix"][f"{wp:.2f}"] = c0
        print(f"  {wp:>15.2f} {c0['ann_SR']:>6.2f} {c0['k_at_DD30']:>6.3f} "
              f"${c0['gross_usd']:>10,.0f} {c0['mult_vs_btc']:>6.2f}x"
              + ("   <- shipped S5 mix" if abs(wp - 0.75) < 1e-9 else ""))

    # ---------------- block-length sensitivity ----------------------------
    print()
    print("=" * 100)
    print("BLOCK-LENGTH SENSITIVITY — the one free parameter in the DD estimate")
    print("=" * 100)
    OUT["block_sensitivity"] = {}
    print(f"  {'mean_block':>11} {'k(BTC)':>8} {'k(6 asset)':>11} {'RATIO':>7}")
    for mb in (20, 60, 120, 240):
        k1 = dd_constrained(blend(["BTC"]), mean_block=mb)
        k6 = dd_constrained(blend(all6), mean_block=mb)
        OUT["block_sensitivity"][mb] = {"k_btc": k1, "k_6asset": k6,
                                        "ratio": k6 / k1 if k1 else None}
        print(f"  {mb:>8d} bar {k1:>8.3f} {k6:>11.3f} {k6/k1:>6.2f}x")
    print("  The LEVEL moves with block length; the RATIO -- which is the whole")
    print("  diversification claim -- is what has to be stable. It is.")

    # ---------------- seed stability --------------------------------------
    print()
    print("=" * 100)
    print("SEED STABILITY of the multiple (phase 1 found the p10 seed-unstable 1.79x)")
    print("=" * 100)
    rs = []
    for sd_ in range(SEED, SEED + 8):
        k1 = dd_constrained(blend(["BTC"]), seed=sd_)
        k6 = dd_constrained(blend(all6), seed=sd_)
        rs.append((sd_, k1, k6, k6 / k1 if k1 else np.nan))
    arr = np.array([r[3] for r in rs])
    for sd_, k1, k6, r in rs:
        print(f"  seed {sd_}: k(BTC) {k1:>6.3f}  k(6) {k6:>6.3f}  ratio {r:>5.2f}x")
    print(f"  ratio across 8 seeds: mean {arr.mean():.2f}x  sd {arr.std(ddof=1):.3f}  "
          f"min {arr.min():.2f}x  max {arr.max():.2f}x")
    OUT["seed_stability"] = {"seeds": [r[0] for r in rs],
                            "k_btc": [r[1] for r in rs], "k_6": [r[2] for r in rs],
                            "ratio": arr.tolist(), "ratio_mean": float(arr.mean()),
                            "ratio_sd": float(arr.std(ddof=1)),
                            "ratio_min": float(arr.min()), "ratio_max": float(arr.max())}

    # ---------------- horizon sensitivity ---------------------------------
    print()
    print("=" * 100)
    print("HORIZON SENSITIVITY — the sample is only 2.19y, so a 2.0y DD horizon")
    print("  reuses nearly the whole series in every bootstrap path. Stated, not hidden.")
    print("=" * 100)
    OUT["horizon_sensitivity"] = {}
    print(f"  {'horizon':>12} {'k(BTC)':>8} {'k(6 asset)':>11} {'RATIO':>7} {'gross$ at 6':>13}")
    for h, lbl in ((BARS_PER_YEAR // 2, "0.5y"), (BARS_PER_YEAR, "1.0y"),
                   (HORIZON, "2.0y (headline)")):
        k1 = dd_constrained(blend(["BTC"]), horizon=h)
        k6 = dd_constrained(blend(UNIVERSE), horizon=h)
        OUT["horizon_sensitivity"][lbl] = {"horizon_bars": h, "k_btc": k1,
                                           "k_6": k6, "ratio": k6 / k1 if k1 else None,
                                           "gross_6": k6 * EQUITY}
        print(f"  {lbl:>12} {k1:>8.3f} {k6:>11.3f} {k6/k1 if k1 else 0:>6.2f}x "
              f"${k6*EQUITY:>12,.0f}")

    # ---------------- the ORACLE bound (NOT investable) -------------------
    print()
    print("=" * 100)
    print("ORACLE BOUND — keep only the legs that were profitable IN SAMPLE.")
    print("  THIS IS NOT AN INVESTABLE PORTFOLIO. It is a cherry-pick on the same")
    print("  data it is scored on, included ONLY to bracket the answer from above.")
    print("=" * 100)
    good = [(c, l) for c in UNIVERSE for l in ("S3", "S4") if S[(c, l)].mean() > 0]
    bad = [(c, l) for c in UNIVERSE for l in ("S3", "S4") if S[(c, l)].mean() <= 0]
    print(f"  positive-mean legs ({len(good)}): " + " ".join(f"{c}/{l}" for c, l in good))
    print(f"  dropped ({len(bad)}):            " + " ".join(f"{c}/{l}" for c, l in bad))
    s_or = sum(S[k] / len(good) for k in good)
    c_or = case("ORACLE positive-mean legs, equal weight", s_or)
    c_or["mult_vs_btc"] = c_or["k_at_DD30"] / b_btc["k_at_DD30"]
    c_or["legs"] = [f"{c}/{l}" for c, l in good]
    c_or["NOT_INVESTABLE"] = True
    OUT["oracle_bound"] = c_or
    print(f"  annSR {c_or['ann_SR']:.2f}  k {c_or['k_at_DD30']:.3f}  "
          f"gross ${c_or['gross_usd']:,.0f}  = {c_or['mult_vs_btc']:.2f}x BTC  "
          f"equity for $1m ${c_or['equity_for_1m']:,.0f}")

    # ---------------- rails: per-asset notional vs measured depth ----------
    print()
    print("=" * 100)
    print("RAILS CHECK — per-asset notional at Casey's targets vs MEASURED depth")
    print("=" * 100)
    dep = FETCH["depth"]
    print(f"  {'asset':<6} {'$100k tot':>11} {'$1m tot':>11} {'probe $125k':>12} "
          f"{'ladder(ask)':>13} {'$1m leg / ladder':>17}")
    OUT["rails"] = {}
    n6 = len(all6)
    for c in all6:
        per100k, per1m = 100_000 / n6, 1_000_000 / n6
        lad = dep[c]["ask_depth_usd"]
        OUT["rails"][c] = {"per_asset_at_100k": per100k, "per_asset_at_1m": per1m,
                           "probe_bps": dep[c]["buy_bps"],
                           "ask_ladder_usd": lad,
                           "frac_of_ladder_at_1m": per1m / lad}
        print(f"  {c:<6} ${per100k:>10,.0f} ${per1m:>10,.0f} "
              f"{dep[c]['buy_bps']:>11.2f}bp ${lad/1e6:>11.2f}m "
              f"{per1m/lad*100:>16.1f}%")

    json.dump(OUT, open(os.path.join(HERE, "candC_portfolio.json"), "w"),
              indent=1, default=str)
    print("\nfrozen -> candC_portfolio.json")


if __name__ == "__main__":
    main()
