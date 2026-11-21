# Independent verification log: dynamic sleeve weight study (addendum 63), 2026-11-21

One reviewer that did not write the code, on commit with the first results and the draft report: 14 states
rebuilt from raw data (0 sessions differing over 8,174 each), all 30 states x 3 samples recomputed (2,033
values exact), the tests re-derived (block bootstrap, brute-force shifts), 126 combinations of threshold, weight pair and lag run (113 beyond the registered ones), and every claim in the draft checked. Then a delta check on the re-run and the rewrite.

## First pass. Verdict: "0 of 9 pass" survives everything; no look-ahead; one bullet false, the leads' p-values belonged to the other direction
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | BLOCKING | "Risk-on when washed out: only on the rebuilt years" and "it has not shown in the years with real funds" were false: on the registered all-real sample (never shown in the draft) less sleeve while washed out is positive in all 8 variants (+0.020 to +0.066 a year), and negative on 2015-06..2020-11 (2020 alone -0.28 log-points). | FIXED: bullet replaced; the all-real and 2015-2020 samples shown; a table of the 8 variants by stretch. |
| S1 | SERIOUS | The p-values printed beside the gaining (less-sleeve) direction were the losing direction's; the two are not one test (a no-information switch loses about 0.005 a year to costs). SPY stretched, less sleeve: own p 0.11, not 0.044. | FIXED: each direction has its own p and Holm; `verdict_of` uses the chosen direction's. Verdict unchanged. |
| S2 | SERIOUS | The "best lead" (less sleeve while SPY is stretched) is 2019-2020: 2020 is 83% of it; -0.002 on the all-real years; best 20 sessions 113%. | STATED in the bullet and the lead. |
| S3 | SERIOUS | The chart's CAPE line used one benchmark weight over 1994-2026 and so showed the static cost of more sleeve, not timing. | FIXED: per-sample benchmark. |
| S4 | SERIOUS | "15% rather than 50% is worth +0.17" carried no one-close-late bound (+0.10; every constant book falls 43-52%); "no switch moves it by more than a quarter" wrong on the loss side (a third). | FIXED. |
| M1 | MINOR | The negative oil print (2020-04-20) blanked the oil state for 200 sessions. | FIXED; oil re-run (-0.037, p 0.15). |
| M2 | MINOR | QQQ states use dividend-adjusted prices; unadjusted flips two of the smallest margins. | DISCLOSED. |
| M3-M8 | MINOR | "Without 2020 and 2022" kept the full-sample benchmark; the QQQ-200-day lead omitted its failures and is the washed-out lead seen from the other side; the "dear stocks" lead is gone one close late; a mislabelled rule reason; "three or fewer rate regimes" wrong; no DEVIATIONS file; registered checks not reported. | FIXED or stated. |
| N | NOTE (clean) | Timing is exactly "read at one close, weights from the next"; no leak signature (lag -1 would give -0.104 against -0.053); the QQQ splice, CAPE dates, policy arithmetic, Newey-West, the FFT shift test and the Holm arithmetic are correct. None of the 113 other combinations passes; the smallest p of any gaining direction since 2015-06 is 0.063 (0.56 after 9). | |
The 126-variant scan and the size of the unadjusted-QQQ effect are the reviewer's own computations.

## Delta check on the re-run and the rewrite. Verdict: signs off on the bullets, tiles and leads
The reviewer reproduced the whole new output independently (5,612 values, 0 mismatches: 30 states x 4
samples, both directions' Holm values, the one-close-late constant books, the chart curves). Three
one-line fixes required and applied: "113 other combinations ... (simple-average stretch states and nine
others)", not "126"; the washed-out table's "without 2022" column now uses the re-averaged benchmark
(+0.014 to +0.040, not -0.002 to +0.027); the sentence on modelled VIX funds now follows the long panel's
own notes. Also applied: the stretched lead's wording (all of it is 2015-06 to 2020-11; five all-real years
show nothing), the two-session-lag figure and the deeper fall on the washed-out lead, the chart caption,
"five or fewer regimes".
