# Pre-registration: macro states as a risk-on / risk-off layer across the symphonies (2026-11-21)

Owner, 2026-11-21: "figure out how to improve the CAGR and/or drawdown on these symphonies ... look at
scenarios on which the macro market like yields, CAPE, gold prices (adjusted and nominal), rates of changes
in these asset classes as well, volume etc in order to see if there are macro indicators that we can use to
improve risk on risk off switching ... a major focus is these symphonies moving in isolation."
Written before any macro state was joined to any engine path. Scouting digest (prior work and data):
session scratchpad `macro_scout/DIGEST.md`; no result was computed in it.

## What is already on the record, and why this is not a repeat
- `ideas-backlog.md` "SETTLED QUESTIONS": external de-risking overlays rejected as a class (ten
  measurements: addenda 19b, 20b, 21, 25, 31, 33, 53); reopen only "with a mechanism that is not 'de-risk
  the stress state'". Addendum 33: "NEVER a book-level rate gate: HG and SLEEVE load in opposite
  directions". Addenda 9, 26: no valuation conditioning; a timing policy must beat a FIXED-weight policy
  with the same average weight. Addendum 40: the one supported use of macro in the literature is on the
  RE-ENTRY side of a trend rule (never tested here). Addendum 57: six macro states on the KMLM switch, none
  detectable.
- New here: (a) indicators never tested in any form: gold (nominal, real, against stocks and copper),
  inflation and breakevens, the 10y-2y curve, financial conditions, liquidity, slow market volume;
  (b) a TILT between engines by state, which addendum 33's "opposite directions" points to, instead of a
  gate; (c) cross-engine signals (does one engine's state predict the others?); (d) macro as a re-entry
  signal for Holy Grail's gate; (e) long daily engine paths (addenda 58-59) at book level.
- The owner asked for this study knowing the record; the de-risk policy (P1) is run as the benchmark the
  record predicts will fail, on indicators it never covered.

## States (0/1 each session; "on" = the risk-off reading, fixed here; no threshold is tuned)
Every series is used as of the session BEFORE the day it applies to, plus its publication lag (below).
63 sessions is about a quarter, 252 a year.

| Family | Id | On when | Series (first date) | Extra lag |
|---|---|---|---|---|
| RATES | R1 | 10y yield up more than 0.50 over 63 sessions | DGS10 (1962) | 1 |
| | R2 | 2y yield up more than 0.50 over 63 sessions | DGS2 (1976) | 1 |
| | R3 | 10y minus 3m below zero | T10Y3M (1982) | 1 |
| | R4 | curve was inverted (R3) at some point in the last 252 sessions and 10y-3m has risen more than 0.50 over 63 | T10Y3M | 1 |
| | R5 | 10y minus 2y below zero | T10Y2Y (1976) | 1 |
| | R6 | 10y real yield up more than 0.40 over 63 sessions | DFII10 (2003) | 1 |
| | R7 | fed funds up more than 0.25 over 126 sessions | DFF (1954) | 1 |
| INFLATION | I1 | 10y breakeven up more than 0.25 over 63 sessions | T10YIE (2003) | 1 |
| | I2 | CPI year-on-year at least 1.0 point above its value six months earlier | CPIAUCSL (1947), latest vintage | month m from the 15th of m+1, plus 1 |
| | I3 | CPI year-on-year above 4% | CPIAUCSL | same |
| VALUATION | V1 | CAPE above its 90th percentile of all history to date | Shiller/multpl monthly (1881) | month m from the first session of m+2 |
| | V2 | CAPE down more than 10% over 12 months | same | same |
| | V3 | 1/CAPE minus (10y yield minus CPI year-on-year) below its 25th percentile to date | CAPE, DGS10, CPI | as each |
| GOLD | G1 | gold above its 200-session average (10-month average before daily data) | GC=F daily (2000-09); monthly average before (1971) | 1; monthly from the first session of m+1 |
| | G2 | gold/S&P 500 above its 200-session (10-month) average | same, ^GSPC | same |
| | G3 | gold/CPI up more than 10% over 12 months | monthly gold, CPI | as CPI |
| | G4 | copper/gold below its 200-session average | HG=F, GC=F (2000-09) | 1 |
| | G5 | gold up more than 10% over 63 sessions (3 months) | as G1 | as G1 |
| CREDIT | C1 | Baa minus 10y spread up more than 0.30 over 63 sessions | BAA10Y (1986) | 1 |
| | C2 | Baa minus 10y above its 80th percentile to date | BAA10Y | 1 |
| | C3 | Chicago Fed financial conditions index above zero | NFCI (1971), weekly, REVISED history | 4 sessions after the week's Friday |
| | C4 | that index up more than 0.15 over 13 weeks | NFCI | same |
| DOLLAR | D1 | dollar index above its 200-session average | DX-Y.NYB (1971) | 1 |
| | D2 | dollar index up more than 5% over 63 sessions | same | 1 |
| VOLUME | M1 | S&P 500 volume, 21-session average, more than 1.25 times its 252-session average | ^GSPC volume (1970) | 1 |
| | M2 | that ratio below 0.85 | same | 1 |
| | M3 | more than 60% of the last 21 sessions' volume traded on down days | same | 1 |
| LIQUIDITY | L1 | M2 year-on-year growth below 5% and below its value six months earlier | M2SL (1959), latest vintage | month m from the first session of m+2, plus 1 |
| | L2 | Fed balance sheet lower than 26 weeks earlier | WALCL (2002-12) | 2 |
| OIL | O1 | WTI up more than 50% over 252 sessions | DCOILWTICO (1986) | 4 |
| (benchmark) | T1 | S&P 500 below its 200-session average | ^GSPC | 1 |

Composites (the PRIMARY family, 11 states): each family's composite is on when at least half of its states
that have data are on (OIL is its one state); GC2 / GC3 are on when at least 2 / 3 of the nine family
composites are on. The 30 single states are secondary and descriptive. T1 is a reference only.

## Cross-engine and re-entry states
- X1 Holy Grail's SPY gate is off. X2 the KMLM switch is risk-off (XLK RSI10 below KMLM's). X3 the sleeve's
  shock ladder holds something other than cash at the prior close. X4 the sleeve's inverse-fund test is on
  (IEF RSI8 below PSQ RSI45). X5 at least two of X1, X2, X4 are on. Each is tested as a predictor of the
  OTHER engines' next-session and next-5-session returns.
