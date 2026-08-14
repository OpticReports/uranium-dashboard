#!/usr/bin/env python3
"""V6 — replace the short SOXL leg with long SOXL puts.

THIS IS A MODEL, NOT A BACKTEST. No historical SOXL option chain was
available from the data vendor, so premiums are priced with Black-Scholes
off TRAILING realized vol plus a swept variance-risk premium. Two
consequences are stated rather than buried:

  * Using trailing realized vol as the implied-vol input understates what a
    buyer actually pays in calm-to-stormy transitions (real IV leads
    realized). The sweep over `vrp` is how that uncertainty is expressed.
  * Every number here inherits that assumption. They are directional -- good
    enough to answer "can premium ever be cheap enough", not to size a book.

The question this answers: the short leg's negative convexity is the
strategy's dominant risk. Puts cap it. What does the cap cost, and is the
edge big enough to pay for it?
"""
import json
import math
import os

import numpy as np

from datalib import Costs, Data, TRADING_DAYS, build_basket, metrics
from variants import BASE_COSTS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "options_v6.json")
START = "2010-03-12"


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, r, sigma, T):
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)


def realized_vol(r, i, w):
    seg = r[max(0, i - w):i]
    seg = seg[np.isfinite(seg)]
    if len(seg) < w // 2:
        return np.nan
    return seg.std(ddof=1) * math.sqrt(TRADING_DAYS)


def simulate(d, moneyness=0.90, tenor=63, cover=0.25, vrp=0.05,
             spread_bps=150, long_w=0.75):
    """Long basket + rolling long SOXL puts covering `cover` of NAV."""
    lo, hi = d.slice_idx(START, d.dates[-1])
    r_soxl = d.ret("SOXL")
    px = d.px["SOXL"]
    nav = 1.0
    navs, dates = [], []
    premium_paid = 0.0
    payoff_recv = 0.0
    pos = None           # (K, n_contracts, expiry_idx)
    basket_shares = {}
    prev_basket_val = None
    i = lo
    mes = _month_ends(d.dates, lo, hi)

    for i in range(lo, hi):
        # long basket leg: rebalanced monthly, share-level drift
        if i in mes or not basket_shares:
            w = build_basket(d, i, 8, "cap")
            if w:
                basket_val = long_w * nav
                basket_shares = {t: basket_val * v / d.px[t][i]
                                 for t, v in w.items()
                                 if np.isfinite(d.px[t][i])}
                prev_basket_val = sum(q * d.px[t][i]
                                      for t, q in basket_shares.items())
        cur_basket = 0.0
        for t, q in basket_shares.items():
            p = d.px[t][i]
            if not np.isfinite(p):
                j = i
                while j >= 0 and not np.isfinite(d.px[t][j]):
                    j -= 1
                p = d.px[t][j]
            cur_basket += q * p
        if prev_basket_val:
            nav += cur_basket - prev_basket_val
        prev_basket_val = cur_basket

        # cash leg earns the short rate on the un-invested balance
        cash = nav - cur_basket
        nav += cash * max(d.rf[i] - 0.005, 0.0) / TRADING_DAYS

        # option leg
        if pos and i >= pos[2]:
            K, n, _ = pos
            pay = max(K - px[i], 0.0) * n
            # book premium and payoff as fractions of the NAV they were
            # charged against; summing raw dollars against a compounding NAV
            # would report a drag inflated by the book's own growth.
            payoff_recv += pay / nav if nav > 0 else 0.0
            nav += pay
            pos = None
        if pos is None and np.isfinite(px[i]) and nav > 0:
            sigma = realized_vol(r_soxl, i, tenor)
            if np.isfinite(sigma):
                sigma *= (1 + vrp)
                K = px[i] * moneyness
                T = tenor / TRADING_DAYS
                prem = bs_put(px[i], K, d.rf[i], sigma, T)
                prem *= (1 + spread_bps / 1e4)      # pay the offer
                n = cover * nav / px[i]             # cover `cover` of NAV
                cost = prem * n
                premium_paid += cost / nav if nav > 0 else 0.0
                nav -= cost
                pos = (K, n, min(i + tenor, hi - 1))
        navs.append(nav)
        dates.append(d.dates[i])
    return (np.array(navs), dates, premium_paid, payoff_recv)


def _month_ends(dates, lo, hi):
    out, cur = set(), None
    for i in range(len(dates)):
        m = dates[i][:7]
        if cur is not None and m != cur[0] and lo <= cur[1] < hi:
            out.add(cur[1])
        cur = (m, i)
    return out


def main():
    d = Data()
    res = {}
    print("=" * 92)
    print("V6 — SHORT SOXL REPLACED BY LONG SOXL PUTS  (MODELLED, not backtested)")
    print("=" * 92)
    sig = realized_vol(d.ret("SOXL"), len(d.dates) - 1, 252)
    full = d.ret("SOXL")
    print(f"  SOXL trailing 1y realized vol: {sig*100:.0f}%   "
          f"full-period realized vol: "
          f"{np.nanstd(full, ddof=1)*math.sqrt(TRADING_DAYS)*100:.0f}%")
    print("  Puts are priced at trailing realized vol x (1 + vrp), plus a")
    print("  150bp spread paid to the offer. Quarterly roll, 25% NAV covered.\n")
    print(f"{'moneyness':<11}{'vrp':>6}{'CAGR':>9}{'vol':>7}{'Sharpe':>8}"
          f"{'maxDD':>8}{'premium/yr':>12}{'payoff/yr':>11}{'net carry':>11}")
    for mny in (1.00, 0.90, 0.80):
        for vrp in (0.0, 0.05, 0.15):
            nav, dates, prem, pay = simulate(d, moneyness=mny, vrp=vrp)
            m = metrics(nav, dates)
            yrs = m["Years"]
            key = f"{mny:.2f}|{vrp:.2f}"
            res[key] = {"cagr": m["CAGR"], "sharpe": m["Sharpe"],
                        "maxdd": m["MaxDD"], "vol": m["Vol"],
                        "premium_per_year": prem / yrs,
                        "payoff_per_year": pay / yrs}
            print(f"{mny:<11.2f}{vrp:>6.2f}{m['CAGR']*100:>8.1f}%"
                  f"{m['Vol']*100:>6.1f}%{m['Sharpe']:>8.2f}"
                  f"{m['MaxDD']*100:>7.1f}%{prem/yrs*100:>11.1f}%"
                  f"{pay/yrs*100:>10.1f}%{(pay-prem)/yrs*100:>10.1f}%")

    print("\n  Reference: the SHORT leg it replaces earns ~1.35%/yr on capital")
    print("  (5.4%/yr of fee alpha x 25% notional). Any put program whose net")
    print("  carry is worse than -1.35%/yr is strictly worse than shorting,")
    print("  and buys only a drawdown cap in exchange.")
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
