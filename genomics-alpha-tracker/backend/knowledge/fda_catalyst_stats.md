# FDA Regulatory Process & Catalyst-Event Statistics — Cited Reference Note

**Purpose:** Grounding base rates on FDA regulatory catalysts (PDUFA, AdComm, CRL) and their documented price/financing behavior, for calibrating trade memos around biotech regulatory events.

**Last researched:** 2026-07-20

---

## How to use this

These figures calibrate the **probability** and **expected-move** sections of a trade memo built around a regulatory catalyst. They are **base rates to adjust, not guarantees.**

- Treat every number as a *prior* for the population, then update for the specific drug (indication, prior CRLs, AdComm signal, sponsor cash position, market cap, how much is already priced in).
- Concordance, first-cycle, and approval statistics are drawn from populations skewed toward drugs that already cleared Phase 3 and reached filing — survivorship is baked in. A single-asset micro-cap with a divided AdComm is **not** the average case.
- Price-behavior and financing statements split into two tiers, always labeled: **[STUDY]** = peer-reviewed / regulator data; **[HEURISTIC]** = practitioner consensus with no rigorous public dataset. Weight them accordingly. Do not present a heuristic as a measured probability in a memo.
- Ranges are given where sources disagree. When a memo needs a point estimate, state the range and pick a value with a one-line rationale — do not invent a false-precision number.

---

## The regulatory calendar, defined plainly

**PDUFA date (Prescription Drug User Fee Act goal date).** The FDA's self-imposed target date to complete review of an NDA/BLA and issue an *action* — either an approval or a Complete Response Letter (CRL). Standard review target is ~10 months from the 60-day filing acceptance; priority review is ~6 months [Source 2]. The PDUFA date is a *decision deadline, not an approval*; the action can be either outcome, and the FDA can also act early or miss the date. In 2024, CDER met or beat the PDUFA goal date for 47 of 50 (94%) novel-drug approvals [Source 1]. *Stock behavior:* the single most-watched binary. Names typically drift/run up into it (see Price Behavior), then gap violently on the action — up on approval, sharply down on a CRL. Implied volatility peaks the day before and collapses ("IV crush") the moment the outcome prints [Source 15, HEURISTIC].

**Advisory Committee (AdComm).** A panel of external experts convened by the FDA to review an application publicly and *vote* (often on questions of efficacy, safety, or benefit-risk). The vote is **non-binding** — advisory only. AdComms are held for a minority of applications, typically the more contested or novel ones, and the FDA has been holding fewer of them recently [Source 5]. *Stock behavior:* a mid-cycle mini-catalyst that can move a stock 20-50% by itself, because the vote is a strong (though imperfect) read on the eventual PDUFA outcome. A briefing-document release ~2 business days before the meeting is itself a tradable sub-event, since FDA reviewers' internal concerns become public then.

**Complete Response Letter (CRL).** The FDA's formal action stating it *will not approve the application in its present form*, listing deficiencies (clinical, manufacturing/CMC, safety, or label). It is a delay/rejection, **not** a permanent denial — the sponsor can resubmit. Resubmissions are classified Class 1 (2-month review goal) or Class 2 (6-month review goal) depending on the scope of new data [Source 7]. *Stock behavior:* the primary downside catalyst. Reaction scales inversely with market cap and pipeline breadth (see Base Rates and Price Behavior); single-asset micro-caps can lose the majority of their value intraday.

**BLA / NDA.** The marketing applications. **NDA** (New Drug Application) is for small-molecule/conventional drugs under the FD&C Act; **BLA** (Biologics License Application) is for biologics (antibodies, cell/gene therapies, vaccines) under the Public Health Service Act. Functionally, for catalyst-trading purposes both trigger a PDUFA clock and can end in approval or CRL. The *acceptance/filing* of an NDA/BLA (≈60 days after submission) is a minor positive catalyst; the PDUFA action is the major one.

