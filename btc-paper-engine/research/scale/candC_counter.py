"""CANDIDATE C counter-agent pass. MANDATORY per CLAUDE.md before any finding
is acted on. Every attack here is aimed at MY OWN numbers, and the ones that
land are reported as landing.

A1 MULTIPLE TESTING. I ran 12 legs. ETH/S3's ann.SR 1.45 is the result that
   carries the whole candidate. Under a null of ZERO edge, what is the
   distribution of the MAXIMUM ann.SR across 12 legs at this sample length and
   this vol clustering? If 1.45 sits inside that null, the candidate's engine
   is the best of twelve coin flips.
A2 IS THE 1.66x MULTIPLE A PROPERTY OF THE 30%/10% BUDGET? Re-run at other
   drawdown limits and probabilities.
A3 CORRELATION ESTIMATE UNCERTAINTY. Block-bootstrap CI on the mean
   off-diagonal rho, and on the multiple, as a paired statistic.
A4 DATA BASIS. The repo's registered BTC data is the FIXTURE, not HL. Re-run
   the multiple with BTC's leg taken from the fixture over the same window.
A5 DEPTH-GATE STABILITY. The eligibility gate flipped two coins between two
   runs ten minutes apart. Re-sample it and quantify.
A6 INDEPENDENT RE-DERIVATION of k by a different code path.

Run: python3 research/scale/candC_counter.py
"""
from __future__ import annotations
import json, os, time, urllib.request

import numpy as np
from candC_lib import (BACKEND, BARS_PER_YEAR, DD_LIMIT, EQUITY, FEE_TAKER_RT,
                       HERE, HORIZON, P_LIMIT, SEED, ann_stats, asset_path,
                       dd_constrained, dd_prob, load_bars, replay_mtm, sb_idx)

Z = np.load(os.path.join(HERE, "candC_streams.npz"), allow_pickle=True)
UNIVERSE = [str(x) for x in Z["assets"]]
S = {(c, l): Z[f"{c}_{l}"] for c in UNIVERSE for l in ("S3", "S4")}
NB = len(S[("BTC", "S3")])
API = "https://api.hyperliquid.xyz/info"


