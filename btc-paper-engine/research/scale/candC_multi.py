"""CANDIDATE C, step 2: run the SHIPPED engine, UNCHANGED, on every eligible
asset. Measure per-asset edge and the real cross-asset correlation matrix.

WHAT IS AND IS NOT OUT OF SAMPLE HERE — read this before the numbers:
  The strategy parameters (SMA 50/200, RSI 45/55, depth 0.5 ATR, stop 2.5 ATR,
  Donchian 20, chandelier 5.0 ATR, time stop 60 bars) were selected on BTC.
  Applying them UNCHANGED to ETH/SOL/XRP/LTC/DOGE is out of sample in the
  ASSET dimension: nothing was fitted on those five. It is NOT out of sample
  in the calendar dimension -- the 2024-06 -> 2026-09 window overlaps the BTC
  selection sample. So: five genuinely unfitted assets, one fitted one (BTC),
  same window. The BTC column is the in-sample control and is labelled as such
  everywhere.

Run: python3 research/scale/candC_multi.py
"""
from __future__ import annotations
import json, os, time

import numpy as np
from candC_lib import (BARS_PER_YEAR, FEE_ENGINE_RT, FEE_MAKER_RT, FEE_TAKER_RT,
                       HERE, ann_stats, asset_path, boot_stats, load_bars,
                       replay_mtm, sb_idx, SEED)
from app.engine.kelly import analyze as kelly_analyze
from app.engine.kelly import stationary_bootstrap_idx as _REF

FETCH = json.load(open(os.path.join(HERE, "candC_fetch.json")))
UNIVERSE = FETCH["eligible"]
LEGS = ("S3", "S4")          # pullback, donchian -- the two shipped legs


