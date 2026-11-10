# Adversarial number-and-data verification — AI capex scoping study

Reviewer: independent (did not write any of the material). Date 2026-10-31.
Scratch code: `review1/code/` (dump_facts.py, rzone_check.py, fredA_check.py, eq_indep.py, footer_stats.py, nvda_msft_check.py).
Fresh pulls: `review1/raw/` (EDGAR companyfacts x6 re-pulled today, SEC submissions + ex-99.1 press releases for AMZN/ORCL, FRED x14, Census privsa/privtime, TWSE t187ap05_L, CBOE CRWV chain, FMP cash-flow statements). All parsed with `python3 -I`.

## VERDICT

| Unit | Verdict | One line |
|---|---|---|
| Finder A | **PASS** | All 8 dated claims reproduce from primary data; one presentational nit (1929 spread "low"). |
| Finder B | **PASS_WITH_FIXES** | Every number reproduces from EDGAR/FMP/press releases; but Oracle's Q3 OCF ($23.1bn) contains $11.4bn of customer capex prepayments, which the notes do not say — the group capex/OCF headline needs that caveat. |
| Finder C | **PASS_WITH_FIXES** | All quoted paper figures match the PDF extracts; its pre-registered outcome Y1 ("drawdown from the t0 level") is not GSY's crash definition it labels it with; GSY paper is internally inconsistent on the 5-yr filter (50% body / 100% table caption). |
| Scoping (earthquake, R-zone, capex chain) | **PASS_WITH_FIXES** | Headline table reproduces exactly and the corrections sign survives every stress; but "GSY-strict n=21 / 57%" and "GSY primary n=60 / 53% = the paper's 53%" use a NON-GSY net-of-market definition (ratio, not difference). With GSY's arithmetic definition the free file gives n≈47–50 and a crash rate of **40%**, not 53%. |

## Check table

