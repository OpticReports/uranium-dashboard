# Independent verification log: windows study of HG, the sleeve and the book (addendum 59), 2026-11-21

Two reviewers that did not write the code, in parallel, on commit 894d09af. Each read the real code and
recomputed from the stored daily paths.

## Review A: simulation. Verdict: no blocking finding; the cell paths can be relied on
- Two independent pandas evaluators (no shadow_runner or ksim logic) reproduce all 90 + 46 paths on both
  panels; the only differences are exact RSI ties between identical rebuilt funds in 1991-93 (11 HG cells,
  1-4 sessions each, same return).
- All 17 families diffed against the approved trees: only the named nodes change, on both window
  encodings; thresholds change only in the matched cells. No look-ahead in any flag.
- Four further read-only backtests on Composer itself, on forms the gates had not covered (native EMA
  5/10 with price below EMA 10; pick window 3; sleeve RSI windows 5-8; 5-day returns in the ladder):
  99.89% to 100% of sessions agree.
- Data: no stale runs in the real panels; the long panel equals fresh closes after launch; the KMLM chain
  at 2020-12-02 is clean; the sleeve's verdict sample starts 2020-12-02 as the fallback clause requires.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| A1 | SERIOUS (3 cells) | The sleeve's "matched" ladder-return variants are not matched: the live thresholds almost never fire on the proxy bond funds of 1994-2008, five of 13 rungs never fire and are switched off, and firing rates in the verdict years are off several-fold. | ACCEPTED as a labelling fault. The report now calls them "in effect a different ladder" and draws no conclusion on the one-day tests beyond "behind on every stretch, not distinguishably". |
| A2 | MINOR | Same thinness for the CORP test in the matched RSI-ladder variants. Cost constant about 15% above Composer's own (common to every variant). The ladder is active on 91 of 1,498 verdict sessions. `stat`'s max drawdown ignores the stretch's starting level (12.73% vs 12.79%). 26 and 24 long-panel sessions without a T-bill print are skipped. Before 1998 several rebuilt leveraged funds are the same series. About a fifth of HG's rebuilt sessions hold a fund before its launch. | Disclosed in report sections 3 and 6. |

## Review B: statistics and report. Verdict: every number reproduces; headline stands; four claims fixed
| # | Severity | Finding | Disposition |
|---|---|---|---|
| B1 | SERIOUS | "Is it still a hedge?" was not a fair reading: on the pair's worst days the sleeve earns about what it earns on any day (t 0.4), more on their best days, and less than nothing on the long history. | REWRITTEN (section 3, new verdict bullet, DEVIATIONS 6). The HG-only offset is reported as a candidate edge with its mirror and long-history check. |
| B2 | SERIOUS | The sleeve's bar of 4.19 is an artefact of variants that differ from the live rule on a handful of days. | ACCEPTED (DEVIATIONS 5): Bonferroni bar (2.84) and a restricted bootstrap bar (3.05) reported; the chart, the text and the smallest detectable gain use the sound bar. No verdict changes under any test. HG's 3.11 is sound. |
| B3 | SERIOUS | The EMA bullet omitted the family where EMA and SMA differ (both trend tests scaled). | ADDED. |
| B4 | SERIOUS | "About 17 points of book" contradicted the study's own book series (28% in July-August 2011); a 32% book fall in 2003-05 was unreported. | REPLACED with the book's own deepest falls. |
| B5 | MINOR | RSI and "should stay one-day" sentences overstated; missing candidate edges (IEF 14/20 on the long history, 10/30 crossover, the cash-test pattern, 37 of 89 ahead on modelled years); edge texts lacked concentration; engine-level p quoted for a book-level interval; family averages, the standardised t, the KMLM gap and the stretch moves undocumented; stretch names inconsistent; gates tile unclear; open questions and honesty items missing. | All applied (report sections 2-7; DEVIATIONS 3-6). |
| N | NOTE (clean) | Conditions 1-5 recomputed for all 134 cells with no mismatch; joining the stretches is harmless; block length and autocorrelation fine for HG; the book arithmetic and intervals reproduce. Cross-cell rank correlation of HG gains between stretches is 0.07 and -0.12: flat ground. | |
