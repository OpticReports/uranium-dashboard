# Pre-registration: forward ranges for the book by sleeve weight (2026-11-21)

Owner, 2026-11-21: "how about performing monte carlo simulations on these sleeves as well. Are there other
methods for estimating future returns, data backed ones that quants use, that we can use here to add more
estimates of what the next 1, 5, and 10 years looks like?" Written before any path was drawn.

## What is on the record, and what is new
- Monte Carlo has been run three times: addendum 4 (sleeve, 20 years), addendum 5 (12 months, each
  position and two books), addendum 13 (regime bootstrap on the S&P since 1971, low-return decade) and
  addendum 18 (the drift cap). All resample the engines' own backtests; all say "ranking tool, not
  forecast".
- New here: (a) the six sleeve weights of addendum 60; (b) the long daily engine paths of addenda 58-60
  (1994 on) as a source, beside the recent years; (c) the book as it is actually run: weights DRIFT and
  are reset only at the cap (POLICY operation 5), not rebalanced daily; the owner pointed out on
  2026-11-21 that the simulated falls understate the live ones, and in the one live fall of the three-engine
  book (2026-10-28..11-05) live was 14.2% against 10.7% simulated; (d) scenarios that shrink the simulated
  edge, each tied to evidence: published backtest-to-live decay, the one-close-late bound of addendum 61,
  and a low-return decade for stocks through each engine's market beta.

## Books
Third-leg (sleeve) weight 0, 10, 20, 31.8 (today), 40, 50%; the rest split equally between Holy Grail and
KMLM. Start at target weights. Weights drift with each engine's return; when any engine exceeds the largest
target plus 10 points (POLICY's cap and headroom rule: 44% today), all three are reset to target at 5.856
bps of turnover. For comparison only, the 31.8% book is also run with a daily reset to target (the
convention of addenda 59-61).

## Scenarios (each is a source of joint daily returns for HG, KMLM, SLEEVE and T-bills)
| Id | Name | Source | Why |
|---|---|---|---|
| A | As simulated, all-real years | 2021-06-02..2026-11-19 | the ceiling the sleeve-weight table shows; in sample |
| B | As simulated, since 2015 | 2015-06-01..2026-11-19 (hole 2020-12-02..2021-06-01 joined) | every traded fund real except KMLM before 2021; has 2018, 2020, 2022 |
| C | As simulated, whole rebuilt history | 1994-06-02..2026-11-19 | adds 2000-02 and 2007-09; shape only before 2015 |
| D | Half the edge | B, each engine's mean return over T-bills halved, volatility unchanged | published decay of strategies after discovery (McLean-Pontiff 2016: 58% lower after publication) and the common 50% backtest haircut (Harvey-Liu 2015) |
| E | A quarter of the edge | B, mean return over T-bills times 0.27 | Suhonen-Lennkh-Perez 2017: median 73% fall in Sharpe from backtest to live across 215 bank strategies |
| F | One close late | the one-close-late paths of addendum 61 (`late_path`), 2015-06 on | the execution bound: what a book that always fills a session late would have done |
| G | Low-return decade for stocks | B, each engine's mean lowered by its beta to the S&P 500 times (S&P's mean in B less 2% a year nominal) | the owner's low-return thesis and the published cluster of addendum 13 (-0.7% to +6.5%) |
"Mean halved" means: r' = r - (1 - k) x mean(r - tbill) over the source sample, per engine, k = 0.5 or 0.27.
Beta: OLS of the engine's daily return over T-bills on the S&P 500's (SPY total return), on B.
The citations' figures are spot-checked by the independent reviewer before the report ships.

## Draws
Stationary bootstrap of the source's sessions (the same sessions for all engines, so their joint behaviour
is kept), mean block 21 sessions, 10,000 paths of 2,520 sessions, one seed. The same draws serve all six
weights within a scenario. Horizons: 252, 1,260 and 2,520 sessions.

## Reported, per scenario x weight x horizon
Growth of $1: 5th, 25th, 50th, 75th, 95th percentile, and the same as a yearly rate; chance of ending below
the start; deepest fall within the horizon: median and 95th percentile; chance of a fall deeper than 20, 30,
40 and 50%.

## Other methods (reported beside the draws; none produces a path)
1. **Multiple-testing haircut / deflated Sharpe ratio** (Bailey and Lopez de Prado 2014): the Sharpe ratio
   the best of N unskilled trials would show on a sample this long, for N = 10, 100, 1,000, against each
   book's simulated Sharpe; the number of trials behind these symphonies is unknown.
2. **Market beta and what is left** (the building-block method): each engine's beta to the S&P 500 and the
   share of its mean return that beta explains, on B and on C. Feeds scenario G.
3. **The live record**: each symphony's live return since it started against the simulation on the same
   dates, with its span. Too short to fit anything; reported as the only out-of-sample evidence there is.

## How to read it (fixed now)
No scenario is a forecast and none will be called one. A, B, C are ceilings: they replay in-sample
backtests. The range to plan on is D to G; F is a bound that live fills have not sat at (addendum 14b).
The answer to "which sleeve weight" is whichever ordering holds in EVERY scenario; an ordering that flips
between scenarios is reported as not decided by the data. Nothing here changes a symphony, a weight or
POLICY without the owner.

## Honesty box
Every source is the engines' own simulated history: a regime outside it (the 1970s, a vol-market structure
change, a leveraged fund closing) is not in any draw. Leveraged and inverse funds can lose most of their
value in a day; no draw contains a day worse than the worst in its source. Taxes, capacity at larger size
and deposits are not modelled. Same-close fills in A-E and G. Measurement basis: daily mark-to-market.