**Breakthrough Therapy / Fast Track / Accelerated Approval / Priority Review.** These are FDA expedited-program designations, not approvals:
- **Fast Track** — earlier and more frequent FDA interaction; rolling review eligibility. Granted on preliminary evidence of addressing unmet need.
- **Breakthrough Therapy** — for drugs showing *substantial improvement* over available therapy on a preliminary clinical endpoint; brings intensive FDA guidance.
- **Accelerated Approval** — approval based on a *surrogate endpoint* reasonably likely to predict clinical benefit, conditioned on confirmatory trials (which, if they fail, can trigger withdrawal).
- **Priority Review** — compresses the PDUFA review clock to ~6 months (vs ~10 for standard) [Source 2]. A drug can carry several of these at once.
*Stock behavior:* the *grant* of a designation is a positive catalyst, strongest for small-caps whose value hinges on the single program [Source 8]. Designations also raise the market's implied probability of eventual approval, which compresses the *surprise* (and thus the pop) at the eventual PDUFA. Accelerated-approval names carry a distinct later risk: confirmatory-trial failure or an ODAC/withdrawal action.

---

## Base rates

Compact table (see notes below for scope and caveats). All figures carry survivorship bias toward drugs advanced enough to reach the stated stage.

| Metric | Figure | Scope / period | Source |
|---|---|---|---|
| Novel drugs meeting PDUFA goal date (timeliness, not approval) | 94% (47/50) in 2024; ~96% of CDER approvals in 2025 | CDER novel approvals | [1], [2] |
| First-cycle approval rate, novel drugs | ~74% (37/50, 2024); ~84% (46/55, 2023); ~81% (166/204, 2011-2016); ≥85% most years since 2017 | CDER novel drugs | [1], [6] |
| CRL frequency, original NDAs/BLAs | ~37% of applications received a CRL | PDUFA VI cycle, 2018-2022 | [7] |
| FDA–AdComm overall concordance | 88% (262/298 votes) | 2010-2021 | [3] |
| FDA–AdComm overall agreement (alt. estimate) | 86% (2017-2022); 78% (2008-2015) | 2008-2022 | [4] |
| Positive AdComm vote → approval (initial approvals) | 97% (142/147) | 2010-2021 | [3] |
| Negative AdComm vote → non-approval (initial approvals) | 67% (40/60) | 2010-2021 | [3] |
| Positive vote → approval (supplemental) | 92% (33/36) | 2010-2021 | [3] |
| Negative vote → non-approval (supplemental) | 86% (18/21) | 2010-2021 | [3] |
| FDA acting *against* AdComm | 3/7 = 43% in 2025, vs ~16% discordance in 2020-2024 | recent trend | [5] |
| Regulatory-filing (NDA/BLA) → approval, eventual | ~90% | 2011-2020 | [11] |
| Phase 3 → approval (likelihood of approval from Ph3) | ~55-60% | 2011-2020 | [11] |
| Phase 1 → approval (all modalities) | 7.9% (biologics 9.1%, small molecules 5.7%) | 2011-2020 | [11] |

**Approval rate at PDUFA for drugs that reach it.** There is no single clean public "% approved at PDUFA" number; triangulate:
- ~37% of original NDAs/BLAs got a CRL at first action in the 2018-2022 PDUFA cycle [7], implying roughly **~60-63% first-cycle approval** among filed applications.
- But a CRL is not the end: eventual approval among *filed* applications is high — BIO/Informa/QLS put regulatory-filing→approval at **~90%** for 2011-2020 [11]. Many CRL'd drugs are approved on resubmission after addressing deficiencies.
- Among *novel* drugs specifically, first-cycle approval runs **74-90%** depending on year [1][6] — higher than the all-application figure because novel-drug submissions are, on average, better-developed and more heavily pre-negotiated with FDA.

**How often FDA follows its AdComm (concordance).** The best peer-reviewed anchor is **88% overall (262/298 votes, 2010-2021)** [3], with a strong asymmetry: FDA follows **positive** votes almost always (**97%** on initial approvals) but overrides **negative** votes about a third of the time (non-approval followed only **67%** of negative initial-approval votes) [3]. A practitioner dataset puts overall agreement at **86% (2017-2022)** and **78% (2008-2015)** [4]. Note a **regime shift**: FDA went against its AdComm in **3 of 7 (43%)** meetings in 2025, versus ~16% discordance in 2020-2024 [5] — recent concordance is lower and more variable than the decade average, so weight the historical priors down for current-year events.

