# HG 200-day leverage gate: comparison (2026-10-17)

Same signals and trades; below the SPY 200-day average the five trend baskets (TQQQ, UPRO, UDOW, SSO, TNA) are held at 1x, half 1x / half cash, or cash. Dip-buys stay at 3x. Costed at HG's measured slippage including the switches. Source: levgate.json (add. 42, counter-agent reviewed).

## 1990-2026 (proxy panel, out of sample for HG's rules)

| Variant | CAGR | Sharpe | Sortino | Max DD | Worst year | Sharpe gap vs as built (90%) | P(beats as built) |
|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +49.5% | 1.00 | 1.55 | 71.7% | -41.8% | | |
| 200d gate, trend baskets to 1x below | +53.6% | 1.12 | 1.80 | 64.6% | -45.2% | +0.04 to +0.20 | 0.99 |
| 200d gate, trend baskets to half 1x / half cash | +54.6% | 1.14 | 1.84 | 62.3% | -48.0% | +0.05 to +0.25 | 0.99 |
| 200d gate, trend baskets to cash (add. 40 B1) | +55.5% | 1.16 | 1.88 | 60.0% | -48.9% | +0.03 to +0.28 | 0.97 |
| 200d gate on every leveraged long, 1x below | +43.2% | 1.04 | 1.59 | 58.2% | -39.8% | -0.06 to +0.13 | 0.69 |
| Trend baskets always 1x (reference) | +35.0% | 1.00 | 1.86 | 64.6% | -38.6% | | |

## By regime, 1990-2026 panel (CAGR per year / max DD in the window)

| Variant | 2000-02 bear | 2007-09 bear | 2009-19 | 2020-26 |
|---|---|---|---|---|
| As built (trend baskets always 3x) | -9.6% / 71.7% | -46.5% / 70.1% | +55.3% / 55.0% | +127.4% / 35.9% |
| 200d gate, trend baskets to 1x below | +12.5% / 64.6% | +2.1% / 39.3% | +53.6% / 50.7% | +109.4% / 35.9% |
| 200d gate, trend baskets to half 1x / half cash | +20.4% / 62.3% | +21.2% / 34.2% | +53.0% / 49.9% | +104.7% / 35.9% |
| 200d gate, trend baskets to cash (add. 40 B1) | +28.3% / 60.0% | +42.8% / 29.0% | +52.3% / 49.3% | +99.8% / 35.9% |
| 200d gate on every leveraged long, 1x below | -17.7% / 57.7% | -21.0% / 44.8% | +44.5% / 50.7% | +88.0% / 35.9% |
| Trend baskets always 1x (reference) | +40.2% / 64.6% | +21.1% / 25.8% | +34.1% / 35.3% | +79.3% / 22.0% |

## 2015-2026 real tickers (in sample), live era and 2026 YTD

| Variant | CAGR 2015-26 | Sharpe | Max DD | Live era 2023-04 on: CAGR / Sharpe / DD | 2026 YTD (to 10-07) |
|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +103.9% | 1.69 | 35.9% | +80.3% / 1.46 / 27.9% | +86.6% |
| 200d gate, trend baskets to 1x below | +92.4% | 1.63 | 35.9% | +73.8% / 1.39 / 27.9% | +86.6% |
| 200d gate, trend baskets to half 1x / half cash | +89.4% | 1.61 | 35.9% | +72.1% / 1.37 / 27.9% | +86.6% |
| 200d gate, trend baskets to cash (add. 40 B1) | +86.4% | 1.57 | 35.9% | +70.5% / 1.35 / 27.9% | +86.6% |
| 200d gate on every leveraged long, 1x below | +72.9% | 1.49 | 35.9% | +63.9% / 1.38 / 27.9% | +82.2% |
| Trend baskets always 1x (reference) | +67.4% | 1.66 | 22.0% | +45.0% / 1.26 / 14.2% | +36.5% |

## Book level, 2015-2026 (29/29/27/15, drift, 40% cap; gate on HG only)

