# Deviations from PREREG.md (each recorded before the affected number was computed, unless it says otherwise)

Seen before the build (the scouting pass's rough first fit, 2021-03-01..2024-03-28, nothing tuned): daily
correlation with the corrected fund 0.871 (2023-01..2024-03: 0.920), switch-flag agreement 96.4% (98.1%),
monthly correlation with the published index 2008-03..2020-11 0.967, synthetic vol 13.9% vs fund 16.7%.
RYMFX on the same days: 0.612 and 86.9%.

1. **The one scalar is calibrated on the PUBLISHED INDEX, not on the fund.** Exposure = the least-squares
   slope (through the origin) of the index's monthly return on the synthetic's gross monthly return over the
   months before the fund existed where all 22 markets have data. So NO fund data is used to build the
   synthetic, and the whole fund overlap is validation. Stricter than the pre-registration.
2. **The fidelity bars are read on 2021-03-01..2024-03-28**, the days where the fund has 60 closes for its
   RSI and the futures files have data (they end 2024-03-28), and separately on the second part
   (2022-08-01..2024-03-28). The pre-registered halves (split at 2023-12-01, to the last close) cannot be
   scored: no roll-adjusted futures data after 2024-03 is reachable from here.
3. **The signal rule is inferred from the fund's published holdings, not from a rulebook** (none is public):
   a market's strength at the close of D is the average over the 21 sessions ending D-1 of the daily sign
   of (price above its 252-session simple average); the position is the strength times a fixed notional.
   The scout found this on 21 holdings files; the published text says only "a daily trend signal ... versus
   its long-term moving average ... executed in small increments over a period of several days".
4. **Notionals:** the published basket split (commodities 25%, currencies 32.5%, global bonds 42.5%), equal
   within a basket, reset on the first session of each month, times the one exposure scalar. Cash earns
   T-bills on all assets. Costs 0.90% (expense ratio) + 0.15% (the fund's own estimate of trading costs).
5. **The signal is read on each market's excess-return index** (the held contract's daily returns chained),
   the documented "synthetic price ... rolling forward futures contracts", not on a raw front-month price.
6. **The fund is measured on its corrected total return** (raw closes plus the distributions on the fund's
   page): Yahoo's adjusted close understates the 2022-12-28 distribution ($2.481 for $4.037692).
7. **Before a market's data starts, its basket is split among the markets that have data** (equal within
   the basket; basket shares unchanged). The index committee's actual historical market list is not public.
8. **How F4 and F5 are scored (written before either was computed).** Window: 2021-06-01 (the first day
   every variant's indicator exists on the real fund, as in addendum 57) to 2024-03-28; the second part
   (2022-08-01 on) beside it. The real-fund run uses the corrected total-return series (6). F4 "holds the
   same" = the same set of funds in the live rule's target that session; growth = the live rule's total log
   growth. F5 = Spearman rank correlation, across the 74 variants, of total log growth minus the live
   rule's. The synthetic is cut to the fund's own first day so both runs warm up on the same sessions.

## The long-history run: design fixed before it was run (2026-11-20)

Fidelity as scored: F2-F5 pass on both windows; F1 (daily correlation >= 0.90) is 0.874 on the whole
overlap and 0.907 on the second part. On the pre-registration's own reading (the later window) all five
pass; on deviation 2's whole-window reading F1 misses. So the long history is run and judged as
pre-registered, and anything that passes on it is a CANDIDATE to be ruled on by the independent
verifiers, not a settled finding. Seen before this run: addendum 57's stand-in years (2007-09..2020-12 on
RYMFX), where longer windows averaged +0.087 log/yr (t 1.6).

9.  **Panel.** `research/longrun/long_panel.build_long_prices()` (main mode `ts_synth`), with its KMLM
    series replaced by the synthetic (today's rules; exposure as calibrated; deviation 7 for markets with
    no data yet). The synthetic's calendar is the long panel's SPY sessions; it must reproduce the
    fidelity run's series on every later day (checked in code).
10. **Three stretches, never pooled across the model line.**
    REAL 2021-06-01..2026-11-19: the real fund (corrected total return), as addendum 57.
    REPLICATION 2008-02-01..2020-12-01: every one of the 22 markets has data and VIX-fund returns come
    from the real VIX term structure. (Leveraged and sector funds before their launch are their index
    times the leverage, as the long panel builds them.)
    MODEL 1991-04-01..2008-01-31: VIX funds are a model of futures that did not trade (before 2004) or of
    a curve fitted from the VIX alone (to 2006-07); the euro, JGB and Bund legs are missing for part of it;
    sector funds before 1998 are industry portfolios. Shown, with the two other VIX-model modes as a
    range; it cannot carry a verdict.
    1991 is as far as the VIX itself goes back (1990) plus the warm-up: 50 years is not reachable for THIS
    symphony because a third of its tree trades volatility funds.
