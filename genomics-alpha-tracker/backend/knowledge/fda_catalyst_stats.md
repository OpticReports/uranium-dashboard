# FDA Regulatory Process & Catalyst-Event Statistics — Cited Reference Note

**Purpose:** Grounding base rates on FDA regulatory catalysts (PDUFA, AdComm, CRL) and their documented price/financing behavior, for calibrating trade memos around biotech regulatory events.

**Last researched:** 2026-07-20

---

## How to use this

These figures calibrate the **probability** and **expected-move** sections of a trade memo built around a regulatory catalyst. They are **base rates to adjust, not guarantees.**

- Treat every number as a *prior* for the population, then update for the specific drug: indication, prior CRLs, AdComm signal, sponsor cash position, market cap, float, short interest, and how much is already priced in.
- Concordance, first-cycle, and approval statistics are drawn from populations skewed toward drugs that already cleared Phase 3 and reached filing — survivorship is baked in. A single-asset micro-cap with a divided AdComm is **not** the average case.
- Price-behavior and financing statements split into two tiers, always labeled:
  - **[STUDY]** = peer-reviewed research or regulator data.
  - **[HEURISTIC]** = practitioner consensus with no rigorous public dataset behind the magnitude.
- Weight them accordingly. Do **not** present a heuristic band as if it were a measured probability in a memo. Where a study exists, cite it; where only practitioner knowledge exists, say so.
- Ranges are given where sources disagree. When a memo needs a point estimate, state the range and pick a value with a one-line rationale — do not invent a false-precision number.
- Re-pull the numbers before leaning on any specific figure: PDUFA cycles, annual novel-drug counts, and yearly concordance all move year to year. This note was researched 2026-07-20.

**Interpretation guardrails (read before quoting any number in a memo):**

- A high approval prior is **not** a long thesis by itself — if it is priced in, the payoff is asymmetric to the downside (reflexivity).
- "Met PDUFA goal date" is a *punctuality* metric, never an approval probability [1][2] — do not substitute one for the other.
- Positive and negative AdComm votes are **not** symmetric signals — weight a positive vote much more heavily than a negative one [3].
- Practitioner **[HEURISTIC]** magnitude bands are for framing scenarios, not for stating probabilities; only **[STUDY]**-tagged figures should anchor a stated likelihood.
- Always pair an approval/failure move estimate with the **financing overlay** — dilution risk is a near-constant for pre-profit biotech [11][13][14].

---

## Quick-reference priors (one number per line)

Each line is a base rate with its source tag; full context and caveats are in the sections below. Use as a fast lookup when drafting the probability line of a memo.

- Novel drug reaches PDUFA and is approved first cycle: **~74-90%** [1][6]
- All-application first-cycle approval (implied by CRL rate): **~60-63%** [7]
- Filed NDA/BLA approved *eventually* (after any resubmissions): **~90%** [11]
- Original NDA/BLA receives a CRL at first action: **~37%** [7]
- FDA follows its AdComm overall: **~88%** (2010-2021) / **~86%** (2017-2022) [3][4]
- FDA follows a **positive** initial-approval vote: **~97%** [3]
- FDA follows a **negative** initial-approval vote (i.e., does not approve): **~67%** [3]
- FDA acted *against* its AdComm in 2025: **43%** (3 of 7), vs ~16% in 2020-2024 [5]
- Phase 3 asset ultimately approved: **~55-60%** [11]
- Phase 1 asset ultimately approved (all modalities): **~7.9%** [11]
- Positive clinical-trial event, large-firm day 0-1 CAR: **+0.5% to +6.4%** [8][9]
- Negative clinical-trial event, large-firm day 0-1 CAR: **−0.8% to −2.7%** [8][9]
- Single-name CRL drop — small-cap / mid-cap / large-cap: **~40-75% / ~20-45% / ~5-20%** [10, HEURISTIC]
- Pre-PDUFA run-up: **~20-40%**, starting ~4-8 weeks out [12, HEURISTIC]
- Pre-event implied volatility: **~150-300%** annualized, collapses on resolution [15, HEURISTIC]

Direction to always encode: **downside on failure tends to exceed upside on approval** [8][9][12], and **positive AdComm votes are stronger signals than negative ones** [3].

---

## The regulatory calendar, defined plainly

### PDUFA date (Prescription Drug User Fee Act goal date)

**What it is.** The FDA's self-imposed target date to complete review of an NDA/BLA and issue an *action* — either an approval or a Complete Response Letter (CRL).

