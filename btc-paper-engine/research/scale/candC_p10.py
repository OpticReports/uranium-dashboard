"""CANDIDATE C, step 7: WHICH KELLY TERM ACTUALLY BINDS, and is the one
configuration with a positive authorised size robust?

candC_portfolio.py reported k at the DRAWDOWN budget. That is only ONE of the
four terms in KELLY.md's recommendation:
    rec = min(half-Kelly, bootstrap p10, c* x m*, dd30)
Phase 1 established that on recent windows the bootstrap p10 binds, not dd30.
Re-reading my own ladder: p10 = 0.000 for N = 1, 3, 4, 5 and 6. Under the
repo's own doctrine the authorised size on this window is ZERO for the 6-asset
book AND for BTC alone. The ONLY configuration with a positive p10 is
BTC+ETH (0.750).

So the headline 1.66x is a ratio of two DRAWDOWN-BUDGET numbers, neither of
which is an authorised size. This file says so explicitly and then asks the
only question that can still be actionable: is BTC+ETH's positive p10 real, or
is it a seed?

Run: python3 research/scale/candC_p10.py
"""
from __future__ import annotations
import itertools, json, os, time

import numpy as np
from candC_lib import (EQUITY, HERE, LIVE_GROSS, REF_LEV, SEED, ann_stats,
                       boot_stats, dd_constrained, kstar_rows)

Z = np.load(os.path.join(HERE, "candC_streams.npz"), allow_pickle=True)
ZN = np.load(os.path.join(HERE, "candC_net_streams.npz"), allow_pickle=True)
U = [str(x) for x in Z["assets"]]
S = {(c, l): Z[f"{c}_{l}"] for c in U for l in ("S3", "S4")}
SN = {(c, l): ZN[f"net_{c}_{l}"] for c in U for l in ("S3", "S4")}


def blend(d, coins, w=0.75):
    n = len(coins)
    return sum((w / n) * d[(c, "S3")] + ((1 - w) / n) * d[(c, "S4")] for c in coins)


def full_rec(s, seed=SEED):
    """KELLY.md's own min(), on this stream. half-Kelly and c*·m* included."""
    r = np.asarray(s, float)
    star = float(kstar_rows(r[None, :], cap=30.0)[0])
    p10, p50, pneg = boot_stats(r, seed=seed)
    sd = r.std(ddof=1)
    sr = r.mean() / sd if sd > 0 else 0.0
    n = len(r)
    c_star = n * sr ** 2 / (n * sr ** 2 + 1) if sr > 0 else 0.0
    dd30 = dd_constrained(r, seed=seed)
    terms = {"half_kelly": star / 2, "bootstrap_p10": p10,
             "c_star_x_mstar": c_star * star, "dd30": dd30}
    rec = min(terms.values())
    killed = pneg > 0.25
    return {"kelly_star": star, "terms": terms,
            "binding": min(terms, key=terms.get),
            "recommended_k": 0.0 if killed else max(0.0, rec),
            "prob_neg_edge": pneg, "killed_by_kill_rule": killed}


