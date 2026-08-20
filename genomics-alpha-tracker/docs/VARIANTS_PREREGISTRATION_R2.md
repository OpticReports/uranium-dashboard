# Variant campaign — ROUND 2 pre-registration, 2026-08-20

Registered BEFORE any round-2 variant is run. Round 1
(VARIANTS_PREREGISTRATION.md → BACKTEST_VARIANTS_10Y.md, counter-agent PASS
WITH CORRECTIONS, all applied) established with prior-close gates: V2 (200dma
gate) $261,677 / +9.48% / 33.7% DD / 0.58 Sharpe; V6b (50dma-gated momentum)
$733,261 / +20.64% / 50.1% DD / 0.73 Sharpe; SPY 0.89 Sharpe still unbeaten.
Round-2 variants are motivated ONLY by round-1 results and its counter-agent
findings. Same anti-data-mining contract as round 1.

## Judgment protocol (same as round 1, restated baselines)

- Dollar book $100k, risk 1% of current equity per call where applicable,
  daily MTM, rf = 0 except where a variant IS the cash-yield fix, prior-close
  gates everywhere (the round-1 counter-agent convention).
- Full period 2016-2026 + the same three sub-periods.
- SURVIVES = Sharpe AND Calmar beat BOTH baselines (V0 and restated V2) over
  the full period AND in >=2 of 3 sub-periods. The bar is deliberately higher
  than round 1: round 2 must beat the best clean survivor, not the broken
  baseline.
- Multiple comparisons: 5 variants; consistency is the bar; no
  re-parameterization after seeing results.

## Registered variants

- **R2-A** V2 gate (200dma, prior-close) + V10 trailing exits (3.0xATR trail
  from prior-bar peak close, ATR14 recomputed, 90d time stop) on the combined
  live-flag fires. Motivation: the two cleanest DD reducers of round 1,
  independently surviving; the combination is untested.
- **R2-B** Momentum book top-10 (instead of top-5), monthly, 50dma prior-close
  gate, tier A/B. Motivation: round-1 counter-agent flagged 5-name
  concentration as untradeable; breadth is the standard fix.
- **R2-C** Momentum book top-5, 50dma gate, with a POINT-IN-TIME liquidity
  floor replacing today's tiers: trailing 60d median dollar volume >= $2M
  computed from bars as of each rebalance. Motivation: removes the tier
  hindsight the counter-agent quantified (direction: the hindsight filter
  COST ~3pp CAGR, so this is honesty, not flattery).
- **R2-D** Cash yield realism: V2 and V6b re-run with idle cash earning the
  BIL ETF's total return (2016-2026, adjusted closes; where BIL data is
  missing, 3-month T-bill proxy at a flat 2.0% with the substitution dated
  and flagged). Motivation: rf=0 understates gated books (counter-agent
  minor); this measures by how much. Judged for reporting honesty — a
  realism restatement of survivors, not a new strategy (SURVIVES column
  n/a).
- **R2-E** Momentum book top-5, 200dma prior-close gate (round 1's V6b used
  50dma per its contract; the 200dma gate was round 1's cleanest DD
  mechanism). Motivation: cross the two strongest round-1 components.

## Fixed parameters (not tunable this round)

Top-10; $2M PIT floor; BIL/2.0% proxy; 200dma. Refinements require a round-3
registration.
