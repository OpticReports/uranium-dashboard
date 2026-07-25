# Margin debt as a canary input — backtest notes

**Question** (2026-07): viral chart shows FINRA net credit balances at a record
−$1.06T. Is margin debt a leading indicator worth adding, and is it "the pin
that pricks the bubble"?

**Data**: FINRA monthly margin statistics 1997-01..2026-06 (debit balances in
margin accounts; free credit in cash + margin accounts), SPY month-end closes,
DGS10 monthly averages. Analysis script lived in the working session; headline
cells reproduced below.

## Findings

1. **Coincident at monthly frequency.** Margin-debt MoM vs S&P monthly return:
   r = +0.53 contemporaneous; every forward lag ≈ 0. No monthly timing power —
   margin debt is an *amplifier*, not a trigger. It is the powder, not the pin
   (the pin historically arrives via rates/funding/credit — the canary's other
   channels).

2. **Led every major top at cycle scale.** Margin-debt $ peak vs S&P peak:
   2000: −5m · 2007: −3m · 2015: −1m · 2018: −4m · 2021: −2m. YoY-growth peak
   led by −3 to −9m. Five episodes = consistent sign, not statistics.

3. **The validated signal is EXCESS growth** (margin YoY minus S&P YoY).
   Forward 12m S&P returns vs unconditional baseline (+8.3% mean, 24% neg):

   | Condition | n (months) | fwd-12m mean | % negative |
   |---|---|---|---|
   | margin YoY > +40% | 25 | −6.8% | 76% |
   | **excess > +25pp** | **17** | **−13.1%** | **94%** |
   | margin YoY < 0 (contraction) | 104 | +9.3% | 28% |
   | margin −10% off 12m high | 101 | +4.3% | 41% |

   The 17 excess-months cluster into ~3 independent episodes (1999-2000, 2007,
   2021) — treat n as 3, not 17. Contraction rows: by the time margin falls,
   forward returns are back above baseline. **Deleveraging is a buy-zone
   marker, not a sell signal.**

4. **The viral metric itself does NOT backtest.** Bottom-decile cash-coverage
   (credit/debit) months were all 2021-2026 and preceded *above*-baseline
   returns (+15.8% fwd-12m, 8% neg). The ratio trends structurally lower
   (portfolio margin, cash swept outside brokerage free-credit), so it sets
   "records" by construction. Coverage at the 2000 top: 0.56; at the 2007 top:
   1.04; June 2026: 0.29. The level regime shifts — the level is untradeable.

5. **Treasury linkage.** After forced-deleveraging months (margin MoM < −5%,
   n=27), the 10y yield fell −0.18pp over the next 3m vs ~0.00 unconditionally
   — equity margin unwinds produce a flight-to-quality Treasury bid. Exception:
   2022, when the positive stock-bond-correlation regime broke the hedge and
   yields rose through the unwind. Read the margin gauges jointly with
   `crossasset.stock_bond_corr`: high excess growth + positive correlation is
   the combination with no shock absorber.

6. **Reading at build time (June 2026).** Margin YoY +49% (96th pct), excess
   vs SPX +28.2pp (inside the 94%-negative cell), margin at its 12m high,
   coverage 0.29 (0th pct — but see finding 4). Structurally the March-2000 /
   March-2021 shape, on a 12-month horizon.

## What shipped

- `sources/finra_margin.py`: keyless monthly fetch of FINRA's xlsx (full
  1997+ history; 24h cache; stale-cache fallback).
- `crossasset.margin_excess_yoy` — **composite member** (category H).
  Yellow +15pp, red +25pp. The one cell that backtests.
- `crossasset.margin_yoy` — informational context (yellow +30, red +40), note
  encodes "contraction = historically a buy zone".
- `crossasset.margin_coverage` — informational, deliberately unthresholded;
  exists to defuse the recurring viral chart with finding 4.
- Severity index block A now prefers FINRA monthly margin (lag 36) over
  quarterly Z.1 security credit (lag 12), ~one quarter timelier.
- **Leverage Cycle chart** (`GET /margin/leverage` + `MarginLeverageChart`):
  full margin-YoY history (1997+) and excess-vs-S&P line with NBER bands, a
  five-state machine (checked in order: WASHOUT YoY ≤ −15% · SQUEEZE YoY < 0 ·
  BLOWOFF excess ≥ +25pp or YoY ≥ +40% · ELEVATED excess ≥ +15pp or YoY ≥
  +30% · NEUTRAL), and a prescriptive banner per state. Per-state forward-SPY
  stats (mutually exclusive monthly states, 1997-2026):

  | State | n (fwd12) | fwd-12m mean | median | % lower | worst |
  |---|---|---|---|---|---|
  | BLOWOFF | 27 | −7.3% | −11.8% | 78% | −37.4% |
  | ELEVATED | 35 | +1.6% | +5.5% | 31% | −44.8% |
  | NEUTRAL | 164 | +11.6% | +11.9% | 12% | −38.3% |
  | SQUEEZE | 62 | +11.7% | +14.0% | 21% | −36.8% |
  | WASHOUT | 42 | +5.8% | +10.5% | 38% | −28.2% |

  The post-crash read the chart exists for: WASHOUT = forced selling in
  progress (bimodal — bottoms form here but 38% of months had more downside);
  the transition to SQUEEZE = the leverage reset completing, forward returns
  back to full baseline. These constants live in
  `crossasset.LEVERAGE_PLAYBOOK` — if the state definitions change, recompute
  the table (script pattern preserved here + FINRA xlsx + SPY closes).

## Limits (stated on the tiles)

Three independent historical episodes; 12-month horizon (slow-burning); ~3-4
week publication lag; no monthly timing power; SPX leg of the excess gauge
uses FRED's SP500 series (~10y history), which bounds the excess series'
percentile window — status comes from the fixed thresholds, not percentiles.
