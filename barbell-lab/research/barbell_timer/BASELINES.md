# BARBELL-TIMER Phase 1 — baselines, monthly 1975-02 -> 2026-07 (618 months)

Produced by `baselines.py` from the frozen fixtures; charts in `figs/`
(`fig1_equity_curves.png`, `fig2_drawdowns.png`, `fig3_rolling10y_spreads.png`).
GDE-synth is the Phase 0 validated model (see `VALIDATION_REPORT.md`:
conditional pass, ±1%/yr structural carry uncertainty pre-2007). These are
descriptive backtest statistics on a partly-modeled instrument — in-sample
history, **not forecasts**.

## Conventions (stated, per honesty rules)

- **Basis**: month-END total-return closes; portfolio rebalancing at month-end
  close. No signals exist in Phase 1; the repo's next-month-open execution
  convention binds Phases 2-3.
- **Sharpe**: arithmetic mean monthly excess return over bills (TB3MS) x 12,
  divided by std of monthly *excess* returns (ddof=1) x sqrt(12).
- **Sortino**: MAR = bills. Downside deviation = sqrt(mean over ALL months of
  min(0, r - rf)^2) x sqrt(12) (full-sample denominator convention).
- **MaxDD / underwater / Calmar / Ulcer**: month-end curve, intramonth-blind
  (bias sized below). Ulcer = sqrt(mean squared %-drawdown). Calmar =
  CAGR / |maxDD| over the full 51.5y (not the 36m convention).
- **SPX TR splice**: 1975-1993 = ^GSPC month-end price + Shiller dividend rate
  D/(12P) (dividends smeared; Shiller D is trailing-annualized — flagged);
  1993-02-> = SPY dividend-adjusted (9bp ER inside). Month-end convention
  throughout — the Shiller monthly-AVERAGE price convention is NOT used for
  returns (only its dividend rate), avoiding the averaging smear.
- **Gold splice**: 1975-02..1976-03 datahub monthly-AVERAGE London fix (14
  months, convention mismatch flagged); 1976-04-> GCUSD month-end.
- **GDE-synth**: 0.90 SPX_TR + 0.10 bills + 0.90 (gold - carry) - 25bp/yr
  (20 fee + 5 roll, held constant pre-2022 — counterfactual, the fund did not
  exist). Carry = TB3 - effective lease (schedule pre-2007; -0.40%/yr
  GDE-anchored 2007->). Carry drag by decade: VALIDATION_REPORT.md table.

## Master stats table

| Portfolio | CAGR | Vol | Sharpe | Sortino | MaxDD (m) | Longest UW | Calmar | Ulcer | Worst 12m | % pos m |
|---|---|---|---|---|---|---|---|---|---|---|
| B&H GDE-synth | 13.87% | 21.85% | 0.52 | 0.81 | -61.3% | 73 m | 0.23 | 16.7 | -46.8% | 59.1% |
| B&H SPY | 12.16% | 14.94% | 0.57 | 0.85 | -50.8% | 74 m | 0.24 | 12.0 | -43.4% | 63.8% |
| 25/75 GDE/SPY (M) | 12.88% | 15.29% | 0.60 | 0.91 | -47.7% | 62 m | 0.27 | 11.2 | -42.9% | 63.9% |
| 50/50 GDE/SPY (M) | 13.40% | 16.72% | 0.59 | 0.91 | -44.9% | 50 m | 0.30 | 11.3 | -42.6% | 61.2% |
| 75/25 GDE/SPY (M) | 13.74% | 19.00% | 0.56 | 0.87 | -52.5% | 63 m | 0.26 | 13.2 | -42.7% | 60.2% |
| 25/75 GDE/SPY (Q) | 12.83% | 15.31% | 0.60 | 0.91 | -48.1% | 62 m | 0.27 | 11.2 | -43.4% | 63.9% |
| 50/50 GDE/SPY (Q) | 13.34% | 16.76% | 0.59 | 0.90 | -45.4% | 50 m | 0.29 | 11.4 | -43.3% | 61.5% |
| 75/25 GDE/SPY (Q) | 13.69% | 19.03% | 0.55 | 0.86 | -52.2% | 63 m | 0.26 | 13.2 | -43.2% | 60.7% |
| Bills (TB3MS) | 4.23% | 0.94% | — | — | 0.0% | 0 | — | 0.0 | 0.0% | 100% |
| *[pessimistic carry]* B&H GDE-synth | 13.27% | 21.85% | 0.49 | 0.77 | -61.8% | 73 m | 0.21 | 17.4 | -47.2% | 59.1% |
| *[pessimistic carry]* 50/50 (M) | 13.11% | 16.73% | 0.57 | 0.88 | -44.9% | 53 m | 0.29 | 11.5 | -42.6% | 61.2% |

