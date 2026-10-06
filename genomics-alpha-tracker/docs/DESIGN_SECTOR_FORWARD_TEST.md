# Design + pre-registration: forward test of a ranked genomics screen

_Status: DESIGN, revision 4 (after calibration and two counter-agent rounds).
**Recommendation: do not run a forward test now.** On last year's data the
trial-date rankings lost to plain volatility across all names. In small and
mid caps they did no better than a volatility measure that ignores 20%
days. Against volatility, the best hybrid's edge would need about 16 years
of forward data to confirm; against jump-robust volatility it has none. The protocol below is complete. It runs only if a better catalyst
source passes the gate first (P1). No production code until Casey approves
this document._

## Recommendation

1. **Do not start a forward test of a ClinicalTrials.gov trial-date
   ranking.** The calibration below shows it cannot pass.
2. **The gate.** A catalyst source with FDA decision (PDUFA) dates and
   company-guided readout timing, and with point-in-time history, must pass
   a retrospective check first. The check takes days, not months, and is
   frozen below. It takes days if the source has vintage history; without
   it there is no gate.
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
- **Rankings tested:**
  - **R1:** days to the nearest completion date on or after P among own
    phase 2/3 trials with an active status, nearest first.
  - **R2:** names with an own phase 2/3 trial (active or COMPLETED) whose
    completion falls in [P-120d, P+30d] come first; phase 3 before phase
    2, then nearest.
  - **H1:** names in that readout window first, each group ordered by B1.
  
  Trial data are as of the Monday on or before P, with the 12-day lag. The
  gate's window ([P-7d, P+30d], sourced catalysts) and its ordering (by
  B1x) differ from these on purpose.
- **De-clustering in the panel:** the 10-trading-day window runs from the
  last COUNTED event. Anchors are the name's non-M&A, non-artifact
  genomics-labelled 20% moves. Name-days whose next trading day falls
  within the 10 trading days after a counted event leave the odds-ratio
  panel.

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
   $10B (`calibrate2.py`, all-cap event days).
2. **Under $10B, trial dates only match volatility, and B1x beats them
   all.**
   - **Hybrid H1 vs B1, by list length:**
     - top 25: 14 events only H1 caught vs 8 only B1 caught (one-sided
       sign test p = 0.14);
     - top 10: B1 leads 16 to 12;
     - top 40: tied at 7 to 7.
     
     The top-25 edge is the only positive one, and top 25 was looked at
     after check 1.
   - **Hybrid H1 vs B1x:** H1 trails at every list length:
     - top 10: 10 vs 19;
     - top 25: 14 vs 16 (p = 0.71);
     - top 40: 6 vs 9.
     
     There is no edge to power.
   - **Power:** at half the top-25 edge and 7.5 events a month, a forward
     test has 11% power after 12 months, 19% after two years and 38% after
     five. 80% power needs 189 months, about 16 years (exact sign test,
     alpha 0.05, discordance held fixed; computed in `calibrate2.py`).
3. **The readout window carries no reliable signal once volatility and
   size are known.**
   - Mantel-Haenszel odds ratio of a next-day 20% move inside a readout
     window: **1.34** (90% CI 0.82-2.07), over 20,968 de-clustered
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
   - 5 events come from 4 names with own trials but no active trial with
     a dated upcoming completion.
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
  and RCKT. MRNA was under $10B and non-core on 22 name-days, so its 21
  current-record studies touch that panel. The under-$10B analysis is
  otherwise close to fully point in time; the all-cap one is not.
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
- **(g) Reviewer-only figure.** The robustness reviewer's 27 alternatives
  exist only in its scratch scripts (the session scratchpad,
  `review_cal/`). They are cited, not reproduced here.

## The gate (frozen now)

Run the forward test only if a better catalyst source passes all of the
following on the past year (2025-10-01 to 2026-09-30).

**Point in time, or no gate.**
- Each catalyst record must carry a first-seen or as-of timestamp, from
  vendor history or archived snapshots.
- On day P, only records whose as-of timestamp is at or before **16:00
  America/New_York on P** count. That is P's close, the same cutoff in the
  gate and in the protocol. Later revisions are invisible, and records
  without provenance count as no catalyst.
- **Spot-check, frozen.** The sample is `random.Random(20261006).sample`
  of 20 records, sorted by vendor record ID, drawn from all sourced records
  with an as-of date in the gate year. Two reviewers check each record
  against an archived snapshot. ANY failure means the source is treated as
  having no vintage history. The 20 IDs and the verdicts are logged here.
