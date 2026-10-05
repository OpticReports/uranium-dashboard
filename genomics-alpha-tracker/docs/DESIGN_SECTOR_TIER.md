# Design + pre-registration: a watched genomics SECTOR tier

_Status: DESIGN, revision 3 (after two counter-agent rounds). No code until
Casey approves this document and answers the P1 questions below. The
measurements are run before the build decision; their results are appended,
never edited in._

## The ask

Casey, 2026-10-05: "we should be looking at the entire sector of genomics
right? not just a small list."

## What exists today, and why it is not that

| layer | what it is | size |
|---|---|---|
| Traded core | `watchlist.yaml` + discovery-promoted names: full ingestion (prices, analyst, social, insiders, short interest, science, news), scoring, flags, calls | 34 |
| Discovery funnel | daily Nasdaq census + rotating CT.gov sweep (the 2026-10-05 recall fixes included); a name is SEEN only if it trips a lane: a 10% day at the close, or on its rotation day a near phase-3 or a phase-2/3 plus a genomics tag | 1,068 health care + ~22 supplement scanned; queue history lives in the production database |

Everything that does not trip a lane is discarded unseen. Nothing persists
the census, nothing lists the sector, and "genomics" is a keyword list plus,
since the recall fixes, signals from a company's own phase 2/3 trials. The
rotation is `toordinal % 10` but the sweep runs weekdays only, so some names
are re-checked every 20 days, not every 10.

The recall fixes were validated for one purpose: auto-promote ranking (over
498 eligible names, the only newly auto-promotable name is Vertex). They
were NOT validated as a sector-membership classifier, and this design does
not assume they are one.

## Proposal: three tiers

**Tier 0 — Census snapshot (all screener rows).** Persist one dated row per
name per trading day, from the all-sector `download=true` call (the only
call that returns volume, sector and industry). The date comes from the
paginated health-care call's "as of" stamp, because the download call
carries none; a snapshot whose as-of date has not changed (holiday, stale
feed) is not saved. The funnel already does this since 2026-10-05: the
screener still showed Friday's close at 22:50 UTC on a Monday, so moves are
dated by the as-of stamp and an already-read snapshot is never re-read. Prices are the screener's last sale, which is NOT
split-adjusted: a day with a |move| ≥ 50% is flagged for an adjusted-price
check before it is used. Names that drop off the screener are marked "gone
since <date>", never deleted; identity is symbol plus name, so a reused
ticker starts a new history. Cost: the calls the sweep already makes.

**Tier 1 — Genomics sector.** A classified, watched set on its own Sector
screen. No calls are generated from it.

- *Expected size.* Rules (a), (b) and the industry half of (c), run on the
  2026-10-05 census and cached CT.gov data, tag about 60 names including the
  core (the profile-description half of (c) could not be computed offline
  and adds to that). The size is an OUTPUT of the rule, not a target;
  thresholds are not loosened to hit a number.
- *Classification rule* (pre-registered; re-run weekly; every decision
  logged with its evidence). A census name with market cap ≥ $300M is IN if
  any of:
  (a) a genomics keyword in the company name;
  (b) on the company's OWN interventional phase 2/3 trials (lead sponsor or
      named collaborator, whole-word match): a GENETIC intervention, a
      genomics keyword in a title, or a therapeutic-modality core name as a
      collaborator. NOTE the shipped funnel differs on titles: it reads title
      keywords from EVERY returned study, because investigator-led trials of
      a company's product carry the descriptive titles (restricting titles to
      own trials dropped Iovance and ProKidney). Tier 1 uses the stricter
      own-trial rule for membership and measurement 2 tests what it misses;
      if the misses sample shows the same cell-therapy losses, the title
      half of rule (b) reverts to the funnel's behaviour BEFORE the build
      decision, and that change is recorded here;
  (c) industry "Biotechnology: Laboratory Analytical Instruments", or a
      genomics keyword in the company's FMP profile description (checked at
      most once a month per name; this replaces a hand-made allow-list,
      which would reintroduce the "a human must remember the company"
      problem);
  (d) the manual include list, which starts EMPTY and every addition is
      dated and never applied retroactively; and NOT on the manual exclude
      list (same rules).
  A name leaves Tier 1 only after four consecutive weekly misses, so
  membership does not flicker as trial dates pass.
- *Watched with data we already have:* daily close, move and volume from
  Tier 0; a 10% / 20% move log; relative strength vs XBI and 20-day dollar
  volume once 60 trading days of Tier 0 history exist (a one-time FMP
  backfill of about one call per name fills the gap; budgeted below);
  catalyst proximity from the weekly CT.gov evaluation; a runway figure
  from FMP fundamentals, cached by filing date (statements change four
  times a year).
