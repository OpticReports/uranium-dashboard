# RESEARCH_FUNDING.md — D3: perp funding & dated-futures basis vs the live stack (2026-08-19)

**Status: descriptive study, ZERO trials added to the registry (~1,622 unchanged).
No candidate was run; NO H4 pre-registration was written (§5 — evidence too weak).
Counter-agent verification of this study: PENDING (repo convention: required
before any finding here is acted on).**

## 0. Verdict (results first)

| book | question | answer |
|---|---|---|
| **S3** | does the pullback edge survive funding-adjusted accounting? | **YES — funding is ~neutral for S3.** Full-window counterfactual funding is a small net CREDIT (+$7.5k vs ±$0 strategy P&L; entries are counter-cyclical, longs bought when funding is depressed). Modern era 2022→: drag < 30 bp/yr of equity; MAR 0.86 → 0.84. Dated-future roll drag ≈ 2 bp of equity per trade (S3 is long only ~10% of bars). |
| **S4** | does the drought or the edge change under carrying costs? | **Edge survives, smaller; drought conclusion UNCHANGED (slightly worse).** 2016-07→now perp counterfactual: funding = **−20.0% of closed P&L** (CAGR 51.7% → 34.0%). Modern era 2022→: +152% → +124%, MAR 0.44 → 0.37 — still positive both ways. Drought window 2024-03→now: funding −$202k on top of −$1.86M strategy P&L (−124 bp/yr of avg equity) — funding-adjusted accounting makes the drought ~11% deeper, it does not rescue or explain it. |
| **S5** | blend | **Survives.** 2022→: +298% → +276%, MAR 1.50 → 1.36; full-window CAGR 22.2% → 18.0%. Drought window +42.5% → +40.3%. |
| — | was the S4 drought a funding-regime artifact? | **NO.** Funding during the drought sits at the **46th percentile** of 10.2y history (mean +0.53 bp/8h vs +0.74 full-sample); no prior study's conclusion (D1 longest-drought, H1/H2 rejections, retirement-trigger status) changes. |
| — | is there a fundable H4 hypothesis? | **NO — nothing registered.** The only real pattern (very negative funding → strong forward returns) is concentrated in 2016-2019 and nearly absent since (§4); our trades' outcomes are ~independent of funding regime. |

**Live-venue translation:** the live book trades **BIP-20DEC30-CDE, a DATED
future — it pays no funding at all**; the relevant carry is basis/roll. Front-
quarter annualized basis (BitMEX proxy): 2024 +10.1%, 2025 +5.7%, 2026 +2.4%
(§3). With S3 long only ~10% of bars and S4 long/short balanced (46%/47%), net
roll carry is small and partially self-hedging: measured on our trade log, a
dated-future S4 would have paid −$748k on longs and EARNED +$860k on shorts
(shorting a contango future earns the basis). The spot-basis backtests are
closest to the truth for the CDE product in today's 2-3% basis regime; the big
perp-funding drags above are the counterfactual we do NOT pay.

## 1. Data (Job 1) — what was fetched, integrity

