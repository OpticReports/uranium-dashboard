## What it is for

**Status: being closed.** Owner decision 2026-11-18; $36,546 withdrawn 11-19, a small stub left
until the tooling can run without it (`research/zvol_2026-11/MOVE_PLAN.md`). The same rule still runs
as the 25% VIX sleeve inside [KMLM](KMLM.md).

A community strategy picked from a sweep of 41 candidates as a "pure stabilizer" (add. 11), funded
2026-07-21 at a 15% target. Its saved description is the community author's: "a very simple strategy
that earns from VIX ... SPY RSI predicts whether to short or go long VIX Mid-Term Futures ETPs".

## Why each block is there

| Block | What it does | The reason on record | Source |
|---|---|---|---|
| Nine voters | Wilder RSI of SPY over 2 to 10 days, weighted 36 / 16 / 8 / 8 / 8 / 8 / 8 / 4 / 4 | The group is named "SPY RSI predicts VIX moves over different RSI time periods". No reason for those weights is recorded | tree; add. 56 |
| RSI under 25: ZVOL | Short mid-term volatility after an oversold close | "A rebound trade, not a carry trade"; the edge "disappears one close late" | add. 56 |
| RSI above 80: VXZ | Long mid-term volatility after an overbought close | The author's "short or go long"; the leg added 28 points in the real era | add. 56 |
| Otherwise PULS | Cash-like | | tree |
| "Black Swan Catcher" | UVXY RSI(14) above 70: PULS in place of ZVOL | "Surgical (35 of 812 ZVOL days), and it caught the one catastrophe": it kept the rule out on 2018-02-06 (-31%) | add. 31 |

The rule has no backwardation input and no credit input.

## What changed, and why

- **`XVtsDTV1`** (live from 2026-07-22): the only approved version. Two earlier saves (`J6evkY1V`, and
  `uQf3HrDb`, which ran on 07-21) are logically identical to it and to the community copy (add. 48).
  No logic change was ever made.

## Studied and not built

| Idea | Verdict | Source |
|---|---|---|
| HYG credit guard (no ZVOL when HYG falls more than 1% in a day) | approved in add. 12, **never saved**: see "Open items" | add. 12, 48 |
| Intraday HYG guard | "no meaningful edge" | add. 14 |
| Stand aside into long VXZ ("rider") | killed | add. 12 |
| Sizing on the variance risk premium or contango | no overlay | add. 25 |
| GARCH gates and sizers | no build | add. 31 |
| Vol targeting | Sharpe 2.11 to 1.87 | add. 21 |
| Exit when VIX is above VIX3M | killed: "its backwardation entries are the edge" | add. 39 |
| Skipping entries on inverted closes | watch item only | add. 54.4 |
| SVXY in place of ZVOL; dropping the VXZ leg; a carry gate | "no refinement recommended" | add. 56 |

## Known quirks and limits

- "Harvester" is a misnomer: carry is 0.06 of the ZVOL leg's 0.64 (add. 56 verification).
- ZVOL pays about 82% of its value a year in distributions. A payout lands in account cash, outside
  the symphony, if the rule sold between ex-date and pay-date ($1,970 on 08-19/20, add. 37-38).
  ZVOL is a $20.6M fund: payout-cut and closure risk.
- Live ZVOL fills ran a median 12.7 bps worse than the close (n 22) against a break-even near 11 bps.
- On the IBKR mirror every ZVOL buy has been discarded by IBKR (11-16 to 11-19).

## Numbers on record (in sample; none is a forecast)

- Live 07-22 to 11-17 (83 sessions): -$363 as displayed, +$830 with the stranded payout, against
  +$446 for T-bills on the same dollars (add. 56).
- Backtest 2023-04-19..2026-11-17: +23.2% a year, Sharpe 1.97, max drawdown 9.5%.
- Longer simulation net of 5 bps: 2010-2019 -1.8% a year; all years before ZVOL existed +8.9% a year,
  Sharpe 0.64; traded one close late, -0.1% a year (add. 56).
- "All in-sample; real ZVOL history is 3.6 years, chosen after the fact" (add. 56).

## Open items in the record

- **The name claims a guard no version has.** Addendum 12 records a guarded symphony as "built +
  saved"; addendum 48 found "no HYG condition in any saved version". Older documents call the UVXY
  test "the credit guard". It is not a credit test.
- The architecture doc (2026-08-31) says the voters are equally weighted and that ZVOL is held about
  6% of the time. The tree's weights are above, and addendum 56 corrects the second to "20% of days,
  mean weight 11%".
- No record links this symphony's id to the strategy inside KMLM, beyond "one rule held twice".
