#!/usr/bin/env python3
"""Validate the point-in-time universe reconstruction before trusting it.

Three independent checks:
  A. Coverage — which names exist, when, and what the vendor is missing.
  B. Membership — reconstructed top-30 today vs SOXX's ACTUAL live holdings.
  C. Return fidelity — reconstructed index daily returns vs actual SOXX
     (correlation, tracking error, cumulative divergence), and SOXL vs 3x.

If C fails, every downstream conclusion about the "index leg" is suspect and
the study says so instead of quietly proceeding.
"""
import json
import os

import numpy as np

from datalib import (Data, TRADING_DAYS, build_index_proxy, month_ends,
                     pit_members)
from universe import DEAD_TICKERS, LIVE

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "universe_validation.json")


def main():
    d = Data()
    res = {}
    print(f"calendar: {d.dates[0]} -> {d.dates[-1]}  ({len(d.dates)} days)")

    # ---- A. coverage -----------------------------------------------------
    have = set(d.tickers)
    dead_have = sorted(t for t in DEAD_TICKERS if t in have)
    dead_miss = sorted(t for t in DEAD_TICKERS if t not in have)
    print(f"\nA. COVERAGE\n  dead names WITH history: {len(dead_have)} {dead_have}")
    print(f"  dead names MISSING:      {len(dead_miss)} {dead_miss}")
    for t in ["SOXL", "SOXS", "SOXX", "SPY"]:
        p = d.px[t]
        ok = np.where(~np.isnan(p))[0]
        print(f"  {t}: {d.dates[ok[0]]} -> {d.dates[ok[-1]]} ({len(ok)} obs)")
    res["coverage"] = {"dead_with_history": dead_have,
                       "dead_missing": dead_miss}

    # how many names are rankable over time (survivorship-gap proxy)
    mes = month_ends(d.dates)
    counts = []
    for me in mes:
        counts.append((d.dates[me], len(pit_members(d, me, 60))))
    print("  rankable candidates by year:")
    by_year = {}
    for dt_, c in counts:
        by_year.setdefault(dt_[:4], []).append(c)
    for y in sorted(by_year):
        print(f"    {y}: {int(np.mean(by_year[y]))}")
    res["rankable_by_year"] = {y: float(np.mean(v)) for y, v in by_year.items()}

    # ---- B. membership vs live SOXX -------------------------------------
    live = {h["asset"]: h["weight"] for h in d.live_holdings
            if h.get("asset") and h.get("weight")}
    live_top = sorted(live.items(), key=lambda kv: -kv[1])[:30]
    recon = pit_members(d, len(d.dates) - 1, 30)
    recon_names = list(recon)
    live_names = [t for t, _ in live_top]
    overlap = set(recon_names) & set(live_names)
    print(f"\nB. MEMBERSHIP (today)\n  reconstructed top-30 vs actual SOXX top-30: "
          f"{len(overlap)}/30 overlap")
    print(f"  in SOXX not reconstructed: {sorted(set(live_names)-set(recon_names))}")
    print(f"  reconstructed not in SOXX: {sorted(set(recon_names)-set(live_names))}")
    print(f"  reconstructed top-8: {recon_names[:8]}")
    print(f"  actual SOXX top-8:   {live_names[:8]}")
    res["membership_overlap"] = len(overlap)
    res["recon_top8"] = recon_names[:8]
    res["soxx_top8"] = live_names[:8]

    # ---- C. return fidelity ---------------------------------------------
    proxy, members = build_index_proxy(d)
    soxx = d.ret("SOXX")
    ok = np.isfinite(proxy) & np.isfinite(soxx)
    corr = float(np.corrcoef(proxy[ok], soxx[ok])[0, 1])
    te = float((proxy[ok] - soxx[ok]).std(ddof=1) * np.sqrt(TRADING_DAYS))
    beta = float(np.cov(proxy[ok], soxx[ok])[0, 1] / np.var(soxx[ok], ddof=1))
    cum_p = float(np.prod(1 + proxy[ok]) - 1)
    cum_s = float(np.prod(1 + soxx[ok]) - 1)
    print(f"\nC. RETURN FIDELITY (proxy vs SOXX, n={ok.sum()})")
    print(f"  corr={corr:.4f}  beta={beta:.3f}  tracking error={te*100:.2f}%/yr")
    print(f"  cumulative: proxy {cum_p*100:,.0f}%  vs SOXX {cum_s*100:,.0f}%")
    res["proxy_vs_soxx"] = {"corr": corr, "beta": beta, "te": te,
                            "cum_proxy": cum_p, "cum_soxx": cum_s,
                            "n": int(ok.sum())}

    # per-year tracking, to expose where the early-period gap bites
    print("  tracking error by year:")
    yr = {}
    for i in np.where(ok)[0]:
        yr.setdefault(d.dates[i][:4], []).append(proxy[i] - soxx[i])
    for y in sorted(yr):
        v = np.array(yr[y])
        print(f"    {y}: TE {v.std(ddof=1)*np.sqrt(TRADING_DAYS)*100:5.2f}%/yr   "
              f"cum diff {(np.prod(1+v)-1)*100:+6.2f}%")
    res["te_by_year"] = {y: float(np.std(yr[y], ddof=1) * np.sqrt(TRADING_DAYS))
                         for y in yr}

    # ---- D. SOXL vs 3x SOXX (the decay identity) ------------------------
    soxl = d.ret("SOXL")
    ok2 = np.isfinite(soxl) & np.isfinite(soxx)
    b3 = float(np.cov(soxl[ok2], soxx[ok2])[0, 1] / np.var(soxx[ok2], ddof=1))
    resid = soxl[ok2] - 3 * soxx[ok2]
    print(f"\nD. SOXL DAILY BETA TO SOXX = {b3:.4f} (design: 3.000)")
    print(f"   mean daily residual (r_soxl - 3*r_soxx) = {resid.mean()*1e4:.3f} bp"
          f"  -> {resid.mean()*TRADING_DAYS*100:+.2f}%/yr")
    print(f"   residual sd = {resid.std(ddof=1)*1e4:.1f} bp/day")
    res["soxl_beta_to_soxx"] = b3
    res["soxl_daily_fee_drag_annual"] = float(resid.mean() * TRADING_DAYS)

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