- Standard review target is ~10 months from the 60-day filing-acceptance milestone; priority review is ~6 months [Source 2].
- The PDUFA date is a *decision deadline, not an approval*. The action can be either outcome. The FDA can also act *early* (increasingly common) or, rarely, miss the date.
- In 2024, CDER met or beat the PDUFA goal date for 47 of 50 (94%) novel-drug approvals [Source 1]; across all CDER approvals, ~96% met the goal date in 2025 [Source 2]. These are *punctuality* stats, not approve/deny odds.

**What the stock typically does.** The single most-watched binary.

- Names usually drift or run up into the date as speculative and event-driven capital accumulates (see Price Behavior), then gap violently on the action — up on approval, sharply down on a CRL.
- Implied volatility peaks the day before and collapses ("IV crush") the moment the outcome prints [Source 15, HEURISTIC].
- Large-caps with an expected approval often trade flat or dip on the news because it is priced in; small single-asset names carry the fat-tailed moves [Source 12, HEURISTIC].

### Advisory Committee (AdComm)

**What it is.** A panel of external experts convened by the FDA to review an application publicly and *vote* on questions of efficacy, safety, or overall benefit-risk.

- The vote is **non-binding** — advisory only. The FDA makes the final decision at the PDUFA date.
- AdComms are held for only a *minority* of applications, disproportionately the contested or novel ones, and the FDA has been holding *fewer* of them recently [Source 5].
- A briefing-document release ~2 business days before the meeting is itself a tradable sub-event, since FDA reviewers' internal concerns become public then.

**What the stock typically does.**

- A mid-cycle mini-catalyst that can move a stock 20-50% by itself, because the vote is a strong (though imperfect) read on the eventual PDUFA outcome (concordance figures below).
- The briefing docs can move the stock *before* the vote; a harsh FDA review memo can gap a name down two days ahead of the meeting.
- A split/negative vote is a strong negative signal but not decisive — FDA overrides negative votes ~1/3 of the time [Source 3].

### Complete Response Letter (CRL)

**What it is.** The FDA's formal action stating it *will not approve the application in its present form*, listing deficiencies (clinical/efficacy, manufacturing/CMC, safety, or labeling).

- It is a delay/rejection, **not** a permanent denial — the sponsor can resubmit.
- Resubmissions are classified **Class 1** (2-month review goal) or **Class 2** (6-month review goal) depending on the scope of new data required [Source 7].
- FDA has begun *publishing* CRLs and is moving toward real-time release, so deficiency details increasingly become public [Source 17].

**What the stock typically does.** The primary downside catalyst.

- The gap is immediate and severe, and scales inversely with market cap and pipeline breadth (magnitudes in Price Behavior).
- Single-asset micro-caps can lose the majority of their value intraday; a CRL that cites *efficacy* is materially more ominous (and more often terminal) than one citing fixable CMC/manufacturing issues.
- Post-CRL drift is common, partly because the delay frequently forces a dilutive financing at a depressed price (see Financing Behavior).

### BLA / NDA

**What they are.** The marketing applications.

- **NDA** (New Drug Application) — small-molecule/conventional drugs, under the FD&C Act.
- **BLA** (Biologics License Application) — biologics (antibodies, cell/gene therapies, vaccines), under the Public Health Service Act.
- Functionally, for catalyst-trading both trigger a PDUFA clock and end in approval or CRL.

**What the stock typically does.**

- *Acceptance/filing* of the application (~60 days after submission) is a minor positive catalyst — it confirms the FDA deemed the package reviewable and sets the PDUFA clock.
- The *PDUFA action* is the major catalyst; the filing is the appetizer.

### Breakthrough Therapy / Fast Track / Accelerated Approval / Priority Review

**What they are.** Expedited-program designations, *not* approvals. A single drug can carry several at once.

- **Fast Track** — earlier and more frequent FDA interaction plus rolling-review eligibility; granted on preliminary evidence of addressing an unmet need.
- **Breakthrough Therapy** — for drugs showing *substantial improvement* over available therapy on a preliminary clinical endpoint; brings intensive FDA guidance and senior-manager attention.
- **Accelerated Approval** — approval based on a *surrogate endpoint* reasonably likely to predict clinical benefit, conditioned on confirmatory trials; failure of those trials can trigger withdrawal.
- **Priority Review** — compresses the PDUFA review clock to ~6 months (vs ~10 for standard) [Source 2].

**What the stock typically does.**

- The *grant* of a designation is a positive catalyst, strongest for small-caps whose value hinges on the single designated program [Source 8].
- Designations also *raise the market's implied approval probability*, which compresses the *surprise* (and thus the pop) at the eventual PDUFA — a reflexivity trap for late longs.
- Accelerated-approval names carry a distinct later risk: confirmatory-trial failure, an ODAC review, or a withdrawal action.

---

## Base rates

Compact table; scope and caveats in the notes below. Every figure carries survivorship bias toward drugs advanced enough to reach the stated stage.