- RE (Holy Grail only; days its gate is off): does the ungated tree (approved version `bP4mvRy6`) earn more
  than cash on gate-off days when RE1 the Baa spread has narrowed more than 0.20 over 63 sessions, RE2 the
  financial conditions index has fallen over 13 weeks, RE3 the S&P 500 is above its 50-session average?

## Targets and stretches
Engine paths: the live rules' simulated daily returns of addenda 58-59 (HG 1991-04 on; KMLM 1991-04 on,
with 2020-12..2021-05 uncovered; SLEEVE 1994-06 on) and the book at 34.1 / 34.1 / 31.8.
| | Shape only | Mostly real | Real |
|---|---|---|---|
| HG | 1991-04..2006-07 | 2006-07..2015-08 (rebuilt funds) | 2015-09 on |
| KMLM | 1991-04..2020-12 (rebuilt KMLM fund; VIX funds modelled before 2008) | none | 2021-06 on |
| SLEEVE | 1994-06..2015-05 | 2015-06..2020-12 (KMLM signal rebuilt) | 2020-12 on |
| BOOK | 1994-06..2015-05 | 2015-06..2020-12 | 2021-06 on |
The verdict sample for each target is its "mostly real" plus "real" years; the shape years must agree in
sign. The book's verdict sample is 11 years with about one of each macro regime: a macro rule CANNOT be
confirmed on it. The study can rule states out, rank them, and name candidates with what would confirm.

## Tests
1. **Map.** For every state and target: mean daily log return on and off, their difference per year, the
   share of the target's deepest falls that sit in on-days, the number of separate on-episodes. p-value by
   1,000 circular shifts of the state (keeps its persistence), two-sided; Holm across the 11 primary
   states per target.
2. **P1 de-risk** (the benchmark the record says fails): target held at 50%, rest T-bills, while the state
   is on. Against a constant mix with the same average exposure: growth difference and deepest-fall
   difference, with the same shifted-state placebo (the policy's edge over its own shifted copies).
3. **P2 tilt between engines** (book only): while the state is on, 15 points of weight move from the
   engine with the worst to the engine with the best average return in that state's earlier on-days,
   estimated on data strictly before each month, starting after 5 years; fixed weights otherwise. Against
   the fixed book: growth, deepest fall, shifted-state placebo.
4. **Cross-engine**: the other engines' next-1 and next-5-session returns, state on against off, same
   placebo; and P1 applied to the other engines on that state.
5. **Re-entry**: the ungated tree's return minus T-bills on gate-off days, RE state on against off.

## What counts
A state "works" for a policy only if, on the verdict sample: the policy beats its matched constant mix (or
the fixed book) on growth, or cuts the deepest fall by at least 3 points without lower growth; shifted-state
p < 0.05 after Holm over the 11 primary states (cross-engine: over its 5; re-entry: over its 3); the
shape years have the same sign; the mirror (state inverted) is worse; and it has at least 8 separate
on-episodes in the verdict sample. Anything short of that is listed as a candidate edge with its sample
size, mirror, and what would confirm it. Nothing is built into a symphony or POLICY without the owner.

## Honesty box
In sample; none of it a forecast. CPI, M2 and the financial conditions index are today's revised vintages,
not what was published at the time. Daily gold starts 2000-09 (monthly averages before). Before 2015 the
book is largely rebuilt engines. Thirty single states, eleven composites, three engines and a book: the
multiplicity is large and is corrected only within each primary family; the single states are a map, not
a test. Simulated at the close; measurement basis daily mark-to-market.
