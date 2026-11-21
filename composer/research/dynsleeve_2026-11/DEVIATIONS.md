# Deviations from PREREG.md (dynamic sleeve weight study)

After the independent review (2026-11-21); everything re-run.
1. **Each direction has its own p and its own Holm correction.** PREREG called the two directions of a state
   "one test (two-sided)". They are not mirror images: a switch with no information loses about 0.005 a year
   to costs, so the losing direction looks more significant. The first draft attached the more-sleeve
   direction's p to less-sleeve leads; corrected.
2. **A fourth sample, 2015-06 to 2020-11**, added so that 2015-06 on can be read as its two parts (they
   cancel for the washed-out states). The all-real sample (2021-06 on) was registered but not shown in the
   first draft; it is now in the tables.
3. **Oil: the negative WTI print of 2020-04-20** blanked the 200-day average for 200 sessions; a missing
   print now takes the previous session's price.
4. **"Without 2020 and 2022"** re-averages the benchmark's weight on the days kept.
5. **The chart of running edges** uses each sample's own average weight (the first draft used one average
   over 1994-2026, which showed the static cost of holding more sleeve, not the timing).
6. **Registered checks, reported for the stretched-SPY lead and in the JSON for every state:** the time-shift p (too generous for states tied to
   volatility: the sleeve's gap to the other engines swings 27% more on stretched days), the share of the
   edge from its best 20 sessions, on-regimes and off-regimes.
7. **Not changed, disclosed:** QQQ states use the dividend-adjusted series (SPY states use the price index);
   regimes for the rule are on-spells, which under-counts states that are on most of the time.
