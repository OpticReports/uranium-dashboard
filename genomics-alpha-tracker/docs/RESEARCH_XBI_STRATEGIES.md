# XBI strategy study — is there a better way to trade the sector ETF?

_Pre-registration `backend/research/xbi_strategies/PREREG.md` (frozen before
the first run; round-2 amendments recorded at its foot) · engine
`xbi_lib.py` · variants `run.py` · post-hoc combos `combos.py` · tables
rendered by `report.py` from `results.json` · charts `figures.py`._

**Question (Casey, 2026-10-01):** "What about a strategy around XBI? Is there
a better way to trade it? Buy XBI and short several of the worst names, or
some other sleeve or strategy to improve DD or something else. Try many
variants and non-conventional ideas."

## Short answer

Under the frozen rule (cut max DD by ≥ 10 pp while giving up ≤ 2 pp of CAGR,
and be shallower than XBI in 2 of 3 sub-periods) **none of the 25
pre-registered variants passes.** Every single-ETF overlay on XBI — trend,
momentum, vol targeting, drawdown sizing, seasonality, mean reversion —
buys its shallower drawdown with 2 to 6 pp of CAGR, because XBI's
drawdowns are fast and its recoveries are V-shaped: a filter that is out
for the fall is also out for the first leg back. Shorting "the worst names"
is the worst idea in the table (−14% CAGR, 86% DD), with the caveat that
the universe is survivors so the short leg is biased against — but the
loss is so large the bias is not the story.

What DOES change the ride is not timing XBI but **what sits next to it**:
an inverse-volatility mix of XBI, TLT and GLD (R1), rebalanced monthly,
has a 31% max DD against XBI's 64% and the best Sharpe in the table
(0.76), at 8.2% CAGR vs 11.9%. It fails the rule only on the CAGR
give-up. The post-hoc combos built around it (labelled, in-sample) show
the trade-off cleanly: lever R1 back toward XBI's volatility (1.8× gross,
margin paid) and you get 11.3% with a 53% drawdown (C1a); hold XBI at 50%
with TLT/GLD inverse-vol around it and you get 10.2% / 43% (C1d). Both
pass the rule on paper and neither is evidence — they were chosen after
looking, and C1a clears the drawdown bar by 0.66 pp on an assumed margin
rate.

## Read this first (one line each)

