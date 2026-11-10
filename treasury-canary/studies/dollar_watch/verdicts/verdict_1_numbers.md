# Counter-agent verdict — numbers and data, dollar-as-crisis-predictor scoping

Reviewer: adversarial number/data verifier (did not write any of the material). Date 2026-11-02.
Method: fresh pulls (Yahoo DX-Y.NYB / GC=F / ^GSPC daily, FRED, BIS SDMX, OFR FSI, FMP XAUUSD) into `review1/raw/`; independent re-implementations in `review1/code/` (`check_dxy.py`, `check_A_band.py`, `check_A_crises_gold.py`, `check_C_real.py`, `check_B_leadlag.py`, `check_scoping.py`, `check_decel.py`, `check_misc.py`). Nothing outside `review1/` was touched.

## Top-line verdicts

| Unit | Verdict | One line |
|---|---|---|
| Finder A (event record, band test, gold, 2022 chain) | **PASS_WITH_FIXES** | Every headline number reproduces from the committed files and from a fresh pull. Fixes: the headline band edge (53%/76% vs 42%/69%) is computed on a padded 25-crisis list; on a 15- or 12-crisis systemic list the band is *below* base rate. Three mislabels (160.41 vs 164.72; "20 of 22"; 2022-08-28 is a Sunday). |
| Finder B (mechanism, BIS/FRED/OFR, lead-lag, re-dollarisation) | **PASS_WITH_FIXES** | All stock/flow numbers verified to the decimal on fresh pulls. Fix: the 2022 "CP−bill peak −87d" and "OFR funding peak −87d" rest on a single-day DCPF3M print (2022-07-01); excluding it the 2022 peak is 2022-03-04 (−206d). Growth rates labelled "%" are log-changes. |
| Finder C (literature numbers, synthetic DXY, band/momentum/quadrant) | **PASS_WITH_FIXES** | Synthetic DXY is the real ICE monthly average to within 0.05 pts (sd), so every C result survives on the real series. 16 of 17 paper numbers match the pdftotext extracts. Fixes: "DXY higher 3m after onset 8/16" is 7/16; BIS negative-growth episode mis-dated; momentum NSR degrades 0.42→0.51 on month-end closes. |
| Scoping (orchestrator: dollar_scoping.py, decel_test.py, decel_realtime.py) | **PASS_WITH_FIXES** | All tables and all 7 re-armed firings reproduce exactly (committed raw and fresh FRED). No look-ahead in the rules. Fix: the Shiller→FRED S&P splice uses a single-day value (S&P close 2023-09-01 = 4515.77) as the Sep-2023 "monthly average" (true mean 4409.1) — a 2.4% level error at the splice; no headline number changes. |

No BLOCKING findings. No headline number is wrong as stated on its own definition; the defects are label/window/basis and list-construction issues.

## Check table

