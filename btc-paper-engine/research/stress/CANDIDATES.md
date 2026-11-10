# CANDIDATES - pre-registered logic changes for a market meltdown (2026-10-07)

Registered AFTER the baseline and ATTRIBUTION.md, BEFORE any candidate run (PREREG "Improvement
candidates" rule: at most two, chosen from what actually hurt, tested on the three crash paths and
the normal eras, proposed only if the crash drawdown improves without lowering 2019+ fixed-base
$/yr by more than 10%). Both candidates attack mechanism 1 of ATTRIBUTION.md (pullback stop-outs in
the crash regime: -18.0k COVID / -19.9k 1999 / the 2008 DD window), the leading item of every maxDD
window. Neither touches the trend leg (the net earner on all three paths), the carry sleeve (never a
loser), the executor halts (never fired) or the S3 paper-book halt (open P1 key input). Nothing here
needs hindsight: both read only what the engine already has at the signal bar. Implemented as
`stress.Options` switches in `stress.py` (default OFF); production untouched.

## C1 - fast vol brake on the pullback leg's size (engine-side, next to `volsize.size_mult`)

Rule: for a pullback entry signalled on bar s, `m_fast = clip(v_ref / v_now, 0.25, 1.0)` with
`v_now = ATR14 / close` at bar s (the engine's own `Ind.atr14` at the SIGNAL bar; correction after
the refuters' pass: the pullback STOP itself is built from the FILL bar's ATR14, not the signal
bar's, so C1 reads the ATR one bar earlier than the stop it is meant to scale)
and `v_ref = median of ATR14 / close over the 2,190 bars ending at s` (the same 1-year reference
window as `volsize`; >= 90% valid else `m_fast = 1.0`, volsize's fallback). The leg's size is
`K x 1.5 x 0.70 x base x min(m_live, m_fast)`; the trend leg keeps `m_live`.

Parameters (fixed): floor 0.25 (the task's own example floor; it binds at `v_now >= 4 x v_ref`,
0.24% of bars 2019+, 0.56% 2017+); reference window 2,190 bars; min valid 0.9. No "zero" zone.

Why this measure: the live brake's sigma_now is a 180-bar (30-day) window whose ratio to its
reference never exceeded 2.59 on 2017-26 history (so its 0.50 floor is the whole brake) and which
reads 1.00 on days 1-2 of each crash. ATR14/close responds within two days and its ratio reaches
3.5 at p99 (2017+) / 6.4 at the max; `>= 2` on 5.6% of bars 2019+, `>= 3` on 1.0%.

Should move: the pullback's crash-regime stop-outs (COVID 10-08 and 11-12..11-26, 1999 10-08 x2 and
12-04/12-06, 2008 Aug-Sep) shrink toward normal-regime risk per stop; COVID / 1999 maxDD and the
12m balance improve; cost in normal eras = every pullback entry in an elevated-ATR period, winners
included (the pullback is a mean-reversion leg and some of its edge may sit in vol spikes) - the
2019+ $/yr cost is the number to watch.

## C2 - post-stop damper on the pullback leg (executor-side, in `mirror._leg_frac`, or engine-side)

Rule: after a pullback exit by the engine's STOP, a pullback entry within 5 days of that stop is
sized x0.5 (one stop) or x0.25 (two or more consecutive stops). A SIGNAL / TIME exit resets the
streak; an entry more than 5 days after the last stop resets it (full size). An executor HALT_*
flatten is not a STOP (it is not the engine's verdict) and leaves the streak unchanged.

Parameters (fixed): window 5 days = 30 bars, half the engine's 60-bar time stop and the gap between
the two modes of the pullback's post-stop re-entry gap on 2017-26 history (383 trades, 144 stops:
45% re-enter within 3 days, 47% within 5, 52% within 7, median 6.25 days); multipliers 0.5 / 0.25
(the floor equals C1's). Stop streaks on that history: 68 singles, 17 doubles, 8 triples, 4 of 4+.

Post-stop re-entry outcome by gap (added after the refuters' pass; 2017-26 engine pullback trades,
the population C2 acts on):

| gap from the last STOP to the re-entry | re-entries | won | win rate |
|---|---|---|---|
| within 1 day | 62 | 37 | 60% |
| 5 to 7 days (just outside C2's 5-day window) | 7 | 7 | 100% |

C2's x0.5 / x0.25 falls hardest on the within-1-day group, which wins 60% of the time: the damper
cuts winners more often than it cuts stops.

Should move: the second and third stop-outs of each crash cluster (COVID 10-08 and 11-26, 1999
10-08 20:00 and 12-06, 2008 10-07/10-08, 03-05, 08-08) are halved or quartered; cost = post-stop
re-entries that win (on 2017-26 history 47% of post-stop re-entries fall inside the window, and the
pullback exits 62% of its trades by SIGNAL/TIME rather than STOP) and the 2019+ $/yr.

## Both together

`m_pull = min(m_live, m_fast) x damp`: C1 and C2 compound on the pullback leg only.

## Grid (fixed before running)

- Crash: COVID / 2008 / 1999 x offsets -28, -14, 0, +14, +28 x {baseline, C1, C2, C1+C2}, K 0.75,
  variant A, intrabar, carry included (XBTUSD proxy), BTC funding modelled - the headline set-up.
- Normal eras (no splice, real history): E2 2017-01-01..2019-12-31, E3 2020-01-01..2021-12-31,
  E4 2022-01-01..2024-06-30, E5 2024-07-01..2026-07-31 (harness.ERAS) and 2019-01-01..2026-10-07
  (through the seed's last closed bar, 08:00Z) x the same four configurations, K 0.75, fixed base
  100,000, paper books seeded 100k/100k, real BitMEX XBTUSD funding on the book's positions, carry
  flat 30k (the candidates do not touch the sleeve and no halt fires on the baseline paths; the
  sleeve's P&L is identical across configurations, so it is left out of the $/yr).
- Reported per run: fixed-base $/yr = (BTC-book equity change) / years, max MTM drawdown (account,
  from 100,000; and BTC book from 70,000), executor halts, engine-book halts, trades, brake counts.
- Decision (PREREG): PROPOSE a candidate only if every crash path's maxDD (offset 0 headline, and
  the crash-path offset range) is no worse than the baseline's AND 2019+ fixed-base $/yr >= 90% of
  the baseline's. Otherwise DO NOT PROPOSE. The in-sample selection is stated in the result.

Not chosen, and why (from ATTRIBUTION.md): a trend-leg damper or brake (halves the winners that
follow the streaks; the trend is the earner on all three paths); a crash-mode daily-loss re-arm or
a drawdown-halt auto-resume (no executor halt fired in 83 runs: nothing to measure); a faster carry
disarm (the sleeve never lost); an account-level drawdown throttle (it would halve the COVID
recovery longs, +17.4k and +11.8k, that enter while the account is still 10%+ below its high-water:
a predictable failure of the $/yr test, not a measurement).

## Post-run findings (refuters' pass, 2026-10-07): the verdicts stand and are strengthened

Recorded after the grid; candidates.json `meta.honesty` carries the same points as text and
ADDENDUM.md item 7 summarises them. None of this re-opens the decision: all three stay DO NOT
PROPOSE.

1. **Venue reachability.** C1's floor 0.25 and any engine-side C2 cannot reach the venue as
   described: btc-executor clamps `size_mult` to [0.5, 1.0] (`mirror.py` `SIZE_MULT_MIN` /
   `SIZE_MULT_MAX`, L86; clamp at L1584-1588), so either needs an executor code change. With the
   clamp emulated (floor 0.5) the crash cells are COVID 116,537 / -20.92%, 2008 124,214 / -8.50%,
   1999 119,158 / -13.28% (12m / maxDD) and 2019+ 13,740 $/yr.
2. **C2 'executor-side' is not implementable.** `/exec/target` carries no exit reason and the
   executor cannot see engine STOPs it did not hold; C2 can only live engine-side, where (1) applies.
3. **The registered 2019+ cost yardstick is trend-dominated.** The S3 paper book (seeded 100k on
   2019-01-01) halts on 2020-03-20 and drops 266 pullback trades, so 2019+ $/yr barely sees the leg
   the candidates act on. With the pullback leg alive (`engine_halts=False`) the 2019+ ratios are C1
   91.6%, C2 88.9% (FAILS the 90% test), C1+C2 81.7% (FAILS). Pooled active eras E3+E4+E5 (6.58
   years; baseline 27,320 $/yr) against an exposure-matched uniform pullback cut as the control:
   C1 93.3% vs uniform 97.3%, C2 86.1% vs 94.9%, C1+C2 80.8% vs 92.4% - each candidate costs more
   than a plain cut of the same exposure.
4. **The exposure-matched control reproduces the crash gain.** The baseline with the pullback
   weight scaled to the candidate's bar-weighted gross pullback exposure (C1 at offset 0: 0.749
   COVID / 0.960 2008 / 0.624 1999): 12m uniform vs C1 119,846 vs 119,147 (COVID), 125,468 vs
   124,214 (2008), 122,842 vs 123,092 (1999); maxDD -18.63% vs -18.62%, -8.09% vs -8.50%, -11.66%
   vs -11.23%. The candidates are a pullback size cut, not a logic improvement.
5. **+/-30% parameter sweep, 8 variants** (C1 floor 0.175 / 0.325, reference window 1,533 / 2,847
   bars; C2 window 3.5 / 6.5 days, multipliers 0.35/0.175 and 0.65/0.325): DO NOT PROPOSE for every
   variant; C2's window parameter is inert (3.5 d and 6.5 d reproduce the registered 5 d crash
   cells).
6. **2019+ C1 decomposition corrected** (net of fees and funding): 18 resized pullback entries,
   -6,917 forgone on 15 winners / +2,407 saved on 3 stops (gross -7,066 / +2,372); the earlier
   -5.6k / +2.2k mixed bases.
7. **C1 text corrected** (section C1 above): the pullback stop uses the FILL bar's ATR14, not the
   signal bar's.
8. **Post-stop re-entry outcome by gap** (table in section C2 above): within 1 day 60% won (37 of
   62); 5-7 days after the stop 100% (7 of 7), on 2017-26 engine trades.
9. **Offsets worse / better than the baseline**, counted over all five start offsets next to each
   range-worst (the 1999 range itself uses its four crash-path offsets; also in the DECISION block
   of candidates.json as `offsets_worse_better`):

| candidate | path | range-worst maxDD base -> cand | close maxDD worse / better | intrabar maxDD worse / better | 12m worse / better |
|---|---|---|---|---|---|
| C1 | COVID | -22.0% -> -19.5% | 0 / 5 | 0 / 5 | 3 / 2 |
| C1 | 2008 | -10.2% -> -9.4% | 4 / 1 | 5 / 0 | 5 / 0 |
| C1 | 1999 | -16.7% -> -14.2% | 0 / 5 | 0 / 5 | 0 / 5 |
| C2 | COVID | -22.0% -> -21.7% | 3 / 2 | 3 / 2 | 4 / 1 |
| C2 | 2008 | -10.2% -> -10.4% | 2 / 3 | 3 / 2 | 4 / 1 |
| C2 | 1999 | -16.7% -> -17.7% | 2 / 3 | 2 / 3 | 2 / 3 |
| C1+C2 | COVID | -22.0% -> -18.8% | 3 / 2 | 3 / 2 | 3 / 2 |
| C1+C2 | 2008 | -10.2% -> -10.3% | 1 / 4 | 2 / 3 | 5 / 0 |
| C1+C2 | 1999 | -16.7% -> -13.5% | 0 / 5 | 0 / 5 | 0 / 5 |

   C1's 2008 range-worst improves (-10.2% -> -9.4%) while the candidate is worse on 4 of 5 offsets
   on close maxDD and on all 5 on intrabar maxDD and 12m: a range-worst is set by a single offset
   and is not a summary of the path.
