# Leverage gate — literature & factor brief (research pass, 2026-10-16)

Question: is there a factor (or small set) that times *leveraged vs 1x* for the same trades, and what do 2026+ dynamics imply? Evidence first; opinion tagged **[opinion]**. Numbers are as reported by the cited source (mostly in-sample, gross) unless stated.

## 1. What the evidence says

**Why a gate can work at all (LETF math).** Over a horizon, LETF log-return ≈ L·(index log-return) − ½·L(L−1)·∫σ² — exact in discrete time, fits 56 funds quarterly [AZ10]; same result in [CM09]. Decay coefficient ½L(L−1): +2x = 1, +3x = 3, **−1x = 1, −3x = 6** → inverse legs decay 2x faster than same-size longs, and a "1x" inverse fallback (PSQ/TBF) still decays like a 2x long. Positive daily autocorrelation (streaks) offsets the drag; chop adds to it — "auto-variation" dominated quadratic variation empirically [LWZ12]. Illustrative (my arithmetic): 3x at σ=15% ≈ 6.75%/yr drag, σ=30% ≈ 27%/yr, σ=60% ≈ 108%/yr. Optimal constant leverage falls with σ² [G10]. Justified holding periods at a fixed decay tolerance were >4 months pre-2007 and collapsed in 2008 with GARCH vol [TC13]; 2x ≈ 1.4x over multi-year horizons [TB08]. Single-stock LETFs lose 0.79%/mo (0.26 rebalancing, 0.53 frictions) [B25]. **So the gate's job is to predict σ² and chop, not direction.**

| Study | Rule / params | Works (as reported) | OOS status | Bull-market cost |
|---|---|---|---|---|
| Gayed & Bilello 2016, Dow Award [GB16] | S&P TR > SMA(10…200d) → 1.25/2/3x; below → T-bills; 1%/yr leverage fee; no switching costs; 1928–2015 | Mechanism: forward vol higher below *every* MA tested; worst-1% days cluster below MA; up-day streaks more likely above; below 200d 69% of recession time vs 19% in expansions. Unlev 200d: 10.9% CAGR / 12.4% vol / Sharpe 0.60 / MDD −49.5% / 5 trades/yr (B&H 9.1 / 18.9 / 0.30 / −86.2). 3x LRS: 26.8% / 37.3% / 0.47 / **−92.2%**; 2x LRS 19.1 / 24.9 / 0.51 / −78.7. MA length robust (Sharpe 0.59–0.69; 10d = 38 trades/yr) | None in paper. Practitioner replication (SSO/SHY, 200d, 5y): Sharpe 0.555 vs SPY 0.524 [QC]. Critiques: 1% leverage cost unrealistic pre-ETF, 1928 start, no frictions [CXO] | Unlevered rotation vs S&P: 43% vs 121% (2002–07), 95% vs 260% (2009–15); MA beats B&H in absolute terms in only 49% of rolling 3y (risk-adjusted 69%) |
| Moreira & Muir 2017 JF [MM17]; 2019 JFE [MM19] | w ∝ 1/RV² (prior month daily), monthly | Market Sharpe +25%, alpha 4.9%; vol changes not matched by expected-return changes; long-horizon investors still gain (~2.4%/yr wealth cost of ignoring) | **Weak in real time**: 72/103 strategies lose Sharpe/CE OOS, scaling coefficients unstable [COWY20]; fixing look-ahead in the scaling constant → MDD 68–93%, gains concentrated in 2008 [LTZ19]; after costs only the market factor survives, mostly when sentiment is high [BD21]; downside-vol scaling survives real-time tests [WY21] | Leverage in calm bulls, so low direct cost; cost is turnover and drawdowns when vol spikes *after* the loss |
| Harvey et al. 2018 JPM [H18]; Perchet et al. 2016 JAI [P16] | Constant-vol scaling, 60+ assets since 1926 | Sharpe gain only where vol clusters *and* leverage effect exists (equities 0.40→0.48–0.51, credit); nil for bonds/FX/commodities; cuts left tail and vol-of-vol (4.6%→1.8%) everywhere | Broad cross-asset, long sample; still in-sample parameters | Implicit momentum: trims after losses |
| Bongaerts, Kang & van Dijk 2020 FAJ [BKD20] | "Conditional" targeting: act only in extreme high/low vol states; 10 markets 1972–2019 | Plain vol targeting fails in global equities and raises drawdowns; conditional version raises Sharpe, cuts DD/tails with low turnover | Multi-market, but thresholds in-sample | Low: untouched in normal regimes |
| Barroso & Santa-Clara 2015 JFE [BSC15]; Daniel & Moskowitz 2016 JFE [DM16] | Momentum scaled by 126d realized variance (weights 0.13–2.0); DM: forecast mean+variance | Crashes removed, Sharpe ~2x; crashes occur in "panic states" (post-decline, high vol) *during rebounds* | Multiple markets/asset classes | Relevant to **inverse legs** (SQQQ/UVXY/TMV/LABD): their crash is the V-rebound (Apr 9 2025) |
| Trend filters: Faber 2007/13 [F13]; Hurst–Ooi–Pedersen 2017 JPM [HOP17]; Zakamulin 2014 JAM [Z14] | 10-month SMA, monthly; TSMOM 1880–2016 | S&P 1901–2012: 10.2% vs 9.3% CAGR, vol 12.0 vs 17.9; MDD ≈ −50% vs −84% (1840–2011 table). TSMOM positive in 8 of 10 worst 60/40 drawdowns | Faber: 20 other markets; Zakamulin (frictions + bootstrap OOS): only marginal risk-adjusted gain, materially lower terminal wealth | Lag on re-entry; monthly signal leaves intra-month gaps |