**First-cycle approval.** ~74-90% of novel drugs are approved on the first review cycle [1][6]; the high rate reflects extensive pre-submission FDA–sponsor interaction. First-cycle rate is *lower* for the broader NDA/BLA universe once you include non-novel, generic-adjacent, and less-developed filings (the ~37% CRL rate implies ~60% first-cycle there) [7].

**CRL frequency and what follows.** ~37% of original applications drew a CRL (2018-2022) [7]. A CRL routes to a Class 1 (2-month) or Class 2 (6-month) resubmission [7]; the drug can ultimately be approved (filing→approval eventual ~90% [11]), withdrawn, or stalled. The *typical* path after a fixable (e.g., CMC/manufacturing) CRL is resubmission and later approval; a CRL citing *efficacy* deficiencies is materially more ominous and more often terminal for the asset. Note the recent transparency change: FDA has begun publishing CRLs, so the letter's specific deficiencies increasingly become public [Source 17].

---

## Price behavior around catalysts

**Pre-catalyst run-up.** Names tend to appreciate into a PDUFA/AdComm as speculative and event-driven capital builds positions. Practitioner estimates: a run-up **starting ~4-8 weeks out**, adding roughly **20-40%**, and often peaking **1-3 trading days before** the date [Source 12, HEURISTIC]. The magnitude is highly idiosyncratic and larger for single-asset small-caps; it does *not* hold for large-cap pharma, where an expected approval is largely priced in and the stock can trade flat or dip on the news [Source 12, HEURISTIC]. There is no clean peer-reviewed dataset isolating the *PDUFA* run-up specifically — treat the magnitude as a heuristic band, not a measured mean.

**Documented event-day moves (peer-reviewed).** Event studies on clinical/regulatory outcomes find **asymmetric reactions — losses on bad news are larger and more persistent than gains on good news:**
- Singh et al. (PLOS One, 2022), 13,807 trials / 379 U.S.-listed firms, 2000-2020: day 0-1 cumulative abnormal returns of **+6.35%** for an early positive outcome and **+0.54%** for met primary endpoints, versus **−2.71%** for unmet primary endpoints, **−2.43%** for lack of efficacy, and **−0.82%** for a safety signal. The authors document explicit asymmetry (downside magnitudes exceed matched upside) [Source 8].
- Hirsch/Rothenstein et al. (PLOS One, 2013), large-biopharma event study: median day-0 CAR of **+0.8%** on positive announcements vs **−2.0%** on negative, with negative-event underperformance greater in magnitude and *longer-lasting* than positive-event outperformance [Source 9].
- Note these large-firm/clinical-trial CARs are *smaller* than single-name PDUFA gaps because they pool diversified big-caps; a single-asset small-cap PDUFA is a fat-tailed event, not a few-percent move.

**Implied vs realized moves on binary events.** Options routinely price very large moves into a PDUFA/AdComm: implied volatility can reach **150-300% annualized** pre-event, and the *implied move* (from the at-the-money straddle) is frequently in the tens of percent [Source 15, HEURISTIC]. On resolution, IV collapses ("IV crush") regardless of direction, so a long straddle loses unless realized move exceeds the priced-in move [Source 15, HEURISTIC]. Practitioner consensus — consistent with the study-level asymmetry above — is that **realized moves are often larger on failures (CRL/negative vote) than on approvals**, because approvals are more anticipated and partly priced in while failures are the surprise tail [Source 12, Source 8]. There is no single public dataset cleanly quantifying PDUFA implied-vs-realized across the universe; the *direction* of the asymmetry is well-supported [8][9], the *practitioner magnitude bands are heuristic.*

**"Sell the news" on approvals.** A frequently observed pattern: a long-anticipated approval produces a brief pop that then *drifts lower*, because the market priced the outcome in during the run-up and the remaining path (launch, reimbursement, revenue ~12-18 months out, and likely dilution) offers limited near-term upside [Source 16, HEURISTIC]. Strongest where (a) the run-up was large, (b) approval probability was already high (priority review, positive AdComm, strong Phase 3), and (c) the label/commercial read on approval disappoints. Not universal — a surprise-clean label or a doubted approval can still gap up.