| # | Item | Claimed | My check | Result | Source |
|---|---|---|---|---|---|
| 1.1 | DXY daily file = Yahoo DX-Y.NYB | 14,177 rows 1971-01-04..2026-11-02 | fresh pull 14,177 rows; 14,176 closes identical, only 2026-11-02 differs (101.742 vs 101.704 live) | PASS | `review1/raw/yahoo_dxy_1d.json` vs `finderA/data/dxy_daily.csv` |
| 1.2 | 2026-11-02 close 101.74 | 101.74 | 101.70 at pull time (intraday) | PASS (live) | same |
| 1.3 | 1985-02-25 peak ~164.7 | 164.72 | 164.72 close/high; all-time max | PASS | same |
| 1.4 | 2008-03-17 low 70.70 | 70.70 | intraday low 70.70 (close 71.46; min close 71.33 on 2008-04-22) | PASS (intraday) | same |
| 1.5 | 2022-09-27 close 114.11 / 09-28 intraday 114.78 | 114.1 / 114.78 | 114.11 / 114.78 | PASS | same |
| 1.6 | 2025-01-13 110.18 | 110.18 | intraday high 110.18 (close 109.96) | PASS (intraday) | same |
| 1.7 | 2026-01-27 low 95.55 | 95.55 | intraday low 95.55 (close 96.22) | PASS (intraday) | same |
| 1.8 | Finder C synthetic vs real monthly avg at checkpoints | Feb-85 158.4; Mar-08 72.4; Sep-22 110.7 | real avg 158.5 / 72.5 / 110.7; over 645 overlapping months mean diff 0.00, sd 0.05, max 0.4 (1985-09) | PASS — synthetic ≡ real | `check_C_real.py` |
| 1.9 | C band test on real series | 22 excursions, 9 (41%) vs 31% base | real avg: 22 / 9 (41%) / 31% identical; real month-end close: 25 / 10 (40%) / 31% | PASS | `check_C_real.py` |
| 1.10 | C momentum >+10% | NSR 0.42, P 48% vs 29% | real avg: 0.42 / 48% / 29% identical; real close: NSR 0.51, P 44%; >+15% close NSR 0.32 (vs 0.24) | PASS_WITH_FIX (basis-sensitive) | `check_C_real.py` |
| 2.1 | A base rates | 12m 42%, 24m 69%, in-window 48% | 0.422 (n=659), 0.694 (n=647), 0.478 | PASS | `check_A_band.py` |
| 2.2 | A merged excursions | 17; 9 within 12m; 13 within 24m | 17 / 9 / 13 | PASS | same |
| 2.3 | A speed table | 28/18/8 events; 13/5/0 hits | 28/18/8; 13/5/0 | PASS | same |
| 2.4 | A "12 of 25 raw excursions / 10 of 18 fast rises began inside a crisis" | 12/25, 10/18 (7/17 merged) | 12/25, 10/18, 7/17 | PASS | same |
| 2.5 | Same on strict 15-crisis list (drop C02 1976, C05 ContIll, C16 taper, C18 2018, C19 repo, C21 China prop, C23 SVB, C24 yen, C25 LibDay, C26 open) | — | base 12m 27% / 24m 52%; merged-17: 4/17 = 24% / 8/17 = 47%; speed ≥10%: 4/18; ≥15%: 0/8 | band BELOW base rate | same |
| 2.6 | Same on strict 12 (also drop ERM, 2014-16, 2022) | — | base 22% / 42%; merged-17: 2/17 = 12% / 6/17 = 35% | band BELOW base rate | same |
| 2.7 | Window alignment | excursion hit = start in [s, s+11]; base = start in (m, m+12] | strict (s+1..s+12): merged 8/17 (47%), 12/17 (71%); raw 11/25, 18/25; speed ≥15%: 1/8 (1993-02 → C10 1994-02) | MINOR | `check_misc.py` |
| 3.1 | "Dollar fell at peak stress in 9 of 25" | C04, C07, C08, C10, C12, C15, C23, C24, C25 | eve close → peak-stress close: −1.4, −5.0, −14.5, −14.3, −7.4, −3.3, −2.3, −3.9, −4.5; exactly these 9 | PASS | `check_A_crises_gold.py` |
| 3.2 | Gold GFC −32.9% | Mar-08 → 2008-10-24 | GC=F intraday high 1014.6 (2008-03-17) → intraday low 681.0 (2008-10-24) = −32.9%; close-to-close −29.7% (1003.2 → 704.9, 2008-11-13) | PASS (basis = intraday extremes, unlabelled) | same |
| 3.3 | Gold 2020 −14.7% | 03-09 → 03-16 | high 1701.6 → low 1452.1 = −14.7%; close-to-close −11.8% | PASS (intraday) | same |
| 3.4 | Gold 2022 −22.0% | Mar-22 → 2022-10-21 | high 2078.8 (03-08) → low 1621.1 (10-21) = −22.0%; episode low is actually 1618.3 on 2022-11-03 (−22.2%); close-to-close −20.2% | PASS (10-21 is the C22 window end, not the trough) | same |
| 3.5 | Gold dotcom −16.2% monthly | 1999-10 310.7 → 2001-04 260.5 | 310.72 → 260.48 = −16.2% | PASS | same |
| 3.6 | Gold 2026 −30.6% | 5,586 (01-29) → 3,879 (10-30) | fresh GC=F: intraday 5586.2 → 3879.3 = −30.6%; close-to-close 5318.4 → 3898.9 = −26.7%. FMP XAUUSD spot: intraday 5602.2 (01-29) → 3870.3 (10-30) = −30.9%; close 5418.5 (01-28) → 3875.6 = −28.5%. Spot confirms; not a roll artefact. 2026-01-29 was a one-day spike (range 5097–5586; 01-30 close −10.8%) | PASS; FMP key present and used | `review1/raw/gc_daily_fresh.csv`, `raw/fmp_xauusd_2026.json` |
| 3.7 | 2022 chain | +12.5% six months after 2022-02-28; +18.0% to 09-27 | 96.71 → 108.80 (2022-08-26 close) = +12.5%; → 114.11 = +18.0%; → 113.32 (10-12) = +17.2%; 2021-06-01 → freeze +7.7% | PASS; chain row dated 2022-08-28 (Sunday) carries the Fri 08-26 close | same |
| 3.8 | "fell 10% into December" | −10% | 114.11 → 103.52 (12-30) = −9.3% | MINOR rounding | same |
| 4.1 | BIS GLI Q.USD.3P.N.A.I.B.USD | $15.13tn 2026Q2, +8.1% yoy | 15,132,724 $m; yoy +8.07%; 2022Q2 13.306; 2008Q3 6.075; 2009Q1 5.839; 2024Q4 yoy +2.89% | PASS | `review1/raw/bis_gli.csv` |
| 4.2 | EMEs | $4.60tn +8.7% | 4,599,223 $m; +8.70% | PASS | `raw/bis_gli_eme.csv` |
| 4.3 | BIS OTC FX fwds+swaps+ccy swaps | $129.3tn end-2025; USD leg $113.5tn; 2022-S1 $97tn/$85tn | 129,301,929 / 113,496,917 $m; 2022-S1 96.6 / 85.5; 2016-S2 67.2 | PASS | `raw/bis_otc_*.csv` |
| 4.4 | SWPT | $156m 2026-10-28; $583bn 2008-12-17; $449bn 2020-05-27; $109bn 2012-02-15; $11.3bn 2022-10-26 | 156; 583,135; 448,946; 109,088; 11,302 $m | PASS | `raw/fred_SWPT.csv` |
| 4.5 | CP−bill | 0.05pp 2026-10-29; 5th pct all / 14th 10y | 4.05 − 4.00 = 0.05; 5.0% / 14.4% | PASS | `raw/fred_DCPF3M.csv`, `fred_DTB3.csv` |
| 4.6 | CP−bill peaks | 2008-10-15 (−139d); 2022-07-01 (−87d) | 3.73 on 2008-10-15, broad-$ peak 2009-03-03 → −139d ✓; 1.11 on 2022-07-01 vs 2022-09-26 → −87d ✓ BUT 07-01 is a one-day print (DCPF3M 2.25 → 2.77 → 2.14; DTB3 flat 1.66); excluding it the 2022 peak is 0.79 on 2022-03-04 (−206d). OFR funding also peaks 2022-07-01 (same input) | PASS_WITH_FIX | `check_B_leadlag.py` |
| 4.7 | OFR funding alarms (first day > trailing-5y 95th pct) | 2007-08-09; 2022-03-04 | 2007-08-09 (1.339 > 0.335); 2022-03-04 (0.179 > −0.085); peak 9.58 on 2008-10-10 ✓ | PASS | `raw/ofr_fsi.csv` |
| 4.8 | Gold trough 2008 −111d | 2008-11-12, 1003 → 712 | GC=F close trough 2008-11-13 704.9 (−110d), −29.7%; B used FMP spot (−1 day) | PASS (±1d basis) | same |
| 4.9 | Re-dollarisation regression | 9.5% vs 4.8%; corr −0.50 (−0.55 $ leading 1q) | from johnson_quarterly.csv: 9.46 (n=50) vs 4.80 (n=52); −0.503 / −0.552; fresh rebuild from BIS + TWEXBMTH/TWEXBGSMTH splice: identical. Values are 100×log-diff; simple-% equivalents 10.1 vs 5.0 | PASS (label fix) | same |
| 4.10 | Negative-yoy quarters | B: 2009Q1–Q3, 2022Q3–2023Q4 | 2009Q1 −1.0, Q2 −2.1, Q3 −1.5; 2022Q3 −2.7 … 2023Q4 −0.4 (seven quarters) | B PASS; C's "2022Q3–2023Q1" wrong | `check_misc.py` |
| 5.1 | Scoping headline all months | n=627; 0.10 / 0.12 / 0.12 | 627; 0.10 / 0.12 / 0.12 | PASS | `check_scoping.py` |
| 5.2 | 6m rise ≥15% | n=12; 0.17 / 0.50 / 0.25 | 12; 0.17 / 0.50 / 0.25 (months: 1974-01, 1981-05..08, 1993-02, 2008-10/11, 2009-01, 2015-01..03) | PASS | same |
| 5.3 | Band groups | >105 n=126 dd20 0.20; in-band n=386 0.06; <85 n=115 0.12 | identical | PASS | same |
| 5.4 | Quintiles / quadrants / speed falls | as in dollar_summary.json | all identical to 2 dp | PASS | same |
| 5.5 | dxy_spliced column | finder A dxy_avg | max abs diff 0.0 | PASS | same |
| 5.6 | Shiller month decoding (.1 = Oct) | — | 1987.1 → Oct-87 280.2 (Sep 318.7, Nov 245.0); 2009.03 → Mar-09 757.13 — correct monthly averages | PASS | same |
| 5.7 | S&P splice continuity | Shiller to 2023-09 then FRED mean | Shiller 2023-09 = 4515.77 = S&P **close on 2023-09-01** (single day); FRED Sep-23 monthly mean 4409.1; Jun–Aug 2023 Shiller = FRED to 0.1. Splice creates a +2.4% level spike then −5.5% Sep→Oct (true −3.2%) | SERIOUS (data), no headline change | same; `raw/yahoo_gspc_1d.json` |
| 5.8 | Real-time turn look-ahead | first month ≤ 3% below trailing 6m high after trigger | D[k] ≤ 0.97·max(D[k−6..k]); backward-looking only; all 12 turns reproduced | PASS | same |
| 5.9 | decel_realtime 7 re-armed firings | 2008-09-22, 2008-11-06, 2010-06-03, 2011-11-01, 2012-06-07, 2020-04-09, 2022-07-28 | identical dates, roc max, levels, further rise (17.7/6.5/1.1/4.4/0.5/1.4/5.2%), VIX60 (+13.5/−20.3/−5.0/−15.3/−4.2/−12.2/+7.5), SPX60 (+12.7%/−6.8%) on committed raw AND fresh FRED | PASS | `check_decel.py` |
| 5.10 | decel_realtime uses future data? | — | all conditions use indices ≤ k; forward fields labelled as outcomes. Caveat: DTWEXBGS is published with ~1-week lag (H.10), so "real-time daily" is ≈ T+5 business days in practice | PASS (NOTE) | same |
| 5.11 | decel_test monthly 2008 / 2022 | ROC 2008-10, $ peak 2009-02, S&P trough 2009-03; ROC 2022-05, $ peak 2022-10 | identical; rise after 4.1% / 8.5% | PASS | same |
| 5.12 | decel_test daily 2008 | ROC20 peak 2008-10-24, 12.3%, VIX 2008-11-20, $ peak 2009-03-03, +4.1% | reproduced on decel_test's calendar (DTWEXBGS∩VIX). On decel_realtime's calendar (∩DGS10, drops 2008-10-13 Columbus Day) the same quantity is 2008-10-27, 12.9%, +3.6% — the two scoping scripts disagree by one trading day | PASS (NOTE) | same |
| 6.1 | Obstfeld–Zhou −1.5% at ~8q | | `obstfeld_zhou_bpea.txt:971` "trough of about −1.5 percent … after about eight quarters" | PASS | grep |
| 6.2 | Hofmann–Park −0.3 / −0.6 ppt | | `:13`, `:280-281` | PASS | grep |
| 6.3 | ADKS −2.6bp per 1ppt | | `:508` 2.6 bp; Table −2.641 / −2.080 `:524` | PASS | grep |
| 6.4 | Bruno–Shin −0.22 | | `:1529` RER −0.2204*** | PASS | grep |
| 6.5 | DCP −0.6%, −0.19 / −0.03 | | `:65`, `:316-318` | PASS | grep |
| 6.6 | KLR REER NSR 0.19 / called 0.57 / P 0.67; exports 0.42/0.85; US rate 0.97; oil 0.99; G-7 0.58 | | Edison Table 5 `:2182-2183`, `:2226-2229` | PASS | grep |
| 6.7 | Bussière–Fratzscher 82.4 / 57.8 / 57.3 / 42.7 / 7.7; BBP 59.8 / 70.3 / 29.7 | | `:711-715`, `:728-730` | PASS | grep |
| 6.8 | Gourinchas–Obstfeld +11.5 / 6.4 / 9.4; −4.3 / 4.7 / 2.5; RER sd 19.99 | | `:1140-1145`, `:1903` | PASS (paper says "percent", C says "pp" — same meaning here) | grep |
| 6.9 | Catão–MF AUROC 0.73 → 0.90 | | `:981`, `:1025`, `:1030-1036` | PASS | grep |
| 6.10 | BMM $97 / 85 / 26 / 39tn (abstract 25 / 35) | | `:93`, `:99`, `:60-62`, `:12-13` | PASS | grep |
| 6.11 | DTV 24 / 27bp | | `:125-126` | PASS | grep |
| 6.12 | Bahaj–Reis 0.28 / 0.59pp | | `:1226`, `:1230` | PASS | grep |
| 6.13 | Granger F DXY→VIX 0.05 / 0.12 / 0.64; VIX→DXY 3.71 | | on real avg: 0.06 / 0.12 / 0.65; 3.65 | PASS | `check_misc.py` |
| 6.14 | Quadrant 9/16 USD↑+10y↓; 5/16 USD↓ | | real avg: 9 / 2 / 3 / 2 (USD↓ = 5) identical; on month-end close: 7 / 3 / 2 / 4 (USD↓ = 6) | PASS (avg basis) | `check_C_real.py` |
| 6.15 | "DXY higher 3m after onset in 8/16; gold lower in 5/16" | 8/16; 5/16 | 7/16 (1974, 1982, 1992, 2001, 2008, 2015, 2018) on both synthetic and real avg; gold 5/16 ✓ | 8/16 → **7/16** | `check_misc.py` |