Net: **the robust, replicated finding is tail/vol-of-vol reduction, not Sharpe gain**. For LETFs that is exactly the quantity that matters (drag ∝ σ²), which is why the LETF case is stronger than the generic vol-timing case **[opinion]**.

## 2. Candidate gates (ranked by evidence quality)

| # | Factor | Leveraged when… | Mechanism | Composer? | Grade |
|---|---|---|---|---|---|
| 1 | 1x underlying vs its 100–200d SMA (per leg: QQQ for TQQQ/SQQQ, SOXX for SOXL, IWM for TNA…) | above (long legs); for inverse legs gate on the *underlying's* regime, see R4 | forward vol, chop and worst days concentrate below [GB16]; cross-asset (R2000 vol 14.7% above vs 26.5% below) | Yes: price vs MA-of-price(N) | **A** (97y, cross-asset; OOS only informal) |
| 2 | Realized vol of the 1x underlying (std-dev-of-return 10d/20d, annualized) with 2–3 buckets | σ below in-sample quantile; blend in the middle | drag ∝ σ²; vol clusters [H18][BKD20] | Yes: std-dev-of-return(N) thresholds; blend via nested if/else | **A** for tails, **B** for Sharpe; thresholds must come from a training window [LTZ19] |
| 3 | VIX term structure via VIXY/VIXM ratio (or VIXY vs its 20d MA) | ratio falling / below MA (contango, calm) | curve shape prices short-horizon variance risk [J17]; backwardation = high-vol regime (bad for drag) but *contrarian-bullish* for returns 2010–17 [FH19][SC14] | Yes (both tradable); level non-stationary from roll → use ratio change/MA | **B** |
| 4 | Drawdown from 252d high of the underlying | DD small | nearness to 52w high → higher aggregate returns, G7 [LY12]; overlaps #1 | Yes: max-drawdown(N) | **B** |
| 5 | T-bill rate (BIL/SGOV 63d cumulative return ≈ quarterly yield) | low rf | financing (L−1)·(SOFR+spread) is certain, not a timing signal | Yes (proxy) | **C** as gate, **A** as cost hurdle |
| 6 | Credit spreads via HYG vs IEF/SHY relative 20–60d return | HY outperforming | EBP shocks → equity declines [GZ12]; slow, cycle-frequency | Proxy only | **C** |
| 7 | Breadth (RSP/SPY relative return; Any/All of sector ETFs above MA) | strong | modest literature; note mid-2026: 56% above 200d at record highs, 24.5% above 40d in Oct 2026 [INV26][WST26] | Crude proxy only | **C** |
| 8 | Strategy's own equity curve vs MA | — | anecdotal; smoother but lower return | **No** (no self-reference) | **D** |

VIX *level* alone is contrarian-bullish for returns yet bearish for drag; the predictive object is the variance risk premium (VIX²−RV²) [BTZ09] and the VIX premium falls before risk rises [C19] — neither expressible in Composer.

## 3. Forward dynamics, 2026 on

