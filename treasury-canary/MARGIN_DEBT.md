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

## Long view (added after the chart shipped)

The chart's series now reaches back to the 1940s-50s via two splices, both
**context-only** (the playbook stats remain validated on the FINRA era):

- Margin leg: FINRA monthly (1997+) spliced onto **FRED:HNOSCIQ027S** —
  households security credit liability, $mm, quarterly, 1945-2015 (discontinued
  mnemonic). It tracks FINRA near-1:1 where they overlap (1997-Q1: $101B vs
  FINRA $103B). Points at/after the first FINRA month are dropped.
  While wiring this up we found the severity catalog's old "margin_debt" id
  (BOGZ1FL153166006Q) was actually *consumer credit as % of disposable income*
  — wrong series, wrong units. Config now points at HNOSCIQ027S.
- S&P leg: FMP ^GSPC daily (~1951+, paginated 5,000 rows/call, 24h cache),
  FRED SP500 (~10y) as no-key fallback. Excess YoY computable from ~1952.
- BTC: FRED:CBBTCUSD starts 2014 — no earlier price exists.
- NBER bands fetched from 1945 for the deep view (the shared bundle starts
  1976).
- YoY on the spliced series is DATE-matched with a 20-day tolerance — looser
  tolerances let series edges slip to an 11-month base and fabricate a YoY.
- UI: range chips (All 1946+ · 1971+ · 1997+ · 10y); overlays re-index to 100
  at the first month inside the selected window.

## Blowoff-peak study (75y, added 2026-07)

Hypothesis tested: "margin-YoY peaks in the 40-60% range reliably lead S&P
declines by 6-9 months." Method: all local peaks of the long margin-YoY series
≥35% (deduped to 18 episodes, 1949-2026) vs all >15% S&P drawdowns since 1951.

- **Hit rate: 8/17** peaks were followed by a >15% decline starting within 18
  months, vs a 28% unconditional base rate — blowoffs roughly DOUBLE the odds,
  nothing like a reliable trigger.
- **False positives include the two highest readings ever**: 1983-04 (+71.5%,
  nothing) and 1986-01 (+72.6%, S&P +29% the next 12m; the '87 crash came 19m
  later). Also fizzled: 1963, 1976, 1978, 1992, 2004, 2010.
- **Lead time when it hits**: 1-19 months, median ~9-10 (2000: 5m · 2007: 3m ·
  2021: 9m · 1972: 11m · 1968: 13m). Post-peak melt-ups are common (2021:
  +20% after the margin peak before the top) — selling on rollover forfeits
  the melt-up about as often as it dodges the bear.
- **Coverage (the strong side): 9/13** major declines were preceded by a
  blowoff, including every generational bear (1968-70, 1973-74, 2000, 2008,
  2022). Missed: 1962, 1966, 1990, 2020 (exogenous). Asymmetric truth: big
  bears almost always follow blowoffs; blowoffs produce big bears ~half the
  time.

Confirms the playbook framing: BLOWOFF is a risk-elevation dial (de-risk over
quarters), not a timing trigger — and the excess-vs-market cut exists exactly
because raw-YoY false positives (1983/1986) were margin keeping pace with a
ripping tape.

## Limits (stated on the tiles)

Three independent historical episodes; 12-month horizon (slow-burning); ~3-4
week publication lag; no monthly timing power; SPX leg of the excess gauge
uses FRED's SP500 series (~10y history), which bounds the excess series'
percentile window — status comes from the fixed thresholds, not percentiles.