## Findings, ranked

### BLOCKING
None.

### SERIOUS (right number, wrong label / window / list)

S1. **Finder A: the headline band edge is computed on a padded crisis list and disappears or reverses on a systemic list.** `finderA/notes_A.md` §3 / "Five facts" #1 reports 53% / 76% vs 42% / 69%. The 25-crisis list includes C02 (1976 sterling/lira), C05 (Continental Illinois, one US bank), C16 (taper tantrum), C18, C19 (one-day repo spike), C21 (China property, a 26-month window that wholly contains C22 and C23), C23, C24 (yen carry, 2 months), C25 (Liberation Day, 2 months), C26 (open; every month to 2026-11 counted "in crisis"). Crisis windows cover 321/671 months; 17 months sit in two windows at once (C03/C04, C21/C22, C21/C23). On the 15 episodes that are systemic/multi-country (C01 C03 C04 C07 C08 C09 C10 C11 C12 C13 C14 C15 C17 C20 C22): base 27% / 52%, merged-17 band 24% / 47% — **below** base. On 12 (also dropping ERM, 2014-16, 2022): base 22% / 42%, band 12% / 35%. The qualitative conclusion ("no edge") is robust and strengthens; the quoted 53%/42% pair should not be shown without the strict-list pair beside it. Suggested text: "outside 85-105 → crisis start within 12m: 53% (25-crisis list, base 42%); 24% (15 systemic, base 27%); 12% (12 systemic, base 22%)". File: `notes_A.md` §3 table and "Five facts" #1; `data/crises.csv`.

