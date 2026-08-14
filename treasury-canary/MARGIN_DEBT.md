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

### What separates real blowoffs from false positives (corroboration study)

Snapshot of macro conditions at each of the 16 scoreable peaks (FRED: GS10,
TB3MS, CPIAUCSL, UNRATE, BAA/AAA, USREC; plus our own excess and S&P series):

| condition at peak | bears (n=8) | fizzles (n=8) |
|---|---|---|
| curve slope (10y−3m, pp) | **1.00** | **2.54** |
| unemployment rate | **5.2%** | **7.4%** |
| S&P trailing 3y return | **+50%** | **+17%** |
| months since recession end | **47** | **22** |
| margin excess YoY (pp) | 32 | 30 (no separation) |
| CPI YoY / credit spread | ~equal | ~equal |

The story is one sentence: **false positives are early-cycle re-leveraging
after a bust** (steep curve, high-but-falling unemployment, un-extended
market, Fed easing — 1963/1976/1983/1986/1992/2004/2010), while **real
blowoffs are late-cycle speculation** (flat curve, low unemployment, extended
market, long expansion — 1967/1998/2000/2007). Same normalization-vs-
deterioration logic as the labor V/U conditioning.

Six pre-specified late-cycle flags (curve <1pp · Fed hiked >0.5pp/12m ·
expansion ≥48m · unemployment <5% · S&P 3y >+50% · excess ≥+25pp):

