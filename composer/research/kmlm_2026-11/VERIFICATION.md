# Independent verification of the KMLM switcher study (2026-11-20)

Two reviewers who did not write the code, each reading the real scripts and running their own.

| Reviewer | Scope | Verdict |
|---|---|---|
| A | simulator, variant builders, injected flags, thresholds, data splices, gates | PASS WITH CORRECTIONS: no blocking or serious finding; three minor |
| B | the five-condition verdict, power, tier comparisons, overfitting measures, macro tests, the book, the wording | PASS WITH CORRECTIONS: no blocking finding; four serious, all wording stronger than the evidence |

## What A confirmed
- Every variant changes only the nodes it names (key-by-key diff of nine variants against the approved
  tree). The window split equals the mean of its members' targets on 1,377 of 1,377 days.
- Flags recomputed with the reviewer's own RSI, EMA and momentum code are identical on every decision
  day for the five forms tested; no flag is undefined inside either span.
- Four more variants were backtested on Composer itself (price > EMA(10); EMA 50x200 crossover; RSI 14
  switch and picks with 5-day matched pops and dips; 20-day momentum): holdings 898 of 898 each,
  correlation at least 0.999997, and the simulator's difference from the live rule within 0.01 log of
  Composer's in each case.
- An independent path loop reproduces three series to 4e-16, turnover and trade count included.
- A full re-run of all 75 + 63 series from the committed code matches the stored outputs to 1e-17.

## What B confirmed
- Condition 1 re-implemented independently: critical t 3.37 / 3.89 (study 3.36 / 3.83), family-wise p of
  the best cell 0.83 (study 0.84). Robust to block lengths 5 to 40; autocorrelation of the differences
  is about zero.
- Conditions 2 to 5, the double-cost construction, the ensemble rule, the overfitting probability, the
  deflated Sharpe, all 36 macro rows, Holm and the out-of-sample R2 reproduce. The book's metrics
  reproduce; its drift rule resets 1.68 times a year, as POLICY operation 5 expects.
- The rule is not impossible to pass: with a challenger as the base, the live rule clears it against
  price-vs-EMA(10) (p 0.007), price-vs-SMA(10) (0.018), the 3-day switch and picks (0.047) and the
  50x200 crossover (0.075). It does not against the 5, 7 or 8-day windows.

## Corrections applied
| # | From | Finding | What changed |
|---|---|---|---|
| 1 | B, serious | Power: the test sees only large gains; "shorter is clearly worse" and "10 is not a fluke" said more than that | wording; smallest detectable gain stated per cell (`q5_robust.py`) |
| 2 | B, serious | "Longer windows are ahead since 2023" was an overread: their average since 2023 is +0.02 log-points a year (t 0.2); before it -0.34, half of it one session (2022-11-10) | wording; numbers in the report |
| 3 | B, serious | "51 of 60 ahead on the stand-in years" is one correlated pattern, family-wise p 0.25; "the fund matters, the window does not" was never tested | sentence removed; tier C's family-wise p reported |
| 4 | B, serious | Macro: "five of six point the wrong way" miscounted (four at 21 sessions) and the signs are noise; "none predicts" should be "none detectable"; the claim that a veto would remove the best entries was not tested | wording; the bar's size stated |
| 5 | B, minor | The dollar index is weekly but was lagged one session | lagged six; its t went 1.5 to 1.2 |
| 6 | B, minor | The best cell's book interval does not survive being picked from 71 (lower bound about -7 points) | stated beside it |
| 7 | B, minor | Deviations not recorded (tier C start, "worst month" definition, the overfitting matrix) | DEVIATIONS.md 9-11 |
| 8 | A, minor | The 2026-11-20 bar was not final when fetched (12 of 24 tickers moved up to 59 bp) | every series ends 2026-11-19; all scripts re-run; no sign changed |
| 9 | A, minor | The cost constant is 13% above what Composer charged in this window | disclosed; no sign changes at Composer's rate or at zero cost |
| 10 | A, minor | Tier C carries Yahoo's stale VXZ for 2018 | disclosed; re-run by the reviewer with modelled data: no sign change |
| 11 | A, note | The 8-10-12 vote is the live rule on every session | labelled; 71 distinct challengers |
| 12 | A, note | An undefined flag would have dropped a session silently | guard added in `q1_cells.py` (never triggered) |

## Not verified by anyone
- Tier B cannot be checked against Composer (SVIX and ZVOL are modelled there).
- The window split was never sent to Composer.
- Minute-level behaviour of any variant; the stress index as published on the day.