S2. **Finder B: the 2022 lead of −87d for CP−bill and OFR funding is a one-observation artefact.** DCPF3M prints 2.25 (06-30) → 2.77 (07-01) → 2.14 (07-05) with DTB3 flat at 1.66; the 1.11pp "peak" exists on one day. Excluding it, the 2022 CP−bill maximum is 0.79 on 2022-03-04 (−206d before the 2022-09-26 broad-dollar peak) — i.e. the 2022 "funding stress" peaked at the invasion, not in July. OFR's Funding sub-index peaks the same day (0.34) because it ingests the same CP input. `notes_B.md` §0 item 3, §2 table rows "Fin CP − bill" and "OFR funding", §3 table "Funding normalised 2022-07-05". Fix: report the 2022 lead as "−206d (−87d on a single-day print)" or smooth with a 5-day mean before taking extrema.

S3. **Scoping: S&P splice carries a single-day value as a monthly average.** `scoping/code/dollar_scoping.py:43-51`: Shiller's last row (2023.09) is 4515.77, which is the S&P close on 2023-09-01, not the September mean (FRED mean 4409.1). Jun–Aug 2023 Shiller equals FRED to 0.1, so the file's last row is a partial month. Effect: `out/dollar_monthly.csv` spx_shiller 2023-09 is +2.4% too high; the Sep→Oct 2023 drop is −5.5% instead of −3.2%. No group statistic changes (the 2023 drawdown is ~10%, far from the 20% threshold) and `decel_test.py` monthly S&P troughs are unaffected, but it is a wrong level in a published series. Fix: `if m not in spx or m >= "2023-09": spx[m]=v` (prefer FRED from 2023-09), or drop Shiller's final row.

