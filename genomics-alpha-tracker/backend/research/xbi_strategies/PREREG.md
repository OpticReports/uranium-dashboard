# XBI strategy study — pre-registration (written BEFORE any variant ran)

**Question (Casey, 2026-10-01):** "What about a strategy around XBI? Is there a
better way to trade it? Buy XBI and short several of the worst names, or some
other sleeve or strategy to improve DD or something else. Try many variants
and non-conventional ideas."

**Data.** FMP dividend-adjusted daily closes (round-7 lane, cache
`data/xbi_study_cache/`, gitignored): XBI, IBB, XLV, XPH, SPY, QQQ, IWM, TLT,
IEF, GLD, BIL, SHV (2006-11-14 → 2026-10-01); LABU/LABD (2015-05-28 →);
the 32 genomics names from the 10-year campaign cache (`backtest_bars.json`,
2015-09 →, SURVIVORS ONLY). Study window: first date with 200 XBI bars
(2007-09) → 2026-10-01. Cash leg earns BIL total return (SHV before BIL
exists; zero before 2007-01). Everything decided on close t is applied to the
return of t+1. No lookahead by construction; the verifier checks it.

**Costs (assumed, not measured).** ETF trades 5 bps per side on |Δw|; single
names 25 bps; LABU/LABD 10 bps + 8%/yr borrow; ETF shorts 0.5%/yr borrow
(IBB/XLV/SPY), short proceeds earn nothing extra; leverage above 1.0 pays
BIL + 1.5%/yr. Rebalance bands where stated so continuous rules do not
churn.

**Variants** (frozen list; each is ONE idea, no tuning before the first run):

| id | idea | rule |
|---|---|---|
| B0 | XBI buy & hold | the benchmark everything is judged against |
| B1 | SPY buy & hold | context |
| B2 | 50/50 XBI/BIL | monthly rebalance |
| B3 | 60/40 XBI/TLT | monthly rebalance |
| T1 | 200-day trend | close > SMA200 → XBI, else BIL; daily check |
| T2 | 10-month SMA | month-end close > 10m SMA → XBI, else BIL |
| T3 | 12-1 absolute momentum | 12m return ex last month > 0 → XBI, else BIL; monthly |
| T4 | dual momentum | best 12m of {XBI, SPY} if > BIL, else BIL; monthly |
| T5 | relative-strength switch | XBI/SPY ratio > its SMA200 → XBI, else SPY; daily |
| V1 | vol target 20%, cap 1.0 | w = min(1, 0.20 / realized 20d vol), 5pp band, cash in BIL |
| V2 | vol target 20%, cap 1.5 | same, leverage allowed with margin cost |
| V3 | trend + vol target | T1 gate × V1 sizing |
| D1 | drawdown de-risk | w = clip(1 − DD₁ᵧ/0.40, 0.25, 1), 5pp band |
| D2 | buy the dip (contrarian) | base 0.5; 1.0 while DD₁ᵧ > 20%; back to 0.5 at a new 1y high |
| S1 | seasonal | XBI 1 Nov – 31 Mar (JPM-conference window), BIL otherwise |
| S2 | seasonal + trend | S1 and close > SMA200 |
| M1 | RSI(2) mean reversion | buy RSI2 < 10, exit RSI2 > 70 or 10 bars; BIL otherwise |
| P1 | market-neutral XBI | long 100 XBI / short β·SPY (β = 60d rolling, cap 1.0); cash in BIL |
| P2 | size spread | long 100 XBI / short 100 IBB |
| P3 | sector spread | long 100 XBI / short 100 XLV |
| P4 | decay overlay | XBI 100 + short LABU 10 + short LABD 10, monthly reset (2015-06 →) |
| P5 | decay harvest, standalone | short LABU 50 / short LABD 50, daily reset to equal (2015-06 →) |
| N1 | long XBI / short worst survivors | XBI 100 + short the 5 worst 12-1 momentum names of the 32, 10% each, monthly (2016-09 →) |
| N2 | long XBI / short the broken | XBI 100 + short every name below its SMA200, equal-weight to 50% total, monthly (2016-09 →) |
| R1 | inverse-vol XBI/TLT/GLD | monthly, 60d vol, unlevered |
| C1 | post-hoc combo | built only AFTER the table above is read; labelled in-sample selection |

**Judging rule (frozen).** The benchmark is B0. A variant "improves the
ride" if (a) max DD is at least 10 pp shallower than B0 AND (b) CAGR is no
more than 2 pp below B0, on the full window, AND (c) max DD is shallower than
XBI's in at least 2 of the 3 sub-periods (2007-09→2012, 2013→2018,
2019→2026-10). Calmar and Sharpe are reported, not judged. Parameter
stability maps (T1: SMA 100–300; V1: target 15–25%) are reported for
anything that passes. Anything that passes only with leverage or shorting is
reported with its borrow/margin assumptions in the same row.

**Known biases, stated up front.** All in-sample on one 19-year path; XBI's
two great drawdowns (2008, 2021-22) are two observations. N1/N2 trade
SURVIVORS: shorting names that later survived is biased AGAINST the short
leg, so a loss there proves little and a win is not flattered by
survivorship — but the universe is still hindsight-selected, so neither
result is evidence. LABU/LABD borrow is assumed; real borrow on leveraged
ETFs spikes exactly when the trade hurts. Seasonality is a folk pattern
with a story attached (JPM conference); treat any pass as a candidate for
out-of-sample watching, not a rule.

**Never present any CAGR here as a forecast.**

---

## Amendments after counter-agent round 2 (2026-10-01, recorded, not silently edited)

The round-2 code review found the first engine re-levelled every variant
to its target DAILY at zero cost, which made the "monthly" labels false and
left short-leg re-levelling free (SERIOUS). Changes, all applied before the
numbers above the RESULTS markers in the study doc were (re)written:

1. The engine now CARRIES positions: weights drift with price, and a rule
   trades from the drifted book to its target only on the days it decides
   to, paying cost on the whole move. Cadences: monthly (B2, B3, T2, T3, T4,
   P1–P4, N1, N2, R1, C1x), daily-on-change (B0, B1, T1, T5, D2, S1, S2,
   M1), 5pp band on the target (V1–V3, D1), daily reset (P5).
2. P1/P2/P3 re-level monthly (the frozen table did not say; daily was the
   accidental first reading).
3. Study start moved from 2007-09-04 to 2007-11-15, the first bar where
   every 252-bar indicator is valid, so T3/T4/D1 are not flat for a reason
   unrelated to their rule. T4's BIL hurdle is 0 until BIL has 12 months
   (2008-05-29).
4. Single-name borrow is 3%/yr (omitted from the cost list above).
5. N1/N2 trade the ELIGIBLE survivors: 9 names at 2016-09, 31 by the end
   (23 of the 32 listed 2018–2024), not "the 32".
6. Worst calendar year excludes the partial first/last years.
