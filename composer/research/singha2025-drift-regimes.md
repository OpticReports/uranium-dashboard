# Singha 2025 — "Discovery of a 13-Sharpe OOS Factor: Drift Regimes" (arXiv:2511.12490)

**Verdict: REJECTED — results are artifacts of a poisoned backtest universe.
Do not build. No symphony changes.** Reviewed 2026-07-23 at the owner's
request. Single-author q-fin preprint (author is a NASA astrophysicist, not
a finance researcher), not peer-reviewed, no code or data release.

## Claim

Long-short S&P 500 factor: 0.7×value (inverse share price, ranked) +
0.3×reversal (negated 10-day return, z-scored), gated ON only for stocks in
a "drift regime" (>60% positive days over trailing 63d). Claims OOS Sharpe
13.19, +158.6%/yr at 12% vol, max DD −11.9%, over three 1-year walk-forward
test windows (2010-11, 2015-16, 2020-21).

## Why it's wrong (checkable, in descending order of severity)

1. **Survivorship bias, admitted and amplified.** The universe is the
   *current* (2024) S&P 500 constituents backfilled to 2004 — admitted on
   p.3. The drift filter (>60% up-days) then *selects precisely the
   stock-periods where survivor bias is strongest*, and the "value" signal
   is literally **1/price** — in a survivor universe, buying low-nominal-
   price current constituents in 2004-2015 is buying future multi-baggers
   (AMD at $2, etc.) with a time machine. The claimed "interaction effect"
   (53% of returns, Table 8) is the interaction of two bias amplifiers.
2. **The paper's own benchmark proves the data is poisoned.** Their
   equal-weight benchmark of the same universe returns **+79%/yr in each of
   the three test windows** (+478% cumulative, Table 2/3). Actual SPX for
   those windows (verified against our own daily data): 2010→11 +12% to
   +30%, 2015→16 −2% to +1%, 2020→21 +14% to +39%. An equal-weight S&P
   basket cannot return +79% in 2015-16 (real: ~0%). The +79%/yr is the
   survivorship premium of the backfilled universe — and the strategy's
   returns sit on top of the same contamination.
3. **"Sharpe 13" fails the smell test by an order of magnitude.** Best
   sustained market-neutral performance in history (Medallion, net) is
   ~2.5–4. Their TRAINING Sharpes are 19–27; window 2 shows 207% return
   with a −0.9% max drawdown. These are not "remarkable results"; they are
   diagnostic of pipeline error.
4. **Transaction costs assumed at 0.6bp** per unit traded, with 42% daily
   turnover and a 10-day reversal leg. Realistic all-in costs for daily
   long-short large-cap trading are 5-10× that; short-term reversal is the
   classic strategy that dies on real costs + bid-ask bounce (their close-
   to-close reversal harvests bounce that cannot be captured).
5. **"20 years of validation" is actually 3 cherry-located test years**,
   all in recovery/bull phases (2010-11, 2015-16, 2020-21). 2008, 2018,
   and 2022 are never traded OOS. The "2008 crisis" resilience (Sharpe
   4.1) is a *simulated* stress on the same biased data, not history.
6. **Internal inconsistencies:** 42% daily turnover vs "8-day median
   holding" (implies ~2.4d); "67% winning days" vs a +0.63% median daily
   return at 0.76% daily vol (implies ~80%); microstructure table (Table
   12) has no data source; capacity/impact numbers are unsupported.
7. The 1,000-random-regime-filter test only shows the *specific* filter
   couples to the bias — a randomization test on contaminated data cannot
   validate alpha.

## Any learnings for our book?

- The one legitimate idea — **binary regime-gating of a signal** — we
  already run in better-validated forms: the HYG credit guard gating ZVOL,
  the KMLM switcher's regime branches, HG's sort/safe-sector rotation, and
  the canary's accident composite. Nothing here improves them.
- Not buildable in Composer anyway: requires ~375-position cross-sectional
  long-SHORT market-neutral daily rebalancing; Composer is long-only
  allocation over a fixed ticker list.
- Useful as a **negative exemplar** vs Wang 2020 (modest claims, honest
  methodology, partially adopted): extraordinary Sharpe + admitted
  survivorship + no code = reject without backtest. Our standing rule
  holds: any third-party strategy claim must survive our own
  survivorship-clean reconstruction before capital discussion.

## Next steps

None for the portfolio. PDF retained in session uploads only; this memo is
the durable record.
