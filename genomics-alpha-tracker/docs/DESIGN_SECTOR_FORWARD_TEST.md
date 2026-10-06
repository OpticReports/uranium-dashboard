# Design + pre-registration: forward test of a ranked genomics screen

_Status: DESIGN, revision 2 (after calibration, before counter-agent review).
**Recommendation: do not start the forward test as specified.** On last
year's data, the trial-date rankings did no better than plain volatility,
and worse among all names. Even the best hybrid's edge would take years of
forward data to confirm. The protocol below is kept complete and ready, and
is gated on a better catalyst source (P1). No production code until Casey
approves this document._

## Calibration on last year (exploratory, not a result)

`research/sector_forward/calibrate.py`, `calibrate2.py`,
`calibration*.json`, `charts/calibration_*.png`.

- **Universe on day P:** genomics-labelled names, not in the core, with a
  prior-day cap of $300M or more (86 on average).
- **Events:** their next-day 20% moves with M&A days excluded (102; 8.5 a
  month).
- **Trial data:** own phase 2/3 trials through the audited alias table,
  point in time with a 12-day posting lag.

Checks 2-4 below were declared after check 1's result and before they were
computed.

1. **The pre-registered rankings lose to volatility, and R1 and R2 lose to
   random too.** Top-25 hit rate: R1 (nearest completion) 20%, R2 (readout
   window) 19%, B1 (60-day volatility) 48%, random 29%. Top 10: 0%, 1%,
   30% and 12%. The cause is big pharma, which always has a trial
   completing within days and almost never moves 20%. It fills the top of
   any trial-date list.
2. **Without big pharma, trial dates only match volatility.** Over caps
   under $10B (100 of the 102 events), the top-25 hit rate is R1 48%, B1
   49%, random 40%. H1 (readout-window names first, each group ordered by
   volatility) is 55%. Against B1, the discordant events are 14 H1-only and
   8 B1-only. That is not significant even in-sample (one-sided sign test
   p = 0.14). At half that edge and 8.5 events a month, a forward test has
   11% power after 12 months, 22% after two years and 41% after five
   (simulated exact sign test, alpha 0.05).
3. **The readout window carries no reliable signal once volatility is
   known.**
   - Over 22,000 name-days, the Mantel-Haenszel odds ratio of a next-day
     20% move inside a readout window is 1.20 (90% CI 0.72-1.83, bootstrap
     over names). Strata are volatility quintile by cap tercile.
   - Volatility alone spans a 20x range: 0.05% a day in the lowest
     quintile, 0.92% in the highest.
   - Only 25 of the 102 moves happened inside a readout window.
4. **This is not a data gap.** 77 of the 102 moving names had a dated
   upcoming completion on P. The 10 with no own phase 2/3 trial are mostly
   tools and diagnostics companies.

**What it means.** ClinicalTrials.gov primary completion dates are a weak
catalyst proxy. Readouts follow them by an unknown lag, and three in four
big genomics moves are not near one. A forward test of any ranking built
on them would spend 6-12 months confirming what the calibration already
shows.

## The gate before any forward test

Run the forward test only after a better catalyst source passes a
retrospective check. That source would carry PDUFA dates and
company-guided readout timing, for example a commercial biotech catalyst
calendar. The check is cheap: days of work, not months.

- **Gate check (frozen now).** On the past year, with the new source:
  - the Mantel-Haenszel odds ratio of a next-day 20% move for names with a
    sourced catalyst within [P-7d, P+30d], with the same strata and name
    bootstrap as check 3;
  - and the hybrid H1' (sourced-catalyst names first, then by volatility)
    against B1, over caps under $10B, top 25.
- **Gate:** the odds ratio's lower 90% bound is above 1.0, AND H1' beats
  B1 by at least 5 percentage points in-sample. If either fails, the
  forward test is not run.
- **If the gate passes:** the protocol below runs with R\* = H1', K = 25,
  the universe restricted to caps under $10B, and the duration set by the
  power calculation on half the in-sample edge, at no more than 12 months.

## What can be built without any test (Casey's call)

A reference **Sector list**: the 133 genomics-labelled names, sortable by
volatility, with each name's next dated trial completion shown as context.
It makes no ranking claim. It is what "look at the entire sector" means
in practice, at the cost of one view. No decision hinges on it beating
anything, so it needs no test.

## Why this test

