# B.5 Enhanced: entry / exit / stop / profit-harvest overlays (2026-11-18)

> WIP DRAFT - the independent code-and-claims audit is still running; numbers and wording below are not final.

Question (Casey): now that B.5 trades on IBKR ...3321, is there a rule for when to exit, re-enter, stop out or
harvest - on the book or on its legs, from price, RSI, volume, macro - that lifts Sharpe by cutting drawdown?
And which legs do not pull their weight?

Pre-registered (PREREG.md, commit e2e213c) and amended once before any result (DEVIATIONS.md, commit 8373227).
Research only: nothing here changes the live book, a gate or a symphony.

## Verdict: NOTHING SURVIVES. Keep the live rule (month-end check, +/-20% band).

| | CAGR | Sharpe | max drawdown |
|---|---|---|---|
| LIVE book, 2007-06..2026-11 (stand-ins before 2017) | 8.3% | 0.58 | -34.4% |
| LIVE book, 2017-04..2026-11 (real TAIL) | 10.5% | 0.71 | -23.0% |
| Walk-forward "pick last year's best rule", 2010-2026 | 5.6% | 0.46 | -21.7% |
| LIVE book, same 2010-2026 window | 9.5% | 0.72 | -23.0% |

- 53 timing rules x 2 tapes: 0 pass the Sharpe test. Best raw Sharpe gain over a same-exposure static book is
  +0.06 (CAPE half-weight, interval [-0.08, +0.18], and its drawdown is 5.7 pts WORSE). 43 of 53 are negative
  (median -0.05). Lowest family-adjusted p is 0.95.
- 0 pass the weaker DRAWDOWN TOOL test. Closest: A2, each risk leg held only above its own 10-month average,
  checked monthly. Drawdown -14.1% vs -24.5% for a static book with the same 76% exposure, better in both
  halves (+9.4 and +6.4 pts), same CAGR as that control. It fails on two registered conditions: ulcer index
  not lower in the first half, and family-wise placebo p 0.11 (bar 0.10). Against LIVE it costs 1.3 pts/yr.
- Book-level stops and trend exits HURT: Sharpe 0.19-0.57 vs 0.58; they sell after the fall and buy back late
  (2020: live +51% in the rebound, stop rules +18% to +35%).
- Profit harvesting (RSI > 70/80, stretch over the 200-day, top-decile run-up) adds nothing on the book and is
  significantly negative on the international legs over 30 years (AVDV proxy -0.17 Sharpe [-0.25, -0.08]).
- Macro gates (SPY trend, VIX backwardation, VIX > 30, credit spread, unemployment, 2-of-4 composite) helped in
  2008 and cost in every case since 2017 (-0.13 to -0.44 Sharpe vs control). CAPE does not time this book.
- Rebalance/harvest variants (10/15/30% bands, daily check, trim any leg above 1.25x target): all within noise.
- The mirror of every rule is also negative or zero: there is no inverted edge hiding here.

## Legs: none flagged
Dropping a leg (2017+ window; intervals are 95% bootstrap on the Sharpe change):
AVUV +0.09 [-0.20, +0.35] (weakest point estimate, not significant); AVDV +0.04; AVEM +0.02; TAIL +0.01;
QUAL -0.04; KMLM -0.03; PHYS -0.12 [-0.33, +0.10] (the most valuable leg).
KMLM and TAIL earn their keep on drawdown only: without KMLM the 2017+ drawdown is 3.5 pts deeper [-8.0, -0.3];
without TAIL 2.7 pts deeper [-4.1, -0.5] for +1.05 pt/yr CAGR. Swapping TAIL for T-bills: +0.6 pt/yr CAGR,
1.3 pts deeper drawdown [-2.2, +0.5] - TAIL has been no better than cash per point of drawdown since 2017.

## The cheapest reliable drawdown lever is exposure, not timing
80% book / 20% T-bills: Sharpe unchanged (+0.01), drawdown 6.4 pts shallower, CAGR -1.2 pts/yr.
No timing rule beats that trade reliably in both halves.

## Candidate edges (EDGE rule) - none clears multiplicity
120 conditional-return tests (5 legs x 8 states x 3 horizons); ~6 would exclude zero by chance, 7 did.
- Oversold bounce: after RSI14 < 30 the next 21 days beat normal by +2.4 pts on SPY/QUAL [+0.4, +4.6]
  (115 days, 58 spells) and +1.3 pts on gold [+0.0, +2.9] (183 days, 53 spells). Mirror (overbought) is not
  negative. Use: never sell a leg into an oversold reading; if a band rebalance is due then, do it.
- Momentum on international legs: after RSI14 > 70, AVDV/AVEM proxies beat normal by +1.4 / +1.3 pts over 21
  days (CIs exclude zero; mutual-fund NAVs are stale-priced, which flatters this). Use: do not trim winners there.
- High-volume down days on SPY: next 5 days +0.5 pt better [+0.1, +1.0] (147 days). Selling after one is wrong.
- Trend filters on single legs over 30 years helped EM, international small value and large-cap (+0.1 to +0.2
  Sharpe vs control, placebo 93-99th percentile, intervals include zero) and HURT US small value (-0.09) and
  gold (-0.09). Inside the diversified book this nets to nothing.
To use any of these would need a pre-registered single-hypothesis test on new data; none is tradeable as is.

## Honesty box
- Basis: daily closes, mark-to-market, BIL-excess Sharpe; signal at close t, trade at close t+1; costs 3-12 bps
  one-way per leg. All numbers are in-sample history, none is a forecast.
- Power: on 19 years the smallest Sharpe gain this design can detect is ~0.4-0.6 for rules that switch the
  whole book and ~0.13 for small trims. It rules out big edges, not small ones.
- Stand-ins before 2017: TAIL earns bills (T1) or a fitted Treasuries+puts model that over-earns real TAIL by
  4.6 pts/yr (T2); KMLM is RYMFX (T1) or 2x RYMFX (T2) before 2010-08, ASFYX to 2020-12; QUAL is SPY before
  2013-07; Avantis legs are DFA mutual funds before 2019-10. Every verdict is the same on both tapes.
- The first half (2007-2017) and second half are a consistency check, not a holdout.
- Not modelled: intraday stops, partial fills, IBKR minimums, option hedges, UNRATE/CAPE revisions, taxes (none).
- Deviations from the pre-registration: DEVIATIONS.md (one amendment, logged before results).

## Files
PREREG.md, DEVIATIONS.md, results.json (every number), data_meta.json (sources, hashes, first/last dates),
code/ (prep, common, arms, engine, run, charts, test_engine - 10 gate tests incl. a no-look-ahead test on all
53 rules and mirrors), charts/*.png. Raw price cache not committed (re-fetch with code/prep.py).