- **No vintage history means no gate and no forward test.** The data
  cannot show what was known on each day, and a short logging period
  would yield too few events to pass condition 1.
- **More than one source.** Every source evaluated is logged here with its
  gate result. If m sources are evaluated, condition 1 uses the lower
  bound of a (1 - 0.10/m) interval, and the first source declared is
  primary.

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
- **H1′:** exposed names first, each group ordered by B1x; ties go to
  higher 20-day dollar volume.
- **K:** comes from the P2 answer and is recorded in this document BEFORE
  any gate statistic is computed. If P2 is unanswered when a source
  arrives, the gate is not run until it is answered. No default K is
  chosen after seeing data.

**Pass if ALL of these hold:**
1. the odds ratio's lower 90% bound is above 1.0;
2. at the desk's list length K (P2), H1′ beats B1x with an exact one-sided
   sign-test power of at least 80% within 12 months. Power is computed on
   half the in-sample paired edge, with discordance held fixed, at the
   de-clustered event rate. For reference, with discordance held fixed,
   80% power within 12 months needs discordance of about 30% or more and an
   in-sample edge of about 30 percentage points or more. At last year's
   H1-vs-B1x discordance (33% at top 25) no positive edge was observed;
3. H1′ is no worse than B1x at the other two list lengths of 10, 25 and 40
   (point estimates).

Otherwise no forward test is run, and the result is recorded here.

### Source declarations (logged before any gate statistic)