The sector-tier study (`DESIGN_SECTOR_TIER.md`, results 2026-10-06) found
that the shipped discovery funnel had already queued 125 of 127 genomics
20% movers before they moved. But the queue held about 540 names, and a
name sitting in a 540-name list has not been seen in any useful sense. The
open question is ranking, not coverage: does a short list of genomics
names, built each evening from data available that evening, put the next
day's big genomics movers at the top more often than the obvious
alternatives?

A forward test answers this without the look-ahead that limited the
retrospective study. Labels, aliases, rankings, list length and the
decision rule are frozen before any test-period data exist.

## The protocol (runs only if the gate passes)

### What is frozen at the start (T0)

| input | frozen as | why |
|---|---|---|
| Genomics labels | `research/sector_tier/labels.json` (722 names, two blind labellers + adjudicator, amendment-1 mandate) | the universe; no mid-test relabelling |
| Sponsor alias table | `research/sector_forward/aliases.json`, after its two-reviewer audit | the shipped name-to-sponsor cleaning finds zero trials for about a third of genomics names (`"uniQure N V"`, `"CRISPR Therapeutics AG Common Shares"`); a trial-date ranking is blind without it |
| Ranking, list length K, baselines, events, decision rule, end date | this document | one confirmatory comparison |
| Code | the snapshot job and `evaluate.py`, by commit SHA recorded here at T0 | the instrument cannot drift |

Names that become eligible during the test (IPOs, a cap crossing $300M)
are outside the frozen universe. Their moves are counted and reported
separately, never in the primary metric.

### The instrument: one ranked snapshot per weekday

The snapshot runs every weekday after the close, alongside the 21:45 UTC
discovery sweep, and is dated by the screener's as-of date (the sweep's own
gate). It covers every frozen-universe name that is listed, NOT in the core
that day, and has a prior-day cap of $300M or more. For each name it
records:

- the rank under the chosen ranking R\* and under each baseline;
- the inputs behind those ranks: days to catalyst, the NCT number and
  primary completion date that set it, 60-day volatility, 20-day dollar
  volume, and cap;
- the code SHA.

Rows are insert-only: unique on (as-of, symbol) and never updated. Each
day also stores a SHA-256 over its sorted rows. Catalyst data come from the
name's own phase 2/3 trials, matched through the alias table and refreshed
weekly (each name on its weekday, crc32 % 5). Prices and volume come from
FMP daily bars.

**Missed days.** If no snapshot exists for an event's prior day P, the
latest snapshot within the previous 3 trading days stands in. If there is
none, the event is excluded and counted. More than 10% of weekdays missing
voids the test (operational failure, not a result).

### Rankings (calibration ruled out R1 and R2 as specified; the gated R* is H1')

All rankings use catalyst data as of the Monday on or before P, matching the
weekly refresh.

- **R1 catalyst.** Days to the nearest primary completion date on or after P
  among the name's own phase 2/3 trials with an active status. Ties go to
  higher 20-day dollar volume. Names without one come last, ordered by
  dollar volume. This is the sort pre-registered for the original Sector
  screen.
- **R2 readout window.** The name has an own phase 2/3 trial whose primary
  completion falls between 120 days before P and 30 days after it, and
  whose status is active or COMPLETED. Top-line readouts usually come weeks
  to months after primary completion. Phase 3 ranks before phase 2, then the
  nearest date first. Names without one come last, ordered by dollar
  volume.

### Baselines

- **B1 volatility (the gate).** 60-trading-day realized volatility, highest
  first. "The names that move a lot will move a lot" is free to compute and
  needs no trial data. A ranking that cannot beat it adds nothing a desk
  needs.
- **B2 Discovery tab (secondary).** The live discovery queue ordered by its
  candidate score, as the Discovery tab shows it, logged in the same
  snapshot. It cannot be calibrated, because the queue's past scores were
  not stored.
- **Random.** K divided by the universe size.

### Events (the outcome)

The same definition as the sector-tier study, measured after the fact from
FMP dividend-adjusted bars:

- a one-day close-to-close move of 20% or more (absolute value, rounded to
  9 decimals);
- a prior-day cap of $300M or more;
- the name is in the frozen universe and not in the core on P;
- M&A target days and adjustment artifacts (price change vs cap change
  mismatch over 50%) are excluded;
- M&A days are decided by two blind reviewers from filings and headlines,
  with a third on disagreement, using the same prompt as the study;
- **de-clustered:** once a name's event is counted, its further 20% moves
  within the next 10 trading days are not counted again. They are usually
  the second day of the same news (KYTX on 12-15 and 12-17, IBRX on 01-15
  and 01-16), and counting them would overstate the evidence. Events on
  the same day in different names count separately; the sector-wide days
  that produce them are reported.