No Sharpe crosses the 1.2 tripwire (max 0.60); nothing here smells leaked.
Pessimistic carry = pre-2007 lease reduced 1pp (drag +1%/yr on the gold leg):
costs B&H GDE-synth ~0.60%/yr of CAGR, ranking of mixes unchanged.

**Readings.** (1) The prior study's headline survives monthly resolution:
static 50/50 already harvests most of the available improvement — best Calmar
(0.30), best/equal Sortino (0.91), shortest underwater (50 m vs 73-74 m for
either sleeve), maxDD -44.9% vs -61.3% / -50.8%, while giving up only 0.5%/yr
of CAGR vs B&H GDE-synth. (2) Monthly vs quarterly rebalancing is worth ~5bp
CAGR and moves nothing — rebalancing frequency is NOT a lever worth tuning.
(3) The 90/90 stack concentrates crash risk: worst months are Oct-2008 -31.6%,
Mar-1980 -26.6% (equity+gold correlation spikes); GDE-synth's maxDD (peak
1980-11 -> trough 1982-06, -61.3%, underwater into 1986-12) is the gold bust
plus 7%+ carry drag era.

## Decade CAGRs (regime honesty)

| | 1975-79 | 1980s | 1990s | 2000s | 2010s | 2020-26.7 |
|---|---|---|---|---|---|---|
| B&H GDE-synth | 31.4% | 6.2% | 10.0% | 9.6% | 14.3% | 26.3% |
| B&H SPY | 12.1% | 17.4% | 18.0% | -1.0% | 13.4% | 15.3% |
| 50/50 (M) | 22.2% | 12.3% | 14.1% | 4.5% | 14.2% | 21.0% |

GDE-synth's full-sample CAGR edge over SPY is manufactured in 1975-79 and
2020-26 (gold booms); it *lost* to SPY for two straight decades in between.
Start-date sensitivity (Phase 4) will bite; anyone quoting the 13.87% without
this table is misleading themselves.

## Rolling 10-year spreads (monthly, 120m windows; chart = fig3)

| Portfolio | vs SPY: win rate / range | vs 50/50 (M): win rate |
|---|---|---|
| B&H GDE-synth | 51% / [-13.4%, +17.1%] | 46% |
| 50/50 (M) | 54% / [-6.5%, +8.6%] | — |
| 25/75 (M) | 55% / [-3.2%, +4.3%] | 48% |
| 75/25 (M) | 52% / [-9.9%, +12.9%] | 49% |

Coin-flip win rates with huge ranges — regime-dominated, matching the frozen
brief's priors (~48-55%). The 10y spread vs SPY ran -13%/yr (windows ending
~1990) to +17%/yr (ending ~2012).

## Intramonth-blind bias (daily estimates, 1976-03 -> 2026-08)

Daily curves use ^GSPC + smeared Shiller dividends pre-1993 (approximation)
and GCUSD (1:30pm settle vs 4pm equity close — mismatched intraday, immaterial
for drawdown depth at this scale).

| | Monthly maxDD | Daily-estimate maxDD | Bias |
|---|---|---|---|
| B&H GDE-synth | -61.3% | **-65.5%** | ~4pp deeper |
| B&H SPY | -50.8% (1975->) | **-55.2%** | ~4pp deeper |
| 50/50 monthly-rebal | -44.9% | **-49.3%** | ~4pp deeper |

This confirms the brief's instruction to assume true GDE-synth drawdowns of
-55/-60% or worse: the honest planning number for B&H GDE-synth is **about
-65%**. All Phase 3 drawdown comparisons must repeat this caveat.

## Every approximation / splice in this phase (consolidated)

1. Gold futures excess = spot - (bills - effective lease); lease assumed
   (literature) 1975-2006, measured 2007-> (DGL/GDE instruments). Weakest
   link; pessimistic variant shown.
2. GDE fee+roll (25bp/yr) extended back to 1975 — counterfactual fund.
3. SPX TR 1975-1993 dividends from Shiller trailing-annualized rate, smeared.
4. Gold 1975-02..1976-03: monthly-average convention (14 months).
5. Daily maxDD pre-1993: price index + smeared dividends; GCUSD settle-time
   mismatch. Estimates, not measurements.
6. TB3MS monthly-average yield treated as the month's bill return (standard).
7. GDE-synth pre-2022 never traded: market impact, financing spreads at 1980s
   scale, and fund viability in that era are all assumed away.

Next: Phase 2 signal isolation (per frozen brief) on `panel_monthly.json`,
signals at month-end, execution NEXT month open.
