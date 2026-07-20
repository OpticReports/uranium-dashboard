# Clinical-Trial Success Base Rates — Cited Reference Note

**Purpose:** A grounding knowledge file of empirical clinical-trial success / likelihood-of-approval (LOA) base rates, with every quantitative claim sourced, for calibrating probability estimates in a genomics/biotech trading assistant.

**Last researched: 2026-07-20**

---

## How to use this

- These are **BASE RATES** (priors), not verdicts on any specific asset. They describe how an *average* program in a given bucket has historically fared.
- **Always adjust** for the specific drug, indication, trial design, sponsor quality, prior data readouts, and mechanism. A prior of "Phase 2 oncology ≈ 25% advance" is a starting point to be updated by the actual evidence in front of you, not a substitute for it.
- Buckets are **compounding**: LOA from Phase 1 = (P1→2) × (P2→3) × (P3→filing) × (filing→approval). A drug that has already cleared Phase 2 should be scored off the *conditional* rate from its current phase, not the Phase-1 LOA.
- Numbers differ across studies because of **definitional choices** (all-indications vs lead-indication, dataset, time window, how suspensions are counted). Where sources diverge, both/ranges are given. Treat the *direction and rank order* as more robust than any single decimal.
- Rank-order intuition that is stable across every major study: **Phase 2 is the biggest hurdle; oncology and neurology/CNS run LOW; hematology, rare/orphan disease with genetic basis, and biomarker-selected programs run HIGH; the regulatory (NDA/BLA→approval) step is nearly always the easiest.**

---

## Section 1 — Phase transition success rates & Likelihood of Approval (LOA)

### 1.1 Headline industry-wide numbers (three primary datasets)

| Metric | BIO/Biomedtracker/QLS 2011–2020 [S1] | Wong, Siah & Lo 2019 (2000–2015) [S2] | Hay et al. 2014 (2003–2011) [S3] |
|---|---|---|---|
| Phase 1 → Phase 2 | 52.0% (n=4,414) | 66.4% | 64.5% (n=1,918) |
| Phase 2 → Phase 3 | 28.9% (n=4,933) | 58.3% | 32.4% (n=2,268) |
| Phase 3 → NDA/BLA filing | 57.8% (n=1,928) | 59.0% | 60.1% (n=975) |
| NDA/BLA filing → Approval | 90.6% (n=1,453) | — | 83.2% (n=659) |
| **Overall LOA, Phase 1 → Approval (all indications)** | **7.9% (n=12,728)** | **13.8%** | **10.4% (n=5,820)** |
| Overall LOA, lead indication only | — | 21.6% | 15.3% (n=3,688) |

**Why the three disagree — read before quoting a single number:**
- **Definition of Phase 2→3.** Wong/Siah/Lo report ~58% for Phase 2→3, roughly double BIO's 28.9% and Hay's 32.4%. Wong et al. count a broader set of trial-level transitions and treat "success" differently; BIO/Hay count program suspensions against the phase, which makes Phase 2 look far harder. This single definitional gap explains most of the spread in the overall LOA. [S1][S2][S3]
- **All-indications vs lead-indication.** Counting every drug-indication path (all-indications) lowers success vs. counting only a drug's best/lead indication. Hay's all-indications LOA is 10.4% but lead-indication LOA is 15.3%; Wong's are 13.8% vs 21.6%. [S2][S3]
- **Time window & dataset.** BIO 2011–2020 (Biomedtracker); Wong 2000–2015 (Citeline/Informa Trialtrove + Pharmaprojects); Hay 2003–2011 (Biomedtracker). Later windows include the oncology/immuno-oncology boom, which is high-volume but low-LOA and drags the aggregate down. [S1][S2][S3]

**Practical default:** For a broad "random Phase 1 asset, all comers" prior, use **~7.9%–10.4%** (BIO/Hay). If you specifically mean "this drug for its single most-advanced indication," the lead-indication figure (~15%–22%) is the better anchor. [S1][S2][S3]

### 1.2 Where the attrition happens

