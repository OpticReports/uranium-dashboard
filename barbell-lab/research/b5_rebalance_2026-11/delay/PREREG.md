# PREREG — B.5 rebalance fill-delay (k-day wait after trigger), long-history test

Status: FROZEN before any data pull or return computation (2026-11-16).
Nothing below may change after the first data pull; any deviation is logged
in a DEVIATIONS section with its reason, and the result is then labeled
"deviated from prereg".

## 0. Origin and claim under test
- Prior short-sample study (2013/2017/2020 starts, 10-17 rebalance events):
  B.5, +/-20% relative band checked daily; filling k=3-5 trading days after
  the breach beat k=1 by 14-41 bps/yr in-sample. 12-month-block bootstrap:
  nothing. Status: candidate edge, NOT usable.
- Live today: month-end check, full rebalance to target, fill next trading
  day (k=1). Live weights (B.5 v1.2 without CAOS): AVUV .235, PHYS .235,
  QUAL .153, KMLM .141, AVDV .118, AVEM .059, TAIL .059.
- **H1**: filling k in {3,4,5} trading days after the trigger beats k=1,
  net of costs. **H0**: no difference (two-sided reported, one-sided H1 tested).
- Mechanism to be checked (not assumed): short-term momentum after a breach
  (winners keep rising / losers keep falling for a few days) would make
  delay pay; short-term reversal would make it cost.

## 1. Mechanics (fixed for all runs)
- Daily total returns, close-to-close. Holdings drift with returns between fills.
- Trigger day t is known at t's close. Fill at close of t+k (trading days).
  k=0 = same-close fill (optimistic, reported only as a bound); **k=1 = baseline**.
- Fill = full rebalance to target weights.
- While a fill is pending, new triggers are ignored. If the band un-crosses
  during the wait, the fill STILL executes (primary). "Cancel-if-uncrossed"
  is a reported sensitivity, not tested for the pass bar.
- Costs: 5 bps per side on traded notional (primary); 2 and 10 bps sensitivity.
  Analogue sleeves carry no ETF expense ratio (equal across k, cancels in the diff).
- Start: equal to target weights on the first common date of the universe.

## 2. Test families
- **k grid**: 0,1,2,...,10. Primary contrasts: k=3,4,5 vs k=1. Secondary
  (descriptive + Holm across all 10 non-baseline k): every k vs k=1.
- **Trigger families** (each run separately):
  - T-D (daily check): any sleeve with |w/w* - 1| > 0.20 at a close.
  - T-M (month-end, LIVE rule): last trading day of each month, unconditional
    full rebalance. Delay k lands on trading day k of the next month.
  - T-MB (month-end, band-gated): month-end, rebalance only if the 20%
    relative band is breached. Reported, not part of the pass bar.
- Confound noted in advance: T-M delays move fills across the
  turn-of-month window; a T-M result is reported with the T-D result
  beside it so a turn-of-month effect is not read as a breach effect.

## 3. Data (free, long, independent of the 2013+ ETF sample)
Universe A = B.5 asset-class analogues, same weights as live.

| Sleeve | Analogue | Source | Starts |
|---|---|---|---|
| AVUV .235 | US Small-Value (Small/High B/M of 6 size-B/M, value-weighted) | Ken French library, daily | 1926-07 |
| AVDV .118 | Developed ex-US Small-Value (Small/High of 6 size-B/M) | Ken French, Developed ex US, daily | 1990-07 |
| AVEM .059 | Emerging Markets value-weighted market (or Big/High if market not available) | Ken French, Emerging, daily | ~1989-07 |
| QUAL .153 | US Big/High operating profitability (6 size-OP portfolios) | Ken French, daily | 1963-07 |
| PHYS .235 | Gold spot, LBMA PM fix (USD) | LBMA (or a stated mirror of it); splice to GLD/PHYS only for dates the fix is missing, flagged | 1968-04 |
| KMLM .141 | Rule-based TSMOM built from long series (below); KMLM itself used only to check correlation on the 2021+ overlap | constructed | ~1973 |
| TAIL .059 | Cash: French daily RF (primary). CBOE PPUT minus SPX-TR as a protection overlay, sensitivity only, if obtainable | French; CBOE | 1926 / 1986 |

- KMLM analogue (fixed now): 4 markets — US equity (French Mkt total return),
  US 10y Treasury (total return built from FRED DGS10 constant-maturity
  yield, duration approximation), gold (LBMA), USD (FRED broad dollar index,
  DTWEXB spliced to DTWEXBGS). Signal = sign of trailing 252-day excess
  return, each leg scaled to 10% annualized vol (60-day EWMA, lagged one
  day), legs equally weighted, monthly signal update, plus cash RF.
  Repo's ASFYX splice (barbell-lab; flagged there as "indicative only"
  pre-2020) is a sensitivity only, from 2010.
- Universe A primary window: first date all seven sleeves exist (~1990-07)
  to latest available. ~36 years.
