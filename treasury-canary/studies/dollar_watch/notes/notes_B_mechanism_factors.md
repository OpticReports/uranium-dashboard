# Finder B — the dollar-crisis MECHANISM and the free series that measure it

Date: 2026-11-02. Every endpoint below was probed with one live request today; status/shape/latest value are from those probes (raw bodies in `raw/`, probe + analysis scripts in `scripts/`, episode chart `episodes_leadlag.png`). Nothing is recommended that was not probed. Numbers from web pages are flagged `[web]`; from my own memory `[memory]`.

Companion files
- `scripts/probe.py` generic prober; `scripts/analyze.py` episode lead/lag + current readings (output `scripts/analyze_out.json`); `scripts/johnson_test.py` BIS-credit-vs-dollar test (`scripts/johnson_quarterly.csv`); `scripts/chart.py` -> `episodes_leadlag.png`.
- `raw/bis_bulk/WS_GLI_csv_col.csv` = the whole BIS Global Liquidity Indicators set (225 series, 1977Q4-2026Q2, 105 KB zip).

---

## 0. Ten-line read

1. Johnson's "$13tn" is the BIS GLI series `Q.USD.3P.N.A.I.B.USD` (USD credit to non-banks outside the US). It was $13.3tn at 2022Q2; it is **$15.13tn at 2026Q2, +8.1% yoy** (bank loans $6.94tn +9.6%, int'l debt securities $8.20tn +6.7%; EMEs $4.60tn +8.7%). Free CSV, quarterly, ~4-month lag.
2. Johnson's "~$100tn" is the BIS Dec-2022 QR figure: FX swaps/forwards/currency swaps outstanding **$97tn at end-June 2022** (USD on one side of 88% = ~$85tn; non-banks outside US ~$26tn, non-US banks ~$39tn). The same BIS OTC series now reads **$129.3tn at end-2025** (all currencies), **$113.5tn with a USD leg**. Free CSV, semiannual.
3. The mechanism is a chain: stock of USD debt -> rollover need -> dollar funding price (basis, CP, swap lines) -> EM FX/reserves -> growth/trade -> defaults. The free, LEADING measurements sit in the funding-price link: **financial-CP minus T-bill spread (DCPF3M−DTB3), OFR FSI funding subindex, NFCI risk subindex, Fed swap-line usage (SWPT / NY Fed ops)**. All of them peaked 2-5 months BEFORE the broad dollar in 2008 and 1-3 months before it in 2022; in 2020 everything was within +/-7 days.
4. The broad dollar itself (DTWEXBGS) is COINCIDENT-to-LAGGING: its peak marks the END of each episode (2009-03-03, 2016-01-20, 2018-11-27, 2020-03-23, 2022-09-26). Treat a dollar peak as the all-clear, not the warning.
5. Gold behaves as Johnson says at the acute point (−29% 2008, −12% in 8 days 2020, −21% Mar->Sep 2022, −21% 2014->2015), but it bottoms BEFORE or AT the dollar peak (111 days before in 2008), so gold's turn is one of the earliest free "crisis subsiding" flags.
6. Johnson's sign claim holds descriptively in the BIS data: USD credit outside the US grows **9.5% yoy when the dollar is down yoy vs 4.8% when it is up** (2001-2026, n=102 quarters); corr(yoy credit growth, yoy dollar change) = −0.50 contemporaneous, −0.55 with the dollar leading by one quarter. The only outright contractions were 2009Q1-Q3 and 2022Q3-2023Q4 — both after dollar spikes. Causality is not identified (dollar and credit both respond to risk appetite).
7. Current: broad dollar 121.3 (93rd pct since 1995, 78th pct 10y; +2.2% 6m, +0.3% 12m; all-time high was 130.0 on 2025-01-13). DXY 101.6 — inside Johnson's 85-105 band, upper third. Funding stress is absent (CP spread 5 bp = 5th pct; SOFR 99th-pct−SOFR 8 bp; swap-line draws $156m; OFR funding −0.15). Two things are NOT calm: Brent $123 (+88% 12m, 99th pct) and foreign official custody holdings at the Fed at $2.57tn (0.4th pct of 10y, −6.6% 12m).
8. FRED's ICE BofA OAS series (EM and all HY/IG) now start **2023-11-03** — history was cut; the EM-OAS "1998+" promise in the brief is gone. Anything needing EM spread history must use EMB price (FMP, 2007-12+) or OFR's EM subindex (2000+).
9. Cross-currency basis, FRA-OIS, EMBI, sovereign CDS, global PMI, Baltic Dry, China TSF are paid or scrape-only. The free proxies for the basis are CP−bill, OFR funding, and swap-line draws; for EMBI, EMB and OFR EM; nothing free proxies CDS or PMI.
10. Panel recommendation (section 5): 12 series, 10 of them FRED/OFR/NY Fed/BIS keyless CSV, 2 via the existing FMP key.

---

## 1. THE MECHANISM — nodes, free series, probe results

Chain: **(a) stock of USD debt outside the US** -> rollover/hedging demand -> **(b) price of dollar funding** -> **(c) EM FX, reserves, spreads** -> **(d) trade/growth** -> defaults; policy drivers **(e)**, safe-haven amplifier **(f)**, and the feedback **(g)** (falling dollar -> more USD credit -> bigger stock).