11. **Cells.** The 62 switch-type variants. The 12 threshold variants (F3) are not run before 2021: their
    thresholds were calibrated on 1990-2020 data.
12. **Verdict rule** (the five conditions of addendum 57 on REPLICATION + REAL joined, 62 cells):
    (1) ahead, family-wise p < 0.10, max-statistic stationary bootstrap (mean block 10, 5,000 draws,
    studentised, centred); (2) ahead in REPLICATION and in REAL separately; (3) neighbours on its grid
    also ahead; (4) max drawdown no more than 5 points worse than the live rule's in each stretch;
    (5) still ahead at double cost. Also reported: each cell's MODEL-years result, the long (14-60) and
    short (3-8) window group averages per stretch, and the smallest gain the test could see.

## After the independent construction review (2026-11-20): a data defect, and the rule for fixing it

The review found the loader BLOCKING-wrong: `sdata.futures()` took the last row of each day, and in many
market-years the day's `23:00:00` row is the PREVIOUS session's close (CAD 2009-20, CHF 2010-20, heating
oil 2012-20, gasoline 2010-20, Canadian 10y, parts of copper, wheat, crude, corn, US 10y). It is staleness,
not look-ahead, but it corrupts the daily series the RSI reads in 2009-2020, mostly outside the window the
fidelity bars were scored on. Everything computed from the first build (out/fidelity.json, symphony.json,
long.json, extras.json as of commit 4b5652f7 and its report draft) is withdrawn.

13. **The loader's new rule, fixed here before it is run.** Per market and calendar year, three readings of
    the same files are built: (a) the `23:00:00` row of the day; (b) the last other print of the day;
    (c) the `23:00:00` row of the NEXT recorded day (a close stamped a day late). The reading used that
    year is the one whose daily returns correlate best, same day, with an INDEPENDENT daily close: Yahoo's
    front-month future for 18 markets; for the Canadian 10y, Bund and gilt the US 10y as fixed by this
    rule; for the JGB the US 10y of the day before (Tokyo closes before New York opens). Years with no
    reference (before about 2000) use (a). The real fund is never consulted. The table of choices and
    correlations is written to out/data_manifest.json, and any market-year whose best correlation is under
    0.5 is listed as unresolved.
14. **Not fixable from this data, disclosed (review S1):** the files hold December-only crude, corn and
    wheat and November-only soybeans, where the fund holds nearer contracts (47 of 154 market-dates differ
    on the fund's quarter-end filings). Those four are 9% of the notional. Effects under about 0.05
    log-points a year on the synthetic years are to be read as unresolved.
15. **Bars, corrected reading (review S3, minor 1).** The pre-registration's second half starts 2023-12-01;
    the 2022-08-01 split of deviation 2 was written after the scout's rough numbers had been seen. All three
    windows are reported (whole overlap, 2022-08-01 on, 2023-12-01 on). The bars are read on the WHOLE
    overlap; a bar that misses there is a miss.
13b. **A fourth reading was added after rule 13's first table was seen** (heating oil, gasoline and cattle
    still had years under 0.5): (d) per day, the filed close unless it sits nearer the previous day's value
    than the day's own last print, in which case the last print. The choice among the four is still rule
    13's (best same-day correlation with the independent close, per market-year); the fund is still never
    consulted. Left unresolved and listed in the manifest: heating oil 2016 and 2020, gasoline 2009, 2010
    and 2020 (best 0.30-0.41; the files hold a deferred contract and the reference is the front month), the
    JGB throughout and the gilt in 2009 and 2020 (no independent close; the US 10y is a weak reference).
13c. **The second construction review found rule 13's implementation still wrong; corrected here before the
    re-run (2026-11-21).** (i) A year read as "the 23:00 row" dropped every session that has no such row:
    124 sessions of sugar in 2023 (inside the fidelity window), 102 of the JGB in 2021-22, 452
    market-sessions from 2008 in all. Now any day with a print is kept (the chosen reading first, the
    other print otherwise). (ii) The selector compared percentage changes of the back-adjusted LEVEL,
    which is noise where that level is near zero or negative (gasoline 2020, heating oil 2016 and 2020,
    gilt 1987 and 1994); it now compares the excess return itself (change in adjusted price over the held
    contract's price). 13b's explanation of the "unresolved" years (deferred contract against front
    month) was wrong: on the right basis those years resolve. (iii) Reading (c), the next day's 23:00
    row, is REMOVED: where it was chosen it was an artefact of (ii) and on some days it was tomorrow's
    close. Readings are now (a), (b) and (d). The outputs of the build between 13b and this item
    (commit 894d09af) are superseded; the Holy Grail study of addendum 59 never read them, the sleeve's
    and the book's shape-only years did and are re-run.
15b. **F4 and F5 are also scored on the 2023-12 window** (81 sessions), as deviation 15 said all three
    would be.