- *Sector screen:* every Tier 1 name, sortable by move, relative strength,
  catalyst date, size and modality; why each name is in (its evidence); and
  its discovery-queue status. The Discovery tab stays the cross-sector
  miss-detector; the Sector screen does not duplicate its movers list.
- *Promote from the Sector screen* adds the name to the discovery queue
  with source "sector" and then follows the manual Promote path, with its
  OWN weekly cap separate from the auto-promote cap (today a manual promote
  consumes an auto slot and could starve the mega-cap fast path that exists
  for the MRNA case). Auto-promote inputs are unchanged by this build.

**Tier 2 — Traded core.** Unchanged: full ingestion, scoring, flags, calls.
The partner set used by rule (b) is Tier 2's hand-curated names only.

What this deliberately does NOT do: generate calls on Tier 1 names, or
widen what auto-promote sees, without a separate pre-registered study.

## Pre-registered measurements (run BEFORE the build decision)

**Window and population.** 2025-10-01 to 2026-09-30. Every single-day move
of ≥ 20% either way (adjusted close to close) in any name with market cap
≥ $300M on the PRIOR day (historical market cap), from the full census, the
supplement, and names delisted or acquired in the window (FMP delisted
list). The five trading days after an IPO are excluded. M&A announcement
days are reported separately and are not in the primary metric.

**Labels.** A counter-agent who has not seen any tier membership labels each
move's name genomics / not genomics under the mandate Casey sets below.

**1. Point-in-time recall over the shipped baseline (primary).**
- Baseline = what the desk could have seen the day before: the core as it
  stood that day (from production `security.created_at`), plus a replay of
  the SHIPPED funnel code (recall fixes included) over the window.
- Tier 1 is evaluated point-in-time on the day before: rule (b) from CT.gov
  record history (the `scripts/build_pit_catalysts.py` method), the partner
  set as the core stood that day, rule (c) frozen as written here, rule (d)
  empty.
- Metric: of the labelled genomics moves that were NOT visible to the
  baseline, the share where Tier 1 had the name in the Sector screen's top
  25 or showed a dated catalyst within 30 days. The screen's default sort,
  frozen here: days to the nearest dated catalyst ascending, ties broken by
  20-day dollar volume descending, undated names last. Reported with n and
  a Wilson 90% interval.
- Also reported: the enrichment ratio (genomics-LABELLED movers in Tier 1 ÷
  Tier 1 size) ÷ (genomics-labelled movers in the census ÷ census size), so
  size alone cannot pass.
- Rule (c)'s data (industry, FMP profile text) exists only as of today, so
  names that enter Tier 1 ONLY through rule (c) carry look-ahead: their
  contribution is reported separately as an upper bound and excluded from
  the primary metric.
- A figure using TODAY's classification may appear only as a labelled
  upper bound.

**2. Classification quality.** The counter-agent labels a random 50
non-core Tier 1 names (precision) AND a random 50 census names NOT in Tier
1 (what the rule misses), against the mandate. Every disagreement listed.
The misses share is reported with its Wilson 90% interval; at n = 50 a
count of 5 spans roughly 4-19%, so the gate below uses the count and the
interval is reported beside it, not hidden.

**3. Cost.** Added calls per day by provider (CT.gov: about 105 per weekday
to evaluate rule (b) weekly for all ~520 census names ≥ $300M; FMP: the
one-time backfill plus monthly profiles), added scoring runtime, database
growth, on a one-week dry run. The FMP plan's real quota is needed: the
600 calls/minute figure in the code is our own client-side limiter, not the
plan limit.

**4. The two known misses, point-in-time, rules (a)-(c) only, empty manual
lists.** MRNA on 2026-08-18 (the day before its readout) and VRTX on the
day before its largest move in the window. Informational, not a gate: two
names cannot decide a build. A "no" is reported as a finding with the rule
that missed it.

**Decision rule (frozen).** BUILD Tier 1 if, on measurement 1, at least 15
labelled genomics moves were invisible to the baseline AND Tier 1 surfaced
at least half of them (lower Wilson bound reported) AND the enrichment
ratio exceeds 2; AND measurement 2 shows precision ≥ 80% and misses ≤ 10%
of the sampled non-Tier-1 names judged genomics; AND measurement 3 fits the
real provider quotas with headroom. Fewer than 15 such moves: INCONCLUSIVE,
not BUILD. Otherwise: report why and stop. Tier 0 alone may ship regardless
because measurement 3 needs it.

## Decisions and inputs needed from Casey

