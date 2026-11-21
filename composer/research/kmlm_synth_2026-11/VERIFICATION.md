# Independent verification log: synthetic KMLM (addendum 58), 2026-11-20

Two reviewers that did not write the code, run in parallel on the first build (commit 4b5652f7). Each read
the real code and recomputed from the stored series.

## Review A: construction. Verdict: NOT USABLE as built; fix the loader and re-run
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | BLOCKING | `sdata.futures()` took the last row of each day; in many market-years the `23:00:00` row is the previous session's close (CAD 2009-20, CHF 2010-20, heating oil 2012-20, gasoline 2010-20, Canadian 10y, parts of copper, wheat, crude, corn, US 10y). Staleness, not look-ahead. It sat mostly outside the fidelity window, so the bars could not see it. Corrected, the long-window lean on 2008-2020 roughly halved and the 9-12 day cells flipped. | FIXED. Loader rewritten (DEVIATIONS 13, 13b): per market-year the reading that best matches an independent daily close. First-build outputs withdrawn (`out/first_build_withdrawn/`); everything re-run. Unresolved market-years listed in the manifest. |
| S1 | SERIOUS | The files hold December-only crude, corn, wheat and November-only soybeans; the fund holds nearer contracts (47 of 154 market-dates differ on quarter-end filings). | NOT FIXABLE from this data. Disclosed (DEVIATIONS 14, report sections 2 and 9); open question for front-contract data. |
| S2 | SERIOUS | F1 misses on the whole overlap even after the fix. The "actively managed until April 2022" sentence in the prospectus is about collateral and does not explain 2021. The synthetic is autocorrelated day to day (+0.14) where the fund's close is not. | ACCEPTED. The April-2022 explanation is removed from the report. The bar is read as missed; the rebuilt years are shape only. |
| S3 | SERIOUS | F5's rank correlation is carried by far-off cells; the synthetic does not resolve neighbouring windows (per-cell error about 0.09 log/yr). | ACCEPTED. New section 7 measures this on the overlap; the "sharper test" claim is withdrawn. |
| m | MINOR | The pre-registered second half starts 2023-12-01 (on it F1 and F3 miss); the 2022-08-01 split was set after scouting numbers were seen. Label "1988-2004" is really 1993-02 on. The check against `synth_v1.json` proves calendar invariance only. About 45% of 2021+ days end on a print up to an hour after the equity close. Roll days off by up to 0.16 points on three hand checks. | Windows: all three now reported, bars read on the whole overlap (DEVIATIONS 15). The rest disclosed here. |
| n | NOTE (clean) | No look-ahead (independent rebuild matches to 1e-17; an extra day of lag changes nothing material). `xr_index` exact off roll days. All 22 markets mapped correctly. Exposure reproduced (3.09) and consistent with the fund's holdings (2.96-3.08). Yahoo's distribution error confirmed on a fresh pull; the $4.04 figure reproduces the prospectus's 2022 return; the fund site could not be reached. Only KMLM is replaced in the long panel. | |

## Review B: statistics and report. Verdict: the null verdict stands; four claims overstated
| # | Severity | Finding | Disposition |
|---|---|---|---|
| S1 | SERIOUS | "Three times the evidence / three times sharper" overstates: the joined sample re-uses addendum 57's years, and on the overlap the synthetic does not reproduce the real fund's small differences between neighbouring windows. | ACCEPTED. Claim removed; section 7 added. |
| S2 | SERIOUS | "All 26 moving-average forms behind" and "short windows t -2.7" rest mostly on the real years, which are in sample for the live rule; the group t is unadjusted and the groups post hoc. | ACCEPTED. Results now shown per stretch; t labelled unadjusted and post hoc. |
| S3 | SERIOUS | Deviation 2 named the whole overlap as the window and F1 fails there; the pre-registration then licenses "no faithful synthetic", not evidence. | ACCEPTED. The rebuilt years are reported as shape only; the verdict rests on addendum 57. |
| S4 | SERIOUS | Unreported by-product: the switch itself beats always-on, always-off and its mirror on the rebuilt years. | ADDED as section 5 (`v5_review.py`), recomputed on the corrected data. |
| M | MINOR | 2018 drawdown is in real funds, not a modelled leg, but the long panel carries a stale VXZ in 2018 (49.9% with a model VXZ, no holding changes). "Under water 2002-2008" was cut by the stretch restart. 16 points should be 17. "Within 0.5%" was log growth. Erratum paragraph omitted that long-window cells moved by up to 0.07 a year. | All corrected in the report. |
| N | NOTE (clean) | Joining the stretches is statistically sound (critical t 2.6-2.7 under every pooling); conditions 2-5 recomputed with no mismatch; commit order of the pre-registration holds. | |

## After the fix
The corrected loader, the re-run and the rewritten report were checked by a third reviewer (below).

## Second round, on the first fix and the rewritten report (commit 894d09af)