| Metric | Figure | Scope / period | Source |
|---|---|---|---|
| Novel drugs meeting PDUFA goal date (timeliness, *not* approval) | 94% (47/50) in 2024; ~96% of CDER approvals in 2025 | CDER novel approvals | [1], [2] |
| First-cycle approval rate, novel drugs | ~74% (37/50, 2024); ~84% (46/55, 2023); ~85% (39/46, 2017); ~81% (166/204, 2011-2016); ≥85% most years since 2017 | CDER novel drugs | [1], [6] |
| CRL frequency, original NDAs/BLAs | ~37% of applications received a CRL | PDUFA VI cycle, 2018-2022 | [7] |
| FDA–AdComm overall concordance | 88% (262/298 votes) | 2010-2021 | [3] |
| FDA–AdComm overall agreement (alt. estimate) | 86% (2017-2022); 78% (2008-2015) | 2008-2022 | [4] |
| Positive AdComm vote → approval (initial approvals) | 97% (142/147) | 2010-2021 | [3] |
| Negative AdComm vote → non-approval (initial approvals) | 67% (40/60) | 2010-2021 | [3] |
| Positive vote → approval (supplemental indications) | 92% (33/36) | 2010-2021 | [3] |
| Negative vote → non-approval (supplemental indications) | 86% (18/21) | 2010-2021 | [3] |
| FDA acting *against* its AdComm | 3/7 = 43% in 2025, vs ~16% discordance in 2020-2024 | recent trend | [5] |
| Regulatory filing (NDA/BLA) → approval, *eventual* | ~90% | 2011-2020 | [11] |
| Phase 3 → approval (likelihood of approval from Ph3) | ~55-60% | 2011-2020 | [11] |
| Phase 1 → approval (all modalities) | 7.9% (biologics 9.1%, small molecules 5.7%, vaccines 9.7%) | 2011-2020 | [11] |

### Approval rate at PDUFA for drugs that reach it

There is no single clean public "% approved at PDUFA" number; triangulate three angles:

- **First-action split.** ~37% of original NDAs/BLAs got a CRL at first action in the 2018-2022 PDUFA cycle [7], implying roughly **~60-63% first-cycle approval** among filed applications.
- **Eventual outcome.** A CRL is not the end. Eventual approval among *filed* applications is high — BIO/Informa/QLS put regulatory-filing→approval at **~90%** for 2011-2020 [11]. Many CRL'd drugs are approved on resubmission after addressing deficiencies.
- **Novel-drug subset.** Among *novel* drugs specifically, first-cycle approval runs **74-90%** depending on year [1][6] — higher than the all-application figure, because novel-drug submissions are on average better-developed and more heavily pre-negotiated with the FDA.

**Reading for a memo:** for a well-developed novel drug reaching PDUFA, a ~75-90% first-cycle approval prior is defensible [1][6]; for a messier or non-novel filing, lean toward the ~60% first-cycle figure [7]; in *either* case eventual approval is much higher than first-cycle because of resubmission [11].

### How often FDA follows its AdComm (concordance)

- Best peer-reviewed anchor: **88% overall (262/298 votes, 2010-2021)** [3].
- Strong asymmetry [3]:
  - FDA follows **positive** votes almost always — **97%** on initial approvals, **92%** on supplemental.
  - FDA overrides **negative** votes about a third of the time — non-approval followed only **67%** of negative initial-approval votes (86% for supplemental).
- Practitioner dataset: overall agreement **86% (2017-2022)** and **78% (2008-2015)**, with 100% agreement in 2022 [4].
- **Regime shift warning:** FDA went against its AdComm in **3 of 7 (43%)** meetings in 2025 vs ~16% discordance in 2020-2024 [5]. Recent concordance is *lower and more variable* than the decade average — discount the historical priors for current-year events.

**Reading for a memo:** a *positive* AdComm vote is a very strong (≈95%+) signal toward approval [3]; a *negative* vote is meaningfully weaker as a signal because FDA overrides it ~1/3 of the time [3], and the recent regime makes both directions less predictable [5].

### First-cycle approval

- ~74-90% of *novel* drugs are approved on the first review cycle [1][6]; the high rate reflects extensive pre-submission FDA–sponsor interaction and negotiation.
- The rate is *lower* for the broader NDA/BLA universe once non-novel, generic-adjacent, and less-developed filings are included — the ~37% CRL rate implies ~60% first-cycle there [7].
- Match the statistic to the asset type; do not apply the novel-drug rate to a run-of-the-mill filing.

### CRL frequency and what typically follows

