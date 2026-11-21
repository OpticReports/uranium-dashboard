# Pre-registration: a sleeve weight that moves with the market (2026-11-21)

Owner, 2026-11-21: "perhaps the sleeve weight alternates based upon where things are at ... when markets
are expensive, i.e. SPY's forward earnings are really high or the cape is really high, historically
speaking, then you would flip to something a little more conservative like the 50% sleeve weight. When
prices become lower ... switch to the lower sleeve weight and go more risk on ... Another one could be
switching based off the SMAs or the EMAs ... if it's really too high, relative on the 20 or the 50 ... you
might start to switch the sleeve weight after a certain point downward, and vice versa. Can you run some
tests ... specifically around maybe SPY or the QQs, oil prices, interest rates, cape."
Written before any state was joined to any return.

## What is on the record, and what is new
- Addendum 61 (today): thirty macro states as a switch to CASH and as a 15-point tilt toward the engine
  that did best: none passed; the book earned more in weak markets on same-close fills. Addenda 9 and 26:
  no valuation conditioning; a timing policy must beat a FIXED policy with the same average weight.
  Backlog, settled questions: overlays that de-risk the stress state are rejected as a class.
- New here: (a) the instrument is the SLEEVE WEIGHT (more sleeve = the defensive setting), not cash and not
  a data-picked engine; (b) the owner's direction is the opposite of the rejected class: be defensive when
  the market is expensive or stretched UP, risk-on when it is cheap or washed out; (c) states never tested:
  the level of valuation and of rates against their own history, oil's trend, and how far SPY and QQQ sit
  from their 20- and 50-day simple and exponential averages.
- The owner's sentence on the averages can be read two ways (stretched up -> more sleeve, or -> less).
  Every state is scored in BOTH directions, so the reading does not have to be settled first.

## The policy
The sleeve weight is HIGH (50%) while a state is on and LOW (15%) while it is off; the rest is split equally
between Holy Grail and KMLM; the book is set to those weights each session. The mirror is the same state
with HIGH and LOW swapped. A state read at close t sets the weights from close t+1 (one session to move
money between symphonies; POLICY's transfers settle the next evening); a two-session lag is reported too.
A switch costs 5.856 bps of the turnover.
**Benchmark: the book at one constant sleeve weight equal to the policy's own average weight** (addenda 9,
26). The policy's edge is the difference in yearly log growth against that book, and the change in the
deepest fall.

## States (0/1; "on" = the reading the owner calls expensive / stretched / tight; no threshold is tuned)
Data as of the session before, with the publication lags of addendum 61 (`macro_2026-11/mdata.py`).
| Family | Id | On when |
|---|---|---|
| VALUATION | V1 | CAPE above its 90th percentile of all history to date (addendum 61's V1; on nearly all of 2015 on) |
| | VA | CAPE above its own 10-year median |
| | VB | CAPE in the top third of its trailing 20 years |
| | V3 | stock earnings yield (1/CAPE) minus the real 10-year yield in its lowest quarter to date |
| RATES | RA | 10-year yield above its 5-year average |
| | RB | 10-year yield above its 1-year average |
| | R1 | 10-year yield up more than 0.50 over a quarter |
| | R3 | 10-year below 3-month (inverted curve) |
| | R7 | fed funds up more than 0.25 over six months |
| OIL | OA | WTI above its 200-day average |
| | OB | WTI up more than 25% over a quarter |
| | O1 | WTI up more than 50% over a year |
| STRETCH (SPY, QQQ) | SU.x.k.n | price more than its own 90th-percentile distance (trailing 5 years) ABOVE its n-day average; x = SPY or QQQ, k = simple or exponential, n = 20 or 50 |
| | SD.x.k.n | price more than its 10th-percentile distance BELOW it (washed out) |
| TREND | TA.x | x above its 200-day simple average; x = SPY, QQQ |
SPY is the S&P 500 index; QQQ is the fund from 1999-03 and the rebuilt series of the long panel before.

**Primary (9, corrected together):** VA, V3, RA, R1, OA, SU.SPY.s.50, SD.SPY.s.50, SU.QQQ.s.50, TA.SPY. All
others are a map. The two directions of a state are one test (two-sided).

## Samples
Verdict: 2015-06-01 on (a third of the book is the rebuilt KMLM fund until 2020-12; no sessions
2020-12-02..2021-06-01). Shape only: 1994-06..2015-05 (rebuilt and modelled funds). Real only: 2021-06 on.

## Tests, all fixed now (the lessons of addenda 61 and 62 built in)
1. Growth difference against the equal-average-weight book, and the change in the deepest fall.
2. p-values: (a) every circular shift of the state, (1 + count) / (1 + shifts), two-sided; (b) a
   Newey-West test (63 sessions) on the daily difference between policy and benchmark, because (a) is too
   generous for states tied to volatility. (b) is the one the verdict uses; Holm over the 9 primaries.
3. The same on the one-close-late paths (the execution bound), and with a two-session lag on the switch.
4. Without 2020 and 2022; number of separate regimes (on-spells under a quarter apart merged); switches a
   year; share of the edge from its best 20 sessions.
5. Per engine: what the sleeve earned less the average of the other two, state on against off (the policy's
   edge is exactly this spread times the weight gap).

## What counts
A state "works" only if, on the verdict sample and in ONE direction: growth above the equal-average-weight
book with a deepest fall no more than 1 point deeper, or a deepest fall at least 3 points shallower with no
less growth; Newey-West p < 0.05 after Holm over the 9 primaries; the same sign on the shape years; still
positive one close late and with a two-session lag; still positive without 2020 and 2022; at least 6
separate regimes. Anything short of that is a lead, reported with its sample, mirror and what it would
take. Eleven recent years cannot confirm a valuation or rates rule: those can at most be leads. Nothing is
built into a symphony, a weight or POLICY without the owner.

## Honesty box
In sample; none of it a forecast. CAPE has been in the top tenth of its history for nearly all of the
verdict sample, so "expensive against all history" can only be read on the rebuilt years. CPI is today's
vintage. Same-close fills in the engine paths. About 30 states, two directions, three samples: the
multiplicity is large and is corrected only across the 9 primaries. Measurement basis: daily mark-to-market.
