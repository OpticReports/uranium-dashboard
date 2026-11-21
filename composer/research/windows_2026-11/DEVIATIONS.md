# Deviations from PREREG.md (each recorded before the affected number was computed, unless it says otherwise)

1. **G4 reads "fail" for HG on one fund and is accepted.** BIL shows 10 consecutive unchanged adjusted
   closes to 2015-10-19: a T-bill fund at a zero rate, not stale data. No other series trips it. Recorded
   after the gate ran, before any variant was simulated.
2. **The sleeve tree has 15 return-ranked picks, not the 16 the first tree dump suggested** (one of the 16
   filters ranks by volatility and is not varied). The cell list is unchanged.
3. **The sleeve's history was re-cut as the pre-registration's fallback clause requires.** The addendum-58
   synthetic missed its fidelity bar (and its first build had a data defect), so it is not cleared for
   2008-2020: the sleeve's verdict sample starts 2020-12-02 (real KMLM) and 1994-06..2020-12-01 is shape
   only (`w3_stats.py 2020-12-02`; sessions 6650 / 544 / 954). The matched thresholds were set on
   1994-06..2008-01 as registered; 2008-2020 is not claimed as out of sample for anything.
4. **The book's stretches** follow from that and from KMLM's own paths: shape only to 2020-12-01; then
   2021-06-02..2023-01-31 (KMLM and HG real, the sleeve part rebuilt); then 2023-02-02 on (all real). The
   124 sessions 2020-12-02..2021-06-01 are in no book stretch: addendum 57's real-fund paths start
   2021-06-02 (indicator warm-up on the new fund).
5. **A second significance bar is reported beside the pre-registered one (after the statistics review).**
   The studentised max-statistic bootstrap is inflated when some variants differ from the live rule on
   only a handful of days (a resample with few differing days has near-zero variance): the sleeve's bar
   came out at 4.19, and 10.3 on its 544-session stretch alone. Reported beside it: the Bonferroni bar
   (one-sided 10% over the engine's cells: about 2.85 for the sleeve, 3.06 for HG) and the bootstrap bar
   over variants with at least 75 differing days. A variant that cleared the Bonferroni bar and the other
   four tests would be reported as a candidate. None does. HG's bar (3.11) is unaffected.
6. **The hedge check was widened after the review**: the first version (the sleeve's average on the pair's
   worst 5% of days, 69 days) read as a hedge something that is merely uncorrelated. Added: the difference
   from ordinary days, the mirror (the pair's best 5%), the long history, the pair's unconditional 20-day
   return, and each of HG and KMLM alone.