### MINOR (rounding / presentation / basis unlabelled)

M1. `notes_A.md` §3 last paragraph: "peak 160.41 on 1985-02-25" — 160.41 is the Feb-1985 **monthly close** (1985-02-28); the 1985-02-25 close/high is 164.72 (correctly quoted in §0 and §6). Write "monthly close 160.41 (Feb-1985); daily peak 164.72 on 1985-02-25".

M2. `notes_A.md` §2: "in 20 of 22 datable episodes the DXY monthly peak came before the end month" — `crises_metrics.csv` column `dxy_peak_before_end` gives yes for 21 of 24 closed crises (no: C04, C05, C23, all "peak at end month"); C26 is open and should be excluded. Write "21 of 24".

M3. `data/chain_2022.csv` row "2022-08-28 Six months after the reserve freeze … 108.80": 2022-08-28 is a Sunday; 108.80 is the 2022-08-26 (Fri) close. Label the row 2022-08-26 (or 08-29, 108.84, +12.5% either way).

M4. `notes_A.md` §4/§2: gold drawdowns "−32.9 / −14.7 / −22.0 / −30.6 daily" are **intraday high → intraday low** on the GC=F front month; close-to-close they are −29.7 / −11.8 / −20.2 / −26.7. The intraday basis is defensible (it is what "peak-to-trough" means on a chart) but must be stated, because the 2026 figure is quoted beside finder B's −27% (FMP close basis) and the two look contradictory. Also "2022-03 → 2022-10-21" is the C22 window end, not the gold trough (1618.3 on 2022-11-03, −22.2%).