- ~37% of original applications drew a CRL (2018-2022) [7].
- A CRL routes to a Class 1 (2-month) or Class 2 (6-month) resubmission [7]. Outcomes: eventual approval (filing→approval eventual ~90% [11]), withdrawal, or an indefinite stall.
- *Typical* path after a fixable (e.g., CMC/manufacturing) CRL: resubmission and later approval. An *efficacy* CRL is materially more ominous and more often terminal for the asset.
- Transparency shift: FDA now publishes CRLs, so the specific deficiencies increasingly become public and analyzable [17].

---

## Price behavior around catalysts

### Pre-catalyst run-up

- Names tend to appreciate into a PDUFA/AdComm as speculative and event-driven capital builds positions.
- Practitioner estimates [Source 12, HEURISTIC]:
  - Run-up **starts ~4-8 weeks out.**
  - Adds roughly **20-40%** to the price.
  - Often *peaks 1-3 trading days before* the date, then de-risks as some traders take profit ahead of the binary.
- Highly idiosyncratic; larger for single-asset small-caps. Does **not** hold for large-cap pharma, where an expected approval is largely priced in and the stock can trade flat or dip on the news [Source 12, HEURISTIC].
- **No clean peer-reviewed dataset isolates the PDUFA-specific run-up.** Treat the magnitude as a heuristic band, not a measured mean.

### Documented event-day moves (peer-reviewed)

Event studies on clinical/regulatory outcomes consistently find **asymmetric reactions — losses on bad news are larger and more persistent than gains on good news:**

- **Singh et al. (PLOS One, 2022)** — 13,807 trials / 379 U.S.-listed firms, 2000-2020 [Source 8]. Day 0-1 cumulative abnormal returns (CARs):
  - Early positive outcome: **+6.35%**
  - Primary endpoints met: **+0.54%**
  - Safety/adverse signal: **−0.82%**
  - Lack of efficacy: **−2.43%**
  - Primary endpoints *not* met: **−2.71%**
  - The authors explicitly document positive/negative *asymmetry* — downside magnitudes exceed matched upside.
- **Hirsch/Rothenstein et al. (PLOS One, 2013)** — large-biopharma event study [Source 9]:
  - Median day-0 CAR **+0.8%** (positive announcements) vs **−2.0%** (negative).
  - Negative-event underperformance is *greater in magnitude and longer-lasting* than positive-event outperformance.
- **Caveat on magnitude:** these are pooled large-firm/clinical-trial CARs and are *much smaller* than single-name PDUFA gaps. A single-asset small-cap PDUFA is a fat-tailed event, not a few-percent move. Use the studies for *direction and asymmetry*, not for sizing a micro-cap gap.

### Implied vs realized moves on binary events

- Options routinely price *very large* moves into a PDUFA/AdComm [Source 15, HEURISTIC]:
  - Pre-event implied volatility can reach **150-300% annualized.**
  - The *implied move* (from the at-the-money straddle) is frequently in the tens of percent.
- On resolution, IV collapses ("IV crush") regardless of direction, so a long straddle *loses* unless realized move exceeds the priced-in move [Source 15, HEURISTIC].
- **Realized often larger on failures than approvals.** Consistent with the study-level asymmetry [8][9], practitioner consensus is that realized moves are typically *larger on failures* (CRL / negative vote) than on approvals, because approvals are more anticipated and partly priced in while failures are the surprise tail [Source 12, Source 8].
- **No single public dataset** cleanly quantifies PDUFA implied-vs-realized across the universe. The *direction* of the asymmetry is well-supported [8][9]; the *practitioner magnitude bands are heuristic.*

### "Sell the news" on approvals

- A frequently observed pattern [Source 16, HEURISTIC]: a long-anticipated approval produces a brief pop that then *drifts lower.*
- Mechanism: the market priced the outcome in during the run-up, and the remaining path (launch, reimbursement, revenue ~12-18 months out, and likely dilution) offers limited near-term upside.
- Strongest where:
  - The run-up was large.
  - Approval probability was already high (priority review, positive AdComm, strong Phase 3).
  - The approved label / commercial read disappoints (narrow label, boxed warning, REMS).
- **Not universal** — a surprise-clean label or a doubted approval can still gap up.

### Drift after CRLs

- The CRL gap is immediate and severe, and scales inversely with size/pipeline [Source 10, HEURISTIC]:
  - **Small-cap (<$500M): ~40-75% single-day drop.** Single-asset names can be existential if runway is short.
  - **Mid-cap ($500M-$5B): ~20-45%.** More cash and pipeline diversification, but still a major setback.
  - **Large-cap ($5B+): ~5-20%.** Absorbed by diversified revenue and deep balance sheets.
- Post-CRL, names often *continue to drift* rather than snap back, because:
  - Timeline-to-revenue is pushed out 1-3 years.
  - A resubmission may require new/expensive data (an efficacy CRL especially).
  - A CRL frequently *forces* a dilutive financing at a depressed price (see Financing Behavior).