- **Phase 2 is the killer.** In the BIO 2011–2020 set only 28.9% of Phase 2 programs advanced — the lowest of the four transitions, in every disease area studied. This is the first deliberate efficacy/proof-of-concept test. [S1]
- **Phase 1 flatters itself.** Phase 1 is largely a safety gate (52% BIO / ~65% Wong & Hay). BIO explicitly warns Phase 1 rates may be inflated by *delayed reporting / omission bias* — large firms often do not publicly disclose quiet Phase 1 failures. [S1]
- **The regulatory step is easy.** NDA/BLA → approval is ~90.6% (BIO) / 83.2% (Hay), because it counts *eventual* success including resubmissions after Complete Response Letters (CRLs). Only 137 of ~1,453 filed programs were suspended at this stage over 2011–2020. Do not model filing→approval as a major risk gate for a drug with clean pivotal data. [S1][S3]
- **Timeline:** BIO estimates it takes on average **~10.5 years** for a Phase 1 asset to reach approval; higher-LOA disease areas tend to have the shortest timelines. [S1]

### 1.3 By therapeutic area — BIO 2011–2020 LOA from Phase 1 (the reference table)

Ordered high→low. LOA is the compounded Phase 1→approval probability; n = total advanced-or-suspended transitions used in the calculation. Source: BIO/Biomedtracker/QLS 2011–2020 [S1].

| Disease area | LOA (Phase 1 → approval) | n | P1→2 | P2→3 | P3→filing | Filing→appr |
|---|---|---|---|---|---|---|
| **Hematology** | **23.9%** | 352 | 69.6% | 48.1% | 76.8% | 93.1% |
| Metabolic | 15.5% | 399 | 61.8% | 45.0% | 63.6% | 87.5% |
| Infectious disease | 13.2% | 1,170 | 57.8% | 38.4% | 64.0% | 92.9% |
| Other | 13.0% | 541 | 63.6% | 38.6% | 60.0% | 88.4% |
| Ophthalmology | 11.9% | 415 | 71.6% | 35.5% | 51.2% | 91.1% |
| Autoimmune | 10.7% | 1,305 | 55.2% | 31.4% | 65.3% | 94.1% |
| Allergy | 10.3% | 201 | 56.4% | 28.3% | 64.7% | 100.0% |
| Gastroenterology | 8.3% | 186 | 46.7% | 34.2% | 57.1% | 90.9% |
| **All indications** | **7.9%** | **12,728** | **52.0%** | **28.9%** | **57.8%** | **90.6%** |
| Respiratory | 7.5% | 501 | 55.9% | 21.9% | 64.5% | 95.6% |
| Psychiatry | 7.3% | 442 | 52.7% | 26.8% | 56.3% | 91.2% |
| Endocrine | 6.6% | 887 | 43.3% | 26.6% | 66.2% | 86.3% |
| **Neurology** | **5.9%** | 1,411 | 47.7% | 26.8% | 53.1% | 86.7% |
| **Oncology** | **5.3%** | 4,179 | 48.8% | 24.6% | 47.7% | 92.0% |
| Cardiovascular | 4.8% | 651 | 50.0% | 21.0% | 55.2% | 82.5% |
| **Urology** | **3.6%** | 88 | 40.9% | 15.0% | 69.2% | 84.6% |

Key reads: **Hematology's 23.9% is ~7× Urology's 3.6%**, the widest spread in the dataset, driven mostly by the Phase 2 transition (48.1% vs 15.0%). Oncology and Neurology carry the two largest n values *and* below-average LOA, so they mechanically drag the whole-industry number down. [S1]

### 1.4 Oncology detail (BIO 2011–2020) [S1]

- **All oncology LOA (P1): 5.3%** (n=4,179) vs **non-oncology 9.3%** (n=8,549) — roughly half. Oncology = 33% of all transitions in the dataset.
- **Solid tumors: 4.6% LOA** (n=2,982) vs **hematologic cancers: 7.5% LOA** (n=1,094).
- **Immuno-oncology (IO): 12.4% LOA** (n=679) — a rare high-LOA pocket inside oncology, driven by an unusually strong Phase 2 advance rate of 42.0% vs 24.6% for oncology overall.
- Oncology's *only* above-average step is the regulatory one (92.0% filing→approval), reflecting accelerated-approval pathways.

### 1.5 Cross-study therapeutic-area sanity checks

