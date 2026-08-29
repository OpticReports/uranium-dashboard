# PROBES — verified data capability

Every claim below came from an agent that actually called the endpoint and reported the
response, then — where the verifier ran — was re-checked by a second agent with its own
independent data pull. The recon phase caught feeds returning HTTP 200 with data frozen
in 2019, date parameters silently ignored so every query returned identical bytes, and
queries truncated and presented as full history. Nothing here is accepted on a status
code alone.

Source: workflow `contrarian-swarm-design`, run wf_c1add4e4-ccb, 2026-08-29. Three of
seven verifier passes did not run (usage limit) and are marked as single-sourced.
Full untrimmed output: the run's `journal.jsonl` in the session transcript directory.

---

## P1 — What is already priced in (the denominator of a variant perception)

**Independent verification:** ran — 6 correction(s), 5 fatal flag(s)


### Verdict

BOTTOM LINE: the gap is closable and it is closable free. Every leg of a market-implied baseline and a surveyed-consensus baseline was pulled live, keyless, today. CME is a dead end (403 + explicit anti-scraping ToU) and it does not matter, because Yahoo serves individual DATED contract months for rates/energy/metals/FX with volume and full contract-life history, and the Atlanta Fed republishes the CME SOFR-options distribution itself. The one class with no free 12-24m baseline is equity indices; the one theme with no baseline at all is uranium — which is the flagship node, so the refusal path is not a corner case, it is the default for the thing Casey cares most about.

The single most important finding is that "consensus" is two different numbers right now: market-implied policy rate mid-2027 is 412-423bp (ZQ futures and Atlanta Fed SOFR options, agreeing within 10bp) while surveyed consensus is 350-363bp (NY Fed dealers+buy-side, SPF). A 50-70bp wedge on the most-quoted macro variable in the world. thesis_delta therefore cannot be a scalar against "the" consensus; it must be a pair, and sign disagreement between the pair is a NO-TRADE — P3 applied to the denominator instead of the numerator.

======================================================================
SPECIFICATION: thesis_delta
======================================================================
DEFINITION. thesis_delta = agent's stated 12-24m outcome MINUS the baseline-implied outcome for the same instrument at the same horizon date, in the instrument's own units, computed twice (market baseline and survey baseline), frozen at intake, scored at resolution.

INTAKE ROW (append-only; write once, never update; store sha256 of the exact bytes pulled):
  intake_ts_utc, instrument, instrument_class, horizon_date,
  agent_outcome_value, agent_outcome_units,
  baseline_market_source, baseline_market_value, baseline_market_asof, baseline_market_pull_ts,
  baseline_survey_source, baseline_survey_value, baseline_survey_asof, baseline_survey_release_date,
  thesis_delta_market, thesis_delta_survey, sign_agreement,
  scale_denominator, scale_denominator_source, thesis_delta_sigma,
  scoreable, refusal_reason, raw_payload_sha256.
RESOLUTION ROW: realized_value, realized_source, error_agent, error_baseline_market, error_baseline_survey, agent_beat_market, agent_beat_survey.

---------- A. RATES ----------
Units: percentage points, annualized.
Market baseline (policy rate): take the fed funds contract whose delivery month equals the calendar month of horizon_date. r_fwd = 100 - settle(ZQ<M><YY>.CBT) — the risk-neutral expected average EFFR over that month. Cross-check against Atlanta Fed MPT "Rate: mean"/100 at the reference_start nearest horizon_date; if they differ by more than 25bp, FAIL the row rather than pick one.
Market baseline (10y): bootstrap the Treasury par curve to zeros, then the n-year-forward m-year rate f = ((1+z_{n+m})^(n+m) / (1+z_n)^n)^(1/m) - 1.
Survey baseline: NY Fed SME rows subject='fed_funds_target_range', question_type='path_of_modes', panel_type='Combined', aggregation='pctl50', horizon_date nearest; multiply by 100 (file stores decimals). Or SPF TBILL/TBOND at the matching horizon quarter (VAR2..VAR6 = T..T+4; VARA..VARD = annual averages).
thesis_delta = r_agent - r_baseline, in pp.
Scale: divide by the published SPF RMSE(S) at the matching horizon — TBOND H=5 RMSE = 1.04pp. thesis_delta_sigma = delta / RMSE. A rates thesis inside ±1.0pp at 12m sits inside the consensus's own historical error bar and is not a variant perception.
Bias: SPF ME(TBOND,H=5) = -0.55pp (actual minus forecast, 1993Q1-2023Q1) — the survey baseline runs 55bp high at 4 quarters. Store raw AND debiased delta as separate columns; never silently debias.
Honesty-box note: RMSE(S/NC) = 1.08 at H=5 means the SPF 10y forecast is worse than no-change, so for the 10y the forward is the primary baseline and the survey is secondary.

---------- B. FX ----------
Units: the futures quote itself (quote ccy per base).
Market baseline: F(H) = settle of the dated CME FX contract nearest horizon_date (6E/6J/6B<M><YY>.CME; IMM quarterly only).
Survey baseline: NONE free. baseline_survey_source = NULL and the row prints "no survey consensus source" — it does NOT fall back to the forward.
thesis_delta_fx = ln(S_agent(H) / F(H)).
Also store carry_embedded = ln(F(H)/S_0) annualized: "spot unchanged" is not a null thesis, it is a bet on the carry. Label F "forward, not forecast" — …


### Findings


**1. Philadelphia Fed SPF full historical panel is free, keyless, and parses: 58 variable sheets, 233 quarterly rows back to 1968Q4, current vintage 2026Q3.**


