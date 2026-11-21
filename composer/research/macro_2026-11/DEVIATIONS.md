# Deviations from PREREG.md (macro study)

1. **Composites are reported as built, though two are poorly sized.** GC2 ("at least 2 of 9 families on")
   is on 65-81% of days and the VOLUME composite on 1-2%. Neither threshold was changed after seeing this.
2. **"At least 8 separate on-episodes" was written as a count of switches; switches flicker.** A second
   count is reported beside it: regimes, with on-spells less than 63 sessions apart merged
   (`m2_followup.py`). The LIQUIDITY composite cleared the pre-registered P1 rule by the letter on the book
   (growth above its equal-exposure mix, shifted-state p 0.000, same sign on the shape years, mirror worse,
   21 switches) but has TWO regimes in the verdict sample and loses significance without 2020-2021. It is
   reported as a candidate, not as a state that works. This is a downgrade against the letter of the rule,
   made after seeing the result, and is stated as such in the report.
3. **Cross-engine signals on the BOOK target contain the signalling engine's own return.** They are re-scored
   on the other two engines only (post hoc, `m2_followup.py`); the report uses those.
4. **P1's Holm correction** takes, per state, the smaller of its growth p and its deepest-fall p, over the
   11 primary states. **P2's placebo** uses 400 shifts, not 1,000.
5. **Post hoc follow-ups** (all labelled in the report): liquidity and gold by calendar year and without
   their strongest years; the gold composite with the opposite sign to the one registered; the policy of
   moving weight out of Holy Grail while its gate is off.
6. **States with fewer than 40 on-days or off-days in a sample are not scored there** (e.g. CREDIT and
   VOLUME on KMLM's real years).