- Universe A-long (sensitivity, not pass bar): 1973+ with AVDV/AVEM weight
  folded into the US small-value sleeve.
- **Universe B (independent check)**: 40% US equity market (French Mkt
  total return) / 40% US 10y Treasury total return (from DGS10) / 20% gold
  (LBMA). Window 1968-04 to latest. ~58 years. Same band (+/-20% relative),
  same k grid, same trigger families.
- Independence: the 2013+ segment overlaps the discovery sample. The
  pre-2013 segment of each universe is reported separately as the clean
  out-of-sample test.
- MISSING DATA RULE: if any primary source (French daily files, LBMA fix,
  FRED DGS10/DTWEX) cannot be fetched or parsed, STOP and report; do not
  substitute a different series silently.

## 4. Metrics and significance
- **Primary metric**: CAGR(k) - CAGR(1), net of costs, k in {3,4,5}, in bps/yr.
  Also reported: Sharpe, max drawdown, turnover, cost drag, event count.
- **Per-event test (primary inference)**: for each trigger event e, start
  from the same pre-trigger holdings and compute portfolio log return over
  [t+1, t+11] under fill-at-k vs fill-at-1 (both net of costs). d_e = diff.
  Test mean(d_e) > 0 with a sign-flip permutation test (100,000 flips,
  seed 20261116); t-stat and Wilcoxon reported alongside. Event count
  reported per cell.
- **Bootstrap**: moving-block bootstrap of the joint daily asset-return
  matrix, 12-month blocks (252 trading days), 10,000 resamples, seed
  20261116; full strategy rerun for k and k=1 on each resample; 95%
  percentile CI of CAGR(k) - CAGR(1).
- **Multiple testing**: Holm across k=3,4,5 within each (universe, trigger
  family, half) cell for the primary family; Holm across the full 10-k grid
  for the secondary family.
- **Placebo 1 (random trigger dates)**: same number of events, dates drawn
  uniformly from non-trigger days (>= 11 days from any real trigger), same
  k vs 1 contrast; 1,000 draws. Real effect must exceed the placebo 95th pct.
- **Placebo 2 (random delays)**: each event gets k drawn uniformly from
  1..10; 1,000 draws. Real k=3-5 effect must exceed the placebo 95th pct.
- **Mirrored check**: split events by the breaching sleeve's direction —
  up-breach (overweight, delay = keep selling winner later) vs down-breach
  (underweight, delay = buy loser later). Report mean d_e and CI per side.
  Momentum predicts delay helps on BOTH sides; reversal predicts it hurts
  on both. One side only = asymmetry, reported as its own candidate edge
  (per EDGE rule), not as a pass of H1. (T-M: direction = sign of the
  largest-|drift| sleeve.)

## 5. Pass bar (all must hold, per trigger family)
For at least one k in {3,4,5}, the SAME k in every cell:
1. Per-event Holm-adjusted p < 0.05, AND
2. Bootstrap 95% CI of CAGR diff excludes 0 (lower bound > 0), AND
3. Holds in BOTH universes (A and B), AND
4. Holds in BOTH halves of each universe (split at the midpoint date), AND
5. Sign positive in the pre-2013 segment of each universe, AND
6. Beats both placebos' 95th pct, AND
7. Mirrored check: same sign on up- and down-breaches, AND
8. >= 30 events in every cell; a cell with < 30 events = underpowered = fail, AND
9. Net effect >= 10 bps/yr at 10 bps/side cost (economic floor).
Any failure -> **NOT PROVEN**. The adoption decision is made on T-M (live
rule); T-D is supporting evidence only.

## 6. What keeps monthly next-day (k=1) as is
- NOT PROVEN under section 5 (default outcome expected given the prior
  bootstrap) -> keep month-end check, full rebalance, fill k=1.
- k=1 or k=0 significantly beats k=3-5 -> keep k=1 and record delay as refuted.
- Passes on T-D only, not T-M -> keep k=1 on the live monthly rule; delay
  would matter only if the operating rule moves to daily band checks (a
  separate decision).
- Passes with effect < 10 bps/yr, or sign flips between halves/universes
  -> keep k=1.
- PASS on T-M -> proposal only: counter-agent review, then change lands on
  Composer and the IBKR mirror (approved fixtures) together with a parity
  check, before it counts as done.

## 7. Reporting (fixed now)
- Table: universe x trigger family x half x k: CAGR diff, CI, Holm p,
  event count. Charts: CAGR diff vs k (0..10) with CIs per universe;
  equity curves k=1 vs best k (log); per-event d_e distribution split
  up/down-breach; placebo histograms with the real value marked.
- Caveats: analogues are not the ETFs (KMLM/TAIL proxies weakest); close
  fills, no intraday slippage; cost model flat bps; in-sample numbers are
  not a forecast.
- Counter-agent review of code and numbers before results are presented.
