# B.5 Enhanced: structural changes to raise Sharpe and Sortino (2026-11-19)

Question (Casey): untested, structural ways (weights, leg swaps, capital efficiency) to raise the Sharpe AND
Sortino of the live B.5 book. Timing was closed by the overlay study. Pre-registered (PREREG.md, commit 745e5c3),
amended once before any arm was run (DEVIATIONS.md, commit f559d16, plus D15); post-result notes N1-N8.
Research only: nothing here changes the live book, a gate or a symphony. Charts: charts/01-06.

## Verdict: nothing IMPROVES. Two CANDIDATES by the registered rule; neither is a reason to trade.

Calibration: the Sharpe test alone had a 45-55% chance of catching a true +0.05 gain for ideas 3 and 5 (42% idea
1, 98% idea 6). IMPROVES needs Sharpe AND Sortino significant: about 1 in 5 for idea 3, about 1 in 4 for ideas
1 and 5. CANDIDATE fires for roughly one arm in four with no effect at all: it can justify a shadow track, never a trade.

Live book: 2007-06..2026-11 CAGR 8.3%, Sharpe 0.58, Sortino 0.95, max drawdown -34.4%; 2017-04..2026-11
10.5%, 0.71, 1.17, -23.0%. Ratios are over T-bills. Sortino uses monthly (21-day) returns averaged over all
21 grid starts; the registered single grid happened to be the most favourable for 2017+ (1.43; range 0.97-1.43).

| idea | arm | window | Sharpe change [95%] | Sortino change [95%] | CAGR pt/yr | verdict |
|---|---|---|---|---|---|---|
| 1 Risk-balanced weights | six-leg equal risk, halfway to live, 25% cap | 2007+ | -0.01 [-0.07, +0.04] | -0.02 [-0.17, +0.10] | -0.65 | NO |
| 2 Leverage back to live volatility | idea 1 at about 1.1x | 2007+ | -0.01 (0.00 at cheap financing) | 0.00 (+0.01) | -0.15 (-0.06) | no verdict (a translation of idea 1) |
| 3 TAIL -> BTAL | full swap | 2017+ | +0.03 [-0.02, +0.08] | +0.07 [-0.03, +0.21] | +0.36 | CANDIDATE |
| 4 Trend blend | KMLM + DBMF at 14.1% | 2010-08+ | -0.01 [-0.03, +0.02] | -0.01 | -0.06 | sign only: no |
| 5 Add Treasuries | 10% IEF from equity | 2007+ | +0.03 [-0.02, +0.08] | +0.07 [-0.04, +0.18] | -0.61 | NO (by 0.003) |
| 6 Lower-volatility equity | 8 pts AVUV -> large value | 2007+ | +0.01 [-0.01, +0.03] | +0.02 [-0.03, +0.07] | 0.00 | CANDIDATE (negligible) |

Adjusted p (Sharpe / Sortino): idea 1 0.97 / 0.95; idea 3 0.35 / 0.12 (0.34 with the grid-free Sortino);
idea 5 0.36 / 0.24; idea 6 0.56 / 0.49. Minimum detectable change at 80% power: Sharpe 0.035-0.08, Sortino 0.07-0.18.

### What each result means
- **Idea 1 (NO).** The solver wants KMLM at the 25% cap every year and AVUV near 10%; halfway to live that is a
  near-static AVUV 16.7, PHYS 22.8, QUAL 14.5, KMLM 19.6, AVDV 11.8, AVEM 8.8. First half -0.05, second half
  +0.05. The sign depends on the start: the arm equals the live book through 2008 (not enough trend history),
  and holding its final weights from 2007 would have given +0.01, positive in both halves (hindsight row X1).
- **Idea 2.** Leverage cannot add what idea 1 did not deliver. Leverage ALONE (live book at 1.2x) lowers Sharpe
  by 0.021 at T-bills + 1.5% (0.008 at + 0.5%), adds 0.9-1.1 pt/yr CAGR and deepens the 2008 drawdown from
  -34.4% to -40.5%.
