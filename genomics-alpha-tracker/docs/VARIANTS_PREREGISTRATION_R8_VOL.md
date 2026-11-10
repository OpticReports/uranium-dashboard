# ROUND 8 — volatility: the thesis, then the overlay. Pre-registration, 2026-08-22

Registered BEFORE any round-8 code. Casey: test the vol-clustering thesis over
20 years, then overlay it on the existing books to see whether vol-based
weighting, rebalancing or sizing improves CAGR or drawdown.

## What can and cannot be established

CAN: whether vol clustered, whether it was forecastable, and whether a vol
overlay improved CAGR/DD/Sharpe/Calmar **historically, over 19.9 years
containing 2008, 2011, 2015, 2018, 2020 and 2022**. Effect sizes here are
large — round 4's C4 moved max DD by ~3pp, two orders of magnitude above the
+0.012 the sleeve rounds were chasing — so unlike rounds 4-6 this question is
well-powered.

CANNOT: establish forward performance. Nothing here is a forecast and nothing
may be promoted (TUNING.md).

## THE TRAP THIS ROUND MUST NOT FALL INTO

A vol-targeted book holds less exposure on average, so it cuts drawdown
MECHANICALLY. Comparing it to a fully-invested book measures "holds less
equity", not "times vol" — the exact error round 7's counter-agent caught
(a 63/37 SPY/T-bill book beat B.5 on drawdown with no factors at all).

**PRIMARY BAR: every overlay is judged against a STATIC book with the SAME
AVERAGE EQUITY EXPOSURE**, computed from the overlay's own realized weight
path. The static control is the null. An overlay that beats a fully-invested
book but not its own matched control has demonstrated nothing.
Secondary (reported, never the headline): the same overlay vs the
fully-invested book, and vs 60/40 SPY/AGG.

## Part A — the thesis, descriptive, no strategy

Window 2006-10-05→2026-08-19, FMP dividend-adjusted lane (round 7's, cross-
validation gate re-run). Subject: SPY, plus B.5-T1 and the 63/37 book.

- **A1 regime persistence.** Regimes = terciles of trailing 20d realized vol,
  thresholds from an **EXPANDING** window (using full-sample quantiles is
  look-ahead and is forbidden). Report P(low→low) and P(high→high) at 1 day
  and 5 days, with Wilson intervals. The tweet asserts 74% and 81%; report
  what OUR data says at OUR registered thresholds, and state the sensitivity
  to the threshold choice (terciles vs quintiles vs a fixed 20%/80%).
- **A2 autocorrelation** of realized vol and |return| at lags 1-60, versus the
  same for signed returns (the direction/vol contrast the thesis rests on).
- **A3 forecast quality, walk-forward, no look-ahead.** One-day-ahead vol
  forecasts from GARCH(1,1) (refit annually on expanding history), EWMA
  (lambda 0.94), and trailing 20d realized. Score by RMSE and QLIKE against
  realized. If GARCH does not beat trailing-realized out of sample, that is
  the finding and Part B's GARCH arms are expected to add nothing.

## Part B — the overlay

Books: SPY, B.5-T1, 63/37 SPY/T-bill, and the live 30/70 blend (2016+ only,
reported separately — it cannot reach 2006).

- **V1** vol target 10% annualized, trailing-20d estimator, deleverage-only
  (cap 1.0), monthly rebalance. The round-4 C4 rule, now over 20 years.
- **V2** V1 with daily rebalance. (Isolates rebalance frequency; costs bite.)
- **V3** V1 with the GARCH(1,1) conditional forecast as the estimator.
- **V4** V1 with the EWMA(0.94) estimator.
- **V5** V1 at targets 12% and 15%. (Target sensitivity.)
- **V6** V1 allowing leverage to 1.5x. (Tests whether the gain is downside
  scaling or upside participation.)
- **V7** vol-scaled REBALANCE BANDS: band width proportional to current vol
  estimate, on the existing 30/70 and B.5 band rules. Casey's "rebalancing"
  question, distinct from sizing.
- **V8** inverse-vol weighting between the risky book and cash, monthly.

## Costs — not optional this round

Daily vol targeting turns over materially. Report realized annual turnover
for every arm, and score every arm at BOTH 5 bps and 20 bps per side. An arm
whose edge does not survive 20 bps is reported as cost-fragile.

## Judgment protocol

Carried from rounds 4-7: both Sharpe bases (BIL-excess ADJUDICATES — round 7
ruled rf=0 must not be scored), standard Sortino, paired block bootstrap (21d
blocks, 4000 draws, seed 20260822) on the DIFFERENCE vs the matched-exposure
control, the round-7 named regimes (GFC / recovery / COVID / 2022 / 2020-26)
with max DD and recovery time, max-T multiplicity over this round's arms, no
post-hoc amendment, "nothing survives" is a valid finding.

SURVIVES = beats its MATCHED-EXPOSURE control on Sharpe AND Calmar over the
full window, with a bootstrap 95% CI on ΔSharpe excluding zero, in >=3 of the
5 named regimes, and still at 20 bps costs.

## Honest prior, recorded in advance

Vol targeting reliably improves drawdown and Calmar and rarely improves
Sharpe once exposure is matched; the literature's Sharpe gains are largest in
equity indices and shrink in diversified books. GARCH usually beats trailing
realized on QLIKE by a modest margin that often does not survive into
strategy P&L. The prior is therefore: **Part A confirms clustering; Part B
improves drawdown at matched exposure but does NOT clear the Sharpe bar**, and
the daily arms lose their edge at 20 bps.
