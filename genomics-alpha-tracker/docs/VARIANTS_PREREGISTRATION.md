# Variant campaign pre-registration — 2026-08-20

Registered BEFORE any variant was run (the anti-data-mining contract for this
campaign; see TUNING.md for why this exists). The 10y replay (BACKTEST_CALLS_10Y.md)
found the combined book ≈ sector beta (7.2% CAGR / 65.5% maxDD / 0.42 Sharpe at
1% risk-per-call vs XBI 9.2%/63.9%/0.43 and SPY 15.4%/33.7%/0.80). The desk's
mandate: raise CAGR, cut drawdown. Every variant below is motivated by evidence
that existed BEFORE this campaign; nothing may be added or re-parameterized
after results are seen — follow-up ideas go to a NEXT round's registration.

## Judgment protocol (fixed)

- Full period 2016-01-01 → 2026-08-19 AND three sub-periods: 2016-2019,
  2020-2022, 2023-2026(Aug). Dollar book: $100k, risk 1% of current equity per
  call (variants may alter sizing only where that IS the variant), daily MTM on
  adjusted closes, exits at r_net (tiered slippage), rf = 0.
- A variant SURVIVES only if it improves BOTH Sharpe and Calmar vs V0 over the
  full period AND in at least 2 of 3 sub-periods.
- Benchmarks SPY and XBI reported in every table. Multiple-comparison caution:
  11 variants — one full-period winner alone is noise; consistency is the bar.
- Survivors become HYPOTHESES.md entries / TUNING proposals — never direct
  config changes (TUNING.md law).

## Registered variants

Motivations cite pre-existing evidence only.

- **V0** baseline: combined live-flag-type book, ≤10 open (BACKTEST_CALLS_10Y).
- **V1** V0 + entries only while XBI > 50dma (motivation: the 10y regime table —
  every live-set signal decays below the 50dma).
- **V2** V0 + entries only while XBI > 200dma (slower gate, fewer whipsaws).
- **V3** V0 + per-position XBI hedge: short equal notional XBI opened/closed
  with each call (motivation: signals are XBI-EXCESS positive in the flag
  framing; hedging converts excess into absolute return).
- **V4** V1 + V3.
- **V5** rel_strength_60d fires only, ≤10 open, + 50dma regime gate
  (motivation: the only CI-cleared signal × the regime table).
- **V6a/V6b** cross-sectional momentum book: monthly rebalance, long the top-5
  names by 60-bar return vs XBI (liquidity tier A/B only), equal weight, no
  stops; V6b adds the 50dma regime gate (in cash when off). Motivation:
  rel_strength's edge is cross-sectional momentum; the rank-portfolio form is
  the literature-standard implementation and BACKTEST_SIGNALS.md supported RS.
- **V7** V0 + confluence: entry only when ≥2 DISTINCT replayable flag types
  fire on the name within 5 trading days (motivation: the live confidence
  model's corroboration bonus, pre-existing in calls.yaml).
- **V8** V0 with max_open 5 (motivation: 3,872 fires were skipped at the cap —
  tests whether marginal fires dilute).
- **V9** V0 + portfolio vol targeting: scale risk fraction daily to target 20%
  annualized book vol from trailing 20d realized (motivation: pure DD
  mechanics; changes sizing only).
- **V10** [EXPLORATORY — different exit engine, highest overfit risk, flagged]
  rel_strength fires, 3.0xATR TRAILING stop from peak close, no profit target,
  90d time stop, ≤10 open, 50dma gate. Motivation: the 2y exit grid found wide
  stops dominate and slippage kills tight ones; trailing preserves that while
  letting winners run. Graded with a bar-walking exit consistent with
  grade_call's open-first conventions.

## Fixed parameters (not tunable this round)

50dma/200dma as-is; top-5; 5-day confluence window; 20% vol target; 3.0xATR
trail; 90d time stop. If any of these looks "almost good", the ONLY allowed
action is registering a refined variant in a future round.
