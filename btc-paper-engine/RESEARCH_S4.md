# S4/S5 strategy search — 14.5-year lab results (2026-07)

**Mandate**: find superior strategies beyond S1-S3 ("test many variants and
loop until better"). **Protocol** (anti-overfit): Bitstamp 4h, 2012-2026
(31,920 bars, five regimes). TRAIN 2013-2021 → VALIDATE 2022-2024H1 →
HOLDOUT 2024-07..2026-07 touched ONCE by two pre-registered champions.
Market entries, 6 bps/side, 1x compounding. Families: F1 Donchian breakout +
chandelier trail (9 cfgs) · F2 SMA-cross trend (9) · F3 gated RSI reversion
(6) · F4 volatility-squeeze breakout (4) · F5 = current pullback as baseline.

## The result that matters — the regime matrix

| Strategy | 2013-2021 | 2022-24H1 | 2024-26 (holdout) |
|---|---|---|---|
| **Pullback (S1-S3 signal)** | **−81%** (dead, all eras) | **+79%**, MAR 1.5, n=101 | **+43%**, MAR 1.4, n=89 |
| Donchian-20 / trail-5 | +390k%, MAR 3.2 | +205%, MAR 2.2 | **+12%, DD −44%**, MAR 0.1 |
| Donchian-55 / trail-4 | +12.5k%, MAR 1.0 | +203%, MAR 2.1 | **−20%** |
| Buy & hold | +356k% | +30% | −1% |

Monthly-return correlation, trend vs pullback (holdout): **−0.15**.

Also tested and rejected: F3 RSI reversion (negative everywhere), F4 squeeze
(TRAIN MAR up to 4.3, VALIDATE ≤0.9 and sign-flips — early-era artifact),
F2 SMA-cross (TRAIN MAR ≤0.8, no stable plateau).

## Readings

1. **There is no regime-free champion.** Trend-following owned 2013-2024 and
   died in the 2024-26 range market; the pullback is the mirror image. Any
   "loop until superior" search inside one window just picks the strategy
   that matches that window's regime — which is how the original 2-year
   research found the pullback and missed that it was dead 2013-2021.
2. **The pullback is better-supported than its 2-year provenance suggested**:
   ~190 trades across 2022-2026 with MAR 1.4-1.5 through three distinct
   sub-regimes (2022 bear, 2023-24 recovery, 2024-26 round trip). Its
   pre-2022 failure is consistent with early-era BTC (thin, violently
   trending) being a different instrument than modern BTC.
3. **The honest improvement is a portfolio, not a replacement.** Donchian-20/
   trail-5: 12 years of validated trend edge, currently dormant, corr −0.15
   to the pullback. Running it small alongside the pullback books buys the
   coverage the pullback lacks: a sustained bull or collapse — the pullback's
   explicitly untested regime — is exactly where the trend book prints.

## Recommendation

- **S4 = Donchian-20 breakout, 5×ATR chandelier trail, 1x notional** — the
  diversifier. Expect small losses in chop, large wins in sustained trends.
  Judge it ONLY as a portfolio member (its holdout standalone is poor and
  that is priced in), and on ≥12 months of live data.
- **S5 = 50/50 risk blend of S1 + S4** (rebalanced monthly) — the portfolio
  expression; the book that should have the best MAR if the corr estimate
  holds.
- Do NOT replace S1-S3; do not add F3/F4; do not re-tune the pullback.
- Revisit trigger: if BTC enters a confirmed trend regime (e.g. 26-week
  channel breakout) and S4 still isn't earning after 20+ trades, retire it.

*Selection-bias note: ~28 configs examined here on TRAIN+VALIDATE; holdout
touched once by two pre-registered champions. Fewer trials than the original
research (~1,500), longer data, and the champions' holdout FAILURE is
reported rather than hidden — that failure is the finding.*
