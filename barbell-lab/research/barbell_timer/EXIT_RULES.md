# BARBELL-TIMER Amendment A12 — the GDE-anchored exit-engine family (rules 6/6b/7/8)

Produced by `rules_exit.py` -> `rules_exit_results.json` (monthly net return
series + state series + month-end trigger inputs included for Phase 4).
Chart: `figs/fig7_exit_rules_drawdowns.png` (per-rule drawdown profiles vs
B&H GDE-synth and vs relmom_cash, exit months shaded). GDE-synth is a MODEL
(±1%/yr carry band pre-2007); month-end curves are intramonth-blind (daily
estimates ~4pp deeper, BASELINES.md). Walk-forward history, NOT forecasts.
Parameters were FROZEN in SPEC A12 (P=85 / Q=70 / corr 90th / 63d / 3m) —
nothing was tuned, no additional variants were run; bad rules are reported
bad.

## Discipline (verified in-code before results were read)

- Same standing convention as rules.py: state decided at month-end t from
  data knowable at t, executed next month's open, earns the month t+1 panel
  return; 5bp x one-way turnover in the traded month; BOXX = bills - 5bp/yr.
- **QA battery**: truncation-invariance (inputs cut at 1990-12 / 2005-06 /
  2019-12 -> identical decisions up to the cut) and future-perturbation
  (violent shocks to post-cut panel + daily inputs -> decisions unchanged):
  **PASS at all three cuts, both tests.** rules_exit.py hard-exits on any
  failure.
- Sharpe tripwire: max observed Sharpe in the family = 0.62 (OOS rule 7) —
  far below 1.2, no audit triggered beyond the standing battery.
- Windows: **FULL_A12 = 1978-05 -> 2026-07** (see flag F1 — starts LATER
  than the rules-1-5 full window 1977-02); OOS = 1990-02 -> 2026-07,
  identical to Phase 3 so every head-to-head comparison is same-window.
