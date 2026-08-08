# Venture Deal Analyzer — evidence-based design

**Status:** research + design proposal (no code yet). **Author basis:** three
parallel research passes (2026-08-08) over the academic VC-decision literature,
founder-assessment evidence, published firm memos/processes, and the current
state of AI-assisted diligence. Sources cited inline.

---

## 1. Objective

Build a deal analyzer that produces institutional-quality investment memos
fast, across heterogeneous sectors (robotics, materials science, consumer,
SaaS, bio/climate), with a one-page executive synthesis on top and full depth
underneath — and that provably gets *better over time* via a logged
prediction/outcome feedback loop.

## 2. What the evidence actually says

Six findings drive the whole design. Each is load-bearing.

### 2.1 Returns come from selection, and errors are asymmetric

- VCs themselves rank **deal selection** as the #1 source of value creation
  (49% "most important" vs 27% value-add, 23% sourcing) — Gompers, Gornall,
  Kaplan & Strebulaev, *JFE* 2020 (885 VCs surveyed).
- Return distribution is a power law: **~65% of deals return <1x, ~4% return
  >10x, ~0.4% return ≥50x** (Correlation Ventures, 21,640 financings
  2004–2013). In Horsley Bridge data (~7,000 investments), **6% of deals
  produced ~60% of total returns**, and the *best* funds had MORE sub-1x deals
  than average funds ("Babe Ruth effect").
- At seed, the tail is fat enough (Othman/AngelList: power-law α < 2 →
  unbounded mean) that **a missed winner costs more than any number of small
  losses**. Fewer than ~10% of seed investors beat broad indexing of credible
  deals.

**Design consequence:** the analyzer is a **disqualifier of predictably bad
deals and a detector of extreme-upside potential — not a precision picker.**
Its two headline outputs are a kill-list score (is this predictably bad?) and
an outlier thesis (what would have to be true for ≥10x, and is any of it
already evidenced?). It must never kill a deal solely on "fixable" flaws
attached to a live outlier thesis.

### 2.2 Predictably-bad deals exist and are machine-detectable

Davenport (2022; 16,054 accelerator startups, >$9B invested): a simple ML
model on information available at investment time shows **~50% of follow-on
investments were "predictably bad"**; dropping the flagged bottom half and
indexing the rest would have raised returns by **7–41 percentage points**.
LLM-specific: a 2025 study on 61,814 ventures found LLM agents outperform
human analysts at screening; a Michigan forecasting tournament found Gemini
2.5 Pro at **0.74 rank correlation with outcomes vs 0.04–0.45 for human
experts** — and adding humans to the loop *degraded* accuracy. (Caveats:
screening ≠ allocating; self-published components; observable-signal skew.)

**Design consequence:** automate the screen aggressively; reserve human time
for references, terms, and the final call.

### 2.3 Mechanical aggregation beats holistic gut

- Meehl/Grove et al. (2000 meta-analysis, 136 studies): formula-based
  combination of inputs beats clinical judgment on average by ~10%; clinical
  wins in only 6–16% of studies. Robust for 60+ years.
- Structured interviews predict at **r ≈ .42–.51 vs r ≈ .19–.38
  unstructured** (Schmidt & Hunter 1998; Sackett et al. 2022 puts structured
  at the top of ALL selection methods and unstructured near the bottom).
  The modal VC founder meeting is unstructured — i.e., close to the
  worst validated assessment method.

**Design consequence:** fixed question set per section, anchored 1–5 rubrics,
**pre-committed weights, scores recorded independently BEFORE discussion,
mechanically combined**. The system enforces the structure; humans supply
judgment inside it.

### 2.4 Team vs market: weight the horse at least as much as the jockey

- VCs *say* team is everything (95% cite it, 47% rank it #1; 96% attribute
  success to team — GGKS 2020).
- Outcome data disagrees: Kaplan, Sensoy & Strömberg (*JF* 2009) tracked
  firms from business plan → IPO: **business lines almost never change; the
  management team usually does** (most founder-CEOs replaced by IPO).
  "Bet on the horse at the margin."
- Wasserman: **65% of high-potential startup failures trace to people
  problems**; ~75% of founder-CEOs are eventually replaced.

**Design consequence:** market/business quality gets equal-or-greater
scorecard weight than team. Team assessment focuses on what outcome data
supports: execution evidence, replaceability risk, and team-conflict red
flags — not charisma.

### 2.5 Founder assessment: what's real, what's noise

Ranked by evidence weight:

1. **Structured, scored evidence of execution/persistence** (r ≈ .4 class —
   Kaplan-Klebanov-Sorensen *JF* 2012: performance loads on general ability +
   execution skills, NOT "team player" interpersonal traits; ghSMART-style
   4-hour structured assessment is the only near-validated instrument).