- Wong, Siah & Lo 2019 (overall probability of success, Phase 1→approval): **oncology 3.4%** (lowest; vs 5.1% in prior studies), vaccines/infectious ~33.4%, ophthalmology ~32.6%, cardiovascular ~25.5%, CNS ~15.0%, autoimmune ~15.1%; **all non-oncology combined ~20.9%.** (Wong's absolute levels sit above BIO/Hay for the definitional reasons in §1.1, but the *rank order* — oncology bottom, infectious/ophtho top — matches.) [S2]
- Hay et al. 2014: **oncology lowest at 6.7% LOA** (n=1,803); infectious disease 16.7%, autoimmune 12.7%, the pooled "other" (allergy/GI/ophtho/derm/ob-gyn/urology) highest at 18.2%. [S3]
- **Takeaway that survives all three studies:** oncology (esp. solid tumors) and CNS/neurology are structurally LOW; hematology and infectious disease are HIGH. Use this ranking even when the absolute decimals differ.

---

## Section 2 — What moves the odds

### 2.1 Patient-selection biomarkers (largest single documented lever)
- **BIO 2011–2020: programs using patient-preselection biomarkers had LOA 15.9% vs 7.6% without — a ~2× premium.** The benefit is concentrated at **Phase 2 (46.3% advance with biomarker vs 28.3% without)** and Phase 3 (68.2% vs 57.1%); Phase 1 shows essentially no difference (~52% either way). Only ~6% (767/12,728) of transitions used preselection biomarkers. [S1]
- **Wong, Siah & Lo 2019: with biomarkers 10.3% vs without 5.5% overall POS (~87% relative improvement).** [S2]
- Interpretation: enrichment mostly de-risks the *efficacy* gates, not safety. A biomarker-defined population is one of the strongest positive priors available.

### 2.2 Prior-approval precedent / drug novelty
- **Novel vs off-patent:** BIO 2011–2020 novel drugs (NMEs + new biologics + vaccines) had LOA 6.8% (n=10,527) vs off-patent/non-originator products 14.7% (n=2,161) — the ~2× gap is largest at Phase 3 (52.9% novel vs 70.3% off-patent). Reformulations/repurposing of validated mechanisms carry lower risk. [S1]
- **Novel-mechanism penalty:** BIO's machine-learning analysis ranks **disease indication, target, modality, and drug novelty** as the top predictive factors of phase success — a first-in-class / unprecedented-target program should be discounted relative to a "me-too" hitting a clinically validated target. [S1] Biosimilars sit at the extreme validated end (32.2% LOA from Phase 1). [S1]

### 2.3 Orphan / rare disease
- **BIO 2011–2020 (non-oncology rare disease): LOA 17.0% (n=1,256) vs chronic high-prevalence disease 5.9% (n=1,978) — ~3×.** The rare-disease edge is again largest at Phase 2 (44.6% advance vs 23.1%). Rare-oncology indications also beat non-rare oncology (6.8% vs 4.4% LOA). [S1]
- Drivers: strong genetic causal links, clearer endpoints, smaller/faster trials, regulatory flexibility (orphan designation, single-arm pivotal acceptance). Chronic high-prevalence indications (large trials, modest effect sizes, active comparators) are a *negative* prior even outside oncology.

### 2.4 Pivotal design & endpoint type
- **NDA/BLA→approval is design-contingent:** BIO notes Phase-3 design largely determines the regulatory outcome; biomarker-supported programs carry a 96.0% filing→approval rate vs 90.3% without. [S1]
- **Surrogate vs clinical endpoints / single-arm vs randomized:** hematology and rare disease benefit from accepted surrogate endpoints (e.g., hematologic response, transfusion independence) and single-arm registrational trials, which shorten timelines and lift LOA; large chronic-disease indications requiring long randomized outcome trials on hard clinical endpoints are structurally harder. This is the mechanism behind the hematology/rare-disease premium above. [S1] Oncology's high regulatory-step success (92%) reflects accelerated approval on surrogate endpoints (ORR/PFS). [S1]

---

## Section 3 — Modality-specific notes for a genomics universe

Context: BIO 2011–2020 explicitly found **"biological complexity generally leads to higher LOA."** LOA from Phase 1 by modality (BIO 2011–2020, Figure 10) [S1]:

| Modality | LOA (P1→appr) | n | Notes |
|---|---|---|---|
| CAR-T | 17.3% | 67 | Highest of all modalities; >3× oncology avg. 4 successful BLA transitions in window. |
| siRNA / RNAi | 13.5% | 87 | 3 approvals as of 2020 (first in 2018). Strong Phase 1 (70%). |
| Monoclonal antibody | 12.1% | 2,136 | Large-n, validated large-molecule class. |
| Antibody-drug conjugate (ADC) | 10.8% | 184 | — |
| Gene therapy | 10.0% | 96 | Includes AAV; small n. |
| Vaccine | 9.7% | 316 | 100% NDA/BLA→approval (n=27). |
| Protein | 9.4% | 800 | — |
| Peptide | 8.0% | 619 | — |
| Small molecule | 7.5% | 7,171 | The industry workhorse baseline. |
| **Antisense (ASO)** | **5.2%** | 162 | Lowest here; weak Phase 2 (20%) and unusual 66.7% filing rate in window. |

Cross-check: Wong/Siah/Lo (biologics) and Hay 2014 both find **biologics ≈ 2× the LOA of small-molecule NMEs** (Hay: biologics 14.6% vs NME 7.5%; BIO: biologic 9.1% vs NME 5.7%). [S1][S3] These modality n's are small — treat CAR-T/RNAi/gene-therapy LOAs as *indicative*, not precise.

### 3.1 Gene editing — CRISPR / base / prime editing
- **Precedent now exists:** Casgevy (exagamglogene autotemcel), the **first CRISPR/Cas9-edited therapy, FDA-approved 2023-12-08** for sickle cell disease (ex vivo edit of autologous CD34+ cells raising fetal hemoglobin). [S6] This converts gene editing from "unprecedented modality" toward "validated for ex vivo hematopoietic editing."
- **Risk profile:** ex vivo edits (blood/immune cells) are substantially de-risked on delivery vs in vivo. In vivo editing and newer classes (base/prime editing) remain early — key risks are **off-target/on-target editing, delivery, durability of edit, and long-term genotoxicity**. Score in-vivo/base/prime editors closer to the gene-therapy prior with an added novelty discount.

### 3.2 Gene therapy — AAV (in vivo)
- BIO gene-therapy LOA 10.0% (n=96, small) [S1]. Very few approvals despite two decades of investment; the field's cautionary case, Glybera, was EMA-approved 2012 then withdrawn 2017. [S5]
- **Specific risks:** (i) **pre-existing/anti-vector immunity** — a large share of AAV trials (~45%) exclude patients with neutralizing antibodies, capping addressable population and complicating enrollment; (ii) **durability** — single-dose durable expression is the value proposition but waning transgene expression and inability to re-dose are real risks; (iii) **manufacturing/CMC** — vector production scale, potency, and comparability are frequent bottlenecks; (iv) **safety** — dose-dependent hepatotoxicity and, at high systemic doses, serious immune events. [S5]

### 3.3 Durable cell & gene therapy (dCGT) — dedicated dataset
MIT NEWDIGS FoCUS "Pipeline Analysis Model" (PAM), ClinicalTrials.gov 1988–2023, published as supplementary to Nature Reviews Drug Discovery 2025 [S4]:

| Segment | Phase 1 | Phase 2 (incl. I/II) | Phase 3 (incl. II/III) | Filing→appr | **LOA** |
|---|---|---|---|---|---|
| **Rare-disease gene therapy** | 55.0% | 49.2% | 68.4% | 100% | **18.5%** |
| **Hematologic CAR-T / TCR** | 26.3% | 38.7% | 75.0% | 100% | **7.6%** |
| BIO all-therapeutic-areas (ref.) | 52.0% | 28.9% | 57.8% | 90.6% | 7.9% |
| BIO all-oncology (ref.) | 48.8% | 24.6% | 47.7% | 92.0% | 5.3% |
| IQVIA all-therapeutic-areas (ref.) | 45% | 36% | 56% | 81% | 7.3% |

Reads: **rare-disease gene therapy (18.5%) substantially beats the market**, consistent with the rare-disease + biomarker premiums. Hematologic CAR-T/TCR (7.6%) tracks the *hematologic-oncology* benchmark (~7.5%) rather than all-oncology — i.e., cell therapy roughly matches, and modestly beats, its oncology comparator rather than being a magic bullet. Note the methodology counts trial-phase progressions on ClinicalTrials.gov and heavily combines Phase 1/2 (67% of orphan gene-therapy trials start in Phase 1/2), so these are not directly comparable decimal-for-decimal to BIO. [S4]

### 3.4 Antisense (ASO) / RNAi / oligonucleotides
- BIO 2011–2020: **siRNA/RNAi 13.5% LOA (high)** but **antisense 5.2% LOA (low)** — do not treat "oligos" as one bucket. [S1]
- **Field is now validated & productive:** ~**21 oligonucleotide therapeutics FDA-approved as of 2024** (≈11 ASOs, 6 siRNAs, 3 aptamers, plus defibrotide). [S8] GalNAc conjugation (liver targeting) and chemical-stability advances (e.g., cEt) have driven potency/durability up and dosing frequency down. [S8]
- **Risks:** delivery beyond liver/CNS remains the core constraint; historic ASO issues include injection-site/renal/hepatic tolerability; **manufacturing** of oligos has its own CMC challenges (solvent recovery, reagent stability scheduling). [S8]

### 3.5 mRNA
- **Validated at scale for prophylactic vaccines** (COVID-19); BIO vaccines LOA 9.7% with 100% regulatory-step success (small n) [S1]. Expansion into therapeutic mRNA (oncology neoantigen vaccines, protein-replacement, autoimmune) is earlier-stage.
- **Risks:** LNP delivery gives **transient** expression — protein appears in ~2–6 h, peaks 24–48 h, and declines over ~7–14 days — so durability/redosing and biodistribution/tolerability are the central translational challenges beyond vaccines. [S9] Individualized neoantigen mRNA (e.g., mRNA-4157/V940) has shown a ~44% relapse-risk reduction vs pembrolizumab monotherapy in melanoma, illustrating upside but still mid-stage. [S9]

### 3.6 Cell therapy (CAR-T / TCR)
- Highest single-modality LOA in BIO (CAR-T 17.3%) [S1] and 7.6% in the dedicated dCGT dataset for hematologic CAR-T/TCR [S4]. Strongest evidence base is **hematologic malignancies**; solid-tumor cell therapy remains far less proven.
- **Risks:** manufacturing (autologous vein-to-vein logistics, cost, failure-to-manufacture), CRS/neurotoxicity safety, and durability of response. Allogeneic "off-the-shelf" approaches trade manufacturing risk for persistence/rejection risk.

### 3.7 Liquid-biopsy diagnostics
- Different regulatory track (diagnostics/companion Dx, not drug NDA/BLA) — **drug LOA base rates do not transfer.** Success hinges on analytical + clinical validation, and reimbursement/coverage (e.g., CMS) is often the binding commercial gate rather than "approval." No authoritative published phase-transition base-rate series analogous to the BIO drug tables was located for liquid-biopsy diagnostics as of this research date; score these on evidence-generation and coverage milestones, not on the drug LOA framework. (Absence-of-data flag — do not fabricate a percentage.)

---

## Section 4 — Key caveats: how these numbers can mislead

1. **Survivorship / reporting bias.** BIO explicitly warns Phase 1 success is likely *overstated* because large firms under-report quiet early failures; failures that never enter the tracked database inflate apparent success. [S1]
2. **Self-reported / commercial pipelines.** Biomedtracker, Pharmaprojects/Trialtrove and ClinicalTrials.gov depend on press releases, investor calls, and registrations — negative results are disclosed less and later than positive ones. [S1][S3][S4]
3. **All-indications vs lead-indication is a factor-of-~1.5 swing.** The same underlying reality reads as 10.4% or 15.3% (Hay) / 13.8% or 21.6% (Wong) depending purely on this choice. Always know which convention a number uses before quoting it. [S2][S3]
4. **Definitional divergence across studies.** The Phase 2→3 rate is ~29–32% (BIO/Hay) vs ~58% (Wong) — a ~2× difference from methodology alone, not from reality. Never mix phase rates across studies inside one compounded LOA calculation. [S1][S2][S3]
5. **Look-ahead / regime change.** All series are historical. LOA drifts with the therapeutic mix (oncology/CNS heavy = lower aggregate), regulatory posture (accelerated approval expansions/contractions), and platform maturation. A 2011–2020 base rate may misprice a 2026 program in a fast-moving modality. [S1]
6. **Small-n modality figures.** CAR-T (n=67), gene therapy (n=96), siRNA (n=87), ADC (n=184) LOAs rest on tiny samples and few approval events — wide confidence intervals; treat as directional. [S1]
7. **The regulatory step is not risk-free at the margin.** ~90% filing→approval counts *eventual* success after CRLs and resubmissions; a specific program can still receive a CRL and be delayed years even if it "eventually" approves. [S1]
8. **Compounding amplifies error.** LOA multiplies four uncertain rates; small per-phase mis-estimates compound. Prefer conditioning on the drug's *current* phase over quoting a Phase-1 LOA for a late-stage asset.
9. **Bucket ≠ destiny.** These are population averages. A biomarker-selected, precedented-target, rare-disease asset with strong Phase 2 data can vastly outrun its headline bucket; a first-in-class solid-tumor program can underperform even oncology's low bar.

---

## Sources

1. **Clinical Development Success Rates and Contributing Factors 2011–2020.** BIO (Biotechnology Innovation Organization), Informa Pharma Intelligence / Biomedtracker, and QLS Advisors. February 2021. (12,728 transitions, 9,704 programs, 1,779 companies; Jan 2011–Nov 2020.) https://go.bio.org/rs/490-EHZ-999/images/ClinicalDevelopmentSuccessRates2011_2020.pdf — landing page: https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020
2. **Wong CH, Siah KW, Lo AW. "Estimation of clinical trial success rates and related parameters."** *Biostatistics*, 2019;20(2):273–286 (correction: Biostatistics 2019;20(2):366). (406,038 trial records, 21,143 compounds, 2000–2015; MIT/Andrew Lo lab.) https://academic.oup.com/biostatistics/article/20/2/273/4817524 — open copy: https://pmc.ncbi.nlm.nih.gov/articles/PMC6409418/
3. **Hay M, Thomas DW, Craighead JL, Economides C, Rosenthal J. "Clinical development success rates for investigational drugs."** *Nature Biotechnology*, 2014;32(1):40–51. (BioMedTracker; 4,451 drugs, 7,372 development paths, 5,820 transitions; 2003–2011.) https://www.nature.com/articles/nbt.2786 doi:10.1038/nbt.2786
4. **"Clinical development success rates for durable cell and gene therapies"** (MIT NEWDIGS FoCUS Pipeline Analysis Model; Young CM, Quinn C, Trusheim MR et al.). Supplementary information to *Nature Reviews Drug Discovery*, 2025. (ClinicalTrials.gov 1988–2023; rare gene therapy LOA 18.5%, hematologic CAR-T/TCR 7.6%.) https://doi.org/10.1038/d41573-025-00036-8 — PDF: https://media.nature.com/original/magazine-assets/d41573-025-00036-8/50677254
5. **Thomas D, Burns J, Audette J, Carroll A, Dow-Hygelund C, Hay M. "Clinical Development Success Rates 2006–2015."** BIO / Biomedtracker / Amplion, 2016. (Predecessor to [S1].) https://go.bio.org/rs/490-EHZ-999/images/Clinical%20Development%20Success%20Rates%202006-2015%20-%20BIO,%20Biomedtracker,%20Amplion%202016.pdf
6. **FDA / Vertex Pharmaceuticals & CRISPR Therapeutics — CASGEVY (exagamglogene autotemcel) approval,** 2023-12-08 (first CRISPR/Cas9 gene-editing therapy approved in the US; sickle cell disease). https://www.drugs.com/history/casgevy.html — company release: https://news.vrtx.com/news-releases/news-release-details/vertex-and-crispr-therapeutics-announce-us-fda-approval
7. **IQVIA Institute. "Global Trends in R&D 2024: Activity, Productivity, and Enablers."** IQVIA, 2024. (All-therapeutic-area LOA ~7.3%; comparator dataset in [S4].) https://www.iqvia.com/insights/the-iqvia-institute/reports-and-publications/reports/global-trends-in-r-and-d-2024-activity-productivity-and-enablers
8. **Oligonucleotide Therapeutics Society / "2024 FDA TIDES (Peptides and Oligonucleotides) Harvest"** (PMC) and OTS 2024 FDA-approvals review. (≈21 oligonucleotide therapeutics FDA-approved as of 2024.) https://pmc.ncbi.nlm.nih.gov/articles/PMC11945313/ — https://oligotherapeutics.org/2024-fda-approvals-a-wave-of-innovation-in-treating-serious-diseases/
9. **"mRNA therapeutics beyond vaccines: dosing precision challenges and clinical translation framework."** *RSC Pharmaceutics*, 2026. (LNP-mRNA expression kinetics: onset 2–6 h, peak 24–48 h, decline 7–14 days; mRNA-4157 melanoma data.) https://pubs.rsc.org/en/content/articlehtml/2026/pm/d5pm00159e
10. **Yamaguchi S, Kaneko M, Narukawa M. "Approval success rates of drug candidates based on target, action, modality, application, and their combinations."** *Clinical and Translational Science*, 2021;14(3):1113–1122. (Modality/target-based approval success; 2000–June 2019.) doi:10.1111/cts.12980

---

*Compiled 2026-07-20. All quantitative claims carry an inline [S#] reference to the numbered Sources list. Where sources disagree, ranges and the reason for divergence are stated in-line. Modality LOAs with small n are flagged as directional. No liquid-biopsy diagnostic phase-transition base rate is reported because no authoritative series was found — do not substitute a drug LOA for it.*
