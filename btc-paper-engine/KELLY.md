# KELLY.md — position-sizing study for S1–S6

Build (2026-08-04): empirical Kelly engine (`backend/app/engine/kelly.py`),
validation gates (`backend/tests/test_kelly.py`), `/kelly/compare` endpoint,
dashboard panel. Verifier checklist: see the amendments section at the end.

## Why not the web-calculator formula

The binary Kelly formula ((p·b − q)/b) assumes every trade is the same coin
flip. Real books produce a full return distribution — fat tails, skew,
clustered losses — so this engine maximizes the exact growth criterion on
the EMPIRICAL per-step equity returns: g(m) = E[log(1 + m·R)], where m is a
multiplier ON CURRENT SIZING (m = 1 is what runs today).

## Pipeline (n ≈ 60–150 trades per book)

1. Point estimate: numeric argmax of g(m), feasibility-guarded (no m that
   could have produced ≤ −100% on an observed step), capped at 4x.
2. Uncertainty: stationary block bootstrap (Politis–Romano, mean block 10,
   2000 draws) → sampling distribution of m*.
3. Shrinkage: recommendation = min(half-Kelly, bootstrap p10, c*·m*,
   largest m with P(maxDD > 30%) ≤ 10%), where c* = n·SR²/(n·SR² + 1) is
   the principled shrinkage fraction under mean-estimation error
   (Rising–Wyner / Baker–McHale form). Estimation error dominates at these
   sample sizes and over-betting destroys growth faster than under-betting
   gives it up (the g-curve is asymmetric), so the conservative envelope is
   the honest size.
4. Kill rule: if > 25% of bootstrap resamples say the edge is non-positive,
   the recommendation is forced to zero regardless of the point estimate.
5. Drawdown lens: P(maxDD > 20%/30%) at current size, the largest m that
   keeps those within a 10% probability budget, and Thorp's infinite-horizon
   analytic law (c_max = 2/(1 + ln p/ln(1−d)) of full Kelly) as an
   independent cross-check on the bootstrap answer.

## Results (2y replay window, closed trades, per-step equity returns)

| book | current | n | m* (growth-max) | boot p10–p90 | half-K | c* | m @ DD30 budget (analytic) | P(DD>20%) @ current | **recommended m** | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | pullback, vol-target 5.5% | 88 | 2.9x | 0.4–4.0 | 1.4x | 0.58 | 0.79x (0.77) | 87% | **0.38x** | oversized for a DD budget |
| S2 | pullback 1.95x | 88 | 2.7x | 0.5–4.0 | 1.3x | 0.65 | 0.67x (0.72) | 98% | **0.51x** | oversized |
| S3 | pullback 1x | 88 | 4.0x (cap) | 0.6–4.0 | 2.0x | 0.59 | 1.11x (1.07) | 40% | **0.60x** | modestly oversized |
| S4 | donchian | 58 | 0.5x | 0.0–2.3 | 0.3x | 0.08 | 0.48x (0.14) | 99% | **0.0x** | KILLED — edge not distinguishable from zero (34% of resamples non-positive) |
| S5 | blend 75/25 @1.5x | 146 | 3.5x | 1.0–4.0 | 1.8x | 0.64 | 0.94x (0.94) | 63% | **0.94x** | ~right-sized |
| S6 | blend 75/25 @2.0x | 146 | 2.6x | 0.7–4.0 | 1.3x | 0.64 | 0.70x (0.71) | 88% | **0.70x** | ~40% too hot |

The "m @ DD30 budget" column shows the bootstrap answer with Thorp's
infinite-horizon analytic value in parentheses — two independent methods
landing within a few hundredths of each other on every well-sampled book
(S1: 0.79 vs 0.77; S5: 0.94 vs 0.94) is the strongest internal-consistency
evidence in this study. S4's gap (0.48 vs 0.14) is itself diagnostic: the
analytic law assumes the point-estimate edge is real, and S4's isn't.

## What the numbers actually say

1. **The blends are the well-sized books.** S5 at 1.5x lands almost exactly
   on the recommendation (0.94x of current) — diversification between the
   pullback and trend legs is doing real work. S6's 2.0x is ~40% past the
   same budget: S6 ≈ S5's risk story with the dial turned past the line.
