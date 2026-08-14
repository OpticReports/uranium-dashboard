#!/usr/bin/env python3
"""Step 1 — decompose the trade BEFORE backtesting it.

Five questions, answered with arithmetic rather than a backtest:

  1. What does shorting SOXL actually pay? Split the ETF's shortfall into
     the DETERMINISTIC fee/financing term (harvestable by a hedged, daily
     rebalanced book) and the PATH/variance-drag term (harvestable only by
     letting the position ride, i.e. by selling convexity).
  2. What is the book's real net beta?
  3. Does "own the winners" have standalone alpha vs the index?
  4. What does the cost stack take?
  5. What does the short leg do in a trend? (tail behaviour by regime)

Writes fixtures/decomposition.json for the report and the gate tests.
"""
import json
import math
import os

import numpy as np

from datalib import (Data, TRADING_DAYS, build_basket, metrics, month_ends,
                     rolling_beta)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures", "decomposition.json")
START = "2010-03-12"          # first full SOXL day


def ols(y, x):
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    b = np.cov(y, x)[0, 1] / np.var(x, ddof=1)
    a = y.mean() - b * x.mean()
    resid = y - (a + b * x)
    se_b = math.sqrt(np.var(resid, ddof=2) / (np.var(x, ddof=1) * (len(x) - 1)))
    se_a = math.sqrt(np.var(resid, ddof=2) / len(x))
    return a, b, se_a, se_b, int(len(x))