### Metric and decision rule (frozen)

**Primary: hit@K.** The share of events whose name ranked within the top K
on the snapshot of P, under R\* and under B1. The comparison is paired, by
event: a one-sided exact sign test on the discordant events (R\* hit while
B1 missed, against B1 hit while R\* missed), alpha = 0.05.

**BUILD** the ranked Sector screen (a dashboard panel: the top K with each
name's catalyst evidence; no calls generated from it) if, at the end date,
ALL of these hold:

1. at least N_min events;
2. hit@K(R\*) minus hit@K(B1) is at least DELTA percentage points;
3. the sign test gives p < 0.05;
4. hit@K(R\*) is at least twice random;
5. hit@K(R\*) is at least hit@K(B2) (non-inferior to what the Discovery tab
   already shows).

If there are fewer than N_min events at the end date, the test extends once
to the maximum end date. If there are still fewer, the result is
INCONCLUSIVE. Otherwise the result is DO NOT BUILD, with the reason. There
are no interim looks at the metric. Monitoring during the test is
operational only: the job ran, row counts, missed days.

**Secondary, reported but not gating:**

- hit@K on all genomics events, core names included;
- hit@K on readout-driven events: each event's cause (readout, regulatory,
  earnings, financing, other) is labelled from headlines by two blind
  reviewers;
- lead time: the share of events whose name was in the top K on each of
  the 5 prior trading days;
- up moves vs down moves;
- moves by new entrants (outside the frozen universe).

### Duration and power

Set at the gate (see above). Computed on HALF the gated in-sample edge, at 80% power, and capped at 12 months.

### Where the snapshot runs (asked only if the gate passes)

- **A. Inside the genomics service (recommended).** It runs right after the
  discovery sweep and reuses the census, CT.gov and FMP code paths, at no
  per-day cost. It needs:
  - a new insert-only table;
  - an export route with its own read-only token, following the
    BLEND_API_TOKEN pattern (one route, GET only, every other route still
    Basic-gated);
  - a weekly Routine that pulls the export and commits it to git. That
    commit is the timestamped, append-only witness that the snapshots
    existed before the moves they are scored against.

  Casey sets `RESEARCH_EXPORT_TOKEN` on Render and in this environment, and
  redeploys once.
- **B. A daily Claude Code Routine** runs the snapshot script in a fresh
  cloud session and commits each day's file. This needs no production
  change, but it costs one model session per weekday (about 130 over six
  months) and has its own failure modes.

## Honesty box

- hit@K measures attention ranking, not P&L. A name in the top K is not a
  tradeable call, and the direction of the move is not predicted.
- A primary completion date is not a readout date. Readouts lag it by weeks
  to months, and some are never announced.
- Labels and aliases are frozen at T0. A company that changes modality
  during the test keeps its label.
- Winner's curse: R\* and K are chosen on last year's data. Expect the
  forward hit rate to be lower than the calibration figure. Power is
  therefore computed on HALF the calibrated advantage.
- B1 is a strong baseline. "Rank by volatility, it is simpler" is a
  legitimate outcome.

## Pending questions (ranked; asked / answered / refused / expired)

| P | question | what it moves | status |
|---|---|---|---|
| P1 | Is there a catalyst source with PDUFA dates and guided readout timing (one you have, or a commercial calendar you would pay for)? Without one, no forward test is worth running. | whether the gate check and any forward test happen | asked 2026-10-06 |
| P2 | Build the reference Sector list (133 genomics names, sortable, trial dates as context, no ranking claim)? | one dashboard view | asked 2026-10-06 |
| P2 | If the gate passes: where the snapshot runs (A, the service plus a read-only export plus a weekly git witness; or B, a daily Routine), and the end date | the instrument | deferred to the gate |
| P3 | What the desk would do with a ranked screen: a morning glance or position preparation | which metric gates | deferred to the gate |
| P3 | Production export from the sector-tier study | nothing here | asked 2026-10-05 |

## Separate finding: the shipped funnel's CT.gov queries

`clean_company_name()` leaves listing boilerplate in about a third of
genomics names ("Common Shares", "N V", "S A", the misspelling "Depository"),
and CT.gov's sponsor search then returns nothing. The live catalyst lane is
blind to those names today. Fixing this is a funnel recall change with its
own review. The forward test does not depend on it, because B2 is logged as
it ships.
