# notes_A.md — Historical record of technology-led capex booms/busts (finder A)

Date: 2026-10-31. Lens: the HISTORICAL RECORD as measurable indicators. Hypothesis under test
(user): new tech -> over-investment -> capex throttled -> delayed ripple of over-valuation through
markets -> crash; recurs every boom; visible in stocks, rates/bonds, and in canary failures
(Global Crossing, WorldCom, Lehman) first.

Conventions. Every number has a URL. "FRED-calc" = computed by me from CSVs in raw/ with
`python3 -I calc_*.py` (scripts in this folder; outputs in computed_tables.txt). "KF-calc" = computed
from Ken French 48-industry value-weighted monthly returns (raw/ff/). UNVERIFIED = I could not
find a primary/secondary source in this pass; FROM-MEMORY = standard fact I know but did not
re-verify here. Nothing marked UNVERIFIED/FROM-MEMORY should be used in a published number.

Raw files: raw/fred_*.csv (FRED), raw/ff/48_Industry_Portfolios.csv + F-F_Research_Data_Factors.csv
(Ken French), raw/shiller_ie_data.xls (not parsed yet), raw/*.pdf + .txt (Richmond Fed 2003,
NY Fed McCarthy 2003, Greenwood-Shleifer-You NBER w23191, Jordà-Schularick-Taylor NBER w21486,
Dallas Fed Jan/Feb 2002, Cambridge Associates 2002, Ulmer NBER ch. c9500).

---------------------------------------------------------------------------------------------------
## 0. Bottom line (read this first)

1. In EVERY well-measured episode, SECTOR EQUITY PEAKED BEFORE (or coincident with) THE CAPEX PEAK,
   not after. Telecom: Nasdaq telecom index peaked 10-Mar-2000; BEA communications-equipment
   investment peaked Q4-2000 (real) / calendar 2000 (nominal), telecom structures Q4-1999. UK
   railways: shares peaked Aug-1845, capex peaked 1847. Japan: Nikkei peaked 29-Dec-1989, business
   investment peaked 1991. Shale: Oil-sector equity peaked Jun-2014, capex peaked FY2014. The
   user's causal order "capex throttle -> delayed market ripple" is reversed relative to the record:
   markets re-priced first and capex followed with a 2-24 month lag.
2. Credit spreads are LAGGING confirmers, not leading indicators. Baa-Aaa was at its cycle LOW
   (0.55pp) in Jan-2000, the equity peak month, and peaked (1.41pp) in Oct-2002, 31 months later.
   Same shape in 1929 (low Feb-1929, peak May-1932) and 2014-16 (low Jun-2014, peak Dec-2015).
3. "Canary" failures came 7-30 months AFTER the equity peak in telecom (Winstar +13m, Global
   Crossing +22m, WorldCom +28m), 1929 (Insull +31m), 1980s oil (Penn Square +20m), 2007-08
   (Lehman +11m). The only true LEADING canaries in the record are equipment-vendor guidance cuts
   (Lucent, 6-Jan-2000, two months before the Nasdaq peak). Exceptions where the canary WAS the
   crash trigger: Jay Cooke (18-Sep-1873), Philadelphia & Reading (20-Feb-1893).
4. Base rate (Greenwood-Shleifer-You, US 1926-2012): after a 100% two-year industry run-up net of
   market, P(>=40% drawdown within 2 yrs) = 53% (21/40); at 150% run-up, 80% (12/15); unconditional
   = 14%. Average 2-yr MARKET return in the 21 industry-crash cases: -42%. Recession followed the
   sector bust in telecom-2000, 1929, 1873, 1893, 1981-82 (oil), Japan-1991 (mild), 1973-74; NOT in
   shale-2014-16, PC-1984, China-2015. Credit-financed busts -> recession; equity-financed -> usually not
   (JST 2015).
5. n is small: 7-9 heterogeneous episodes; GSY's 40 US industry run-ups cluster into ~6 periods and
   are not independent.

---------------------------------------------------------------------------------------------------
## 1. EPISODE TABLE

Legend for "order of turn": Cg = capex-growth peak; Cl = capex-level peak; G = guidance cuts/vendor
warnings; Se = sector equity peak; Me = broad market peak; I = issuance peak; Sp = credit-spread
trough (low); F1 = first canary failure; X = broad crash phase; R = recession start (NBER or national).

### 1.1 UK Railway Mania, 1844-1850
- Tech: steam railways; 263 Acts authorising ~9,500 miles passed in 1846 (peak year of
  authorisations). https://www-users.cse.umn.edu/~odlyzko/doc/hallucinations.pdf (via search summary)
- Capex measure: railway expenditure ~6.7-7% of national income at the 1847 peak; 4.5% of GNP
  averaged over 1845-49. https://richardjohnbr.blogspot.com/2008/04/railways-construction.html ;
  https://songsfromtheageofsteam.uk/railways/railway-mania ; Robb chapter via
  https://www.cambridge.org/core/product/identifier/CBO9780511522789A009/type/BOOK_PART
- Run-up: share-price run-up dated 1-Jan-1844 to peak 9-Aug-1845 (Campbell & Turner).
  https://www.cambridge.org/core/product/7109FB424D9C7FC0317D5527AE000C88/core-reader
- Order: Se (Aug-1845) -> BoE rate rises late 1845 -> Cl (1847, ~2 yrs AFTER Se) -> credit crisis
  Oct-1847 (Bank Rate 8%, Bank Charter Act suspended; Consols 94 -> 79) -> trough Apr-1850.
  https://www.marxists.org/archive/hyndman/1892/crises/ch04.html ;
  https://en.wikipedia.org/wiki/Railway_Mania
- Peak-to-trough: railway share index 167.9 (summer 1845) -> 60.5 (end 1849) = -64% (Odlyzko).
  GFD transport index -57.3% Jul-1845 -> Apr-1850; GFD UK-100 -34% Jun-1845 -> Apr-1850.
  https://globalfinancialdata.com/finance-and-transports-in-britain-in-the-1800s-from-countercyclical-to-benchmark
- Lead times: Se -> capex peak +24m; Se -> credit crisis +26m; Se -> trough +56m.
- Recession: 1847-48 commercial crisis (not an NBER-style dating). Real-economy depth UNVERIFIED.
- Canaries: 1847 failures were corn merchants and provincial banks (Royal Bank of Liverpool, Oct-1847)
  FROM-MEMORY; George Hudson's accounting exposed 1849 FROM-MEMORY. Financing: equity with
  uncalled capital ("calls") — effectively leverage on shareholders; capital calls in 1846-47 forced
  liquidation of other assets (mechanism described in Odlyzko/Campbell; magnitudes UNVERIFIED).
- Scale: railway revenue GBP4.5m (1843) -> GBP6.2m (1845) vs GDP ~GBP500m; investors implicitly
  priced 1850 revenue of GBP30-50m. https://www-users.cse.umn.edu/~odlyzko/talks/gmu2008.pdf
- Contested: Campbell argues NOT a bubble on dividend/risk fundamentals.
  https://ideas.repec.org/p/pra/mprapa/21820.html

### 1.2 US Railroads I, 1866-1879 (Panic of 1873)
- Tech: transcontinental/land-grant railroads. 35,000 miles laid 1866-73.
  https://www.pbs.org/wgbh/americanexperience/features/grant-panic
- Capex measure: railroad gross capital formation = 20.1% of total US gross capital formation in
  1870-79 (Ulmer, NBER). https://www.nber.org/system/files/chapters/c9500/c9500.pdf
  Railroad bonds outstanding $416m (1867) -> $2.23bn (1874).
  https://www.library.hbs.edu/hc/crises/1873.html
- Order: I/Cl (1871-73) -> European liquidation (Vienna crash May-1873) -> F1 = Jay Cooke & Co.
  fails 18-Sep-1873 (Northern Pacific agent; could not place new bonds) -> X (NYSE closed 10 days
  FROM-MEMORY) -> R (NBER peak Oct-1873, trough Mar-1879, 65 months — standard NBER chronology,
  not re-fetched here: https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions).
- Failures: 55 railroads failed by Nov-1873, 60 more within a year; 89 of 364 railroads bankrupt;
  ~half in receivership by 1876. https://www.globalsecurity.org/military/world/usa/history/panic-of-1873.htm ;
  https://www.pbs.org/wgbh/americanexperience/features/grant-panic
- Peak-to-trough of railroad stock index: UNVERIFIED (NBER Macrohistory m11 series exists; not
  fetched). Canary distinguishing feature: construction financed by bonds sold ahead of traffic,
  banker carrying unsold inventory (Cooke covered >$5m with own bank funds).
  https://www.oupress.com/9780806144689/jay-cookes-gamble
- NOTE: here the canary failure WAS the crash trigger (lead ~0), unlike 2000-02.

### 1.3 US Railroads II, 1879-1897 (Panic of 1893)
- Capex: 100,000 miles added 1878-96; construction 4,700 miles (1892) -> 1,800 (1895); total
  176,804 miles in 1893. 1887 construction peak (~12-13k miles) UNVERIFIED.
  https://sites.pitt.edu/~zander/Research%20archive/Jaybird/Jaybird11.htm ;
  https://brewminate.com/silver-and-gold-bank-runs-and-the-economic-panic-of-1893/ ;
  https://en.wikipedia.org/wiki/Panic_of_1893
- Order: Cl (1887, UNVERIFIED) -> Baring crisis Nov-1890 (FROM-MEMORY) -> F1 = Philadelphia &
  Reading bankrupt 20-Feb-1893 -> gold-reserve run/NY panic May-Jun 1893 -> R (NBER Jan-1893 to
  Jun-1894, then Dec-1895 to Jun-1897 — standard chronology).
- Failures: 125 railroads into receivership Jun-1893 to Jun-1894; >192 by end-1894; 25,375 miles
  (~1/7 of US mileage) into receivership in 1893 alone; ~1/3 of US mileage through bankruptcy 1893-97.
  https://sites.pitt.edu/~zander/Research%20archive/Jaybird/Jaybird11.htm ;
  https://finhist.com/bank-runs/episodes/22427.html ; https://ebsco.com/research-starters/history/panic-1893
- Lead time Cl -> F1: ~6 years (long). Equity index peak-to-trough: UNVERIFIED.

### 1.4 Electrification / radio / utilities holding companies, 1922-1933
- Capex: public-utility construction (electric power + telephone + electric railway) $2.657bn (1923)
  -> $3.265bn (1929) -> $1.332bn (1932) -> $0.902bn (1933). Electric-only peak may be 1930 (~$919m,
  SEC 1947 speech, OCR-garbled, UNVERIFIED). https://www.nber.org/system/files/chapters/c5610/c5610.pdf ;
  https://sec.gov/news/speech/1947/071747mcentire.pdf
- Aggregate: gross private domestic investment 16.4% of GDP (1929) -> 3.1% (1932).
  https://fred.stlouisfed.org/data/A006RE1A156NBEA ; nonres fixed inv 11.1% (1929) -> 5.5% (1932)
  (FRED-calc, A008RE1A156NBEA).
- Equity: utilities 18% of NYSE cap Sep-1929; Dow Utilities 144 (1929) -> 17 (1934); RCA $490.65
  peak 3-Sep-1929 at P/E 41.6; Insull Utility Investments $30 -> $147 in first 8 months of 1929.
  https://www.fool.com/investing/general/2013/09/03/why-did-the-greatest-bull-market-in-history-last-s.aspx ;
  https://www.americanheritage.com/farthest-fall-0
- KF-calc (value-weighted total return): Util peak Sep-1929 -> May-1932, -81.1% (2-yr run-up to
  peak +195%); ElcEq peak Aug-1929 -> May-1932, -92.9% (run-up +235%); Trans (rails) Aug-1929 ->
  Jun-1932, -91.2%; market Aug-1929 -> Jun-1932, -83.7%.
- Rates/credit: Fed discount rate 3.5% -> 6% in four steps Jan-1928 to Aug-1929 (NY Fed to 6% on
  9-Aug-1929). https://www.federalreservehistory.org/essays/stock-market-crash-of-1929
  Baa-Aaa 1.00pp (Feb-1929, low) -> 5.64pp (May-1932, high) (FRED-calc, BAA/AAA).
- Order: Fed tightening (Jan-1928..Aug-1929) -> Se/Me (Aug-Sep 1929) -> R (NBER Aug-1929) -> X
  (Oct-1929) -> Cl electric 1929/30 (AFTER equity peak) -> spreads blow out 1931-32 -> F1 canary:
  Middle West Utilities receivership 14-Apr-1932, Insull Utility Investments 16-Apr-1932 (31 months
  after equity peak). https://law.justia.com/cases/federal/district-courts/FSupp/6/663/2264990/ ;
  https://www.britannica.com/money/Samuel-Insull
- Canary features: pyramided holding companies financed by stock sales of leveraged holdcos
  (circular ownership), Insull kept buying own stock through trusts after the crash.
- Contested: whether Fed tightening "caused" the crash. https://mises.org/online-book/economics-and-public-welfare/30-stock-market-crash-1929

### 1.5 Nifty Fifty / computing, 1968-1974 (optional; weak capex analogue)
- Equity: S&P 500 120.2 (11-Jan-1973) -> 62.3 (3-Oct-1974), -48%; Nifty Fifty avg P/E 41.9 vs S&P
  18.9 at end-1972; equal-weight NF basket ~-55% by Oct-1974; Polaroid -91%, Xerox -71%.
  https://www.foxbusiness.com/markets/history-of-bear-markets-since-1929 ;
  https://boyarresearch.substack.com/p/a-warning-from-1972-and-where-were ;
  https://realinvestmentadvice.com/are-the-magnificent-seven-in-a-bubble-ask-the-nifty-fifty/
- KF-calc: Drugs peak Jul-1973 -> Sep-1974, -48.2%; Util peak Nov-1972 -> Sep-1974, -42.6%; market
  Dec-1972 -> Sep-1974, -46.5%.
- Capex: nonres fixed investment only 12.1% of GDP in 1973 (FRED-calc) — NOT a capex boom; the bust
  was valuation + oil shock + inflation. Recession Nov-1973 to Mar-1975 (NBER, standard chronology).
- Siegel: NF returned 12.2%/yr Dec-1972 to Aug-1998 vs S&P 12.7% — a valuation episode that did
  not destroy long-run value. https://www.lgt.com/en/magnet/financial-markets/nifty-fifty-a-boom-in-growth-stocks/
- Verdict: include only as "equity-only bubble without capex boom" control.

### 1.6 US oil/gas drilling boom, 1979-1986 (added: cleanest debt-financed capex bust before telecom)
- Capex: US rig count all-time high 4,530 on 28-Dec-1981; -40% Dec-1981 to Jul-1982.
  https://worldoil.com/magazine/2019/july-2019/columns/the-last-barrel ;
  https://webarchive.library.unt.edu/eot2008/20090513013000/https:/www.fdic.gov/about/learn/learning/when/1980s.html
  US nonres fixed investment/GDP hit its POSTWAR MAXIMUM 15.4% in Q4-1981 (FRED-calc, A008RE1Q156NBEA)
  — the all-time-high capex share was the energy/structures boom, not 2000.
- Equity (KF-calc): Oil sector peak Nov-1980 -> Jul-1982, -48.9% (2-yr run-up +209%); market
  -16.3% same window. Oil price peak $36.95 Apr-1981.
  https://www.fdic.gov/resources/publications/history-eighties/volume-1/history-80s-volume-1-part2-09.pdf
- Order: Se (Nov-1980) -> oil price peak (Apr-1981) -> Cl (Dec-1981, +13m after Se) -> R (Jul-1981,
  NBER) -> F1 = Penn Square Bank 5-Jul-1982 (+20m after Se) -> Continental Illinois May-1984 (+42m)
  -> 425 Texas banks fail 1980-89 (peak 1988).
  https://stateimpact.npr.org/oklahoma/2012/07/05/penn-square-bank-anniversary-of-a-failure-that-changed-finance-forever
- Canary features: loan participations sold upstream (Penn Square -> Continental $1bn, Chase $212m);
  the failure chain ran 1982 -> 1984 -> 1988, i.e. canaries kept dying for 6 years after the peak.

### 1.7 Japan capex + asset bubble, 1986-1993
- Capex: business fixed investment ~20% of GDP in 1990 -> ~16% in 1998 (IMF/Ramaswamy); ~11pp above
  US in 1990. https://international.vlex.com/vid/japan-examines-causes-slump-business-52665665
  Investment the dominant factor in the 1986-91 boom and post-1991 bust (Kiyotaki-West).
  https://www.nber.org/chapters/c11031.pdf
- Rates: BoJ official discount rate 2.5% -> 6.0% in five steps May-1989 to 30-Aug-1990.
  https://en.wikipedia.org/wiki/Japanese_asset_price_bubble
- Equity (FRED-calc, NIKKEI225): peak 38,915.87 on 29-Dec-1989 -> 14,309 on 18-Aug-1992 (-63.2%)
  -> 7,608 on 28-Apr-2003 (-80.5%).
- Order: BoJ tightening (May-1989) -> Se/Me (Dec-1989) -> land prices peak 1990-91 -> business-cycle
  peak Feb-1991 -> Cl (1991, ~15m AFTER equity peak) -> slow deflation; first major financial failures
  1995-97 (jusen 1995; Sanyo Securities, Hokkaido Takushoku, Yamaichi Nov-1997) FROM-MEMORY.
  https://link.springer.com/chapter/10.1007/978-981-15-9598-1_3
- Key non-fit: NO credit-spread crash, NO canary within 5 years, bust via slow deflation. Equity
  -63% in 32 months but spread over a decade to -80%.
- Annual % changes in business investment 1991-94: UNVERIFIED (Cabinet Office SNA needed).

### 1.8 US telecom/fiber + dotcom, 1996-2003 — see Section 2 (full detail)
- Summary row: Tech = DWDM fiber (2.5 -> 100 Gbps/strand 1996-2000), Telecom Act 1996, Internet.
  Capex measure: BEA communications equipment $70.8bn (1996) -> $123.3bn (2000, 1.20% of GDP,
  16.1% of all equipment investment) -> $83.7bn (2002) (FRED-calc, C275RC1A027NBEA / GDP). Run-up
  4 years (1997-2000). Order: G (Lucent 6-Jan-2000) -> Se (10-Mar-2000) -> Me (Aug-2000 KF; S&P
  Mar/Sep-2000) -> Cl (Q4-2000 real) -> R (Mar-2001) -> F1 (ICG Nov-2000; Winstar Apr-2001) ->
  spreads peak Oct-2002 -> trough Sep/Oct-2002. Sector -72% (KF Telcm), Nasdaq -77.9%, market -45%.
  Recession followed with 12m lag from Se.

### 1.9 US shale, 2010-2016
- Capex: global upstream oil & gas investment peaked 2014 at $730-780bn -> $434bn in 2016 (-40 to -44%);
  US shale investment by 2016 < 1/3 of 2014 levels (IEA via OGJ).
  https://www.ogj.com/general-interest/article/17289664/iea-upstream-oil-and-gas-investment-continued-to-tumble-in-2016 ;
  https://www.mees.com/2016/9/16/oil-gas/middle-east-nocs-keep-spending-despite-global-upstream-capex-squeeze/e5dfdc60-4932-11e7-8d5d-17bb2a374939
  US E&P (S&P-rated) capex $239bn in 2014, -30% in 2015; EY top-50 US E&P capex $85.7bn in 2016,
  -57% vs 2014. https://www.naturalgasintel.com/?p=89533 ; https://www.naturalgasintel.com/?p=98944
- Prices/output: Brent $115 (Jun-2014) -> $29 (Jan-2016); US crude output peak 9.6 mb/d Jun-2015 ->
  8.55 mb/d mid-2016. https://www.haynesboone.com/news/articles/the-economist-energy-bankruptcy-report ;
  https://www.energyintel.com/0000017b-a7cf-de4c-a17b-e7cfcb6c0000
- Equity (KF-calc): Oil sector peak Jun-2014 -> Feb-2016, -40.3% (2-yr run-up only +51%); market
  Nov-2014 -> Feb-2016, -5.6%. Baa-Aaa 0.55pp (Jun-2014) -> 1.49pp (Dec-2015) (FRED-calc).
- Failures: 42 N. American E&P bankruptcies in 2015 ($17.2bn debt); 2016 was the peak year (one
  Bloomberg-cited count: 142 energy companies, $70.3bn debt — scope unclear). Fitch E&P HY trailing
  default rate 27% (May-2016), 29% (Jun-2016); energy sector 15%.
  https://www.haynesboone.com/news/articles/the-economist-energy-bankruptcy-report ;
  https://www.naturalgasintel.com/?p=92328 ; https://wolfstreet.com/2016/07/12/great-american-oil-bust-defaults-bankruptcies-e-p-sector-oilfield-services/
- Order: Se (Jun-2014) -> OPEC no-cut 27-Nov-2014 (FROM-MEMORY) -> Cl (FY2014) -> capex cuts 2015
  -> F1 (first E&P bankruptcies H1-2015: Quicksilver Mar-2015 FROM-MEMORY) -> spread peak Dec-2015/
  Feb-2016 -> equity trough Feb-2016. NO US recession; broad market -5.6%.
- Trigger was a SUPPLY/price shock, not monetary; debt-financed (HY) bust fully contained to sector.

### 1.10 China fixed-asset / property, 2009-2016 (capex-boom analogue)
- Capex: gross capital formation 46.3-47.3% of GDP in 2011-13 (World Bank; peak 2011 on GCF, 2013
  on GFCF at 44.5%); credit 130% -> 220% of GDP 2007-14.
  https://www.indexmundi.com/facts/china/gross-capital-formation ; https://uts.edu.au/node/383611 ;
  https://www.theneweconomy.com/?p=101392
  FAI growth 25.6%/yr 2003-11 -> 10.0% nominal in 2015 (NBS); property investment growth 19.8%
  (2013) -> 10.5% (2014) -> ~1% (2015).
  https://www.stats.gov.cn/english/PressRelease/201601/t20160119_1306487.html ;
  https://www.gulf-times.com/story/388733/china-realty-sector-loses-steam ;
  https://archive.shine.cn/business/China-2015-property-investment-slows/shdaily.shtml
- Equity: Shanghai Composite 5,166 (12-Jun-2015) -> -43% by 26-Aug-2015.
  https://dqydj.com/how-the-shanghai-composite-compares-to-the-nasdaq-bubble/ ;
  https://www.business-standard.com/article/news-cm/china-market-crashes-another-7-6-115082501480_1.html
- Failures: Kaisa first offshore developer default 2015; the real wave came 2021 (Evergrande, Dec-2021).
  https://www.scmp.com/business/china-business/article/3159082/china-evergrande-kaisa-group-restricted-default-after
- Order: Cl share (2011-13) -> growth slowdown 2014-15 -> Se/X (Jun-Aug 2015, a separate margin-
  driven equity bubble) -> managed deleveraging; GDP growth 7.4% (2014) -> 6.9% (2015); no recession,
  no spread crash; canary wave delayed 6-8 years by policy. Poor fit for the hypothesis.

---------------------------------------------------------------------------------------------------
## 2. TELECOM 1996-2003 in depth

### 2.1 Capex series (what, where)
| Series | Source | Values |
|---|---|---|
| Communications equipment, nominal, annual | FRED C275RC1A027NBEA (BEA Table 5.5.5) | 1996 70.8; 1997 80.0; 1998 87.1; 1999 98.7; 2000 123.3; 2001 109.1; 2002 83.7; 2003 82.2 ($bn). Share of GDP 0.88% (1996) -> 1.20% (2000) -> 0.77% (2002). Share of all equipment inv 12.5% -> 16.1% -> 12.7%. (FRED-calc) |
| Communications equipment, real quantity index | FRED B275RA3A086NBEA | 10.0 (1996) -> 20.7 (2000) -> 15.8 (2002); i.e. +107% real in 4 yrs, -24% in 2 yrs (FRED-calc) |
| Comm. equipment, real, quarterly (1996$) | Richmond Fed Fig.2 (BEA/Haver) | ~$62bn/yr Q1-1996 -> >$135bn Q4-2000 (~18%/yr); 7 straight negative y/y quarters; low <$93bn Q4-2001 = 69% of year-earlier; 7% of total private investment (2000) -> 4.8% (end-2002). https://www.richmondfed.org/-/media/RichmondFedOrg/publications/research/economic_quarterly/2003/fall/pdf/wolman.pdf |
| Telecom structures, real | same | flat ~$12bn through 1990s; +$9bn in 1999 to >$21bn in Q4-1999; ~$13bn end-2002. Structures peaked ~1 year BEFORE equipment. |
| Telephone-industry investment rate (I/K) | NY Fed McCarthy 2003, Chart 3 | 15-20% in 1980s-early 90s; ~33% in 2000 (highest since 1948); industry contributed ~1/2 of total investment growth in 2000 with <10% share; >1/4 of aggregate investment decline in 2001. https://resources.newyorkfed.org/medialibrary/media/research/economists/mccarthy/investmentboom_jun03.pdf |
| N. American wireline carrier capex | RHK via Lightwave | ~$92bn (2000) -> ~$66-77bn (2001) -> $46-53bn (2002). https://www.lightwaveonline.com/business/article/16653883/north-american-telecom-capex-to-turn-up-in-2004-says-rhk |
| Capex/revenue, worldwide carriers | In-Stat/MDR | 31% of revenue (2000 peak) -> 20% (2002). https://www.lightwaveonline.com/business/article/16657070/service-provider-capex-spending-remains-cautious-says-instatmdr |
| Nonfin. corporate capex (all sectors) | FRED BOGZ1FA105050005Q (Fed Z.1) | peak Q2-2000 $1,184bn SAAR -> Q4-2001 $949bn (-20%) (FRED-calc) |
| PNFI/GDP (all sectors) | FRED PNFI, GDP | peak 14.73% Q3-2000 -> 11.93% Q1-2003 (FRED-calc) |

Other series worth pulling (not fetched): FCC ARMIS carrier capex; BEA Table 5.5.5U quarterly
(communication equipment) via https://db.nomics.world/BEA/NIUnderlyingDetail-U50505 ; Doms (FRBSF
2004) https://www.frbsf.org/wp-content/uploads/er19-34bk.pdf (model-based overinvestment estimate).

### 2.2 Contribution to GDP: boom and the 2001 subtraction
- FRED A008RY2Q224SBEA (contribution of nonresidential fixed investment to real GDP growth, pp SAAR):
  1999 avg +1.13; 2000 avg +1.18 (Q1 +2.07, Q2 +1.84, Q3 +0.62, Q4 +0.20); 2001 avg -0.99 (Q1 -0.56,
  Q2 -1.20, Q3 -0.66, Q4 -1.56); 2002 avg -0.66. Gross private domestic investment incl. inventories
  (A006RY2Q224SBEA): 2001 avg -2.15pp. (FRED-calc)
- NY Fed Table 1 (E&S growth Q4/Q4 and contributions, pp): E&S 1998 14.9 / 1999 9.7 / 2000 5.2 /
  2001 -8.8 / 2002 3.3; communications equipment contribution 1.9 / 1.6 / 2.9 / -3.9 / 0.2. In 2000
  comm equipment = "well over one-half of investment growth" with 12% share; in 2001 "nearly 4pp drag".
- BEA WP2002-2: declining contributions of IP equipment & software accounted for ~2/5 of the fall in
  trend real GDP growth 2000:II-2001:III. https://www.bea.gov/system/files/papers/WP2002-2.pdf
- Real GDP growth slipped to 0.8% in H1-2001 (NY Fed Current Issues 10-6).
  https://www.newyorkfed.org/medialibrary/media/research/current_issues/ci10-6.pdf
- Mechanical arithmetic: comm equipment fell $123.3bn -> $109.1bn (2001) -> $83.7bn (2002) nominal =
  -0.14pp and -0.24pp of GDP directly, before multipliers; the whole nonres FI swing was ~ -2.2pp of
  GDP-growth contribution between 2000 and 2001 (FRED-calc).

### 2.3 Vendor financing (equipment makers lending to customers)
- Committed vendor financing per SEC filings: Lucent ~$7bn (down from $7.7bn prior quarter), Cisco
  $2.5bn, Nortel $2.1bn, Alcatel $1.5bn. https://www.lightreading.com/cable-technology/vendor-financing
- Nortel: credit commitments $4.1bn (end-2000) -> $2.8bn (Mar-2001) per CEO; filings show $5.2bn
  (2000) -> $2.1bn (2001). https://itworldcanada.com/?p=24821 ; https://www.eweek.com/news/vendor-financing-backfires/
- Lucent wrote off $1.1bn on vendor-financing deals (incl. One.Tel). Winstar sued Lucent for $10bn
  over a $2bn vendor-financing deal. https://www.eweek.com/news/vendor-financing-backfires/
- Cisco offered $1.1bn of $2bn available (Apr-2001). same
- McKinsey "Caveat Vendor": nine largest equipment makers, GBP18bn outstanding vendor finance.
  https://www.information-age.com/?p=23403
- Circular revenue: IRU capacity swaps. Global Crossing booked $720m cash revenue from the sale side
  of swaps in H1-2001; swaps ~20% of GX Q2-2001 revenue; Qwest deleted $950m of swap revenue
  (2000-01). https://www.gpo.gov/fdsys/pkg/CHRG-107hhrg81961/html/CHRG-107hhrg81961.htm ;
  https://radsoft.net/news/roundups/fg/irus.html ; https://www.theregister.co.uk/2002/09/24/qwest_deletes_950m_of_hollow/
- Nortel Q2-2001 loss $19.4bn; JDS Uniphase FY2001 write-down $50.6bn (Cambridge Associates).

### 2.4 Issuance and debt
- $192bn of high-yield debt issued by telecom and cable 1997-2000 (Cambridge Associates 2002, p.12).
  https://publishedresearch.cambridgeassociates.com/wp-content/uploads/2015/01/Telecom-Investing-2002.pdf
- "Record $1.3 trillion in debt raised over the past five years" (FT via Cambridge Associates).
- WSJ (via Springer 2004): telecom borrowed ~$1.5tn from banks and issued $630bn bonds 1996-2001
  (SECONDHAND). https://www.springerprofessional.de/en/cellular-3g-broadband-and-wifi/14746178
- Telecom = 15% of HY dollar volume 1996; 18% H1-1997; CLECs = 33% of 1997 issuance (Bear Stearns).
  https://www.rcrwireless.com/?p=52577
- Media+telecom ~35% of HY index at end-2000; ~40-50% of HY issuance in the years before.
  https://www.etftrends.com/2015/08/why-this-is-not-2002-or-2009/
- Networking IPOs: 15 ($1.3bn) 1998; 52 ($5.9bn) 1999; 34 ($5.1bn) 2000; VC into telecom H1-2000
  $7.55bn vs H1-2001 $2.8bn (Cambridge Associates). CLEC market cap $3bn (1996) -> $86bn (1999)
  -> $32.1bn (Feb-2001) -> $3.77bn (Feb-2002) (Richmond Fed).
- Z.1 nonfinancial corporate net debt issuance (BOGZ1FA104104005Q): $240-480bn/qtr SAAR through
  2000 -> $90bn Q1-2001 -> negative by Q2-2002 (FRED-calc).
- Defaults: 2001 HY defaults $78.2bn (Fitch record); default rate 12.9% vs 5.9% ex-telecom & fallen
  angels; telecom 13.3% (2000) and 25.8% (2001) of corporate default dollar volume (Moody's/FDIC);
  Jan-Sep 2002 defaults $83.1bn with 57% telecom (Altman). https://www.ogj.com/home/article/17247453/energy-defaults-contributed-to-record-2001-agencies-say ;
  https://www.fdic.gov/bank/analytical/bank-trends/bt0205.pdf ; https://archive.nyu.edu/bitstream/2451/26494/2/02-50.pdf
- Year-by-year telecom HY issuance 1996-2000 in $: NOT FOUND in a free source (needs Moody's/
  Bear Stearns annual or SDC). UNVERIFIED gap.

### 2.5 Sequence of failures vs Nasdaq peak (10-Mar-2000) and recession (Mar-2001)
| Date | Event | Months after Nasdaq peak |
|---|---|---|
| 6-Jan-2000 | Lucent warns FQ1 EPS 36-39c vs 54c consensus; stock -28% ($72.38 -> $52), record NYSE volume. https://money.cnn.com/2000/01/07/companies/lucent/index.htm | -2 |
| 10-Mar-2000 | Nasdaq Composite 5,048.62; Nasdaq Telecom 1,230.06 | 0 |
| Jul-2000 | 8th Circuit adverse UNE-pricing ruling (Richmond Fed) | +4 |
| Q3-2000 | PNFI/GDP peak 14.73% (FRED-calc) | +6 |
| Oct-2000 | Lucent 3rd/4th warning of year; CEO out 23-Oct-2000. https://money.cnn.com/2000/10/23/technology/lucent/index.htm | +7 |
| 14-Nov-2000 | ICG Communications Ch.11 (first large CLEC). https://www.sec.gov/Archives/edgar/data/786343/000102140801503681/d10k.txt | +8 |
| Q4-2000 | Real comm-equipment investment peak (Richmond Fed) | +9 |
| 16-Jan-2001 | NorthPoint Ch.11 | +10 |
| 15/16-Feb-2001 | Nortel guidance cut (Q1 loss). https://www.theglobeandmail.com/report-on-business/nortel-posts-loss-slashes-jobs/article25437663 | +11 |
| Mar-2001 | NBER recession start; telecom employment peak 1.59m | +12 |
| 18-Apr-2001 | Winstar Ch.11 (~$5bn assets), sues Lucent $10bn. https://www.homemediamagazine.com/news/winstar-files-bankruptcy-1080 | +13 |
| 21-May-2001 | Teligent Ch.11 | +14 |
| 31-May/1-Jun-2001 | PSINet Ch.11 ($4.3bn liabilities vs $2.2bn assets). https://money.cnn.com/2001/06/01/technology/psinet/index.htm | +15 |
| Jun-2001 | Nortel $19bn quarterly loss (Richmond Fed); 360networks Ch.11 28-Jun-2001 | +15 |
| Nov-2001 | NBER recession trough | +20 |
| 28-Jan-2002 | Global Crossing Ch.11 ($22.4bn assets; debt ~$12.4bn UNVERIFIED). https://www.benzinga.com/node/19369738 | +22 |
| 21-Jul-2002 | WorldCom Ch.11 ($107bn assets; $3.8bn improper accounting). https://money.cnn.com/2002/07/19/news/worldcom_bankruptcy/ | +28 |
| Sep/Oct-2002 | Telcm (KF) and Nasdaq trough (1,114.11 on 9-Oct-2002, -77.9%); Baa-Aaa peak 1.41pp Oct-2002 | +31 |
Lead/lag summary: G -> Se = -2m; Se -> Cl(real) = +9m; Se -> R = +12m; Se -> F1 = +8m (ICG) /
+13m (Winstar); Se -> spread peak = +31m; Se -> market trough = +30m. Recession ENDED (Nov-2001)
before the two famous canaries (GX, WCOM) failed.

### 2.6 Equity measures
- Nasdaq Telecom 198 (Apr-1997) -> 1,230 (Mar-2000), ~+84%/yr; -62% by end-2000; 136 by 16-May-2003
  (Richmond Fed). S&P communications-equipment index -86% Mar-2000 to Sep-2001 (-$793bn); S&P
  long-distance -65%; S&P comm services -43% (Dallas Fed). https://www.dallasfed.org/~/media/documents/research/swe/2002/swe0201c.pdf
- Worldwide telecom market cap $6.3tn (Mar-2000) -> -$3.8tn by Sep-2001 (FT via Cambridge Assoc.).
  S&P telecom market-cap loss 2000-02 ~$700bn, >3.5% of all US corporate equity at the 2000 peak
  (Richmond Fed).
- KF-calc Telcm VW index (Mar-2000=100): Jun-00 85.8, Dec-00 59.8, Mar-01 58.2, Sep-01 51.2, Mar-02
  45.6, Sep-02 28.0 (trough, -72%). Market (Mkt-RF+RF): peak Aug-2000, trough Sep-2002, -45%.
  Telecom led the market peak by 5 months and fell ~1.6x as far.
- Chips (KF) peak Mar-2000 -> Sep-2002, -83.9% (2-yr run-up +228%); Comps peak Aug-2000, -83.9%.

### 2.7 What the data said IN REAL TIME at the capex peak (2000)
- Known/knowable in 2000: Lucent's Jan-2000 miss (customer "buying patterns"); telecom corporate
  profits negative for 2000 even as market cap peaked (Richmond Fed Fig.4); CLEC market share of
  local telephony <8% in 2000 despite $86bn cap; "old guard" share of long-haul fiber 72% (1996) ->
  30% (1999) with annual fiber deployment up >4x (Richmond Fed); Internet traffic "doubling every
  100 days" claim (WorldCom) vs Odlyzko's ~100%/yr; vendor-financing balances rising (Lucent $7.7bn).
- Not visible until 2001: fiber glut press (Feb-2001 Network World "pain phase for fiber barons,
  600,000 miles of new inter-city fiber on the way"); lit-fiber utilization figures (Dallas Fed cites
  "below 3 percent in April 2001, down from 15 percent in 1988" for the backbone — extraction context
  truncated; verify wording before use).
- Credit market did NOT warn: Baa-Aaa at cycle low (0.55pp) Jan-2000; HY issuance still heavy
  through 2000 (telecom+media 35% of HY index at end-2000).
- Fed was TIGHTENING into the peak: fed funds 4.76% (Jun-1999) -> 6.54% (Jul-2000), then 1.82% by
  Dec-2001 (FRED-calc, FEDFUNDS).

---------------------------------------------------------------------------------------------------
## 3. FREE DATA to rebuild the episodes as time series

| Series | ID / location | Span, freq |
|---|---|---|
| Comm. equipment investment, nominal | FRED C275RC1A027NBEA (BEA 5.5.5 line) | 1929-2025, annual |
| Comm. equipment, real qty index | FRED B275RA3A086NBEA | 1929-2025, annual |
| Comm. equipment quarterly | BEA Table 5.5.5U via https://db.nomics.world/BEA/NIUnderlyingDetail-U50505 | quarterly |
| Nonres fixed investment ($) | FRED PNFI | 1947-, quarterly |
| Nonres FI share of GDP | FRED A008RE1Q156NBEA (q), A008RE1A156NBEA (a, 1929-) | |
| Contribution of nonres FI to real GDP growth | FRED A008RY2Q224SBEA; equipment Y033RY2Q224SBEA; GPDI A006RY2Q224SBEA | 1947-, quarterly |
| GPDI share of GDP | FRED A006RE1A156NBEA | 1929-, annual |
| Z.1 nonfin. corporate capex | FRED BOGZ1FA105050005Q | 1946-, quarterly |
| Z.1 NFCB debt (securities+loans) net issuance | FRED BOGZ1FA104104005Q | 1946-, quarterly |
| Z.1 NFCB net equity issuance | FRED id BOGZ1FA103164103Q returned HTML (not found) — use Fed Z.1 table F.103 directly https://www.federalreserve.gov/releases/z1/ | quarterly |
| Moody's Baa, Aaa yields | FRED BAA, AAA | 1919-, monthly |
| HY OAS | FRED BAMLH0A0HYM2 (CSV via fredgraph returns only last ~3 yrs; full 1996- on site) | daily |
| Fed funds, 10y | FRED FEDFUNDS (1954-), GS10 (1953-) | monthly |
| NBER recession indicator | FRED USREC | 1854-, monthly |
| NBER business-cycle dates | https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions | 1854- |
| Nasdaq Composite | FRED NASDAQCOM | 1971-, daily |
| Nikkei 225 | FRED NIKKEI225 | 1965-, daily |
| Sector equity returns | Ken French 48 industry portfolios https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/48_Industry_Portfolios_CSV.zip (Telcm, Util, Oil, Chips, Comps, Trans, ElcEq) + F-F_Research_Data_Factors_CSV.zip | 1926-07 to 2026-09, monthly (daily variant exists) |
| S&P composite, earnings, CAPE, long rate | Shiller http://www.econ.yale.edu/~shiller/data/ie_data.xls (saved raw/, parse with xlrd) | 1871-, monthly |
| Pre-1926 US stock/bond/rail series | NBER Macrohistory https://www.nber.org/research/data/nber-macrohistory-database (series m11xxx: rail stock prices, bond yields, construction) | 1857-, monthly |
| 17-country investment/GDP, credit, equity & house prices, rates | Jordà-Schularick-Taylor https://www.macrohistory.net/database/ (release 6, 1870-2020, annual, "iy" = investment/GDP, "tloans", "eq_tr") | 1870-, annual |
| Railroad capital formation 1870-1950 | Ulmer NBER https://www.nber.org/system/files/chapters/c9500/c9500.pdf (tables; railroad GCF = 20.1% of US GCF in 1870s) | annual |
| 1920s utility construction | NBER chapter https://www.nber.org/system/files/chapters/c5610/c5610.pdf ; FRED A0266AUSA398NNBR (private commercial/industrial/utility construction), PRPWRCON (power construction, modern) | annual |
| UK railway mania share index | Campbell-Turner index (MPRA 21820 https://mpra.ub.uni-muenchen.de/21820/ ; data by request); Odlyzko papers | weekly/monthly 1843-50 |
| HY issuance by sector | SIFMA US corporate bond issuance https://www.sifma.org/research/statistics/ (total only, 1996-); sector split requires Moody's/Altman NYU papers https://archive.nyu.edu/handle/2451/26494 | annual |
| Energy bankruptcies 2015- | Haynes & Boone Oil Patch Bankruptcy Monitor https://www.haynesboone.com/ | monthly |
| China GFCF/GDP, FAI | World Bank NE.GDI.FTOT.ZS; NBS press releases https://www.stats.gov.cn/english/PressRelease/ | annual/monthly |
| Japan business investment share | Cabinet Office SNA (not fetched); IMF Survey (Ramaswamy) for 20%->16% 1990-98 | annual |

---------------------------------------------------------------------------------------------------
## 4. WHERE THE HYPOTHESIS DOES NOT MATCH THE RECORD

A. Capex peaked AFTER the equity peak (so "capex throttle -> delayed market ripple" is the wrong order):
   - UK railways: shares Aug-1845, capex 1847 (+2 yrs).
   - Japan: Nikkei Dec-1989, business investment 1991 (+1-1.5 yrs), BoJ still hiking to Aug-1990.
   - Telecom: Nasdaq telecom Mar-2000, real comm-equipment Q4-2000 (+9m); nominal annual peak 2000.
     Structures peaked Q4-1999 (-3m) — the only sub-series that led.
   - 1920s: equity Aug/Sep-1929, utility construction 1929 (coincident) or electric 1930 (+1 yr).
   - Shale: Oil equity Jun-2014, capex FY2014 (roughly coincident), cuts 2015.
   - Oil 1980s: Oil equity Nov-1980, rig count Dec-1981 (+13m).
   What DID lead the equity peak in telecom: equipment-vendor guidance (Lucent Jan-2000), telecom
   structures investment (Q4-1999), telecom corporate profits (declining from 1996, negative in 2000).

B. Credit spreads lag by 2-3 years in every episode measured (1929-32, 2000-02, 2014-16). They are
   useless as a warning and good as a bottom-confirmer.

C. Canaries are mid-bust casualties, not early warnings (telecom +8..+28m; Insull +31m; Penn Square
   +20m; Lehman +11m). Only in 1873 and 1893 was the first big failure the crash trigger itself.
   WorldCom failed 8 months AFTER the recession ended.

D. Equity-financed booms that ended without a credit crash or recession:
   - PC boom 1983-84: Comps sector -18% (Jun-1983 -> Jun-1984), Chips -24%, market flat, no recession
     (KF-calc).
   - Internet pure-plays 1998-2000: 6% of total US market cap at Feb-2000 (Ofek-Richardson), IPO/
     lockup-driven, essentially no debt; the recession came from the DEBT-financed telecom/capex leg.
     https://www.nber.org/papers/w8630
   - JST (17 countries, 1870-2012): equity-only bubbles preceded 13 financial-crisis recessions and 34
     NORMAL recessions; post-WW2 the equity-bubble dummy is not a significant predictor of a financial-
     crisis recession; credit growth is what makes a bubble dangerous. https://www.nber.org/papers/w21486.pdf
   - GSY: 19 of 40 US 100%-run-ups did NOT crash within 2 yrs and gained +46% over the next 2 yrs
     (e.g., Software 1978, Healthcare 1980, Industrial Mining 2005).

E. Slow deflation rather than crash: Japan (-63% over 32m, -80% over 13 yrs, no spread blow-out, no
   bank failure until 1995-97); UK railways (56 months to trough); China 2015 (equity -43% in 10 weeks
   but capex glide-path and canaries deferred to 2021 by policy).

F. Monetary tightening preceded most peaks and is the better-fitting proximate trigger:
   Fed +175bp Jun-1999..May-2000; BoJ +350bp May-1989..Aug-1990; Fed 3.5%->6% Jan-1928..Aug-1929;
   BoE hikes late-1845 and 8% Bank Rate Oct-1847. Exceptions: shale (supply/price shock) and 1873
   (European liquidation after Vienna crash).

G. Sector size matters more than "every boom": comm equipment was 1.2% of GDP at peak; total nonres
   FI 14.7%. The 1981 energy/structures boom (15.4% of GDP, postwar record) produced a bank-failure
   wave lasting 7 years but the equity market fell only 16%.

H. n: UK-1845, US-1873, US-1893, US-1929, JP-1989, US-2000, US-2014, plus optional US-1973, US-1981,
   CN-2013 = 7-10 episodes; heterogeneous in financing (equity calls / bonds / bank loans / HY /
   policy credit), monetary regime (gold standard vs fiat), and sector size. GSY's 40 run-ups cluster
   into ~6 calendar episodes (1928-29, 1936-37, 1967-68, 1972, 1980, 1999-2000, 2007-08). Treat any
   base rate as having effective n < 10.

---------------------------------------------------------------------------------------------------
## 5. BASE RATES

Definition X: two-year value-weighted industry return >= X% both raw and net of market (GSY).
Definition Y: >= 40% drawdown from any point within the next 2 years. Z = 2 years.
Source: Greenwood, Shleifer, You, "Bubbles for Fama", JFE 2019 / NBER w23191 Table 3.
https://www.nber.org/system/files/working_papers/w23191/w23191.pdf

| Run-up X (2-yr, net of mkt) | US 1926-2012: run-ups / crashes / P(crash) / avg drawdown of crashes | Intl 1987-2012 |
|---|---|---|
| 50% | 168 / 34 / 20% / -53% | 237 / 85 / 36% |
| 75% | 77 / 28 / 36% / -54% | 153 / 64 / 42% |
| 100% | 40 / 21 / 53% / -60% | 107 / 53 / 50% |
| 125% | 21 / 16 / 76% / -60% | 74 / 39 / 53% |
| 150% | 15 / 12 / 80% / -62% | 51 / 34 / 67% |
| Unconditional | 14% (1928-2013), 11% post-1970 | 24% |
- Timing: in the 21 US crash cases prices peaked on average 6 months after first identification,
  +30% to the peak; crash begins ~5 months after identification. Average 2-yr raw MARKET return in
  those 21 cases: -42% (so industry crashes of this size coincide with broad bear markets).
- Predictors that discriminate crash vs no-crash: rising volatility, share issuance (% issuers 34% vs
  22%), "acceleration", new-vs-old-firm return tilt, higher market CAPE (25.5 vs 19.1). Sales growth
  does NOT discriminate.
- Applied to KF-calc run-ups: Telcm +68% (would NOT have triggered GSY's 100% screen — the telecom
  crash was in a sector whose own 2-yr run-up was modest; Chips +228% and Comps +297% did trigger),
  Util-1929 +195%, ElcEq-1929 +235%, Oil-1980 +209%, Oil-2014 +51%.

Recession base rate given a sector capex bust (my tally, NOT from a paper; UNVERIFIED as a statistic):
- Episodes with a measurable sector capex bust (>=30% real decline in the sector's investment within
  2 yrs): UK-1847, US-1873, US-1893, US-1929/30, US-1981/82, JP-1991, US-2000/01, US-2014/16, CN-2015.
  Recession within 24 months of the sector equity peak: 7 of 9 (all but shale and China). With DEBT
  financing + monetary tightening: 6 of 6. Equity/retained-earnings financed or policy-managed: 1 of 3.
- JST 2015 (Table 3): of 46 financial-crisis recessions, 31 had a preceding equity and/or housing
  bubble; of 120 normal recessions, 50 did. Equity bubbles (n=98) average amplitude 28%, duration
  ~2 yrs; housing 15%, ~3 yrs.
- Magnitude: in GSY crash cases average sector drawdown -60%; broad market -42%. Observed broad-market
  drawdowns in the capex-bust episodes: 1929-32 -84%, 2000-02 -45% (KF) / Nasdaq -78%, 1973-74 -46%,
  1980-82 -16%, 2014-16 -6%, Japan -63%, UK-100 1845-50 -34%.

---------------------------------------------------------------------------------------------------
## 6. Five most decision-relevant facts
1. Sector equity peaked BEFORE capex in every measured episode (lead 0-24 months); capex is a
   lagging indicator of the bust, not a leading one. Watch vendor guidance and sector profits instead.
2. Credit spreads bottomed AT the equity peak (Baa-Aaa 0.55pp Jan-2000; 1.00pp Feb-1929; 0.55pp
   Jun-2014) and peaked 18-36 months later. They confirm, they do not warn.
3. GSY base rate: P(>=40% sector crash within 2 yrs | 100% 2-yr run-up) = 53%; 80% at 150%;
   unconditional 14%. Telecom's own 2-yr run-up (+68%) was below the screen; chips/computers (+228%/
   +297%) were well above.
4. Recession followed within 24 months in 7 of 9 capex busts, and in 6 of 6 where the boom was
   DEBT-financed and the central bank had tightened into the peak; the two misses (shale, China) were
   contained by sector size / policy. In telecom, nonres FI subtracted ~1pp/yr from GDP growth in 2001
   (-2.2pp swing vs 2000) with comm equipment alone a -3.9pp drag on equipment growth.
5. The famous canaries failed 13-28 months after the peak and after the recession had ended (WorldCom).
   Canary failure dates are useful for dating the bottom (GX Jan-2002, WCOM Jul-2002 vs trough Oct-2002),
   not the top. The only canary that led was a vendor (Lucent, -2 months).

## 7. Five most important things NOT established
1. Year-by-year telecom HY issuance 1996-2000 in dollars (only $192bn 1997-2000 total and share
   figures found); and the primary source for the $1.3tn / $1.5tn+$630bn debt totals.
2. Capex-level series for the 19th-century episodes (UK railway capex by year in GBP; US railroad
   capital formation by year 1868-1876 and 1885-1895) and their equity indices — Ulmer tables and
   NBER Macrohistory m11 series exist but were not parsed; 1887 construction peak unverified.
3. Japan annual business-investment changes 1991-94 and the exact capex peak quarter (Cabinet Office
   SNA); dates of first Japanese financial failures (from memory only).
4. Global Crossing's debt at filing ($12.4bn), the 2016 full-year energy HY default rate, the Dallas
   Fed fiber-utilization quote context, and electric-only utility capex peak year (1929 vs 1930).
5. A defensible recession base rate conditioned on capex-boom MAGNITUDE (e.g., sector capex/GDP rising
   >X pp in N years) — no paper found; my 7-of-9 tally is hand-built on heterogeneous episodes with
   n<10 and should be labelled as such in any downstream artifact.