- **Idea 3 (CANDIDATE, weak).** +0.030 Sharpe under the live rule, +0.026 to +0.028 with rebalance timing
  removed. But: (a) about 40% of it is simply holding less TAIL: TAIL -> T-bills alone gives +0.013, and BTAL's
  increment over T-bills is +0.017 [-0.03, +0.06], p 0.24; (b) timing-free, the first half is only +0.007 and
  the second +0.045; (c) one alternative rebalance phase the verifier tried gave +0.004; (d) 9.6 years, no 2008
  and no 2009-style rebound, where anti-beta strategies lost heavily; (e) BTAL's closing prices were stale on
  16-20% of days in 2017-18; (f) the tape-2 and 2x-cost checks are uninformative here. Crash episodes were no
  worse (2020 fall -21.8% vs -22.0%; 2022 -7.9% vs -9.2%; 2025 tariff drop -9.2% vs -8.8%).
- **Idea 5 (NO, inside the noise).** The same size as idea 3 (+0.032). It fails only because the second half is
  -0.003, and that flips to +0.002 once rebalance timing is removed. All of the gain is 2007-2017 (+0.06); on
  the real-KMLM years it is -0.06 (2022). It cut the 2008 drawdown by 6.3 pts for -0.6 pt/yr.
- **Idea 6 (CANDIDATE, negligible).** Variants: to QUAL +0.02 [-0.01, +0.06]; to minimum-volatility (USMV,
  2011-10+) +0.03 [-0.02, +0.08] with a 2.2 pt shallower drawdown. 1993-2007 small value BEAT large value
  (Sharpe 0.87 vs 0.65), so cutting AVUV now is partly chasing the last decade.

## Exploratory and by-products (EDGE rule)
- **TAIL is the common thread.** Every arm that holds less TAIL gains a little: TAIL -> T-bills +0.013 (2017+),
  TAIL -> BTAL +0.030, 5 pts of TAIL -> dollar +0.020. Consistent with the overlay study (TAIL priced like
  T-bills). None is significant.
- **5% long dollar (UUP) from TAIL:** +0.020 [-0.002, +0.042]. About half is the TAIL removal; the dollar's
  increment over T-bills is +0.011 [-0.005, +0.027], p 0.08. On tape 2 the first half is negative (-0.012).
  To use: its own single-hypothesis test with a TAIL -> T-bills control; it offsets part of gold.
- **Collar and put-protected wrappers on QUAL:** -0.024 and -0.009. Dead.
- **Combination picked on 2007-2017 (large value + Treasuries + BTAL), shown on 2017+:** Sharpe 0.78 vs 0.71
  (+0.07 [-0.04, +0.18]), Sortino +0.15, volatility 9.5% vs 11.6%, drawdown -18.3% vs -23.0%, CAGR 9.9% vs
  10.5% (live scaled to the same volatility: 9.1%). No verdict: the menu was chosen with sight of 2017+, and two
  of its three members got in on first-half margins of +0.0004 and +0.003.
