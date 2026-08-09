# Counter-agent review of rubric v1 (2026-08-08)

Instrument-level red team, run at the LP's request after two scored deals.
This review drove the v1 → v1.1 changes. Verbatim findings:

## 1. Weights — evidence supports directions, never the numbers

DESIGN §2.4 supports "market ≥ team" — a direction. Nothing supports 30 vs
25 vs 35; the only numeric ancestor is Bill Payne doctrine, cited as
doctrine. The rubric contradicts its own evidence base twice:

- **Timing is buried.** §2.7 calls timing "the strongest under-weighted
  predictor" (Gross: 42% of variance vs team's 32%; GKLS vintage effects
  52% vs 18%). The rubric folds it inside market's 30. If the evidence
  means anything numerically, timing alone deserves near-team weight.
- **Stage-dependence is admitted inside anchors but denied in weights.**
  Anchor 6 says entry-multiple discipline "switches on at Series B+"
  (Othman: price is second-order at seed only), yet deal/price stays 5%
  at every stage, and traction stays 10% whether the company is
  pre-revenue seed or a Series B where traction is the main signal.
  Scoring a seed-ish SPV and a Series B SPV with one fixed vector is
  indefensible — the observed Quaise weight-sensitivity (2.67–3.20) vs
  DexMat stability (3.00–3.35) is exactly the symptom.
- Weakest mapping: product/moat 15 rests on the NFX 70% figure the honesty
  box itself discounts.

## 2. Anchors — 2-point honest disagreements and smuggled dimensions

- Market 3↔5: "plausible-but-unproven inflection" vs "curve crossed" —
  two honest scorers split 3/5 on Quaise.
- Team 3↔5: no ruling on repeat-academic spinout founders; "hiring
  magnetism" unmeasurable.
- **Traction is two dimensions**: demand evidence and delivery evidence.
  Quaise = 5 on demand, 1 on delivery, "nets to 3" — identical to a
  genuinely at-benchmark company. Averaging incommensurables destroys
  exactly the information the outlier-thesis verdict needs.
- Deal/price is also two: price/terms and syndicate quality. Competition
  anchor 1 names two opposite states (crowded-no-wedge / "no
  competitors") — sound kill logic, ambiguous score.

## 3. Aggregation — wrong functional form

Dawes 1979: improper linear models are weight-insensitive; the 30/30/15/
10/10/5 precision is theater. The deeper failure: Σ(weight×median) is a
compensatory rule, but the decision structure is **disjunctive kill /
conjunctive tail** — one fatal flaw kills; one evidenced 5 carries the
outlier thesis. Quaise proved it: deal/price = 1 WAS the decision yet
moved the total by 0.10. A 1 whose anchor reads "ownership too small to
matter even in the tail case" is a mathematical kill at any other scores
— it must be a **gate**, not a 5% term. Convert to gates: (a) verification
failure on material claimed metrics; (b) ownership/fee-stack cannot
return the vehicle in the evidenced tail case; (c) years-to-liquidity
exceeds vehicle horizon. Keep the median/IQR machinery — the Σ across
dimensions is what's wrong. Demote the weighted total to tiebreaker;
headline the kill-list and outlier verdicts.

## 4. Missing dimensions

- Timing/vintage as its own axis (the evidence base's strongest predictor).
- Founder-market fit (GKLS: serial persistence is industry-year choice;
  v1 scores generic team).
- Syndicate/sponsor quality for SPVs (fee stacking, information rights,
  sponsor track record) — access drives persistence
  (Nanda-Samila-Sorenson).
- Track-record-priced-in check — nowhere scored.

## 5. v1.1 proposal (adopted, see rubric.md)

Gates first (verification · vehicle-returning ownership · fund-life fit);
seed and B+ weight vectors with timing promoted and traction/deal split;
sensitivity-band reporting rule; weighted total demoted to tiebreaker.
**Change now on argument**: structural items above. **Wait for ledger**:
weight tuning beyond coarse vectors, stage-modifier magnitudes, anchor
recalibration from IQR flags. Stamp rubric_version on every ledger entry.
