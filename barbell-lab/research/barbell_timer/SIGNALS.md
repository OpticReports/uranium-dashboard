# BARBELL-TIMER Phase 2 — signal library, each in isolation (per frozen SPEC)

Produced by `signals.py` -> `signals_results.json` + `signal_series.json`.
Inputs: frozen `panel_monthly.json` (1975-02 -> 2026-07) + macro built from
the frozen fixtures. GDE-synth is a MODEL (Phase 0 conditional pass, ±1%/yr
carry band pre-2007); nothing here is a forecast.

## Timing discipline (pre-registered, binds rules.py too)

- Signal dated month t uses ONLY data knowable at month-end t; the implied
  position executes at the NEXT month's open and earns the month t+1 panel
  return (close-to-close; the overnight-gap approximation is part of the
  intramonth-blind caveat from BASELINES.md).
- **Availability lags** (amendment A10): CPI-based inputs use CPI through t-1
  (mid-month release), and the trade-weighted USD index is lagged one month
  (Fed H.10 publishes weekly with a lag) — i.e. "t-1 data earns month t+1"
  for those signals. Market prices (panel indices, DFII10/DGS10 month-end)
  and FEDFUNDS (real-time daily EFFR average) use the month-t value.
- Only estimated quantity anywhere: an EXPANDING median (walk-forward, min
  24 obs) for the two level signals. Everything else is a fixed a-priori
  lookback from the brief.

## Real-10y splice (amendment A6 — new fixture `fred_dgs10.json`)

DFII10 month-end from 2003-01; before that DGS10 month-end minus trailing-12m
CPI inflation (CPI through t-1). **FLAGGED**: the proxy is nominal minus
REALIZED inflation, not a market real yield. Overlap 2003-01..2007-12: proxy
runs **-0.51pp below** DFII10 on average; at the splice, 2002-12 proxy 1.58%
vs 2003-01 DFII10 2.19%. Level-sensitive uses (the expanding median in
`tips_level`) inherit this bias; trend/change signals are less exposed.

## Evaluation (frozen)