def main():
    d = Data()
    lo, hi = d.slice_idx(START, d.dates[-1])
    dates = d.dates[lo:hi]
    r_soxl = d.ret("SOXL")[lo:hi]
    r_soxs = d.ret("SOXS")[lo:hi]
    r_soxx = d.ret("SOXX")[lo:hi]
    r_spy = d.ret("SPY")[lo:hi]
    rf = d.rf[lo:hi]
    res = {"period": [dates[0], dates[-1]], "n_days": len(dates)}

    # =====================================================================
    # 1. WHAT SHORTING SOXL ACTUALLY PAYS
    # =====================================================================
    print("=" * 74)
    print("1. LEVERAGED-ETF DECAY: DETERMINISTIC FEE vs PATH DRAG")
    print("=" * 74)
    a, b, se_a, se_b, n = ols(r_soxl, r_soxx)
    fee_annual = a * TRADING_DAYS
    print(f"  r_SOXL = alpha + beta * r_SOXX     (daily, n={n})")
    print(f"    beta  = {b:.4f}  (SE {se_b:.4f}; design 3.0)")
    print(f"    alpha = {a*1e4:+.3f} bp/day = {fee_annual*100:+.2f}%/yr "
          f"(SE {se_a*TRADING_DAYS*100:.2f}%/yr)")
    print(f"    t(alpha) = {a/se_a:+.2f}")
    print("  -> a beta-matched, DAILY-REBALANCED short of SOXL against long")
    print("     SOXX earns this alpha and nothing else. It is the fund's")
    print("     expense ratio + financing spread. This is the only piece of")
    print("     'decay' that is harvestable without taking path risk.")
    res["soxl_vs_soxx"] = {"alpha_daily": a, "alpha_annual": fee_annual,
                           "beta": b, "se_alpha_annual": se_a * TRADING_DAYS,
                           "t_alpha": a / se_a, "n": n}

    a_s, b_s, se_as, _, _ = ols(r_soxs, r_soxx)
    print(f"\n  SOXS: beta={b_s:.4f} (design -3.0), "
          f"alpha={a_s*TRADING_DAYS*100:+.2f}%/yr")
    res["soxs_vs_soxx"] = {"alpha_annual": a_s * TRADING_DAYS, "beta": b_s}

    # --- path/variance drag, realized and theoretical --------------------
    print("\n  PATH DRAG (the part you can only get by NOT rebalancing):")
    print("    theory: log(SOXL_T) - 3*log(SOXX_T) = -(3^2-3)/2 * sigma^2 * T"
          " - fees*T")
    print(f"    {'year':<6}{'sigma_SOXX':>11}{'3*sig^2 (th)':>14}"
          f"{'realized gap':>14}{'SOXX ret':>10}{'SOXL ret':>11}")
    yearly = {}
    for y in sorted({x[:4] for x in dates}):
        m = np.array([x[:4] == y for x in dates])
        if m.sum() < 100:
            continue
        rl, rx = r_soxl[m], r_soxx[m]
        ok = np.isfinite(rl) & np.isfinite(rx)
        rl, rx = rl[ok], rx[ok]
        sig = rx.std(ddof=1) * math.sqrt(TRADING_DAYS)
        theory = 3 * sig ** 2
        gap = np.log(np.prod(1 + rl)) - 3 * np.log(np.prod(1 + rx))
        cum_x = np.prod(1 + rx) - 1
        cum_l = np.prod(1 + rl) - 1
        print(f"    {y:<6}{sig*100:>10.1f}%{theory*100:>13.1f}%"
              f"{-gap*100:>13.1f}%{cum_x*100:>9.1f}%{cum_l*100:>10.1f}%")
        yearly[y] = {"sigma": sig, "theory_drag": theory,
                     "realized_gap": float(-gap), "soxx": float(cum_x),
                     "soxl": float(cum_l)}
    res["yearly"] = yearly

    tot_gap = (np.log(np.nanprod(1 + r_soxl))
               - 3 * np.log(np.nanprod(1 + r_soxx)))
    sig_all = np.nanstd(r_soxx, ddof=1) * math.sqrt(TRADING_DAYS)
    yrs = len(dates) / TRADING_DAYS
    print(f"\n    FULL PERIOD: realized gap {-tot_gap*100:.0f}% of log return "
          f"over {yrs:.1f}y = {-tot_gap/yrs*100:.1f}%/yr")
    print(f"    theory at sigma={sig_all*100:.1f}%: "
          f"{3*sig_all**2*100:.1f}%/yr drag + {-fee_annual*100:.1f}%/yr fees "
          f"= {(3*sig_all**2 - fee_annual)*100:.1f}%/yr")
    res["path_drag"] = {"realized_annual": float(-tot_gap / yrs),
                        "theory_variance_drag": float(3 * sig_all ** 2),
                        "sigma_full": float(sig_all)}

    # --- THE CENTRAL TEST: does rebalancing frequency change the harvest? -
    print("\n  DECAY HARVEST vs REBALANCE FREQUENCY (short SOXL 1x notional,")
    print("  long SOXX 3x notional, reset to those notionals every k days):")
    print(f"    {'reset':<10}{'CAGR':>9}{'vol':>8}{'Sharpe':>8}{'maxDD':>9}"
          f"{'skew':>8}")
    harvest = {}
    for k, name in [(1, "daily"), (5, "weekly"), (21, "monthly"),
                    (63, "quarterly"), (10**9, "never")]:
        nav = _pair_trade(r_soxl, r_soxx, k)
        r = nav[1:] / nav[:-1] - 1
        r = r[np.isfinite(r)]
        if len(r) < 50 or nav[-1] <= 0:
            print(f"    {name:<10}{'WIPED OUT':>9}")
            harvest[name] = {"wiped": True}
            continue
        cagr = nav[-1] ** (TRADING_DAYS / len(r)) - 1
        vol = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
        sh = r.mean() / r.std(ddof=1) * math.sqrt(TRADING_DAYS)
        dd = (nav / np.maximum.accumulate(nav) - 1).min()
        sk = float(((r - r.mean()) ** 3).mean() / r.std(ddof=1) ** 3)
        print(f"    {name:<10}{cagr*100:>8.1f}%{vol*100:>7.1f}%{sh:>8.2f}"
              f"{dd*100:>8.1f}%{sk:>8.2f}")
        harvest[name] = {"cagr": float(cagr), "vol": float(vol),
                         "sharpe": float(sh), "maxdd": float(dd), "skew": sk}
    res["harvest_by_reset"] = harvest
    print("  -> read this table before believing any 'decay harvesting' pitch.")

    # =====================================================================
    # 2. BETA ACCOUNTING
    # =====================================================================
    print("\n" + "=" * 74)
    print("2. BETA ACCOUNTING — is this book market-neutral?")
    print("=" * 74)
    mes = [i for i in month_ends(d.dates) if lo <= i < hi]
    basket_r = _basket_returns(d, mes, 8, "cap", lo, hi)
    ok = np.isfinite(basket_r) & np.isfinite(r_soxx)
    a_b, beta_b, se_ab, _, nb = ols(basket_r, r_soxx)
    print(f"  top-8 cap-weighted basket vs SOXX: beta = {beta_b:.3f}, "
          f"alpha = {a_b*TRADING_DAYS*100:+.2f}%/yr (n={nb})")
    # book beta: -0.25 * beta_soxl + 0.75 * beta_basket, all vs SOXX
    net_beta = -0.25 * b + 0.75 * beta_b
    print(f"  V0 net beta to SOXX = -0.25*{b:.3f} + 0.75*{beta_b:.3f} "
          f"= {net_beta:+.3f}")
    book_r = 0.75 * basket_r - 0.25 * r_soxl
    a_bk, beta_bk, se_abk, _, nbk = ols(book_r, r_soxx)
    print(f"  measured directly:   beta = {beta_bk:+.3f}, "
          f"alpha = {a_bk*TRADING_DAYS*100:+.2f}%/yr "
          f"(SE {se_abk*TRADING_DAYS*100:.2f})")
    a_sp, beta_sp, _, _, _ = ols(book_r, r_spy)
    print(f"  vs SPY:              beta = {beta_sp:+.3f}")
    res["beta_accounting"] = {
        "basket_beta_vs_soxx": beta_b, "basket_alpha_annual": a_b * TRADING_DAYS,
        "soxl_beta": b, "v0_net_beta_implied": float(net_beta),
        "v0_net_beta_measured": beta_bk, "v0_alpha_annual": a_bk * TRADING_DAYS,
        "v0_beta_vs_spy": beta_sp}

    rb = rolling_beta(book_r, r_soxx, 126)
    fin = rb[np.isfinite(rb)]
    print(f"  rolling 126d net beta: min {fin.min():+.2f}  "
          f"median {np.median(fin):+.2f}  max {fin.max():+.2f}  "
          f"share>0: {(fin>0).mean()*100:.0f}%")
    res["rolling_net_beta"] = {"min": float(fin.min()),
                               "median": float(np.median(fin)),
                               "max": float(fin.max()),
                               "share_positive": float((fin > 0).mean())}

    # how much of the book's return is just beta?
    bench_contrib = beta_bk * np.nansum(r_soxx)
    print(f"\n  DECOMPOSITION OF V0 GROSS RETURN (arithmetic, sum of daily):")
    tot = np.nansum(book_r)
    print(f"    total            {tot*100:8.1f}%")
    print(f"    beta*SOXX        {bench_contrib*100:8.1f}%   "
          f"({bench_contrib/tot*100:.0f}% of total)")
    print(f"    residual/alpha   {(tot-bench_contrib)*100:8.1f}%   "
          f"({(1-bench_contrib/tot)*100:.0f}% of total)")
    res["v0_return_attribution"] = {"total_sum": float(tot),
                                    "beta_component": float(bench_contrib)}

    # =====================================================================
    # 3. DISPERSION / CONCENTRATION ALPHA
    # =====================================================================
    print("\n" + "=" * 74)
    print("3. DOES 'OWN THE TOP NAMES' HAVE STANDALONE ALPHA?")
    print("=" * 74)
    print(f"  {'basket':<22}{'CAGR':>9}{'beta':>8}{'alpha/yr':>11}"
          f"{'t(alpha)':>10}{'IR':>7}")
    disp = {}
    for n_names, scheme in [(3, "cap"), (5, "cap"), (8, "cap"), (12, "cap"),
                            (8, "ew"), (8, "mom")]:
        br = _basket_returns(d, mes, n_names, scheme, lo, hi)
        aa, bb, sea, _, nn = ols(br, r_soxx)
        act = br - bb * r_soxx
        ok2 = np.isfinite(act)
        ir = (act[ok2].mean() * TRADING_DAYS /
              (act[ok2].std(ddof=1) * math.sqrt(TRADING_DAYS)))
        cg = np.nanprod(1 + br) ** (TRADING_DAYS / np.isfinite(br).sum()) - 1
        tag = f"top-{n_names} {scheme}"
        print(f"  {tag:<22}{cg*100:>8.1f}%{bb:>8.2f}"
              f"{aa*TRADING_DAYS*100:>10.2f}%{aa/sea:>10.2f}{ir:>7.2f}")
        disp[tag] = {"cagr": float(cg), "beta": bb,
                     "alpha_annual": aa * TRADING_DAYS, "t": aa / sea,
                     "ir": float(ir)}
    res["dispersion"] = disp

    # cross-sectional dispersion series (used later as a gate)
    xsd = _cross_sec_dispersion(d, mes, lo, hi)
    print(f"\n  cross-sectional dispersion of constituent 21d returns: "
          f"median {np.nanmedian(xsd)*100:.1f}%")
    res["xsec_dispersion_median"] = float(np.nanmedian(xsd))

    # --- 3B. WHERE DOES THE BASKET ALPHA COME FROM? ----------------------
    # Hypothesis: it is not stock-picking skill, it is the ABSENCE of the
    # index's 8%/4% weight caps. SOXX trims its compounders every quarter;
    # a top-N cap-weighted basket lets them run. Test by applying the SAME
    # caps to the basket and re-measuring alpha.
    print("\n  3B. IS THE ALPHA 'PICKING WINNERS' OR JUST 'NOT CAPPING THEM'?")
    br_uncapped = _basket_returns(d, mes, 8, "cap", lo, hi)
    br_capped = _basket_returns(d, mes, 8, "cap_iceclip", lo, hi)
    for tag, br in [("top-8 uncapped", br_uncapped),
                    ("top-8 ICE-capped", br_capped)]:
        aa, bb, sea, _, _ = ols(br, r_soxx)
        print(f"    {tag:<20} beta {bb:.2f}  alpha {aa*TRADING_DAYS*100:+6.2f}%/yr"
              f"  t {aa/sea:+.2f}")
        res.setdefault("alpha_source", {})[tag] = {
            "beta": bb, "alpha_annual": aa * TRADING_DAYS, "t": aa / sea}

    # single-name dependence: drop the single best performer ex-post. This is
    # deliberately hindsight-biased -- it answers "how concentrated is the
    # result in one name", not "what would we have earned".
    for drop in ["NVDA", "AVGO"]:
        br = _basket_returns(d, mes, 8, "cap", lo, hi, exclude={drop})
        aa, bb, sea, _, _ = ols(br, r_soxx)
        print(f"    ex-{drop:<17} beta {bb:.2f}  alpha {aa*TRADING_DAYS*100:+6.2f}%/yr"
              f"  t {aa/sea:+.2f}")
        res["alpha_source"][f"ex_{drop}"] = {
            "beta": bb, "alpha_annual": aa * TRADING_DAYS, "t": aa / sea}

    # subperiod stability of the concentration alpha
    print("    subperiod alpha (top-8 cap vs SOXX):")
    for tag, s, e in [("2010-2014", "2010-03-12", "2014-12-31"),
                      ("2015-2019", "2015-01-01", "2019-12-31"),
                      ("2020-2026", "2020-01-01", "2026-12-31")]:
        m = np.array([s[:10] <= x <= e for x in dates])
        aa, bb, sea, _, nn = ols(br_uncapped[m], r_soxx[m])
        print(f"      {tag}: beta {bb:.2f}  alpha {aa*TRADING_DAYS*100:+6.2f}%/yr"
              f"  t {aa/sea:+.2f}  (n={nn})")
        res["alpha_source"][tag] = {"alpha_annual": aa * TRADING_DAYS,
                                    "t": aa / sea, "beta": bb}

    # =====================================================================
    # 4. THE COST STACK AND THE BREAKEVEN BORROW RATE
    # =====================================================================
    print("\n" + "=" * 74)
    print("4. COST STACK — what has to be true for the short leg to pay")
    print("=" * 74)
    print(f"  Gross edge from shorting SOXL = its alpha vs SOXX = "
          f"{-fee_annual*100:.2f}%/yr of SHORT NOTIONAL")
    print(f"  At V0's 25% short notional that is "
          f"{-fee_annual*0.25*100:.2f}%/yr on capital.")
    print("\n  Borrow-rate breakeven (short leg's fee edge fully consumed):")
    print(f"    breakeven borrow = {-fee_annual*100:.2f}%/yr on SOXL")
    print("    Above that rate the short is a pure hedge with negative carry;")
    print("    below it, it is a cheaper hedge than shorting 3x SOXX outright.")
    res["breakeven_borrow_soxl"] = float(-fee_annual)

    print("\n  Turnover is measured exactly by the backtest engine (which")
    print("  tracks share-level drift), not estimated here -- see variants.py.")

    # =====================================================================
    # 5. NEGATIVE CONVEXITY OF THE SHORT LEG
    # =====================================================================
    print("\n" + "=" * 74)
    print("5. NEGATIVE CONVEXITY — what the short leg does in a trend")
    print("=" * 74)
    print("  Static short of 25% notional SOXL, never rebalanced, by year:")
    print(f"    {'year':<6}{'SOXL ret':>11}{'P&L on 25% short':>20}"
          f"{'end notional':>15}")
    conv = {}
    for y in sorted(yearly):
        m = np.array([x[:4] == y for x in dates])
        rl = r_soxl[m]
        rl = rl[np.isfinite(rl)]
        path = np.cumprod(1 + rl)
        pnl = -0.25 * (path[-1] - 1)
        print(f"    {y:<6}{(path[-1]-1)*100:>10.1f}%{pnl*100:>19.1f}%"
              f"{0.25*path[-1]*100:>14.1f}%")
        conv[y] = {"soxl": float(path[-1] - 1), "pnl": float(pnl),
                   "end_notional": float(0.25 * path[-1])}
    res["static_short_by_year"] = conv

    worst = min(conv.items(), key=lambda kv: kv[1]["pnl"])
    best = max(conv.items(), key=lambda kv: kv[1]["pnl"])
    print(f"\n  worst year {worst[0]}: {worst[1]['pnl']*100:.1f}% on capital, "
          f"short grew to {worst[1]['end_notional']*100:.0f}% of starting capital")
    print(f"  best  year {best[0]}: {best[1]['pnl']*100:+.1f}%")

    # regime conditioning: which regime is the short actually long?
    print("\n  SOXL short P&L conditioned on regime (daily, 25% notional):")
    trend = _sma_state(d.px["SOXX"][lo:hi], 200)
    vol20 = _rolling_vol(r_soxx, 20)
    volmed = np.nanmedian(vol20)
    rows = {}
    for tname, tmask in [("SOXX > 200dma", trend > 0), ("SOXX < 200dma", trend < 0)]:
        for vname, vmask in [("vol<med", vol20 < volmed), ("vol>med", vol20 >= volmed)]:
            m = tmask & vmask & np.isfinite(r_soxl)
            if m.sum() < 30:
                continue
            pnl = -0.25 * r_soxl[m]
            ann = pnl.mean() * TRADING_DAYS
            sh = pnl.mean() / pnl.std(ddof=1) * math.sqrt(TRADING_DAYS)
            key = f"{tname} & {vname}"
            rows[key] = {"days": int(m.sum()), "ann": float(ann),
                         "sharpe": float(sh)}
            print(f"    {key:<26} n={m.sum():>4}  "
                  f"ann {ann*100:>+6.1f}%  Sharpe {sh:>+5.2f}")
    res["short_regime"] = rows

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {OUT}")


