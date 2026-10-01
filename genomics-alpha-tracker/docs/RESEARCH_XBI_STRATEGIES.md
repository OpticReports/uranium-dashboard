# XBI strategy study — is there a better way to trade the sector ETF?

_Pre-registration `backend/research/xbi_strategies/PREREG.md` (frozen before
the first run) · engine `xbi_lib.py` · variants `run.py` · post-hoc combos
`combos.py` · tables rendered by `report.py` from `results.json` · charts
`figures.py`._

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
is the worst idea in the table (−14% CAGR, 86% DD), with the usual caveat
that the universe is survivors so the short leg is biased against — but
the loss is so large the bias is not the story.

What DOES change the ride is not timing XBI but **what sits next to it**:
an inverse-volatility mix of XBI, TLT and GLD (R1) has a 30% max DD against
XBI's 64% and the best Sharpe in the table (0.82), at 8.9% CAGR vs 11.9%.
It fails the rule only on the CAGR give-up. The post-hoc combos built
around it (labelled, in-sample) show the trade-off cleanly: lever R1 back
to XBI's volatility and you get XBI's CAGR with a 52% drawdown (C1a);
hold XBI at 50% with TLT/GLD inverse-vol around it and you get 10.9% /
42% (C1d). Both pass the rule on paper and neither is evidence — they were
chosen after looking.

## Read this first (one line each)

- In-sample on one 19-year path; XBI's two great drawdowns (2008: 38%, 2021-22: 64%) are two observations.
- Costs assumed, not measured: 5 bps/side ETF, 25 bps names, borrow 0.5% ETF / 3% names / 8% LABU-LABD, margin BIL + 1.5%.
- Shorts of the 32-name universe are survivorship-poisoned in BOTH directions: a loss proves little; a win would not be flattered. The universe is hindsight-selected either way.
- LABU/LABD real borrow spikes exactly when the decay trade hurts; P4/P5 are illustrations, not trades.
- TLT and GLD carried R1 through 2008-2012 and 2020; 2022 shows what happens when they fall WITH XBI (R1 DD 30% is that year).
- Post-hoc combos (C1x) are in-sample selection by construction.
- Never present any CAGR here as a forecast.

## Results

<!-- RESULTS:BEGIN -->
_Window 2007-09-04 → 2026-10-01 unless the start column says later. Costs per PREREG.md. Judge: max DD ≥ 10 pp shallower than XBI on the same window, CAGR within 2 pp, DD shallower in ≥ 2 of 3 sub-periods._