### (a) Stock of USD debt outside the US
| Series | Endpoint (probed) | Freq / lag / history | Latest |
|---|---|---|---|
| BIS GLI: USD credit to non-banks outside US, loans+IDS | `https://stats.bis.org/api/v1/data/WS_GLI/Q.USD.3P.N.A.I.B.USD/all?format=csv` (200, 106 rows) | Q, ~4 mo, 2000Q1+ | 2026Q2 **$15.133tn**, yoy +8.07% (2026Q1 $14.771tn, 2025Q4 $14.264tn) |
| same, yoy growth % | key `...I.B.771` (in `all/all?lastNObservations=1` dump) | Q | 8.03% |
| bank loans only | `Q.USD.3P.N.B.I.G.USD` | Q | $6.936tn, +9.6% |
| int'l debt securities, non-banks | `Q.USD.3P.N.A.I.D.USD` | Q | $8.196tn, +6.7% |
| IDS, non-financial issuers only | `Q.USD.3P.P.A.I.D.USD` | Q | $4.533tn, +8.7% |
| EMEs total | `Q.USD.4T.N.A.I.B.USD` (200, 106 rows) | Q | **$4.599tn, +8.7%** (loans $2.035tn +7.0%; IDS $2.564tn +10.1%) |
| EME regions | `4U` LatAm $1.390tn (+6.1%), `4Y` Asia-Pac $1.080tn (+0.7%), `4W` Africa+ME $1.719tn (+17.0%), `3C` Dev. Europe $0.411tn (+8.7%) | Q | |
| countries | CN $303bn (−6.1%), MX $389bn (+6.0%), BR $200bn (+6.9%), TR $234bn (+9.7%), ID $218bn (+10.0%), IN $115bn (−2.8%), SA $265bn (+21.8%), ZA $36bn (−5.8%), AR $102bn (+19.8%), RU $43bn (−10.6%) | Q | |
| whole dataset, bulk | `https://data.bis.org/static/bulk/WS_GLI_csv_col.zip` (200, 105 KB; one CSV, 225 series wide-format) | | — |
| EUR / JPY analogues | `Q.EUR.3P.N.A.I.B.EUR`, `Q.JPY.3P...` present in bulk | | BIS commentary 29-Oct-2026: euro IDS +13% yoy vs USD IDS +6.7% `[web]` |
| BIS release/commentary | `https://www.bis.org/publications/202610-commentary-ibs-gli` (fetched; "IBS/GLI 29 October 2026"; cross-border bank credit $40.7tn +11% yoy; EMDE cross-border bank credit +8.9%) | Q | |

History markers (same series, $tn): 2008Q3 6.07 -> 2009Q1 5.84; 2014Q2 9.23 -> 2016Q1 10.06; 2018Q4 11.57; 2020Q1 12.59; 2022Q2 13.31 -> 2022Q3 13.09 -> 2023Q4 12.76; 2024Q4 13.13; 2026Q2 15.13. Note the Jan-2026 BIS revision cut the EMDE aggregate (was shown as $5.3tn at 2025Q2, now $4.27tn at 2025Q3) `[web]` — do not splice old releases.

**Off-balance-sheet dollar debt (the "$100tn")**
- Source: Borio, McCauley, McGuire, "Dollar debt in FX swaps and forwards: huge, missing and growing", BIS Quarterly Review, 5 Dec 2022 (`https://www.bis.org/publ/qtrpdf/r_qt2212h.htm`, fetched). Exact figures: FX swaps + forwards + currency swaps outstanding **$97tn at end-June 2022** (from $67tn in 2016); USD on one side of 88% (~$85tn); "$80 trillion-plus" obligations to pay dollars; **non-banks outside the US $26tn** (vs ~$13tn on-balance-sheet, i.e. "double"); **non-US-headquartered banks $39tn** (vs $15tn on-balance-sheet, >10x capital); almost four-fifths matures in under one year. Abstract uses $25tn / "upwards of $35tn" — the body figures ($26tn/$39tn) are the ones to quote.
- Same aggregate, live, free: BIS OTC derivatives `WS_OTC_DERIV2`, FX risk category, instrument C = "forwards and swaps" (= outright forwards + FX swaps + currency swaps):
  `https://stats.bis.org/api/v1/data/WS_OTC_DERIV2/H.A.C.B.5J.A.5J.A.TO1.TO1.A.A.3.C/all?format=csv` -> **2025-S2 $129.30tn** (2025-S1 $129.95tn). USD-leg: `...A.USD.TO1...` -> **$113.50tn**. Breakdown 2025-S2: outright fwds+FX swaps (D) $83.3tn (USD $74.0tn), currency swaps (I) $46.0tn (USD $39.5tn), options (R) $19.3tn; all FX derivatives (A) $148.65tn. By counterparty (all FX): reporting dealers $52.0tn, other financials $78.7tn, **non-financial customers $18.0tn**. Semiannual, ~5-month lag, 1998+. Johnson's "$100tn" is therefore 2022-vintage; the current all-currency number is ~$129tn, dollar-leg ~$113tn.
- Caveat: BIS OTC is notional and consolidated by reporting dealer — it does not give "non-banks outside the US" directly; that split is the authors' estimate from Triennial + BIS banking data, only in the QR article (and a 2017 predecessor, r_qt1709e: ~$10.7tn+ for non-banks then).

**EM external debt (World Bank)**
- `https://api.worldbank.org/v2/country/LMY/indicator/DT.DOD.DECT.CD?format=json&per_page=100` (200): low- & middle-income total external debt stock **2024 $8.936tn** (2023 $8.835tn). Short-term: `DT.DOD.DSTC.CD` -> **$2.394tn 2024**. IDS source 6 also works (`/v2/sources/6/country/LMY/series/DT.DOD.DECT.CD/time/all/data?format=json`, 19,152 rows paged). Annual, ~12-month lag — a context number, not a monitor.
- IMF COFER (reserve composition) via the new SDMX API: `https://api.imf.org/external/sdmx/2.1/data/COFER?lastNObservations=1` (200, XML, 140 series): allocated reserves **$13.217tn 2026Q2, USD $7.495tn = 56.70% share** (2025 annual 56.52%). The de-dollarisation stock measure; quarterly, ~3-month lag. IRFCL (reserves templates) also answers but the unfiltered pull is 15.6 MB XML — use the FRED mirrors below for country reserves instead.