| P | question | what it moves |
|---|---|---|
| P1 | **The mandate.** Strict genomics (gene editing, gene therapy, RNA/mRNA, sequencing and tools, genomic diagnostics) or genetic medicines broadly, including large companies with a genomics franchise (Vertex)? Name explicitly: cell therapy (CAR-T: the second most common tag) and cancer vaccines - in or out? Kiniksa is out under all of these. | rule (a)-(c) keywords; measurement 1 and 2 labels |
| P1 | **Production export**: `universe_candidate` (all columns) and `security` (symbol, created_at, active). The core's membership on each past date and the live funnel's queue history exist only there; measurement 1 cannot be run honestly without them. | measurement 1 baseline |
| P1 | **FMP plan quota** (calls per minute and per day). | measurement 3 |
| P2 | Should Tier 1 names ever generate calls directly? This design says only after promotion to the core. | scope |
| P3 | Promote-from-Sector cap: how many per week, separate from the auto cap? | Promote path |

## Amendments before any measurement data (2026-10-05, recorded, not silently edited)

1. **Mandate (Casey: "all of the above").** Genomics for this tier means
   genetic medicines broadly: gene editing, gene therapy, RNA/mRNA and
   oligonucleotide medicines, cell therapy (incl. CAR-T, TCR-T, TIL), cancer
   vaccines, sequencing and genomics tools, genomic and molecular
   diagnostics, AND large companies with a genomics franchise (Vertex).
   Kiniksa-type companies with no genetic-medicine, tools or diagnostics
   activity are out. This is the labelling standard for measurements 1, 2
   and 4.
2. **Provider quota (Casey: "a huge amount of allowable API calls").** No
   number was given; the quota half of measurement 3's gate is taken as met
   on Casey's statement. Measurement 3 still reports calls per day by
   provider against our own client-side limiter (600/minute for FMP) and the
   CT.gov politeness delay, plus runtime and database growth.
3. **Measurement 3 dry run.** One day, not one week: Casey's quota answer
   removes the constraint the week was meant to probe, and the Tier 0
   snapshot has no history to replay. Per-day figures are extrapolated and
   labelled as such.
4. **Rule (b) point-in-time method.** Membership signals (GENETIC
   intervention, title keyword, own-trial therapeutic partner) are read from
   the company's own interventional phase 2/3 trials whose
   StudyFirstPostDate is on or before the evaluation date; titles,
   interventions and sponsors come from the CURRENT record (they rarely
   change; a later edit is look-ahead and is stated). Catalyst DATES (primary
   completion, status) are point-in-time from CT.gov record history, the
   `scripts/build_pit_catalysts.py` method, for phase 2/3 trials of the names
   whose ranking or funnel replay needs them.
5. **Labels.** Every name in the measured population, not only sampled
   ones, is labelled by TWO independent counter-agents who see only the
   company's name, industry and FMP profile description (never tier,
   watchlist or queue membership); disagreements go to a third. The
   pre-registered random-50 samples of measurement 2 are drawn from these
   labels with a fixed seed (20261005) and reported as specified; the
   full-population precision and misses are reported beside them as
   supplementary figures.
6. **Funnel replay baseline.** The live funnel only existed from
   2026-09-08; the baseline replays the SHIPPED funnel code's lanes over the
   whole window as if it had run every weekday (movers: a close-to-close
   |move| >= 10% with prior-day cap >= $300M queues the name from that day
   on; catalyst: each name's weekday rotation day, point-in-time phase-3
   dates and rule-(b) tags). A queued name is visible from its queue date
   onward. The production export (`security`, `universe_candidate`) supplies
   the core's discovery promotions and the live queue for 2026-09-08 onward,
   used to cross-check the replay for those weeks.