Hit rate of each signal's prediction vs the SIGN of the next-12m GDE-synth
minus SPY compounded relative return. OOS only: 1975-02..1990-01 is warmup
(15y); evaluation months t = 1990-01..2025-07, **N = 427**. KILL RULE: OOS
hit rate <= 50%. Caveat: 12m forward windows overlap -> ~N/12 independent
observations; p-values below are one-sided vs 50% with N_eff = N/12 (naive
binomial p's in the JSON). **Base-rate honesty: always predicting "GDE wins"
scores 54.8%** — a signal below that adds nothing over a constant, even if it
clears the frozen 50% kill bar (flagged per-row).

Single-signal rule: monthly toggle per the mapping column (decided at t,
earns t+1, 5bp/switch, BOXX = bills - 5bp/yr), stats on 1990-02 -> 2026-07.

## Master table (OOS)

| # | signal | mapping (+1/-1) | hit | p(adj) | verdict | rule CAGR | MaxDD | Ulcer | Sharpe | switches |
|---|--------|-----------------|-----|--------|---------|-----------|-------|-------|--------|----------|
| 1 | sma10_gde | GDE/BOXX | 45.7% | 0.70 | **KILL** | 10.21% | -31.8% | 13.6 | 0.53 | 69 |
| 2 | sma10_spy | BOXX/SPY | 56.2% | 0.23 | live | 9.51% | -21.7% | 6.1 | 0.66 | 54 |
| 3 | mom12_1_abs_gde | GDE/BOXX | 47.3% | 0.63 | **KILL** | 11.97% | -27.4% | 8.0 | 0.62 | 48 |
| 4 | mom12_1_abs_spy | BOXX/SPY | 56.4% | 0.22 | live | 11.47% | -19.4% | 5.3 | 0.77 | 36 |
| 5 | mom12_1_rel | GDE/SPY | **66.3%** | **0.03** | live | 15.57% | -48.2% | 11.9 | 0.74 | 53 |
| 6 | ratio_sma10 | GDE/SPY | 60.7% | 0.10 | live | 12.30% | -47.6% | 12.2 | 0.60 | 78 |
| 7 | tsmom_3_gde | GDE/BOXX | 50.8% | 0.46 | live* | 8.12% | -30.8% | 11.5 | 0.43 | 121 |
| 8 | tsmom_6_gde | GDE/BOXX | 48.0% | 0.59 | **KILL** | 9.39% | -32.0% | 13.8 | 0.49 | 85 |
| 9 | tsmom_12_gde | GDE/BOXX | 45.9% | 0.69 | **KILL** | 11.04% | -23.6% | 9.3 | 0.58 | 58 |
| 10 | tips_level | GDE/SPY | 60.2% | 0.11 | live | 13.75% | -44.4% | 12.3 | 0.63 | 39 |
| 11 | tips_chg3 | GDE/SPY | 51.5% | 0.43 | live* | 12.76% | -45.3% | 12.3 | 0.62 | 113 |
| 12 | tips_trend12 | GDE/SPY | 50.4% | 0.48 | live* | 11.69% | -57.1% | 13.6 | 0.56 | 61 |
| 13 | real_ffr | GDE/SPY | 53.9% | 0.32 | live* | 13.49% | -44.8% | 11.3 | 0.65 | 21 |
| 14 | dxy_trend12 | GDE/SPY | 55.0% | 0.27 | live | 12.70% | -57.1% | 13.4 | 0.62 | 62 |

\* live under the frozen <=50% kill rule but BELOW the 54.8% always-GDE base
rate — adds nothing over a constant on this metric. `tips_trend12` (50.4%) is
essentially a coin flip; it is nonetheless the real-rate input the frozen
Phase-3 rules 3/4 pre-registered, so they inherit this weakness (see RULES.md
— that is a finding, not a surprise to hide).

**KILL LIST (4): sma10_gde, mom12_1_abs_gde, tsmom_6_gde, tsmom_12_gde.**
All four are trend rules on the GDE sleeve itself — monthly revalidation of
the prior study's "naive gold-trend timing was the WORST rule tested".
Note the mismatch flag: the kill metric is RELATIVE-sign hit rate, which is
the frozen criterion but a poor test of absolute/cash-filter signals; e.g.
killed `mom12_1_abs_gde` still cuts the GDE B&H maxDD -61% -> -27% as a
GDE/BOXX toggle. Its role inside pre-registered rule 2 is exactly that
absolute-filter role, so rule 2 proceeds as frozen (kill applies to the
signal as an isolated relative predictor).

## Infeasible (logged, not faked — amendment A7)

**futures_term_structure (state + slope)**: `fmp_gcusd_light` is a
price-spliced FRONT-MONTH-only continuous series — no deferred contracts in
the frozen fixtures, so no curve slope exists. A GLD-minus-GCUSD "basis"
surrogate was considered and rejected: it would mix a 1:30pm COMEX settle
with a 4pm NYSE close and a 40bp/yr fee with a price-spliced roll — mark
noise, not term structure. Not tested.

## Readings (kept short; fig4-6 carry the intuition)

1. The only signal with real OOS relative information is **12-1 relative
   momentum** (66.3%, p~0.03 even overlap-adjusted) — consistent with the
   prior study's best rule. `ratio_sma10` (60.7%) and `tips_level` (60.2%)
   are its weaker cousins (all three share the gold-vs-equity trend).
2. SPY-side absolute signals (sma10_spy, mom12_1_abs_spy) beat the base rate
   modestly — equity weakness predicts GDE outperformance — and their
   BOXX-toggle rules have the shallowest drawdowns/ulcers of the library.
3. The real-rate CHANGE/TREND family (tips_chg3, tips_trend12, real_ffr) is
   ~coin-flip on the relative sign at 12m. Real rates collapse IN equity
   crises, so "falling real yields -> gold" fires at exactly the wrong
   moments (see rule 3's 2008 autopsy in RULES.md).
4. Variant count for the multiple-testing adjustment: **14 signals tested,
   1 infeasible, zero unreported variants.**
