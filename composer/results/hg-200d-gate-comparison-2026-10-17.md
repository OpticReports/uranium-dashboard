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

## Operation

- SPY below its 200-day: 22% of sessions 1990-2026, 18% in 2015-2026.
- Gate flips (above/below the 200-day): 6.6 per year 1990-2026, 5.5 per year 2015-2026; each flip is one extra trade on the trend leg held that day.
- Today (2026-10-07): SPY +8.1% vs its 200-day, so the gate is open and HG would hold exactly what it holds now.
- Composer can express it as one condition (SPY price above SPY 200-day moving average of price) in front of each trend basket.