- In-sample on one 19-year path; XBI's two great drawdowns (2008: 38%, 2021-22: 64%) are two observations.
- Costs assumed, not measured: 5 bps/side ETF, 25 bps names, borrow 0.5% ETF / 3% names / 8% LABU-LABD, margin BIL + 1.5%; positions carried and drift between rebalances, cost on the full move when they do (round-2 fix).
- Shorts of the genomics universe are survivorship-poisoned in BOTH directions: a loss proves little; a win would not be flattered. Only 9 of the 32 names are eligible at the start (31 by the end).
- LABU/LABD real borrow spikes exactly when the decay trade hurts; P4/P5 are illustrations, not trades.
- TLT and GLD carried R1 through 2008-2012 and 2020; 2022 shows what happens when they fall WITH XBI (R1's 31% DD is that year).
- Post-hoc combos (C1x) are in-sample selection by construction.
- Never present any CAGR here as a forecast.

## Results

<!-- RESULTS:BEGIN -->
_Window 2007-09-04 → 2026-10-01 unless the start column says later. Costs per PREREG.md. Judge: max DD ≥ 10 pp shallower than XBI on the same window, CAGR within 2 pp, DD shallower in ≥ 2 of 3 sub-periods._

| id | rule | start | CAGR | max DD | Sharpe | Sortino | Calmar | underwater | worst yr | turnover/yr | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | XBI buy & hold (benchmark) | 2007-11 | +11.9% | 63.9% | 0.51 | 0.74 | 0.19 | 2061d* | 2022 -25.9% | 0.1× | bench |
| B1 | SPY buy & hold | 2007-11 | +11.2% | 53.9% | 0.64 | 0.90 | 0.21 | 1555d | 2008 -36.8% | 0.1× | no |
| B2 | 50/50 XBI/BIL, monthly rebalance | 2007-11 | +7.5% | 39.0% | 0.54 | 0.78 | 0.19 | 1892d | 2022 -12.3% | 0.2× | no |
| B3 | 60/40 XBI/TLT, monthly rebalance | 2007-11 | +9.1% | 54.5% | 0.56 | 0.81 | 0.17 | 2061d* | 2022 -27.5% | 0.4× | no |
| T1 | close > SMA200 → XBI else BIL | 2007-11 | +6.2% | 55.7% | 0.38 | 0.55 | 0.11 | 2061d* | 2022 -30.2% | 8.4× | no |
| T2 | month-end close > 10m SMA → XBI else BIL | 2007-11 | +6.0% | 51.1% | 0.36 | 0.51 | 0.12 | 1960d | 2008 -18.3% | 2.0× | no |
| T3 | 12-1 momentum > 0 → XBI else BIL | 2007-11 | +8.6% | 57.8% | 0.46 | 0.65 | 0.15 | 2033d | 2016 -31.7% | 1.1× | no |
| T4 | dual momentum XBI/SPY vs BIL (hurdle 0 until BIL has 12m, 2008-05) | 2007-11 | +9.9% | 49.2% | 0.51 | 0.72 | 0.20 | 1960d | 2016 -25.3% | 2.8× | no |
| T5 | XBI/SPY ratio > SMA200 → XBI else SPY | 2007-11 | +6.5% | 51.7% | 0.37 | 0.53 | 0.12 | 2019d | 2022 -24.8% | 25.7× | no |
| V1 | vol target 20%, cap 1.0, 5pp band | 2007-11 | +8.8% | 47.7% | 0.51 | 0.73 | 0.18 | 1967d | 2021 -12.6% | 3.3× | no |
| V2 | vol target 20%, cap 1.5 (margin), 5pp band | 2007-11 | +9.0% | 48.1% | 0.51 | 0.73 | 0.19 | 1967d | 2021 -12.3% | 5.2× | no |
| V3 | SMA200 gate × vol target 20%, 5pp band | 2007-11 | +5.8% | 37.4% | 0.42 | 0.61 | 0.16 | 1809d | 2022 -16.0% | 7.8× | no |
| D1 | de-risk as 1y drawdown deepens, 5pp band | 2007-11 | +7.9% | 40.4% | 0.48 | 0.68 | 0.20 | 1960d | 2016 -12.8% | 3.7× | no |
| D2 | buy the dip: 0.5 base, 1.0 while DD>20% (drifts between flips) | 2007-11 | +10.8% | 60.2% | 0.52 | 0.75 | 0.18 | 1961d | 2022 -25.9% | 0.6× | no |
| S1 | XBI Nov–Mar, BIL otherwise | 2007-11 | +5.6% | 50.8% | 0.37 | 0.52 | 0.11 | 2061d* | 2016 -21.0% | 2.0× | no |
| S2 | Nov–Mar and close > SMA200 | 2007-11 | +7.5% | 35.1% | 0.57 | 0.84 | 0.21 | 2061d* | 2022 -15.7% | 3.7× | no |
| M1 | RSI(2)<10 buy, exit >70 or 10 bars | 2007-11 | +4.9% | 43.3% | 0.35 | 0.50 | 0.11 | 2662d | 2016 -28.1% | 23.3× | no |
| P1 | long XBI / short β·SPY (60d, cap 1), monthly re-level | 2007-11 | +0.3% | 72.7% | 0.13 | 0.19 | 0.00 | 2061d* | 2021 -37.3% | 1.5× | no |
| P2 | long XBI / short IBB, monthly re-level | 2007-11 | +0.7% | 45.0% | 0.12 | 0.17 | 0.02 | 3234d | 2021 -21.4% | 1.2× | no |
| P3 | long XBI / short XLV, monthly re-level | 2007-11 | +1.3% | 68.8% | 0.17 | 0.25 | 0.02 | 2061d* | 2021 -38.9% | 1.2× | no |
| P4 | XBI + short 10% LABU + 10% LABD, monthly reset | 2015-06 | +7.2% | 61.7% | 0.37 | 0.54 | 0.12 | 1963d | 2016 -22.0% | 0.7× | no |
| P5 | short 50% LABU / 50% LABD, daily reset (cost on every reset) | 2015-06 | -4.5% | 41.1% | -1.38 | -2.22 | -0.11 | 4139d* | 2025 -6.8% | 11.9× | no |
| N1 | XBI + short 5 worst 12-1 of the eligible survivors (9→31 names), monthly | 2016-09 | -13.8% | 85.7% | -0.45 | -0.61 | -0.16 | 3356d* | 2018 -29.2% | 4.6× | no |
| N2 | XBI + short eligible survivors below SMA200 (9→31 names, 50% total), monthly | 2016-09 | -10.3% | 80.8% | -0.33 | -0.44 | -0.13 | 3356d* | 2021 -33.3% | 4.9× | no |
| R1 | inverse-vol XBI/TLT/GLD, monthly rebalance | 2007-11 | +8.2% | 30.6% | 0.76 | 1.10 | 0.27 | 1853d | 2022 -17.2% | 0.9× | no |
| C1a | inverse-vol XBI/TLT/GLD levered to 20% vol (cap 2.0, margin) | 2007-11 | +11.3% | 53.2% | 0.64 | 0.92 | 0.21 | 1897d | 2022 -28.7% | 2.2× | **PASS (post-hoc)** |
| C1b | inverse-vol XBI/TLT/GLD, XBI leg gated by SMA200 | 2007-11 | +6.8% | 25.1% | 0.67 | 0.96 | 0.27 | 1714d | 2022 -12.9% | 1.2× | no |
| C1c | equal thirds XBI/TLT/GLD (is R1 the assets or the sizing?) | 2007-11 | +8.9% | 36.4% | 0.72 | 1.04 | 0.24 | 1703d | 2022 -19.5% | 0.5× | no |
| C1d | XBI 50% + TLT/GLD inverse-vol 50% | 2007-11 | +10.2% | 42.8% | 0.68 | 0.98 | 0.24 | 1778d | 2022 -19.8% | 0.7× | **PASS (post-hoc)** |

_* still underwater at the window end. Post-hoc rows (C1x) were designed after the table above was read: in-sample selection, not evidence._

**Sub-periods (CAGR / max DD), the ride not the average:**

| id | 2007-09→2012 | 2013→2018 | 2019→2026-10 |
|---|---|---|---|
| B0 | +8.5% / 37.5% | +15.9% / 49.2% | +10.3% / 63.9% |
| B1 | +1.8% / 53.9% | +11.6% / 19.3% | +17.2% / 33.7% |
| B2 | +5.1% / 20.1% | +9.2% / 27.2% | +7.3% / 39.0% |
| R1 | +13.8% / 13.0% | +3.8% / 14.5% | +7.8% / 30.6% |
| D1 | +2.7% / 31.7% | +11.6% / 32.8% | +8.2% / 40.4% |
| S2 | +6.7% / 16.2% | +12.6% / 19.2% | +3.6% / 35.1% |
| V3 | -1.0% / 24.7% | +13.4% / 20.5% | +4.4% / 37.4% |
| T4 | +6.2% / 32.5% | +12.3% / 49.2% | +9.9% / 36.1% |
| C1a | +23.9% / 18.6% | +4.3% / 27.4% | +8.8% / 53.2% |
| C1b | +11.2% / 11.0% | +3.0% / 16.5% | +6.7% / 25.1% |
| C1c | +12.6% / 15.9% | +5.8% / 14.4% | +8.7% / 36.4% |
| C1d | +12.1% / 17.9% | +8.9% / 23.6% | +9.5% / 42.8% |

**Parameter maps (full window):**

- T1_sma: 100 → +3.9% / DD 57.8% / Sh 0.29; 125 → +4.5% / DD 68.3% / Sh 0.31; 150 → +6.4% / DD 57.7% / Sh 0.40; 175 → +5.1% / DD 61.7% / Sh 0.34; 200 → +6.2% / DD 55.7% / Sh 0.38; 225 → +7.8% / DD 49.4% / Sh 0.45; 250 → +7.2% / DD 46.6% / Sh 0.42; 275 → +6.3% / DD 51.6% / Sh 0.39; 300 → +6.7% / DD 55.5% / Sh 0.40
- V1_target: 0.150 → +7.5% / DD 38.2% / Sh 0.53; 0.175 → +8.0% / DD 43.9% / Sh 0.51; 0.200 → +8.8% / DD 47.7% / Sh 0.51; 0.225 → +9.5% / DD 52.4% / Sh 0.51; 0.250 → +10.0% / DD 54.9% / Sh 0.51
<!-- RESULTS:END -->

## Reading the table

- **Timing XBI does not work on this history.** T1 (SMA200) is the classic
  and it halves CAGR (6.2%) while leaving a 56% drawdown; the parameter map
  (SMA 100–300) never gets DD below 47% or CAGR above 7.8%. T2/T3/T5 are
  the same story with different lags. Dual momentum T4 is the best timer
  (9.9% / 49%) and still fails on both counts.
- **Vol targeting is a dial, not an edge.** V1 at 15–25% target traces a
  line from roughly 7.5%/38% to 10%/55%: you choose the point, you do not
  beat the line. Sharpe is ~0.5 at every setting — the same as buy and
  hold.
- **Drawdown-reactive sizing (D1) and seasonality-plus-trend (S2)** are
  the two overlays that get DD to ~35–40% with Sharpe at or above XBI's,
  and both give up 4 to 4.5 pp of CAGR. S2 is in the market ~35% of the
  time; a folk pattern (JPM conference window) with a story attached.
  Candidates for out-of-sample watching, not rules.
- **Market-neutral XBI (P1) is zero.** XBI's return since 2007 is almost
  entirely market beta plus the 2013-15 run; hedge out SPY and there is
  no alpha left (0.3% CAGR, 73% DD). The size spread (long XBI / short
  IBB, P2) and sector spread (P3) say the same thing.
- **Decay harvest (P5) loses** once borrow (8% each leg) and the daily
  reset are paid: the volatility decay of LABU/LABD is real but smaller
  than what it costs to short them.
- **R1 is the result.** Not because inverse-vol is clever (equal thirds,
  C1c, does nearly as well: 8.9% / 36% / Sharpe 0.72) but because TLT and
  GLD were negatively or weakly correlated with XBI for most of the
  window. The honest statement is: "the cheapest drawdown reduction for
  XBI came from diversifying assets, not from timing it, and that
  depended on bonds and gold behaving as they did 2007-2020."

## What this does and does not say about the calls engine

The calls engine's 10-year replay (BACKTEST_CALLS_10Y.md) is ≈ sector beta
with a 65% drawdown, the same hole as XBI. Nothing in this study makes a
timing overlay on that book look better than it looked on XBI itself. If
the goal is a shallower ride, the evidence here points at the mix (what
the sleeve sits beside), which is a portfolio question, not an engine
question.

## Pending DD questions (ranked)

| P | question | what it moves | status |
|---|---|---|---|
| P1 | Is the goal a shallower ride at the SAME CAGR, or a better Sharpe at lower CAGR? The frozen rule assumed the first; R1 wins the second outright. | which row is the headline | asked 2026-10-01 |
| P2 | Is leverage on the bond/gold legs acceptable (C1a: 1.8× gross)? If not, C1a is off the table and C1d/R1 are the candidates. | whether any post-hoc row is actionable | asked 2026-10-01 |
| P2 | Should the trend/seasonal overlays get an out-of-sample watch (shadow log, no money) for 12 months? | turns S2/D1 from in-sample curiosities into a test | asked 2026-10-01 |
| P3 | Real borrow rates for LABU/LABD if the decay idea is ever revisited. | P4/P5 only | asked 2026-10-01 |

## Counter-agent verdict

**Round 1 (2026-10-01, independent re-implementation of the first
engine): MATCH.** A second implementation written from the spec (plain
Python, no shared code) reproduced B0, T1, R1 and S2 — CAGR, max DD,
Sharpe and end value — to 1e-15, confirming decide-at-close-i /
earn-i-to-i+1, the indicator windows, month-end timing, cost application
and the stats conventions.

**Round 2 (2026-10-01, adversarial code review): SHIP-WITH-FIXES, all
applied, numbers regenerated.** No lookahead found (each indicator checked
through bar i; an independent T1 recompute matched to 5 decimals; a
one-day-peek probe showed what a leak would look like: CAGR 32%). B0
reproduced from the raw cache (end value differs by exactly the one 5 bps
entry cost). Findings and what changed:

- SERIOUS: the first engine re-levelled every variant to its target DAILY
  at zero cost, so "monthly" labels were false and short-leg re-levelling
  (P2–P5, N1, N2) was free — worth ~1 pp/yr on the short rows and 10–30
  bps on B2/B3/R1. Fixed: positions are carried, rules decide when to
  trade, cost on the full move. The reviewer's own true-monthly B2
  recompute (7.51% / 39.0%) matches the regenerated row. No pass/fail
  changed.
- MINOR: N1/N2 universe is 9→31 eligible names, not 32 (row notes fixed);
  52-bar warm-up dead zone for T3/T4/D1 (start moved to 2007-11-15);
  3% single-name borrow was missing from PREREG (recorded).
- NOTE: month-end flag derives from the XBI calendar (no gaps present);
  partial first/last years now excluded from "worst year"; the cash leg
  trades free (consistent with PREREG's wording, ~1–2 bps/yr on T1/T5).

**Round 2b (re-check of the fix, same reviewer): MATCH, no lookahead.**
A dollar-holdings simulator written from scratch (carry positions,
month-end rebalance from drifted holdings, cost paid from cash)
reproduced B2 (7.465% / 39.02% / Sharpe 0.541) and R1 (8.155% / 30.62% /
0.763) to four decimals, and B0 from the raw cache to the one 5 bps entry
cost. Drift arithmetic confirmed (x(1+rₛ)/(1+rₚ), shorts sign-preserving,
cash implicit). Remaining NOTEs, none changing a verdict: post-trade
weights are understated by the day's cost factor on trade days (≤ 25 bps
of weight, those days only); C1a clears the 10 pp bar by 0.66 pp and only
at ~1.8× gross on BIL + 1.5% margin — a 1 pp wider margin spread would
plausibly flip it, which is one more reason it is a post-hoc curiosity;
the partial-year test is month-granular (not hit).