- **Binance (the brief's primary) and Bybit are GEO-BLOCKED through the session
  proxy** (Binance: "restricted location"; Bybit: CloudFront country block).
  Documented, not worked around.
- **Primary: BitMEX XBTUSD perp funding** — public, keyless. **11,206
  settlements, 2016-05-14 → 2026-08-19 (10.3y)**; 8h interval from 2016-06-04
  (21 daily-interval settlements before that, excluded from analysis); 15
  non-8h gaps (all documented in `integrity_report.json`); mean +0.89 bp/8h,
  median +1.00 bp, 70.8% positive; 170 settlements at the ±0.375% clamp; range
  −0.68% to +1.125% (pre-clamp-regime-era extremes).
- **Cross-check: Deribit BTC-PERPETUAL** — 63,951 hourly records 2019-04-30 →
  now. Daily-sum agreement vs BitMEX over 2,581 common days: **corr 0.86, means
  +1.9 vs +2.1 bp/day, sign agreement 78%** — the BitMEX series is not a venue
  artifact at the daily scale.
- **Cross-check 2: OKX BTC-USDT-SWAP** — public depth only ~3 months (280
  settlements). Corr 0.30 vs BitMEX on 92 days — weak, but the overlap window
  is a near-zero-funding regime (means 0.2-1.1 bp/day, mean abs diff 1.9 bp);
  disclosed as a limited check.
- **Basis proxy: BitMEX dated XBT quarterlies** (all H/M/U/Z contracts
  2016→2027, daily closes + expiries) vs the .BXBT composite index; **3,858
  front-quarter days 2015-12 → 2026-08** (7 ≤ DTE ≤ 200). Spot sanity: .BXBT vs
  our Bitstamp daily close — mean abs diff 5.6 bp, p99 88 bp (2017 era).
- Raw + cleaned CSVs in the study scratchpad: `funding_bitmex.csv`,
  `funding_deribit.csv`, `funding_okx.csv`, `basis_front_quarter.csv`,
  `spot_daily.csv`, `integrity_report.json`, fetch/clean scripts
  (`fetch_funding.py`, `clean_funding.py`).
- **≥4y requirement: met** — 10.3y of 8h funding from one venue, 7.3y
  corroborated by a second. Pre-2019 rests on BitMEX alone; pre-2016
  unavailable anywhere. Nothing was interpolated.

## 2. Measured funding P&L (Job 2) — engine replay, per-trade counterfactual

**Estimator (stated once):** engine code path (`run_replay` semantics, frozen
S3/S4 configs, research fees, cash_apy 0), continuous run **2016-07-01 →
2026-08-19**, dd_halt disabled for BOTH books (disclosed: run verbatim, S3's
dd_halt=0.30 fires 2017-06-26; S4 never halts in this window — same D1
convention, both-ways disclosure). Funding counterfactual: at every BitMEX
settlement (04/12/20 UTC = 4h bar closes) an open position pays/receives
`rate × qty × settle-bar close`; **longs pay when funding is positive**.
Funding-adjusted curve compounds per-bar strategy return + funding return.
S5 = per-bar constant-mix 75/25 @1.5x (the s4_batch estimator), funding scaled
by the same weights/leverage.

| | S3 | S4 | S5 blend |
|---|---|---|---|
| trades (L/S) | 385 (212/173) | 267 (141/126) | — |
| closed strategy P&L | −$5.5k | +$6.71M | — |
| counterfactual funding | **+$7.5k** | **−$1.34M** | — |
| funding as % of closed P&L | n/m (P&L ≈ 0) | **−20.0%** | — |
| funding as % of gross wins | +1.8% | −4.2% | — |
| long-side funding | +$5.1k | −$1.55M | — |
| short-side funding | +$2.4k | +$0.21M | — |
| CAGR unadj → adj (2016-07→) | −0.6% → +0.4% | 51.7% → 34.0% | 22.2% → 18.0% |
| maxDD unadj → adj (MTM) | −78.8% → −76.3% | −53.8% → −56.8% | −52.3% → −55.6% |
| 2022→ ret unadj → adj | +125% → +123% | +152% → +124% | +298% → +276% |
| 2022→ MAR unadj → adj | 0.86 → 0.84 | 0.44 → 0.37 | 1.50 → 1.36 |
| worst single-trade funding | −$463 (2016 S; −46 bp of notional) | **−$151k** (L 2024-01-26, 233 bars, −262 bp of notional, −2.6% of equity) | — |
| worst relative | −0.69% of eq (2018-11 S) | **−10.5% of eq** (L 2017-09-18) | — |

- **Who the drag hits:** S4's funding bill is a LONG-side, bull-era phenomenon
  — yearly funding as bp of avg equity: 2017 −6,008, 2018 −1,727, 2020 −781,
  2021 −856, 2022 −283, 2023 −497, 2024 −517, **2025 +21, 2026 +54**. A perp
  S4 in 2017-2021 would have paid away roughly half its headline edge; in
  2025-26 funding is a small credit.
- S3's mean per-trade funding: longs +3.6 bp of notional, shorts +1.7 bp —
  pullback entries systematically buy when funding is depressed. (S4 mean per
  trade: longs −89 bp, shorts −21 bp of notional; the short-side dollar total
  is positive because the big-notional 2018/2022 bear shorts collected.)
- **Drought window (2024-03-04 →):** S4 funding −$202k (bar basis; −$328k on
  trades closing in-window, which include the January-2024 entry) vs −$1.86M
  strategy P&L; S3 −$0.4k; S5 +42.5% → +40.3%. Funding neither caused nor
  meaningfully deepened the drought — and on the live CDE product it does not
  exist at all.

## 3. Dated-futures basis / roll drag (Job 2b)

Mean (median) front-quarter annualized basis by year, BitMEX quarterlies vs
.BXBT: 2017 +9.0% (+5.3), 2018 **−1.8%** (−1.6), 2019 +2.8%, 2020 +5.5%,
2021 +12.4% (+8.5), 2022 **−0.8%** (+0.3), 2023 +3.6%, 2024 +10.1% (+8.6),
2025 +5.7%, 2026 +2.4%.

Roll-drag estimate on our trade log (drag ≈ −side × ann_basis × holding-years ×
notional; assumes linear convergence — crude, labeled as such):

- **S3:** longs −$2.3k total (**−2.1 bp of equity per long trade** — immaterial
  vs the 6 bp/side fee line), shorts +$1.3k. S3 holds positions only ~20% of
  bars (10.4% long / 9.5% short).
- **S4:** longs −$748k, shorts **+$860k** → net ≈ +$112k. A dated-future
  trend-follower is roughly basis-neutral over a full cycle because the short
  legs earn the contango the long legs pay; S4 is long 46.4% / short 46.7% of
  bars.
- Current regime (2026 basis ≈ +2.4%/yr): worst-case S3 long-book drag ≈
  2.4% × 10% time-in-market ≈ **2-3 bp/yr of equity**; S4 ≈ neutral ± the
  long/short imbalance of the prevailing trend.

## 4. Funding as information (Job 3) — DESCRIPTIVE ONLY, no adopt/reject language

Full-sample percentile buckets of the last settled BitMEX rate at each 4h bar
close (n=22,210 bars, 2016-07→2026-08); forward BTC returns, 95% CI =
1.96·SD/√(n/k) (overlap-adjusted). Chart: `d3_regime_fwd.png`.

| bucket | mean rate | fwd 4h | fwd 1d | fwd 1w |
|---|---|---|---|---|
| Q1 (lowest) | −6.0 bp | +0.07% ±0.05 | +0.41% ±0.30 | **+2.80% ±1.90** |
| Q2 | +0.03 bp | +0.01% ±0.03 | +0.06% ±0.21 | +0.94% ±1.46 |
| Q3 | +0.97 bp | +0.02% ±0.04 | +0.14% ±0.20 | +0.96% ±1.54 |
| Q4 | +1.0 bp | +0.02% ±0.04 | +0.11% ±0.24 | +1.02% ±1.78 |
| Q5 (highest) | +7.7 bp | +0.03% ±0.05 | +0.20% ±0.30 | +0.81% ±2.21 |
| bottom 5% | −16.7 bp | +0.15% ±0.15 | +0.96% ±0.77 | **+5.26% ±4.76** |
| top 5% | +21.3 bp | +0.11% ±0.12 | +0.57% ±0.69 | +2.94% ±5.30 |

- The only structure is the classic contrarian low-funding effect (Q1/bottom-5%
  outperform). **Era split kills it as a candidate:** bottom-5% 1w = +4.75%
  ±4.9 in 2016-19 (n=1,016 of the 1,110 bucket bars), n=76 in 2020-22 and n=18
  in 2023-26 (CIs ±17-52%) — the signal barely fires in the modern era, and Q1
  1w is +3.8% ±2.9 pre-2020 vs +1.6-1.8% (±3.1-3.3) after, against ~+0.9% for
  the rest. High funding predicts nothing measurable.
- **Our trades vs funding regime:** S3 winners and losers are indistinguishable
  (mean entry percentile 49.7 vs 49.1). S4 losers sit modestly higher (entry
  55.8 vs 50.6; during-trade 54.8 vs 48.2), but the entry-quintile table is
  non-monotone (win rate Q4 31%, Q5 43%; mean P&L flat 2.0-3.3% everywhere) —
  consistent with noise on n≈50/bucket.
- **S3's worst 10 losses** span the whole funding range (entry percentiles 0.6
  to 99.3; 4 of 10 above the 90th, 3 below the 10th) — extreme funding is not
  the loss regime.