- An efficacy-related CRL drifts worse than a CMC/manufacturing CRL, which the market reads as fixable [Source 10, HEURISTIC].

---

## Financing behavior

The core, well-documented pattern: **cash-burning biotechs raise equity into strength.** Pre-revenue and early-commercial biotechs fund operations almost entirely through equity dilution, and they *time issuance to price spikes* — including post-catalyst run-ups — to minimize the share count sold [Source 13, Source 14].

### Post-run-up offerings

- A large run into a catalyst is itself a *dilution-risk signal.* It creates a window to sell shares at favorable prices, and companies "tap the shelf" quickly after a positive catalyst — or after a big pre-catalyst rally [Source 14, HEURISTIC].
- Announcement of a secondary almost always produces a short-term price drop *beyond* the pure arithmetic of dilution, as event-driven holders exit into the print [Source 13].
- The pattern: "good raises follow good news" — a de-risking readout or an approval is the ideal issuance window [Source 13].

### ATM (at-the-market) programs

- Common in small-cap biotech; they let a company sell shares *continuously and opportunistically* into strength through a registered agent, without a single announced deal [Source 14, HEURISTIC].
- Consequence: a strong run can be met with steady, *un-announced* supply that quietly caps upside.
- An active ATM (disclosed in filings) is a structural overhang on any run-up thesis.

### Filing tells

- **S-3 shelf registration** establishes *capacity* to raise (no imminent deal implied).
- **424B5 prospectus supplement** signals an *imminent* offering.
- Traders monitor both as dilution early-warnings [Source 14, HEURISTIC].

### Runway-driven pressure

- The financing decision is dominated by cash runway. A company with **<12 months of cash** is *structurally compelled* to raise, which means:
  - Any strength is likely sold into.
  - A CRL or negative surprise forces a raise at a *depressed* price, compounding the drawdown.
- The flip side of "good raises follow good news" is that the same names *must* raise into weakness when the catalyst fails [Source 13].

### Base-rate context for why dilution is near-inevitable

- Phase-1→approval likelihood is only **7.9%**, and even Phase-3 assets approve only ~55-60% of the time [11].
- The long, capital-intensive, high-failure path means recurring equity raises are the *norm, not the exception,* for pre-profit biotech.

**Practical read for a memo:** a big run into a catalyst raises the probability of a *post-catalyst offering* regardless of the catalyst's outcome. Factor a dilution overhang into any "sell the news" or post-approval long thesis, and factor a *forced, cheap* raise into any CRL/failure downside case.

---

## Catalyst signal-strength ranking (for a memo's probability section)

Ordered from strongest to weakest as a *read on eventual approval*, with the base rate that supports the ranking. This is a synthesis of the cited base rates, not a separate dataset.

1. **Positive AdComm vote** — ~97% of positive initial-approval votes were followed by approval [3]. Near-decisive positive signal (but note recency drift toward more overrides [5]).
2. **Prior first-cycle approval of a novel drug that reached PDUFA** — ~74-90% first-cycle approval for novel drugs [1][6]; strong prior once a well-developed novel drug is at the finish line.
3. **Application filed / accepted (NDA/BLA)** — ~90% *eventual* filing→approval [11]; the drug will very likely be approved *eventually*, though not necessarily first cycle (~37% CRL rate [7]).
4. **Breakthrough / Priority / Fast Track designation** — positive but *soft*; raises implied approval odds and shortens the clock [Source 2], but does not guarantee the action; strongest as an *early* small-cap catalyst [8].
5. **Negative AdComm vote** — non-approval followed only ~67% of negative initial-approval votes [3]; a warning, not a verdict, since FDA overrides ~1/3 of the time.
6. **Efficacy-citing CRL** — most ominous; often terminal or requires an expensive new trial; worst post-event drift [10].

Corollary asymmetries a memo should encode:
- A *positive* AdComm is a much stronger signal than a *negative* one is [3].
- *Realized* downside on failures tends to exceed realized upside on approvals [8][9][12].
- The more "priced in" the approval (designations, positive vote, strong data), the smaller the pop and the larger the relative crash if it fails (reflexivity).

---

## Applying these base rates — illustrative worked examples

**These are illustrative applications of the cited priors, not measured outcomes for any real name.** They show *how* to turn the base rates into a memo's probability and expected-move lines. Do not present the derived numbers as data.

