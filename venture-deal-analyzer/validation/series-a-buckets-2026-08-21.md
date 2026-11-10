# Study — measured stage-conditional exit multiples, and what they broke

VERIFIED after adversarial review, 2026-08-21. Prompted by Casey:
*"In general, what are the break downs for multiples on series A
probabilities."* Counter-agent verdict on the first pass was **NOT SAFE
TO CALIBRATE FROM**, with six required corrections. All applied.

This is the largest single correction the instrument has taken.

## 1. The numbers, and how they were obtained

PitchBook *VC Returns by Series* Part IV publishes a figure —
"Multiple on invested capital (MOIC) VC distribution by series" —
whose categories are exactly Seed / Series A / Series B / Series C /
Series D+ across exactly our six buckets. **PitchBook published the
chart and withheld its data labels.** The PDF text layer for that
figure carries only axis and legend text, while the *adjacent* Series
C+ figure does carry labels (50/41/6/2/1/0).

The counter-agent recovered the values by converting the page to SVG
(`pdftocairo -svg`) and reading the geometry of the 30 bar rectangles,
then normalizing each series column to 100%. **No bar heights were
eyeballed.** Precision ±0.5pp.

| bucket | Seed | **Series A** | Series B | Series C | Series D+ |
|---|---|---|---|---|---|
| <1x | 81.2 | **66.0** | 55.4 | 50.7 | 48.4 |
| 1–5x | 8.9 | **18.4** | 31.0 | 37.7 | 44.1 |
| 5–10x | 3.8 | **7.1** | 7.5 | 7.0 | 5.2 |
| 10–20x | 2.8 | **4.2** | 3.3 | 2.8 | 1.4 |
| 20–50x | 1.9 | **2.8** | 1.9 | 1.4 | 0.5 |
| >50x | 1.4 | **1.4** | 0.9 | 0.5 | 0.5 |
| **P(≥10x)** | 6.1 | **8.4** | 6.1 | 4.7 | 2.4 |

Basis: US, n=31,642 companies taking a first VC round 2009–2018,
measured 2024-06-06, **count basis**, **includes tracked failures**
(out-of-business plus no-major-round-in-6-years), gross and pre-fee,
IPO payout marked at **IPO pre-money**.

### Two independent validation locks — both pass

1. Recovered **Seed <1x = 81.2%** against PitchBook's own prose: *"as
   much as 81% of seed investments return less than the original
   cost."*
2. **mean(Series C, Series D+) = 49.5 / 40.9 / 6.1 / 2.1 / 0.9 / 0.5**,
   which rounds to **50 / 41 / 6 / 2 / 1 / 0** — PitchBook's *printed*
   Series C+ labels.

Both locks are now merge-blocking gate tests. If a future edit breaks
either, the recovery is no longer corroborated and must not ship.

## 2. What this replaced — two mislabeled anchors

**The vector installed as `seed` was never a seed distribution.**
64.8/25.3/5.9/2.5/1.1/0.4 is Correlation Ventures' **all-sector,
all-series pooled** 2014 figure. The counter-agent reconstructed it
exactly as the n-weighted blend of CV's two published sector bars
(Other VC n=19,412 at 65.7/24.6/5.8/2.5/1.1/0.4; BioPharma n=2,228 at
57.0/31.6/7.1/2.8/1.3/0.3 → 64.804/25.321/5.934/2.531/1.121/0.390).
Provenance is solid; the *label* was wrong. Retained in
`calibration.json` under `_superseded` as a cross-check, not a stage.

**`series_b` was CONSTRUCTED and 14pp optimistic.** Its 41.7% loss mass
rested on a "CV dollar-basis 37% <1x" that is Correlation's
**all-stages pooled dollar-weighted** figure, not a Series B figure.
Measured B is **55.4%**. Worse: the gate we built to defend it required
B loss mass in [0.40, 0.50] — **that gate would now reject the true
value.** A gate built on a mislabeled source defended the wrong number
for six days.

## 3. A REFUTED inference of ours, logged deliberately

We proposed: *CV's pooled <1x (64.8%) ≈ CV's Series A <1x (65%),
therefore the pooled vector is "Series-A-shaped" and is a better-founded
`series_a` anchor than a `seed` one.*

**Refuted. The coincidence is arithmetic.** Sweeping stage weights on a
5% grid over the measured columns, **133 distinct mixtures** reproduce
pooled <1x = 64.8%, spanning 19.7–26.5% at 1–5x and 4.2–8.2% at ≥10x.
One moment cannot identify six buckets. Worse for the claim, the
mixtures whose *shape* best matches the pooled vector are seed-heavy
and **Series-A-light**.

Measured Series A is **18.4%** at 1–5x and **8.4%** at ≥10x, against the
pooled vector's 25.3% and 4.0%. **Importing the pooled mid-buckets
would have halved the Series A tail.**

## 4. Basis discipline — do not target 3.0X

Correlation publishes matched pairs: **65% <1x on a count basis**, and
**56% <1x on a dollar basis together with the 3.0X average realized
multiple**. For a per-deal analyzer the count basis is correct, and the
corollary is that **3.0X must not be used as a target mean** — it is a
dollar-weighted object and these bucket frequencies are count-weighted.
`implied_mean()` exists to keep that gap visible rather than fitted
away.