- Free parameters: 6/6b two (P=85, Q=70), 7 two (90th pct, 3m), 8 the union
  — all fixed a-priori by SPEC A12; the only estimated quantities are the
  expanding percentiles themselves (walk-forward, burn-in 24 monthly obs,
  the repo's standing expanding-estimator convention).
- Multiple-testing family (SPEC A12): now 14 Phase-2 signals + 4 Phase-3
  rules + **4 A12 exit variants**; Phase 4 recomputes adjusted bars on that
  count. No unreported variants exist.

## Flags (data/approximation)

- **F1** Daily gold exists only from 1976-02-26 (PROVENANCE.md), so 63d
  vol/corr start 1976-05 and, after the 24m percentile burn-in, the first
  live decision is 1978-04 (first held month 1978-05). **No monthly-derived
  "63d" substitute was used for 1975-02..1976-04**: a 63-trading-day vol
  from 3 monthly observations is noise, not an estimator. Cost of honesty:
  the A12 full window misses 1977-02..1978-04; the OOS verdict window is
  untouched.
- **F2** Pre-1993 daily equity leg = ^GSPC + smeared Shiller dividends
  (affects vol63/corr63 ESTIMATION only; standing flag, same as rule 5's
  sigma60). Daily GDE-synth compounds to the monthly panel at corr 0.9993.
- **F3** The gold leg of corr63 is GCUSD (1:30pm COMEX settle) vs a 4pm
  equity close — intraday mismatch smears extreme same-day co-moves,
  which is material to rule 7's phenotype detection (see autopsy).

## Rule definitions as implemented (ambiguities resolved a-priori, BEFORE results)

- **A13** vol63 = trailing 63-trading-day std (ddof=1, x sqrt252) of daily
  GDE-synth returns; corr63 = 63d Pearson corr of daily gold vs equity
  returns; both sampled at the last trading day <= month-end t. Expanding
  percentiles taken over the MONTH-END history of the statistic (decisions
  are monthly), including month t, min 24 obs.
- **A14** 6b's destination re-evaluated EVERY month while in the exit state
  (SPY trend = SPY TR index >= its 10m SMA, signals.py convention);
  destination changes pay normal switch costs.
- **A15** Rule 7 "GDE 3m return" = trailing 3m compounded return incl.
  month t (tsmom_3 convention); "negative" = < 0. Exit needs (corr AND
  ret3); re-entry when either clears -> rule 7 is memoryless: cash iff both
  hold at t.
- **A16** Strict inequalities (exit >, re-enter <); initial state = GDE
  (default position IS GDE per the amendment).

## Master table — OOS window 1990-02 -> 2026-07 (the verdict window)

| portfolio | CAGR | Vol | Sharpe | Sortino | MaxDD | UW | Calmar | Ulcer | Worst12m | %GDE |
|---|---|---|---|---|---|---|---|---|---|---|
| B&H GDE-synth | 13.98% | 19.51% | 0.64 | 0.99 | -44.2% | 47m | 0.32 | 10.8 | -43.1% | 100% |
| B&H SPY | 11.03% | 14.67% | 0.61 | 0.91 | -50.8% | 74m | 0.22 | 13.5 | -43.4% | — |
| static_5050 (null) | 12.77% | 15.75% | 0.68 | 1.04 | -44.9% | 50m | 0.28 | 10.7 | -42.6% | — |
| relmom_cash (P3 champion) | 15.23% | 15.82% | 0.81 | 1.38 | **-22.7%** | 44m | **0.67** | **8.0** | -18.5% | 46% |
| 6 vol_exit | 10.21% | 15.94% | 0.52 | 0.83 | -35.3% | 68m | 0.29 | 12.6 | -26.6% | 83% |
| 6b vol_exit_spy | 11.96% | 16.51% | 0.61 | 0.97 | -35.3% | 57m | 0.34 | 10.6 | -27.1% | 83% |
| 7 corr_exit | 13.46% | 19.00% | 0.62 | 0.98 | -44.2% | 47m | 0.30 | 11.3 | -43.1% | 97% |
| 8 dual_exit | 10.17% | 15.54% | 0.53 | 0.85 | -35.3% | 55m | 0.29 | 10.7 | -26.6% | 80% |

Full A12 window 1978-05 -> 2026-07 (regime honesty; includes the 1979-82
episode the OOS window hides): B&H GDE 14.33%/-61.3%/Calmar 0.23;
relmom_cash 16.15%/-33.2%/0.49; 6: 9.97%/**-45.9%**/0.22;
6b: 12.40%/**-47.7%**/0.26; 7: 13.19%/**-62.2%**/0.21 (DEEPER than B&H);
8: 9.66%/-50.0%/0.19.

## Owner criterion (A12): "GDE's DD materially reduced while CAGR stays above B&H SPY" — OOS

| rule | dMaxDD vs GDE | dCAGR vs GDE | dCAGR vs SPY | dMaxDD vs SPY | dSharpe vs SPY | gross notional | verdict |
|---|---|---|---|---|---|---|---|
| 6 vol_exit | +9.0pp | -3.77pp | **-0.82pp** | +15.5pp | -0.09 | 1.46x | **FAIL** (CAGR < SPY) |
| 6b vol_exit_spy | +9.0pp | -2.02pp | +0.93pp | +15.5pp | **0.00** | 1.59x | marginal (see below) |
| 7 corr_exit | **+0.0pp** | -0.52pp | +2.43pp | +6.5pp | +0.01 | 1.73x | **FAIL** (DD not reduced) |
| 8 dual_exit | +9.0pp | -3.81pp | **-0.85pp** | +15.5pp | -0.10 | 1.40x | **FAIL** (CAGR < SPY) |

A5/Q2 reading: 6b is the only variant that clears the letter of Q2
(`dominates_raw=True`: CAGR 11.96% >= SPY 11.03%, maxDD -35.3% vs -50.8%,
Calmar 0.34 vs 0.22, Sortino 0.97 vs 0.91) — but **leverage-aware it has
ZERO scale-free edge** (Sharpe 0.608 vs SPY 0.609) while running 1.59x
average gross risk notional. Its entire raw-CAGR edge over SPY is the
leverage of the stack it holds 83% of the time, exactly the pattern the
amendment says is "expected, not evidence". Compare relmom_cash: Sharpe
0.81 at 1.19x gross.

## Head-to-head vs relmom_cash (the owner's real question) — OOS

| rule | dCAGR | dMaxDD | dCalmar | dUlcer | dSortino | NW-t (mean monthly diff) |
|---|---|---|---|---|---|---|
| 6 vol_exit | -5.02pp | -12.6pp | -0.38 | +4.6 | -0.55 | **-2.23** |
| 6b vol_exit_spy | -3.27pp | -12.6pp | -0.33 | +2.7 | -0.41 | -1.53 |
| 7 corr_exit | -1.77pp | -21.6pp | -0.37 | +3.3 | -0.40 | -0.51 |
| 8 dual_exit | -5.06pp | -12.6pp | -0.38 | +2.7 | -0.53 | **-2.32** |

**Every A12 variant loses to relmom_cash on every metric** — CAGR, maxDD,
Calmar, ulcer, Sortino — and for 6 and 8 the mean-return deficit is
statistically significant (NW-t ~-2.2, one of the few significant results
this project has produced, and it is AGAINST the new family). The
GDE-anchored engine does not beat the rotation engine; it holds less GDE
at the wrong times (autopsy below). vs the static 50/50 null the family is
also non-viable: best dCalmar +0.05 (6b) with dCAGR -0.81pp; 6 and 8 give
up ~2.6pp/yr CAGR for zero Calmar gain; nothing here approaches the
Calmar/ulcer improvement the frozen criterion demands.

## Per-regime blocks (CAGR / MaxDD / Calmar)

| portfolio | 1980-99 | 2001-11 | 2012-18 | 2022-> |
|---|---|---|---|---|
| B&H GDE-synth | 8.1% / -61.3% / 0.13 | 15.1% / -44.2% / 0.34 | 7.6% / -20.1% / 0.38 | 24.7% / -30.2% / 0.82 |
| relmom_cash | 12.6% / -33.2% / 0.38 | 15.0% / -18.5% / 0.81 | 9.3% / -17.2% / 0.54 | 22.8% / -15.6% / 1.47 |
| 6 vol_exit | 6.8% / -45.9% / 0.15 | 11.3% / -24.6% / 0.46 | **3.3% / -20.7% / 0.16** | 23.0% / -20.9% / 1.10 |
| 6b vol_exit_spy | 9.7% / -47.7% / 0.20 | 13.6% / -24.6% / 0.55 | 5.2% / -20.1% / 0.26 | 22.2% / -21.4% / 1.04 |
| 7 corr_exit | **6.4% / -62.2% / 0.10** | 13.6% / -44.2% / 0.31 | 8.4% / -14.0% / 0.60 | 22.7% / -31.3% / 0.73 |
| 8 dual_exit | 6.1% / -50.0% / 0.12 | 9.9% / -24.6% / 0.40 | 5.7% / -14.0% / 0.41 | 22.1% / -20.9% / 1.06 |

The brief's bad-regime test ("at worst mildly negative") is failed across
the board: 6 loses 7.0pp/yr to the null in 2012-18 (a calm regime — the
worst place for an exit engine to bleed); 7's 1980-99 maxDD (-62.2%) is
worse than the thing it is supposed to protect.

## Turnover (one-way x/yr) and state switches / exit episodes

| rule | 1980s | 1990s | 2000s | 2010s | 2020s | switches/decade | exit episodes |
|---|---|---|---|---|---|---|---|
| 6 vol_exit | 0.5 | 0.3 | 0.8 | 0.5 | 1.1 | 5/3/8/5/7 | 16 |
| 6b vol_exit_spy | 0.7 | 0.4 | 0.9 | 0.6 | 2.1 | 7/4/9/6/14 | 16 |
| 7 corr_exit | 1.0 | 0.0 | 0.4 | 0.4 | 0.8 | 10/0/4/4/5 | 12 |
| 8 dual_exit | 0.7 | 0.3 | 1.0 | 0.5 | 1.4 | 7/3/10/5/9 | 19 |

Low turnover (~0.3-1.1 switches/yr, ~2-5bp/yr cost) — costs drive nothing;
the losses are timing, not friction.

## Autopsy — WHY the family fails (from the state series + trigger inputs)

1. **Realized vol is direction-blind, and GDE's vol spikes on melt-UPS.**
   Rule 6's exits cluster on parabolic rallies as often as crashes. The
   decisive episode: exit at 1979-10 month-end (vol63 0.349 > q85 0.264,
   driven by the gold rally itself) -> in cash for Nov-79/Dec-79/Jan-80
   while GDE-synth returned **+14.0% / +24.3% / +32.0% (+83% cumulative)**,
   then re-entered 1981-05, mid-bust. Same phenotype 2020-03 (missed
   Apr-20 +16.9%) and 2025-04. The one clean save — exit at 2008-09
   month-end, dodging Oct-08's -31.6% — was followed by 20 months in cash
   (vol stayed above the re-entry percentile through 2010-05), missing the
   2009-10 recovery and giving back more than the crash avoided.
2. **The corr-spike trigger cannot see Oct-2008 coming — it is the
   Oct-2008 REACTION, not predictor.** At Sep-08 month-end, 63d
   gold-equity corr was **-0.38** (gold had rallied while equities fell all
   summer); it only crossed its expanding 90th percentile in Dec-08/Jan-09,
   AFTER the crash months entered the trailing window — and by Jan-09 GDE's
   3m return had turned positive, so the AND-gate never opened. Rule 7 held
   GDE straight through Oct-2008. Trailing realized correlation is a
   lagging estimator of exactly the event it was named after.
3. **Where rule 7 did fire it was late and whipsawy**: five 1-3 month
   episodes inside the 1980-82 bust, each exiting after a crash month and
   re-entering into the next leg down — full-window maxDD -62.2%, ~1pp
   DEEPER than B&H GDE. An exit engine that deepens the drawdown it exists
   to cut is dead on its own terms.
4. **Rule 8 is the union of both failure modes** (blow-off-top selling from
   6 + lagging whipsaws from 7) and has the family's worst full-window
   CAGR (9.66%).
5. 6b's SPY-fallback recovers ~1.8pp/yr of 6's cash drag (74 of its 108
   exit months routed to SPY, 34 to cash) — it papers over the bad exit
   timing with equity beta, which is why its Sharpe lands exactly on SPY's.

## Honest bottom line (subject to Phase 4 adversarial QA)

The genuinely untested branch has now been tested and it loses. **All four
A12 exit engines fail the owner's own success criterion**: 6 and 8 cut
GDE's OOS maxDD by only 9pp (44.2% -> 35.3%) at the price of dropping CAGR
BELOW B&H SPY; 7 cuts nothing (97% time-in-GDE, maxDD identical to B&H,
and a deeper-than-B&H drawdown in its 1980-82 whipsaw era); 6b keeps CAGR
0.9pp above SPY but with zero scale-free edge (Sharpe 0.608 vs 0.609) at
1.59x gross notional — a leveraged SPY impersonation, not a better GDE.
Every variant is dominated by relmom_cash on every reported metric, two of
them statistically significantly (NW-t ~-2.2). Answer to the owner's
head-to-head question: **a GDE-anchored exit engine does not beat the
rotation engine — it just holds less GDE, and at the wrong times**,
because GDE's realized vol spikes on blow-off rallies as much as crashes,
and trailing gold-equity correlation flags Oct-2008 only after Oct-2008.
The vol/corr family joins trend (twice) on the pile of failed GDE-sleeve
exit overlays; relmom_cash remains the only standing challenger going into
Phase 4.