| id | rule | start | CAGR | max DD | Sharpe | Sortino | Calmar | underwater | worst yr | turnover/yr | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 | XBI buy & hold (benchmark) | 2007-09 | +11.9% | 63.9% | 0.52 | 0.74 | 0.19 | 2061d* | 2022 -25.9% | 0.1× | bench |
| B1 | SPY buy & hold | 2007-09 | +11.0% | 55.2% | 0.63 | 0.89 | 0.20 | 1773d | 2008 -36.8% | 0.1× | no |
| B2 | 50/50 XBI/BIL, monthly | 2007-09 | +7.8% | 38.5% | 0.56 | 0.81 | 0.20 | 1809d | 2022 -11.0% | 0.0× | no |
| B3 | 60/40 XBI/TLT, monthly | 2007-09 | +9.8% | 52.8% | 0.59 | 0.86 | 0.19 | 2061d* | 2022 -26.0% | 0.1× | no |
| T1 | close > SMA200 → XBI else BIL | 2007-09 | +6.3% | 55.7% | 0.39 | 0.56 | 0.11 | 2061d* | 2022 -30.2% | 8.3× | no |
| T2 | month-end close > 10m SMA → XBI else BIL | 2007-09 | +6.1% | 51.1% | 0.37 | 0.53 | 0.12 | 1960d | 2008 -18.3% | 1.9× | no |
| T3 | 12-1 momentum > 0 → XBI else BIL | 2007-09 | +8.4% | 57.8% | 0.45 | 0.64 | 0.15 | 2033d | 2016 -31.7% | 1.1× | no |
| T4 | dual momentum XBI/SPY vs BIL | 2007-09 | +9.6% | 49.2% | 0.50 | 0.71 | 0.20 | 1960d | 2016 -25.3% | 2.8× | no |
| T5 | XBI/SPY ratio > SMA200 → XBI else SPY | 2007-09 | +6.6% | 51.7% | 0.38 | 0.53 | 0.13 | 2019d | 2022 -24.8% | 25.4× | no |
| V1 | vol target 20%, cap 1.0 | 2007-09 | +9.0% | 47.1% | 0.52 | 0.75 | 0.19 | 1964d | 2021 -12.4% | 3.4× | no |
| V2 | vol target 20%, cap 1.5 (margin) | 2007-09 | +9.2% | 47.5% | 0.52 | 0.74 | 0.19 | 1964d | 2021 -12.1% | 5.2× | no |
| V3 | SMA200 gate × vol target 20% | 2007-09 | +6.0% | 37.3% | 0.43 | 0.62 | 0.16 | 1809d | 2022 -15.9% | 7.8× | no |
| D1 | de-risk as 1y drawdown deepens | 2007-09 | +8.0% | 39.8% | 0.48 | 0.69 | 0.20 | 1960d | 2016 -11.9% | 3.9× | no |
| D2 | buy the dip: 0.5 base, 1.0 while DD>20% | 2007-09 | +10.7% | 59.0% | 0.52 | 0.76 | 0.18 | 1960d | 2022 -25.9% | 0.6× | no |
| S1 | XBI Nov–Mar, BIL otherwise | 2007-09 | +5.5% | 50.8% | 0.36 | 0.52 | 0.11 | 2061d* | 2016 -21.0% | 2.0× | no |
| S2 | Nov–Mar and close > SMA200 | 2007-09 | +7.3% | 35.1% | 0.56 | 0.83 | 0.21 | 2061d* | 2022 -15.7% | 3.7× | no |
| M1 | RSI(2)<10 buy, exit >70 or 10 bars | 2007-09 | +5.2% | 43.3% | 0.37 | 0.53 | 0.12 | 2662d | 2016 -28.1% | 23.4× | no |
| P1 | long XBI / short β·SPY (60d, cap 1) | 2007-09 | +0.7% | 72.4% | 0.15 | 0.21 | 0.01 | 4094d* | 2021 -36.5% | 2.0× | no |
| P2 | long XBI / short IBB | 2007-09 | +1.0% | 41.9% | 0.14 | 0.21 | 0.02 | 3164d | 2021 -20.7% | 0.1× | no |
| P3 | long XBI / short XLV | 2007-09 | +1.5% | 67.5% | 0.18 | 0.26 | 0.02 | 2061d* | 2021 -37.4% | 0.1× | no |
| P4 | XBI + short 10% LABU + 10% LABD, monthly reset | 2015-06 | +5.1% | 64.1% | 0.31 | 0.45 | 0.08 | 2061d* | 2022 -26.3% | 0.1× | no |
| P5 | short 50% LABU / 50% LABD, daily reset | 2015-06 | -3.4% | 32.7% | -1.02 | -1.68 | -0.10 | 4139d* | 2025 -5.8% | 0.1× | no |
| N1 | XBI + short 5 worst 12-1 survivors, 10% each | 2016-09 | -14.1% | 86.1% | -0.50 | -0.67 | -0.16 | 3356d* | 2024 -34.2% | 2.9× | no |
| N2 | XBI + short survivors below SMA200 (50% total) | 2016-09 | -8.2% | 76.0% | -0.28 | -0.38 | -0.11 | 3356d* | 2021 -30.9% | 3.7× | no |
| R1 | inverse-vol XBI/TLT/GLD, monthly | 2007-09 | +8.9% | 29.7% | 0.82 | 1.20 | 0.30 | 1799d | 2022 -16.4% | 0.8× | no |
| C1a | inverse-vol XBI/TLT/GLD levered to 20% vol (cap 2.0, margin) | 2007-09 | +12.7% | 52.0% | 0.70 | 1.01 | 0.24 | 1896d | 2022 -27.6% | 2.0× | **PASS (post-hoc)** |
| C1b | inverse-vol XBI/TLT/GLD, XBI leg gated by SMA200 | 2007-09 | +7.4% | 24.9% | 0.72 | 1.04 | 0.30 | 1698d | 2022 -12.7% | 1.1× | no |
| C1c | equal thirds XBI/TLT/GLD (is R1 the assets or the sizing?) | 2007-09 | +9.7% | 34.6% | 0.78 | 1.12 | 0.28 | 1694d | 2022 -18.1% | 0.1× | no |
| C1d | XBI 50% + TLT/GLD inverse-vol 50% | 2007-09 | +10.9% | 41.7% | 0.72 | 1.04 | 0.26 | 1747d | 2022 -18.4% | 0.4× | **PASS (post-hoc)** |

_* still underwater at the window end. Post-hoc rows (C1x) were designed after the table above was read: in-sample selection, not evidence._

**Sub-periods (CAGR / max DD), the ride not the average:**

