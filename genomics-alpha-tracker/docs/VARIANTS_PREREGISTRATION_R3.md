# Variant campaign — ROUND 3 pre-registration, 2026-08-20

Registered BEFORE any round-3 variant is run. Baseline to beat: the 30/70
R2-A/SPY blend (daily-rebalanced mix, daily granularity: +15.89% CAGR /
29.3% maxDD / 1.02 Sharpe; H13). Round-3 variants are motivated by the
round-1/2 findings, the measured BIL uplift, the 10y per-flag expectancies,
and standard portfolio literature (TSMOM, risk parity, lever-the-better-
portfolio). Same anti-data-mining contract as rounds 1-2; counter-agent
review before anything is acted on.

## Judgment protocol

- Daily granularity throughout. $100k, rf = 0 except where a variant IS the
  cash-yield/leverage mechanic. Prior-close conventions for every signal
  (gates, TSMOM, vol estimates).
- SURVIVES = Sharpe AND Calmar beat the 30/70 baseline over the full period
  AND in >= 2 of 3 sub-periods (2016-2019 / 2020-2022 / 2023-2026).
- R3-F is a robustness MAP (no survival judgment); R3-G is validation (no
  survival judgment). Multiple comparisons now span three rounds (21 judged
  variants cumulative) — say so in the report.

## Registered variants

- **R3-A** 30/70 blend with R2-A idle cash earning BIL total return
  (bil_bars_raw.json; the R2-D mechanic applied to R2-A inside the blend).
- **R3-B** Vol-scaled sleeve weights: w_R2A,t = clamp(0.30 x (sigma_SPY,t /
  sigma_R2A,t), 0.15, 0.45), sigmas = trailing 60d realized (prior-close),
  weights updated monthly at the rebalance.
- **R3-C** Levered blend: 1.25x the 30/70 mix, financed at BIL + 150bps on
  the borrowed 25% (IBKR-margin realism), daily reset on the leverage ratio.
  Also report the leverage that matches SPY's 33.7% maxDD ex post (as a
  descriptive frontier point, not a judged variant).
- **R3-D** TSMOM core: the 70% SPY leg switches to BIL when SPY's trailing
  12-month total return (prior-close) is negative, checked monthly.
- **R3-E** Flag-tilted R2-A sizing: rel_strength fires at 1.25% risk,
  volume_anomaly at 0.75%, all other live-set flags at 1.0% (tilts fixed
  from the 10y per-flag expectancies, NOT fit this round), then 30/70 blend.
- **R3-F** [MAP] R2-A trail/time-stop robustness grid: trail in
  {2.5, 3.0, 3.5}xATR x time stop {60, 90, 120}d, all else fixed. Deliver
  the 3x3 surface of standalone R2-A Sharpe; the claim under test is
  plateau-ness, not a better cell. Any better cell goes to a future round.
- **R3-G** [VALIDATION] Stationary block bootstrap (mean block ~21 days,
  2,000 draws) of the 30/70 daily return series: distribution of 10y CAGR
  and maxDD; report the 5th/50th/95th percentiles of each.

## Fixed parameters (not tunable this round)

0.15/0.45 weight clamps; 60d vol window; 1.25x; 150bps margin spread; 12-1
monthly TSMOM; the tilt sizes; the 3x3 grid bounds; 21d expected block.
Refinements require a round-4 registration.