**Drift after CRLs.** The CRL gap is immediate and severe, and reaction scales inversely with size/pipeline [Source 10, HEURISTIC]:
- Small-cap (<$500M): typically **40-75%** single-day drop — single-asset names can be existential if runway is short.
- Mid-cap ($500M-$5B): typically **20-45%**.
- Large-cap ($5B+): typically **5-20%**, absorbed by diversified revenue.
Post-CRL, names often *continue to drift* rather than snap back, because (a) the timeline-to-revenue is pushed out 1-3 years, (b) a resubmission may require new/expensive data, and (c) a CRL frequently *forces* a dilutive financing at a depressed price (see Financing Behavior). An efficacy-related CRL drifts worse than a CMC/manufacturing CRL, which the market reads as fixable [Source 10, HEURISTIC].

---

## Financing behavior

The core, well-documented pattern: **cash-burning biotechs raise equity into strength.** Pre-revenue and early-commercial biotechs fund operations almost entirely through equity dilution, and they *time issuance to price spikes* — including post-catalyst run-ups — to minimize the share count sold [Source 13, Source 14].

- **Post-run-up offerings.** A large run into a catalyst is itself a *dilution risk signal*: it creates a window to sell shares at favorable prices, and companies "tap the shelf" quickly after a positive catalyst (or a big pre-catalyst rally) [Source 14, HEURISTIC]. Announcement of a secondary almost always produces a short-term price drop beyond the pure arithmetic of dilution, as event-driven holders exit [Source 13].
- **ATM (at-the-market) programs.** Common in small-cap biotech; they let a company sell shares *continuously and opportunistically* into strength through a registered agent, without a single announced deal — so a strong run can be met with steady, un-announced supply that caps upside [Source 14, HEURISTIC]. Presence of an active ATM (disclosed in filings) is a structural overhang.
- **Filing tells.** An S-3 shelf registration establishes *capacity* to raise; a 424B5 prospectus supplement signals an *imminent* offering. Traders monitor these as dilution early-warnings [Source 14, HEURISTIC].
- **Runway-driven pressure.** The financing decision is dominated by cash runway. A company with <12 months of cash is *structurally compelled* to raise, which means (a) any strength is likely sold into, and (b) a CRL or negative surprise forces a raise at a *depressed* price, compounding the drawdown. "Good raises follow good news" — a de-risking readout or approval is the ideal window — but the flip side is that the same names *must* raise into weakness when the catalyst fails [Source 13].
- **Base-rate context for why dilution is near-inevitable:** Phase-1→approval likelihood is only **7.9%** and even Phase-3 assets approve ~55-60% of the time [11]; the long, capital-intensive, high-failure path means recurring equity raises are the norm, not the exception, for pre-profit biotech.

*Practical read for a memo:* a big run into a catalyst raises the probability of a *post-catalyst offering* regardless of the catalyst's outcome — factor an dilution overhang into any "sell the news" or post-approval thesis, and factor a *forced, cheap* raise into any CRL/failure downside case.

---

## Caveats and failure modes of these stats