7. **Implementation choices the design left open** (recorded 2026-10-05
   while only the data was being assembled; no tier membership, label or
   metric existed yet).
   - *Core before the tracker existed.* The tracker was created on
     2026-06-25. Its first committed watchlist is taken to have stood from
     the start of the window, and later additions are dated by their commit
     (MRNA 2026-08-19, VRTX 2026-10-05). An empty core before June would
     count every core name's move as unseen by the baseline and inflate
     Tier 1's recall. If the production export arrives, its
     `security.created_at` adds UI and discovery additions.
   - *Warm-up.* The funnel replay and the weekly Tier 1 evaluation both
     start on 2025-08-01, two months before the window, so neither starts
     cold. The replay's queue never expires, as shipped, and dismissals are
     not modelled. Both choices favour the baseline.
   - *Weekly evaluation.* Tier 1 is evaluated on Mondays with data as of
     that day's close. The screen on day P uses the latest evaluation on or
     before P. "Leaves after four consecutive weekly misses" means a member
     is any name that was IN at one of the last four evaluations and is
     still listed.
   - *Census on a past day.* A name is in the census on day t if it has an
     FMP bar on or before t and, if delisted, t is before its delisting
     date. Its cap is FMP's historical cap on the latest date on or before
     t.
   - *Dated catalyst on the Sector screen.* The primary completion date of
     the company's own interventional phase 2/3 trials, as CT.gov showed it
     on the evaluation date. Only trials with the funnel's active statuses
     count (recruiting, active-not-recruiting, enrolling-by-invitation), and
     only dates on or after day P. Month-only dates are read as the 15th,
     as the shipped parser does. "Within 30 days" means 0 to 30 days after
     P.
   - *20-day dollar volume.* The mean of FMP adjusted close times volume
     over the 20 trading days ending on P.
   - *Rule (c) in the primary metric.* For the primary figures, Tier 1 is
     rules (a) and (b) only, for both membership and ranking. A move whose
     name was in Tier 1 on P only through rule (c) is removed from the
     denominator. The labelled upper bound adds rule (c) to membership and
     ranking and keeps every move in the denominator. The enrichment ratio
     is split the same way.
   - *Enrichment ratio, by distinct names.* The numerator is the share of
     names that were ever in Tier 1 in the window which are
     genomics-labelled and had at least one measured move while in Tier 1.
     The denominator is the same share for the eligible census (names with
     a cap of $300M or more on some day of the window). Moves flagged as
     M&A are left out of every primary figure.
   - *Measurement 2 samples.* The precision sample is drawn from today's
     (2026-10-05) non-core Tier 1, all rules; rule (c) has no look-ahead
     today. The misses sample is drawn from today's census names with a cap
     of $300M or more that are not in Tier 1; a name below the size floor
     is not a classification miss. Both use
     `random.Random(20261005).sample(sorted(symbols), 50)`.
   - *Titles and descriptions.* Rule (b) reads the full brief title. The
     funnel replay reads the first 120 characters, as shipped. Rule (c)
     reads the full FMP description from the cached profile.
   - *Labels.* Labellers never see Tier 1 status. They see the name, the
     screener and FMP industries, and the FMP description, and may use what
     they already know about the company, but no tools. A large company is
     IN when a marketed product or a phase 3 programme in an amendment-1
     modality is a material part of its business.
   - *Posting lag.* CT.gov version dates are quality-control dates; public
     posting follows. A version counts as visible from its date plus L days.
     L is measured from the gap between each study's version-0 date and its
     StudyFirstPostDate (95th percentile) and reported.
   - *Day before.* P is the prior trading day in FMP's bars, and the funnel
     replay at P includes P's own close, since the sweep runs at 21:45 UTC.

## Counter-agent verdict

**Round 1 (2026-10-05): not approvable as written - all findings applied in
this revision.** BLOCKING: measurement 1 was circular (moves were drawn from
names classified as Tier 1 today, so Tier 1 recall was ~100% by
construction; survivorship and look-ahead market caps); the baseline was the
core alone and +20 pp was a size effect - replaced by point-in-time recall
over the shipped funnel replay, an enrichment ratio, and an INCONCLUSIVE
floor. SERIOUS: the 150-300 target was unreachable by the rule (~80-90) -
size is now an output; rule (b) false positives (John Merck Fund, TGen,
Natera consortium, carrier screening as GENETIC) - rule (b) now uses only the
company's own interventional phase 2/3 trials and therapeutic partners,
fixed in the shipped funnel code too; the allow-list was open-ended - now a
profile-description rule plus an empty, dated manual list; the Promote path
was misdescribed (manual promote has no gates, 404s off-queue names, and eats
auto-promote slots) - now its own path and cap; cost and data claims were
wrong against the code (volume/sector only in the download call, no as-of
date there, no history for relative strength, CT.gov needs every census name
weekly not just Tier 1, the 600/min figure is our own limiter) - corrected;
measurement 4 could not fail - now point-in-time with empty manual lists;
funnel recall was to be "estimated" when the inputs exist in production -
now a P1 ask. MINOR items (move definition, a misses sample, delisting and
ticker reuse, Discovery-tab overlap, partner set = core only, which
measurement needs Tier 0) and NOTEs (weekday rotation gap, cell therapy in
the mandate, overstated validation of the recall signals) applied.

**Round 2 (2026-10-05): round-1 items confirmed addressed in the body; the
decision rule can now fail.** New findings applied in this revision: the
claim that rule (b)'s restriction also shipped in the funnel was only half
true (titles still read every study) - now stated, with the reason and a
pre-decision check; rule (c) look-ahead in measurement 1 - rule-(c)-only
names excluded from the primary metric; the default sort was a free
parameter - frozen; the enrichment numerator - genomics-labelled movers;
measurement 4's consequence - informational; the misses gate's interval -
reported; the size estimate - re-measured at about 60. The screener
staleness finding (Friday's close still served on Monday evening) was fixed
in the funnel code, and Tier 0 already planned for it.