2. **The pullback books' realized drawdowns were not bad luck.** P(maxDD >
   20%) at current sizing is 40–98% across S1–S3 — the −22/−23% MTM
   drawdowns they actually printed are the EXPECTED cost of current size.
   If a ≤20–30% drawdown budget matters, these books are 1.5–2.5x too big.
3. **S4 standalone fails the sizing test outright** — the kill rule fires:
   34% of bootstrap resamples say its edge is non-positive (threshold 25%),
   so the honest standalone allocation is zero regardless of the 0.5x point
   estimate. Its value is as a DIVERSIFIER inside S5/S6 — the blend numbers
   price that correctly. Do not trade S4 alone at any size.
4. **Growth-optimal ≠ tradeable.** The raw m* of 2.6–4x on S1–S3/S5–S6
   says IF the last-2y edge is exactly real, bigger is faster — but with
   88–146 trades the edge cannot be known that precisely, and full Kelly at
   estimated parameters is systematically over-bet. The gap between m* and
   the recommendation IS the estimation risk.

## Honesty box

- One 2y window — the same window the strategies were selected on
  (multiple-comparison optimism baked in). Paper fills, 6bp round trip.
- Linear size-scaling approximation: stops/halts are defined in equity
  terms, so far-from-1 multipliers change path behavior in ways the
  multiplier model ignores. Recommendations are capped at 4x and read as
  guidance near current size, not as a leverage prescription.
- The engine never resizes anything by itself; it renders analysis on the
  dashboard. Any sizing change is an operator decision.

## Verifier reconciliation (independent research agent, 2026-08-04)

A second agent audited the engine design against the sizing literature
(Thorp 2006; Politis–Romano 1994; Rising–Wyner; Baker–McHale; MacLean–
Thorp–Ziemba; Busseti–Boyd; Bailey–López de Prado). Checklist outcome:

**Confirmed as built (no change needed):**
1. Empirical g(m) maximization over the binary formula — the binary form
   over-sizes fat-tailed streams by roughly 2x; correct call.
2. m as a multiplier on current sizing with per-trade compounding — exact
   for sequential books.
3. Stationary block bootstrap for estimation error — the right tool; at
   n ≈ 60–150 and these Sharpe ratios, SE(m*)/m* is on the order of 100%,
   which is exactly why the point estimate m* is never the recommendation.
4. Fractional-Kelly shrinkage + DD-constrained envelope + min() combination.
5. Feasibility/ruin guard and the 4x cap.
6. Seeded determinism (gate-testable).

**Amendments adopted this round:**
1. **Kill rule** — recommendation forced to 0 when >25% of bootstrap
   resamples show a non-positive edge. Effect: S4 flips from "possible
   negative edge" hedging to an explicit KILLED verdict (34% > 25%).
2. **c\* shrinkage term** — c\* = n·SR²/(n·SR² + 1) added to the min().
   Effect on this window: none binding (bootstrap p10 is tighter for every
   book), but it caps the recommendation if a future window produces a
   deceptively tight bootstrap.
3. **Analytic DD cross-check** — Thorp's infinite-horizon drawdown law
   published next to the bootstrap DD-constrained m. Agreement within a few
   hundredths on every well-sampled book (see results table).

**Known limitations accepted, stated for the record:**
- Streams are trade-close equity returns, so intra-trade adverse marks are
  invisible to the DD estimator — realized MTM drawdowns run ~1–4pp worse
  than trade-close DDs on these books. This biases the study TOWARD leniency,
  meaning the "oversized" conclusions would only strengthen on per-bar data.
  Per-bar MTM stream extraction is the natural next upgrade.
- No Deflated-Sharpe / multiple-comparison haircut: S1–S6 were selected on
  the same 2y window this study measures, so every recommendation is an
  UPPER bound on honest size.
- Books are ALTERNATIVES, not components: the recommendations are per-book
  standalone sizes and must never be stacked (running S3 at 0.6x AND S5 at
  0.94x simultaneously is double-counting the same capital and mostly the
  same trades).
- S5/S6 are sized on their exit-step blend streams — consistent with how
  the blends actually rebalance, but a per-bar joint simulation would price
  the diversification benefit more precisely.
