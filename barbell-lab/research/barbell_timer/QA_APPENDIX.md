# BARBELL-TIMER Phase 4 — adversarial QA appendix (referee, 2026-08-12)

Referee did NOT build the Phase 0-3 results. Everything below comes from an
**independent reimplementation** (`qa_phase4.py` -> `qa_results.json`, figures
`make_charts_qa.py` -> `figs/fig7_qa_lag_stress.png`, `fig8_qa_robustness.png`).
Rule 2 (relmom_cash) — the verdict-driving candidate — was rebuilt from
`panel_monthly.json` with fresh code (own 12-1 momentum, own state machine, own
backtest, own stat block); the builder's `rules_results.json` was used only as
the object under audit. Bootstrap: circular block, 24m blocks, 4,000 draws.
Noise: 2,000 trials per level. All windows: OOS = held months 1990-02 -> 2026-07
(438m) unless stated.

## 0. Timestamp / alignment audit — PASS (first clean audit in this repo)

- Rule-2 states recomputed independently: **0 mismatches in 595 months.**
- Rule-2 net return series: **max |diff| = 0.0** vs the builder's stored series.
- All five rules re-run through the referee's backtest engine (builder's stored
  states for rules 3/4, lam for rule 5): max |diff| 2.8e-17. Headline OOS table
  in RULES.md reproduces to the digit (relmom 15.23%/-22.7%/Calmar 0.67; null
  12.77%/-44.9%/0.28; SPY 11.03%/-50.8%/0.22). NW-t vs null 1.29 confirmed.
- Leak probe: forcing same-month execution (decision t earns month t — a
  deliberate look-ahead) yields **15.10% CAGR vs 15.23% honest** — look-ahead
  would not even help, so the result is not riding an execution-timing leak.
- Avg gross risk notional, OOS decisions: **1.20x** (builder said 1.19x on the
  full window; immaterial).

## 1. Start-date sensitivity (starts Jan 1990 .. Jan 2015 -> 2026-07) — PASS

relmom_cash: CAGR 14.98%..18.53%, maxDD -22.7%..-17.3%, Calmar 0.66..1.07.
**dCalmar vs null positive at all 26 starts** (min +0.33, max +0.64); vs SPY
min +0.40. Worst start for the edge is 2014/2015 (post-2009 starts lift the
null's Calmar to ~0.6+), and the edge still holds. Other rules: composite min
dCalmar +0.04 (never negative but negligible), voltarget_15 min +0.08,
**realrate_gate negative at 21/26 starts** (confirmed dead).

## 2. Drop-single-year — PASS (the DD edge is NOT 1-2 episodes)

Deleting any single calendar year 1990-2026 from both series:
- dCalmar (relmom - null) **positive in all 37 cases**, min +0.24 (drop-2019 —
  removing the recovery year splices the 2018 and 2020 drawdowns to -29.0%).
- Drop **2008**: relmom -22.7% vs null -40.2% (gap +17.5pp, Calmar 0.71 vs 0.36).
- Drop **2001**: -25.2% vs -44.9% (+19.7pp). Drop **2022**: -22.7% vs -44.9%.
- Mechanism (episode map): relmom sat in BOXX 23 of 33 months of the dot-com
  bust, exited to BOXX at the Oct-2008 open, and was out 8 of 14 months of
  2022 — three independent dodges, so no single year owns the geometry.
- Q2 full-window (1977-02->) CAGR edge vs SPY: relmom +4.29pp -> **+2.75pp
  drop-1979**, +3.68pp drop-2008 — survives. **B&H GDE-synth: +2.52pp ->
  +0.96pp drop-1979** — the prior "the GDE edge may be 1979 alone" is ~60%
  right for buy-and-hold (and B&H GDE's -61.3% maxDD never dominates SPY
  anyway); it is NOT right for the timed rule. The OOS window excludes 1979
  entirely (+4.20pp there).

## 3. Signal-noise flips (15% / 30% of monthly decisions, 2000 trials) — PASS

Decision randomly replaced by another state with prob p, costs recharged:

| rule | p | med CAGR | p10 CAGR | med maxDD | p10 maxDD | med Calmar | P(Calmar > null 0.28) |
|---|---|---|---|---|---|---|---|
| relmom_cash | 15% | 13.68% | 12.16% | -27.7% | -39.4% | 0.49 | **95%** |
| relmom_cash | 30% | 12.14% | 10.21% | -32.5% | -45.5% | 0.37 | **78%** |
| composite | 15% | 12.35% | 11.18% | -40.4% | -46.0% | 0.30 | 68% |
| composite | 30% | 11.61% | 10.00% | -41.9% | -48.0% | 0.28 | 45% |
| realrate_gate | 15% | 9.72% | 8.33% | -54.6% | -58.3% | 0.18 | 2% |
| realrate_gate | 30% | 9.39% | 7.53% | -50.5% | -57.3% | 0.19 | 6% |

Graceful decay, no cliff: even with 30% of decisions randomized, relmom beats
the null's Calmar in 78% of trials. (Noise on realrate_gate *helps* it — a rule
you improve by randomizing is worse than noise.) voltarget_15 inherits rule 4's
states and was not separately noised.

