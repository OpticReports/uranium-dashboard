# PREREG — CAGR study (2026-09-28)

Registered BEFORE any candidate below was run, per RESEARCH_PROTOCOL.md §5.
Nothing in this file is edited after the first candidate result; failures
are recorded in RESEARCH_CAGR.md, not removed from here.

## Mandate (Casey, 2026-09-28)

"Improve the trading engine CAGR" and "find the largest trade size setting
possible with $100k that won't blow up the book or violate the trade
strategy." Answers given to the clarifying questions:

- worst acceptable drawdown on the $100k: **−30%**;
- scope: **anything that holds up** (new signals, exits, legs, other perps)
  if it beats the current engine on data it was not tuned on;
- go-live: **brought to Casey for approval**, nothing ships on its own.

**§7 stopping rule.** RESEARCH_PROTOCOL.md §7 closes signal-space search
until the live gate concludes. Casey's scope answer reopens it. Recorded here
as his decision, not waived by me. Every candidate below is nonetheless
construction/portfolio-layer or a correctness fix except H4.

## Objective (fixed now)

Primary: **CAGR at k_safe** — full sample 2013-01..2026-07, where k_safe is
the largest sizing multiple with P(maxDD > 30% over any 2-year stretch) ≤ 10%
(stationary block bootstrap, mean block 180 bars, 1000 paths, seed 7). This
is KELLY.md's own drawdown criterion at Casey's −30%.
Robustness: per-era **Sharpe** at k = 1 (scale-free) on E1–E4.
Basis: mark-to-market equity; fees **4.32 bps/side** (measured on live
Hyperliquid fills); engine code path for every trade.

## Data and eras

Bitstamp BTC/USD 4h 2011-08..2026-09 (33,123 bars, zero gaps; identical to
the repo fixture on all 10,002 overlapping bars). ETH/LTC/XRP from 2016-12 to
2017-08. Eras: E1 2013–16, E2 2017–19, E3 2020–21, E4 2022–24H1,
E5 2024H2–26 (**SPENT** — swept 63× by the trail study, reported only),
E6 2026-08+ (2 months, reported only).

What each era is out of sample for: the pullback's parameters were fitted on
2024–26 (~1,500 trials), so E1–E3 are OOS for it and E4 is semi-OOS. The
donchian-20/trail-5 was chosen on TRAIN 2013–2021, so E1–E3 are IN-SAMPLE for
it, E4 was its validate era. **No era is clean for both legs.** Candidates
whose rule could have been written in 2013 without outcome knowledge are
judged fairly against that; the baseline's own fit only advantages the
baseline in its fit eras.

## DISCLOSURE — what I saw before registering

Before writing this file I ran the baseline and a per-leg, per-era
decomposition on the harness. It shows the trend leg positive in every era
(+135% E1 decaying to +2% E5) and the pullback leg deeply negative in E1–E2
(−22%, −33%) and positive from E3. **That knowledge biases me toward
trend-heavier constructions.** The decision rule below is written to not
reward hindsight: it requires per-era consistency, and the weighting rules
use volatility only, never returns.

## Hypotheses

**H1 — resting-stop trail (correctness).** Production `_process_donchian`
ratchets the trail from close(t) and then tests bar t's own low against it.
A resting venue stop cannot do that; btc-executor rests the stop at the
PREVIOUS published trail. Rule: test bar t against the trail set at
close(t−1), fill gaps at the open, then ratchet. No edge claimed — it is what
the venue does. Trials: **1**.

**H2 — leg weighting by risk, not dollars.** Two legs with negative
correlation (−0.07 full, −0.23 recent) and regime-dependent returns; a
dollar weighting fitted to one regime is a bet on that regime continuing.
(a) **Walk-forward inverse-vol**: each leg's weight ∝ 1/σ, σ = stdev of that
leg's per-bar unit-weight return over the 2,190 bars strictly before the
entry bar; total gross risk scaled to match the baseline's at k = 1.
(b) **Static 50/50 dollars.** No edge claimed; construction only. Trials: **2**.

**H3 — cross-asset trend, frozen parameters.** Time-series momentum is
documented across assets; the S4 rationale (slow diffusion, herding) is not
BTC-specific. Trend sleeve = donchian-20/trail-5, parameters FROZEN from BTC,
on every Bitstamp USD pair with 8+ years of history and a Hyperliquid perp:
BTC, ETH, LTC, XRP — chosen for history and venue, not outcome. Equal
inverse-vol weight within the sleeve; sleeve weight as the construction
dictates. Pullback stays BTC-only (the ETH transfer test failed, §10).
Trials: **1**. Evaluated on E2–E4 (alts start 2017).

**H4 — trend lookback ensemble.** Equal weight donchian 20/55/100, trail 5,
a standard CTA robustness construction; fixed a priori, no grid. Trials: **1**.

**H5 — the combination** of whichever of H1–H4 pass individually, evaluated
once. Trials: **1**.

Total this batch: **6** → registry ~2,521.

## Decision rule (per hypothesis, versus baseline)

Adopt-for-review iff ALL hold:
1. Sharpe ≥ baseline's in ≥ 3 of 4 eras E1–E4 (H3: ≥ 2 of 3, E2–E4);
2. no era in which Sharpe falls more than 0.25 below baseline's;
3. full-sample CAGR at k_safe strictly above baseline's;
4. independent counter-agent review finds no fatal defect.

E5 and E6 are reported and never decide anything. Ties break toward NOT
changing the live engine (RESEARCH_PROTOCOL.md §8).

## Retirement rule (if adopted)

Live realized drawdown past −20% within the first 90 days of a changed
engine, or its first 30 live trades showing a win rate more than 2 binomial
SE below the backtest's → revert to the engine as it stood 2026-09-28.
