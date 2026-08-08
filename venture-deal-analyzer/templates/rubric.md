# Deal scoring rubric — v1 (fixed instrument)

Every scorer receives: the grounded fact pack (provenance-tagged), the sector
overlay, and this rubric. Scores are integers 1–5 per dimension, anchored
below. Scorers work independently and must not see other scores. Weights are
pre-committed and may only change between deals, never during one.

Weights: market/business 30 · team 30 · product/moat 15 · traction 10 ·
competition 10 · deal/price 5.

## Dimensions and anchors

### 1. Market & why-now (weight 30)
- 1: No falsifiable why-now; static or shrinking market; top-down TAM only.
- 3: Real market with plausible-but-unproven inflection; bottom-up sizing
  possible but thin; timing risk material.
- 5: Named enabling inflection with evidence the cost/behavior curve crossed;
  bottom-up demand build; market expands if price/performance improves 5–10x
  (elasticity); favorable industry-vintage cohort.

### 2. Team (weight 30)
Score execution evidence, not charisma. Inputs: track record (prior
successful exit ≈ +9pp base), structured evidence of persistence/execution,
technical+commercial composition, equity/role clarity, replaceability risk.
- 1: Solo non-technical founder in deep tech; unresolved roles; no shipping
  history; king-over-rich signals.
- 3: Competent team, first-timers, some execution evidence; gaps in
  commercial or technical leadership.
- 5: Complementary team with shipped-at-scale evidence, domain-specific
  execution history, clean role/equity structure, hiring magnetism.

### 3. Product & moat trajectory (weight 15)
At seed, score counter-positioning + cornered resource + the credible
sequence to scale/network/switching power — not today's moat.
- 1: Feature-level differentiation; incumbent's rational response kills it.
- 3: Real technical edge; moat sequence plausible but unproven.
- 5: Cornered resource (IP/exclusive process/data) + incumbent response is
  self-harming + compounding sequence already visible.

### 4. Traction vs sector benchmarks (weight 10)
Use the sector overlay's gates. Provenance matters: verified > claimed.
- 1: Pre-everything, or claimed metrics that fail verification.
- 3: At-benchmark for stage per overlay; some independent verification.
- 5: Above-benchmark on verified data; paid pilots/offtakes (deep tech) or
  flattening cohorts (consumer) or elite efficiency (SaaS).

### 5. Competition — three rings (weight 10)
- 1: Crowded with no defensible wedge, or "no competitors" (= no market or
  no diligence).
- 3: Identifiable wedge; incumbent response expected within base-rate ~2yr
  window; edge may or may not compound in time.
- 5: Wedge compounds faster than the response window; direct competitors
  structurally disadvantaged; crowdedness validates demand.

### 6. Deal & price (weight 5)
At seed: ownership/dilution math, round quality, fee drag. Entry multiple
discipline switches on at Series B+.
- 1: Ownership too small to matter at fund level even in the tail case;
  heavy fee/structure drag; weak syndicate.
- 3: Standard terms; adequate ownership; fee drag noted and modeled.
- 5: Clean terms, strong syndicate with reserves to next gate, ownership
  sufficient for tail case to return the book.

## Required non-score outputs (every scorer)
- P(raises next priced round ≤ 24 months) — %
- P(returns < 1x) — % (base rate ~65%)
- P(returns ≥ 10x) — % (base rate ~4%)
- One-sentence strongest reason to pass.
- One-sentence strongest reason the tail case is real.

## Aggregation
Median per dimension across scorers; IQR reported next to every median;
IQR > 1 point on any dimension = rubric ambiguity flag (fix the rubric or
the fact pack, then re-run). Weighted total = Σ(weight × median)/100.
Verdicts derive from the two-sided framing:
- Kill-list score: driven by dimensions 1, 4, 5 failures on verified data.
- Outlier thesis: requires ≥1 dimension at 5 with the WWHTBT conditions
  graded (evidenced / plausible / heroic).
