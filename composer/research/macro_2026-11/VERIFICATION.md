# Independent verification log: macro regime study (addendum 61), 2026-11-21

Two reviewers that did not write the code. A: construction of the state panel (publication lags,
look-ahead, state definitions) and the test arithmetic, on commit 8140c828. B: statistics and claims, on
the first draft report; then B again on the re-run files and on the rewrite.

## Review A (construction). Verdict: panel and arithmetic reproduce; three construction faults
A rebuilt all 42 states from the raw files (0 sessions differing since 1994-06) and matched every test
number it recomputed to four decimals.
| # | Severity | Finding | Disposition |
|---|---|---|---|
| A1 | SERIOUS | The liquidity composite is two different instruments: in 2015 on it is the Fed balance sheet state (1,771 of 1,790 on-days), before 2003 it is M2 alone; 20 of its 21 "episodes" are flicker around a flat balance sheet in 2015-2017; 596 of 973 off-days are one block, 2019-10 to 2022-08. | ACCEPTED. Reported as one episode, not a candidate rule; split in `m5_review.py`. |
| A2 | SERIOUS | Daily FRED series (yields, curve, real yield, breakeven, fed funds, Baa spread) were used one session early. | FIXED (lag 2, as PREREG says); everything re-run; no verdict moved. |
| A3 | SERIOUS | The financial conditions index is not point-in-time: from 809 weekly vintages (2011-05 on), "above zero" is on in 8 weekly readings since 2015-06 on today's file and in 2 as published. | DISCLOSED (DEVIATIONS 11, report section 8). Not rebuilt: none of the three states built on it carries a result. |
| A4 | MINOR | CPI used from the 15th of the next month was before the release in most months. | FIXED (22nd). |
| A5 | MINOR | Fed balance sheet at lag 2 leaks (released Thursday after the close). | FIXED (lag 3). |
| A6 | MINOR | A zero-volume print (2023-05-24) blanked two volume states for a year. | FIXED. |
| A7 | MINOR | Composite bars shift as states gain data. | DISCLOSED. |
| A8 | MINOR | Holm divided by states scored (10), not registered (11); P1's p from a 1,000 draw read 0.000 where the exact value is 0.0019. | FIXED (every shift; (1+count)/(1+N); Holm over registered tests). |
| A9 | MINOR | The tilt (P2) is a static lean to KMLM: always-on gives +0.098 a year; tilting starts only in 2020-06. | STATED in the report. |
| An | NOTE | Engine paths skip about 25 bond-holiday sessions before 2007 and three splice days; the gate-off result's on-day growth is 2.68 of 3.34 from 2020 and 2022. Checked clean: no look-ahead at lag 0, engine returns run from the prior close, M2 never used before publication, CAPE within 1.6% of Shiller, the gate equals a raw rebuild on 8,174 of 8,174 days, the FFT placebo equals brute force, the tilt is out of sample. | Disclosed / used. |

## Review B (statistics and claims). Verdict: arithmetic reproduces; three verdict bullets did not survive
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | BLOCKING | The headline ("the book is already counter-cyclical") omitted what it depends on: same-close fills (one close late the gap is +0.38 on the book since 2015-06, negative for Holy Grail and the sleeve, gone on the rebuilt years; 62% and 78% of Holy Grail's and the sleeve's below-average growth comes in the session after a trade) and two years (2020 and 2022: half the days, two-thirds of the growth). | ACCEPTED. Recomputed in `m6_robust.py` (matches B's numbers); verdict rewritten; new section 3; the one-close-late bound for the whole book reported as a by-product. |
| B2 | SERIOUS | The shifted-state placebo is too generous for states tied to volatility: with equal means it rejects at 5% in 14 to 31% of draws (S&P state, the gate, credit), about 6 to 8% for gold, the dollar and liquidity. | ACCEPTED. Second test (Newey-West) added to every headline row and quoted in the verdict; DEVIATIONS 14. The size check is B's own computation. |
| B3 | SERIOUS | "The symphonies are not working against each other ... on all four stretches" was B1 counted twice: the gate reads the same as the S&P state on 98% of days; three stretches, not four; no engine carries it in both recent stretches; Holm over the five cross signals not applied. | ACCEPTED. Bullet merged into the S&P finding; concentration and the missing correction stated. |
| B4 | SERIOUS | Gold "in all three engines, and not only in 2020-2022" was wrong: on each engine's own recent sample only the sleeve shows it; one regime (2018-12 to 2020-11) carries it; the rebuilt years have the other sign; one state (gold against the S&P) carries the composite. | ACCEPTED. Demoted from candidate to lead; KPI removed. |
| B5 | SERIOUS | "The gate gave up +0.69 a year on its off-days" compared the ungated tree with T-bills, not with the live tree, which earned +0.76 on the same days. | FIXED. |
| B6 | SERIOUS | The book's 124-session hole (2020-12-02 to 2021-06-01) and the rebuilt KMLM fund inside "recent" (2015-06 to 2020-12) were not stated. | FIXED (sections 1 and 8; DEVIATIONS 17). |
| B7-B11 | MINOR | Liquidity and dollar p-values from a random draw; "after 11" over 10; the tilt's "+0.0 pts" fall an artefact of its burn-in; the redeploy explanation rests on same-close dip-buying. | FIXED by the re-run or stated. |
| B12 | MINOR | Edges omitted (three single states with the same sign on both stretches; two cross signals into the sleeve; a re-entry state) and the volume lead's concentration. | ADDED to section 7. |
| B13 | MINOR | Post hoc items not labelled. | LABELLED; DEVIATIONS 18. |
| B16 | SERIOUS | `m6_robust.py` first dropped the wrong gold regime (the longest, not the one carrying the result). | FIXED before any report used it. |
