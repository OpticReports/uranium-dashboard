# Severity index over time + analogs

**Question (Casey, 2026-09-30):** show the Severity Index over time so we can
see it rising or falling, and add analogs.

## SPEC v0 — written 2026-09-30 before any history was computed

**Reproduction gate (done first):** the frozen-data bundle (`severity_history/
load.py`: every input from 1976-01-01 as `fetch_bundle` does, ICE HY spread
spliced onto its frozen history, FINRA monthly margin debt) reproduces the live
`/severity` exactly on 2026-09-30: 68.9 (base 67.9, +2.3 policy space, −1.3
dampeners), all six blocks and every component identical.

**What each point is.** At each month-end t, the LIVE code (`build_severity`,
unchanged) is run on the bundle truncated to what was PUBLISHED by t. That is
what the dashboard would have said at t using today's data vintage. Ranks are
therefore point-in-time (expanding window from 1976), not today's yardstick.

**Publication lags** (observation date stamp + lag ≤ t):
| series kind | lag |
|---|---|
| daily/weekly (EFFR, HY OAS, 30y mortgage) | 7 days |
| monthly (core PCE, saving rate, months' supply, FINRA margin) | 60 days |
| quarterly (GDP, Z.1, DSR, delinquencies, vacancies, median price, capex, federal debt/GDP, DFA) | 180 days |
| annual federal deficit (FY, stamped Jan 1) | 300 days |
| annual median household income (stamped Jan 1, published Sep of next year) | 630 days |

*Amended after verification (v1):* inventories/sales 75 days, BIS private
credit 275, household debt/GDP 460, federal deficit 390 — the v0 lags let
these in before they were published (checked against ALFRED real-time
vintages). Every other lag matched or was more conservative.

**Minimum history.** An input is used at t only if its as-of history already
spans ≥ 10 years (from 1976 or its first observation). Never binds today (every
input has ≥ 18 years), so the live number is unaffected. Consequence, stated
up front: several inputs start late on FRED — household debt/GDP (BIS) and
the debt-service ratio in 2005, EFFR 2000-07, HY OAS 1996-12, FINRA margin
1997, card delinquency 1991, inventories/sales 1992 — so they enter the
history 10 years later. The chart shows the live-input count at every point
and does not draw the line where fewer than half of the inputs are live.

**Grid:** month-ends from 1986-01 to the latest month.

**Analogs (descriptive, no test — 3-4 endogenous recessions cannot validate
a severity index):**
1. *Recession starts:* the reading at the month before each NBER peak since
   1986 (1990-07, 2001-03, 2007-12, 2020-02) with what followed: months of
   recession, rise in unemployment (max within 30 months of the peak minus the
   peak-month rate), peak-to-trough real GDP (GDPC1). 2020 is shown but marked
   exogenous (the index's own note says it bypasses such shocks).
2. *Nearest readings:* months with a reading within ±5 points of today's and
   ≥ 75% of inputs live, grouped into episodes (gaps < 6 months merge); for
   each, whether a recession began within 24 months and the unemployment
   change over 24 months.

**Honesty:** current-vintage data (revisions not modeled); the index's weights
were set in 2026 with this history in view; the early history is a different
mix of inputs than today's; no claim that the index predicted anything.

## v2 — household debt/GDP extended back with Z.1 (Casey, 2026-09-30)

The index's "THE severity predictor" (household debt/GDP, 3-year change) read
FRED HDTGPDUSQ163N, which starts in 2005. `sources/household_debt.py` now
extends it back with the Fed's Z.1 (CMDEBT, household + nonprofit debt, over
nominal GDP) — for the LIVE index and the history alike.

- **Fit over the overlap (2005Q1-2025Q2, 82 quarters):** 3-year changes
  correlate 0.97, mean gap +0.14pp (sd 1.34, max 4.4); levels run ~2.3pp
  apart (different GDP basis), which only matters where a 3-year window
  crosses the join.
- **Rule:** the published series wins wherever it exists; before 2005Q1 the
  Z.1 ratio is shifted by the gap at 2005Q1 only (−0.4pp) so the join is
  continuous and pre-2005 3-year changes are pure Z.1. Either input missing →
  the published series unchanged (no silent substitution).
- **Live effect:** severity 68.9 → **67.7** (still SEVERE). Today's 3-year
  change (−5.8pp, households deleveraging) ranked at the 39th percentile
  against 2008+; against 1976+ (which includes the 2000s boom) it is the
  15th.

## RESULTS — frozen 2026-09-30 (`severity_history/results.json`, v1 lags, v2 household debt)

- **Trend:** 49.2 (Dec-2023) → 57.2 (Dec-2024) → 66.2 (Dec-2025) → 67.7 today
  (live). Drivers, Dec-2023 → live: tech capex (block F 47 → 89), private
  leverage (A 21 → 45), amplification (C 42 → 47).
- **High by its own history on comparable inputs:** at or above 97% of months
  since 2015-06, when all 23 components exist (SEVERE in 14% of them); 85% of
  months since 1999-12 on ≥ 75% of inputs (SEVERE in 43%). Counting the thin,
  short-yardstick early months too is not a fair denominator.
- **Recession starts** (reading the month BEFORE the NBER peak; real GDP =
  largest peak-to-trough quarterly fall around the recession):

| recession began | reading before | components | months | unemployment rise | real GDP drawdown |
|---|---|---|---|---|---|
| 1990-07 | 64.9 | 15/23 | 8 | +2.3pp | −1.4% |
| 2001-03 | 66.3 | 18/23 | 8 | +2.0pp | −0.4% |
| 2007-12 | 72.4 | 21/23 | 18 | +5.0pp | −3.8% |
| 2020-02 (exogenous) | 55.1 | 23/23 | 2 | +11.3pp | −9.1% |

- **Nearest readings (±5 of 67.7, ≥ 75% inputs, excluding the last 24
  months):** 1999-12..2002-05 (recession began 2001-03; unemployment +1.7pp
  over 24m); 2006-08..2007-11 (recession began 2007-12; +1.4pp); 2008-06..
  2010-06 (already in recession); 2012-12..2015-05 (no recession; −2.3pp). Of
  the three stretches that began outside a recession, two led into one.

Honesty box: descriptive only — three endogenous recessions cannot validate
a severity index; the ordering 2007 > 2001 ≈ 1990 matches depth only loosely.
The debt-service ratio starts 2005 on FRED (enters ~2015), so every reading
before then runs without it. Household debt before 2005 is Z.1-based (a close
but not identical measure). Point-in-time ranks drift: the 1986-87 readings of
83-93 mostly reflect a short yardstick (equity/GDP making new highs vs a 1976
start). Current-vintage data: rebuilding 5 dates from real-time ALFRED
vintages (v1, before the Z.1 extension) moved them by up to 3 points in no
consistent direction, mostly BEA tech-capex revisions. Publication lags are
approximations (the household-debt series keeps the published series' 460-day
lag for its Z.1 part too — conservative, Z.1 is out ~165 days after the stamp).
Weights set in 2026 with this history in view.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| code, look-ahead, numbers (2026-09-30) | 11 months re-derived independently, all match; BLOCKING: 4 lags too short vs ALFRED (gate checked its own constants); should-fix: live grid ended a month early, method text false, hard-coded prose, vacuous drawn-rule test, endpoint CPU cost, quantify revisions | lags fixed + pinned to ALFRED-verified dates in tests; end=today; method rewritten; prose built from data; drawn test on 1986-03..05; scheduler warm-up, no caching of degraded builds; revisions quantified |
| claims, wording, UI (2026-09-30) | BLOCKING: "SEVERE in 57%" used the thin early years; analog readings lack the #1 predictor and the UI did not say so. Should-fix: C driver, like-for-like trend, percentile wording, episode outcome over its whole span, GDP label, 2020 label, 1990 label | all applied |