| Variant | Book CAGR | Sharpe | Sortino | Max DD | Worst year |
|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +111.9% | 2.77 | 5.18 | 22.3% | -8.7% |
| 200d gate, trend baskets to 1x below | +107.7% | 2.76 | 5.17 | 20.5% | -8.1% |
| 200d gate, trend baskets to half 1x / half cash | +105.7% | 2.73 | 5.10 | 20.1% | -7.9% |
| 200d gate, trend baskets to cash (add. 40 B1) | +104.9% | 2.72 | 5.08 | 19.8% | -7.7% |
| 200d gate on every leveraged long, 1x below | +100.2% | 2.73 | 5.01 | 18.2% | -9.5% |
| Trend baskets always 1x (reference) | +96.6% | 2.76 | 5.57 | 20.0% | -3.6% |

## Full metrics by period

### 1990-2026, full history

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +49.5% | 49.4% | 1.00 | 1.55 | 0.69 | 71.7% | -41.8% | 41 mo |
| 200d gate, trend baskets to 1x below | +53.6% | 44.5% | 1.12 | 1.80 | 0.83 | 64.6% | -45.2% | 34 mo |
| 200d gate, trend baskets to half 1x / half cash | +54.6% | 44.0% | 1.14 | 1.84 | 0.88 | 62.3% | -48.0% | 34 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +55.5% | 43.8% | 1.16 | 1.88 | 0.93 | 60.0% | -48.9% | 34 mo |

### 1990-99 (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +38.4% | 45.0% | 0.84 | 1.23 | 0.58 | 66.3% | -41.8% | 32 mo |
| 200d gate, trend baskets to 1x below | +42.8% | 42.4% | 0.94 | 1.41 | 0.73 | 58.6% | -45.2% | 34 mo |
| 200d gate, trend baskets to half 1x / half cash | +43.7% | 42.2% | 0.96 | 1.44 | 0.74 | 58.7% | -48.0% | 34 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +45.0% | 42.1% | 0.98 | 1.47 | 0.77 | 58.8% | -48.9% | 34 mo |

### 2000-02 bear (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | -9.6% | 79.1% | 0.21 | 0.33 | -0.13 | 71.7% | -33.3% | 20 mo |
| 200d gate, trend baskets to 1x below | +12.5% | 69.7% | 0.45 | 0.74 | 0.19 | 64.6% | -25.6% | 20 mo |
| 200d gate, trend baskets to half 1x / half cash | +20.4% | 68.6% | 0.55 | 0.91 | 0.33 | 62.3% | -23.6% | 19 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +28.3% | 68.2% | 0.64 | 1.07 | 0.47 | 60.0% | -22.2% | 17 mo |

### 2003-07 (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +34.0% | 36.3% | 0.91 | 1.34 | 0.81 | 42.0% | +14.0% | 9 mo |
| 200d gate, trend baskets to 1x below | +37.0% | 34.0% | 1.01 | 1.51 | 1.40 | 26.4% | +14.0% | 9 mo |
| 200d gate, trend baskets to half 1x / half cash | +37.9% | 33.8% | 1.03 | 1.55 | 1.43 | 26.4% | +14.0% | 9 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +38.7% | 33.7% | 1.05 | 1.58 | 1.46 | 26.4% | +14.0% | 9 mo |

### 2007-09 bear (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | -46.5% | 63.3% | -0.70 | -0.98 | -0.66 | 70.1% | -38.8% | 16 mo |
| 200d gate, trend baskets to 1x below | +2.1% | 44.7% | 0.23 | 0.38 | 0.05 | 39.3% | -10.4% | 12 mo |
| 200d gate, trend baskets to half 1x / half cash | +21.2% | 42.2% | 0.62 | 1.11 | 0.62 | 34.2% | -0.8% | 12 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +42.8% | 41.2% | 1.02 | 1.87 | 1.48 | 29.0% | +2.6% | 12 mo |