M5. `notes_A.md` §0 headline "6m +3.3% (from 98.47)": 98.47 is the 2026-05-04 close; the exact 6-month-ago date (2026-05-02 → prior close 2026-05-01, 98.21) gives +3.6%. Immaterial; state the anchor date. Finder B's "+0.6% / +3.5% (Yahoo monthly)" for the same quantity disagrees with A's daily numbers (6m ≈ +3.3–3.6%, 12m ≈ +1.9–2.0%) — B's monthly-bar derivation is the wrong one; use A's.

M6. `notes_A.md` §5: "fell 10% into December" → −9.3% (114.11 → 103.52 on 2022-12-30).

M7. Finder A window alignment: excursion/speed hits count a crisis starting in [s, s+11] (same-month inclusive) while the base rate counts (m, m+12]. On the strict (s+1..s+12) alignment: merged 8/17 (47%) and 12/17 (71%) (the 1976-03 excursion starts in the same month as C02); speed ≥15%: **1/8** (1993-02 run → C10 1994-02 at exactly +12m), not 0/8. The "zero crisis starts after the 8 fastest rises" line in "Five facts" #3 is therefore knife-edge; say "0–1 of 8 depending on window alignment".

M8. `notes_B.md` §1(g) and §0 item 6: "9.46% / 4.80% yoy" and "+2.25% / +1.28% qoq" are 100×log-differences, not simple growth rates (simple: 10.1% / 5.0% yoy). Label as log-growth or convert.