- **Financing drag is high and certain.** SOFR ≈ 3.9% (early Oct 2026) [SOFR], FF 3.75–4.00% after a reported Sept hike (not confirmed from Fed text) [FF], 10y ≈ 5.0% [FRED]. 3x pays ~2×(SOFR+spread)+ER; single-stock swap spreads were 3.7–4.5% over SOFR [PT25]; index spreads undisclosed — **estimate TQQQ's drag empirically (intercept of TQQQ on 3×QQQ daily)**. **[opinion]** High rf lowers the opportunity cost of sitting in 1x, so gate break-evens are better than in 2010–21.
- **Vol regime: suppressed baseline, violent spikes.** 0DTE ≈ 60% of SPX volume (Mar 2026) [SIFMA]; Adams et al. (Oct 2025) find dampening on average, literature mixed [SIFMA][CBOE0]; derivative-income ETFs took +$56B in 2025, ≈$145B AUM [FTP][REU]. Against that: Aug 5 2024 (S&P −3.0%, VIX 23→38.6 close, 65.7 pre-market) [CBOE1][MAC]; Apr 2025 (VIX close 52.3, S&P +9.52% Apr 9, −3.46% Apr 10) [MAC][HL]; Mar 2026 (−9.1% to Mar 30, VIX 31, then +12–13% in 13 days, sharpest since Apr 2020) [MH26][GS26]. **[opinion]** V-shapes make *re-entry lag* the dominant cost of MA gates and RV gates; asymmetric gates (fast exit, faster re-entry) are the thing to test, and they are the most overfit-prone.
- **LETF AUM and end-of-day feedback.** $117B (2024) → record ~$198B (Jun 2026; TQQQ ≈ $40B, SOXL ≈ $34B) → ≈ $154B after July 2026 deleveraging [BBG24][Y26a][IF26]. Rebalancing demand = (L²−L)·A·r, same direction as the move [CM09]; ~$7B per 1% in 2024 (Morgan Stanley) [BBG24], scaling with AUM; ≈$50B/day ≈ 1.6% of S&P futures volume in 2026 [AMRO]. Academic evidence on late-day price impact is mixed [CXO2]. Your 15:50 switches trade *with* that crowd.
- **Concentration and sector gap risk.** Top-10 ≈ 38–41% of S&P (2025–26) [CR][KC]; SOX −7.9% / SOXL −23% in one day (Jun 23 2026), SOX down 8 straight days mid-Oct 2026 [Y26a][INV2]. Gate each leg on its own underlying, not SPY.
- **Stock–bond correlation ≈ +0.41 since 2022 (vs −0.37, 2011–21)** [SSGA]: TMV/TMF legs and bond sleeves are not crash hedges on inflation days; their 1x fallbacks still carry duration.
- **Gap risk is unavoidable at daily cadence**: Aug 2024 was in VIX pre-market; Apr 3–4 2025 were back-to-back gaps. A daily gate exits after day 1–2 at best.

## 4. Rule shapes to prioritise

1. **R1 Per-leg SMA switch (baseline).** Lev iff 1x close > SMA(N), N ∈ {100,150,200}; ±1–2% hysteresis band; variant 50/200 cross. Report whipsaw count, time-in-1x, and bull-window "lag cost" separately.
2. **R2 Conditional RV buckets.** σ20 of the underlying: < q50 → lev; q50–q85 → 50/50; > q85 → 1x, quantiles from 2010–2019 only, frozen; σ10 for exit, σ20 for re-entry.
3. **R3 2-of-3 composite.** (a) above SMA200, (b) σ20 < threshold, (c) VIXY/VIXM below its 20d MA; lev on ≥2, blend on 1, 1x on 0 (nested any/all in Composer).
4. **R4 Inverse-leg panic gate.** For SQQQ/UVXY/TMV/LABD: drop to 1x when underlying DD(252d) > 10–15% *and* σ20 high — the rebound state [DM16]. **[opinion]** Likely the largest single contributor given the −3x decay coefficient (6 vs 3).

Pitfalls: thresholds/quantiles from the test window (look-ahead, [LTZ19]); 2015–26 is one regime (V-recoveries, bull drift) — validate on 2000–02/2007–09 with synthetic LETFs (L×index − (L−1)(rf+spread) − ER); Composer signals use the ~15:50 price, so backtests on closes are slightly optimistic and switches coincide with LETF rebalancing; 4 shapes × grids → report the whole grid or a deflated Sharpe; spreads/slippage are fine for TQQQ/SOXL, worse for LABD/TMV.