| # | Item | Claimed | My check | Result | Source |
|---|---|---|---|---|---|
| 1 | Combined 5-co capex 2026Q3 | $231.4bn | 39.367+77.259+51.355+34.906+28.499 = 231.386 from fresh companyfacts | OK | review1/raw/facts_*.json |
| 1 | yoy / q-q | +118% / +27% | 231.386/106.318 = +117.6%; /182.505 = +26.8% | OK | same |
| 1 | capex/OCF Q3 | 1.17 | OCF 58.000+42.422+42.290+32.785+23.103 = 198.600 → 1.165 | OK (see S-1) | same |
| 1 | 2026 YTD | $563bn vs OCF $543bn | 149.228+182.505+231.386 = 563.1; 157.878+186.379+198.600 = 542.9 | OK | same |
| 1 | 2025 FY combined | $414.1bn | 78.515+97.800+106.318+131.419 = 414.05 | OK | CSV |
| 1 | AMZN Q3-26 capex | $77.3bn (anomalous?) | 91-day fact 77.259 (frame CY2026Q3); 9M 175.670 − 6M 98.411 = 77.259; press release "Purchases of property and equipment (77,259)", proceeds+incentives 1,381 → net 75,878 = the "$75.9bn" on the call; FMP 77.259 | OK — a true quarter, not YTD, not double-counted | amzn-20260930xex991.htm; fmp_cf_AMZN.json |
| 1 | ORCL Q3-26 (FQ1 FY27) OCF | $23.1bn (anomalous?) | 91-day fact 23.103; press release "Net cash provided by operating activities 23,103 vs 8,140"; FMP 23.103. **Includes "Increase in deferred revenues from customer prepayments with significant financing component 11,363"** (FQ4 FY26: 4,592). Oracle itself nets these in "Net cash outlay for capex". | Number right, meaning wrong → S-1 | orcl-ex99_1.htm |
| 1 | YTD differencing / tag choices | per notes | MSFT/GOOGL/ORCL PPE tag; AMZN PaymentsToAcquireProductiveAssets (PPE tag stops 2017); META PPE + FinanceLeasePrincipalPayments reproduces 34.906; Q4 = FY − 9M; Q2/Q3 = YTD diff; AMZN TTM facts correctly ignored (dur>100 and end already filled). ORCL FQ1 (Jun–Aug) → CY Q3, FQ2 (Sep–Nov) → Q4, etc. MSFT quarters align 1:1. | OK | build_series.py lines 5-38 |
| 1 | 2025 reconciliations | AMZN 131.8, GOOGL 91.5, META 72.2, MSFT FY25 64.5 | 131.819, 91.447, 69.691+2.524 = 72.215, 64.551 | OK | facts |
| 2 | Episode rule, look-ahead | +100%/24m, first trigger, 36m cooling | Code matches; features use P[t−24..t], R[t−23..t] only; rebound filter in variants uses PM[t−36..t] only; `last[j]` only set on recorded episodes. No look-ahead. | OK | earthquake_scoping.py:71-91; variants.py:12-17 |
| 2 | count_corrections | distinct ≥10% declines, reset on new high | 12 hand-made sequences: logic correct incl. double-dip-without-new-high (=1), end-in-drawdown (=1), three separate dips (=3). Only failure: an EXACT 10.0% drop is missed by float (1−90/100 = 0.0999…); measure-zero on real data. | OK (N-3) | eq_indep.py |
| 2 | Crash definition | ≥40% from running peak within next 24m | `max_dd(fut)` with fut = P[t..t+24]; matches GSY "40% drawdown from any point in the two years after the initial run-up" (gsy.txt:1493). 4 of 408 episodes have truncated horizons (12–23 months) — tiny downward bias. | OK (N-4) | gsy.txt |
| 2 | Headline table | n=408 25%; 0 corr 23% (149) vs ≥2 35% (113); size 12/24/40; vol 12/32/32; GSY-strict n=21 57%; base 13.7% | Independent re-implementation (own parser, own counters): 408/25.5%; 149/23.5% vs 113/34.5%; 12.5/24.3/39.7; 11.8/32.4/32.4; 21/57.1%; 638/4659 = 13.7% (all-months full-horizon variant 14.0%). Also byte-identical re-run of the scoping scripts. | OK | eq_indep.py; review1/out/rerun |
| 2 | Ken French parsing | VW monthly block, −99.99, Mkt = Mkt-RF+RF | VW block header at line 11/12 of 49_Industry_Portfolios.csv; `R<=-0.99` catches −99.99 and −999; 199912 market = 7.66+0.44 = 8.10%; files identical to finder C's copies | OK | scoping/raw |
| 2 | Stress: cooling 24m | — | n=432: 0 corr 21% vs ≥2 37% | sign survives | eq_indep.py |
| 2 | Stress: cooling 12m | — | n=574: 21% vs 39% | survives | |
| 2 | Stress: ≥10 firms | — | n=291: 23% / 13% (1 corr) / 30% | survives, weaker and non-monotone | |
| 2 | Stress: net-of-market outcome | — | n=408: 7% vs 24% (all rates fall to 14% overall) | survives, stronger | |
| 2 | Stress: all three | gap24+10 firms+net outcome | n=303: 7% / 8% / 20% | survives | |
| 2 | Variants panel F | raw & net ≥100%, gap24: n=60, 53% | reproduced: 60/53.3%; corr cells 10/0.60, 18/0.67, 32/0.44 (sign REVERSES in this panel) | numbers OK; label wrong (S-2) | eq_indep.py |
| 2 | Variants panel A within-vol cells | calm: 0 corr 106/0.14 vs ≥1 30/0.03; mid 40/0.42 vs 96/0.28 | reproduced exactly | OK | |
| 2 | Rebound exclusion look-ahead | — | `max_dd(PM[max(0,t-36):t+1])` — past data only | OK | variants.py:12 |
| 2 | exec-based reuse of constants | W/H/GAP unchanged? | exec stops before `W, H, GAP, RUNUP = …`; `episodes()` uses its own defaults W=24, H=24 and explicit gap args; RUNUP replaced by raw_thr. Constants not silently changed. Side effect: re-reads sys.argv (harmless). | OK | variants.py:7-9 |
| 2 | 46 (finder C) vs 21 (scoping) | explain | Finder C: net = r_ind − r_mkt (arithmetic), 5-yr raw ≥50%, ≥10 firms, 24m MERGE of signal months, 24m outcome window → 46 (my re-implementation 47; the extra is Gold 2025-09 with <24m horizon). Scoping: net = (1+r_ind)/(1+r_mkt)−1 (ratio) and strict is a post-hoc subset of raw first-triggers. Decomposition: finder-C rule with ratio-net → **21**; with arithmetic net → 47. The entire gap is the net-of-market definition. GSY use the arithmetic difference (Table 1: Hardware 1999/03 raw 103%, net-of-RF 99%, net-of-mkt 85% → simple subtraction). | explained → S-2 | eq_indep.py; gsy.txt:1520 |
| 3 | TBSDODNS identity | Z.1 nonfinancial business debt sec+loans, $mn, quarterly | FRED title "Nonfinancial Business; Debt Securities and Loans; Liability, Level", Millions of USD. FRED tags it "Seasonally Adjusted Annual Rate" (FRED's label for Z.1 levels; it is a stock, not a flow — fine to use as a level). GDP = $bn SAAR. | OK (N-5) | FRED series pages |
| 3 | 3-yr change in ratio | 2000Q1 +8.3, 2008Q4 +12.1, 2026Q2 −4.5 | 63.87−55.59 = +8.28; 75.61−63.51 = +12.09; 73.62−78.12 = −4.51 | OK | rzone_check.py |
| 3 | GHSS threshold | 8.99 pp over 3 yrs | ghss.txt:398 "top quintile of business debt growth have Δ3(Debt_Bus/GDP) > 8.99%"; equity 26.56% (l.432); 45.3% / 37.4 pp p=0.006 (l.449-453) | OK | ghss.txt |
| 3 | GHSS credit definition | BIS NFC? | No: IMF Global Debt Database total credit (loans + debt securities) to nonfinancial BUSINESSES, supplemented by JST; BIS only for Thailand (ghss.txt:286-294). Z.1 total nonfinancial business (TBSDODNS) is the closer US analogue; BIS NFC (QUSNAM770A) is narrower (excludes noncorporate). | OK — scoping's series choice is defensible | ghss.txt |
| 3 | Recompute with BIS QUSNAM770A | — | Series is % of GDP (FRED title says "Billions" but values are 29–80 = % GDP): 2000Q1 +8.5 pp; 2008Q4 +9.9; latest 2025Q4 −6.7 (2025Q3 −7.5). BIS series ends 2025Q4. Same regime read; 2000Q1 is marginally ABOVE 8.99 on BIS and marginally below on Z.1 — the chart's "2000 just under the line" is series-dependent (N-6). | both reported | fredA_check.py |
| 3 | Chart footer numbers | level 73.6 vs 63.9; debt yoy +2.2% 2024Q1 → +5.1% 2026Q2 | 73.62/63.87; 2.2%/5.1% | OK | |
| 4 | BEA comm equipment | 70.8 / 123.3 / 83.7 | C275RC1A027NBEA fresh: 70.753 / 123.323 / 83.735; real idx 10.0→20.7→15.8 | OK | fred_C275RC1A027NBEA.csv |
| 4 | Baa−Aaa | 0.55 Jan-2000; 1.41 Oct-2002 | 0.55; 1.41; these are the min/max of 1999–2003 | OK | fred_BAA/AAA |
| 4 | Baa−Aaa 1929/32 | 1.00 Feb-1929 (low); 5.64 May-1932 | 1.00 / 5.64. Feb-1929 is the 1929 low; the cycle low was 0.86 (Mar-1928) | OK (M-1) | |
| 4 | NFI contribution | +1.18 (2000) / −0.99 (2001) | quarterly avg +1.18 [2.07,1.84,0.62,0.20]; −0.99 [−0.56,−1.20,−0.66,−1.56]; 1999 +1.13; 2002 −0.66 | OK | fred_A008RY2Q224SBEA |
| 4 | GSY ladder | 53%/76%/80%, uncond. 14% (table in notes_A §5: 168/34/20, 77/28/36, 40/21/53, 21/16/76, 15/12/80) | gsy.txt:1659-1667 Table 3 Panel A identical, incl. drawdowns −53/−54/−60/−60/−62; intl 237/85/36 … 51/34/67; unconditional 14% / 11% post-1970 / intl 24% (l.530-533) | OK | gsy.txt |
| 4 | Lucent 6-Jan-2000 −28% | — | Standard record (Lucent fell ~28% on 6-Jan-2000 after FQ1 warning); CNN URL not re-fetched; no contradiction | OK (not re-fetched) | — |
| 4 | WorldCom Jul-2002 vs recession end Nov-2001 | — | WorldCom Ch.11 21-Jul-2002; NBER trough Nov-2001 — standard chronology; +8 months as stated | OK | — |
| 4 | Nasdaq telecom peak 10-Mar-2000 vs BEA real comm-equipment peak Q4-2000 | — | NASDAQCOM peak 2000-03-10 5048.62, trough 2002-10-09 1114.11 (−77.9%); Richmond Fed text l.200: "From the first quarter of 1996 to the fourth quarter of 2000, investment in communications equipment grew from ~$62bn…" (Q4-2000 peak). Telecom sub-index date not independently re-fetched. | OK | fred_NASDAQCOM; richmondfed txt |
| 4 | KF-calc run-ups | Telcm +68%, Chips +228%, Util-1929 +195%, Oil-1980 +209% | 49-industry file: 68% / 228% / 195% / 209% | OK | eq_indep.py |
| 5 | BEA Y034RC1Q027SBEA | $933.9bn Q3-26, +40.8% yoy | 933.903; 663.284 a year earlier → +40.8% | OK | fresh FRED |
| 5 | Y034RY2Q224SBEA | 0.86 pp Q3-26 | 0.86 (Q2 0.19, Q3-25 0.30) | OK | |
| 5 | Census data center | $84.95bn SAAR Aug-26p, +73.2% yoy, +7.5% m/m; NSA $7.5bn; annual 8.5/12.6/20.0/34.8/49.7; Jan–Aug +41.7% | privsa.xlsx row "Data center": 84,950 / 79,007 / … / 49,052, 7.5, 73.2; privtime NSA Aug-26p 7,535 (Aug-25 4,312); annual 8.5/9.2/9.9/12.6/20.0/34.8/49.7; Jan–Aug 45.2 vs 31.9 = +41.7% | OK | census_priv*.xlsx |
| 5 | TSMC Sep-26 | NT$511.9bn, +54.6% yoy, YTD +41.1% | TWSE t187ap05_L row 2330: 511,857,399 (NT$ thousand), +54.65%, cumulative +41.11%, posted 1151017 | OK | twse_t187ap05_L.json |
| 5 | NVDA DSO / stakes | DSO 59.6d, DIO 119d, AR/rev 0.655, non-marketable equity $47.9bn | AR 63.059 / rev 96.221 × 91 = 59.6; inv 31.575 / COGS 24.079 × 91 = 119.3; 0.655; EquitySecuritiesWithoutReadilyDeterminableFairValueAmount 47.9 (series 1.3→3.8→8.2→22.3→42.3→47.9 matches) | OK | nvda_msft_check.py |
| 5 | MSFT RPO | $683bn Sep-26 | 683 (Jun-26 684); GOOGL 568; ORCL 664 | OK | |
| 5 | CBOE CRWV iv30 | 107 | 106.901 (2026-10-31 delayed quotes) | OK | cboe_CRWV.json |
| 6 | GSY Table 3/4 figures | per notes_C | Table 3 as above; Δvol 0.11, acceleration, issuance etc. not re-read line-by-line (Table 4 not in my 6) | OK (partial) | gsy.txt |
| 6 | GHSS 45% vs 4%, 8.99 / 26.6 | — | 45.3% (l.449), 4.0% unconditional (l.276), 8.99 (l.398), 26.56 (l.432), 13.3/4.5 (l.416-419), 63% (l.161), 6% (l.584), OOS R² 4.2 vs 6.7 and 4.5 vs 11.1 (l.684-692) | OK | ghss.txt |
| 6 | Baron–Xiong | +5.4 pp (3y), −11.4 pp, −37.3% | bx.txt:922 "2.7%, 3.3%, and 5.4%"; l.925 unconditional 8.0/13.9/19.3; l.1014 "3.2%, 6.0%, and 11.4%"; l.156-157 −17.9% (t −2.02), −37.3% (t −2.52) | OK | bx.txt |
| 6 | DVZ AUROC 0.76 | — | Source is a FEDS Note URL, not in raw/; not verifiable offline | NOT CHECKED | — |
| 6 | Goetzmann 6.9% / 17.2% | — | goetzmann txt l.48-49; 4.6%/9.8%/8.4% at l.79, 329 | OK | |
| 6 | Power table | 0.17/0.33/0.54/0.74 etc. | power_calc.txt matches every cell quoted in notes_C (incl. halves 0.22/0.70, pooled 0.40/0.73, 50/50 panel 0.52/0.88); power.py is a correct one-sided two-proportion simulation | OK | power_calc.txt |

## Findings

### BLOCKING
None. No headline number is wrong; no definition makes a headline claim false outright.

### SERIOUS
- **S-1 (finder B, notes_B.md §2a table and §Ranked list #1; scoping chart_capex_chain.py).** The Q3-26 group OCF of $198.6bn — and therefore capex/OCF 1.17 and "2026 YTD $563bn vs OCF $543bn" — includes **$11.363bn of customer prepayments "with significant financing component"** inside Oracle's FQ1 FY27 operating cash flow (orcl-ex99_1.htm, cash-flow statement line; FQ4 FY26 had $4.592bn). Oracle itself strips these in its "Net cash outlay for capital expenditures" reconciliation. These are customer-funded capex, i.e. financing of the build-out routed through OCF, exactly the thing the capex/OCF ratio is meant to expose. Corrected reads: Q3-26 ex-prepayments OCF 187.2 → capex/OCF **1.24**; Oracle alone 28.5/11.7 = **2.4x** (vs 1.23 as shown); 2026Q2 ratio 1.00 (vs 0.98). The notes mention Oracle's gross-vs-net capex guidance but never that OCF carries the prepayments. Fix: add an `ORCL_customer_prepay_in_ocf` column (text-extracted from ex-99.1; it is not a us-gaap tag) and show both ratios; at minimum footnote it on the chart's middle panel.
- **S-2 (scoping, earthquake_scoping.py:78,107; earthquake_variants.py:15,52; chart_earthquake.py:38 footer; summary.json "strict_gsy").** "GSY-strict (net ≥100%) n=21, crash 57%" and "Strict GSY rule … n=60, crash rate 53% = the paper's 53%" are **not GSY's rule**. The scoping defines net-of-market as (1+r_ind)/(1+r_mkt)−1 (ratio); GSY use the arithmetic difference r_ind − r_mkt (verified from Table 1 rows, gsy.txt:1520-1522). With GSY's definition on the same file: raw&net ≥100%, gap24 → n=129, crash 40%; adding GSY's 5-yr ≥50% and ≥10-firm filters → n=50, **40%**; finder C's exact rule → n=47, **40%** (n=21 and 57–62% only re-appear when the ratio definition is imposed). The "= the paper's 53%" line in the chart footer is therefore a coincidence of a stricter, non-standard screen and should be removed or restated as "40% (n≈47–50) under GSY's definition; 53% (n=60) under a stricter ratio-net screen". Note also that in the n=60 panel the corrections effect reverses (0 corr 60%, ≥2 corr 44%), and in the n=47 GSY-rule panel it restores (25% vs 53%): at this n the sign is not stable, which the write-up should say.
- **S-3 (finder C, notes_C.md §2 "Outcomes").** Pre-registered Y1 = "max drawdown from the t0 level over t0+1..t0+24" with Y2 = 1{Y1 ≤ −40%} labelled "GSY crash". GSY's crash is a 40% drawdown **from any point (running peak) within the two years after identification** (gsy.txt:348-349, 1493), which is what the scoping implements and what produces 53%. Measuring from the t0 level is a materially stricter outcome (prices peak on average 6 months AFTER identification, +30%). Either relabel Y1/Y2 or change to the running-peak definition before freezing the pre-registration.

### MINOR
- **M-1 (finder A §1.4, §6.2).** "Baa−Aaa 1.00pp (Feb-1929, low)": Feb-1929 is the low of calendar 1929; the cycle low was 0.86pp in Mar-1928. Say "1929 low".
- **M-2 (finder C §1.1).** GSY's own text is inconsistent on the 5-year filter: body says "50% or more raw return over the past five years" (gsy.txt:260); Table 1 caption says "100% raw return over the past five years" (l.1493); Table 3 caption says 50% (l.1644). Finder C uses 50%; state the inconsistency in the pre-registration.
- **M-3 (scoping chart_rzone.py footer).** "2000Q1 read +8.3 pp (just under the line)" holds for Z.1 total business debt; on the BIS NFC series the same quarter reads +8.5 pp and 2008Q4 +9.9 — still the same qualitative story, but "did not catch 2000" is series-dependent at the margin. Show both or say "borderline".
- **M-4 (finder B §2a).** The notes' Oracle column is labelled by calendar quarter with no flag that each ORCL value is a Jun–Aug / Sep–Nov / Dec–Feb / Mar–May quarter; chart footer says so, table does not.

### NOTE
- **N-1 (finder B).** Amazon's $77.3bn is gross "Purchases of property and equipment"; Amazon's own capex number ($75.9bn) nets $1.381bn of proceeds and incentives; 2026 guide "approximately $220 billion" of cash capex confirmed in the press release. Consistent with the notes; no error.
- **N-2 (finder B).** AMZN "capex" via PaymentsToAcquireProductiveAssets vs others' PPE tag is a label difference only (Amazon's single cash-flow line); fine.
- **N-3 (scoping).** count_corrections misses a drawdown of exactly 10.000% because of float (1−90/100 < 0.1). Irrelevant on real data; use `>= thr - 1e-12` if it bothers anyone. Monthly closes also miss intra-month corrections — a known limitation worth one sentence.
- **N-4 (scoping).** 4 of 408 episodes (triggered after 2024-09) have truncated 12–23-month horizons and are counted as full observations; immaterial to 25%.
- **N-5 (scoping chart_rzone).** FRED labels TBSDODNS "Millions, Seasonally Adjusted Annual Rate"; it is a seasonally-adjusted LEVEL (stock) — the chart's "quarterly, not SAAR" wording is right in substance but will look wrong to anyone who opens the FRED page. Say "seasonally adjusted level".
- **N-6 (scoping chart_rzone).** QUSNAM770A's FRED title says "Billions of US Dollars"; the data are % of GDP (29.1 in 1947Q4 … 72.2 in 2025Q4). Document that if the BIS series is added.
- **N-7 (scoping chart_earthquake footer).** The footer's "27 calendar clusters", "Spearman +0.76 sector vs market drawdown", "+0.75 corrections vs volatility", "cluster-bootstrap 90% CI 1.7 to 4.3 log-odds (size)", "zero-correction effect −0.6 to +0.8" all reproduce (27 clusters at a >12-month gap; 0.76; 0.75; multivariate logit raw24 [+1.6, +4.4], zero-corr [−0.5, +0.9] with a 2,000-draw cluster bootstrap) — but no script in scoping/code produces them. Save the code (footer_stats.py in review1/code reproduces them) so the figure is regenerable; and state the clustering gap (12m) since 24m gives 16 clusters and 36m gives 3.
- **N-8 (finder C).** DVZ AUROC 0.76 and the Greenwood–Hanson / LSZ / Krishnamurthy–Muir magnitudes are web/secondary-sourced and already flagged UNVERIFIED by the finder; not re-checked here.
- **N-9 (finder B).** Headline guidance quotes (AMZN ~$220bn confirmed from ex-99.1); the other four companies' guidance sentences were not re-read.
- **N-10 (scoping earthquake_variants.py:7).** exec-based reuse re-executes `RAW, OUT = sys.argv[1], sys.argv[2]` and the file-loading block; harmless, but a `from earthquake_scoping import …` split (loader module vs. run script) would avoid the string-split fragility (a future edit that moves the "W, H, GAP, RUNUP" line silently changes what gets exec'd).

## Stress summary (requested in check 2)
Corrections effect (0 vs ≥2 corrections ≥10% during the run-up → P(≥40% drawdown next 24m)), raw +100% panel:
base 23%→35% (n 149/113) | cooling 24m 21%→37% | cooling 12m 21%→39% | ≥10 firms 23%→30% (1-corr cell 13%, non-monotone) | net-of-market outcome 7%→24% | all three 7%→20%.
The sign "more corrections → more crashes" (i.e. AGAINST the earthquake hypothesis) survives every cut on the raw-100% panel, is entangled with volatility (Spearman 0.75) and reverses within the calm-volatility tercile (0 corr 14% vs ≥1 corr 3%, n=106/30) — exactly as the variants file shows. Under GSY's own episode rule (n≈47–50) the sign flips twice depending on the net definition; treat it as undetermined there.