- **≥4 flags: 4/4 became bears** (1967, 1998, 2000, 2007)
- **≤2 flags: 4/12 became bears** (~the unconditional blowoff rate)
- Caveat: low flags ≠ safe — 1955/1972/1980/2021 were bears with ≤2 flags
  (2021's snapshot looked early-cycle because COVID reset the clock).
  High flags has no false positive yet, but n=4; treat "4/4" as ~65-85%
  (Laplace ~83%, wide small-n band), not certainty. Thresholds were chosen
  with the data in view — n=16 overfit risk is real even though each flag is
  macro-logical.

**2026-06 reading: 5 of 6 flags** (curve +0.81 · 74m expansion · unemployment
4.2% · S&P 3y +69% · excess +28pp; only missing fed_tightened — the Fed eased
−0.57pp over the past year). Today's configuration matches the 1967/1998/2000/
2007 cluster, not the fizzle cluster.

## Limits (stated on the tiles)

Three independent historical episodes; 12-month horizon (slow-burning); ~3-4
week publication lag; no monthly timing power; SPX leg of the excess gauge
uses FRED's SP500 series (~10y history), which bounds the excess series'
percentile window — status comes from the fixed thresholds, not percentiles.

## Fast-leverage nowcast study (added 2026-07)

Motivation: FINRA is monthly with a ~3-4 week lag and the state machine runs
on YoY, so a violent washout (e.g. the 2026-07 Korea/US deleveraging) reaches
the chart 1-2 prints late. The strip above the chart reads the FLOW — is
leverage being forced out right now — from faster legs.

**Legs.** COT: CFTC TFF leveraged funds, E-mini S&P 500, net position as % of
open interest (funds are structurally net short via the basis trade — raw sign
is meaningless; z-score vs trailing 156w, min 52w). VIX: 20-business-day level
change. Display-only (not scored): BTC-PERPETUAL funding + open interest
(Deribit; Binance/Bybit return HTTP 451 from US hosting), HY OAS Δ20d (FRED
now caps ICE BofA history at ~3y — discovered in this build; too short to
backtest, so it was dropped from the composite in favor of VIX).

**Pre-registration.** Rules and thresholds fixed before forward returns were
computed; evaluated ONCE (single variant, trial count 1, no tuning loop):

- FLUSH: vix20 ≥ +8 AND Δz(4w) ≤ −0.5
- WASHED_OUT: z ≤ −1.0 AND vix20 ≤ 0
- RISK_BUILD: z ≥ +1.0 AND vix20 ≤ +4
- CALM: otherwise

**Results** (2006-06..2026-07, 995 weekly obs; fwd S&P price returns; baseline
1m +1.4% med / 65% pos · 3m +3.7% / 71% · 12m +13.1% / 81%, worst −46.3%):

| state | weeks | episodes | 1m med (%pos) | 3m med | 12m med (%pos) | 12m worst |
|---|---|---|---|---|---|---|
| FLUSH | 5 | 3 | +7.4 (100%) | +2.2 | +7.5 (60%) | −7.5 |
| WASHED_OUT | 115 | 22 | +2.0 (63%) | +2.5 | **+15.6 (95%)** | −12.5 |
| RISK_BUILD | 134 | 16 | +1.5 (70%) | +3.7 | +12.9 (78%) | **−40.3** |
| CALM | 741 | 23 | +1.3 (64%) | +3.7 | +13.1 (80%) | −46.3 |

FLUSH episodes: 2015-09-15 · 2022-03-01/08 · 2025-04-08/15 — all near-bottom
capitulation weeks, hence the positive 1m forward: by the time BOTH legs
confirm, the flush is late-stage. FLUSH is therefore a "don't panic-sell"
state, not a sell signal. WASHED_OUT is the fast analog of the monthly SQUEEZE
re-entry zone, arriving 1-2 months sooner. RISK_BUILD does not time tops but
owns the study's worst left tail. 2008 began from CALM — the strip reads flow
stress, not slow-building cycles; that remains the monthly chart's job.

**Honesty box.** Weekly observations overlap; episode counts are the true n
(FLUSH rests on 3). One evaluation, but the *thresholds* (+8 VIX pts, −0.5 Δz,
±1 z) were chosen by judgment, not swept — still selection-adjacent. The strip
is deliberately unscored in the composite; it exists to sequence the monthly
signal, not replace it. Deribit OI history accrues from first deploy
(SeriesObs `deribit_btc_oi`, one snapshot/day).

**2026-07 reading:** CALM — the US institutional flush already ran in early
June (COT z hit −1.9 on 2026-06-02 = WASHED_OUT; e-mini OI −25% from the
June-16 peak, 2.58M→1.94M contracts);
positioning has re-normalized since (z −0.11 on 2026-07-21). The strip would
have shown the June washout in week one; the FINRA chart won't show the July
echo until the late-August print.

## 75-year stress-cycle × leverage-cycle matrix (added 2026-07)

The user asked for the same 70y depth behind the fast strip that the retail
chart has. Hard limit: the positioning leg cannot exist before 2006 (COT
leveraged-funds category; equity futures at all only from 1982). What CAN
extend: the stress leg — realized 20d vol of daily ^GSPC (FMP serves closes
from 1927; stats frozen on 1951+ to match the retail chart's record).

**Pre-registered proxy states** (mirror the modern thresholds; evaluated once):
rvol = 20d stdev of daily log returns, annualized; vz = z vs trailing 756
trading days (min 252, no lookahead); dv20 = rvol − rvol 20 days earlier.
SHOCK dv20 ≥ +8 · AFTERSHOCK vz ≥ +1 and dv20 ≤ 0 · COMPLACENT vz ≤ −0.75 and
dv20 ≤ +2 · NORMAL else. Weekly obs (every 5th trading day), crossed with the
monthly leverage state (data-date aligned, same convention as the playbook).

**Results** (3,803 weekly obs 1951–2026; baseline 12m median +10.3% / 74% pos
/ worst −46.3):

| cell | wk / eps | fwd 3m med (%pos) | fwd 12m med (%pos) | 12m worst |
|---|---|---|---|---|
| **COMPLACENT × BLOWOFF** | 152 / 30 | +0.5 (55%) | **−0.2 (49%)** | −33.5 |
| **COMPLACENT × WASHOUT** | 19 / 6 | −2.4 (32%) | **−19.6 (11%)** | −24.3 |
| **AFTERSHOCK × SQUEEZE** | 36 / 15 | +7.0 (81%) | **+22.7 (89%)** | −38.3 |
| **SHOCK × BLOWOFF** | 18 / 10 | **+6.2 (100%)** | +19.3 (71%) | −12.5 |
| NORMAL × BLOWOFF (today) | 396 / 34 | +2.7 (71%) | +6.6 (64%) | −41.0 |
| NORMAL × ELEVATED | 279 / 46 | +3.1 (68%) | +12.6 (87%) | −40.3 |
| NORMAL × SQUEEZE | 599 / 48 | +3.0 (68%) | +14.3 (83%) | −39.1 |
| AFTERSHOCK × ELEVATED | 20 / 7 | +2.0 (60%) | −3.1 (50%) | −46.3 |

(full 4×5 matrix frozen in routes_margin_fast.DEEP_MATRIX)

**Interpretation.** The quant story is coherent across both studies: vol
shocks mean-revert (SHOCK × BLOWOFF = climax weeks, 3m positive 18/18);
post-stress fading vol in a squeezed cycle is the re-entry cell; and the
DANGEROUS configuration is not the shock — it's the QUIET: complacent vol
sitting on a blown-off leverage cycle cuts 12m odds from 74% to 49% (median
−0.2%) over 30 distinct episodes, and complacency during a washout (the
bear-market lull) preceded further losses 89% of the time. Fragility hides in
calm, resolution comes through stress — the same asymmetry the modern
RISK_BUILD tail (−40%) showed at weekly resolution.

**Validation vs the modern composite.** On 2007–2026 overlap the proxy agrees
with the mapped COT+VIX state 53% of weeks — the proxy reads the stress half
only, so the two are complementary, not interchangeable (3 of the 5 modern
FLUSH weeks were SHOCK weeks — Mar-2022's VIX-driven FLUSH never moved
realized 20d vol by ≥8pts; corrected by adversarial QA). Live wiring: /margin/fast computes today's
stress state from FMP closes (FRED SP500 fallback) and the banner shows the
matching matrix cell vs the current monthly state, with baseline alongside.

**Honesty box.** Overlapping weekly windows; episode counts are the true n
(COMPLACENT × WASHOUT rests on 6). Thresholds chosen by judgment to mirror the
modern rules, one evaluation, no sweep — selection-adjacent, same standing as
the strip's other stats. Realized vol is price-derived, so state and forward
return share an instrument (vol clustering); the margin leg is the independent
conditioning variable. 2026-07-28 live reading: NORMAL (rvol 9.3%, vz −0.58,
Δ20d −7.8) × monthly BLOWOFF.

## Adversarial QA round (2026-07)

Two counter-agents independently recomputed both monitors from raw sources.
Retail monitor: 0 substantive diffs across 1,184 rows; fixes shipped for a
cold-outage staleness edge (state now nulled past 120 days), 1997 splice-year
YoY suppression (cross-source base distorted up to ~8pp), and a banner
footnote that conflated the FINRA-era playbook with the 75y peak study.
Fast strip: all 32 frozen stat blocks of FAST_PLAYBOOK + DEEP_STATES +
DEEP_MATRIX reproduced bit-for-bit; corrections shipped for DEEP_BASELINE
fwd3m (had been transcribed from the unrestricted 1929+ run: 2.5/63/−43.9 →
correct 1951+ values 2.6/66/−41.8), the Deribit funding window (the API caps
~744 hourly points per call, so the '180d' fetch actually returned ~30d — now
fetched in 30-day windows), a shared cache timestamp that froze the funding
history at process start, and CFTC stale-preferred caching. Standing caveats
confirmed and now documented in the tooltip: COT publishes Friday for Tuesday
data (~3 untradeable days inside every measured forward return), and matrix
pct_pos values are over forward-measurable weeks (smaller than n for 7 cells).
Boundary semantics (>=/<=) proven identical between study and live code;
live z rounding to 2dp changes 0 of 995 historical state calls.

## Usefulness evaluation of the prescriptive analytics (2026-07)

Pre-declared criteria, run once: a quoted stat is REAL only if its
episode-level bootstrap CI (2,000 resamples, episodes as the block unit)
excludes baseline — matrix cells additionally need Benjamini-Hochberg FDR
q=0.10 across all 20 tests; a claim is STABLE only if its vs-baseline
direction agrees in both split halves (75y: 1951-88 / 1989-2026; modern:
2006-16 / 2017-26); a prescriptive rule is USEFUL only if mechanically
following its action text at honest publication lags (FINRA +1 month, COT at
Friday close, vol state next day; idle cash earns TB3MS) improves MAR vs
buy-and-hold.

**(a) Significance.** Validated: modern WASHED_OUT (p=0.011, CI90 87-99 vs
81) and retail NEUTRAL best-regime (p=0.007, CI90 82-95 vs 76). Suggestive:
retail BLOWOFF (p=0.058, CI90 12-58 vs 76, 8 episodes), COMPLACENT×BLOWOFF
(p=0.06), AFTERSHOCK×SQUEEZE (p=0.067) — none survive FDR. FDR-significant:
only COMPLACENT×WASHOUT (p=0.002; all 6 episodes post-1989). Noise at 12m:
SHOCK×BLOWOFF (p=0.87). All four 75y states ALONE are baseline (p>0.74) —
the stress gauge only means something crossed with the leverage cycle.
Corroboration flags, exact 95% CIs: 4/4 → [0.40, 1.00]; 4/12 → [0.10, 0.65];
8/16 → [0.25, 0.75] — the "est. 65-85%" is inside the interval, but so is a
coin flip.

**(b) Split-half.** Stable: WASHED_OUT (94/95), COMPLACENT×BLOWOFF (47 vs 69
| 56 vs 80 — below baseline both halves). Unstable → DEMOTED:
SHOCK×BLOWOFF 12m (100% pre-89, 58% after) and NORMAL×BLOWOFF — today's live
cell — (75 vs 69 pre-89, 45 vs 80 after): its cautionary read is entirely a
modern-era phenomenon. RISK_BUILD halves disagree (87/72 vs baseline 81).

**(c) Decision rules** (CAGR% / MaxDD% / MAR):
| rule | result | verdict |
|---|---|---|
| buy-hold 1998-2026 | 7.38 / 56.8 / 0.130 | — |
| R1 BLOWOFF 0.5, ELEVATED 0.75 | 6.92 / 55.4 / 0.125 | FAILS |
| R2 BLOWOFF 0.0 | 6.67 / 56.3 / 0.119 | FAILS |
| buy-hold 2007-2026 | 8.85 / 56.8 / 0.156 | — |
| R3 RISK_BUILD 0.75 | 8.78 / 53.6 / 0.164 | PASSES |
| buy-hold 1951-2026 | 8.10 / 56.8 / 0.143 | — |
| R4 COMPLACENT×{BLOWOFF,WASHOUT} 0.5 | 8.32 / 56.8 / 0.146 | PASSES (CAGR +0.22pp) |

The retail BLOWOFF de-risk rules FAIL because the drawdowns land after
BLOWOFF ends — by the time margin YoY confirms the top, the state has rolled
to SQUEEZE/WASHOUT and the rule is fully invested again for the crash. The
BLOWOFF signal is a warning, not a timing rule, and its banner now says so.

**Product changes.** Every playbook state and headline matrix cell now
carries an `evidence` field rendered in the banners: VALIDATED (WASHED_OUT,
NEUTRAL), suggestive (BLOWOFF, C×B, A×S), UNPROVEN (FLUSH, WASHOUT-retail,
corroboration probabilities), DEMOTED (S×B "100% at 3m" headline, N×B
stability). RISK_BUILD's evidence notes the successful sizing rule.
Eval script: scratchpad eval_usefulness.py; results frozen in
usefulness_eval.json.

---

## Nowcast layer (2026-08-03) — estimating the months FINRA hasn't printed

FINRA publishes ~3-4 weeks after month-end, so the confirmed line is always
4-7 weeks stale. The panel now draws a DISPLAY-ONLY dashed extension:

- **Price model**: dlog(margin) ~ spx_ret + spx_ret_lag + d(realized vol),
  fit on the full FINRA history at runtime.
- **Schwab anchor**: Schwab files its Monthly Activity Report as an 8-K on
  SEC EDGAR ~2-3 weeks before FINRA prints, with a trailing 13-month table of
  client margin balances (app/sources/schwab_margin.py; keyless, official,
  fair-use UA, budgeted incremental backfill). When Schwab's print exists for
  an unprinted FINRA month, the estimate is precision-weighted toward the
  regression of FINRA-on-Schwab monthly changes.

### Honesty box (frozen pseudo-OOS backtest, 2026-08-03)

Expanding-window, every month predicted using only prior data; 140 scored
months ~2007-2026:

| metric | value |
|---|---|
| OOS R2 (monthly dlog) | 0.49 |
| direction hit | 74.3% |
| YoY-line error sd | 3.1pp (p90 abs 4.8pp) |
| state classification | 86.4% overall |
| state-TRANSITION months | **54.5% (18/33)** — the honest number |

Persistence scores 0% on transition months by definition, so the nowcast's
value-add is exactly there: it catches about half of regime turns a month
early. Misses cluster at band boundaries (SQUEEZE/NEUTRAL confusions
dominate). RULES: the nowcast never feeds the composite, the corroboration
flags, or the playbook — those run on confirmed prints only; the chip
renders the transition hit rate so the estimate is never mistaken for data.