## 4. ONE-MONTH LAG STRESS — **FAIL for relmom_cash (the kill finding)**

Every switch executed one month late (decision t earns t+2), OOS:

| rule | lagged CAGR/maxDD/Calmar | delta vs on-time |
|---|---|---|
| **relmom_cash** | **12.90% / -49.3% / 0.26** | **-2.33pp / -26.6pp / -0.41** |
| static_5050 | 12.77% / -44.9% / 0.28 | 0 (lag-immune) |
| composite | 11.82% / -44.5% / 0.27 | -1.30pp / -5.8pp / -0.07 |
| voltarget_15 | 10.08% / -32.2% / 0.31 | -1.12pp / -2.8pp / -0.07 |
| realrate_gate | 7.82% / -51.0% / 0.15 | -2.25pp / +6.1pp / -0.02 |

Lagged relmom's Calmar (0.26) falls **below the null (0.28)**; the entire
drawdown claim (-22.7% vs -44.9%) evaporates to -49.3%. Autopsy: the failure is
**one month**. The Sep-2008 month-end signal exited to BOXX at the Oct-1 open;
lagged, the rule holds GDE through **Oct-2008 (GDE-synth -31.6%, the worst
month in the panel)**. Delete that single month from the lagged series and the
edge returns (Calmar 0.52 vs null 0.34); dropping all of 2008 gives 0.55 vs
0.36. Fig 7 shows the two paths. Reading: the rule tolerates a month of delay
everywhere EXCEPT crash-speed episodes — which are exactly what the rule is
being bought for. The headline maxDD figure requires executing month-end
signals at the next open, without fail, in the worst month of a generation.
voltarget_15 is the only challenger whose edge survives the lag (0.31 > 0.28).

## 5. Block bootstrap vs null and vs SPY (24m blocks, 4000 draws, OOS)