**Example A — single-asset small-cap, novel drug, priority review, no AdComm, ~9 months of cash.**
- *Approval prior:* start from the ~74-90% first-cycle novel-drug band [1][6]; a single-asset, cash-constrained micro-cap sits below the mean, so anchor lower in the range and state the range explicitly.
- *Expected move:* practitioner PDUFA gaps for small-caps run 20-50%+ up on approval / 40-75% down on a CRL [10][12, HEURISTIC]; asymmetry says size the *downside* tail larger [8][9].
- *Financing overlay:* <12-month runway means a raise is near-certain [11][13]; any pre-PDUFA run-up is a dilution-risk signal [14]; on a CRL, expect a *forced, cheap* raise amplifying the drawdown [13].
- *Sell-the-news risk:* if the stock has already run 20-40% into the date [12], an approval may fade [16].

**Example B — mid-cap, novel oncology drug, positive ODAC/AdComm vote 6 weeks before PDUFA.**
- *Approval prior:* a positive AdComm pushes toward the ~97% initial-approval concordance [3] — high, though discount modestly for the 2025 override regime [5].
- *Expected move:* much of the upside is likely priced in after the positive vote; approval-day reaction is muted for mid/large-caps [12], with real risk of "sell the news" if the run-up was large [16].
- *Tail risk:* the ~3% override case [3] is a fat-tailed downside; a CRL here would still be a 20-45% mid-cap drop [10].

**Example C — a name that just received a CRL.**
- *Path:* eventual approval among filed drugs is ~90% [11], and Class 1 (2-month) vs Class 2 (6-month) resubmission [7] sets the timeline; but *efficacy* CRLs are the terminal-risk bucket [10].
- *Drift:* expect continued drift, not a snap-back, driven by pushed-out revenue and likely dilution at a depressed price [10][13].

---

## Adjacent terms a memo may reference

- **sNDA / sBLA (supplemental application)** — adds a new indication/label to an already-approved drug. Concordance and approval dynamics differ from initial approvals; positive supplemental votes → approval ~92%, negative → non-approval ~86% [3].
- **ODAC (Oncologic Drugs Advisory Committee)** — the oncology AdComm; its votes feed the same concordance statistics [3].
- **REMS (Risk Evaluation and Mitigation Strategy)** — a required safety program that can accompany an approval; a burdensome REMS can dampen the commercial read and feed "sell the news" [16].
- **Boxed warning ("black box")** — the strongest label warning; on an approval it can turn a positive action into a muted or negative stock reaction (a label-disappointment channel for sell-the-news) [16].
- **PDUFA VI vs VII** — successive 5-year user-fee agreements that set the review-goal framework; the ~37% CRL rate cited here is from the PDUFA VI cycle (2018-2022) [7], so re-check against the current cycle.
- **Accelerated-approval confirmatory trial / withdrawal** — the delayed risk for accelerated-approval names: a failed confirmatory trial can trigger an ODAC review and market withdrawal.
- **Shelf (S-3) / takedown (424B5) / ATM** — the equity-issuance machinery behind the financing patterns above [14].

---

## Caveats and failure modes of these stats

1. **Survivorship / selection bias.** Concordance, first-cycle, and filing→approval rates describe drugs that already survived to AdComm or filing. They *overstate* the odds for earlier-stage or lower-quality assets. Do not apply the ~90% filing→approval rate [11] to a shaky single-Phase-3 program.
2. **AdComm is a selected sample.** FDA convenes AdComms disproportionately for *contested* applications and for only a minority of approvals. High overall concordance (88% [3]) coexists with the fact that AdComms cluster on the hard cases — and FDA overrides *negative* votes ~33% of the time [3].
3. **Regime change / recency.** 2025 concordance (57% following the vote; 43% against [5]) diverged sharply from the 2010-2024 record. Leadership, policy, and political shifts can break historical base rates fast; date-check the regime before leaning on a decade average.
4. **Timeliness ≠ approval.** The ~94-96% "met PDUFA goal date" figures [1][2] measure *punctuality*, not the approve/CRL split. Never conflate them in a memo.
5. **Novel-drug vs all-application rates diverge.** First-cycle and approval rates are much higher for CDER *novel* drugs [1][6] than for the full NDA/BLA universe [7]. Match the statistic to the asset type.
6. **Price/financing heuristics lack rigorous public datasets.** Run-up magnitude, implied-vs-realized bands, sell-the-news, and CRL-drift depths are practitioner consensus [10][12][14][15][16], not measured population means. The peer-reviewed CARs [8][9] are *directionally* reliable (asymmetry: downside > upside) but pooled across firm sizes and *smaller* than single-name PDUFA gaps.
7. **Idiosyncratic dominance.** Indication, competitive landscape, label details, safety-database size, manufacturing readiness, prior CRLs, short interest, float, and cash runway routinely swamp the base rate for any single name. Base rates set the *prior*; the specific facts move it a lot.
8. **Reflexivity of "priced in."** The more a catalyst is anticipated (designations, positive AdComm, strong data), the smaller the approval surprise and the larger the *relative* downside if it fails. A "high approval probability" name is not automatically a good long into the print.
9. **Small denominators.** Several concordance sub-rates rest on modest samples (e.g., 60 negative initial-approval votes [3]; 7 AdComms in 2025 [5]). Treat sub-bucket percentages as noisy.
10. **Numbers age.** Cycles (PDUFA VI vs VII), annual novel-drug counts, and yearly concordance all move. Re-pull before relying on a specific figure; this note was researched 2026-07-20.

