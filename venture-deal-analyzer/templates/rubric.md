# Deal scoring rubric — v1.1 (fixed instrument)

Version: **1.1** (2026-08-08). v1 in git history. Changes from v1 were
adopted on the strength of a counter-agent review of the instrument
itself (see `templates/rubric-review-v1.md`): gates added, traction and
deal split into their components, timing promoted to its own axis,
stage-dependent weight vectors, sensitivity-band reporting, and the
weighted total demoted from headline to tiebreaker. Weight *tuning*
beyond these coarse vectors waits for ledger outcomes (Dawes 1979:
improper linear models are weight-insensitive; precision now is theater).
Stamp `rubric_version` on every ledger entry.

## 0. GATES — evaluated first, pass/fail, before any scoring

A failed gate is a kill regardless of scores. Gates are disjunctive
because the downside decision is disjunctive: one fatal flaw kills.

- **G1 Verification**: a material sponsor/company metric remains false or
  misrepresented after diligence and query (basis-switching, invented
  counterparties, fabricated figures). Honest-error corrections and
  puffery resolved on questioning do not trip the gate; refusal or
  persistence does.
- **G2 Vehicle math**: ownership after fees/structure cannot plausibly
  return the vehicle even in the EVIDENCED tail case (anchor: "ownership
  too small to matter even in the tail" is a kill, not a 1/5).
- **G3 Horizon fit**: years-to-liquidity under base rates exceeds the
  vehicle's realistic horizon with no interim-exit path.
- **G4 (SPV only) Price visibility**: entry price/class/fees undisclosed
  after request ⇒ the deal is un-underwritable — verdict is automatically
  "conditional: pass until disclosed," never a buy.

## 1. Scored dimensions and stage weight vectors

Scores 1–5, anchored below. Two pre-committed vectors; pick by stage of
the round being priced (seed/A vs B+). No mid-deal changes.

| Dimension | Seed/A | Series B+ |
|---|---|---|
| Market size & elasticity | 20 | 15 |
| Timing / why-now (own axis) | 15 | 10 |
| Team & founder-market fit | 25 | 20 |
| Moat trajectory | 15 | 10 |
| Demand evidence | 10 | 20 |
| Delivery evidence | 10 | 10 |
| Deal price & terms | 0 (gate-only via G2/G4) | 10 |
| Syndicate & sponsor quality | 5 | 5 |

Rationale anchors (direction-level evidence, not number-level — stated
plainly): market≥team (Kaplan-Sensoy-Strömberg); timing as its own axis
(Gross 42%; GKLS vintage effects — the evidence base's strongest
under-weighted predictor); founder-market fit folded into team (GKLS:
serial persistence is industry-year choice); price scored only at B+
(Othman: second-order at seed); syndicate scored because access drives
persistence (Nanda-Samila-Sorenson).

## 2. Anchors

### Market size & elasticity
1: static/shrinking; top-down TAM only. 3: real market, bottom-up
possible but thin. 5: bottom-up build + demonstrated elasticity (5–10x
price/performance improvement expands usage).

### Timing / why-now
1: no falsifiable enabler; "why wasn't this built 5 years ago" has no
answer. 3: plausible inflection, evidence incomplete; OR enabler real but
the monetization window (who pays, when) likely opens after the vehicle's
horizon. 5: named enabler with dated evidence the cost/behavior curve
crossed, favorable industry-vintage cohort, window open now.

### Team & founder-market fit
Score execution evidence + fit of THIS team to THIS market's failure
modes. 1: no shipping history; roles unresolved; fit generic. 3:
competent, first-time-at-this-scale; partial fit; (explicit ruling:
academic-spinout founders with deep domain lineage but no industrial
scale-up score here, not higher, absent scale evidence). 5:
shipped-at-scale in this domain's hard part; prior outcome in the same
industry-year class; clean structure.
Pedigree earns capped credit: prior EXIT outcomes count; degrees and
brand-name employers alone do not (verified 2026-08-09: Rebel disclosure
— master's/PhD uncorrelated with success; Davenport — founder
backgrounds are systematically over-weighted relative to optimum).

### Moat trajectory
1: feature-level edge; incumbent's rational response kills it. 3: real
edge, sequence to durable power plausible but unproven. 5:
cornered resource/counter-positioning NOW + first compounding evidence.

### Demand evidence (split from v1 "traction")
Provenance-weighted willingness-to-pay. 1: none/claims fail checks. 3:
paying customers or signed conditional offtakes with named counterparties.
5: binding committed volumes/POs from named buyers, verified.

### Delivery evidence (split from v1 "traction")
Can they build/ship the thing the demand is for? 1: demonstrated scale
≥50x below required (record the gap multiple). 3: at-benchmark for stage
per sector overlay. 5: above-benchmark, independently verified.
**Report demand and delivery separately always; never average them.**

### Deal price & terms (B+ only; seed handled by gates)
1: >2x the last clean institutional mark, or structure that consumes the
tail. 3: at institutional mark, standard class, fees ≤2/20. 5: at/below
mark with rights.

### Syndicate & sponsor quality
1: no repeat institutional lead; sponsor opacity, stacked fees, urgency
mechanics. 3: credible lead + standard SPV. 5: top-decile repeat lead,
strategics with domain diligence, clean sponsor with track record.

## 3. Required non-score outputs (unchanged from v1)
P(next priced round ≤24mo), P(<1x net), P(≥10x net) — base-rate anchored
(~65% / ~4%); strongest pass reason; strongest tail reason.

## 4. Aggregation and reporting — v1.1 rules

1. **Gates first.** Any fail ⇒ verdict states the gate, scores become
   diagnostic only.
2. Median + IQR per dimension across 5 independent scorers (unchanged).
   IQR > 1 ⇒ ambiguity flag ⇒ fix rubric/fact pack, re-run.
3. **Headline verdicts are the kill-list and outlier-thesis calls**, not
   the total: kill-list = gates + fatal-flaw dimensions at 1 on verified
   data; outlier thesis = ≥1 dimension at 5 with WWHTBT conditions graded
   evidenced/plausible/heroic.
4. Weighted total = tiebreaker among gate-passers only. **Always report
   its sensitivity band**: [min, max] across {stage vector, unit weights,
   ±50% perturbation of each weight}. If the band crosses a decision
   threshold, the band is the verdict ("weight-sensitive — decide on
   gates and outlier thesis, not the total").
5. Panel vs red-team probability disagreements are logged, never averaged.

## 5. What must wait for data (do not change on argument alone)
Weight magnitudes beyond these coarse vectors; stage-modifier sizes;
anchor recalibration (driven by observed IQR flags); any claim that the
instrument predicts — that is the ledger's job (first resolutions
2028-08; Brier by rubric_version).
