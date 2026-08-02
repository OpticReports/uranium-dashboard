# METHODOLOGY_RESEARCH.md — Quant methods for the EWM exit-timing cohort model

Research memo (2026-08-02), commissioned alongside the report-v6 cohort import
(`treasury-canary/backend/app/ewm/cohort_v6.json`). Scope: data-backed
methodologies for structuring and robustifying a scenario-cohort exit-timing
model for a ~$200M sale, Q4'26–Q2'27+ window. Numbers below use the report-v6
midpoints where a concrete example helps: Q1'27 scenario values
[205, 196, 180, 161, 153.5], Q2'27 [210, 199, 176.5, 155, 146.5] ($M),
weights [.30, .35, .25, .07, .03].

---

## (a) Real-options / optimal-stopping framing of sale timing

The sell decision is a classic optimal-stopping problem: at each decision
epoch t, sell if the immediate value S(t) exceeds the continuation value

```
C(t) = E_P[ max_{m > t feasible} EV(m) | info_t ]  −  carry/process costs
sell at t* = inf { t : S(t) ≥ C(t) }
```

solved in continuous time via the HJB equation with a threshold ("free
boundary") policy — see the [optimal exit strategies literature](https://www.sciencedirect.com/science/article/pii/S0022247X14011512)
and [threshold-strategy treatments](https://arxiv.org/pdf/1511.00468). The
canonical waiting condition ([good-timing / optimal stopping economics](https://www.sciencedirect.com/science/article/abs/pii/S0165188911001813)):
**waiting is optimal only while the expected return from delay — drift in
value plus the change in option premium — exceeds the discount rate.**
Formally, hold while `μ_V + Θ_option > r + λ·L`, where λ is a hazard of a
jump-to-worse (process stall, regime break) and L its loss.

Applied to the EWM cohort, every term argues the option value of waiting is
small-to-negative in the current state:

1. **Drift μ_V is negative under the probability mass.** Q1→Q2 midpoint
   deltas are [+5, +3, −3.5, −6, −7]; weighted drift ≈ **−$1.0M/quarter is
   wrong-signed only in dove rows**, and the hawk rows carry the mass of the
   variance. (Interestingly, the *pure* weighted EV slightly favors Q2 —
   see §(e) — which is exactly why stall hazard and breakeven analysis, not
   point EV, should carry the decision.)
2. **The hazard term λ·L is large:** 25–35% stall odds in rows 3–4, plus the
   50bp-increment regime branch. [Early-termination risk provably pulls the
   optimal exercise earlier](https://arxiv.org/pdf/1601.03962).
3. **Information arrives discretely, not continuously.** The value of waiting
   is the value of observing Sept CPI / Sept 16 dot plot / Oct+Dec FOMC
   before committing ([information acquisition postpones exercise only when
   the signal is decision-relevant](https://www.realoptions.org/papers2003/hroche.pdf)).
   So model the problem as **discrete-event stopping**: decision epochs =
   information events, and quantify the value of waiting to event e as

```
VoW(e) = E[ max(S_after_e, C_after_e) ] − S_now   (≤ value of clairvoyance on e)
```

   If VoW(Sept dot plot) < CoD_delay(k weeks to that event), the "move left"
   posture is quantitatively justified, not just narratively. This gives the
   action cards a proper decision-theoretic backbone: **each "accelerate"
   card should be a statement that VoW < CoD for the next event.**

Recommendation: do NOT build a full HJB/lattice solver (five scenarios, two
info events — the tree is tiny). Build the explicit two-stage decision tree
(act now vs wait-for-event, then act) on top of the cohort table; it is exact
for this structure and auditable.

## (b) Scenario-cohort construction best practice

- **Scenario count: 4–6 is the evidence-backed sweet spot.** The
  intuitive-logics scenario literature converges on 3–5 distinct scenarios;
  more overloads decision-makers and manufactures spurious resolution
  ([enhancing the scenario method](https://durham-repository.worktribe.com/OutputFile/1557182),
  [augmented intuitive logics](https://www.sciencedirect.com/science/article/pii/S0169207016300152)).
  The report's 5 cumulative-hike rows are well chosen because they are
  **mutually exclusive, collectively exhaustive along a single driver**
  (the rate path) — the property that makes probability weighting legitimate
  at all. Resist adding orthogonal scenario axes (growth × rates × …):
  handle secondary drivers as within-scenario ranges or tornado bars.
- **Market-implied where identified, elicited where not.** CME futures
  identify P(0–2 hikes) tightly; SOFR options at hike-3/4 strikes are thin
  (SPEC_AMENDMENTS §1 is right). Best practice is a hybrid: market-implied
  probabilities for the identified region, structured elicitation for the
  tail, with the boundary explicitly tagged. For elicitation, [Cooke's
  classical model](https://www.journals.uchicago.edu/doi/full/10.1093/reep/rex022)
  scores experts on calibration questions and performance-weights them —
  overkill for one operator, but its core lesson ports: **record every tail
  probability with its basis (priced / judged) and score them after each
  FOMC.** Tetlock's forecasting-tournament results say unaided expert point
  probabilities are barely informative but *calibratable with feedback*.
- **Avoid false precision.** [Soll & Klayman-style decomposition](https://pmaconsultants.com/publication/RISK-3824_Calibration-Assessments-Validation-of-Subjective-Probabilities-and-Impact-Ranges-in-Risk-Analysis.pdf)
  shows eliciting low and high bounds separately widens intervals and cuts
  overprecision — the report's cell *ranges* ($8–22M wide, hawk rows widest)
  are methodologically better than the seed's point values + flat 6% noise.
  Preserve ranges end-to-end; round displayed probabilities to 5pp; never
  print an EV without its band.

## (c) Calibration data: middle-market multiples vs rate cycles

What is empirically known, with numbers:

- **GF Data ($10–250M/$500M TEV, PE-sponsored):** average ~**7.4x** EBITDA in
  2022; **Q4 2022 dropped to 6.8x from 8.2x in Q3** as financing costs bit;
  first nine months of 2023 ~**7.3x**; senior debt pricing on $10–250M deals
  ran **10.4%** at end-2023
  ([Capstone Q4-2022 capital markets update](https://www.capstonepartners.com/wp-content/uploads/2023/04/Capstone-Partners-Capital-Markets-Update-Q4-2022.pdf),
  [GF Data Q3-2023 rebound](https://middlemarketgrowth.org/conversations-growthtv-gf-data-q3-2023/),
  [GF Data](https://gfdata.com/mindscapital/)). The quarterly series is
  noisy (n ≈ 40–80 deals/quarter) — the 8.2→6.8 single-quarter swing is
  part signal, part sampling error, which is exactly why the spec's damped
  recalibration (amendment §3 shrinkage) is right.
- **PitchBook / sponsored LBO data:** $10–500M TEV purchase multiples
  **7.6x (2021–22) → ~7.2x (2023)**, i.e. ~0.4 turns off the peak across a
  ~525bp hike cycle at the tier level; size premium is steep — 2024 medians
  **15.5x (≥$1B) vs 12.8x (<$1B) vs <10x (<$100M)**
  ([PitchBook buyout multiples](https://pitchbook.com/news/articles/us-buyout-multiples-steady-as-they-go),
  [middle-market multiple arbitrage](https://pitchbook.com/news/articles/middle-market-pe-offers-fertile-ground-for-multiple-arbitrage)).
  A commonly cited rule of thumb from this cycle: **~250bp of fed funds ≈
  ~25% multiple compression for leveraged buyers**
  ([lower-middle-market statistics](https://capitalpad.com/lower-middle-market-private-equity-statistics/))
  — i.e. roughly **0.15–0.35 turns per 50bp** depending on leverage, which
  brackets the report's debt-capacity anchor (~quarter-turn ≈ $10M per 50bp)
  and the seed's hawk shape (−0.15x/q). The report-v6 Q1→Q2 hawk decay
  (~3x the seed's) is at the aggressive-but-defensible end, justified by its
  revenue-multiple-duration argument (2022–23: revenue-priced deals −60%+
  peak-to-trough vs ~20% for mature-EBITDA deals).
- **DealStats (BVR)** covers smaller private transactions (median deal sizes
  well below this tier) — useful as a *floor/stress* reference and for
  sector spreads, not for level calibration of a $200M process.
- **The bridge problem is the binding constraint** (spec §8, unresolved):
  tier averages (GF ~7x, Capstone ~9.8x) sit far below the deal-specific
  13–15x (or the report's 1.9x revenue). Empirical warrant: the PitchBook
  size gradient above plus growth/quality premia routinely explain 5–8
  turns. Until the size/sector/growth bridge regression exists, tier data
  may only steer **deltas** (damped), never levels — this memo found nothing
  that overturns that rule, and the 2026 private-credit divergence
  (BDC-vs-BB corr −0.10 in year 3, SPEC_AMENDMENTS §4) reinforces that
  tier-specific financing conditions, not headline HY, drive this tier.

## (d) Uncertainty presentation for decision dashboards

Evidence, ranked by strength:

- **Quantile dotplots and CDFs measurably improve decisions.** The
  strongest applied result in the field: bus-catching decisions improved
  (and variance fell) with quantile dotplots vs point estimates or
  intervals ([Fernandes, Walls, Munson, Hullman & Kay, CHI'18](https://www.researchgate.net/publication/322329508_Uncertainty_Displays_Using_Quantile_Dotplots_or_CDFs_Improve_Transit_Decision-Making)).
  Discrete-outcome displays beat continuous bands because people count.
- **Cones/fans are systematically misread as containment + safety.** The
  hurricane cone-of-uncertainty literature shows users read "inside the
  cone = at risk, outside = safe" when the cone is a ~60–70% containment
  band ([Scientific American](https://www.scientificamerican.com/article/how-to-understand-hurricane-forecasts-and-the-cone-of-uncertainty/),
  [AMS animated-trajectory study](https://journals.ametsoc.org/view/journals/wcas/15/2/WCAS-D-21-0173.1.xml)).
  Central-bank fan charts communicate but were not designed for choice
  tasks ([BIS fan-chart review](https://www.bis.org/ifc/events/ifc_8thconf/ifc_8thconf_62pap.pdf)).
- **Showing the mean biases judgments** toward it, slightly degrading
  magnitude estimation ([Kale et al., effect-size judgments](https://mucollective.northwestern.edu/files/2020%20-%20Kale,%20Visual%20Reasoning%20Strategies%20for%20Effect%20Size%20Judgements.pdf));
  [HOPs (animated draws) improve probability estimation](https://users.eecs.northwestern.edu/~jhullman/hops_jobs_pfs.pdf)
  but are poor for an always-on monitoring surface.
- **Tornado diagrams** are the standard, well-understood display for *which
  input moves the answer* ([tornado diagram overview](https://en.wikipedia.org/wiki/Tornado_diagram)) —
  right tool for parameter sensitivity (EBITDA g, tail weight, stall odds),
  wrong tool for the headline value display.
- General reviews ([Padilla, Kay & Hullman](http://space.ucmerced.edu/Downloads/publications/Uncertainty_Visualization_Padilla_Kay_Hullman_2022.pdf),
  [Hullman's evaluation survey](https://users.eecs.northwestern.edu/~jhullman/uncertainty_vis_eval.pdf))
  caution that no single encoding wins everywhere; what consistently helps
  is **explicit probabilities attached to discrete outcomes** — which is
  precisely what a scenario table does.

Net: for THIS product, **table-first** (discrete scenarios × discrete close
windows, probabilities printed in the row header) is the evidence-aligned
choice; keep the EV strip's fan as a secondary trend view with its bands
labeled ("10/90 of scenario spread, not of the world"), and put a tornado
behind a "what moves this" tab.

## (e) Robustness techniques applicable here

1. **Dirichlet probability-weight ensemble** (mirrors the canary's
   approach; standard in [probabilistic sensitivity analysis for
   multi-branch decision trees](https://pubmed.ncbi.nlm.nih.gov/12926584/)):
   draw `p ~ Dirichlet(κ·p̂)` with concentration κ = effective sample size
   of your belief in p̂. Split κ by identification: the futures-identified
   region deserves high κ, the tail low — implement as
   `α = [κ_hi·.30, κ_hi·.35, κ_hi·.25, κ_lo·.07, κ_lo·.03]` (e.g. κ_hi≈60,
   κ_lo≈15), then report the 10–90 band of EV(m) across draws as the
   **weight-uncertainty band**, layered distinctly from within-scenario
   value ranges. This is [robust-Bayes local sensitivity](https://en.wikipedia.org/wiki/Robust_Bayesian_analysis)
   made operational in ~10 lines.
2. **Breakeven ("flip") analysis — the highest-value single addition.**
   Because EV is linear in p, every decision flip has a closed form. Worked
   example on report-v6 midpoints: per-scenario Q1−Q2 deltas are
   [−5, −3, +3.5, +6, +7] → base-weight ΔEV = **−$1.05M (Q2 ahead on pure
   EV)**. Flip conditions: moving ~**16pp** of weight from scenario-1 to
   scenario-2 flips it, or ~**9.5pp** from scenario-0 to scenario-3; and a
   stall-adjusted Q2 (extra hazard h on rows 3–4 value ≈ −6.5% per the
   stall model) flips to Q1-preferred at **h ≳ 7pp of additional stall
   probability** — i.e. the Q1-vs-Q2 call rides on stall hazard and tail
   drift, not on the headline EV. Ship the general form:
   `p*_s = smallest perturbation of p (in total-variation) that changes
   argmax_m EV(m)` and print it in scenario-weight units ("scenario-2 needs
   ≥41% to make Q2 the wrong window").
3. **Scenario-count stress:** recompute the decision under (i) tail rows
   3+4 merged, (ii) row 2 split into 2-hikes-benign / 2-hikes-tight halves
   of its $170–190M range. If the argmax month is stable under both, the
   5-row granularity is adequate; if not, the answer is scenario-structure
   noise and must be flagged. (Cheap: pure table arithmetic.)
4. **Within-cell range propagation:** carry the report's [lo, hi] per cell;
   compute EV_lo/EV_hi by aligning all cells pessimistic/optimistic
   (perfect-correlation bound — conservative and honest given one common
   driver) rather than adding independent noise.
5. **Regime-branch stress, not a sixth scenario:** the 50bp-increment branch
   ($145–170M, process at risk) is a different *model*, not a low-p row.
   Display as a labeled stress footnote; folding it into weights would
   corrupt both the weights and the band.
6. **Hysteresis on all robustness-derived flags** (per amendment §6d) so
   breakeven proximity ("within 5pp of a flip") doesn't flap daily.

## (f) Recommended table-first UI structure

Mirror the report's readable cohort table as the primary surface:

```
                         │ close end Q1'27      │ close end Q2'27      │ later (interp.)
─────────────────────────┼──────────────────────┼──────────────────────┼────────────────
0 hikes      p≈30%       │ $205M  (200–210)     │ $210M  (205–215)     │ …
1 hike ★     p≈35%       │ $196M  (192–200) ★   │ $199M  (194–204)     │ …
2 hikes      p≈25%       │ $180M  (170–190)     │ $176M  (165–188)     │ …
3 hikes      p≈7%  ⚠stall│ $161M  (150–172)     │ $155M  (142–168)     │ …
4 hikes      p≈3%  ⚠stall│ $153M  (145–162)     │ $146M  (135–158)     │ …
─────────────────────────┼──────────────────────┼──────────────────────┼────────────────
Weighted EV              │ $191M  (186–193)     │ $190M  (…)           │ …
Weight-uncertainty band  │ ±$X (Dirichlet 10–90)│ …                    │
BREAKEVEN                │ Q1 vs Q2 flips if scenario-2 ≥ 41% · or stall hazard ≥ +7pp
```

- **Rows = scenarios**, header cell carries probability (nearest 5pp) with a
  priced/judged tag; hawk rows carry the ⚠ 25–35% stall chip. Star the
  modal cell exactly as the report does — it is the single most-read cell.
- **Columns = feasible close windows.** Infeasible windows struck-through
  and uncolored (existing feasibility-gate rule); columns beyond the
  report's two anchors visibly tagged "interpolated" (lag-honest UI).
- **Cells = central value + range**, range typography subordinate to the
  central value; color only on the weighted-EV row (band colors), never on
  raw scenario cells (they are conditionals, not risks).
- **Bottom block = weighted EV row, Dirichlet band row, breakeven row.**
  The breakeven row is the decision surface: it converts the whole table
  into one sentence an operator can argue with.
- Secondary tabs: EV strip/fan over months (trend), tornado (drivers:
  EBITDA g, tail weight, stall hazard, hawk decay slope), and the
  cost-of-delay curve with its VoW-vs-CoD annotation at the next info event
  (Sept CPI, Sept 16 dot plot, Oct FOMC).
- Keep the epistemic banner; add one line: "cells are conditional values —
  the probabilities are the model."

## Implementation shortlist (ranked by decision value per unit effort)

1. **Breakeven row** (§e2): closed-form, ~30 lines, converts the table into
   a decision instrument; also powers a "within 5pp of flip" trigger for the
   action-card layer.
2. **Report-range propagation + stall-adjusted window comparison** (§e4 +
   §a1): the Q1-vs-Q2 call currently flips on stall hazard (~7pp) — make
   that explicit; drop the flat 6% exec-noise in favor of the report's
   hawk-skewed cell ranges.
3. **Dirichlet weight ensemble with split concentration** (§e1): ~10 lines,
   gives the honest weight-uncertainty band and matches the canary's house
   style.
4. **Table-first UI with modal star, stall chips, breakeven row** (§f):
   highest-leverage presentation change; evidence favors discrete
   probabilistic tables over fans for choice tasks.
5. **Discrete-event VoW vs CoD annotation** (§a3): small two-stage tree on
   the cohort; makes "accelerate" cards quantitatively accountable.
6. **Scenario-count stress** (§e3): trivial arithmetic, run in CI next to
   the G1–G4 gates.
7. **GF/PitchBook delta recalibration per amendment §3** (already specced;
   this memo's numbers — 8.2→6.8x single-quarter swings on n≈40–80 —
   confirm the shrinkage cap is necessary).

Sources: [Capstone Q4-2022 update](https://www.capstonepartners.com/wp-content/uploads/2023/04/Capstone-Partners-Capital-Markets-Update-Q4-2022.pdf) · [GF Data Q3-2023](https://middlemarketgrowth.org/conversations-growthtv-gf-data-q3-2023/) · [GF Data](https://gfdata.com/mindscapital/) · [PitchBook buyout multiples](https://pitchbook.com/news/articles/us-buyout-multiples-steady-as-they-go) · [PitchBook middle-market arbitrage](https://pitchbook.com/news/articles/middle-market-pe-offers-fertile-ground-for-multiple-arbitrage) · [CapitalPad LMM statistics](https://capitalpad.com/lower-middle-market-private-equity-statistics/) · [Optimal exit strategies](https://www.sciencedirect.com/science/article/pii/S0022247X14011512) · [Good timing: economics of optimal stopping](https://www.sciencedirect.com/science/article/abs/pii/S0165188911001813) · [Roche, value of waiting](https://www.realoptions.org/papers2003/hroche.pdf) · [Startup timing options w/ termination risk](https://arxiv.org/pdf/1601.03962) · [Threshold strategies](https://arxiv.org/pdf/1511.00468) · [Cooke classical model review](https://www.journals.uchicago.edu/doi/full/10.1093/reep/rex022) · [Scenario-method enhancement](https://durham-repository.worktribe.com/OutputFile/1557182) · [Augmented intuitive logics](https://www.sciencedirect.com/science/article/pii/S0169207016300152) · [Calibration/overprecision validation](https://pmaconsultants.com/publication/RISK-3824_Calibration-Assessments-Validation-of-Subjective-Probabilities-and-Impact-Ranges-in-Risk-Analysis.pdf) · [Quantile dotplots/CDFs transit study](https://www.researchgate.net/publication/322329508_Uncertainty_Displays_Using_Quantile_Dotplots_or_CDFs_Improve_Transit_Decision-Making) · [HOPs](https://users.eecs.northwestern.edu/~jhullman/hops_jobs_pfs.pdf) · [Padilla/Kay/Hullman uncertainty-vis chapter](http://space.ucmerced.edu/Downloads/publications/Uncertainty_Visualization_Padilla_Kay_Hullman_2022.pdf) · [Uncertainty-vis evaluation survey](https://users.eecs.northwestern.edu/~jhullman/uncertainty_vis_eval.pdf) · [Cone-of-uncertainty misinterpretation](https://www.scientificamerican.com/article/how-to-understand-hurricane-forecasts-and-the-cone-of-uncertainty/) · [AMS animated trajectories](https://journals.ametsoc.org/view/journals/wcas/15/2/WCAS-D-21-0173.1.xml) · [BIS fan charts](https://www.bis.org/ifc/events/ifc_8thconf/ifc_8thconf_62pap.pdf) · [Kale et al. effect-size judgments](https://mucollective.northwestern.edu/files/2020%20-%20Kale,%20Visual%20Reasoning%20Strategies%20for%20Effect%20Size%20Judgements.pdf) · [Tornado diagram](https://en.wikipedia.org/wiki/Tornado_diagram) · [Dirichlet PSA for decision trees](https://pubmed.ncbi.nlm.nih.gov/12926584/) · [Robust Bayesian analysis](https://en.wikipedia.org/wiki/Robust_Bayesian_analysis)
