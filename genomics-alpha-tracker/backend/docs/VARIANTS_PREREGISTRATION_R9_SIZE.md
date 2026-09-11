# R9 pre-registration — size-conditional scoring weights (Casey's size hypothesis)

Registered 2026-08-27 BEFORE any result was computed. Origin (Casey, 2026-08-27):
"the team matters more when they're smaller companies versus established
companies... we're using the same weighting... on big companies as we do small
companies... run a massive analysis on how the weights could be different and
back-test all these variants... multiple ways to look at company size...
at least 2 years, longer better."

## What is and is not testable (stated up front)
- The live composite has NO team factor; its components are revision_velocity,
  catalyst_score, hype_divergence, positioning, runway_penalty (equal 0.225 x4
  + 0.10 by operator decision 2026-07). "Team weight by size" is therefore NOT
  directly backtestable — and team/hype have no historical record at all.
- The TESTABLE form of the hypothesis: signal efficacy and optimal component
  weights are size-conditional — concretely, binary-event/catalyst signals
  should matter MORE for small names (execution/binary risk) and
  slower-moving "established pattern" signals (analyst momentum) more for
  large ones. This is the claim R9 tests.
- Team-factor weighting by size goes PROSPECTIVE: an H11-style shadow scorer
  (observe-only) is the only honest instrument; proposed separately if Stage
  results justify the size-conditioning principle at all.

## Universe, period, data (frozen)
- The replay universe: the 34-name bars store used by backtest_calls_10y
  (2016→2026 where bars exist), XBI as excess benchmark.
- PIT components at date t (sources frozen; each labeled where a proxy):
  C_cat  catalyst_score, live config impacts/decays, PIT CT.gov store.
  C_rev  analyst momentum PROXY: net direction of rating actions (FMP grades,
         dated), 90d window / 30d half-life mirroring live revision_velocity
         params. NOT estimate revisions; labeled everywhere.
  C_pos  positioning PROXY: FINRA bi-monthly short interest, z of -Δ(SI/ADV)
         over trailing 3 settlements, available 2018+; options skew has no
         history and is EXCLUDED.
  C_run  runway penalty from quarterly cash + operating burn (FMP), applied
         with a 45-day reporting-lag guard.
- Size measures at t (all PIT; employees EXCLUDED - no historical record):
  Z1 market cap: close(t) x PIT shares (FMP enterprise-values quarterly,
     <=1q lag; fallback historical-market-capitalization where served).
  Z2 pipeline breadth: distinct interventions in non-terminated trials
     as-known-at-t (PIT CT.gov store).
  Z3 stage: commercial (LTM revenue >= $250M as last reported) vs clinical.
- Bucket schemes: B1 absolute cap <$1B / $1-10B / >=$10B (Casey's framing);
  B2 relative terciles within-universe per date; B3 stage split (Z3).

## Stage 1 — signal-level size interaction (the science)
For each component score and each replay flag (quiet_before_catalyst,
pullback_into_catalyst, binary_event_within_n_days + price-only rows), test
forward 5/21/63-bar XBI-excess conditioned on size bucket. Inference: cluster
bootstrap (symbol|month), 4000 draws, seed 20260827; the interaction statistic
is the small-minus-large efficacy gap per signal; Westfall-Young max-T across
the full Stage-1 family. Census tables (names per bucket per year) reported —
a bucket that is 3 names is reported as 3 names.

## Stage 2 — weight-scheme replay (the engineering)
Composite variants: weight vector w(bucket) over {C_cat, C_rev, C_pos, C_run},
applied to the SAME PIT scores, scored daily, portfolio = top-tercile
composite names, monthly rebalance, equal weight, XBI-excess; also the calls
framing via the production grader where flags fire. Arms:
- baseline: size-blind live weights (equal signal weights, 0.10 runway).
- grid: for each of B1/B2/B3, small-bucket tilt x large-bucket tilt drawn
  from the frozen simplex set {equal, cat-heavy .40, rev-heavy .40,
  pos-heavy .40, cat-extreme .55, rev-extreme .55} — 3 buckets x 6 x 6 = 108
  scheme arms + 3 monotone-interpolation arms + baseline = 112 total.
Multiplicity: Westfall-Young max-T over all 111 non-baseline arms against the
baseline; paired cluster bootstrap as Stage 1.

## Frozen metrics & kill language
- Headline: annualized XBI-excess IR of the composite portfolio; secondary:
  hit rates, forward-return spreads, calls-framing expectancy (R multiples).
- An arm SURVIVES only if WY-adjusted p < 0.05 vs baseline AND the sign of
  its edge holds in both sample halves (split at 2021-07-01). Otherwise
  "nothing survives" — a valid and reportable outcome (R4-R6 precedent:
  25 arms, zero survivors).
- No post-hoc arms. Additions require a new registration. Diagnostics may be
  run but are labeled DIAGNOSTIC and cannot be promoted to findings.
- Unicorn lessons bound in as gates: synthetic-panel alignment micro-test
  must pass before any result is read; census sanity checks; Sharpe > 3 on
  any arm triggers a leak audit BEFORE it is reported, not celebration.
- Honesty box carries: proxy labels (C_rev, C_pos), the 2018+ truncation of
  C_pos, survivorship of the current watchlist (names that died before 2026
  are underrepresented; direction of bias stated), and 34-name universe
  breadth limits (bucket n's shown beside every claim).

## Pre-analysis amendment (2026-08-27, before any result computed)
Z2: the PIT CT.gov store records status/phases/PCD timelines but NOT
intervention names, so "distinct interventions" is not reconstructable.
Z2 is REDEFINED as: count of non-terminated trials as-known-at-t (with a
phase-weighted diagnostic variant). Amendment made at data-inspection time,
prior to computing any forward return.