### (b) Dollar funding cost and stress (the link that LEADS)
| Series | Endpoint | Freq/lag/history | Latest (date) | Verdict |
|---|---|---|---|---|
| Financial CP 3m − 3m T-bill | FRED `DCPF3M` (=`RIFSPPFAAD90NB`) minus `DTB3` | D, 1 day, 1997+ | **0.05 pp** (2026-10-29); 5th pct all-time, 14th pct 10y | best free daily basis proxy; LEADS |
| Nonfinancial CP 3m − bill | `DCPN3M` − `DTB3` | D (gappy: DCPN3M last 2026-10-13), 1997+ | 0.00 pp | LEADS (2008: peak 2008-09-17) |
| CP outstanding | `COMPOUT` | W, 2001+ | $1,499bn (2026-10-28) | rollover-shrink signal |
| TED spread | `TEDRATE` | ends 2022-01-21 | 0.09 | history only |
| OFR FSI funding subindex | `https://www.financialresearch.gov/financial-stress-index/data/fsi.csv` (col "Funding"; also "Emerging markets", "Safe assets", "Credit", "Volatility", "United States", "Other advanced economies") | D, 1 day, 2000+ | **−0.151** (2026-10-29); 48th pct all, 66th pct 10y; max 9.58 on 2008-10-10 | LEADS; already loaded in repo (`sources/ofr.py` uses only the total) |
| OFR FSI total / EM subindex | same file | D | −2.117 / **−0.499** (14th pct all, 6th pct 10y) | coincident |
| Fed CB liquidity swaps outstanding (H.4.1) | FRED `SWPT` | W (Wed), 1 day, 2002-12+ | **$156m** (2026-10-28); peaks 2008-12-17 $583.1bn, 2012-02-15 $109.1bn, 2020-05-27 $448.9bn, 2023-12-27 $1.36bn | COINCIDENT-to-LAG in use, LEADING in *announcement* |
| NY Fed swap operations (per-op) | `https://markets.newyorkfed.org/api/fxs/all/search.csv?startDate=2007-12-01&endDate=2026-11-02` (200, 1,614 ops, 2010-05-18+; `latest.json` empty today; counterparties list OK) | per-op; daily outstanding can be rebuilt (I did; matches SWPT exactly at the 2020 peak) | $169m outstanding 2026-11-02 (BoE $5m 7-day 28-Oct @4.15%, ECB, BoJ small-value tests) | note: pre-2010 ops are NOT in this API — use SWPT for 2008 |
| SOFR 99th pct − SOFR | FRED `SOFR99` − `SOFR` | D, 2018-04+ | 0.08 pp (7th pct) | repo tail stress; spiked 3.25 pp 2018-12-31, 1.74 pp 2020-03-16 |
| SOFR − IORB | `SOFR` − `IORB` | D, 2021-07+ | **+0.05 pp (96th pct)** | reserve-scarcity tell (domestic, not FX) |
| ON RRP award rate / SRF usage | `RRPONTSYD` 4.375; `RPONTSYD` 0.000 (2026-10-30) | D | | context |
| Fed primary credit (discount window) | `WLCFLL` $9.57bn (2026-10-28) | W | | domestic bank stress |
| St Louis FSI / KC FSI / Chicago NFCI risk | `STLFSI4` −0.584 (2026-10-23); `KCFSI` −0.986 (Sep-26); `NFCIRISK` −0.562 (2026-10-23) | W/M/W | all low | NFCIRISK alarmed 2007-07-13, 4 weeks before the OFR funding index |
| Cross-currency basis (EUR, JPY 3m) | not free. Bloomberg/Refinitiv only. NOT on FRED, ECB SDW, BoJ, BIS. | | | **GAP #1** — see section 5 |
| FRA-OIS | not free (and FRA/LIBOR gone; the SOFR-era analogue is term-SOFR-vs-OIS, CME-licensed) | | | GAP |

### (c) EM stress
| Series | Endpoint | Freq/hist | Latest | Note |
|---|---|---|---|---|
| Fed EME dollar index (trade-weighted vs EM currencies) | FRED `DTWEXEMEGS` | D, 2006+ | **130.21** (2026-10-23); 89th pct all, 77th 10y; +1.5% 6m, −1.2% 12m; 2026 range 126.1-131.3 | the free "MSCI EM currency index"; AFE counterpart `DTWEXAFEGS` 114.30 |
| Self-built equal-weight EM FX basket (log-avg of BRL, MXN, ZAR, INR, KRW, THB, CNY, MYR; 1995=100; up = EM weaker) | FRED `DEXBZUS DEXMXUS DEXSFUS DEXINUS DEXKOUS DEXTHUS DEXCHUS DEXMAUS` (all 200; TRY and IDR are NOT on FRED daily) | D, 1995+ | 231.1 (88th pct all, 61st 10y) | extends EM FX back to 1995 (Asia crisis) |
| EM hard-currency bond ETF | FMP `historical-price-eod/light?symbol=EMB` (200, 4,747 rows 2007-12-19+) | D | $91.90 (2026-11-02); −4.9% 12m; 19th pct all | the free EMBI proxy (price, not spread) |
| EM equity | FMP `EEM` (2006-12+) | D | $62.03; 97th pct all | |
| EM local-currency ETF | FMP `CEW` (2009-05+) | D | $19.48 | thin volume; basket above is better |
| ICE BofA EM corporate plus OAS | FRED `BAMLEMCBPIOAS` | D, **history starts 2023-11-03** (784 obs) | 1.81% | all 11 EM ICE series probed exist (`BAMLEMPBPUBSICRPIOAS` public-sector 1.43, `BAMLEMHBHYCRPIOAS` EM HY 3.88, `BAMLEMRACRPIASIAOAS` Asia 1.10, `BAMLEMRLCRPILAOAS` LatAm 2.65, `BAMLEMRECRPIEMEAOAS` EMEA 1.90, `BAMLEM4BRRBLCRPIOAS` B-rated 6.04, `BAMLEMUBCRPIUSOAS` USD-only 1.82) but ALL truncated to 2023-11 — same for `BAMLH0A0HYM2` 3.44 and `BAMLC0A0CM` 0.94. Current-level only. |
| EM central-bank reserves (IMF IFS via FRED, total reserves ex gold, $m) | `TRESEGCNM052N` China 3,482,386 (Jun-26); `TRESEGBRM052N` Brazil 339,932 (Sep-26); `TRESEGINM052N` India 635,512 (Aug-26); `TRESEGMXM052N` 249,358; `TRESEGKRM052N` Korea 434,679; `TRESEGTRM052N` Turkey 59,026; `TRESEGIDM052N` Indonesia 134,046 (Aug-26); `TRESEGZAM052N` 58,577 | M, 1-3 mo lag, 1950s+ | | reserve SALES = the EM defence; monthly, lags |
| OFR FSI EM subindex | (b) above | D | −0.499 | |