## Citations
- [GB16] Gayed & Bilello, "Leverage for the Long Run," 2016 Dow Award (CMT Assoc.). https://docs.cmtassociation.org/dow-award/2016-gayed-bilello.pdf
- [CXO] CXO Advisory review of [GB16]. https://www.cxoadvisory.com/volatility-effects/leveraging-the-u-s-stock-market-based-on-sma-rules/
- [QC] QuantConnect, "Leveraged ETFs with Systematic Risk Management." https://www.quantconnect.com/learning/articles/investment-strategy-library/leveraged-etfs-with-systematic-risk-management
- [MM17] Moreira & Muir, JF 72(4) 2017. https://www.nber.org/papers/w22208
- [MM19] Moreira & Muir, "Should Long-Term Investors Time Volatility?" JFE 2019. https://academicnewsletter.sufe.edu.cn/info/356035
- [COWY20] Cederburg, O'Doherty, Wang & Yan, JFE 138 (2020). https://www.lehigh.edu/~xuy219/research/COWY.pdf
- [LTZ19] Liu, Tang & Zhou, JPM 46(1) 2019. https://profiles.wustl.edu/en/publications/volatility-managed-portfolio-does-it-really-work/
- [BD21] Barroso & Detzel, JFE 140(3) 2021. https://cefup-nipe-rank.eeg.uminho.pt/articles/30094/view
- [WY21] Wang & Yan, JBF 2021. https://www.lehigh.edu/~xuy219/research/Downside.pdf
- [H18] Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert, JPM Fall 2018. https://quantpedia.com/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies
- [P16] Perchet, de Carvalho, Heckel & Moulin, JAI 18(3). (citation only; abstract not retrieved)
- [BKD20] Bongaerts, Kang & van Dijk, FAJ 76(4) 2020. https://rpc.cfainstitute.org/research/financial-analysts-journal/2020/conditional-volatility-targeting
- [BSC15] Barroso & Santa-Clara, JFE 2015. https://academicnewsletter.sufe.edu.cn/info/356496
- [DM16] Daniel & Moskowitz, JFE 122(2) 2016. https://www.nber.org/papers/w20439
- [F13] Faber, "A Quantitative Approach to TAA" (2013 update), via CXO. https://www.cxoadvisory.com/technical-trading/long-term-outperformance-from-trends-defined-by-moving-averages
- [HOP17] Hurst, Ooi & Pedersen, JPM 2017. https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- [Z14] Zakamulin, J. Asset Mgmt 15(4) 2014. https://ideas.repec.org/a/pal/assmgt/v15y2014i4d10.1057_jam.2014.25.html
- [CM09] Cheng & Madhavan, JOIM 7(4) 2009. https://joim.com/dynamics-leveraged-inverse-exchange-traded-funds
- [AZ10] Avellaneda & Zhang, SIAM J. Fin. Math 1 (2010) 586–603. https://epubs.siam.org/doi/pdf/10.1137/090760805
- [LWZ12] Lu, Wang & Zhang, Financial Services Review 21 (2012). https://openjournals.libs.uga.edu/fsr/article/view/3234
- [TB08] Trainor & Baryla, J. Financial Planning, May 2008. https://www.financialplanningassociation.org/sites/default/files/2021-08/MAY08%20Leveraged%20ETFs%20A%20Risky%20Double%20That%20Doesnt%20Multiply%20by%20Two.pdf
- [TC13] Trainor & Carroll, J. Financial Studies & Research 2013. https://inventi.in/journal/article/34/6555/
- [G10] Giese, J. Asset Mgmt 11(4) 2010. https://ideas.repec.org/a/pal/assmgt/v11y2010i4d10.1057_jam.2010.16.html
- [B25] Bessembinder 2025, via [PT25].
- [PT25] Ptak, "Breathe Through Your Mouth," Oct 20 2025. https://jeffreyptak.substack.com/p/breathe-through-your-mouth
- [J17] Johnson, JFQA 52(6) 2017. https://ideas.repec.org/a/cup/jfinqa/v52y2017i06p2461-2490_00.html
- [SC14] Simon & Campasano, VIX futures basis, via Quantpedia. https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures
- [FH19] Fassas & Hourvouliades, JRFM 12(3):113, 2019. https://doi.org/10.3390/jrfm12030113
- [BTZ09] Bollerslev, Tauchen & Zhou, RFS 22(11) 2009. https://papers.ssrn.com/abstract=948309
- [C19] Cheng, "The VIX Premium," RFS 32(1) 2019. https://ideas.repec.org/a/oup/rfinst/v32y2019i1p180-227..html
- [LY12] Li & Yu, JFE 104 (2012). https://academicnewsletter.sufe.edu.cn/info/356820
- [GZ12] Gilchrist & Zakrajšek, AER 102(4) 2012. https://www.nber.org/papers/w17021
- Composer: trade window 3:50–4:00 ET https://help.composer.trade/article/60-after-hours-trading ; cross-ticker comparisons https://help.composer.trade/article/214-6-how-composer-symphonies-work ; metrics https://help.composer.trade/category/24-metrics
- [CBOE1] Cboe, VIX attribution of tail events. https://www.cboe.com/insights/posts/vix-index-attribution-of-notable-tail-events
- [MAC] Macroption, VIX highs/spikes. https://www.macroption.com/vix-all-time-high/
- [HL] Hargreaves Lansdown, US close Apr 9 2025. https://hl.co.uk/shares/stock-market-news/market-reports/us-close-stocks-skyrocket-as-trump-announces-90-day-tariff-pause
- [MH26] Moorman Harting, April 2026 recap. https://www.moormanharting.com/blog/monthly-recap-april-2026
- [GS26] Goldman Sachs, US stocks 2026. https://www.goldmansachs.com/insights/articles/us-stocks-forecast-to-rise-in-2026
- [Y26a] 24/7 Wall St via Yahoo, Jun 24 2026. https://finance.yahoo.com/markets/options/articles/yesterday-tech-rout-shows-leveraged-123328863.html
- [IF26] Idea Farm citing Citadel Securities, Aug 2026. https://theideafarm.com/markets/august-checklist/
- [BBG24] Bloomberg via Tiger/Nasdaq, Sep 2024. https://www.nasdaq.com/articles/leveraged-etfs-trigger-volatility-market-rebalancing-intensifies
- [AMRO] AMRO 2026. https://www.amro-asia.org/?p=48299
- [CXO2] CXO on LETF end-of-day effects. https://www.cxoadvisory.com/volatility-effects/front-running-leveraged-etfs-at-the-end-of-the-day
- [SIFMA] SIFMA Insights, Apr 2026. https://www.sifma.org/wp-content/uploads/2026/04/SIFMA-Insights-Equities-and-Options-Monthly-Metrics_April_2026.pdf
- [CBOE0] Cboe, "Much Ado About 0DTEs." https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options
- [FTP] FT Portfolios citing Morningstar, Mar 24 2026. https://www.ftportfolios.com/blogs/MarketBlog/2026/3/24/an-update-on-covered-call-returns
- [REU] Reuters (derivative-income AUM $145B; date unconfirmed). https://979weve.com/?p=736160
- [SSGA] State Street, Oct 2025. https://www.ssga.com/library-content/assets/pdf/global/wmu/2025/mom-20251003.pdf
- [CR] ChartRow concentration. https://chartrow.com/sp500/concentration ; [KC] KuCoin citing S&P DJI (Sep 30 2026). https://www.kucoin.com/blog/ae-nvidia-apple-and-microsoft-sp500-concentration
- [INV26] Investing.com (breadth at highs). https://www.investing.com/analysis/market-correction-risk-why-summer-2026-looks-risky-200679612 ; [WST26] https://wallstreettrader.substack.com/p/inflation-hits-tech-market-breadth ; [INV2] Investrade Oct 16 2026. https://investrade.com/market-review-october-16-2026/
- [SOFR] https://www.sofrrate.com/sofr-rate/2026-10 ; [FRED] DGS10 https://fred.stlouisfed.org/graph/?g=1aRXJ ; [FF] Sept 2026 FOMC (secondary). https://forexfundamentals.com/economic-calendar/fomc/2026-09-16

Not retrieved (cite with care): Perchet et al. abstract; Citadel Securities "After the Reset"/"Reload" notes (403); Benzinga Jul 2026 "$50B rebalancing" (403); exact S&P above/below-MA vol numbers in [GB16] are chart-only (the 14.7%/26.5% pair is Russell 2000, 1979–2015).
