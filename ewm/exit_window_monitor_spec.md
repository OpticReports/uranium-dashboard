# EXIT WINDOW MONITOR (EWM) — BUILD SPEC v1.0 (operator handoff, 2026-08-01)

Live dashboard for timing risk vs expected exit value on a ~$200M company
sale (target window Q4 2026 - Q2 2027+). Separate app on the optic domain;
React + FastAPI; consumes the Treasury Canary + rate-shock simulator as
services. Full verbatim spec retained by operator; this file captures the
build-governing content. Amendments in ewm/SPEC_AMENDMENTS.md.

## Outputs (always live)
1. Expected Exit Value strip: probability-weighted value by close month with
   10/90 bands (scenario-cohort model made live) + 7d drift.
2. Safety Windows timeline Sept'26-Dec'27, green/amber/red Window Score per
   month, FOMC/CPI markers, feasibility strike-through (months closer than
   process-stage lead time are un-choosable, not colored).
3. Prescriptive action cards, ranked, with EV-weighted rationale and a
   cost-of-delay curve ($/week vs best feasible month).
Persistent epistemic banner: ~5 rate cycles, quarterly-lagged deal data;
decision support, not advice.

## Model
- EV(m) = sum_s P_s(t) * V(s, m, EBITDA(t)); P_s live from futures
  (currently ~30/35/25/7/3 for 0-4 hikes) + dissent-cluster bump (param);
  V = cohort surface (multiples fixed per scenario, hike-3 cliff, value
  scales with EBITDA); GF Data quarterly recalibration damped 0.5x
  (anchor, NOT a live signal — 1-2q lag; headline M&A value EXCLUDED,
  tier-specific $100-250M volume only).
- FCI-X (daily z-composite): 0.30 BDC price/NAV, 0.25 BB OAS level+3m chg,
  0.15 MOVE, 0.15 PIK/non-accrual (quarterly, held), 0.15 shock-sim stress
  prob. Bands <-0.5 easy / -0.5..+0.75 normal / >+0.75 tight.
- DMHI (monthly): tier volume trend, damped GF multiple trend, survey close
  rate, paused-vs-died ratio. Stall = DELAY (+1-2q, -5..-8% value) with a
  small true-death tail — NOT binary failure (survey: 48.7% pause vs 13.2%
  die).
- Window Score(m) = w1*RateRisk(m) + w2*FCIX + w3*DMHI + w4*Canary +
  FeasibilityGate(m); event density inside signing-to-close gap extra-
  weighted. Green >=70 / Amber 45-70 / Red <45; calibrated so today
  reproduces: Q1'27 green-amber, Q2'27 amber, post-Q2 amber-red.
- Prescriptive rule table (editable): dissent cluster -> accelerate pre-Dec-
  FOMC; FCI-X tight -> committed-capital buyers/financing outs; P(2 hikes)
  >40% -> rate collar/earnout; EBITDA raise -> re-anchor ask (+$1M ~ +$13-15M);
  stress prob >25% -> Q1 hard deadline. Every card logs its trigger.

## Validation gates (merge-blocking)
G1 static reproduction (July-2026 frozen inputs): modal $194-203M Q1 close,
weighted EV $189-194M, Q1 green-amber. G2 2022 replay: windows red by Q1'22,
acceleration recommended Q4'21. G3 2019 placebo: green, no false-urgent
actions. G4 feasibility gating correct per stage; no card without logged
trigger. NO LOOK-AHEAD in replays (primary QA target).

## Counter-agent findings already incorporated (operator's §8)
GF quarterly = recalibration anchor only (lag-honest UI); sponsors NOT
excluded (dry powder support variable; sponsor-vs-strategic tilt dynamic off
FCI-X); tier-specific volume only; stall=delay not death; UNRESOLVED: GF
7.1-7.3x vs Capstone 9.8x vs deal-specific 13-15x — QA must build the
size/sector/growth premium bridge table before GF deltas recalibrate levels.

## Sacred (per operator): tier-specific deal data, lag-honest UI,
delay-not-death stall modeling, validation gates. Everything else amendable
with documented rationale.

## NOTE — seeded cohort surface
The authoritative V(s,m) table lives in "Rate Cycle & Exit Timing report v6"
(not available to this session). params.json seeds a surface from the spec's
own anchors: EBITDA 14.0 run-rate, scenario multiples [14.5, 14.0, 13.4,
11.8, 11.2] (hike-3 cliff), which reproduces modal 196-203 / weighted ~192.7
at Q1'27 under 30/35/25/7/3. Tagged source:"seeded-from-spec" — REPLACE with
the report table via /api/ewm/inputs when available.