1. **Survivorship / selection bias.** Concordance, first-cycle, and filing→approval rates describe drugs that already survived to AdComm or filing. They *overstate* the odds for earlier-stage or lower-quality assets. Do not apply the ~90% filing→approval rate to a shaky single-Phase-3 program.
2. **AdComm is a selected sample.** FDA convenes AdComms disproportionately for *contested* applications, and holds them for only a minority of approvals. High overall concordance (88%) coexists with the fact that AdComms cluster on the hard cases — and FDA overrides *negative* votes ~33% of the time [3].
3. **Regime change / recency.** 2025 concordance (57% following the vote; 43% against) diverged sharply from the 2010-2024 record [5]. Leadership, policy, and political shifts can break historical base rates fast; date-check the regime before leaning on a decade average.
4. **Timeliness ≠ approval.** The ~94-96% "met PDUFA goal date" figures [1][2] measure *punctuality*, not the approve/CRL split. Don't conflate them.
5. **Novel-drug vs all-application rates diverge.** First-cycle and approval rates are much higher for CDER *novel* drugs than for the full NDA/BLA universe. Match the statistic to the asset type.
6. **Price/financing heuristics lack rigorous public datasets.** Run-up magnitude, implied-vs-realized bands, sell-the-news, and CRL-drift depths are practitioner consensus, not measured population means. The peer-reviewed CARs [8][9] are *directionally* reliable (asymmetry: downside > upside) but pooled across firm sizes and *smaller* than single-name PDUFA gaps.
7. **Idiosyncratic dominance.** Indication, competitive landscape, label details, safety database size, manufacturing readiness, prior CRLs, short interest, float, and cash runway routinely swamp the base rate for any single name. Base rates set the *prior*; the specific facts move it a lot.
8. **Reflexivity of "priced in."** The more a catalyst is anticipated (designations, positive AdComm, strong data), the smaller the approval surprise and the larger the *relative* downside if it fails — so a "high approval probability" name is not automatically a good long into the print.
9. **Numbers age.** Cycles (PDUFA VI vs VII), annual novel-drug counts, and yearly concordance all move. Re-pull before relying on a specific figure; this note was researched 2026-07-20.

---

## Sources

1. **New Drug Therapy Approvals 2024 (Advancing Health Through Innovation)** — U.S. FDA, Center for Drug Evaluation and Research (CDER), Jan 2025. 50 novel approvals; 47/50 (94%) met PDUFA goal date; 37/50 (74%) first-cycle; 26 orphan; 24 first-in-class. https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-2024 and report PDF https://www.fda.gov/media/190705/download

2. **Key measures of U.S. CDER drug approvals / PDUFA review timelines** — Statista, citing CDER (2025 data). ~96% of CDER approvals met the PDUFA goal date; standard ~10-month vs priority ~6-month review clocks. https://www.statista.com/statistics/817552/key-measurements-of-us-cder-drug-approvals/

3. **Association of Advisory Committee Votes With US FDA Decision-Making on Prescription Drugs, 2010-2021** — Daval CJR, Teng TW, Russo M, Kesselheim AS. *JAMA Health Forum*, 2023. Overall concordance 88% (262/298); positive→approval 97% (initial), 92% (supplemental); negative→non-approval 67% (initial), 86% (supplemental). https://pmc.ncbi.nlm.nih.gov/articles/PMC10329213/

4. **Advisory Committee Disagreement With US FDA on Approval Decisions an Increasingly Rare Event** — 3D Communications (J. DiBiasi), via *Pink Sheet*, Jan 24, 2023. Agreement 86% (2017-2022) vs 78% (2008-2015); 100% in 2022. https://3dcommunications.us/latest-thinking/posts/pink-sheet-advisory-committee-disagreement-with-us-fda-on-approval-decisions-an-increasingly-rare-event/

5. **FDA Went Against Adcomm Votes More, Held Fewer Adcomms in 2025** — BioSpace, 2025/2026. FDA went against its AdComm in 3 of 7 (43%) 2025 meetings vs ~16% discordance in 2020-2024. https://www.biospace.com/fda/fda-went-against-adcomm-votes-more-held-fewer-adcomms-in-2025

6. **CDER Brings Many Safe and Effective Therapies to Patients (FDA Voices) / annual novel-drug reports** — U.S. FDA, 2017-2024. First-cycle approval: ~81% (166/204, 2011-2016), ~85% (39/46, 2017), ~84% (46/55, 2023), ~74% (37/50, 2024); ≥85% most years since 2017. https://www.fda.gov/news-events/fda-voices/cder-brings-many-safe-and-effective-therapies-patients-and-consumers-2024

7. **Complete Response Letter frequency and resubmission classes** — Avalere Health, "What is a Complete Response Letter?" (analysis of PDUFA VI cycle). ~37% of BLAs/NDAs received a CRL in 2018-2022; Class 1 resubmission = 2-month, Class 2 = 6-month review goal. https://advisory.avalerehealth.com/insights/what-is-a-complete-response-letter

