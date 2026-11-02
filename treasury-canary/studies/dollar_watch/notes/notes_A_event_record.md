# Finder A — the historical event record, 1971-2026 (dollar as crisis predictor)

Built 2026-11-02. All files under `<scratch>/dxy/finderA/`.
Everything numeric below is re-derivable: `python3 -I scripts/build_series.py && python3 -I scripts/parse_rr.py && python3 -I scripts/crisis_metrics.py && python3 -I scripts/band_test.py && python3 -I scripts/chain_2022.py`.
The Johnson talk itself (Oct-2026) could not be located online (two searches); its five claims are taken as relayed by the caller and are labelled **UNVERIFIED as to source**. Johnson's own earlier public levels differ ("125, 135, 170 is when things break", Benzinga Aug-2024: https://benzinga.com/markets/cryptocurrency/24/08/40375042/dollar-milkshake-theory-is-still-in-play-and-could-benefit-bitcoin-says-santiago-capital-c).

## 0. Headline readings (as of 2026-11-02)

| Series | Latest | Source |
|---|---|---|
| ICE DXY close | **101.74** (2026-11-02); 6m **+3.3%** (from 98.47); 12m **+2.0%** (from 99.80) | Yahoo DX-Y.NYB daily: https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?period1=0&period2=1800000000&interval=1d |
| DXY 2025-26 path | 110.18 intraday high 2025-01-13 -> 95.55 low 2026-01-27 -> 102.58 closing high 2026-10-12 | same |
| Fed broad nominal (DTWEXBGS) | 121.32 (2026-10-23); monthly-avg series max 128.84 in 2025-01 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS |
| Fed advanced-economies (DTWEXAFEGS) | 114.30 (2026-10-23) | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXAFEGS |
| BIS broad NEER (64 economies) | 101.87 (2026-09); narrow (27) 105.87 | https://stats.bis.org/api/v1/data/WS_EER/M.N.B.US/all?format=csv |
| Gold (COMEX GC=F) | 3,968 (2026-11-02); 2026 high 5,586 (2026-01-29) -> low 3,879 (2026-10-30) = **-30.6%** | https://query1.finance.yahoo.com/v8/finance/chart/GC=F?period1=0&period2=1800000000&interval=1d |

DXY is inside every candidate band (85-105 / 90-110 / 83-102). Its 6m rise (+3.3%) is far below the 8% speed trigger.

## 1. Dollar data — what is free and what was built

Probe results (fetched 2026-11-02; raw copies in `raw/`):

| Source | Result | Span |
|---|---|---|
| FRED DTWEXM (Fed major currencies, daily, Mar-1973=100) | OK, discontinued | 1973-01-02..2019-12-31 |
| FRED TWEXMMTH (monthly avg of same) | OK | 1973-01..2019-12 |
| FRED DTWEXBGS / DTWEXAFEGS (broad / AFE, daily, Jan-2006=100) | OK | 2006-01-02..2026-10-23 |
| FRED DTWEXB (old broad, discontinued) | OK | 1995-01..2019-12 |
| Yahoo DX-Y.NYB `range=max&interval=1mo` | returns only **3-month bars from 1985** — unusable as spec'd | — |
| Yahoo DX-Y.NYB `period1=0&period2=1800000000&interval=1d` | **OK: 14,177 daily OHLC rows from 1971-01-04** (3,125 null weekend rows dropped). Pre-Mar-1973 values are a back-cast (index defined =100 in Mar-1973; Yahoo 1973-03 avg = 100.03, FRED DTWEXM 1973-03 = 100.0, so the two agree at the base) | 1971-01-04..2026-11-02 |
| Stooq dx.f / xauusd | **connection reset by proxy** (all attempts) — UNAVAILABLE here | — |
| BIS WS_EER M.N.N.US (narrow NEER) | OK | 1964-01..2026-09 |
| BIS WS_EER M.N.B.US (broad NEER) | OK | 1994-01..2026-09 |

