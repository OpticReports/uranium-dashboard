# Counter-agent verdict — TLT/duration squeeze study (2026-08-25)

**VERDICT: PASS WITH CORRECTIONS.** Pipeline PIT-clean; current-state numbers
reproduce exactly. Two blockers + majors, ALL APPLIED before presentation:

1. BLOCKER — fig2's "≈6% covering, peak Nov 21" was an OI-denominator artifact
   (pre-Thanksgiving roll week: OI +534k). Contracts basis: net short -2,829k
   Oct 31 → -2,541k Dec 12 (~10.2% covered; gross -9.5%), rebuilt -2,850k by
   Jan 2. APPLIED (fig2 v2 rebuilt on contracts).
2. BLOCKER — conditional "edge" (42/38, 14/9) statistically indistinguishable
   from zero: 448 conditional weeks collapse to ~22 runs; block-bootstrap 95%
   CIs on both differences straddle zero. APPLIED (fig3 caveat; language
   downgraded; signed null leads).
3. MAJOR — 2010 episode was EU/flash-crash flight, not QE2 (window ends Jun 29,
   Jackson Hole was Aug 27); "0 positioning-caused" weakened to "none
   identified; design cannot rule out; Oct-2014 flash rally (sub-threshold)
   WAS positioning-driven". APPLIED.
4. MAJOR — futures book ≠ ETF short book. RESOLVED WITH DATA: FINRA SI shows
   the ETF book ROSE 52→81M through Dec 15 2023, covered only after the pivot
   (81→49M by Dec 29). F2 resolved with verified FINRA numbers (16.7%, falling).
5. MAJOR — trigger side nearly blind at Oct 31 2023 (2/5). APPLIED: admission
   in spec; T5 re-specified as vol/dislocation (it fired in 2023 as duration
   capitulation, not flight-to-quality).
6. MAJOR — scoring inconsistencies: T2 PARTIAL→NOT MET (its own threshold);
   T3 quoted y/y vs 3m-ann threshold (2.89%; CPI-gauge disagreement noted);
   F1 percentile now quoted on the registered 10y window (9.2th). APPLIED.
7-8. MINOR — trough-to-peak is +21.4% (Oct 19→Dec 27), not +19%; price-return
   basis line added everywhere. APPLIED.

Independent verifications passed: CFTC current-state percentiles, the 22-episode
census dates/magnitudes, all 2026 macro readings vs FRED, TLT 22-yr-low claim
(lowest since May 2004's 80.65). Standing caveats logged in spec v2.