M9. `notes_C.md` §0 item 5 and §4 fact 3: "DXY was higher 3 months after onset in 8/16" → **7/16** (positives: 1974, 1982, 1992, 2001, 2008, 2015, 2018) on both the synthetic and the real monthly average, using C's own definition. Gold lower in 5/16 is correct.

M10. `notes_C.md` §1.9: "USD credit growth went NEGATIVE only in 2008Q3+4q (−1.5%) and 2022Q3–2023Q1 (−2.7%, −5.5%)" — actual negative-yoy quarters are 2009Q1 −1.0, Q2 −2.1, Q3 −1.5 and 2022Q3 −2.7, Q4 −4.8, 2023Q1 −5.5, Q2 −3.9, Q3 −2.1, Q4 −0.4 (seven quarters, not three). Finder B has it right.

M11. `notes_C.md` §2 momentum table and §4 fact 2 are on the **monthly-average** series. On month-end closes (what a trader sees) the >+10% signal is NSR 0.51, P 44% (vs 0.42 / 48%), and >+15% is NSR 0.32 / 55% (vs 0.24 / 62%); quadrant counts become 7 / 3 / 2 / 4. Still "KLR-grade", but the basis should be stated and the close-basis numbers shown as the robustness row.

M12. `notes_C.md` §3.5: "DXY peaks … Apr-2020 (1 month BEFORE the swap peak)" — on monthly average, Apr-2020 (99.9) is indeed above Mar-2020 (98.8); on daily data the peak is 2020-03-20 (102.82) and on month-end close it is March (99.05). Say which basis; the daily peak is the one every other unit uses.

### NOTE (recorded, no action required)

N1. Finder C's "synthetic" DXY is not an approximation: the ICE DXY is exactly the geometric basket C rebuilt (10 legacy currencies pre-1999, 6 post-1999), so the monthly average of the real index and the index of FRED monthly-average bilaterals coincide to sd 0.05 pts. All of C's price-based results are therefore results on the real monthly-average DXY; C's open question 5 ("what is the right real-time DXY?") is answered by finder A's daily file.

N2. Scoping `dollar_scoping.py` triggers on the monthly **average** of month t and measures forward returns from the Shiller monthly average of month t; both are known only after month end, so "forward 12m from trigger" starts ~half a month before the signal is observable. Half-month look-ahead; direction of bias is small and towards the signal. The `speed_episodes` ex-post peak is correctly labelled ex post; the real-time turn is clean.

