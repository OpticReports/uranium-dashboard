# Deviations from PREREG.md (forward-range study)

1. **Scenario G's shift is growth to growth** (fixed before any result was read): the S&P 500's daily log
   growth on the source less the daily log growth of +2% a year, so the shifted S&P compounds at 2.0%.
   PREREG's wording ("mean ... less 2% a year") left arithmetic-or-compound open; an arithmetic mean less a
   compound rate would have over-shifted by half the variance.
2. **The cap rule was changed after the first run, because the registered one distorts the comparison of
   sleeve weights.** PREREG: reset when any engine exceeds the LARGEST target plus 10 points. At a 40% or
   50% sleeve that is one cap of 50% or 60% for all three, so Holy Grail or KMLM can run from a 25-30%
   target to 50-60% before anything resets: the "50% sleeve" book then held far less sleeve than 50% and
   its median return came out no lower than the 31.8% book's. The main runs now use each engine's OWN
   target plus 10 points (at today's book 44.1 / 44.1 / 41.8, in effect POLICY's 44%). The registered rule
   is kept for scenarios B and D and shown beside it (same draws, so those rows ARE the first run: on B the
   median ten-year return was +120% / +119% / +119% a year at a 31.8 / 40 / 50% sleeve).
3. **Scenario G was registered as a planning scenario and came out close to the ceiling**: the engines'
   simulated returns are mostly not market beta, so a low-return decade for stocks moves them little. It is
   reported under its registered label, with that said.

## After the independent review (2026-11-21)
4. **Three scenarios added** (appended, so A-G keep their draws): Z "none of the edge" (k = 0 on the 2015-on
   source), H and I (the half and quarter haircuts on the 1994-on source). The review's point: the lowest
   registered scenario still assumed about +21% a year, and the haircuts sat only on the friendliest source.
5. **Scenario G relabelled "ceiling, shifted"** (PREREG called it a planning scenario): one average beta is
   a poor description of engines that switch between leveraged long, inverse and cash (the review measured
   half-year betas from -1.7 to +2.7), and the rebuilt 2000-2009 history is the better read of a
   low-return decade. PREREG's "range to plan on is D to G" is withdrawn; the report gives D, E, H, I and Z.
6. **Citations corrected.** Harvey and Liu (2015) describe the 50% rule of thumb and argue against it; they
   are not support for it. McLean and Pontiff (2016) is 26% lower out of sample and 58% lower after
   publication for 97 published predictors: "half" is a round number between them, not their finding, and
   not a backtest-to-live measure. Suhonen, Lennkh and Perez (2017) confirmed from secondary summaries.
7. **The live table's basis fixed**: Composer's deposit-adjusted series starts at the deposit, the
   simulation at the first close; the deposit day's move is now taken out. Rows added: each symphony since
   it held $10,000 or more, and the three together at the weights actually held.
8. **Added after review:** block-length sensitivity (5 and 63 sessions, D and E at 31.8%); Sharpe over
   T-bills in the source table; the share of return from the best 50 sessions and from 2020; the edge each
   engine keeps one close late and before 2015; the beta share on the 1994-on source (promised in PREREG).
9. **Not changed, disclosed:** the haircut is one constant per engine on every session, including the days
   an engine sits in cash; the reset is instant (POLICY stages it); one generator runs through the
   scenarios, so scenarios do not share draws.
