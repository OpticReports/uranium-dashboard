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

## RESULTS — frozen 2026-09-30 (`severity_history/results.json`, v1 lags)

- **Trend:** 51.5 (Dec-2023) → 58.4 (Dec-2024) → 67.3 (Dec-2025) → 68.9 today
  (live). Drivers, Dec-2023 → live: tech capex (block F 47 → 89), private
  leverage (A 28 → 48), amplification (C 42 → 47).
- **High by its own history on comparable inputs:** at or above 96% of months
  since 2016-04, when all 23 components exist (SEVERE in 23% of them); 82% of
  months since 2001-06 on ≥ 75% of inputs (SEVERE in 42%). Counting the
  thin, short-yardstick 1986-2001 months too, SEVERE in 57% — not a fair
  denominator.
- **Recession starts** (reading the month BEFORE the NBER peak; real GDP =
  largest peak-to-trough quarterly fall around the recession):

| recession began | reading before | components | months | unemployment rise | real GDP drawdown |
|---|---|---|---|---|---|
| 1990-07 | 63.2 | 14/23 | 8 | +2.3pp | −1.4% |
| 2001-03 | 67.5 | 17/23 | 8 | +2.0pp | −0.4% |
| 2007-12 | 71.4 | 20/23 | 18 | +5.0pp | −3.8% |
| 2020-02 (exogenous) | 57.9 | 23/23 | 2 | +11.3pp | −9.1% |

- **Nearest readings (±5 of 68.9, ≥ 75% inputs, excluding the last 24
  months):** 2001-06..2002-02 (already in recession; unemployment +1.8pp over
  24m); 2007-03..2010-04 (recession began 2007-12; +4.3pp); 2012-09..2015-05
  (no recession; −1.9pp). Of the two stretches that began outside a
  recession, one led into one. At a 70% input threshold a 1999-12..2002-02
  stretch (recession 2001-03) also qualifies: two of three.

Honesty box: descriptive only — three endogenous recessions cannot validate
a severity index; the ordering 2007 > 2001 > 1990 matches depth only loosely
(2001 read 68 and was the mildest). Every past reading lacks household
debt/GDP and debt service (FRED starts them in 2005; they enter in 2016), so
it is a smaller index than today's; letting them in on their short history
lowers 2012-15 by 2-3 points. Point-in-time ranks drift: the 1986-87 readings
of 83-93 mostly reflect a short yardstick (equity/GDP making new highs vs a
1976 start). Current-vintage data: rebuilding 5 dates from real-time ALFRED
vintages moved them by up to 3 points in no consistent direction (2020-01
54.4 vs 57.4; 2015-12 58.3 vs 59.9; 2023-12 48.8 vs 49.6; 2024-12 61.4 vs
59.5; 2007-11 72.7 vs 71.4), mostly BEA tech-capex revisions. Publication lags
are approximations (the rebuilt Sep-2026 point is 69.5 vs the live 68.9).
Weights set in 2026 with this history in view.

### Counter-agent log

| review | verdict | adopted |
|---|---|---|
| code, look-ahead, numbers (2026-09-30) | 11 months re-derived independently, all match; BLOCKING: 4 lags too short vs ALFRED (gate checked its own constants); should-fix: live grid ended a month early, method text false, hard-coded prose, vacuous drawn-rule test, endpoint CPU cost, quantify revisions | lags fixed + pinned to ALFRED-verified dates in tests; end=today; method rewritten; prose built from data; drawn test on 1986-03..05; scheduler warm-up, no caching of degraded builds; revisions quantified |
| claims, wording, UI (2026-09-30) | BLOCKING: "SEVERE in 57%" used the thin early years; analog readings lack the #1 predictor and the UI did not say so. Should-fix: C driver, like-for-like trend, percentile wording, episode outcome over its whole span, GDP label, 2020 label, 1990 label | all applied |