- **Gold wrapper:** GLDM beat PHYS by 0.85 pt/yr since 2018-06, but GLD (about PHYS's fee) also beat PHYS by
  0.5. The lasting part is the fee gap, about 0.3 pt/yr, i.e. about +0.07 pt/yr on the book; the rest looks like
  PHYS's discount drifting (NAV data not checked).

## Against SPY + T-bills at the same volatility (Sharpe / Sortino)
2007+: live 0.58 / 0.95 vs 0.53 / 0.88. 2010-08+: live 0.72 / 1.25 vs 0.79 / 1.41. 2011-10+: 0.72 / 1.19 vs
0.81 / 1.42. 2017+: live 0.71 / 1.17 vs 0.69 / 1.18; with BTAL 0.74 / 1.24; the combination 0.78 / 1.32.
No tested structure closes the 2010-2016 gap to SPY.

## All arms (tape 1; each on its own window; bold ids are the tested family)
| id | arm | window | Sharpe change [95%] | Sortino change [95%] | CAGR | max DD pts | halves (Sharpe) | timing-free Sharpe |
|---|---|---|---|---|---|---|---|---|
| **P1** | Risk-balanced weights (six legs, halfway to live) | 2007-06+ | -0.013 [-0.07, +0.04] | -0.02 [-0.17, +0.10] | -0.65 | +0.9 | -0.05 / +0.05 | -0.011 |
| S1b | ...no halfway shrink | 2007-06+ | -0.023 [-0.13, +0.08] | -0.04 [-0.29, +0.18] | -1.08 | +0.9 | -0.07 / +0.06 | - |
| S1c | ...on downside co-movement | 2007-06+ | -0.013 [-0.06, +0.04] | -0.02 [-0.16, +0.09] | -0.62 | +0.9 | -0.05 / +0.04 | - |
| P2 | Idea 1 scaled toward live volatility, T-bills + 1.5% | 2007-06+ | -0.008 [-0.06, +0.05] | 0.00 [-0.16, +0.10] | -0.15 | +0.9 | -0.04 / +0.03 | - |
| P2lo | ...at T-bills + 0.5% | 2007-06+ | 0.000 [-0.06, +0.06] | +0.01 [-0.14, +0.12] | -0.06 | +0.9 | -0.03 / +0.04 | - |
| P2drift | ...as an unmanaged margin loan | 2007-06+ | -0.007 [-0.06, +0.05] | 0.00 [-0.15, +0.10] | -0.14 | +0.9 | -0.04 / +0.03 | - |
| S2b | Live book at 1.2x, T-bills + 1.5% | 2007-06+ | -0.021 | -0.04 | +0.87 | -6.0 | -0.02 / -0.02 | - |
| S2blo | Live book at 1.2x, T-bills + 0.5% | 2007-06+ | -0.008 | -0.01 | +1.09 | -5.9 | -0.01 / -0.01 | - |
| **P3** | TAIL replaced by BTAL | 2017-04+ | +0.030 [-0.02, +0.08] | +0.07 [-0.03, +0.21] | +0.36 | +0.3 | +0.04 / +0.02 | +0.026 |
| S3b | Half of TAIL into BTAL | 2017-04+ | +0.025 [0.00, +0.05] | +0.06 [-0.02, +0.14] | +0.22 | +0.7 | +0.04 / +0.01 | +0.014 |
| C3 | Control: TAIL into T-bills (5.9%) | 2017-04+ | +0.013 [-0.02, +0.05] | +0.03 [-0.05, +0.16] | +0.60 | -1.3 | -0.01 / +0.04 | - |
| P4 | Trend sleeve as KMLM + DBMF, same 14.1% | 2010-08+ | -0.007 [-0.03, +0.02] | -0.01 [-0.07, +0.07] | -0.06 | -0.6 | 0.00 / -0.01 | - |
| S4b | Trend blend at 20% (from TAIL and AVUV) | 2010-08+ | +0.010 [-0.03, +0.05] | +0.02 [-0.06, +0.13] | -0.03 | +0.1 | -0.01 / +0.03 | - |
| **P5** | 10% Treasuries (IEF) from equity | 2007-06+ | +0.032 [-0.02, +0.08] | +0.07 [-0.04, +0.18] | -0.61 | +6.3 | +0.06 / 0.00 | +0.039 |
| S5b | 5% IEF + 5% TIPS from equity | 2007-06+ | +0.028 [-0.02, +0.08] | +0.06 [-0.05, +0.16] | -0.63 | +5.6 | +0.05 / 0.00 | - |
| S5c | Live + 10% IEF financed at T-bills + 1.5% | 2007-06+ | +0.008 [-0.02, +0.03] | +0.02 [-0.04, +0.07] | +0.06 | +0.5 | +0.03 / -0.03 | - |
| S5clo | ...at T-bills + 0.5% | 2007-06+ | +0.016 [-0.01, +0.04] | +0.03 [-0.02, +0.08] | +0.17 | +0.6 | +0.04 / -0.02 | - |
| **P6** | 8 pts of AVUV to large value | 2007-06+ | +0.010 [-0.01, +0.03] | +0.02 [-0.03, +0.07] | 0.00 | -0.3 | 0.00 / +0.02 | +0.009 |
| S6a | 8 pts of AVUV to QUAL | 2007-06+ | +0.024 [-0.01, +0.06] | +0.06 [-0.02, +0.14] | +0.09 | +0.7 | +0.01 / +0.05 | +0.022 |
| S6b | 8 pts of AVUV to minimum-volatility | 2011-10+ | +0.033 [-0.02, +0.08] | +0.08 [-0.04, +0.20] | -0.14 | +2.2 | +0.04 / +0.02 | +0.032 |
| E7 | 5% long dollar (UUP) from TAIL | 2007-06+ | +0.020 [0.00, +0.04] | +0.04 [0.00, +0.09] | +0.30 | +0.7 | +0.01 / +0.03 | +0.018 |
| C7 | Control: 5 pts of TAIL into T-bills | 2007-06+ | +0.009 [-0.01, +0.02] | +0.01 [-0.02, +0.06] | +0.23 | 0.0 | 0.00 / +0.01 | - |
| E9a | QUAL replaced by zero-cost collar index | 2007-06+ | -0.024 [-0.05, 0.00] | -0.05 [-0.10, +0.01] | -0.58 | +1.3 | -0.03 / -0.02 | - |
| E9b | QUAL replaced by put-protected index | 2007-06+ | -0.009 [-0.06, +0.04] | 0.00 [-0.14, +0.09] | -0.49 | +2.9 | -0.02 / 0.00 | - |
| X1 | Hindsight: idea 1's final weights from 2007 | 2007-06+ | +0.012 [-0.04, +0.06] | +0.03 [-0.09, +0.11] | -0.36 | +2.6 | +0.01 / +0.02 | - |
| COMBO | Picked on 2007-17: large value + Treasuries + BTAL | 2017-04+ | +0.069 [-0.04, +0.18] | +0.15 [-0.10, +0.41] | -0.66 | +4.8 | +0.10 / +0.04 | - |

Sortino point estimates are grid-averaged; their intervals are from the registered-grid bootstrap.
"Timing-free" = both books rebalanced every month-end (phase_check.json).

## Honesty box
- Daily closes, mark-to-market, ratios over T-bills. In-sample history, not a forecast.
- Rebalance-timing noise under the band rule is about +/-0.02 Sharpe, as large as most effects here.
- Before 2017 TAIL is a stand-in, before 2020-12 KMLM is, before 2019-10 the Avantis legs are, before 2013-07
  QUAL is SPY. The BTAL stand-in failed its gate, so idea 3 rests on 2017+ only.
- Leverage is constant gross reset daily; financing T-bills + 1.5% (IBKR margin; tier to be confirmed) and
  + 0.5% (futures / stacked ETF; consistent with GDE and NTSX). Not modelled: margin calls, forced
  deleveraging, futures rolls, taxes (none). Composer cannot borrow: any leverage breaks two-broker parity.
- The capped risk-balance objective was changed after the first results (N1); the first version had flattered
  idea 1; no verdict changed.
- The downside-risk variant (S1c) cannot see hedges (its co-movement matrix has no negative entries).
- The six ideas, and the leg ranking behind ideas 1 and 6, were chosen with sight of 2017+ data.

## Counter-agent verdicts
1. Design review of PREREG.md before any arm: PASS WITH CORRECTIONS (2 blocking, 7 serious), all adopted.
2. Independent recompute, own engine, from the data: PASS. Every requested number reproduced to 5 decimals,
   including the yearly risk-balanced weights. It raised the rebalance-timing caveat (N2).
3. Code-and-claims audit: PASS WITH CORRECTIONS. No code bug or look-ahead; no verdict flips; results reproduce.
   Its five serious reporting findings (Sortino grid, timing noise, TAIL-removal share, power, warm-up) and the
   minor ones are applied here and logged as N1-N7.

## Files
PREREG.md, DEVIATIONS.md, HYPOTHESES.md, gates.json, results2.json, phase_check.json, risk_shares.json, charts/,
code/ (prep2, lib2, run2, phase_check, charts2, test2 - 11 gate tests). Raw caches not committed.