### (d) Global growth / trade
| Series | Endpoint | Freq/lag | Latest | Note |
|---|---|---|---|---|
| Korea exports (OECD MEI via FRED, USD) | FRED `XTEXVA01KRM667S` | M, ~2 mo | $100.4bn (Aug-26) | Korea Customs first-of-month release is faster but needs a data.go.kr key (XML) — not probed; FRED route is keyless |
| Copper (IMF) | `PCOPPUSDM` | M | $14,473/t (Sep-26) | |
| Brent / WTI | `DCOILBRENTEU` / `DCOILWTICO` | D | **Brent $123.10 (2026-10-27), +88% 12m, 99th pct** | an oil shock is in the current data — dollar-positive for importers' funding needs |
| Baltic Dry | no free API found (stooq blocked by JS challenge; Yahoo has `BDRY` ETF only, 200) | | | GAP; BDRY is a freight-futures ETF, not the index |
| CPB World Trade Monitor | `cpb.nl/en/worldtrademonitor` and 2 variants -> 404 today; search found no 2026 release page | M, ~8 wk | | NOT USABLE as probed; mark manual |
| China TSF | no free machine-readable source (PBoC Chinese-language HTML; CEIC paid) | | | GAP |
| Global PMI | S&P Global, paid | | | GAP |