| id | 2007-09→2012 | 2013→2018 | 2019→2026-10 |
|---|---|---|---|
| B0 | +8.9% / 37.5% | +15.9% / 49.2% | +10.3% / 63.9% |
| B1 | +1.4% / 55.2% | +11.6% / 19.3% | +17.2% / 33.7% |
| B2 | +5.7% / 19.5% | +9.2% / 27.8% | +7.9% / 38.5% |
| R1 | +15.4% / 12.7% | +3.9% / 14.5% | +8.3% / 29.7% |
| D1 | +2.7% / 31.4% | +11.9% / 32.0% | +8.4% / 39.8% |
| S2 | +6.3% / 16.2% | +12.6% / 19.2% | +3.6% / 35.1% |
| V3 | -0.3% / 24.6% | +13.4% / 20.3% | +4.4% / 37.3% |
| T4 | +5.6% / 32.5% | +12.3% / 49.2% | +9.9% / 36.1% |
| C1a | +27.4% / 18.0% | +4.6% / 27.1% | +9.4% / 52.0% |
| C1b | +12.6% / 11.1% | +3.1% / 16.4% | +7.0% / 24.9% |
| C1c | +14.4% / 15.5% | +6.0% / 15.2% | +9.3% / 34.6% |
| C1d | +13.7% / 17.6% | +9.0% / 24.6% | +10.2% / 41.7% |

**Parameter maps (full window):**

- T1_sma: 100 → +4.1% / DD 57.8% / Sh 0.30; 125 → +4.6% / DD 68.3% / Sh 0.32; 150 → +6.5% / DD 57.7% / Sh 0.40; 175 → +5.2% / DD 61.7% / Sh 0.34; 200 → +6.3% / DD 55.7% / Sh 0.39; 225 → +7.6% / DD 49.4% / Sh 0.44; 250 → +7.2% / DD 46.6% / Sh 0.43; 275 → +6.3% / DD 51.6% / Sh 0.39; 300 → +6.6% / DD 55.5% / Sh 0.40
- V1_target: 0.150 → +7.6% / DD 37.8% / Sh 0.54; 0.175 → +8.2% / DD 43.4% / Sh 0.52; 0.200 → +9.0% / DD 47.1% / Sh 0.52; 0.225 → +9.7% / DD 51.8% / Sh 0.52; 0.250 → +10.1% / DD 54.4% / Sh 0.52
<!-- RESULTS:END -->

## Reading the table

- **Timing XBI does not work on this history.** T1 (SMA200) is the classic
  and it halves CAGR (6.3%) while leaving a 56% drawdown; the parameter map
  (SMA 100–300) never gets DD below 47% or CAGR above 7.6%. T2/T3/T5 are
  the same story with different lags. Dual momentum T4 is the best timer
  (9.6% / 49%) and still fails on both counts.
- **Vol targeting is a dial, not an edge.** V1 at 15–25% target traces a
  straight line from 7.6%/38% to 10.1%/54%: you choose the point, you do
  not beat the line. Sharpe is 0.52 at every setting — identical to buy
  and hold.
- **Drawdown-reactive sizing (D1) and seasonality-plus-trend (S2)** are
  the two overlays that get DD under 40% with Sharpe at or above XBI's,
  and both give up 4 to 5 pp of CAGR. S2 is in the market ~35% of the
  time; a folk pattern (JPM conference window) with a story attached.
  Candidates for out-of-sample watching, not rules.
- **Market-neutral XBI (P1) is near zero.** XBI's return since 2007 is
  almost entirely market beta plus the 2013-15 run; hedge out SPY and
  there is no alpha left (0.7% CAGR, 72% DD). The size spread (long XBI /
  short IBB, P2) and sector spread (P3) say the same thing.
- **Decay harvest (P5) loses** after 8% borrow on each leg: the
  volatility decay of LABU/LABD is real but smaller than what it costs to
  short them, and the 2020 and 2024 gaps are the tail.
- **R1 is the result.** Not because inverse-vol is clever (equal thirds,
  C1c, does nearly as well: 9.7% / 35% / Sharpe 0.78) but because TLT and
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

**Round 1 (2026-10-01, independent re-implementation): MATCH.** A second
implementation written from the spec (plain Python, no shared code)
reproduced B0, T1, R1 and S2 — CAGR, max DD, Sharpe and end value — to
1e-15. It confirmed decide-at-close-i / earn-i-to-i+1, the SMA/vol
windows, month-end holding, the 5 bps cost application and the stats
conventions; it noted the BIL→SHV→0 cash fallback never activates inside
the window and that the study starts one bar after the first SMA200 value
(immaterial).

**Round 2 (adversarial code review for lookahead / cost / calendar
defects): PENDING** — appended below when it reports. Until then the
table is "reproduced", not "reviewed".
