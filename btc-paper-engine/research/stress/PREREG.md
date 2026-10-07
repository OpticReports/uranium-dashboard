# PREREG — crash stress test of the live book (2026-10-07)

Registered BEFORE any scenario was run. Mandate (Casey, 2026-10-07): "Simulate
a Covid-like crash, a 2008 and a 1999 crash, say today. What happens to this
portfolio based on its current settings, guards and build? 3/6/9/12-month
balances, max drawdowns, and whether the logic should change for an incoming
meltdown." Nothing here changes any live config; proposals go to Casey.

## What is being stressed (the book as deployed, 2026-10-07)

| component | setting |
|---|---|
| engine blend | pullback (S3) 70% + trend (S4 donchian-20 / trail 5.0) 30%, lev 1.5 |
| executor size | KELLY_M **0.75** (primary) and 0.30 (the tripwire fallback); SIZING_BASE_USD 100,000 fixed; leg notional = K x 1.5 x w x base x size_mult |
| size_mult | engine vol target, down-only: clip(sigma_ref/sigma_now, 0.5, 1.0), `backend/app/volsize.py` |
| caps | MAX_NOTIONAL_USD 130,000; MAX_ACCOUNT_LEV 2.0 x base |
| daily-loss halt | equity < day-start - 6% x max(1, K/0.30) of base (15% = $15k at 0.75, 6% = $6k at 0.30); cancel all, flatten; auto-rearms at 00:00 UTC |
| drawdown halt | equity < high-water - 30% of base ($30k); flatten; MANUAL resume |
| engine book halts | the engine's own paper books halt one-way at dd_halt (S3 -30%, S4 -50% of their own $100k paper equity, fixed leverage 1.0, compounding) and stop publishing that leg |
| carry sleeve | $30k long spot UETH / short ETH perp; ON when 30d mean ETH funding >= 8%/yr, OFF < 5%; monthly resize if drift > 25%; margin guard unwinds within 15% of liquidation, 24h cooldown |
| fees | 4.32 bp/side on every BTC fill (measured live; intended-maker entries crossed 4 of 4); carry 7 bp spot + 4.5 bp perp per side |
| start | equity $100,000 (actual 2026-10-07: $100,031); BTC book FLAT (the executor is halted today; on resume it re-mirrors the engine), carry ON with 11.096 UETH / -11.096 ETH at $2,703.9 |

## Scenarios — the shape, played by BTC's own closest analogue

Equity-index crashes cannot drive this engine (it needs 4h BTC OHLC and
volume for its filters), so each scenario is BTC's nearest historical
analogue, spliced onto today's prices. Anchor = the pre-crash peak; the
crash starts "today".

| scenario | analogue window (12 months from anchor) | BTC move | ETH move | why it is the analogue |
|---|---|---|---|---|
| **COVID-like** | 2020-02-13 -> 2021-02-13 | -56% in 32 days, V-recovery, then the 2020H2 bull (months 6-12) | -64% | a liquidity shock: fastest crash in the data, fastest recovery |
| **2008-like** | 2021-11-09 -> 2022-11-09 | -77% over 12 months: slow bleed, a credit cascade (Luna, May-June), chop, a final failure (FTX, Nov) | -81% | deleveraging with institutional failures = Lehman shape |
| **1999/2000-like** | 2017-12-17 -> 2018-12-17 | -84%: bubble top, lower highs with bear rallies, capitulation | -94% | post-mania grind; dot-com's 31 months compressed into 12 |

Start-offset sensitivity (registered): anchor shifted by -28, -14, 0, +14,
+28 days (the crash begins in 2-4 weeks / today / we start already inside
it). Headline = anchor 0; the range is reported alongside.

## Splice method (fixed)

- History: real Bitstamp 4h bars through the last closed bar before the run,
  at least 2,400 bars (the vol target needs 2,370), so every indicator and
  the vol reference start from TODAY's actual state.
- Path: the analogue's 4h bars, O/H/L/C scaled by one constant per asset
  (today's close / anchor close) so returns are the historical returns;
  volume unscaled (the engine's volume filter is relative to its own 20-bar
  mean); timestamps continue today's 4h grid.
- Funding for the carry gate: BitMEX 8h funding for the analogue window
  (ETHUSD where it exists; XBTUSD as the proxy before 2018-08-02 - the only
  reachable source), annualised x 1095; trailing 30d mean; same 8/5 gate,
  coverage >= 0.5.
- Decisions use only bars at or before the decision bar (no look-ahead at
  the seam). The seam itself is a real discontinuity in volume regime and is
  disclosed, not hidden.

## Portfolio emulation (what the harness must do, in this order per bar)

1. engine: `research/cagr/harness.leg_trades` on the spliced bars gives each
   leg's trades (production code path); the engine's own paper-book halt is
   emulated on top (a halted leg publishes no further entries);
2. executor: exits first, then entries sized K x 1.5 x w x base x size_mult,
   clamped to the caps; mark to market at the close; the worst intrabar
   equity (open positions at the bar's adverse extreme) is also tested
   against the daily-loss and drawdown lines, since the executor polls every
   20 s, and a breach flattens at the breach level (fill assumed at the line;
   a gap through it fills at the open);
3. a flatten by the daily-loss halt re-arms at the next 00:00 UTC; a flatten
   by the drawdown halt stays flat to the horizon (variant A, the code) or
   for 7 days (variant B, "Casey resumes");
4. carry: the sleeve's funding income/cost, fees, and its on/off from the
   gate; its price P&L is zero by construction (spot and perp marked at one
   price; basis not modelled, disclosed); its equity sits inside the same
   account the halts measure.

## Outputs (fixed)

Per scenario x K: equity curve (total, BTC book, carry; benchmarks: hold
$100k BTC, cash), drawdown curve, balance at 3/6/9/12 months, max MTM
drawdown, worst UTC day, every halt / engine-book halt / carry gate flip
with its date and the equity at the time, fees paid, trade count. One chart
per scenario (equity + drawdown + events) and one summary chart.

## Improvement candidates — the rule

At most TWO logic changes, chosen AFTER the baseline run from what actually
hurt (not before), each tested on all three scenarios AND on the three
normal eras E3/E4/E5 (2020-21, 2022-24H1, 2024H2-26) so a change that only
helps in a crash is seen to cost something elsewhere. A candidate is
proposed to Casey only if it improves the crash drawdown without lowering
2019+ fixed-base $/yr by more than 10%. Nothing ships from this study.

## Honesty (standing)

Mark-to-market basis; in-sample history (the pullback was fitted on 2024-26,
the trend on 2013-21; the 2020 and 2022 analogues are inside the trend's fit
window); a stress test of three paths is not a distribution; the splice is a
construction, not a forecast. Every number is an upper bound on what the
live book would do.
