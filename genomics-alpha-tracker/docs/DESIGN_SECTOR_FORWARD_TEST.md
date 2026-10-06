# Design + pre-registration: forward test of a ranked genomics screen

_Status: DESIGN, revision 3 (after calibration and one counter-agent round).
**Recommendation: do not run a forward test now.** On last year's data the
trial-date rankings lost to plain volatility across all names. In small and
mid caps they did no better than a volatility measure that ignores 20%
days. The best hybrid's edge would need about 16 years of forward data to
confirm. The protocol below is complete. It runs only if a better catalyst
source passes the gate first (P1). No production code until Casey approves
this document._

## Recommendation

1. **Do not start a forward test of a ClinicalTrials.gov trial-date
   ranking.** The calibration below shows it cannot pass.
2. **The gate.** A catalyst source with FDA decision (PDUFA) dates and
   company-guided readout timing, and with point-in-time history, must pass
   a retrospective check first. The check takes days, not months, and is
   frozen below.
3. **No-test option.** A reference Sector list of the genomics names, with
   no ranking claim (scope below). It needs no test, because no decision
   depends on it beating anything.

## Calibration on last year (exploratory, not a result)

`research/sector_forward/calibrate.py` (first pass), `calibrate2.py`
(primary), `calibration2.json`, `charts/calibration_*.png`.

- **Universe on day P:** genomics-labelled names, not in the core, with a
  prior-day cap of $300M or more (about 87 a day).
- **Events:** their next-day 20% moves. M&A days are excluded, and events
  are **de-clustered** as in the protocol: a name's further 20% moves
  within the next 10 of its trading days are not counted. That gives 92
  events (7.7 a month), or 90 under $10B (7.5 a month). Without
  de-clustering there are 102 and 100.
- **Trial data:** own phase 2/3 trials via the audited alias table, point in
  time with a 12-day posting lag (exceptions in the honesty box).
- **Baselines:**
  - **B1:** 60-day volatility.
  - **B1x:** 60-day volatility excluding days with a move of 20% or more
    (jump-robust).
  - **Random:** K divided by the universe size.

| top-K hit rate, de-clustered | R1 trial date | R2 readout window | H1 hybrid | B1 volatility | **B1x jump-robust** | random |
|---|---|---|---|---|---|---|
| all caps, top 10 (92 events) | 0% | 1% | 17% | 24% | **29%** | 12% |
| all caps, top 25 | 21% | 20% | 26% | 42% | **51%** | 29% |
| all caps, top 40 | 40% | 33% | 49% | 73% | **75%** | 46% |
| under $10B, top 10 (90 events) | 21% | 19% | 20% | 24% | **30%** | 16% |
| under $10B, top 25 | 47% | 43% | 50% | 43% | **52%** | 40% |
| under $10B, top 40 | 68% | 68% | 73% | 73% | **77%** | 63% |