### (e) US monetary policy and rate differentials
| Series | Endpoint | Latest |
|---|---|---|
| BIS policy rates (13 countries, one call) | `https://stats.bis.org/api/v1/data/WS_CBPOL/M.US+XM+JP+GB+CH+BR+MX+IN+KR+ZA+TR+ID+CN/all?format=csv&startPeriod=2000-01` (200, 3,976 rows) | Sep-26: US 3.875, EA 2.50, JP 1.25, GB 3.75, CH 0, BR 13.75, MX 6.50, IN 5.25, KR 3.00, ZA 7.25, TR 37, ID 5.75, CN 3.00. (Daily `WS_CBPOL_D` -> 404.) |
| Fed target upper / ECB DFR | FRED `DFEDTARU` 4.00 (2026-11-02), `ECBDFR` 2.50, `ECBMRRFR` 2.65, `IORB` 3.90 | daily |
| 2y yields | US `DGS2` 4.61 (2026-10-29); Germany Bundesbank API `https://api.statistiken.bundesbank.de/rest/download/BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R02XX.R.A.A._Z._Z.A?format=csv&lang=en` 3.03 (2026-11-02; 10y `R10XX` 3.34); Japan MOF `https://www.mof.go.jp/english/jgbs/reference/interest_rate/jgbcme.csv` 2y 1.939 (2026-10-01 row; file is current-month only; repo's `boj_mof.py` already has the all-history file) | US−DE 2y = +1.58 pp; US−JP 2y ≈ +2.7 pp |
| 10y monthly (OECD via FRED) | `IRLTLT01DEM156N` 3.47, `IRLTLT01JPM156N` 3.05 (Sep-26) | |
| Real rate | `DFII10` 2.63; no free daily foreign real yields (Bundesbank has none for linkers; GAP, minor) | |

### (f) Safe-haven demand
| Series | Endpoint | Latest |
|---|---|---|
| Foreign official custody at Fed | FRED `WMTSECL1` | **$2,568.6bn (2026-10-28), −6.6% 12m, 0.4th pct 10y** (max $3,135bn 2021-03-10) |
| Gold | FMP `XAUUSD` (200, 5,000 rows back to 2007-12-24 — FMP caps at 5,000; page with `from/to` for older). FRED LBMA series `GOLDAMGBD228NLBM` -> 404 (discontinued). | **$3,962.6 (2026-11-02)**, −14% 6m, −27% from the 2026-01-28 peak $5,418.5 |
| JPY, CHF | `DEXJPUS` 156.87, `DEXSZUS` 0.8248 (CHF at 2.7th pct = strongest ever) | |
| VIX / MOVE | `VIXCLS` 19.42; MOVE via Yahoo `chart/%5EMOVE?range=10y&interval=1d` (200) 101.1 (74th pct 10y) | |
| DXY | FMP `DX-Y.NYB` 101.585 (2026-11-02; `DXY`/`^DXY` return []); Yahoo `DX-Y.NYB` daily only returns monthly for `range=max` | |

### (g) Re-dollarisation test (Johnson's sign claim) — BIS GLI vs broad dollar, 2001Q1-2026Q2
Method: quarterly log-change of `Q.USD.3P.N.A.I.B.USD` vs quarterly log-change of the broad dollar (monthly `TWEXBGSMTH` 2006+, spliced to `TWEXBMTH` before). The BIS series is in USD so there is no FX-valuation artefact (that is the clean property of the USD line; the EUR line would need deflating).
- corr(qoq credit growth, qoq dollar change): **−0.36** contemporaneous; −0.29 with dollar leading 1q; ~0 at ±4q.
- corr(yoy, yoy): **−0.50** contemporaneous, **−0.55** with the dollar leading by one quarter, −0.34 with credit leading by one quarter -> the dollar moves first, credit follows.
- Mean USD-credit growth: **+2.25% qoq when the dollar fell that quarter vs +1.28% when it rose** (n=51/51); **+9.46% yoy when dollar down yoy vs +4.80% when up** (n=50/52). EMEs: 8.99% vs 4.61%, corr −0.43.
- Trend-adjusted level elasticity: log(credit) on log(dollar) with a time trend -> **−1.18** (a 10% stronger dollar ~ 11% less USD credit outside the US than trend).
- Only contractions (yoy < 0): 2009Q1-Q3 and 2022Q3-2023Q4 — i.e. "de-dollarisation through default/deleveraging" shows up exactly after the two largest dollar spikes. At 2026Q2 credit is +7.8% yoy with the dollar −0.4% yoy: the re-dollarisation phase, by Johnson's own definition.
- Honesty: descriptive, in-sample, 102 quarters, no causal identification; both variables load on global risk appetite. Supports the sign, not the mechanism.

---

## 2. LEADS AND LAGS by episode (dates from the probed data; `scripts/analyze_out.json`)

Method: for each window, the date of each series' stress extreme, and the "first alarm" = first day the series exceeded its own trailing-5-year 95th percentile (5th for gold/EMB/custody/JPY/CHF). Window for 2008 is 2007-06 to 2009-06 so the alarms are real, not window-start artefacts.

| Series | 2008 (broad $ trough 2008-07-15, peak **2009-03-03** 106.0) | 2015-16 ($ peak **2016-01-20** 116.4) | 2018 ($ peak **2018-11-27** 116.9) | 2020 ($ peak **2020-03-23** 126.1) | 2022 ($ peak **2022-09-26** 128.5) | Label |
|---|---|---|---|---|---|---|
| Fin CP − bill | alarm 2007-06; peak 2008-10-15 (**−139d**) | alarm 2015-09-01; peak 2015-12-11 (−40d) | alarm 2018-03-09; peak 2018-04-03 (−238d) | alarm 2020-03-09; peak 03-25 (+2d) | alarm 2022-03-04; peak 2022-07-01 (**−87d**) | **LEADING** |
| Nonfin CP − bill | peak 2008-09-17 (−167d) | peak 2016-01-04 (−16d) | peak 2018-04-04 | alarm 2020-03-03; peak 03-26 | alarm 2022-03-04 | LEADING |
| TED | alarm 2007-06; peak 2008-10-10 (−144d) | 2015-12-31 (−20d) | 2018-04-04 (−237d) | 2020-03-26 (+3d) | (dead) | LEADING (history only) |
| OFR funding | alarm **2007-08-09**; peak 2008-10-10 (−144d) | peak 2016-02-11 (+22d) | 2018-04-05 (−236d) | alarm 03-18; peak 03-30 (+7d) | alarm 2022-03-04; peak 2022-07-01 (−87d) | **LEADING** (2008, 2022), coincident (2020) |
| NFCI risk | alarm **2007-07-13**; peak 2008-11-21 | — | — | alarm 2020-02-28 (−24d) | alarm 2022-02-25 | LEADING |
| St Louis FSI | alarm 2007-08-17; peak 2008-10-10 | alarm 2016-01-22; peak 02-12 (+23d) | peak 2018-12-28 (+31d) | alarm 02-28; peak 03-20 (−3d) | peak 2023-03-17 (SVB) | coincident |
| Fed swaps (SWPT) | alarm 2007-12-26; peak 2008-12-17 (−76d) | spikes only ($1.5bn) | $12bn 2018-01 (year-end) | peak 2020-05-27 (**+65d**) | $11.3bn 2022-10-26 (+30d) | usage LAGS the peak; *announcement* leads (below) |
| VIX | alarm 2008-09-17; peak 2008-11-20 (−103d) | 2015-08-24 (−149d) | 2018-02-05 / 12-24 | 2020-03-16 (−7d) | 2022-06-13 (−105d) | coincident/early-coincident; not a funding gauge |
| Gold (trough) | 2008-11-12 (**−111d**; 1003 -> 712, −29%) | 2015-12-17 (−34d; 1338 -> 1051) | 2018-08-16 (−103d) | 2020-03-19 (−4d; 1678 -> 1472, −12%) | 2022-09-26 (0d; 2049 -> 1622, −21%) | **early-coincident; turns first** |
| EMB (trough) | 2008-10-28 (−126d) | 2016-01-20 (0d) | 2018-11-27 (0d) | 2020-03-18 (−5d) | 2022-10-20 (+24d) | coincident |
| EEM (trough) | 2008-11-20 (−103d) | 2016-01-20 (0d) | 2018-10-29 (−29d) | 2020-03-23 (0d) | 2022-10-24 (+28d) | coincident |
| EM FX basket (weakest) | 2009-03-02 (−1d) | 2016-01-20 (0d) | 2018-09-05 (−83d) | 2020-04-24 (+32d) | 2022-10-24 (+28d) | coincident/LAG |
| EME dollar index (DTWEXEMEGS) | 2009-03-02 | 2016-02-11 (+22d) | 2018-11-13 (−14d) | 2020-03-23 (0d) | 2022-10-24 (+28d) | coincident/LAG |
| Custody (trough) | 2008-09-10 (−174d, reserve sales after Lehman) | 2016-11-02 (+287d) | 2019-01-02 | 2020-04-08 (+16d; −$113bn in 5 wks) | 2023-03-22 | LAG (sales continue after the peak) |
| Broad dollar | peak 2009-03-03 | 2016-01-20 | 2018-11-27 | 2020-03-23 | 2022-09-26 | **COINCIDENT-to-LAG: the peak ends the episode** |
| EM reserves (monthly IFS), defaults, Laeven-Valencia dates | 1-3 mo / years after | | | | | LAGGING |

Reading: in the two balance-sheet crises (2008, 2022) the **funding-price** series (CP−bill, OFR funding, NFCI risk) peaked 3-5 months before the dollar and alarmed 6-18 months before; in 2020 (a sudden stop) everything was within a week; in 2015-16 and 2018 (EM/China episodes with no US funding stress) the funding series were nearly silent and the EM series were coincident with the dollar. Two regimes: *dollar funding crisis* (2008, 2020, 2022-lite) where funding leads, vs *EM growth scare* (2015-16, 2018) where nothing free leads the dollar except VIX and gold by 1-5 months.

Swap-line announcement dates (Fed press releases fetched today): 2007-12-12 first ECB/SNB lines `[web, CFR + Fed reform page]`; **2008-10-13** BoE/ECB/SNB lines made unlimited at fixed-rate full allotment (7/28/84-day); 2008-10-29 BR/MX/KR/SG $30bn each `[memory]`; **2020-03-15** pricing cut to OIS+25 and 84-day tenor `[CFR web]`; **2020-03-19** nine temporary lines (AU, BR, KR, MX, SG, SE $60bn; DK, NO, NZ $30bn); 2013-10-31 standing lines made permanent `[web, Yale JFC]`; **2023-03-19** 7-day ops daily from 2023-03-20 "at least through end-April". Usage followed announcements by 1-10 weeks; the announcement itself is the leading policy signal and is not a series — log as events.

---

## 3. "WHEN THE CRISIS HAS SUBSIDED" — dated end-markers and the earliest free flag

"50% retrace" = the first date the series gave back half its move from the extreme toward its pre-window value (`analyze` second pass).

| Episode | Broad $ peak | Policy turn | Funding normalised (CP−bill 50% retrace) | OFR funding 50% | Gold trough | EMB/EEM trough | EM FX trough | Swap usage 50% off peak | Earliest free "turn" flag |
|---|---|---|---|---|---|---|---|---|---|
| 2008-09 | 2009-03-03 | 2008-10-13 unlimited swaps; 2008-11-25 QE1; 2009-03-18 QE1 expanded `[memory]` | 2008-10-17 (4 days after unlimited swaps) | 2008-10-20 | 2008-11-12 | EMB 2008-10-28 / EEM 2008-11-20 | 2009-03-02 | 2009-03-04 | **CP−bill collapse 2008-10-17**, then gold 11-12, EMB 10-28; dollar peaked 4.5 months later |
| 2015-16 | 2016-01-20 | Shanghai G20 2016-02-26 `[memory]`; Fed skips hikes | n/a (no funding stress) | n/a | 2015-12-17 | 2016-01-20 both | 2016-01-20 | n/a | **gold 2015-12-17**; EMB/EEM/EM FX coincident with $ peak |
| 2018 | 2018-11-27 | Powell "just below neutral" 2018-11-28; pivot 2019-01-04 `[memory]` | 2018-11-16 | 2019-01-29 | 2018-10-08 | EEM 2018-10-29 / EMB 2018-11-27 | 2018-10-31 | 2019-01-09 | **gold 10-08, EM FX 10-31, EEM 10-29** — all 1 month before $ peak |
| 2020 | 2020-03-23 | 2020-03-15 swap repricing; 03-19 nine lines; 03-23 unlimited QE + CPFF/PMCCF; 03-31 FIMA repo `[memory]` | 2020-05-07 | 2020-04-29 | 2020-03-19 | EMB 03-18 / EEM 03-23 | 2020-04-24 | 2020-07-08 | **gold 03-19 and EMB 03-18 (3-5 days before $ peak)**; funding spreads lagged by 5-6 weeks; swap usage by 3.5 months |
| 2022 | 2022-09-26 | BoE gilt intervention 09-28; US CPI miss 11-10; Fed step-down 12-14 `[memory]` | 2022-07-05 (stress was mild) | 2022-07-05 | 2022-09-26 | EMB 10-20 / EEM 10-24 | 2022-10-24 | 2022-11-02 | **gold = $ peak 09-26**; EM series bottomed 4 weeks AFTER the $ peak; OFR FSI 50% off by 2022-11-04 |
| 2023 SVB (mini) | 2023-03-15 (122.1) | 2023-03-12 BTFP; 03-19 daily swaps | 2023-03-23 peak only 0.41 | | 2023-02-24 | | | | custody −$52bn 03-22 then rebuild |

Pattern: the end is marked first by **(1) the policy announcement, (2) the funding-price spread halving within days of it (2008-10-17, 2020-05-07), (3) gold bottoming (always at or before the $ peak), (4) EMB/EEM bottoming, (5) the broad dollar peaking, (6) EM FX and custody holdings recovering last.** For an "all-clear" rule on free data: CP−bill back under its 1-year median AND gold above its 20-day high AND EMB above its 20-day high; the dollar peak confirms with a 0-4 month lag.

---

## 4. CURRENT READINGS (as of 2026-11-02; percentiles over each series' own full history / last 10y)

| Item | Reading | Date | 6m / 12m | Percentile (all / 10y) | Comment |
|---|---|---|---|---|---|
| Broad dollar `DTWEXBGS` | **121.32** | 2026-10-23 | +2.2% / +0.3% | 93 / 78 (90th since 2006) | 2026 range 117.4 (01-29) - 122.0 (10-14); ATH 130.04 2025-01-13; 2022 peak 128.45 |
| DXY (FMP `DX-Y.NYB`) | **101.59** | 2026-11-02 | +0.6% / +3.5% (Yahoo monthly) | 79 / 71 | **inside Johnson's 85-105 band, upper third** (3.4 pts below the ceiling) |
| EME dollar `DTWEXEMEGS` | 130.21 | 2026-10-23 | +1.5% / −1.2% | 89 / 77 | |
| AFE dollar `DTWEXAFEGS` | 114.30 | | +2.9% / +1.9% | 88 / 74 | the 2026 dollar bid is vs majors (JPY 156.9), not EM |
| BIS USD credit outside US | $15.13tn, +8.1% yoy | 2026Q2 | | record level; growth 70th-ish pct of 2001-26 (median yoy ≈ 7%) | EMEs $4.60tn +8.7% |
| BIS FX fwds+swaps+ccy swaps | $129.3tn (USD leg $113.5tn) | end-2025 | | record | vs $97tn mid-2022 |
| Fed swap-line usage `SWPT` | $156m | 2026-10-28 | | 54 / 47 | $207m peak 09-30 (quarter-end); effectively zero |
| Fin CP − bill | 0.05 pp | 2026-10-29 | | **5 / 14** | no funding premium |
| Nonfin CP − bill | 0.00 pp | 2026-10-13 | | 2 / 5 | |
| SOFR99 − SOFR | 0.08 pp | 2026-10-30 | | 7 / 7 | repo tails quiet |
| SOFR − IORB | **+0.05 pp** | 2026-10-30 | | **96 / 96** | SOFR 3.95 > IORB 3.90: reserves no longer abundant (QT end-state) — domestic, watch |
| OFR FSI total / funding / EM / safe | −2.12 / −0.15 / −0.50 / −0.29 | 2026-10-29 | | 35 / 48 / 14 / 15 (all) | all benign |
| EM corp OAS `BAMLEMCBPIOAS` | 1.81% (EM HY 3.88%, LatAm 2.65%) | 2026-10-30 | | n/a (3y history: 1.81 is near its 2023-26 low of ~1.6) | |
| EMB / EEM | $91.90 / $62.03 | 2026-11-02 | −3.8% / −3.3% 6m | 19 / 97 (all) | EMB soft (duration), EEM at highs |
| EM FX basket (8 ccy, up = weaker) | 231.1 | 2026-10-23 | +0.6% / −2.1% | 88 / 61 | stable; 2026 range 225.8-235.9 |
| EM reserves | CN $3.48tn (Jun), IN $636bn (Aug), BR $340bn, KR $435bn, MX $249bn, ID $134bn, TR $59bn (Sep) | | | | no sales visible |
| Policy rates | Fed 3.875 (target 3.75-4.00), ECB 2.50, BoJ 1.25, BoE 3.75, BR 13.75, MX 6.50, IN 5.25, KR 3.00, TR 37 | Sep-26 (BIS) | | | Fed−ECB +1.375, Fed−BoJ +2.6 |
| 2y: US / DE / JP | 4.61 / 3.03 / 1.94 | 2026-10-29 / 11-02 / 10-01 | | | US 2y 70 bp above the funds-rate ceiling: market prices hikes (oil) |
| Gold | $3,962.6 | 2026-11-02 | −14.1% / −0.4% | 93 / 88 | −27% from $5,418.5 (2026-01-28) — a gold drawdown with a flat dollar: not the 2008/2020 pattern (there gold fell WITH a dollar spike); here gold fell while the dollar fell from its 2025-01 ATH and oil doubled |
| Brent | $123.10 | 2026-10-27 | +8% / +88% | 99 / 99 | the live shock in the data |
| Foreign official custody | $2,568.6bn | 2026-10-28 | −5.9% / −6.6% | 34 / **0.4** | lowest since 2012; secular official selling/diversification, consistent with COFER USD share 56.7% |
| VIX / MOVE | 19.4 / 101.1 | 2026-10-30 / 11-02 | | 60 / 74 (10y) | |
| CHF | 0.8248 | | | **2.7** (strongest ever) | safe-haven bid is in CHF and gold-until-January, not USD |

One-line read: **the dollar is high-but-not-extreme (broad 93rd pct, DXY 101.6 inside the band) with zero dollar-funding stress on every free gauge; the stock of dollar debt is at a record and growing 8%, which Johnson's own framework calls re-dollarisation, i.e. the fuel is being added, not burned. The anomalies to watch are oil at $123, US 2y at 4.61 above the funds rate, SOFR above IORB, and foreign official custody at decade lows — a rates/oil shock, not a dollar-funding squeeze, is what the data currently describe.**

---

## 5. PANEL: 12 ranked series for a "dollar stress / crisis watch"

| # | Series | Endpoint | Freq / lag | History | Current | Lead label |
|---|---|---|---|---|---|---|
| 1 | Financial CP 3m − 3m bill | FRED `DCPF3M` − `DTB3` | D / 1d | 1997+ | 0.05 pp (5th pct) | LEADING (−87 to −139d in balance-sheet crises) |
| 2 | OFR FSI funding subindex (+ EM, safe-assets cols) | OFR `fsi.csv` (already loaded; expose the columns) | D / 1d | 2000+ | −0.15 | LEADING (alarm 2007-08-09, 2022-03-04) |
| 3 | Fed CB liquidity swaps | FRED `SWPT` (+ NY Fed ops CSV for per-counterparty detail) | W / 1d | 2002-12+ | $156m | announcement LEADS, usage LAGS; any reading > $10bn outside year-end = event |
| 4 | Chicago NFCI risk subindex | FRED `NFCIRISK` | W / 1w | 1971+ | −0.56 | LEADING (earliest 2007 alarm) |
| 5 | Broad dollar + EME/AFE split | FRED `DTWEXBGS`, `DTWEXEMEGS`, `DTWEXAFEGS` (splice `DTWEXB` pre-2006) | D / ~5d (H.10 weekly) | 1995+/2006+ | 121.3 / 130.2 / 114.3 | COINCIDENT; peak = end-marker |
| 6 | Gold | FMP `XAUUSD` (key in env) | D | 2007-12+ (page for older) | $3,963 | EARLY-COINCIDENT; trough leads $ peak by 0-111d |
| 7 | EM hard-ccy bonds EMB | FMP `EMB` | D | 2007-12+ | $91.90 | COINCIDENT (EMBI proxy) |
| 8 | EM FX basket (8 FRED pairs) | FRED `DEX*` | D / ~5d | 1995+ | 231.1 | COINCIDENT/LAG; trough marks the end |
| 9 | BIS USD credit to non-banks outside US (total, EME, loans, IDS, yoy) | BIS `WS_GLI` CSV (bulk zip or per-key) | Q / ~4 mo | 2000+ | $15.13tn +8.1% | SLOW STATE VARIABLE (the fuel); yoy < 0 only after spikes |
| 10 | SOFR tails: `SOFR99`−`SOFR`, `SOFR`−`IORB` | FRED | D / 1d | 2018+/2021+ | 0.08 / +0.05 | LEADING for domestic repo (2018-12, 2019-09, 2020-03) |
| 11 | Foreign official custody | FRED `WMTSECL1` (already loaded) | W / 1d | 2002-12+ | $2,569bn | LAG in crises; secular de-dollarisation gauge |
| 12 | Policy-rate differential | BIS `WS_CBPOL` (13 ccy) + FRED `DFEDTARU`/`ECBDFR` + 2y `DGS2`/Bundesbank/MOF | M / D | 2000+ | Fed−ECB +1.375; US−DE 2y +1.58 | DRIVER (slow) |

Bench: `BAMLEMCBPIOAS` & siblings (level only, 2023-11+), `VIXCLS`, `STLFSI4`, `KCFSI`, `COMPOUT`, `WLCFLL`, `TRESEG*` reserves (monthly), WB IDS (annual), IMF COFER (quarterly), BIS OTC FX swaps (semiannual), Korea exports `XTEXVA01KRM667S`, Brent.

### The 5 biggest gaps (paid-only or not machine-readable)
1. **Cross-currency basis (EURUSD/USDJPY 3m, 1y)** — the direct price of offshore dollars. Bloomberg/Refinitiv/ICAP only; nothing on FRED, ECB, BoJ, BIS, NY Fed. Proxy: CP−bill + OFR funding + swap-line draws (all three captured 2008/2020/2022 with 0-139d lead), but none sees a basis-only squeeze like 2011-12 (SWPT did: $109bn Feb-2012) or year-end turns.
2. **JPM EMBI spread / sovereign CDS** — EMB price (FMP) proxies level moves; FRED's ICE EM OAS history was truncated to 2023-11 (`BAMLEM*`, also `BAMLH0A0HYM2`, `BAMLC0A0CM`). The repo's `sources/ice_reference.py` splices frozen pre-truncation history ONLY for `BAMLH0A3HYC`, `BAMLC0A4CBBB`, `BAMLH0A0HYM2`, `BAMLC0A0CM` (files in `app/data/ice_reference/`); no EM series is frozen there, so EM OAS history before 2023-11 is unavailable free unless a frozen `BAMLEMCBPIOAS.csv` is reconstructed the same way (public mirrors, reconciled against FRED's live window).
3. **FRA-OIS / term-SOFR-OIS, FX-implied dollar rates** — CME/Bloomberg. No free daily. SOFR99−SOFR is the only free repo-tail series (2018+).
4. **Global PMI, China TSF/credit impulse, Baltic Dry, CPB world trade** — S&P Global paid; PBoC Chinese HTML only; BDI no free API (stooq JS-walled); CPB pages 404 today. Free growth proxies that worked: Korea exports (FRED, 2-mo lag), copper (monthly), Brent (daily).
5. **Real-time EM reserve sales / intervention** — IMF IFS via FRED lags 1-3 months; IRFCL SDMX works but is a 15 MB unfiltered pull. The weekly `WMTSECL1` custody series is the only fast free read, and it mixes reserve sales with diversification.

### Implementation notes for treasury-canary
- All FRED pulls fit `sources/fred_csv.py` unchanged. BIS: one GET of the bulk zip per week (105 KB) and pick rows by `(CURR_DENOM, BORROWERS_CTY, ..., UNIT_MEASURE)` — wide format, columns are quarters. BIS API v1 per-key CSV also works (`?format=csv`), ~1s.
- OFR FSI: the repo loads only the total; the Funding/EM/Safe-assets columns are in the same CSV.
- NY Fed ops CSV: rebuild outstanding = sum(Amount) over ops with settlement <= d < maturity; it matches `SWPT` at the 2020 peak ($448.9bn) but starts 2010-05 — keep SWPT as the long series.
- FMP: `historical-price-eod/light` caps at 5,000 rows; page with `from/to` for gold pre-2007.
- Yahoo `range=max` falls back to monthly for indices; use `range=10y&interval=1d` (MOVE OK).
- ICE truncation: `ice_reference.py` freezes only HY/IG/BBB/CCC; add `BAMLEMCBPIOAS` (and `BAMLEMHBHYCRPIOAS`) to `FROZEN_SERIES` with a reconstructed file, or show EM OAS as "level only since 2023-11".
- Stooq is blocked from this network (connection reset / JS challenge) — do not depend on it.