---

## Scope notes and re-pull checklist

**Scope boundaries of these numbers.**

- These statistics are **U.S. FDA / CDER-centric**. Biologics reviewed by CBER (many vaccines, cell/gene therapies) and device pathways (CDRH, PMA/510(k)) have their own timelines and are *not* covered by the CDER novel-drug and PDUFA figures [1][6].
- Approval and concordance rates describe *drugs that reached filing or AdComm* — they say nothing about the ~92% of Phase-1 assets that never get there [11].
- Price and financing patterns are drawn from the *U.S.-listed small/mid-cap biotech* universe, where single catalysts dominate valuation; they attenuate sharply for diversified large-cap pharma [12][10].

**Re-pull checklist (what ages fastest).**

- **Annual novel-drug counts and first-cycle %** — refresh from the current-year CDER "New Drug Therapy Approvals" report each January [1][6].
- **CRL frequency** — tied to the PDUFA cycle (VI = 2018-2022); re-check against PDUFA VII data as it publishes [7].
- **AdComm concordance** — the 2025 regime shift [5] means the decade-average [3] is stale for current-year events; refresh the trailing-12-month discordance rate before use.
- **Price/financing heuristics** — verify against recent comparable events rather than relying on the bands here, which are practitioner consensus, not tracked series [10][12][14][15][16].

**One-line disclaimer to carry into any memo built on this note:** base rates set the prior; the specific asset's facts (indication, prior CRLs, cash runway, float, label risk) routinely move the outcome far from the average.

---

## Sources