Built `data/dollar_monthly.csv` (671 rows, 1971-01..2026-11) with columns: `dxy_close, dxy_avg, dxy_high(+date), dxy_low(+date)`, `fed_major_DTWEXM_avg/eom`, `fed_TWEXMMTH`, `fed_broad_DTWEXBGS_avg`, `fed_afe_DTWEXAFEGS_avg`, `fed_broad_old_DTWEXB_avg`, `bis_narrow_neer`, `bis_broad_neer`, `fed_major_spliced_afe`.
Splice: `fed_major_spliced_afe` = DTWEXM monthly avg to 2019-12, then DTWEXAFEGS multiplied by the 2019-12 ratio of the two monthly averages (computed in `build_series.py`). DXY itself needs no splice. Daily DXY in `data/dxy_daily.csv`.
Note the level gap: DXY 101.9 vs Fed broad 121.4 vs BIS broad 101.9 — different bases and baskets; the band claim is only meaningful on ICE DXY (57.6% EUR), which is what Johnson quotes.

## 2. Crisis table — `data/crises.csv` (26 rows, 25 crises + Plaza as reference non-crisis) and `data/crises_metrics.csv`

Dating sources: Federal Reserve History essays (federalreservehistory.org, all URLs probed 200), NBER cycle dates (https://www.nber.org/research/business-cycle-dating), ECB/BoE/BoJ/MoF/Fed/Treasury/FDIC/SNB press releases (URLs in the csv; all probed 200 except where marked), Reinhart-Rogoff "Global Crises Data by Country" (HBS BFFS, 70 countries, 1800-2016: https://www.hbs.edu/behavioral-finance-and-financial-stability/Documents/ChartData/MapCharts/20160923_global_crisis_data.xlsx — downloaded, parsed to `data/rr_country_year_flags.csv` and `data/rr_crisis_counts_by_year.csv`).
**Laeven-Valencia (IMF WP/18/206) could not be downloaded**: the dataset URL returns 404 and imf.org returns 403 to curl; a WebFetch of the paper's markdown returned only fragments (US 2007-11, UK 2007-11, Spain/Greece/Ireland/Iceland 2008-12, Cyprus 2011-15, Argentina 1980-82/1989/1995/2001, Korea 1997, Japan 1997, Turkey 2000; 151 crises 1970-2017). LV dates are therefore **UNVERIFIED** here; RR flags used instead for the EM/currency waves (RR: 1982 = 13 banking + 21 currency crises; 1994-95 = 24-27 banking; 1997 = 21 banking + 11 new currency crises; 2008 = 17 banking (13 new) + 22 currency (21 new)).
Johnson-relevant months are hand-dated with sources in the csv `date_notes` column. Two rows carry UNVERIFIED primary URLs (C02 1976 sterling/lira; C09 ERM — BoE and Riksbank history pages 404'd; dated from RR 1992 currency flags + public record).

Metrics basis: DXY **monthly close** ("eve" = close of the month before `start`); gold = World Bank Pink Sheet monthly average ($/toz; 1960-2025-12, https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx) extended by the datahub mirror of the same (2026-01..09; https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv; max 1.4% disagreement with WB where both exist) and by GC=F monthly avg for 2026-10/11; intra-month gold lows from GC=F daily (from 2000-09 only). S&P 500 from Yahoo ^GSPC daily as severity proxy.

| id | episode | start / peak / end | DXY eve | prior 6m / 12m | eve->peak-stress | episode DXY peak (month) | DXY peaked before end? | gold eve->trough (mo) | gold max DD in episode (daily where avail.) | gold eve->end | S&P max DD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | 1973-74 oil / equity bear | 1973-10 / 1974-10 / 1975-03 | 94.8 | -6.3 / -13.3 | **+6.8** | 105.9 (1974-01) | yes | -7.8 | -17.0 (monthly, 1974-04..07) | **+73** | -44 |
| C03 | Volcker double-dip | 1980-01 / 1982-11 / 1982-11 | 85.8 | -2.3 / -0.8 | **+41.0** | 124.8 (1982-10) | — | **-30.8** (1982-06) | -53.4 (1980-01..1982-06) | -8.8 | -27 |
| C04 | LatAm debt | 1982-08 / 1982-12 / 1983-12 | 119.1 | +10.2 / +6.6 | -1.4 | 131.8 (1983-12) | no | +7.5 | -22.3 (1983-02..11) | +14.6 | -8 |
| C06 | **Plaza (reference)** | 1985-09 / — / 1987-02 | 138.2 | -13.8 / -1.5 | -4.4 | 132.1 | — | -2.7 | -7.7 | +21 | -9 |
| C07 | 1987 crash | 1987-10 / 1987-10 / 1987-12 | 98.6 | +1.5 / -7.7 | **-5.0** | 93.7 (1987-10) | — | +1.1 | 0.0 | +5.6 | -32 |
| C08 | S&L / 1990 recession / Japan | 1989-08 / 1990-10 / 1991-03 | 97.4 | +0.6 / -0.1 | **-14.5** | 102.3 (1989-08) | yes | -6.1 | -15.5 | -3.1 | -20 |
| C09 | ERM | 1992-09 / 1992-09 / 1993-08 | 78.9 | -11.4 / -15.6 | +2.8 | 95.4 (1993-07) | yes | -4.1 | -4.8 | +10 | -5 |
| C10 | 1994 bonds / Mexico | 1994-02 / 1995-03 / 1995-06 | 95.6 | +0.2 / +3.4 | **-14.3** | 94.6 (1994-02) | yes | -2.6 | -3.8 | +0.2 | -9 |
| C11 | Asia | 1997-07 / 1997-12 / 1998-06 | 95.7 | +8.5 / +8.9 | +4.2 | 101.5 (1998-03) | yes | -15.3 (1997-12) | -15.3 | -14.2 | -11 |
| C12 | Russia / LTCM | 1998-08 / 1998-10 / 1998-12 | 101.2 | +0.4 / +1.6 | **-7.4** | 100.2 (1998-08) | yes | -3.0 | -3.0 | -0.4 | -19 |
| C13 | Dotcom / 2001 / Argentina | 2000-03 / 2002-10 / 2003-03 | 105.9 | +6.0 / +7.3 | +0.7 | 120.2 (2002-01; intraday 121.02 on 2001-07-06) | yes | -13.1 (2001-04) | -16.2 daily (2003); **-16.2% monthly 1999-10 310.7 -> 2001-04 260.5** | +13.6 | -49 |
| C14 | Subprime -> GFC | 2007-08 / 2008-10 / 2009-06 | 80.8 | -4.5 / -5.3 | +6.0 | 88.0 (2009-02; intraday 89.62 on 2009-03-04) | **yes** (S&P low 2009-03-09, NBER trough 2009-06) | 0.0 | **-32.9 daily (2008-03 -> 2008-10-24)** | **+42** | -57 |
| C15 | Euro sovereign | 2010-04 / 2011-11 / 2012-09 | 81.1 | +5.8 / -5.1 | -3.3 | 86.5 (2010-05) | yes | +3.2 | -20.2 daily (2011-09..12) | **+57** | -19 |
| C16 | Taper tantrum | 2013-05 / 2013-08 / 2013-09 | 81.7 | +2.3 / +3.7 | +0.4 | 83.4 (2013-05) | yes | -13.6 | -26.2 daily (2013-04..06-28) | -9.4 | -6 |
| C17 | Oil / Russia / China / Jan-2016 | 2014-06 / 2016-01 / 2016-02 | 80.4 | -0.4 / -3.6 | **+23.9** | 100.2 (2015-11) | yes | -16.5 (2015-12) | -22.1 daily | -6.9 | -14 |
| C18 | 2018 EM + Q4 | 2018-04 / 2018-12 / 2019-01 | 90.2 | -3.1 / -10.2 | +6.7 | 97.3 (2018-11) | yes | -9.5 | -14.9 daily | -2.5 | -20 |
| C19 | Repo Sep-2019 | 2019-09 / 2019-09 / 2019-10 | 98.9 | +2.9 / +4.0 | +0.5 | 99.4 (2019-09) | — | -0.4 | -9.6 daily | -0.4 | -4 |
| C20 | COVID | 2020-02 / 2020-03 / 2020-05 | 97.4 | -1.1 / +1.9 | +1.7 (monthly); **intraday 94.65 (03-09) -> 102.99 (03-20) = +8.8% in 9 sessions** | 99.1 (2020-03) | **yes** (DXY peak 03-20, S&P low 03-23) | +2.0 | **-14.7 daily (2020-03-09 -> 03-16)** | +9.9 | -34 |
| C21 | China property | 2021-09 / 2022-10 / 2023-10 | 92.6 | +1.9 / +0.5 | +20.4 | 112.1 (2022-09) | yes | -6.8 | -22.2 daily | +7.3 | -25 |
| C22 | 2022 (Fed / Russia / gilts / JGB) | 2022-01 / 2022-09 / 2022-10 | 95.7 | +3.5 / +6.4 | **+17.2** | 112.1 (2022-09; intraday 114.78 on 2022-09-28) | **yes** (S&P low 2022-10-12) | -7.0 | **-22.0 daily (2022-03 -> 2022-10-21)** | -7.0 | -25 |
| C23 | SVB / CS | 2023-03 / 2023-03 / 2023-05 | 104.9 | -3.5 / +8.4 | **-2.3** (105.66 on 03-08 -> 102.51 on 03-31) | 104.3 | no | +3.1 | -10.0 daily | +7.4 | -8 |
| C24 | Yen-carry Aug-2024 | 2024-07 / 2024-08 / 2024-08 | 105.9 | +4.5 / +2.9 | **-3.9** (104.10 on 07-31 -> 102.69 on 08-05) | 104.1 | — | +3.1 | -6.5 daily | +6.2 | -9 |
| C25 | Liberation Day | 2025-04 / 2025-04 / 2025-05 | 104.2 | +3.4 / -0.3 | **-4.5** (104.26 on 04-01 -> 97.92 low 04-21) | 99.5 | — | +7.9 | -15.4 daily (04-07) | +10.9 | -15 |
| C26 | Iran war / Hormuz (open) | 2026-02 / 2026-04 / — | 97.0 | -3.0 / -10.5 | +1.1 (97.61 on 02-27 -> 98.08 on 04-30) | 101.9 (2026-10) | — | -16.5 | **-30.6 daily (2026-01-29 -> 2026-10-30)** | -16.5 | -9 |

(Full numbers incl. C02, C05: `data/crises_metrics.csv`.)

**Claim 1 ("dollar rose in every crisis"): FALSE on a monthly-close basis.** DXY was higher at the peak-stress month than on the eve in 16 of 25 crises and lower in 9 (1982 LatAm, 1987, 1989-91, 1994-95 Mexico, 1998 LTCM, 2010-12 euro, 2023 SVB, 2024 yen, 2025 tariffs). It is true for the four episodes Johnson names (1998 only if you stop at August: DXY fell 8.9% 1998-08-28..10-08 as the yen carry unwound — the LTCM peak-stress month saw the dollar *fall*). "Faster rise = worse crisis": Spearman rank correlation between DXY eve->peak-stress % and S&P max drawdown depth = **+0.27 (n=25)**, weak; 1987 (-32% S&P, dollar -5%) and 1973-74 (-44%, dollar +7%) break it, 1980-82 (+41% dollar, -27% S&P) and 2014-16 (+24% dollar, -14% S&P) do not fit a monotone story.
**"Dollar peak = all-clear": supported for the 3 named cases** (DXY peaked 2009-03-04, 2020-03-20, 2022-09-28, each days-to-weeks before the equity low) and more broadly: in 20 of 22 datable episodes the DXY monthly peak came before the end month. But this is near-tautological — the peak is defined ex post, and "end" months are themselves dated by the turn in stress.

## 3. Band test — `data/band_excursions.csv`, `data/speed_events.csv`, `data/band_summary.csv`, `data/base_rates.csv` (script `scripts/band_test.py`)

Base rates from this crisis table (25 starts in 671 months): **P(a crisis starts within the next 12 months | random month) = 42%; within 24 months = 69%**; 48% of all months fall inside a crisis window. Any "X% of excursions were followed by a crisis" must be read against these.

| Test (monthly close) | n events | crisis start within 12m | within 24m | base 12m / 24m |
|---|---|---|---|---|
| Outside 85-105, raw runs | 25 | 11 (44%) | 19 (76%) | 42% / 69% |
| Outside 85-105, runs merged if gap <= 3m | **17** (closest to Johnson's "16") | 9 (53%) | 13 (76%) | 42% / 69% |
| Outside 85-105, merged gap <= 6m | 13 | 5 (38%) | 9 (69%) | 42% / 69% |
| Outside 90-110 | 24 | 7 (29%) | 15 (62%) | 42% / 69% |
| Outside 83-102 | 31 | 17 (55%) | 24 (77%) | 42% / 69% |
| 6m DXY rise >= 8% | 28 | 13 (46%) | 20 (71%) | 42% / 69% |
| 6m DXY rise >= 10% | 18 | 5 (28%) | 11 (61%) | 42% / 69% |
| 6m DXY rise >= 15% | 8 | **0 (0%)** | 5 (62%) | 42% / 69% |

**Result: no band variant beats the base rate by more than noise, and "76% within 24 months" is exactly the unconditional 24-month base rate (69%) plus one or two events.** Johnson's "75% ended in a dollar funding crisis" is numerically reproducible (13/17 = 76% on the merged count, 24m window) but carries no information once the base rate is known.
Reverse causality is visible in the data: **12 of 25 raw excursions (7 of 17 merged) began while a crisis was already under way**, and **10 of 18 >=10% six-month rises started inside a crisis window** (1974, 1981, 1982x2, 1992-93, 2000, 2008-09, 2010, 2014-15, 2022). The fast rises that started *outside* a crisis: 1984-09, 1985-02 (no crisis followed — Plaza), 1988-06/09 and 1989-05 (S&L/recession followed), 1991-05 (nothing within 12m), 1997-04 (Asia followed), 2005-06 (nothing). The dollar's big moves are mostly coincident with, not antecedent to, stress.
Long excursions dominate: above 105 for 59 straight months 1982-01..1986-11 (peak 160.41 on 1985-02-25) and below 85 for 50 months 2010-07..2014-08 (low 72.70 on 2011-05-04). The "band" is a 1990s-2020s artefact; before 1987 the DXY spent most of its life above 105.

## 4. Gold — `data/gold_monthly.csv`, `data/gold_daily.csv`

Free sources: FRED GOLDAMGBD228NLBM / GOLDPMGBD228NLBM **404 (removed)**; LBMA JSON 403; Nasdaq Data Link 403; Bundesbank BBEX3 keys 404; Macrotrends 403; Stooq reset. **Usable: World Bank Pink Sheet monthly (1960+), datahub mirror (updated monthly to 2026-09), Yahoo GC=F daily (2000-08-30+).** No free daily series pre-2000 was reachable, so 1971-1999 intra-month troughs are on monthly-average basis (understates drawdowns).
Johnson's numbers check (peak-to-trough inside the episode, daily GC=F): **dotcom** monthly 1999-10 $310.7 -> 2001-04 $260.5 = **-16.2%** (he says -18%: roughly right if measured from the Feb-2000 daily high); **GFC -32.9%** (Mar-2008 -> 2008-10-24; he says -30%: right); **2020 -14.7%** (2020-03-09 -> 03-16; he says -15%: right); **2022 -22.0%** (Mar-2022 -> 2022-10-21; he says -20%: right). Gold also fell -26% in the 2013 taper tantrum and -22% in 2014-15.
**But "gold falls in every crisis" is false on an eve-to-end basis**: gold finished the episode ABOVE its eve level in 1973-75 (+73%), 1982-83 (+15%), 1987 (+6%), 1992-93 (+10%), GFC (+42%), euro crisis (+57%), COVID (+10%), 2023 (+7%), 2024 (+6%), 2025 (+11%). Gold's intra-crisis dip is a liquidation-window phenomenon (weeks), reversed within the episode in most cases; 3 months after the DXY peak month gold was up in 15 of 24 cases (col `gold_3m_after_dxy_peak_pct`). The pre-2000 record contradicts the mechanism outright: in 1973-74 and 1987 gold rose while the dollar fell.
2026 is the outlier worth flagging: gold -30.6% from 2026-01-29 to 2026-10-30 while DXY rose only +6% (96.2 -> 102.6), during an oil-shock war — a gold crash with a mild dollar rally, not a dollar-funding squeeze on the DXY evidence. (GC=F front-month roll artefacts possible in single-day extremes; UNVERIFIED against LBMA.)

## 5. The 2022 chain — `data/chain_2022.csv` (script `scripts/chain_2022.py`)

| date | event | DXY close | % from freeze (2022-02-28, 96.71) | % from first hike (2022-03-16, 98.38) | source |
|---|---|---|---|---|---|
| 2022-01-03 | S&P peak | 96.24 | -0.5 | | market record |
| 2022-02-28 | OFAC Directive 4: CBR/NWF/MinFin transactions prohibited | 96.71 | 0 | | https://home.treasury.gov/news/press-releases/jy0612 |
| 2022-03-16 | first Fed hike | 98.38 | +1.7 | 0 | https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm |
| 2022-04-12 | Sri Lanka suspends external debt | 100.29 | +3.7 | +1.9 | https://eastmojo.com/news/2022/04/12/crisis-hit-sri-lanka-announces-debt-default/ |
| 2022-06-15 | Fed +75bp | 105.16 | +8.7 | +6.9 | Fed |
| 2022-07-21 | ECB TPI | 106.91 | +10.5 | +8.7 | https://www.ecb.europa.eu/press/pr/date/2022/html/ecb.pr220721~973e6e7273.en.html |
| 2022-08-28 | **six months after freeze** | 108.80 | **+12.5** | +10.6 | computed |
| 2022-09-22 | MoF yen intervention #1 | 111.35 | +15.1 | +13.2 | https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html |
| 2022-09-28 | BoE gilt operation; **DXY intraday high 114.78** | 112.60 | +16.4 (closing high 114.11 on 09-27 = +18.0) | +14.5 | https://www.bankofengland.co.uk/news/2022/september/bank-of-england-announces-gilt-market-operation |
| 2022-10-12 | S&P low | 113.32 | +17.2 | +15.2 | market record |
| 2022-10-21 | MoF intervention #2 | 112.01 | +15.8 | +13.9 | MoF |
| 2022-12-19 | Ghana suspends debt service | 104.72 | +8.3 | +6.4 | https://modeldiplomat.com/learn/glossary/ghana-default-2022 |
| 2022-12-20 | BoJ YCC widened | 103.97 | +7.5 | +5.7 | https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2022/k221220a.pdf |

Johnson's "+15% in six months": the DXY rose **+12.5% in the six months after the freeze** and **+18.0% to the Sept closing peak** (7 months). His 15% is in range if measured Feb-28 -> late Sept. **Evergrande**: Fitch RD on 2021-12-09 (https://www.fitchratings.com/research/corporates/fitch-downgrades-china-evergrande-to-rd-09-12-2021) — the China property crisis began 5+ months before the freeze; the freeze cannot have caused it (it may have deepened the 2022 leg).
Two readings, both consistent with the price data:
- *Johnson*: freezing a G20 central bank's reserves raised the precautionary demand for dollars/dollar assets (and for gold by non-aligned CBs), and the dollar's rise then broke the weakest fixed-income structures (LDI gilts, YCC, EM sovereigns).
- *Conventional*: the dollar rose +7.7% from 2021-06-01 to the freeze on Fed-hike expectations already; 2022's rise tracks the Fed path (hikes 03-16, 05-04, 06-15, 07-27, 09-21, 11-02, 12-14) and the European terms-of-trade shock from gas; the DXY **peaked within a week of the gilt crisis and then fell 10% into December while sanctions stayed in place**, which is what a rate-differential/safe-haven story predicts and what a reserve-freeze story does not. 2022's gilt/JGB stress was a *rates* shock to leveraged duration (LDI, YCC), not a dollar-funding shortage: the Fed's FX swap lines were essentially undrawn in 2022 (**UNVERIFIED here — would need the Fed's swap-line usage series**).
The data cannot separate the two: the freeze and the hiking cycle start 16 days apart. Sri Lanka (Apr-2022) and Ghana (Dec-2022) defaults are better dated to the commodity/food shock and pre-existing debt loads than to DXY level.

## 6. Counter-examples and the reverse-causality problem

- **1985-87**: DXY fell from 164.72 (1985-02-25) to ~100 by early 1987, -40%, with no crisis for 32 months. Then the **Oct-1987 crash occurred with the dollar FALLING** (98.64 on 10-02 -> 93.65 on 10-30 -> 85.42 on 12-31); the Louvre-accord dispute over the dollar's decline is the textbook trigger, not a dollar squeeze.
- **1994-95 Mexico**: DXY at 80.05 on 1995-04-19 — a then-record low vs JPY/DEM — at the peak of the peso crisis.
- **1998 LTCM**: DXY -8.9% from 1998-08-28 to 1998-10-08 as the yen carry trade unwound; the dollar *fell* in the acute phase.
- **2007-08 subprime onset**: DXY all-time low **70.70 on 2008-03-17** (Bear Stearns weekend). The dollar bottomed seven months into the crisis and only rose after Lehman — the rise was the crisis, not its herald.
- **2010-12 euro crisis**: DXY 72.70 on 2011-05-04; the Nov-2011 Italy-at-7% peak had DXY ~78-80. Euro-area sovereign stress is partly mechanical in the DXY (EUR = 57.6%), so a euro crisis *should* lift the DXY; it still sat at the bottom of Johnson's band.
- **2023 SVB/CS, Aug-2024 yen, Apr-2025 tariffs**: dollar fell during all three (105.66 -> 102.51; 104.10 -> 102.69; 104.26 -> 97.92). The 2025 case is a direct inversion: a US-originated shock in which the dollar lost safe-haven behaviour (Treasury selloff, 10y +50bp in the week of 7-Apr; https://www.fxempire.com/forecasts/article/us-dollar-forecast-dxy-drops-below-100-as-china-tariffs-and-yield-surge-undermine-safe-haven-appeal-1511381).
- **2001**: the dollar's 2000-02 peak (121.02 on 2001-07-06) was accompanied by a US manufacturing recession (NBER 2001-03..11) and Argentina/Turkey — but there was no dollar *funding* crisis; the strong dollar was a trade-competitiveness problem, with gold at a 20-year low.
- **Reverse causality**: 12/25 band excursions and 10/18 fast-rise events start inside a crisis window; the DXY's three "all-clear peaks" (2009-03, 2020-03, 2022-09) each came at or within days of the maximum in VIX/credit spreads — the dollar rises *because* a crisis is forcing deleveraging into USD cash, and it peaks when the forced selling stops. "Dollar up -> crisis" and "crisis -> dollar up" generate identical event tables; only lead-lag at daily frequency against a stress index (not done here) could separate them.
- **Claim 5 (falling dollar = re-dollarisation via USD credit creation)** is not testable with price data; it needs the BIS Global Liquidity Indicators (USD credit to non-bank borrowers outside the US, 2000+, free at stats.bis.org). Not fetched — see "not established".

## Five most decision-relevant facts
1. **The band has no edge over base rate**: outside 85-105 (17 merged excursions) -> crisis start within 12m 53% / 24m 76%, vs unconditional 42% / 69%. Johnson's "75%" reproduces and is uninformative.
2. **The dollar fell at peak stress in 9 of 25 crises** (1982, 1987, 1990, 1995, 1998, 2011, 2023, 2024, 2025); "every crisis" is false. The four he names are the ones where it held.
3. **Fast dollar rises are coincident with, not antecedent to, crises**: 10 of 18 >=10%/6m rises began inside a crisis window; the 8 >=15% rises were followed by zero crisis starts within 12 months.
4. **Gold's intra-crisis drawdowns are real and his numbers are right** (GFC -33%, 2020 -15%, 2022 -22%, dotcom -16%), but gold ended above its pre-crisis level in 10 of 25 episodes, and rose outright in 1973-74 and 1987 when the dollar fell. The 2026 gold crash (-31% from Jan-29) with only a +6% DXY is the live anomaly.
5. **2022**: DXY +12.5% in the 6 months after the reserve freeze, +18% to the 27-Sept closing peak; the China property crisis predates the freeze (Fitch RD 2021-12-09), and the DXY fell 10% Oct-Dec 2022 with sanctions intact — the hiking-cycle reading fits the path at least as well. Current DXY 101.74, +3.3% 6m — no trigger on any of his rules.

## Five things not established
1. **Laeven-Valencia dates** — dataset and PDF both blocked (404/403); only fragments via WebFetch. Crisis table rests on Fed History/NBER/central-bank releases + Reinhart-Rogoff (which ends 2016).
2. **The Johnson Oct-2026 talk itself** — not found online; the five claims and his band/counts are as relayed. His "16 excursions" could not be matched to a definition (I get 13/17/25 depending on run-merging).
3. **Pre-2000 daily gold** — every free daily source (FRED, LBMA, Bundesbank, Stooq, Nasdaq DL, Macrotrends) was 404/403/reset; 1971-1999 drawdowns are monthly-average and understated (e.g., 1980 Jan-21 intraday $850 not captured).
4. **Claim 5 (USD credit creation vs dollar level)** — needs BIS GLI; not fetched. Also Fed swap-line drawings per episode (to test "dollar funding crisis" vs "rates shock"), not fetched.
5. **2026 episode dating** — Iran war start 2026-02-28 and Brent peak ~$120-123 on 2026-04-30 come from secondary news aggregators (globalsecurity.org, cp24, businesstoday.in); no end date; the Stooq/LBMA cross-check of the 2026 gold path was unavailable.

## Files
- `data/dollar_monthly.csv`, `data/dxy_daily.csv` — dollar series (sources in §1)
- `data/gold_monthly.csv`, `data/gold_daily.csv`, `data/spx_daily.csv`
- `data/crises.csv` (hand-dated, sourced), `data/crises_metrics.csv`
- `data/band_excursions.csv`, `data/speed_events.csv`, `data/band_summary.csv`, `data/base_rates.csv`
- `data/chain_2022.csv`
- `data/rr_country_year_flags.csv`, `data/rr_crisis_counts_by_year.csv` (Reinhart-Rogoff 1970-2016)
- `scripts/build_series.py`, `scripts/parse_rr.py`, `scripts/crisis_metrics.py`, `scripts/band_test.py`, `scripts/chain_2022.py`
- `raw/` — every fetched file (FRED, BIS, Yahoo JSON, World Bank xlsx, datahub csv, RR xlsx; failed probes kept as evidence)
