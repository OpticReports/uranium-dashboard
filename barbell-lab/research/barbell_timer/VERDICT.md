# BARBELL-TIMER — one-page verdict (Phase 4 referee, 2026-08-12)

Basis: independent referee recompute (`qa_phase4.py`, QA_APPENDIX.md). The
builder's Phase 0-3 pipeline reproduced **exactly** (0 divergent months across
all five rules) — the numbers below are fights about meaning, not arithmetic.
All results are on a MODELED GDE-synth (±1%/yr carry band pre-2007, Shiller
pre-1993 splice), month-end resolution (daily drawdowns ~4pp deeper), history
not forecast.

## Q1 — does any rule beat static 50/50 on Calmar/ulcer OOS, p<0.10 adjusted?

**YES — but by the narrowest admissible margin, on Calmar only, and the edge
is execution-fragile.** relmom_cash OOS: Calmar 0.67 vs 0.28, maxDD -22.7% vs
-44.9%, ulcer 8.0 vs 10.7, +2.46pp/yr CAGR. Bootstrap (24m blocks, 4000
draws): dCalmar one-sided p = 0.013 -> **p_adj = 0.051** under the
pre-logged family of 4 rules — under the 0.10 bar. Honesty attached to that YES:

- The **ulcer half of the criterion fails** (p = 0.14 unadjusted). Calmar-only.
- The pass **does not survive broader countings**: ×8 (rules × both metrics)
  gives 0.102; ×18 (full logged variant family) gives 0.229.
- **The rule dies the one-month lag stress** (the frozen battery's fragility
  test): executed one month late, Calmar 0.26 < null 0.28, maxDD -49.3%. The
  whole failure is Oct-2008 — the on-time rule exited at the Oct-1 open and
  dodged a -31.6% GDE month by exactly one month. The drawdown geometry is
  real across starts, dropped years, and 30% signal noise (edge positive in
  all 26 starts, all 37 drop-years, 78-95% of noise trials), but it is
  conditional on never missing a month-end exit in a fast crash.
- No other rule passes on Calmar. voltarget_15 passes on **ulcer** (p_adj
  0.091), survives the lag stress (0.31 vs 0.28), and costs -1.6pp/yr CAGR —
  the robust-but-boring runner-up. composite is indistinguishable from the
  null; realrate_gate is dead (worse than the null on every battery leg).

## Q2 (A5) — does any GDE-containing portfolio dominate B&H SPY, leverage-aware?

**YES for relmom_cash, on point estimates, and it survives drop-1979 and
drop-2008; but only the Calmar difference is statistically significant after
adjustment.** OOS: 15.23%/-22.7%/Sortino 1.38/Sharpe 0.81 vs SPY
11.03%/-50.8%/0.91/0.61 at **1.20x average gross risk notional** — a
scale-free win, not a leverage artifact. Drop tests (full window 1977-02->):
dCAGR vs SPY +4.29pp -> **+2.75pp without 1979**, +3.68pp without 2008;
dominance (>=CAGR AND better maxDD/Calmar/Sortino) intact in both; the OOS
window excludes 1979 entirely (+4.20pp). Bootstrap: dCalmar p_adj 0.043
(passes); dCAGR raw p 0.030 but p_adj 0.121; dSharpe/dSortino not
individually significant. Qualifiers: under the one-month lag the dominance
narrows to a near-tie (12.9%/-49.3% vs 11.0%/-50.8%); the +4.2pp CAGR edge
exceeds the ±1%/yr model band (pessimistic-carry variant: edge +4.23pp,
Calmar 0.66 — insensitive).

**NO for everything else.** B&H GDE-synth does not dominate SPY (maxDD -61.3%,
and 1979 is ~60% of its full-window CAGR edge: +2.52pp -> +0.96pp). static
50/50 and composite carry ~1.4x gross notional for a +0.07 Sharpe edge — 
leverage, not evidence.

## Bottom line

The null survived 3 of 4 challengers; relmom_cash beat it on the letter of the
frozen criterion (Calmar, p_adj 0.051) and dominates SPY on paper at lower
gross exposure — but the referee's battery shows the entire claim is drawdown
geometry that (a) is not significant on ulcer, (b) flips to NO under stricter
multiplicity counting, and (c) requires flawless next-open execution in crash
months (miss Oct-2008 by one month and the edge is gone). Decision-grade
reading: a *conditional* YES/YES — suitable for paper-trading with hard
execution discipline, not for treating -23% as the planning drawdown. Plan on
the lagged/daily numbers instead (~-30% to -49%). "The 50/50 null captures
most of what is reliably capturable" remains the boring conclusion that
survives every check; relmom_cash is the one candidate with a real, but
fragile, residual claim.