## 5. Three structural problems the measured data exposed

**(a) The tails imply infinite means.** The survival exponent implied
*directly* by the measured 20–50x and >50x buckets: seed **0.94**,
Series A 1.20, B 1.24, C 1.46, D+ **0.76**. An exponent ≤ 1 has no
finite mean — EV becomes purely a function of where one caps, which is
a modelling choice, not a measurement. PitchBook's top bucket is
open-ended (50x+) and absorbs outcomes like Uber's 5,230x seed MOIC.

For seed (1.9%/1.4%) and D+ (0.5%/0.5%) those buckets sit **at the
±0.5pp recovery precision floor**, so their ratio carries no
information; both are fitted under a constraint α ≥ 1.0 and their tails
are indicative only. **Series A, B and C have both tail buckets clear
of the floor — their exponents are genuinely determined.** Series A's
1.20 (CSN 2.20) sits comfortably inside the published range.

**(b) Our functional form has no atom at zero.** Real venture losses
pile up *at* zero; measured loss mass runs 48% (D+) to 81% (seed).
Forcing a continuous lognormal to carry 81% of its mass below 1x, with
a grid floor of 0.001 and a 0.5% truncation cap, is infeasible — the
seed fit degraded to a **69% relative error**. Fixed by pinning each
stage's measured loss mass exactly (`_pin_loss_mass`) and fitting only
the above-1x shape. This is the same principle `tilt_to_forecasts`
already used: **constrain what is known, fit only what is not.** Loss
mass is measured; the distribution *within* the loss region is
published by nobody and affects no output except the loss-region
conditional mean, which the `sub1_drag` convention already sets.
Post-fix, max relative bucket error: seed 9.1%, **Series A 5.0%**,
B 4.7%, C 6.0%, D+ 25.6%.

**(c) Uncapped EV is not a robust statistic.** At the measured
exponents the tail carries ~29–35% of uncapped EV on ~2% of outcomes.
**Capped EV is the headline; uncapped is disclosed, never led with.**

## 6. Gate changes (18 gates pass, was 12)

- `fit_check_relative` — relative bucket error, per-stage tolerance.
  The absolute gate (0.015) is structurally blind to a bucket whose
  target is 0.004 and had been concealing a 39% underfit.
- `upper_truncation_mass` supersedes `truncation_mass` as binding —
  with loss mass pinned, only discarded *upside* distorts anything.
- Loss mass pinned to the measured figure, gate-tested exactly.
- Loss mass must decrease monotonically across stages (81.2 → 48.4).
- Both validation locks, as tests.
- Tail α must exceed 1.0 (finite mean) for every stage.
- Tree reconciliation now compares **capped** EV, asserts direction,
  and bounds the divergence at 0.40.

**FOLLOW-UP OWED:** the audited discrete EV trees were derived against
the old mislabeled vector. Capped EV now sits ~0.30 above the tree at
the test point. That divergence is bounded and recorded, **not
re-banded away** — the trees should be re-derived against the measured
stage curves. Until then the tree headlines on any display.

## 7. Deal impact, and a re-staging decision NOT taken silently

Every logged deal still calls `stage="seed"`. With real stage curves
available, DexMat / Quaise / Matter are Series-A-stage deals and
arguably belong on `series_a`. The difference is small because the tilt
pins P(<1x) and P(≥10x) to the panel's logged forecasts:

| deal | capped EV as `seed` | as `series_a` |
|---|---|---|
| dexmat | 1.941 | 1.995 |
| argentina-gdp-warrants | 1.642 | 1.708 |
| quaise | 1.720 | 1.782 |
| series-x-capital-fund-i | 2.529 | 2.564 |
| matter-intelligence | 1.443 | 1.514 |

Re-scoring is a deliberate decision, flagged rather than bundled into a
calibration commit.

## 8. UNRESOLVED — ask, do not average (standing rule)

Correlation's 2014 source is **internally ambiguous** about whether
"2004–2013" is the **financing** window (Booth's prose: financings
"closed between 2004-2013") or the **exit** window (CV's own chart
subtitle: "companies going out-of-business, acquired, or IPO
2004-2013"). CV's later posts favour the exit reading. Affects only the
retained cross-check vector, not the installed stages.

## 9. Still not published by anyone

- Any Series A **tail exponent** estimated directly. AngelList/Othman's
  figures are pooled early-stage with no seed/A/B split — and note
  there are **two** of them on different samples: α ≈ 2.3 (CSN density,
  n=1,808, pre-Series-C, mixed realized/unrealized) and α = 2.42
  (n=684 winners, xmin=1). Keep both with their samples, or neither;
  do not silently swap.
- A Series A **median** MOIC. Correlation publishes only the mean.
- Any Series A histogram **including unrealized marks** — every source
  here is realized-or-tracked-failure.

## 10. Caveat that governs all of the above

These are **exited-and-tracked-failure** distributions. They say
nothing about whether a position resolves at all — see
`realization-rates-2026-08-20.md`. Roughly half of Series A positions
are still unresolved at these cohort ages. Every figure in this file is
**conditional on realization**.