8. **The reaction of sponsor stock prices to clinical trial outcomes: An event study analysis** — Singh et al. *PLOS One*, 2022. 13,807 trials, 379 U.S.-listed firms, 2000-2020. Day 0-1 CARs: early positive +6.35%, endpoints met +0.54%, endpoints not met −2.71%, lack of efficacy −2.43%, safety −0.82%; documented positive/negative asymmetry. https://pmc.ncbi.nlm.nih.gov/articles/PMC9439234/

9. **Stock Market Returns and Clinical Trial Results of Investigational Compounds: An Event Study Analysis of Large Biopharmaceutical Companies** — Hirsch/Rothenstein et al. *PLOS One*, 2013. Median day-0 CAR +0.8% (positive) vs −2.0% (negative); negative-event underperformance larger and longer-lasting. https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0071966

10. **FDA Complete Response Letter (CRL) Explained: What It Means For Biotech Stocks** — RTTNews, 2025 (corroborated by MedPath). CRL single-day drops: small-cap 40-75%, mid-cap 20-45%, large-cap 5-20%; reaction scales inversely with size/pipeline. https://www.rttnews.com/3662437/fda-complete-response-letter-crl-explained-what-it-means-for-biotech-stocks.aspx

11. **Clinical Development Success Rates and Contributing Factors 2011-2020** — BIO, Informa Pharma Intelligence (Biomedtracker), and QLS Advisors, Feb 17, 2021. Phase 1→approval 7.9% (biologics 9.1%, small molecules 5.7%); Phase 3→approval ~55-60%; regulatory-filing→approval ~90%. https://go.bio.org/rs/490-EHZ-999/images/ClinicalDevelopmentSuccessRates2011_2020.pdf

12. **PDUFA Dates Explained / Biotech catalyst run-up mechanics** — Dan Sfera (dansfera.com) and BiopharmaWatch. [HEURISTIC] Run-up typically starts 4-8 weeks out, adds ~20-40%, peaks 1-3 days before date; PDUFA gaps commonly 20-50%+ for small/mid-caps; large-caps often flat/down on expected approval. https://dansfera.com/pdufa-explained and https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions

13. **Should Biotech Investors Fear Dilution?** — Nasdaq / The Motley Fool, 2018. [Practitioner analysis] Pre-revenue biotechs fund via repeated equity dilution; secondary announcements almost always cause short-term declines beyond pure dilution; "good raises follow good news." https://www.nasdaq.com/articles/should-biotech-investors-fear-dilution-2018-07-21

14. **Biotech Dilution Signals: How to Read 424B5, S-3, and ATM Filings** — Submarine Catalyst. [HEURISTIC] ATM programs sell into strength opportunistically without a single announced deal; S-3 = shelf capacity, 424B5 = imminent offering; companies tap the shelf fast after run-ups. https://submarinecatalyst.com/sec-dilution-signals-biotech.html

15. **Options implied move / IV crush around biotech binary events** — MarketChameleon biotech catalyst reports and QuantStrategy.io. [HEURISTIC] Pre-event IV can reach 150-300% annualized; implied move from ATM straddle; IV collapses on resolution regardless of direction. https://marketchameleon.com/Reports/biotech-stock-catalysts and https://quantstrategy.io/blog/options-trading-strategies-for-high-volatility-biotech/

16. **Why Some FDA Approvals Trigger Stock Drops Instead of Gains ("sell the news")** — Biotech Analyzer. [HEURISTIC] Long-anticipated approvals often pop then drift down as the outcome was priced in during run-up; ~12-18 months to meaningful revenue; dilution/label risk caps upside. https://biotechanalyzer.com/insights/why-some-fda-approvals-trigger-stock-drops-instead-of-gains

17. **FDA publication of Complete Response Letters / CRL transparency** — U.S. FDA (openFDA CRL dataset) and Pharmacy Times coverage, 2025. FDA has begun publishing hundreds of historical CRLs and moving toward real-time release, making deficiency details public. https://open.fda.gov/apis/transparency/completeresponseletters/ and https://www.pharmacytimes.com/view/fda-publishes-hundreds-of-complete-response-letters-from-first-half-of-the-decade