def main():
    print("=" * 96)
    print("BOOTSTRAP RE-VALIDATION — the vectorised copy vs app.engine.kelly's own")
    print("=" * 96)
    rg = np.random.default_rng(7)
    a = np.stack([_REF(400, rg, 10) for _ in range(400)])
    rg = np.random.default_rng(7)
    b = np.stack([sb_idx(400, 400, rg, 10) for _ in range(400)])
    v = {"ref_contig": float(np.mean(np.diff(a, axis=1) == 1)),
         "mine_contig": float(np.mean(np.diff(b, axis=1) == 1)),
         "target": 0.9}
    print(f"  P(idx[i+1]==idx[i]+1): ref {v['ref_contig']:.4f}  mine "
          f"{v['mine_contig']:.4f}  target {v['target']:.4f}")
    assert abs(v["mine_contig"] - 0.9) < 0.01, "bootstrap law drifted"

    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "universe": UNIVERSE, "bootstrap_validation": v,
           "fee_primary_rt_bps": FEE_TAKER_RT, "assets": {}, "fee_sensitivity": {}}

    # ---------------- per-asset replay at the primary fee ------------------
    print()
    print("=" * 96)
    print(f"PER-ASSET REPLAY — shipped engine, zero per-asset fitting, "
          f"{FEE_TAKER_RT} bp round trip (measured, all-taker = today)")
    print("=" * 96)
    streams, pos, trades, closes = {}, {}, {}, {}
    n_bars = None
    for coin in UNIVERSE:
        bars = load_bars(asset_path(coin))
        mtm, inpos, tr = replay_mtm(bars, FEE_TAKER_RT)
        for leg in LEGS:
            r = np.diff(mtm[leg]) / mtm[leg][:-1]
            streams[(coin, leg)] = r
            pos[(coin, leg)] = inpos[leg][1:]
            trades[(coin, leg)] = tr[leg]
        closes[coin] = np.array([b.close for b in bars])
        if n_bars is None:
            n_bars = len(streams[(coin, "S3")])
        assert len(streams[(coin, "S3")]) == n_bars, f"{coin} grid mismatch"
    print(f"  common stream length: {n_bars} bars "
          f"({n_bars / BARS_PER_YEAR:.2f} years), identical for every asset")
    print()
    print(f"  {'asset':<6} {'leg':<4} {'trades':>7} {'win%':>6} {'inMkt':>6} "
          f"{'mean bp':>8} {'annSD':>7} {'annSR':>6} {'k*p10':>7} {'P(neg)':>7}  verdict")
    for coin in UNIVERSE:
        for leg in LEGS:
            r = streams[(coin, leg)]
            st = ann_stats(r)
            tr = trades[(coin, leg)]
            wins = sum(1 for t in tr if t.pnl_usd > 0)
            p10, p50, pneg = boot_stats(r)
            tag = ("IN-SAMPLE (fitted)" if coin == "BTC" else "unfitted")
            OUT["assets"].setdefault(coin, {})[leg] = {
                **st, "n_trades": len(tr),
                "win_rate_pct": 100 * wins / len(tr) if tr else None,
                "in_market_frac": float(pos[(coin, leg)].mean()),
                "kstar_p10": p10, "kstar_p50": p50, "prob_neg_edge": pneg,
                "basis": tag}
            print(f"  {coin:<6} {leg:<4} {len(tr):>7} "
                  f"{100*wins/len(tr) if tr else 0:>5.1f}% "
                  f"{pos[(coin,leg)].mean()*100:>5.1f}% {st['mean_bp_bar']:>+8.2f} "
                  f"{st['ann_sd_pct']:>6.1f}% {st['ann_SR']:>6.2f} {p10:>7.3f} "
                  f"{pneg:>7.3f}  {tag}")

    # buy-and-hold per asset, for context on what the strategy is fighting
    print()
    print("  Buy-and-hold over the same window, for context:")
    for coin in UNIVERSE:
        c = closes[coin]
        tot = c[-1] / c[0] - 1
        pk = np.maximum.accumulate(c)
        OUT["assets"][coin]["hold"] = {
            "total_return_pct": float(100 * tot),
            "max_dd_pct": float(100 * (c / pk - 1).min())}
        print(f"    {coin:<6} total {100*tot:>+8.1f}%   maxDD "
              f"{100*(c/pk-1).min():>7.1f}%")

    # ---------------- the shipped 75/25 blend, per asset -------------------
    print()
    print("=" * 96)
    print("PER-ASSET S5 BLEND (75% pullback / 25% trend — the shipped mix)")
    print("=" * 96)
    blends = {c: 0.75 * streams[(c, "S3")] + 0.25 * streams[(c, "S4")]
              for c in UNIVERSE}
    print(f"  {'asset':<6} {'mean bp':>8} {'annSD':>7} {'annSR':>6} {'k*p10':>7} "
          f"{'P(neg)':>7}  {'kelly.analyze recommended_m':<30}")
    for coin in UNIVERSE:
        r = blends[coin]
        st = ann_stats(r)
        p10, p50, pneg = boot_stats(r)
        # the SHIPPED instrument, on the trade-close blend proxy (per-bar
        # stream fed in; label says exactly what it was fed)
        ka = kelly_analyze(list(r), f"{coin} S5 per-bar")
        OUT["assets"][coin]["blend"] = {
            **st, "kstar_p10": p10, "kstar_p50": p50, "prob_neg_edge": pneg,
            "kelly_analyze": {k: ka.get(k) for k in
                              ("n", "mean_pct", "kelly_m", "recommended_m",
                               "bootstrap", "verdict")}}
        print(f"  {coin:<6} {st['mean_bp_bar']:>+8.2f} {st['ann_sd_pct']:>6.1f}% "
              f"{st['ann_SR']:>6.2f} {p10:>7.3f} {pneg:>7.3f}  "
              f"{ka.get('recommended_m')}  {ka.get('verdict','')[:46]}")

    # ---------------- THE CORRELATION MATRIX -------------------------------
    print()
    print("=" * 96)
    print("MEASURED CROSS-ASSET CORRELATION of the S5 BLEND streams")
    print("  (per-bar MTM, flat bars = 0 — the portfolio-correct view)")
    print("=" * 96)
    M = np.stack([blends[c] for c in UNIVERSE])
    C = np.corrcoef(M)
    hdr = "        " + " ".join(f"{c:>7}" for c in UNIVERSE)
    print(hdr)
    for i, c in enumerate(UNIVERSE):
        print(f"  {c:<6}" + " ".join(f"{C[i, j]:>+7.3f}" for j in range(len(UNIVERSE))))
    off = C[np.triu_indices(len(UNIVERSE), 1)]
    print(f"\n  off-diagonal: mean {off.mean():+.3f}  median {np.median(off):+.3f}  "
          f"min {off.min():+.3f}  max {off.max():+.3f}   (n={len(off)} pairs)")
    OUT["correlation"] = {"assets": UNIVERSE, "matrix": C.tolist(),
                          "offdiag_mean": float(off.mean()),
                          "offdiag_median": float(np.median(off)),
                          "offdiag_min": float(off.min()),
                          "offdiag_max": float(off.max())}

    # price correlation, for the contrast that makes the point
    P = np.stack([np.diff(np.log(closes[c])) for c in UNIVERSE])
    CP = np.corrcoef(P)
    offp = CP[np.triu_indices(len(UNIVERSE), 1)]
    print(f"  UNDERLYING 4h log-return correlation for contrast: mean "
          f"{offp.mean():+.3f}  min {offp.min():+.3f}  max {offp.max():+.3f}")
    print("  -> the STRATEGY streams decorrelate far below the PRICES, because each")
    print("     asset's signal is in the market at different times and on different")
    print("     sides. That gap IS the diversification this candidate is selling.")
    OUT["price_correlation"] = {"matrix": CP.tolist(),
                               "offdiag_mean": float(offp.mean()),
                               "offdiag_min": float(offp.min()),
                               "offdiag_max": float(offp.max())}

    inm = np.stack([(pos[(c, "S3")] | pos[(c, "S4")]) for c in UNIVERSE])
    print(f"\n  in-market overlap: mean legs live simultaneously "
          f"{inm.sum(axis=0).mean():.2f} of {len(UNIVERSE)}")
    OUT["simultaneity"] = {"mean_assets_in_market": float(inm.sum(axis=0).mean()),
                           "n_assets": len(UNIVERSE)}

    # ---------------- fee sensitivity -------------------------------------
    print()
    print("=" * 96)
    print("FEE SENSITIVITY — the dimension phase 1 showed swings authorised size 5x")
    print("=" * 96)
    print(f"  {'fee rt':>7}  " + " ".join(f"{c:>8}" for c in UNIVERSE) + "   (S5 blend ann.SR)")
    for rt, lbl in ((FEE_MAKER_RT, "maker-fix"), (FEE_TAKER_RT, "TODAY"),
                    (FEE_ENGINE_RT, "engine obj")):
        row, srs = {}, []
        for coin in UNIVERSE:
            mtm, _, _ = replay_mtm(load_bars(asset_path(coin)), rt)
            r = 0.75 * (np.diff(mtm["S3"]) / mtm["S3"][:-1]) + \
                0.25 * (np.diff(mtm["S4"]) / mtm["S4"][:-1])
            s = ann_stats(r)
            row[coin] = {**s, "stream": None}
            srs.append(s["ann_SR"])
        OUT["fee_sensitivity"][f"{rt:.2f}"] = {"label": lbl,
                                               "per_asset": {k: {kk: vv for kk, vv in v.items() if kk != "stream"}
                                                             for k, v in row.items()}}
        print(f"  {rt:>7.2f}  " + " ".join(f"{row[c]['ann_SR']:>8.2f}" for c in UNIVERSE)
              + f"   <- {lbl}")

    np.savez_compressed(os.path.join(HERE, "candC_streams.npz"),
                        assets=np.array(UNIVERSE),
                        **{f"{c}_{l}": streams[(c, l)] for c in UNIVERSE for l in LEGS},
                        **{f"{c}_pos_{l}": pos[(c, l)] for c in UNIVERSE for l in LEGS},
                        **{f"{c}_close": closes[c] for c in UNIVERSE})
    json.dump(OUT, open(os.path.join(HERE, "candC_multi.json"), "w"), indent=1,
              default=str)
    print(f"\nfrozen -> candC_multi.json + candC_streams.npz")


if __name__ == "__main__":
    main()