> GET https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/survey-of-professional-forecasters/historical-data/medianLevel.xlsx -> HTTP 200, 554,444 bytes, ctype=spreadsheetml, PK magic. The ?sc_lang/&hash query params are NOT required. 58 sheets: NGDP PGDP CPROF UNEMP EMP INDPROD HOUSING TBILL BOND BAABOND TBOND RGDP ... CPI CORECPI PCE COREPCE CPI5YR CPI10 PCE10 STOCK10 BOND10 BILL10 SPR_TBOND_TBILL SPR_BAA_TBOND CPI05YF05 ... Schema per sheet: (YEAR, QUARTER, VAR1..VAR6, VARA..VARD) where VAR1=survey quarter T-1 and VAR6=T+4; A..D = annual averages for the survey year and the next three. Live sample, 2026Q3 row: TBILL = (3.62, 3.73, 3.70, 3.68, 3.63, 3.50 | A=3.665 B=3.565 C=


Build implication: This is the auditable macro consensus baseline for rates, inflation, unemployment and GDP. Ingest keyed off the release date in spf-release-dates.txt, never off the survey quarter.


**2. The SPF published forecast-error record exists as machine-readable text and says the consensus 10y-yield forecast is WORSE than a random walk at 4 quarters, and biased high by 55bp.**


> GET https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/data-files/TBOND/spf_error_statistics_tbond_1_aict.txt -> HTTP 200, ctype=text/plain, 68,776 bytes, 'Release Date: 08/22/2025'. Table 1A, History=Initial Release, sample 1993:01-2023:01, n=121: H=1 ME -0.06 MAE 0.13 RMSE 0.17 RMSE(S/NC) 0.45; H=2 -0.19/0.43/0.53/0.88; H=3 -0.30/0.61/0.74/0.98; H=4 -0.43/0.75/0.90/1.03; H=5 -0.55/0.88/1.04/1.08. Sign convention quoted verbatim from the file: 'We define a forecast error as the difference between the historical value and the forecast.' So ME(H=5) = -0.55 means the 10y actually printed 0.55pp BELOW the SPF median forecast on average over 3


Build implication: RMSE(S) at the matching horizon is the only defensible denominator for scaling a thesis_delta into significance. It also kills the survey as the rates baseline at 12m: use the forward curve, and if you use the survey, carry the -0.55pp bias explicitly.


**3. CME free settlement data is a hard NO. Both the web settlements API and the public FTP path return 403 with an explicit anti-scraping Terms-of-Use message.**


> GET https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/305/FUT?strategy=DEFAULT&pageSize=50 with a Chrome UA and a matching Referer -> HTTP 403 on 3/3 attempts, body 602 bytes: 'This IP address is blocked due to suspected web scraping activity associated with it on this CMEgroup.com page. Use of scripts, software, spiders, robots, avatars, agents, tools or other scraping mechanisms is strictly prohibited by CME Group's website Data Terms of Use.' GET https://www.cmegroup.com/ftp/pub/settle/stlint -> HTTP 403, identical 602-byte JSON body. There is no keyless CME settlement source and attempting one violates their stated ToU.


Build implication: Do not build any ingest against cmegroup.com. Route every curve requirement through the Yahoo dated-contract path and the Fed-published derivatives.


**4. The full forward curve IS obtainable free and keyless: Yahoo's chart endpoint serves individual DATED contract months (not just the front month) with volume and full contract-life history, for rates, energy, metals and FX.**


> https://query1.finance.yahoo.com/v8/finance/chart/<SYM>?range=5d&interval=1d, no auth, plain UA. Fed funds strip 2026-08-28, all bars dated 2026-08-28: ZQU26 96.3050 (3.695%) vol 66,082 | ZQV26 96.2150 (3.785%) vol 554,584 | ZQX26 96.1450 (3.855%) | ZQZ26 96.0300 (3.970%) | ZQF27 95.9800 (4.020%) | ZQH27 95.8800 (4.120%) | ZQM27 95.7750 (4.225%) | ZQU27 95.7650 (4.235%) vol 540 | ZQX27 95.8400 vol 142 | ZQZ27 95.9450 vol 0 stale bar 08-27 | ZQF28 95.95 vol 0; ZQM28/ZQZ28 'No data found'. Crude: CLV26 83.44 vol 142,318 | CLZ26 79.98 | CLM27 73.00 | CLZ27 70.45 | CLZ28 67.87 | CLZ29 66.00 vol 1,359 | CLZ30 64.67 vol 137 | CLZ31 63.27 vol 16. Gold: GCZ26 4504.10 vol 268,759 | GCZ27 4725.00 vol


Build implication: Closes the 'full curve, not just front month' question affirmatively. Symbol grammar <ROOT><MONTHCODE><YY>.<EXCH> with FGHJKMNQUVXZ and .CBT/.NYM/.CMX/.CME. Never key a horizon off '=F'; resolve the explicit month and assert its expiry. Liquidity collapses past ~15 months — require volume>0 and a floor.


**5. LIVE MEASURED WEDGE: the market-implied policy path and the surveyed consensus disagree by 50-70bp at the 12-month horizon, right now. This is the denominator the recon was missing, and it is not zero.**


> Market-implied, 2026-08-28: ZQM27 = 4.225%, ZQU27 = 4.235% (fed funds futures). Independently, Atlanta Fed MPT as of 2026-08-27, 3-month-average SOFR options-implied: reference_start 2027-06-16 'Rate: mean' 412.50bp, 'Rate: mode' 400.99bp, 'Prob: hike' 72.05%, 'Prob: cut' 16.07%. The two market sources agree within ~10bp (SOFR prints a few bp under EFFR). Survey consensus, same window: NY Fed Survey of Market Expectations released 2026-07-15, panel Combined, path_of_modes, pctl50, horizon_date 2027-06-30 = 0.0363 (3.63%), FLAT at 3.63% for every meeting from Jul-2026 through 2027-12-31, stepping to 3.38% across 2028 and 3.13% in 2029-2030; modal longer-run 3.14%. SPF released 2026-08-14: 3-m


Build implication: 'Consensus' is not one number. thesis_delta must be computed against BOTH a market baseline and a survey baseline and both stored; sign disagreement between them is the P3 no-trade condition applied to the denominator.


**6. Atlanta Fed Market Probability Tracker gives the free, keyless, daily market-implied PROBABILITY DISTRIBUTION of the policy rate out to 2029 — not just a mean path.**


> GET https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/cenfis/market-probability-tracker/mpt_histdata.xlsx -> HTTP 200, 6,746,988 bytes, spreadsheetml. Sheets LICENSE / DICTIONARY / DATA. DATA is long-format, 5 columns (date, reference_start, target_range, field, value), 299,249 rows, 859 observation dates from 2023-03-29 to 2026-08-27 (T+1). Fields per (date, reference_start): 'Rate: mean', 'Rate: mode', 'Rate: 25th percentile', 'Rate: 75th percentile', 'Prob: cut', 'Prob: hike', plus 'Prob: <x>bps - <y>bps' 25bp buckets from 0-25bp to 1675-1700bp. reference_start runs to 2029-09-19. DICTIONARY: 'The Market Probability Tracker uses Chicago Mercantile Exchange (CME) 3-month SO


Build implication: The correct comparator for the design's Brier-scored P(event) ledger primitive: a published market probability, dated daily, with real history. Also the only route to CME-derived option data that never touches cmegroup.com.


**7. NY Fed Survey of Market Expectations publishes a clean long-format XLSX per FOMC meeting with an explicit horizon_date column and separate dealer vs buy-side panels.**


> GET https://www.newyorkfed.org/medialibrary/media/markets/survey/2026/jul-2026-data.xlsx -> HTTP 200, 222,500 bytes. One sheet, 2,418 data rows, 21 columns: survey_release_date, survey_due_date, panel_type, spd_question_number, theme, subject_group, subject, question_type, question_mode, question_text, question_tag, value_tag, top_header_value, left_header_value, horizon, horizon_date, bucket_range, bucket_low, bucket_high, aggregation, aggregation_value. panel_type in {Dealer, Participant, Combined}, 152 fed-funds rows each. subject counts: fed_funds_target_range 456, headline_pce 300, real_gdp_growth 240, unemployment_rate 216, fed_assets_soma 168, headline_cpi 156, us_recession 24, global


Build implication: Highest-quality free survey baseline: 8 vintages/year vs SPF's 4, includes probability_distribution and a us_recession subject, and separates dealers from buy-side so 'consensus' can be computed under two pre-registered definitions from one file.


**8. TIPS breakevens, forwards and real yields are all free keyless on FRED, with exact series IDs and depths verified — but T7YIE does not exist and the 20y/30y breakevens are MONTHLY only.**


> fredgraph.csv?id=<ID>, no key, header 'observation_date,<ID>'. T5YIE 6,172 rows 2003-01-02..2026-08-28 last 2.30. T10YIE 6,172 rows same span last 2.31. T5YIFR (5y5y forward breakeven) 6,172 rows 2003-01-02..2026-08-28 last 2.32. T7YIE -> HTTP 404, does not exist. T20YIEM 265 rows MONTHLY 2004-07-01..2026-07-01 last 2.41. T30YIEM 198 rows MONTHLY 2010-02-01..2026-07-01 last 2.20. Real yields DFII5 6,171 rows 2003-01-02..2026-08-27 last 2.07; DFII10 same span last 2.34; DFII30 4,309 rows 2010-02-22..2026-08-27 last 2.92. Survey companions EXPINF1YR and EXPINF10YR (Cleveland Fed) 536 monthly rows 1982-01-01..2026-08-01, last 2.394 and 2.492; REAINTRATREARAT10Y 536 rows last 2.195; RECPROUSM156


Build implication: Inflation baseline fully solved and free at daily frequency. FRED throttles bursts: 12 rapid sequential pulls failed with resets and read timeouts; fresh connection per series with >=2s spacing succeeded on every retry — build the pacing in.


**9. Free dated analyst consensus for the equity sleeve EXISTS for single names via an undocumented keyless Nasdaq endpoint, and structurally does NOT exist for ETFs or indices — the refusal case is delivered by the source itself.**


> GET https://api.nasdaq.com/api/analyst/<SYM>/targetprice with a browser UA, no auth. CCJ -> 200: consensusOverview {lowPriceTarget 97.0, priceTarget 126.63, highPriceTarget 144.3496, buy 8, hold 1, sell 0} plus 13 months of historicalConsensus stamped monthly (05/01/2026 120.60, 06/01/2026 112.59, 07/01/2026 97.39, 08/01/2026 126.63). NXE -> PT 16.06 (13.71/21.65), 3 buy. UEC -> PT 20.06 (14.00/26.75), 4 buy. OKLO -> PT 74.75 (51.00/100.00), 7 buy 7 hold. URA -> HTTP 200 but data:null, bCodeMessage code 1002 'No record found.' SPY -> identical null. Consensus EPS also free: GET /api/analyst/CCJ/earnings-forecast -> 200, quarterlyForecast {Sep 2026 consensusEPS 0.26 range 0.23-0.31, 3 estimat


Build implication: Single names get a real baseline; every ETF and index returns code 1002, mapping cleanly onto scoreable=false. Monthly stamps and a 30% one-month PT jump mean the baseline is coarse and revision-chasing: store n_analysts and (high-low)/PT as a confidence weight and flag rows where the PT moved >15% month-over-month.


**10. There is NO free 12-24 month consensus forecast for an equity index. The only free equity consensus is SPF's 10-year expected annual return, Q1-only, 35 observations.**


> SPF medianLevel sheet STOCK10: 232 rows but only 35 non-empty; first 1992Q1 = 10.0, last 2026Q1 = 7.0 (expected annual-average S&P 500 return over the next 10 years). Same shape: BOND10 35 obs last 4.0, BILL10 35 obs last 3.0, RGDP10 35 obs last 2.1. All Q1-only annual questions. Nasdaq targetprice returns 'No record found' for SPY. No free strategist year-end index target series was located. The dated index-futures strip prices only cost of carry (F = S*exp((r-q)T)), so its expected excess return is zero by construction and it is not a forecast.


Build implication: For an equity index the only honest baseline at 12-24m is the risk-free rate off the Treasury curve, with the ERP printed beside it as a stated assumption and never folded in. STOCK10 is a 10y anchor; using it at 12-24m is a horizon mismatch and must be blocked.


**11. FRED carries the FOMC SEP dots for the LATEST projection round only — three rows, no vintage history — so no dot-plot track record can be built keylessly from FRED.**


> fredgraph.csv?id=FEDTARMD -> HTTP 200, exactly 3 data rows: 2026-01-01 3.8, 2027-01-01 3.6, 2028-01-01 3.4. FEDTARRM 3 rows (3.90/3.70/3.40), FEDTARRH 3 rows (4.4/4.1/3.9), FEDTARRL 3 rows (3.4/3.1/2.9). No longer-run row in the standard series and no earlier projection round. Historical vintages live in ALFRED, which fredgraph.csv does not expose keylessly.


Build implication: Use the SEP only as a current-round comparator. For a dated, scoreable official-forecaster path WITH history, the NY Fed SME xlsx archive is the substitute and is strictly better (8 vintages/yr, explicit horizon_date, dealer/buy-side split).


**12. Three live silent-staleness traps of exactly the class the recon already flagged, all in sources this build would depend on.**


> (1) Philadelphia Fed's media handler returns HTTP 200 with an HTML 404 body for ANY nonexistent media path: .../historical-data/Errorstats.xlsx, .../historical-data/rmse.xlsx and .../historical-data/TOTALLY_FAKE_zzz.xlsx all returned HTTP 200, ctype=text/html, 18,401 bytes, md5 prefix bdbd5e005208, byte-identical to each other. The real file returns ctype=spreadsheetml, 554,444 bytes, PK magic. Status code alone is worthless. (2) FRED publishes a DERIVED series ahead of its own components: on the 2026-08-28 pull T10YIE had a 2026-08-28 row (2.31) while DGS10 and DFII10 both stopped at 2026-08-27 (4.67 and 2.34; 4.67-2.34 = 2.33 = the published T10YIE for 08-27). A freshness gate on the break


Build implication: Three merge-blocking gates: assert content-type AND magic bytes on every Fed media pull; assert freshness on the COMPONENT series not the derived one; assert the exact column set per Treasury year-file and sort before use.


**13. EIA Short-Term Energy Outlook gives a free official energy price forecast with a complete vintage archive, so an auditable error record for commodities can be constructed.**


> GET https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx -> HTTP 200, 1,096,696 bytes, 28 sheets. Sheet '2tab' = Table 2 Energy Prices, stamped 'Forecast date: Thursday, August ...', monthly columns. Series codes verified in the sheet: WTIPUUS (West Texas Intermediate), BREPUUS (Brent Spot Average), RAIMUUS, RACPUUS, NGHHUUS (Henry Hub Spot), MGRARUS_$, DSRTUUS_$. Vintage archives resolve on a clean pattern with a REAL 404 for a bad month (unlike Philly Fed): archives/aug26_base.xlsx 200 (1,096,696 B), jan26_base 200 (1,065,340), mar25_base 200 (1,066,400), jul24_base 200 (1,029,673), aug20_base 200 (901,169), jan15_base 200 (860,874), zzz99_base -> HTTP 404. At least 11.5 years of dated vintag


Build implication: Crude and natural gas get both a market baseline (Yahoo dated strip) and an official point-forecast baseline with a backfillable error record — the only commodity class where the rates-quality treatment is reproducible. Uranium has neither.


**14. The market-implied distribution degrades in the far tail and the far-dated futures strip is nearly untraded — both baselines need a liquidity floor, not just a successful fetch.**


> Atlanta Fed MPT, observation date 2026-08-27: 'Rate: mode' is stable and monotone across reference_start 2026-09-16 through 2029-06-20 (374.98, 378.14, 384.83, 400.99, 402.31, 401.26, 393.42, 391.95, 394.87, 393.30, 377.82, 379.82) then prints 718.58 at reference_start 2029-09-19 — a 339bp jump while 'Rate: mean' is essentially unchanged at 411.00. Bucket coverage thins in step: 'Prob: 1675bps - 1700bps' has 1 row across the whole 299,249-row file versus 10,348 rows for 'Rate: mean'. Same day on the futures side: ZQZ27 and ZQF28 returned volume 0 with a stale 2026-08-27 bar while every contract through ZQX27 printed a 2026-08-28 bar; GCZ28 traded 2 contracts, CLZ31 16, CLZ30 137, ZQU27 540.


Build implication: Use MPT 'Rate: mean' and the percentiles, never 'Rate: mode', and cap the usable reference_start. Require volume>0 on the pull date for any futures baseline and mark deferred contracts 'indicative only' below a liquidity floor rather than silently treating them as prices.


### Blockers raised


- MISSING KEY INPUT - Atlanta Fed MPT redistribution terms. The workbook ships a sheet literally named LICENSE and it contains no license text; the only provenance strings in the file are the DICTIONARY lines saying the tracker uses CME 3-month SOFR options. Since cmegroup.com itself returns 403 with an explicit anti-scraping ToU, I will not assume the Fed's derived republication is freely reusable in a persisted internal dataset. ASK before this becomes a backbone feed.


- MISSING KEY INPUT - api.nasdaq.com/api/analyst/* is undocumented, unversioned, requires a browser User-Agent, and redistributes a third-party estimates vendor. It is the ONLY free dated single-name consensus found, so the entire equity sleeve's denominator rests on it. Need a decision on whether to depend on it and a named fallback before it is wired.


- DECISION NEEDED - uranium, the flagship theme, has no consensus denominator of any kind: no listed futures curve, no analyst coverage for URA (code 1002), no official forecast. Under the spec its thesis_delta is NULL and scoreable=false. Does an unscoreable thesis enter the ledger at all, and if it does, what stops it being sized as if it had been validated? A ledger-design question that must be answered before the intake schema is frozen.


- UNRESOLVED - forward is not expectation. thesis_delta against the ZQ strip or the SOFR-options mean conflates a rates view with a term-premium view, and the live 50-70bp market-vs-survey wedge is the same order as a plausible term premium, so the whole wedge may be premium rather than disagreement. I did not verify a free term-premium series (THREEFYTP10 sat in a batch that failed on FRED throttling and I will not claim an untested result). Until a term-premium adjustment is sourced and verified, both baselines must be reported side by side and neither may be called 'the' expectation.


- SCOPE GAP - the published error record exists ONLY for SPF's own variables at horizons out to 5 quarters (ME, MAE, RMSE, and ratios vs no-change/AR benchmarks). There is no published error record for the futures curve, for the NY Fed SME modal path, or for analyst price targets. So thesis_delta_sigma is computable for rates/inflation/unemployment/GDP and NOT for FX, commodities, equity indices or single names, where the delta must be reported raw and unscaled. Do not let a scaled and an unscaled delta share a column or a chart axis.


### Corrections from independent verification

- **OVERSTATED** — Yahoo chart endpoint serves individual DATED contract months keylessly with volume and full contract-life history — CLZ27 1,954 bars from 2018-11-20, ZQZ26 1,170 from 2021-12-31, GCZ27 1,171 from 2021-12-30 — via ?range=<R>&interval=1d; and '=F' is not the front month (ZQ=F = ZQV26, not ZQU26).
  Every quoted price and volume reproduces to the tick on 2026-08-28 (ZQU26 96.3050/66,082; ZQV26 96.2150/554,584; ZQM27 95.7750; ZQU27 95.7650/540; CLV26 83.44/142,318; CLM27 73.00; CLZ31 63.27/16; GCZ26 4504.10/268,759; GCZ28 4952.00/2; 6EU26 1.15895/215,327). ZQM28/ZQZ28 404 as claimed. The ZQ=F trap is CONFIRMED exactly — ZQ=F returns 96.21499633789062 / vol 554,584, byte-identical to ZQV26, while ZQU26 still trades on 66,082 lots; G5 stands. (The CL=F half of that evidence is void: CLU26.NYM …

- **OVERSTATED** — MPT degrades in the far tail: mode stable and monotone through 2029-06-20 then 718.58 at 2029-09-19 against a mean of 411.00 — so use 'Rate: mean' and the percentiles, never 'Rate: mode' (G7).
  The mode blowup is CONFIRMED exactly: my 2026-08-27 pull gives the identical sequence 374.98, 378.14, 384.83, 400.99, 402.31, 401.26, 393.42, 391.95, 394.87, 393.30, 377.82, 379.82, then 718.58, with mean 411.00. But the prescribed remedy is unsafe: the PERCENTILES degrade in the same row — p25 = 254.01 and p75 = 815.39 at reference_start 2029-09-19, versus 306.63/484.47 one quarter earlier. A gate that bans the mode and blesses the percentiles still ingests a 561bp interquartile range as a …

- **OVERSTATED** — NY Fed SME publishes a clean long-format XLSX per meeting: 222,500 B, one sheet, 2,418 rows, 21 columns, panel_type {Dealer, Participant, Combined} with 152 fed-funds rows each, question_type in {path_of_modes, probability_distribution, modal_point_estimate}, aggregation in {count, pctl25, pctl50, …
  File size, sheet count, 2,418 rows, 21-column header, panel split (806/806/806), decimal encoding, subject counts (fed_funds_target_range 456, headline_pce 300, real_gdp_growth 240, unemployment_rate 216, fed_assets_soma 168, headline_cpi 156, us_recession 24, global_recession 12) and release date 2026-07-15 all reproduce exactly. Two enumerations are incomplete: question_type has SIX values — path_of_modes 1392, probability_distribution 660, percentiles 192, modal_point_estimate 120, …

- **OVERSTATED** — Three live silent-staleness traps: (1) Philly Fed media handler returns HTTP 200 with a byte-identical 18,401-byte HTML 404 for any fake path; (2) FRED publishes T10YIE a day ahead of DGS10/DFII10; (3) Treasury yield CSVs change schema by year AND are not date-sorted (2015 file starts 12/31/2015 …
  (1) CONFIRMED exactly — TOTALLY_FAKE_zzz.xlsx, rmse.xlsx and Errorstats.xlsx all return HTTP 200, ctype text/html, 18,401 B, md5 bdbd5e0052080e9357eb9c0d7848bc65, byte-identical. (2) CONFIRMED exactly — T10YIE has a 2026-08-28 row (2.31) while DGS10 stops at 2026-08-27 (4.67) and DFII10 at 2026-08-27 (2.34); 4.67-2.34 = 2.33 = the published T10YIE for 08-27. (3) The schema half is CONFIRMED (2026 file 14 columns incl. '1.5 Month'/'2 Mo'/'4 Mo'; 2015 file 11). The sort half is REFUTED: both …

- **OVERSTATED** — FRED carries FOMC SEP dots for the latest round only — FEDTARMD 3.8/3.6/3.4, FEDTARRM 3.90/3.70/3.40, FEDTARRH 4.4/4.1/3.9, FEDTARRL 3.4/3.1/2.9 — three rows each, no vintage history.
  The structural claim is CONFIRMED — all four series return exactly 3 rows (2026/2027/2028), no longer-run row, no earlier round. But three of the four quoted triples are WRONG at the 2027 row. Actual: FEDTARMD 3.8/3.6/3.4 (correct); FEDTARRM 3.90/3.65/3.40 (recon said 3.70); FEDTARRH 4.4/4.4/3.9 (recon said 4.1); FEDTARRL 3.4/2.9/2.9 (recon said 3.1). SEP values are fixed between FOMC rounds, so these are transcription errors, not revisions — and they would go straight into a comparator …

- **UNSUPPORTED** — There is NO free 12-24 month consensus forecast for an equity index; the only free equity consensus is SPF STOCK10, Q1-only, 35 observations, 7.0 at 2026Q1.
  The verifiable half is CONFIRMED: STOCK10 has exactly 35 numeric observations, all Q1, first 1992Q1 = 10.0, last 2026Q1 = 7.0 (BOND10 35 obs last 4.0, BILL10 35 last 3.0, RGDP10 35 last 2.1 all confirmed), and Nasdaq refuses SPY with code 1002. But 'there is NO free 12-24m consensus for an equity index' is a universal negative resting on two tested endpoints; the recon's own supporting evidence is 'No free strategist year-end index target series was located' — absence of a search result, not …


### Fatal flags

- MOMENT MISMATCH BAKED INTO THE RATES SCHEMA. Spec section A pairs a market baseline that is a distribution MEAN (ZQ settle; MPT 'Rate: mean') against a survey baseline that is a MODE (SME question_type='path_of_modes', aggregation='pctl50'). Every rates thesis_delta_survey will carry a skew term as if it were disagreement. Measured at 2027-12, the only horizon where both sides publish a distribution: mean-vs-mean 66.4bp, mode-vs-mode 38.3bp, spec's mixed pairing 46.5bp — a ~20-28bp artifact. Worse, the SME modal path prints exactly today's target-range midpoint (3.63% vs target_range '350bps …

- WRONG DENOMINATOR AND A MISSING NULL. Section A says 'Scale: divide by the published SPF RMSE(S) at the matching horizon' with no restriction to the survey delta. SPF RMSE describes SPF's own survey errors; dividing thesis_delta_market by it produces a sigma with no meaning, and the spec's own SCOPE GAP blocker concedes no error record exists for the forward. Separately, the SPF error record stops at H=5 = four quarters ahead (verified: Table 1A has exactly H=1..5), so across the upper half of the declared '12-24m' band there IS no denominator and thesis_delta_sigma must be NULL. Neither …

- INSTRUMENT MISMATCH IN THE SURVEY FALLBACK. Section A offers 'Or SPF TBILL/TBOND at the matching horizon quarter' as the survey baseline against a fed funds futures market baseline. SPF TBILL is the 3-MONTH TREASURY BILL yield, not the overnight policy rate — measured today DTB3 = 3.69 against EFFR = 3.63, and the sign of that basis flips with the expected path. Comparing a 3m bill yield to a fed funds futures rate injects a bill/OIS basis straight into thesis_delta with no adjustment and no flag. The same confusion appears in the wedge evidence, which cites SPF TBILL6 = 3.50% as a …

- YAHOO HISTORY SILENTLY TRUNCATES UNDER THE DOCUMENTED GRAMMAR. The spec's URL form is '?range=<R>&interval=1d'. With range=max, CLZ27.NYM returns 407 bars (first 2018-11-19); the recon's reported 1,954 bars reproduce only via '?period1=0&period2=<epoch>&interval=1d' (1,957 bars / 1,954 non-null). Same for ZQZ26 (245 vs 1,170) and GCZ27 (245 vs 1,171). Both forms return HTTP 200 with no error. Any backfill of a per-contract baseline or error record built on the documented grammar loses ~79% of the contract's life and computes statistics on a window far shorter than claimed. Additionally there …

- STEO MONTH COLUMNS CARRY NO YEAR AND THE HISTORY/FORECAST SPLIT IS A FORMULA. Sheet '2tab' has 72 monthly data columns whose header row is only 'Jan','Feb',...,'Dec' repeated six times. The year anchor is Dates!D3 (=YEAR(D1)-4, cached 2022), the start month Dates!D5 (202201), and the last historical month Dates!D7 (202607) — all formulas, so openpyxl without data_only=True returns formula strings and the 'Forecast date' stamp the spec relies on reads as the literal '=Dates!D3'. An ingest that indexes 2tab positionally without those anchors assigns every WTIPUUS/BREPUUS/NGHHUUS value to the …


---

## P2 — Options surface and carry-vs-catalyst divergence

**Independent verification:** ran — 5 correction(s), 5 fatal flag(s)


### Verdict

QUALIFIED YES on pricing, PARTIAL on the detector, and one hard NO you must escalate.

CAN a keyless brain price a defined-loss options expression? YES, for US-listed equities and ETFs, today, with no key. The recon's hard blocker is dead. Feeds: cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json for per-strike bid/ask/IV/OI/greeks out to 840 days (underscore-prefix index symbols); .../quotes/{SYM}.json for spot and iv30; marketdata.theocc.com/series-search for independent per-strike OI (58/58 exact agreement with Cboe on URA) and position limits; home.treasury.gov daily-treasury-rates.csv for the discount curve (use it, not FRED — FRED failed all session); Yahoo chart API with a DESCRIPTIVE User-Agent for realized vol; Cboe us_indices CSVs for index history; Deribit for the full crypto surface. Computation: cost comes straight off bid/ask, no model needed. Carry comes from put-call parity F = K + (Cmid-Pmid)e^(rT), median over near-ATM strikes, reported with its across-strike dispersion band — validated because it recovers TLT's real distribution yield (+4.4 to +5.1%/yr) and SPY's (+0.6 to +0.9%/yr) out of nothing but option quotes and the Treasury curve.

CAN it detect carry-vs-catalyst divergence? HALF of it, cleanly. The CARRY half is fully computable now: forward variance between adjacent expiries, 25-delta skew term structure, implied net carry, and VRP. Whether the cost of a trade has repriced is answerable today for any liquid US-listed underlying. Two halves are missing. (1) There is NO free options-surface history — Cboe 403s dated paths, OCC returns byte-identical output for every reportDate — so the detector starts with zero history, cannot be backtested, and cannot z-score itself. It must accumulate its own snapshots for months before any threshold is calibrated. Build the persistence layer FIRST or the detector is a write-only ledger with extra steps. (2) The CATALYST half has no data source — I found no dated machine-readable policy-event calendar in this probe, and the task did not scope one. Divergence needs both legs.

The hard NO: CME is IP-blocked with an explicit anti-scraping message on all 6 hosts/paths tried. The entire futures-options surface — CL, GC, ZN, ES, 6E — is dark. Scope futures options out of v1 and make those nodes display "no surface coverage", never a benign score.

Two findings that change the design, not just the feed list. First, the naive vega-weighted ATM IV FABRICATED two catalyst signals on SPY (22.22% and 29.41% forward vol) that were pure strike-listing-density artifacts and vanished to 17.35%/18.85% under fixed-moneyness interpolation — the detector's first two live alerts would both have been false. Second, a put-call IV agreement test at the same strike is a free self-validating gate that passes TLT 157/157 and SPY 771/780 while failing URA on 21 of 51 near-ATM strike-pairs. The same feed is production-grade for the index and 41% unreliable on the repo's own uranium node. Gate per-symbol and per-expiry.

The concrete cost, on URA: a genuine 6-month expression does not exist at usable liquidity (URA jumps 140d to 231d, and the 231d expiry carries 539 total OI with 41% ATM parity failures). At the nearest usable tenor, 140d, the long 44P/short 37P spread costs 6.32% of spot crossing the bid/ask — of which $0.40, or 13.8% of the premium, is pure execution friction — for max profit 8.94%, R:R 1.41:1, breakeven -10.4%. The cash short is carry-POSITIVE by +4.13%/yr, so choosing defined loss gives up 6.32% premium plus 1.60% forgone carry = 7.92% of spot over 140 days = 20.65%/yr, and moves the breakeven 5.49 URA points, 12.0% of spot, further away. URA's skew is INVERTED (25d put 4.26pp BELOW the 25d call, versus SPY's +4.99pp) — the puts are already relatively cheap for a crowded-long name, and the expression still costs that much. This is live, on-node confirmation of the evidence base's conclusion that long optionality is a confirmation-phase instrument, not a probe-phase one: at the probe phase you need better than 41% on a -10.4% move just to break even.


### Findings


**1. The per-strike IV surface exists, is free, keyless, and covers every optionable US name including the repo's own uranium nodes — this closes the inversion track's hard blocker outright.**


> GET https://cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json → HTTP 200 for 18/19 probed symbols. Each record carries option, bid, bid_size, ask, ask_size, iv, open_interest, volume, delta, gamma, vega, theta, rho, theo, last_trade_price/time. Counts (n_options / n with iv>0): SPY 13514, _SPX 12877644 bytes, _RUT 12144/10720, QQQ 11882/10535, GLD 8260/7285, IWM 5572/4843, SLV 5250/4761, USO 4610/4248, TLT 2516/2168, SOXS 2154/1671, EEM 2006/1751, XLE 1910/1678, TQQQ 1702/1536, UVXY 1694/1505, _VIX 1520/1365, OKLO 1282/1104, CCJ 1062/896, URA 984, UEC 624/504, NXE 230/198. Only SRUUF (OTC) 403. Index symbols need a leading underscore (_SPX, _VIX, _RUT). Companion quote endpoint /dela


Build implication: Delete the 'no per-strike IV' gate from the Inverter. OTM option expressions become priceable for US-listed equities/ETFs. Wire this as the surface source; it needs no key, no auth, no session cookie.


**2. There is NO free options-surface HISTORY anywhere. Cboe refuses dated paths and OCC silently ignores its date parameter — the same failure mode P6 was written for. Every surface number is a live snapshot only.**


> GET https://cdn.cboe.com/api/global/delayed_quotes/options/2026-08-27/SPY.json → HTTP 403 <Error><Code>AccessDenied</Code>. OCC series-search md5 test: reportDate=20260820 → 16075f879beac65526ca7bbe40751154; reportDate=20260703 → 16075f879beac65526ca7bbe40751154; no date param → 16075f879beac65526ca7bbe40751154. Byte-identical across all three, exactly like the known-broken OCC volume-totals endpoint.


Build implication: BINDING CONSTRAINT. You cannot backtest a divergence threshold, cannot z-score today's forward vol against its own history, and cannot Brier-score the detector before running it forward. The PERSISTENCE GAP stops being a nice-to-have and becomes the first thing built: a daily snapshot writer with an immutable append-only store, started before any threshold is calibrated. Any 'percentile' or …


**3. CME is hard-blocked at the IP/WAF layer on every host and path — the entire futures-options surface (settlements, per-strike OI, implied vols on CL/GC/ZN/ES/6E) is dark, not merely inconvenient.**


> HTTP 403 with body {"message": "This IP address is blocked due to suspected web scraping activity associated with it on this CMEgroup.com page..."} for www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/133/FUT, .../Options/Settlements/133/OOF, www.cmegroup.com/ftp/pub/settle/stlads, www.cmegroup.com/services/nymex-settlements, and bare cmegroup.com/CmeWS/... ftp.cmegroup.com/pub/settle/stlads and ftp.cmegroup.com/settle/stlads → curl (35) Recv failure: Connection reset by peer. datamine.cmegroup.com/cme/api/v1/list → connection failure. 6 hosts/paths, 0 successes.


Build implication: Do not scope any futures-options logic into v1. For any theme whose real optionality lives in futures options (energy, rates, metals, FX), the brain must display 'no options-surface coverage' — never a benign or imputed score. This is the structurally-dark-crowding rule applied to the surface layer.


**4. OCC series-search is the working replacement for the broken volume-totals endpoint and gives per-strike, per-expiry call/put open interest that agrees with Cboe EXACTLY — a genuine independent second source for the OI field.**


> GET https://marketdata.theocc.com/series-search?symbolType=U&symbol=URA → HTTP 200, 22782 bytes, 479 series parsed (tab-delimited: ProductSymbol, year, month, day, strike-integer, strike-decimal, C/P, Call OI, Put OI, Position Limit). Cross-check against the Cboe chain for URA 2027-01-15: 58/58 strikes exact agreement (100.0%) on BOTH call and put OI — e.g. K=40 call 16837/16837 put 8327/8327; K=60 call 18026/18026 put 10022/10022; K=50 call 9362/9362 put 15624/15624. SPY series-search also 200 (454855 bytes).


Build implication: Satisfies P10's independent-data-pull requirement for the OI field at zero cost. Also yields position limits (URA 25,000,000) — a free hard ceiling on how large any single-name flow can get. Note it is a live snapshot only (see the date-parameter finding), so it dual-sources today's OI, not history.


**5. The naive vega-weighted ATM IV fabricates false catalyst signals. Two apparent SPY event-kinks were pure strike-composition artifacts and vanished under a fixed-moneyness interpolation.**


> SPY forward vol between adjacent expiries, vega-weighted ATM over strikes within ±5% of spot: 2027-01-29 (T=154d) 22.22% and 2027-06-30 (T=306d) 29.41%, both towering over a ~15-17% baseline. Those two expiries carry n=110 and n=94 qualifying strikes versus n=30 for their neighbours. Recomputing ATM IV by linear interpolation of IV in strike evaluated exactly at K=spot (identical construction at every expiry) collapses them to 17.35% and 18.85%, and the whole SPY forward-vol curve becomes smooth and monotone from 10.38% (T=4d) to 21.47% (T=840d) with no kink anywhere.


Build implication: Mandatory method spec: ATM IV must be strike-interpolated at fixed moneyness, never a vega- or OI-weighted average over a variable strike set, because Cboe lists far more strikes on some expiries than others. Had this gone in unchecked, the detector's first two live 'catalyst divergence' alerts on SPY would both have been artifacts of strike listing density.


**6. A put-call IV agreement test at the same strike is a self-validating merge-blocking gate that needs no external reference — and it shows the same feed is production-grade for SPY/TLT and 41% unreliable for URA.**


> Fraction of near-ATM strike-pairs (T>=7d, |K/S-1|<=3%) where |IV_call - IV_put| > 2 vol points: TLT 0/157 (0%); SPY 9/780 (1.2%, and every failure has OI=0 on one leg); URA 21/51 (41.2%). Worst URA cases: 2026-10-09 K=46.5 IV_call 52.36% vs IV_put 35.98% (16.38pp divergence, OI 0/0); K=46.0 51.99% vs 35.62% (16.37pp); 2027-04-16 K=47.0 48.96% vs 41.10% (7.86pp). The URA 2026-10-09 expiry carries total OI of 7 across the whole expiry.


Build implication: Ship this as the surface gate: reject any (symbol, expiry) whose near-ATM put-call IV divergence exceeds ~2pp or whose expiry-level OI is below a floor. It is per-symbol and per-expiry, not global — a single feed-level health check would pass URA while 41% of its ATM surface is unusable.


**7. Cboe chain snapshots refresh per-symbol on independent cadences: at one wall-clock fetch the freshest and stalest chains were 114 minutes apart, and URA's chain was 108 minutes older than its own quote file on a day URA fell 5.8%.**


> chain_ts across 19 symbols fetched inside one ~15-minute window: URA 19:59:52, UVXY 20:03:38, CCJ 20:04:28, OKLO 20:52:25, SOXS 20:55:46, UEC 21:13:42, NXE 21:27:32, then IWM/SLV/TLT/_RUT/EEM/QQQ/TQQQ/GLD/USO/XLE/_VIX all 21:47:22-21:47:43, SPY 21:53:35. Spread = 114 minutes. URA chain_ts 19:59:52 vs URA quote_ts 21:47:49 = 108 min apart, while URA's own quote showed price_change_percent -5.7887 for the session.


Build implication: P6 assertion must be per-symbol on the chain file's OWN timestamp, and the spot used to compute moneyness/greeks must come from the chain snapshot's own reference — never from the separately-refreshed quote file. Thinner symbols are staler, so the staleness bias lands hardest exactly on the single names the crowding work cares about.


**8. Put-call parity against the Treasury curve recovers the implied net carry (r - q - b) and self-validates: TLT's implied dividend-plus-borrow lands on its real distribution yield.**


> F = K + (Cmid - Pmid)·e^(rT), median across near-ATM strikes, r interpolated from home.treasury.gov 08/28/2026 (1Mo 3.84, 3Mo 3.90, 6Mo 4.02, 1Yr 4.15). TLT implied q+b: 2026-12-18 +5.147%/yr, 2026-12-31 +5.062%, 2027-01-15 +4.847%, 2027-02-19 +4.577%, 2027-03-19 +4.433%, 2027-04-16 +4.421% — a smooth term structure matching TLT's actual distribution yield, on an ETF with negligible borrow. SPY implied q+b +0.61% to +0.93%/yr across six expiries. URA implied q+b +0.224% (112d) and -0.238% (140d).


Build implication: This is the carry half of carry-vs-catalyst and it is fully computable keyless today. It also gives borrow cost — normally a paid datapoint — as the residual once the dividend is known. Use Treasury.gov, not FRED, for the discount curve: it returns the whole curve in one call and FRED's fredgraph.csv failed repeatedly this session (curl 92 INTERNAL_ERROR, then curl 52 Empty reply from server).


**9. The across-strike dispersion of the parity-implied forward is comparable in size to the carry signal itself, so any single-strike carry read is unusable — and the noise band narrows with liquidity, which makes it a usable confidence measure.**


> Carry noise band = [min,max] implied carry across the 14-25 near-ATM strikes used. URA 2026-12-18: median +3.629%/yr, band [+2.71%,+7.51%], width 4.80pp. URA 2027-01-15: median +4.127%, band [+2.46%,+6.35%], width 3.89pp. URA 2027-04-16: median +7.000%, band [+4.75%,+7.80%], width 3.06pp. SPY 2026-12-18: median +2.989%, width 3.61pp (46 strikes). TLT 2027-03-19: median -0.477%, width 0.70pp (25 strikes, deep OI). TLT 2027-02-19 width 1.40pp.


Build implication: Emit implied carry only as median ± measured band, and refuse to emit at all when the band exceeds the median. The band is a free, per-name, per-expiry liquidity score computed from the same pull — no separate liquidity feed needed.


**10. CONCRETE COST: a defined-loss 140-day bearish URA expression costs 6.32% of spot in premium and gives up a further 1.60% of positive carry, totalling 20.65%/yr, and pushes the breakeven 12.0% of spot further away than the cash short.**


> URA spot 45.8577, 2027-01-15 (T=140d). Long 44P / short 37P debit spread: cost crossing both bid/ask = $2.900 (6.32% of spot); mid = $2.500 (5.45%) — so bid-ask friction alone is $0.40 = 13.8% of the premium. Max profit $4.100 (8.94% of spot), R:R 1.41:1, breakeven 41.10 (-10.4%), full payoff needs -19.3%. Cash short: parity-implied net carry +4.127%/yr = +1.596% over the window, so the short is carry-POSITIVE and its breakeven is 46.589, ABOVE spot. Total give-up for the capped loss = 6.32% + 1.60% = 7.92% of spot over 140d = 20.65%/yr. Breakeven gap between the two expressions = 5.49 URA points = 12.0% of spot. Wider structures: 44/32 costs 8.72% of spot (R:R 2.00:1); 41/28 costs 5.89% (R:


Build implication: Live confirmation of the evidence base's 'long options are a CONFIRMATION-phase expression, not a probe-phase one'. At the probe phase the brain would need P(URA <= -10.4% by 2027-01-15) to beat roughly 1/(1+1.41) = 41% just to break even on EV. Hard-code the breakeven-gap number into the expression selector: a defined-loss structure must be justified against 12% of spot in forgone breakeven, not …


**11. URA's volatility skew is INVERTED versus the index — 25-delta puts trade BELOW 25-delta calls by 3-7 vol points — the signature of a crowded upside trade, and it means the bearish expression is already relatively cheap and still costs 20.65%/yr.**


> 25-delta skew (put IV minus call IV) at 2026-12-18 (T=112d): SPY +4.99pp (25dP K=730 delta -0.251 IV 17.23% OI 15787; 25dC K=815 delta +0.255 IV 12.24% OI 12058); TLT +0.00pp (25dP K=79 IV 11.60% OI 13522; 25dC K=87 IV 11.60% OI 66157); URA -4.26pp (25dP K=40 delta -0.240 IV 45.38% OI 36; 25dC K=58 delta +0.240 IV 49.64% OI 6). URA skew is negative across its term structure: -6.63pp (14d), -6.83pp (21d), -4.26pp (112d), -3.34pp (140d), -7.39pp (231d), -5.62pp (511d).


Build implication: Skew sign is a free, live, per-name crowding read that is about the SHAPE of the distribution — exactly the thing the evidence base says crowding actually predicts — and it needs no trader-category identification, sidestepping the P3 identification problem entirely. Confidence is medium not high because the URA 25-delta wings carry OI of 36 and 6; the SIGN is stable across six expiries, the …


**12. Deribit exposes a complete crypto IV surface plus both realized-vol and a VIX-analogue with history — the crypto leg needs no additional work.**


> get_book_summary_by_currency?currency=BTC&kind=option → HTTP 200, 461549 bytes, 1030 instruments, 1030/1030 carrying mark_iv, 13 expiries (25SEP26 n=130, 25DEC26 n=118, 30OCT26 n=106, 26MAR27 n=102, 25JUN27 n=100, 27NOV26 n=88, out to 9 months), each row carrying open_interest, bid_price, ask_price, mark_price, mark_iv, underlying_price. get_historical_volatility?currency=BTC → 200, hourly realized-vol series. get_volatility_index_data (DVOL) → 200, hourly OHLC bars. The repo's existing treasury-canary/backend/app/sources/deribit.py uses only get_book_summary_by_instrument and get_funding_rate_history — it touches none of the surface endpoints.


Build implication: Extend the existing module rather than write a new one; carry forward its two documented QA traps (separate cache timestamps per endpoint, and the ~744-point/31-day cap forcing <=30-day fetch windows). Unlike Cboe, Deribit's DVOL and historical-volatility endpoints DO accept start/end timestamps, so crypto is the one asset class where the detector has real history to calibrate against on day 1.


**13. FX forward points cannot be recovered from free futures-minus-spot; the covered-interest-parity route from rate curves works instead, leaving only the cross-currency basis unobtainable.**


> Futures-minus-spot fails two independent ways. Timestamp: 6E=F regularMarketTime 20:59:59Z vs EURUSD=X 21:29:05Z — 29 minutes apart, a gap that swamps the ~16bp 1-month forward point; same for 6B=F vs GBPUSD=X. Precision: 6J=F quotes 0.00625 with a 1e-5 tick, so USDJPY resolution is 0.256 yen = 0.1597% of spot = ±3.43%/yr of noise on the implied differential at a 17-day tenor. CIP route works: home.treasury.gov (USD 1Mo 3.84 / 3Mo 3.90 / 6Mo 4.02) + ECB data-api ESTR (2026-08-27 = 2.188) → EURUSD F(30d) 1.16029 (+15.9 pts), F(91d) 1.16369 (+49.9 pts), F(182d) 1.16931 (+106.1 pts) off spot 1.1587.


Build implication: Build FX forwards from rate differentials, never from scraped futures. Document the residual honestly: the cross-currency basis is the part CIP cannot see, it is not free, and it is precisely the part that blows out in funding stress — so an FX carry reading must be labelled 'basis not observed'.


**14. Realized-vol inputs are free but the estimator choice is not innocent: on URA the two standard estimators disagree by 13 vol points over the same 21 days — more than the volatility risk premium being measured — so no VRP claim on URA survives.**


> URA daily bars 2023-07-24 to 2026-08-28 (779 bars, Yahoo). Close-to-close annualised: 10d 57.76%, 21d 46.26%, 63d 51.46%, 126d 52.07%, 252d 52.93%. Parkinson high-low over the same windows: 10d 36.33%, 21d 33.22%, 63d 37.95%, 126d 39.27%, 252d 42.92%. The 21d gap is 13.04 vol points. URA IV30 is 43.096%, which sits INSIDE the [33.22, 46.26] estimator band, so the apparent VRP of -3.17 points (IV/RV 0.93x) is smaller than the measurement uncertainty. By contrast SPX is clean: Cboe SPX_History.csv (13022 rows, 1975-01-02 to 2026-08-27) gives RV21 11.53% against VIX 14.51 (08/27) = +2.98 points, consistent with the published VIX 13-16 regime figure of +3.40.


Build implication: Compute both estimators always and refuse to emit a VRP whenever they disagree by more than the VRP. Operational note that unblocked this: Yahoo returned HTTP 429 to a standard browser User-Agent on every attempt but HTTP 200 to the repo's own descriptive UA 'Mozilla/5.0 (canary-dashboard)' — same descriptive-UA rule already known for Wikipedia pageviews. Cboe's index CSVs …


### Blockers raised


- P1 DECISION-GATING, for Casey: no free options-surface history exists (Cboe 403s dated paths; OCC returns byte-identical output for reportDate=20260820, 20260703 and no-date). This means the carry-vs-catalyst detector cannot be backtested, cannot z-score itself, and cannot be Brier-scored before it runs live. Three options — (a) fund a historical options-surface vendor (ORATS/IVolatility/CBOE DataShop) so thresholds can be calibrated before launch; (b) ship the detector as observation-only with a daily snapshot writer and no thresholds for ~6-12 months while it accrues its own history; (c) scope options out of v1 entirely. Under the house rule I am not modelling around this with assumed history. Which?


- P1 DECISION-GATING, for Casey: the CATALYST half of carry-vs-catalyst divergence has no identified data source. I probed the cost side successfully but found nothing free and machine-readable that supplies dated policy-event triggers (NRC/DOE decisions, Section 232 rulings, Fed dates, election dates) for the uranium and macro nodes. Without it the detector measures whether vol is bid in a window but cannot say whether a catalyst sits in that window. Do you want a scoped follow-up probe for event-calendar sources, or should the detector ship as a pure cost-repricing monitor with the catalyst leg supplied manually per deal?


- P1 DECISION-GATING, for Casey: CME is IP-blocked outright (403 anti-scraping on 6 hosts/paths), so futures options on CL/GC/ZN/ES/6E are unavailable at any lag. Confirm the ruling: futures-options nodes display 'no surface coverage' and are formally out of v1 — versus buying CME DataMine or a vendor. I have NOT modelled around this with equity-ETF proxies (USO options are not WTI futures options and the basis is exactly the thing being measured).


- P2 SCORE-MOVING, for Casey: the cross-currency basis is not obtainable free. CIP from Treasury.gov + ECB gives EURUSD forwards, but the basis residual is unobserved — and it is precisely the component that blows out in funding stress, i.e. when an FX carry reading would matter most. Accept an FX carry signal permanently labelled 'basis not observed', or drop the FX sleeve from v1?


- P2 SCORE-MOVING, for Casey: URA has no tradeable 6-month expiry (140d then 231d, and the 231d carries 539 total OI with 41% of near-ATM strike-pairs failing the put-call IV integrity test). Any URA options expression is therefore locked to the ~140d January tenor or must accept an untradeable quote. Confirm the horizon grid should snap to actual liquid listed expiries per name rather than to a fixed 6-month target — this changes the ledger's forecast-horizon convention, which is currently written as fixed N-month windows.


### Corrections from independent verification

- **OVERSTATED** — Naive vega-weighted ATM IV fabricated two SPY forward-vol spikes (22.22%, 29.41%) that were strike-density artifacts; fixed-moneyness interpolation collapses them to 17.35%/18.85% and 'the whole SPY forward-vol curve becomes smooth and monotone from 10.38% to 21.47% with no kink anywhere'.
  The core is CONFIRMED and reproduces to two decimals on my own snapshot: vega-weighted forward vol 22.22% at 2027-01-29 (n=110 strikes) and 29.41% at 2027-06-30 (n=94) against n=30 neighbours; strike-interpolated at K=spot they collapse to 17.34% and 18.86%. The supporting claim is REFUTED. The interpolated curve is neither smooth nor monotone: 10 of its 30 forward steps DECREASE. The 2026-09-08 expiry prints a 7.36% forward-vol trough (vs 13.01% before and 11.75% after) because Labor Day 2026 …

- **REFUTED** — Put-call parity recovers implied net carry and self-validates on TLT (+4.42% to +5.15%/yr) and SPY (+0.61-0.93%); URA implied q+b = +0.224% (112d) and -0.238% (140d).
  The METHOD is sound and I reproduce its shape, but the URA numbers are computed off the wrong spot — the exact error the same report's own staleness finding forbids. The URA chain (timestamp 19:59:52, identical snapshot to the report's) carries current_price 45.615; the report used 45.8577 from the separately-refreshed QUOTE file. Feeding 45.8577 into my code reproduces the report's URA figures (+0.774% / +0.011%); the chain's own spot gives q+b = -0.955% (112d) and -1.372% (140d) — a SIGN FLIP …

- **OVERSTATED** — Across-strike dispersion of the parity-implied forward is comparable to the carry signal itself; URA 2026-12-18 band width 4.80pp, 2027-01-15 3.89pp, 2027-04-16 3.06pp, TLT 2027-03-19 0.70pp.
  The qualitative point holds — band width shrinks with liquidity and is a usable free confidence measure — but the widths are NOT measured constants, they are set by the moneyness window chosen, and the report never states its window. On the identical URA snapshot with a +/-10% window I get widths of 2.47pp (112d), 2.50pp (140d), 3.06pp (231d) against the reported 4.80/3.89/3.06 — only the 231d matches. TLT 2027-03-19 comes out 0.36pp against the reported 0.70pp, 2027-02-19 0.51pp against …

- **OVERSTATED** — URA 44P/37P 140d spread costs 6.32% of spot, gives up 1.60% forgone carry, totals 7.92% over 140d = 20.65%/yr, breakeven -10.4%, breakeven gap 12.0% of spot; probe phase needs P(URA <= -10.4%) to beat 1/(1+1.41) = 41%.
  Option leg CONFIRMED exactly: long 44P bid/ask 3.60/4.10 (OI 481), short 37P 1.20/1.50 (OI 2776), cross debit $2.900, mid $2.500, friction $0.400 = 13.8% of premium, max profit $4.100, R:R 1.41:1. Wider structures also exact (44/32 R:R 2.00:1; 41/28 R:R 3.81:1). Two corrections. (a) Spot: on the chain's own 45.615 the debit is 6.36% of spot (not 6.32%), breakeven -9.9% (not -10.4%), full payoff -18.9% (not -19.3%). (b) Carry: with the corrected net carry of +5.337%/yr the forgone carry over …

- **REFUTED** — URA's two RV estimators disagree by 13 vol points over 21 days, more than the VRP being measured, so no VRP claim on URA survives — whereas SPX is clean (RV21 11.53% vs VIX 14.51 = +2.98). Also: Yahoo 429s a browser UA but 200s a descriptive UA; use Treasury.gov not FRED because FRED failed all …
  The arithmetic is right; the inference and both operational notes are wrong. Numbers confirmed: URA 779 bars 2023-07-24 to 2026-08-28; Parkinson 36.33/33.22/37.95/39.27/42.92 matches to the second decimal; close-to-close matches under sample stdev (ddof=1) — 46.26 at 21d, gap 13.04pp; SPX RV21 11.54% vs VIX 14.51 = +2.97. But the disagreement is NOT a URA data-quality signal. Parkinson ignores overnight gaps and therefore structurally understates on every name: my measured …


### Fatal flags

- WRONG SPOT ON THE CARRY LEG. URA implied carry was computed off the quote file's spot (45.8577) instead of the chain snapshot's own spot (45.615), violating the report's own staleness rule. This flips the sign of implied q+b at both URA expiries (+0.224%/-0.238% reported vs -0.955%/-1.372% correct) and understates the 140d net carry by 29% (+4.127%/yr reported vs +5.337%/yr correct), which propagates into the headline cost of the URA expression (20.65%/yr reported vs 21.92%/yr correct). Any production carry calculation must take S from the same JSON document as the option quotes.

- THE PRESCRIBED ATM-IV FIX DOES NOT PRODUCE A CLEAN CURVE. Fixed-moneyness interpolation removes the two strike-density artifacts as claimed, but 10 of 30 forward-vol steps still decrease and the 2026-09-08 expiry prints a 7.36% forward-vol trough (3.34% on a trading-day clock) purely because Labor Day falls in the gap — a calendar-versus-trading-day unit error. A detector shipped on the report's spec would still fire false catalyst alerts at every holiday-straddling expiry. Forward variance needs an explicit trading-day/holiday calendar AND a minimum-gap floor, neither of which is in the spec.

- THE PROPOSED VRP GATE IS A VOLATILITY-LEVEL FILTER, NOT A DATA-QUALITY FILTER. 'Refuse to emit a VRP whenever the two estimators disagree by more than the VRP' uses an absolute vol-point threshold against a gap that is proportional: close-to-close/Parkinson ratios are 1.36 on SPY, 1.39 on URA, 1.97 on TLT. Parkinson structurally understates because it discards overnight gaps. The rule would silence every high-volatility name by construction and pass every low-volatility one, which inverts the intended screen. Use the ratio, or an estimator that includes overnight returns …

- THE BREAKEVEN-PROBABILITY RULE IS MISCOMPUTED. 'At the probe phase the brain needs P(URA <= -10.4%) to beat 1/(1+1.41) = 41%' attaches the full-payoff probability to the breakeven price. R:R 1.41:1 makes 41.5% the required probability of the FULL move to K=37 (-18.9% on the correct spot); the breakeven price is -9.9%. If this is hard-coded into the expression selector as written it will approve defined-loss structures at roughly half the probability threshold they actually require.

- THE CARRY-BAND GATE IS TUNABLE, NOT MEASURED. The 'refuse to emit when the band exceeds the median' rule rests on band widths that are a function of the undocumented moneyness window. On the identical URA snapshot a +/-10% window yields widths of 2.47pp/2.50pp/3.06pp against the reported 4.80/3.89/3.06, and TLT 2027-03-19 yields 0.36pp against 0.70pp. Any name can be moved across the gate by widening or narrowing the window, so the window must be pinned in the spec and the strike count emitted alongside every band.


---

## P3 — The official-actor and synchronizing-event corpus

**Independent verification:** ran — 9 correction(s), 5 fatal flag(s)


### Verdict

The corpus exists and is better than expected; the recon's framing of it is wrong. BIS central bankers' speeches is a genuine flagship asset — 20,728 full-text speeches, 1996 to present, free, keyless, one 129MB zip or cheap per-year zips — but it is a POST-HOC EXPLANATION corpus, not an event feed. Measured over all 20,728 rows the publication lag is median 5 days, p90 27, p99 84, and it detects capitulation (+1d for the SNB's own 2015-01-15 exit speech) an order of magnitude faster than defence (+23d for the 2011 floor, +58d for the SNB's own first mention; exactly one LDI-mentioning speech exists in the entire 2022 gilt crisis window). Build the classifier and base rates on BIS offline, keyed to the URL-derived publication date; run the live detector off the primary feeds. Those live feeds are all present and same-day: Fed/ECB/BoJ/BoE/SNB RSS (shallow rolling windows, daily polling mandatory, persistence is a v1 prerequisite), and — the best find of this pass, absent from the recon entirely — the NY Fed markets API, which serves SRF repo operations same-day, 1,600 central-bank FX swap drawings back to 2010, SOMA weekly from 2003 and SOFR at T+1, all keyless. Treasury adds a true forward calendar (7,680 auctions from 1979 with a 2-7 day announcement lead, 218 buyback operations from 2000), and the Federal Register API adds dated mandate changes from 1994 with forward effective_on plus a pre-publication feed. FX intervention disclosure is structurally lagged and must stay off the live path; the synchronizing-event calendar is half sourced (FOMC, COT, EIA, NYSE) and half hard-403 (OPEC, CME, S&P, BLS) so it needs an expiring hard-coded table. The classification rule is frozen above on the object-and-boundedness axis, coder-checkable in five steps, and the five worked examples settle the question the recon left open: the official actor won or is still winning in three of five (HKMA 42.9 years, BoJ YCC 7.5 years, BoE 2022 as a bounded plumbing operation that ended on schedule), and the two clean breaks came only after 709 and 1,227 days of bleeding. That arithmetic is why this detector ships as a hazard clock and a candidate generator, exactly as the killed-claims list demands, and never as a direction, an EV rank or the largest allocation.


### Findings


**1. BIS central bankers' speeches: the bulk corpus is real, free, keyless and deep — 20,728 speeches, 1996-09-10 to present, full unredacted text, 1,021 named authors. Download mechanism established.**


> GET https://www.bis.org/speeches/speeches.zip -> HTTP 200, application/zip, 129,497,217 bytes, 92s. Single member speeches.csv, columns exactly: url,title,description,date,text,author. Parsed 20,728 rows (csv.field_size_limit must be raised; default 131072 throws). Median text length 15,955 chars; 0 rows with <200 chars. Per-year counts: 1996=10, 1997=212, 2000=298, 2004=572, 2008=871, 2013=1003 (peak), 2020=711, 2025=743, 2026=360. Per-year zips also exist and are cheap: speeches_1996.zip 66KB ... speeches_2026.zip 2.0MB, all HTTP 200. Top authors Trichet 478, Draghi 337, Tetangco 272, Coeure 254, Bernanke 252.


Build implication: Use per-year zips for incremental refresh, not the 129MB monolith. This is the training/backtest corpus for the classifier vocabulary — nothing else free comes close. It is NOT the live detector (see next two findings).


**2. KILL THE RECON'S FRAMING: BIS is not an event feed. Measured over all 20,728 rows, the median publication lag is 5 days, p90 27 days, p99 84 days. Backtesting the official-actor detector on the corpus `date` field leaks up to three months of lookahead for 8.3% of documents.**


> Lag = date parsed from the BIS Review URL slug (/review/rYYMMDDx) minus the `date` field (delivery date), computed on all 20,728 rows, 0 unparseable. min -729, p05 0, p25 1, median 5, p75 11, p90 27, p95 42, p99 84, max 3687. Share <=1d 26.3%, <=7d 67.2%, <=14d 81.1%, <=30d 91.7%. Median lag by recent year: 2019=2, 2022=2, 2024=3, 2025=4, 2026=6. Separately, the bulk zip itself is stale: Last-Modified Mon, 06 Jul 2026 20:27 GMT (53 days old today) and max date inside speeches_2026.csv = 2026-06-22 (67 days old), while the RSS already carries 2026-08-17.


Build implication: Every point-in-time reconstruction must key off the URL-derived publication date, never the `date` field. Add a merge-blocking gate: HEAD the zip, assert Last-Modified >= today-45d, and assert max(url_pub_date) >= today-14d. Visual of the lag distribution written to /tmp/claude-0/-home-user-uranium-dashboard/a0106a67-22d0-5920-b96a-b21949d01b35/scratchpad/bis_lag.html


**3. THE DETECTOR-DEFINING ASYMMETRY: the BIS corpus detects official CAPITULATION in about one day and official PRICE DEFENCE not at all for weeks. Two independent crisis case studies confirm it. Therefore the corpus can carry the exit leg of the taxonomy but cannot carry the entry leg.**


> SNB floor ANNOUNCED 2011-09-06 (press release, not a speech): zero SNB-official speeches in the corpus 2011-09-01..2011-09-27; the first franc-floor mention by any author is BIS-published 2011-09-29 (+23d) and the SNB's OWN first mention is Danthine 2011-11-03 (+58d). SNB floor ABANDONED 2015-01-15: Jordan, 'The rationale for discontinuing the minimum exchange rate and lowering interest rates', date field 2015-01-15 (+0d), BIS-published r150116a (+1d). BoJ YCC introduced 2016-09-21: Kuroda BIS-published 2016-09-28 (+7d). BoE gilt/LDI intervention 2022-09-28: exactly ONE speech mentioning \bLDI\b or 'liability-driven' exists in the whole 2022-09-23..2022-10-14 window (Pill, delivered 10-12, p


Build implication: Split the detector: CAPITULATION leg may read BIS (T+1 median for the actor's own explanation); DEFENCE/CREATION leg must read the actor's own primary feed same-day. Never score a defence commitment as absent because BIS is silent.


**4. The live official-actor layer exists and is same-day, but every feed is a shallow rolling window, so v1 must persist or it silently loses events. Measured minimum poll intervals.**


> All HTTP 200, keyless, probed 2026-08-28: Fed press_monetary.xml 15 items span 160d (poll <=11d), Fed speeches.xml 15 items span 91d newest 2026-08-28 (poll <=6d), ECB rss/press.html 15 items span 35d newest 2026-08-28 (poll <=2d), BoJ en/rss/whatsnew.xml 47 items span 30d newest 2026-08-28 (poll <=1d), BoE rss/news 50 items span 114d (poll <=2d), SNB public/rss/en/news (301 from public/en/rss/news) 20 items span 30d newest 2026-08-28 (poll <=1d), BIS doclist/cbspeeches.rss RDF/RSS1.0 25 items span 17d (poll <=1d; note it uses <rdf:Seq>/<item rdf:about>, a naive <item> regex returns 0). Decision events are title-identifiable: 'Federal Reserve issues FOMC statement', 'Bank Rate maintained at


Build implication: Daily polling minimum, BoJ/SNB/BIS strictly daily. This directly hits the recon's PERSISTENCE GAP blind spot: the monorepo persists one series today; an append-only event store keyed on (feed, guid, first_seen_utc) is a v1 prerequisite, not a v2 nicety.


**5. BEST FIND OF THIS PASS, unlisted in the recon: the NY Fed markets API is a fully keyless, dated, same-day feed of official-actor PLUMBING operations — exactly the non-price, machine-checkable trigger class the design needs.**


> markets.newyorkfed.org, all HTTP 200 application/json, no key: /api/rp/all/all/results/latest.json returns today's SRF operations with operationDate 2026-08-28, lastUpdated 2026-08-28 13:15:31, per-securityType amtSubmitted/amtAccepted/percentAwardRate (one op showed 175,000,000 Treasury accepted at 3.50%); /api/rp/all/all/announcements/latest.json returns forward announcements (empty today); /api/fxs/all/search.json?startDate=2008-09-01&endDate=2026-08-28 returns 1,600 central-bank USD liquidity swap drawings, 2010-05-18 to 2026-08-26, T+1 (ECB $131mm 7-day at 3.88%, lastUpdated 2026-08-27 16:00); /api/fxs/list/counterparties.json enumerates 11 CB counterparties; /api/rates/secured/sofr/las


Build implication: Make this the primary PLUMBING-DEFENCE detector. A non-zero FX swap drawing by a G10 counterparty and a non-zero SRF takedown are both dated, quantitative, unambiguous, and precede the speech corpus by weeks. Note /api/ambs/... and /api/soma/tsy/get/all/monthly.json return HTTP 400 — path shapes must be probed individually, not assumed.


**6. Treasury supply is a genuine FORWARD calendar, not a nowcast: FiscalData and TreasuryDirect both publish auctions before they happen, with a measured 2-7 day announcement lead, plus same-day results carrying dealer-takedown stress metrics.**


> api.fiscaldata.treasury.gov/.../od/auctions_query: total-count 7,680, oldest auction_date 1979-10-31 (announcemt_date 1979-10-24). Forward rows present today (2026-08-28): auction_date 2026-09-01 / announcemt_date 2026-08-27 (6-Week bill, offering 85,000,000,000) and 52-Week 52,000,000,000; auction_date 2026-08-31 announced 2026-08-27. od/buybacks_operations: 218 operations, oldest 2000-03-09, latest 2026-08-25 with operation_type 'Liquidity Support', total_par_amt_offered 8,402,000,000 vs total_par_amt_accepted 1,191,000,000, plus preliminary/final/results XML filenames. TreasuryDirect TA_WS/securities/announced and /auctioned return the same content as JSON with bidToCoverRatio (2.73, 2.77


Build implication: Auction announcement date is a precomputable trigger with a 2-7 day lead; buyback 'Liquidity Support' operations are a named forced-flow mechanism with a published operation date. Both qualify under P1's closed enum without any positioning percentile.


**7. Federal Register API is the cleanest regulatory/mandate-change feed available: same-day, 1994+, with forward-dated effective_on and comments_close_on, and a pre-publication feed that leads publication by days.**


> federalregister.gov/api/v1/documents.json HTTP 200 JSON: newest publication_date 2026-08-28 (today); oldest 1994-01-03. conditions[agencies][]=securities-and-exchange-commission + conditions[type][]=RULE -> count 1,022 with effective_on populated (e.g. 2026-07-20 pub / 2026-07-26 effective). conditions[term]="capital requirement" -> count 1,026. conditions[publication_date][gte]=2026-08-01 + CFTC -> count 12. /api/v1/public-inspection-documents/current.json -> 124 documents already filed with future publication_date (filed_at 2026-08-27T16:15-04:00, publication_date 2026-08-31). Pagination caps at 10,000/50 pages but exposes search_after_cursor for full enumeration.


Build implication: effective_on is a dated machine-checkable trigger that satisfies P1 directly. Public inspection gives a 1-4 day lead over publication. This is the forced-flow MANDATE class detector; wire it to the same closed enum.


**8. FX intervention disclosure is structurally lagged and cannot be a live detector. The MoF Japan CSV is real and deep but publishes monthly aggregates with daily detail only quarterly; SNB weekly sight deposits could not be located at all — only a monthly series.**


> MoF: https://www.mof.go.jp/english/policy/international_policy/reference/feio/foreign_exchange_intervention_operations.csv HTTP 200 text/csv 43,477 bytes, 550 lines, Shift-JIS (cp932) with Japanese-era year labels and interleaved quarterly subtotal rows; header states 'period: April 1991-'. The landing page states 'Monthly Release Latest: July 30, 2026 - August 26, 2026 (August 28, 2026)' and 'Quarterly Release Latest: April - June 2026 (August 7, 2026)' — i.e. daily amounts carry roughly a one-quarter lag. The earlier feive.htm / feint/ paths in the recon are all 404; feio/ is the live path. SNB: data.snb.ch/api/cube/{id}/data/csv/en works (snbmonagg 252KB, snbbipo 278KB 1996-12..2026-06, b


Build implication: Do not put an FX-intervention detector on the live path. MoF is a backtest/base-rate input only. SNB weekly sight deposits is an open ask (see blockers) — do not substitute the monthly series and call it an intervention proxy.


**9. The synchronizing-event calendar is buildable but is a MIXED source: four components are machine-derivable, three are hard 403 and must be hard-coded with an expiry, and one (BLS) is bot-blocked entirely.**


> SOURCED: FOMC — federalreserve.gov/monetarypolicy/fomccalendars.htm HTTP 200, 57 meetings scrapeable from CSS classes fomc-meeting__month / fomc-meeting__date, covering h4 headings 2021-2027 (forward-dated); parse traps observed: 'Apr/May' + '30-1' spanning months, '22 (notation vote)', and '*' marking press conferences. CFTC COT — cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule HTTP 200, explicit text 'released at 3:30 p.m. Eastern time... usually released on Friday... data from the previous Tuesday... tentative schedule of releases through 2026', with a month/dates table. EIA WPSR — eia.gov/petroleum/supply/weekly/schedule.php HTTP 200 with the standard rule (10:30 a.m. ET Wedn


Build implication: Split the calendar builder into a SOURCED table with freshness gates and a HARDCODED table where every row carries a source_url, an entered_on date and a 180-day expiry that fails the build when stale. Never let a hard-coded date silently outlive its check.


**10. FROZEN CLASSIFICATION RULE, pre-registered before any backtest. The axis is the OBJECT the act commits a number to, crossed with whether the quantity is bounded. Two coders applying these five steps to the same primary document reach the same label without judgement about intent.**


> S0 ADMISSION: actor in {central bank, finance ministry/treasury, official stabilization fund acting on instruction, financial regulator, official multilateral (IMF/BIS/ESM)}; act has a machine-readable date and a retrievable primary URL on a probed live feed. Former officials, staff working papers and academic conference papers are EXCLUDED. S1 OBJECT — exactly one: (P) a numeric level, band, floor, ceiling or target for a price of a MARKET-TRADED instrument (exchange rate, bond yield or price, index level, commodity price); (Q) a quantity/functioning variable (collateral eligibility, haircut, margin, capital/liquidity/reserve requirement, facility access, settlement or clearing arrangement,


Build implication: Freeze this file before any backtest and log any later edit as a registered trial under P13. Every admitted act must ALSO carry a MECHANISM from P1's closed enum {mandate/regulatory constraint, margin or collateral trigger, index or roll rule, dealer balance-sheet date, published mechanical trigger level} or MECHANISM=NONE; MECHANISM=NONE can never reach the sizer.


**11. FIVE WORKED EXAMPLES under the frozen rule, three of them wins for the official actor. The durations are the point: this class is not a fade generator, it is a hazard clock.**


> 1) HKMA Linked Exchange Rate System, 1983-10-17 to today = 15,656 days / 42.86 years. Object P (7.75-7.85 HKD/USD convertibility undertaking), C1 (unbounded at the strong/weak side). -> PRICE-DEFENCE / DEFEND. OFFICIAL ACTOR WINNING, 42.9 years and counting. Corpus support: 'Linked Exchange Rate System' appears in 32 speeches 1996-2024; 'convertibility undertaking' in 5. 2) SNB EURCHF 1.20 floor, announced 2011-09-06, abandoned 2015-01-15 = 1,227 days / 3.36 years (not 3.5). Object P, C1 ('unlimited quantities'). -> PRICE-DEFENCE / DEFEND, then a clean CAPITULATE on 2015-01-15. OFFICIAL ACTOR WON FOR 3.36 YEARS, then broke in one morning. 3) BoJ Yield Curve Control, 2016-09-21 to 2024-03-19


Build implication: This is the arithmetic that kills any EV ranking built on 1992. A short against a live C1 commitment has a median holding period measured in years and an unknown hazard rate. The instrument may emit P(commitment abandoned within N months) as a Brier-scored hazard; it may not emit a position.


**12. WHAT THIS TAXONOMY MAY AND MAY NOT EMIT — written to respect the twelve killed claims, in particular the one that killed this exact detector's ranking.**


> The evidence base states verbatim: "'OFFICIAL PRICE DEFENCE IS THE HIGHEST-EV ESCALATION CLASS' — UNSUPPORTED as a ranking... No hit rate, expected return, average holding period or base rate is sourced anywhere in the track... DO NOT BUILD: an EV ranking that puts this class above everything else, or a sizing rule that gives it the largest allocation. The price-vs-plumbing detector itself is fine as a candidate generator." It also killed 'a passed test is a forward-observable escalation trigger' (Soros: 'it cannot predict in advance whether a test will be successful or not') and 'a failed attack is a BUY signal'.


Build implication: MAY emit: (a) a dated commitment register row {commitment_id, actor, object, level, C-form, mechanism, opened_on, source_url, live}; (b) P(commitment abandoned within 12m | live at t), Brier-scored, base rate printed beside it per P2; (c) the standing P(drawdown >= X% within N months) primitive for instruments referencing the commitment; (d) a size and tail-hedge multiplier, capped below the top …


**13. A pre-registered rhetorical-intensity hypothesis on this corpus FAILS on its first look, and reporting that now is what keeps it out of the build.**


> Counting SNB-official speeches (Jordan, Danthine, Hildebrand, Zurbrugg, Maechler, Schlegel; 297 speeches in corpus) containing 'minimum exchange rate', by quarter: 2011Q4=5, 2012Q1=2, 2012Q2=4, 2012Q3=1, 2012Q4=5, 2013Q2=4, 2013Q3=1, 2013Q4=5, 2014Q1=2, 2014Q2=2, 2014Q4=4, 2015Q1=4, 2015Q2=6. The quarter before the 2015-01-15 break (2014Q4=4) is indistinguishable from 2012Q4=5 and 2013Q4=5, and there is no 2014Q3 observation at all. Rising defence-rhetoric intensity did not precede the break in the one episode where the corpus is dense enough to look.


Build implication: Do not ship a 'defence rhetoric is intensifying' feature. n=1 episode is not a refutation, but it is not support either, and under P13 this look is already a logged trial. If it is revisited it must be against a frozen multi-episode commitment register with the count normalised by total speeches per quarter.


**14. One recon data-layer claim did not reproduce: FRED was unreachable from this session on every path tried.**


> https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF -> curl 92, 'HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR'; retried with --http1.1 -> curl 52, 'Empty reply from server'; https://fred.stlouisfed.org/data/DFF.txt, .../fredgraph.csv?id=SP500 and the bare https://fred.stlouisfed.org/ all returned code 000, size 0. All other hosts probed in this session returned normally through the same proxy, so this is host-specific rather than a blanket egress failure, but it may still be transient or proxy-policy related rather than a FRED outage.


Build implication: The recon recorded 'FRED keyless via fredgraph.csv' as available. Re-probe from the actual runtime host before any component depends on it, and dual-source anything that does. Under P6 this is exactly the failure a max(date) gate would catch — except FRED fails loudly rather than serving stale 200s, which is the better failure mode.


### Blockers raised


- P1 DECISION-GATING — no base rate exists for the taxonomy's own forecast primitive. P(commitment abandoned within 12m | live) cannot be Brier-scored without a frozen historical register of C1 commitments with opened_on/closed_on dates, and no such register exists in the evidence base or on any probed feed. The five worked examples are five episodes, not a base rate. ASK Casey to authorise building the register as a separate pass (my estimate: BIS corpus + primary feeds can populate roughly 30-60 episodes back to 1996) before any conditional probability is published. Under the MISSING KEY INPUTS rule this must not be recorded as UNKNOWN and shipped anyway.


- P1 DECISION-GATING — the price-vs-plumbing detector inherits the recon's dark-crowding blind spot unresolved. The 2022 gilt/LDI unwind had zero public positioning warning and, as measured here, near-zero speech-corpus warning as well: one speech in the 23-day crisis window. Any theme whose exposure sits in LDI/pension leverage, structured products, private credit or TRS must display 'no positioning coverage AND no official-actor coverage', never a benign score. Confirm this is wired as a hard display state, not a default zero.


- P2 SCORE-MOVING — SNB weekly sight deposits, the intended intervention proxy, was not located. Nineteen candidate cube ids on data.snb.ch returned 404 and the portal's search/tree/sitemap endpoints all return the SPA shell; only MONTHLY series (snbmonagg D1=S0 'Sight deposits', snbbipo) are reachable. Either Casey supplies the correct cube id or weekly-frequency SNB intervention proxying is formally scoped out of v1. Do not substitute the monthly series.


- P2 SCORE-MOVING — FRED was unreachable from this session on all four paths tried while every other host succeeded. Re-probe from the real runtime host. If it stays dark, the recon's macro sleeve loses its keyless series source and needs a named replacement before anything depends on it.


- P3 COMPLETENESS — OPEC, CME Group and S&P DJI are hard 403 to this environment even with a browser UA, so futures/options expiries and index rebalance dates must be computed from published contract rules or hard-coded. Confirm Casey accepts an expiring hard-coded table (source_url + entered_on + 180-day expiry that fails the build) rather than paying for a calendar vendor.


### Corrections from independent verification

- **REFUTED** — The visual accompanying the lag finding (scratchpad/bis_lag.html) presents the lag distribution.
  The chart contradicts the finding it illustrates. bis_lag.html is titled 'n=20,571' and its annotation lines read p50=5d, p90=26d, p95=41d, p99=76d. The finding text — and my independent computation — give n=20,728, p90=27, p95=42, p99=84. The chart is a stale earlier run on 157 fewer rows and understates the p99 tail by 8 days. Under the standing visuals-with-every-study rule this is the artifact Casey actually looks at, and it disagrees with the numbers beside it. Regenerate before it ships.

- **REFUTED** — SNB floor 2011-09-06: the first franc-floor mention by any author is BIS-published 2011-09-29 (+23d).
  The first mention is BIS-published 2011-09-16, i.e. +10 days, not +23. Lorenzo Bini Smaghi, 'Policy rules and institutions in times of crisis' (delivered 2011-09-15, published 2011-09-16), states verbatim: 'I would point to the extraordinary decision of the Swiss National Bank to set a minimum exchange rate for the Swiss franc vis-a-vis the euro, making massive euro purchases.' That is an unambiguous, on-point franc-floor mention 13 days earlier than claimed. It is also the ONLY speech …

- **OVERSTATED** — SNB floor 2011-09-06: the SNB's OWN first mention is Danthine 2011-11-03 (+58d).
  Wrong date basis, and it is the exact basis the same pass declares forbidden. +58d is computed from Danthine's DELIVERY date (2011-11-03). His speech was BIS-published 2011-11-09, so on the URL-derived publication basis that finding 2 mandates ('must key off the URL-derived publication date, never the date field') the correct lag is +64d. The finding mixes bases inside one sentence: the +23d figure beside it is publication-based. Same-sentence unit inconsistency.

- **OVERSTATED** — BoE gilt/LDI: exactly ONE speech mentioning \bLDI\b or 'liability-driven' exists in the whole 2022-09-23..2022-10-14 window (Pill, delivered 10-12, published 10-17, +19d).
  Basis-inconsistent and self-contradicting. Pill was published 2022-10-17, which is OUTSIDE the stated 2022-09-23..2022-10-14 window. On the publication basis the pass mandates, the window contains 67 speeches and ZERO matches. On a delivery-date window it contains 84 speeches and exactly one (Pill). So the count is 1 or 0 depending on a basis the finding never states, and the document it names cannot be 'in' the window it defines. The +19d figure is publication-based and correct. The …

- **REFUTED** — An unanchored 'LDI' substring matches 'holdings'/'yielding' and produced 10 false positives before anchoring; word-boundary anchoring matters.
  10 does not reproduce under either matching regime. Case-SENSITIVE unanchored 'LDI' in the delivery window yields 1 hit = 1 anchored hit, i.e. ZERO false positives (uppercase LDI cannot match lowercase 'holdings'). Case-INSENSITIVE unanchored yields 33 false positives, not 10. The lesson generalizes but the number is wrong either way. Far more important and entirely unflagged: Pill's text reads 'liability driven investment (LDI)' — UNHYPHENATED. The pass's own pattern 'liability-driven' …

- **REFUTED** — NY Fed markets API: /api/rp/all/all/results/latest.json returns today's SRF operations with per-securityType amtSubmitted/amtAccepted/percentAwardRate (one op showed 175,000,000 Treasury accepted at 3.50%). Make this the primary PLUMBING-DEFENCE detector; a non-zero SRF takedown is the trigger.
  Directional misidentification that inverts the signal. The 175,000,000 at 3.50% operation is operationId 'RP 082826 26', operationType 'Reverse Repo', operationMethod 'Fixed Rate' — that is the RRP facility, the Fed DRAINING liquidity, the opposite of the SRF providing it. The two actual Repo/Full-Allotment operations today (RP 082826 25 and 27) accepted 0 and 1,000,000 respectively. So the pass's headline example of the plumbing-DEFENCE detector firing is a routine liquidity drain. Second …

- **REFUTED** — NY Fed: /api/ambs/... and /api/soma/tsy/get/all/monthly.json return HTTP 400 — path shapes must be probed individually.
  Half wrong. /api/soma/tsy/get/all/monthly.json does return 400 (confirmed). But /api/ambs/all/results/summary/last/5.json returns HTTP 200 with real data (operationId 'OR 081426 25', operationDate 2026-08-14, totalSubmittedOrigFace 2424000000). Agency MBS operations are available; the pass wrote off a live endpoint on one bad path shape. Confirmed in the same finding: fxs search 1,600 operations, tradeDate range 2010-05-18..2026-08-26, ECB $131mm 7-day at 3.88% lastUpdated 2026-08-27 16:00, 11 …

- **REFUTED** — Treasury FiscalData od/auctions_query: total-count 7,680, oldest auction_date 1979-10-31 (announcemt_date 1979-10-24); od/buybacks_operations 218 operations.
  The auction total-count is 11,097, not 7,680 — a 31% undercount of the primary backtest universe. I could not reproduce 7,680 under any filter (security_type=Bill gives 8,318, Note gives 2,328). Everything else in the finding reproduces exactly: oldest 1979-10-31/1979-10-24; forward rows auction_date 2026-09-01 announced 2026-08-27 for the 6-Week at 85,000,000,000 and 52-Week at 52,000,000,000; 2026-08-31 announced 2026-08-27; buybacks total-count 218 with 2026-08-25 'Liquidity Support' offered …

- **REFUTED** — FRED was unreachable from this session on every path tried (curl 92 / curl 52 / code 000); re-probe before anything depends on it and find a named replacement if it stays dark.
  FRED is fully reachable from this same environment. https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF returns HTTP 200, 423,531 bytes, valid CSV ('observation_date,DFF' / '1954-07-01,1.13'), over both HTTP/2 and --http1.1. The bare host returns 200/58,981 B. /data/DFF.txt returns 301 (a redirect, not the reported code 000) and resolves when followed. Corroborating evidence the pass missed: the shared scratchpad already contains f_DFF.csv at exactly 423,531 bytes from 20:58 the same day — …


### Fatal flags

- NY Fed SRF detector reads the wrong side of the balance sheet. The pass's worked example — 175,000,000 Treasury at 3.50% — is operationType 'Reverse Repo' (RRP), the Fed DRAINING liquidity, not an SRF takedown providing it. Built as specified ('a non-zero SRF takedown is a plumbing-defence trigger'), the detector fires on routine RRP volume every single day and inverts the signal it exists to produce. Compounding it: 'percentAwardRate' exists only on the RRP detail object; genuine Repo details carry only 'percentOfferingRate', so code keying on percentAwardRate silently drops real repo …

- Treasury auction universe undercounted by 31%. Claimed total-count 7,680; actual is 11,097, and no filter I tried reproduces 7,680. Any base rate, announcement-lead statistic or backtest denominator computed on the claimed figure is wrong. This is precisely the truncated-count failure class the recon was told to expect.

- FRED was declared unreachable and it is not. fredgraph.csv?id=DFF returns HTTP 200 with 423,531 bytes of valid data from 1954 over both HTTP/2 and HTTP/1.1, and an earlier agent in this same session already saved that exact byte count to the shared scratchpad. A transient local failure was escalated into a P2 blocker demanding a named replacement source. Acting on it means re-architecting the macro sleeve away from a working feed.

- The date basis is mixed inside the very findings that mandate a single basis. Finding 2 rules that publication date must always be used, then finding 3 reports the SNB's own first mention as '+58d' (delivery basis; publication basis is +64d) and defines a 2022-09-23..2022-10-14 window whose single named member, Pill, was published 2022-10-17 — outside it. On the mandated publication basis that window contains zero matches, not one. Every lag number in the taxonomy must be recomputed on one declared basis before any of it is frozen.

- The lag visual contradicts its own finding. bis_lag.html reports n=20,571, p90=26, p95=41, p99=76; the finding and my independent recomputation give n=20,728, p90=27, p95=42, p99=84. The chart understates the p99 lookahead tail by 8 days, and it is the artifact Casey actually reads under the standing visuals rule. Regenerate it from the same run that produced the numbers, or the honesty box and the picture disagree.


---

## P4 — COT beyond net position: concentration, ICE, and feed continuity

**Independent verification:** DID NOT RUN (usage limit) — single-sourced


### Verdict

Concentration data does NOT arbitrate the sign flip — it is another degree of freedom, exactly as you predicted, and I can now prove it three separate ways. Under all 10 concentration-conditioning states, TFF leveraged money stays negative and TFF asset manager stays positive; the disagreement is never resolved. The best result in the whole 50-config family (t_NW = -3.24) has a block-bootstrap family-wise p of 0.16 against a null whose median max|t| is already 2.58. And the one configuration that looked real (commodity managed money at high top-8 net concentration) REVERSES SIGN on ICE Brent versus NYMEX WTI over the identical weeks with identical methodology. Do not build a concentration-conditioned direction rule. Three things ARE worth taking: (1) crowding predicts SHAPE not mean — skew goes +0.08 → -1.49 and P(12wk MAE ≤ -10%) goes 2.8% → 5.4% across |z| buckets for asset managers, which is exactly the P2 primitive the design already wants; (2) ICE COT is a real, undocumented, keyless 2011-2026 feed with full concentration and trader counts covering Brent and gasoil, which CFTC does not cover at all; (3) the recon's "817-row Socrata $limit truncation" diagnosis is WRONG — it is a CFTC contract rename on 2022-02-08 that hit 36 contracts, 8 of the 16 in this universe — and the real continuity threat is retroactive reclassification, which on 18 July 2008 rewrote 54 weeks of energy history and is undetectable from any CFTC channel today.


### Findings


**1. The recon's diagnosis of the 817-row truncation is wrong. It is not a Socrata $limit=1000 default; it is a CFTC contract-name change effective report date 2022-02-08 that splits any series keyed on market_and_exchange_names into 817 + 238 rows. The scope is also twice what the recon reported: 36 contracts renamed, 8 of the 16 markets in this universe, not 4 of 9.**


> Paginated with explicit $limit/$offset and asserted against a server-side count(*) for all 31 series: every one matched exactly, zero duplicate report dates. Keyed on cftc_contract_market_code, GBP/UST10Y/UST30Y/ES all return 1,055 TFF rows 2006-06-13 to 2026-08-25. Keyed on the name string they split: 'BRITISH POUND STERLING' 817 rows to 2022-02-01 + 'BRITISH POUND' 238 rows from 2022-02-08; identical 817/238 split for '10-YEAR U.S. TREASURY NOTES'->'UST 10Y NOTE', 'U.S. TREASURY BONDS'->'UST BOND', 'E-MINI S&P 500 STOCK INDEX'->'E-MINI S&P 500'. 817 is not 1000. CFTC's own announcement of 11 Feb 2022 lists 36 contract codes; 8 are in this universe (ULSD, UST10Y, GBP, COPPER, WTI, ES, RBOB,


Build implication: Join key is cftc_contract_market_code, never market_and_exchange_names. Merge-blocking gate: assert row count equals a server-side count(*) for the same $where, assert no duplicate report_date, and assert the distinct-name count per code against a frozen expected value so the next rename fires a build failure instead of a silent 4.5-year hole. The ICE file has the opposite problem — its …


**2. THE ARBITRATION FAILS. Conditioning on top-4 or top-8 net concentration does not resolve the trader-definition sign flip in any state. Leveraged funds stay negative and asset managers stay positive in 10 of 10 conditioning states, and the third definition (dealer/intermediary) sides with asset managers, not with leveraged funds.**


> Own computation, net position/OI z-scored on a strictly-past 156-week window, entry the first tradeable close 6 days after the as-of Tuesday, 4-week hold, Newey-West lag-3 t on the equal-weight weekly portfolio. At |z|>=2.0, fade return per 4 weeks: TFF_LEV ALL -0.277% (t_NW -1.52), C4HI -0.133 (-0.43), C4LO -0.215 (-1.09), C8HI -0.126 (-0.43), C8LO -0.386 (-1.66) — negative in all five. TFF_AM ALL +0.391% (t_NW +2.60), C4HI +0.327 (+1.55), C4LO +0.547 (+2.46), C8HI +0.281 (+1.47), C8LO +0.564 (+2.36) — positive in all five. TFF_DEALER at |z|>=2.0 goes +0.051 ALL and +0.348 at C4HI (t_NW +2.49). Same picture at |z|>=1.5. Panel: 54,813 signal-weeks, 2009-06-09 to 2026-07-21 for TFF/DISAGG, 19


Build implication: P3 stands unchanged and is now empirically load-bearing: three pre-registered definitions, disagreement on sign forces NO-TRADE. Do not add concentration as the tie-breaker — it breaks no ties. Freeze the definition set in config before any backtest and count any addition as a registered trial.


**3. The single best result in the entire concentration family does not survive its own multiple-testing correction. Family-wise adjusted p = 0.16 against a null whose median max|t| is already 2.58.**


> 50 configurations evaluated (5 trader definitions x 2 z-gates x 5 conditioning states), all logged. Observed max |t_NW| = 3.241 at DIS_MM, |z|>=1.5, C8HI. Stationary circular block bootstrap, B=4,000, 8-week blocks (covering the 4-week overlap), null imposed by demeaning each config's weekly portfolio series: family-wise p of the max = 0.1595. Null distribution of max|t|: median 2.58, p90 3.46, p95 3.79, p99 4.58. Only 1 of 50 configs has FW-adjusted p < 0.35. Mean pairwise correlation across the 50 weekly series is 0.096 over 990 pairs, so the tests are close to independent and the family penalty is close to full.


Build implication: Wire this bootstrap into the publish path as the deflation step for P13 — it is more honest than Bonferroni here because it measures the actual cross-trial correlation (0.096) rather than assuming it. Practical bar: on a 50-config family in this data a t of 3.8 is the 95th percentile of pure noise, so nothing below ~3.8 ships.


**4. DECISIVE OUT-OF-SAMPLE KILL: the one surviving concentration result reverses sign between two exchanges' COT for the same commodity over the same weeks. NYMEX WTI says fade at high concentration; ICE Brent says the opposite.**


> Identical methodology, identical window 2013-12-31 to 2026-07-21, |z|>=1.5 and top-8 net concentration percentile >= 0.70 on the crowd's side. NYMEX WTI (CFTC disaggregated managed money): fade -2.049% per 4 weeks, t_NW -2.52, n=29, hit 31%. ICE Brent (ICE-published COT, managed money): fade +0.482%, t_NW +0.17, n=59, hit 39%. Low-concentration bucket also flips: WTI +1.823% (t 1.02) vs Brent -1.493% (t -0.83). The full 7-commodity CFTC set over the same window gives C8HI -1.720% (t_NW -2.94) vs C8LO -0.078% (t 0.43), so the CFTC-side result is internally consistent and still does not replicate on the nearest independent instrument.


Build implication: This is the finding to put in the honesty box. Concentration conditioning is not measuring a mechanism; it is measuring a particular exchange's reportable population. Do not build a concentration-conditioned direction rule. If a concentration measure is used at all it goes to SIZE and tail-hedge budget only (P9), never to direction (P1).


**5. Trader counts — the most direct 'how few holders is this' measure — add nothing and disagree with the concentration ratios about which direction is more concentrated.**


> 18 configurations conditioning the fade on the strictly-past 156-week percentile of the trader count on the crowd's side. Max |t_NW| across all 18 = 1.92 (TFF_AM, |z|>=2.0, many traders, +0.406%). No conditioning state flips any definition's sign: TFF_LEV stays negative in both few-trader (-0.483, t -1.83) and many-trader (-0.027, t -0.38) buckets; TFF_AM stays positive in both. Worse, the two concentration families point opposite ways: corr(log contracts-per-trader, conc_net_le_4) = -0.236 (TFF_LEV), -0.210 (TFF_AM), -0.131 (DIS_MM) — i.e. when the top-4 hold more of OI, the average category member holds LESS. Only -log(n_traders) lines up with conc4 (+0.55 to +0.69).


Build implication: Drop trader counts from the direction stack. If you want 'how few holders', -log(n_traders) is the measure that agrees with the published concentration ratio; contracts-per-trader is a different and contradictory quantity and must not be labelled 'concentration'. Also: traders_* can be literally 0 (asset manager and dealer minima are both 0), so any contracts-per-trader field needs a zero guard …


**6. What crowding DOES predict is the shape, not the mean — and this replicates on two of four definitions, monotonically. This is direct empirical support for the P2 primitive already in the design.**


> 12-week forward path of a position held WITH the crowd. TFF asset manager, by |z| bucket: mean 12w +0.441% -> +0.061% -> -1.020%; skew +0.08 -> -0.22 -> -1.49; P(max adverse excursion <= -10%) 2.8% -> 3.4% -> 5.4%; median MAE -2.11% -> -2.18% -> -2.52%. Legacy non-commercial (16 markets, 1995-2026): skew +0.91 -> -1.05 across the 1<=|z|<2 and |z|>=2 buckets, P(MAE<=-10%) 17.8% -> 18.6% -> 20.9%, median MAE -3.54% -> -3.72% -> -4.09%. Honest caveat: TFF leveraged money and commodity managed money show no monotone pattern in either statistic, and one legacy skew reading (+15.86 in the |z|<1 bucket) is a single-outlier artifact.


Build implication: Keep P2 as the ledger primitive and calibrate it on asset-manager and legacy-non-commercial positioning, not on leveraged money. Print the unconditional base rate beside every conditional — for legacy non-commercials that base rate is P(12wk MAE <= -10%) = 17.8% at |z|<1 rising to 20.9% at |z|>=2, which is a 3.1pp move, not a regime change. Do not let a 3pp hazard shift authorise a directional …


**7. ICE publishes a full, keyless, undocumented COT archive covering Brent and gasoil back to 2011, with the same disaggregated schema INCLUDING concentration ratios and trader counts. CFTC does not cover ICE Brent or ICE gasoil at all — the energy sleeve's actual benchmark is invisible to the feed every track used.**


> https://www.ice.com/publicdocs/futures/COTHist{YYYY}.csv returns HTTP 200 for 2011 through 2026 (151KB-456KB each); the ICE report page links only 2023-2026, so 2011-2022 are live but undocumented. 2006-2010 return 404. Brent and Gasoil each have 931 rows, 817 distinct as-of dates, 2011-01-04 to 2026-08-25, 813 Tuesdays and 4 Mondays. Zero blank values in Conc_Net_LE_4/8_TDR_Long/Short_All and Traders_M_Money_Long_All across all 931 rows. Last Brent row: OI 2,705,043, MM long 345,087, 550 total traders, Conc_Net_LE_4 long 9.0 / short 14.9. A CFTC Socrata search for BRENT returns only NYMEX financial look-alikes (06765T BRENT LAST DAY) and crack spreads; GASOIL returns only dead NYMEX swaps,


Build implication: Wire ICE as a fourth ingester for the energy sleeve. Three gotchas that are merge-blocking: (a) CFTC_Contract_Market_Code is EMPTY in every ICE row, so the join key is the name string and a rename silently splits the series with no code fallback; (b) the 2011-2013 files carry both FutOnly and Combined rows under the SAME market name — 114 weeks double-count unless you key on (name, …


**8. HISTORICALLY REALIZED FAILURE 1 — the 2018-19 shutdown. Five weekly releases were missed, max staleness reached 44 days, and full currency was not restored for 76 days. Critically, the as-of report_date series was fully backfilled, so a continuity gate that asserts report-date completeness would have PASSED green through the entire blackout.**


> CFTC: 'During the shutdown of the federal government, the Commitments of Traders report will not be published' (22 Dec 2018). Last normal release 21 Dec 2018 carrying as-of 2018-12-18. Publication resumed Friday 1 Feb 2019 with the 2018-12-24 data, then 'one report on Tuesday and another on Friday of each week until the reports are current'; fully caught up 8 March 2019. Missed Friday releases: 28 Dec, 4 Jan, 11 Jan, 18 Jan, 25 Jan. On 31 Jan 2019 the freshest available COT was 44 days old. In today's data the as-of series shows NO gap whatsoever across that window: 2018-12-18, 12-24, 12-31, 2019-01-08, 01-15, 01-22, 01-29, 02-05 — the only >7d gap is the 8-day 2018-12-31 -> 2019-01-08 holid


Build implication: The continuity gate MUST be keyed on the RELEASE timestamp, not report_date (this is P5 with teeth). Required assertions: (1) Socrata rowsUpdatedAt >= last expected Friday 15:30 ET, else BUILD FAILS; (2) max(report_date) >= today - 10 days, else FAILS; (3) a staleness_days field stamped on every crowding reading and any reading over 14 days old is refused as an input, not silently used. Do NOT …


**9. HISTORICALLY REALIZED FAILURE 2 — the Oct-Nov 2025 shutdown, with the exact catch-up table. Max staleness 56 days, 87 days from first missed release to normal schedule, and the schedule was itself revised mid-catch-up.**


> CFTC: 'The processing and publication of Commitments of Traders data were interrupted from October 1 - November 12 due to a lapse in federal appropriations.' First missed release 3 Oct 2025 (as-of 09/30/2025), actually published 19 Nov 2025 — 47 days late. On 18 Nov 2025 the freshest COT was as-of 09/23/2025, 56 days stale. Normal schedule restored with the 12/23/2025 report on 12/29/2025. The 18 Nov schedule and the 9 Dec revised schedule DISAGREE on the back half: 11/10/2025 data was scheduled for 12/12/2025 then moved to 12/10/2025; 12/16/2025 data moved from 01/06/2026 to 12/23/2025. Again zero gap in today's as-of series; the only artefact is that 2025-11-10 is a MONDAY (Veterans Day sh


Build implication: Two more gate rules. (1) Never assert report_date.weekday()==Tuesday: 22 legitimate non-Tuesdays since 1992 (17 Mondays, 2 Wednesdays, 3 Fridays) would fail it. Assert instead that the as-of date is within 1-3 days before the expected release. (2) During a catch-up the release cadence is 2/week and the published schedule can be revised, so the Friday-16:00-ET Routine must tolerate off-cadence …


**10. HISTORICALLY REALIZED FAILURE 3, AND THE ONE THAT ACTUALLY BREAKS CALIBRATION — on 18 July 2008 the CFTC retroactively rewrote 54 weeks of energy COT history. I detected the seam in the data and CFTC's own announcement confirms the scope.**


> CFTC: 'the Commission has now revised Commitments reports for markets affected by reclassified positions, for reports as of July 3, 2007, to date... the historical Compressed Reports (in text and EXCEL formats) found on our website now reflect the improved data.' Detected independently by testing whether published change_in_X[t] equals stored X[t] - X[t-1]: exactly 4 breaks in 2008, all on 2008-07-15, all energy (WTI, NATGAS, ULSD, RBOB), zero elsewhere in 2008 and zero in gold/silver/copper. Full reconstruction of the originally-published 2008-07-08 WTI row from the change fields: commercial long 819,837 -> 672,082 (-147,755, -18.0%); commercial short 820,140 -> 679,465 (-140,675, -17.2%);


Build implication: CONTINUITY GATE SPEC, part 1 (cheap, run every ingest): for every (series, field) pair with a published change_in_* twin, assert abs((X[t] - X[t-1]) - change_in_X[t]) <= 0.5 for every adjacent pair less than 10 days apart. A residual is a restatement seam and must fail the build. Caveat that makes it honest: this catches only the BOUNDARY week of a revision — a revision that restates both the …


**11. The retroactive revision is undetectable from CFTC's own products. Both independent distribution channels serve the restated value today, so only YOUR stored snapshot can detect a rewrite — which the monorepo currently cannot do, since it persists exactly one series.**


> Diffed today's Socrata snapshot against CFTC's separately-produced static annual archives. deacot2019/annual.txt: 832 matched market-weeks x 5 fields (open interest, non-commercial long/short, conc_net_le_4_long, traders_noncomm_long) = 0 differences. deacot2008/annual.txt: 832 x 3 fields = 0 differences, including the very weeks that were rewritten in July 2008. fut_fin_txt_2019/FinFutYY.txt: 468 matched TFF market-weeks x 10 fields including both concentration ratios and both trader counts = 0 differences; zero rows present in one channel and absent from the other, in either direction. Separately, the archive uses a THIRD column-naming convention (Report_Date_as_YYYY-MM-DD, Conc_Net_LE_4_T


Build implication: CONTINUITY GATE SPEC, part 2 (the one that actually matters): persist every COT row you ever fetch, keyed (resource_id, contract_code, report_date, fetch_date), append-only. On each ingest, diff the incoming rows for all prior report_dates against the stored copy; ANY changed value on a previously-stored row fails the build and quarantines every z-score whose 156-week window touches it. This …


**12. The concentration ratios themselves have been published wrong and silently corrected — in the legacy series only, with the disaggregated and TFF versions of the same week unaffected. This is the exact field this whole exercise was asked to test.**


> CFTC, 25 Sept 2018: 'The concentration ratios published on September 21, 2018 for records dated September 18, 2018 are incorrect for the legacy futures only and legacy options and futures combined series. The concentration ratios for the disaggregated and traders in financial futures reports are accurate.' Corrected reports republished 26 Sept 2018. The published register also records reclassifications on 21 Aug 2009 and 13 Nov 2009 (copper), 8 Jul 2011 (CME Brazilian Real), 19 Jul 2013 (ICE cocoa) and 25 Jul 2018 (index classification), plus a non-government outage: the ION cyber incident delayed publication 2-24 Feb 2023.


Build implication: Scrape and parse the Historical Special Announcements page into a machine-readable event table on every ingest, and fail the build on any NEW announcement containing 'reclassif', 'correct', 'revis', 'suspend' or 'name'. Treat the announcement register as a first-class feed with its own staleness assertion. Also: cross-check legacy against disaggregated/TFF concentration ratios for the same …


**13. Design principle P4's stated constant does not replicate on the full free history, and its sign is a commodity-sleeve rule mis-stated as universal. On financials, commercials are net short less than half the time.**


> Own computation, legacy commercial long vs short, 16 markets, 1986-2026, n=28,757 market-weeks. Overall: commercials net SHORT in 59.4% of weeks, not 71.3%. Split: 7 commodities 76.7% (n=12,468); 9 financials 46.0% (n=16,289). Per market the range is enormous — RBOB 100.0%, SILVER 99.5%, ULSD 83.9%, GOLD 80.3%, WTI 77.6% at one end; UST10Y 24.6%, CHF 34.8%, JPY 36.4%, NATGAS 41.1%, UST30Y 41.9% at the other. Separately, the July 2008 reclassification moved WTI commercial net short for the week of 2008-07-08 from 303 contracts (0.0230% of OI, as originally published) to 7,383 (0.5609% of OI, as served today) — a 24.4x change in exactly the P4 primitive, with open interest unchanged at 1,316,2


Build implication: Rewrite P4 as a per-market rule with the sign estimated from that market's own history, not a global 'commercials are net short' assumption — applied globally it puts the slow insurance leg on the wrong side of the rates and JPY/CHF sleeve, which is more than half the v1 macro universe by market count. And note the 24.4x: P4's own primitive is the field most exposed to reclassification, because a …


**14. A frequency regime break sits inside the legacy series that no track flagged: the COT was SEMI-MONTHLY until 30 Sept 1992, not weekly. Any 156-week z-window reaching before Oct 1992 is silently mixing two sampling frequencies.**


> Own computation on 1,930 legacy WTI report dates. 1986-1991: exactly 24 reports per year, median gap 15 days, as-of dates on the 15th and month-end landing on any weekday (weekday histogram across the full series: 1,769 Tuesdays but also 72 Fridays, 40 Mondays, 26 Wednesdays, 24 Thursdays). 1992 is the transition year at 31 reports; weekly Tuesday reporting begins 1992-10-06 and every year from 1993 onward has 52-53 reports at a 7-day median gap. Also confirmed a benign artefact that looks like a restatement: 20 change_in_* residuals all dated 1997-12-23 are fully explained by an off-cycle report published Friday 1997-12-19 — the change field was computed against the prior Tuesday 12-16, and


Build implication: Hard-floor every legacy-based z-window at 1992-10-06 and assert it, or the pre-1993 semi-monthly era doubles the effective window length and deflates every historical z-score. And before any future restatement alarm fires, check for an off-cycle report between t-1 and t — my own test produced 20 false positives from one, and an agent that had not checked would have published a fabricated 1997 …


### Blockers raised


- DECISION NEEDED on the energy z-score history. CFTC rewrote all energy COT reports for as-of dates 2007-07-03 through 2008-07-08, and both CFTC channels now serve only the restated values — the originals are unrecoverable. Every threshold calibrated on that window is calibrated on data that did not exist at the time. Options: (a) exclude 2007-07-03..2008-07-08 energy from all calibration windows, (b) accept restated history and state it in the honesty box, (c) reconstruct the originals from a third-party 2008-vintage archive. I did not pick one — this is a MISSING KEY INPUT and it lands directly on the uranium/energy node.


- NO KEYLESS PRICE SERIES FOR ICE GASOIL. The ICE COT gives gasoil positioning 2011-2026 with full concentration and trader counts, but Yahoo returns 'No data found' for LGO=F, GAS=F, QS=F and LF=F, so there is nothing free to score it against. NYMEX ULSD (HO=F) is a proxy, not the instrument. Either name an acceptable proxy or drop gasoil from v1 — do not silently substitute HO=F.


- ICE COT COVERS SIX MARKETS, NOT 'UK PRODUCTS' BROADLY: Brent, Gasoil, White Sugar, Cocoa, Robusta Coffee, Wheat. There is no ICE COT for UK gasoline, naphtha, jet or fuel oil. If the energy sleeve's thesis needs refined-product positioning beyond gasoil, that exposure has no positioning coverage at all and must display 'no positioning coverage', never a benign score.


- STILL NO DOLLAR WEIGHT. Everything above is in contracts. Concentration ratios are percent of open interest, trader counts are headcount, and neither converts to capital without contract multipliers and prices I did not apply. Every number in this report is unweighted by dollars.


- THE 2008 RECLASSIFICATION'S CAUSAL ATTRIBUTION IS INFERRED, NOT PROVEN. I measured that ~148k WTI contracts moved commercial -> non-commercial-spreading at 2008-07-08 with all totals unchanged, and CFTC's 18 July 2008 announcement says energy positions were reclassified from commercial to non-commercial over exactly that window. I did not obtain a document tying the specific 147,755-contract figure to that announcement. Treat the mechanism as P2-confirmed-by-timing, not as sourced fact.


---

## P5 — How many resolvable forecasts per year this actually produces

**Independent verification:** ran — 7 correction(s), 5 fatal flag(s)


### Verdict

Episode supply was never the problem — I measured 47.3 distinct (contract x side) episodes per year across the 29-contract v1 universe, 35.3 of them effectively independent after a measured design effect of 1.34, and the rate has been flat at 35-59/yr for 17 straight years. The recon's "~8/year" is the same data at a 6x coarser grain (my calendar-cluster count is 8.2/yr). So the gate CAN be reached: 194 verdicts in 5.5 years of accrual plus a measured 1.84-year resolution lag, first verdict 2034-01; 330 by 2037-11.

Two things break it instead, and both are decisions rather than facts of nature. First, the P3 gate is ambiguous and the two readings differ by 26x: "all three definitions concordant" passes 2.5% of episodes = 1.8/yr = 144 years to n=194 and can never be validated; "reject only when a definition is on the opposite side" passes 87% = 41/yr = 6.3 years. That is a P1 decision-gating question for Casey, not something to resolve by analysis. Second — and this is the real finding — effect size, not sample size, is what is missing. On 705-773 resolved observations, entering the extreme positioning band makes the adverse move LESS likely than a random date at every threshold and horizon: 0.88x at P(dd>=40%/24m), 0.96x at 20%/12m, fade returns mean -0.28% with t=-0.24. This independently reproduces treasury-canary's p=0.84 null on a different dataset. There is no effect of the assumed sign to power a study for.

Grain: one row per (contract, side, episode_start), with cluster_id, the P3 concordance class, and monthly re-affirmation appended to the row rather than creating new rows. Per-leg inflates n by 57% with zero information; monthly re-affirmation rows are the write-only-ledger failure in a new costume (144 rows/yr collapsing to the same ~35 effective).

And yes: 35.3 < 50. Conviction sizing stays fully mechanical, the LLM never touches size, and the escalation ceiling comes from c_max = 2/(1 + ln p / ln(1-d)) — 0.27 of full Kelly at P(30% drawdown) <= 0.10 — because at 1-2 escalations/year it could not be fitted in a lifetime. The one genuinely actionable lever I found: the Greenwood-Shleifer-You >=125% run-up band does carry a 1.31x hazard lift here, but at 5.7 entries/yr on a 42-name watchlist it needs 26.5 years — run the screen on 300-400 names instead and it validates in 4.8. That single change is worth more to the calibration loop than every other design choice combined.


### Findings


**1. Episode supply is 6x larger than the recon assumed. Under the pre-registered definition, the v1 macro universe produces 47.3 distinct (contract x side) episodes per year, 35.3 of them effectively independent — not ~8. The '~8/year' figure is not wrong, it is a 6x coarser grain: it equals my calendar-simultaneous macro-cluster count of 8.2/yr exactly.**


> Pulled the full free CFTC history with a completeness gate (row count == count(1), the $limit=1000 trap): legacy 6dca-aqww 39,219 rows, TFF gpe5-46if 20,592, disaggregated 72hh-3qpy 9,332 = 69,143 rows, 29 contracts, max report_date 2026-08-25. DEFINITION STATED FIRST: x_t = (cat_long - cat_short)/open_interest_all weekly; p_t = point-in-time rank of x_t in the trailing 156-week window; band p>=0.95 (crowded long) / p<=0.05 (crowded short); episode STARTS on entry to the band, ENDS after 8 consecutive weeks outside it (hysteresis), and no new episode of the same (contract, definition, side) may start within 26 weeks of the prior start (the anti-double-count rule). RESULTING GRAIN LADDER, 200


Build implication: The escalation gate is NOT starved by episode supply. Delete '~8 episodes/year' from every planning document; it is the wrong grain. Build the ledger at the per-instrument grain and the 194-verdict target is reachable in 5.5 years of accrual, not 24.


**2. Per-definition counts: 640 / 310 / 308 / 150 / 143 episodes. The rate is remarkably constant at ~0.92-0.99 episodes per contract-year across every trader definition, and stationary across 17 years — episode supply is not regime-dependent.**


> NONCOMM (legacy, 29 contracts, 1992-10 weekly onward): 640 episodes / 649 contract-years = 0.986/contract-yr. LEVMONEY (TFF, 20 financials): 310 / 335 = 0.925. ASSETMGR (TFF, 20 financials): 308 / 335 = 0.919. MGDMONEY (disaggregated, 9 commodities): 150 / 152 = 0.988. OTHERREPT: 143 / 152 = 0.942. Per-contract extremes under NONCOMM: RBOB 1.39/yr, S&P-big 1.27, NQ 1.25 ... EUR 0.70, ED3M 0.76, GBP 0.80. Distinct (contract x side) events by calendar year 2009-2025: 45, 42, 52, 51, 59, 50, 53, 49, 50, 47, 48, 51, 35, 40, 42, 47, 50 — flat, min 35, max 59, no trend. Sensitivity across 36 knob settings (band 1/99 to 20/80, lookback 104/156/260w, hysteresis 4/8/13w, min-sep 13/26/52w): the singl


Build implication: Freeze the definition at 5/95, 156w lookback, 8w hysteresis, 26w min-separation and log the other 35 as evaluated trials under P13. The count is robust to every knob, so no one can later claim the throughput was tuned.


**3. THE P3 GATE, NOT THE EPISODE RATE, DECIDES WHETHER THE SYSTEM CAN EVER BE VALIDATED. Read strictly (all three pre-registered definitions in the same band) it passes 2.5% of episodes = 1.8 events/yr, and 194 verdicts takes 144 years. Read loosely (reject only when a definition sits on the OPPOSITE side) it passes 87.0% = 41 events/yr and 194 verdicts takes 6.3 years. That is a 26x fork sitting on …**


> Scored all 1,551 episode-starts on the three pre-registered trios (financials: NONCOMM/LEVMONEY/ASSETMGR; commodities: NONCOMM/MGDMONEY/OTHERREPT) by what the other two definitions read on the SAME week. Result: 1-of-3 with the others silent 1,005 (64.8%); 2-of-3 concordant 306 (19.7%); OPPOSED 201 (13.0%); 3-of-3 concordant 39 (2.5%). Strict survivors dedupe to 29 distinct (contract, side) events over 16.1 years = 1.80/yr, spread {2010:2, 2011:1, 2012:3, 2013:2, 2014:1, 2015:3, 2016:4, 2017:3, 2018:2, 2020:2, 2021:1, 2022:2, 2024:1, 2025:1, 2026:1} — three calendar years with zero. At 1.80/yr and DEFF 1.34: n=194 in 144.4 years, n=330 in 245.7 years.


Build implication: P1 DECISION-GATING QUESTION FOR CASEY. Recommend the LOOSE reading, wired as a hard NO-TRADE only on the 13.0% OPPOSED cases, with the 2-of-3 and 3-of-3 flags carried as a confirmation FIELD on the row (which R2 can later score as a stratifier) rather than as an entry filter. The strict reading is not a conservative choice, it is a decision never to have evidence.


**4. The 13.0% OPPOSED rate is the identification problem measured live: ~12 times a year, two equally defensible CFTC trader categories on the same contract in the same week put you on opposite sides.**


> 201 of 1,551 episode-starts had another pre-registered definition in the OPPOSITE extreme band on the same report date. At the per-instrument rate that is 0.130 x 47.3/0.87 ≈ 6.1 forced NO-TRADEs per year out of 47.3 candidates, or 12.4/yr counted at the per-leg grain. This is the direct empirical analogue of the recon's fading-leveraged-funds -0.256%/4wk (t=-2.18) versus fading-asset-managers +0.321% (t=+3.17) contradiction, and it recurs roughly monthly.


Build implication: The OPPOSED counter is a first-class dashboard number and a merge-blocking gate test fixture. If a build ever shows an OPPOSED rate near zero, the three definitions have collapsed into one and P3 is not actually running.


**5. THE BINDING CONSTRAINT IS EFFECT SIZE, NOT SAMPLE SUPPLY. On this universe, entering the extreme positioning band makes the adverse move LESS likely than a random date, at every threshold and horizon tested. Every measured lift is below 1.0x, so the 194-verdict question is moot: there is no effect of that sign to detect.**


> Adverse move = price moves against the crowded side within the horizon; episodes without a fully elapsed horizon excluded (no truncation bias). Conditional p1 vs unconditional p0 (21,600 random contract-dates, both sides): P(dd>=10%/6m) 0.314 vs 0.328 (0.96x, n=773); P(dd>=10%/12m) 0.430 vs 0.445 (0.97x, n=754); P(dd>=20%/12m) 0.235 vs 0.245 (0.96x, n=754); P(dd>=20%/24m) 0.339 vs 0.367 (0.92x, n=705); P(dd>=40%/24m) 0.162 vs 0.184 (0.88x, n=705). Fade-the-crowd 12m returns across all 754 distinct episodes: mean -0.28%, sd 31.13%, t = -0.24, p = 0.807. Ex-VIX: mean -0.74%, t = -0.66. This independently reproduces treasury-canary's 'not distinguishable from baseline (p=0.84)' on a completely


Build implication: Do not ship a P(drawdown) module whose conditioning variable is a COT positioning percentile — measured on 705-773 resolved observations it makes the forecast slightly WORSE than the base rate. The ledger primitive should be kept, but the conditioner must be a forced-flow mechanism with a dated trigger (P1/P14), not the percentile.


**6. Effective N is 35.3/yr, not 47.3. Design effect 1.34, computed from measured theme-cluster sizes and a measured within-cluster outcome correlation of 0.277. Crucially, cross-sector correlation is ZERO (-0.061), so the five-sector sleeve does NOT collapse — but a single-sector v1 would.**


> 468 sector-theme clusters (same sector + same side within 8 weeks) hold the 835 per-instrument rows; sizes {1:219, 2:156, 3:71, 4:19, 5:3}. Kish m_eff = sum(m^2)/sum(m) = 1861/835 = 2.229. Binary-outcome correlation between episodes starting within 4 weeks (P(dd>=20%/12m)): same sector +0.277 (n=560 pairs), different sector -0.061 (n=2,410 pairs), pooled -0.001 (n=2,970 pairs). DEFF = 1 + (2.229-1)(0.277) = 1.340, so 47.3/1.340 = 35.3 effective independent rows/yr. Separately the in-band COT indicator correlation across the 29 contracts is rho_bar = 0.035, giving N_eff = 29/(1+28*0.035) = 14.6 effective contracts. Within-sector indicator correlation ranks: metals +0.299, equity +0.075, fx +0


Build implication: Stamp cluster_id on every ledger row so R2 can report both raw and cluster-robust scores, and so the sizer caps exposure at the cluster, not the row. And do NOT launch a rates-only or metals-only v1: metals carry rho 0.299 internally and rates only 9.4 rows/yr, which together would push the effective count under 10/yr.


**7. Years to a scorable verdict at 35.3 effective/yr, including the measured 1.84-year resolution lag: 194 verdicts by 2034-01, 330 (ten concurrent variants, P13 deflation) by 2037-11, 480 (a 5-bin reliability diagram) by 2042-02, 800 (Brier skill at a +15pp true effect) by 2051-03.**


> Reproduced the recon's two anchors exactly before using the machinery: 60% vs 50% at two-sided alpha=0.05, 80% power gives n=193.8 (recon said 194); at alpha=0.05/10 it gives n=329.7 (recon said 330). Accrual at 35.3/yr: 194 -> 5.5y, 330 -> 9.3y, 480 -> 13.6y, 800 -> 22.7y, 1,600 -> 45.3y. Resolution lag measured directly: at P(dd>=40%/24m) 16% of rows resolve early (median 345 days to the event) and 84% must run the full 24 months, so the MEAN calendar days for a row to close is 671 = 1.84 years; at P(dd>=20%/12m) it is 313 days = 0.86 years. Quarterly R2 throughput in steady state: per-leg 18.6 rows/quarter, per-instrument 11.8, per-thesis 6.6, per-macro-episode 2.0, strict-P3 0.5, WASHED_


Build implication: The first R2 with >=30 closed rows lands 2029-02 at the per-instrument grain and 2032-03 at the macro-episode grain. Choose the shorter primitive (20%/12m, 0.86y lag) for the calibration loop and keep 40%/24m as the headline hazard, or R2 has nothing to score until 2029.


**8. The fade return series is so negatively skewed that the t-statistic itself is untrustworthy below ~900-1,200 observations — 25 to 34 years of accrual at the effective rate, before any question of edge is even asked.**


> 754 distinct-episode 12-month returns to the fader: skew -5.93, excess-kurtosis-basis kurtosis 101.60. Ex-VIX (719 obs): skew -6.93, kurtosis 121.00. Cochran / Boos-Hughes-Oliver rule n > 25*skew^2 gives 878 (all) and 1,200 (ex-VIX). At 35.3 effective/yr that is 24.9 and 34.0 years of accrual respectively. By contrast the Lo/Mertens Sharpe SE with variance factor 0.949 needs only n = 83 independent 12m observations to show Sharpe 0.30 differs from zero, and n = 30 for Sharpe 0.50 — 2.4 and 0.9 years. The skew is the squeeze tail: shorting a crowded trade occasionally loses several hundred percent.


Build implication: Never report a t-statistic or a mean on this series; report medians and bootstrap intervals only, exactly as P12 already requires for leveraged paths. If a real Sharpe of 0.30+ existed it would be detectable in 2-3 years — the fact that it is not, at n=754, is itself informative.


**9. A Brier/reliability calibration layer needs 400-1,600 resolved rows depending on the true effect, i.e. 11 to 45 years. The R2 quarterly calibration will have something to LIST from 2028-11 but nothing statistically meaningful to CONCLUDE until the 2040s.**


> Monte-Carlo power (1,500 reps, one-sided 5%, half the rows carrying the signal) to reject BSS<=0 versus climatology: climatology 0.245 vs conditional 0.345 (+10pp) needs n > 1,600; 0.245 vs 0.395 (+15pp) needs n ~ 800; 0.245 vs 0.445 (+20pp) needs n ~ 400; 0.184 vs 0.284 needs n > 1,600. Reliability diagram sample sizes: 5 bins at +/-0.10 per bin (95%) needs 1.96^2*0.25/0.01 = 96/bin = 480 rows; 3 bins at +/-0.15 needs 43/bin = 128 rows.


Build implication: Set R2's stated purpose honestly: for the first 4 years it is a completeness and discipline audit (are rows being closed, are the asks expiring, is the OPPOSED counter non-zero), not a skill measurement. Print 'n=X of 128 needed for a 3-bin reliability curve' on the R2 page so the gap is never mistaken for a result.


**10. The Greenwood-Shleifer-You >=125% two-year run-up band DOES carry a real hazard lift in Casey's own theme universe — 1.31x — but only 5.7 entries/year on a 42-name watchlist, needing 26.5 years. Expanding the watchlist is the single highest-leverage design lever in the whole system: at 400 names it validates in 4.8 years.**


> Computed trailing-24m returns on 42 sector/theme ETFs and single names (XLE...XLU, SMH, XBI, TAN, GDX, ARKK, URA, URNM, NLR, COPX, XME, plus CCJ, NXE, UEC, OKLO, LEU, SMR, TQQQ, NVDA, TSLA, PLTR, MSTR, COIN), Yahoo daily, 828 instrument-years: 113 crossings of +125% with a 100%-level exit hysteresis and 1-year re-arm = 0.137/instrument-yr = 5.7/yr for the watchlist. Bursty: 15 in 2022, 13 in 2020, 12 in 2024, 3 of 22 years with zero. Outcomes on the 94 with a full 24m elapsed: P(dd>=30%/24m) 0.489 vs base 0.375 = 1.31x; P(dd>=40%/24m) 0.319 vs 0.281 = 1.13x; P(dd>=50%/24m) 0.181 vs 0.204 = 0.89x; P(dd>=30%/12m) 0.337 vs 0.270 = 1.25x. But forward RETURN is not negative here: mean +57.4% vs b


Build implication: Put the run-up screen on 300-400 liquid US names and ETFs, not on a hand-picked theme list. That one change is worth more to the calibration loop than every other design choice combined. Honesty caveat: this is 2000-2026 ETFs and single names, n=94, not GSY's 1928-2015 industry portfolios — treat the 1.31x as suggestive, and note the positive forward mean contradicts GSY's -28% excess, so do NOT …


**11. The Composer cohort supplies 12.2 trigger days per year on the core tickers and a median of 7.6 crossings/yr per ticker — enough to be a real observable, but it is a same-session flow event, not a forecast that resolves.**


> Computed 10-day Wilder RSI crossings of the recon's measured threshold piles (79/80 up, 30/31 down) on 18 cohort tickers, Yahoo daily full history. Per-ticker totals/yr: SPY 7.1 (2.1 OB / 5.0 OS), QQQ 8.2, TQQQ 8.8, UVXY 11.8, SQQQ 10.8, SOXL 7.8, TECL 8.2, XLK 8.2, IWM 6.2, TLT 7.5, GLD 6.9, BIL 4.1; median across the 18 = 7.6/yr. Distinct COHORT-WIDE trigger days where SPY, QQQ or TQQQ crosses (1993-04 to 2026-07): 407 days = 12.2/yr. NOTE: the Composer MCP server returned 502 (upstream dial failed) this session, so I could not re-enumerate the 2,659 symphonies; this is the RSI-crossing proxy on the recon's verified dominant condition, not a direct cohort census, and it inherits the recon'


Build implication: Composer crossings belong on the watchlist as a same-day forced-flow trigger (P14: a mechanism that publishes its own trigger level), not in the calibration ledger — a same-session flow event has no 12-24 month outcome to score. If it enters the ledger at all it needs its own short primitive (e.g. next-5-day realized move) with its own base rate.


**12. The two validated states in Casey's own repo can NEVER self-validate further: WASHED_OUT fires 1.09 times a year and POST_BLOWOFF 0.34 times a year, both on a single instrument. Their existing p-values are the most evidence they will ever have in a human lifetime.**


> treasury-canary MARGIN_DEBT.md: WASHED_OUT = 22 episodes over 2006-06 to 2026-07 (20.1 years) = 1.09/yr, 115 weeks, 12m median +15.6% with 95% positive, p=0.011, split-half stable 94/95. POST_BLOWOFF (post_blowoff_study.json): 10 episodes 1998-2026 (~29 years) = 0.34/yr, 32 months, fwd12 mean -3.8% vs baseline +8.4%, permutation p=0.028. At 1.09/yr, n=194 takes 178 years; at 0.34/yr it takes 571 years. Reaching even n=30 for a 3-bin reliability curve segment takes 27.5 and 88 years respectively.


Build implication: Freeze both. Never re-tune them, never add a variant, and never present a forward claim on them beyond what the frozen numbers already say — every additional variant tested on a 22-episode sample burns the only evidence there is. Their role in v1 is as pre-validated regime gates on SIZE, exactly as the repo already uses them.


**13. LEDGER GRAIN RECOMMENDATION: per-instrument-episode (contract x side x episode), with cluster_id and a monthly re-affirmation FIELD rather than monthly re-affirmation ROWS. It is the only grain that reaches n=194 inside a decade while keeping the rows honestly independent.**


> Arithmetic across the four candidates. PER-LEG (definition x contract x side, 74.2/yr): rejected — the three definitions on one contract are near-duplicates by construction, so its effective count cannot exceed the per-instrument count of 47.3; logging it would inflate n by 57% with zero information and would corrupt every Brier denominator. PER-INSTRUMENT (47.3 raw, DEFF 1.34, 35.3 effective): n=194 in 5.5y, n=330 in 9.3y, R2 throughput 11.8 rows/quarter, first 30-row R2 2029-02. PER-THESIS (sector theme cluster, 26.5/yr, DEFF ~1.0 because the cluster IS the unit): n=194 in 7.3y, 6.6 rows/quarter — cleaner rows but 33% slower and it throws away the fact that a 3-contract cluster genuinely c


Build implication: One row per (contract, side, episode_start). Required fields: report_date (release-keyed per P5), the three definition percentiles, the P3 concordance class (3of3 / 2of3 / 1of3 / OPPOSED), cluster_id, the named forced-flow mechanism and its dated trigger (P1), X and N declared at intake, the base rate printed beside the conditional (P2), and a monthly re-affirmation log APPENDED TO THE ROW. R1 …


**14. YES — under ~50 resolvable forecasts a year. 35.3 effective. Therefore conviction sizing stays fully mechanical and the LLM layer never touches size, and the escalation gate must be set from the drawdown budget because it can never be fitted.**


> 35.3 effective resolvable forecasts/yr < 50, and that is the OPTIMISTIC branch (loose P3, per-instrument grain, 20%/12m primitive). The escalation grain is worse by an order of magnitude: at the brief's own 1-2 full escalations/yr, n=194 at the escalation grain takes 97-194 years, so no escalation rule can ever have an empirical basis. Substitute, per P7: c_max = 2/(1 + ln p / ln(1-d)) gives c_max = 0.175 of full Kelly for P(ever draw down 25%) <= 0.05; 0.268 for 30% at <=0.10; 0.482 for 40% at <=0.20; 0.463 for 50% at <=0.10. All are at or below half-Kelly, which is what P7 already defaults to.


Build implication: Write it into the spec as a hard constraint, not a caution: (1) no LLM-emitted confidence, probability or conviction number may enter the sizing function by any route (P8) — there will never be enough resolved forecasts to calibrate one; (2) the escalation ceiling is c_max from the drawdown budget with Casey's chosen (p,d), never a fitted multiple; (3) the LLM layer's only sanctioned outputs are …


### Blockers raised


- P1 DECISION-GATING: which reading of P3? 'All three definitions concordant' = 1.8 events/yr = 144 years to n=194 (never validatable). 'No definition on the opposite side' = 41/yr = 6.3 years. 26x fork on one ambiguous sentence. Recommend LOOSE with the 13.0% OPPOSED cases as a hard NO-TRADE and the concordance class carried as a scorable field — but this is Casey's call, not mine.


- P1 DECISION-GATING: which forecast primitive is the ledger's unit? P(dd>=40% in 24m) has a 16% base rate and a measured 1.84-year mean time-to-close, so the first meaningful R2 is 2029-02. P(dd>=20% in 12m) closes in 0.86y and doubles R2 throughput. Cannot recommend one without knowing whether Casey wants the headline hazard number or the calibration loop to be the primitive.


- P1 DECISION-GATING: is the theme watchlist size a free variable? 42 names -> GSY band validates in 26.5y; 400 names -> 4.8y. I do not know whether Casey wants the screen confined to his existing themes or run broadly. This is the highest-leverage single decision in the build.


- P2 SCORE-MOVING: Composer MCP returned 502 (upstream dial failed) this session, so I could not re-enumerate the 2,659 symphonies. The 12.2 cohort-trigger-days/yr is an RSI-crossing proxy on the recon's verified dominant condition, not a direct census, and it inherits the caveat that only 27.0% of symphonies carry an UNGATED instance. Needs a re-run when the server is up before any Composer number enters a spec.


- P2 SCORE-MOVING: every number above was recomputed from vendor endpoints today. The monorepo persists exactly one series (deribit_btc_oi), so a CFTC revision silently rewrites past percentiles and every count here drifts. The append-only + revision-tripwire pattern in barbell-lab/src/barbell/edge/db.py must be wired to the COT series BEFORE the ledger opens, or the 47.3/yr baseline is unreproducible in a year.


### Corrections from independent verification

- **OVERSTATED** — Per-definition counts: NONCOMM 640, LEVMONEY 310, ASSETMGR 308, MGDMONEY 150, OTHERREPT 143; rate constant at ~0.92-0.99 episodes/contract-yr; sensitivity spans 11.7 to 62.1/yr across 36 knob settings.
  Two of the five counts are wrong because of a data bug. Corrected: NONCOMM 803 episodes over 810.1 contract-years (not 640/649), MGDMONEY 153, OTHERREPT 154 (not 150/143). LEVMONEY 310 and ASSETMGR 308 are correct. The claim's real substance -- rate per contract-year ~0.92-0.99 and stationarity -- is CONFIRMED and is in fact the reason the bug did not change the headline: corrected NONCOMM rate 0.991/contract-yr vs their 0.986. Sensitivity sweep reproduces exactly (min 11.7/yr at …

- **OVERSTATED** — The OPPOSED rate is 13.0%, i.e. ~6.1 forced NO-TRADEs per year out of 47.3 candidates, or 12.4/yr at the per-leg grain -- roughly monthly.
  13.0% is the per-LEG fraction, but the finding's own recommended ledger unit is the per-INSTRUMENT episode, and an instrument-episode is OPPOSED if any constituent leg is. At that grain: 174 of 835 = 20.8% (corrected 184 of 858 = 21.4%) = 9.9-10.5 forced NO-TRADEs/yr, not 6.1. The stated arithmetic '0.130 x 47.3/0.87 ~ 6.1' does not evaluate to 6.1 either (it is 7.07). Knock-on: the loose-P3 pass rate at the ledger grain is ~79%, so ~38 events/yr, not 41, and the loose-branch time-to-194 is …

- **REFUTED** — Entering the extreme positioning band makes the adverse move LESS likely than a random date at every threshold and horizon (0.88x to 0.96x lift), so there is no effect of that sign to detect.
  The sub-1.0 lift is an artifact of a period-mismatched control. Their conditional sample is 2009-2026, but the 21,600 'random contract-dates' were drawn from each ticker's FULL price history (MID400 from 1981, VIX from 1990, most from 2000) minus only the last 600 trading days -- so the baseline contains 2000-02 and 2008 while the conditional sample does not. I reproduced their p1 exactly (0.314/0.430/0.235/0.339/0.162, n=773/754/754/705/705). With a ticker-AND-side-matched 2009+ baseline the …

- **REFUTED** — Separately, the in-band COT indicator correlation across the 29 contracts is rho_bar = 0.035 giving N_eff = 14.6 effective contracts; within-sector ranks metals +0.299, equity +0.075, fx +0.070, energy +0.028, rates -0.085.
  On corrected data rho_bar = 0.027 and N_eff = 16.4, not 0.035 / 14.6. The within-sector ranks change materially: metals +0.159 (not +0.299), fx +0.083, equity +0.046, rates +0.030 (sign flips from -0.085), energy +0.012. Undisclosed window problem: this statistic is computed on the intersection of report dates across all 29 contracts, which SPBIG's September-2021 delisting truncates to 599 weeks ending 2021-09-14 -- the last five years of data never enter it. The build implication 'do NOT …

- **REFUTED** — The fade return series has skew -5.93 and kurtosis 101.60, so the t-statistic is untrustworthy below ~900-1,200 observations (25-34 years of accrual); by contrast a Sharpe of 0.30 needs only n=83.
  The entire moment claim rests on ONE observation: WTI long, entry 2020-04-21, where Yahoo's unadjusted continuous CL=F printed $10.01 during the negative-oil expiry week, producing a -513% 12-month fade return that no holder of a rolled position experienced. Reproduced their numbers (n=754, mean -0.28%, t=-0.24, skew -5.94, kurtosis 101.3). Drop that single row: n=753, skew -0.10, excess kurtosis 7.1, and the Cochran bound 25*skew^2 falls from 882 to 0. The corrected episode set, which happens …

- **REFUTED** — The Greenwood-Shleifer-You >=125% two-year run-up band carries a real 1.31x hazard lift (P(dd>=30%/24m) 0.489 vs 0.375, n=94); expanding the watchlist from 42 to 300-400 names is the single highest-leverage design lever, validating in 4.8 years.
  Same control-construction defect as the COT outcome test, and here it is decisive. The baseline gave all 67 tickers equal weight over their full histories, while the run-up screen fires disproportionately on the highest-volatility names (OKLO, TQQQ, NXE, UEC, ARKK, MSTR). I reproduced their conditional side exactly (0.489 n=94, 0.319, 0.181, 0.337 n=101, mean fwd +57.4%, median +11.6%). With a per-ticker matched baseline the lift collapses: 30%/24m 0.489 vs 0.448 = 1.09x (z=+0.80); 40%/24m …

- **OVERSTATED** — The Composer cohort supplies 12.2 trigger days/yr on the core tickers and a median of 7.6 RSI crossings/yr per ticker; the 2,659-symphony census could not be re-run because the MCP server returned 502.
  The 502 is real and reproduces for me (same server, same error), so the cohort census is genuinely UNVERIFIABLE this session -- the finding is honest to flag this. The RSI proxy itself is consistently ~8% high. My independent 10-day Wilder RSI on the same tickers: SPY 6.43/yr (1.85 OB / 4.59 OS) vs their 7.1 (2.1/5.0); QQQ 7.57 vs 8.2; TQQQ 8.22 vs 8.8; UVXY 11.07 vs 11.8; SQQQ 10.34 vs 10.8; SOXL 6.98 vs 7.8; TECL 7.64 vs 8.2; XLK 7.37 vs 8.2; IWM 5.67 vs 6.2; TLT 6.94 vs 7.5; GLD 6.80 vs 6.9; …


### Fatal flags

- CONTRACT-IDENTITY BUG, would produce wrong numbers in production. The legacy COT pull keys on `market_and_exchange_names`, which CFTC RENAMED on 2022-02-08 (e.g. 'E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE' -> 'E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE'). 17 of 29 NONCOMM series therefore just stop: heating oil at 2013-11-05, 15 contracts at 2022-02-01, S&P-big at 2021-09-14 (that one a genuine delisting). 10,221 of 49,440 rows are missing -- 20.7% -- and they are the most recent 4.5 years of more than half the universe. The agent's completeness gate (declared count(1) == …

- PERIOD-MISMATCHED CONTROL invalidates the headline effect-size finding. The conditional episodes span 2009-2026 but the 21,600 'random contract-dates' were drawn from each ticker's entire price history (back to 1981 for MID400, 1990 for VIX, 2000 for most) minus only the trailing 600 trading days, so the baseline absorbs the dot-com bust and the GFC while the treatment sample does not. That single mismatch manufactures the whole result. Rebuilt with a ticker-and-side-matched 2009+ control, the lifts move from 0.88-0.96x to 0.97-1.01x with |z| <= 0.62 at every threshold. 'Entering the band …

- SINGLE-OBSERVATION ARTIFACT drives the entire distributional claim. skew -5.94, kurtosis 101.3 and the resulting 'n > 878-1,200 before a t-stat is trustworthy, i.e. 25-34 years of accrual' all trace to ONE row: WTI long, entry 2020-04-21, where the unadjusted continuous Yahoo CL=F series printed $10.01 during the negative-oil expiry week, giving a -513% twelve-month fade return that no holder of a rolled position ever experienced. Remove that row and skew is -0.10, excess kurtosis 7.1, and 25*skew^2 falls from 882 to 0. Any accrual schedule or reporting rule ('never report a mean or …

- GSY WATCHLIST LEVER DOES NOT EXIST at the size claimed, and it is the finding's own nominated top design decision. The 1.31x hazard lift is a ticker-mix artifact of the same equal-weight-full-history baseline: the >=125% run-up screen selects the highest-volatility names in the panel (OKLO, TQQQ, NXE, UEC, ARKK, MSTR), whose unconditional drawdown probability is far above the panel average. Per-ticker matched, 30%/24m is 0.489 vs 0.448 = 1.09x (z=+0.80), 40%/24m 0.98x, 50%/24m 0.83x, 30%/12m 1.01x -- no threshold survives. Required n rises from 144 to 1,158, so a 400-name watchlist takes 22.6 …

- PRICE PANEL IS NOT FIT FOR THE OUTCOME LAYER, contaminating claims 5, 6 and 7 independently of the control-construction bugs. SPBIG and ES are mapped to the identical Yahoo ES=F series, so 49 ledger rows are a duplicated instrument whose outcomes are perfectly correlated by construction and which feed straight into the within-cluster rho that sets DEFF. VIX positioning is measured on VIX FUTURES but its outcome is measured on ^VIX SPOT (37 rows) -- structurally different drawdown behavior. ED3M and FEDFUNDS have no price series at all, so their 42 rows are silently dropped from every outcome …


---

## P6 — Netting against Casey's live book, and the are-we-the-crowd check

**Independent verification:** DID NOT RUN (usage limit) — single-sourced


### Verdict

YES — Casey IS the crowd, and it is now measured, not asserted. All 4 live symphonies fire in the cohort's pile bands; 18 of his 24 distinct 10-day-RSI triggers (75%) sit inside 78-82 or 29-32, including the corpus's #1 and #2 modal tuples verbatim (RSI(TQQQ,10)>79, RSI(TQQQ,10)<30). On the cohort's modal OVERSOLD day his book's median SPY beta-notional is +201% of book; on the modal OVERBOUGHT day it is -190%. So the one validated signal in the whole evidence base — WASHED_OUT / post-flush long re-entry — is precisely the signal his existing book already expresses at 2x book notional, in the same session, at the same level. The swarm's best idea is its most duplicated idea. Second structural result: the book is UNCONDITIONALLY diversified (max pairwise symphony rho 0.28, 3.76 effective bets of 4) yet CONDITIONALLY concentrated (+201% on trigger days). Any risk model reading the unconditional correlation matrix concludes "diversified" and sizes a new thesis several times too large. NETTING SPEC (v1, no capital moves): (1) Every thesis declares a tradeable return proxy R — a ticker or signed basket. No proxy, no size, no exception. (2) Regress R's daily log returns on six factor proxies (SMH, SPY, TLT, XBI, VIXY, GLD) over 1y AND 3y; if any loading flips sign between windows, mark UNSTABLE and halve the cap. (3) Compute book exposure B_f CONDITIONALLY, never from today's snapshot: replay each symphony's tdvm_weights history at today's dollar values, then take the median B_f over the subset of days where the thesis's OWN entry trigger was true. Today's snapshot reads -6% SPY beta and sits at the 30th percentile of its own history — using it would understate the real exposure by ~144 percentage points of book. (4) Reject when sign(size x beta(R,f)) == sign(B_f_conditional) and |B_f_conditional| > 0.5 x book on the thesis's dominant factor. (5) Otherwise shrink: multiplier = 1 - |corr(R, book return proxy)|, applied ON TOP of the P7 Kelly ceiling, and divide the Kelly fraction by N_eff (HHI of the correlation-matrix eigenvalues over book+thesis), which is 4.17 of 54 instruments at 1y — not 1. (6) Cluster gate: if R's dominant loading lands in the 31-name mega-cluster (mean pairwise rho 0.58, contains every leveraged-Nasdaq name, the whole uranium sleeve AND gold), it is a DUPLICATE — cap at the increment that brings the cluster to budget. NIGHTLY "ARE WE THE CROWD" JOB: 03:00 ET pull /accounts/list, symphony-stats-meta, /symphonies/{sid}/score for each of Casey's; run the tree extractor (121 conditions, 84 RSI today); enumerate the 2,659 public cohort (~35 min at 25/min search + 250/min score); compute Wilder RSI at every (ticker, window) in EITHER set from free Yahoo closes; print beside every recommendation: distance-to-flip on each of Casey's own triggers, the cohort's count at that same level, and the conditional book beta if it fires. MERGE-BLOCKING GATES: assert max(date) >= today-4 on every price feed (P6), and re-verify the Wilder replication nightly against three canary trees via POST /backtest — today 29/29, 32/33, 189/189. If replication drops below 95%, DISABLE the distance-to-flip readout rather than degrade it. Persist append-only: the monorepo currently persists exactly one series, so every threshold silently drifts. And build the closing loop in the same commit as the writing loop — venture-deal-analyzer/ledger.csv is 6 rows and 0 resolved outcomes because the R1/R2 Routines were never created.


### Findings


**1. Composer evaluates RSI as WILDER smoothing on the SAME session's close with ZERO lag, so every cohort trigger level is exactly precomputable from free Yahoo daily closes. The competing Cutler/SMA convention is refuted and would have been catastrophic — it differs by 11-19 RSI points on live readings.**


> Three read-only ad-hoc POST /backtest probes (2023-01-01..2026-08-27), holdings recovered from the tdvm_weights field. RSI(SPY,10)<30: Composer fired 29 days, Wilder fired 29, exact same-day overlap 29/29, 0 false pos, 0 false neg; lag=1 overlap collapses to 11/29. RSI(TQQQ,10)>79: Composer 33, Wilder 32, overlap 32, fp=0, fn=1. RSI(SPY,2)<25: Composer 189, Wilder 193, overlap 189, fp=4, fn=0. Total 250/251 = 99.6%; residual is price-basis (dividend-adjusted close), not convention. Cutler on the same window fired 74 days vs Composer's 29. Live spread today Wilder vs Cutler: SOXL 38.5 vs 27.1, TQQQ 50.4 vs 33.4, QQQE 52.1 vs 33.1 — under Cutler SOXL would read as ALREADY firing the cohort's o


Build implication: This is the load-bearing primitive for the entire instrument — without it the distance-to-flip readout is noise. Freeze Wilder + zero lag, and re-verify nightly against these three canary trees as a merge-blocking gate; disable the readout, never degrade it, if replication falls below 95%.


**2. ARE WE THE CROWD: yes, mechanically. All 4 live symphonies fire inside the cohort's pile bands, and 18 of 24 distinct 10-day-RSI triggers (75%) sit in 78-82 or 29-32 — including the corpus's two modal tuples verbatim.**


> Tree extraction over all 4 GET /symphonies/{sid}/score: 121 conditions, 84 RSI, 24 distinct 10-day-RSI (ticker,cmp,threshold) tuples. 13 in the 78-82 overbought pile, 5 in the 29-32 oversold pile, 4 of 4 symphonies represented. Exact matches to the cohort census: RSI(TQQQ,10)>79 (cohort's #1 tuple, x1049) in YPTSJFJw; RSI(TQQQ,10)>80 (x948) in mbkiXcuN; RSI(TQQQ,10)<30 (x988) in both YPTSJFJw and mbkiXcuN; RSI(SOXL,10)<30 in both; RSI(SPXL,10)<30; RSI(QQQE,10)>79; RSI(TECL,10)>79; RSI(VOOG/VOOV/VOX/VTV,10)>79; RSI(XLY,10)>80. Rebalance cadence: 3 of 4 daily, 1 threshold-corridor — matching the cohort's 94% daily-or-corridor, so flow lands in the same session.


Build implication: No recommendation on a leveraged-Nasdaq/semis name may ship without its overlap badge printed beside it. Casey's own triggers must be in the same nightly extractor run as the public cohort's — same code path, same output table.


**3. The collision is not merely directional overlap, it is amplification: on the cohort's modal oversold trigger day Casey's book runs a MEDIAN +201% of book SPY beta-notional, and on the modal overbought day -190%. The one validated signal in the evidence base (WASHED_OUT post-flush long) is therefore the single most duplicated idea the swarm could emit.**


> 843 co-live days (2023-04-19..2026-08-27), each symphony's tdvm_weights replayed at today's dollar values with 1y regression betas. RSI(TQQQ,10)<31 fired 37 days (4.4%): median book SPY beta +$653,576 = +201% of the $325,764 book, vs +$421,545 = +129% on non-trigger days. P(book SPY beta > +100% of book | trigger fired) = 86% vs 53% otherwise. RSI(TQQQ,10)<30 (n=32): +203%. RSI(SPY,10)<30 (n=28): +202%. RSI(SOXL,10)<30 (n=25): +191% SPY / +75% AI-capex. Mirror side — RSI(TQQQ,10)>79 (n=32): median -190% SPY; RSI(SPY,10)>80 (n=9): -240%.


Build implication: Invert the intuition the gap statement encodes. The danger is NOT that a fade recommendation gets traded against — on an overbought reading his book is already -190% short, so a fade DOUBLES it. The danger is that the WASHED_OUT long, the only signal with a p-value, arrives when he is already +201% long. Netting must be evaluated conditional on the thesis's own trigger state, and the WASHED_OUT …


**4. The book is unconditionally diversified but conditionally concentrated — the two readings differ by ~200 points of book beta, and any risk model using the unconditional correlation matrix will size a new thesis several times too large.**


> Pairwise correlation of the 4 live symphonies' daily backtest returns over 2023-04-19..2026-08-27: max 0.28 (mbkiXcuN/YPTSJFJw), others 0.13, 0.11, 0.07, 0.05, -0.11. PC1 explains 34% of variance; effective independent bets (HHI) = 3.76 of 4 — textbook diversified. Yet the same four, replayed jointly, produce a median +138% of book SPY beta and a p5-p95 range of -100% to +232% (p1 -$782,003, p99 +$819,535, max +$931,418 = +286% of book). Today's snapshot is -6%, the 30th percentile of its own history (AI-capex 26th, biotech 22nd, duration 27th).


Build implication: Forbid the unconditional correlation matrix as a sizing input. The netting layer must consume the conditional distribution built by replaying tdvm_weights, and the 'current holdings' snapshot must be labelled with its own historical percentile so a benign reading can never be mistaken for a benign book.


**5. Live book inventory, fully reconciled: $325,488 across two real brokerage venues, 57.0% in cash equivalents, exactly 6 Composer tickers plus 2 IBKR positions. No uranium, no genomics, no BTC-sleeve equity anywhere in it.**


> GET /accounts/list: one ACTIVE account b4ee3fe9-fc12-4991-8df4-de29c857099c (ALPACA_WHITE_LABEL, INDIVIDUAL, EQUITIES), first deploy 2025-12-05. Composer $276,083.46 in 4 symphonies: YPTSJFJwD2ZKfAeYJUbW $92,574 (TLT 74.9% / PULS 25.0%), mbkiXcuNDjueXpiox5Av $74,579 (BIL 99.9%), nNdBk7hc5NiBzeRvbI5T $71,877 (BOXX 49.9% / LABD 25.1% / TMV 24.9%), ORQNCfZnA18wmsMWVhf8 $37,053 (PULS 99.9%). GET /accounts/{id}/holdings confirms exactly 6 tickers: BIL, BOXX, LABD, PULS, TLT, TMV. IBKR blend3070 live since 2026-08-28, venue-confirmed fills 09:58:30-31 ET: 45 SPY @ 772.00 = $34,740.00 and 163 BIL @ 91.66 = $14,940.58, $49,680.58 deployed, 83% utilization, sleeve flat. btc-executor is a Hyperliquid


Build implication: This is the netting baseline. Pull it live every night rather than caching — 3 of 4 symphonies rebalance daily, so a day-old snapshot is a different book.


**6. Uranium — the dashboard's own 13 names — is NOT held anywhere visible, and is NOT a diversifier: it is a levered blend of the two named factors, and it is the bridge that welds them into a single cluster.**


> No uranium ticker appears in either live account (Composer holdings = 6 tickers, IBKR = SPY+BIL), and no cost-basis or position file exists in the monorepo (searched *.json/*.csv/*.yaml for shares/cost-basis/entry-price/allocation: only btc-paper-engine reference trades, a Composer template, and venture-deal-analyzer/ledger.csv). 1y daily-log correlations: URA +0.61 to SMH and +0.54 to GLD (5y: +0.53 / +0.37 — both rising); CCJ +0.51/+0.46, NXE +0.47/+0.50, DNN +0.47/+0.53, UEC +0.45/+0.51. OKLO and SMR are pure AI-capex, not gold: 1y SMH +0.54/+0.52 vs GLD +0.35/+0.33, and their SMH correlation nearly doubled from 5y (+0.28/+0.33). Average-linkage clustering at rho~0.45 on 54 instruments pu


Build implication: Delete 'uranium as an uncorrelated thesis' from the design. A uranium recommendation is a leveraged AI-capex recommendation with a gold kicker, and must net against both. Because the uranium names are the bridge, adding uranium exposure REDUCES the book's effective bet count rather than raising it.


**7. The evidence base's named 'dollar debasement (gold, BTC, short USD)' factor does not exist in the data. BTC is a singleton that loads on equity beta, not on gold.**


> 1y / 5y daily-log correlations: GLD-BTC +0.24 / +0.14; BTC-UUP -0.15 / -0.17 (nearly no dollar loading); BTC-SPY +0.45 / +0.42; BTC-QQQ +0.41 / +0.42. GLD-UUP is -0.39 / -0.40, so gold alone carries the dollar leg. In the 1y clustering BTC-USD falls out as a SINGLETON alongside UUP and XLU, while GLD/PHYS/GDE are absorbed into the 31-name equity mega-cluster. Effective independent bets across all 54 instruments: 4.17 (HHI) / 9.27 (entropy) at 1y, 4.06 / 9.34 at 5y; PC1 alone explains 46.3% of variance.


Build implication: Re-specify the factor set from measurement rather than from the recon's narrative: the defensible proxies are SMH (AI capex), SPY (broad equity), TLT (duration), XBI (biotech), VIXY (vol) and GLD (real assets/dollar), with BTC carried as its own factor. Grouping BTC with gold would have let a BTC thesis and a gold thesis net against each other when they are 0.24 correlated.


**8. A live, unmanaged self-collision already exists inside the Composer book: $121k of gross duration exposure in two different symphonies that nets to $8.5k, with both legs paying spread and daily rebalance costs.**


> YPTSJFJw holds TLT $69,372 (beta to TLT +1.00); nNdBk7hc holds TMV $17,920 (beta to TLT -2.86, i.e. -$51,319). Net duration beta-notional across the whole live book = -$8,475 = -2.6% of book, from $120,691 of gross. Neither symphony can see the other — Composer sizes and rebalances each independently, and both rebalance daily/threshold.


Build implication: The netting layer has to run across symphonies, not within them, and its first output should be a standing gross-vs-net report on the EXISTING book. This pair is the worked example that justifies the whole build before a single new thesis is sized.


**9. Second live self-collision, and this one crosses services: the Composer sleeve is short $54,756 of XBI beta via LABD while the genomics-alpha-tracker R2-A long call book went live through ibkr-executor today. The genomics sleeve's entire risk budget sits inside the noise of a position taken by a different service with no knowledge of it.**


> nNdBk7hc holds LABD $18,018 with a 1y beta of -3.04 to XBI = -$54,756 XBI beta-notional. corr(LABU, XBI) = +1.00 and corr(LABD, XBI) = -1.00 at 1y, so the Composer leg and the tracker universe are literally the same factor. genomics-alpha-tracker HYPOTHESES.md H11/H13 define R2-A as a LONG call book gated by the XBI 200dma prior close, routed into ibkr-executor blend.py blend3070 at 1% sleeve risk per call on a $15,000 BIL-parked sleeve — order ~$150 risk per call versus a $54,756 short. Ratio ~20-35x.


Build implication: Netting must span services, not just Composer. The nightly job needs the IBKR sleeve state as an input; today it is inferable only from a README commit, which is not a data source.


**10. LABD is 5.5% of capital and drives essentially 100% of the book's net factor exposure on every single factor — a size-vs-risk mismatch that any position-weight-based risk view would miss entirely.**


> 1y regression betas for LABD: SPY -3.11, QQQ -1.80, SMH -0.80, XBI -3.04, TLT -2.27, GLD -0.92, BTC -0.68. At $18,018 it contributes -$56,034 SPY, -$32,441 QQQ, -$54,756 XBI, -$40,853 TLT, -$16,640 GLD — the largest single contributor on all six factors, ahead of the $34,740 SPY position and the $69,372 TLT position. Resulting net book exposures: SP500 -$19,116 (-5.9%), AI-capex -$5,370 (-1.6%), biotech -$45,644 (-14.0%), duration -$8,475 (-2.6%), gold -$11,261 (-3.5%).


Build implication: Size every exposure in beta-notional, never in market value or portfolio weight. A 5.5% weight carrying 3x inverse leverage against a high-beta sector is not a 5.5% position.


**11. Casey's can-hold universe is 30 tickers by asset node and 48 including signal-only names; overlap with the cohort's published top-20 is 12 holdable / 15 in any role — 69% when weighted by cohort reach. The recon's '19 of the top-25' does not reproduce at the top-20 level and should be restated.**


> Asset-node extraction across all 4 trees: 30 distinct holdable tickers (BIL BOXX KIE LABD LABU PULS QLD SMH SOXL SOXS SPXL SQQQ SSO SVIX SVXY TECL TLT TMF TMV TNA TQQQ UDOW UGL UPRO USD UVXY VIXM VIXY VXZ ZVOL). The symphony-stats-meta tickers field lists 48, the extra 18 being signal-only (CORP FAS HYG IEF KMLM LQD PEJ PSQ QQQE SHY SPY VOOG VOOV VOX VTV XLK XLP XLY) — the asset-node set is a strict subset, no discrepancy in the other direction. Against the recon's published top-20: 12 holdable (TQQQ TECL BIL UVXY SOXL TMF SQQQ UPRO TLT TMV SPXL VIXY), 15 in any role (adds SHY PSQ SPY). Reach-weighted: 450.2 of 649.0 percentage points = 69%.


Build implication: Publish the overlap as two separate numbers — holdable and signal-only — because only the holdable set can produce flow, while the signal-only set determines when the flow fires. Correct the recon's figure in the design doc rather than carrying it forward.


**12. The full trigger inventory is 121 conditions, the non-RSI half is different in kind (1-day gap gates on credit and rates), and Casey's own book contains the same fake-precision parameter-sweep trap the recon flagged in the public corpus.**


> Deduped: 84 RSI conditions (67 distinct tuples) plus 21 distinct non-RSI. Non-RSI is dominated by nNdBk7hc's 1-day cumulative-return gates: LQD <-4% / >+1.5%, KIE >+3.45% / <-6%, TMF <-7.5% / >+10.5%, TLT <-3.5% / >+6%, HYG <-1.75% / >+1.75%, SHY >+0.5% / >+0.6% / <-0.33%; plus 4 filter/sort nodes and 2 price/MA gates on TQQQ. THE TRAP: ORQNCfZn and YPTSJFJw each carry an identical RSI(SPY,w) ladder for w=2..10, all at >80 and all at <25 — 36 raw conditions collapsing to 18 tuples and, at the symphony level, to 2 decisions. Live readings prove the ladder is one bet: SPY RSI at w=2..10 today reads 59.5, 60.5, 58.0, 56.5, 55.9, 55.8, 55.9, 56.0, 56.2 — a 4.7-point spread across nine 'independe


Build implication: The nightly extractor must handle four node kinds (if-child, filter, price/MA, and relative-RSI where the RHS is a ticker not a number), and every published overlap statistic must be symphony-deduped with its denominator stamped — the same rule the recon imposed on the public corpus now applies to Casey's book. The HYG/LQD credit gates are the only place in his whole book where a forced-flow …


**13. The reachable-exposure envelope is bounded and computable from realized weights rather than tree worst-cases, which cuts the headline swing roughly in half and makes it defensible.**


> POST /symphonies/{sid}/backtest over 2021-08-28..2026-08-27 gives empirical max weights, not tree bounds: mbkiXcuN reaches 1.000 on each of TQQQ/UDOW/SSO/TNA/QLD/TECL/LABU/UPRO/SMH/UVXY and is in a 3x name 54.0% of days; YPTSJFJw caps at SOXL 0.750, TECL 0.757, SQQQ 0.765, UVXY 0.792; nNdBk7hc caps at 0.500 for SOXL/TQQQ/SPXL/TMF/UVXY and 0.250 for LABD/TMV; ORQNCfZn is vol-only (PULS/VXZ/ZVOL). Summing per-symphony extremes gives a 691% SPY-beta swing (-$1,009,005 to +$1,243,424), but the empirical joint distribution over 843 co-live days narrows this to a p5-p95 of -100% to +232% of book, max +286%.


Build implication: Use the empirical joint distribution, not summed maxima, as the netting denominator — the summed-maxima bound is ~2x too wide because the symphonies are rarely all risk-on at once. Caveat this: it applies today's dollar values and 1y betas to 2023-2026 weight states, and the 843-day window is truncated at ZVOL's 2023-04-19 inception.


**14. Every price input the design needs is live and keyless today, but the persistence gap makes any calibrated threshold unreproducible tomorrow.**


> 64 of 64 Yahoo chart symbols returned HTTP 200 with daily granularity through 2026-08-28, zero failures, including the uranium names (URA, CCJ, NXE, UEC, UUUU, DNN, LEU, OKLO, SMR, LTBR), all 30 Composer holdables, the genomics proxies (XBI 5,173 bars, ARKG, CRSP, TEM), the barbell shadow instruments (GDE, KMLM, AVUV, AVDV, PHYS, AVEM, QUAL, TAIL, XLU) and continuous futures CL=F 6,612 bars / GC=F 6,607 bars. Longest ^GSPC 14,286 bars from 1970-01-02; shortest TEM 553 bars from 2024-06-14. Against this, the monorepo persists exactly one series (deribit_btc_oi); venture-deal-analyzer/ledger.csv holds 6 rows and 0 resolved outcomes, the R1/R2 Routines never having been created.


Build implication: Free-first is satisfied — no paid feed is needed for any of this. But write the append-only persistence layer and the R1/R2 closing Routines in the SAME commit as the first ledger write, or this instrument becomes the second write-only ledger in the repo.


### Blockers raised


- P1 DECISION-GATING — Is the uranium sleeve actually held, and where? No uranium position exists in either visible live account (Composer = 6 tickers, IBKR = SPY + BIL) and no cost-basis file exists anywhere in the monorepo. If the 13 names are held at a broker this session cannot see, every netting number in this report is wrong: uranium sits in the 31-name mega-cluster at rho 0.58 alongside the leveraged-Nasdaq book, so it would ADD to the dominant factor rather than diversify it. Per the repo's MISSING KEY INPUTS rule I am not analyzing around this — asking. Same question for genomics single names and any BTC spot held outside btc-executor.


- P1 DECISION-GATING — IBKR holdings are inferred, not read. The $34,740 SPY / $14,940.58 BIL figures come from a README commit dated today, not from the venue. Credentials live only in ibkr-executor (correct, per repo law), so the netting job needs a read-only holdings endpoint exposed by that service. Until then one of the two live venues is a static assumption inside a daily-rebalancing calculation.


- P2 SCORE-MOVING — Are the TLT/TMV duration offset ($121k gross to $8.5k net) and the LABD-vs-genomics-longs conflict intentional or accidental? They are the two worked examples that justify building the netting layer at all, but the correct remedy differs entirely: if intentional, the layer should whitelist them; if accidental, they are live money being spent on offsetting spread and daily rebalance costs right now.


- P2 SCORE-MOVING — Cohort threshold histograms (RSI(10)>79 x1049, <30 x988 etc.) come from the recon's 259-symphony SAMPLE, not the full 2,659 corpus, and carry no dollar weight because the 52-column search schema has no AUM field. Casey's overlap percentages are therefore against a sampled, author-counted denominator. A full 2,659 census is a ~35-minute job and should run before any overlap number is published.


- P3 COMPLETENESS — All betas here are 1y daily log returns applied to 2023-2026 weight states, and several loadings are visibly drifting (OKLO to SMH moved +0.28 to +0.54; URA to GLD +0.37 to +0.54). The spec requires 1y AND 3y sign agreement; I computed both windows for correlations but only 1y betas for the exposure math. Re-run with rolling betas before any of these dollar figures is treated as frozen.


---

## P7 — Price-layer resilience and the persistence gap

**Independent verification:** DID NOT RUN (usage limit) — single-sourced


### Verdict

The price layer is in better shape than the brief assumed, and the persistence layer is in worse shape. Yahoo has no rate limit worth designing around (~3,200 requests / 170 MB pulled with zero throttling) - its 429 is a UA blocklist masquerading as one, and a backoff loop would hang forever. But it is under a blanket robots Disallow and has already killed two of its three price endpoints, so it cannot stand alone; stockanalysis.com plus api.nasdaq.com give a genuine keyless 3-source quorum (0.00% median agreement on raw close) for US listings over the last 10 years, and NOTHING for CCJ pre-2016, U-UN.TO or SRUUF. Stooq is dead (JS proof-of-work behind a 200). FRED was unreachable on 8/8 attempts and is a P1 blocker, not a fallback. Two structural facts change the design: (1) CL=F is an unadjusted front-month splice whose phantom roll gaps dominate its 20-year return (+21.4% printed vs -76.2% actually earned by USO), so `=F` is a level-only symbol - the recon's already-refuted contango trade would have landed exactly here; (2) `adjclose` is retroactively rewritten on every dividend - 99,150 rows/year across 14 names - so vendor adjusted close is not a storable primitive, and any naive port of the edge_revisions tripwire to prices jams the system in a permanent un-clearable YELLOW within days. The persistence gap is not that the pattern is missing; it is that barbell-lab's upsert_prices does ON CONFLICT DO UPDATE SET close_adj=... today, silently overwriting history on every ingest, while the correct append-only tripwire sits in edge/db.py wired only to NAV and trades. Fix is: store raw close plus a corporate-actions table, derive adjusted at read, and reconcile any delta explainable by a newly-observed action before raising the tripwire. Best unexpected find: the Global X holdings archive is date-addressable back to 2024-08-06 with share counts, and the median share-count change across 57 holdings (+0.384%, extremes spanning 0.004pp) is a clean creation/redemption read - an actual dollar-flow series for the uranium complex, which is the kind of mechanism P14 ranks above every statistical crowding measure. 14/14 gates pass live.


### Findings


**1. Yahoo's 429 is a User-Agent blocklist, NOT a rate limit. Any retry/backoff loop on 429 spins forever. There is no observable rate limit at any volume a nightly job would use.**


> Same URL, same params, same second: UA 'Mozilla/5.0' -> 200 (3631B); UA 'Mozilla/5.0 (crowding-research)' -> 200; UA 'python-requests/2.33.1' -> 429 body 'Edge: Too Many Requests' (23B); UA 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36' -> 429 body 'Too Many Requests\r\n' (19B). Two distinct edge rules, both deterministic on UA. Meanwhile with an accepted UA: 1403 sequential requests in 60.0s (23.4 req/s), then 600 @ conc=20, 1000 @ conc=50, 200 full-history @ conc=20 (169.7 MB in 7.3s, 23.3 MB/s) = ~3200 requests / 170 MB with codes={200: N} every time, ZERO 429s. Latency p50=41ms p95=49ms. The ~25 req/s ceiling was the local egress proxy, not Yahoo.


Build implication: Pin the exact UA string in config as part of the contract and gate it (G1). On 429: FAIL the feed and alert as 'UA rejected' - never back off and retry. Per-source UA, not one global: Yahoo 429s the full Chrome UA that stockanalysis.com requires.


**2. ToS/continuity risk on Yahoo is concrete and already realised: it has killed two of its three public price endpoints and the survivor sits under a blanket robots Disallow.**


> query1.finance.yahoo.com/robots.txt = 'User-agent: *\nDisallow: /' (26 bytes, entire API host). Probed live today: /v7/finance/quote?symbols=SPY -> 401 {'code':'Unauthorized'}; /v7/finance/download/SPY?...&events=history -> 401 {'code':'unauthorized','description':'User is not logged in'}. Only /v8/finance/chart survives, crumbless. Free redundancy: query2.finance.yahoo.com/v8/finance/chart/SPY returns a byte-identical 3631B payload. By contrast stockanalysis.com/robots.txt disallows only /e/ and /p/ (our path is allowed); api.nasdaq.com/robots.txt disallows all.


Build implication: Yahoo cannot be the sole price layer. Treat it as primary-but-revocable, wire query2 as a same-vendor host failover, and keep stockanalysis.com (the only leg whose robots permits the path) as the independent-vendor fallback. Budget for the v8 endpoint disappearing the way v7 did.


**3. Yahoo adjclose semantics settled: `close` is SPLIT-adjusted only; `adjclose` is split AND dividend adjusted. adjclose is therefore RETROACTIVELY REWRITTEN across the entire history on every single dividend - 99,150 rows/year across a 14-name universe.**


> NVDA 10:1 split 2024-06-10: close[i-1]/close[i]=0.993 (not 10) -> splits already back-applied to raw close. adjclose/close steps only at ex-div dates and equals exactly 1.000000 after the last dividend (CCJ, TQQQ, NVDA, SPY all confirmed); first-bar adj/close = 0.663 (CCJ), 0.549 (SPY). Concrete rewrite: CCJ's 1996-03-14 adjclose is 5.983489 today; before the 2025-12-01 $0.172 dividend it was 5.995139 (-0.1943%) - all 7,664 CCJ rows changed value on that one day. Per-year totals: CCJ 7664 bars x 3.12 div/yr, SPY 8453 x 4.02, QQQ 6911 x 3.24, TQQQ 4162 x 1.27, URA 3976 x 1.26, LEU 7069 x 1.03, URNM 1692 x 0.74 = 99,150 rows/yr. Splits rewrite raw close the same way.


Build implication: NEVER persist a vendor's adjusted close. Store raw `close` + the dividend/split event stream (events=div,splits) and DERIVE adjusted at read time. Otherwise the revision tripwire fires ~99k times a year and the only documented exit (resolve_revisions, human rationale >=10 chars) makes the system permanently un-clearable YELLOW.


**4. CL=F and GC=F are UNADJUSTED front-month splices. The phantom roll gap is not a rounding artifact - it is the dominant term in CL=F's 20-year 'return'.**


> CL=F today = 83.44 = CLV26.NYM exactly (meta.shortName 'Crude Oil Oct 26'). The roll: 2020-04-20 close -37.63 (May contract), 2020-04-21 close 10.01, 2020-04-22 close 13.78 -> a +37.6623% one-day 'return' that is purely the May->June calendar spread. Aggregate over the common window 2006-04-10..2026-08-28: CL=F close 68.74 -> 83.44 = +21.4%, while USO (an actually-rolled long WTI position) adjclose 544.16 -> 129.70 = -76.2%. 97.6pp of divergence is phantom. Gold is far milder: GC=F +917.6% vs GLD +821.3% over 2004-11-18..2026-08-28 (~0.45%/yr, roughly GLD's own 0.40% fee). Historical dated contracts are NOT retrievable - only CLV26/CLX26/CLZ26 (3 of 24 tried) returned data.


Build implication: Any `=F` symbol is legal as a LEVEL (for term-structure/backwardation reads) and ILLEGAL as a return. G5 enforces this two ways: a numeric assertion pinning the +37.66% gap, plus a static scan that fails the build if an `=F` string and a returns calculation appear in the same file. That scan is live-tested: it flagged 3 of my own probe scripts and finds ZERO offenders in …


**5. Yahoo returns HTTP 200 with a valid schema and exactly ONE row for ^VIX9D, ^VIX3M and ^VIX6M. A max(date) >= today - N staleness gate PASSES on this, because the single row is today's.**


> ^VIX9D, ^VIX3M, ^VIX6M: n=1, first=last=2026-08-28, under every param form tried (period1=0, range=max, range=5y, period1=2020) - and meta.validRanges still advertises ['1d','5d','1mo','3mo','6mo','1y','2y','5y','10y','ytd','max']. Controls in the same run: ^VIX n=9564 (1990-01-02+), ^VVIX n=4945 (2007-01-03+), ^SKEW n=9232. Separately, range=max + interval=1d SILENTLY returns dataGranularity='1mo' (^VIX n=440 monthly instead of 9564 daily) - production must use epoch period1/period2.


Build implication: Freshness alone is insufficient. Every feed needs BOTH max(date) >= today-N AND a minimum row count AND a minimum history span (G2). The whole VIX term-structure sleeve must come from Cboe, never Yahoo; G3 pins the empty series as a known-bad control so anyone wiring VIX9D from Yahoo fails the build.


**6. Cboe's index CSVs are the term-structure source and are live and deep - but their legs are published on DIFFERENT days, so a naive .iloc[-1] ratio silently mixes two dates.**


> All 200/text-csv today: VIX n=9260 01/02/1990..08/27/2026 (last-modified Fri 28 Aug 01:50 GMT); SKEW n=9215 ..08/27/2026 (01:21 GMT); VIX9D n=3936 01/04/2011..08/28/2026; VIX3M n=4262 09/18/2009..08/28/2026; VIX6M n=4694 01/02/2008..08/28/2026; VVIX n=5093 03/06/2006..08/28/2026 (all four at 22:01 GMT). VIX and SKEW are ONE DAY STALER than the rest. Term-structure history is therefore 15.6y (VIX9D) / 16.9y (VIX3M), confirming the recon's ~15y, not 36y. Cboe put/call totalpc.csv is now 403 AccessDenied with an S3 XML body (previously 200-with-2019-data) - dead either way.


Build implication: G6 asserts per-leg freshness AND cross-leg date alignment (max-min spread <= 4 days) AND sets the composite's as-of to min() across legs. Any ratio built from multiple files inherits the OLDEST leg's date - this is a new gate class the recon did not have.


**7. Stooq is DEAD as a keyless fallback - it answers HTTP 200 with a JavaScript proof-of-work browser challenge. FRED was unreachable from this session on every attempt.**


> stooq.com/q/d/l/?s=ccj.us&i=d -> HTTP 200, 796 bytes, content-type text/html, body is a <script> computing SHA-256 until it finds a 4-zero prefix then POSTing /__verify. Two calls returned two different nonces - it is a live challenge, not a cached page. FRED: fredgraph.csv?id=DCOILWTICO failed 8/8 attempts across requests and curl - 'HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR', 'Empty reply from server' on --http1.1, ProxyError/RemoteDisconnected under python. fred.stlouisfed.org does NOT appear in the proxy's recentRelayFailures list (unlike ai.composer.trade), so this is not an egress-policy denial. api.stlouisfed.org -> 400 (key required). federalreserve.gov datadownload -> 2


Build implication: Delete Stooq from the fallback plan entirely. FRED must be re-probed from the production network before anything load-bearing depends on it - the recon listed it as live today, so this is either intermittent or path-dependent. Do not design around it in the meantime (house rule: ask, don't analyze around a missing input).


**8. The real keyless price fallback is stockanalysis.com, with Nasdaq as a third quorum leg. Raw closes agree with Yahoo to 0.00% median across the whole v1 universe - but stockanalysis silently degrades any unrecognised range token to 1 year.**


> 14/15 universe symbols: median |close diff| vs Yahoo = 0.0000% over the last 250 common days, on both stockanalysis and Nasdaq. Range trap: /api/symbol/s/ccj/history?range=10Y -> n=2513 (2016-08-30); range=All / MAX / Max / 20Y / 30Y -> n=252 (2025-08-28) with HTTP 200 and identical valid JSON. 10Y is the ceiling. Coverage limits, all verified: TSX and OTC paths (quote/tsx/U.UN, quote/tsx/CCO, quote/otc/SRUUF) -> 400; Nasdaq needs assetclass=etf for ETFs or returns 200-with-empty. Nasdaq is the odd leg out on 2 of 250 UUUU closes (2026-05-15: 17.40 vs Yahoo=stockanalysis 18.41, 5.49%; 2025-12-24: 14.64 vs 15.10) - two sources cannot break that tie, three can.


Build implication: Three-source median quorum, not A-vs-B (G14). Fallbacks cover only the last 10 years and only US listings - CCJ's 1996+, U-UN.TO and SRUUF have NO keyless second source. G12 pins the range-token trap so a refactor to range='All' fails the build.


**9. Yahoo and stockanalysis disagree by up to 1.36% on ADJUSTED closes for the same instrument on the same day while agreeing to 0.056% on RAW closes - independent proof that vendor adjusted-close is not a storable primitive.**


> CCJ, 2513 common days: raw close max diff 0.0562%; adjusted max diff 1.3564%, median 0.0055%. Concrete: 2016-08-30 both report close = 9.34 exactly, but Yahoo adjclose = 8.647 and stockanalysis 'a' = 8.53. Different dividend back-adjustment conventions on identical price data. Separately, Yahoo is MISSING 15 months of SMR history (n=1129 from 2022-03-01) that both fallbacks carry (n=1435/1436 from 2020-12-08) - Yahoo drops pre-deSPAC SPAC history.


Build implication: Cross-source reconciliation must run on RAW close only; adjusted values would blow any tolerance gate. Confirms the store-raw-plus-events design. Also: for any de-SPAC name (SMR, OKLO) Yahoo's history depth is not authoritative - check a fallback before freezing a lookback window.


**10. SPUT resolves to U-UN.TO. SPUT.TO and U.TO are 404. The 2006+ history on U-UN.TO is a spliced predecessor with a 6-session FROZEN price at the 2021 conversion.**


> U-UN.TO -> 200, n=5097, 2006-05-09..2026-08-28, CAD, 'SPROTT PHYSICAL URANIUM TRUST'. U-U.TO -> 200, n=1279, 2021-07-26+, USD. SRUUF -> 200, n=1282, 2021-07-22+, USD (OTC). SPUT.TO and U.TO -> 404 'No data found, symbol may be delisted'. The splice artifact: U-UN.TO close is EXACTLY 5.11 on 2021-07-16, 07-19, 07-20, 07-21, 07-22 and 07-23 - a 6-bar flatline straddling the Uranium Participation Corp -> SPUT conversion. Broader flatline audit (longest identical-close run): NXE 11 bars (2013-12-12..12-27, plus 249 zero-volume bars), CCJ 7, UEC 7, U-UN.TO 6, OKLO 5 (28 zero-vol), everything else <= 3.


Build implication: Use U-UN.TO for depth (CAD - needs a USDCAD leg) and SRUUF/U-U.TO for the clean post-2021 USD line; neither USD line has any keyless fallback. Add a flatline/zero-volume detector to the gate set and quarantine the 2021-07-16..23 window explicitly. NXE's pre-2014 history is too thin to calibrate on.


**11. The Global X holdings archive is date-addressable back to 2024-08-06 and carries Shares Held AND Market Value per holding - which yields a genuine DOLLAR FLOW measure for the uranium equity complex, not a positioning percentile. This partly repairs blind spot (1).**


> URL pattern https://assets.globalxetfs.com/funds/holdings/ura_full-holdings_YYYYMMDD.csv, discovered by scraping the fund page (the legacy ?download_full_holdings=true param is now silently ignored and returns 303KB of HTML with a 200). Date IS honoured: 20260827/20260826/20260820/20260728/20250827/20240827 all 200 with DISTINCT md5s; 20260828 and 19990101 both 404. Bisected archive start = 2024-08-06. Flow decomposition 2026-08-20 -> 2026-08-27: total market value $6.145B -> $6.805B (+10.74%), but the MEDIAN share-count change across 57 common holdings is +0.384% with extremes of +0.3820% and +0.3868% - a spread of 0.004pp, i.e. a near-perfect uniform basket scaling. That uniform multiplier


Build implication: Ship URA net-creation flow as a first-class daily series: estimator = MEDIAN across holdings of the share-count ratio (median, so quarterly index rebalances don't corrupt it). Caveats to stamp on every use: 2 years of history only (~515 obs), one fund, one number per day (no per-holding information - the uniform scaling is the whole signal). The recon's 'valid for basket definition, NOT for flow' …


**12. barbell-lab is ALREADY silently overwriting price history today. The revision tripwire the monorepo needs exists in edge/db.py but is wired only to NAV and trades - never to prices or FRED.**


> barbell-lab/src/barbell/db.py line ~143: `INSERT INTO prices (...) VALUES (?,?,?,?,?,?) ON CONFLICT(ticker, date, source) DO UPDATE SET close_adj=excluded.close_adj, close_raw=excluded.close_raw, volume=excluded.volume` - an unconditional silent overwrite of stored history on every ingest. upsert_fred does the same (`DO UPDATE SET value=excluded.value`). grep for edge_revisions / record_nav / REVISION outside barbell/edge/ returns ZERO hits. Meanwhile barbell-lab/src/barbell/edge/db.py has exactly the right pattern: record_nav returns 'inserted'|'unchanged'|'REVISION', never overwrites, logs conflicts to edge_revisions(strategy_id, table_name, row_key, stored, incoming, seen_at, resolved, re


Build implication: Do not build a new persistence layer - re-point the existing one. (a) Add a `series_revisions` table mirroring edge_revisions to barbell/db.py. (b) Replace both DO UPDATE clauses with ON CONFLICT DO NOTHING plus a compare-and-log path. (c) Drop close_adj from the stored columns; store close_raw + a corporate_actions(ticker, ex_date, kind, value) table and derive adjusted at read time. (d) …


**13. Every trap the recon named on FINRA and Socrata reproduced today, plus two new ones - and all are now expressible as assertions rather than folklore.**


> FINRA regsho: CNMSshvol20260827/26/28 all 200 with DISTINCT md5s (9d2d69/b74934/bdbbb6) - today's file already published, so T+0 not T+1. 20260829 and 20260830 both 403 with a 111-byte S3 <Error><Code>AccessDenied</Code> body and IDENTICAL md5 b6c792c0f58f - the terminal-403 signature. Volumes are fractional as warned ('760961.969573'). NEW: FINRA consolidatedShortInterest POST with settlementDate EQUAL returns HTTP **204 with 0 bytes** for 2026-08-15 and 2026-08-16, and 200/670B for 2026-07-31 - raise_for_status() PASSES a 204 and .json() then throws. Socrata: the WTI legacy-COT filter returns exactly 648 rows at $limit=1000, 5000 AND 50000 - stable and strictly under the smallest limit, so


Build implication: Encoded as G8 (403 bodies must be byte-identical -> terminal, never retried), G9 (204 counts as failure; only row-count is honest), G10 (three limits must agree AND fall strictly below the smallest - equality-to-limit IS the truncation signature), G11 (distinct date params must yield distinct hashes; an impossible date must 404).


**14. The gate suite is written and RUNS GREEN against the real feeds today: 14 of 14 pass.**


> /tmp/claude-0/-home-user-uranium-dashboard/a0106a67-22d0-5920-b96a-b21949d01b35/scratchpad/gates/test_feed_gates.py, run via run.py (no pytest in this image): G1 yahoo_429_is_a_ua_block PASS 0.9s | G2 yahoo_freshness_AND_depth PASS 10.9s (15 symbols x freshness + min-bars + min-span) | G3 empty_series_trap PASS 1.1s | G4 range_max_degrades_to_monthly PASS 0.4s | G5 futures_quarantined PASS (numeric |gap-0.3766|<0.002 True; static scan over /home/user/uranium-dashboard finds ZERO offenders - it correctly flagged 3 of my own probe scripts, proving the scan works) | G6 cboe_fresh_and_DATE_ALIGNED PASS 2.7s | G7 putcall_stays_quarantined PASS | G8 finra_403_terminal PASS 1.4s | G9 finra_204_is_f


Build implication: Lift the file into the repo as-is (I was read-only). Two additions still needed before it is complete: a bar-finality rule - only persist Yahoo's last bar as FINAL when meta.regularMarketTime >= meta.currentTradingPeriod.regular.end (verified field names; both = 2026-08-28T20:00:00Z today), otherwise you persist a live partial bar and manufacture a revision - and a flatline/zero-volume detector …


### Blockers raised


- P1 FRED IS DOWN FROM THIS SESSION - 8/8 failures (HTTP/2 INTERNAL_ERROR, empty reply, ProxyError) across requests and curl, on fredgraph.csv and /data/*.txt alike. It is NOT an egress-policy denial (fred.stlouisfed.org is absent from the proxy's recentRelayFailures, unlike ai.composer.trade). The recon listed it live today, so this is intermittent or path-dependent. Re-probe from the Render production network before any rates/credit/liquidity series depends on it. I have deliberately NOT designed around it.


- P1 WHAT IS THE v1 UNIVERSE? I probed a 15-name uranium+macro set of my own construction (URA URNM URNJ CCJ NXE UEC DNN UUUU LEU OKLO SMR U-UN.TO U-U.TO SRUUF plus TQQQ/SPY/QQQ/^GSPC/^VIX/futures). The coverage matrix, the min-bars/min-span thresholds in G2, and the fallback-gap list are all keyed to that guess. Give me the actual list and I will re-verify every cell; several answers change (anything non-US or pre-2016 has NO keyless second source).


- P1 COMPOSER MCP IS UNREACHABLE - the server returned 502 on connect and the proxy logged 7+ connect_rejected entries for ai.composer.trade:443 ('gateway answered 502 to CONNECT - policy denial or upstream failure'). I could not run any of the permitted read-only routes (POST /search/symphonies, /backtest), so nothing in the 2,659-symphony finding was re-verified and no Composer feed appears in the coverage matrix or the gate suite. Needs an egress-policy fix or a working endpoint.


- P2 CAMECO URANIUM SPOT/TERM IS AN HTML SCRAPE, NOT A CSV. The uranium_price_history.csv URL returns 28KB of the HTML site with a 200. The data IS there and complete (491 Drupal table rows: monthly spot from 1988/01/01, plus a separate 5-year term table), but it is a server-rendered <table> that any site redesign silently breaks, and the endpoint returns 200-with-HTML on every failure mode. Confirm this is acceptable as the sole uranium-price source, or name a second one - there is no alternative keyless uranium spot feed and UX=F on Yahoo is dead (n=1, ALTSYMBOL, name=None).


- P2 I WAS READ-ONLY, so test_feed_gates.py, the raw-close+corporate-actions schema change, and the upsert_prices/upsert_fred fix are all specified but NOT applied. The two silent-overwrite ON CONFLICT DO UPDATE clauses in barbell-lab/src/barbell/db.py are corrupting stored history on every ingest right now; that is a live defect, not a design task.


---
