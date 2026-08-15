# Hurdle ledger — venture risk vs execution risk (DRAFT v0.9)

STATUS: DRAFT pending counter-agent verification of the research brief
(2026-08-09). Do not use for a shipped verdict until this header is
replaced with the verification verdict. Origin: Casey's proposal to
decompose deal risk into venture vs execution hurdles for more granular
probability analysis.

## Definitions (from the literature, not invented)

- **VENTURE RISK (exogenous):** does the thing work and does the world
  cooperate — science/tech breakthrough, market existence, regulatory
  and strategic-partner events, financing-window conditions. Lineage:
  Sahlman's Opportunity/Context axes (HBS 897-101); Kerr-Nanda-
  Rhodes-Kropf "entrepreneurship as experimentation" (JEP 2014).
  Properties: team can barely move it; resolves at discrete dated
  events; ABSORBING on failure (no retry — the physics said no).
- **EXECUTION RISK (endogenous):** can THIS organization convert a
  working thing into a business — key-talent assembly, operations,
  FOAK plant/ramp, commercial delivery, cash-bridge management.
  Lineage: Sahlman's People axis; Gompers staged-financing (JF 1995);
  Kaplan-Sensoy-Strömberg (JF 2009: business lines stable, managers
  replaceable). Properties: team-quality-sensitive; mostly continuous
  (late/over-budget >> never); PARTIALLY RECOVERABLE at a cost
  (jockeys are replaceable); CORRELATED across hurdles via the
  organizational common cause.
- Formal framing per verification (see verdict when appended): both
  hurdle families are largely epistemic; the operative distinction is
  CONTROLLABILITY and CORRELATION STRUCTURE, not aleatory-vs-epistemic.

## The template industry

Drug development prices every asset as a product of named conditional
hurdles with published base rates (BIO/Informa 2021, 12,728 phase
transitions: I→II 52.0%, II→III 28.9%, III→filing 57.8%,
filing→approval 90.6%, overall 7.9%). The hurdle ledger copies that
architecture for deep tech; where an anchor is an ANALOGY (drug PoS
applied outside pharma, reliability β outside hardware) it is labeled
as a modeling assumption, never as a measured base rate.

## Hurdle taxonomy and base-rate anchors

| Type | Hurdle class | Anchor | Source |
|---|---|---|---|
| V1 | Science/tech works at next scale | grade by TRL; pre-TRL4 ≈ ~50% per major step, TRL4-6 ≈ 30-60% (phase-transition ANALOGY) | BIO 2021; GAO TRL |
| V2 | Market/demand materializes | ~35-42% of startup deaths = no market need; 55% overall VC failure | CB Insights; KNR-K 2014 |
| V3 | Regulatory / strategic-partner event | late formal gates ~90% (analogy); policy markets graded down | BIO 2021 |
| E1 | FOAK plant / production ramp | expect ~2x cost, 50-75% of nameplate yr-1; 65% of megaprojects miss; overrun by project type (solar +1% … nuclear +120%) | RAND 1981; Merrow 2011; Flyvbjerg |
| E2 | Key-talent assembly | 40-50% failure per critical external senior hire (18mo) | Heidrick; DDI 2021 |
| E3 | Ops scale-up + cash bridge | per-round survival (staging); protracted-development is the modal hardware death | Gompers 1995; hardware data |

## Structural rules

1. Every EV-tree branch decomposes into named hurdles, each: type
   (V/E), difficulty grade (evidenced/plausible/heroic — WWHTBT
   grades), reference class + anchor, deal-specific adjustment WITH
   justification, resolves-by date.
2. **Combination rule:** V hurdles on distinct mechanisms multiply as
   ~independent. E hurdles DO NOT naively multiply — they share an
   organizational common cause (reliability β analogy). Interpolate
   between independent product (worst case for many hurdles) and the
   minimum single hurdle (perfect correlation) with weight set by the
   team score: P(all E) = (1-w)·Πp_i + w·min(p_i), w = (team-1)/4.
   This gives team's 30-weight a mechanistic job: team quality IS the
   correlation across execution hurdles.
3. V failures are absorbing; E failures cost time and money first —
   model E misses as delay/dilution before death (Merrow: late and
   over-budget, not never).
4. Every hurdle becomes a DATED ledger forecast. This is the accuracy
   engine: hurdle forecasts resolve in months, exits in a decade —
   hurdle-level Brier scores calibrate the panel's V-judgment and
   E-judgment SEPARATELY, years before any exit resolves.
5. Diligence targeting: the binding hurdle's type dictates the work.
   Binding-V → date-driven events, independent technical review; no
   team meeting moves it. Binding-E → team/org diligence, site visits,
   reference calls.

## Worked classification (current book)

- **DexMat = execution-risk deal.** V hurdles modest (additive
  transfer; qualification chemistry); binding hurdles are E1 (FOAK
  30t→3kt scale-up — where Nanocomp died; RAND/Merrow anchors apply
  directly) and E3 (qualification grind + cash bridge). Site visit
  diligences exactly the binding risk. Recoverability real: managers
  replaceable, ramps late-not-never.
- **Quaise = venture-risk deal.** Binding hurdles V1 (physics at
  depth; 400-500°C completions) with an absorbing failure mode;
  E hurdles barely matter until V1 resolves. No team diligence moves
  the answer; the Dec 2026 flow test does.
- Same weighted scores, opposite risk types — a distinction the W
  total cannot see and the EV tree only sees implicitly. The hurdle
  ledger makes it the headline.

## Limits

- Ulu Ventures precedent (Korver, Kauffman Fellows 2012) uses this
  architecture but published NO calibration — the structure is
  citable, claimed accuracy is not. Ours must earn accuracy through
  the ledger's hurdle-level Brier scores.
- β/correlation weight w is a modeling assumption pending our own
  calibration data; sensitivity on w must be reported when the E-side
  drives a verdict.
- Anchors marked ANALOGY are assumptions, honesty-box convention
  applies.
