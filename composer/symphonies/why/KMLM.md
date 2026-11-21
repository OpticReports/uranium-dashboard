## What it is for

The regime switcher: long tech, short vol, short tech or long bonds, decided by one comparison. "The
largest single source of book return and book variance" (architecture doc). Created 2026-07-05 from
the community "Simons KMLM switcher (single pops)" with 25% of it given to a separate VIX strategy.
Funded at the 07-07 window ($27,870, queued the day HG's $49,076 withdrawal executed) and the 07-08
window ($41,463, from the original's liquidation) (CHANGELOG 07-06, 07-07). Target weight 34.1% since 2026-11-18; before that
29% (07-22), 39% (set 07-20, its top-up cancelled by the owner) and 35% (07-06).

## Why each block is there

| Block | What it does | The reason on record | Source |
|---|---|---|---|
| Overbought scan | RSI(10) above 79-80 on any of eleven equity funds (75 for XLP): hold UVXY | The pops "fire on equity overbought signals, which historically preceded the vol spikes the original was harvesting with UVXY" | results.md first study |
| Dip-buys ("Combined Pop Bot") | RSI(10) under 30 on TQQQ, SOXL or SPXL (25 for LABU): hold TECL, SOXL, SPXL or LABU | No design reason is recorded. The SOXL branch "has no measured return (n 212, +0.14%/day, t 0.2 ...)" but removing it is worse in the rules' own years (2015-26), so it "stays as built" | add. 54.1 |
| The switch | RSI(10) of XLK above RSI(10) of KMLM: the two weakest of TECL, SOXL, SVIX; else the stronger of SQQQ, TLT | "Disabling the switch takes CAGR from +258% to -9%". Its "edge is concentrated on exact flag timing ... a design fact" | add. 33, 39 |
| 75 / 25 split | 75% switcher, 25% VIX sleeve | "Diversification beats modification": "better on every risk measure over every window tested", for about a third of the matched-window CAGR | add. 2 |
| VIX sleeve | The same nine-voter rule as HARV: see [HARV](HARV.md) | One rule held twice; this copy is unchanged by HARV's closing | POLICY "Allocation"; add. 56 |
| Threshold rebalance | Trades only when a holding is more than 10 percentage points of the symphony's own value from its target weight; the signals are still read daily | Inherited from the community original. Why it was kept when the crash sleeve went daily is not recorded | add. 4c; manifest |

## What changed, and why

- **`MVfHI8Og`** (saved 2026-07-06, the only approved version): the 75/25 pair, threshold rebalance
  with a 0.10 corridor. Against the unsplit original on the matched window from 2023-04-19: CAGR 323%
  to 230%, max drawdown 32.0% to 24.5%, Sharpe 2.34 to 2.44 (add. 2). What differs between the
  07-05 creation and this 07-06 save is not recorded. No logic change since.

## Studied and not built

| Idea | Verdict | Source |
|---|---|---|
| SPY 200d trend gate; full regime wrapper (copies A and B) | archived in `fixtures/rejected/` | first study |
| XLK trend gates, TQQQ drawdown breaker, vol cap on the rotator | not adopted | 07-05 study |
| Inverse-vol rotator, KMLM ballast, pop confirmation | not adopted | add. 2 |
| A fourth engine (WashSale3) | "do not fund" | add. 11 |
| Swap to "Simons IMPROVED" | identical to the original | add. 23 |
| Spreading the thresholds across tranches | not shipped | add. 24 |
| Rate-confirmation veto | rejected | add. 33 |
| SVIX to PULS when VIX is above VIX3M | "no measurable effect"; not adopted | add. 39 |
| Caps, vol targeting, VIX gates, 2x or 1x funds on the 75% leg | "nothing in the data says to resize" | add. 54.1 |
| Exit a leg on an overnight gap of -8% or worse | log line only | add. 54.2 |
| Another RSI window on the switch (3 to 60 days), with or without the ranked picks | none of 30 passes; 5 to 60 days cannot be told apart from 10 on 5.5 years | add. 57 |
| The same switch variants on a rebuilt KMLM fund, 1991-2020 (shape only: the rebuild missed one fidelity bar) | no variant distinguishable from the live rule on 2008-2020; does not contradict add. 57 | add. 58 |
| The switch as a moving average (price vs SMA/EMA 10-200, crossovers) or relative momentum | all 26 below the live rule in both periods | add. 57 |
| Pops and dips at 5, 7, 14, 20 days with frequency-matched thresholds; voting or splitting across windows | 11 of 12 below; votes and splits level with the live rule | add. 57 |
| A macro input to the switch (credit, financial stress, stock-bond correlation, dollar, curve, real rates) | none detectable as a predictor on 2010-2026; not built into the tree | add. 57 |
| Stripping the VIX sleeve | open owner decision | add. 56 |

## Known quirks and limits

- "The live thresholds sit on an in-sample performance peak ... textbook overfit signature" (add. 24).
  The original's advertised backtest starts exactly where its best year starts (add. 23).
- The record contains no hostile regime. Crash behaviour is "unresolved": -58% to +51% across six
  stand-ins for the 2020 signal (add. 34, 39).
- 2026-11-05: -26.7% in one session, a knife-edge at 15:54 that bought SOXL at 75% (add. 53, 54).
- On the IBKR mirror the sleeve's ZVOL buys are discarded by IBKR, so that part sits in cash there.

## Numbers on record (in sample; none is a forecast)

- Live 07-07 to 11-17: +30.8% (add. 56), with a 36% live drawdown
  (`research/zvol_2026-11/PREREG.md`).
- Live vs model to 2026-10-02 (window as in add. 36's table): +31.3% vs +31.6%, correlation 0.989.
- Backtest 2023-04-19..2026-11-17: +214% a year, max drawdown 37.6%
  (`research/zvol_2026-11/PREREG.md`). The repo's own caveat: this backtest is overfit and is not
  used as a forecast (add. 16, 24).
- Synthetic path 1995-2026: 80.5% a year with an 83.5% drawdown (add. 54.1).

## Open items in the record

- The architecture doc (2026-08-31) calls the VIX sleeve "VXZ/PULS"; the tree holds ZVOL, VXZ and PULS.
- Whether to strip the VIX sleeve now that HARV is closed (add. 56) is undecided.
