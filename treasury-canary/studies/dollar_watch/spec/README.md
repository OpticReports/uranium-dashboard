# Dollar watch pre-registration — SPEC v0 and its two reviews (2026-11-02)

Status: **NOT FROZEN.** Both adversarial reviews returned NOT_PASS on SPEC v0. Its primary route (D-1, a
cross-section of 15 FRED currencies) is withdrawn as designed. The recommended route is now
`forward_only`: the dated forward ledger the Dollar tab already writes (memo §9.1). The freeze waits on
Casey's answers.

## The two reviews

Statistics and design (`review_stats_v0.md`): NOT_PASS, 2 BLOCKING, 3 SERIOUS.

- **The D-1 benchmark is not a valid null.** A series with no information scores T < 0, because the
  random-rule hit probability uses the whole episode and the deceleration day follows the steepest,
  most volatile climb. On synthetic martingales, the information-free rule is declared INVERSE 24–28% of
  the time.
- **PASS is close to unreachable.** The +0.15–0.25 detectable edge ignores the PASS bars: a real
  +0.16–0.19 edge passes with probability about 0.01 and is permanently FAILed 60–81% of the time.
- **Clusters are not independent.** Clusters link at 126 days but outcomes run 250. Only about 5–17
  non-overlapping clusters exist, against a floor of 15.
- **The volatility-scaled transposition is not the frozen rule.** Applied to the dollar itself, it keeps
  2 of the 5 frozen post-warm-up firings exactly.
- **About 20% of the "floating" sample are basket or crawling pegs.**
- **Ledger power under exact binomials:** about 45, 90 and 234 years at edges of 0.70, 0.60 and 0.50
  against 0.35. Momentum needs about 400 years.

Data, look-ahead and contamination (`review_data_v0.md`): NOT_PASS, 1 BLOCKING, 6 SERIOUS.

- **Most of the "unseen" record has been seen.** The 8-pair EM basket's outcomes after the US rule's
  firings and the momentum months were computed for the panel, and seven of those pairs are D-1
  currencies. Finder B charted the basket's full paths, and DTWEXBGS contains 11 of the 15 D-1 pairs.
  Done properly, the clean subset is 266–310 of about 625 currency-years, mostly NZD, NOK, LKR and
  managed Asian regimes before 1997.
- **D-2 (DXY 1973–2005) is not semi-clean.** Its monthly outcomes are already published in the scoping
  outputs.
- **Survivorship.** TRY, IDR, ARS and RUB are absent, and no LatAm pair covers 1982.
- **The VIX calendar cuts 1973–89.**
- **Some transposition choices were made with partial outcome knowledge.**
- **The rule's code is equivalent** across decel_realtime.py and build_reference.py: both give 6
  unpatched and 7 re-arm firings, on both calendars and across 15 ALFRED vintages.
- **The study code skips the last index day.** That lags a live firing by up to one weekly H.10
  release. The panel's live rule evaluates through the latest day.

## What follows from the reviews

- **D-1 as designed cannot change the decision** (a biased null, and PASS out of reach), and running it
  would spend the only partly unseen data. It is not run. A redesign is possible: a surrogate-calibrated
  null, de facto regime filtering and seen-span accounting. But its power would still be low on the
  clean subset. That is Casey's call (Q1).
- **D-2 is descriptive at most.**
- **The forward ledger (D-3) is the only clean route.** The panel has written it since 2026-11-02 under
  both variants, so no future firing is lost while the freeze waits. To freeze it, the open questions
  are:
  - Q2: the primary crisis list.
  - Q3: the primary variant, unpatched or re-arm.
  - Q5: the mechanical rule that dates future crises, so the ledger is not scored by hindsight.
  - Q6: may a live alert on the gauge ever come from anything but the ledger?
- **The panel withholds the EM FX outcome columns until the freeze** (data review S1). Seven of the
  basket's eight currencies are in D-1's proposed set, so seeing them could steer Q7–Q13.

## Files

- `SPEC_v0.md`, `freeze_template.json`: the draft and its 16 questions with defaults (not Casey's answers).
- `probe_manifest.txt`: the drafter's FRED probe (dates and row counts only).
- `review_*_v0.md`, `review_*_scripts/`: the reviews and their scripts. The statistics review's
  simulations are synthetic. The data review's scripts read the US series and calendars only. Neither
  computed an outcome on any D-1 currency or on DXY 1973–2005. Raw downloads stay out of the repo.
