# GDP watch — growth of the largest economies, with a tested 4-quarter projection

Casey, 2026-11-16: "a chart that shows the gdp growth, and gdp growth by capita (toggle between) of the top 25
countries (or whichever number makes sense) ... make each country toggle on and off ... try to work an average or
mathematical basis to try to predict what the chart for each country will look like over the next year ... custom
dates ... past 1, 3, 5, 10, 25 years."

Shipped as the **GDP** tab on treasury-canary (`GET /gdp-watch`). Study code and frozen outputs are in
`studies/gdp_watch/`.

## 1. Results first

| Method, mean absolute error in points of YoY growth (pandemic quarters out) | 1q | 2q | 3q | 4q | 4q, pandemic in |
|---|---|---|---|---|---|
| Naive (last YoY holds) | 0.88 | 1.36 | 1.87 | 2.25 | 2.98 |
| Trend (10-yr median q/q) | 0.58 | 0.96 | 1.32 | 1.67 | 2.16 |
| **AR(1) toward trend (chosen, shown on the tab)** | **0.56** | **0.93** | **1.29** | **1.64** | 2.24 |

- **Sample:** 20 economies, origins 2006-Q1 to 2025-Q3. 1,340 projections per horizon with the pandemic quarters out, 1,500 with them in.
- **The rule beats naive** four quarters ahead in 18 of 20 economies: a median 31% less error (+43% UK down to +6% Brazil).
- **Naive did better** in China (−14%) and Indonesia (−20%). Their official series are very smooth.
- **With the pandemic in,** trend-only edges out AR(1) at 3–4 quarters (2.16 vs 2.24 at 4q), because AR(1) extrapolates the shock.
- **Bands, tested out of sample.** They were fitted on origins up to 2015-Q4 and tested on 2016+:
  - The 80% band held **85–88%** of outcomes without the pandemic (n = 553) and **73–76%** with it (n = 697).
  - The 50% band held 59–60% and 49–51%.
  - So the bands run a little wide in normal times and short in a shock.
- **The rule lags slowdowns.** Since 2023 its 4-quarter projections ran too high in most economies. Mean miss: Germany −1.5, Poland −1.4, China −1.2, Turkey −1.0, Netherlands −1.0 points (n = 15 per economy).
- **A 5-year trend window** cuts China's 4-quarter error from 1.74 to 0.94, but raises the pooled error (1.36 vs 1.28, on common origins 2016-Q4+). The frozen 10-year rule stands, and this is disclosed rather than switched.

Chart: `studies/gdp_watch/out/gdp_forecast_study_v1.png`. It shows error by horizon, skill against naive by economy, and what the rule said a year ahead against what happened (US, China, Germany).

## 2. Data

| Choice | Why |
|---|---|
| **20 economies, 79% of world GDP** (IMF 2025, market FX) | The largest with current quarterly data. The US and China alone are 43% and the six largest 57%, so a few economies set the pace. Those six are selected by default. |
| Russia out | Its OECD quarterly series stops in 2021-Q3. |
| Taiwan out | Not in the OECD accounts. |
| G20 and OECD aggregates | Shown, never projected (not in the study). |
| **Quarterly, % on a year earlier** | OECD QNA (`DF_QNA_EXPENDITURE_GROWTH_OECD`, seasonally adjusted). It makes the 1Y and 3Y views meaningful; annual data would give 1–3 points. |
| **Per person** | GDP growth divided by population growth over the same four quarters, from IMF WEO population (log-linear between mid-years, IMF projections ahead). |
| IMF WEO projections | Shown beside the rule as an independent reference. Not backtested: DataMapper serves only the current vintage. |

The snapshot is frozen at `data/snapshot_2026-11-16.json.gz` (44 KB). The panel's cold-start fallback is a byte-identical copy of it.

**Roll-forward identity.** Rolling the published YoY forward with the published q/q reproduces the next YoY exactly for 19 economies. China is 0.13pp off, because its official YoY is not seasonally adjusted while its q/q is.

## 3. Method (frozen; selection rule written before the run)

- **Target:** YoY real GDP growth, 1–4 quarters ahead, using data dated up to the origin only.
- **Candidates.** None was tuned on outcomes:
  - naive;
  - trend: each coming quarter grows at μ, the median q/q of the 40 quarters to the origin;
  - AR(1): q/q decays toward μ at φ, the OLS slope on those 40 quarters, clipped to [0, 0.8].
- **Pandemic quarters** (2020-Q1 to 2021-Q4) never enter μ or φ.
- **Forecast path:** trend and AR(1) roll the published YoY forward one quarter at a time, so the quarters already published count.
- **Selection rule:** lowest mean MAE over h = 1–4, pandemic out. A method within 2% of a simpler one loses to it.
- **Outcome:** AR(1) won by 2.9% over trend.
- **Parity:** the tab's code equals the study's at every origin (merge-blocking gate).

## 4. Honesty box

- **Revised data.** The record is on today's revised data, not real-time vintages; first releases get revised, so real-time misses run larger than shown.
- **Pandemic.** It is out of the scores and bands, and a shock like it falls outside them.
- **In-sample choice.** The method was picked among three on the same data, so its edge over trend (2.9%) is within noise. Its edge over naive is not.
- **No market edge.** Edge check (CLAUDE.md, "edge is the point"): none surfaced. This study tests forecast accuracy only: no asset return, conditional trade or mispricing was examined. The rule's persistent over-projection since 2023 is a statement about the rule, not a tested market signal.

## 5. Counter-agent verdicts

(Logged after review.)

## 6. Open questions (ranked)

| P | Question | What it would move | Status |
|---|---|---|---|
| P2 | Measure the real-time error with first-release vintages (OECD or ALFRED revisions)? | The size of the bands | open, first asked 2026-11-16 |
| P2 | Add the euro area as one economy? | One line for the EUR bloc, instead of six members | open, first asked 2026-11-16 |
| P3 | Anchor the trend to the IMF's medium-term growth instead of the 10-year median? | The 2023+ over-projection. Untestable without WEO vintages. | open, first asked 2026-11-16 |

Redeploy: **treasury-canary** (autodeploy on merge to main).