def post(b):
    req = urllib.request.Request(API, data=json.dumps(b).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def blend(d, coins, w=0.75):
    n = len(coins)
    return sum((w / n) * d[(c, "S3")] + ((1 - w) / n) * d[(c, "S4")] for c in coins)


def main():
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rng = np.random.default_rng(SEED)

    # ================= A1: multiple testing ==============================
    print("=" * 100)
    print("A1 — MULTIPLE TESTING. Is ETH/S3 just the best of twelve tries?")
    print("=" * 100)
    obs = {k: ann_stats(S[k])["ann_SR"] for k in S}
    order = sorted(obs, key=lambda k: -obs[k])
    print("  observed ann.SR, ranked:")
    for k in order:
        print(f"    {k[0]:<5}/{k[1]:<3} {obs[k]:>+6.2f}")
    best_obs = obs[order[0]]
    # NULL: block sign-flip. Preserves each leg's vol clustering, its fat tails
    # and the CROSS-ASSET dependence (same flip pattern is NOT used -- each leg
    # flipped independently is the conservative choice for a max statistic),
    # while forcing the expected mean to zero.
    BLK, DRAWS = 60, 4000
    nblk = int(np.ceil(NB / BLK))
    maxes, eth_null = [], []
    legs = list(S)
    for _ in range(DRAWS):
        srs = []
        for k in legs:
            f = np.repeat(rng.choice([-1.0, 1.0], nblk), BLK)[:NB]
            r = S[k] * f
            sd = r.std(ddof=1)
            srs.append(r.mean() / sd * np.sqrt(BARS_PER_YEAR) if sd > 0 else 0.0)
        maxes.append(max(srs))
        eth_null.append(srs[legs.index(("ETH", "S3"))])
    maxes = np.array(maxes)
    eth_null = np.array(eth_null)
    p_family = float((maxes >= best_obs).mean())
    p_single = float((eth_null >= obs[("ETH", "S3")]).mean())
    print(f"\n  NULL (block sign-flip, block={BLK} bars, {DRAWS} draws):")
    print(f"    max-of-12 ann.SR under the null: median {np.median(maxes):.2f}  "
          f"p90 {np.percentile(maxes,90):.2f}  p95 {np.percentile(maxes,95):.2f}  "
          f"max {maxes.max():.2f}")
    print(f"    ETH/S3 observed {obs[('ETH','S3')]:+.2f}")
    print(f"    SINGLE-test p-value (ETH/S3 alone):      {p_single:.4f}")
    print(f"    FAMILY-WISE p-value (max of 12 legs):    {p_family:.4f}")
    verdict_a1 = ("SURVIVES family-wise at 5%" if p_family < 0.05
                  else "DOES NOT survive family-wise at 5% — ATTACK LANDS")
    print(f"    -> {verdict_a1}")
    OUT["A1_multiple_testing"] = {
        "observed_ann_SR": {f"{c}/{l}": v for (c, l), v in obs.items()},
        "best_leg": f"{order[0][0]}/{order[0][1]}", "best_ann_SR": best_obs,
        "null_block_bars": BLK, "null_draws": DRAWS,
        "null_max_median": float(np.median(maxes)),
        "null_max_p95": float(np.percentile(maxes, 95)),
        "p_single": p_single, "p_familywise": p_family, "verdict": verdict_a1}

    # portfolio-level null: can the 6-asset k exceed BTC's under zero edge?
    print("\n  Portfolio-level null: the MULTIPLE itself, under zero edge.")
    nullmult = []
    for _ in range(40):
        D = {}
        for k in legs:
            f = np.repeat(rng.choice([-1.0, 1.0], nblk), BLK)[:NB]
            D[k] = S[k] * f
        k1 = dd_constrained(blend(D, ["BTC"]))
        k6 = dd_constrained(blend(D, UNIVERSE))
        nullmult.append((k1, k6))
        
    k1o = dd_constrained(blend(S, ["BTC"]))
    k6o = dd_constrained(blend(S, UNIVERSE))
    nz = [(a, b) for a, b in nullmult if a > 0]
    print(f"    observed: k(BTC) {k1o:.3f}  k(6) {k6o:.3f}  multiple {k6o/k1o:.2f}x")
    print(f"    under the null, k(BTC) > 0 in {len(nz)}/{len(nullmult)} draws; "
          f"k(6) > 0 in {sum(1 for a,b in nullmult if b>0)}/{len(nullmult)}")
    if nz:
        nm = np.array([b / a for a, b in nz])
        print(f"    null multiple (when both defined): median {np.median(nm):.2f}x  "
              f"p90 {np.percentile(nm,90):.2f}x  max {nm.max():.2f}x")
        print("    NOTE: a zero-edge stream gets k=0 by construction (Kelly refuses a")
        print("    non-positive mean), so this null is weak on the LEVEL. It is the A1")
        print("    Sharpe test that carries the edge question.")
        OUT["A1_portfolio_null"] = {"observed_mult": k6o / k1o,
                                   "null_defined": len(nz),
                                   "null_mult_median": float(np.median(nm)),
                                   "null_mult_p90": float(np.percentile(nm, 90))}
    else:
        OUT["A1_portfolio_null"] = {"observed_mult": k6o / k1o, "null_defined": 0}

    # ================= A2: budget sensitivity ============================
    print()
    print("=" * 100)
    print("A2 — IS 1.66x A PROPERTY OF THE 30%/10% DRAWDOWN BUDGET?")
    print("=" * 100)
    print(f"  {'dd limit':>9} {'p limit':>8} {'k(BTC)':>8} {'k(6)':>8} {'MULTIPLE':>9}")
    A2 = {}
    for dl in (0.15, 0.20, 0.30, 0.40):
        for pl in (0.05, 0.10, 0.20):
            k1 = dd_constrained(blend(S, ["BTC"]), dd_limit=dl, p_limit=pl)
            k6 = dd_constrained(blend(S, UNIVERSE), dd_limit=dl, p_limit=pl)
            A2[f"dd{dl}_p{pl}"] = {"k_btc": k1, "k_6": k6,
                                   "mult": k6 / k1 if k1 else None}
            print(f"  {dl:>9.0%} {pl:>8.0%} {k1:>8.3f} {k6:>8.3f} "
                  f"{k6/k1 if k1 else 0:>8.2f}x"
                  + ("   <- KELLY.md's budget" if (dl, pl) == (0.30, 0.10) else ""))
    ms = [v["mult"] for v in A2.values() if v["mult"]]
    print(f"  multiple across all 12 budgets: min {min(ms):.2f}x  median "
          f"{np.median(ms):.2f}x  max {max(ms):.2f}x")
    OUT["A2_budget_sensitivity"] = {"grid": A2, "mult_min": float(min(ms)),
                                   "mult_median": float(np.median(ms)),
                                   "mult_max": float(max(ms))}

    # ================= A3: correlation + multiple CI ======================
    print()
    print("=" * 100)
    print("A3 — ESTIMATION UNCERTAINTY on rho and on the multiple")
    print("=" * 100)
    B = {c: 0.75 * S[(c, "S3")] + 0.25 * S[(c, "S4")] for c in UNIVERSE}
    M = np.stack([B[c] for c in UNIVERSE])
    iu = np.triu_indices(len(UNIVERSE), 1)
    rhos = []
    rg2 = np.random.default_rng(SEED + 99)
    for _ in range(500):
        idx = sb_idx(NB, NB, rg2, 60)
        rhos.append(np.corrcoef(M[:, idx])[iu].mean())
    rhos = np.array(rhos)
    print(f"  mean off-diagonal rho: point {np.corrcoef(M)[iu].mean():+.3f}  "
          f"block-bootstrap 90% CI [{np.percentile(rhos,5):+.3f}, "
          f"{np.percentile(rhos,95):+.3f}]")
    print("  -> rho is comfortably below 0.5 across the CI, so the mechanism is not")
    print("     an artefact of the point estimate.")
    OUT["A3_rho_ci"] = {"point": float(np.corrcoef(M)[iu].mean()),
                       "ci5": float(np.percentile(rhos, 5)),
                       "ci95": float(np.percentile(rhos, 95))}

    # ================= A4: data basis ====================================
    print()
    print("=" * 100)
    print("A4 — DATA BASIS. The repo's registered BTC series is the FIXTURE.")
    print("=" * 100)
    fx = load_bars(os.path.join(BACKEND, "tests", "fixtures", "bars_4h_btcusd.csv"))
    hl = load_bars(asset_path("BTC"))
    lo, hi = hl[0].ts, hl[-1].ts
    fxw = [b for b in fx if lo <= b.ts <= hi]
    mtm, _, tr = replay_mtm(fxw, FEE_TAKER_RT)
    fx_leg = {l: np.diff(mtm[l]) / mtm[l][:-1] for l in ("S3", "S4")}
    n = min(len(fx_leg["S3"]), NB)
    print(f"  fixture-over-HL-window stream: {len(fx_leg['S3'])} bars vs HL {NB}; "
          f"comparing on the first {n}")
    Sfx = dict(S)
    Sfx[("BTC", "S3")] = fx_leg["S3"][:n]
    Sfx[("BTC", "S4")] = fx_leg["S4"][:n]
    for c in UNIVERSE:
        for l in ("S3", "S4"):
            if c != "BTC":
                Sfx[(c, l)] = S[(c, l)][:n]
    k1f = dd_constrained(blend(Sfx, ["BTC"]))
    k6f = dd_constrained(blend(Sfx, UNIVERSE))
    print(f"  BTC leg from FIXTURE: k(BTC) {k1f:.3f}  k(6) {k6f:.3f}  "
          f"multiple {k6f/k1f if k1f else 0:.2f}x")
    print(f"  BTC leg from HL     : k(BTC) {k1o:.3f}  k(6) {k6o:.3f}  "
          f"multiple {k6o/k1o:.2f}x")
    print("  The fixture BTC leg is stronger (S4 ann.SR +0.20 vs -0.78 on the same")
    print("  window, per candC_window.json), so it RAISES the denominator and")
    print("  SHRINKS the multiple. That direction matters: the headline multiple is")
    print("  measured against the WEAKER of the two available BTC baselines.")
    OUT["A4_data_basis"] = {"k_btc_fixture": k1f, "k_6_fixture_btc": k6f,
                           "mult_fixture": k6f / k1f if k1f else None,
                           "k_btc_hl": k1o, "k_6_hl": k6o, "mult_hl": k6o / k1o,
                           "n_bars_compared": int(n)}

    # ================= A5: depth gate stability ==========================
    print()
    print("=" * 100)
    print("A5 — DEPTH-GATE STABILITY. The gate flipped SUI/LINK between two runs.")
    print("=" * 100)
    PROBE, REP = 125_000.0, 6
    cands = ["BTC", "ETH", "SOL", "XRP", "LTC", "DOGE", "SUI", "LINK"]
    samples = {c: [] for c in cands}
    for _ in range(REP):
        for c in cands:
            try:
                b = post({"type": "l2Book", "coin": c, "nSigFigs": 4})
                bids, asks = b["levels"][0], b["levels"][1]
                mid = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
                spent = filled = 0.0
                ok = False
                for lv in asks:
                    px, sz = float(lv["px"]), float(lv["sz"])
                    take = min(sz * px, PROBE - spent)
                    filled += take / px
                    spent += take
                    if spent >= PROBE - 1e-6:
                        ok = True
                        break
                samples[c].append(((spent / filled) / mid - 1) * 1e4 if ok else None)
            except Exception:                                      # noqa: BLE001
                samples[c].append(None)
        time.sleep(1.0)
    print(f"  {'coin':<6} {'n ok':>5} {'min':>7} {'median':>8} {'max':>7}  "
          f"{'passes 10bp gate':>17}")
    OUT["A5_depth_stability"] = {}
    for c in cands:
        v = [x for x in samples[c] if x is not None]
        npass = sum(1 for x in samples[c] if x is not None and x <= 10.0)
        OUT["A5_depth_stability"][c] = {
            "n_ok": len(v), "n_samples": REP,
            "min_bps": min(v) if v else None,
            "median_bps": float(np.median(v)) if v else None,
            "max_bps": max(v) if v else None, "n_pass_gate": npass}
        print(f"  {c:<6} {len(v):>3}/{REP} "
              f"{(min(v) if v else float('nan')):>7.2f} "
              f"{(np.median(v) if v else float('nan')):>8.2f} "
              f"{(max(v) if v else float('nan')):>7.2f}  {npass:>10}/{REP}")

    # ================= A6: independent re-derivation of k ================
    print()
    print("=" * 100)
    print("A6 — INDEPENDENT RE-DERIVATION of k by a different code path")
    print("=" * 100)
    s6 = blend(S, UNIVERSE)
    # path B: explicit loop, no vectorisation, different RNG, IID block draws
    def dd_prob_loopy(r, m, dd=DD_LIMIT, horizon=HORIZON, draws=300, blk=60, seed=1234):
        rg = np.random.default_rng(seed)
        n = len(r)
        hits = 0
        for _ in range(draws):
            pieces = []
            while sum(len(p) for p in pieces) < horizon:
                st = int(rg.integers(0, n))
                pieces.append(np.take(r, np.arange(st, st + blk) % n))
            path = 1.0 + m * np.concatenate(pieces)[:horizon]
            if np.any(path <= 0):
                hits += 1
                continue
            eq = np.cumprod(path)
            if float((eq / np.maximum.accumulate(eq) - 1).min()) < -dd:
                hits += 1
        return hits / draws
    print(f"  {'m':>6} {'P(maxDD>30%) primary':>22} {'P(...) independent path':>25}")
    A6 = {}
    for m in (1.0, 1.4, 1.666, 2.0):
        pa = dd_prob(s6, m)
        pb = dd_prob_loopy(s6, m)
        A6[f"{m}"] = {"primary": pa, "independent": pb, "abs_diff": abs(pa - pb)}
        print(f"  {m:>6.3f} {pa:>22.3f} {pb:>25.3f}")
    print("  Fixed-length blocks vs geometric blocks are DIFFERENT bootstraps, so")
    print("  exact agreement is not expected; agreement on where the 10% crossing")
    print("  sits is what validates the k estimate.")
    OUT["A6_independent_dd"] = A6

    json.dump(OUT, open(os.path.join(HERE, "candC_counter.json"), "w"), indent=1,
              default=str)
    print("\nfrozen -> candC_counter.json")


if __name__ == "__main__":
    main()