1. **FMP press releases** (`/stable/news/press-releases`), declared
   2026-10-06 on Casey's pointer to a news API we already have.
   - **Content:** company releases from GlobeNewswire, PR Newswire and
     others, full text with a publish timestamp, going back to at least
     2023.
   - **Catalysts in them:** PDUFA target action dates ("PDUFA target
     action date set for April 10, 2026", Replimune) and guided readouts
     ("topline data ... on track for December 2026", Kodiak; "in 1H
     2027", Taysha).
   - **Point in time:** a release is never backfilled. Its publish
     timestamp is the as-of time, and a later release that revises a date
     supersedes it from its own timestamp.
   - **Filtering:** only releases issued by the company count. Law-firm
     alerts and third-party items are excluded.
   - **Status:** primary source; not yet evaluated.

**K = 10** (Casey, 2026-10-06: a shortlist of the roughly 63-name
universe; top 25 is 40% of it). Recorded before any gate statistic. Top 25
and top 40 are reported, and must not lose (condition 3).

**Extraction from source 1, frozen before any statistic.**
- **Releases.** Every FMP press release for each alias-table name,
  published 2024-06-01 to 2026-09-30. It counts only if both hold:
  - its first 600 characters carry "(NASDAQ: SYM)", "(NYSE: SYM)" or the
    company's alias-table core name;
  - its title does not match a law-firm or third-party pattern
    (shareholder / investor alert, class action, investigation, "law
    firm", "LLP", "deadline", "reminds").
- **Catalyst sentences.** Sentences that name a catalyst term (PDUFA,
  target action date, topline / top-line, data, results, readout,
  approval decision) together with a forward-looking cue (expect,
  anticipate, on track, plan, will, set for, scheduled, target, by). The
  sentence must also carry a time expression, mapped by the guided-timing
  table:
  - an exact date "Month D, YYYY";
  - "Month YYYY" (that month);
  - "Qn YYYY" or "nth quarter of YYYY";
  - "1H/2H YYYY" or "first/second half of YYYY";
  - "mid-YYYY";
  - "early YYYY";
  - "late / end of / year-end YYYY";
  - "YYYY" alone only directly after "in" or "during".
- **Kept windows.** A window counts only if it ends on or after the
  release's publish date. Past-tense reports of results are the event, not
  a catalyst.
- **As-of time.** The release's publish timestamp, under the 16:00 New
  York cutoff rule.
- **Staleness.** A window extracted from a release counts for 365 days
  after publication. A later release that moves a date does not cancel the
  earlier window (linking statements to programmes is not attempted). This
  over-states exposure and is stated as a limitation.
- **Spot-check, as frozen above.** 20 extracted catalyst records,
  `random.Random(20261006).sample` sorted by (symbol, publish time,
  sentence). Two independent reviewers check each against the release on
  its wire service: was the date public at that timestamp, and does the
  window match the sentence? Any point-in-time failure means no gate. The
  extraction accuracy is reported.

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
A labelled name that crosses $300M joins it that day. Only names absent
from `labels.json` (IPOs, new listings) are outside the frozen labels;
their moves are counted and reported separately.

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
  ties broken by 20-day dollar volume. Catalyst data are as known at 16:00
  America/New_York on P, using the stored as-of timestamps; records after
  that cutoff are excluded and counted.
- **B1x (the baseline H1′ must beat).** The sample standard deviation of
  daily log returns over the last 61 closes through P. Days whose simple
  close-to-close return is 20% or more in absolute value (rounded to 9
  decimals) are excluded. Fewer than 20 remaining returns gives B1x = 0,
  ranked last.
- **B1.** The same, without the exclusion (secondary).
- **B2.** The live Discovery queue in candidate-score order, as the
  Discovery tab shows it. It is logged in the snapshot before the sweep's
  upserts of that day and restricted to universe names. A universe name not
  in the queue is unranked, so its event is a miss, and the list is not
  padded (secondary).
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
  of its trading days are not counted. The window runs from the last
  counted event. Sector-wide days are reported.

### Metric and decision rule (frozen; formulas fixed now)

**Primary metric:** hit@K, the share of events whose name ranked within
the top K on P's snapshot. It is compared paired between H1′ and B1x with
a one-sided exact sign test on the discordant events, alpha 0.05.

**Formulas fixed now:**
- **N_min** is the event count at which the gate's exact sign-test power
  reaches 80%, on half the in-sample edge with discordance held fixed.
- There is no separate observed-edge threshold. Requiring the observed
  edge to reach the assumed edge halves the power, to about 49% (round-2
  finding). A significant one-sided sign test already means a positive
  edge.
- **The end date** is T0 plus the months the gate's power calculation needs
  (12 or fewer). There is no extension. Fewer than N_min events at the end
  date makes the result INCONCLUSIVE.

**BUILD** a ranked screen (the top K with each name's catalyst evidence;
no calls generated) only if ALL of these hold:
1. at least N_min events;
2. the sign test of H1′ over B1x gives p < 0.05;
3. hit@K(H1′) is above random;
4. hit@K(H1′) is at least hit@K(B2).

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
| P1 | Is there a catalyst source with PDUFA dates and guided readout timing AND point-in-time history (vendor vintages or archived snapshots), one you have or one you would pay for? | whether the gate runs at all | 2026-10-06 | answered 2026-10-06: FMP press releases (source 1) | — |
| P1 | What the desk would do with a ranked screen: a morning glance (top 10) or position preparation (top 25, 5-day lead time) | the list length K and the gating metric; the gate cannot run without it | 2026-10-06 (rev 1, then P3) | answered 2026-10-06: K = 10 | — |
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

**Round 2 (2026-10-06, 17 agents).**
- **Round-1 findings:** 20 of 22 confirmed fully addressed, 2 partly. Both
  are now completed (the spot-check rule and the after-close cutoff).
- **New findings, confirmed and applied in revision 4:**
  - SERIOUS: the BUILD rule's extra "observed edge at least DELTA" halved
    the real power, to about 49%. It is dropped, and the sign test carries
    the bar.
  - SERIOUS: the forward snapshot could see after-hours catalyst updates
    that drive the next day's move. There is now one 16:00 New York cutoff
    in the gate and the protocol.
  - SERIOUS: the point-in-time spot-check had no pass/fail rule. Any
    failure now means no vintage, and no vintage means no gate.
  - MINOR:
    - K is now fixed before any gate statistic, with no default if P2 is
      unanswered.
    - The impossible "25 pp at 22% discordance" reference is replaced.
    - The no-vintage fallback is removed.
    - The panel window was off by one. It is fixed and re-run, and the
      odds ratio is unchanged at 1.34.
    - B1x, B2 and the universe are now fully specified.
    - R1, R2 and H1 are defined in the doc again.
    - The headline power is now also stated against B1x, where H1 has no
      edge.
    - A multiplicity rule now covers testing several catalyst sources.
  - NOTES applied:
    - the 61% figure is now computed in `calibrate2.py`;
    - MRNA's under-$10B days are disclosed;
    - check 4's wording is corrected;
    - the desk question is now P1.
