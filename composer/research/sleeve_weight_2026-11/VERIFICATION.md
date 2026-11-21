# Independent verification log: sleeve weight study (addendum 60), 2026-11-21

One reviewer that did not write the code, on commit ffb577f3 (simulation, statistics and the draft
report), then a delta check on the rewrite.

## First pass. Verdict: every number reproduces; the headline and two verdict lines did not survive
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | BLOCKING | Verdict sentence had the two growth figures swapped (+172% is the book with NO third leg). | FIXED. |
| B2 | BLOCKING | "With no deeper fall" false: against T-bills the sleeve book falls +0.8 and +1.8 points deeper. | FIXED; figures stated. |
| B3 | BLOCKING | "Mostly the data" not supported: without 2020-02..04, 2015-2020 falls below the real years' interval; the ladder's rarest tests (TLT up more than 6% in a day: two days in 32 years, both March 2020) look fitted to that month; 2015-2020 is all ladder while the real years are about half inverse funds; 2011-2015 had mostly real funds and was flat. | ACCEPTED. Headline is now "unresolved, and the answer differs by half"; recomputed in `s3_review.py`. |
| S1 | SERIOUS | The "mirror" claim was false for 2002-2011: the one-day tests fired on 172 days there and made nothing, on modelled volatility funds. | Rewritten as the reviewer's finding. |
| S2 | SERIOUS | "UVXY the day after a shock" misdescribed the best days (several fired on overbought readings; 2024-08-05 on a band 0.1 wide). No look-ahead. | Rewritten; the band and the day's weight in the result stated. |
| S3 | SERIOUS | "The 31.8% weight passes" over-read a test that only asks whether the sleeve beats cash; it passes at 10% and 50% too; the inverse half alone passes only since 2021-06. | Rewritten; each half as third leg added. |
| S4 | SERIOUS | The Holy Grail offset is standing short exposure, not timing. | Reworded, attributed. |
| S5 | SERIOUS | Edges under-reported: the ladder alone as third leg; the ladder's overbought/oversold tests. | Both in section 5. |
| m | MINOR | Counts, attribution gross of costs, single-session dependence of 2011-2015, leverage changes of UVXY and SVXY in 2018, one missing seam day (2023-02-01), undefined terms, missing open questions. | Applied or disclosed. |
| n | NOTE (clean) | The half-trees isolate correctly; all 20 tickers match fresh closes from 2015-06; the pass against T-bills survives dropping the sleeve's ten best days and hardly depends on the rebuilt KMLM engine. | |

## Delta check on the rewrite. Verdict: fit to send once two points were fixed
The pre-registered rule, applied as written, returns "the data"; "in between" appears only without
2020-02..04: the headline now says exactly that. One candidate edge was still missing (the ladder's
overbought/oversold tests): added as the reviewer's finding, with the note that no placebo was run.
Twelve wording and layout minors applied. Every `out/review.json` number matched the reviewer's own run.
