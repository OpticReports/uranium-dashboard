# Independent verification log: forward-range study (addendum 62), 2026-11-21

One reviewer that did not write the code, on commit with the first full results and the draft report:
an independent re-implementation of the Monte Carlo, the statistics, the citations (checked on the web)
and every claim in the draft.

## First pass. Verdict: the Monte Carlo is sound and reproduces; four verdict bullets and two citations were not fit to ship
The reviewer's own engine (own seed, 10,000 paths) matched 526 of 528 comparisons within three standard
errors (scenarios B, D, E, F at 0 / 31.8 / 50% sleeve, three horizons, all statistics, both cap rules and
the daily reset); the source table, betas, deflated-Sharpe figures and the live-fall split reproduced
exactly.
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | BLOCKING | No scenario had zero or negative edge; the lowest still assumed about +21% a year. At zero edge: median -2.4% a year, 57-59% chance below the start at 1 / 5 / 10 years, median deepest fall 72%; the sleeve ordering flips. | ADDED as scenario Z in every table, the verdict and a KPI tile. "No scenario is a floor." |
| B2 | BLOCKING | "The live record is ahead of the simulation" did not hold for the money held: basis mismatch on the deposit day; Holy Grail since funding +78% against +93%; KMLM's lead is one session, the sleeve's mostly one. | FIXED: basis corrected, funded-period and as-held rows added, bullet rewritten ("neither confirms nor contradicts"). |
| B3 | BLOCKING | "A low-return decade barely moves it" presented a ceiling as a planning scenario; a single beta is unstable (half-year betas -1.7 to +2.7; R-squared 0.04 to 0.18); the rebuilt 2000-2009 history has the book at about +30% a year. | FIXED: G relabelled "ceiling, shifted"; bullet and note rewritten around the rebuilt decade. |
| S1 | SERIOUS | "The sleeve gets cheaper as the edge shrinks" was produced by giving all three engines the same haircut; where decay is measured per engine the sleeve gives up a larger share. Two orderings flip between scenarios, which PREREG said to report as not decided. | FIXED: new table "what the sleeve costs and buys"; bullet rewritten; "not decided by the data" stated. |
| S2 | SERIOUS | "The risk grows faster than the return shrinks" false as stated. | Retitled "Less edge means deeper falls, not only lower returns". |
| S3 | SERIOUS | Harvey and Liu misattributed; McLean and Pontiff's 58% is not "half" and not backtest-to-live. | FIXED (DEVIATIONS 6). |
| S4 | SERIOUS | One-year medians and loss odds move with the block length. | ADDED: sensitivity table and note; one-year figures quoted as ranges. |
| S5 | SERIOUS | Haircuts only on the friendliest long source. | ADDED: scenarios H and I. |
| S6 | SERIOUS | Return concentration not disclosed (best 50 sessions; 2020). | ADDED to section 6. |
| M1-M7 | MINOR | Haircut on cash days; the live-fall split by engine; Sharpe not over T-bills; a mislabelled column; log against compound growth of the S&P; the source hole; the promised beta share on the long source. | FIXED or disclosed. |
| N | NOTE | One generator across scenarios; the model resets instantly; the bootstrap, the drift-and-reset logic and the late paths are correct; "drift changes the fall little" holds path by path. | Disclosed. |
Figures marked "reviewer" in the report (the single-session live gaps, rolling betas, the cash-day and
fading-on-best-days checks, the deflated Sharpe with real skew and kurtosis) are the reviewer's own
computations, not recomputed by me.

## Delta check on the re-run and the rewrite. Verdict: signs off on the verdict bullets, tiles and notes
Scenarios A-G unchanged (same draws). The added scenarios matched the reviewer's own runs within Monte
Carlo error (none of the edge: -2.4% a year, 57-58% below the start, median fall 72-73%; the 1994-on
haircuts +24% and +11%); the cost table, the block table, the side numbers and all five live rows
reproduced. One figure adjudicated: "the three as held since 2026-07-07" is +28.7% live against +24.3% for
the simulated engines at the same start-of-day weights; the reviewer's first-pass "+28.9% against +29.3%,
level" used fixed target weights for the simulation and is withdrawn as not like for like. Qualifier
required and added: 3.4 of the 4.4 points are one session (2026-10-27). Six wording residuals applied (the
zero-edge sentence against T-bills; a range for the one-year loss chance at a quarter; "the backtest", not
"the ceiling", without 2020; which legs are real, rebuilt or modelled, stated in the report; the methods
table by name; a footnote on the single-path falls of the long haircut sources). Suhonen, Lennkh and Perez
remains confirmed from secondary summaries only.
