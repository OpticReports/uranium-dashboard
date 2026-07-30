# Rate Shock study — long-yield moves × stock-bond hedge regime (2026-07)

Question from the user: "as yields rise people sell stocks to buy bonds —
how does a rising 20y/30y affect recession odds and stock prices, and are we
tracking it?" This study answers it with the same discipline as the margin
work: pre-registered rules, one evaluation, frozen stats, bootstrap evidence.

## Method (pre-registered before any forward return was computed)

- Long yield: DGS30 (1977-02+) spliced with DGS20 across the 2002-02..2006-02
  30y discontinuation. Shock d60 = change over 60 trading days.
  SPIKE ≥ +75bp · PLUNGE ≤ −75bp · NEUTRAL otherwise.
- Regime: rolling 60d Pearson corr of daily S&P returns vs bond-price returns
  (−Δy10). POS ≥ +0.2 (bonds NOT hedging stocks) · NEG ≤ −0.2 (hedge intact)
  · MIXED otherwise. Same sign convention as the dashboard's corr tile.
- 2,480 weekly obs (every 5th S&P trading day) 1977-05..2026-07. Forward S&P
  +21/63/252 trading days; recession odds = any USREC month within 12 months.
- Bootstrap: episode-level (35-day gap rule), 2,000 resamples, on fwd-12m
  pct-positive vs the 79% baseline; BH-FDR q=0.10 across the 9 matrix cells.

## Results (baseline: rec-within-12m 21% · fwd12m +12.0% med / 79% pos / −46.3 worst)

| cell | wk / eps | rec-12m | fwd12m med (%pos) | worst | verdict |
|---|---|---|---|---|---|
| SPIKE (all) | 151 / 24 | **44%** | +12.1 (64%) | **−16.9** | recession signal, NOT a stock signal |
| SPIKE × POS | 112 / 15 | 47% | +11.5 (62%) | −16.5 | p=0.21 — not significant for stocks |
| SPIKE × NEG | 7 / 2 | 71% | +42.7 (100%) | +19.2 | FDR-pass but 2 Volcker episodes — ignore |
| PLUNGE (all) | 154 / 22 | 32% | **+22.1 (97%)** | −25.0 | the validated signal |
| **PLUNGE × POS** | 102 / 13 | 25% | **+21.2 (100%)** | **+0.1** | VALIDATED p<0.001, FDR-pass |
| PLUNGE × NEG | 32 / 7 | 38% | +25.1 (97%) | −2.8 | validated p=0.029, FDR-pass |
| PLUNGE × MIXED | 20 / 6 | **60%** | +13.8 (85%) | −25.0 | ns; plunge here is often the recession arriving |
| NEUTRAL × POS | 837 / 44 | 16% | +12.6 (84%) | −23.7 | baseline-like (today's cell, 2026-07) |
| NEUTRAL × NEG | 837 / 28 | 24% | +10.9 (74%) | −46.3 | baseline; the deep tails (2008) lived here |

## The two findings

1. **Rate spikes are a recession signal, not a stock-sell signal.** +75bp/60d
   on the long bond doubled 12-month recession odds (44% vs 21%; 47% in the
   no-hedge regime). But forward stock returns after spikes ran near baseline
   with MILDER worst cases (−17% vs −46%): the great crashes started from
   calm-rate weeks, not spike weeks. Mechanically selling equities on a yield
   spike had no historical support — the folk model fails its own backtest.
2. **Yield plunges are the validated equity buy.** −75bp/60d of rate relief in
   the no-hedge regime: S&P higher 12 months later in 102 of 102 weeks across
   13 episodes (worst +0.1%) — the strongest validated cell in any canary
   study. Exception that proves the rule: a plunge in a MIXED regime carried
   60% recession odds — sometimes the plunge IS the recession arriving; read
   it jointly with the curve canary.

## Honesty box

Overlapping weekly windows — episode counts are the honest n. SPIKE × NEG is
a 2-episode Volcker artifact and is labeled "ignore" in the product. The
recession-odds column is descriptive conditioning, NOT the recession model
(the curve-based model remains the validated predictor). Thresholds (±75bp,
±0.2 corr) chosen by judgment to be round, one evaluation, no sweep —
selection-adjacent, same standing as the other panels. Shipped: /rates/shock
endpoint (frozen stats + auto-written summary + live state) and the Rate
Shock panel beside the flow/correlation section; verdicts render as evidence
lines. Study script: scratchpad rate_shock_study.py; frozen output
fast_study_cache/rate_shock.json.