- **S4's drought is not a funding regime:** drought bars average the 46.6th
  funding percentile; 25% negative-funding bars vs 29% full-sample.

## 5. Pre-registration decision (Job 4): **NOTHING REGISTERED — 0 configs**

Judged against the bar set in the brief (genuine hypothesis + who-pays
rationale before any spec): the descriptive evidence is **weak** —
(a) the only forward-return effect is era-concentrated in 2016-2019 and
statistically thin since; (b) our books' outcomes are ~independent of funding
regime (S4's mild loser-tilt is non-monotone, n-small); (c) the drought D3 was
probing is not funding-related; (d) any funding filter is signal-space
(protocol §7 CLOSED) and family-adjacent to the ~63 already-failed
regime/vol/efficiency switching rules; (e) the live venue pays no funding, so
the economic link from "Binance/BitMEX perp positioning" to our CDE fills is
one more untested step. Writing an H4 spec on this evidence would be
hypothesis-shopping. **H4 therefore stays exactly where RESEARCH_S4_DROUGHT.md
§5 left it: DEFERRED, 0 configs, not re-invented.** If a future cycle wants to
revisit, the bar is: a who-pays rationale that survives the era-split above,
≤2 configs, blend-level MAR gates both folds both directions, diversifier
preservation per the −0.22 baseline, anti-shrinkage with the arithmetic basis
NAMED in the registration (batch-verification C2), DSR vs the then-current
registry — and §7 amended by Casey first.

## 6. Honesty box

- **Measurement basis:** engine dollar accounting, per-bar MTM curves, research
  fees (6 bp/side; 12 bp RT donchian), cash_apy 0, 1x books, frozen configs,
  continuous 2016-07→2026-08-19 run, **dd_halt disabled both books** (verbatim,
  S3 halts 2017-06-26; disclosed above). Funding-adjusted curves compound
  per-bar strategy + funding returns; per-trade funding uses qty × settle-bar
  close. Blend = per-bar constant-mix 75/25 @1.5x (s4_batch estimator).
- **Exchange-history caveats:** funding is **BitMEX XBTUSD** (inverse,
  coin-margined) — it reflects BitMEX positioning, clamped at ±0.375%/8h (170
  clamped settlements), and BitMEX's market share collapsed after ~2020, so
  early-era rates describe a venue that dominated then and is marginal now.
  Binance (USDT-margined, the deepest venue) is geo-blocked from this sandbox;
  Deribit corroborates 2019→ at daily granularity (corr 0.86) but no second
  source exists here for 2016-2018. Pre-2016 funding does not exist anywhere.
  **Our live venue is CDE (dated future, no funding)** — every funding number
  is a counterfactual "had it been a perp elsewhere," not a live cost.
- **Basis caveats:** BitMEX quarterlies vs .BXBT index; roll drag assumes
  linear basis convergence and front-quarter-only positioning; CME/CDE basis
  can differ from BitMEX basis (institutional vs offshore flow); 2016 basis
  data is sparse/noisy pre-2017.
- In-sample caveats: one asset, one non-stationary decade; the funding-regime
  buckets are full-sample percentiles (mild hindsight in the bucket EDGES,
  none in the descriptive claim); forward-return CIs use an overlap
  adjustment, not HAC — treat borderline significance as decoration.
- The 2016-2021 window shown for S3/S4 includes eras before their research
  windows; modern-era (2022→) rows are the decision-relevant ones and are
  reported separately.
- NOT modeled: slippage beyond fees, venue risk, margin interest on the CDE
  future, funding on intra-8h round trips (positions opened and closed between
  settlements pay nothing here, matching perp mechanics).
- **§7 boundary:** signal-space remains CLOSED; this study ran zero trials,
  registered zero configs, and touches no holdout. Nothing here authorizes a
  funding-based rule; any future H4 requires Casey to amend §7 first.
- **Counter-agent verification: PENDING** — per repo convention this study's
  numbers must be independently recomputed before any finding is acted on.

## 7. Files

Study scratchpad (`/tmp/claude-0/-home-user-uranium-dashboard/12c903ed-4550-5fbe-8b7c-b52480531ae3/scratchpad/`):
`fetch_funding.py`, `clean_funding.py`, `d3_funding.py`, `d3_charts.py`,
`d3_results.json`, `integrity_report.json`, cleaned CSVs (`funding_bitmex.csv`,
`funding_deribit.csv`, `funding_okx.csv`, `basis_front_quarter.csv`,
`spot_daily.csv`), raw JSON per source, and charts:
`d3_equity_funding.png` (adjusted vs unadjusted equity per book),
`d3_funding_history.png` (funding history, drought windows shaded),
`d3_regime_fwd.png` (regime vs forward returns), `d3_basis_by_year.png`.
