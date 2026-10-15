# AI-trade debt flows — research record

Casey's question (2026-10-15): track the debt the AI trade raises (chips, memory,
hyperscalers, neoclouds, data centres, power, the SPV/private-credit channel), by
rating tranche; who buys it (sovereigns, institutions); and whether sovereigns such
as Japan are buying it instead of Treasuries, pushing UST yields up — and what a
reversal would look like. Decisions so far: full chain, not hyperscalers only; a
tab of its own on treasury-canary. Casey has FMP (equities fundamentals, 13F,
Treasury curve — no bond issuance, ratings or holder data; probed 2026-10-15).

Status: SCOPING PASS ONLY — nothing is pre-registered, built or graded. The memo
below is the synthesis of five finders and five adversarial verifiers (one per
finder; finder C's tally was NOT_PASS and is shown corrected). Data behind it:
`ai_debt_flows/data/` (deals.csv with the two verifier re-inclusions applied;
TIC, BoJ, MOF, Z.1, ACM, MSPD, FRED spread files as fetched 2026-10-13..15).
Charts: `ai_debt_flows/figs/fig_aidebt_{tally,japan,breaking}.png`
(`ai_debt_flows/scoping_charts.py`). The finders' and verifiers' full notes
live in the session scratchpad and are not committed.

Chart note: the rating chart's 2025 "not captured" row is $10.5bn — the memo's
$8.5bn plus the re-included CoreWeave $2.0bn the verifier left unbucketed — so
both 2025 bars sum to $242.8bn.

---

# AI-trade debt flows — scoping memo (rev 1, pre-build)

Date 2026-10-15. Inputs: five finders (A issuance data, B holders/flows, C deal tally, D substitution hypothesis, E breaking indicators) and five adversarial verifiers. Only numbers a verifier marked CONFIRMED or CORRECTED appear as fact (corrected value used); UNVERIFIABLE items are labelled. Source tags in [brackets] resolve to URLs in section 9. Finder and verifier notes: session scratchpad (not committed).

## 1. Verdict

1. **Measurable now, free, same-day, tranche level**: every SEC-registered AI-trade bond (size, coupon, maturity, spread, expected rating, currency, ISIN) from EDGAR FWP term sheets; 144A deals of SEC registrants from 8-K EX-99 press releases; rating = agency rating printed at pricing. A primary-document tally of **$682.5bn** (2024 $39.7bn / 2025 $242.8bn / 2026 YTD $400.0bn, 67% traced to fetched filings) already exists and is rebuildable by script [EDGAR-SUB][FWP-NVDA].
2. **Measurable now, free, aggregate only**: who holds US corporates by sector (Fed Z.1, quarterly, ~70-day lag); foreign net buying of US corporates vs Treasuries by ~150 countries (TIC, monthly, ~7-week lag, custody-biased); Japan's purchases of US sovereign vs non-sovereign debt (BOJ, monthly, 2014→) and by Japanese investor type (MOF, weekly/monthly); UST net supply (MSPD), term premium, auction indirect share, OAS by rating (3-year history only), CCC stress, BDC price/NAV.
3. **Not measurable free at any frequency**: who bought a *specific* AI bond, by country or investor type (no free source; allocations are syndicate-reported and surface only in paid trade press); daily single-name CDS; swap spreads; CUSIP-level TRACE prices; full-history ICE OAS; private borrowers (xAI, Crusoe, Vantage) and bank/insurer loan books; rating migration faster than 12-24 months.
4. **Paid unlocks**: Bloomberg NIM/HDS, LSEG (IFR + eMAXX) or Dealogic → deal-level allocation and 144A completeness; S&P GMI / ICE DS → single-name CDS; ICE Data Indices → full OAS history and sector sub-indices; EPFR → fund flows by country; PitchBook LCD → private credit. **Free-registration unlocks**: SIFMA monthly IG/HY xls, FINRA Public API (monthly TRACE volume by grade), NBIM holdings via Snowflake, DART key.
5. **Hypothesis read so far**: the data refute the simple Japan story and are silent on the issuer-level one. Japan sold JPY 5.47trn of US sovereign LT debt Jan-Aug 2026 and bought only JPY 0.43trn of US non-sovereign [BOJ-BP]; its TIC corporate-bond holdings fell. All foreigners did rotate (corp +$282bn vs LT Treasuries +$174bn, Jan-Jul 2026 [FRED-TIC-GT-CORP]) but TIC cannot attribute that to AI issuers; the one published event study finds no significant crowding-out footprint [PIMCO-0921]; the 2026 10y rise is ~all expected short rates, not term premium [ACM].

## 2. Feasibility matrix

| Casey asked for | Free source | Granularity | Frequency / lag | History | Verified? | Paid alternative |
|---|---|---|---|---|---|---|
| Issuance by issuer | EDGAR submissions JSON + FWP/424B term sheets [EDGAR-SUB]; 8-K EX-99 + EFTS `"senior notes"` for registrants' 144A [CRWV-EX99]; issuer PRs / HKEX for non-US (SoftBank, Tencent) [SBG-PR][HKEX-TCEH] | Tranche (size, coupon, maturity, spread, CUSIP/ISIN, bookrunners, currency) | Same day (minutes via Atom feed); 10 req/s, User-Agent mandatory | FWP regime 2005→; tally 2024→ | A1, C1 CONFIRMED; 4 deals re-parsed to the dollar | Bloomberg NIM, Dealogic, LSEG DCM for non-registrant 144A and loans |
| By rating tranche | Expected ratings printed on FWPs (Meta, Oracle, Nvidia all carry them); agency new-issue press releases for 144A; 17g-7(b) XBRL history for backfill [17g7] | Deal/tranche, rating at pricing | Same day at pricing; 17g-7(b) lagged 12/24 months by rule | 17g-7(b) from 2012-06-15 | A1, A4 CONFIRMED; C6 CORRECTED (rating captured from a fetched doc for 52.6% of tally dollars) | Agency feeds; Bloomberg for migration |
| Total inflows by source (holder type) | Fed Z.1 F3.5.t / L.213 net purchases by holder sector incl. Rest of World [Z1-F35t]; FRED SAAR mirrors [FRED-FA893]; TIC issuer-type cut (non-financial / financial / ABS, official vs private) [TIC-CSLT] | Sector x instrument; no issuer, industry or rating | Quarterly, ~70 days (2026Q2 out 2026-09-11; next 2026-12-10) | 1945Q4 | A5, A6, B8 CONFIRMED/CORRECTED | eMAXX (institution x security), N-PORT is free but funds only |
| Buyer country attribution | TIC CSLT: holdings, net purchases, valuation change by ~150 countries x {Treasuries, agency, corporate, equity} [TIC-CSLT]; SHL annual survey (NAICS industry at world level only) [SHL2025] | Country x asset class; custody-centre residence | Monthly, ~7 weeks | Positions 1984-12, flows 1985-01 | B1, B2, D1 CONFIRMED (negative claim survived attack) | Bloomberg HDS, eMAXX; none covers sovereign reserve managers |
| Sovereign-vs-Treasury substitution | Japan only: BOJ BoP "Sovereign (LT)" vs "LT debt" to USA → corporate residual [BOJ-BP][MOF-SOV]; MOF flows by investor type [MOF-B3]; TIC Japan corp vs Treasuries incl. and excl. bills; GPIF/AP3 annual issuer lists [GPIF][AP3]; IMF PIP Japan x US x holder sector (verifier find, untested by finder) [IMF-PIP] | Country x instrument (Japan); issuer level only in annual fund lists | Monthly (BOJ/MOF ~6 weeks; MOF weekly 1 week); annual (GPIF) | BOJ 2014-01; MOF 2005-01 | B3, B12, D3-D6 CONFIRMED/CORRECTED | Deal allocation stats (IFR/Bloomberg); nothing covers Gulf SWFs or China SAFE |
| Reversal / breaking signals | FRED ICE OAS by rating (3y only), CCC-B gap, IG/HY yields; BAA10Y long history; Fed EBP; OFR FSI; ACM/KW term premium; TreasuryDirect auction stats; MOVE (Yahoo, cross-checked); BDC P/NAV (Yahoo + 8-K NAV); Boerse Frankfurt bond quotes by ISIN [FRED-CCC][ACM][TD-BOND][BF-ORCL] | Index / auction / ticker / ISIN | Daily, T+1; Frankfurt intraday, no backfill | OAS 2023-10-16 only; BAA10Y 1986; ACM 1961 | E1-E5, E11-E12, E16 CONFIRMED/CORRECTED | S&P GMI / ICE DS (CDS), TRACE EOD, ICE Data Indices, Bloomberg swap spreads and composites |

## 3. First look (verified numbers)

### 3a. AI-trade debt tally by bucket x year ($bn, USD at FRED FX on trade date; corrected per verifier C) [C-DEALS]

| Bucket | 2024 | 2025 | 2026 YTD | Note |
|---|---|---|---|---|
| Hyperscaler straight bonds (Meta, Alphabet, Amazon, Oracle) | 16.8 | 108.4 | 217.5 | 2026 incl. $54.7bn non-USD legs (EUR/GBP/CAD/JPY); Microsoft issued nothing 2024-26 [EDGAR-SUB]; matches JPM AM $17bn/$109bn [JPMAM] |
| Chips / memory (Nvidia, Broadcom, AMD, Intel, Micron) | 13.6 | 18.2 | 40.8 | Only Nvidia's $25bn is clearly AI-growth funding; Broadcom $28.5bn is VMware refi; Micron net negative after $5.4bn tender |
| Neocloud / miner (CoreWeave, Nebius, IREN, TeraWulf, Cipher, Applied Digital) | 8.0 | 21.5 | 49.5 | +~$18.5bn missed 8-K deals not yet in file: Hut 8 $7.5bn [8K-HUT8-1][8K-HUT8-2], Galaxy $4.8bn [8K-GLXY-1][8K-GLXY-2], Core Scientific $5.4bn [8K-CORZ], Cipher Stingray $0.81bn [8K-CIFR-STING]; CoreWeave alone $43.8bn |
| AI lab (SpaceX $25bn) | 0 | 5.0 | 25.0 | SpaceX tranches/ratings UNVERIFIABLE (press only) |
| Data-center ABS / landlord | 1.4 | 9.3 | 9.3 | Deal-level ABS lists are paid; KBRA PRs free [KBRA] |
| Power | 0 | 5.6 | 17.1 | Mostly acquisition debt |
| Off-balance-sheet SPV / project | 0 | 74.7 | 40.9 | Hyperion $27.3bn (terms press-only, no filing; Meta 10-Q RVG ~$28bn corroborates size [10Q-META]), Sopaipilla $12.3bn (launched, pricing never sourced), Oracle/Vantage $38bn bank loans (press [SF-ORCLVTG]), Abilene $9.4bn UNVERIFIABLE, Valor $3.5bn, SoftBank $11.1bn HY [SBG-PR] |
| **Total** | **39.7** | **242.8** | **400.0** | **$682.5bn**; ~$701bn after the missed miner deals |

Verification mix: 67.2% of dollars traced to a fetched primary filing, 12.3% fetched press, 20.4% search snippet only [C-TOTALS].

### 3b. By rating at issue x year ($bn, S&P letter at pricing; corrected) [C-TOTALS]

| Rating | 2024 | 2025 | 2026 YTD | Total |
|---|---|---|---|---|
| AAA | 0 | 0 | 0 | 0 |
| AA | 10.5 | 82.7 | 217.5 | 310.6 |
| A | 2.5 | 33.8 | 30.1 | 66.4 |
| BBB | 17.9 | 43.3 | 70.6 | 131.9 |
| BB | 0 | 5.9 | 26.3 | 32.2 |
| Unrated / private | 8.0 | 62.4 | 26.7 | 97.2 |
| ABS/CMBS tranched | 0.8 | 4.2 | 2.7 | 7.7 |
| Rating not captured | 0 | 8.5 | 26.0 | 34.5 |

2025 rating rows sum to $240.8bn: the re-included CoreWeave $2.0bn 9.25% 2030 [8K-CRWV-2505] was not re-bucketed by the verifier. Rating captured from a fetched document for 52.6% of dollars (58% once the three mis-flagged FWPs are fixed).

### 3c. AI share of total issuance

| Measure | 2024 | 2025 | 2026 YTD | Source |
|---|---|---|---|---|
| SIFMA US corporate issuance ($bn) | 1,972.7 | 2,218.6 (+12.5%) | 2,195.1 through Sep (+24.5% Y/Y); H1 1,522.8 = +28.1% vs H1-25 (the "+12.5%" printed beside YTD is the FY figure) | [SIFMA-PDF][SIFMA-PAGE] |
| Hyperscaler USD legs / SIFMA | 0.85% | 4.2% | 7.2% | C10 CONFIRMED; all-currency "9.5%" dropped (non-USD legs over a US-only denominator) |
| IG / HY split | gated xls | gated xls | 2Q26 IG 75.2% / HY 14.3% of $732.6bn → IG ~$551bn, HY ~$105bn (verifier-derived from pie x total) | [SIFMA-PDF]; annual IG/HY dollars UNVERIFIABLE until the HubSpot form [SIFMA-FORM] is submitted |
| Z.1 nonfinancial corporate net bond issuance ($mn SAAR) | — | 2025Q2 -47,532; Q3 417,732; Q4 217,488 | 2026Q1 483,688; Q2 327,000 | [FRED-FA103]; FRED "FU" codes are un-annualised (2026Q2 299,829 vs FA 1,351,916, ratio 4.5x) — never mix [FRED-FU893] |
| External cross-checks | — | hyperscalers >$100bn (BIS) | hyperscalers ~10% of global IG issuance from <1% in 2024 [IMF-GFSR]; ~7% of US IG index [BARCLAYS-PB]; AI borrowers "nearly a quarter" of nonfinancial USD IG supply YTD [PIMCO-0928] | definitions differ ~3x across sell-side tallies ($194bn to $570bn) |

### 3d. TIC and BOJ: Japan and total foreign, Treasuries vs corporates ($bn; LT = excl. bills)

| Series | 2024 | 2025 | 2026 Jan-Jul | Level Jul-26 (Dec-25) | Source |
|---|---|---|---|---|---|
| Japan net purchases, LT Treasuries | -45.0 | +65.0 | -11.5 | 1,023.8 (1,046.3) | [FRED-TIC-JP-TSY][FRED-TIC-JP-TSYPOS] |
| Japan net purchases, Treasuries incl. bills | n/a | +95.5 | -70.5 (12m to Jul: -48.6) | — | [TIC-CSLT] (CORRECTED: LT-only hides the bill selling) |
| Japan net purchases, corporate bonds | +13.1 | +13.2 | +8.4 | 312.5 (320.9); 164.2 Dec-15 | [FRED-TIC-JP-CORP][FRED-TIC-JP-CORPPOS] |
| Grand Total net, LT Treasuries | +490.4 | +428.4 | +174.0 | 7,783.3 | [FRED-TIC-GT-CORP] |
| Grand Total net, corporate bonds | +304.5 | +392.3 | +282.2 (12m: +452.0) | 5,272.8 (corp share of LT 40.4% vs 37.2% Dec-15) | [FRED-TIC-GT-CORPPOS] |
| All Countries net, Treasuries incl. bills | — | +577.3 | +187.2 (12m: +291.8) | — | [TIC-CSLT] |
| Foreign official net, corporate bonds | +40.4 | +43.2 | +41.1 | 316.0 = 6.0% of foreign-held corporates; SHL Jun-25: 5.2% | [FRED-TIC-OFF][SHL2025] |
| Foreign official, LT Treasuries | — | — | net +21.6; valuation ≈ -92 | 3,418.8 (3,489.1) | [FRED-TIC-OFFPOS] |
| Non-official net, 12m to Jul-26 | — | — | corp +392.3 vs LT Tsy +263.4 | 4,956.8 corp | [FRED-TIC-NONOFF] |
| BOJ: Japan residents' net purchases of US LT debt (JPY trn) | +16.12 total / +13.45 sovereign / +2.67 other | +10.53 / +7.57 / +2.95 | Jan-Aug: -5.03 / -5.47 / +0.43 | — | [BOJ-BP]; sovereign = govt + agency + local govt [MOF-SOV] |
| MOF: Japanese net purchases of foreign LT debt by investor (JPY trn, 12m to Sep-26) | — | — | all -5.09; banks -12.83; life insurers -2.11; trust accounts (pensions) +12.23; investment trusts -1.50 | — | [MOF-B3] |

Other countries, 2026 Jan-Jul (Treasuries / corporates, $bn): UK +126.4 / +32.9; China -48.0 / 0; Ireland +1.8 / +29.1; Norway +4.3 / +15.8; Korea -23.2 / +5.3 [FRED-TIC-UK]. Largest holders of US corporates are custody and fund centres (Luxembourg 811.2, Belgium 704.5, Cayman 548.5, UK 544.9, Ireland 341.5) ahead of Japan 312.5, Canada 270.8, Taiwan 201.3; China holds 15.2 of corporates vs 578.3 of Treasuries [TIC-CSLT].

### 3e. AI issuance vs net Treasury issuance

| Ratio | Value | Basis | Source |
|---|---|---|---|
| Tally / net marketable UST | 2025: $240.8bn / $1,991bn = 12.1%; FY2026: $389.9bn / $2,120bn = 18.4% | finder tally (corrected tally nudges both up ~0.5pp); MSPD change in marketable outstanding (gross of Fed) | [MSPD] |
| Hyperscaler bonds / net marketable UST, 2026 | 13-19% gross all-currency (JPM $279bn / MS $400bn forecasts vs ~$2,085bn run-rate); ~10-14% USD-only; ~15-22% of net coupon issuance USD-only (21-30% all-currency); 2025: 5.5-6.1% | CORRECTED: numerator is gross and ~28% non-USD, denominator is net — state the basis | [MSPD][JPMAM] |
| Duration-supply view | ~1/8 of Treasury duration supply (up to $360bn 10y-equivalents on $300bn) | Dallas Fed | [DALLAS] |
| UST supply detail | CY2025 +$1,991bn (coupons +1,631, bills +360); 2026 Jan-Sep +$1,564bn (coupons +993, bills +571); outstanding $31.835tn; privately-held net borrowing Apr-Jun-26 $190bn actual, Jul-Sep est $739bn, Oct-Dec est $628bn | | [MSPD][TSY-SB0584] |

### 3f. Issuer level: what the public funds and ETFs show

- **GPIF** (ISIN level, 2026-03-31, 10,040 lines, JPY 72.82trn foreign bonds): Oracle JPY 11.06bn (53 lines), Amazon 8.60bn, Alphabet 6.41bn, Meta 4.11bn, Broadcom 3.66bn, Microsoft 1.75bn, Blue Owl Technology Finance 0.90bn, CoreWeave 0.14bn, Nvidia 0.11bn; six hyperscalers + Nvidia = JPY 32.0bn = 0.044% of the book vs US Treasuries JPY 36.84trn = 50.6% [GPIF]. Passive, government-benchmarked: not the marginal corporate buyer.
- **AP3** (Dec-25): Oracle SEK 385.1mn, Amazon SEK 277.5mn [AP3].
- **NBIM**: issuer-level holdings exist (semi-annual) but the page is a single-page app; not retrieved; Snowflake Marketplace tables need an account [NBIM][NBIM-SNOW].
- **LQD/HYG**: bot-blocked from the sandbox (HTTP 200 with block HTML); untested from a browser or Render [LQD]. **SSGA** works: SPIB 2026-10-14 weights Amazon 4.8% 2031 0.426%, Alphabet 0.329%, Nvidia 0.325%, Oracle 0.238%, Meta 0.198%; JNK holds Galaxy Helios 9.875% 2031 0.375%, Core Scientific 0.325%, CoreWeave 9% 2031 0.183%, Cipher 0.174% [SSGA-SPIB].
- **N-PORT** (verifier A find): PIMCO Variable Insurance Trust lists "BEIGNET INVESTOR LLC / PROJECT BEIGNET SR SEC 144A", CUSIP 990AAXQG4, due 2049 — the Meta Hyperion SPV notes, absent from any prospectus feed [NPORT-PIMCO]; quarterly bulk zips 2019Q4-2026Q3 [NPORT-SETS]. Covers US registered funds only; not sovereigns, insurers or banks.

## 4. The substitution hypothesis

**What the data say.** (i) Japan is a net *seller* of US sovereign debt in 2026 on every basis: BOJ sovereign LT -JPY 5.47trn Jan-Aug; TIC LT Treasuries -$11.5bn Jan-Jul, -$70.5bn incl. bills; MFH incl. bills $1,185.5bn Dec-25 [BOJ-BP][TIC-CSLT]. (ii) Japan is *not* a meaningful buyer of US corporates: +$8.4bn Jan-Jul 2026 (vs +$13.1bn in 2024, +$13.2bn in 2025), holdings down $8.4bn since December; BOJ non-sovereign residual +JPY 0.43trn [FRED-TIC-JP-CORP]. (iii) The Japanese money is going home: banks -JPY 11.74trn of foreign LT debt Jan-Sep 2026, life insurers net sellers every year 2020-26, trust accounts (pension money) the only buyers at +JPY 11.41trn [MOF-B3]; JGB 10y 2.066% → 3.015%, 30y 3.354% → 4.072% (2025-12-30 → 2026-10-14) [MOF-JGB]; BoJ to 1.25% on 2026-09-18 [BOJ-MPM]. (iv) Foreign officials hold 6.0% of foreign-held US corporates and their net buying (+$41bn Jan-Jul 2026) is a flat drift that predates the AI boom [FRED-TIC-OFF]. (v) The aggregate foreign rotation is real — corp +$282bn vs LT Treasuries +$174bn Jan-Jul 2026, against +$305bn / +$490bn in 2024 — and is led by non-official buyers in custody centres (UK +$126bn Treasuries / +$33bn corporates; Ireland +$29bn corporates) [FRED-TIC-GT-CORP][FRED-TIC-UK]. TIC cannot say whether any of it is AI paper; the SHL survey carries issuer industry only as world totals (computer & electronic product mfg $239bn, telecom & information $219bn, computer systems design $75bn at Jun-25) [SHL2025].

**Where the data are silent.** No free source attributes a specific issuer's bonds to a country or investor type; this negative claim was attacked (IMF PIP, ECB SHSS, NZ Super, ABP) and survived [TIC-CSLT]. Deal allocations are not a structured field even in the cited paid feed [FIDESK-NIM]. The only place a central bank has named buyers is the euro area: US big tech ~10% of euro NFC gross issuance, 15% of the year-to-Mar-2026 increase in domestic euro corporate-bond holdings, bought by pension funds and insurers [ECB]; $48bn of hyperscaler bonds in European currencies to 2026-09-25 [APOLLO-EU]. Alphabet's JPY 576.5bn seven-tranche yen deal (≈$3.63bn) [FWP-GOOGL-JPY] is AI capex funded in yen from Japanese investors — a channel that bypasses Treasuries entirely and is visible in FWPs.

**Competing explanations and what the published pieces say.** Fiscal supply: IMF GFSR attributes the term-premium rise "most notably" to persistent deficits and only says AI issuance "could compete" with sovereign issuance [IMF-GFSR]; TBAC minutes do not mention corporates at all. Rate expectations: ACM shows the 2026 YTD +95bp in the 10y is +84bp expected short rates and +10bp term premium (the +129bp since end-2023 is +120bp term premium) [ACM]; PIMCO's Feb-May window is 38bp expectations / 13bp term premium [PIMCO-0601]. Event study: six surprise AI deals, two-day windows, no statistically significant move in 10y yields, term premia or swap spreads [PIMCO-0921]; "repricing, not displacing" [PIMCO-0928]. Current account: the NY Fed finds the foreign-financing story is government dissaving, not AI investment [LSE-CA]. Fed demand: TREAST +$339bn YTD to $4,566bn is a competing demand-side factor no crowding-out piece addresses [FRED-TREAST]. Long-end technical: hyperscalers are 4.5% of the ICE US Corporate index but 31.2% of the >26y bucket, 41% of their issuance beyond 15y vs 16% for the index [T24]; BNY sees "modest" marginal pressure on long-end demand [BNY]; the Cembalest "68% of new long-duration Treasury borrowing" figure has no stated denominator and reaches us only via secondary coverage [247]. Auctions: 10y indirect share 64.0-78.2% in H1 → 76.7-81.5% Jul-Oct, 30y 72.3-79.5% Sep-Oct, 20y reopening of 2026-09-15 at 52.5% the only weak print — no visible foreign abandonment at auction [TD-NOTE][TD-BOND].

**Clean test vs. what is possible now.** A clean test needs holder-country x issuer flows (deal allocations or eMAXX/HDS holdings) alongside the issuance tally; nothing free supplies it. Partial tests buildable today: (1) TIC rotation index by country, both LT and incl.-bills, with custody centres shown as unattributable; (2) BOJ sovereign vs non-sovereign residual for Japan, monthly from 2014 — the one country-level direct test; (3) MOF investor-type flows weekly; (4) IMF PIP Japan x US x Japanese holder sector, semi-annual, reserves excluded (end-Dec 2025: deposit-takers $404.7bn, insurers and pensions $260.2bn, other financial $493.6bn; verifier find, single pass) [IMF-PIP][FEDS-TIC]; (5) ACM/KW term premium and auction indirect share around issuance clusters; (6) annual GPIF/NBIM/AP3 issuer lists as spot checks. Bills-inclusive Treasury flows must be shown alongside LT-only: Japan's 12-month sign flips between them.

## 5. Breaking indicators

| Series | Source | Freq | Free/paid | Shows | Jun-Oct 2026 read (verified) |
|---|---|---|---|---|---|
| ICE OAS by rating (AAA/AA/A/BBB/IG/BB/B/HY) | [FRED-BBB][FRED-IG][FRED-HY] | daily | free, 3y history only (FRED notice; ALFRED vintages rewritten too [ALFRED][FRED-NOTICE]) | tranche-bucket repricing | 2026-10-14: 0.40 / 0.60 / 0.70 / 1.04 / 0.84 / 1.99 / 3.29 / 3.25 — all inside 2026 ranges (IG high 0.94, BBB 1.16, HY 3.46 in March) |
| CCC OAS and CCC-B gap | [FRED-CCC] | daily | free | the only index line that moved with neocloud stress | CCC 12.82 = 2026 high, +3.78 since 05-01; gap 9.53 vs 5.84 at end-2025 |
| IG / HY effective yield | [FRED-IGEY] | daily | free | all-in funding cost | 5.94% (high 6.03, 10-02) / 8.20% (high 8.22, 10-01): yields at highs while spreads are not |
| Moody's Baa-10y / Aaa-10y | [FRED-BAA10Y] | daily | free, 1986→ | long-history spread substitute | 1.46 / 0.96 (10-13) |
| Fed excess bond premium | [FED-EBP] | monthly | free, 1973→ | risk-appetite turn | -0.39 (Sep) |
| OFR FSI; STLFSI4 / NFCI | [OFR-FSI][FRED-STLFSI] | daily / weekly | free | has it gone systemic | -2.139 (credit -0.98); -0.72 / -0.50 — calm |
| ACM TP10; Kim-Wright TP10 | [ACM][FRED-KW] | daily | free | crowding / term-premium channel | 0.851 (10-13; high 0.985 on 10-07; 0.748 at end-2025); KW 1.073 (10-09) |
| DGS10 / DGS30 / DGS2 | [FRED-DGS10][FRED-DGS30] | daily | free | long-end level | 5.21 / 5.56 / 4.79 (as of 10-13, CORRECTED date); 30y high 5.67 on 10-07, highest since 2002-07-05; T10YIE 2.35 [FRED-T10YIE] |
| Auction high yield, bid-to-cover, indirect % | [TD-BOND][TD-NOTE] | per auction | free (no tail: no WI field) | foreign-demand proxy | 30y 10-08: 5.618%, 2.54, indirect 72.3%; 10y 10-07: 5.300%, 2.77, 80.3%; 20y 09-15: 52.5% (min in 365d) |
| MOVE | [MOVE-YH] cross-checked [MOVE-INV] | daily | free | rates vol | 99.06 close 10-14; 52w 55.77-115.02 (Yahoo label bug retired) |
| BDC price / NAV (ARCC, OBDC, BXSL, FSK, MAIN, GBDC) | [BDC-YH]; NAV from 8-Ks [BXSL-8K][GBDC-8K] | daily / quarterly | free | private-credit lender stress | 0.98 / 0.72 / 0.95 / 0.58 / 1.61 / 0.87 (10-15); 44 BDCs FV/cost 99.25% → 97.57% H1 (Reuters analysis of filings; 81% of software loans marked down per Houlihan Lokey) [RTRS-BDC] |
| Issuer bond price by ISIN, Boerse Frankfurt | [BF-ORCL] | intraday poll, no backfill | free | issuer-level long-bond price | Oracle 5.95% 2055 at 72.21 (10-15); ISINs are free in FWPs [FWP-ORCL-2509] |
| Single-name 5y CDS | press prints only; feed paid (S&P GMI, ICE DS) [RTRS-CDS][CB-CRWV] | event | paid | first-mover stress | 10-15: CoreWeave 1,194.5bp record (provider unnamed), >1,100bp per S&P GMI, ~881 vs ~547 end-June; Oracle "near 300bp, +~31bp on the week" (CORRECTED from "288, +26"), 218bp late Jul [IFR-2644]; Nvidia peak 82bp late Jul; SoftBank "424bp" unsourced — dropped |
| Neocloud bond prices | press [MW-CRWV][CB-CRWV] | event | paid feed | HY AI distress | CoreWeave 2031-32 notes 76.5-81, >15% yield; 9.625% 2032 "touched 15%" (14.8% UNVERIFIABLE); 10-15 rebound Jun-2030 +5.7 to 91.3 |
| SPV paper | press [GURU-HYPERION][YARDENI] | event | paid feed | off-balance-sheet distress | Hyperion $27.3bn 6.581% 2049 at ~91.6 (10-07, price source unnamed); Project Jupiter debt <90 and Volta loan at 11%+ are aggregator-level (Bloomberg originals 403) |
| New-issue concession, cover ratio | [RTRS-NIC][APOLLO-COVER][FORTUNE-AMZN] | per deal | free prints | primary-market indigestion | median NIC 12bp 2026 vs 2.25bp 2025; 78 of 91 bonds wider than issue, median +22bp (07-28); cover ~5x Feb → <2x Jul; Amazon Jul $25bn paid 18-21bp, book 2.5x vs 3.2x in March |
| Spread at issue, 30y tranche (bp over UST) | FWPs [FWP-META-2604][FWP-ORCL-2509][FWP-ORCL-2602] | per deal | free | cleanest free gauge | Meta 98 → 132; Amazon 75 → 105 → 110; Alphabet 82 → 83 → 115; Oracle 125 → 180 (10y 105 → 145; CORRECTED tenors); Nvidia 65 |
| Rating actions | press [HEISE-ORCL] | event | free | migration | S&P Oracle BBB → BBB- 07-09 (stable); Moody's Baa2 negative; CoreWeave agency rating conflicting across sources |
| TRACE volume in AI-linked bonds; DTCC CDS outstanding | [IFR-2644] | monthly / weekly | free prints | hedging demand | record $127bn Jul = 14.5% of IG volume vs 4.5% avg 2025; Oracle CDS outstanding $25.1bn vs $6.9bn y/y |
| Treasury long-end buybacks | [BIS-QR] | per op | free | official response | ≥$4bn/op 09-09 → 11-04, ~+$14bn |
| Swap spreads; ICE sector sub-indices; TRACE EOD | none free | daily | paid | the Dallas Fed / PIMCO crowding signal | not available |

## 6. Proposed build

**Phase 1 — ships on treasury-canary, free data only.** Cadence: EDGAR Atom + submissions poll daily; TIC/BOJ/MOF/Z.1 on release calendar; FRED/ACM/TreasuryDirect daily.

| Panel | Series | Source |
|---|---|---|
| AI-trade issuance | Tranche table from FWP/424B parser over a CIK whitelist (Meta, Alphabet, Amazon, Oracle, Nvidia, Broadcom, AMD, Intel, Micron, Equinix, GE Vernova, Vistra) plus 8-K EX-99 / EFTS "senior notes" for registrants' 144A (CoreWeave, Core Scientific, Cipher, Hut 8, Galaxy, TeraWulf, Applied Digital); `deals.csv` as the seed with verif and rating_verified flags; stacked monthly by bucket and quarterly by rating; non-USD legs as a separate series | [EDGAR-SUB][EFTS][C-DEALS] |
| AI share | USD legs / SIFMA quarterly totals (PDF) and / Z.1 nonfinancial net issuance; IG/HY from pie x total until the xls is registered | [SIFMA-PDF][FRED-FA103] |
| Who holds US corporates | Z.1 F3.5.t holder-sector flows and L.213 levels; ROW vs ETFs/insurers/funds; ex-ABS ROW line (verifier find) | [Z1-F35t][Z1-ZIP][FRED-FA893] |
| Foreign bid by country | TIC net purchases and holdings, corporates vs Treasuries (LT and incl. bills), for Japan, Taiwan, Korea, Norway, Switzerland, UK, China, official / non-official; custody centres (Belgium, Luxembourg, Cayman, Ireland, UK) grouped as unattributable | [TIC-CSLT][TIC-SLT1] |
| Japan | BOJ sovereign vs non-sovereign residual (2014→); MOF by investor type (monthly) and total (weekly); JGB 10y/30y; policy rate; USDJPY; LIAJ foreign-securities balance; Taiwan FSC foreign-investment table as the second Asian life-insurer series | [BOJ-BP][MOF-B3][MOF-WEEK][MOF-JGB][LIAJ][TW-FSC] |
| Crowding gauges | MSPD net marketable issuance (coupons vs bills) against the tally; ACM and KW TP10; DGS10/30; auction high yield, BTC, indirect % by tenor; Fed TREAST | [MSPD][ACM][FRED-KW][TD-BOND][FRED-TREAST] |
| Breaking | OAS by rating + CCC-B gap + BAA10Y; IG/HY yields; EBP; OFR FSI; MOVE; BDC P/NAV with NAVs pulled from 8-Ks; Frankfurt daily poll of ~15 hyperscaler ISINs from FWPs; event log with provenance badge (primary / press / aggregator) and retrieval timestamp | [FRED-CCC][FED-EBP][OFR-FSI][BF-ORCL] |
| Issuer-level spot checks | GPIF annual ISIN list; AP3 semi-annual; SSGA SPIB/SPLB/JNK daily; quarterly N-PORT scan for SPV CUSIPs (Beignet-type) | [GPIF][AP3][SSGA-SPIB][NPORT-SETS] |

**Phase 2 — needs a paid-data decision.** Bloomberg NIM/HDS or LSEG Workspace (IFR deal reports + eMAXX holdings) or Dealogic: deal-level order book and allocation by investor type / region, 144A completeness for non-registrants, loans. S&P GMI or ICE DS: daily single-name CDS. ICE Data Indices: full-history OAS and sector sub-indices. EPFR: fund flows by country. PitchBook LCD: private credit. Registration-only (free): SIFMA xls, FINRA Public API ($0; the 10 GB/month cap is documented for Firm credentials only [FINRA-FEES]), DART OpenAPI key, Snowflake trial for NBIM, iShares CSV from a browser.

**Counter-agent gate tests (merge-blocking).** Tranche sums re-derive the headline for every parsed deal (Meta 30.0 / 25.0, Oracle 25.0, Nvidia 25.0, Amazon C$14.0); FX conversion equals FRED on trade date; Z.1 FU vs FA unit check (ratio 4-4.5x; mixing refused); TIC "All Countries" vs "Grand Total" labelled; LT-only and bills-inclusive Treasury flows both present; BOJ sovereign + residual = total; SIFMA YTD growth computed from the quarterly series, not the page label; share denominators currency-consistent (USD legs only); MSPD class sum equals total marketable; every press-derived number stores retrieval timestamp and quoted text (the Reuters CDS article changed intraday); no number without a URL; inclusion flags consistent with the stated rules (the Amazon CAD and CoreWeave May-25 errors); rating bucket per the chosen convention; honesty box with frozen numbers and the measurement basis (gross vs net, LT vs all-maturity).

## 7. Pending questions (ranked)

| # | Priority | Question | What it moves |
|---|---|---|---|
| 1 | P1 | Do you have, or will you buy, Bloomberg, LSEG Workspace (IFR + eMAXX), Dealogic, S&P GMI/ICE CDS or EPFR access? | The only route to deal-level allocation by investor type / region (the buyer side of your hypothesis), 144A completeness, daily CDS and swap spreads. Decides whether the tracker is an issuance panel plus a buyer-side test, or an aggregate rotation monitor. |
| 2 | P1 | Universe boundary: which issuers and instruments count as "the AI trade"? Hyperscalers only; + Nvidia / SpaceX; + neoclouds and miners; + chips/memory including refinancing (Broadcom VMware, Intel); + SPVs and DC ABS/CMBS; + private-credit lenders. Converts in? Mandatory converts? Off-balance-sheet debt at launch or at close? | Swings the 2024-26 total by $60-90bn, the chips and power buckets by >50%, shifts ~$38bn between 2025 and 2026, and sets which free series (CCC vs BBB vs AA) is the tell. Public tallies differ 3x on scope alone. |
| 3 | P1 | Which hypothesis should the tracker score: (a) sovereign/Japanese substitution at issuer level (infeasible free) or (b) aggregate foreign rotation from Treasuries into US corporates by country, with Japan's BOJ sovereign/non-sovereign split as the direct test (feasible monthly now)? | Whether the sovereign panel is built, and how its verdict is worded given the data so far point to repatriation, not substitution. |
| 4 | P2 | Rating convention: agency rating printed at pricing (free, same day) or migration per bond (17g-7(b) at 12-24 months lag, or paid)? S&P letter at issue, lowest of three, or Moody's? Multi-class ABS by senior class or split? | Moves ~$30bn between AA/A and BBB/BB; whether downgrades can serve as a breaking signal. |
| 5 | P2 | May the build register free accounts in your name (SIFMA xls, FINRA Public API, DART key, KBRA, agency issuer pages, Snowflake for NBIM), and can you download iShares LQD/HYG CSVs and the NBIM Excel once from a browser (and does Render's egress hit the same bot block)? | Unlocks monthly IG/HY by-rating denominator, TRACE volume by grade, issuer-level NBIM, and the liquid ETF proxies. |
| 6 | P2 | Is a daily Boerse Frankfurt poll of ~15 hyperscaler ISINs (thin retail prints, no backfill) acceptable as the issuer-level price layer, pending a FINRA key test for CUSIP-level TRACE? | Whether v1 has any issuer-level daily price series. |
| 7 | P2 | Do you have FT access for "Are Big Tech Bonds Crowding Out the US Treasury?" (2026-09-27) and the JPMorgan Cembalest original behind the 68% figure? | Whether the 68% can be reproduced or must be discarded; could raise the magnitude verdict. |
| 8 | P3 | Bonds first, with loans / private credit (BDC schedules, 8-K loan filings) in a later phase, and a monthly tally refresh with manual entry of 144A/press deals? | Build scope and time to a first working panel. |
| 9 | P3 | Alert thresholds to pre-register (e.g. CCC OAS >1,300bp, AA >70bp, BBB >120bp, ACM TP10 >1.0, 30y auction indirect <55%, MOVE >120, FSK P/NAV <0.55, any BDC gate >20% of NAV)? | Turns the candidate list into alerts rather than charts. |
| 10 | P3 | Show aggregator-only events (Yardeni monitor citing Bloomberg) with a "secondary, unverified" badge, or exclude until a primary is fetched? | Coverage vs honesty on the event timeline. |

## 8. Counter-agent log

| Finder | Verdict | Claims C / Corr / Ref / Unv (skipped NOTE) | Numbers C / Corr / Unv | Material corrections | What the verifier found missed |
|---|---|---|---|---|---|
| A issuance data | PASS_WITH_FIXES | 10 / 3 / 0 / 0 (1) | 20 / 2 / 0 | SIFMA YTD growth is +28.1% vs H1-25, not +12.5% (that is FY25 vs FY24); Nvidia FWP does carry expected ratings; FRED serves SAAR Z.1 mirrors (finder queried a wrong code); FINRA 10 GB cap documented for Firm tier only; "no free source gives who holds a specific bond" narrowed — N-PORT does, for registered funds | N-PORT CUSIP-level holdings (Beignet/Hyperion 144A sighted); CoreWeave's 144A bond and convert program is on EDGAR via 8-K EX-99; Alphabet EUR/JPY registered tranches need a currency field; Form D does not capture private AI borrowers' debt |
| B holders / flows | PASS_WITH_FIXES | 11 / 5 / 0 / 0 (1) | 21 / 3 / 0 | Japan Treasuries incl. bills: 12m -$48.6bn, 2026 Jan-Jul -$70.5bn (LT-only read +$4.0bn / -$11.5bn); "$5.27bn" should be $5.27trn Grand Total; Z.1 nonfinancial bonds excl. eREITs $7,751.6bn (the $8,278.0bn double counts); SSGA holdings counts (SPIB 5,367 not 355); Taiwan official FSC table located | Taiwan FSC monthly table (NT$22.45trn, 65.50%, Jun-26); IMF PIP Japan x US x holder sector; Z.1 ex-ABS ROW line and Fed H.8 weekly; NBIM Snowflake tables; Gulf CSLT series end 2011/2023 |
| C universe / deal tally | NOT_PASS | 11 / 6 / 0 / 1 (2) | 21 / 5 / 3 | Total $682.5bn not $670.5bn (Amazon C$14.0bn and CoreWeave $2.0bn wrongly excluded against the finder's own rules); hyperscaler 2026 $217.5bn; AA $310.6bn, unknown $34.5bn; CoreWeave $43.8bn not $34.6bn; Oracle spread tenors (10y 105 → 145, 30y 125 → 180); all-currency share invalid; Hyperion terms press-unnamed; SoftBank $11.1bn sits in the off-BS bucket | ~$18.5bn of 8-K-documented miner/landlord notes (Hut 8, Galaxy, Core Scientific, Cipher Stingray); Meta 10-K/10-Q RVG thresholds as primary anchors for SPV sizes; agency new-issue press releases for 144A ratings; IG/HY dollars derivable from the SIFMA PDF |
| D substitution hypothesis | PASS_WITH_FIXES | 12 / 2 / 0 / 0 (2) | 27 / 3 / 0 | Hyperscaler-to-UST ratio mixes gross all-currency with net: state 13-19% all-ccy, ~10-14% USD-only; the 68% figure is "Cembalest/JPMorgan via 247wallst", original unidentified; yields dated 10-13 not 10-14 | FEDS Note on TIC vs IMF PIP custodial asymmetries; Z.1 on FRED (ROW Treasuries +$47bn vs corporates +$435bn SAAR, 2026Q2; nonfinancial net issuance as the net denominator); TreasuryDirect indirect-share series (no collapse Jan-Oct); FEDS Note on the TIC S splice; NY Fed current-account piece (fiscal, not AI) |
| E breaking indicators | PASS_WITH_FIXES | 15 / 4 / 0 / 0 (1) | 30 / 5 / 1 | Oracle CDS "near 300bp, +~31bp on the week", provider unnamed (not 288/+26); SoftBank 424bp and "+74.5bp ICE DS" unsupported by cited URLs; CoreWeave 2032 yield "touched 15%" (14.8% unverifiable); 10y indirect H1 range 64.0-78.2% not 64-70%; PIMCO "low-20s → ~40bp" is the 10s30s curve slope, not a spread level; BDC FV/cost is Reuters' own analysis, not Houlihan Lokey; MOVE caveat retired | Hyperscaler ISINs are free in FWPs (closes the Frankfurt ISIN gap); BDC NAVs from 8-K exhibits; investing.com MOVE cross-check; ALFRED truncation is total (vintage 2024-06-01 also starts 2023-10-16); DataGrapple retired; press articles change intraday — store retrieval timestamp |

## 9. Source key

| Tag | URL |
|---|---|
| C-DEALS | ai_debt_flows/data/deals.csv |
| C-TOTALS | ai_debt_flows/data/totals.json (finder version, pre-correction) |
| EDGAR-SUB | https://data.sec.gov/submissions/CIK0001326801.json |
| EDGAR-ACCESS | https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data |
| EFTS | https://efts.sec.gov/LATEST/search-index?q=%22pricing%20term%20sheet%22&forms=FWP&dateRange=custom&startdt=2026-09-15&enddt=2026-10-15 |
| FWP-META-2510 | https://www.sec.gov/Archives/edgar/data/1326801/000119312525258837/d61769dfwp.htm |
| FWP-META-2604 | https://www.sec.gov/Archives/edgar/data/1326801/000119312526197902/d148113dfwp.htm |
| FWP-META-2408 | https://www.sec.gov/Archives/edgar/data/1326801/000119312524196020/d881153dfwp.htm |
| FWP-ORCL-2602 | https://www.sec.gov/Archives/edgar/data/1341439/000119312526033882/d44245dfwp.htm |
| FWP-ORCL-2509 | https://www.sec.gov/Archives/edgar/data/1341439/000119312525215807/d49252dfwp.htm |
| FWP-NVDA | https://www.sec.gov/Archives/edgar/data/1045810/000119312526271326/d49394dfwp.htm |
| FWP-AMZN-CAD | https://www.sec.gov/Archives/edgar/data/1018724/000110465926071456/tm2613616d3_fwp.htm |
| FWP-AMZN-2603 | https://www.sec.gov/Archives/edgar/data/1018724/000110465926025948/tm266670d5_fwp.htm |
| FWP-GOOGL-JPY | https://www.sec.gov/Archives/edgar/data/1652044/000119312526225046/d104539dfwp.htm |
| FWP-GOOGL-EUR | https://www.sec.gov/Archives/edgar/data/1652044/000119312526206404/d127573dfwp.htm |
| FWP-GOOGL-2608 | https://www.sec.gov/Archives/edgar/data/1652044/000119312526338750/d159970dfwp.htm |
| 8K-CRWV-DDTL | https://www.sec.gov/Archives/edgar/data/1769628/000176962826000357/crwv-20260807.htm |
| 8K-CRWV-2505 | https://www.sec.gov/Archives/edgar/data/1769628/000176962825000025/crwv-20250527.htm |
| CRWV-EX99 | https://www.sec.gov/Archives/edgar/data/1769628/000176962826000432/ex991pricing.htm |
| 8K-NVDA-RVG | https://www.sec.gov/Archives/edgar/data/1045810/000104581026000069/nvda-20260817.htm |
| 10Q-META | https://www.sec.gov/Archives/edgar/data/1326801/000162828026050705/meta-20260630.htm |
| 8K-HUT8-1 | https://www.sec.gov/Archives/edgar/data/1964789/000110465926053247/tm2613163d1_8k.htm |
| 8K-HUT8-2 | https://www.sec.gov/Archives/edgar/data/1964789/000110465926071952/tm2617190d1_8k.htm |
| 8K-GLXY-1 | https://www.sec.gov/Archives/edgar/data/1859392/000185939226000079/glxy-20260728.htm |
| 8K-GLXY-2 | https://www.sec.gov/Archives/edgar/data/1859392/000095010325013949/dp236467_8k.htm |
| 8K-CORZ | https://www.sec.gov/Archives/edgar/data/1839341/000119312526208905/d47435d8k.htm |
| 8K-CIFR-STING | https://www.sec.gov/Archives/edgar/data/1819989/000095010326008994/dp248453_8k.htm |
| TWULF-8K | https://investors.terawulf.com/sec-filings/all-sec-filings/content/0001083301-25-000096/0001083301-25-000096.pdf |
| NPORT-PIMCO | https://www.sec.gov/Archives/edgar/data/1047304/000109926325004523/primary_doc.xml |
| NPORT-SETS | https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets |
| ARCC-10Q | https://www.sec.gov/Archives/edgar/data/1287750/000162828026050307/arcc-20260630.htm |
| BCRED-10Q | https://www.sec.gov/Archives/edgar/data/1803498/000180349826000048/bcred-20260630.htm |
| CF-META | https://data.sec.gov/api/xbrl/companyfacts/CIK0001326801.json |
| SBG-PR | https://group.softbank/en/news/press/20260924 |
| DSA-SBG | https://www.dealstreetasia.com/?p=496053 |
| HKEX-TCEH | https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1014/2026101400063.pdf |
| SIFMA-PDF | https://www.sifma.org/wp-content/uploads/2026/04/SIFMA-Research-Quarterly-Fixed-Income-IT-2Q26.pdf |
| SIFMA-PAGE | https://www.sifma.org/research/statistics/us-corporate-bonds-statistics/ |
| SIFMA-FORM | https://share.hsforms.com/1cLnJJ_PhTDSEjA4VhfBe7wct3d3 |
| Z1-F35t | https://www.federalreserve.gov/releases/z1/current/html/F3_5_t.htm |
| Z1-ZIP | https://www.federalreserve.gov/releases/z1/data/FRB_Z1_csv.zip |
| FRED-FA893 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BOGZ1FA893163005Q |
| FRED-FA103 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BOGZ1FA103163005Q |
| FRED-FU893 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BOGZ1FU893163005Q |
| FRED-ROWCB | https://fred.stlouisfed.org/series/ROWCBAQ027S |
| MSPD | https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/mspd_table_1?filter=record_date:gte:2022-09-01&page[size]=3000 |
| TSY-SB0584 | https://home.treasury.gov/news/press-releases/sb0584 |
| TIC-CSLT | https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/cslt.zip |
| TIC-SLT1 | https://ticdata.treasury.gov/Publish/slt_table1.txt |
| SHL2025 | https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/shl2025r.pdf |
| FRED-TIC-JP-CORP | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPNET42609 |
| FRED-TIC-JP-CORPPOS | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPPOS42609 |
| FRED-TIC-JP-TSY | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTTREASNET42609 |
| FRED-TIC-JP-TSYPOS | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTTREASPOS42609 |
| FRED-TIC-GT-CORP | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPNET99996 |
| FRED-TIC-GT-CORPPOS | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPPOS99996 |
| FRED-TIC-NONOFF | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPNET99991 |
| FRED-TIC-OFF | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTCORPNET99990 |
| FRED-TIC-OFFPOS | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTTREASPOS99990 |
| FRED-TIC-UK | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FORLTTREASNET13005 |
| FRED-FDHBFIN | https://fred.stlouisfed.org/graph/fredgraph.csv?id=FDHBFIN |
| FEDS-TIC | https://www.federalreserve.gov/econres/notes/feds-notes/measuring-cross-border-securities-positions-explaining-asymmetries-20260213.html |
| IMF-PIP | https://api.imf.org/external/sdmx/2.1/data/IMF.STA,PIP/JPN.....USA.?lastNObservations=3 |
| BOJ-BP | https://www.stat-search.boj.or.jp/info/bp_m_en.zip |
| MOF-SOV | https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/preliminary/bppi202608.pdf |
| MOF-B3 | https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/monthb3.csv |
| MOF-WEEK | https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv |
| MOF-JGB | https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv |
| MOF-IIP | https://www.mof.go.jp/policy/international_policy/reference/iip/data/rdip_all2025.xls |
| BOJ-MPM | https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k260918a.pdf |
| GPIF | https://www.gpif.go.jp/en/performance/73509681gpif/unyoujoukyou_2025_20_en_2.xlsx |
| AP3 | https://a.storyblok.com/f/257759/x/5d6f418064/ap3-fixed-income-holdings-dec31-2025.pdf |
| NBIM | https://www.nbim.no/en/investments/all-investments/ |
| NBIM-SNOW | https://www.nbim.no/en/terms-of-use-holdings-data-in-snowflake-marketplace/ |
| SSGA-SPIB | https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spib.xlsx |
| LQD | https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf/1467271812596.ajax?fileType=csv&fileName=LQD_holdings&dataType=fund |
| TW-FSC | https://www.ib.gov.tw/uploaddowndoc?file=statistics/202610071448110.pdf&filedisplay=x.pdf&flag=doc |
| LIAJ | https://www.seiho.or.jp/english/statistics/summary/xls/e_toukei2026.4-7.xls |
| NAIC | https://content.naic.org/sites/default/files/capital-markets-special-reports-asset-mix-ye2025.pdf |
| SNB | https://www.snb.ch/en/the-snb/mandates-goals/investment-assets/reserves-bonds |
| ICI | https://www.ici.org/research/stats/flows |
| ACM | https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls |
| FRED-KW | https://fred.stlouisfed.org/graph/fredgraph.csv?id=THREEFYTP10 |
| FRED-DGS10 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10 |
| FRED-DGS30 | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS30 |
| FRED-T10YIE | https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE |
| FRED-TREAST | https://fred.stlouisfed.org/graph/fredgraph.csv?id=TREAST |
| FRED-DEXJPUS | https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXJPUS |
| FRED-CCC | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A3HYC |
| FRED-BBB | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A4CBBB |
| FRED-IG | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CM |
| FRED-HY | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 |
| FRED-IGEY | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLC0A0CMEY |
| FRED-BAA10Y | https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAA10Y |
| FRED-NOTICE | https://fred.stlouisfed.org/series/BAMLH0A0HYM2 |
| ALFRED | https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=BAMLH0A0HYM2&vintage_date=2024-06-01 |
| FED-EBP | https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv |
| OFR-FSI | https://www.financialresearch.gov/financial-stress-index/data/fsi.csv |
| FRED-STLFSI | https://fred.stlouisfed.org/graph/fredgraph.csv?id=STLFSI4 |
| TD-BOND | https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Bond&days=365 |
| TD-NOTE | https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Note&days=365 |
| MOVE-YH | https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE?range=2y&interval=1d |
| MOVE-INV | https://www.investing.com/indices/ice-bofaml-move |
| BDC-YH | https://query1.finance.yahoo.com/v8/finance/chart/FSK?range=2y&interval=1d |
| BXSL-8K | https://www.sec.gov/Archives/edgar/data/1736035/000121390026085889/ea0300654-01_ex991.htm |
| GBDC-8K | https://www.sec.gov/Archives/edgar/data/1476765/000147676526000047/gbdcfy2026q3epfinal.htm |
| BF-ORCL | https://api.boerse-frankfurt.de/v1/data/quote_box/single?isin=US68389XDR35&mic=XFRA |
| FINRA-FEES | https://developer.finra.org/fees |
| FINRA-DOCS | https://developer.finra.org/docs |
| FINRA-DATA | https://www.finra.org/finra-data/fixed-income/market-corp |
| 17g7 | https://www.law.cornell.edu/cfr/text/17/240.17g-7 |
| MOODYS-17g7 | https://ratings.moodys.com/sec-17g-7b |
| KBRA | https://www.kbra.com/publications/tGrWrdbr |
| DCABS | https://www.datacentres.com/news/data-centre-abs-issuance-hits-38b-as-wall-street-securitizes-the-ai-lease-boom-slot1-2026-09-01 |
| SFA | https://structuredfinance.org/wp-content/uploads/2026/07/SFA-Research-Corner_How-Data-Center-ABS-and-CMBS-Fit-in-a-Broader-Financing-Ecosystem.pdf |
| INVNEWS-DCABS | https://www.investmentnews.com/alternatives/sec-exemption-clears-path-for-more-data-center-asset-backed-bonds/267767 |
| CREDAILY | https://www.credaily.com/briefs/data-center-cmbs-boom-rewrites-real-estate-risk/ |
| RTRS-CDS | https://www.investing.com/news/stock-market-news/ai-credit-default-swap-spreads-widen-sharply-4950549 |
| CB-CRWV | https://cryptobriefing.com/coreweave-credit-risk-record-high/ |
| MW-CRWV | https://finance.yahoo.com/markets/options/articles/coreweave-ai-bonds-tumble-raising-111700097.html |
| IFR-2644 | https://www.ifre.com/topic-codes/2463896/trading-frenzy-builds-in-hyperscaler-debt-and-cds-markets |
| IFR-ORCL | https://www.ifre.com/bonds/2379081/oracle-raises-us25bn-in-bond-offering-as-ai-funding-spree-continues |
| FIDESK-META | https://www.fi-desk.com/origination-meta-sold-us30-billion-of-ai-bonds-on-30-october/ |
| FIDESK-NIM | https://www.fi-desk.com/exclusive-bloombergs-new-issues-feed-takes-small-important-step-towards-improving-bond-issuance/ |
| RTRS-NIC | https://www.investing.com/news/stock-market-news/hyperscaler-debt-binge-pushes-yields-up-as-investor-demand-cools-4820617 |
| APOLLO-COVER | https://www.apollo.com/institutional/insights-news/insights/daily-spark/cover-ratios-for-hyperscaler-bonds-declining |
| APOLLO-EU | https://www.apollo.com/institutional/insights-news/insights/daily-spark/europe-is-financing-the-us-ai-buildout |
| FORTUNE-AMZN | https://fortune.com/2026/07/17/ai-boom-debt-blitz-investor-demand-hyperscaler-bond-issuance/ |
| FORTUNE-SP | https://fortune.com/2026/07/31/ai-debt-hypescalers-capex-capital-spending-hidden-borrowing-bond-issuance/ |
| HEISE-ORCL | https://www.heise.de/en/news/S-P-downgrades-Oracle-to-BBB-only-one-notch-above-junk-level-11363472.html |
| GURU-HYPERION | https://www.gurufocus.com/news/9113532/meta-platforms-273b-ai-data-center-bond-drops-amid-macro-pressure-meta |
| META-PR | https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Announces-Joint-Venture-with-Funds-Managed-by-Blue-Owl-Capital-to-Develop-Hyperion-Data-Center/default.aspx |
| GDCH-SOPA | https://www.globaldatacenterhub.com/p/blackrock-launches-123-billion-bond |
| SF-ORCLVTG | https://startupfortune.com/banks-that-financed-the-ai-data-center-boom-now-want-out-of-that-debt/ |
| RTRS-BDC | https://www.investing.com/news/economy-news/us-private-credit-firms-mark-down-more-loans-4886397 |
| YARDENI | https://yardeni.com/tools/private-credit-monitor |
| BIS-QR | https://www.bis.org/publications/qr-202609/yields-climb-yet-risk-appetite-holds-firm |
| T24 | https://blog.twentyfouram.com/insights/how-hyperscaler-issuance-is-reshaping-the-treasury-curve |
| PIMCO-0921 | https://www.pimco.com/us/en/insights/the-credit-market-lens-ai-capex-and-the-limits-of-crowding-out |
| PIMCO-0928 | https://www.pimco.com/us/en/insights/the-credit-market-lens-hyperscalers-are-repricing-not-displacing-so-far |
| PIMCO-0601 | https://www.pimco.com/eu/en/insights/ai-financing-needs-do-not-override-cyclical-drivers-of-yield |
| IMF-GFSR | https://www.imf.org/-/media/files/publications/gfsr/2026/october/english/ch1.pdf |
| ECB | https://www.ecb.europa.eu/press/blog/date/2026/html/ecb.blog20260831~dac6a37e73.en.html |
| DALLAS | https://www.dallasfed.org/research/economics/2026/0210 |
| JPMAM | https://am.jpmorgan.com/us/en/asset-management/adv/insights/market-insights/market-updates/on-the-minds-of-investors/can-credit-markets-absorb-the-ai-buildout |
| BNY | https://www.bny.com/corporate/global/en/solutions/platforms/execution-services/iflow/equities/hyperscaler-issuance-tests-long-end-ust-demand.html |
| 247 | https://247wallst.com/investing/2026/09/10/ai-companies-debt-now-equals-68-of-new-long-term-u-s-treasury-borrowing-this-year-jpmorgan-finds/ |
| LSE-CA | https://libertystreeteconomics.newyorkfed.org/2026/10/has-the-ai-boom-impacted-the-u-s-current-account/ |
| BARCLAYS-PB | https://privatebank.barclays.com/insights/market-perspectives-october-10-2026/bond-markets-break-multi-decade-records/ |
| MS-RTRS | https://www.marketscreener.com/news/global-ai-debt-issuance-to-top-500-billion-in-2026-morgan-stanley-says-ce7f5cdad088f424 |
| TOKENPOST | https://www.tokenpost.com/news/business/28445 |
| EMAXX | https://lseg.com/en/data-analytics/products/workspace/updates/emaxx |
| EPFR | https://financialintelligence.informa.com/en-US/epfr |

**Honesty box.** Tally totals are gross issuance at pricing, not net of redemptions; non-USD legs at spot on trade date; 20% of dollars rest on search snippets. TIC attributes by custodial residence and cannot see purchases routed through London/Luxembourg managers or Gulf SWFs. Z.1 "households" is a residual. FRED ICE OAS history is three years. All CDS and secondary-price levels are dated press prints, not a feed. Nothing here is a forecast.
