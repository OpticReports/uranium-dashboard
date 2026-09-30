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
| monthly (core PCE, saving rate, inventories/sales, months' supply, FINRA margin) | 60 days |
| quarterly (GDP, Z.1, BIS, DSR, delinquencies, vacancies, median price, capex, federal debt/GDP, DFA) | 180 days |
| annual federal deficit (FY, stamped Jan 1) | 300 days |
| annual median household income (stamped Jan 1, published Sep of next year) | 630 days |

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

## RESULTS — frozen 2026-09-30 (`severity_history/results.json`)

- **Trend:** 49.6 (Dec-2023) → 58.1 (Dec-2024) → 67.2 (Dec-2025) → 68.9 today
  (live). Drivers: tech capex (block F 47 → 89), private leverage (A 22 → 48),
  amplification (C 42 → 50).
- **Not rare by its own history:** SEVERE (>60) in 57% of drawn months since
  1986; today is above 82% of months since 2001-06 (≥ 75% of inputs live).
- **Recession starts** (reading the month before the NBER peak):

| peak | reading | inputs | months | unemployment rise | real GDP |
|---|---|---|---|---|---|
| 1990-07 | 60.9 | 14/23 | 8 | +2.3pp | −1.4% |
| 2001-03 | 67.6 | 17/23 | 8 | +2.0pp | −0.4% |
| 2007-12 | 70.7 | 20/23 | 18 | +5.0pp | −3.8% |
| 2020-02 (exogenous) | 57.3 | 23/23 | 2 | +11.3pp | −9.1% |

- **Nearest readings (±5 of 68.9, ≥ 75% inputs, excluding the last 24
  months):** 2001-06..2002-02 (already in recession; unemployment +1.8pp over
  24m); 2007-03..2010-02 (recession began 2007-12; +4.3pp); 2012-09..2015-06
  (no recession; −1.9pp). One of the two pre-recession stretches led into one.

Honesty box: descriptive only — three endogenous recessions cannot validate
a severity index; the ordering 2007 > 2001 > 1990 matches depth only loosely
(2001 read 68 and was the mildest). Point-in-time ranks drift: before ~1997
several components rank against 10-20 years, so the 1986-89 readings of
85-93 mostly reflect a short yardstick (equity/GDP making new highs vs a
1976 start). Household debt/GDP and the debt-service ratio start 2005 on
FRED, so the index's own "THE severity predictor" is absent from the history
before 2015 — the 1990/2001/2007 readings are built without it. Publication
lags are approximations (the rebuilt Sep-2026 point is 69.5 vs the live 68.9
because the lags drop the newest prints). Current-vintage data; weights set
in 2026 with this history in view.