1. **Across all names, trial dates lose to random.** Big pharma always has
   a trial completing within days and almost never moves 20%, so it fills
   the top of any trial-date list. Of R1's top 25, 61% are names over
   $10B (the robustness reviewer's count).
2. **Under $10B, trial dates only match volatility, and B1x beats them
   all.**
   - **Hybrid H1 vs B1, by list length:**
     - top 25: 14 events only H1 caught vs 8 only B1 caught (one-sided
       sign test p = 0.14);
     - top 10: B1 leads 16 to 12;
     - top 40: tied at 7 to 7.
     
     The top-25 edge is the only positive one, and top 25 was looked at
     after check 1.
   - **Power:** at half the top-25 edge and 7.5 events a month, a forward
     test has 11% power after 12 months, 19% after two years and 38% after
     five. 80% power needs 189 months, about 16 years (exact sign test,
     alpha 0.05, discordance held fixed; computed in `calibrate2.py`).
3. **The readout window carries no reliable signal once volatility and
   size are known.**
   - Mantel-Haenszel odds ratio of a next-day 20% move inside a readout
     window: **1.34** (90% CI 0.83-2.06), over 21,046 de-clustered
     name-days. Under $10B it is 1.43 (0.90-2.11). Without de-clustering it
     is 1.20 (0.72-1.83).
   - Strata are volatility quintile by cap tercile, with the interval from a
     1,000-draw bootstrap over names.
   - The chance of a 20% move per name-day rises about 16x with volatility,
     from 0.05% in the lowest quintile to 0.76% in the highest.
   - Only 24 of the 92 events fell inside a readout window.
4. **This is not a data gap.**
   - Of the 92 events, from 54 names, 69 had a dated upcoming completion on
     P.
   - 18 events come from 10 names with no own phase 2/3 trial: tools and
     diagnostics companies, plus phase-1 companies such as Sana and CAMP4.
   - 5 events come from 4 names whose trials were all past.
5. **Plain volatility partly re-surfaces recent movers.** Under $10B at top
   25:
   - On 16 events whose name had moved 20% in the prior 60 trading days, B1
     hit 88%.
   - On the 74 "fresh" events it hit 34%, below random at 40%. B1x hit 45%,
     R1 45% and H1 41%. No list clearly beats random on fresh events.

**What it means.** ClinicalTrials.gov primary completion dates are a weak
catalyst proxy. Readouts land anywhere from months before the registered
date to a year after it:
- ENGN's pivotal data moved the stock 7 months before its registered
  completion;
- SLN's topline came 39 days early;
- SRPT's ESSENCE failure came about a year after its completion date.

Three in four big genomics moves are not near a completion date at all. A
forward test of any ranking built on these dates would spend months or
years confirming what last year already shows.

**Robustness (counter-agent, exploratory).** The reviewer tried 27
alternatives:
- horizons of 5 and 20 trading days;
- phase 3 only;
- six readout-window bounds;
- up and down moves separately;
- few-trial names;
- fresh-event cuts;
- H1 against B1x.

None gives an odds ratio whose lower bound clears 1. The one nominally
significant cut (R1 over B1 on fresh events) does not survive the
multiplicity. It comes from B1 falling below random, not from R1 beating
random.

**Calibration honesty box.**
- **(a) Look-ahead.** Labels and the alias table date from 2026-10-06 and
  are applied to the past year. The direction of the bias is not known.
- **(b) Not point in time for large caps.** 3,244 point-in-time-relevant
  own studies, beyond the 60-per-name history cap, use their current
  record. They sit in 12 large caps (MRK, AZN, BMY, NVS, PFE, JNJ, SNY, GSK,
  LLY, REGN, AMGN, GILD) and MRNA, plus 1 each in AUTL, BNTX, CRSP, IMTX, LH
  and RCKT. The under-$10B analysis is therefore close to fully point in
  time; the all-cap one is not.
- **(c) Stale trial data.** The 12-day lag is the 95th percentile of
  first-post minus version-0 gaps, applied to every version. A live
  snapshot would see fresher records. That biases the calibration against
  trial rankings, slightly.
- **(d) Post-hoc choices.** The $10B cut, H1, top 25 and B1x were chosen
  after check 1, so expect a winner's curse. Checks 2-3 were written into
  `calibrate2.py`'s docstring after check 1 was seen, and no separate
  commit witnesses that order. Checks 4-5 were added after the review.
- **(e) Pooled cut points.** Quintile and tercile cut points are pooled over
  the whole panel.
- **(f) Different definition in the first pass.** `calibrate.py` was not
  de-clustered. `calibration2.json` carries both versions, with the
  de-clustered one primary.

## The gate (frozen now)

Run the forward test only if a better catalyst source passes all of the
following on the past year (2025-10-01 to 2026-09-30).

**Point in time, or no gate.** Each catalyst record must carry a first-seen
or as-of timestamp, from vendor history or archived snapshots. On day P,
only catalyst dates known by P's close count. Later revisions are
invisible, so a date first shown on P+1 does not count on P. Records
without provenance count as no catalyst. Before any statistic is computed,
20 randomly drawn sourced catalysts (seed 20261006) are checked by hand for
point-in-time correctness. If the source has no vintage history, the gate
cannot run retrospectively. It then becomes a three-month forward logging
period of the source, followed by this same check.

**Guided timing, frozen mapping.**

| guidance | window |
|---|---|
| an exact date | that day |
| "Qn YYYY" | the quarter |
| "1H" / "2H YYYY" | the half |
| "mid-YYYY" | June 1 to July 31 |
| "early YYYY" | January 1 to April 30 |
| "late" / "end YYYY" | September 1 to December 31 |
| "YYYY" alone | the year |

A name is exposed on P if any of its catalyst windows overlaps [P-7d,
P+30d]. Both PDUFA and readout catalysts count, and names the source does
not cover count as unexposed.

**Statistics.**
- **Events:** de-clustered, M&A excluded, cap under $10B on P.
- **Odds ratio:** the Mantel-Haenszel odds ratio of exposure on the
  de-clustered panel, strata and bootstrap as in check 3, seed 20261006.
- **H1′:** exposed names first, each group ordered by B1x.

**Pass if ALL of these hold:**
1. the odds ratio's lower 90% bound is above 1.0;
2. at the desk's list length K (P2), H1′ beats B1x with an exact one-sided
   sign-test power of at least 80% within 12 months. Power is computed on
   half the in-sample paired edge, with discordance held fixed, at the
   de-clustered event rate. For reference, at last year's 22% discordance
   this needs an in-sample edge of roughly 25 percentage points;
3. H1′ is no worse than B1x at the other two list lengths of 10, 25 and 40
   (point estimates).

Otherwise no forward test is run, and the result is recorded here.

## The Sector list (needs no test; Casey's call)

A reference view: every genomics-labelled name that is listed with a cap
of $300M or more (about 100 today, core names flagged and names over $10B
flagged). Each row shows the name's next dated trial completion and next
sourced catalyst if a source exists, as context only. A caption on the
view says: "Trial dates are context, not a catalyst signal; ranking by the
nearest completion was below random last year."

The default sort is B1x (jump-robust volatility), last year's best simple
list for next-day 20% moves. Plain volatility mostly re-surfaces names that
just moved.

Trial context needs the alias table in production, because the shipped
`clean_company_name()` finds no trials for about a third of these names.
Until it ships, the row says "no matched trials", never a blank. The list
makes no ranking claim, and nothing is generated from it.

## The protocol (runs only if the gate passes)

### Frozen at the start (T0)

| input | frozen as |
|---|---|
| Genomics labels | `research/sector_tier/labels.json` (722 names, two blind labellers + adjudicator) |
| Catalyst source | its name, the vintage policy above, the guided-timing mapping, the snapshot ID at T0 |
| Alias table | `research/sector_forward/aliases.json` (audited); trial context only, not in any ranking |
| Rankings, K, baselines, events, decision rule, formulas | this document; K from the P2 answer, recorded at T0 |
| Code | the snapshot job and `evaluate.py`, by commit SHA recorded here at T0 |

**Universe on day P:** genomics-labelled names that are listed, not in the
core, with a prior-day cap of at least $300M and under $10B, evaluated
daily. A name that crosses $10B leaves the universe while it is above it.
Names that become eligible during the test (IPOs, a cap crossing $300M)
are outside the frozen labels; their moves are counted and reported
separately.

### The instrument: one ranked snapshot per weekday

The snapshot runs after the 21:45 UTC discovery sweep and is dated by the
screener's as-of date. For every universe name it records:
- the ranks under H1′, B1x, B1 and B2;
- the catalyst ID, source, date window and as-of timestamp behind H1′;
- 60-day volatility, B1x volatility, 20-day dollar volume and cap;
- the code SHA.

Rows are insert-only: unique on (as-of, symbol), never updated. A daily
SHA-256 is taken over the sorted rows. If an event's day P has no
snapshot, the latest one within 3 trading days stands in; otherwise the
event is excluded and counted. More than 10% of weekdays missing voids the
test as an operational failure.

### Rankings and baselines

- **H1′ (R\*).** Names with a sourced catalyst window overlapping
  [P-7d, P+30d] first, then the rest. Each group is ordered by B1x, with
  ties broken by 20-day dollar volume. Catalyst data are as known at the
  snapshot.
- **B1x (the baseline H1′ must beat).** 60-day volatility of daily log
  returns over the last 61 closes, excluding returns of 20% or more.
- **B1.** Plain 60-day volatility (secondary).
- **B2.** The live Discovery queue in candidate-score order, as the
  Discovery tab shows it. It is logged in the snapshot before the sweep's
  upserts of that day (secondary).
- **Random.** K divided by the universe size.

### Events (the outcome)

These are measured after the fact from FMP dividend-adjusted bars:
- a one-day close-to-close move of 20% or more (absolute value, rounded to
  9 decimals), with a prior-day cap of $300M or more and under $10B;
- the name is in the universe on P;
- adjustment artifacts are excluded (price change vs cap change mismatch
  over 50%);
- M&A target days are excluded, decided by two blind reviewers from filings
  and headlines with a third on disagreement (the sector-tier prompt);
- events are de-clustered: a name's further 20% moves within the next 10
  of its trading days are not counted. Sector-wide days are reported.

### Metric and decision rule (frozen; formulas fixed now)

**Primary metric:** hit@K, the share of events whose name ranked within
the top K on P's snapshot. It is compared paired between H1′ and B1x with
a one-sided exact sign test on the discordant events, alpha 0.05.

**Formulas fixed now:**
- **DELTA** is half the gated in-sample edge, in percentage points.
- **N_min** is the event count at which the gate's power reaches 80%.
- **The end date** is T0 plus the months the gate's power calculation needs
  (12 or fewer). There is no extension. Fewer than N_min events at the end
  date makes the result INCONCLUSIVE.

**BUILD** a ranked screen (the top K with each name's catalyst evidence;
no calls generated) only if ALL of these hold:
1. at least N_min events;
2. hit@K(H1′) minus hit@K(B1x) is at least DELTA;
3. the sign test gives p < 0.05;
4. hit@K(H1′) is above random;
5. hit@K(H1′) is at least hit@K(B2).

Otherwise the result is DO NOT BUILD, with the reason. There are no interim
looks at the metric; monitoring is operational only.

**Secondary metrics, not gating:**
- hit@K at the other two list lengths;
- hit@K on readout-driven events (cause labelled from headlines by two
  blind reviewers);
- lead time (top K on each of the 5 prior trading days);
- up and down moves separately;
- fresh vs recent movers;
- B1 and B2 levels;
- moves by new entrants.

### Where the snapshot runs (asked only if the gate passes)

- **A. Inside the genomics service.** It hooks in after the sweep, uses an
  insert-only table, and exposes a GET-only export route with its own
  read-only token, following `BLEND_API_TOKEN` in `app/main.py`. A weekly
  Routine commits the export to git as the timestamped witness. Casey sets
  the token on Render and in this environment, and redeploys once.
- **B. A daily Claude Code Routine** commits each day's file. It needs no
  production change but costs one model session per weekday.

## Honesty box (forward test)

- **hit@K measures attention ranking, not P&L.** A top-K name is not a
  tradeable call, and the direction of the move is not predicted.
- **Catalyst dates are imperfect.** Guided windows are coarse, and some
  readouts are never announced or land outside any window.
- **Labels are frozen at T0.** A company that changes modality keeps its
  label.
- **Expect regression.** H1′ is judged on half its in-sample edge for
  exactly that reason.
- **B1x is a strong, free baseline.** "Sort by jump-robust volatility, it is
  simpler" is a legitimate outcome.

## Pending questions (ledger; 60-day expiry from first ask)

| P | question | what it moves | first asked | status | expires |
|---|---|---|---|---|---|
| P1 | Is there a catalyst source with PDUFA dates and guided readout timing AND point-in-time history (vendor vintages or archived snapshots), one you have or one you would pay for? | whether the gate runs at all | 2026-10-06 | open | 2026-12-05 |
| P2 | What the desk would do with a ranked screen: a morning glance (top 10) or position preparation (top 25, 5-day lead time) | the list length K and the gating metric, needed before the gate | 2026-10-06 (rev 1, then P3) | open; promoted 2026-10-06 (rev 3) | 2026-12-05 |
| P2 | Build the reference Sector list (no test needed)? | one dashboard view | 2026-10-06 | open | 2026-12-05 |
| P3 | Where the snapshot runs (A or B) | the instrument | 2026-10-06 (rev 1) | deferred to the gate (rev 2) | — |
| — | The end date | — | 2026-10-06 (rev 1) | withdrawn (rev 3): now a formula | — |
| — | Show the ranked list during the test | — | 2026-10-06 (rev 1) | withdrawn (rev 2): no test running | — |

The sector-tier production export question lives in that study's ledger.

## Separate finding: the shipped funnel's CT.gov queries

`clean_company_name()` leaves listing boilerplate in about a third of
genomics names:
- "Common Shares";
- "N V" and "S A";
- the misspelling "Depository".

CT.gov's sponsor search then returns nothing. Sponsors also register under
other names ("Autolus Limited", "ModernaTX, Inc."). The live catalyst lane
is blind to those names today. The audited `aliases.json` is the fix's raw
material. Fixing this is a funnel recall change with its own review; this
design does not depend on it.

## Counter-agent verdict

**Round 1 (2026-10-06, 35 agents).**
- **Blind re-implementation:** it reproduced every headline calibration
  number. It found two small spec gaps: the volatility window (61 closes
  vs 60) and trial phases taken from the current record. Neither moves a
  metric.
- **Robustness reviewer:** it tried 27 alternatives, and the
  recommendation stands.
- **Confirmed findings, all applied in this revision:**
  - SERIOUS: the calibration was not de-clustered. It now is, and B1's
    level fell from 49% to 43%.
  - SERIOUS: the 5-point gate admitted an approximately 9%-power test, and
    the CT.gov hybrid already cleared it. It is now a power condition.
  - SERIOUS: the gate did not require point-in-time catalyst data. Now it
    does, with a vintage rule, a frozen guided-timing mapping and a hand
    spot-check.
  - SERIOUS: the hybrid's edge existed only at top 25. All list lengths are
    now reported; K comes from the desk answer and the other two list
    lengths must not lose.
  - SERIOUS: rev-1 text left in the protocol. It has been rewritten for
    H1′, B1x, the under-$10B universe and the new source.
  - SERIOUS: "at least twice random" was unreachable in the gated universe.
    It is now "above random", with the B1x comparison carrying the bar.
  - SERIOUS, later rated MINOR: no calibration honesty box. Added.
  - SERIOUS, later rated MINOR: the desk-use question was ranked P3 while K
    was frozen. Promoted, with ledger hygiene.
  - MINOR: undefined N_min, DELTA and end dates (now formulas); power
    figures in no committed code (now in `calibrate2.py`); wording and unit
    errors; readouts also come before the registered date; the Sector
    list's scope; the order of declaration.
- **B1x** (jump-robust volatility) came from the robustness review. It beat
  every list at every K, and it is now the baseline H1′ must beat.