# --------------------------------------------------------------------------
def _pair_trade(r_soxl, r_soxx, reset_days):
    """Short 1 unit SOXL / long 3 units SOXX, notionals reset every k days.

    Capital = 1. Share-level drift between resets, so 'never' is a genuinely
    static position and can blow up. NAV floored at 0.
    """
    n = len(r_soxl)
    nav = np.ones(n)
    s_notional, l_notional = -1.0, 3.0
    equity = 1.0
    last_reset = 0
    for i in range(1, n):
        rl, rx = r_soxl[i], r_soxx[i]
        if not (np.isfinite(rl) and np.isfinite(rx)):
            nav[i] = nav[i - 1]
            continue
        pnl = s_notional * rl + l_notional * rx
        s_notional *= (1 + rl)
        l_notional *= (1 + rx)
        equity += pnl
        if equity <= 0:
            nav[i:] = 0.0
            return nav
        nav[i] = equity
        if i - last_reset >= reset_days:
            s_notional, l_notional = -equity, 3.0 * equity
            last_reset = i
    return nav


def _basket_returns(d, mes, n_names, scheme, lo, hi, exclude=None):
    """Daily returns of a monthly-rebalanced top-N basket, share-level drift.

    `exclude` drops names from the candidate set BEFORE selection. It is a
    hindsight diagnostic (how concentrated is the result in one name), never
    a tradeable variant.
    """
    out = np.full(hi - lo, np.nan)
    for k, me in enumerate(mes[:-1]):
        w = build_basket(d, me, n_names + (len(exclude) if exclude else 0),
                         scheme)
        if exclude:
            w = {t: v for t, v in w.items() if t not in exclude}
            tot = sum(w.values())
            w = {t: v / tot for t, v in w.items()} if tot > 0 else {}
        if not w:
            continue
        nxt = mes[k + 1]
        shares, prev = {}, 0.0
        for t in w:
            p = d.px[t][me]
            if np.isnan(p):
                continue
            shares[t] = w[t] / p
            prev += w[t]
        if prev <= 0:
            continue
        for i in range(me + 1, min(nxt + 1, hi)):
            val = 0.0
            for t, q in shares.items():
                p = d.px[t][i]
                if np.isnan(p):
                    j = i
                    while j >= 0 and np.isnan(d.px[t][j]):
                        j -= 1
                    p = d.px[t][j] if j >= 0 else 0.0
                val += q * p
            out[i - lo] = val / prev - 1.0
            prev = val
    return out


def _cross_sec_dispersion(d, mes, lo, hi, window=21):
    out = np.full(hi - lo, np.nan)
    for me in mes:
        w = build_basket(d, me, 30, "cap")
        rs = []
        for t in w:
            p = d.px[t]
            if me - window < 0 or np.isnan(p[me]) or np.isnan(p[me - window]):
                continue
            rs.append(p[me] / p[me - window] - 1)
        if len(rs) > 5:
            out[me - lo] = float(np.std(rs, ddof=1))
    # forward-fill month-end value across the month
    last = np.nan
    for i in range(len(out)):
        if np.isfinite(out[i]):
            last = out[i]
        else:
            out[i] = last
    return out


def _sma_state(px, w):
    out = np.full(len(px), np.nan)
    for i in range(w, len(px)):
        seg = px[i - w:i]
        if np.isfinite(seg).all():
            out[i] = px[i] - seg.mean()
    return out


def _rolling_vol(r, w):
    out = np.full(len(r), np.nan)
    for i in range(w, len(r)):
        seg = r[i - w:i]
        if np.isfinite(seg).all():
            out[i] = seg.std(ddof=1) * math.sqrt(TRADING_DAYS)
    return out


if __name__ == "__main__":
    main()