### 2009-19 (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +55.3% | 41.8% | 1.25 | 1.87 | 1.01 | 55.0% | -41.5% | 17 mo |
| 200d gate, trend baskets to 1x below | +53.6% | 38.7% | 1.29 | 1.96 | 1.06 | 50.7% | -35.9% | 17 mo |
| 200d gate, trend baskets to half 1x / half cash | +53.0% | 38.4% | 1.29 | 1.96 | 1.06 | 49.9% | -34.9% | 14 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +52.3% | 38.3% | 1.28 | 1.95 | 1.06 | 49.3% | -34.0% | 14 mo |

### 2020-26 (1990-2026 panel)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +127.4% | 52.5% | 1.76 | 3.19 | 3.55 | 35.9% | +48.2% | 7 mo |
| 200d gate, trend baskets to 1x below | +109.4% | 48.9% | 1.68 | 3.13 | 3.05 | 35.9% | +26.6% | 7 mo |
| 200d gate, trend baskets to half 1x / half cash | +104.7% | 48.6% | 1.65 | 3.07 | 2.92 | 35.9% | +22.0% | 9 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +99.8% | 48.5% | 1.60 | 2.99 | 2.78 | 35.9% | +17.2% | 11 mo |

### 2015-2026, real tickers (in sample)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +103.9% | 47.4% | 1.69 | 2.93 | 2.90 | 35.9% | -19.8% | 13 mo |
| 200d gate, trend baskets to 1x below | +92.4% | 44.5% | 1.63 | 2.90 | 2.58 | 35.9% | -17.7% | 14 mo |
| 200d gate, trend baskets to half 1x / half cash | +89.4% | 44.3% | 1.61 | 2.86 | 2.49 | 35.9% | -17.0% | 14 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +86.4% | 44.2% | 1.57 | 2.80 | 2.41 | 35.9% | -16.4% | 14 mo |

### Live era, 2023-04-19 to 2026-10-07

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +80.3% | 43.5% | 1.46 | 2.59 | 2.88 | 27.9% | +36.1% | 7 mo |
| 200d gate, trend baskets to 1x below | +73.8% | 42.9% | 1.39 | 2.44 | 2.65 | 27.9% | +36.1% | 7 mo |
| 200d gate, trend baskets to half 1x / half cash | +72.1% | 42.8% | 1.37 | 2.40 | 2.59 | 27.9% | +36.1% | 7 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +70.5% | 42.8% | 1.35 | 2.36 | 2.52 | 27.9% | +36.1% | 7 mo |

### Book 2015-2026 (29/29/27/15, 40% cap; gate on HG only)

| Variant | CAGR | Vol | Sharpe | Sortino | Calmar | Max DD | Worst year | Longest underwater |
|---|---|---|---|---|---|---|---|---|
| As built (trend baskets always 3x) | +111.9% | 27.8% | 2.77 | 5.18 | 5.02 | 22.3% | -8.7% | 6 mo |
| 200d gate, trend baskets to 1x below | +107.7% | 27.0% | 2.76 | 5.17 | 5.25 | 20.5% | -8.1% | 6 mo |
| 200d gate, trend baskets to half 1x / half cash | +105.7% | 26.9% | 2.73 | 5.10 | 5.25 | 20.1% | -7.9% | 6 mo |
| 200d gate, trend baskets to cash (add. 40 B1) | +104.9% | 26.9% | 2.72 | 5.08 | 5.31 | 19.8% | -7.7% | 6 mo |


## Operation

- SPY below its 200-day: 22% of sessions 1990-2026, 18% in 2015-2026.
- Gate flips (above/below the 200-day): 6.6 per year 1990-2026, 5.5 per year 2015-2026; each flip is one extra trade on the trend leg held that day.
- Today (2026-10-07): SPY +8.1% vs its 200-day, so the gate is open and HG would hold exactly what it holds now.
- Composer can express it as one condition (SPY price above SPY 200-day moving average of price) in front of each trend basket.
