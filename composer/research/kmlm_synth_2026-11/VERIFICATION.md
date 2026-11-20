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
