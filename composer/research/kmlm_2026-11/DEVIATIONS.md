# Deviations from PREREG.md (each made before the affected result was read, unless it says otherwise)

1. **Tier B starts 2021-06-01, not 2020-12-02.** The KMLM fund's first close is 2020-12-02; the cells
   need up to 121 of its closes (the 120-day return in F4) and Wilder RSI needs 60. One start date for
   every cell keeps the family-wise test on one sample. Tier B is 474 sessions, A 902, pooled 1,376.
2. **Q4 also shows the cell with the highest t although it does not pass** (decided after q2 was read,
   so it is an ILLUSTRATION of the nearest miss at the book level, not a candidate and not a test).
3. **Tier C runs 62 of the 74 cells:** the pops/dips family (F3) is left out there, as the plan for C
   was the switch-type cells only ("for the shape of a surface").
4. **Knife-edge share is defined as:** the share of decision days on which the switch flag would differ
   with XLK's close 0.3% higher or lower (the pre-registration said "within one unit of the flip",
   which has no single meaning across RSI, moving-average and momentum forms).
5. **M4 uses FRED's broad dollar index (DTWEXBGS)** as pre-registered; no deviation. Recorded because the
   Yahoo dollar index was also fetched and is NOT used.
6. **G4 was run on four trees, not three:** the approved tree was added as a control on the request.
7. **After the independent review (statistics): the dollar state is lagged six sessions, not one.** The
   broad dollar index is released weekly. Its 21-session t went from 1.5 to 1.2; no verdict changed.
   The OFR stress index and the FRED series are the latest vintage (the stress index is revised after
   publication); this is disclosed, not corrected.
8. **q5_robust.py was added after the review:** the smallest gain the test could see, the longer and
   shorter windows averaged into one series per period, and tier C's family-wise p. It selects nothing.
9. **Tier C starts 2007-09-04, not 2007-02-22** (the stand-in fund's first close plus the 121 closes the
   longest indicator needs), for the same reason as deviation 1.
10. **"Worst month" in the book table is the worst of consecutive 21-session blocks** (last block
   shorter), not a calendar month and not a rolling window.
12. **After the independent review (simulation): every series ends 2026-11-19, not 11-20.** The 11-20 bar
   was fetched 29 minutes after the close and 12 of 24 tickers moved afterwards (up to 59 bp). One
   session shorter (1,375); no sign changed. Macro's sample ends the same day.
13. **F2.vote8-10-12 IS the live rule** on every session of tiers A and B (its flag equals the 10-day
   flag on 1,377 of 1,377 days). So 71 cells are distinct challengers, not 72; the trial count for
   multiplicity stays at the 74 declared.
14. **Tier C carries Yahoo's stale VXZ (and so a flat ZVOL) for 2018-01-25..2019-01-31.** Both sit in the
   VIX sleeve every cell shares. The reviewer re-ran tier C with the repo's modelled series: base CAGR
   50.6% -> 50.9%, largest change in any cell's difference 0.024 log-points, no sign change.
15. **Cost: 5.856 bps per unit of turnover as pre-registered; Composer's backtest implies 5.19 in this
   window.** That is the whole of the simulator's 3-point CAGR shortfall to Composer. The bias on a cell
   is 0.67 bp times its turnover gap to the live rule (at most 1.6% in total); no sign changes at 5.19
   or at zero cost (independent review).
11. **The overfitting probability is computed with the live rule as one of the columns** (75 columns:
   74 cells of which two are the live rule, plus the base). With one copy of the live rule it is 0.42;
   on the RSI windows alone 0.50 (independent review).
