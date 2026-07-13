# Canary Backtest Report

_Generated 2026-07-13. Reproduce: `python -m scripts.backtest`._

## A. Re-steepening canary — full replay (monthly 3m10y, 1953–2026)

Sustained inversion = ≥3 consecutive months below zero. Market prices are unrevised → **no vintage bias in this part**.

| Inversion start | Dis-inversion | Months inv. | Depth (bps) | Onset lag (mo) | Verdict |
|---|---|---|---|---|---|
| 1966-09-01 | 1967-02-01 | 5 | -34 | 35 | FALSE POSITIVE |
| 1969-11-01 | 1970-02-01 | 3 | -17 | — | HIT (onset during inversion) |
| 1973-06-01 | 1974-07-01 | 13 | -127 | — | HIT (onset during inversion) |
| 1978-12-01 | 1980-05-01 | 17 | -245 | — | HIT (onset during inversion) |
| 1980-11-01 | 1981-09-01 | 10 | -265 | — | HIT (onset during inversion) |
| 2000-08-01 | 2001-01-01 | 5 | -53 | 3 | HIT |
| 2006-08-01 | 2007-05-01 | 9 | -38 | 8 | HIT |
| 2019-06-01 | 2019-10-01 | 4 | -32 | 5 | HIT |
| 2022-11-01 | 2024-12-01 | 25 | -157 | — | PENDING |

- **Episodes (sustained): 9** → hits 7, false positives 1, pending 1.
- **Recessions in window: 11** → missed by the canary: ['1953-08-01', '1957-09-01', '1960-05-01', '1990-08-01'].
- **Median dis-inversion → onset lag (post-dis-inversion hits): 5 months** (range 3–8; earlier-era onsets often began while still inverted).
- **On the 1990 'miss':** in this long-history data the 1989 spread bottomed at +0.13 — TB3MS quotes bills on the DISCOUNT-rate convention, which understates bond-equivalent yield by ~20–40bp, so 1989's shallow inversion never registers. On the bond-equivalent basis (NY Fed's model, and the LIVE dashboard's DGS3MO), 1989 did invert and 1990 is caught. The 1950s misses are similar early-era convention/shallow-inversion artifacts. A replay artifact, not a live-canary flaw.
- Current live state: **NORMAL**.

## B. Walk-forward probit (out-of-sample)

Model refit each month using only data available then; predicts P(recession within 12m); scored against what actually happened.

- Out-of-sample months scored: **666** (1970–present, base rate 24.2%).
- **Out-of-sample AUC: 0.736** vs in-sample **0.738** (optimism gap: 0.002).

| Predicted prob | n | Realized freq | Avg predicted |
|---|---|---|---|
| 0%–10% | 174 | 11.5% | 6.0% |
| 10%–20% | 125 | 12.8% | 14.9% |
| 20%–30% | 128 | 18.0% | 25.1% |
| 30%–50% | 130 | 26.9% | 40.7% |
| 50%–101% | 109 | 61.5% | 67.1% |

## C. Leading-stack breadth replay (1971–present)

Fixed thresholds applied month-by-month (7 long-history indicators; SLOOS/GDPNow too short/quarterly). Caveats: macro series as revised today (vintage bias favors the indicators); thresholds come from literature that knew this history — treat as validation of coherence, not discovery.

- Avg breadth in the 6 months before onsets: **40.7%** vs **17.0%** in normal expansion months.
- Majority alarms (≥50% flashing, 2 consecutive months, outside recession): 5

| Alarm date | Months to next onset | Verdict |
|---|---|---|
| 1979-11-01 | 3 | HIT |
| 2001-01-01 | 3 | HIT |
| 2007-10-01 | 3 | HIT |
| 2023-11-01 | — | FALSE POSITIVE |
| 2025-11-01 | — | PENDING |

## Honest limitations

- Composite/pins not fully replayable: SOFR (2018+), IORB (2021+), RRP, FMP gold etc. lack deep history; the composite's funding leg simply didn't exist pre-2018.
- Part C uses today's revised data (except SAHMREALTIME, which is real-time by construction). See VINTAGE.md (`python -m scripts.vintage_check`) for the ALFRED as-of-then replay of these alarms.
- NBER dates recessions ~4–12 months after they begin: outcome TRUTH here uses final dating; in real time you would not know a hit was a hit that fast.
- Threshold-selection bias: rules like CFNAI −0.7 and Sahm 0.5 were set by researchers who had seen this history.