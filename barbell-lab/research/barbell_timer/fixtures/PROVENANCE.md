# BARBELL-TIMER fixture provenance log — fetched 2026-08-12

Rule: every series below is FROZEN as of the fetch date. Downstream
scripts read fixtures only. Gaps are logged, never interpolated at
fetch time.

- fmp_gde_dividend_adjusted.json: GDE 2022-03-17 -> 2026-08-12 (1105 rows). GDE ETF daily, dividend-adjusted (adjClose ~= total-return index). Inception 2022-03-15 (first trade 2022-03-16/17 on exchanges).
- fmp_gde_full.json: GDE 2022-03-17 -> 2026-08-12 (1105 rows). GDE ETF daily raw OHLC (unadjusted close/open) — for open-execution and dividend cross-checks.
- fmp_spy_dividend_adjusted.json: SPY 1993-01-29 -> 2026-08-12 (8441 rows). SPY daily dividend-adjusted (total-return proxy incl. dividends, gross of nothing — SPY's 9bp ER is already inside the NAV).
- fmp_gld_dividend_adjusted.json: GLD 2004-11-18 -> 2026-08-12 (5466 rows). GLD daily (physical gold minus 40bp/yr fee) — cross-check series.
- fmp_boxx_dividend_adjusted.json: BOXX 2022-12-28 -> 2026-08-12 (908 rows). BOXX daily adj — actual bills-proxy vehicle post-2022 per brief.
- fmp_dgl_dividend_adjusted.json: DGL 2007-01-05 -> 2023-03-16 (4077 rows). Invesco DB Gold (DGL): REAL gold-futures fund (futures + T-bill collateral, ~0.75-0.78%/yr ER). Used to REALIZE the futures-vs-spot carry gap: DGL_TR - GLD_TR ~= lease - ER_DGL + ER_GLD, so realized lease ~= (DGL-GLD) + 0.78% - 0.40%. Brief lists lease rates as optional Phase 0 data; this is the measurement instrument chosen (documented amendment: extra ticker, same endpoint).
- fmp_gcusd_light.json: GCUSD 1976-02-26 -> 2026-08-12 (12848 rows). COMEX gold continuous front-month, PRICE-SPLICED (not back-adjusted): level tracks the front contract so LEVEL returns ~= spot returns and do NOT embed the carry a real long-futures position pays. FLAGGED — replication.py subtracts financing carry explicitly instead.
- fmp_gspc_light.json: ^GSPC 1970-01-02 -> 2026-08-12 (14274 rows). S&P 500 price index daily (NO dividends) — used only for daily-maxDD shape estimates pre-1993, with dividends smeared from monthly.
- fmp_gde_dividends.json: 8 GDE distributions (cross-check for the adjusted series; GDE pays semi-annual, incl. large cap-gain distributions from futures gains).
- fred_tb3ms.json: TB3MS 1934-01-01 -> 2026-07-01 (1111 obs, 0 missing-value rows dropped-and-logged). 3M T-bill secondary-market rate, monthly avg, %/yr, 1934->
- fred_dtb3.json: DTB3 1954-01-04 -> 2026-08-10 (18142 obs, 799 missing-value rows dropped-and-logged). 3M T-bill secondary-market rate, DAILY, %/yr — bills leg for the daily replication
- fred_dfii10.json: DFII10 2003-01-02 -> 2026-08-10 (5905 obs, 253 missing-value rows dropped-and-logged). 10Y TIPS constant-maturity real yield, daily, 2003-> (pre-2003 proxy is a Phase-2 concern, not fetched here)
- fred_dtwexm.json: DTWEXM 1973-01-02 -> 2019-12-31 (11834 obs, 427 missing-value rows dropped-and-logged). Trade-weighted USD major currencies (goods), daily, 1973-01 -> 2020-01 (DISCONTINUED — splice partner below)
- fred_dtwexbgs.json: DTWEXBGS 2006-01-02 -> 2026-08-07 (5164 obs, 211 missing-value rows dropped-and-logged). Trade-weighted USD broad goods&services, daily, 2006-01 -> present (splice onto DTWEXM at 2006-01 via ratio; splice done downstream and flagged wherever used)
- fred_cpiaucsl.json: CPIAUCSL 1947-01-01 -> 2026-07-01 (954 obs, 1 missing-value rows dropped-and-logged). CPI-U SA monthly, for real-rate work in Phase 2
- fred_fedfunds.json: FEDFUNDS 1954-07-01 -> 2026-07-01 (865 obs, 0 missing-value rows dropped-and-logged). Effective fed funds, monthly avg, 1954->
- longhist_shiller_spx.json: px 1871-01 -> 2026-07, div -> 2023-06. MONTHLY-AVERAGE price convention FLAGGED. div series ends 2023-06 — post-1993 uses SPY adj so no gap in the spliced series.
- longhist_gold_monthly.json: 1833-01 -> 2026-07 (2323 obs). MONTHLY-AVERAGE convention FLAGGED.

- fred_dgs10.json: DGS10 1962-01-02 -> 2026-08-10 (16136 obs, 719 missing-value rows dropped-and-logged). 10Y Treasury constant-maturity NOMINAL yield, daily, 1962-> — fetched in Phase 2 (2026-08-12) solely for the pre-2003 TIPS real-yield splice proxy (DGS10 month-end minus trailing-12m CPI inflation). FLAGGED: proxy mixes a nominal-minus-realized-inflation construct with true market real yields at the 2003 splice.
## Standing approximations (fixed at fetch time)
1. GCUSD is a price-spliced continuous front-month: its returns are
   spot-like; futures-position excess return must be built as
   spot-return minus financing carry (bills - lease). replication.py
   quantifies and documents the lease haircut; VALIDATION_REPORT.md
   verifies the whole construction against actual GDE NAV.
2. Shiller SPX price and datahub gold are monthly AVERAGES, not
   month-end. Splices to daily month-end data occur 1993-01 (SPY) and
   1976-03 (GCUSD). Every consumer restates this caveat.
3. FRED daily series have holiday gaps ('.' rows dropped here);
   downstream alignment forward-fills RATES only (never prices),
   which is standard for yields and flagged in code.
