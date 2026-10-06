# Design + pre-registration: forward test of a ranked genomics screen

_Status: DESIGN, revision 1 (before counter-agent review). No production
code until Casey approves this document and answers the P1 questions. The
calibration numbers below come from the PAST year and only set the test's
free parameters; they are not results. Results are appended at the end of
the test, never edited in._

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

## What is frozen at the start (T0)

| input | frozen as | why |
|---|---|---|
| Genomics labels | `research/sector_tier/labels.json` (722 names, two blind labellers + adjudicator, amendment-1 mandate) | the universe; no mid-test relabelling |
| Sponsor alias table | `research/sector_forward/aliases.json`, after its two-reviewer audit | the shipped name-to-sponsor cleaning finds zero trials for about a third of genomics names (`"uniQure N V"`, `"CRISPR Therapeutics AG Common Shares"`); a trial-date ranking is blind without it |
| Ranking, list length K, baselines, events, decision rule, end date | this document | one confirmatory comparison |
| Code | the snapshot job and `evaluate.py`, by commit SHA recorded here at T0 | the instrument cannot drift |

Names that become eligible during the test (IPOs, a cap crossing $300M)
are outside the frozen universe. Their moves are counted and reported
separately, never in the primary metric.

## The instrument: one ranked snapshot per weekday

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

## Rankings (one is chosen at T0 from calibration; see below)

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

## Baselines

- **B1 volatility (the gate).** 60-trading-day realized volatility, highest
  first. "The names that move a lot will move a lot" is free to compute and
  needs no trial data. A ranking that cannot beat it adds nothing a desk
  needs.
- **B2 Discovery tab (secondary).** The live discovery queue ordered by its
  candidate score, as the Discovery tab shows it, logged in the same
  snapshot. It cannot be calibrated, because the queue's past scores were
  not stored.
- **Random.** K divided by the universe size.

## Events (the outcome)

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

## Metric and decision rule (frozen)

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

## Duration and power (from calibration)

CALIBRATION_PLACEHOLDER

## Where the snapshot runs (P1 for Casey)

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
| P1 | Where the snapshot runs: A (service + read-only export token + weekly git witness) or B (daily Routine) | the instrument; the token and redeploy are Casey's | asked 2026-10-06 |
| P1 | The end date: the default and the maximum (see power) | the decision date | asked 2026-10-06 |
| P2 | What the desk would do with the screen: a morning glance (hit on the prior day is primary) or position preparation (5-day lead time becomes primary) | which metric gates | asked 2026-10-06 |
| P3 | Show the ranked list in the dashboard during the test (it cannot contaminate the outcome) or keep it log-only | UI scope | asked 2026-10-06 |
| P3 | Production export from the sector-tier study (the earlier P1, still unanswered) | nothing in this test; cross-check only | asked 2026-10-05 |

## Separate finding: the shipped funnel's CT.gov queries

`clean_company_name()` leaves listing boilerplate in about a third of
genomics names ("Common Shares", "N V", "S A", the misspelling "Depository"),
and CT.gov's sponsor search then returns nothing. The live catalyst lane is
blind to those names today. Fixing this is a funnel recall change with its
own review. The forward test does not depend on it, because B2 is logged as
it ships.
