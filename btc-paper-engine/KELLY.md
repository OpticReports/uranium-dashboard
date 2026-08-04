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
3. Shrinkage: recommendation = min(half-Kelly, bootstrap p10, largest m with
   P(maxDD > 30%) ≤ 10%). Estimation error dominates at these sample sizes
   and over-betting destroys growth faster than under-betting gives it up
   (the g-curve is asymmetric), so the conservative envelope is the honest
   size.
4. Drawdown lens: P(maxDD > 20%/30%) at current size, and the largest m
   that keeps those within a 10% probability budget.

## Results (2y replay window, closed trades, per-step equity returns)

| book | current | n | m* (growth-max) | boot p10–p90 | half-K | m @ DD30 budget | P(DD>20%) @ current | **recommended m** | verdict |
|---|---|---|---|---|---|---|---|---|---|
| S1 | pullback, vol-target 5.5% | 88 | 2.9x | 0.4–4.0 | 1.4x | 0.79x | 87% | **0.38x** | oversized for a DD budget |
| S2 | pullback 1.95x | 88 | 2.7x | 0.5–4.0 | 1.3x | 0.67x | 98% | **0.51x** | oversized |
| S3 | pullback 1x | 88 | 4.0x (cap) | 0.6–4.0 | 2.0x | 1.11x | 40% | **0.60x** | modestly oversized |
| S4 | donchian | 58 | 0.5x | 0.0–2.3 | 0.3x | 0.48x | 99% | **0.0x** | possible negative edge standalone |
| S5 | blend 75/25 @1.5x | 146 | 3.5x | 1.0–4.0 | 1.8x | 0.94x | 63% | **0.94x** | ~right-sized |
| S6 | blend 75/25 @2.0x | 146 | 2.6x | 0.7–4.0 | 1.3x | 0.70x | 88% | **0.70x** | ~40% too hot |

## What the numbers actually say

1. **The blends are the well-sized books.** S5 at 1.5x lands almost exactly
   on the recommendation (0.94x of current) — diversification between the
   pullback and trend legs is doing real work. S6's 2.0x is ~40% past the
   same budget: S6 ≈ S5's risk story with the dial turned past the line.
2. **The pullback books' realized drawdowns were not bad luck.** P(maxDD >
   20%) at current sizing is 40–98% across S1–S3 — the −22/−23% MTM
   drawdowns they actually printed are the EXPECTED cost of current size.
   If a ≤20–30% drawdown budget matters, these books are 1.5–2.5x too big.
3. **S4 standalone fails the sizing test outright** (recommendation 0: the
   bootstrap puts ≥10% odds on a negative edge; PF 0.9 on this window).
   Its value is as a DIVERSIFIER inside S5/S6 — the blend numbers price
   that correctly. Do not trade S4 alone at any size.
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
