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

## After the construction review (review A, 2026-11-21); all numbers re-run
7. **Daily FRED series were used one session early; corrected.** The first run read the d-1 observation of
   the Treasury yields, curve spreads, real yield, breakeven, fed funds and the Baa spread for a position
   taken at the d-1 close; those are published after that close. PREREG says "session before, plus extra
   lag 1": the code now does that (lag 2). Touches R1-R7, I1, C1, C2, V3, RE1. First-run outputs are in git
   history (commit 8140c828); no verdict moved.
8. **Stricter than PREREG, to remove residual look-ahead:** CPI is used from the 22nd of the next month
   (PREREG: the 15th, which was before the release in most months); the Fed balance sheet at lag 3 (PREREG:
   2; H.4.1 is released Thursday after the close). Months with a late release (the 2025 shutdown) can
   still be a few days early.
9. **A zero-volume print (S&P 500, 2023-05-24)** blanked M1/M2 for 252 sessions; a missing print now takes
   the previous session's volume.
10. **p-values:** P1 uses every circular shift from 63 to n-63 (not a draw of 1,000); every p is
    (1 + count) / (1 + shifts), so none reads zero; Holm multiplies by the number of REGISTERED tests (11
    composites, 3 re-entry states) even where one could not be scored.
11. **Not fixed, disclosed in the report:** the financial conditions index (C3, C4, RE2) is today's revised
    file; review A fetched the 809 weekly vintages from 2011-05 and found C3 on in 8 weekly readings since
    2015-06 on today's data against 2 as first published (March 2020 read -0.48 then, +0.04 now). No vintage
    exists before 2011-05. The composites' "at least half" bar moves as states gain data (RATES 3-of-6
    before 2003-04, GOLD 2-of-4 before 2001-06, LIQUIDITY is M2 alone before 2003-06 and in effect the Fed
    balance sheet alone from 2015). Market series (S&P 500, gold, copper, dollar, volume) are taken at the
    prior close, the same convention as the engines' own signals. Engine paths skip about 25 bond-holiday
    sessions before 2007 and three splice days (2015-09-01, 2021-06-01, 2023-02-01), inherited from
    addenda 58-59.
12. **Post hoc from review A (`m5_review.py`):** the liquidity composite split into its two states and its
    largest block of off-days; the gate-off result by year; the tilt with the state always on.
13. **Post hoc (`m4_leanin.py`):** the mirror of P1 on the S&P-below-its-200-day state and on gold (book at
    half size on the other days), scored also against the constant mix with the same deepest fall; book
    growth by year and engine.