One-sided p = share of draws where the difference is unfavorable. Adjustments:
x4 = Bonferroni over the 4 active rules (the builder's logged count); x8 adds
the two verdict metrics; x18 = the full logged family (14 signals + 4 rules).

| comparison | point | 90% CI | p | p x4 | p x8 | p x18 |
|---|---|---|---|---|---|---|
| relmom dCalmar vs null | +0.39 | [+0.10, +0.59] | 0.013 | **0.051** | 0.102 | 0.229 |
| relmom dUlcer vs null | -2.77 | [-8.86, +0.99] | **0.142** | 0.57 | — | — |
| relmom dCAGR vs null | +2.46pp | [-0.1pp, +5.2pp] | 0.058 | 0.23 | — | — |
| relmom dMaxDD vs null | +22.2pp | [+2.8pp, +30.5pp] | 0.027 | 0.107 | — | — |
| relmom dSharpe vs null | +0.13 | [-0.03, +0.30] | 0.101 | 0.40 | — | — |
| voltarget dUlcer vs null | -2.24 | [-6.33, -0.35] | 0.023 | **0.091** | 0.182 | 0.409 |
| voltarget dCalmar vs null | +0.10 | [-0.01, +0.29] | 0.062 | 0.249 | — | — |
| composite dCalmar vs null | +0.05 | [-0.04, +0.19] | 0.241 | 0.96 | — | — |
| realrate dCalmar vs null | -0.11 | [-0.25, -0.02] | 0.974 | 1.0 | — | — |
| relmom dCalmar vs SPY | +0.46 | [+0.14, +0.68] | 0.011 | **0.043** | — | — |
| relmom dCAGR vs SPY | +4.2pp | [+0.4pp, +8.4pp] | 0.030 | 0.121 | — | — |
| relmom dMaxDD vs SPY | +28.1pp | [+3.0pp, +38.8pp] | 0.026 | 0.102 | — | — |
| relmom dSharpe vs SPY | +0.20 | [-0.04, +0.44] | 0.089 | 0.354 | — | — |
| relmom dSortino vs SPY | +0.46 | [-0.01, +0.91] | 0.053 | 0.210 | — | — |

Findings: (a) the Q1 pass rests on **Calmar alone** — the ulcer half of the
frozen "Calmar/ulcer" criterion is not significant even UNadjusted (p 0.14);
(b) the Calmar pass is a knife edge: 0.051 under the logged family of 4, 0.102
if the two metrics are counted, 0.229 over the full 18-variant family;
(c) voltarget_15's ulcer improvement (8.5 vs 10.7) is the second passing cell
(p x4 = 0.091) and, unlike relmom's, survives the lag stress;
(d) vs SPY, only the Calmar difference clears the adjusted bar — the +4.2pp
CAGR edge and +0.20 Sharpe edge do not, individually.

## 6. Oracle gap

Perfect-foresight monthly best-of-3-sleeves (5bp costs, ~7.9 switches/yr):
OOS CAGR **50.6%**, maxDD -0.05%. Of the oracle-minus-null CAGR excess,
relmom_cash captures **6.5%**; composite +0.9%, voltarget -4.1%, realrate
-7.1%. The rule is a blunt instrument that harvests a sliver of the timing
space — consistent with its edge being drawdown-geometric, not predictive.

## 7. Regime honesty: 1980-99 in-sample block — CONFIRMED

Referee recompute: relmom 12.62%/yr vs null 13.17%/yr (**-0.55pp/yr**, builder
said -0.6pp), maxDD -33.2% vs -42.1% (9pp shallower), 35 switches in 20 years
(~1.75/yr — no whipsaw catastrophe). Reconciliation with the prior
annual-resolution study's "whipsaw disasters in that era": those disasters
belonged to **gold-trend rules on the GDE sleeve itself** — Phase 2's kill list
(sma10_gde, mom12_1_abs_gde, tsmom_6/12) is the monthly confirmation. Relative
momentum + cash filter loses the era mildly, as pre-registered ("at worst
mildly negative": met).

## 8. Model-band sensitivity (±1%/yr pre-2007 carry)

Pessimistic variant (pre-2007 gold lease -1pp, drag +0.9pp/yr on GDE-synth,
signals AND returns rebuilt): relmom OOS 15.26%/-23.1%/Calmar 0.66 vs null
Calmar 0.28; dCAGR vs SPY +4.23pp. Only 5 of 595 state decisions change. The
drawdown geometry and both verdict edges are insensitive to the carry band;
the band matters for CAGR *levels*, and the +4.2pp OOS CAGR edge vs SPY
exceeds it.

## Referee findings, severity-ranked

1. **HIGH — lag-stress kill.** One-month-late execution destroys the entire
   drawdown edge (Calmar 0.26 < null 0.28; maxDD -49.3%), through a single
   month (Oct-2008). The headline claim is conditional on disciplined
   next-open execution during crashes. Not a bug — a fragility bound.
2. **MEDIUM — ulcer leg fails.** The frozen criterion says "Calmar/ulcer";
   ulcer is not significant even unadjusted (p 0.14). The Q1 pass is
   Calmar-only.
3. **MEDIUM — adjustment knife edge.** p_adj = 0.051 under the logged
   4-rule family; 0.102 counting metrics; 0.229 over all 18 logged variants.
   The YES does not survive every defensible counting.
4. **LOW — none of the CAGR/Sharpe differences (vs null or vs SPY) is
   individually significant after adjustment**; the statistical case is
   drawdown-geometry only, as the builder already conceded.
5. **Confirmations:** builder's pipeline reproduces exactly (first Phase with
   zero referee-found implementation bugs); realrate_gate dead on every
   battery leg; composite adds nothing; voltarget_15 is the lag-robust,
   ulcer-significant runner-up at -1.6pp/yr CAGR.

Caveats carried everywhere: GDE-synth is a model (±1%/yr carry band pre-2007);
month-end curves are intramonth-blind (daily drawdowns est. ~4pp deeper);
pre-1993 equity leg is Shiller-spliced; BOXX = bills - 5bp is a proxy;
no taxes modeled (Act 60).