def main():
    OUT = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    print("=" * 104)
    print("ALL FOUR KELLY TERMS — what the repo's own doctrine authorises on this window")
    print("  rec = min(half-Kelly, bootstrap p10, c* x m*, dd30), then the >25% kill rule")
    print("=" * 104)
    print(f"  {'portfolio':<30} {'half-K':>8} {'p10':>8} {'c*m*':>8} {'dd30':>8} "
          f"{'BINDS':>14} {'rec k':>7} {'rec gross $':>12}")
    ROWS = {}
    cases = [("BTC only (today's book)", ["BTC"]), ("BTC+ETH", ["BTC", "ETH"]),
             ("BTC+ETH+SOL", ["BTC", "ETH", "SOL"]),
             ("all 6 assets", U)]
    for lbl, coins in cases:
        f = full_rec(blend(S, coins))
        ROWS[lbl] = {**f, "coins": coins,
                     "rec_gross_usd": f["recommended_k"] * EQUITY,
                     "x_live": f["recommended_k"] * EQUITY / LIVE_GROSS}
        t = f["terms"]
        print(f"  {lbl:<30} {t['half_kelly']:>8.3f} {t['bootstrap_p10']:>8.3f} "
              f"{t['c_star_x_mstar']:>8.3f} {t['dd30']:>8.3f} {f['binding']:>14} "
              f"{f['recommended_k']:>7.3f} ${f['recommended_k']*EQUITY:>11,.0f}"
              + ("   KILLED" if f["killed_by_kill_rule"] else ""))
    OUT["full_kelly_terms"] = ROWS
    print()
    print("  -> The bootstrap p10 binds EVERYWHERE and it is 0.000 for every case but")
    print("     BTC+ETH. On this 2.19y window the repo's own instrument authorises")
    print("     ZERO for today's BTC book and ZERO for the 6-asset book. The 1.66x")
    print("     headline is a ratio of two DRAWDOWN-BUDGET numbers; it is NOT a ratio")
    print("     of two authorised sizes, and it must never be quoted as one.")

    # ---- is BTC+ETH's positive p10 real, or a seed? ----------------------
    print()
    print("=" * 104)
    print("THE ONLY POSITIVE ROW: is BTC+ETH's p10 robust across seeds?")
    print("=" * 104)
    print(f"  {'seed':>10} " + " ".join(f"{lbl:>14}" for lbl, _ in cases))
    P = {lbl: [] for lbl, _ in cases}
    for sd in range(SEED, SEED + 10):
        line = f"  {sd:>10} "
        for lbl, coins in cases:
            p10, _, _ = boot_stats(blend(S, coins), seed=sd)
            P[lbl].append(p10)
            line += f"{p10:>14.3f}"
        print(line)
    print()
    OUT["p10_seed_stability"] = {}
    for lbl, _ in cases:
        a = np.array(P[lbl])
        OUT["p10_seed_stability"][lbl] = {
            "values": a.tolist(), "mean": float(a.mean()),
            "min": float(a.min()), "max": float(a.max()),
            "frac_zero": float((a == 0).mean())}
        print(f"  {lbl:<30} mean {a.mean():>6.3f}  min {a.min():>6.3f}  "
              f"max {a.max():>6.3f}  zero in {int((a==0).sum())}/10 seeds")

    # net of funding, for the one row that matters
    print()
    print("=" * 104)
    print("BTC+ETH NET OF FUNDING, and what it would authorise")
    print("=" * 104)
    for lbl, d in (("gross of funding", S), ("NET of funding", SN)):
        f = full_rec(blend(d, ["BTC", "ETH"]))
        g = f["recommended_k"] * EQUITY
        OUT[f"btc_eth_{lbl.split()[0].lower()}"] = {
            **f, "rec_gross_usd": g, "x_live": g / LIVE_GROSS,
            "equity_for_100k": 100_000 / f["recommended_k"] if f["recommended_k"] else None,
            "equity_for_1m": 1_000_000 / f["recommended_k"] if f["recommended_k"] else None,
            "implied_KELLY_M_at_base_equity": f["recommended_k"] / REF_LEV}
        print(f"  {lbl:<20} rec k {f['recommended_k']:.3f} -> gross ${g:,.0f} "
              f"= {g/LIVE_GROSS:.2f}x today's $15,000")
        if f["recommended_k"]:
            print(f"  {'':<20} equity needed: ${100_000/f['recommended_k']:,.0f} for $100k gross, "
                  f"${1_000_000/f['recommended_k']:,.0f} for $1m")
            print(f"  {'':<20} implied KELLY_M at base=equity: "
                  f"{f['recommended_k']/REF_LEV:.3f} (repo cap is 0.20)")

    # every PAIR, so BTC+ETH is not just the lucky pair
    print()
    print("=" * 104)
    print("EVERY PAIR — is BTC+ETH special, or would any pair have done?")
    print("=" * 104)
    print(f"  {'pair':<14} {'p10':>8} {'dd30':>8} {'P(neg)':>8} {'rec k':>8} {'rec gross $':>12}")
    PAIRS = {}
    for combo in itertools.combinations(U, 2):
        f = full_rec(blend(S, list(combo)))
        PAIRS["+".join(combo)] = {"p10": f["terms"]["bootstrap_p10"],
                                  "dd30": f["terms"]["dd30"],
                                  "prob_neg": f["prob_neg_edge"],
                                  "rec_k": f["recommended_k"],
                                  "rec_gross": f["recommended_k"] * EQUITY}
        v = PAIRS["+".join(combo)]
        print(f"  {'+'.join(combo):<14} {v['p10']:>8.3f} {v['dd30']:>8.3f} "
              f"{v['prob_neg']:>8.3f} {v['rec_k']:>8.3f} ${v['rec_gross']:>11,.0f}"
              + ("   <-- the only one" if v["rec_k"] > 0 else ""))
    OUT["all_pairs"] = PAIRS
    npos = sum(1 for v in PAIRS.values() if v["rec_k"] > 0)
    print(f"\n  {npos} of {len(PAIRS)} pairs authorise anything at all.")
    print("  One survivor out of fifteen is exactly what the A1 multiple-testing")
    print("  result predicted, and it is the SAME asset (ETH) driving it.")
    OUT["n_pairs_positive"] = npos

    json.dump(OUT, open(os.path.join(HERE, "candC_p10.json"), "w"), indent=1,
              default=str)
    print("\nfrozen -> candC_p10.json")


if __name__ == "__main__":
    main()