2. **Prior successful exit: ≈ +9pp absolute success probability** (30% vs
   21% first-timers vs 22% previously-failed — Gompers-Kovner-Lerner-
   Scharfstein *JFE* 2010). BUT the market prices it in: First Round found
   repeat-founder deals did NOT outperform because entry valuations ran >50%
   higher. Code track record as company-success signal, not returns signal.
3. **Team composition & trait diversity**: 3+ founders >2x solo success odds;
   diverse founder archetypes 8–10x solo (McCarthy et al. 2023, *Sci Rep*,
   n≈21k, 82.5% classifier accuracy — correlational, Twitter-inferred).
   Technical+commercial mix matters for enterprise (First Round: technical
   cofounders +230% enterprise, no benefit consumer). Counter-evidence
   (Greenberg-Mollick): solo founders survive better — solo is a
   scale-ambition question, not a survival risk.
4. **Red flags**: quick un-negotiated equal equity splits (Hellmann-Wasserman
   — the *failure to negotiate* is the signal); friends/family cofounders
   without prior working history; "king vs rich" control orientation
   (control-keeping founders' companies worth ~half); grandiosity/narcissism
   markers → widen the variance estimate rather than dock the mean
   (Chatterjee-Hambrick: more extreme, more volatile outcomes, same mean).
5. **NLP personality signals**: weak-prior tiebreaker only, with explicit
   confidence bands (openness/energy/low-modesty correlate with success but
   basis is correlational). **Do NOT use**: grit scales (ρ=.84 with
   conscientiousness — jangle fallacy; Credé et al. 2017), age penalties
   (Azoulay et al. *AER* 2020: mean age of fastest-growing 0.1% founders is
   **45**; a 50-year-old is ~1.8x more likely than a 30-year-old to found a
   top-growth firm).

### 2.6 Decision hygiene has cheap, positive-EV components

- **Pre-mortem** ("it's 2031 and this returned 0x — why?"): prospective
  hindsight improves risk identification ~30% (Mitchell-Russo-Pennington
  1989; Klein HBR 2007).
- **Structured dissent** (devil's advocate / dialectical inquiry) beats
  consensus expert approach (Schwenk 1990 meta-analysis) — but assigned
  dissent is weaker than genuine dissent → an LLM red-team agent is a
  genuinely adversarial, non-role-playing standing dissenter.
- **Base rates + calibration**: ~1 hour of base-rate training improved
  forecast Brier scores ~10% for a year+ (Mellers et al. 2014, Good Judgment
  Project). Calibration requires outcome feedback — which VC's 5–10-year
  cycles destroy unless predictions are **logged and scored**.
- **Anti-portfolio tracking**: logging pass reasons and re-scoring against
  outcomes is the only way to learn whether your filters are alpha or bias
  (Bessemer institutionalized the confession; the lesson from their Airbnb
  pass: anchoring on price while underestimating growth slope).

## 3. Architecture

Pipeline of specialized agents; deterministic orchestration; every stage
writes to a common deal record.

```
Intake & Grounding → Sector Router → Parallel Analysis Agents → Adversarial
Layer → Mechanical Synthesis → Tiered Memo → Forecast Log
```

### Stage 1 — Intake & grounding
Parse deck, data room, call notes, product data. **Every number gets a
provenance tag**: `founder-claimed` / `independently-verified` /
`system-estimated`. No untagged number may appear downstream. This is the
defense against the two documented LLM failure modes: hallucinated quant
(~8–15% hallucination rates on unsourced financial claims) and
garbage-in from founder-provided data (the reason Tribe Capital insists on
raw product data, not deck metrics).

### Stage 2 — Sector router
A shared spine (identical section skeleton for every deal) + a sector
overlay that swaps in the key questions, benchmarks, and kill criteria:

| Sector | Organizing question | Benchmarks / gates |
|---|---|---|
| Robotics/hardware | Is technical risk retired before market risk is bought? | TRL 7–8 + paid pilots before serious checks; BOM/COGS glide path EVT→NOAK; DFM plan; services-drag check (product co. vs integrator); RaaS vs capex economics |
| Materials/deep tech | Lab-to-fab: does the process survive 1000x volume? | TRL 1–9 staging; composition-of-matter vs process IP; offtake/paid pilots as demand validation; years-to-revenue vs fund life; the high-TRL/low-business-readiness failure mode |
| Consumer | Do cohort curves flatten by month 6–12, or decline forever? | LTV:CAC ≥3:1 (marketplaces 4x+ both sides); organic vs paid-treadmill mix; whale concentration; smiling-curve reactivation |
| SaaS | Efficient growth? | Burn multiple 1.0–1.5x (Series A), <1x elite; NDR >100% mandatory, 120%+ elite; magic number >0.75; Rule of 40 |
| Bio/climate | Does each tranche buy a killable experiment? | Milestone-gated tranching on regulatory value-inflection points; syndicate reserves to next gate |

### Stage 3 — Parallel analysis agents
Market & why-now · Competition (current + adjacent + incumbents' likely
response) · Product/tech · Traction vs sector benchmarks · Founder/team
(structured rubric per §2.5) · Deal & valuation (price vs entry, ownership
math, follow-on reserves, track-record-priced-in check).

### Stage 4 — Adversarial layer
1. **Red-team agent**: prompted to kill the deal; must produce the strongest
   pass case with evidence. Counters LLM sycophancy toward the pitch
   narrative (observed ~58% of cases, ~78.5% persistence once triggered).
2. **Pre-mortem generator**: "this returned 0x — the three most likely
   causes," forced to be specific to this deal, not generic.
3. **"What would have to be true"** (Roger Martin): decompose the ≥10x case
   into conditions; classify each as evidenced / plausible / heroic.

### Stage 5 — Mechanical synthesis
- Scorecard with **pre-committed weights** (starting point, tunable):
  market/business 30 · team 30 · product/moat 15 · traction 10 ·
  competition 10 · deal/price 5. (Bill Payne scorecard doctrine puts
  team ≥ product explicitly; §2.4 argues market/business parity with team.)
- **Base-rate-anchored probability estimates**: P(<1x), P(≥10x) stated
  explicitly, anchored to the §2.1 priors and adjusted with reasons.
- Two headline verdicts, per §2.1: **Predictably-bad score** (kill-list) and
  **Outlier thesis strength** (evidenced conditions for the tail case).
- Partner scores entered independently before any discussion; system shows
  the spread, not just the mean (disagreement is information).

### Stage 6 — Tiered memo
Page 1 (the synced report Casey asked for): thesis in 2–3 sentences ·
scorecard + probability estimates · what-would-have-to-be-true table ·
top 3 risks · red-team's best pass case in one paragraph · recommendation.
Depth sections follow the consensus memo architecture (problem, product,
market/why-now, traction with cohort detail, competition, team, model,
deal terms, risks & mitigations, open questions & diligence plan) —
the same skeleton Bessemer/Sequoia memos use.

### Stage 7 — Forecast log (the compounding asset)
Every memo commits: P(<1x), P(≥10x), predicted next-round-within-24-months,
the top pre-mortem cause, and — for passes — the pass reason. Scored against
outcomes on a rolling basis; calibration dashboard (Brier scores by partner,
by sector, by score band); anti-portfolio review annually. This is the only
mechanism by which the methodology becomes *provably* good rather than
plausibly good.

## 4. Division of labor

**System:** screening, grounding/verification, benchmark comparisons,
red-team, consistency of structure, memory (base rates, forecast log).
**Humans:** reference calls (behavioral work-samples: "tell me about a
specific time…"), term negotiation, the final call — with scores committed
before discussion. The Michigan result (§2.2) pressures even this split at
the screening stage; the forecast log will tell us where the line belongs
for our book.

## 5. Build roadmap

- **v1 (weeks):** memo generator — intake w/ provenance tags, shared spine,
  structured founder rubric, red-team + pre-mortem, page-1 synthesis,
  scorecard with fixed weights. Manual sector selection.
- **v2:** sector overlays with benchmark tables; competition agent w/ live
  search; deal/valuation module with ownership + reserves math.
- **v3:** forecast log + calibration dashboard; anti-portfolio tracker;
  weight tuning from accumulated outcomes (expect years, not months, for
  significance — say so in every report until then).

## 6. Honesty box

- Almost all founder-personality evidence is **correlational**, on
  VC-visible survivor samples. The classifier accuracies (82.5%) do not
  transfer to our deal flow at face value.
- Rebel Fund's 65% IRR and ghSMART's 90% hit rate are **self-published /
  vendor-reported**, not peer-reviewed. Treated as existence proofs only.
- The LLM-vs-human screening results are new (2025–2026), on observable
  signals, and screening ≠ allocation. Do not extrapolate to "the model
  should size checks."
- VC return persistence is substantially **deal access, not judgment**
  (Nanda-Samila-Sorenson: early lucky wins → better deal flow). This
  system improves judgment and error rates; it does not manufacture access.
- Nothing here is modeled on our own book yet — the forecast log (§3 stage
  7) exists precisely because none of these priors are proven on our data.