### Review C: the corrected loader. Verdict: not yet; two defects in the fix
| # | Severity | Finding | Disposition |
|---|---|---|---|
| C-B1 | BLOCKING | The fix dropped every session of a "23:00 row" year that has no such row: 124 sessions of sugar in 2023 (inside the fidelity window, +28.6% booked on one day), 102 of the JGB in 2021-22, 452 market-sessions from 2008. The published fidelity figures were understated; the whole-overlap F1 miss does not change. | FIXED (DEVIATIONS 13c): any day with a print is kept. Everything re-run. |
| C-S1 | SERIOUS | The selector compared percentage changes of the back-adjusted level, noise where that level is near zero or negative; the "unresolved" commodity years and every choice of reading (c) were artefacts of it, and (c) was partly tomorrow's close (gasoline 2010 and 2020, gilt 1994). | FIXED (13c): selector on the excess return; reading (c) removed; heating oil and gasoline now resolve (0.79-0.94). Left unresolved: the JGB (no independent close) and the gilt in 2009 and 2020. |
| C-S2 | SERIOUS | F4/F5 were not scored on the pre-registered second half. | FIXED (15b); shown in the bars table. |
| C-m | MINOR | Section 5 read as confirmation; stale joined-verdict fields remain in `long.json` (unused by the report); about 13% of market-sessions in 2008-2020 use a print stamped after the equity close (8-15 flag days either way); year-boundary splices are 1.8x noisier; copper's intraday prints are quantised 2014-2020; the Bund joins a month late (by the monthly reset). | Section 5 rewritten as a by-product; the rest disclosed here and in report section 9. |
| C-n | NOTE | The reviewer's own four corrected rebuilds and the first reviewer's three agree with the author's series on 99.3-99.8% of switch days in 2008-2020, give the same picture on the 62 variants (best t 1.0-1.9 against 2.65-2.80), and keep the switch-against-mirror result at t 2.25-2.61. Exposure, all bars and the long-run figures reproduced exactly. | |

### Review D: the rewritten report. Verdict: verdict stands, nearly every number reproduces; rewording required
| # | Severity | Finding | Disposition |
|---|---|---|---|
| D-B1 | BLOCKING (claim) | "The switch itself held up" was overstated: 2008 and 2020 carry 65% of it; without them t 1.1; against staying risk-on it is zero without 2008, when most of the tree's funds are models; the mirror row is the sum of the other two; "fairer read", "28%" and "re-rates" unsupported. | REWRITTEN as "by-product, not evidence" with those numbers (`v6_followup.py`), the post-2022-04 real-fund line and the edge-rule fields. KPI tile replaced. |
| D-S | SERIOUS | Wrong recovery date (sampled series) and missing unbroken-path low (81%, 2008-10); "late 2018" was the second-deepest fall; "agree with the real ones" too strong (rank correlation 0.2); the moving-average row of the resolution table was true by construction; "nothing fitted to the fund" ignored that the signal rule was inferred from holdings; verification block empty. | All corrected; daily paths now used for every date. |
| D-m | MINOR | Counts, duplicated names, euro date, missing 2024 diagnostic, wording, the VIX-model range, undefined terms, missing section 9 and 11 items. | Applied. |
| D-n | NOTE (clean) | Sections 3, 4 and 10, the bars table and the tiles reproduce; the placebo is sound (3 of 240 on the reviewer's design); the mirror t is not inflated by compounding. | |

## Third round
The second fix (13c, 15b) and the re-run were sent back to the two reviewers who had built their own
corrected series (A and C) for a delta check; result below.
Results of the third round (commit cfe38b1c):

- **Reviewer C on the second loader fix: it holds; no blocking or serious finding.** An independent
  rebuild matches the series to 6e-17 and the 62 long-run cells to 1e-17. No session with a print is
  dropped from 2008 in any market; every value comes from a row stamped the same day; the reviewer's own
  selector picks the same reading in every market-year; outside the JGB and the gilt no market-year
  2008-2023 looks stale or misdated. Every headline number reproduced (exposure, the bars on three
  windows, the long-run figures, the switch table, the follow-up checks). Minor, disclosed: the JGB's
  filled sessions in 2021-22 use a print about 15 hours after the Tokyo close (8.5% of notional, about
  1.5% of risk); the best-by-t variant on the rebuilt years differs from the live rule on only 30
  sessions; F5 on the 81-session window is 0.882 with ties averaged (0.888 as scored; both pass); two
  figures for the live rule on 2008-2020 (80.5% on the continuous path, 80.8% from a fresh start).
  Verdict: "fit to be reported as a better stand-in than the old one, read for shape only".
- **Reviewer D on the rewritten report: fit to send once three points were fixed**, all applied: the
  resolution table printed an upper-middle value instead of the median; "old high regained in 2010-09"
  held for only 15 sessions (now: touched 2010-09, held from 2012-03); the verification block was a
  placeholder. Wording minors applied. Every other number reproduced; no sentence leans on the rebuilt
  years as evidence.
