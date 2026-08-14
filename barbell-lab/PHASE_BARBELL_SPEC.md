# Phase-aware allocation engine — pre-registered spec

Registered 2026-08-11, BEFORE any backtest result was computed. The
allocation mapping, phase rules, data tiers, and metrics below are frozen;
if the results later motivate changes, that is a NEW study with this one's
results reported alongside. Origin: Zeberg "phase-aware portfolio"
screenshot — his own fine print ("zone labels use revised data — not a
live track record") is the pitfall this design exists to avoid.

## Claim under test

Using ONLY real-time-computable phase labels (expanding-window z-scores,
publication-lagged inputs, one label per month, no revisions), a
phase-driven stocks/bonds/cash(/gold) allocation delivers materially
shallower drawdowns than buy-and-hold equities with comparable long-run
CAGR — i.e. a Sharpe/sequence-risk edge, NOT a return-alpha claim.

## Phase engine

Phases and thresholds are EXACTLY the shipped cycle tracker's
(`treasury-canary/backend/app/sources/business_cycle.py::phase_of`):
CONTRACTION coin<-0.75 · SLOWDOWN coin<0 & lead<-0.3 · STALL coin<0 ·
LATE_CYCLE lead<-0.5 · EXPANSION otherwise. No re-tuning for this study.

Data tiers (dimension availability is an era property, disclosed per era):

- **Tier C, 1960→now (full)**: the 4 coincident + 6 leading members as
  shipped.
- **Tier B, ~1934→1959 (synthetic era)**: the members that existed —
  INDPRO growth (1919→), PAYEMS growth (1939→), curve = Shiller long rate
  minus TB3MS (1934→; NBER-macrohistory commercial paper if it extends
  the short rate earlier), CPI yoy, SPX 12m momentum. Composite = mean of
  available member z's; phase thresholds unchanged. Expanding-z warmup
  may use Z_MIN=90 months for this era (disclosed) so labels exist by the
  mid-1930s.
- Pre-1934 (Tier A) is OUT OF SCOPE for the headline: too few live
  dimensions to call a phase honestly. If shown at all, it is labeled
  exploratory.

Labels are computed at month-end t using data with a 1-month publication
lag (series value for month t-1 is the latest usable at t). Allocation
changes take effect at the NEXT month's open. The treasury-canary nowcast
is NOT used in the historical tiers (it cannot be reconstructed pre-1967
claims data); a nowcast-triggered variant may be reported as a secondary
line for 1970→ only.

## Asset return series

- **Stocks**: S&P 500 TOTAL return (Shiller price + dividends, monthly).
- **Bonds**: synthetic 10y constant-maturity total return from the
  Shiller/GS10 yield series via the standard approximation
  (yield/12 + duration-adjusted price change from yield moves).
  This is the "synthetic look-back": validated 1962→ against actual
  10y total-return data before use (correlation and CAGR gap reported);
  if validation fails (corr < 0.95 or CAGR gap > 50bp/yr) the study
  starts where real data starts instead.
- **Cash**: 3m T-bill (TB3MS), monthly compounding; commercial-paper
  splice pre-1934 if used.
- **Gold**: post-1971 ONLY (convertibility). In pre-1971 months any gold
  weight is reassigned to cash. Source: LBMA/datahub monthly.

Costs: 10bp one-way on every rebalance trade (conservative for index
exposure); monthly rebalance to target.

## Allocation mapping (frozen)

Risk slider r in {0.5 defensive, 1.0 balanced (headline), 1.5 aggressive}
scales the equity weight around the balanced row; bonds absorb the
difference; gold/cash rows fixed.

| phase       | stocks | bonds | gold | cash |
|-------------|--------|-------|------|------|
| EXPANSION   | 70     | 20    | 5    | 5    |
| LATE_CYCLE  | 55     | 30    | 10   | 5    |
| STALL       | 45     | 35    | 10   | 10   |
| SLOWDOWN    | 30     | 45    | 15   | 10   |
| CONTRACTION | 20     | 50    | 15   | 15   |

(Balanced row chosen a priori from the cycle literature's usual shape —
equity glide from ~70 to ~20 across the cycle. NOT optimized; the point
is whether the LABELS carry information, not whether the weights are
optimal. A weight-sensitivity table is reported but never headline.)

## Benchmarks & metrics

vs 100% S&P total return and monthly-rebalanced 60/40. Metrics per the
barbell-lab stack: CAGR, max drawdown, Sharpe (arith, rf=TB3MS), Ulcer
index, worst-36m window, and per-era splits (Tier B alone, Tier C alone,
1970→, 2000→, 2020→). Deflated Sharpe via `barbell.stats.dsr` with
trials=1 (mapping frozen) but risk-slider variants counted as 3 trials.

## Pre-committed honesty items

- The 2023–2026 stretch will show the strategy defensively positioned
  through a strong equity run (the cycle model's known over-prediction
  streak). Reported prominently, not buried.
- Phase labels use revised historical DATA (vintage series are not
  available back to the 30s) even though the z-window is real-time in
  shape. This overstates live performance by an unknown amount; the
  2023–2026 live-ish period is the closest thing to a vintage test.
- Synthetic bond returns are a model, not an index; the validation gap
  vs real data 1962→ is reported.
- Gold pre-1971 does not exist as an asset here.

## Ship gates

Merge-blocking: bond-synthesis validation bounds; mapping matrix
reproduced from spec by test; label parity with treasury-canary
`phase_of` on the overlapping era; no-lookahead test (allocation at t
uses labels from t-1's data only); cost application test. Counter-agent
panel BEFORE results are presented.
