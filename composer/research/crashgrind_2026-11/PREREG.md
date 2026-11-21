# Pre-registration: can a crash be told from a grind? On volatility funds rebuilt from VIX futures (2026-11-21)

Owner, 2026-11-21: "okay do the research" (the open question of addendum 63: holding less sleeve while the
market is washed out paid in drawn-out bear markets and failed in the 2020 crash; is there a signal,
visible at the time, that separates the two?). Written before any file was parsed or any return joined.

## Why a rebuild comes first (CLAUDE.md: synthetic history before short samples)
The sleeve's crash payoff comes from UVXY and SVXY. They launched 2011-10; before that the long panel uses
a regression on the VIX and VIX3M (addendum 60: "volatility funds are models before 2011-10", and the
ladder "made nothing" on them in 2002-2011). So only the crashes since 2011-10 can test anything, and
2020 dominates them. VIX futures have traded since 2004 and the funds track a published, rules-based index
of them. Rebuilding the funds from the exchange's own settlement prices adds 2007-08, 2008-09/10, 2010-05
and 2011-08 as test cases. This is also the open item of addenda 58 and 60 ("exchange settlement data";
"rebuild UVXY/SVXY 2006-2011").

## Stage A: the rebuild
- Data: CBOE's daily settlement file for every monthly VX contract (cdn.cboe.com archive and
  market-statistics files). Nothing else.
- Index (S&P 500 VIX Short-Term Futures, as published): each day holds the first- and second-month
  contracts; a roll period runs from a monthly settlement Wednesday through the Tuesday before the next;
  at the close of the k-th business day of a period of dt days the first-month weight is (dt - k) / dt;
  the day's return is the change in the two settlements weighted at the previous close, over their
  weighted previous settlements. Total return adds T-bills.
- Funds: VIXY = index total return less 0.85% a year. UVXY = 2 x the index excess return (1.5 x from
  2018-02-28) plus T-bills less 0.95% a year. SVXY = -1 x (-0.5 x from 2018-02-28), same form. Before
  launch the launch-era leverage (2 x, -1 x) is used, the convention of the existing panel; today's
  leverage (1.5 x, -0.5 x) is reported beside it for the episodes.
- **Fidelity bars, set now** (synthetic against the real fund's adjusted close, every session both exist):
  A1 VIXY daily-return correlation at least 0.98. A2 VIXY log growth a year within 0.03 of the real fund's
  over the whole overlap and within 0.06 in every calendar year. A3 UVXY and SVXY correlation at least 0.97
  each and log growth a year within 0.08 overall. A4 on the 20 largest real VIXY daily moves, the
  synthetic's move is within 0.8 to 1.25 times the real one on at least 17. A5 the sleeve re-run on
  2011-11..2020-11 with synthetic UVXY and SVXY in place of the real ones holds the same funds on at least
  95% of sessions and its total log growth is within 10% of the real-fund run's.
  The existing regression model is scored on the same bars beside it. A missed bar is reported as missed,
  and the rebuilt years are then shape only (as in addendum 58).
- Not rebuilt: VIXM and VXZ (mid-term index, fourth to seventh month); they stay on the existing model.

## Stage B: the engines on the rebuilt funds
The long panel with UVXY, SVXY and VIXY replaced by the Stage A series from 2006-01 to each fund's launch;
the sleeve and Holy Grail re-simulated on it (KMLM does not hold these funds). Everything before 2006-01
is unchanged and stays a model of a market that did not exist.

## Stage C: crash against grind
Washed-out states, frozen from addendum 63: B1 S&P 500 in the bottom tenth (trailing 5 years) of its
distance below its 50-day average; B2 the same for the 20-day; B3 S&P 500 below its 200-day average.
Crash readings, fixed now (each on = "this fall is a crash"), all known at the prior close:
| Id | On when |
|---|---|
| D1 speed | the S&P 500 was down more than 10% over 10 sessions at some close in the last 21 sessions |
| D2 term structure | the VIX closed above VIX3M on at least 5 of the last 10 sessions (VIX3M from 2006-07) |
| D3 level | the VIX closed above 40 at some close in the last 21 sessions |
| D4 futures | the first-month VIX future settled above the second-month on at least 5 of the last 10 sessions (from Stage A; 2006 on) |
Primary: D1 and D2 on B1 (two tests, corrected together). The rest are a map.
1. **Episode table** (the core, descriptive): every separate washed-out episode since 2006-01 with its dates,
   depth, speed, which readings flag it, and what the sleeve and the other two engines earned in it.
2. **Day level**: the sleeve less the average of the other two on washed-out days, crash-flagged against
   not; Newey-West p (63 sessions); on 2006-01 on, on each of 2006-01..2011-10 (funds rebuilt from
   futures), 2011-11..2020-11 and 2021-06 on, and on 2006-01 on WITHOUT 2020.
3. **Policy**: sleeve 31.8% normally, 15% on washed-out days not flagged (a grind), 50% on washed-out days
   flagged (a crash); against the book at one constant weight equal to the policy's average; weights move
   one close after the reading; also one close late on the engine paths, and without 2020.

## What counts
The readings were written knowing what 2020 looked like, so 2020 proves nothing. A reading "works" only if:
the crash-flagged days' spread exceeds the unflagged days' on 2006-01 on WITHOUT 2020 (Newey-West p < 0.05
after correcting for the two primaries); the sleeve beat the other two in at least three separate flagged
episodes other than 2020; the policy beats its constant book without 2020 and one close late; and Stage A's
bars are met for the years those episodes sit in. Otherwise it is a lead, with its episodes listed. My
stated expectation before running: a handful of episodes cannot confirm a rule. Nothing is built into a
symphony, a weight or POLICY without the owner.

## Honesty box
In sample; none of it a forecast. A fund rebuilt from its index ignores what a real fund faced in a crash
(creation halts, tracking gaps at the close, the 2018-02 event that led to the leverage cut). Same-close
fills in the engine paths. Before 2006 nothing changes. Measurement basis: daily mark-to-market.