1. **New Drug Therapy Approvals 2024 (Advancing Health Through Innovation)** — U.S. FDA, Center for Drug Evaluation and Research (CDER), Jan 2025. 50 novel approvals; 47/50 (94%) met PDUFA goal date; 37/50 (74%) first-cycle; 26 orphan; 24 first-in-class; 34/50 (68%) approved in U.S. before other countries. https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-2024 (report PDF: https://www.fda.gov/media/190705/download )

2. **Key measures of U.S. CDER drug approvals / PDUFA review timelines** — Statista, citing CDER (2025 data). ~96% of CDER approvals met the PDUFA goal date; standard ~10-month vs priority ~6-month review clocks. https://www.statista.com/statistics/817552/key-measurements-of-us-cder-drug-approvals/

3. **Association of Advisory Committee Votes With US FDA Decision-Making on Prescription Drugs, 2010-2021** — Daval CJR, Teng TW, Russo M, Kesselheim AS. *JAMA Health Forum*, 2023. Overall concordance 88% (262/298); positive→approval 97% (initial, 142/147) and 92% (supplemental, 33/36); negative→non-approval 67% (initial, 40/60) and 86% (supplemental, 18/21); 409 AdComm meetings held 2010-2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC10329213/

4. **Advisory Committee Disagreement With US FDA on Approval Decisions an Increasingly Rare Event** — 3D Communications (J. DiBiasi), via *Pink Sheet*, Jan 24, 2023. Agreement 86% (2017-2022) vs 78% (2008-2015); 100% in 2022; 133 meetings analyzed with 6 approvals despite negative votes and 12 rejections despite positive votes. https://3dcommunications.us/latest-thinking/posts/pink-sheet-advisory-committee-disagreement-with-us-fda-on-approval-decisions-an-increasingly-rare-event/

5. **FDA Went Against Adcomm Votes More, Held Fewer Adcomms in 2025** — BioSpace, 2025/2026. FDA went against its AdComm in 3 of 7 (43%) 2025 meetings vs ~16% discordance in 2020-2024. https://www.biospace.com/fda/fda-went-against-adcomm-votes-more-held-fewer-adcomms-in-2025

6. **CDER Brings Many Safe and Effective Therapies to Patients (FDA Voices) / annual novel-drug reports** — U.S. FDA, 2017-2024. First-cycle approval: ~81% (166/204, 2011-2016), ~85% (39/46, 2017), ~84% (46/55, 2023), ~74% (37/50, 2024); ≥85% most years since 2017; ~87% (374/428) over the prior decade. https://www.fda.gov/news-events/fda-voices/cder-brings-many-safe-and-effective-therapies-patients-and-consumers-2024

7. **Complete Response Letter frequency and resubmission classes** — Avalere Health, "What is a Complete Response Letter?" (analysis of the PDUFA VI cycle). ~37% of BLAs/NDAs received a CRL in 2018-2022; Class 1 resubmission = 2-month review goal, Class 2 = 6-month. https://advisory.avalerehealth.com/insights/what-is-a-complete-response-letter

8. **The reaction of sponsor stock prices to clinical trial outcomes: An event study analysis** — Singh et al. *PLOS One*, 2022. 13,807 trials, 379 U.S.-listed firms, 2000-2020. Day 0-1 CARs: early positive +6.35%, endpoints met +0.54%, safety −0.82%, lack of efficacy −2.43%, endpoints not met −2.71%; documented positive/negative asymmetry (downside > upside). https://pmc.ncbi.nlm.nih.gov/articles/PMC9439234/

9. **Stock Market Returns and Clinical Trial Results of Investigational Compounds: An Event Study Analysis of Large Biopharmaceutical Companies** — Hirsch/Rothenstein et al. *PLOS One*, 2013. Median day-0 CAR +0.8% (positive) vs −2.0% (negative); negative-event underperformance larger and longer-lasting. https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0071966

10. **FDA Complete Response Letter (CRL) Explained: What It Means For Biotech Stocks** — RTTNews, 2025 (corroborated by MedPath / Submarine Catalyst). CRL single-day drops: small-cap 40-75%, mid-cap 20-45%, large-cap 5-20%; reaction scales inversely with size/pipeline; range across examples 2% (AbbVie) to 75% (Aldeyra). https://www.rttnews.com/3662437/fda-complete-response-letter-crl-explained-what-it-means-for-biotech-stocks.aspx

11. **Clinical Development Success Rates and Contributing Factors 2011-2020** — BIO, Informa Pharma Intelligence (Biomedtracker), and QLS Advisors, Feb 17, 2021. Phase 1→approval 7.9% (biologics 9.1%, small molecules 5.7%, vaccines 9.7%); Phase 3→approval ~55-60%; regulatory-filing→approval ~90%; 12,728 phase transitions / 9,704 programs analyzed. https://go.bio.org/rs/490-EHZ-999/images/ClinicalDevelopmentSuccessRates2011_2020.pdf

12. **PDUFA Dates Explained / Biotech catalyst run-up mechanics** — Dan Sfera (dansfera.com) and BiopharmaWatch. [HEURISTIC] Run-up typically starts 4-8 weeks out, adds ~20-40%, peaks 1-3 days before date; PDUFA gaps commonly 20-50%+ for small/mid-caps; large-caps often flat/down on expected approval. https://dansfera.com/pdufa-explained and https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions

13. **Should Biotech Investors Fear Dilution?** — Nasdaq / The Motley Fool, 2018. [Practitioner analysis] Pre-revenue biotechs fund via repeated equity dilution; secondary announcements almost always cause short-term declines beyond pure dilution; "good raises follow good news." https://www.nasdaq.com/articles/should-biotech-investors-fear-dilution-2018-07-21

14. **Biotech Dilution Signals: How to Read 424B5, S-3, and ATM Filings** — Submarine Catalyst. [HEURISTIC] ATM programs sell into strength opportunistically without a single announced deal; S-3 = shelf capacity, 424B5 = imminent offering; companies tap the shelf fast after run-ups. https://submarinecatalyst.com/sec-dilution-signals-biotech.html

15. **Options implied move / IV crush around biotech binary events** — MarketChameleon biotech catalyst reports and QuantStrategy.io. [HEURISTIC] Pre-event IV can reach 150-300% annualized; implied move read from the ATM straddle; IV collapses on resolution regardless of direction. https://marketchameleon.com/Reports/biotech-stock-catalysts and https://quantstrategy.io/blog/options-trading-strategies-for-high-volatility-biotech/

16. **Why Some FDA Approvals Trigger Stock Drops Instead of Gains ("sell the news")** — Biotech Analyzer. [HEURISTIC] Long-anticipated approvals often pop then drift down as the outcome was priced in during run-up; ~12-18 months to meaningful revenue; dilution/label risk caps upside. https://biotechanalyzer.com/insights/why-some-fda-approvals-trigger-stock-drops-instead-of-gains

17. **FDA publication of Complete Response Letters / CRL transparency** — U.S. FDA (openFDA CRL dataset) and Pharmacy Times coverage, 2025. FDA has begun publishing hundreds of historical CRLs and is moving toward real-time release, making deficiency details public. https://open.fda.gov/apis/transparency/completeresponseletters/ and https://www.pharmacytimes.com/view/fda-publishes-hundreds-of-complete-response-letters-from-first-half-of-the-decade
