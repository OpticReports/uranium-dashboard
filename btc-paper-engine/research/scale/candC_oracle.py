"""CANDIDATE C, correction O: the oracle row in candC_portfolio.py is
CONFOUNDED and this file replaces it.

The bug (mine, caught before it was reported): the "keep only positive-mean
legs" portfolio weighted its 6 surviving legs at 1/6 = 0.167 each, while the
12-leg blend weights the donchian legs at 0.25/6 = 0.042. Three of the six
survivors are donchian legs with 57-67% annualised vol, so the oracle
accidentally TRIPLED the weight on the highest-vol legs in the book. Its lower
k was a weighting artefact, not a statement about leg selection.

This file re-runs selection at MATCHED risk weights (inverse-vol, so every leg
contributes equal variance) for: all 12 legs, the 6 in-sample winners, and the
6 in-sample losers. Now the only thing that differs is WHICH legs are held.

Run: python3 research/scale/candC_oracle.py
"""
from __future__ import annotations
import json, os, time

import numpy as np
from candC_lib import (EQUITY, HERE, ann_stats, boot_stats, dd_constrained)

Z = np.load(os.path.join(HERE, "candC_streams.npz"), allow_pickle=True)
UNIVERSE = [str(x) for x in Z["assets"]]
S = {(c, l): Z[f"{c}_{l}"] for c in UNIVERSE for l in ("S3", "S4")}
ALL = [(c, l) for c in UNIVERSE for l in ("S3", "S4")]


def wmix(legs, weights):
    return sum(w * S[k] for k, w in zip(legs, weights))


def invvol(legs):
    iv = np.array([1.0 / S[k].std(ddof=1) for k in legs])
    return iv / iv.sum()


def shipped(legs):
    """0.75/0.25 within asset, equal across the assets present."""
    coins = sorted({c for c, _ in legs})
    w = []
    for c, l in legs:
        w.append((0.75 if l == "S3" else 0.25) / len(coins))
    w = np.array(w)
    return w / w.sum()


def case(lbl, legs, w):
    s = wmix(legs, w)
    k = dd_constrained(s)
    p10, p50, pneg = boot_stats(s)
    return {"label": lbl, "n_legs": len(legs),
            "legs": [f"{c}/{l}" for c, l in legs],
            "weights": {f"{c}/{l}": float(x) for (c, l), x in zip(legs, w)},
            "k_at_DD30": k, "gross_usd": k * EQUITY,
            "equity_for_1m": 1_000_000 / k if k else None,
            "kstar_p10": p10, "prob_neg_edge": pneg, **ann_stats(s)}


def main():
    win = [k for k in ALL if S[k].mean() > 0]
    los = [k for k in ALL if S[k].mean() <= 0]
    base = case("BTC 75/25 (today), shipped weights",
                [("BTC", "S3"), ("BTC", "S4")], shipped([("BTC", "S3"), ("BTC", "S4")]))
    print("=" * 100)
    print("MATCHED-RISK LEG SELECTION — does dropping the losing legs help?")
    print("=" * 100)
    print(f"  in-sample WINNERS ({len(win)}): " + " ".join(f"{c}/{l}" for c, l in win))
    print(f"  in-sample LOSERS  ({len(los)}): " + " ".join(f"{c}/{l}" for c, l in los))
    rows = [base,
            case("all 12 legs, SHIPPED 75/25 weights (headline)", ALL, shipped(ALL)),
            case("all 12 legs, inverse-vol", ALL, invvol(ALL)),
            case("6 in-sample WINNERS, inverse-vol [ORACLE, not investable]", win, invvol(win)),
            case("6 in-sample LOSERS, inverse-vol [control]", los, invvol(los))]
    print()
    print(f"  {'portfolio':<58} {'annSR':>6} {'annSD':>7} {'k':>6} {'gross $':>10} {'vs BTC':>7}")
    for r in rows:
        r["mult_vs_btc"] = r["k_at_DD30"] / base["k_at_DD30"]
        print(f"  {r['label']:<58} {r['ann_SR']:>6.2f} {r['ann_sd_pct']:>6.1f}% "
              f"{r['k_at_DD30']:>6.3f} ${r['gross_usd']:>9,.0f} {r['mult_vs_btc']:>6.2f}x")
    ship = rows[1]
    orac = rows[3]
    print()
    print(f"  ORACLE vs the investable headline: {orac['k_at_DD30']/ship['k_at_DD30']:.2f}x")
    print("  Read this as the CEILING that perfect in-sample leg selection would")
    print("  buy on top of holding everything. It is not available out of sample.")
    print(f"  The LOSERS-only control still sizes to k={rows[4]['k_at_DD30']:.3f} "
          f"({rows[4]['mult_vs_btc']:.2f}x BTC) — which is the diversifier argument:")
    print("  legs with no standalone edge are not worthless in a portfolio, they are")
    print("  just not worth much.")
    json.dump({"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "winners": [f"{c}/{l}" for c, l in win],
               "losers": [f"{c}/{l}" for c, l in los],
               "rows": rows,
               "oracle_over_headline": orac["k_at_DD30"] / ship["k_at_DD30"]},
              open(os.path.join(HERE, "candC_oracle.json"), "w"), indent=1, default=str)
    print("\nfrozen -> candC_oracle.json")


if __name__ == "__main__":
    main()