N3. Scoping `excursions` in `dollar_summary.json` (21 raw runs) are on the monthly average; finder A's 25 raw / 17 merged are on month-end closes. Not a conflict, but the orchestrator should not mix the two counts in one sentence.

N4. `decel_test.py` daily (calendar DTWEXBGS∩VIX) and `decel_realtime.py` (∩DGS10) disagree on the 2008 ROC20 peak by one trading day (10-24 12.3% / +4.1% vs 10-27 12.9% / +3.6%) because DGS10 is missing on 2008-10-13 (Columbus Day). Pick one calendar for the chart and the text.

N5. DTWEXBGS is an H.10 weekly release (~T+3 to T+7 business days); the "real-time" deceleration rule cannot be evaluated same-day. ICE DXY daily (finder A) could, but the rule was built on the Fed broad index; a DXY re-run is the obvious next step and was not done.

N6. Finder B's gold trough 2008-11-12 ($712, FMP spot) vs GC=F 2008-11-13 ($704.9) — one-day basis difference (spot London vs COMEX settle); the −111d/−110d lead is unaffected.

N7. 2026 gold: GC=F and FMP XAUUSD agree (intraday −30.6% vs −30.9%; close −26.7% vs −28.5%); the 2026-01-29 high is a genuine one-day spike (intraday range 5097–5586 on the futures; 5097–5602 spot) followed by a −10.8% close-to-close day. Any "peak-to-trough" that starts from that print should say so.

N8. Finder A's Spearman "+0.27" between DXY eve→peak-stress rise and S&P max drawdown is −0.273 (p = 0.19) when drawdowns are signed negative, i.e. the same weak relationship in the direction "bigger dollar rise ↔ deeper drawdown". Sign convention only.

N9. Scoping `current` month is 2026-09 (GS10/BAA monthly end there) while finder A runs to 2026-11-02; the scoping d6/d12 (+0.6% / +2.4%) are monthly-average figures, not the daily +3.3–3.6% / +1.9–2.0%.

## Re-stated corrected headline block (for the orchestrator)

- ICE DXY 101.70–101.74 (2026-11-02 live); 6m +3.3–3.6%, 12m +1.9–2.0% (daily closes).
- Band outside 85-105, merged excursions 17: crisis start ≤12m 53% (25-crisis list; base 42%) | 24% (15 systemic; base 27%) | 12% (12 systemic; base 22%). ≤24m 76% | 47% | 35% vs 69% | 52% | 42%. **No edge on any list; negative on the strict lists.**
- Fast rises ≥15%/6m (n=8): 0–1 crisis starts within 12m depending on window alignment; 6 of 8 began inside a crisis window.
- Dollar fell eve→peak-stress in 9/25 (verified). Gold intraday peak-to-trough: GFC −32.9%, 2020 −14.7%, 2022 −22.0% (to the window end; −22.2% to the 11-03 trough), dotcom −16.2% monthly, 2026 −30.6% (close basis −26.7%; spot confirms).
- BIS USD credit to non-banks ex-US $15.13tn 2026Q2 +8.1% yoy (EMEs $4.60tn +8.7%); FX swaps/fwds $129.3tn (USD leg $113.5tn) end-2025; SWPT $156m; CP−bill 0.05pp (5th pct). All verified on fresh pulls.
- Re-dollarisation: USD-credit log-growth 9.5% when $ down yoy vs 4.8% when up (simple 10.1% vs 5.0%); corr −0.50 / −0.55 with $ leading 1q. Verified from a fresh rebuild.
- 2022 funding-stress lead over the dollar peak: −139d (2008, robust); 2022 −206d on a smoothed series, −87d only on the 2022-07-01 single-day print.
- Scoping tables and all 7 deceleration firings reproduce exactly; fix the S&P splice at 2023-09 before publishing the series.
